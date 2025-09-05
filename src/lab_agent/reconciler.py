"""Desired state reconciler for device agents."""

import json
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path

from .logging import log_command_execution


class StateReconciler:
    """Manages desired state persistence and reconciliation."""
    
    def __init__(self, device_id: str, state_file: Optional[Path] = None):
        self.device_id = device_id
        self.state_file = state_file or Path(f"/tmp/lab_agent_{device_id}_state.json")
        self.desired_state: Dict[str, Dict[str, Any]] = {}
        self.last_reconcile_time = 0
        self._load_state()
    
    def _load_state(self):
        """Load desired state from file."""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    self.desired_state = data.get("modules", {})
                    self.last_reconcile_time = data.get("last_reconcile", 0)
        except Exception as e:
            import logging
            logger = logging.getLogger(f"agent.{self.device_id}")
            logger.warning(f"Failed to load state file: {e}")
            self.desired_state = {}
    
    def _save_state(self):
        """Save desired state to file."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            
            state_data = {
                "device_id": self.device_id,
                "modules": self.desired_state,
                "last_reconcile": time.time(),
                "timestamp": datetime.utcnow().isoformat() + 'Z'
            }
            
            # Write to temporary file first, then rename (atomic operation)
            temp_file = self.state_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(state_data, f, indent=2, default=str)
            
            temp_file.replace(self.state_file)
            
        except Exception as e:
            import logging
            logger = logging.getLogger(f"agent.{self.device_id}")
            logger.error(f"Failed to save state file: {e}")
    
    def update_desired_state(self, module_name: str, state: Dict[str, Any]):
        """Update desired state for a module."""
        if module_name not in self.desired_state:
            self.desired_state[module_name] = {}
        
        self.desired_state[module_name].update(state)
        self.desired_state[module_name]["updated_at"] = time.time()
        
        self._save_state()
        
        import logging
        logger = logging.getLogger(f"agent.{self.device_id}")
        logger.info(
            f"Updated desired state for module {module_name}",
            extra={"log_module": module_name, "log_state": state}
        )
    
    def get_desired_state(self, module_name: str) -> Dict[str, Any]:
        """Get desired state for a module."""
        return self.desired_state.get(module_name, {})
    
    def clear_desired_state(self, module_name: str):
        """Clear desired state for a module."""
        if module_name in self.desired_state:
            del self.desired_state[module_name]
            self._save_state()
    
    def reconcile_module(self, module_name: str, module_instance) -> List[Dict[str, Any]]:
        """
        Reconcile module state with desired state.
        
        Returns:
            List of reconciliation actions taken
        """
        desired = self.get_desired_state(module_name)
        if not desired:
            return []
        
        actions = []
        logger = logging.getLogger(f"agent.{self.device_id}")
        
        try:
            # Get current module state
            current_status = module_instance.status_payload()
            current_fields = current_status.get("fields", {})
            
            # Check if reconciliation is needed
            needs_reconcile = self._needs_reconciliation(desired, current_fields)
            
            if not needs_reconcile:
                logger.debug(f"Module {module_name} state is already reconciled")
                return actions
            
            logger.info(f"Reconciling module {module_name} state")
            
            # Reconcile specific state items
            actions.extend(self._reconcile_process_state(module_name, module_instance, desired, current_fields))
            actions.extend(self._reconcile_configuration(module_name, module_instance, desired))
            actions.extend(self._reconcile_input_source(module_name, module_instance, desired, current_fields))
            
            # Update reconcile timestamp
            self.last_reconcile_time = time.time()
            self._save_state()
            
        except Exception as e:
            logger.error(f"Failed to reconcile module {module_name}: {e}")
            actions.append({
                "action": "reconcile_error",
                "module": module_name,
                "error": str(e),
                "timestamp": time.time()
            })
        
        return actions
    
    def _needs_reconciliation(self, desired: Dict[str, Any], current: Dict[str, Any]) -> bool:
        """Check if reconciliation is needed."""
        # Check process state
        if "process_running" in desired:
            current_running = current.get("pid") is not None
            if desired["process_running"] != current_running:
                return True
        
        # Check input source
        if "input_source" in desired:
            if desired["input_source"] != current.get("input"):
                return True
        
        # Check recording state
        if "recording" in desired:
            if desired["recording"] != current.get("recording", False):
                return True
        
        # Check configuration changes
        if "config" in desired:
            # This would compare configuration objects
            # Implementation depends on module specifics
            pass
        
        return False
    
    def _reconcile_process_state(self, module_name: str, module_instance, desired: Dict[str, Any], current: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Reconcile process running state."""
        actions = []
        
        if "process_running" not in desired:
            return actions
        
        should_run = desired["process_running"]
        is_running = current.get("pid") is not None
        
        logger = logging.getLogger(f"agent.{self.device_id}")
        
        if should_run and not is_running:
            # Should be running but isn't - start it
            try:
                input_source = desired.get("input_source") or current.get("input")
                if input_source:
                    start_time = time.time()
                    success, error, details = module_instance.handle_cmd("start", {"source": input_source})
                    duration = (time.time() - start_time) * 1000
                    
                    log_command_execution(
                        logger, module_name, "start", duration, 
                        "success" if success else "failed", 
                        extra={"reconcile": True, "input_source": input_source}
                    )
                    
                    actions.append({
                        "action": "start_process",
                        "module": module_name,
                        "success": success,
                        "input_source": input_source,
                        "error": error,
                        "timestamp": time.time()
                    })
                else:
                    logger.warning(f"Cannot start {module_name}: no input source specified")
                    
            except Exception as e:
                logger.error(f"Failed to start {module_name} during reconciliation: {e}")
                actions.append({
                    "action": "start_process",
                    "module": module_name,
                    "success": False,
                    "error": str(e),
                    "timestamp": time.time()
                })
        
        elif not should_run and is_running:
            # Should not be running but is - stop it
            try:
                start_time = time.time()
                success, error, details = module_instance.handle_cmd("stop", {})
                duration = (time.time() - start_time) * 1000
                
                log_command_execution(
                    logger, module_name, "stop", duration,
                    "success" if success else "failed",
                    extra={"reconcile": True}
                )
                
                actions.append({
                    "action": "stop_process",
                    "module": module_name,
                    "success": success,
                    "error": error,
                    "timestamp": time.time()
                })
                
            except Exception as e:
                logger.error(f"Failed to stop {module_name} during reconciliation: {e}")
                actions.append({
                    "action": "stop_process",
                    "module": module_name,
                    "success": False,
                    "error": str(e),
                    "timestamp": time.time()
                })
        
        return actions
    
    def _reconcile_input_source(self, module_name: str, module_instance, desired: Dict[str, Any], current: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Reconcile input source."""
        actions = []
        
        if "input_source" not in desired:
            return actions
        
        desired_input = desired["input_source"]
        current_input = current.get("input")
        
        if desired_input != current_input:
            logger = logging.getLogger(f"agent.{self.device_id}")
            
            try:
                start_time = time.time()
                success, error, details = module_instance.handle_cmd("set_input", {"source": desired_input})
                duration = (time.time() - start_time) * 1000
                
                log_command_execution(
                    logger, module_name, "set_input", duration,
                    "success" if success else "failed",
                    extra={"reconcile": True, "desired_input": desired_input, "current_input": current_input}
                )
                
                actions.append({
                    "action": "set_input_source",
                    "module": module_name,
                    "success": success,
                    "desired_input": desired_input,
                    "current_input": current_input,
                    "error": error,
                    "timestamp": time.time()
                })
                
            except Exception as e:
                logger.error(f"Failed to set input source for {module_name} during reconciliation: {e}")
                actions.append({
                    "action": "set_input_source",
                    "module": module_name,
                    "success": False,
                    "error": str(e),
                    "timestamp": time.time()
                })
        
        return actions
    
    def _reconcile_configuration(self, module_name: str, module_instance, desired: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Reconcile module configuration."""
        actions = []
        
        if "config" not in desired:
            return actions
        
        desired_config = desired["config"]
        logger = logging.getLogger(f"agent.{self.device_id}")
        
        try:
            # Apply configuration
            module_instance.apply_cfg(desired_config)
            
            actions.append({
                "action": "apply_configuration",
                "module": module_name,
                "success": True,
                "config": desired_config,
                "timestamp": time.time()
            })
            
            logger.info(f"Applied configuration to {module_name} during reconciliation")
            
        except Exception as e:
            logger.error(f"Failed to apply configuration to {module_name} during reconciliation: {e}")
            actions.append({
                "action": "apply_configuration",
                "module": module_name,
                "success": False,
                "error": str(e),
                "timestamp": time.time()
            })
        
        return actions
    
    def should_reconcile(self, min_interval_seconds: int = 60) -> bool:
        """Check if reconciliation should run based on time interval."""
        return time.time() - self.last_reconcile_time > min_interval_seconds
    
    def get_reconciliation_summary(self) -> Dict[str, Any]:
        """Get summary of current reconciliation state."""
        return {
            "device_id": self.device_id,
            "modules_with_desired_state": list(self.desired_state.keys()),
            "last_reconcile_time": self.last_reconcile_time,
            "state_file": str(self.state_file),
            "state_file_exists": self.state_file.exists(),
            "total_desired_states": len(self.desired_state)
        }


class ReconciliationScheduler:
    """Scheduler for periodic reconciliation."""
    
    def __init__(self, reconciler: StateReconciler, interval_seconds: int = 300):
        self.reconciler = reconciler
        self.interval_seconds = interval_seconds
        self._running = False
        self._thread = None
    
    def start(self):
        """Start periodic reconciliation."""
        if self._running:
            return
        
        self._running = True
        
        import threading
        self._thread = threading.Thread(
            target=self._reconciliation_loop,
            name=f"reconciler-{self.reconciler.device_id}",
            daemon=True
        )
        self._thread.start()
        
        import logging
        logger = logging.getLogger(f"agent.{self.reconciler.device_id}")
        logger.info(f"Started reconciliation scheduler (interval: {self.interval_seconds}s)")
    
    def stop(self):
        """Stop periodic reconciliation."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        
        import logging
        logger = logging.getLogger(f"agent.{self.reconciler.device_id}")
        logger.info("Stopped reconciliation scheduler")
    
    def _reconciliation_loop(self):
        """Main reconciliation loop."""
        import logging
        logger = logging.getLogger(f"agent.{self.reconciler.device_id}")
        
        while self._running:
            try:
                if self.reconciler.should_reconcile(self.interval_seconds):
                    # This would need access to module instances
                    # In practice, this would be called from the main agent
                    logger.debug("Reconciliation check - would reconcile if modules available")
                
                time.sleep(min(30, self.interval_seconds // 10))  # Check more frequently than interval
                
            except Exception as e:
                logger.error(f"Error in reconciliation loop: {e}")
                time.sleep(30)  # Wait before retrying
