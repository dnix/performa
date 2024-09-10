.DEFAULT_GOAL := help

.PHONY: help
help: ## View help information
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $ $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: asdf-bootstrap
asdf-bootstrap: ## Install all tools through asdf
	@asdf plugin-add python > /dev/null || true
	@asdf install

.PHONY: venv
venv: ## Create python venv using asdf
	@test -d .venv/ || asdf exec python -m venv .venv && source .venv/bin/activate && (\
		pip install uv \
		uv pip install -r requirements.txt \
		uv pip install -e . \
	)

.PHONY: activate
activate: ## Activate python venv
	@test -d .venv/ && source .venv/bin/activate

.PHONY: install
install: # Install dependencies (pre-existing venv)
	@test -d .venv/ && source .venv/bin/activate && ( \
		uv pip install -r requirements.txt \
		uv pip install -e . \
	)
