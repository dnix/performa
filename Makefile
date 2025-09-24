.DEFAULT_GOAL := help

# Colors for output
CYAN := \033[36m
RESET := \033[0m
GREEN := \033[32m
YELLOW := \033[33m

.PHONY: help
help: ## View help information
	@echo "$(CYAN)Available targets:$(RESET)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-20s$(RESET) %s\n", $$1, $$2}'

.PHONY: check-asdf
check-asdf: ## Check if asdf is installed
	@command -v asdf >/dev/null 2>&1 || (echo "$(YELLOW)asdf is not installed. Please install it first.$(RESET)" && exit 1)

.PHONY: asdf-bootstrap
asdf-bootstrap: check-asdf ## Install and configure all tools through asdf
	@echo "$(CYAN)Setting up asdf tools...$(RESET)"
	@asdf plugin-add python 2>/dev/null || echo "Python plugin already installed"
	@asdf install
	@echo "$(GREEN)asdf setup complete!$(RESET)"

.PHONY: check-uv
check-uv: ## Check if uv is available
	@command -v uv >/dev/null 2>&1 || (echo "$(YELLOW)uv not found. Installing via asdf python...$(RESET)" && asdf exec pip install uv)

.PHONY: venv
venv: asdf-bootstrap check-uv ## Create python virtual environment using uv
	@echo "$(CYAN)Creating virtual environment...$(RESET)"
	@test -d .venv || asdf exec uv venv
	@echo "$(GREEN)Virtual environment created!$(RESET)"

.PHONY: install
install: venv ## Install project dependencies with dev extras
	@echo "$(CYAN)Installing dependencies...$(RESET)"
	@uv sync --extra dev
	@echo "$(GREEN)Dependencies installed!$(RESET)"

.PHONY: install-all
install-all: venv ## Install all dependency groups (current and future)
	@echo "$(CYAN)Installing all dependencies...$(RESET)"
	@uv sync --all-extras
	@echo "$(GREEN)All dependencies installed!$(RESET)"

.PHONY: install-prod
install-prod: venv ## Install only production dependencies
	@echo "$(CYAN)Installing production dependencies...$(RESET)"
	@uv sync
	@echo "$(GREEN)Production dependencies installed!$(RESET)"

.PHONY: activate
activate: ## Show how to activate the virtual environment
	@echo "$(CYAN)To activate the virtual environment, run:$(RESET)"
	@echo "  source .venv/bin/activate"
	@echo ""
	@echo "$(CYAN)Or use uv to run commands directly:$(RESET)"
	@echo "  uv run python your_script.py"
	@echo "  uv run pytest"

.PHONY: update
update: ## Update dependencies to latest compatible versions
	@echo "$(CYAN)Updating dependencies...$(RESET)"
	@uv sync --upgrade
	@echo "$(GREEN)Dependencies updated!$(RESET)"

.PHONY: lint
lint: ## Run linting with ruff
	@echo "$(CYAN)Running linter...$(RESET)"
	@uv run ruff check .
	@uv run ruff format --check .

.PHONY: lint-fix
lint-fix: ## Run linting with automatic fixes
	@echo "$(CYAN)Running linter with fixes...$(RESET)"
	@uv run ruff check --fix .
	@uv run ruff format .

.PHONY: test
test: ## Run tests with pytest
	@echo "$(CYAN)Running tests...$(RESET)"
	@uv run pytest

.PHONY: test-cov
test-cov: ## Run tests with coverage report
	@echo "$(CYAN)Running tests with coverage...$(RESET)"
	@uv run pytest --cov=src --cov-report=html --cov-report=term

.PHONY: clean
clean: ## Clean up temporary files and caches
	@echo "$(CYAN)Cleaning up...$(RESET)"
	@rm -rf .ruff_cache/
	@rm -rf .pytest_cache/
	@rm -rf __pycache__/
	@rm -rf src/**/__pycache__/
	@rm -rf htmlcov/
	@rm -rf .coverage
	@rm -rf dist/
	@rm -rf build/
	@rm -rf *.egg-info/
	@echo "$(GREEN)Cleanup complete!$(RESET)"

.PHONY: clean-all
clean-all: clean ## Clean everything including virtual environment
	@echo "$(CYAN)Removing virtual environment...$(RESET)"
	@rm -rf .venv/
	@echo "$(GREEN)Full cleanup complete!$(RESET)"

.PHONY: dev-setup
dev-setup: install ## Complete development environment setup
	@echo "$(GREEN)Development environment is ready!$(RESET)"
	@echo "$(CYAN)Next steps:$(RESET)"
	@echo "  1. source .venv/bin/activate"
	@echo "  2. uv run pytest  # run tests"
	@echo "  3. uv run ruff check .  # run linter"

.PHONY: check
check: ## Verify the setup is working
	@echo "$(CYAN)Checking setup...$(RESET)"
	@asdf current python
	@uv --version
	@test -d .venv && echo "$(GREEN)✓ Virtual environment exists$(RESET)" || echo "$(YELLOW)✗ Virtual environment missing$(RESET)"
	@uv run python -c "import performa; print('✓ Package importable')" 2>/dev/null || echo "$(YELLOW)✗ Package not importable$(RESET)"

.PHONY: build
build: ## Build the package
	@echo "$(CYAN)Building package...$(RESET)"
	@uv build
	@echo "$(GREEN)Package built!$(RESET)"

.PHONY: shell
shell: ## Start an interactive Python shell with the project environment
	@uv run python
