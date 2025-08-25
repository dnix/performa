# Performa `core.primitives`

This module provides the essential building blocks for all real estate financial modeling in Performa. These primitives handle timeline management, cash flow calculations, settings, validation, and fundamental data types.

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
- **GlobalSettings**: Analysis configuration
- **CalculationSettings**: Engine behavior and dependency validation
- **ReportingSettings**: Output formatting and fiscal year handling
- **InflationSettings**: Growth rate timing and methodology
- **RecoverySettings**: Expense recovery calculation parameters
- **ValuationSettings**: DCF and exit value methodologies

### Enumerations
- **Enums** for all real estate modeling concepts
- **Asset types, lease terms, unit measures, frequencies**
- **Calculation passes, line items, and status enumerations**
- **Construction financing methods** with InterestCalculationMethod
- **Lease expiration behaviors** with UponExpirationEnum
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

### Utilities
- **enum_to_string**: Pandas-compatible enum value conversion
- **Enum compatibility** functions for DataFrame operations

## Architecture

The primitives module provides the foundation that enables:
- **Consistent behavior** across all asset types
- **Type-safe modeling** with validation
- **Flexible timeline and cash flow management**
- **Standardized configuration and settings**
- **Industry-standard terminology and enumerations**
- **Pandas integration** with enum utilities

## Enumerations

### `InterestCalculationMethod`

Provides a complexity dial for construction interest calculations, enabling projects to match their complexity needs:

```python
from performa.core.primitives import InterestCalculationMethod

# Simple draws without interest calculations
InterestCalculationMethod.NONE

# Quick percentage-based reserve estimate (industry: 8-12%)
InterestCalculationMethod.SIMPLE

# Draw-based calculation using actual schedules (industry standard)
InterestCalculationMethod.SCHEDULED

# Full multi-pass iteration for maximum precision (future enhancement)
InterestCalculationMethod.ITERATIVE
```

**Usage in Construction Financing**:
```python
from performa.debt import ConstructionFacility
from performa.core.primitives import InterestCalculationMethod

construction_loan = ConstructionFacility(
    name="Development Construction Loan",
    loan_amount=15_000_000,
    interest_rate=0.065,
    interest_calculation_method=InterestCalculationMethod.SCHEDULED
)
```

### `UponExpirationEnum`

Defines behavior when a lease expires, controlling how space is treated in rollover scenarios:

```python
from performa.core.primitives import UponExpirationEnum

# Weighted average approach based on market conditions
UponExpirationEnum.MARKET

# Assumes 100% renewal probability with predetermined terms
UponExpirationEnum.RENEW

# Assumes 0% renewal probability, space available for new tenant
UponExpirationEnum.VACATE

# Models a contractual renewal option as a distinct lease
UponExpirationEnum.OPTION

# Triggers unit transformation workflow for renovation
UponExpirationEnum.REABSORB
```

**Usage in Lease Modeling**:
```python
from performa.asset.residential import ResidentialRolloverProfile
from performa.core.primitives import UponExpirationEnum

rollover_profile = ResidentialRolloverProfile(
    name="Value-Add Rollover Strategy",
    upon_expiration=UponExpirationEnum.REABSORB,  # Trigger renovation workflow
    target_absorption_plan_id=renovation_plan.uid  # Link to absorption plan
)
```

## Utility Functions

### `enum_to_string`

Converts enum values to their string representation for pandas compatibility:

```python
from performa.core.primitives.enums import enum_to_string, CashFlowCategoryEnum

# Convert enum to string for DataFrame storage
category_str = enum_to_string(CashFlowCategoryEnum.REVENUE)
# Returns: "Revenue"

# Works with any enum
method_str = enum_to_string(InterestCalculationMethod.SCHEDULED)
# Returns: "scheduled"

# Safe for non-enums
already_string = enum_to_string("already_string")
# Returns: "already_string"
```

**Usage in Ledger System**:
```python
# Used internally by Ledger for DataFrame compatibility
def _records_to_dataframe(self, records):
    for record in records:
        row_data = {
            'flow_purpose': enum_to_string(record.flow_purpose),
            'category': enum_to_string(record.category),
            'subcategory': enum_to_string(record.subcategory),
            # ... other fields
        }
```

**Benefits**:
- **Pandas Compatibility**: Ensures enums work properly in DataFrames
- **Query Consistency**: String-based filtering works reliably
- **Type Safety**: Preserves semantic meaning while enabling operations
- **Performance**: Avoids categorical data type complexity

## Example Usage

### Basic Timeline and Settings

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

### Enum Usage in Financial Models

```python
from performa.core.primitives import (
    CashFlowCategoryEnum, 
    InterestCalculationMethod,
    UponExpirationEnum
)

# Construction financing with specific interest method
construction_settings = {
    'interest_method': InterestCalculationMethod.SCHEDULED,
    'draw_frequency': FrequencyEnum.MONTHLY
}

# Lease expiration handling
lease_terms = {
    'expiration_behavior': UponExpirationEnum.REABSORB,
    'renewal_probability': 0.75
}

# Transaction categorization
transaction_metadata = {
    'category': CashFlowCategoryEnum.CAPITAL,
    'subcategory': CapitalSubcategoryEnum.HARD_COSTS
}
```

### Enum Integration with DataFrames

```python
from performa.core.primitives.enums import enum_to_string
import pandas as pd

# Create DataFrame with enum data
transactions = pd.DataFrame({
    'date': pd.date_range('2024-01-01', periods=3, freq='M'),
    'category': [
        enum_to_string(CashFlowCategoryEnum.REVENUE),
        enum_to_string(CashFlowCategoryEnum.EXPENSE),
        enum_to_string(CashFlowCategoryEnum.CAPITAL)
    ],
    'amount': [50_000, -20_000, -100_000]
})

# Query with string-based filtering (works reliably)
revenue_transactions = transactions[
    transactions['category'] == enum_to_string(CashFlowCategoryEnum.REVENUE)
]

# Groupby operations work seamlessly
category_totals = transactions.groupby('category')['amount'].sum()
```

### Settings and Configuration

```python
from performa.core.primitives import (
    GlobalSettings, 
    CalculationSettings,
    ReportingSettings,
    ValuationSettings
)

# Analysis configuration
settings = GlobalSettings(
    analysis_start_date=date(2024, 1, 1),
    calculation=CalculationSettings(
        max_dependency_depth=5,
        enable_validation=True
    ),
    reporting=ReportingSettings(
        fiscal_year_start_month=1,
        currency_symbol="$"
    ),
    valuation=ValuationSettings(
        default_discount_rate=0.10,
        terminal_growth_rate=0.025
    )
)
```

## Integration Benefits

The primitives module enables:

### Type Safety
- All enums are strongly typed with Pydantic validation
- Consistent vocabulary prevents modeling errors
- IDE autocompletion and type checking support

### Pandas Compatibility
- `enum_to_string` utility ensures DataFrame operations work reliably
- No categorical data type complications
- Consistent string-based queries and filters

### Industry Standards
- Enumerations reflect real estate industry terminology
- Construction financing methods align with institutional practices
- Lease modeling behaviors match market conventions

### Extensibility
- Easy to add new enum values for expanding capabilities
- Utility functions support custom enum types
- Consistent patterns for new primitive additions

These primitives enable financial modeling while maintaining simplicity for straightforward analyses and ensuring seamless integration with pandas-based data operations throughout the Performa ecosystem.