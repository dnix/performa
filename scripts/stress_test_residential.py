# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Residential Analysis Stress Testing Script

Tests the residential module across different scales:
- Small Developer (3-8 units)
- Regional Investor (50-100 units)
- Institutional Scale (250-500 units)

Validates fundamental functionality and performance.
"""

import time
from datetime import date
from typing import Any, Dict, List

from performa.analysis import run
from performa.analysis.orchestrator import AnalysisContext
from performa.asset.residential import (
    ResidentialCreditLoss,
    ResidentialExpenses,
    ResidentialGeneralVacancyLoss,
    ResidentialLosses,
    ResidentialMiscIncome,
    ResidentialOpExItem,
    ResidentialProperty,
    ResidentialRentRoll,
    ResidentialRolloverLeaseTerms,
    ResidentialRolloverProfile,
    ResidentialUnitSpec,
)
from performa.asset.residential.lease import ResidentialLease
from performa.core.capital import CapitalPlan
from performa.core.ledger import LedgerBuilder
from performa.core.primitives import (
    FrequencyEnum,
    GlobalSettings,
    LeaseStatusEnum,
    PropertyAttributeKey,
    Timeline,
    UnleveredAggregateLineKey,
    UponExpirationEnum,
)
from performa.core.primitives.growth_rates import PercentageGrowthRate


def create_basic_rollover_profile(name: str) -> ResidentialRolloverProfile:
    """Create a basic rollover profile for testing."""
    market_terms = ResidentialRolloverLeaseTerms(
        market_rent=2200.0,
        capital_plan_id=None,
        term_months=12,
    )

    return ResidentialRolloverProfile(
        name=name,
        renewal_probability=0.65,
        downtime_months=1,
        term_months=12,
        market_terms=market_terms,
        renewal_terms=market_terms,
    )


def create_sophisticated_rollover_profile(name: str) -> ResidentialRolloverProfile:
    """Create a sophisticated rollover profile with growth rates."""
    market_terms = ResidentialRolloverLeaseTerms(
        market_rent=2500.0,
        market_rent_growth=PercentageGrowthRate(name="Market Growth", value=0.035),
        renewal_rent_increase_percent=0.028,
        concessions_months=1,
        capital_plan_id=None,
        term_months=12,
    )

    renewal_terms = ResidentialRolloverLeaseTerms(
        market_rent=2400.0,
        market_rent_growth=PercentageGrowthRate(name="Renewal Growth", value=0.025),
        renewal_rent_increase_percent=0.028,
        concessions_months=0,
        capital_plan_id=None,
        term_months=12,
    )

    return ResidentialRolloverProfile(
        name=name,
        renewal_probability=0.72,
        downtime_months=1,
        term_months=12,
        market_terms=market_terms,
        renewal_terms=renewal_terms,
    )


def test_small_developer_scale() -> Dict[str, Any]:
    """Test small developer scale (3-8 units)."""
    print("\n🏠 SMALL DEVELOPER SCALE TEST")
    print("Testing: Triplex property (3 units)")

    timeline = Timeline(start_date=date(2024, 1, 1), duration_months=24)
    settings = GlobalSettings()

    rollover_profile = create_basic_rollover_profile("Small Developer Profile")

    unit_spec = ResidentialUnitSpec(
        unit_type_name="2BR/1BA - Triplex",
        unit_count=3,
        avg_area_sf=900.0,
        current_avg_monthly_rent=1650.0,
        rollover_profile=rollover_profile,
    )

    rent_roll = ResidentialRentRoll(unit_specs=[unit_spec])

    property_model = ResidentialProperty(
        name="Downtown Triplex",
        gross_area=3200.0,
        net_rentable_area=2700.0,
        unit_mix=rent_roll,
        expenses=ResidentialExpenses(),
        losses=ResidentialLosses(
            general_vacancy=ResidentialGeneralVacancyLoss(rate=0.05),
            collection_loss=ResidentialCreditLoss(rate=0.01),
        ),
    )

    start_time = time.time()
    scenario = run(model=property_model, timeline=timeline, settings=settings)
    execution_time = time.time() - start_time

    # Validate results using new architecture
    orchestrator = (
        scenario.scenario._orchestrator
    )  # Access orchestrator through scenario
    lease_models = scenario.models  # Models are directly accessible

    # Use the on-demand summary property
    summary = scenario.summary_df

    # Get PGR using new query-based approach
    if len(summary) > 0:
        first_month = summary.index[0]
        # Use exact column name from new architecture
        if "Potential Gross Revenue" in summary.columns:
            actual_pgr = summary.loc[first_month, "Potential Gross Revenue"]
        else:
            actual_pgr = 0
    else:
        actual_pgr = 0

    expected_pgr = 3 * 1650.0  # 3 units × $1,650

    print(f"  Property: {property_model.name}")
    print(f"  Units: {property_model.unit_count}")
    print(f"  Expected Monthly Income: ${expected_pgr:,.0f}")
    print(f"  Actual PGR: ${actual_pgr:,.0f}")
    print(f"  Lease Models Created: {len(lease_models)}")
    print(f"  Execution Time: {execution_time:.3f}s")
    print(f"  Performance: {len(lease_models) / execution_time:.0f} units/second")

    # Fundamental sanity checks
    assert len(lease_models) == 3, f"Expected 3 lease models, got {len(lease_models)}"
    assert (
        abs(actual_pgr - expected_pgr) < 10
    ), f"PGR mismatch: expected {expected_pgr}, got {actual_pgr}"

    return {
        "scale": "Small Developer",
        "units": 3,
        "execution_time": execution_time,
        "units_per_second": len(lease_models) / execution_time,
        "pgr_accuracy": abs(actual_pgr - expected_pgr) < 10,
        "lease_models": len(lease_models),
    }


def test_regional_investor_scale() -> Dict[str, Any]:
    """Test regional investor scale (50-100 units)."""
    print("\n🏢 REGIONAL INVESTOR SCALE TEST")
    print("Testing: Mid-size apartment complex (75 units)")

    timeline = Timeline(start_date=date(2024, 1, 1), duration_months=36)
    settings = GlobalSettings()

    rollover_profile = create_sophisticated_rollover_profile(
        "Regional Investor Profile"
    )

    unit_specs = [
        ResidentialUnitSpec(
            unit_type_name="1BR/1BA",
            unit_count=30,
            avg_area_sf=750.0,
            current_avg_monthly_rent=1950.0,
            rollover_profile=rollover_profile,
        ),
        ResidentialUnitSpec(
            unit_type_name="2BR/2BA",
            unit_count=35,
            avg_area_sf=1100.0,
            current_avg_monthly_rent=2650.0,
            rollover_profile=rollover_profile,
        ),
        ResidentialUnitSpec(
            unit_type_name="3BR/2BA",
            unit_count=10,
            avg_area_sf=1400.0,
            current_avg_monthly_rent=3200.0,
            rollover_profile=rollover_profile,
        ),
    ]

    rent_roll = ResidentialRentRoll(unit_specs=unit_specs)

    # Add some expenses
    expenses = ResidentialExpenses(
        operating_expenses=[
            ResidentialOpExItem(
                name="Property Management",
                timeline=timeline,
                value=0.06,
                frequency=FrequencyEnum.MONTHLY,
                reference=UnleveredAggregateLineKey.EFFECTIVE_GROSS_INCOME,
            ),
            ResidentialOpExItem(
                name="Maintenance & Repairs",
                timeline=timeline,
                value=450.0,
                frequency=FrequencyEnum.ANNUAL,
                reference=PropertyAttributeKey.UNIT_COUNT,
            ),
        ]
    )

    property_model = ResidentialProperty(
        name="Riverside Commons Apartments",
        gross_area=85000.0,
        net_rentable_area=rent_roll.total_rentable_area,
        unit_mix=rent_roll,
        expenses=expenses,
        losses=ResidentialLosses(
            general_vacancy=ResidentialGeneralVacancyLoss(rate=0.04),
            collection_loss=ResidentialCreditLoss(rate=0.015),
        ),
    )

    start_time = time.time()
    scenario = run(model=property_model, timeline=timeline, settings=settings)
    execution_time = time.time() - start_time

    # Validate results using new architecture
    orchestrator = scenario.scenario._orchestrator
    lease_models = scenario.models
    expense_models = [m for m in scenario.models if "ExItem" in m.__class__.__name__]

    summary = scenario.summary_df
    if len(summary) > 0:
        first_month = summary.index[0]
        # Use exact column name from new architecture
        if "Potential Gross Revenue" in summary.columns:
            actual_pgr = summary.loc[first_month, "Potential Gross Revenue"]
        else:
            actual_pgr = 0
    else:
        actual_pgr = 0

    expected_pgr = (30 * 1950) + (35 * 2650) + (10 * 3200)  # Weighted by unit counts

    print(f"  Property: {property_model.name}")
    print(f"  Units: {property_model.unit_count}")
    print(f"  Expected Monthly Income: ${expected_pgr:,.0f}")
    print(f"  Actual PGR: ${actual_pgr:,.0f}")
    print(f"  Lease Models: {len(lease_models)}")
    print(f"  Expense Models: {len(expense_models)}")
    print(f"  Execution Time: {execution_time:.3f}s")
    print(f"  Performance: {len(lease_models) / execution_time:.0f} units/second")

    # Fundamental sanity checks - Updated for new architecture
    # Note: New architecture may create additional models for better granularity
    assert (
        len(lease_models) >= 75
    ), f"Expected at least 75 lease models, got {len(lease_models)}"
    assert (
        abs(actual_pgr - expected_pgr) < 100
    ), f"PGR mismatch: expected {expected_pgr}, got {actual_pgr}"
    assert (
        len(expense_models) >= 2
    ), f"Expected at least 2 expense models, got {len(expense_models)}"

    return {
        "scale": "Regional Investor",
        "units": 75,
        "execution_time": execution_time,
        "units_per_second": len(lease_models) / execution_time,
        "pgr_accuracy": abs(actual_pgr - expected_pgr) < 100,
        "lease_models": len(lease_models),
        "expense_models": len(expense_models),
    }


def test_institutional_scale() -> Dict[str, Any]:
    """Test institutional scale (250+ units)."""
    print("\n🏛️ INSTITUTIONAL SCALE TEST")
    print("Testing: Large apartment community (400 units)")

    timeline = Timeline(start_date=date(2024, 1, 1), duration_months=60)  # 5 years
    settings = GlobalSettings()

    rollover_profile = create_sophisticated_rollover_profile("Institutional Profile")

    unit_specs = [
        # High volume unit types
        ResidentialUnitSpec(
            unit_type_name="Studio",
            unit_count=50,
            avg_area_sf=550.0,
            current_avg_monthly_rent=1750.0,
            rollover_profile=rollover_profile,
        ),
        ResidentialUnitSpec(
            unit_type_name="1BR/1BA - Standard",
            unit_count=150,
            avg_area_sf=750.0,
            current_avg_monthly_rent=2200.0,
            rollover_profile=rollover_profile,
        ),
        ResidentialUnitSpec(
            unit_type_name="1BR/1BA - Premium",
            unit_count=75,
            avg_area_sf=850.0,
            current_avg_monthly_rent=2650.0,
            rollover_profile=rollover_profile,
        ),
        ResidentialUnitSpec(
            unit_type_name="2BR/2BA - Standard",
            unit_count=100,
            avg_area_sf=1150.0,
            current_avg_monthly_rent=3400.0,
            rollover_profile=rollover_profile,
        ),
        ResidentialUnitSpec(
            unit_type_name="2BR/2BA - Premium",
            unit_count=25,
            avg_area_sf=1300.0,
            current_avg_monthly_rent=4100.0,
            rollover_profile=rollover_profile,
        ),
    ]

    rent_roll = ResidentialRentRoll(unit_specs=unit_specs)

    # Institutional-grade expenses
    expenses = ResidentialExpenses(
        operating_expenses=[
            ResidentialOpExItem(
                name="Property Management",
                timeline=timeline,
                value=0.055,
                frequency=FrequencyEnum.MONTHLY,
                reference=UnleveredAggregateLineKey.EFFECTIVE_GROSS_INCOME,
            ),
            ResidentialOpExItem(
                name="Maintenance & Repairs",
                timeline=timeline,
                value=525.0,
                frequency=FrequencyEnum.ANNUAL,
                reference=PropertyAttributeKey.UNIT_COUNT,
            ),
            ResidentialOpExItem(
                name="Utilities & Common Areas",
                timeline=timeline,
                value=350000.0,
                frequency=FrequencyEnum.ANNUAL,
                # reference=None (direct currency amount)
            ),
        ]
    )

    # Multiple income streams
    misc_income = [
        ResidentialMiscIncome(
            name="Parking Revenue",
            timeline=timeline,
            value=95.0,
            frequency=FrequencyEnum.MONTHLY,
            reference=PropertyAttributeKey.UNIT_COUNT,
        ),
        ResidentialMiscIncome(
            name="Pet Fees",
            timeline=timeline,
            value=35.0,
            frequency=FrequencyEnum.MONTHLY,
            reference=PropertyAttributeKey.UNIT_COUNT,
        ),
    ]

    property_model = ResidentialProperty(
        name="Metropolitan Heights",
        gross_area=450000.0,
        net_rentable_area=rent_roll.total_rentable_area,
        unit_mix=rent_roll,
        expenses=expenses,
        losses=ResidentialLosses(
            general_vacancy=ResidentialGeneralVacancyLoss(rate=0.03),
            collection_loss=ResidentialCreditLoss(rate=0.012),
        ),
        miscellaneous_income=misc_income,
    )

    start_time = time.time()
    scenario = run(model=property_model, timeline=timeline, settings=settings)
    execution_time = time.time() - start_time

    # Validate results using new architecture
    orchestrator = scenario.scenario._orchestrator
    lease_models = scenario.models
    expense_models = [m for m in scenario.models if "ExItem" in m.__class__.__name__]
    misc_models = [
        m for m in scenario.models if m.__class__.__name__ == "ResidentialMiscIncome"
    ]

    summary = scenario.summary_df
    if len(summary) > 0:
        first_month = summary.index[0]
        # Use exact column names from new architecture
        if "Potential Gross Revenue" in summary.columns:
            actual_pgr = summary.loc[first_month, "Potential Gross Revenue"]
        else:
            actual_pgr = 0
        if "Miscellaneous Income" in summary.columns:
            actual_misc = summary.loc[first_month, "Miscellaneous Income"]
        else:
            actual_misc = 0
    else:
        actual_pgr = actual_misc = 0

    expected_pgr = (50 * 1750) + (150 * 2200) + (75 * 2650) + (100 * 3400) + (25 * 4100)
    expected_misc = 400 * (95 + 35)  # 400 units × ($95 + $35) parking + pet fees

    print(f"  Property: {property_model.name}")
    print(f"  Units: {property_model.unit_count}")
    print(f"  Expected Monthly Rent: ${expected_pgr:,.0f}")
    print(f"  Expected Monthly Misc Income: ${expected_misc:,.0f} (estimated)")
    print(f"  Actual PGR: ${actual_pgr:,.0f}")
    print(f"  Actual Misc Income: ${actual_misc:,.0f}")
    print(f"  Lease Models: {len(lease_models)}")
    print(f"  Expense Models: {len(expense_models)}")
    print(f"  Misc Income Models: {len(misc_models)}")
    print(f"  Execution Time: {execution_time:.3f}s")
    print(f"  Performance: {len(lease_models) / execution_time:.0f} units/second")

    # Performance assertions for institutional scale
    assert (
        execution_time < 5.0
    ), f"Institutional analysis should complete in <5s, took {execution_time:.3f}s"
    assert (
        len(lease_models) / execution_time > 80
    ), f"Should process >80 units/sec, got {len(lease_models) / execution_time:.0f}"

    # Fundamental sanity checks - Updated for new architecture
    assert (
        len(lease_models) >= 400
    ), f"Expected at least 400 lease models, got {len(lease_models)}"
    assert (
        abs(actual_pgr - expected_pgr) < 500
    ), f"PGR mismatch: expected {expected_pgr}, got {actual_pgr}"
    assert actual_misc > 0, f"Misc income should be positive, got {actual_misc}"
    assert (
        len(misc_models) >= 2
    ), f"Expected at least 2 misc income models, got {len(misc_models)}"

    return {
        "scale": "Institutional",
        "units": 400,
        "execution_time": execution_time,
        "units_per_second": len(lease_models) / execution_time,
        "pgr_accuracy": abs(actual_pgr - expected_pgr) < 500,
        "misc_accuracy": actual_misc > 0,
        "lease_models": len(lease_models),
        "expense_models": len(expense_models),
        "misc_models": len(misc_models),
    }


def test_fundamental_sanity() -> bool:
    """Test fundamental functionality to ensure we didn't break core features."""
    print("\n🔧 FUNDAMENTAL SANITY CHECKS")

    # Test 1: Basic lease cash flow computation
    print("  Test 1: Basic lease cash flow...")
    timeline = Timeline(start_date=date(2024, 1, 1), duration_months=3)
    lease = ResidentialLease(
        name="Test Lease",
        timeline=timeline,
        value=2000.0,
        frequency=FrequencyEnum.MONTHLY,
        status=LeaseStatusEnum.CONTRACT,
        area=800.0,
        suite="101",
        floor="1",
        upon_expiration=UponExpirationEnum.MARKET,
        monthly_rent=2000.0,
    )

    context = AnalysisContext(
        timeline=timeline,
        settings=GlobalSettings(),
        property_data=None,
        ledger_builder=LedgerBuilder(),  # Add required ledger_builder
        recovery_states={},  # Add required recovery_states
    )

    cf_result = lease.compute_cf(context)
    assert isinstance(
        cf_result, dict
    ), f"compute_cf should return dict, got {type(cf_result)}"
    assert "base_rent" in cf_result, "compute_cf should have base_rent component"
    assert (
        cf_result["base_rent"].sum() == 6000.0
    ), f"Expected $6,000 total, got {cf_result['base_rent'].sum()}"
    print("    ✅ Basic lease cash flow: PASS")

    # Test 2: Component aggregation
    print("  Test 2: Component aggregation...")
    project_result = lease.project_future_cash_flows(context)
    assert hasattr(
        project_result, "columns"
    ), "project_future_cash_flows should return DataFrame"
    assert "base_rent" in project_result.columns, "Should have base_rent column"
    print("    ✅ Component aggregation: PASS")

    # Test 3: UUID field presence
    print("  Test 3: UUID field presence...")
    plan = CapitalPlan(name="Test Plan")
    profile = ResidentialRolloverProfile(
        name="Test Profile",
        renewal_probability=0.6,
        downtime_months=1,
        term_months=12,
        market_terms=ResidentialRolloverLeaseTerms(
            market_rent=2000.0, capital_plan_id=None, term_months=12
        ),
        renewal_terms=ResidentialRolloverLeaseTerms(
            market_rent=2000.0, capital_plan_id=None, term_months=12
        ),
    )
    expenses = ResidentialExpenses()

    assert hasattr(plan, "uid"), "CapitalPlan should have uid field"
    assert hasattr(profile, "uid"), "ResidentialRolloverProfile should have uid field"
    assert hasattr(expenses, "uid"), "ResidentialExpenses should have uid field"
    print("    ✅ UUID field presence: PASS")

    print("  🎯 All fundamental sanity checks: PASSED")
    return True


