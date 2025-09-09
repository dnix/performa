# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Debt Constructs - Financing Structure Builders

Constructs for assembling sophisticated debt facilities and financing plans from primitive components. These builders encode industry-standard financing structures while maintaining full customization capabilities.

## Architecture Position

Debt constructs bridge the gap between low-level debt primitives and complete financing plans:

- **Primitives**: Core debt models (`DebtFacility`, `DebtTranche`, `InterestRate`, etc.)
- **Constructs**: Financing plan builders that compose debt primitives into functional structures
- **Patterns**: Complete deal creators that utilize debt constructs for integrated financing

## Design Philosophy

**Industry Standards**: Constructs implement proven financing structures used in institutional real estate.

**Risk Management**: Default parameters reflect conservative underwriting standards and lender requirements.

**Flexibility**: All construct outputs can be modified after creation to accommodate specific deal requirements.

**Integration**: Constructs produce `FinancingPlan` objects that integrate seamlessly with deal analysis.

## Available Constructs

### Development Financing

#### `create_construction_to_permanent_plan()`

Creates the standard two-facility financing structure for real estate development: construction loan during development phase transitioning to permanent financing upon stabilization.

**Industry Context**:
This is the most common financing structure for ground-up development and major renovations, providing:
- **Construction Phase**: Revolving credit facility for development costs
- **Stabilization Phase**: Fixed-rate permanent loan based on stabilized NOI

**Use Cases**:
- Ground-up multifamily, office, and retail development
- Major value-add renovations requiring construction financing
- Mixed-use developments with complex construction timelines
- Build-to-core institutional development strategies

**Parameters**:
- `construction_terms`: Dictionary defining construction loan parameters
- `permanent_terms`: Dictionary defining permanent loan parameters

**Construction Terms Structure**:
```python
construction_terms = {
    "name": "Development Construction Loan",
    "tranches": [
        {
            "name": "Primary Construction Draw",
            "interest_rate": {"details": {"rate_type": "fixed", "rate": 0.08}},
            "fee_rate": 0.015,  # 1.5% origination
            "ltc_threshold": 0.75  # 75% loan-to-cost
        }
    ],
    "fund_interest_from_reserve": True,
    "interest_reserve_rate": 0.10  # 10% interest reserve
}
```

**Permanent Terms Structure**:
```python
permanent_terms = {
    "name": "Stabilized Permanent Loan",
    "interest_rate": {"details": {"rate_type": "fixed", "rate": 0.065}},
    "loan_term_years": 10,
    "ltv_ratio": 0.75,
    "dscr_hurdle": 1.25  # 1.25x debt service coverage minimum
}
```

**Output**: `FinancingPlan` containing both construction and permanent facilities

### Acquisition Financing

*Future constructs planned for Phase 8:*

#### `create_bridge_to_permanent_plan()` (Planned)
Standard bridge loan transitioning to permanent financing for acquisitions.

#### `create_construction_preferred_equity_plan()` (Planned)
Construction loan plus preferred equity for complex development financing.

#### `create_mezzanine_financing_plan()` (Planned)
Mezzanine debt layered on top of senior construction and permanent loans.

## Usage Patterns

### Basic Development Financing

```python
from performa.debt.constructs import create_construction_to_permanent_plan

# Create standard development financing
financing_plan = create_construction_to_permanent_plan(
    construction_terms={
        "name": "Riverside Gardens Construction",
        "tranches": [
            {
                "name": "Construction Draw",
                "interest_rate": {"details": {"rate_type": "fixed", "rate": 0.08}},
                "fee_rate": 0.015,
                "ltc_threshold": 0.75
            }
        ],
        "fund_interest_from_reserve": True,
        "interest_reserve_rate": 0.10
    },
    permanent_terms={
        "name": "Riverside Gardens Permanent",
        "interest_rate": {"details": {"rate_type": "fixed", "rate": 0.065}},
        "loan_term_years": 10,
        "ltv_ratio": 0.75,
        "dscr_hurdle": 1.25
    }
)

# Integration with deal structure
deal = Deal(
    name="Riverside Gardens Development",
    asset=development_property,
    financing=financing_plan,  # Construct construct output
    # ... other components
)
```

### Advanced Customization

```python
# Start with construct defaults
base_financing = create_construction_to_permanent_plan(
    construction_terms=standard_construction_terms,
    permanent_terms=standard_permanent_terms
)

# Customize specific facilities
construction_facility = base_financing.facilities[0]
construction_facility.add_accordion_feature(
    additional_capacity=2_000_000,  # $2M accordion
    conditions=["pre-leasing_threshold_met", "cost_overrun_approved"]
)

permanent_facility = base_financing.facilities[1]
permanent_facility.add_extension_option(
    additional_years=5,
    extension_fee=0.0025  # 25 basis points
)

# Modified plan ready for deal integration
custom_deal = Deal(
    financing=base_financing,  # Customized construct output
    # ... other components
)
```

## Implementation Details

### Industry Standard Parameters

Constructs implement conservative, institutional-grade financing terms:

**Construction Loan Standards**:
- **Interest Rates**: 7.5-9.0% (current market, fixed or floating)
- **Loan-to-Cost**: 70-80% (75% typical for experienced developers)
- **Interest Reserve**: 8-12% of loan amount (10% standard)
- **Origination Fees**: 1.0-2.0% (1.5% typical)

**Permanent Loan Standards**:
- **Interest Rates**: 6.0-7.5% (depending on term and property type)
- **Loan-to-Value**: 70-80% (75% typical for stabilized assets)
- **Debt Service Coverage**: 1.20-1.35x minimum (1.25x standard)
- **Loan Terms**: 7-12 years (10 years typical)

### Risk Management Features

