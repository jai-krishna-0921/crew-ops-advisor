.DEFAULT_GOAL := help
SHELL := /bin/bash
API := api
WEB := web
# Local VoiceKit is intentionally disabled for hosting. Uncomment only for
# optional local experiments.
# VOICE_DIR ?= ../voice
# VOICE_PYTHON ?= python3.12

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ----------------------------------------------------------------- setup

.PHONY: install
install: install-api install-web ## Install everything

.PHONY: install-api
install-api: ## Python env via uv
	cd $(API) && uv sync --extra dev

.PHONY: install-web
install-web: ## Web deps via pnpm
	cd $(WEB) && pnpm install

.PHONY: test-web
# Local VoiceKit targets are intentionally commented out for hosted deployments.
# .PHONY: install-voice voice voice-download dev-voice test-web
# install-voice: ## Optional local speech dependencies (Python 3.10 through 3.12)
# 	test -x "$(VOICE_DIR)/.venv/bin/python" || "$(VOICE_PYTHON)" -m venv "$(VOICE_DIR)/.venv"
# 	"$(VOICE_DIR)/.venv/bin/python" -m pip install -e "$(VOICE_DIR)[stt,tts,api]"

# voice: ## Local VoiceKit on :8001, with the repository environment loaded
# 	$(API)/.venv/bin/python scripts/voice_service.py serve --voice-dir "$(VOICE_DIR)"

# voice-download: ## Download local speech models before going offline
# 	$(API)/.venv/bin/python scripts/voice_service.py download --voice-dir "$(VOICE_DIR)"

# dev-voice: ## Local voice, API, and web together
# 	@trap 'kill 0' EXIT INT TERM; \
# 	$(MAKE) voice & \
# 	$(MAKE) dev & \
# 	wait

test-web: ## Browser voice lifecycle and component tests, no API keys needed
	cd $(WEB) && pnpm test

# ----------------------------------------------------------------- run

.PHONY: dev
dev: ## API on :8000 and web on :3000 together
	@echo "API  http://localhost:8000"
	@echo "Web  http://localhost:3000"
	@trap 'kill 0' EXIT INT TERM; \
	( cd $(API) && uv run uvicorn --factory crewops.server.app:create_app --reload --port 8000 ) & \
	( cd $(WEB) && pnpm dev ) & \
	wait

.PHONY: serve
serve: ## API only
	cd $(API) && uv run uvicorn --factory crewops.server.app:create_app --reload --port 8000

.PHONY: web
web: ## Web only
	cd $(WEB) && pnpm dev

# ----------------------------------------------------------------- checks

.PHONY: test
test: ## Full Python suite
	cd $(API) && uv run pytest

.PHONY: golden
golden: ## Answer-key parity against the shipped questions and scenarios
	cd $(API) && uv run pytest -m golden -v

.PHONY: eval
eval: ## Scorecard across all 38 questions, every tier
	cd $(API) && uv run python -m crewops.eval.scorecard

.PHONY: lint
lint: ## ruff and eslint
	cd $(API) && uv run ruff check . && uv run ruff format --check .
	cd $(WEB) && pnpm lint

.PHONY: types
types: ## mypy and tsc
	cd $(API) && uv run mypy
	cd $(WEB) && pnpm exec tsc --noEmit

.PHONY: boundary
boundary: ## Assert no model client is imported by the deterministic core
	cd $(API) && uv run pytest tests/test_boundary.py -v

.PHONY: check
check: lint types boundary test test-web ## Everything CI runs

.PHONY: validate-data
validate-data: ## Run the dataset's own validator, read only
	python3 data/crew-ops-advisor-dataset/validate.py

.PHONY: build
build: ## Production web build
	cd $(WEB) && pnpm build

.PHONY: clean
clean: ## Remove build and cache artefacts. Never touches data/
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf $(API)/.pytest_cache $(API)/.ruff_cache $(API)/.mypy_cache
	rm -rf $(WEB)/.next $(WEB)/out
	@echo "Cleaned. data/ untouched."
