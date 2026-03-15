# Symphony Makefile
# Quick commands for development and deployment

.PHONY: help install install-dev test lint format clean docker-build docker-run

# Default target
help:
	@echo "Symphony - Available commands:"
	@echo ""
	@echo "  make install       - Install Symphony via pip"
	@echo "  make install-dev   - Install in development mode"
	@echo "  make test          - Run tests"
	@echo "  make lint          - Run linters"
	@echo "  make format        - Format code"
	@echo "  make clean         - Clean build artifacts"
	@echo ""
	@echo "Docker commands:"
	@echo "  make docker-build  - Build Docker image"
	@echo "  make docker-run    - Run with Docker Compose"
	@echo "  make docker-stop   - Stop Docker containers"
	@echo ""
	@echo "Development commands:"
	@echo "  make init          - Initialize Symphony configuration"
	@echo "  make doctor        - Run environment diagnostics"
	@echo "  make run           - Run Symphony orchestrator"
	@echo ""

# Installation
install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"
	pre-commit install

# Testing
test:
	pytest -v -m "not llm and not slow"

test-all:
	pytest -v

test-llm:
	pytest -v -m llm

test-unit:
	pytest -v -m "not llm and not slow and not integration"

test-integration:
	pytest -v -m integration

test-cov:
	pytest --cov=symphony --cov-report=html --cov-report=term

test-fast:
	pytest -v -m "not llm and not slow" --timeout=10 -x

test-parallel:
	pytest -v -m "not llm and not slow" -n auto

# Linting and formatting
lint:
	ruff check src tests
	mypy src

format:
	ruff check --fix src tests
	ruff format src tests

# Cleanup
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

# Docker commands
docker-build:
	docker-compose build

docker-run:
	docker-compose up -d

docker-stop:
	docker-compose down

docker-logs:
	docker-compose logs -f symphony

# Development workflow
init:
	@python -m symphony.cli init

doctor:
	@python -m symphony.cli doctor

run:
	@python -m symphony.cli run WORKFLOW.md --verbose

run-dashboard:
	@python -m symphony.cli run WORKFLOW.md --dashboard

validate:
	@python -m symphony.cli validate WORKFLOW.md

# Release
build:
	python -m build

upload:
	python -m twine upload dist/*