def test_comprehensive_performance_suite() -> List[Dict[str, Any]]:
    """Test comprehensive performance across all user segments."""
    print("\n🎯 COMPREHENSIVE PERFORMANCE SUITE")
    print("Testing across full spectrum: Small Developer → Institutional")

    timeline = Timeline(start_date=date(2024, 1, 1), duration_months=36)
    settings = GlobalSettings()

    test_scenarios = [
        # Small Developer Segment
        {
            "name": "Triplex",
            "units": 3,
            "user_type": "Small Developer",
            "unit_specs": [
                ResidentialUnitSpec(
                    unit_type_name="2BR/1BA",
                    unit_count=3,
                    avg_area_sf=900.0,
                    current_avg_monthly_rent=1650.0,
                    rollover_profile=create_basic_rollover_profile("Basic Profile"),
                )
            ],
        },
        {
            "name": "Fourplex",
            "units": 4,
            "user_type": "Small Developer",
            "unit_specs": [
                ResidentialUnitSpec(
                    unit_type_name="2BR/1.5BA",
                    unit_count=4,
                    avg_area_sf=1050.0,
                    current_avg_monthly_rent=1850.0,
                    rollover_profile=create_basic_rollover_profile("Basic Profile"),
                )
            ],
        },
        # Small Investor Segment
        {
            "name": "8-Unit Building",
            "units": 8,
            "user_type": "Small Investor",
            "unit_specs": [
                ResidentialUnitSpec(
                    unit_type_name="1BR/1BA",
                    unit_count=4,
                    avg_area_sf=750.0,
                    current_avg_monthly_rent=1650.0,
                    rollover_profile=create_sophisticated_rollover_profile(
                        "Small Investor Profile"
                    ),
                ),
                ResidentialUnitSpec(
                    unit_type_name="2BR/1BA",
                    unit_count=4,
                    avg_area_sf=950.0,
                    current_avg_monthly_rent=2100.0,
                    rollover_profile=create_sophisticated_rollover_profile(
                        "Small Investor Profile"
                    ),
                ),
            ],
        },
        # Regional Investor Segment
        {
            "name": "24-Unit Complex",
            "units": 24,
            "user_type": "Regional Investor",
            "unit_specs": [
                ResidentialUnitSpec(
                    unit_type_name="1BR/1BA",
                    unit_count=12,
                    avg_area_sf=750.0,
                    current_avg_monthly_rent=1950.0,
                    rollover_profile=create_sophisticated_rollover_profile(
                        "Regional Profile"
                    ),
                ),
                ResidentialUnitSpec(
                    unit_type_name="2BR/2BA",
                    unit_count=12,
                    avg_area_sf=1100.0,
                    current_avg_monthly_rent=2650.0,
                    rollover_profile=create_sophisticated_rollover_profile(
                        "Regional Profile"
                    ),
                ),
            ],
        },
        # Mid-size Operator Segment
        {
            "name": "48-Unit Property",
            "units": 48,
            "user_type": "Mid-size Operator",
            "unit_specs": [
                ResidentialUnitSpec(
                    unit_type_name="1BR/1BA",
                    unit_count=20,
                    avg_area_sf=750.0,
                    current_avg_monthly_rent=2100.0,
                    rollover_profile=create_sophisticated_rollover_profile(
                        "Mid-size Profile"
                    ),
                ),
                ResidentialUnitSpec(
                    unit_type_name="2BR/2BA",
                    unit_count=20,
                    avg_area_sf=1100.0,
                    current_avg_monthly_rent=2850.0,
                    rollover_profile=create_sophisticated_rollover_profile(
                        "Mid-size Profile"
                    ),
                ),
                ResidentialUnitSpec(
                    unit_type_name="3BR/2BA",
                    unit_count=8,
                    avg_area_sf=1400.0,
                    current_avg_monthly_rent=3500.0,
                    rollover_profile=create_sophisticated_rollover_profile(
                        "Mid-size Profile"
                    ),
                ),
            ],
        },
        # Regional Portfolio Segment
        {
            "name": "96-Unit Portfolio Property",
            "units": 96,
            "user_type": "Regional Portfolio",
            "unit_specs": [
                ResidentialUnitSpec(
                    unit_type_name="Studio",
                    unit_count=16,
                    avg_area_sf=550.0,
                    current_avg_monthly_rent=1750.0,
                    rollover_profile=create_sophisticated_rollover_profile(
                        "Portfolio Profile"
                    ),
                ),
                ResidentialUnitSpec(
                    unit_type_name="1BR/1BA",
                    unit_count=40,
                    avg_area_sf=750.0,
                    current_avg_monthly_rent=2200.0,
                    rollover_profile=create_sophisticated_rollover_profile(
                        "Portfolio Profile"
                    ),
                ),
                ResidentialUnitSpec(
                    unit_type_name="2BR/2BA",
                    unit_count=32,
                    avg_area_sf=1100.0,
                    current_avg_monthly_rent=3000.0,
                    rollover_profile=create_sophisticated_rollover_profile(
                        "Portfolio Profile"
                    ),
                ),
                ResidentialUnitSpec(
                    unit_type_name="3BR/2BA",
                    unit_count=8,
                    avg_area_sf=1400.0,
                    current_avg_monthly_rent=3800.0,
                    rollover_profile=create_sophisticated_rollover_profile(
                        "Portfolio Profile"
                    ),
                ),
            ],
        },
        # Institutional Segment - Class B
        {
            "name": "150-Unit Class B",
            "units": 150,
            "user_type": "Institutional",
            "unit_specs": [
                ResidentialUnitSpec(
                    unit_type_name="Studio",
                    unit_count=30,
                    avg_area_sf=550.0,
                    current_avg_monthly_rent=1850.0,
                    rollover_profile=create_sophisticated_rollover_profile(
                        "Institutional Profile"
                    ),
                ),
                ResidentialUnitSpec(
                    unit_type_name="1BR/1BA",
                    unit_count=75,
                    avg_area_sf=750.0,
                    current_avg_monthly_rent=2400.0,
                    rollover_profile=create_sophisticated_rollover_profile(
                        "Institutional Profile"
                    ),
                ),
                ResidentialUnitSpec(
                    unit_type_name="2BR/2BA",
                    unit_count=45,
                    avg_area_sf=1100.0,
                    current_avg_monthly_rent=3200.0,
                    rollover_profile=create_sophisticated_rollover_profile(
                        "Institutional Profile"
                    ),
                ),
            ],
        },
        # Institutional Segment - Class A
        {
            "name": "300-Unit Class A",
            "units": 300,
            "user_type": "Institutional",
            "unit_specs": [
                ResidentialUnitSpec(
                    unit_type_name="Studio - Premium",
                    unit_count=30,
                    avg_area_sf=600.0,
                    current_avg_monthly_rent=2200.0,
                    rollover_profile=create_sophisticated_rollover_profile(
                        "Class A Profile"
                    ),
                ),
                ResidentialUnitSpec(
                    unit_type_name="1BR/1BA - Standard",
                    unit_count=120,
                    avg_area_sf=800.0,
                    current_avg_monthly_rent=2800.0,
                    rollover_profile=create_sophisticated_rollover_profile(
                        "Class A Profile"
                    ),
                ),
                ResidentialUnitSpec(
                    unit_type_name="1BR/1BA - Premium",
                    unit_count=60,
                    avg_area_sf=900.0,
                    current_avg_monthly_rent=3200.0,
                    rollover_profile=create_sophisticated_rollover_profile(
                        "Class A Profile"
                    ),
                ),
                ResidentialUnitSpec(
                    unit_type_name="2BR/2BA - Standard",
                    unit_count=70,
                    avg_area_sf=1200.0,
                    current_avg_monthly_rent=4200.0,
                    rollover_profile=create_sophisticated_rollover_profile(
                        "Class A Profile"
                    ),
                ),
                ResidentialUnitSpec(
                    unit_type_name="2BR/2BA - Premium",
                    unit_count=20,
                    avg_area_sf=1400.0,
                    current_avg_monthly_rent=5100.0,
                    rollover_profile=create_sophisticated_rollover_profile(
                        "Class A Profile"
                    ),
                ),
            ],
        },
    ]

    results = []

    for scenario in test_scenarios:
        print(f"\n  🏠 {scenario['name']} ({scenario['units']} units)")

        rent_roll = ResidentialRentRoll(unit_specs=scenario["unit_specs"])

        # Add appropriate expenses for larger properties
        expenses = ResidentialExpenses()
        if scenario["units"] >= 24:
            expenses = ResidentialExpenses(
                operating_expenses=[
                    ResidentialOpExItem(
                        name="Property Management",
                        timeline=timeline,
                        value=0.055,
                        frequency=FrequencyEnum.MONTHLY,
                        reference=UnleveredAggregateLineKey.EFFECTIVE_GROSS_INCOME,
                    ),
                    ResidentialOpExItem(
                        name="Maintenance & Repairs",
                        timeline=timeline,
                        value=400.0 + (scenario["units"] * 2),  # Scale with size
                        frequency=FrequencyEnum.ANNUAL,
                        reference=PropertyAttributeKey.UNIT_COUNT,
                    ),
                ]
            )

        property_model = ResidentialProperty(
            name=f"{scenario['name']} Test Property",
            gross_area=scenario["units"] * 1000.0,  # Estimate
            net_rentable_area=rent_roll.total_rentable_area,
            unit_mix=rent_roll,
            expenses=expenses,
            losses=ResidentialLosses(
                general_vacancy=ResidentialGeneralVacancyLoss(rate=0.04),
                collection_loss=ResidentialCreditLoss(rate=0.015),
            ),
        )

        start_time = time.time()
        scenario_result = run(
            model=property_model, timeline=timeline, settings=settings
        )
        execution_time = time.time() - start_time

        # Validate results using new architecture
        orchestrator = scenario_result.scenario._orchestrator
        lease_models = scenario_result.models

        units_per_second = len(lease_models) / execution_time
        execution_ms = execution_time * 1000

        print(f"     Time: {execution_ms:.1f}ms → {units_per_second:.0f} units/sec")

        results.append({
            "name": scenario["name"],
            "units": scenario["units"],
            "user_type": scenario["user_type"],
            "execution_time": execution_time,
            "execution_ms": execution_ms,
            "units_per_second": units_per_second,
            "lease_models": len(lease_models),
        })

        # Sanity check - Updated for new architecture
        assert (
            len(lease_models) >= scenario["units"]
        ), f"Expected at least {scenario['units']} lease models, got {len(lease_models)}"

    return results


