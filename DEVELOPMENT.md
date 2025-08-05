# Development Guide

This guide covers everything you need to know for developing with and contributing to Performa.

## Quick Start

The fastest way to get started with development:

```bash
git clone https://github.com/performa-dev/performa.git
cd performa
make dev-setup
```

This single command will:

- Set up asdf and install the correct Python version
- Create a virtual environment using uv
- Install all dependencies (including dev dependencies)
- Install the package in editable mode

Verify everything is working:

```bash
make check
```

## Installation for Development

### Recommended: Using the Makefile

```bash
# Complete development environment setup
make dev-setup

# Or step by step:
make asdf-bootstrap  # Set up asdf and Python
make venv           # Create virtual environment
make install        # Install dependencies
```

### From Source (Alternative Method)

```bash
git clone https://github.com/performa-dev/performa.git
cd performa
pip install -e .
```

This installs Performa in editable mode, allowing you to make changes to the source code and immediately see the effects without needing to reinstall.

### Development Environment Setup

#### Using `uv` with Makefile (Recommended)

Our Makefile provides convenient targets for all development tasks:

```bash
# Install dev dependencies (recommended for most development)
make install

# Install ALL dependency groups (current and future: docs, viz, etc.)
make install-all

# Install only production dependencies
make install-prod

# Update all dependencies to latest compatible versions
make update
```

#### Manual Setup with `uv`

If you prefer manual setup, `uv` is a fast Python package installer and resolver:

```bash
# Install all dependency groups (recommended for full development setup)
pip install uv
uv sync --all-extras

# Or install only specific groups
uv sync --extra dev  # Development tools only
```

#### Individual Dependency Groups

You can install specific dependency groups based on your needs:

```bash
# Core dependencies only
uv sync

# Development tools (linting, formatting, testing, etc.)
uv sync --extra dev

# All extras (current: dev; future: docs, viz, etc.)
uv sync --all-extras
```

**Note:** Additional dependency groups like `docs`, `viz`, and others may be added in the future. Use `--all-extras` to ensure you get everything.

#### Alternative Setup Methods

**Coming Soon**: Additional setup options for:

- `asdf` for Python version management
- Virtual environment configuration (`venv`, `conda`, etc.)
- Pre-commit hooks and code formatting
- IDE configuration

## Project Structure

```bash
performa/
├── src/performa/     # Main library code
│   ├── analysis/     # Analysis engine and orchestration
│   ├── asset/        # Asset-specific models (office, residential, etc.)
│   ├── core/         # Core primitives and base classes
│   ├── deal/         # Deal structuring and partnerships
│   ├── debt/         # Debt and financing models
│   ├── development/  # Development project modeling
│   ├── reporting/    # Reporting and visualization
│   └── valuation/    # Valuation methodologies
├── tests/            # Test suite
│   ├── unit/         # Unit tests
│   ├── integration/  # Integration tests
│   └── e2e/          # End-to-end tests
├── examples/         # Usage examples
├── notebooks/        # Interactive Marimo notebooks
└── docs/             # Additional documentation
```

## Logging for (Software) Developers

`performa` uses Python's standard `logging` module to emit informative messages about operations, warnings, and errors. The library gets logger instances but does **not** configure logging handlers by default, leaving that responsibility to the consuming application.

### Basic Logging Setup

```python
import logging
import performa

# Configure logging for your application
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Optional: Set specific level for performa logs
logging.getLogger("performa").setLevel(logging.INFO)

# Optional: More granular control
logging.getLogger("performa.analysis").setLevel(logging.DEBUG)
logging.getLogger("performa.asset").setLevel(logging.INFO)
```

### Advanced Logging Configuration

For production applications, you may want more sophisticated logging:

```python
import logging.config

LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'detailed': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
        },
        'simple': {
            'format': '%(levelname)s - %(message)s'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'INFO',
            'formatter': 'simple',
            'stream': 'ext://sys.stdout'
        },
        'file': {
            'class': 'logging.FileHandler',
            'level': 'DEBUG',
            'formatter': 'detailed',
            'filename': 'performa.log',
        }
    },
    'loggers': {
        'performa': {
            'level': 'DEBUG',
            'handlers': ['console', 'file'],
            'propagate': False
        }
    }
}

logging.config.dictConfig(LOGGING_CONFIG)
```

### Logger Hierarchy

Performa uses a hierarchical logger structure:

- `performa` - Root logger
  - `performa.analysis` - Analysis engine
    - `performa.analysis.orchestrator` - Cash flow orchestration
    - `performa.analysis.scenario` - Analysis scenarios
  - `performa.asset` - Asset models
    - `performa.asset.office` - Office properties
    - `performa.asset.residential` - Residential properties
  - `performa.core` - Core primitives
  - `performa.deal` - Deal structuring
  - `performa.debt` - Debt modeling

