# Device Agent Makefile

.PHONY: help install run test clean health setup-config

help: ## Show this help message
	@echo 'Lab Platform Device Agent Commands:'
	@echo ''
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install device agent
	pip install -e .

setup-config: ## Create .env from example
	cp env.example .env
	@echo "Edit .env with your device settings"

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
	@echo "Service installed. Configure .env then: sudo systemctl start lab-agent"

# Development helpers
dev-ndi: ## Run with NDI module for development
	DEVICE_ID=dev-ndi-01 DEVICE_LABELS=ndi,development MQTT_HOST=localhost lab-agent

dev-projector: ## Run with projector module for development  
	DEVICE_ID=dev-proj-01 DEVICE_LABELS=projector,development MQTT_HOST=localhost lab-agent
