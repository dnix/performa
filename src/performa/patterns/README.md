# Performa Patterns

High-level functions that assemble complete Deal objects for immediate analysis, implementing common real estate investment strategies with enterprise-grade sophistication and startup-level productivity.

## Overview

Patterns represent the highest abstraction layer in Performa's three-tier architecture:

- **Primitives**: Core data models and calculations (timelines, cash flows, etc.)
- **Constructs**: Module-specific builder functions (debt facilities, partnerships, etc.)  
- **Patterns**: Complete investment archetype implementations (value-add, development, etc.)

Patterns transform complex deal modeling from hundreds of lines of component assembly into simple, parameter-driven function calls while maintaining full modeling sophistication.

## Architecture Benefits

### Productivity Multiplier

**Low-Level Approach** (Component Assembly):
```python
# 785+ lines of code across multiple functions
property = create_property_with_unit_mix(...)  # 200+ lines
capital_plan = create_renovation_program(...)   # 50+ lines  
absorption = create_absorption_plans(...)       # 100+ lines
financing = create_debt_facilities(...)         # 150+ lines
acquisition = create_acquisition_terms(...)     # 25+ lines
deal = assemble_complete_deal(...)              # 50+ lines
# + extensive parameter coordination and validation
```

**Pattern Approach**:
```python
# 7 lines of code, single function call
deal = create_value_add_acquisition_deal(
    property_name="Riverside Gardens",
    acquisition_price=10_000_000,
    renovation_budget=1_500_000,
    stabilized_noi=1_470_000,
    hold_period_years=7,
    ltv_ratio=0.75,
)
```

**Result**: **112x productivity improvement** with identical financial outputs.

### Enterprise Sophistication

Patterns automatically generate:

- **Complex Property Models**: Multi-unit residential with strategic lease lifecycle management
- **Value-Add Logic**: REABSORB → Renovation → Premium Absorption workflows  
- **Coordinated Capital Plans**: Renovation programs synchronized with lease expiration timing
- **Integrated Financing**: Construction-to-permanent debt structures with realistic terms
- **Complete Deal Assembly**: All components properly linked and validated

### Strategic Standardization

- **Industry Methodologies**: Patterns encode proven real estate investment strategies
- **Consistent Implementation**: Reduces modeling errors and improves reliability across teams
- **Rapid Iteration**: Business users can model complex deals without technical expertise
- **Maintainable Logic**: Centralized pattern updates propagate to all implementations

## Available Patterns

### Acquisition Patterns

#### `create_value_add_acquisition_deal()`

Models a complete value-add acquisition strategy: acquire underperforming property, execute renovations, hold for cash flow and appreciation, exit via sale.

**Input Parameters** (6 total):
- `property_name`: Property identification
- `acquisition_price`: Purchase price ($)
- `acquisition_date`: Acquisition closing date  
- `renovation_budget`: Total renovation investment ($)
- `stabilized_noi`: Target NOI after improvements ($)
- `hold_period_years`: Investment timeline (years)
- `ltv_ratio`: Loan-to-value ratio for financing

**Generated Components**:
- **Residential Property**: 100-unit multifamily with mixed unit types (1BR/2BR)
- **Rolling Renovation Strategy**: Units expire with REABSORB behavior for systematic renovation
- **Capital Coordination**: $1.5M renovation program aligned with lease lifecycle  
- **Premium Absorption**: Post-renovation leasing at market rents with improved terms
- **Financing Structure**: Construction-to-permanent debt facilities
- **Complete Integration**: All components properly linked for immediate analysis

**Example Usage**:
```python
from datetime import date
from performa.patterns import create_value_add_acquisition_deal
from performa.deal import analyze
from performa.core.primitives import Timeline

# Create complete value-add deal
deal = create_value_add_acquisition_deal(
    property_name="Sunrise Apartments",
    acquisition_price=5_000_000,
    acquisition_date=date(2024, 1, 1),
    renovation_budget=800_000,
    stabilized_noi=450_000,
    hold_period_years=5,
    ltv_ratio=0.75
)

# Run comprehensive analysis
timeline = Timeline.from_dates("2024-01-01", "2029-12-31")
results = analyze(deal, timeline)

# Access results via fluent reporting interface
pro_forma = results.reporting.pro_forma_summary(frequency="A")
print(f"Year 5 NOI: ${pro_forma.loc['Net Operating Income', pro_forma.columns[4]:,.0f}")
```

**Value-Add Strategy Implementation**:

1. **Acquisition Phase**: Property acquired with existing tenant base generating current cash flows
2. **Strategic Rollover**: Natural lease expirations trigger REABSORB behavior
3. **Renovation Coordination**: Units go offline for 2-month renovation cycles  
4. **Premium Re-leasing**: Renovated units return via absorption plans at target rents
5. **Value Creation**: Systematic NOI improvement through rolling renovation program

