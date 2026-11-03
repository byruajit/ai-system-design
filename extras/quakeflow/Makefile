.PHONY: install dev-install db-up db-down run dry-run test lint format ci clean

install:
	pip install -e .

dev-install:
	pip install -e ".[dev]"
	pre-commit install

db-up:
	docker compose up -d postgres

db-down:
	docker compose down -v

init-db:
	quakeflow init-db

run:
	quakeflow run --days 3

dry-run:
	quakeflow run --days 1 --dry-run

stats:
	quakeflow stats

test:
	pytest --cov=quakeflow --cov-report=term-missing

lint:
	ruff check .
	ruff format --check .

format:
	ruff check . --fix
	ruff format .

ci: lint test

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage build dist
