# Performa Residential Asset Models - Multifamily Property Analysis

This module provides modeling capabilities for multifamily residential
properties, implementing the "unit-centric" paradigm where properties are modeled
by unit mix rather than individual leases. Supports value-add scenarios, renovations,
and absorption modeling for developments.

## Key Components

### Core Models
- **ResidentialProperty**: Main property container with unit mix and operating assumptions
- **ResidentialRentRoll**: Unit mix container organizing occupied and vacant units
- **ResidentialLease**: Runtime lease model for individual units with residential terms
- **ResidentialAnalysisScenario**: Analysis orchestration with unit-centric cash flow logic

### Unit Structure
- **ResidentialUnitSpec**: Specification for groups of identical units (e.g., "50 1BR units")
- **ResidentialVacantUnit**: Specification for groups of vacant units ready for lease-up
- Unit-based modeling vs. individual lease tracking for efficiency

### Financial Components
- **ResidentialExpenses**: Operating and capital expense containers for multifamily
- **ResidentialLosses**: Vacancy and collection loss modeling for residential
- **ResidentialMiscIncome**: Additional income streams (parking, storage, amenities)

### Rollover & Absorption
- **ResidentialRolloverProfile**: Lease renewal and market rate transitions
- **ResidentialRolloverLeaseTerms**: Terms for lease renewal scenarios
- **ResidentialAbsorptionPlan**: Unit-based absorption with required operating assumptions

### Development Integration
- **ResidentialDevelopmentBlueprint**: Development-to-operations transition
- Capital planning integration for renovations
- Construction-to-lease-up modeling with stabilized operating assumptions

## Architecture

The residential module follows the unit-centric paradigm with key principles:

1. **Unit Mix Organization**: Properties modeled by unit types, not individual leases
2. **Explicit Vacancy Pattern**: Occupancy emerges from occupied vs vacant unit composition
3. **Efficiency Focus**: Avoids individual lease tracking for hundreds of units
4. **Value-Add Integration**: Capital planning for unit renovations and improvements

## Design Principles

- Unit-centric modeling appropriate for multifamily scale
- Simplified lease structures suitable for residential properties
- Integration with capital planning for value-add scenarios
- Efficient modeling for properties with hundreds of units
- Industry-standard residential terminology and practices

## Key Features

- Unit mix modeling with flexible unit type definitions
- Value-add renovation scenarios with capital planning integration
- Residential-specific rollover and absorption modeling
- Simplified lease structures appropriate for multifamily
- Development blueprint integration for construction-to-operations
- Efficient analysis for large unit counts

## Example Usage

### Development Analysis

```python
from datetime import date
from performa.asset.residential import (
    ResidentialAbsorptionPlan, ResidentialDevelopmentBlueprint, ResidentialVacantUnit,
    ResidentialUnitFilter, FixedQuantityPace, ResidentialDirectLeaseTerms
)

# Create absorption plan with standard assumptions
absorption_plan = ResidentialAbsorptionPlan.with_typical_assumptions(
    name="Apartment Lease-Up",
    space_filter=ResidentialUnitFilter(unit_types=["1BR", "2BR"]),
    pace=FixedQuantityPace(
        type="FixedQuantity",
        quantity=20,
        unit="Units",
        frequency_months=1
    ),
    leasing_assumptions=ResidentialDirectLeaseTerms(
        monthly_rent=2800.0,
        lease_term_months=12,
        security_deposit_months=1.0
    ),
    start_date_anchor=date(2024, 6, 1)
)

# Create development blueprint
blueprint = ResidentialDevelopmentBlueprint(
    name="Apartment Development", 
    vacant_inventory=[ResidentialVacantUnit(...)],
    absorption_plan=absorption_plan
)

# Convert to stabilized property
stabilized_property = blueprint.to_stabilized_asset(timeline)
```

### Asset Analysis

```python
from performa.asset.residential import (
    ResidentialProperty, ResidentialUnitSpec, ResidentialVacantUnit,
    ResidentialRentRoll
)
from performa.analysis import run
from performa.core.capital import CapitalPlan, CapitalItem

# Create unit specifications
unit_1br = ResidentialUnitSpec(
    unit_type="1BR",
    unit_count=50,
    unit_area=750,
    market_rent=2_500
)

vacant_2br = ResidentialVacantUnit(
    unit_type="2BR", 
    unit_count=10,
    unit_area=1_100,
    market_rent=3_200
)

# Create property with unit mix
property = ResidentialProperty(
    name="Maple Ridge Apartments",
    total_units=150,
    rent_roll=ResidentialRentRoll(
        occupied_units=[unit_1br],
        vacant_units=[vacant_2br]
    ),
    renovation_plan=capital_plan
)

# Run analysis
scenario = run(property, timeline, settings)
results = scenario.get_cash_flow_summary()
```

### Value-Add Scenarios

```python
from performa.core.capital import CapitalPlan

# Value-add renovation program
renovation_plan = CapitalPlan.create_residential_value_add(
    target_units=75,
    cost_per_unit=15_000,
    rent_increase_per_unit=300,
    renovation_timeline=timeline.slice('2024-01-01', '2025-12-31')
)

property.renovation_plan = renovation_plan
```

The residential module enables sophisticated multifamily analysis while maintaining
efficiency for properties with large unit counts, supporting everything from
simple buy-and-hold scenarios to complex value-add development projects. 