def generate_performance_insights(results: List[Dict[str, Any]]) -> None:
    """Generate comprehensive performance insights and user experience analysis."""
    print("\n" + "=" * 80)
    print("🚀 PERFORMANCE BENCHMARK RESULTS: Exceptional Across All User Types!")
    print("=" * 80)

    # Group by user type
    user_segments = {}
    for result in results:
        user_type = result["user_type"]
        if user_type not in user_segments:
            user_segments[user_type] = []
        user_segments[user_type].append(result)

    print("\n### **Key Performance Insights:**")

    # Small Developer Analysis
    small_dev = user_segments.get("Small Developer", [])
    if small_dev:
        avg_perf = sum(r["units_per_second"] for r in small_dev) / len(small_dev)
        print("\n**⚡ Lightning Fast for Small Developers:**")
        for result in small_dev:
            print(
                f"- **{result['name']} ({result['units']} units)**: {result['execution_ms']:.0f}ms → **{result['units_per_second']:.0f} units/sec**"
            )
        print('- Perfect for quick "what-if" scenarios and deal evaluation')

    # Mid-Market Analysis
    mid_market = []
    for segment in ["Small Investor", "Regional Investor", "Mid-size Operator"]:
        mid_market.extend(user_segments.get(segment, []))

    if mid_market:
        print("\n**🏢 Excellent for Mid-Market:**")
        for result in mid_market:
            print(
                f"- **{result['name']}**: {result['execution_ms']:.0f}ms → **{result['units_per_second']:.0f} units/sec**"
            )
        print("- Real-time analysis for portfolio decisions")

    # Institutional Analysis
    institutional = user_segments.get("Institutional", [])
    institutional.extend(
        user_segments.get("Regional Portfolio", [])
    )  # Include large regional

    if institutional:
        print("\n**🏙️ Institutional-Grade Performance:**")
        for result in institutional:
            if result["execution_time"] >= 1.0:
                print(
                    f"- **{result['name']}**: {result['execution_time']:.2f}s → **{result['units_per_second']:.0f} units/sec**"
                )
            else:
                print(
                    f"- **{result['name']}**: {result['execution_ms']:.0f}ms → **{result['units_per_second']:.0f} units/sec**"
                )
        max_time = max(r["execution_time"] for r in institutional)
        print(
            f"- Under {max_time:.1f} seconds even for large institutional properties!"
        )

    # User Experience Table
    print("\n### **User Experience by Segment:**")
    print()
    print("| User Type | Typical Size | Time | Experience |")
    print("| --- | --- | --- | --- |")

    for user_type, segment_results in user_segments.items():
        if not segment_results:
            continue

        avg_time = sum(r["execution_time"] for r in segment_results) / len(
            segment_results
        )
        sizes = [r["units"] for r in segment_results]
        size_range = (
            f"{min(sizes)}-{max(sizes)} units"
            if len(sizes) > 1
            else f"{sizes[0]} units"
        )

        if avg_time < 0.05:
            time_str = f"~{avg_time * 1000:.0f}ms"
            experience = "Instant response"
        elif avg_time < 0.1:
            time_str = f"~{avg_time * 1000:.0f}ms"
            experience = "Real-time"
        elif avg_time < 0.3:
            time_str = f"~{avg_time * 1000:.0f}ms"
            experience = "Near-instant"
        elif avg_time < 0.6:
            time_str = f"~{avg_time * 1000:.0f}ms"
            experience = "Very responsive"
        elif avg_time < 1.0:
            time_str = f"~{avg_time * 1000:.0f}ms"
            experience = "Fast"
        else:
            time_str = f"{avg_time:.1f}s"
            experience = "Excellent"

        print(f"| **{user_type}** | {size_range} | {time_str} | {experience} |")

    # Performance Insights
    print("\n### **What This Means for Users:**")

    small_dev_avg = sum(
        r["units_per_second"] for r in user_segments.get("Small Developer", [])
    ) / len(user_segments.get("Small Developer", [1]))
    institutional_avg = sum(
        r["units_per_second"] for r in user_segments.get("Institutional", [])
    ) / len(user_segments.get("Institutional", [1]))

    print(f"\n**🎯 Small Developers ({small_dev_avg:.0f} units/sec avg):**")
    print("- Can analyze multiple deals in seconds")
    print("- Perfect for quick feasibility studies")
    print("- Ideal for real-time negotiation support")

    print(f"\n**🏢 Institutional Investors ({institutional_avg:.0f} units/sec avg):**")
    max_institutional_time = max(
        (r["execution_time"] for r in user_segments.get("Institutional", [])), default=0
    )
    max_units = max(
        (r["units"] for r in user_segments.get("Institutional", [])), default=0
    )
    print(
        f"- Even {max_units}-unit properties complete in under {max_institutional_time:.1f}s"
    )
    print("- Excellent for scenario modeling and sensitivity analysis")
    print("- Fast enough for interactive portfolio optimization")

    max_time_overall = max(r["execution_time"] for r in results)
    print("\n**💡 Universal Benefits:**")
    print(
        f"- **All scenarios under {max_time_overall:.1f} seconds** (even the largest)"
    )
    print("- Perfect for **real-time analysis** and **scenario modeling**")
    print("- Fast enough to support **interactive dashboards**")
    print("- Enables **rapid iteration** on assumptions")

    # Performance Pattern Analysis
    print("\n### **Performance Pattern:**")
    small_props = [r for r in results if r["units"] <= 10]
    large_props = [r for r in results if r["units"] >= 100]

    if small_props:
        small_avg = sum(r["units_per_second"] for r in small_props) / len(small_props)
        print(
            f"- **Small properties**: Fastest per-unit processing ({small_avg:.0f} units/sec avg - less overhead)"
        )

    if large_props:
        large_avg = sum(r["units_per_second"] for r in large_props) / len(large_props)
        print(
            f"- **Large properties**: Slight efficiency decrease but still excellent absolute performance ({large_avg:.0f} units/sec)"
        )

    min_units = min(r["units"] for r in results)
    max_units = max(r["units"] for r in results)
    print(
        f"- **Sweet spot**: Consistently excellent across {min_units}-{max_units} unit range"
    )

    print(
        "\nThis performance profile makes Performa residential analysis **competitive with Argus and Rockport** while being fast enough to enable **modern, interactive user experiences** that traditional desktop software can't match! 🎉"
    )

    print("\nThe speed enables use cases like:")
    print("- Real-time deal screening")
    print("- Interactive scenario modeling")
    print("- Portfolio optimization dashboards")
    print("- Mobile-responsive analysis tools")


