# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is the **Performa** project - an open-source real estate financial modeling framework that provides transparent, auditable alternatives to spreadsheets and black-box software. The project includes:

- **Python Library**: Located in `src/performa/` - composable building blocks for real estate analysis
- **Three-Tier Architecture**: Primitives, Constructs, and Patterns for different abstraction levels
- **Interactive Notebooks**: Marimo-based browser interfaces in `examples/marimo/`
- **Comprehensive Testing**: Unit, integration, and end-to-end test coverage

## Architecture

### Core Components

1. **Primitives** (`src/performa/core/`): Timeline, CashFlow, Model, Ledger - foundational building blocks
2. **Asset Models** (`src/performa/asset/`): Property-specific modeling for office, residential, retail, etc.
3. **Analysis Engine** (`src/performa/analysis/`): Orchestrator with dependency resolution and cash flow coordination
4. **Deal Structuring** (`src/performa/deal/`): Partnership waterfalls, acquisition terms, fee structures
5. **Debt Modeling** (`src/performa/debt/`): Construction/permanent financing with amortization schedules

### Key Directories

- `src/performa/`: Main library code organized by domain
- `tests/`: Test suite with unit/, integration/, e2e/ structure
- `examples/`: Usage examples including marimo notebooks
- `patterns/`: High-level deal workflow implementations
- `validation_scripts/`: External validation (separate from tests)

## Development Commands

### Setup

```bash
make dev-setup    # Complete environment setup (asdf, Python, uv, dependencies)
make check        # Verify installation is working
```

### Core Development

```bash
make test         # Run all tests (pytest, no parameters)
make test-cov     # Run tests with coverage report
make lint         # Check code style with ruff
make lint-fix     # Auto-fix code style issues
make clean        # Remove temporary files
```

### Testing Commands

```bash
# Run specific tests
uv run pytest tests/unit/core/test_timeline.py::test_function_name -v
uv run pytest tests/integration/deal/ -v
uv run pytest tests/e2e/ -v

# Debug tests
uv run pytest tests/unit/core/ -v -s
```

## Important Notes

### Current Analysis Architecture

**Ledger-Based Analysis**: The analysis engine automatically builds a transactional ledger during execution:

```python
from performa.analysis import run
from performa.core.primitives import Timeline, GlobalSettings

# Analysis creates and populates ledger automatically
results = run(property, timeline, GlobalSettings())
# Access financial metrics through ledger queries
ledger_queries = results.get_ledger_queries()
noi = ledger_queries.noi()  # Computed on-demand from ledger
egi = ledger_queries.egi()  # Single source of truth
ledger_df = results.get_ledger_df  # Full transaction history dataframe
```

### Critical Debugging & Model Validation Framework

**FUNDAMENTAL FOR LLM DEVELOPMENT**: Always use debug utilities for model iteration:

```python
from performa.reporting import (
    generate_assumptions_report,
    dump_performa_object, 
    analyze_ledger_semantically
)

# 1. ASSUMPTIONS DOCUMENTATION - Essential for model validation
assumptions_doc = generate_assumptions_report(
    deal_or_pattern,
    include_risk_assessment=True,  # Flag dangerous defaults
    include_defaults_detail=True   # Full parameter visibility
)
print(assumptions_doc)  # Suitable for due diligence

# 2. CONFIGURATION INTROSPECTION - Essential for debugging
config = dump_performa_object(deal, exclude_defaults=True)
print(f"Class: {config['_object_info']['class_name']}")
print(f"User-specified params: {len(config['config'])}")

# 3. LEDGER VALIDATION - Single source of truth for all cash flows
ledger_analysis = analyze_ledger_semantically(results.ledger)
print(f"Total records: {ledger_analysis['record_count']}")
print(f"Net flow: ${ledger_analysis['balance_checks']['total_net_flow']:,.0f}")

# 4. FLUENT REPORTING - Report generation
assumptions_summary = results.reporting.assumptions_summary()
pro_forma = results.reporting.pro_forma_summary(frequency='A')
```

**LLM Development Workflow**:
1. **Create model** → Always validate with `generate_assumptions_report()`
2. **Check parameters** → Use `dump_performa_object()` for configuration visibility  
3. **Validate math** → Use `analyze_ledger_semantically()` for cash flow sanity checks
4. **Generate reports** → Use `results.reporting.*` for documentation

### Debt Facility Integration

Process debt facilities through their `compute_cf` method like other CashFlowModels:

