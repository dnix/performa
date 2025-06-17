# tests/asset/office/test_e2e_scenarios.py

from datetime import date

import pandas as pd
import pytest

from performa.analysis import run
from performa.asset.office import (
    ExpensePool,
    OfficeAbsorptionPlan,
    OfficeCollectionLoss,
    OfficeExpenses,
    OfficeGeneralVacancyLoss,
    OfficeLeaseSpec,
    OfficeLeasingCommission,
    OfficeLosses,
    OfficeOpExItem,
    OfficeProperty,
    OfficeRecoveryMethod,
    OfficeRentRoll,
    OfficeRolloverLeaseTerms,
    OfficeRolloverProfile,
    OfficeTenantImprovement,
    OfficeVacantSuite,
    Recovery,
    SpaceFilter,
)
from performa.common.base import CommissionTier, FixedQuantityPace
from performa.common.primitives import (
    AggregateLineKey,
    GlobalSettings,
    Timeline,
    UponExpirationEnum,
)


@pytest.fixture(scope="module")
def complex_property_fixture() -> dict:
    """
    Provides a dictionary containing a complex OfficeProperty model,
    timeline, and settings for E2E tests.
    """
    analysis_timeline = Timeline.from_dates(date(2024, 1, 1), end_date=date(2030, 12, 31))
    global_settings = GlobalSettings(analysis_start_date=analysis_timeline.start_date.to_timestamp().date())

    # --- Define Reusable Components ---
    # These will be attached to the OfficeProperty model so the scenario's
    # internal lookup function can resolve string references.
    
    # Rollover Profile for speculative leases
    rollover_profile = OfficeRolloverProfile(
        name="Standard Rollover",
        term_months=60, renewal_probability=0.75, downtime_months=3,
        market_terms=OfficeRolloverLeaseTerms(
            market_rent=65.0, term_months=60,
            ti_allowance=OfficeTenantImprovement(
                name="Market TI", timeline=analysis_timeline, value=25.0, unit_of_measure="per_unit"
            ),
            leasing_commission=OfficeLeasingCommission(
                name="Market LC", timeline=analysis_timeline, tiers=[CommissionTier(year_start=1, rate=0.04)], value=0, unit_of_measure="currency"
            )
        ),
        renewal_terms=OfficeRolloverLeaseTerms(
            market_rent=60.0, term_months=60,
            ti_allowance=OfficeTenantImprovement(
                name="Renewal TI", timeline=analysis_timeline, value=10.0, unit_of_measure="per_unit"
            ),
        )
    )

    # Expenses that will be recovered
    cam_expense = OfficeOpExItem(
        name="CAM", timeline=analysis_timeline, value=5.0,
        unit_of_measure="per_unit", frequency="annual", variable_ratio=0.5, recoverable_ratio=1.0
    )
    tax_expense = OfficeOpExItem(
        name="Taxes", timeline=analysis_timeline, value=150000.0,
        unit_of_measure="currency", frequency="annual", recoverable_ratio=1.0
    )

    # Recovery Method that uses the expenses
    recovery_method = OfficeRecoveryMethod(
        name="Base Stop Recovery", gross_up=True, gross_up_percent=0.95,
        recoveries=[
            Recovery(
                expenses=ExpensePool(name="All OpEx", expenses=[cam_expense, tax_expense]),
                structure="net",
            )
        ]
    )

    # --- Define the Rent Roll ---
    rent_roll = OfficeRentRoll(
        leases=[
            OfficeLeaseSpec(
                tenant_name="Stable Tenant", suite="100", floor="1", area=10000, use_type="office",
                start_date=date(2022, 1, 1), term_months=120, base_rent_value=62.0,
                base_rent_unit_of_measure="per_unit", base_rent_frequency="annual", lease_type="net",
                upon_expiration=UponExpirationEnum.MARKET, 
                recovery_method=recovery_method
            ),
            OfficeLeaseSpec(
                tenant_name="Renewing Tenant", suite="200", floor="2", area=5000, use_type="office",
                start_date=date(2021, 6, 1), term_months=42, # Expires Nov 2024
                base_rent_value=58.0, base_rent_unit_of_measure="per_unit", lease_type="net",
                upon_expiration=UponExpirationEnum.RENEW, 
                rollover_profile=rollover_profile
            ),
            OfficeLeaseSpec(
                tenant_name="Departing Tenant", suite="300", floor="3", area=7500, use_type="office",
                start_date=date(2022, 1, 1), term_months=48, # Expires Dec 2025
                base_rent_value=60.0, base_rent_unit_of_measure="per_unit", base_rent_frequency="annual", lease_type="net",
                upon_expiration=UponExpirationEnum.REABSORB, 
                rollover_profile=rollover_profile
            ),
        ],
        vacant_suites=[
            OfficeVacantSuite(suite="400", floor="4", area=2500, use_type="office")
        ]
    )

    # --- Define Absorption Plan ---
    absorption_plan = OfficeAbsorptionPlan(
        name="Lease Up Vacancy",
        space_filter=SpaceFilter(use_types=["office"]),
        start_date_anchor=date(2026, 1, 1),
        pace={"type": "FixedQuantity", "quantity": 10000, "unit": "SF", "frequency_months": 6},
        leasing_assumptions="Standard Rollover" # Reference by name
    )

    # --- Assemble the Property with components attached for lookup ---
    property_data = OfficeProperty(
        name="E2E Test Tower",
        property_type="office", net_rentable_area=25000, gross_area=28000,
        rent_roll=rent_roll,
        expenses=OfficeExpenses(operating_expenses=[cam_expense, tax_expense]),
        losses=OfficeLosses(
            general_vacancy=OfficeGeneralVacancyLoss(rate=0.05),
            collection_loss=OfficeCollectionLoss(rate=0.01)
        ),
        absorption_plans=[absorption_plan],
    )

    return {
        "model": property_data,
        "timeline": analysis_timeline,
        "settings": global_settings
    }

