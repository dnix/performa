# Performa `debt` Module - Real Estate Finance & Debt Structuring

This module provides debt modeling capabilities for real estate transactions, supporting construction loans, permanent financing, and complex debt structures with multiple tranches and varying terms. Built on a transactional ledger architecture for precise cash flow tracking and analysis.

## Key Components

### Core Debt Models
- **DebtFacility**: Abstract base for all debt types with common financing terms
- **PermanentFacility**: Traditional permanent financing with fixed/floating rates
- **ConstructionFacility**: Construction-to-permanent loans with multiple interest calculation methods
- **DebtTranche**: Individual debt components within facilities

### Financial Mechanics
- **LoanAmortization**: Payment schedules with principal and interest calculations
- **InterestRate**: Flexible rate structures (fixed, floating, tiered)
- **FinancingPlan**: Coordinated debt structuring across project phases
- **InterestCalculationMethod**: Multiple approaches for construction interest (NONE, SIMPLE, SCHEDULED, ITERATIVE)

### Rate Management
- **InterestRateType**: Rate type definitions (fixed, prime-based, SOFR-based)
- Support for rate caps, floors, and spreads
- Time-varying rate scenarios

## Architecture

The debt module implements a layered financing model with full ledger integration:

1. **Facility-level**: Overall debt structure and terms
2. **Tranche-level**: Individual debt components with specific terms  
3. **Payment-level**: Amortization and cash flow calculations
4. **Rate-level**: Interest rate mechanics and timing
5. **Ledger-level**: Transactional recording of all debt activities

## Construction Financing Features

### Interest Calculation Methods

The module provides a complexity dial for construction interest calculations:

#### `InterestCalculationMethod.NONE`
**Use Case**: Simple draws without interest calculations
- No interest reserve calculations
- Draws recorded as loan proceeds only
- Suitable for preliminary analysis or equity-funded construction

```python
construction_loan = ConstructionFacility(
    name="Simple Construction Facility",
    loan_amount=10_000_000,
    interest_rate=0.065,
    term_months=24,
    interest_calculation_method=InterestCalculationMethod.NONE
)
```

#### `InterestCalculationMethod.SIMPLE`
**Use Case**: Quick percentage-based interest reserves (industry standard: 8-12%)
- Estimates total interest as percentage of loan amount
- Creates upfront interest reserve
- Fast calculations for preliminary underwriting

```python
construction_loan = ConstructionFacility(
    name="Construction Loan with Simple Interest",
    loan_amount=10_000_000,
    interest_rate=0.065,
    term_months=24,
    interest_calculation_method=InterestCalculationMethod.SIMPLE,
    simple_reserve_rate=0.10  # 10% interest reserve
)
```

#### `InterestCalculationMethod.SCHEDULED`
**Use Case**: Draw-based calculation using actual schedules
- Interest calculated based on actual draw timing
- Interest capitalized into project cost basis
- Industry-standard approach for institutional development
- Full ledger integration with detailed transaction records

```python
construction_loan = ConstructionFacility(
    name="Institutional Construction Facility",
    loan_amount=10_000_000,
    interest_rate=0.065,
    term_months=24,
    interest_calculation_method=InterestCalculationMethod.SCHEDULED
)
```

#### `InterestCalculationMethod.ITERATIVE` 
**Use Case**: Multi-pass iteration for maximum precision (future enhancement)
- Full iterative calculation with feedback loops
- Maximum precision for complex scenarios
- Planned for future implementation

### Loan-to-Cost (LTC) vs Loan-to-Value (LTV)

The module properly handles both construction and permanent financing metrics:

**Construction Loans**: Use LTC (Loan-to-Cost)
- Based on total project costs (land + hard + soft costs)
- Automatically calculated from ledger-based project costs
- Industry-standard sizing approach

**Permanent Loans**: Use LTV (Loan-to-Value)
- Based on appraised or market value
- Supports both manual and automatic sizing

```python
# Construction facility with LTC sizing
construction = ConstructionFacility(
    tranches=[
        DebtTranche(
            name="Senior Construction",
            ltc_threshold=0.75,  # 75% LTC
            interest_rate=InterestRate(details=FixedRate(rate=0.065))
        )
    ]
)

# Permanent facility with LTV sizing
permanent = PermanentFacility(
    name="Permanent Loan",
    ltv_ratio=0.70,  # 70% LTV
    sizing_method="auto",  # Auto-size based on value
    interest_rate=0.055
)
```

### Ledger Integration

All debt facilities integrate with the transactional ledger:

**Transaction Recording**: Every debt activity creates detailed ledger entries
```python
# Loan proceeds recorded as:
TransactionRecord(
    category=CashFlowCategoryEnum.FINANCING,
    subcategory=FinancingSubcategoryEnum.LOAN_PROCEEDS,
    amount=loan_draw_amount,
    item_name=f"{facility.name} - Draw"
)

# Interest capitalization recorded as:
TransactionRecord(
    category=CashFlowCategoryEnum.CAPITAL,
    subcategory=CapitalSubcategoryEnum.SOFT_COSTS,
    amount=capitalized_interest,
    item_name=f"{facility.name} - Capitalized Interest"
)
```

**Analysis Integration**: Debt analysis uses ledger data for precise calculations
```python
# Automatic LTC calculation from ledger
total_project_cost = ledger_queries.capital_uses().sum()
max_loan_amount = total_project_cost * ltc_threshold

# Interest calculation from actual draw schedule
drawn_amounts = ledger_queries.loan_proceeds_by_period()
interest_calculation = calculate_interest_on_drawn_balances(drawn_amounts, rate)
```

## Design Principles

