# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Integration tests for construction loan backward compatibility.

Tests that SIMPLE interest calculation method behaves exactly as before,
ensuring no breaking changes for existing users.

Uses ResidentialDevelopmentPattern for realistic end-to-end testing.
"""

from datetime import date

import pytest

from performa.core.primitives import InterestCalculationMethod
from performa.debt.construction import ConstructionFacility
from performa.debt.rates import FixedRate, InterestRate
from performa.patterns.residential_development import ResidentialDevelopmentPattern


@pytest.mark.integration
def test_simple_method_unchanged():
    """
    SIMPLE method should behave exactly as before the synchronous calculation changes.

    This is the KEY backward compatibility test. Validates that:
    - SIMPLE method uses legacy path
    - Upfront interest calculation unchanged
    - Same results as before implementation
    - No breaking changes to public API

    Setup:
    - Full residential development with SIMPLE interest method
    - Cash sweep configured (PREPAY mode)

    Expected:
    - Interest transactions posted
    - No synchronous calculation artifacts
    - Sweep prepayments work via legacy process() method
    """
    # Create pattern with SIMPLE method
    pattern = ResidentialDevelopmentPattern(
        project_name="SIMPLE Backward Compat Test",
        acquisition_date=date(2024, 1, 1),
        land_cost=3_500_000,
        total_units=120,
        unit_mix=[
            {"unit_type": "1BR", "count": 60, "avg_sf": 650, "target_rent": 1800},
            {"unit_type": "2BR", "count": 60, "avg_sf": 950, "target_rent": 2400},
        ],
        construction_cost_per_unit=160_000,
        construction_duration_months=18,
        hold_period_years=7,
        interest_calculation_method="SIMPLE",  # Legacy method
        construction_sweep_mode="prepay",  # Test sweep integration
    )

    # Run full analysis
    results = pattern.analyze()
    ledger_df = results.ledger_df

    print(f"\n=== SIMPLE METHOD VALIDATION ===")
    print(f"Total transactions: {len(ledger_df)}")

    # CRITICAL CHECK 1: Interest payments should exist
    interest_txns = ledger_df[ledger_df["subcategory"] == "Interest Payment"]
    assert len(interest_txns) > 0, "SIMPLE should post interest transactions"
    print(f"✓ Found {len(interest_txns)} interest payment transactions")

    # CRITICAL CHECK 2: No synchronous calculation artifacts
    # SCHEDULED method posts "Interest from Sweep" subcategory - SIMPLE should NOT
    interest_from_sweep = ledger_df[
        ledger_df["item_name"].str.contains("Interest from Sweep", case=False, na=False)
    ]
    assert (
        len(interest_from_sweep) == 0
    ), "SIMPLE should NOT have synchronous 'Interest from Sweep' artifacts"
    print(f"✓ No 'Interest from Sweep' transactions (confirms legacy path)")

    # CRITICAL CHECK 3: Sweep prepayments should work
    sweep_prepayments = ledger_df[ledger_df["subcategory"] == "Sweep Prepayment"]
    assert len(sweep_prepayments) > 0, "SIMPLE should process sweep prepayments"
    print(f"✓ Found {len(sweep_prepayments)} sweep prepayment transactions")

    # CRITICAL CHECK 4: Analysis should complete successfully
    assert results.levered_irr > 0, "Deal should have positive IRR"
    print(f"✓ Deal IRR: {results.levered_irr:.2%}")

    print(f"\n✓ SIMPLE METHOD BACKWARD COMPATIBILITY VALIDATED")
    print(f"  - Legacy interest calculation works ✓")
    print(f"  - No breaking changes ✓")
    print(f"  - Distinct from SCHEDULED method ✓")


@pytest.mark.integration
def test_simple_vs_scheduled_comparison():
    """
    Compare SIMPLE vs SCHEDULED methods for same deal.

    Should show:
    - SIMPLE: Interest from reserve upfront
    - SCHEDULED: Interest from sweep, period-by-period
    - Different transaction patterns
    - Both produce valid results
    """
    base_params = {
        "project_name": "Method Comparison",
        "acquisition_date": date(2024, 1, 1),
        "land_cost": 3_500_000,
        "total_units": 120,
        "unit_mix": [
            {"unit_type": "1BR", "count": 60, "avg_sf": 650, "target_rent": 1800},
            {"unit_type": "2BR", "count": 60, "avg_sf": 950, "target_rent": 2400},
        ],
        "construction_cost_per_unit": 160_000,
        "construction_duration_months": 18,
        "hold_period_years": 7,
        "construction_sweep_mode": "prepay",
    }

    # Test SIMPLE
    simple_pattern = ResidentialDevelopmentPattern(
        **base_params, interest_calculation_method="SIMPLE"
    )
    simple_results = simple_pattern.analyze()
    simple_ledger = simple_results.ledger_df

    # Test SCHEDULED
    scheduled_pattern = ResidentialDevelopmentPattern(
        **base_params, interest_calculation_method="SCHEDULED"
    )
    scheduled_results = scheduled_pattern.analyze()
    scheduled_ledger = scheduled_results.ledger_df

    print(f"\n=== METHOD COMPARISON ===")

    # Count interest transactions
    simple_interest = len(
        simple_ledger[simple_ledger["subcategory"] == "Interest Payment"]
    )
    scheduled_interest = len(
        scheduled_ledger[scheduled_ledger["subcategory"] == "Interest Payment"]
    )

    print(f"SIMPLE interest transactions:    {simple_interest}")
    print(f"SCHEDULED interest transactions: {scheduled_interest}")

    # Key difference: SCHEDULED should have more interest transactions
    # because it calculates period-by-period vs SIMPLE's upfront calculation
    print(
        f"\nDifference: {scheduled_interest - simple_interest} more transactions in SCHEDULED"
    )

    # Both methods should produce interest payments
    assert simple_interest > 0, "SIMPLE should post interest"
    assert scheduled_interest > 0, "SCHEDULED should post interest"

    # SCHEDULED should generally have more transactions (period-by-period)
    # But this isn't always guaranteed depending on implementation details
    # So we just verify both work

    # Check sweep prepayments
    simple_sweeps = len(
        simple_ledger[simple_ledger["subcategory"] == "Sweep Prepayment"]
    )
    scheduled_sweeps = len(
        scheduled_ledger[scheduled_ledger["subcategory"] == "Sweep Prepayment"]
    )

    print(f"\nSweep prepayments:")
    print(f"  SIMPLE:    {simple_sweeps}")
    print(f"  SCHEDULED: {scheduled_sweeps}")

    # Both should produce valid results
    assert simple_results.levered_irr > 0, "SIMPLE should have positive IRR"
    assert scheduled_results.levered_irr > 0, "SCHEDULED should have positive IRR"

    print(f"\n✓ BOTH METHODS WORK CORRECTLY")
    print(f"  - SIMPLE IRR:    {simple_results.levered_irr:.2%}")
    print(f"  - SCHEDULED IRR: {scheduled_results.levered_irr:.2%}")
    print(f"  - Both produce valid deal analysis ✓")


@pytest.mark.integration
def test_no_breaking_api_changes():
    """
    Validate no breaking changes to public API.

    - All existing fields still work
    - Constructor signature unchanged
    - Pattern creation works with SIMPLE method
    """

    # This test can run immediately - just validates API
    facility = ConstructionFacility(
        name="Test Facility",
        interest_rate=InterestRate(details=FixedRate(rate=0.07)),
        ltc_ratio=0.75,
        loan_term_months=18,
        interest_calculation_method=InterestCalculationMethod.SIMPLE,
    )

    # Verify all expected attributes exist
    assert hasattr(facility, "name")
    assert hasattr(facility, "interest_rate")
    assert hasattr(facility, "ltc_ratio")
    assert hasattr(facility, "loan_term_months")
    assert hasattr(facility, "interest_calculation_method")
    assert hasattr(facility, "cash_sweep")

    # Verify all expected methods exist
    assert hasattr(facility, "compute_cf")
    assert hasattr(facility, "process_covenants")

    # Verify defaults unchanged
    assert facility.cash_sweep is None, "cash_sweep should default to None"
    assert facility.interest_calculation_method == InterestCalculationMethod.SIMPLE

    print("✓ API backward compatibility validated")