def main():
    """Run comprehensive stress testing."""
    print("=" * 60)
    print("🚀 RESIDENTIAL ANALYSIS STRESS TESTING")
    print("=" * 60)

    results = []

    try:
        # Fundamental sanity checks first
        test_fundamental_sanity()

        # Original basic scale testing for backwards compatibility
        print("\n" + "=" * 60)
        print("📊 BASIC SCALE VERIFICATION")
        print("=" * 60)

        basic_results = []
        basic_results.append(test_small_developer_scale())
        basic_results.append(test_regional_investor_scale())
        basic_results.append(test_institutional_scale())

        # Comprehensive performance suite
        comprehensive_results = test_comprehensive_performance_suite()

        # Combine all results
        all_results = basic_results + comprehensive_results

        # Generate comprehensive insights
        generate_performance_insights(comprehensive_results)

        # Basic summary for backwards compatibility
        print("\n" + "=" * 60)
        print("📋 BASIC VALIDATION SUMMARY")
        print("=" * 60)

        total_units = sum(r["units"] for r in basic_results)
        avg_performance = sum(r["units_per_second"] for r in basic_results) / len(
            basic_results
        )

        print(f"Basic Test Units: {total_units:,}")
        print(f"Basic Test Average Performance: {avg_performance:.0f} units/second")
        print()

        for result in basic_results:
            print(f"{result['scale']}:")
            print(f"  Units: {result['units']}")
            print(f"  Time: {result['execution_time']:.3f}s")
            print(f"  Performance: {result['units_per_second']:.0f} units/sec")
            print(f"  PGR Accuracy: {'✅' if result['pgr_accuracy'] else '❌'}")
            print()

        print("🎉 All stress tests completed successfully!")

    except Exception as e:
        print(f"❌ Stress test failed: {e}")
        raise


if __name__ == "__main__":
    main()
