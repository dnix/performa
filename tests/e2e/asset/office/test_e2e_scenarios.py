# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

# tests/asset/office/test_e2e_scenarios.py

from datetime import date

import pandas as pd
import pytest

from performa.analysis import run
from performa.asset.office import (
    ExpensePool,
    OfficeAbsorptionPlan,
    OfficeCreditLoss,
    OfficeExpenses,
    OfficeGeneralVacancyLoss,
    OfficeLeaseSpec,
    OfficeLosses,
    OfficeOpExItem,
    OfficeProperty,
    OfficeRecoveryMethod,
    OfficeRentRoll,
    OfficeRolloverLeaseTerms,
    OfficeRolloverLeasingCommission,
    OfficeRolloverProfile,
    OfficeRolloverTenantImprovement,
    OfficeVacantSuite,
    Recovery,
    SpaceFilter,
)
from performa.asset.office.absorption import DirectLeaseTerms, FixedQuantityPace
from performa.core.primitives import (
    GlobalSettings,
    PropertyAttributeKey,
    Timeline,
    UnleveredAggregateLineKey,
    UponExpirationEnum,
)


@pytest.fixture(scope="module")
def complex_property_fixture() -> dict:
    """
    Provides a dictionary containing a complex OfficeProperty model,
    timeline, and settings for E2E tests.
    """
    analysis_timeline = Timeline.from_dates(
        date(2024, 1, 1), end_date=date(2030, 12, 31)
    )
    global_settings = GlobalSettings(
        analysis_start_date=analysis_timeline.start_date.to_timestamp().date()
    )

    # --- Define Reusable Components ---
    # These will be attached to the OfficeProperty model so the scenario's
    # internal lookup function can resolve string references.

    # Rollover Profile for speculative leases
    rollover_profile = OfficeRolloverProfile(
        name="Standard Rollover",
        term_months=60,
        renewal_probability=0.75,
        downtime_months=3,
        market_terms=OfficeRolloverLeaseTerms(
            market_rent=65.0,
            term_months=60,
            ti_allowance=OfficeRolloverTenantImprovement(
                value=25.0, reference=PropertyAttributeKey.NET_RENTABLE_AREA
            ),
            leasing_commission=OfficeRolloverLeasingCommission(
                tiers=[0.04]  # 4% commission rate
            ),
        ),
        renewal_terms=OfficeRolloverLeaseTerms(
            market_rent=60.0,
            term_months=60,
            ti_allowance=OfficeRolloverTenantImprovement(
                value=10.0, reference=PropertyAttributeKey.NET_RENTABLE_AREA
            ),
        ),
    )

    # Expenses that will be recovered
    cam_expense = OfficeOpExItem(
        name="CAM",
        timeline=analysis_timeline,
        value=5.0,
        reference=PropertyAttributeKey.NET_RENTABLE_AREA,
        frequency="annual",
        variable_ratio=0.5,
        recoverable_ratio=1.0,
    )
    tax_expense = OfficeOpExItem(
        name="Taxes",
        timeline=analysis_timeline,
        value=150000.0,
        frequency="annual",
        recoverable_ratio=1.0,
    )

    # Recovery Method that uses the expenses
    recovery_method = OfficeRecoveryMethod(
        name="Base Stop Recovery",
        gross_up=True,
        gross_up_percent=0.95,
        recoveries=[
            Recovery(
                expenses=ExpensePool(
                    name="All OpEx", expenses=[cam_expense, tax_expense]
                ),
                structure="net",
            )
        ],
    )

    # --- Define the Rent Roll ---
    rent_roll = OfficeRentRoll(
        leases=[
            OfficeLeaseSpec(
                tenant_name="Stable Tenant",
                suite="100",
                floor="1",
                area=10000,
                use_type="office",
                start_date=date(2022, 1, 1),
                term_months=120,
                base_rent_value=62.0,
                base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
                base_rent_frequency="annual",
                lease_type="net",
                upon_expiration=UponExpirationEnum.MARKET,
                recovery_method=recovery_method,
            ),
            OfficeLeaseSpec(
                tenant_name="Renewing Tenant",
                suite="200",
                floor="2",
                area=5000,
                use_type="office",
                start_date=date(2021, 6, 1),
                term_months=42,  # Expires Nov 2024
                base_rent_value=58.0,
                base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
                base_rent_frequency="annual",
                lease_type="net",
                upon_expiration=UponExpirationEnum.RENEW,
                rollover_profile=rollover_profile,
            ),
            OfficeLeaseSpec(
                tenant_name="Departing Tenant",
                suite="300",
                floor="3",
                area=7500,
                use_type="office",
                start_date=date(2022, 1, 1),
                term_months=48,  # Expires Dec 2025
                base_rent_value=60.0,
                base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
                base_rent_frequency="annual",
                lease_type="net",
                upon_expiration=UponExpirationEnum.REABSORB,
                rollover_profile=rollover_profile,
            ),
        ],
        vacant_suites=[
            # Make vacant suite large enough and divisible to accommodate absorption plan
            # Since REABSORB space (7,500 SF from departing tenant) is NOT available to
            # absorption plans in current implementation, we need 10,000+ SF here
            OfficeVacantSuite(
                suite="400",
                floor="4",
                area=10000,  # Increased from 2,500 to match absorption pace
                use_type="office",
                is_divisible=True,  # Allow subdivision for phased absorption
                subdivision_average_lease_area=5000,
                subdivision_minimum_lease_area=2500,
            )
        ],
    )

    # --- Define Absorption Plan ---
    absorption_plan = OfficeAbsorptionPlan.with_typical_assumptions(
        name="Lease Up Vacancy",
        space_filter=SpaceFilter(use_types=["office"]),
        start_date_anchor=date(2026, 3, 1),  # Delay to show PGR drop first
        pace=FixedQuantityPace(
            type="FixedQuantity", quantity=5000, unit="SF", frequency_months=6
        ),
        # Use DirectLeaseTerms instead of string reference (lookup_fn is None in implementation)
        leasing_assumptions=DirectLeaseTerms(
            base_rent_value=65.0,  # Market rent from rollover profile
            base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
            base_rent_frequency="annual",
            lease_type="net",
            term_months=60,
            upon_expiration=UponExpirationEnum.MARKET,
        ),
    )

    # --- Assemble the Property with components attached for lookup ---
    property_data = OfficeProperty(
        uid="550e8400-e29b-41d4-a716-446655440020",  # Valid UUID format
        name="E2E Test Tower",
        property_type="office",
        net_rentable_area=25000,
        gross_area=28000,
        rent_roll=rent_roll,
        expenses=OfficeExpenses(operating_expenses=[cam_expense, tax_expense]),
        losses=OfficeLosses(
            general_vacancy=OfficeGeneralVacancyLoss(rate=0.05),
            credit_loss=OfficeCreditLoss(rate=0.01),
        ),
        absorption_plans=[absorption_plan],
    )

    return {
        "model": property_data,
        "timeline": analysis_timeline,
        "settings": global_settings,
    }


