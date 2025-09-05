"""Structured logging for device agents."""

import json
import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, Any, Optional


class AgentStructuredFormatter(logging.Formatter):
    """JSON formatter for device agent logs."""
    
    def __init__(self, device_id: str):
        super().__init__()
        self.device_id = device_id
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON."""
        log_entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ", time.gmtime(record.created)),
            "level": record.levelname,
            "component": "agent",
            "device_id": self.device_id,
            "module": getattr(record, 'module', ''),
            "message": record.getMessage(),
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields from record
        for key, value in record.__dict__.items():
            if key.startswith('log_'):
                log_entry[key[4:]] = value  # Remove 'log_' prefix
        
        return json.dumps(log_entry, default=str)


def setup_agent_logging(
    device_id: str,
    level: str = "INFO",
    log_dir: Optional[Path] = None
) -> logging.Logger:
    """Setup structured logging for device agent.
    
    Args:
        device_id: Device identifier
        level: Logging level
        log_dir: Directory for log files
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(f"agent.{device_id}")
    logger.setLevel(getattr(logging, level.upper()))
    
    # Clear existing handlers
    logger.handlers.clear()
    
    formatter = AgentStructuredFormatter(device_id)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"agent_{device_id}.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10_000_000,
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    logger.propagate = False
    return logger


def log_mqtt_event(logger: logging.Logger, direction: str, topic: str, 
                  req_id: str = "", action: str = "", result: str = ""):
    """Log MQTT events with structured data."""
    logger.info(
        f"MQTT {direction}: {topic}",
        extra={
            "log_direction": direction,
            "log_topic": topic,
            "log_req_id": req_id,
            "log_action": action,
            "log_result": result
        }
    )


def log_command_execution(logger: logging.Logger, module: str, action: str, 
                         duration_ms: float, result: str, req_id: str = "", **extra):
    """Log command execution with timing."""
    logger.info(
        f"Module command: {module}.{action} -> {result}",
        extra={
            "log_module": module,
            "log_action": action,
            "log_duration_ms": duration_ms,
            "log_result": result,
            "log_req_id": req_id,
            **{f"log_{k}": v for k, v in extra.items()}
        }
    )


def log_process_event(logger: logging.Logger, module: str, action: str, 
                     pid: Optional[int] = None, cmd: str = "", **extra):
    """Log process lifecycle events."""
    logger.info(
        f"Process {action}: {module}",
        extra={
            "log_module": module,
            "log_action": action,
            "log_pid": pid,
            "log_cmd": cmd,
            **{f"log_{k}": v for k, v in extra.items()}
        }
    )
