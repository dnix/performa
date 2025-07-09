# Performa `debt` Module - Real Estate Finance & Debt Structuring

This module provides comprehensive debt modeling capabilities for real estate
transactions, supporting construction loans, permanent financing, and complex
debt structures with multiple tranches and varying terms.

## Key Components

### Core Debt Models
- **DebtFacility**: Abstract base for all debt types with common financing terms
- **PermanentFacility**: Traditional permanent financing with fixed/floating rates
- **ConstructionFacility**: Construction-to-perm loans with interest reserves
- **DebtTranche**: Individual debt components within facilities

### Financial Mechanics
- **LoanAmortization**: Payment schedules with principal and interest calculations
- **InterestRate**: Flexible rate structures (fixed, floating, tiered)
- **FinancingPlan**: Coordinated debt structuring across project phases

### Rate Management
- **InterestRateType**: Rate type definitions (fixed, prime-based, SOFR-based)
- Support for rate caps, floors, and spreads
- Time-varying rate scenarios

## Architecture

The debt module implements a layered financing model:

1. **Facility-level**: Overall debt structure and terms
2. **Tranche-level**: Individual debt components with specific terms  
3. **Payment-level**: Amortization and cash flow calculations
4. **Rate-level**: Interest rate mechanics and timing

## Design Principles

- Flexible debt structuring for simple to complex scenarios
- Industry-standard financing terminology and calculations
- Integration with development timelines and cash flows
- Support for construction and permanent financing phases
- Realistic modeling of lender requirements and constraints

## Key Features

- Construction-to-permanent loan transitions
- Multiple debt tranches with varying terms
- Interest reserves and payment calculations
- Loan-to-cost and loan-to-value monitoring
- Integration with development and stabilization phases

## Example Usage

```python
from performa.debt import (
    ConstructionFacility, PermanentFacility, FinancingPlan,
    InterestRate, InterestRateType
)

# Construction financing
construction_loan = ConstructionFacility(
    name="Construction Facility",
    loan_amount=15_000_000,
    interest_rate=InterestRate(
        base_rate=0.065,
        rate_type=InterestRateType.FIXED
    ),
    term_months=24,
    interest_only_months=24
)

# Permanent financing
permanent_loan = PermanentFacility(
    name="Permanent Facility", 
    loan_amount=20_000_000,
    interest_rate=InterestRate(
        base_rate=0.055,
        rate_type=InterestRateType.FIXED
    ),
    term_months=300,
    amortization_months=360
)

# Combined financing plan
financing_plan = FinancingPlan(
    construction_facility=construction_loan,
    permanent_facility=permanent_loan,
    transition_timing="project_completion"
)
```

## Integration

This module integrates with:
- **Development module** for construction financing
- **Asset modules** for permanent financing
- **Deal module** for debt service and returns
- **Valuation module** for debt sizing and LTV calculations

The debt module enables sophisticated financing analysis while maintaining
simplicity for straightforward permanent financing scenarios. 