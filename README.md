# Lab Platform Device Agent

The Device Agent is the edge component of the Lab Platform that runs on laboratory devices (Raspberry Pi, lab computers, IoT devices) to enable remote control and monitoring. It provides a clean, modular interface for managing hardware and external processes.

## 🚀 Quick Start

### Installation
```bash
# Install the device agent
pip install -e .

# Or use make
make install
```

### Configuration
```bash
# Create configuration from templates
make setup-config

# Edit environment variables
nano .env

# Edit device configuration
nano config.yaml
```

### Running
```bash
# Run the agent
lab-agent

# Or use make
make run

# Run with debug logging
make debug
```

## 📋 Prerequisites

- **Python 3.8+**
- **MQTT Broker** (EMQX or Mosquitto)
- **Network Access** to the Lab Platform orchestrator

### System Requirements
- **CPU**: 1+ core (ARM or x86)
- **RAM**: 1GB minimum, 2GB recommended
- **Storage**: 8GB minimum
- **OS**: Linux (Raspberry Pi OS, Ubuntu), macOS, Windows

## ⚙️ Configuration

### Environment Variables (`.env`)
```bash
# Device Identity
DEVICE_ID=lab-device-01
DEVICE_LABELS=lab,production,ndi

# MQTT Connection
MQTT_HOST=mqtt.lab.example.com
MQTT_PORT=1883
MQTT_USERNAME=lab_device
MQTT_PASSWORD=secure_password

# Agent Settings
HEARTBEAT_INTERVAL_S=30
FEATURES_PATH=../features
LOG_LEVEL=INFO
```

### Device Configuration (`config.yaml`)
```yaml
# Device metadata
device_id: "lab-device-01"  # Overridden by DEVICE_ID env var
labels: ["lab", "production"]  # Overridden by DEVICE_LABELS

# MQTT broker connection
mqtt:
  host: "localhost"     # Overridden by MQTT_HOST
  port: 1883           # Overridden by MQTT_PORT
  username: "mqtt"     # Overridden by MQTT_USERNAME
  password: "public"   # Overridden by MQTT_PASSWORD
  keepalive: 60
  clean_session: true

# Agent behavior
heartbeat_interval_s: 10  # Overridden by HEARTBEAT_INTERVAL_S

# Module configuration (optional)
modules:
  ndi:
    ndi_path: "/usr/local/lib/ndi"
    log_file: "/tmp/ndi_device.log"
  projector:
    serial_port: "/dev/ttyUSB0"
    baudrate: 9600
```

## 🔧 Features

### Core Capabilities
- **MQTT Communication**: Reliable messaging with the orchestrator
- **Dynamic Module Loading**: Automatic discovery and loading of features
- **Process Management**: Safe handling of external processes
- **Configuration Management**: Environment-based configuration with validation
- **Health Monitoring**: Continuous health reporting and diagnostics
- **State Recovery**: Graceful recovery from network interruptions

### Module System
- **Automatic Discovery**: Scans `features/modules/` for available modules
- **Manifest-Driven**: Self-describing modules with validation
- **Lifecycle Management**: Proper initialization, running, and cleanup
- **Command Handling**: Structured request/response pattern
- **Configuration**: Per-module configuration and defaults

## 📁 Project Structure

```
device-agent/
├── src/lab_agent/
│   ├── __init__.py          # Package initialization
│   ├── agent.py             # Main agent implementation
│   ├── base.py              # Module base class
│   ├── common.py            # MQTT utilities and helpers
│   ├── config.py            # Configuration loading
│   ├── logging.py           # Logging configuration
│   ├── metrics.py           # System metrics collection
│   └── reconciler.py        # State reconciliation
├── scripts/
│   └── check_readiness.py   # System readiness validation
├── config.yaml.example     # Configuration template
├── env.example             # Environment template
├── pyproject.toml          # Package definition
├── Makefile               # Development commands
└── README.md              # This file
```

## 🔌 Module Development

### Creating a Module

1. **Create module directory**:
   ```bash
   mkdir -p ../features/modules/my_module
   cd ../features/modules/my_module
   ```

2. **Create manifest file** (`manifest.yaml`):
   ```yaml
   name: my_module
   version: 1.0.0
   description: "My custom module"
   module_file: my_module.py
   class_name: MyModule
   
   # Configuration schema
   config_schema:
     port:
       type: integer
       description: "Serial port number"
       required: true
     timeout:
       type: number
       description: "Command timeout in seconds"
       default: 5.0
   
   # Default configuration
   default_config:
     port: 8080
     timeout: 5.0
   
   # Supported actions
   actions:
     - name: start
       description: "Start the module"
       params:
         mode:
           type: string
           required: false
     - name: stop
       description: "Stop the module"
     - name: status
       description: "Get module status"
   ```

