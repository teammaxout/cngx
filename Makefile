.PHONY: help install dev test lint format build publish clean docker docs demo

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install Cogscope (core only)
	pip install -e .

dev: ## Install Cogscope with all dev dependencies
	pip install -e ".[all,dev,docs]"

test: ## Run all tests (no API keys needed)
	python -m pytest tests/ -v --noconftest -x

test-unit: ## Run unit tests only
	python -m pytest tests/unit/ -v --noconftest

test-integration: ## Run integration tests
	python tests/integration/test_e2e_pipeline.py

test-coverage: ## Run tests with coverage report
	python -m pytest tests/ --noconftest --cov=cogscope --cov-report=html --cov-report=term

lint: ## Run linters (ruff)
	ruff check cogscope/ tests/
	ruff format --check cogscope/ tests/

format: ## Auto-format code
	ruff format cogscope/ tests/
	ruff check --fix cogscope/ tests/

typecheck: ## Run type checker
	mypy cogscope/ --ignore-missing-imports

build: ## Build package
	python -m build

publish: ## Publish to PyPI (requires credentials)
	python -m build
	twine upload dist/*

clean: ## Remove build artifacts
	rm -rf build/ dist/ *.egg-info .cogscope/ htmlcov/ .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

docker: ## Build Docker image
	docker build -t cogscope:latest .

docs: ## Build documentation site
	mkdocs build

docs-serve: ## Serve docs locally
	mkdocs serve

demo: ## Run the full system demo (no API keys needed)
	python examples/basic_usage.py

demo-e2e: ## Run integration pipeline tests
	python -m pytest tests/integration/test_full_pipeline.py -v

gate-mock: ## Run a sample gate check with mock adapter
	cogscope gate check "Solve x^2 + 5x + 6 = 0" \
		--contract contracts/math_correctness.yaml \
		--adapter mock \
		--model mock-model

version: ## Show Cogscope version
	cogscope version
