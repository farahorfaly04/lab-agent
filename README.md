# Lab Platform Device Agent

Edge device communication agent that runs on Raspberry Pi, lab computers, and IoT devices to enable remote control and monitoring.

## Quick Start

### Installation

```bash
pip install -e .
```

### Configuration

Option A - Environment variables (recommended):
```bash
# Copy example and edit
cp env.example .env

# Key settings:
export DEVICE_ID=lab-device-01
export MQTT_HOST=10.205.10.7
export MQTT_USERNAME=mqtt
export MQTT_PASSWORD=123456789
export FEATURES_PATH=../features  # Path to features directory
```

Option B - YAML config file:
```yaml
device_id: "lab-device-01"
labels: ["lab", "production"]
mqtt:
  host: "10.205.10.7"
  port: 1883
  username: "mqtt"
  password: "123456789"
heartbeat_interval_s: 10
modules: {}  # Loaded dynamically from features/
```

### Running

```bash
lab-agent
```

## Features

- **MQTT Communication**: Connects to orchestrator via MQTT
- **Dynamic Module Loading**: Loads modules from `features/modules/` directory
- **Device Metadata**: Publishes capabilities and status
- **Command Handling**: Processes commands from orchestrator
- **Heartbeat Monitoring**: Continuous health reporting
- **Process Management**: Manages external processes for modules
- **Structured Logging**: JSON logs with device context
- **Metrics Collection**: Lightweight system monitoring

## Module Development

1. Create module directory: `features/modules/your_module/`
2. Add `manifest.yaml`:
```yaml
name: your_module
module_file: your_module.py
class_name: YourModule
```
3. Implement module class extending `Module`

## Module Interface

```python
from lab_agent.base import Module

class YourModule(Module):
    name = "your_module"
    
    def handle_cmd(self, action: str, params: dict) -> tuple[bool, str | None, dict]:
        if action == "start":
            # Handle start command
            return True, None, {"status": "started"}
        return False, f"Unknown action: {action}", {}
```

## MQTT Topics

- `/lab/device/{device_id}/meta` - Device metadata (retained)
- `/lab/device/{device_id}/status` - Device heartbeat (retained)  
- `/lab/device/{device_id}/cmd` - Device commands
- `/lab/device/{device_id}/{module}/cmd` - Module commands
- `/lab/device/{device_id}/{module}/status` - Module status (retained)

## Health Monitoring

The agent provides lightweight HTTP health endpoints (optional):

- `GET :8080/health` - Health summary
- `GET :8080/metrics` - Detailed metrics

## Dependencies

- Python 3.9+
- MQTT broker connection
- Features directory with modules
- Hardware-specific dependencies (pyserial for projector, etc.)

## Development

```bash
# Install with dev dependencies  
pip install -e .

# Run with debug logging
LOG_LEVEL=DEBUG lab-agent

# Test module loading
python -c "from lab_agent.agent import DeviceAgent; print('✓ Agent imports OK')"
```

## System Requirements

- Linux (Raspberry Pi OS, Ubuntu) or macOS
- Python 3.9+
- Network connectivity to MQTT broker
- Hardware access for specific modules (USB, serial ports, etc.)