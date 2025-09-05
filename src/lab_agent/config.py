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
    candidates = [
        Path.cwd() / ".env",                        # current working directory (highest priority)
        here.parent.parent.parent / ".env",         # device-agent/.env
        here.parent.parent.parent.parent / ".env",  # parent of device-agent (for separate repos)
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
        config = {
            "device_id": os.getenv("DEVICE_ID", "unknown-device"),
            "labels": os.getenv("DEVICE_LABELS", "").split(",") if os.getenv("DEVICE_LABELS") else [],
            "mqtt": {
                "host": os.getenv("MQTT_HOST", "localhost"),
                "port": int(os.getenv("MQTT_PORT", "1883")),
                "username": os.getenv("MQTT_USERNAME", "mqtt"),
                "password": os.getenv("MQTT_PASSWORD", "public"),
            },
            "heartbeat_interval_s": int(os.getenv("HEARTBEAT_INTERVAL_S", "10")),
            "modules": {}
        }
        print("No config.yaml found, using environment variables only")
        return config
    
    # Load from YAML file
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        
        # Override secrets and private variables from environment
        # Device settings (can be overridden)
        if os.getenv("DEVICE_ID"):
            config["device_id"] = os.getenv("DEVICE_ID")
        
        if os.getenv("DEVICE_LABELS"):
            config["labels"] = os.getenv("DEVICE_LABELS").split(",")
        
        # MQTT settings - always override credentials from env for security
        mqtt_config = config.get("mqtt", {})
        mqtt_config.update({
            "host": os.getenv("MQTT_HOST", mqtt_config.get("host", "localhost")),
            "port": int(os.getenv("MQTT_PORT", str(mqtt_config.get("port", 1883)))),
            "username": os.getenv("MQTT_USERNAME", mqtt_config.get("username", "mqtt")),
            "password": os.getenv("MQTT_PASSWORD", mqtt_config.get("password", "public")),
        })
        config["mqtt"] = mqtt_config
        
        # Other settings that can be overridden
        if os.getenv("HEARTBEAT_INTERVAL_S"):
            config["heartbeat_interval_s"] = int(os.getenv("HEARTBEAT_INTERVAL_S"))
        
        print(f"Loaded config from: {config_file}")
        print(f"  Device ID: {config.get('device_id', 'unknown')}")
        print(f"  Labels: {config.get('labels', [])}")
        print(f"  MQTT Host: {config['mqtt']['host']}:{config['mqtt']['port']}")
        print(f"  MQTT User: {config['mqtt']['username']} (password from env)")
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