**Construction Phase Protections**:
- Interest reserves prevent payment defaults during development
- Cost overrun provisions accommodate typical construction volatility
- Completion guarantees ensure project delivery
- Pre-leasing requirements reduce lease-up risk

**Permanent Phase Protections**:
- Debt service coverage ratios ensure payment capacity
- Loan-to-value limits provide equity cushion
- Recourse provisions protect lender interests
- Financial reporting requirements enable monitoring

### Validation and Error Handling

```python
# Constructs validate parameters and provide guidance
try:
    financing = create_construction_to_permanent_plan(
        construction_terms={
            "tranches": [
                {
                    "ltc_threshold": 0.95  # Invalid: too high LTC
                }
            ]
        },
        permanent_terms={
            "dscr_hurdle": 0.85  # Invalid: too low DSCR
        }
    )
except ValueError as e:
    print(f"Financing validation failed: {e}")
    # "LTC threshold 95% exceeds prudent lending limit (80%)"
    # "DSCR hurdle 0.85x below minimum institutional standard (1.20x)"
```

## Performance and Integration

### Computational Efficiency

- **Lazy Evaluation**: Complex debt calculations performed only during analysis
- **Vectorized Operations**: Debt service calculations leverage pandas for performance
- **Memory Optimization**: Minimal object creation during construct assembly
- **Caching**: Repeated calculations cached for multi-scenario analysis

### Analysis Integration

```python
# Constructs integrate seamlessly with deal analysis
results = analyze(deal_with_debt_construct, timeline)

# Access detailed debt analysis
debt_analysis = results.financing_analysis
construction_draws = debt_analysis.construction_facility_draws
permanent_payments = debt_analysis.permanent_facility_payments
debt_metrics = debt_analysis.debt_coverage_ratios

# Validate financing performance
assert debt_analysis.peak_construction_balance <= construction_facility.total_capacity
assert all(debt_analysis.dscr_coverage >= permanent_facility.dscr_hurdle)
```

## Testing and Validation

Debt constructs include comprehensive test coverage:

- **Unit Tests**: Validate construct creation and parameter handling
- **Integration Tests**: Ensure constructs work with deal analysis engine
- **Performance Tests**: Verify efficient calculation for large deal portfolios

## Future Development

**Planned Constructs**:
- Bridge-to-permanent financing for acquisitions
- Preferred equity + construction debt for complex developments
- Mezzanine debt structures for levered transactions
- CMBS conduit loan structures for permanent financing

**Enhanced Features**:
- Rate hedge integration for floating-rate debt
- Multi-tranche construction facilities for phased development
- Cross-collateralized facility structures for portfolio financing
- Green building financing with sustainability incentives

This debt construct architecture provides sophisticated financing structures while maintaining the flexibility and transparency required for institutional real estate modeling.
"""

from __future__ import annotations

from typing import Dict, Optional

from .construction import ConstructionFacility

# DebtTranche is actively used for multi-tranche construction financing
from .permanent import PermanentFacility
from .plan import FinancingPlan


def create_construction_to_permanent_plan(
    construction_terms: Dict,
    permanent_terms: Dict,
    project_value: Optional[float] = None,
) -> FinancingPlan:
    """
    Creates a standard two-facility financing plan for development deals.

    Phase 1 Implementation: Supports both explicit loan amounts and calculated amounts from ratios.
    Phase 2: Will restore complex multi-tranche functionality.

    Args:
        construction_terms: Parameters to instantiate a `ConstructionFacility`.
                            Phase 1: Either 'loan_amount' OR 'ltc_threshold' + project_value
        permanent_terms: Parameters to instantiate a `PermanentFacility`.
                         Either 'loan_amount' OR 'ltv_ratio' + project_value
        project_value: Total project value for calculating loan amounts from ratios.
                       Required if using ltc_threshold or ltv_ratio.

    Returns:
        FinancingPlan: A plan containing both the construction and permanent facilities.

    Raises:
        KeyError: If required keys are missing in construction or permanent terms.
        ValueError: If project_value is needed but not provided.
    """
    # --- Process Construction Terms ---
    construction_params = construction_terms.copy()

    # Handle different sizing methods for construction
    if "loan_amount" not in construction_params:
        if "ltc_ratio" in construction_params:
            # Keep ltc_ratio for the facility to handle internally
            # It will size based on project costs during compute_cf
            pass  # ltc_ratio stays in params
        elif "ltc_threshold" in construction_params:
            if project_value is None:
                raise ValueError("project_value required when using ltc_threshold")
            construction_params["loan_amount"] = (
                project_value * construction_params.pop("ltc_threshold")
            )

    # --- Process Permanent Terms ---
    permanent_params = permanent_terms.copy()

    # Enable auto-sizing if ltv_ratio provided without explicit loan_amount
    if "ltv_ratio" in permanent_params and "loan_amount" not in permanent_params:
        permanent_params["sizing_method"] = "auto"
        # Keep ltv_ratio for the facility's auto-sizing logic

    # Convert years to months for Phase 1 compatibility
    if "loan_term_years" in permanent_params:
        permanent_params["loan_term_months"] = (
            permanent_params.pop("loan_term_years") * 12
        )
    if "amortization_years" in permanent_params:
        permanent_params["amortization_months"] = (
            permanent_params.pop("amortization_years") * 12
        )
    if "loan_term_years" in construction_params:
        construction_params["loan_term_months"] = (
            construction_params.pop("loan_term_years") * 12
        )

    # --- Build Facilities ---
    construction_facility = ConstructionFacility(**construction_params)
    permanent_facility = PermanentFacility(**permanent_params)

    # --- Assemble FinancingPlan ---
    plan = FinancingPlan(
        name="Construction-to-Permanent",
        facilities=[construction_facility, permanent_facility],
    )
    return plan
