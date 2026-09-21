.DEFAULT_GOAL := help

help:  ## list targets
	grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

install:  ## install dependencies, build the synthetic reference set and enable the pre-push hook
	uv sync
	$(MAKE) fixtures
	git config core.hooksPath .githooks

fixtures:  ## rebuild the synthetic reference documents; deterministic, no credentials
	uv run --group samples python samples/gerar_sinteticos.py samples

check:  ## format, lint, types and layers
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	uv run lint-imports

test:  ## unit and contract tests, fake profile, no network, no credentials
	DIS_PROFILE=fake uv run pytest tests/unit tests/contract -q

serve:  ## run the API locally with Swagger at http://127.0.0.1:8000/docs
	DIS_PROFILE=fake uv run uvicorn entrypoints.http.app:app --reload

demo:  ## analyse a medical certificate and print the response
	DIS_PROFILE=fake uv run python -m entrypoints.cli analisar samples/atestado_01_pdf_nativo.pdf

analisar:  ## analyse any file: make analisar FILE=samples/atestado_06_captura_tela.png
	@test -n "$(FILE)" || { echo "usage: make analisar FILE=<caminho>"; exit 2; }
	DIS_PROFILE=fake uv run python -m entrypoints.cli analisar $(FILE)

coverage:  ## the suite plus the core coverage gate. `test` is the same run, without the gate
	DIS_PROFILE=fake uv run pytest tests/unit tests/contract -q \
		--cov=src/core --cov-report=term-missing --cov-fail-under=90

ci:  ## everything the pipeline runs, in one command; works on a fresh clone
	$(MAKE) fixtures
	$(MAKE) check
	$(MAKE) coverage
	$(MAKE) eval

# Each profile has its own frozen baseline: fake and aws numbers are never compared.
# `make eval PROFILE=aws` needs AWS credentials, DIS_KENDRA_INDEX_ID and DIS_BEDROCK_GUARDRAIL_ID.
PROFILE ?= fake
BASELINE = $(if $(filter aws,$(PROFILE)),evals/baseline-aws.json,evals/baseline.json)

eval:  ## regression against the frozen baseline of PROFILE (fake by default); non-zero exit on regression
	uv run python -m evals.run --profile $(PROFILE) --baseline $(BASELINE)

eval-baseline:  ## freeze the current numbers of PROFILE as its baseline; review the diff before committing
	uv run python -m evals.run --profile $(PROFILE) --output evals/reports
	uv run python -c "import json,pathlib; d=json.loads(pathlib.Path('evals/reports/report.json').read_text()); d.pop('regressions',None); pathlib.Path('$(BASELINE)').write_text(json.dumps(d,ensure_ascii=False,indent=2)+chr(10))"

.PHONY: help install check test coverage ci serve demo analisar fixtures eval eval-baseline
