# Performa Core Capital Planning - Capital Expenditure & Renovation Modeling

This module provides sophisticated capital expenditure modeling with factory methods
for common renovation patterns. Built on the CashFlowModel foundation for seamless
integration with existing analysis workflows and timeline management.

## Key Components

### Core Models
- **CapitalPlan**: Coordinated capital project container with factory methods for common scenarios
- **CapitalItem**: Individual capital expenditure with flexible timing and cost distribution
- Integration with DrawSchedule for sophisticated cost distribution patterns

### Capital Planning Features
- Factory methods for common renovation scenarios (value-add, modernization, etc.)
- Flexible timing with start dates, duration, and completion triggers
- Multiple draw schedule patterns (uniform, S-curve, front-loaded, back-loaded)
- Integration with property timelines and development phases

## Architecture

The capital module follows the composable design pattern:

1. **CapitalPlan** serves as the coordinating container
2. **Individual CapitalItem** objects define specific expenditures
3. **DrawSchedule patterns** control cost distribution over time
4. **CashFlowModel integration** enables timeline-aware calculations

## Design Principles

- Composable design with clear separation of concerns
- Timeline-aware calculations with proper period alignment
- Flexible unit-of-measure support (total cost, per-unit, per-SF)
- Integration with absorption and rollover scenarios
- Factory methods for common real estate scenarios

## Key Features

- Value-add renovation scenario modeling
- Capital improvement planning with phased execution
- Integration with lease rollover and absorption plans
- Sophisticated draw schedule patterns for realistic cash flow timing
- Support for both development and stabilized property scenarios

## Example Usage

### Basic Capital Planning

```python
from performa.core.capital import CapitalPlan, CapitalItem
from performa.core.primitives import Timeline

# Create timeline
timeline = Timeline.from_dates('2024-01-01', '2029-12-31')

# Individual capital item
roof_replacement = CapitalItem(
    name="Roof Replacement",
    total_cost=500_000,
    start_date=date(2025, 6, 1),
    duration_months=3,
    draw_schedule="uniform"
)

# Capital plan with multiple items
modernization_plan = CapitalPlan(
    name="Property Modernization",
    capital_items=[
        roof_replacement,
        elevator_upgrade,
        lobby_renovation
    ]
)

# Factory method for value-add scenario
value_add_plan = CapitalPlan.create_residential_value_add(
    target_units=75,
    cost_per_unit=15_000,
    renovation_duration_months=18,
    start_date=date(2024, 3, 1)
)
```

### Integration with Development

```python
from performa.development import DevelopmentProject

# Development with capital improvements
project = DevelopmentProject(
    property_name="Mixed-Use Development",
    development_program=program,
    construction_plan=construction_plan,
    capital_improvements=modernization_plan
)
```

### Draw Schedule Integration

```python
from performa.core.primitives import SCurveDrawSchedule

capital_item = CapitalItem(
    name="Major Renovation",
    total_cost=2_000_000,
    draw_schedule=SCurveDrawSchedule(
        duration_months=12,
        early_phase_percentage=0.2,
        peak_phase_percentage=0.6,
        completion_phase_percentage=0.2
    )
)
```

## Factory Methods

The module provides factory methods for common scenarios:
- **create_residential_value_add()**: Multifamily renovation programs
- **create_office_modernization()**: Office building improvements
- **create_retail_tenant_improvements()**: Retail space improvements
- **create_mixed_use_capital_plan()**: Complex mixed-use scenarios

This capital planning system enables sophisticated renovation and improvement
modeling while maintaining simplicity for straightforward capital expenditures,
supporting everything from single-item replacements to complex value-add programs. 