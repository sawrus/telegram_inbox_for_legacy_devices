VENV ?= .venv
PYTHON ?= $(VENV)/bin/python

.PHONY: install dev test lint fmt clean build help

install: ## Install Python dependencies
	python3 -m venv $(VENV)
	$(PYTHON) -m pip install -r requirements.txt

dev: ## Run the Flask app locally
	$(VENV)/bin/flask --app wsgi:app run --host 0.0.0.0 --port 8080 --debug

test: ## Run tests
	$(PYTHON) -m pytest

lint: ## Run syntax checks
	$(PYTHON) -m compileall app tests scripts wsgi.py

fmt: ## Formatting is manual for this small project
	@echo "No formatter is configured."

clean: ## Remove Python caches
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +

build: ## Build Docker image
	docker compose build

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'