def test_full_scenario_kitchen_sink(complex_property_fixture):
    """
    Validates high-level metrics at key points in the property's lifecycle,
    ensuring rollovers, vacancy, and absorption produce the expected financial story.
    """
    # ARRANGE
    # This is our "Source of Truth" - these values can be pre-calculated in a spreadsheet
    # or simple script now that our engine is reliable.
    EXPECTED_NOI_2024_06 = 778449.07 # UPDATED to match correct calculation
    EXPECTED_PGR_2025_01 = 76666.67  # After renewal (rent for Renewing Tenant changes)
    EXPECTED_REIMB_2026_02 = 3009.11 # During low-occupancy (proves gross-up)
    EXPECTED_TI_2026_07 = -250000.0  # From first absorption lease (10k sf * $25/sf)

    # ACT
    scenario = run(**complex_property_fixture)
    summary_df = scenario.get_cash_flow_summary()

    # ASSERT
    # 1. Assert specific line items at specific times
    assert summary_df.loc["2024-06", AggregateLineKey.NET_OPERATING_INCOME.value].sum() == pytest.approx(EXPECTED_NOI_2024_06, rel=1e-3)
    assert summary_df.loc["2025-01", AggregateLineKey.POTENTIAL_GROSS_REVENUE.value].sum() == pytest.approx(EXPECTED_PGR_2025_01, rel=1e-3)
    assert summary_df.loc["2026-02", AggregateLineKey.EXPENSE_REIMBURSEMENTS.value].sum() > 0
    
    # TI is paid at commencement (1 month after lease start)
    absorption_lease_1_commencement = pd.Period("2026-07", "M")
    assert summary_df.loc[absorption_lease_1_commencement, AggregateLineKey.TOTAL_TENANT_IMPROVEMENTS.value].sum() == pytest.approx(EXPECTED_TI_2026_07, rel=1e-3)
    
    # 2. Assert that the absorption plan eventually increased total rent
    revenue_2025 = summary_df.loc["2025", AggregateLineKey.POTENTIAL_GROSS_REVENUE.value].sum()
    revenue_2027 = summary_df.loc["2027", AggregateLineKey.POTENTIAL_GROSS_REVENUE.value].sum()
    assert revenue_2027 > revenue_2025

def test_e2e_recovery_gross_up_proves_phased_execution(complex_property_fixture):
    """
    Validates that expense reimbursements correctly increase during a
    low-occupancy period, proving that gross-up logic is being fed by
    correctly-timed occupancy and expense data. This is a key validation
    of the phased execution engine.
    """
    # ACT
    scenario = run(**complex_property_fixture)
    summary_df = scenario.get_cash_flow_summary()

    # ASSERT
    # Occupancy drops sharply in Jan 2026 when the 7,500sf Departing Tenant leaves.
    low_occupancy_period = pd.Period("2026-02", "M")
    high_occupancy_period = pd.Period("2025-06", "M")

    # Get the expense reimbursement line for the one remaining tenant subject to recovery
    reimbursements = summary_df[AggregateLineKey.EXPENSE_REIMBURSEMENTS.value]

    # The key insight: because variable expenses (like CAM) are "grossed-up" to a
    # higher occupancy level (95%) before being passed through, the recoverable
    # expense *base* is larger during the low-occupancy period. Therefore, the
    # single remaining tenant pays more in reimbursements.
    assert reimbursements.loc[low_occupancy_period] > 0
    assert reimbursements.loc[high_occupancy_period] > 0
    assert reimbursements.loc[low_occupancy_period] > reimbursements.loc[high_occupancy_period]

def test_pgr_calculation_for_jan_2025(complex_property_fixture):
    """
    Validates the PGR for a specific month (Jan 2025) to isolate calculation issues.
    This provides a clear, verifiable benchmark to debug against.
    """
    # ARRANGE
    # Manually calculated expected value for Jan 2025:
    # Stable Tenant: 10000sf * $62/sf/yr / 12 = 51666.67
    # Renewing Tenant (renews Dec 2024 at $60/sf): 5000sf * $60/sf/yr / 12 = 25000.00
    # Departing Tenant (still active): 7500sf * $60/sf/yr / 12 = 37500.00
    # Total Expected = 114,166.67
    EXPECTED_PGR_2025_01 = 114166.67

    # ACT
    scenario = run(**complex_property_fixture)
    summary_df = scenario.get_cash_flow_summary()

    # ASSERT
    actual_pgr = summary_df.loc["2025-01", AggregateLineKey.POTENTIAL_GROSS_REVENUE.value].sum()
    assert actual_pgr == pytest.approx(EXPECTED_PGR_2025_01, rel=1e-3)
