#!/usr/bin/env python3
"""Readiness check script for Lab Platform Device Agent."""

import os
import sys
from pathlib import Path

# Add shared directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))
from readiness_base import ReadinessChecker


def create_device_agent_checker() -> ReadinessChecker:
    """Create and configure device agent readiness checker."""
    agent_dir = Path(__file__).parent.parent
    checker = ReadinessChecker("Device Agent", agent_dir)
    
    # Add basic checks
    checker.add_check("Python Version", lambda: checker.check_python_version())
    checker.add_check("Environment Template", lambda: checker.check_file_exists(agent_dir / "env.example", "env.example"))
    checker.add_check("Device Config Template", lambda: checker.check_file_exists(agent_dir / "config.yaml.example", "config.yaml.example"))
    
    # Add custom checks
    def check_env_config():
        env_file = agent_dir / ".env"
        if not env_file.exists():
            return False, ".env file missing. Copy from env.example"
        
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
            required_vars = ["DEVICE_ID", "MQTT_HOST"]
            missing = [var for var in required_vars if not os.getenv(var)]
            if missing:
                return False, f"Missing required variables: {', '.join(missing)}"
            return True, "Environment configuration valid"
        except ImportError:
            return False, "python-dotenv not installed"
        except Exception as e:
            return False, f"Error loading .env: {e}"
    
    def check_device_config():
        config_file = agent_dir / "config.yaml"
        if not config_file.exists():
            return False, "config.yaml missing. Copy from config.yaml.example"
        return checker.check_yaml_file(config_file)
    
    def check_dependencies():
        required_imports = [
            ("paho.mqtt.client", "paho-mqtt"),
            ("yaml", "PyYAML"),
            ("dotenv", "python-dotenv"),
            ("lab_agent", "lab_agent")
        ]
        
        missing = []
        for module_name, package_name in required_imports:
            passed, _ = checker.check_import(module_name, package_name)
            if not passed:
                missing.append(package_name)
        
        if missing:
            return False, f"Missing packages: {', '.join(missing)}. Run: pip install -e ."
        return True, "All dependencies available"
    
    def check_mqtt_connectivity():
        try:
            from dotenv import load_dotenv
            load_dotenv(agent_dir / ".env")
            
            mqtt_host = os.getenv("MQTT_HOST", "localhost")
            mqtt_port = int(os.getenv("MQTT_PORT", "1883"))
            
            from paho.mqtt.client import Client
            import time
            
            client = Client(client_id="readiness-check", clean_session=True)
            client.connect(mqtt_host, mqtt_port, 5)
            client.loop_start()
            time.sleep(1)
            
            if client.is_connected():
                client.disconnect()
                client.loop_stop()
                return True, f"MQTT broker reachable at {mqtt_host}:{mqtt_port}"
            else:
                client.loop_stop()
                return False, f"Could not connect to MQTT broker at {mqtt_host}:{mqtt_port}"
                
        except Exception as e:
            return False, f"MQTT connectivity check failed: {e}"
    
    checker.add_check("Environment Config", check_env_config)
    checker.add_check("Device Config", check_device_config)
    checker.add_check("Dependencies", check_dependencies)
    checker.add_check("MQTT Connectivity", check_mqtt_connectivity)
    
    return checker


def main():
    """Main entry point."""
    checker = create_device_agent_checker()
    suggestions = {
        "Environment Config": "Run 'make setup-config' to create .env from template",
        "Dependencies": "Run 'make install' to install dependencies"
    }
    checker.main(suggestions)


if __name__ == "__main__":
    main()
