.PHONY: setup migrate run frontend frontend-test frontend-build lint lint-fix format check test test-cov help

setup:
	uv sync --extra dev

migrate:
	uv run alembic upgrade head

run:
	uv run uvicorn main:app --host 0.0.0.0 --port 8080

frontend:
	cd ../frontend && npm run dev

frontend-test:
	cd ../frontend && npm test

frontend-build:
	cd ../frontend && npm run build

lint:
	uv run ruff check src tests main.py

lint-fix:
	uv run ruff check --fix src tests main.py

format:
	uv run ruff format src tests main.py

check:
	uv run ruff format --check src tests main.py
	uv run ruff check src tests main.py
	uv run mypy src main.py

test:
	uv run pytest

test-cov:
	uv run pytest --cov=src --cov-report=term-missing --cov-report=xml

help:
	@echo "setup migrate run frontend frontend-test frontend-build lint lint-fix format check test test-cov"
