"""Configuration loader for device agent."""

import os
from pathlib import Path
from typing import Dict, Any
import yaml

# Load environment variables from .env if present
try:
    from dotenv import load_dotenv
    # Support .env placed in various locations
    here = Path(__file__).resolve()
    device_agent_dir = here.parent.parent.parent  # device-agent directory
    candidates = [
        device_agent_dir / ".env",                  # device-agent/.env (highest priority)
        device_agent_dir / ".env.test",             # device-agent/.env.test (for testing)
        Path.cwd() / ".env",                        # current working directory
        device_agent_dir.parent / ".env",           # parent of device-agent (for separate repos)
        Path.home() / ".lab-platform.env",         # user home directory
    ]
    for env_path in candidates:
        if env_path.exists():
            load_dotenv(env_path)
            print(f"Loaded environment from: {env_path}")
            break
except ImportError:
    # python-dotenv not installed, skip
    pass
except Exception:
    pass


def load_agent_config() -> Dict[str, Any]:
    """Load device agent configuration from config.yaml with .env overrides for secrets."""
    
    # Look for config.yaml file in multiple locations
    config_paths = [
        Path.cwd() / "config.yaml",                 # Current directory
        Path(__file__).parent.parent.parent / "config.yaml",  # device-agent/config.yaml
        Path.home() / ".lab-agent-config.yaml",    # User home
        Path("/etc/lab-platform/agent.yaml"),      # System config
    ]
    
    config_file = None
    for path in config_paths:
        if path.exists() and path.is_file():
            config_file = path
            break
    
    if not config_file:
        # Fallback to environment variables only
        print("No config.yaml found, using environment variables only")
        
        device_id = os.getenv("DEVICE_ID", "unknown-device")
        device_labels = [label.strip() for label in os.getenv("DEVICE_LABELS", "").split(",") if label.strip()] if os.getenv("DEVICE_LABELS") else []
        mqtt_host = os.getenv("MQTT_HOST", "localhost")
        mqtt_port = int(os.getenv("MQTT_PORT", "1883"))
        mqtt_username = os.getenv("MQTT_USERNAME", "mqtt")
        mqtt_password = os.getenv("MQTT_PASSWORD", "public")
        heartbeat_interval = int(os.getenv("HEARTBEAT_INTERVAL_S", "10"))
        
        config = {
            "device_id": device_id,
            "labels": device_labels,
            "mqtt": {
                "host": mqtt_host,
                "port": mqtt_port,
                "username": mqtt_username,
                "password": mqtt_password,
            },
            "heartbeat_interval_s": heartbeat_interval,
            "modules": {}
        }
        
        print("Configuration from environment variables:")
        print(f"  Device ID: {device_id}")
        print(f"  Labels: {device_labels}")
        print(f"  MQTT Host: {mqtt_host}:{mqtt_port}")
        print(f"  MQTT User: {mqtt_username}")
        print(f"  Heartbeat: {heartbeat_interval}s")
        print(f"  Modules configured: []")
        
        return config
    
    # Load from YAML file
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        
        # Override with environment variables (from .env file)
        overrides_applied = []
        
        # Device settings
        if os.getenv("DEVICE_ID"):
            old_value = config.get("device_id")
            config["device_id"] = os.getenv("DEVICE_ID")
            overrides_applied.append(f"DEVICE_ID: {old_value} -> {config['device_id']}")
        
        if os.getenv("DEVICE_LABELS"):
            old_value = config.get("labels", [])
            config["labels"] = [label.strip() for label in os.getenv("DEVICE_LABELS").split(",") if label.strip()]
            overrides_applied.append(f"DEVICE_LABELS: {old_value} -> {config['labels']}")
        
        # Ensure mqtt section exists
        if "mqtt" not in config:
            config["mqtt"] = {}
        mqtt_config = config["mqtt"]
        
        # MQTT settings - always check environment variables
        env_mqtt_host = os.getenv("MQTT_HOST")
        if env_mqtt_host:
            old_value = mqtt_config.get("host", "localhost")
            mqtt_config["host"] = env_mqtt_host
            overrides_applied.append(f"MQTT_HOST: {old_value} -> {env_mqtt_host}")
        elif "host" not in mqtt_config:
            mqtt_config["host"] = "localhost"
            
        env_mqtt_port = os.getenv("MQTT_PORT")
        if env_mqtt_port:
            old_value = mqtt_config.get("port", 1883)
            mqtt_config["port"] = int(env_mqtt_port)
            overrides_applied.append(f"MQTT_PORT: {old_value} -> {mqtt_config['port']}")
        elif "port" not in mqtt_config:
            mqtt_config["port"] = 1883
            
        env_mqtt_username = os.getenv("MQTT_USERNAME")
        if env_mqtt_username:
            old_value = mqtt_config.get("username", "mqtt")
            mqtt_config["username"] = env_mqtt_username
            overrides_applied.append(f"MQTT_USERNAME: {old_value} -> {env_mqtt_username}")
        elif "username" not in mqtt_config:
            mqtt_config["username"] = "mqtt"
            
        env_mqtt_password = os.getenv("MQTT_PASSWORD")
        if env_mqtt_password:
            old_value = mqtt_config.get("password", "public")
            mqtt_config["password"] = env_mqtt_password
            overrides_applied.append(f"MQTT_PASSWORD: {old_value} -> [HIDDEN]")
        elif "password" not in mqtt_config:
            mqtt_config["password"] = "public"
        
        # Heartbeat interval
        env_heartbeat = os.getenv("HEARTBEAT_INTERVAL_S")
        if env_heartbeat:
            old_value = config.get("heartbeat_interval_s", 10)
            config["heartbeat_interval_s"] = int(env_heartbeat)
            overrides_applied.append(f"HEARTBEAT_INTERVAL_S: {old_value} -> {config['heartbeat_interval_s']}")
        elif "heartbeat_interval_s" not in config:
            config["heartbeat_interval_s"] = 10
        
        print(f"Loaded config from: {config_file}")
        
        # Show environment overrides that were applied
        if overrides_applied:
            print("Environment variable overrides applied:")
            for override in overrides_applied:
                print(f"  {override}")
        else:
            print("No environment variable overrides found")
            
        # Show final configuration
        print("Final configuration:")
        print(f"  Device ID: {config.get('device_id', 'unknown')}")
        print(f"  Labels: {config.get('labels', [])}")
        print(f"  MQTT Host: {config['mqtt']['host']}:{config['mqtt']['port']}")
        print(f"  MQTT User: {config['mqtt']['username']}")
        print(f"  Heartbeat: {config.get('heartbeat_interval_s', 10)}s")
        print(f"  Modules configured: {list(config.get('modules', {}).keys())}")
        
        return config
        
    except Exception as e:
        print(f"Failed to load config from {config_file}: {e}")
        raise


def get_features_path() -> Path:
    """Get the path to the features directory."""
    features_path = os.getenv("FEATURES_PATH")
    if features_path:
        return Path(features_path).resolve()
    
    # Default search locations
    possible_paths = [
        Path.cwd() / ".." / "features",  # Parent directory
        Path.cwd() / "features",         # Current directory
        Path.home() / "lab-features",    # User home
        Path("/opt/lab-platform/features"),  # System
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    
    raise FileNotFoundError("Features directory not found. Set FEATURES_PATH environment variable.")
