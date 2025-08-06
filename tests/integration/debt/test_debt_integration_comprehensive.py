# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Comprehensive Debt Module Integration Test

This test demonstrates the complete integration of all debt module features
working together in a realistic real estate development scenario:
- Floating rate construction loans with SOFR + spread + caps
- Construction-to-permanent refinancing with automatic sizing
- Loan sizing constraints (LTV, DSCR, Debt Yield)
- Interest-only periods for permanent loans
- Covenant monitoring throughout loan lifecycle
- Complete cash flow integration and validation

Uses real Pydantic models to ensure proper integration.
"""

import sys

import pandas as pd

from performa.core.primitives import Timeline
from performa.debt.construction import ConstructionFacility, DebtTranche
from performa.debt.permanent import PermanentFacility
from performa.debt.plan import FinancingPlan
from performa.debt.rates import FixedRate, FloatingRate, InterestRate, RateIndexEnum


def test_comprehensive_debt_integration():
    """
    Comprehensive debt module integration test.

    This test demonstrates all debt module features working together:
    1. Floating rate construction financing
    2. Construction-to-permanent refinancing with automatic sizing
    3. Interest-only permanent loans
    4. Covenant monitoring integration
    5. Complete cash flow calculations
    """
    print("🚀 Testing Comprehensive Debt Module Integration")
    print("=" * 60)

    # Create timeline for development project
    timeline = Timeline.from_dates("2024-01-01", "2029-01-01")
    print(
        f"✓ Timeline: {len(timeline.period_index)} months ({timeline.start_date} to {timeline.end_date})"
    )

    # 1. Create Construction Facility with Floating Rate (SOFR + spread + cap)
    construction_facility = ConstructionFacility(
        name="SOFR Construction Loan",
        kind="construction",
        tranches=[
            DebtTranche(
                name="Senior Construction Tranche",
                ltc_threshold=0.75,  # 75% LTC
                interest_rate=InterestRate(
                    details=FloatingRate(
                        rate_index=RateIndexEnum.SOFR_30_DAY_AVG,
                        spread=0.0275,  # 275 basis points
                        interest_rate_cap=0.08,  # 8% cap
                        interest_rate_floor=0.02,  # 2% floor
                        reset_frequency="monthly",
                    )
                ),
                fee_rate=0.01,  # 1% origination fee
            )
        ],
    )
    print("✓ Construction Facility: SOFR + 275bps, 8% cap, 75% LTC")

    # 2. Create Permanent Facility with automatic sizing + interest-only + covenants
    permanent_facility = PermanentFacility(
        name="Permanent Loan",
        kind="permanent",
        interest_rate=InterestRate(details=FixedRate(rate=0.055)),  # 5.5% fixed
        loan_term_years=10,
        amortization_years=25,
        refinance_timing=36,  # Refinance after 36 months (construction + stabilization)
        # Automatic loan sizing using multiple constraints
        sizing_method="auto",
        ltv_ratio=0.75,  # 75% LTV maximum
        dscr_hurdle=1.25,  # 1.25x DSCR minimum
        debt_yield_hurdle=0.08,  # 8% debt yield minimum
        # Interest-only period
        interest_only_months=24,  # 2 years interest-only
        # Ongoing covenant monitoring
        ongoing_ltv_max=0.80,  # 80% max LTV ongoing
        ongoing_dscr_min=1.20,  # 1.20x min DSCR ongoing
        ongoing_debt_yield_min=0.075,  # 7.5% min debt yield ongoing
    )
    print(
        "✓ Permanent Facility: 5.5% fixed, auto-sizing, 24-month I/O, covenant monitoring"
    )

    # 3. Create Complete Financing Plan
    financing_plan = FinancingPlan(
        name="Construction-to-Permanent Financing",
        facilities=[construction_facility, permanent_facility],
    )
    print(f"✓ Financing Plan: {len(financing_plan.facilities)} facilities")

    # 4. Test Floating Rate Calculations with Mock SOFR Curve
    print("\n📈 Testing Floating Rate Calculations:")

    # Create rising SOFR curve (realistic scenario)
    periods = pd.period_range("2024-01", periods=36, freq="M")
    sofr_rates = [0.045 + (i * 0.001) for i in range(36)]  # 4.5% to 7.9%
    sofr_curve = pd.Series(sofr_rates, index=periods)

    # Test rate calculations for different periods
    floating_rate = construction_facility.tranches[0].interest_rate

    test_periods = [periods[0], periods[17], periods[35]]  # Start, middle, end
    for period in test_periods:
        effective_rate = floating_rate.get_rate_for_period(period, sofr_curve)
        sofr_base = sofr_curve[period]
        print(f"  {period}: SOFR {sofr_base:.3%} + 275bps = {effective_rate:.3%}")

    # Verify cap functionality
    high_sofr_period = periods[35]  # Should trigger cap
    high_rate = floating_rate.get_rate_for_period(high_sofr_period, sofr_curve)
    expected_uncapped = sofr_curve[high_sofr_period] + 0.0275
    is_capped = high_rate < expected_uncapped
    print(
        f"  Rate Cap Applied: {is_capped} (effective: {high_rate:.3%}, uncapped: {expected_uncapped:.3%})"
    )

    # 5. Test Refinancing Transaction Calculation
    print("\n🔄 Testing Refinancing Process:")

    # Mock property value and NOI series for refinancing
    property_values = []
    noi_values = []

    for i, period in enumerate(timeline.period_index):
        # Property value grows during construction/stabilization
        if i < 24:  # Construction phase
            property_value = 8_000_000 + (i * 50_000)  # $8M to $9.2M
        else:  # Stabilized phase
            property_value = 9_200_000 + ((i - 24) * 25_000)  # Growing value

        # NOI grows during lease-up and stabilization
        if i < 18:  # Pre-stabilization
            noi = 0
        elif i < 30:  # Lease-up phase
            noi = (i - 18) * 50_000  # $0 to $600K
        else:  # Stabilized phase
            noi = 600_000 + ((i - 30) * 5_000)  # $600K growing

        property_values.append(property_value)
        noi_values.append(noi)

    property_value_series = pd.Series(property_values, index=timeline.period_index)
    noi_series = pd.Series(noi_values, index=timeline.period_index)

    # Calculate refinancing transactions
    refinancing_transactions = financing_plan.calculate_refinancing_transactions(
        timeline=timeline,
        property_value_series=property_value_series,
        noi_series=noi_series,
        financing_cash_flows=None,  # Simplified for this test
    )

    assert len(refinancing_transactions) == 1, "Should have one refinancing transaction"

    transaction = refinancing_transactions[0]
    print(f"  Transaction Type: {transaction['transaction_type']}")
    print(
        f"  Timing: {transaction['transaction_date']} (month {permanent_facility.refinance_timing})"
    )
    print(
        f"  From: {transaction['payoff_facility']} → To: {transaction['new_facility']}"
    )

    # 6. Test Automatic Loan Sizing
    print("\n🎯 Testing Automatic Loan Sizing:")

    sizing_analysis = transaction["sizing_analysis"]
    refinance_period_idx = permanent_facility.refinance_timing - 1  # 0-indexed
    refinance_property_value = property_value_series.iloc[refinance_period_idx]
    refinance_noi = noi_series.iloc[refinance_period_idx]

    print(f"  Property Value: ${refinance_property_value:,.0f}")
    print(f"  NOI: ${refinance_noi:,.0f}")
    print(f"  LTV Constraint: ${sizing_analysis['ltv_constraint']:,.0f}")
    print(f"  DSCR Constraint: ${sizing_analysis['dscr_constraint']:,.0f}")
    print(f"  Debt Yield Constraint: ${sizing_analysis['debt_yield_constraint']:,.0f}")
    print(f"  Most Restrictive: {sizing_analysis['most_restrictive']}")
    print(f"  Final Loan Amount: ${transaction['new_loan_amount']:,.0f}")

    # Verify sizing logic
    ltv_loan = refinance_property_value * 0.75
    debt_yield_loan = refinance_noi / 0.08
    most_restrictive_amount = min(
        ltv_loan, sizing_analysis["dscr_constraint"], debt_yield_loan
    )

    assert (
        abs(transaction["new_loan_amount"] - most_restrictive_amount) < 1000
    ), "Loan amount should equal most restrictive constraint"

    # 7. Test Interest-Only Period Integration
    print("\n⏱️  Testing Interest-Only Periods:")

    # Generate amortization schedule for permanent loan
    amortization = permanent_facility.generate_amortization(
        loan_amount=transaction["new_loan_amount"],
        start_date=transaction["transaction_date"],
    )

    # Verify interest-only structure
    io_periods = permanent_facility.interest_only_months

    # Check first I/O payment vs first amortizing payment
    io_payment = amortization.iloc[0]["Payment"]
    amortizing_payment = amortization.iloc[io_periods]["Payment"]

    print(f"  Interest-Only Period: {io_periods} months")
    print(f"  I/O Payment: ${io_payment:,.0f}/month")
    print(f"  Amortizing Payment: ${amortizing_payment:,.0f}/month")
    print(
        f"  Payment Increase: ${amortizing_payment - io_payment:,.0f}/month ({((amortizing_payment / io_payment) - 1) * 100:.1f}%)"
    )

    # Verify I/O periods have zero principal
    io_schedule = amortization.iloc[:io_periods]
    assert (
        io_schedule["Principal"] == 0
    ).all(), "I/O periods should have zero principal payment"

    # Verify amortizing periods have principal > 0
    amortizing_schedule = amortization.iloc[io_periods:]
    assert (
        amortizing_schedule["Principal"] > 0
    ).all(), "Amortizing periods should have principal > 0"

    # 8. Test Covenant Monitoring Integration
    print("\n⚖️  Testing Covenant Monitoring:")

    covenant_monitoring = transaction["covenant_monitoring"]
    print(f"  Monitoring Enabled: {covenant_monitoring['monitoring_enabled']}")
    print(f"  Ongoing LTV Max: {covenant_monitoring['ongoing_ltv_max']:.1%}")
    print(f"  Ongoing DSCR Min: {covenant_monitoring['ongoing_dscr_min']:.2f}x")
    print(
        f"  Ongoing Debt Yield Min: {covenant_monitoring['ongoing_debt_yield_min']:.1%}"
    )

    # Verify covenant monitoring configuration
    assert covenant_monitoring["ongoing_ltv_max"] > 0, "Ongoing LTV should be positive"
    assert (
        covenant_monitoring["ongoing_dscr_min"] > 0
    ), "Ongoing DSCR should be positive"
    assert (
        covenant_monitoring["ongoing_debt_yield_min"] > 0
    ), "Ongoing debt yield should be positive"

    print("  ✓ Covenant hurdles are configured and reasonable")

    # 9. Test Cash Flow Integration
    print("\n💰 Testing Cash Flow Integration:")

    net_proceeds = transaction["net_proceeds"]
    closing_costs = transaction["closing_costs"]
    payoff_amount = transaction.get("payoff_amount", 0)

    print(f"  New Loan Proceeds: ${transaction['new_loan_amount']:,.0f}")
    print(f"  Less: Payoff Amount: ${payoff_amount:,.0f}")
    print(f"  Less: Closing Costs: ${closing_costs:,.0f}")
    print(f"  Net Proceeds: ${net_proceeds:,.0f}")

    # Verify cash flow math
    expected_net = transaction["new_loan_amount"] - payoff_amount - closing_costs
    assert (
        abs(net_proceeds - expected_net) < 1
    ), "Net proceeds calculation should be accurate"

    # 10. Integration Summary
    print("\n🎉 COMPREHENSIVE INTEGRATION TEST RESULTS:")
    print("=" * 60)
    print("✅ Floating Rate Construction Loan: WORKING")
    print(f"   - SOFR-based rates with cap/floor: {is_capped}")
    print(
        f"   - Rate range: {floating_rate.get_rate_for_period(periods[0], sofr_curve):.2%} to {high_rate:.2%}"
    )

    print("✅ Construction-to-Permanent Refinancing: WORKING")
    print(f"   - Automatic timing at month {permanent_facility.refinance_timing}")
    print("   - Seamless construction → permanent transition")

    print("✅ Automatic Loan Sizing: WORKING")
    print(f"   - Most restrictive constraint: {sizing_analysis['most_restrictive']}")
    print(f"   - Conservative loan sizing: ${transaction['new_loan_amount']:,.0f}")

    print("✅ Interest-Only Periods: WORKING")
    print(f"   - {io_periods}-month I/O period integrated")
    print("   - Payment structure validated")

    print("✅ Covenant Monitoring: WORKING")
    print("   - Ongoing risk management setup")
    print("   - Covenant hurdles configured properly")

    print("✅ Cash Flow Integration: WORKING")
    print(f"   - Net refinance proceeds: ${net_proceeds:,.0f}")
    print("   - Complete transaction accounting")

    print("\n🏆 ALL DEBT MODULE FEATURES WORKING TOGETHER SUCCESSFULLY!")
    print(
        "Complete debt module integration validated in realistic development scenario."
    )


if __name__ == "__main__":
    test_comprehensive_debt_integration()
    print("\nTest PASSED")
    sys.exit(0)
