RUFF := $(shell command -v ruff 2>/dev/null || echo ~/.local/bin/ruff)

.PHONY: fix check setup

setup:
	@command -v ruff >/dev/null 2>&1 || (echo "Installing Ruff..." && curl -LsSf https://astral.sh/ruff/install.sh | sh)

fix: setup
	$(RUFF) check --fix .
	$(RUFF) format .

check: setup
	$(RUFF) check .
	$(RUFF) format --check .
