# Project Makefile

PROJECT := modSim
SERVICE_LOC := /etc/systemd/system

ROOT_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

default:
	@echo "Valid make commands are:"
	@echo "  install:	Install and setup virtualenv"
	@echo "  stop:		Stop the service"
	@echo "  start:		Start the service"
	@echo "  restart:	Restart the service"
	@echo "  local:		Create a local instance"
.PHONY: default

install: virt
ifneq ($(shell id -u), 0)
	@echo "You must be root to perform this action."
else
	@echo "Creating service file..."
	@ln -sf $(ROOT_DIR)/$(PROJECT).service $(SERVICE_LOC)/$(PROJECT).service
	systemctl daemon-reload
	systemctl enable $(PROJECT)
	systemctl start $(PROJECT)

	@echo "Install complete"
endif
.PHONY: install

stop:
	@echo "Stopping the service."
	systemctl stop $(PROJECT)
.PHONY: stop

start:
	@echo "Starting the service."
	systemctl start $(PROJECT)
.PHONY: start

restart:
ifneq ($(shell id -u), 0)
	@echo "You must be root to perform this action."
else
	systemctl restart $(PROJECT)
	@sleep 10
	@echo "Restart complete"
endif
.PHONY: restart

virt:
	@echo "Creating virtual environment..."

	@python3 -m venv $(ROOT_DIR)/env
	@$(ROOT_DIR)/env/bin/pip install --upgrade pip
	@$(ROOT_DIR)/env/bin/pip install -r $(ROOT_DIR)/requirements.txt

	@echo "Environment created."
.PHONY: virt

local: virt
.PHONY: local