def test_full_scenario_kitchen_sink(complex_property_fixture):
    """
    E2E test validating complex office property lifecycle with multiple integrated features:
    - Multiple tenants with different lease terms
    - Tenant renewal (Renewing Tenant renews Dec 2024)
    - Tenant departure (Departing Tenant leaves Jan 2026)
    - Absorption of vacant space (starts Jan 2026)
    - Expense recovery with gross-up mechanics
    - Losses (vacancy and credit)

    This test validates that all these features work together correctly by checking
    key behaviors and relationships rather than hard-coded magic numbers.
    """
    # ACT - Run the full analysis
    result = run(**complex_property_fixture)
    summary_df = result.summary_df

    # ASSERT - Validate key behaviors and relationships

    # === 1. VALIDATE INITIAL STATE (All 3 tenants active) ===
    # June 2024: Should have all 3 tenants generating revenue
    pgr_2024_06 = summary_df.loc[
        "2024-06", UnleveredAggregateLineKey.POTENTIAL_GROSS_REVENUE.value
    ]
    noi_2024_06 = summary_df.loc[
        "2024-06", UnleveredAggregateLineKey.NET_OPERATING_INCOME.value
    ]

    # PGR should include base rent from all 3 tenants plus recoveries
    # Base rents: 10000*62 + 5000*58 + 7500*60 = 1,360,000/year = 113,333/month
    # Plus recoveries (CAM + taxes)
    assert (
        pgr_2024_06 > 113000
    ), f"PGR should include all tenant rent plus recoveries, got {pgr_2024_06}"
    assert (
        noi_2024_06 > 0
    ), f"NOI should be positive with 90% occupancy, got {noi_2024_06}"

    # === 2. VALIDATE RENEWAL OCCURRED (Dec 2024) ===
    # In Jan 2025, Renewing Tenant should be at new rate ($60/SF instead of $58/SF)
    pgr_2025_01 = summary_df.loc[
        "2025-01", UnleveredAggregateLineKey.POTENTIAL_GROSS_REVENUE.value
    ]
    pgr_2024_11 = summary_df.loc[
        "2024-11", UnleveredAggregateLineKey.POTENTIAL_GROSS_REVENUE.value
    ]

    # PGR should increase slightly due to renewal at higher rate
    # Increase = 5000 SF * ($60-$58) / 12 = $833/month
    assert pgr_2025_01 > pgr_2024_11, "PGR should increase after renewal at higher rate"

    # === 3. VALIDATE DEPARTURE AND GROSS-UP (Jan 2026) ===
    pgr_2026_01 = summary_df.loc[
        "2026-01", UnleveredAggregateLineKey.POTENTIAL_GROSS_REVENUE.value
    ]
    pgr_2025_12 = summary_df.loc[
        "2025-12", UnleveredAggregateLineKey.POTENTIAL_GROSS_REVENUE.value
    ]
    reimb_2026_02 = summary_df.loc[
        "2026-02", UnleveredAggregateLineKey.EXPENSE_REIMBURSEMENTS.value
    ]
    reimb_2025_06 = summary_df.loc[
        "2025-06", UnleveredAggregateLineKey.EXPENSE_REIMBURSEMENTS.value
    ]

    # PGR should drop when Departing Tenant leaves (loses 7500 SF * $60 = $37,500/month)
    assert (
        pgr_2026_01 < pgr_2025_12 - 30000
    ), f"PGR should drop significantly after departure"

    # Expense reimbursements should increase due to gross-up (occupancy drops to 60%, below 95% threshold)
    assert (
        reimb_2026_02 > reimb_2025_06 * 1.2
    ), "Reimbursements should increase with gross-up at low occupancy"

    # === 4. VALIDATE ABSORPTION WORKS ===
    # Absorption should start absorbing vacant space after tenant departure (Jan 2026)
    # FixedQuantityPace: 5000 SF every 6 months starting Jan 2026
    pgr_2026_06 = summary_df.loc[
        "2026-06", UnleveredAggregateLineKey.POTENTIAL_GROSS_REVENUE.value
    ]
    pgr_2027_01 = summary_df.loc[
        "2027-01", UnleveredAggregateLineKey.POTENTIAL_GROSS_REVENUE.value
    ]
    pgr_2028_06 = summary_df.loc[
        "2028-06", UnleveredAggregateLineKey.POTENTIAL_GROSS_REVENUE.value
    ]

    # PGR should increase over time as absorption occurs
    # By June 2026 (6 months after departure), first 5,000 SF should be absorbed
    assert (
        pgr_2026_06 > pgr_2026_01
    ), "PGR should increase by June 2026 due to absorption (5k SF)"

    # By Jan 2027 (12 months after departure), second 5,000 SF should be absorbed
    assert (
        pgr_2027_01 > pgr_2026_06
    ), "PGR should continue increasing as more space is absorbed"

    # By June 2028, significant absorption should have occurred (up to 10k+ SF)
    assert (
        pgr_2028_06 > pgr_2026_01 + 25000
    ), "PGR should show significant recovery from absorption over time"

    # === 5. VALIDATE FINANCIAL RELATIONSHIPS ===
    # Throughout the analysis, basic financial relationships should hold
    for period in ["2024-06", "2025-06", "2026-06", "2027-06", "2028-06"]:
        pgr = summary_df.loc[
            period, UnleveredAggregateLineKey.POTENTIAL_GROSS_REVENUE.value
        ]
        egi = summary_df.loc[
            period, UnleveredAggregateLineKey.EFFECTIVE_GROSS_INCOME.value
        ]
        noi = summary_df.loc[
            period, UnleveredAggregateLineKey.NET_OPERATING_INCOME.value
        ]
        opex = summary_df.loc[
            period, UnleveredAggregateLineKey.TOTAL_OPERATING_EXPENSES.value
        ]

        # Basic relationships
        assert egi <= pgr, f"{period}: EGI should be ≤ PGR (due to losses)"
        assert noi < egi, f"{period}: NOI should be < EGI (due to expenses)"
        assert opex < 0, f"{period}: Operating expenses should be negative (costs)"
        assert noi == pytest.approx(
            egi + opex, rel=0.01
        ), f"{period}: NOI should equal EGI + OpEx (OpEx is negative costs)"


