# Performa `core.base` Classes

This module provides the foundational base classes that enable all real estate
modeling in Performa. These abstract and concrete base classes define the
contracts and common behaviors that asset-specific implementations extend.

## Key Categories

### Property & Program
- **PropertyBaseModel**: Foundation for all property types with core characteristics
- **ProgramComponentSpec**: Mixed-use property component specifications
- **Address**: Standard address modeling

### Lease Modeling
- **LeaseBase**: Abstract base for all lease types with timeline and cash flow contracts
- **LeaseSpecBase**: Base for lease specifications and terms
- **TenantBase**: Tenant information and characteristics

### Lease Components
- **RentEscalationBase**: Flexible rent escalation mechanisms (fixed, percentage, time-based)
- **RentAbatementBase**: Free rent and concession modeling
- **CommissionTier**: Multi-tier leasing commission structures
- **LeasingCommissionBase**: Base leasing commission calculations
- **TenantImprovementAllowanceBase**: TI allowance with flexible payment methods

### Financial Models
- **ExpenseItemBase**: Base for all expense items with growth and occupancy support
- **OpExItemBase**: Operating expenses with recoverable/variable flags
- **CapExItemBase**: Capital expenditures without automatic growth
- **MiscIncomeBase**: Miscellaneous income with variable components

### Recovery & Rollover
- **RecoveryMethodBase**: Expense recovery from tenants
- **RecoveryBase**: Individual recovery calculations
- **ExpensePoolBase**: Grouped expenses for recovery
- **RolloverProfileBase**: Lease rollover and renewal logic
- **RolloverLeaseTermsBase**: Terms for rollover scenarios

### Absorption & Development
- **AbsorptionPlanBase**: Generic base with stabilized operating assumptions
  - Bridges development analysis to deal analysis
  - Type constraints ensure office plans accept office types, residential plans accept residential types
  - Required stabilized assumptions (no default values)
  - Factory methods provide standard assumptions
- **DevelopmentBlueprintBase**: Development-to-operations transitions
- **SpaceFilter**: Filtering criteria for absorption plans
- **PaceStrategy**: Leasing velocity patterns (Fixed, EqualSpread, CustomSchedule)

### Loss Modeling
- **Losses**: Property-level loss configurations
- **VacancyLossConfig**: Vacancy allowance calculations
- **CollectionLossConfig**: Collection loss modeling

## Architecture Principles

### Core Design
- **Abstract base classes** define contracts without implementation details
- **Concrete base classes** provide reusable functionality
- **Pydantic validation** ensures data integrity
- **Timeline integration** for period-aware calculations
- **Flexible unit-of-measure** support across all models

### Generic Absorption Plans
The absorption plan architecture uses generic types and required fields.

#### Type Constraints
- Generic constraints ensure office plans accept `OfficeExpenses`, not `ResidentialExpenses`
- Residential plans accept `ResidentialExpenses`, not `OfficeExpenses`
- Type checking occurs at validation time

#### Required Fields
- All stabilized operating assumptions are required with no default values
- Forces explicit specification of financial assumptions

#### Factory Methods
```python
# With standard assumptions
plan = OfficeAbsorptionPlan.with_typical_assumptions(...)

# With custom assumptions (all fields required)
plan = OfficeAbsorptionPlan(
    stabilized_expenses=custom_expenses,
    stabilized_losses=custom_losses,
    stabilized_misc_income=custom_income,
    ...
)
```

#### Development to Deal Analysis
- Absorption plans bridge development analysis to deal analysis
- Plans define leasing strategy and stabilized operating characteristics
- Blueprints extract stabilized assumptions for property creation

## Example Usage

```python
from performa.core.base import LeaseBase, PropertyBaseModel

class CustomLease(LeaseBase):
    def compute_cf(self, context):
        # Implement lease-specific logic
        return {"base_rent": rent_series}

class CustomProperty(PropertyBaseModel):
    # Add property-specific fields
    pass
```

These base classes enable consistent behavior and contracts across all
asset types while providing flexibility for property-specific requirements.
