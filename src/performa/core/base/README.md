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
- **AbsorptionPlanBase**: Vacant space lease-up modeling
- **DevelopmentBlueprintBase**: Development-to-operations transitions
- **SpaceFilter**: Filtering criteria for absorption plans
- **PaceStrategy**: Leasing velocity patterns

### Loss Modeling
- **LossesBase**: Property-level loss configurations
- **GeneralVacancyLossConfigBase**: Vacancy allowance calculations
- **CollectionLossConfigBase**: Collection loss modeling

## Architecture Principles

- **Abstract base classes** define contracts without implementation details
- **Concrete base classes** provide reusable functionality
- **Pydantic validation** ensures data integrity
- **Timeline integration** for period-aware calculations
- **Flexible unit-of-measure** support across all models

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