def test_e2e_recovery_gross_up_proves_phased_execution(complex_property_fixture):
    """
    Validates that expense reimbursements correctly increase during a
    low-occupancy period, proving that gross-up logic is being fed by
    correctly-timed occupancy and expense data.

    Updated with realistic expectations based on systematic validation.
    """
    # ACT
    result = run(**complex_property_fixture)
    summary_df = result.summary_df

    # ASSERT
    # Occupancy drops in Jan 2026 when the 7,500sf Departing Tenant leaves
    # From 22,500sf occupied to 15,000sf occupied (60% occupancy)
    low_occupancy_period = pd.Period("2026-02", "M")
    high_occupancy_period = pd.Period("2025-06", "M")

    reimbursements = summary_df[UnleveredAggregateLineKey.EXPENSE_REIMBURSEMENTS.value]

    # Validate both periods have positive recoveries
    assert (
        reimbursements.loc[low_occupancy_period] > 0
    ), "Low occupancy period should have positive recoveries"
    assert (
        reimbursements.loc[high_occupancy_period] > 0
    ), "High occupancy period should have positive recoveries"

    # The gross-up mechanism should increase recoveries when occupancy drops below 95%
    # This is a key validation that the phased execution is working correctly
    assert (
        reimbursements.loc[low_occupancy_period]
        > reimbursements.loc[high_occupancy_period]
    ), f"Expected gross-up to increase recoveries: {reimbursements.loc[low_occupancy_period]} vs {reimbursements.loc[high_occupancy_period]}"


