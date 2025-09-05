# Device Agent Makefile

.PHONY: help install run test clean health setup-config

help: ## Show this help message
	@echo 'Lab Platform Device Agent Commands:'
	@echo ''
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install device agent
	pip install -e .

setup-config: ## Create config.yaml from example
	cp config.yaml.example config.yaml
	@echo "Edit config.yaml with your device settings"

run: ## Run device agent
	lab-agent

test: ## Run tests
	pytest tests/ -v

clean: ## Clean up log files and temp data
	rm -f *.log
	rm -f /tmp/lab_agent_*.json
	rm -f /tmp/*_lab-*.log

health: ## Check agent health (if HTTP server enabled)
	@curl -f http://localhost:8080/health 2>/dev/null || echo "Health server not running (this is optional)"

logs: ## Show recent logs
	tail -f *.log 2>/dev/null || echo "No log files found"

debug: ## Run with debug logging
	LOG_LEVEL=DEBUG lab-agent

install-system: ## Install as system service (Linux)
	@echo "Creating systemd service..."
	sudo cp lab-agent.service /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl enable lab-agent
	@echo "Service installed. Configure config.yaml then: sudo systemctl start lab-agent"

# Development helpers
dev-ndi: ## Run with NDI module for development
	@echo "device_id: dev-ndi-01" > dev-config.yaml
	@echo "modules: {ndi: {}}" >> dev-config.yaml
	@echo "mqtt: {host: localhost, port: 1883}" >> dev-config.yaml
	AGENT_CONFIG=dev-config.yaml lab-agent

dev-projector: ## Run with projector module for development  
	@echo "device_id: dev-proj-01" > dev-config.yaml
	@echo "modules: {projector: {}}" >> dev-config.yaml
	@echo "mqtt: {host: localhost, port: 1883}" >> dev-config.yaml
	AGENT_CONFIG=dev-config.yaml lab-agent
