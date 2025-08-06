# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

import sys

import pandas as pd

from performa.core.primitives import Timeline
from performa.debt.construction import ConstructionFacility, DebtTranche
from performa.debt.permanent import PermanentFacility
from performa.debt.plan import FinancingPlan
from performa.debt.rates import FixedRate, InterestRate


def test_refinancing_orchestration():
    """Quick test of refinancing orchestration functionality."""
    print("🚀 Testing Refinancing Orchestration")
    print("=" * 50)

    # Create timeline
    timeline = Timeline.from_dates("2024-01-01", "2029-01-01")
    print(f"✓ Timeline created: {len(timeline.period_index)} periods")

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
    print("✓ Construction facility created")

    # Create permanent facility with automatic sizing
    permanent_facility = PermanentFacility(
        name="Permanent Loan",
        kind="permanent",
        interest_rate=InterestRate(details=FixedRate(rate=0.055)),
        loan_term_years=10,
        amortization_years=25,
        refinance_timing=36,  # 36 months
        # Loan sizing constraints
        sizing_method="auto",
        ltv_ratio=0.75,
        dscr_hurdle=1.25,
        debt_yield_hurdle=0.08,
        # Covenant monitoring
        ongoing_ltv_max=0.80,
        ongoing_dscr_min=1.20,
        ongoing_debt_yield_min=0.075,
        # Interest-only period
        interest_only_months=24,
    )
    print("✓ Permanent facility created with auto sizing")

    # Create financing plan
    financing_plan = FinancingPlan(
        name="Construction-to-Permanent Financing",
        facilities=[construction_facility, permanent_facility],
    )
    print("✓ Financing plan created")

    # Create mock property value and NOI series
    property_values = []
    noi_values = []

    for i, period in enumerate(timeline.period_index):
        # Property value grows from $8M to $10M
        if i < 24:  # Construction phase
            property_value = 8_000_000 + (i * 50_000)
        else:  # Stabilized phase
            property_value = 9_200_000 + ((i - 24) * 25_000)

        # NOI grows from $0 to $700K
        if i < 18:  # Pre-stabilization
            noi = 0
        elif i < 30:  # Lease-up phase
            noi = (i - 18) * 50_000
        else:  # Stabilized phase
            noi = 600_000 + ((i - 30) * 5_000)

        property_values.append(property_value)
        noi_values.append(noi)

    property_value_series = pd.Series(property_values, index=timeline.period_index)
    noi_series = pd.Series(noi_values, index=timeline.period_index)
    print("✓ Property value and NOI series created")

    # Test refinancing transaction calculation
    refinancing_transactions = financing_plan.calculate_refinancing_transactions(
        timeline=timeline,
        property_value_series=property_value_series,
        noi_series=noi_series,
        financing_cash_flows=None,
    )
    print(
        f"✓ Refinancing transactions calculated: {len(refinancing_transactions)} transactions"
    )

    if refinancing_transactions:
        transaction = refinancing_transactions[0]
        print("\n📋 Transaction Details:")
        print(f"  Type: {transaction['transaction_type']}")
        print(f"  Payoff Facility: {transaction['payoff_facility']}")
        print(f"  New Facility: {transaction['new_facility']}")
        print(f"  Transaction Date: {transaction['transaction_date']}")
        print(f"  New Loan Amount: ${transaction['new_loan_amount']:,.0f}")
        print(f"  Payoff Amount: ${transaction['payoff_amount']:,.0f}")
        print(f"  Closing Costs: ${transaction['closing_costs']:,.0f}")
        print(f"  Net Proceeds: ${transaction['net_proceeds']:,.0f}")

        # Print sizing analysis
        sizing = transaction["sizing_analysis"]
        print("\n📊 Sizing Analysis:")
        print(f"  Method: {sizing['sizing_method']}")
        print(f"  Property Value: ${sizing['property_value']:,.0f}")
        print(f"  NOI: ${sizing['noi']:,.0f}")
        print(f"  LTV Constraint: ${sizing['ltv_constraint']:,.0f}")
        print(f"  DSCR Constraint: ${sizing['dscr_constraint']:,.0f}")
        print(f"  Debt Yield Constraint: ${sizing['debt_yield_constraint']:,.0f}")
        print(f"  Most Restrictive: {sizing['most_restrictive']}")

        # Print covenant monitoring
        covenant = transaction["covenant_monitoring"]
        print("\n🔍 Covenant Monitoring:")
        print(f"  Enabled: {covenant['monitoring_enabled']}")
        print(f"  Ongoing LTV Max: {covenant['ongoing_ltv_max']:.1%}")
        print(f"  Ongoing DSCR Min: {covenant['ongoing_dscr_min']:.2f}x")
        print(f"  Ongoing Debt Yield Min: {covenant['ongoing_debt_yield_min']:.1%}")

        print("\n🎉 Refinancing Orchestration Test PASSED!")
    else:
        print("❌ No refinancing transactions generated")
        assert False, "No refinancing transactions generated"


if __name__ == "__main__":
    try:
        test_refinancing_orchestration()
        print("Test PASSED")
        sys.exit(0)
    except Exception as e:
        print(f"Test FAILED: {e}")
        sys.exit(1)
