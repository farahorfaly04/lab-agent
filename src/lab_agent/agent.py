"""Main device agent implementation."""

import json, yaml, threading
from pathlib import Path
from paho.mqtt.client import Client, MQTTMessage
from typing import Dict, Any
import signal, time
import importlib.util
import sys
import os

from lab_agent.common import (
    jdump, now_iso, t_device_meta, t_device_status, t_device_cmd, t_device_evt,
    t_module_status, t_module_cmd, t_module_cfg, t_module_evt, parse_json, validate_envelope,
    make_ack, deep_merge, MAX_PARAMS_BYTES
)


class DeviceAgent:
    """Device agent for Lab Platform.

    - Loads configuration from config.yaml
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
        self._load_modules()
        
        self.client = Client(client_id=f"device-{self.device_id}", clean_session=True)
        self.heartbeat_interval_s = int(cfg.get("heartbeat_interval_s", 10))
        self._hb_stop = threading.Event()
        self._setup_mqtt()

    def _load_modules(self):
        """Load modules from configuration and features directory."""
        # Load modules from config
        modules_cfg: Dict[str, Any] = {}
        explicit = self.cfg.get("modules") or {}
        if isinstance(explicit, dict):
            modules_cfg.update(explicit)
        
        # Load modules from features directory
        self._load_feature_modules()
        
        # Instantiate configured modules
        for mname, mcfg in modules_cfg.items():
            module_class = self._get_module_class(mname)
            if module_class:
                self.modules[mname] = module_class(self.device_id, mcfg)
            else:
                print(f"Warning: Unknown module in config: {mname}")

    def _load_feature_modules(self):
        """Load module classes from features/ directory."""
        # Look for features in the main repo
        features_dir = Path(__file__).resolve().parents[4] / "features"
        if not features_dir.exists():
            return
        
        for module_dir in features_dir.glob("modules/*/"):
            manifest_file = module_dir / "manifest.yaml"
            if not manifest_file.exists():
                continue
                
            try:
                with open(manifest_file) as f:
                    manifest = yaml.safe_load(f)
                
                module_name = manifest.get("name")
                module_file = manifest.get("module_file", "module.py")
                class_name = manifest.get("class_name")
                
                if not all([module_name, class_name]):
                    continue
                
                # Load the module
                module_path = module_dir / module_file
                if module_path.exists():
                    spec = importlib.util.spec_from_file_location(
                        f"features.modules.{module_name}", 
                        module_path
                    )
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        
                        # Register the module class
                        if hasattr(module, class_name):
                            self._module_classes = getattr(self, '_module_classes', {})
                            self._module_classes[module_name] = getattr(module, class_name)
                        
            except Exception as e:
                print(f"Failed to load module from {module_dir}: {e}")

    def _get_module_class(self, module_name: str):
        """Get module class by name."""
        return getattr(self, '_module_classes', {}).get(module_name)

    def _setup_mqtt(self):
        """Configure credentials, will message, callbacks, and connect."""
        m = self.cfg["mqtt"]
        self.client.username_pw_set(m.get("username"), m.get("password"))
        
        # LWT -> offline (broker will publish this on unexpected disconnect)
        lwt_payload = jdump({"online": False, "ts": now_iso(), "device_id": self.device_id})
        self.client.will_set(t_device_status(self.device_id), lwt_payload, qos=1, retain=True)
        
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.connect(m.get("host", "127.0.0.1"), m.get("port", 1883), keepalive=30)

    def start(self):
        """Start the agent."""
        # Start network loop and publish birth messages
        self.client.loop_start()
        self.publish_meta()
        self.publish_device_status({"online": True, "device_id": self.device_id})
        
        # Subscribe to device + module topics
        self.client.subscribe(t_device_cmd(self.device_id), qos=1)
        for mname in self.modules.keys():
            self._subscribe_module_topics(mname)
        
        # Heartbeat loop
        threading.Thread(target=self._heartbeat_loop, name="hb", daemon=True).start()

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

    def on_connect(self, client, userdata, flags, rc):
        """Handle MQTT connection."""
        # Re-subscribe happens automatically; publish statuses
        for mname, mod in self.modules.items():
            try:
                if hasattr(mod, "on_agent_connect"):
                    mod.on_agent_connect()
            except Exception:
                pass
            self.publish_module_status(mname, mod.status_payload())

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

    def on_message(self, client: Client, userdata, msg: MQTTMessage):
        """Handle incoming MQTT messages."""
        topic = msg.topic
        
        # Device-level commands
        if topic == t_device_cmd(self.device_id):
            ok, p, err = parse_json(msg.payload)
            evt_t = t_device_evt(self.device_id)
            if not ok:
                self._pub(evt_t, make_ack("?", False, "?", code="BAD_JSON", error=err))
                return
            ok, verr = validate_envelope(p)
            if not ok:
                self._pub(evt_t, make_ack(p.get("req_id","?"), False, p.get("action","?"), p.get("actor"), code="BAD_REQUEST", error=verr))
                return
            
            action = p["action"]
            params = p["params"]
            rid = p["req_id"]
            actor = p.get("actor")
            
            try:
                ok, error, details = self.handle_device_cmd(action, params)
                self._pub(evt_t, make_ack(rid, ok, action, actor, code=("OK" if ok else "DEVICE_ERROR"), error=error, details=details))
            except Exception as e:
                self._pub(evt_t, make_ack(rid, False, action, actor, code="EXCEPTION", error=str(e)))
            return
        
        # Module-level commands/config
        for mname, mod in list(self.modules.items()):
            if topic == t_module_cmd(self.device_id, mname):
                ok, p, err = parse_json(msg.payload)
                evt_t = t_module_evt(self.device_id, mname)
                if not ok:
                    self._pub(evt_t, make_ack("?", False, "?", code="BAD_JSON", error=err))
                    return
                ok, verr = validate_envelope(p)
                if not ok:
                    self._pub(evt_t, make_ack(p.get("req_id","?"), False, p.get("action","?"), p.get("actor"), code="BAD_REQUEST", error=verr))
                    return
                
                action = p["action"]
                params = p["params"]
                rid = p["req_id"]
                actor = p.get("actor")
                
                try:
                    ok, err_msg, details = mod.handle_cmd(action, params)
                    self.publish_module_status(mname, mod.status_payload())
                    self._pub(evt_t, make_ack(rid, ok, action, actor, code=("OK" if ok else "MODULE_ERROR"), error=err_msg, details=details))
                except Exception as e:
                    self._pub(evt_t, make_ack(rid, False, action, actor, code="EXCEPTION", error=str(e)))
                return
            
            if topic == t_module_cfg(self.device_id, mname):
                ok, p, err = parse_json(msg.payload)
                evt_t = t_module_evt(self.device_id, mname)
                if not ok:
                    self._pub(evt_t, make_ack("?", False, "cfg", code="BAD_JSON", error=err))
                    return
                if not isinstance(p, dict):
                    self._pub(evt_t, make_ack("?", False, "cfg", code="BAD_REQUEST", error="cfg_not_object"))
                    return
                
                try:
                    if len(json.dumps(p).encode("utf-8")) > MAX_PARAMS_BYTES:
                        self._pub(evt_t, make_ack(p.get("req_id","?"), False, "cfg", code="BAD_REQUEST", error="cfg_too_large"))
                        return
                except Exception:
                    pass
                
                try:
                    # Deep-merge configuration
                    mod.cfg = deep_merge(mod.cfg, p)
                    self.publish_module_status(mname, mod.status_payload())
                    self._pub(evt_t, make_ack(p.get("req_id","?"), True, "cfg"))
                except Exception as e:
                    self._pub(evt_t, make_ack(p.get("req_id","?"), False, "cfg", code="EXCEPTION", error=str(e)))
                return

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
    # Look for config file
    config_paths = [
        Path(__file__).parent / "config.yaml",
        Path.cwd() / "config.yaml",
        Path.cwd() / "device-agent" / "config.yaml"
    ]
    
    config_file = None
    for path in config_paths:
        if path.exists():
            config_file = path
            break
    
    if not config_file:
        print("Error: config.yaml not found")
        return
    
    cfg = yaml.safe_load(config_file.read_text())
    agent = DeviceAgent(cfg)
    agent.start()

    def _graceful(*_):
        agent.shutdown()

    signal.signal(signal.SIGTERM, _graceful)
    signal.signal(signal.SIGINT, _graceful)
    
    # Keep alive
    threading.Event().wait()


if __name__ == "__main__":
    main()
