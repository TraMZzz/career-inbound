.PHONY: dev test lint data

dev:            ## run the API with reload on http://localhost:8000
	uv run uvicorn app.main:app --reload --port 8000

test:           ## unit tests (no network, no API key)
	uv run pytest -q

lint:
	uv run ruff check . && uv run ruff format --check .

data:           ## regenerate demo-shop data (deterministic)
	uv run python -m demo_shop generate
