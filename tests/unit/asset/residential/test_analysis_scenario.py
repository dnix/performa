# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Test suite for ResidentialAnalysisScenario - Step 1.5
======================================================

Tests the complete end-to-end analysis pipeline for residential properties.
Verifies the critical "unit mix unrolling" functionality and analysis execution.
"""

from datetime import date

import pytest

from performa.analysis import run
from performa.analysis.orchestrator import AnalysisContext
from performa.asset.residential import (
    ResidentialAnalysisScenario,
    ResidentialCreditLoss,
    ResidentialExpenses,
    ResidentialGeneralVacancyLoss,
    ResidentialLosses,
    ResidentialOpExItem,
    ResidentialProperty,
    ResidentialRentRoll,
    ResidentialRolloverLeaseTerms,
    ResidentialRolloverProfile,
    ResidentialUnitSpec,
)
from performa.core.ledger import Ledger
from performa.core.primitives import (
    CashFlowModel,
    FrequencyEnum,
    GlobalSettings,
    Timeline,
    UnleveredAggregateLineKey,
)
from performa.core.primitives.growth_rates import PercentageGrowthRate


@pytest.fixture
def analysis_timeline():
    """Create a 2-year analysis timeline for testing."""
    return Timeline(start_date=date(2024, 1, 1), duration_months=24)


@pytest.fixture
def global_settings():
    """Create global settings for testing."""
    return GlobalSettings()


@pytest.fixture
def sample_rollover_profile():
    """Create a sample rollover profile for testing."""
    rollover_terms = ResidentialRolloverLeaseTerms(
        market_rent=2000.0,
        market_rent_growth=PercentageGrowthRate(name="Market Growth", value=0.03),
        renewal_rent_increase_percent=0.025,
        concessions_months=0,
        # Capital planning now handled at property level
        term_months=12,
    )

    return ResidentialRolloverProfile(
        name="Test Rollover Profile",
        renewal_probability=0.70,
        downtime_months=1,
        term_months=12,
        market_terms=rollover_terms,
        renewal_terms=rollover_terms,
    )


@pytest.fixture
def sample_residential_property(analysis_timeline, sample_rollover_profile):
    """Create a sample residential property for testing."""
    # Simple 20-unit property with two unit types
    unit_specs = [
        ResidentialUnitSpec(
            unit_type_name="1BR/1BA",
            unit_count=12,
            avg_area_sf=700.0,
            current_avg_monthly_rent=1800.0,
            rollover_profile=sample_rollover_profile,
        ),
        ResidentialUnitSpec(
            unit_type_name="2BR/2BA",
            unit_count=8,
            avg_area_sf=1000.0,
            current_avg_monthly_rent=2400.0,
            rollover_profile=sample_rollover_profile,
        ),
    ]

    rent_roll = ResidentialRentRoll(unit_specs=unit_specs)

    expenses = ResidentialExpenses(
        operating_expenses=[
            ResidentialOpExItem(
                name="Property Management",
                timeline=analysis_timeline,
                value=0.05,  # 5% of revenue
                reference=UnleveredAggregateLineKey.EFFECTIVE_GROSS_INCOME,
                frequency=FrequencyEnum.MONTHLY,
            ),
        ]
    )

    losses = ResidentialLosses(
        general_vacancy=ResidentialGeneralVacancyLoss(rate=0.05),
        credit_loss=ResidentialCreditLoss(rate=0.0),  # 0% collection loss
    )

    return ResidentialProperty(
        name="Test Residential Property",
        gross_area=22000.0,
        net_rentable_area=rent_roll.total_rentable_area,
        unit_mix=rent_roll,
        expenses=expenses,
        losses=losses,
        miscellaneous_income=[],
    )


def test_analysis_scenario_registration(
    sample_residential_property, analysis_timeline, global_settings
):
    """Test that ResidentialAnalysisScenario is properly registered."""
    # Run analysis - this will automatically select ResidentialAnalysisScenario
    result = run(
        model=sample_residential_property,
        timeline=analysis_timeline,
        settings=global_settings,
    )

    # Verify the correct scenario type was selected
    assert isinstance(result.scenario, ResidentialAnalysisScenario)
    assert result.scenario.model is sample_residential_property
    # Also verify we have ledger and other new features
    assert result.ledger is not None
    assert result.noi is not None


def test_unit_mix_unrolling(
    sample_residential_property, analysis_timeline, global_settings
):
    """Test that unit mix is correctly unrolled into individual lease instances."""
    result = run(
        model=sample_residential_property,
        timeline=analysis_timeline,
        settings=global_settings,
    )

    # Can access models directly from result now
    assert result.models is not None
    assert len(result.models) > 0

    # Count different types of models
    lease_models = [
        m for m in result.models if m.__class__.__name__ == "ResidentialLease"
    ]
    expense_models = [m for m in result.models if "ExItem" in m.__class__.__name__]

    # Verify correct number of lease instances (one per unit)
    expected_lease_count = sample_residential_property.unit_count
    assert len(lease_models) == expected_lease_count, (
        f"Expected {expected_lease_count} lease models, got {len(lease_models)}"
    )

    # Verify we have expense models
    assert len(expense_models) > 0, "Should have expense models"

    # Check that leases have the correct unit mix linkages
    unit_1br_count = sum(1 for lease in lease_models if "1BR/1BA" in lease.suite)
    unit_2br_count = sum(1 for lease in lease_models if "2BR/2BA" in lease.suite)

    assert unit_1br_count == 12, f"Expected 12 1BR units, got {unit_1br_count}"
    assert unit_2br_count == 8, f"Expected 8 2BR units, got {unit_2br_count}"


def test_cash_flow_generation(
    sample_residential_property, analysis_timeline, global_settings
):
    """Test that cash flows are generated correctly."""
    result = run(
        model=sample_residential_property,
        timeline=analysis_timeline,
        settings=global_settings,
    )

    # Can access cash flows directly from result now
    summary_df = result.summary_df

    # Basic validation
    assert len(summary_df) == 24, "Should have 24 monthly periods"
    assert len(summary_df.columns) > 0, "Should have cash flow columns"

    # Check that first month has reasonable values
    first_month = summary_df.index[0]
    first_month_data = summary_df.loc[first_month]

    # Should have positive potential gross revenue
    pgr_col = "AggregateLineKey.POTENTIAL_GROSS_REVENUE"
    if pgr_col in first_month_data:
        pgr = first_month_data[pgr_col]
        expected_pgr = (12 * 1800) + (8 * 2400)  # 1BR + 2BR monthly income
        assert pgr == pytest.approx(expected_pgr, rel=0.01), (
            f"Expected PGR ~{expected_pgr}, got {pgr}"
        )


def test_analysis_scenario_properties(
    sample_residential_property, analysis_timeline, global_settings
):
    """Test that the analysis scenario has the expected properties and methods."""

    scenario = ResidentialAnalysisScenario(
        model=sample_residential_property,
        timeline=analysis_timeline,
        settings=global_settings,
        ledger=Ledger(),
    )

    context = AnalysisContext(
        timeline=analysis_timeline,
        settings=global_settings,
        property_data=sample_residential_property,
        ledger=Ledger(),  # Create new ledger, don't use scenario's
        capital_plan_lookup={},
        rollover_profile_lookup={},
    )

    # Test prepare_models method with context
    models = scenario.prepare_models(context)

    # Should return a list of CashFlowModel instances
    assert isinstance(models, list)
    assert len(models) > 0

    # Should have the expected number of total models
    expected_lease_count = sample_residential_property.unit_count  # 20 leases
    expected_expense_count = 1  # 1 operating expense item
    expected_total = expected_lease_count + expected_expense_count
    assert len(models) == expected_total, (
        f"Expected {expected_total} total models, got {len(models)}"
    )

    for model in models:
        assert isinstance(model, CashFlowModel), (
            f"Expected CashFlowModel, got {type(model)}"
        )


def test_minimal_property_analysis():
    """Test analysis with minimal property setup."""
    # Create minimal components
    timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)

    rollover_terms = ResidentialRolloverLeaseTerms(
        market_rent=1500.0,
        term_months=12,
    )

    rollover_profile = ResidentialRolloverProfile(
        name="Minimal Profile",
        renewal_probability=0.5,
        downtime_months=1,
        term_months=12,
        market_terms=rollover_terms,
        renewal_terms=rollover_terms,
    )

    unit_spec = ResidentialUnitSpec(
        unit_type_name="Studio",
        unit_count=5,
        avg_area_sf=500.0,
        current_avg_monthly_rent=1500.0,
        rollover_profile=rollover_profile,
    )

    rent_roll = ResidentialRentRoll(unit_specs=[unit_spec])

    # Minimal expenses and losses
    expenses = ResidentialExpenses()  # Empty
    losses = ResidentialLosses(
        general_vacancy=ResidentialGeneralVacancyLoss(rate=0.0),  # No vacancy
        credit_loss=ResidentialCreditLoss(rate=0.0),  # No collection loss
    )

    property_model = ResidentialProperty(
        name="Minimal Property",
        gross_area=2500.0,
        net_rentable_area=2500.0,
        unit_mix=rent_roll,
        expenses=expenses,
        losses=losses,
    )

    # Run analysis
    result = run(
        model=property_model,
        timeline=timeline,
        settings=GlobalSettings(),
    )

    # Should complete without errors
    assert isinstance(result.scenario, ResidentialAnalysisScenario)

    # Verify ledger was built
    assert result.ledger is not None
    assert not result.ledger.ledger_df().empty

    # Should unroll to 5 lease instances
    lease_models = [
        m for m in result.models if m.__class__.__name__ == "ResidentialLease"
    ]
    assert len(lease_models) == 5