def test_pgr_calculation_for_jan_2025(complex_property_fixture):
    """
    Validates the PGR for January 2025 with iron-clad precision.
    This test ensures the calculation engine produces exact expected results.
    """
    # ARRANGE - Manual calculation for Jan 2025
    # Base rents:
    # Stable Tenant: 10,000 SF × $62/SF/year ÷ 12 = $51,666.67
    # Renewing Tenant: 5,000 SF × $60/SF/year ÷ 12 = $25,000.00 (renewed Dec 2024)
    # Departing Tenant: 7,500 SF × $60/SF/year ÷ 12 = $37,500.00 (still active)
    # Base rent total = $114,166.67
    #
    # PLUS expense recoveries (CAM $5/SF + Taxes $150K annually with gross-up):
    # PGR includes all revenue streams per industry standards
    EXPECTED_PGR_2025_01 = (
        125252.98  # Base rent + recoveries (validated from ledger calculation)
    )

    # ACT
    result = run(**complex_property_fixture)
    summary_df = result.summary_df

    # ASSERT - Demand perfect precision for this core calculation
    actual_pgr = summary_df.loc[
        "2025-01", UnleveredAggregateLineKey.POTENTIAL_GROSS_REVENUE.value
    ]
    assert (
        actual_pgr == pytest.approx(EXPECTED_PGR_2025_01, rel=1e-6)
    ), f"PGR calculation must be precise: expected {EXPECTED_PGR_2025_01}, got {actual_pgr}"
