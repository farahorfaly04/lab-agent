#!/usr/bin/env python3
"""Test script to verify .env override functionality."""

import os
import sys
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from lab_agent.config import load_agent_config

def test_config_loading():
    """Test that configuration loading works correctly."""
    print("Testing configuration loading...")
    print("=" * 50)
    
    try:
        config = load_agent_config()
        
        print("\nConfiguration test completed successfully!")
        print("=" * 50)
        
        # Verify critical settings
        critical_checks = [
            ("device_id", config.get("device_id")),
            ("mqtt.host", config.get("mqtt", {}).get("host")),
            ("mqtt.port", config.get("mqtt", {}).get("port")),
            ("mqtt.username", config.get("mqtt", {}).get("username")),
            ("mqtt.password", config.get("mqtt", {}).get("password")),
        ]
        
        print("\nCritical settings check:")
        all_good = True
        for setting, value in critical_checks:
            status = "✓" if value else "✗"
            print(f"  {status} {setting}: {value}")
            if not value:
                all_good = False
                
        if all_good:
            print("\n🎉 All critical settings are configured!")
        else:
            print("\n⚠️  Some critical settings are missing - check your .env file")
            
        return config
        
    except Exception as e:
        print(f"❌ Configuration loading failed: {e}")
        return None

if __name__ == "__main__":
    config = test_config_loading()
    
    if config:
        print(f"\nTo test with different values, modify your .env file and run this script again.")
        sys.exit(0)
    else:
        sys.exit(1)