## Testing

### Running Tests

Use the Makefile for convenient testing:

```bash
# Run all tests
make test

# Run tests with coverage report
make test-cov

# Manual testing with pytest
uv run pytest
uv run pytest --cov=performa --cov-report=html
```

### Running Tests Manually

```bash
# Run all tests
pytest

# Run specific test categories
pytest tests/unit/
pytest tests/integration/
pytest tests/e2e/

# Run with coverage
pytest --cov=performa --cov-report=html
```

### Writing Tests

Performa uses pytest for testing. Follow these patterns:

```python
import pytest
from performa.core.primitives import Timeline

def test_timeline_creation():
    timeline = Timeline.from_dates('2024-01-01', '2024-12-31')
    assert len(timeline.period_index) == 12

class TestOfficeProperty:
    def test_property_creation(self):
        # Test implementation
        pass
```

## Code Standards

### Linting and Formatting

Use the Makefile for code quality checks:

```bash
# Check code style and formatting
make lint

# Automatically fix code style issues
make lint-fix
```

Manual commands:

```bash
# Check with ruff
uv run ruff check .
uv run ruff format --check .

# Auto-fix with ruff
uv run ruff check --fix .
uv run ruff format .
```

### Python Style Guide

Performa follows these coding standards:

- **PEP 8** for Python style
- **Type hints** for all public APIs
- **Docstrings** for all public classes and methods
- **Pydantic models** for all data structures
- **pytest** for testing

### Documentation Standards

- **Module READMEs**: Each major module has a README.md explaining its purpose
- **Inline documentation**: Comprehensive docstrings with examples
- **Type annotations**: Full type coverage for public APIs
- **Examples**: Working code examples in docstrings and README files

### Import Organization

```python
# Standard library imports
from datetime import date
from typing import Optional, List

# Third-party imports
import pandas as pd
from pydantic import Field

# Performa imports
from performa.core.primitives import Model
from performa.core.base import PropertyBaseModel
```

## Contributing Workflow

### Setting Up for Contribution

1. **Fork the repository** on GitHub
2. **Clone your fork** locally
3. **Create a feature branch** from `main`
4. **Set up development environment**: `make dev-setup`
5. **Verify setup**: `make check`
6. **Make your changes**
7. **Run quality checks**: `make lint test`
8. **Submit a pull request**

### Pull Request Guidelines

- **Clear description** of what the PR accomplishes
- **Reference any issues** being addressed
- **Include tests** for new functionality: `make test`
- **Ensure code quality**: `make lint-fix`
- **Update documentation** as needed
- **Follow the established code style**

### Development Workflow Commands

```bash
# Daily development workflow
make lint-fix    # Fix any style issues
make test        # Run tests
make check       # Verify setup

# Clean up when needed
make clean       # Remove temporary files
make clean-all   # Full cleanup including venv
```

### Release Process

**Coming Soon**: Detailed release procedures including:

- Version bumping strategy
- Changelog maintenance
- PyPI deployment process
- Documentation updates

## Architecture Guidelines

### Design Principles

When contributing to Performa, keep these principles in mind:

1. **Transparency**: All calculations should be auditable and traceable
2. **Composability**: Components should work together seamlessly
3. **Type Safety**: Use Pydantic models and type hints extensively
4. **Performance**: Consider performance implications of design decisions
5. **Standards**: Follow real estate industry standards and terminology

### Pydantic Best Practices

```python
from pydantic import Field, computed_field, model_validator
from typing import Optional

class ExampleModel(Model):
    """Clear, concise description of what this model represents."""
    
    # Required fields first
    name: str = Field(..., description="Human-readable name")
    value: float = Field(..., gt=0, description="Positive value")
    
    # Optional fields with defaults
    description: Optional[str] = Field(None, description="Optional description")
    
    @computed_field
    @property
    def computed_value(self) -> float:
        """Computed properties for derived values."""
        return self.value * 1.1
    
    @model_validator(mode='after')
    def _validate_business_rules(self) -> 'ExampleModel':
        """Custom validation for business logic."""
        if self.value > 1000:
            raise ValueError("Value cannot exceed 1000")
        return self
```

## Getting Help

- **GitHub Issues**: Report bugs and request features
- **GitHub Discussions**: Ask questions and share ideas
- **Documentation**: Start with module README files
- **Examples**: Check the `/examples` directory
- **Community**: Join our community channels (coming soon)

## License and CLA

- **License**: Apache 2.0 (see [LICENSE](LICENSE))
- **Contributing Agreement**: CLA process (coming soon)
- **Code of Conduct**: See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
