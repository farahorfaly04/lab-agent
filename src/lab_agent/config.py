"""Configuration loader for device agent."""

import os
from pathlib import Path
from typing import Dict, Any

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
    """Load device agent configuration from environment variables and .env file."""
    
    # Create config purely from environment variables
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
    
    print(f"Loaded config from environment variables:")
    print(f"  Device ID: {config['device_id']}")
    print(f"  Labels: {config['labels']}")
    print(f"  MQTT Host: {config['mqtt']['host']}:{config['mqtt']['port']}")
    print(f"  MQTT User: {config['mqtt']['username']}")
    print(f"  Heartbeat: {config['heartbeat_interval_s']}s")
    
    return config


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
