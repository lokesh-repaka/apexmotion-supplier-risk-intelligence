# ==============================================================================
# ApexMotion Supplier Risk Intelligence Platform — Developer Makefile
# Central developer command interface for backend, frontend, testing, and infra.
# Reference: TASKS.md (P2-5) & GEMINI.md Section 2
# ==============================================================================

.DEFAULT_GOAL := help

.PHONY: help run-api run-worker run-frontend test test-unit test-golden test-coverage lint format type-check seed up down clean

PYTHON ?= python3
HOST ?= 0.0.0.0
PORT ?= 8000

# ------------------------------------------------------------------------------
# 1. Developer Help & Discovery
# ------------------------------------------------------------------------------
.PHONY: help
help: ## Display this target catalog with available commands
	@echo "ApexMotion Developer Commands:"
	@echo ""
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""

# ------------------------------------------------------------------------------
# 2. Application Runtime Commands
# ------------------------------------------------------------------------------
.PHONY: run-api
run-api: ## Run FastAPI backend with uvicorn reload on port 8000
	uvicorn src.api.main:app --reload --host $(HOST) --port $(PORT)

.PHONY: run-worker
run-worker: ## Run Kafka signal consumption worker loop
	$(PYTHON) -m src.kafka.consumer

.PHONY: run-frontend
run-frontend: ## Run React 18/Vite frontend development server
	cd frontend && npm run dev

# ------------------------------------------------------------------------------
# 3. Test Suites & Verification
# ------------------------------------------------------------------------------
.PHONY: test
test: ## Run unit tests offline with zero external network I/O
	USE_LOCALSTACK=true USE_MOCK_LLM=true USE_LOCAL_KAFKA=true pytest tests/unit/ -v

.PHONY: test-unit
test-unit: ## Run unit tests offline (alias for test)
	USE_LOCALSTACK=true USE_MOCK_LLM=true USE_LOCAL_KAFKA=true pytest tests/unit/ -v

.PHONY: test-golden
test-golden: ## Run NanoCore golden reference scenario tests
	pytest tests/golden/ -v

.PHONY: test-coverage
test-coverage: ## Run unit tests and enforce >=80% statement coverage
	USE_LOCALSTACK=true USE_MOCK_LLM=true USE_LOCAL_KAFKA=true pytest --cov=src --cov-fail-under=80 tests/unit/

# ------------------------------------------------------------------------------
# 4. Code Quality, Formatting & Static Typing
# ------------------------------------------------------------------------------
.PHONY: lint
lint: ## Run code linters (ruff) and static type checker (mypy)
	ruff check src/ tests/
	ruff format --check src/ tests/
	mypy src/

.PHONY: format
format: ## Auto-format and organize imports with ruff
	ruff check --fix src/ tests/
	ruff format src/ tests/

.PHONY: type-check
type-check: ## Run mypy static type checking
	mypy src/

# ------------------------------------------------------------------------------
# 5. Local Infrastructure & Seeding
# ------------------------------------------------------------------------------
.PHONY: seed
seed: ## Bootstrap local infrastructure stores and seed demo datasets
	bash scripts/localstack_bootstrap.sh
	bash scripts/redpanda_topics.sh
	bash scripts/neptune_smoke_test.sh --dry-run

.PHONY: up
up: ## Start local backing store containers with docker-compose
	docker compose up -d

.PHONY: down
down: ## Stop and remove local backing store containers
	docker compose down

# ------------------------------------------------------------------------------
# 6. Housekeeping & Cache Cleanup
# ------------------------------------------------------------------------------
.PHONY: clean
clean: ## Remove temporary build, test, and bytecode artifacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov coverage.xml build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