- **Industry Standards**: Follows real estate financing conventions and terminology
- **Flexible Complexity**: From simple permanent loans to multi-tranche construction facilities
- **Ledger Integration**: Full transaction recording and audit trail
- **Calculation Transparency**: Every financial calculation is explicit and auditable
- **Multi-Tranche Support**: Complex debt structures with varying terms and priorities

## Key Features

### Construction Financing
- Construction-to-permanent loan transitions
- Interest reserve calculations and funding
- Draw-based interest capitalization
- LTC-based loan sizing
- Integration with development timelines

### Permanent Financing
- Fixed and floating rate structures
- Amortization schedules with various terms
- LTV-based loan sizing (manual and automatic)
- Refinancing and loan assumption modeling

### Multi-Tranche Structures
- Senior/subordinate debt layers
- Varying interest rates and terms
- Waterfall payment priorities
- Cross-collateralization support

## Example Usage

### Simple Permanent Financing

```python
from performa.debt import PermanentFacility, FixedRate, InterestRate

permanent_loan = PermanentFacility(
    name="Acquisition Loan",
    loan_amount=12_000_000,
    interest_rate=InterestRate(details=FixedRate(rate=0.055)),
    term_months=300,  # 25-year term
    amortization_months=360,  # 30-year amortization
    loan_to_value_ratio=0.75
)
```

### Construction Financing

```python
from performa.debt import (
    ConstructionFacility, DebtTranche, InterestRate, FixedRate
)
from performa.core.primitives import InterestCalculationMethod

# Multi-tranche construction facility
construction_loan = ConstructionFacility(
    name="Development Construction Loan",
    tranches=[
        DebtTranche(
            name="Senior Construction Tranche",
            ltc_threshold=0.70,
            interest_rate=InterestRate(details=FixedRate(rate=0.065)),
            fee_rate=0.01
        ),
        DebtTranche(
            name="Mezzanine Construction Tranche",
            ltc_threshold=0.80,
            interest_rate=InterestRate(details=FixedRate(rate=0.095)),
            fee_rate=0.015
        )
    ],
    interest_calculation_method=InterestCalculationMethod.SCHEDULED,
    term_months=18,
    interest_only_months=18
)
```

### Construction-to-Permanent Structure

```python
from performa.debt import create_construction_to_permanent_plan

financing_plan = create_construction_to_permanent_plan(
    construction_loan_amount=15_000_000,
    construction_interest_rate=0.065,
    construction_term_months=24,
    
    permanent_loan_amount=20_000_000,
    permanent_interest_rate=0.055,
    permanent_term_months=300,
    permanent_amortization_months=360,
    
    interest_calculation_method=InterestCalculationMethod.SCHEDULED
)
```

### Floating Rate Structures

```python
from performa.debt import FloatingRate, RateIndexEnum

# Floating rate with spread and floor
floating_rate = InterestRate(
    details=FloatingRate(
        index=RateIndexEnum.SOFR,
        spread=0.025,  # 250 basis points spread
        floor=0.045,   # 4.5% floor
        cap=0.085      # 8.5% cap
    )
)

permanent_loan = PermanentFacility(
    name="Floating Rate Loan",
    loan_amount=25_000_000,
    interest_rate=floating_rate,
    term_months=120,
    amortization_months=360
)
```

## Integration

This module integrates with:

### Asset Modules
- **Development module**: Construction financing for ground-up projects
- **Office/Residential modules**: Permanent financing for stabilized assets
- **Capital planning**: Coordinated funding with renovation and improvement programs

### Analysis Engine
- **Cash flow orchestration**: Debt service calculations in multi-pass analysis
- **Funding cascade**: Debt proceeds funding capital uses via ledger
- **Sensitivity analysis**: Rate and term sensitivity modeling

### Valuation Module
- **DCF analysis**: Debt service integration in levered cash flows
- **Debt sizing**: LTV and DSCR-based loan sizing
- **Refinancing analysis**: Value-based refinancing scenarios

### Ledger System
- **Transaction recording**: All debt activities recorded as ledger entries
- **Query interface**: Analysis uses ledger queries for precise calculations
- **Audit trail**: Complete transaction history for compliance and review

## Construction Loan Monitoring

Real-time construction loan monitoring and compliance:

```python
# Monitor construction loan metrics
def monitor_construction_loan(facility, context):
    current_ltc = facility.calculate_current_ltc(context)
    remaining_capacity = facility.calculate_remaining_capacity(context)
    
    return {
        "current_ltc": current_ltc,
        "remaining_capacity": remaining_capacity,
        "compliance_status": "compliant" if current_ltc <= facility.max_ltc else "violation"
    }
```

## Best Practices

### Construction Financing
- Use `InterestCalculationMethod.SCHEDULED` for institutional-grade analysis
- Size construction loans using LTC based on total project costs
- Include appropriate interest reserves (typically 8-12% of loan amount)
- Coordinate draw schedules with development timelines

### Permanent Financing
- Use LTV-based sizing for stabilized assets
- Consider cash flow coverage (DSCR) in addition to LTV
- Model floating rates with appropriate floors and caps
- Include refinancing scenarios for long-term holds

### Multi-Tranche Structures
- Layer tranches by risk and return profile
- Ensure waterfall payment priorities are clearly defined
- Model cross-default and cross-collateralization provisions
- Include appropriate fees and closing costs

### Ledger Integration
- Leverage ledger queries for precise debt sizing
- Use transaction records for audit trails
- Coordinate debt analysis with funding cascade calculations
- Maintain transaction categorization consistency

The debt module enables financing analysis while maintaining simplicity for straightforward permanent financing scenarios. The ledger-first architecture ensures all calculations are transparent, auditable, and aligned with institutional standards.