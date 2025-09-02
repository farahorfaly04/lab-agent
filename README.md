# Lab Platform Device Agent

Edge device communication agent for the Lab Platform. Runs on devices like Raspberry Pi to enable remote control and monitoring.

## Features

- **MQTT Communication**: Real-time bidirectional communication with orchestrator
- **Dynamic Module Loading**: Load functionality from features directory
- **Device Metadata**: Automatic capability discovery and publishing
- **Command Handling**: Execute commands from orchestrator
- **Health Monitoring**: Heartbeat and status reporting
- **Configuration Management**: Runtime configuration updates
- **Graceful Shutdown**: Clean process termination

## Installation

```bash
pip install -e .
```

## Usage

### Command Line
```bash
lab-agent
```

### Python Module
```bash
python -m lab_agent.agent
```

## Configuration

Create `config.yaml` from the example:

```yaml
device_id: "lab-device-01"
labels: ["example", "lab"]

mqtt:
  host: "localhost"
  port: 1883
  username: "mqtt"
  password: "public"

heartbeat_interval_s: 10
modules: {}  # Loaded dynamically from features/
```

## Module Development

Extend the `Module` base class:

```python
from lab_agent.base import Module

class MyModule(Module):
    name = "my_module"
    
    def handle_cmd(self, action, params):
        if action == "start":
            # Handle start command
            return True, None, {"status": "started"}
        return False, f"unknown action: {action}", {}
```

## MQTT Topics

The agent communicates using structured MQTT topics:

- `/lab/device/{device_id}/meta` - Device metadata (retained)
- `/lab/device/{device_id}/status` - Device status (retained)
- `/lab/device/{device_id}/cmd` - Device commands
- `/lab/device/{device_id}/evt` - Device events
- `/lab/device/{device_id}/{module}/cmd` - Module commands
- `/lab/device/{device_id}/{module}/status` - Module status (retained)
- `/lab/device/{device_id}/{module}/evt` - Module events

## Architecture

- **Agent Core**: Main event loop and MQTT handling
- **Module System**: Dynamic loading of device functionality
- **Common Utilities**: Shared MQTT topics and message formats
- **Configuration**: YAML-based device configuration
