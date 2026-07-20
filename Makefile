# Maisha-Mahsa — build & verify gate. See CLAUDE.md §6.
.DEFAULT_GOAL := help
SHELL := /bin/bash
PY := api/.venv/bin/python
PIP := api/.venv/bin/pip
# Prefer a rustup-installed cargo; fall back to PATH.
CARGO := $(shell [ -x "$$HOME/.cargo/bin/cargo" ] && echo "$$HOME/.cargo/bin/cargo" || echo cargo)

.PHONY: help verify test test-rust test-py eval eval-real capture brief dunning scheduler lint fmt venv dev clean migrate

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n",$$1,$$2}'

venv: ## Create the Python venv and install api in editable mode
	python3 -m venv api/.venv
	$(PIP) install --upgrade pip
	$(PIP) install -e "api[dev]"

verify: lint test eval ## Full gate: lint + all tests + golden-eval (green before marking a module done)
	@echo "✅ verify passed"

test: test-rust test-py ## Run all tests

eval: ## Golden-eval gate for the Maisha LLM layer (stub producer — the CI gate, no model)
	cd api && .venv/bin/python -m evals.harness --all

eval-real: ## Run the golden eval against a live model (MAISHA_LLM_PROVIDER, e.g. ollama)
	cd api && .venv/bin/python -m evals.harness --all --provider ollama --report text

migrate: ## Apply DB schema migrations (alembic upgrade head) — the production schema path
	cd api && .venv/bin/alembic upgrade head

seed: ## Load a realistic sample company (dev only) so screens show real numbers
	cd api && .venv/bin/python -m app.dev.seed

capture: ## Run the snapshot-capture job once (records metrics for trend charts)
	cd api && .venv/bin/python -m app.jobs capture

dunning: ## Send overdue-invoice reminders once (needs SMTP/MailHog up)
	cd api && .venv/bin/python -m app.jobs dunning

alerts: ## Dispatch statutory compliance alerts (T-7/T-1/T-0/overdue) once (needs SMTP/MailHog)
	cd api && .venv/bin/python -m app.jobs alerts

brief: ## Send the daily CFO brief once (needs Mahsa + SMTP/MailHog up)
	cd api && .venv/bin/python -m app.jobs brief

scheduler: ## Run the long-lived scheduler loop (daily capture + 8pm brief)
	cd api && .venv/bin/python -m app.jobs serve

test-rust: ## cargo test for the Mahsa DIF core
	cd dif && $(CARGO) test

test-py: ## pytest unit + integration for the Maisha API
	cd api && .venv/bin/pytest -q

lint: gates ## ruff + mypy + clippy + statutory grep-gates (warnings are errors)
	cd api && .venv/bin/ruff check . && .venv/bin/mypy app evals
	cd dif && $(CARGO) clippy --all-targets -- -D warnings

gates: ## MMX-1.0 grep-gates (QG.3): truncate-then-round, draft-IRN honesty, RLS coverage, etc.
	bash scripts/check_no_truncate_round.sh
	bash scripts/check_no_draft_irn.sh
	bash scripts/check_rls_coverage.sh

fmt: ## Format Rust + Python
	cd dif && $(CARGO) fmt
	cd api && .venv/bin/ruff format .

dev: ## Bring up the full stack
	cd infra && docker compose up --build

clean: ## Remove build artifacts
	cd dif && cargo clean
	rm -rf api/.venv api/.pytest_cache api/.ruff_cache
