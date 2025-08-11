# Performa `office` Asset Modeling

This module provides modeling capabilities for commercial office properties,
from single-tenant buildings to multi-tenant office towers. It implements
commercial real estate features while maintaining usability for
various scenarios.

## Key Components

### Core Models
- **OfficeProperty**: Main property container with rent roll, expenses, and operating assumptions
- **OfficeLease**: Commercial lease model with escalations, recoveries, TI/LC integration
- **OfficeAnalysisScenario**: Analysis orchestration with assembler pattern implementation

### Lease Structure
- **OfficeLeaseSpec**: Lease specification and terms
- **OfficeRentEscalation**: Complex escalation patterns (percentage, fixed, recurring)
- **OfficeRentAbatement**: Free rent and concession modeling
- **OfficeRecoveryMethod**: Expense recovery calculations (net, base year, fixed stop)

### Financial Components
- **OfficeTenantImprovement**: TI allowance with flexible payment timing
- **OfficeLeasingCommission**: Multi-tier commission structures
- **OfficeExpenses**: Operating and capital expense containers
- **OfficeRolloverProfile**: Renewal vs. market rate transitions

### Absorption & Development
- **OfficeAbsorptionPlan**: Vacant space lease-up modeling with required operating assumptions
- **OfficeDevelopmentBlueprint**: Development-to-operations transition
- **OfficeVacantSuite**: Vacant space with subdivision capabilities

## Key Features

- **Multi-escalation lease support** with timing controls
- **Expense recovery** with gross-up calculations
- **TI/LC modeling** with payment timing (signing vs. commencement)
- **Rollover analysis** with state transitions and capital planning
- **Absorption modeling** with subdivision logic for large floorplates
- **Development blueprint integration** for construction-to-operations

## Architecture

The office module follows the commercial base class pattern with office-specific
enhancements for lease structures, recovery methods, and rollover scenarios.
The assembler pattern enables zero-lookup performance during analysis.

## Example Usage

### Development Analysis
```python
from datetime import date
from performa.asset.office import (
    OfficeAbsorptionPlan, OfficeDevelopmentBlueprint, OfficeVacantSuite,
    SpaceFilter, FixedQuantityPace, DirectLeaseTerms
)

# Create absorption plan with standard assumptions
absorption_plan = OfficeAbsorptionPlan.with_typical_assumptions(
    name="Office Lease-Up",
    space_filter=SpaceFilter(use_types=["office"]),
    start_date_anchor=date(2024, 6, 1),
    pace=FixedQuantityPace(
        type="FixedQuantity",
        quantity=25000,
        unit="SF",
        frequency_months=6
    ),
    leasing_assumptions=DirectLeaseTerms(
        base_rent_value=45.0,
        base_rent_frequency="annual",
        term_months=60,
        upon_expiration="market"
    )
)

# Create development blueprint
blueprint = OfficeDevelopmentBlueprint(
    name="Office Development",
    vacant_inventory=[OfficeVacantSuite(...)],
    absorption_plan=absorption_plan
)

# Convert to stabilized property
stabilized_property = blueprint.to_stabilized_asset(timeline)
```

### Asset Analysis
```python
from performa.asset.office import (
    OfficeProperty, OfficeLeaseSpec, OfficeRecoveryMethod
)
from performa.analysis import run

# Create office property
property = OfficeProperty(
    name="Downtown Office Tower",
    net_rentable_area=150000,
    rent_roll=office_rent_roll,
    expenses=office_expenses
)

# Run analysis
scenario = run(property, timeline, settings)
results = scenario.get_cash_flow_summary()
```

The office module supports everything from simple single-tenant net lease
buildings to complex multi-tenant towers with sophisticated lease structures
and recovery methods. 