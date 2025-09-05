"""Main device agent implementation."""

import json
import yaml
import threading
import signal
import time
import importlib.util
import os
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from paho.mqtt.client import Client, MQTTMessage

from lab_agent.common import (
    jdump, now_iso, t_device_meta, t_device_status, t_device_cmd, t_device_evt,
    t_module_status, t_module_cmd, t_module_cfg, t_module_evt, parse_json, validate_envelope,
    make_ack, deep_merge, MAX_PARAMS_BYTES
)


class DeviceAgent:
    """Device agent for Lab Platform.

    - Loads configuration from environment variables and .env file
    - Dynamically loads modules from features/
    - Connects to the MQTT broker
    - Subscribes for per-module commands and config updates
    - Publishes meta, device status, and module status/acks
    """
    
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.device_id = cfg["device_id"]
        self.labels = cfg.get("labels", [])
        self.modules: Dict[str, Any] = {}
        self._module_classes: Dict[str, Any] = {}
        
        # Initialize MQTT client
        self.client = Client(client_id=f"device-{self.device_id}", clean_session=True)
        self.heartbeat_interval_s = int(cfg.get("heartbeat_interval_s", 10))
        self._hb_stop = threading.Event()
        
        # Load modules and setup MQTT
        print(f"Initializing agent for device: {self.device_id}")
        self._load_modules()
        self._setup_mqtt()

    def _load_modules(self):
        """Load modules from configuration and features directory."""
        try:
            # First load available module classes from features directory
            self._discover_feature_modules()
            
            # Then instantiate configured modules
            modules_cfg = self.cfg.get("modules", {})
            if not isinstance(modules_cfg, dict):
                modules_cfg = {}
                
            for module_name, module_config in modules_cfg.items():
                self._load_module(module_name, module_config or {})
                
            print(f"Loaded {len(self.modules)} modules: {list(self.modules.keys())}")
        except Exception as e:
            print(f"Warning: Failed to load modules: {e}")

    def _discover_feature_modules(self):
        """Discover and load module classes from features directory."""
        features_dir = self._find_features_directory()
        if not features_dir:
            print("No features directory found - modules will not be available")
            return
            
        print(f"Discovering modules in: {features_dir}")
        modules_dir = features_dir / "modules"
        
        if not modules_dir.exists():
            print(f"No modules directory found in {features_dir}")
            return
            
        for module_dir in modules_dir.iterdir():
            if module_dir.is_dir():
                self._load_module_class(module_dir)
                
    def _find_features_directory(self) -> Optional[Path]:
        """Find the features directory from various locations."""
        # Check environment variable first
        features_path = os.getenv("FEATURES_PATH")
        if features_path:
            features_dir = Path(features_path).resolve()
            if features_dir.exists():
                return features_dir
            print(f"FEATURES_PATH specified but not found: {features_dir}")
        
        # Search common locations
        search_paths = [
            Path.cwd() / ".." / "features",  # Parent directory
            Path.cwd() / "features",         # Current directory
            Path(__file__).parent.parent.parent.parent / "features",  # Repo root
            Path.home() / "lab-features",    # User home
            Path("/opt/lab-platform/features"),  # System
        ]
        
        for path in search_paths:
            if path.exists() and path.is_dir():
                return path
                
        return None
        
    def _load_module_class(self, module_dir: Path):
        """Load a single module class from directory."""
        manifest_file = module_dir / "manifest.yaml"
        if not manifest_file.exists():
            return
            
        try:
            with open(manifest_file) as f:
                manifest = yaml.safe_load(f)
                
            module_name = manifest.get("name")
            module_file = manifest.get("module_file", "module.py") 
            class_name = manifest.get("class_name")
            
            if not all([module_name, class_name]):
                print(f"Invalid manifest in {module_dir}: missing name or class_name")
                return
                
            module_path = module_dir / module_file
            if not module_path.exists():
                print(f"Module file not found: {module_path}")
                return
                
            # Load the Python module
            spec = importlib.util.spec_from_file_location(
                f"features.modules.{module_name}", module_path
            )
            if not spec or not spec.loader:
                print(f"Failed to create spec for {module_name}")
                return
                
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            if hasattr(module, class_name):
                self._module_classes[module_name] = getattr(module, class_name)
                print(f"Loaded module class: {module_name}")
            else:
                print(f"Class {class_name} not found in {module_path}")
                
        except Exception as e:
            print(f"Failed to load module from {module_dir}: {e}")
            
    def _load_module(self, module_name: str, module_config: Dict[str, Any]):
        """Load and instantiate a specific module."""
        module_class = self._module_classes.get(module_name)
        if not module_class:
            print(f"Warning: Module class '{module_name}' not found")
            return
            
        try:
            self.modules[module_name] = module_class(self.device_id, module_config)
            print(f"Initialized module: {module_name}")
        except Exception as e:
            print(f"Failed to initialize module {module_name}: {e}")

    def _get_module_class(self, module_name: str):
        """Get module class by name."""
        return self._module_classes.get(module_name)

    def _setup_mqtt(self):
        """Configure and connect to MQTT broker."""
        mqtt_cfg = self.cfg["mqtt"]
        
        # Set credentials
        self.client.username_pw_set(mqtt_cfg.get("username"), mqtt_cfg.get("password"))
        
        # Configure Last Will and Testament (offline message)
        offline_msg = {"online": False, "ts": now_iso(), "device_id": self.device_id}
        self.client.will_set(
            t_device_status(self.device_id), 
            jdump(offline_msg), 
            qos=1, 
            retain=True
        )
        
        # Set callbacks
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        
        # Connect to broker
        host = mqtt_cfg.get("host", "localhost")
        port = mqtt_cfg.get("port", 1883)
        print(f"Connecting to MQTT broker at {host}:{port}...")
        
        try:
            self.client.connect(host, port, keepalive=60)
        except Exception as e:
            raise ConnectionError(f"Failed to connect to MQTT broker at {host}:{port}: {e}")

    def start(self):
        """Start the agent and begin processing."""
        print(f"Starting agent for device: {self.device_id}")
        
        # Start MQTT network loop
        self.client.loop_start()
        
        # Wait a moment for connection
        time.sleep(0.5)
        
        # Start heartbeat thread
        heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, 
            name="heartbeat", 
            daemon=True
        )
        heartbeat_thread.start()
        
        print(f"Agent started successfully with {len(self.modules)} modules")

    def _pub(self, topic: str, payload: Dict[str, Any], qos: int = 1, retain: bool = False) -> None:
        """Publish JSON payload to MQTT topic."""
        self.client.publish(topic, json.dumps(payload), qos=qos, retain=retain)

    def _heartbeat_loop(self):
        """Heartbeat loop to maintain device status."""
        while not self._hb_stop.wait(self.heartbeat_interval_s):
            self.publish_device_status({"online": True, "device_id": self.device_id})

    def shutdown(self):
        """Shutdown the agent gracefully."""
        # Stop heartbeat and best-effort offline publish
        self._hb_stop.set()
        try:
            self.publish_device_status({"online": False, "device_id": self.device_id})
            time.sleep(0.2)
        except Exception:
            pass
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass

    def _subscribe_module_topics(self, mname: str) -> None:
        """Subscribe to module-specific MQTT topics."""
        self.client.subscribe(t_module_cmd(self.device_id, mname), qos=1)
        self.client.subscribe(t_module_cfg(self.device_id, mname), qos=1)

    def _unsubscribe_module_topics(self, mname: str) -> None:
        """Unsubscribe from module-specific MQTT topics."""
        self.client.unsubscribe(t_module_cmd(self.device_id, mname))
        self.client.unsubscribe(t_module_cfg(self.device_id, mname))

    def _on_connect(self, client, userdata, flags, rc):
        """Handle MQTT connection events."""
        if rc == 0:
            print("Connected to MQTT broker")
            
            # Subscribe to device command topic
            self.client.subscribe(t_device_cmd(self.device_id), qos=1)
            
            # Subscribe to module topics and notify modules
            for module_name, module in self.modules.items():
                self._subscribe_module_topics(module_name)
                try:
                    if hasattr(module, "on_agent_connect"):
                        module.on_agent_connect()
                except Exception as e:
                    print(f"Error notifying module {module_name} of connection: {e}")
                    
            # Publish initial status messages
            self.publish_meta()
            self.publish_device_status({"online": True})
            
            # Publish module statuses
            for module_name, module in self.modules.items():
                try:
                    self.publish_module_status(module_name, module.status_payload())
                except Exception as e:
                    print(f"Error publishing status for module {module_name}: {e}")
        else:
            print(f"Failed to connect to MQTT broker (code: {rc})")
            
    def _on_disconnect(self, client, userdata, rc):
        """Handle MQTT disconnection events."""
        if rc != 0:
            print("Unexpected disconnection from MQTT broker")
        else:
            print("Disconnected from MQTT broker")

    def publish_meta(self):
        """Publish device metadata."""
        meta = {
            "device_id": self.device_id,
            "modules": list(self.modules.keys()),
            "capabilities": {m: self.modules[m].cfg for m in self.modules},
            "labels": self.labels,
            "version": "dev-0.1.0",
            "ts": now_iso()
        }
        self.client.publish(t_device_meta(self.device_id), jdump(meta), qos=1, retain=True)

    def publish_device_status(self, extra: Dict[str, Any] | None = None):
        """Publish device status."""
        payload = {"online": True, "ts": now_iso(), "device_id": self.device_id}
        if extra: 
            payload.update(extra)
        self.client.publish(t_device_status(self.device_id), jdump(payload), qos=1, retain=True)

    def publish_module_status(self, mname: str, status: Dict[str, Any]):
        """Publish module status."""
        self.client.publish(t_module_status(self.device_id, mname), jdump(status), qos=1, retain=True)

    def _on_message(self, client: Client, userdata, msg: MQTTMessage):
        """Handle incoming MQTT messages."""
        topic = msg.topic
        
        try:
            # Parse JSON payload
            payload_ok, payload, parse_error = parse_json(msg.payload)
            if not payload_ok:
                print(f"Invalid JSON in message on {topic}: {parse_error}")
                return
                
            # Handle device-level commands
            if topic == t_device_cmd(self.device_id):
                self._handle_device_command(payload)
                return
                
            # Handle module-level commands and config
            for module_name, module in self.modules.items():
                if topic == t_module_cmd(self.device_id, module_name):
                    self._handle_module_command(module_name, module, payload)
                    return
                elif topic == t_module_cfg(self.device_id, module_name):
                    self._handle_module_config(module_name, module, payload)
                    return
                    
        except Exception as e:
            print(f"Error handling message on {topic}: {e}")
            
    def _handle_device_command(self, payload: Dict[str, Any]):
        """Handle device-level commands."""
        # Validate envelope
        envelope_ok, validation_error = validate_envelope(payload)
        event_topic = t_device_evt(self.device_id)
        
        if not envelope_ok:
            ack = make_ack(
                payload.get("req_id", "?"), 
                False, 
                payload.get("action", "?"), 
                payload.get("actor"), 
                code="BAD_REQUEST", 
                error=validation_error
            )
            self._pub(event_topic, ack)
            return
            
        action = payload["action"]
        params = payload["params"]
        req_id = payload["req_id"]
        actor = payload.get("actor")
        
        try:
            success, error_msg, details = self.handle_device_cmd(action, params)
            code = "OK" if success else "DEVICE_ERROR"
            ack = make_ack(req_id, success, action, actor, code=code, error=error_msg, details=details)
            self._pub(event_topic, ack)
        except Exception as e:
            ack = make_ack(req_id, False, action, actor, code="EXCEPTION", error=str(e))
            self._pub(event_topic, ack)
            
    def _handle_module_command(self, module_name: str, module: Any, payload: Dict[str, Any]):
        """Handle module-level commands."""
        envelope_ok, validation_error = validate_envelope(payload)
        event_topic = t_module_evt(self.device_id, module_name)
        
        if not envelope_ok:
            ack = make_ack(
                payload.get("req_id", "?"), 
                False, 
                payload.get("action", "?"), 
                payload.get("actor"), 
                code="BAD_REQUEST", 
                error=validation_error
            )
            self._pub(event_topic, ack)
            return
            
        action = payload["action"]
        params = payload["params"]
        req_id = payload["req_id"]
        actor = payload.get("actor")
        
        try:
            success, error_msg, details = module.handle_cmd(action, params)
            self.publish_module_status(module_name, module.status_payload())
            code = "OK" if success else "MODULE_ERROR"
            ack = make_ack(req_id, success, action, actor, code=code, error=error_msg, details=details)
            self._pub(event_topic, ack)
        except Exception as e:
            ack = make_ack(req_id, False, action, actor, code="EXCEPTION", error=str(e))
            self._pub(event_topic, ack)
            
    def _handle_module_config(self, module_name: str, module: Any, payload: Dict[str, Any]):
        """Handle module configuration updates."""
        event_topic = t_module_evt(self.device_id, module_name)
        
        if not isinstance(payload, dict):
            ack = make_ack("?", False, "cfg", code="BAD_REQUEST", error="Config must be an object")
            self._pub(event_topic, ack)
            return
            
        # Check config size
        try:
            if len(json.dumps(payload).encode("utf-8")) > MAX_PARAMS_BYTES:
                req_id = payload.get("req_id", "?")
                ack = make_ack(req_id, False, "cfg", code="BAD_REQUEST", error="Config too large")
                self._pub(event_topic, ack)
                return
        except Exception:
            pass
            
        try:
            # Apply configuration
            module.cfg = deep_merge(module.cfg, payload)
            self.publish_module_status(module_name, module.status_payload())
            req_id = payload.get("req_id", "?")
            ack = make_ack(req_id, True, "cfg")
            self._pub(event_topic, ack)
        except Exception as e:
            req_id = payload.get("req_id", "?")
            ack = make_ack(req_id, False, "cfg", code="EXCEPTION", error=str(e))
            self._pub(event_topic, ack)

    def handle_device_cmd(self, action: str, params: Dict[str, Any]) -> tuple[bool, str | None, Dict[str, Any]]:
        """Handle device-level commands."""
        if action == "ping":
            return True, None, {"device_id": self.device_id, "ts": now_iso()}

        if action == "set_labels":
            labels = params.get("labels")
            if not isinstance(labels, list):
                return False, "labels must be a list", {}
            self.labels = labels
            self.cfg["labels"] = labels
            self.publish_meta()
            return True, None, {"labels": labels}

        if action == "add_module":
            mname = params.get("name")
            mcfg = params.get("cfg", {}) or {}
            if not mname:
                return False, "missing module name", {}
            
            module_class = self._get_module_class(mname)
            if not module_class:
                return False, f"unknown module: {mname}", {}
            
            if mname in self.modules:
                self.modules[mname].apply_cfg(mcfg)
                self.publish_module_status(mname, self.modules[mname].status_payload())
                self.publish_meta()
                return True, None, {"updated": True}
            
            mod = module_class(self.device_id, mcfg)
            self.modules[mname] = mod
            self._subscribe_module_topics(mname)
            self.publish_module_status(mname, mod.status_payload())
            self.publish_meta()
            return True, None, {"added": mname}

        if action == "remove_module":
            mname = params.get("name")
            if not mname or mname not in self.modules:
                return False, "module not found", {}
            
            try:
                self._unsubscribe_module_topics(mname)
            except Exception:
                pass
            try:
                self.modules[mname].shutdown()
            except Exception:
                pass
            
            del self.modules[mname]
            self.publish_meta()
            return True, None, {"removed": mname}

        return False, f"unknown action: {action}", {}


def main():
    """Main entry point for the device agent."""
    from .config import load_agent_config
    
    print("Lab Platform Device Agent starting...")
    
    try:
        # Load configuration
        cfg = load_agent_config()
        
        # Create and start agent
        agent = DeviceAgent(cfg)
        agent.start()
        
        # Setup graceful shutdown
        def shutdown_handler(*_):
            print("\nShutting down agent...")
            agent.shutdown()
            print("Agent stopped")
            
        signal.signal(signal.SIGTERM, shutdown_handler)
        signal.signal(signal.SIGINT, shutdown_handler)
        
        print("Agent is running. Press Ctrl+C to stop.")
        
        # Keep the main thread alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            shutdown_handler()
            
    except KeyboardInterrupt:
        print("\nStartup interrupted")
        return 1
    except Exception as e:
        print(f"Failed to start agent: {e}")
        return 1
        
    return 0


if __name__ == "__main__":
    main()
