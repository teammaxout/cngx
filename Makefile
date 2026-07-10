.PHONY: help install dev test lint format build publish clean docker docs demo

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install cngx (core only)
	pip install -e .

dev: ## Install cngx with all dev dependencies
	pip install -e ".[all,dev,docs]"

test: ## Run all tests (no API keys needed)
	python -m pytest tests/ -q --tb=short

test-unit: ## Run unit tests only
	python -m pytest tests/unit/ -q --tb=short

test-integration: ## Run integration tests
	python -m pytest tests/integration/ -q --tb=short

test-coverage: ## Run tests with coverage report
	python -m pytest tests/ --cov=cngx --cov-report=html --cov-report=term

lint: ## Run linters (ruff)
	ruff check cngx/ tests/
	ruff format --check cngx/ tests/

format: ## Auto-format code
	ruff format cngx/ tests/
	ruff check --fix cngx/ tests/

typecheck: ## Run type checker
	mypy cngx/ --ignore-missing-imports

build: ## Build package
	python -m build

publish: ## Publish to PyPI (requires credentials)
	python -m build
	twine upload dist/*

clean: ## Remove build artifacts
	rm -rf build/ dist/ *.egg-info .cngx/ htmlcov/ .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

docker: ## Build Docker image
	docker build -t cngx:latest .

docs: ## Build documentation site
	mkdocs build

docs-serve: ## Serve docs locally
	mkdocs serve

demo: ## Run the full system demo (no API keys needed)
	python examples/basic_usage.py

demo-e2e: ## Run integration pipeline tests
	python -m pytest tests/integration/test_full_pipeline.py -v

gate-mock: ## Run a sample gate check with mock adapter
	cngx check -c examples/contracts/basic_reasoning.yaml \
		"Solve x^2 + 5x + 6 = 0" \
		--adapter mock \
		--model mock-model

version: ## Show cngx version
	cngx version
