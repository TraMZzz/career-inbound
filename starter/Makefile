# Course tools (folder tools/ of the course repo). Override for a local copy: make eval CI_TOOLS=path/to/tools
CI_TOOLS ?= git+https://github.com/TraMZzz/career-inbound@tools-v0.1.0\#subdirectory=tools
URL ?= http://localhost:8000
STAGE ?= 1
ENV_FILE := $(if $(wildcard .env),--env-file .env,)
CI := uvx --from "$(CI_TOOLS)"

.PHONY: dev test lint tools eval baseline compare perf attack check

dev:
	uv run $(ENV_FILE) uvicorn app.main:app --reload --port 8000

test:
	uv run pytest -q

lint:
	uv run ruff check . && uv run ruff format --check .

tools:
	@case '$(CI_TOOLS)' in *'<'*) echo "CI_TOOLS still has the GitHub owner placeholder: fix it in the Makefile or run make eval CI_TOOLS=git+https://github.com/OWNER/career-inbound#subdirectory=tools"; exit 1;; esac

eval: tools     ## evals/golden.jsonl -> evals/results.json
	$(CI) ci-eval run --url $(URL)

baseline:
	cp evals/results.json evals/baseline.json

compare: tools
	$(CI) ci-eval compare evals/baseline.json evals/results.json

perf: tools
	$(CI) ci-eval perf --url $(URL) --n 20 --exclude-tag edge

attack: tools
	$(CI) ci-eval attack --url $(URL)

check: tools    ## make check STAGE=2
	$(CI) ci-check --stage $(STAGE) --url $(URL)