3. **Implement module class** (`my_module.py`):
   ```python
   from lab_agent.base import Module
   from typing import Dict, Any
   
   class MyModule(Module):
       """My custom module implementation."""
       
       name = "my_module"
       
       def __init__(self, device_id: str, cfg: Dict[str, Any] = None):
           super().__init__(device_id, cfg)
           self.running = False
           
       def handle_cmd(self, action: str, params: Dict[str, Any]) -> tuple[bool, str | None, dict]:
           """Handle module commands."""
           if action == "start":
               return self._handle_start(params)
           elif action == "stop":
               return self._handle_stop()
           elif action == "status":
               return self._handle_status()
           else:
               return False, f"Unknown action: {action}", {}
       
       def _handle_start(self, params: Dict[str, Any]) -> tuple[bool, None, dict]:
           """Start the module."""
           mode = params.get("mode", "default")
           # Your implementation here
           self.running = True
           return True, None, {"status": "started", "mode": mode}
       
       def _handle_stop(self) -> tuple[bool, None, dict]:
           """Stop the module."""
           # Your implementation here
           self.running = False
           return True, None, {"status": "stopped"}
       
       def _handle_status(self) -> tuple[bool, None, dict]:
           """Get module status."""
           return True, None, {
               "running": self.running,
               "config": self.cfg,
               "device_id": self.device_id
           }
       
       def shutdown(self) -> None:
           """Clean up resources."""
           self.running = False
   ```

4. **Create readiness check**:
   ```bash
   python3 ../../shared/create_module_readiness.py my_module
   ```

### Module Base Class

All modules extend the `Module` base class:

```python
from abc import ABC, abstractmethod
from typing import Dict, Any

class Module(ABC):
    """Base class for device agent modules."""
    
    name: str = "base"  # Override in subclass
    
    def __init__(self, device_id: str, cfg: Dict[str, Any] = None):
        self.device_id = device_id
        self.cfg = cfg or {}
    
    @abstractmethod
    def handle_cmd(self, action: str, params: Dict[str, Any]) -> tuple[bool, str | None, dict]:
        """Handle a command and return (success, error_message, response_data)."""
        pass
    
    def on_agent_connect(self) -> None:
        """Called when agent connects to MQTT broker."""
        pass
    
    def on_agent_disconnect(self) -> None:
        """Called when agent disconnects from MQTT broker."""
        pass
    
    def shutdown(self) -> None:
        """Clean up resources before shutdown."""
        pass
```

## 📡 MQTT Communication

### Topic Structure

The agent communicates using structured MQTT topics:

```
/lab/device/{device_id}/
├── meta                    # Device metadata (retained)
├── status                  # Device status (retained)
├── cmd                     # Device commands
├── evt                     # Device events
└── {module}/
    ├── cmd                 # Module commands
    ├── cfg                 # Module configuration
    ├── status              # Module status (retained)
    └── evt                 # Module events
```

### Message Format

All messages use a standardized JSON envelope:

```json
{
  "req_id": "550e8400-e29b-41d4-a716-446655440000",
  "actor": "orchestrator",
  "ts": "2024-01-01T12:00:00Z",
  "action": "start",
  "params": {
    "mode": "production",
    "timeout": 30
  }
}
```

### Response Format

Module responses follow a consistent pattern:

```json
{
  "req_id": "550e8400-e29b-41d4-a716-446655440000",
  "success": true,
  "error": null,
  "data": {
    "status": "started",
    "pid": 1234
  },
  "ts": "2024-01-01T12:00:01Z"
}
```

## 🔍 Monitoring and Diagnostics

### Health Checks

```bash
# Check agent readiness
python3 scripts/check_readiness.py

# Verbose output
python3 scripts/check_readiness.py --verbose

# JSON output
python3 scripts/check_readiness.py --json

# Using make
make check-readiness
```

### Logging

The agent provides structured logging:

```python
import logging

# Get logger
logger = logging.getLogger("lab_agent.my_module")

# Log with context
logger.info("Module started", extra={
    "device_id": self.device_id,
    "module": self.name,
    "action": "start"
})
```

Log levels:
- **DEBUG**: Detailed diagnostic information
- **INFO**: General operational messages
- **WARNING**: Warning messages for unusual situations
- **ERROR**: Error messages for failures
- **CRITICAL**: Critical errors that may cause shutdown

