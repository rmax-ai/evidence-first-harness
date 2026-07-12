.PHONY: install test lint format typecheck check clean run docker-build docker-up docker-down

install:
	uv sync
	uv sync --extra dev

test:
	uv run pytest tests/ -v

test-unit:
	uv run pytest tests/unit/ -v

test-integration:
	uv run pytest tests/integration/ -v

test-sandbox:
	uv run pytest tests/ -v -m sandbox

test-cov:
	uv run pytest tests/ --cov=src/evidence_first_harness --cov-report=term-missing

lint:
	uv run ruff check src/ tests/

format:
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

typecheck:
	uv run pyright src/

check: lint typecheck test
	@echo "All checks passed"

clean:
	rm -rf .pytest_cache .ruff_cache __pycache__ .coverage htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '*.egg-info' -exec rm -rf {} + 2>/dev/null || true

run:
	uv run efh

docker-build:
	docker build -t evidence-first-harness .

docker-up:
	docker compose up -d

docker-down:
	docker compose down
