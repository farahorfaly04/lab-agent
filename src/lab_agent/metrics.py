"""Lightweight metrics collection for device agents."""

import json
import time
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class AgentMetrics:
    """Agent metrics data structure."""
    device_id: str
    uptime_seconds: float
    
    # MQTT metrics
    mqtt_messages_sent: int = 0
    mqtt_messages_received: int = 0
    mqtt_connection_errors: int = 0
    mqtt_last_connected: Optional[str] = None
    
    # Module metrics
    modules_loaded: int = 0
    modules_active: int = 0
    commands_processed: int = 0
    commands_successful: int = 0
    commands_failed: int = 0
    
    # System metrics
    cpu_percent: Optional[float] = None
    memory_percent: Optional[float] = None
    disk_percent: Optional[float] = None
    
    # Process metrics (for modules that spawn processes)
    processes_spawned: int = 0
    processes_active: int = 0
    processes_failed: int = 0
    
    # Error tracking
    last_error: Optional[str] = None
    error_count: int = 0
    
    # Timestamps
    last_updated: str = None
    
    def __post_init__(self):
        if self.last_updated is None:
            self.last_updated = datetime.utcnow().isoformat() + 'Z'


class AgentMetricsCollector:
    """Lightweight metrics collector for device agents."""
    
    def __init__(self, device_id: str):
        self.device_id = device_id
        self.start_time = time.time()
        self.metrics = AgentMetrics(
            device_id=device_id,
            uptime_seconds=0
        )
        self._command_start_times = {}  # Track command execution times
    
    def update_uptime(self):
        """Update uptime metric."""
        self.metrics.uptime_seconds = time.time() - self.start_time
        self.metrics.last_updated = datetime.utcnow().isoformat() + 'Z'
    
    def record_mqtt_message_sent(self, topic: str, size_bytes: int):
        """Record MQTT message sent."""
        self.metrics.mqtt_messages_sent += 1
        self.update_uptime()
    
    def record_mqtt_message_received(self, topic: str, size_bytes: int):
        """Record MQTT message received."""
        self.metrics.mqtt_messages_received += 1
        self.update_uptime()
    
    def record_mqtt_connection_error(self):
        """Record MQTT connection error."""
        self.metrics.mqtt_connection_errors += 1
        self.update_uptime()
    
    def record_mqtt_connected(self):
        """Record successful MQTT connection."""
        self.metrics.mqtt_last_connected = datetime.utcnow().isoformat() + 'Z'
        self.update_uptime()
    
    def record_module_loaded(self, module_name: str, success: bool):
        """Record module loading result."""
        if success:
            self.metrics.modules_loaded += 1
        else:
            self.record_error(f"Failed to load module: {module_name}")
        self.update_uptime()
    
    def record_module_activated(self, module_name: str):
        """Record module activation."""
        self.metrics.modules_active += 1
        self.update_uptime()
    
    def record_module_deactivated(self, module_name: str):
        """Record module deactivation."""
        self.metrics.modules_active = max(0, self.metrics.modules_active - 1)
        self.update_uptime()
    
    def record_command_start(self, req_id: str, module: str, action: str):
        """Record command execution start."""
        self._command_start_times[req_id] = {
            'start_time': time.time(),
            'module': module,
            'action': action
        }
        self.metrics.commands_processed += 1
        self.update_uptime()
    
    def record_command_complete(self, req_id: str, success: bool, error: str = None):
        """Record command execution completion."""
        if req_id in self._command_start_times:
            duration = time.time() - self._command_start_times[req_id]['start_time']
            del self._command_start_times[req_id]
        
        if success:
            self.metrics.commands_successful += 1
        else:
            self.metrics.commands_failed += 1
            if error:
                self.record_error(f"Command failed: {error}")
        
        self.update_uptime()
    
    def record_process_spawned(self, pid: int, command: str):
        """Record process spawn."""
        self.metrics.processes_spawned += 1
        self.metrics.processes_active += 1
        self.update_uptime()
    
    def record_process_terminated(self, pid: int, success: bool):
        """Record process termination."""
        self.metrics.processes_active = max(0, self.metrics.processes_active - 1)
        if not success:
            self.metrics.processes_failed += 1
        self.update_uptime()
    
    def record_error(self, error_message: str):
        """Record error."""
        self.metrics.last_error = error_message
        self.metrics.error_count += 1
        self.update_uptime()
    
    def update_system_metrics(self):
        """Update system resource metrics."""
        try:
            import psutil
            
            self.metrics.cpu_percent = psutil.cpu_percent(interval=None)
            self.metrics.memory_percent = psutil.virtual_memory().percent
            self.metrics.disk_percent = psutil.disk_usage('/').percent
            
        except ImportError:
            # psutil not available, skip system metrics
            pass
        except Exception as e:
            self.record_error(f"Failed to collect system metrics: {e}")
        
        self.update_uptime()
    
    def get_metrics_dict(self) -> Dict[str, Any]:
        """Get metrics as dictionary."""
        self.update_uptime()
        return asdict(self.metrics)
    
    def get_metrics_json(self) -> str:
        """Get metrics as JSON string."""
        return json.dumps(self.get_metrics_dict(), default=str)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary for health checks."""
        self.update_uptime()
        
        return {
            "device_id": self.metrics.device_id,
            "uptime_seconds": self.metrics.uptime_seconds,
            "status": "healthy" if self.metrics.error_count == 0 else "degraded",
            "modules_loaded": self.metrics.modules_loaded,
            "modules_active": self.metrics.modules_active,
            "commands_success_rate": (
                self.metrics.commands_successful / max(1, self.metrics.commands_processed)
            ),
            "mqtt_connected": self.metrics.mqtt_last_connected is not None,
            "last_error": self.metrics.last_error,
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }
    
    def reset_counters(self):
        """Reset accumulated counters (useful for periodic reporting)."""
        # Keep cumulative counters, reset only rate-based ones
        self.metrics.error_count = 0
        self.metrics.last_error = None
        self.update_uptime()


class AgentHealthReporter:
    """HTTP-based health reporting for device agents."""
    
    def __init__(self, metrics_collector: AgentMetricsCollector, port: int = 8080):
        self.metrics = metrics_collector
        self.port = port
        self._server = None
    
    def start_health_server(self):
        """Start lightweight HTTP server for health checks."""
        try:
            from http.server import HTTPServer, BaseHTTPRequestHandler
            import threading
            import json
            
            class HealthHandler(BaseHTTPRequestHandler):
                def __init__(self, metrics_collector, *args, **kwargs):
                    self.metrics = metrics_collector
                    super().__init__(*args, **kwargs)
                
                def do_GET(self):
                    if self.path == '/health':
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        
                        health_data = self.metrics.get_summary()
                        self.wfile.write(json.dumps(health_data).encode('utf-8'))
                    
                    elif self.path == '/metrics':
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        
                        metrics_data = self.metrics.get_metrics_dict()
                        self.wfile.write(json.dumps(metrics_data).encode('utf-8'))
                    
                    else:
                        self.send_response(404)
                        self.end_headers()
                
                def log_message(self, format, *args):
                    # Suppress HTTP server logs
                    pass
            
            # Create handler with metrics injected
            def handler_factory(*args, **kwargs):
                return HealthHandler(self.metrics, *args, **kwargs)
            
            self._server = HTTPServer(('0.0.0.0', self.port), handler_factory)
            
            # Run server in background thread
            server_thread = threading.Thread(
                target=self._server.serve_forever,
                daemon=True,
                name="health-server"
            )
            server_thread.start()
            
            return True
            
        except Exception as e:
            self.metrics.record_error(f"Failed to start health server: {e}")
            return False
    
    def stop_health_server(self):
        """Stop health server."""
        if self._server:
            self._server.shutdown()
            self._server = None


class MQTTMetricsReporter:
    """MQTT-based metrics reporting for device agents."""
    
    def __init__(self, metrics_collector: AgentMetricsCollector, mqtt_client):
        self.metrics = metrics_collector
        self.mqtt_client = mqtt_client
        self._reporting_active = False
    
    def start_periodic_reporting(self, interval_seconds: int = 60):
        """Start periodic metrics reporting via MQTT."""
        import threading
        
        def report_loop():
            while self._reporting_active:
                try:
                    self._send_metrics_report()
                    time.sleep(interval_seconds)
                except Exception as e:
                    self.metrics.record_error(f"Metrics reporting failed: {e}")
                    time.sleep(interval_seconds)
        
        self._reporting_active = True
        report_thread = threading.Thread(
            target=report_loop,
            daemon=True,
            name="metrics-reporter"
        )
        report_thread.start()
    
    def stop_periodic_reporting(self):
        """Stop periodic metrics reporting."""
        self._reporting_active = False
    
    def _send_metrics_report(self):
        """Send metrics report via MQTT."""
        topic = f"/lab/device/{self.metrics.device_id}/metrics"
        payload = self.metrics.get_metrics_dict()
        
        # Update system metrics before sending
        self.metrics.update_system_metrics()
        
        self.mqtt_client.publish_json(topic, payload, qos=1, retain=False)
    
    def send_health_update(self):
        """Send immediate health status update."""
        topic = f"/lab/device/{self.metrics.device_id}/health"
        payload = self.metrics.get_summary()
        
        self.mqtt_client.publish_json(topic, payload, qos=1, retain=True)