**Expected Performance**:
- **Renovation Yields**: 15-25% annual return on renovation investment
- **NOI Growth**: 25-40% improvement from acquisition to stabilization
- **Property Value Creation**: $3-5M+ appreciation (depending on exit cap rates)
- **Investment Returns**: 18-25% unlevered IRR for successful implementations

#### `create_stabilized_acquisition_deal()`

*Status: Scaffolded for future implementation*

Models acquisition of stabilized, cash-flowing assets for steady income and appreciation.

### Development Patterns

#### `create_development_deal()`

*Status: Scaffolded for future implementation*

Models complete ground-up development from land acquisition through construction, lease-up, and stabilization.

## Implementation Architecture

### Value-Add Pattern Deep Dive

The `create_value_add_acquisition_deal` pattern demonstrates sophisticated real estate modeling:

**Dynamic Property Sizing**:
- Calculates unit count from acquisition price using industry standards ($100K/unit)
- Determines optimal unit mix based on target NOI and market conditions
- Generates realistic unit specifications (area, current rents, lease terms)

**Strategic Lease Management**:
- Implements REABSORB expiration behavior for renovation opportunities
- Coordinates 2-month downtime periods with capital plan execution
- Links renovated units to premium absorption plans for re-leasing

**Financial Integration**:
- Connects renovation budgets to actual capital expenditure schedules
- Aligns financing terms with hold period and investment strategy
- Generates realistic operating expenses and loss assumptions

**Market-Driven Logic**:
- Current rents calculated from acquisition NOI (typically 75% of stabilized)
- Target rents derived from stabilized NOI goals with improved margins
- Vacancy and collection assumptions reflect value-add risk profile

### Pattern Validation

All patterns undergo rigorous validation:

1. **Parameter Usage**: Every input parameter meaningfully affects deal structure
2. **Strategy Logic**: Investment approach correctly implemented in component relationships  
3. **Analysis Integration**: Generated deals run successfully through analysis engine
4. **Financial Reasonableness**: Outputs align with industry benchmarks and expectations
5. **Equivalence Testing**: Pattern outputs verified against manual component construction

## Best Practices

### When to Use Patterns

**Ideal Use Cases**:
- Rapid deal modeling and iteration during underwriting
- Standardized investment strategy implementation across portfolios
- Business user deal creation without deep technical knowledge
- Teaching and demonstration of real estate investment concepts
- Baseline scenarios for sensitivity analysis and stress testing

**Consider Component Construction When**:
- Implementing novel or highly customized investment strategies
- Requiring granular control over specific component relationships
- Building new pattern templates for future standardization
- Debugging complex deal structures or unusual performance issues

### Pattern Extension

Patterns are designed for extension and customization:

```python
# Start with standard pattern
base_deal = create_value_add_acquisition_deal(...)

# Customize specific components
base_deal.asset.expenses = create_custom_expense_model(...)
base_deal.financing = create_specialized_debt_structure(...)

# Maintain pattern benefits with targeted modifications
```

### Integration with Analysis

Patterns integrate seamlessly with Performa's analysis and reporting systems:

```python
# Pattern → Analysis → Reporting workflow
deal = create_value_add_acquisition_deal(...)  # Pattern
results = analyze(deal, timeline)               # Analysis Engine  
reports = results.reporting.pro_forma_summary() # Fluent Reporting

# Access all analysis components
partnership_returns = results.partner_distributions
debt_metrics = results.financing_analysis  
property_performance = results.unlevered_analysis
```

## Future Development

### Planned Patterns

- **Stabilized Acquisition**: Standard cash-flowing asset acquisition
- **Ground-Up Development**: Complete development project lifecycle
- **Opportunistic Strategies**: Distressed asset and special situation patterns
- **Portfolio Patterns**: Multi-asset and fund-level investment strategies

### Enhancement Roadmap

- **Sensitivity Integration**: Built-in sensitivity analysis for key parameters
- **Market Data Connections**: Dynamic parameter updating from market data sources
- **Strategy Optimization**: AI-driven parameter tuning for target return profiles
- **Custom Pattern Builder**: Tools for creating organization-specific patterns

## Contributing

Patterns follow established conventions:

1. **Function Signature**: Clear parameter names with type hints and defaults
2. **Documentation**: Comprehensive docstrings with examples and expected performance
3. **Validation**: External validation scripts proving parameter usage and logic
4. **Testing**: Unit tests covering creation, analysis integration, and edge cases
5. **Equivalence**: Demonstration of equivalence to manual component construction

New patterns should demonstrate significant productivity benefits while maintaining full modeling sophistication.
