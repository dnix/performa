# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0


"""
Integration Tests for Debt Module Features

This test suite demonstrates the key integration points of the debt module:
- Debt service calculations with interest-only periods
- Dynamic floating rate calculations with time-varying indices
- Construction-to-permanent refinancing workflows
- Loan covenant monitoring
- Rate cap and floor enforcement
"""

import sys
import traceback

import numpy as np
import pandas as pd

from performa.core.primitives import Timeline
from performa.debt import DebtTranche
from performa.debt.construction import ConstructionFacility
from performa.debt.permanent import PermanentFacility
from performa.debt.plan import FinancingPlan
from performa.debt.rates import FixedRate, FloatingRate, InterestRate, RateIndexEnum


def test_debt_service_with_interest_only():
    """Test debt service calculations with interest-only periods."""
    print("🔧 Testing Debt Service with Interest-Only Periods")
    print("-" * 50)

    # Create permanent facility with interest-only periods
    permanent_facility = PermanentFacility(
        name="Permanent Loan",
        kind="permanent",
        interest_rate=InterestRate(details=FixedRate(rate=0.055)),
        loan_term_years=10,
        amortization_years=25,
        # Interest-only period
        interest_only_months=24,
        # Manual sizing
        sizing_method="manual",
        loan_amount=5_000_000,
        # Required fields
        ltv_ratio=0.75,
        dscr_hurdle=1.25,
    )

    # Create timeline for loan term
    timeline = Timeline.from_dates("2024-01-01", "2034-01-01")

    # Generate amortization schedule
    schedule = permanent_facility.generate_amortization(
        loan_amount=5_000_000, start_date=timeline.period_index[0]
    )

    # Verify interest-only periods
    first_24_months = schedule.iloc[:24]
    assert (
        first_24_months["Principal"] == 0
    ).all(), "First 24 months should be interest-only"
    assert (first_24_months["Interest"] > 0).all(), "Should have interest payments"

    # Verify amortizing periods start after I/O period
    amortizing_months = schedule.iloc[24:]
    assert (
        amortizing_months["Principal"] > 0
    ).all(), "Should have principal payments after I/O period"

    print("✓ Interest-only period verified: 24 months")
    print(f"✓ I/O payment: ${first_24_months['Payment'].iloc[0]:,.0f}")
    print(f"✓ Amortizing payment: ${amortizing_months['Payment'].iloc[0]:,.0f}")


def test_floating_rate_calculations():
    """Test floating rate calculations with time-varying indices."""
    print("\n🔧 Testing Floating Rate Calculations")
    print("-" * 50)

    # Create floating rate facility
    floating_rate = InterestRate(
        details=FloatingRate(
            rate_index=RateIndexEnum.SOFR_30_DAY_AVG,
            spread=0.0275,  # 275 bps
            interest_rate_cap=0.08,  # 8% cap
        )
    )

    timeline = Timeline.from_dates("2024-01-01", "2026-01-01")

    # Create rising SOFR curve
    sofr_values = np.linspace(0.045, 0.065, len(timeline.period_index))  # 4.5% to 6.5%
    sofr_curve = pd.Series(sofr_values, index=timeline.period_index)

    # Test rate calculations for different periods
    rates = []
    for period in timeline.period_index[:6]:
        rate = floating_rate.get_rate_for_period(period, sofr_curve)
        rates.append(rate)

    # Verify rates are changing
    assert len(set(rates)) > 1, "Rates should vary with SOFR curve"

    # Verify cap is applied (SOFR + spread might hit cap)
    max_rate = max(rates)
    assert max_rate <= 0.08, "Rate cap should be enforced"

    print(f"✓ Dynamic rates calculated: {min(rates):.3%} to {max(rates):.3%}")
    print(f"✓ Rate cap enforced at: {max_rate:.3%}")


