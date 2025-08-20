# Performa `analysis` Engine

This module provides the core analysis engine for Performa, implementing the orchestrator
pattern for cash flow calculations and the scenario pattern for property analysis.

## Key Components

- **AnalysisScenarioBase**: Base class for asset-specific analysis scenarios
- **CashFlowOrchestrator**: Executes multi-phase cash flow calculations with dependency resolution
- **AnalysisContext**: Universal data bus for analysis state and resolved object references
- **Registry**: Maps model types to their appropriate analysis scenarios

## Architecture

The analysis engine uses a sophisticated orchestrator pattern with assembler logic:

1. **Scenarios prepare models** and resolve UUID references to direct object references
2. **AnalysisContext serves** as universal data bus with pre-built lookup maps
3. **Orchestrator executes** calculations in dependency-aware phases
4. **Results are aggregated** into industry-standard financial statements

## Example Usage

```python
from performa.analysis import run
from performa.asset.office import OfficeProperty
from performa.core.primitives import Timeline, GlobalSettings

# Run analysis for any property type
scenario = run(
    model=office_property,
    timeline=Timeline.from_dates('2024-01-01', '2033-12-31'),
    settings=GlobalSettings()
)

# Get results
summary = scenario.summary_df
```

The analysis engine automatically selects the appropriate scenario based on model type
and handles all the complexity of cash flow orchestration and dependency resolution. 