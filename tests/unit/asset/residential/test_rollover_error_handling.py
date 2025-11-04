# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Test Rollover Error Handling

Tests error handling scenarios for our new REABSORB + target_absorption_plan_id functionality.
These are critical for user experience - users WILL make configuration mistakes.
"""

from datetime import date
from uuid import uuid4

import pytest

from performa.analysis import run
from performa.asset.residential import (
    ResidentialAbsorptionPlan,
    ResidentialExpenses,
    ResidentialLosses,
    ResidentialProperty,
    ResidentialRentRoll,
    ResidentialRolloverLeaseTerms,
    ResidentialRolloverProfile,
    ResidentialUnitSpec,
)
from performa.asset.residential.absorption import ResidentialDirectLeaseTerms
from performa.core.base import Address
from performa.core.base.absorption import FixedQuantityPace
from performa.core.primitives import (
    GlobalSettings,
    StartDateAnchorEnum,
    Timeline,
    UponExpirationEnum,
)


class TestRolloverErrorHandling:
    """Test error handling for rollover scenarios."""

    def test_missing_target_absorption_plan_id(self):
        """Test REABSORB with missing target_absorption_plan_id."""

        # Create rollover profile with REABSORB but no target plan
        rollover_profile = ResidentialRolloverProfile(
            name="Broken Profile",
            term_months=12,
            renewal_probability=0.0,
            downtime_months=2,
            market_terms=ResidentialRolloverLeaseTerms(
                market_rent=2000.0, term_months=12
            ),
            renewal_terms=ResidentialRolloverLeaseTerms(
                market_rent=2000.0, term_months=12
            ),
            upon_expiration=UponExpirationEnum.REABSORB,
            target_absorption_plan_id=None,  # Missing target plan ID
        )

        unit_spec = ResidentialUnitSpec(
            unit_type_name="Broken Unit",
            unit_count=1,
            avg_area_sf=800.0,
            current_avg_monthly_rent=2000.0,
            rollover_profile=rollover_profile,
            lease_start_date=date(2023, 3, 1),
        )

        property_model = ResidentialProperty(
            name="Broken Property",
            address=Address(
                street="123 Error St",
                city="Test",
                state="CA",
                zip_code="90210",
                country="USA",
            ),
            gross_area=800.0,
            net_rentable_area=800.0,
            unit_mix=ResidentialRentRoll(unit_specs=[unit_spec]),
            capital_plans=[],
            absorption_plans=[],  # No absorption plans provided
            expenses=ResidentialExpenses(operating_expenses=[]),
            losses=ResidentialLosses(
                general_vacancy={"rate": 0.0, "method": "Potential Gross Revenue"},
                credit_loss={"rate": 0.0, "basis": "Potential Gross Revenue"},
            ),
            miscellaneous_income=[],
        )

        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=24)
        settings = GlobalSettings()

        # Should handle gracefully without crashing
        scenario = run(model=property_model, timeline=timeline, settings=settings)
        cash_flow_summary = scenario.summary_df

        # Should complete analysis (though unit won't transform)
        assert not cash_flow_summary.empty

        # Revenue should stop when lease expires (month 3)
        pgr_series = cash_flow_summary["Potential Gross Revenue"]
        month_2_revenue = pgr_series.iloc[1]  # Month 2 (before expiration)
        month_3_revenue = pgr_series.iloc[2]  # Month 3 (expiration)
        month_6_revenue = pgr_series.iloc[5]  # Month 6

        # Should have revenue before expiration, none after (unit didn't transform)
        assert month_2_revenue > 0, "Should have revenue before lease expires"
        assert month_3_revenue == 0, "Should have no revenue when lease expires"
        assert month_6_revenue == 0, (
            "Should have no revenue later (unit didn't transform)"
        )

    def test_nonexistent_target_absorption_plan_id(self):
        """Test REABSORB with target_absorption_plan_id that doesn't exist."""

        fake_plan_id = uuid4()  # Random UUID that doesn't exist

        rollover_profile = ResidentialRolloverProfile(
            name="Broken Profile",
            term_months=12,
            renewal_probability=0.0,
            downtime_months=2,
            market_terms=ResidentialRolloverLeaseTerms(
                market_rent=2000.0, term_months=12
            ),
            renewal_terms=ResidentialRolloverLeaseTerms(
                market_rent=2000.0, term_months=12
            ),
            upon_expiration=UponExpirationEnum.REABSORB,
            target_absorption_plan_id=fake_plan_id,  # Points to non-existent plan
        )

        # Create a different absorption plan (not the target)
        real_plan = ResidentialAbsorptionPlan(
            uid=uuid4(),  # Different UUID
            name="Real Plan",
            start_date_anchor=StartDateAnchorEnum.ANALYSIS_START,
            pace=FixedQuantityPace(quantity=1, unit="Units", frequency_months=1),
            leasing_assumptions=ResidentialDirectLeaseTerms(monthly_rent=2500.0),
            stabilized_expenses=ResidentialExpenses(operating_expenses=[]),
            stabilized_losses=ResidentialLosses(
                general_vacancy={"rate": 0.0, "method": "Potential Gross Revenue"},
                credit_loss={"rate": 0.0, "basis": "Potential Gross Revenue"},
            ),
            stabilized_misc_income=[],
        )

        unit_spec = ResidentialUnitSpec(
            unit_type_name="Broken Unit",
            unit_count=1,
            avg_area_sf=800.0,
            current_avg_monthly_rent=2000.0,
            rollover_profile=rollover_profile,
            lease_start_date=date(2023, 3, 1),
        )

        property_model = ResidentialProperty(
            name="Broken Property",
            address=Address(
                street="123 Error St",
                city="Test",
                state="CA",
                zip_code="90210",
                country="USA",
            ),
            gross_area=800.0,
            net_rentable_area=800.0,
            unit_mix=ResidentialRentRoll(unit_specs=[unit_spec]),
            capital_plans=[],
            absorption_plans=[real_plan],  # Has plan but wrong UUID
            expenses=ResidentialExpenses(operating_expenses=[]),
            losses=ResidentialLosses(
                general_vacancy={"rate": 0.0, "method": "Potential Gross Revenue"},
                credit_loss={"rate": 0.0, "basis": "Potential Gross Revenue"},
            ),
            miscellaneous_income=[],
        )

        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=24)
        settings = GlobalSettings()

        # Should handle gracefully without crashing
        scenario = run(model=property_model, timeline=timeline, settings=settings)
        cash_flow_summary = scenario.summary_df

        # Should complete analysis
        assert not cash_flow_summary.empty

        # Unit transformation should fail gracefully
        pgr_series = cash_flow_summary["Potential Gross Revenue"]
        month_6_revenue = pgr_series.iloc[5]  # After expiration + downtime

        # Should have no revenue from this unit after expiration
        assert month_6_revenue == 0

    def test_circular_reference_prevention(self):
        """Test that circular references are prevented or handled gracefully."""

        plan_id = uuid4()

        # Create absorption plan that points to itself (circular reference)
        circular_plan = ResidentialAbsorptionPlan(
            uid=plan_id,
            name="Circular Plan",
            start_date_anchor=StartDateAnchorEnum.ANALYSIS_START,
            pace=FixedQuantityPace(quantity=1, unit="Units", frequency_months=1),
            leasing_assumptions=ResidentialDirectLeaseTerms(
                monthly_rent=2500.0,
                upon_expiration=UponExpirationEnum.REABSORB,  # Would create circular reference
                stabilized_renewal_probability=0.0,
                stabilized_downtime_months=2,
            ),
            stabilized_expenses=ResidentialExpenses(operating_expenses=[]),
            stabilized_losses=ResidentialLosses(
                general_vacancy={"rate": 0.0, "method": "Potential Gross Revenue"},
                credit_loss={"rate": 0.0, "basis": "Potential Gross Revenue"},
            ),
            stabilized_misc_income=[],
        )

        rollover_profile = ResidentialRolloverProfile(
            name="Circular Profile",
            term_months=12,
            renewal_probability=0.0,
            downtime_months=2,
            market_terms=ResidentialRolloverLeaseTerms(
                market_rent=2000.0, term_months=12
            ),
            renewal_terms=ResidentialRolloverLeaseTerms(
                market_rent=2000.0, term_months=12
            ),
            upon_expiration=UponExpirationEnum.REABSORB,
            target_absorption_plan_id=plan_id,  # Points to plan that also has REABSORB
        )

        unit_spec = ResidentialUnitSpec(
            unit_type_name="Circular Unit",
            unit_count=1,
            avg_area_sf=800.0,
            current_avg_monthly_rent=2000.0,
            rollover_profile=rollover_profile,
            lease_start_date=date(2023, 3, 1),
        )

        property_model = ResidentialProperty(
            name="Circular Property",
            address=Address(
                street="123 Circular St",
                city="Test",
                state="CA",
                zip_code="90210",
                country="USA",
            ),
            gross_area=800.0,
            net_rentable_area=800.0,
            unit_mix=ResidentialRentRoll(unit_specs=[unit_spec]),
            capital_plans=[],
            absorption_plans=[circular_plan],
            expenses=ResidentialExpenses(operating_expenses=[]),
            losses=ResidentialLosses(
                general_vacancy={"rate": 0.0, "method": "Potential Gross Revenue"},
                credit_loss={"rate": 0.0, "basis": "Potential Gross Revenue"},
            ),
            miscellaneous_income=[],
        )

        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=24)
        settings = GlobalSettings()

        # Should handle gracefully without infinite loops
        scenario = run(model=property_model, timeline=timeline, settings=settings)
        cash_flow_summary = scenario.summary_df

        # Analysis should complete without hanging
        assert not cash_flow_summary.empty