```python
for facility in deal.financing.facilities:
    facility.compute_cf(analysis_context)  # Standard CashFlowModel pattern
```

### Testing Requirements

- Use **pytest** framework (not unittest)
- Run tests with `make test` only (no parameters)
- **Never** use `model_construct()` in tests
- Fix or delete problematic tests (never skip)
- Inline all validation logic directly in test files (no external imports)

### Marimo Notebook Development

```python
@app.cell
def __():
    import marimo as mo
    import performa
    return mo, performa

@app.cell
def __(mo):
    slider = mo.ui.slider(0, 100, 1)
    slider  # Always create UI, conditionally display

@app.cell
def __(slider, mo):
    value = slider.value  # Reference with .value
    mo.md(f"Value: {value}")
```

**Key Requirements**:

- Convert PeriodIndex to DatetimeIndex with `.to_timestamp()` for pyobsplot
- Import dependencies in first cell and return them
- Return display objects naked (no tuple wrapping)

### Code Quality Standards

- **Return Types**: Use `LeveredCashFlowResult` model for function outputs
- **Realistic Names**: No placeholder classes (use actual real estate terms)
- **Explicit Values**: Derive parameters from objects, avoid magic numbers
- **Import Organization**: Standard library → third-party → performa imports
- **Type Safety**: Comprehensive type hints for all public APIs
- **Model Validation**: Always use debug utilities for analysis and validation

### Technical Preferences

- **Documentation**: Update README files when changing public APIs
- **Dependencies**: Use 'chore' prefix for dependency update commits
- **Architecture**: Unified solutions over patchwork fixes

## Key Configuration Files

- **`pyproject.toml`**: Main project config with ruff, pytest settings
- **`Makefile`**: Development automation (preferred over direct uv/pytest)
- **`PROJECT.md`**: Feature roadmap (reference for all implementations)
- **Module READMEs**: Component-specific documentation

## Development Workflow

1. **Plan with todos**: Track complex multi-step tasks
2. **Ask permission**: Share thought process before making changes  
3. **Fix incrementally**: One issue at a time, not batch fixes
4. **Validate with debug utilities**: Use assumptions reports and ledger analysis
5. **Test thoroughly**: Comprehensive coverage required
6. **Clean up**: Remove any temporary files created during development

### Essential Model Validation Pattern

**CRITICAL**: Always validate model assumptions and ledger math when developing:

```python
# Step 1: Document assumptions for analysis
from performa.reporting import generate_assumptions_report
assumptions_doc = generate_assumptions_report(deal, include_risk_assessment=True)

# Step 2: Validate configuration quality (context-aware scoring)
from performa.reporting import analyze_configuration_intentionality
analysis = analyze_configuration_intentionality(deal)
quality_score = analysis['intentionality_metrics']['quality_score']  # Context-aware scoring
is_pattern = analysis['intentionality_metrics']['is_pattern_based']

# Step 3: Validate ledger math (single source of truth)  
from performa.reporting import analyze_ledger_semantically
ledger_analysis = analyze_ledger_semantically(results.ledger)
net_flow = ledger_analysis['balance_checks']['total_net_flow']

# Step 4: Deal comparison and parity validation
from performa.reporting import (
    compare_deal_timelines, compare_deal_configurations, 
    validate_deal_parity, compare_ledger_shapes
)

# For deal comparison (e.g., composition vs pattern)
if comparing_multiple_deals:
    # Check timeline alignment first (common issue)
    timeline_diff = compare_deal_timelines(deal1, deal2)
    if timeline_diff['has_mismatches']:
        print(f"🎯 Timeline issues: {timeline_diff['summary']}")
    
    # Check configuration differences (ALL differences shown - no filtering)
    config_diff = compare_deal_configurations(deal1, deal2)
    if config_diff['has_differences']:
        print(f"❌ Config differences: {config_diff['impact_assessment']}")
    
    # Validate results parity after analysis
    parity = validate_deal_parity(results1, results2, 
                                tolerance={'irr': 0.01, 'em': 0.05, 'equity': 10000})
    if not parity['passes']:
        print(f"Parity issues: {parity['summary']}")

# Step 5: Flow validation and reasonableness checks
from performa.reporting import validate_flow_reasonableness, analyze_ledger_shape
flow_check = validate_flow_reasonableness(results, deal_type="stabilized")
ledger_shape = analyze_ledger_shape(results)

# Step 6: Generate analysis reports
pro_forma = results.reporting.pro_forma_summary()
assumptions_summary = results.reporting.assumptions_summary()
```
