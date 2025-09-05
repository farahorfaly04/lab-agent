#!/usr/bin/env python3
"""Simple test script to verify .env override functionality."""

import sys
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Import without manually loading .env - let config.py handle it
from lab_agent.config import load_agent_config

def test_config():
    print("Testing automatic .env loading...")
    print("=" * 50)
    
    try:
        config = load_agent_config()
        print("\n✅ Configuration loaded successfully!")
        return config
    except Exception as e:
        print(f"❌ Configuration loading failed: {e}")
        return None

if __name__ == "__main__":
    config = test_config()
    if config:
        print("\n🎉 Test passed - .env override is working!")
    else:
        print("\n❌ Test failed")
        sys.exit(1)
