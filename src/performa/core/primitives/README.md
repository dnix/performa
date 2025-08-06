# Performa `core.primitives`

This module provides the essential building blocks for all real estate financial
modeling in Performa. These primitives handle timeline management, cash flow
calculations, settings, validation, and fundamental data types.

## Key Components

### Timeline & Temporal
- **Timeline**: Flexible timeline management supporting absolute and relative periods
- **Period-based calculations** with proper alignment and resampling

### Cash Flow Engine
- **CashFlowModel**: Universal cash flow calculation with growth, dependencies, and units
- **Automatic frequency conversion** and timeline alignment
- **Support for scalar, series, and dictionary-based** values
- **Dependency resolution** for complex financial calculations

### Settings & Configuration
- **GlobalSettings**: Comprehensive analysis configuration
- **CalculationSettings**: Engine behavior and dependency validation
- **ReportingSettings**: Output formatting and fiscal year handling
- **InflationSettings**: Growth rate timing and methodology
- **RecoverySettings**: Expense recovery calculation parameters
- **ValuationSettings**: DCF and exit value methodologies

### Enumerations
- **Comprehensive enums** for all real estate modeling concepts
- **Asset types, lease terms, unit measures, frequencies**
- **Calculation passes, line items, and status enumerations**
- **Consistent vocabulary** across the entire framework

### Growth & Rates
- **PercentageGrowthRate**: Flexible percentage-based growth rate modeling
- **Support for time-varying rates** via Series and dictionaries
- **Inflation-aware calculations** with proper timing

### Validation Framework
- **ValidationMixin**: Reusable validation patterns
- **Term specification validation** for leases
- **Mutual exclusivity and conditional requirement validators**
- **Type-safe validation** with clear error messages

### Data Types
- **PositiveFloat, PositiveInt**: Type-safe numeric constraints
- **FloatBetween0And1**: Percentage and ratio validation
- **Model**: Enhanced Pydantic BaseModel with consistent configuration

## Architecture

The primitives module provides the foundation that enables:
- **Consistent behavior** across all asset types
- **Type-safe modeling** with comprehensive validation
- **Flexible timeline and cash flow management**
- **Standardized configuration and settings**
- **Industry-standard terminology and enumerations**

## Example Usage

```python
from performa.core.primitives import (
    Timeline, CashFlowModel, GlobalSettings, PercentageGrowthRate
)

# Create timeline
timeline = Timeline.from_dates('2024-01-01', '2029-12-31')

# Configure analysis
settings = GlobalSettings(
    analysis_start_date=date(2024, 1, 1),
    calculation=CalculationSettings(max_dependency_depth=3)
)

# Model with growth
class CustomModel(CashFlowModel):
    def compute_cf(self, context):
        # Automatic growth application
        return super().compute_cf(context)
```

These primitives enable sophisticated financial modeling while maintaining
simplicity for straightforward analyses. 