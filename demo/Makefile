CI_TOOLS ?= ../tools
URL ?= http://localhost:8000
ENV_FILE := $(if $(wildcard .env),--env-file .env,)
# --refresh-package: pick up edits in ../tools (uv caches local builds by pyproject.toml only)
CI := uvx --refresh-package ci-tools --from "$(CI_TOOLS)"

.PHONY: dev test lint data eval baseline compare perf attack check

dev:            ## run the API with reload on http://localhost:8000 (reads .env if present)
	uv run $(ENV_FILE) uvicorn app.main:app --reload --port 8000

test:           ## unit tests (no network, no API key)
	uv run pytest -q

lint:
	uv run ruff check . && uv run ruff format --check .

data:           ## regenerate demo-shop data and the golden set (deterministic)
	uv run python -m demo_shop generate

eval:           ## golden set against the running API -> evals/results.json
	$(CI) ci-eval run --url $(URL)

baseline:       ## keep the current results as the baseline to compare against
	cp evals/results.json evals/baseline.json

compare:        ## what changed since the baseline
	$(CI) ci-eval compare evals/baseline.json evals/results.json

perf:
	$(CI) ci-eval perf --url $(URL) --n 20 --exclude-tag edge

attack:
	$(CI) ci-eval attack --url $(URL)

check:          ## course self-check for stage 2 against the running API
	$(CI) ci-check --stage 2 --url $(URL)
