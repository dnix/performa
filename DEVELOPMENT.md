# Development Guide

This guide covers everything you need to know for developing with and contributing to Performa.

## Installation for Development

### From Source (Recommended for Development)

```bash
git clone https://github.com/performa-dev/performa.git
cd performa
pip install -e .
```

This installs Performa in editable mode, allowing you to make changes to the source code and immediately see the effects without needing to reinstall.

### Development Environment Setup

#### Using `uv` (Recommended)

`uv` is a fast Python package installer and resolver. To install all development dependencies:

```bash
# Install all dependency groups (recommended for full development setup)
pip install uv
uv pip install -r pyproject.toml --all-extras
```

#### Individual Dependency Groups

You can also install specific dependency groups based on your needs:

```bash
# Core dependencies only
uv pip install -e .

# Development tools (linting, formatting, testing, etc.)
uv pip install -e .[dev]

# Documentation dependencies
uv pip install -e .[docs]
```

#### Alternative Setup Methods

**Coming Soon**: Additional setup options for:
- `asdf` for Python version management
- Virtual environment configuration (`venv`, `conda`, etc.)
- Pre-commit hooks and code formatting
- IDE configuration

## Project Structure

```
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
4. **Install in development mode**: `pip install -e .`
5. **Make your changes**
6. **Run tests** to ensure nothing breaks
7. **Submit a pull request**

### Pull Request Guidelines

- **Clear description** of what the PR accomplishes
- **Reference any issues** being addressed
- **Include tests** for new functionality
- **Update documentation** as needed
- **Follow the established code style**

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
    def validate_business_rules(self) -> 'ExampleModel':
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