def test_construction_to_permanent_refinancing():
    """Test construction-to-permanent loan refinancing with automatic sizing."""
    print("\n🔧 Testing Construction-to-Permanent Refinancing")
    print("-" * 50)

    # Create construction facility
    construction_facility = ConstructionFacility(
        name="Construction Loan",
        kind="construction",
        tranches=[
            DebtTranche(
                name="Senior Construction",
                ltc_threshold=0.75,
                interest_rate=InterestRate(details=FixedRate(rate=0.08)),
                fee_rate=0.01,
            )
        ],
    )

    # Create permanent facility with automatic sizing
    permanent_facility = PermanentFacility(
        name="Permanent Loan",
        kind="permanent",
        interest_rate=InterestRate(details=FixedRate(rate=0.055)),
        loan_term_years=10,
        amortization_years=25,
        refinance_timing=24,  # 24 months
        # Loan sizing constraints (LTV, DSCR, Debt Yield)
        sizing_method="auto",
        ltv_ratio=0.75,
        dscr_hurdle=1.25,
        debt_yield_hurdle=0.08,
        # Ongoing covenant monitoring
        ongoing_ltv_max=0.80,
        ongoing_dscr_min=1.20,
        ongoing_debt_yield_min=0.075,
    )

    # Create financing plan
    financing_plan = FinancingPlan(
        name="Construction-to-Permanent Financing",
        facilities=[construction_facility, permanent_facility],
    )

    # Create timeline and test data
    timeline = Timeline.from_dates("2024-01-01", "2029-01-01")

    # Mock property value and NOI series
    property_value_series = pd.Series(
        [9_000_000] * len(timeline.period_index), index=timeline.period_index
    )
    noi_series = pd.Series(
        [600_000] * len(timeline.period_index), index=timeline.period_index
    )

    # Test refinancing transaction calculation
    refinancing_transactions = financing_plan.calculate_refinancing_transactions(
        timeline=timeline,
        property_value_series=property_value_series,
        noi_series=noi_series,
        financing_cash_flows=None,
    )

    assert (
        len(refinancing_transactions) == 1
    ), "Should generate one refinancing transaction"

    transaction = refinancing_transactions[0]
    assert transaction["transaction_type"] == "construction_to_permanent_refinancing"
    assert transaction["new_loan_amount"] > 0
    assert transaction["sizing_analysis"]["sizing_method"] == "automatic"
    assert transaction["covenant_monitoring"]["monitoring_enabled"] == True  # noqa: E712

    print("✓ Refinancing transaction generated")
    print(f"✓ New loan amount: ${transaction['new_loan_amount']:,.0f}")
    print(
        f"✓ Most restrictive constraint: {transaction['sizing_analysis']['most_restrictive']}"
    )
    print(
        f"✓ Covenant monitoring enabled: {transaction['covenant_monitoring']['monitoring_enabled']}"
    )


