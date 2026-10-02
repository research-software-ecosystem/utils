# Keep in step with RUFF_VERSION in .github/workflows/lint.yml. A different
# local ruff reports different findings, which is how a branch passed
# `make check` here and still failed the lint job.
RUFF_VERSION := 0.16.10
RUFF := $(shell command -v ruff 2>/dev/null || echo ~/.local/bin/ruff)

.PHONY: fix check setup verify-ruff

setup:
	@command -v $(RUFF) >/dev/null 2>&1 || (echo "Installing Ruff $(RUFF_VERSION)..." && curl -LsSf https://astral.sh/ruff/$(RUFF_VERSION)/install.sh | sh)

verify-ruff: setup
	@have=$$($(RUFF) --version 2>/dev/null | awk "{print \$$2}"); \
	if [ "$$have" != "$(RUFF_VERSION)" ]; then \
	  echo "ruff $$have is on PATH, but CI pins $(RUFF_VERSION): results will not match."; \
	  echo "  curl -LsSf https://astral.sh/ruff/$(RUFF_VERSION)/install.sh | sh"; \
	  exit 1; \
	fi

fix: verify-ruff
	$(RUFF) check --fix .
	$(RUFF) format .

check: verify-ruff
	$(RUFF) check .
	$(RUFF) format --check .
