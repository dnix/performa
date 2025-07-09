# Performa `core` Framework

This module provides the foundational building blocks for all real estate financial modeling
in Performa. It contains the essential primitives, base classes, and capital planning tools
that enable sophisticated property analysis and development modeling.

## Key Components

### Base Classes (`performa.core.base`)
- **PropertyBaseModel**: Foundation for all property types
- **LeaseBase & LeaseSpecBase**: Lease modeling infrastructure 
- **CashFlowModel**: Universal cash flow calculation engine
- **Recovery, expense, and revenue base classes**
- **Absorption and rollover modeling foundations**

### Primitives (`performa.core.primitives`)
- **Timeline**: Flexible timeline management for any analysis period
- **CashFlowModel**: Base for all cash flow calculations with growth and dependencies
- **GlobalSettings**: Configuration for analysis behavior and industry standards
- **Enums**: Comprehensive enumerations for real estate modeling
- **Validation**: Reusable validation patterns

### Capital Planning (`performa.core.capital`)
- **CapitalPlan**: Coordinated capital project container with factory methods
- **CapitalItem**: Individual capital expenditure with flexible timing
- **DrawSchedule**: Sophisticated cost distribution patterns (uniform, S-curve, etc.)

## Architecture Principles

- **Composable design** with clear separation of concerns
- **Pydantic-based validation** and type safety
- **Flexible unit-of-measure** support (currency, per-unit, percentage)
- **Timeline-aware calculations** with proper period alignment
- **Dependency resolution** for complex financial calculations

## Example Usage

```python
from performa.core.primitives import Timeline, CashFlowModel, GlobalSettings
from performa.core.capital import CapitalPlan
from performa.core.base import PropertyBaseModel

# Create timeline
timeline = Timeline.from_dates('2024-01-01', '2029-12-31')

# Use base classes for custom models
class CustomExpense(CashFlowModel):
    def compute_cf(self, context):
        return self._cast_to_flow(self.value)
```

This core framework enables all higher-level asset modeling while maintaining
consistency and reliability across the entire Performa ecosystem. 