def test_loan_covenant_monitoring():
    """Test loan covenant monitoring functionality."""
    print("\n🔧 Testing Loan Covenant Monitoring")
    print("-" * 50)

    # Create permanent facility with covenant monitoring
    permanent_facility = PermanentFacility(
        name="Permanent Loan",
        kind="permanent",
        interest_rate=InterestRate(details=FixedRate(rate=0.055)),
        loan_term_years=10,
        amortization_years=25,
        # Manual sizing
        sizing_method="manual",
        loan_amount=6_000_000,
        # Required fields
        ltv_ratio=0.75,
        dscr_hurdle=1.25,
        # Covenant monitoring parameters
        ongoing_ltv_max=0.80,
        ongoing_dscr_min=1.20,
        ongoing_debt_yield_min=0.075,
    )

    # Create timeline
    timeline = Timeline.from_dates("2024-01-01", "2029-01-01")

    # Create test scenarios
    # Scenario 1: Compliant metrics
    property_values_good = pd.Series(
        [8_000_000] * len(timeline.period_index), index=timeline.period_index
    )
    noi_good = pd.Series(
        [600_000] * len(timeline.period_index), index=timeline.period_index
    )

    results_good = permanent_facility.calculate_covenant_monitoring(
        timeline=timeline,
        property_value_series=property_values_good,
        noi_series=noi_good,
        loan_amount=6_000_000,
    )

    breach_summary_good = permanent_facility.get_covenant_breach_summary(results_good)

    # Scenario 2: Covenant breach scenario
    property_values_bad = pd.Series(
        [7_000_000] * len(timeline.period_index), index=timeline.period_index
    )
    noi_bad = pd.Series(
        [400_000] * len(timeline.period_index), index=timeline.period_index
    )

    results_bad = permanent_facility.calculate_covenant_monitoring(
        timeline=timeline,
        property_value_series=property_values_bad,
        noi_series=noi_bad,
        loan_amount=6_000_000,
    )

    breach_summary_bad = permanent_facility.get_covenant_breach_summary(results_bad)

    # Verify covenant monitoring detects breaches
    assert (
        breach_summary_good["Breach_Rate"] < breach_summary_bad["Breach_Rate"]
    ), "Should detect more breaches in stressed scenario"

    print(f"✓ Compliant scenario breach rate: {breach_summary_good['Breach_Rate']:.1%}")
    print(f"✓ Stressed scenario breach rate: {breach_summary_bad['Breach_Rate']:.1%}")
    print("✓ Covenant monitoring working correctly")


def test_interest_rate_caps():
    """Test that interest rate caps are properly enforced."""
    print("\n🔧 Testing Interest Rate Cap Enforcement")
    print("-" * 50)

    # Create floating rate with restrictive cap
    floating_rate = InterestRate(
        details=FloatingRate(
            rate_index=RateIndexEnum.SOFR_30_DAY_AVG,
            spread=0.03,  # 300 bps
            interest_rate_cap=0.06,  # 6% cap
        )
    )

    timeline = Timeline.from_dates("2024-01-01", "2025-01-01")

    # Create high SOFR curve that would exceed cap
    high_sofr = pd.Series(
        [0.055] * len(timeline.period_index), index=timeline.period_index
    )  # 5.5% SOFR

    # Calculate rates - should be capped
    capped_rate = floating_rate.get_rate_for_period(timeline.period_index[0], high_sofr)

    # 5.5% SOFR + 3% spread = 8.5%, but cap at 6%
    expected_uncapped = 0.055 + 0.03  # 8.5%
    assert capped_rate == 0.06, f"Rate should be capped at 6%, got {capped_rate:.3%}"
    assert expected_uncapped > 0.06, "Test setup: uncapped rate should exceed cap"

    print("✓ SOFR: 5.50%")
    print("✓ Spread: 3.00%")
    print(f"✓ Uncapped: {expected_uncapped:.2%}")
    print(f"✓ Capped rate: {capped_rate:.2%}")
    print("✓ Rate cap enforcement working")


def run_all_integration_tests():
    """Run all debt module integration tests."""
    print("🚀 Debt Module Integration Tests")
    print("=" * 60)

    tests = [
        test_debt_service_with_interest_only,
        test_floating_rate_calculations,
        test_construction_to_permanent_refinancing,
        test_loan_covenant_monitoring,
        test_interest_rate_caps,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"❌ {test.__name__} failed with error: {str(e)}")
            traceback.print_exc()

    print("\n" + "=" * 60)
    print("🎯 Integration Test Summary")
    print("=" * 60)
    print(f"Tests Passed: {passed}")
    print(f"Tests Failed: {failed}")
    print(f"Success Rate: {passed / (passed + failed):.1%}")

    if failed == 0:
        print("\n🎉 All integration tests passed!")
        print("Debt module features are working correctly!")
        return True
    else:
        print(f"\n❌ {failed} integration tests failed")
        return False


if __name__ == "__main__":
    success = run_all_integration_tests()
    sys.exit(0 if success else 1)