class TestRolloverConfigurationValidation:
    """Test validation of rollover profile configurations."""

    def test_reabsorb_without_target_plan_validation(self):
        """Test that REABSORB without target_absorption_plan_id is allowed (legacy support)."""

        # This should be valid - REABSORB without target plan is legacy behavior
        rollover_profile = ResidentialRolloverProfile(
            name="Legacy REABSORB",
            term_months=12,
            renewal_probability=0.0,
            downtime_months=2,
            market_terms=ResidentialRolloverLeaseTerms(
                market_rent=2000.0, term_months=12
            ),
            renewal_terms=ResidentialRolloverLeaseTerms(
                market_rent=2000.0, term_months=12
            ),
            upon_expiration=UponExpirationEnum.REABSORB,
            target_absorption_plan_id=None,  # Legacy: REABSORB without target plan
        )

        # Should create successfully
        assert rollover_profile.upon_expiration == UponExpirationEnum.REABSORB
        assert rollover_profile.target_absorption_plan_id is None

    def test_non_reabsorb_with_target_plan_validation(self):
        """Test that non-REABSORB with target_absorption_plan_id raises validation error."""

        # This should raise a validation error
        with pytest.raises(
            ValueError,
            match="target_absorption_plan_id can only be specified when upon_expiration='reabsorb'",
        ):
            ResidentialRolloverProfile(
                name="Invalid Profile",
                term_months=12,
                renewal_probability=0.5,
                downtime_months=1,
                market_terms=ResidentialRolloverLeaseTerms(
                    market_rent=2000.0, term_months=12
                ),
                renewal_terms=ResidentialRolloverLeaseTerms(
                    market_rent=2000.0, term_months=12
                ),
                upon_expiration=UponExpirationEnum.MARKET,  # Not REABSORB
                target_absorption_plan_id=uuid4(),  # But has target plan - should be invalid
            )