### Metrics

System metrics are automatically collected:

```python
from lab_agent.metrics import get_system_metrics

# Get current metrics
metrics = get_system_metrics()
# Returns: CPU usage, memory usage, disk usage, network stats
```

## 🛠️ Development

### Make Commands

```bash
make help              # Show available commands
make install           # Install device agent
make setup-config      # Create configuration from templates
make run              # Run device agent
make debug            # Run with debug logging
make test             # Run tests
make clean            # Clean up log files
make health           # Check agent health
make check-readiness  # Validate system readiness
```

### Development Setup

```bash
# Clone repository
git clone <repository-url>
cd lab_platform/device-agent

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install in development mode
pip install -e .

# Set up configuration
make setup-config

# Run tests
make test

# Run with debug logging
LOG_LEVEL=DEBUG lab-agent
```

### Testing Modules

```bash
# Test module loading
python3 -c "
from lab_agent.agent import DeviceAgent
agent = DeviceAgent({'device_id': 'test'})
print('Available modules:', list(agent.modules.keys()))
"

# Test MQTT connectivity
python3 -c "
import paho.mqtt.client as mqtt
client = mqtt.Client()
client.connect('localhost', 1883, 60)
client.publish('/lab/test', 'hello')
client.disconnect()
"
```

## 🔧 Troubleshooting

### Common Issues

#### Agent Won't Start
```bash
# Check configuration
python3 scripts/check_readiness.py --verbose

# Check logs
tail -f *.log

# Check MQTT connectivity
telnet mqtt-broker 1883
```

#### Module Not Loading
```bash
# Check manifest syntax
python3 -c "import yaml; print(yaml.safe_load(open('manifest.yaml')))"

# Check module imports
python3 -c "from my_module import MyModule; print('OK')"

# Check features path
echo $FEATURES_PATH
ls -la $FEATURES_PATH/modules/
```

#### MQTT Connection Issues
```bash
# Test broker connectivity
mosquitto_pub -h your-broker -p 1883 -u user -P pass -t test -m "hello"

# Check network
ping your-broker
nslookup your-broker

# Check credentials
echo "MQTT_USERNAME: $MQTT_USERNAME"
echo "MQTT_PASSWORD: [hidden]"
```

### Debug Mode

Enable detailed logging:

```bash
# Environment variable
export LOG_LEVEL=DEBUG
lab-agent

# Command line
make debug

# Configuration file
# Edit config.yaml:
log_level: DEBUG
```

### Performance Monitoring

```bash
# Monitor system resources
top -p $(pgrep -f lab-agent)

# Check memory usage
ps aux | grep lab-agent

# Monitor MQTT traffic
mosquitto_sub -h your-broker -t '/lab/device/+/+' -v
```

## 🔒 Security

### Best Practices
- **Unique Device IDs**: Use hardware-based identifiers when possible
- **Secure Credentials**: Store MQTT credentials in environment variables
- **Network Security**: Use TLS for MQTT connections in production
- **Access Control**: Limit file system access for modules
- **Regular Updates**: Keep agent and dependencies updated

### TLS Configuration

```bash
# Configure TLS in .env
MQTT_PORT=8883
MQTT_USE_TLS=true
MQTT_CA_CERT=/path/to/ca.crt
MQTT_CLIENT_CERT=/path/to/client.crt
MQTT_CLIENT_KEY=/path/to/client.key
```

## 📚 API Reference

### Agent Class

```python
class DeviceAgent:
    def __init__(self, cfg: Dict[str, Any])
    def start(self) -> None
    def stop(self) -> None
    def publish_status(self) -> None
    def get_module(self, name: str) -> Module | None
```

### Module Interface

```python
class Module(ABC):
    name: str
    
    def __init__(self, device_id: str, cfg: Dict[str, Any] = None)
    def handle_cmd(self, action: str, params: Dict[str, Any]) -> tuple[bool, str | None, dict]
    def on_agent_connect(self) -> None
    def on_agent_disconnect(self) -> None
    def shutdown(self) -> None
```

### MQTT Utilities

```python
from lab_agent.common import (
    t_device_status,     # Build device status topic
    t_module_cmd,        # Build module command topic
    validate_envelope,   # Validate message format
    make_ack,           # Create acknowledgment message
)
```

## 📄 License

[Your License Here]

## 🆘 Support

- **Documentation**: See main repository documentation
- **Issues**: Report bugs and feature requests on GitHub
- **Community**: Join discussions and get help