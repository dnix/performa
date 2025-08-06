# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Edge Case Validation Tests

Tests for the specific edge cases identified in the rolling value-add implementation.
These tests document and validate the expected behavior for edge scenarios.
"""

from datetime import date
from uuid import uuid4

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
from performa.core.capital import CapitalItem, CapitalPlan
from performa.core.primitives import (
    GlobalSettings,
    PropertyAttributeKey,
    StartDateAnchorEnum,
    Timeline,
    UponExpirationEnum,
)


class TestZeroDowntimeScenarios:
    """Test zero downtime renovation scenarios (downtime_months=0)."""

    def test_zero_downtime_immediate_transition(self):
        """Test that zero downtime causes immediate lease transition without gaps."""

        # Create absorption plan for immediate post-renovation
        plan_id = uuid4()
        absorption_plan = ResidentialAbsorptionPlan(
            uid=plan_id,
            name="Immediate Renovation Plan",
            start_date_anchor=StartDateAnchorEnum.ANALYSIS_START,
            pace=FixedQuantityPace(quantity=1, unit="Units", frequency_months=1),
            leasing_assumptions=ResidentialDirectLeaseTerms(
                monthly_rent=2500.0,  # Premium rent
                stabilized_renewal_probability=0.8,
                stabilized_downtime_months=1,
            ),
            stabilized_expenses=ResidentialExpenses(operating_expenses=[]),
            stabilized_losses=ResidentialLosses(
                general_vacancy={"rate": 0.05, "method": "Potential Gross Revenue"},
                collection_loss={"rate": 0.02, "basis": "egi"},
            ),
            stabilized_misc_income=[],
        )

        # Create rollover profile with ZERO downtime
        rollover_profile = ResidentialRolloverProfile(
            name="Zero Downtime Renovation",
            term_months=12,
            renewal_probability=0.0,
            downtime_months=0,  # ZERO DOWNTIME - immediate transition
            market_terms=ResidentialRolloverLeaseTerms(
                market_rent=2200.0, term_months=12
            ),
            renewal_terms=ResidentialRolloverLeaseTerms(
                market_rent=2100.0, term_months=12
            ),
            upon_expiration=UponExpirationEnum.REABSORB,
            target_absorption_plan_id=plan_id,
        )

        unit_spec = ResidentialUnitSpec(
            unit_type_name="Zero Downtime Unit",
            unit_count=1,
            avg_area_sf=800.0,
            current_avg_monthly_rent=2000.0,
            rollover_profile=rollover_profile,
            lease_start_date=date(2023, 6, 1),  # Expires June 2024
        )

        property_model = ResidentialProperty(
            name="Zero Downtime Property",
            address=Address(
                street="123 Zero St",
                city="Test",
                state="CA",
                zip_code="90210",
                country="USA",
            ),
            gross_area=800.0,
            net_rentable_area=800.0,
            unit_mix=ResidentialRentRoll(unit_specs=[unit_spec]),
            capital_plans=[],
            absorption_plans=[absorption_plan],
            expenses=ResidentialExpenses(operating_expenses=[]),
            losses=ResidentialLosses(
                general_vacancy={"rate": 0.0, "method": "Potential Gross Revenue"},
                collection_loss={"rate": 0.0, "basis": "egi"},
            ),
            miscellaneous_income=[],
        )

        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=24)
        settings = GlobalSettings()

        scenario = run(model=property_model, timeline=timeline, settings=settings)
        cash_flow_summary = scenario.get_cash_flow_summary()

        pgr_series = cash_flow_summary["Potential Gross Revenue"]

        # Verify timing: lease expires June 2024 (month 6, index 5)
        # With zero downtime, premium lease should start immediately in June
        assert pgr_series.iloc[4] == 2000.0  # Month 5 (May 2024) - original lease
        assert (
            pgr_series.iloc[5] == 2500.0
        )  # Month 6 (Jun 2024) - premium lease starts (zero downtime)
        assert pgr_series.iloc[6] == 2500.0  # Month 7 (Jul 2024) - continues

        # Verify no gap in revenue (zero downtime working correctly)
        for i in range(len(pgr_series)):
            if pgr_series.iloc[i] > 0:  # If there's revenue, ensure no unexpected gaps
                assert pgr_series.iloc[i] in [
                    2000.0,
                    2500.0,
                ], f"Unexpected revenue amount at month {i + 1}"


class TestExtendedDowntimeScenarios:
    """Test very long downtime scenarios (>12 months)."""

    def test_extended_downtime_major_renovation(self):
        """Test that very long downtime periods work correctly for major renovations."""

        # Create absorption plan for major renovation
        plan_id = uuid4()
        absorption_plan = ResidentialAbsorptionPlan(
            uid=plan_id,
            name="Major Renovation Plan",
            start_date_anchor=StartDateAnchorEnum.ANALYSIS_START,
            pace=FixedQuantityPace(quantity=1, unit="Units", frequency_months=1),
            leasing_assumptions=ResidentialDirectLeaseTerms(
                monthly_rent=3000.0,  # Premium rent for major renovation
                stabilized_renewal_probability=0.8,
                stabilized_downtime_months=1,
            ),
            stabilized_expenses=ResidentialExpenses(operating_expenses=[]),
            stabilized_losses=ResidentialLosses(
                general_vacancy={"rate": 0.05, "method": "Potential Gross Revenue"},
                collection_loss={"rate": 0.02, "basis": "egi"},
            ),
            stabilized_misc_income=[],
        )

        # Create rollover profile with 18-month downtime (major renovation)
        rollover_profile = ResidentialRolloverProfile(
            name="Major Renovation Profile",
            term_months=12,
            renewal_probability=0.0,
            downtime_months=18,  # 18 MONTHS downtime - major renovation
            market_terms=ResidentialRolloverLeaseTerms(
                market_rent=2200.0, term_months=12
            ),
            renewal_terms=ResidentialRolloverLeaseTerms(
                market_rent=2100.0, term_months=12
            ),
            upon_expiration=UponExpirationEnum.REABSORB,
            target_absorption_plan_id=plan_id,
        )

        unit_spec = ResidentialUnitSpec(
            unit_type_name="Major Renovation Unit",
            unit_count=1,
            avg_area_sf=800.0,
            current_avg_monthly_rent=2000.0,
            rollover_profile=rollover_profile,
            lease_start_date=date(2023, 6, 1),  # Expires June 2024
        )

        property_model = ResidentialProperty(
            name="Major Renovation Property",
            address=Address(
                street="123 Major St",
                city="Test",
                state="CA",
                zip_code="90210",
                country="USA",
            ),
            gross_area=800.0,
            net_rentable_area=800.0,
            unit_mix=ResidentialRentRoll(unit_specs=[unit_spec]),
            capital_plans=[],
            absorption_plans=[absorption_plan],
            expenses=ResidentialExpenses(operating_expenses=[]),
            losses=ResidentialLosses(
                general_vacancy={"rate": 0.0, "method": "Potential Gross Revenue"},
                collection_loss={"rate": 0.0, "basis": "egi"},
            ),
            miscellaneous_income=[],
        )

        timeline = Timeline(
            start_date=date(2024, 1, 1), duration_months=36
        )  # 3-year analysis
        settings = GlobalSettings()

        scenario = run(model=property_model, timeline=timeline, settings=settings)
        cash_flow_summary = scenario.get_cash_flow_summary()

        pgr_series = cash_flow_summary["Potential Gross Revenue"]

        # Verify extended downtime pattern
        # Original lease expires June 2024 (month 6, index 5)
        # 18 months downtime: June 2024 - November 2025 (months 6-23)
        # New lease starts December 2025 (month 24, index 23)

        # Should have original rent before expiration
        assert (
            pgr_series.iloc[4] == 2000.0
        ), "Should have original rent in month 5 (May 2024)"

        # Should have zero revenue during expiration + downtime (months 6-23)
        for month_idx in range(5, 23):  # Months 6-23 (0-indexed)
            if month_idx < len(pgr_series):
                assert (
                    pgr_series.iloc[month_idx] == 0.0
                ), f"Should have zero revenue during downtime (month {month_idx + 1})"

        # Verify premium rent after extended renovation (month 24+)
        if len(pgr_series) > 23:
            assert (
                pgr_series.iloc[23] == 3000.0
            ), "Should have premium rent after extended renovation (month 24)"


class TestLeaseExpirationBeyondAnalysis:
    """Test lease expirations that occur beyond the analysis period."""

    def test_lease_expiration_beyond_analysis_period(self):
        """Test that leases expiring beyond analysis period are handled correctly."""

        # Create absorption plan
        plan_id = uuid4()
        absorption_plan = ResidentialAbsorptionPlan(
            uid=plan_id,
            name="Future Renovation Plan",
            start_date_anchor=StartDateAnchorEnum.ANALYSIS_START,
            pace=FixedQuantityPace(quantity=1, unit="Units", frequency_months=1),
            leasing_assumptions=ResidentialDirectLeaseTerms(
                monthly_rent=2500.0,
                stabilized_renewal_probability=0.8,
                stabilized_downtime_months=1,
            ),
            stabilized_expenses=ResidentialExpenses(operating_expenses=[]),
            stabilized_losses=ResidentialLosses(
                general_vacancy={"rate": 0.05, "method": "Potential Gross Revenue"},
                collection_loss={"rate": 0.02, "basis": "egi"},
            ),
            stabilized_misc_income=[],
        )

        rollover_profile = ResidentialRolloverProfile(
            name="Future Renovation Profile",
            term_months=12,
            renewal_probability=0.0,
            downtime_months=2,
            market_terms=ResidentialRolloverLeaseTerms(
                market_rent=2200.0, term_months=12
            ),
            renewal_terms=ResidentialRolloverLeaseTerms(
                market_rent=2100.0, term_months=12
            ),
            upon_expiration=UponExpirationEnum.REABSORB,
            target_absorption_plan_id=plan_id,
        )

        unit_spec = ResidentialUnitSpec(
            unit_type_name="Future Expiration Unit",
            unit_count=1,
            avg_area_sf=800.0,
            current_avg_monthly_rent=2000.0,
            rollover_profile=rollover_profile,
            lease_start_date=date(
                2025, 6, 1
            ),  # Expires June 2026 - BEYOND 24-month analysis (ends Dec 2025)
        )

        property_model = ResidentialProperty(
            name="Future Expiration Property",
            address=Address(
                street="123 Future St",
                city="Test",
                state="CA",
                zip_code="90210",
                country="USA",
            ),
            gross_area=800.0,
            net_rentable_area=800.0,
            unit_mix=ResidentialRentRoll(unit_specs=[unit_spec]),
            capital_plans=[],
            absorption_plans=[absorption_plan],
            expenses=ResidentialExpenses(operating_expenses=[]),
            losses=ResidentialLosses(
                general_vacancy={"rate": 0.0, "method": "Potential Gross Revenue"},
                collection_loss={"rate": 0.0, "basis": "egi"},
            ),
            miscellaneous_income=[],
        )

        timeline = Timeline(
            start_date=date(2024, 1, 1), duration_months=24
        )  # 2-year analysis
        settings = GlobalSettings()

        scenario = run(model=property_model, timeline=timeline, settings=settings)
        cash_flow_summary = scenario.get_cash_flow_summary()

        pgr_series = cash_flow_summary["Potential Gross Revenue"]

        # Lease starts June 2025 (month 18) and expires June 2026 (beyond analysis)
        # Should have no revenue for months 1-17, then revenue from month 18-24

        # No revenue before lease starts (months 1-17)
        for month_idx in range(17):  # months 1-17 (0-indexed 0-16)
            assert (
                pgr_series.iloc[month_idx] == 0.0
            ), f"Should have no revenue before lease starts (month {month_idx + 1})"

        # Revenue from lease start through analysis end (months 18-24)
        for month_idx in range(17, len(pgr_series)):  # months 18-24 (0-indexed 17-23)
            assert (
                pgr_series.iloc[month_idx] == 2000.0
            ), f"Should have original rent from lease start (month {month_idx + 1})"

        # This documents expected behavior: transformations beyond analysis period don't affect projections
        # Since the lease doesn't expire until June 2026 (beyond Dec 2025 analysis end), no transformation occurs


class TestCircularReferenceDetection:
    """Test detection and handling of circular references in absorption plans."""

    def test_circular_reference_prevention_documentation(self):
        """Document the circular reference scenario and expected prevention."""

        # This test documents the circular reference scenario for posterity
        # Circular references occur when:
        # 1. Lease A has REABSORB + target_absorption_plan_id = Plan X
        # 2. Plan X creates leases with REABSORB + target_absorption_plan_id = Plan Y
        # 3. Plan Y creates leases with REABSORB + target_absorption_plan_id = Plan X
        # This would create an infinite loop of transformations

        # CURRENT PREVENTION: The ResidentialDirectLeaseTerms in absorption plans
        # default to upon_expiration=MARKET, which breaks potential circles.
        # This is sufficient for typical use cases.

        # FUTURE ENHANCEMENT: If users need complex chained transformations,
        # add explicit circular reference detection in ResidentialAnalysisScenario

        plan_id_1 = uuid4()
        plan_id_2 = uuid4()

        # Plan 1: Creates leases that might point to Plan 2
        plan_1 = ResidentialAbsorptionPlan(
            uid=plan_id_1,
            name="Transformation Plan 1",
            start_date_anchor=StartDateAnchorEnum.ANALYSIS_START,
            pace=FixedQuantityPace(quantity=1, unit="Units", frequency_months=1),
            leasing_assumptions=ResidentialDirectLeaseTerms(
                monthly_rent=2500.0,
                # Default upon_expiration=MARKET prevents circular references
                stabilized_renewal_probability=0.8,
                stabilized_downtime_months=1,
            ),
            stabilized_expenses=ResidentialExpenses(operating_expenses=[]),
            stabilized_losses=ResidentialLosses(
                general_vacancy={"rate": 0.05, "method": "Potential Gross Revenue"},
                collection_loss={"rate": 0.02, "basis": "egi"},
            ),
            stabilized_misc_income=[],
        )

        # Plan 2: Would create leases that point back to Plan 1 (potential circle)
        plan_2 = ResidentialAbsorptionPlan(
            uid=plan_id_2,
            name="Transformation Plan 2",
            start_date_anchor=StartDateAnchorEnum.ANALYSIS_START,
            pace=FixedQuantityPace(quantity=1, unit="Units", frequency_months=1),
            leasing_assumptions=ResidentialDirectLeaseTerms(
                monthly_rent=3000.0,
                # Default upon_expiration=MARKET prevents circular references
                stabilized_renewal_probability=0.8,
                stabilized_downtime_months=1,
            ),
            stabilized_expenses=ResidentialExpenses(operating_expenses=[]),
            stabilized_losses=ResidentialLosses(
                general_vacancy={"rate": 0.05, "method": "Potential Gross Revenue"},
                collection_loss={"rate": 0.02, "basis": "egi"},
            ),
            stabilized_misc_income=[],
        )

        # Initial rollover profile points to Plan 1
        rollover_profile = ResidentialRolloverProfile(
            name="Initial Transformation",
            term_months=12,
            renewal_probability=0.0,
            downtime_months=2,
            market_terms=ResidentialRolloverLeaseTerms(
                market_rent=2200.0, term_months=12
            ),
            renewal_terms=ResidentialRolloverLeaseTerms(
                market_rent=2100.0, term_months=12
            ),
            upon_expiration=UponExpirationEnum.REABSORB,
            target_absorption_plan_id=plan_id_1,  # Points to Plan 1
        )

        unit_spec = ResidentialUnitSpec(
            unit_type_name="Circular Test Unit",
            unit_count=1,
            avg_area_sf=800.0,
            current_avg_monthly_rent=2000.0,
            rollover_profile=rollover_profile,
            lease_start_date=date(2023, 6, 1),
        )

        property_model = ResidentialProperty(
            name="Circular Reference Test Property",
            address=Address(
                street="123 Circle St",
                city="Test",
                state="CA",
                zip_code="90210",
                country="USA",
            ),
            gross_area=800.0,
            net_rentable_area=800.0,
            unit_mix=ResidentialRentRoll(unit_specs=[unit_spec]),
            capital_plans=[],
            absorption_plans=[plan_1, plan_2],  # Both plans available
            expenses=ResidentialExpenses(operating_expenses=[]),
            losses=ResidentialLosses(
                general_vacancy={"rate": 0.0, "method": "Potential Gross Revenue"},
                collection_loss={"rate": 0.0, "basis": "egi"},
            ),
            miscellaneous_income=[],
        )

        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=24)
        settings = GlobalSettings()

        # This should work without infinite loops because absorption plans
        # create leases with MARKET expiration by default
        scenario = run(model=property_model, timeline=timeline, settings=settings)
        cash_flow_summary = scenario.get_cash_flow_summary()

        pgr_series = cash_flow_summary["Potential Gross Revenue"]

        # Should complete successfully with one transformation (2000 -> 2500)
        # and then stabilize with MARKET behavior (no further REABSORB)
        initial_revenue = pgr_series.iloc[0]
        final_revenue = pgr_series.iloc[-1]

        assert initial_revenue == 2000.0, "Should start with original rent"
        assert final_revenue == 2500.0, "Should end with premium rent from Plan 1"

        # Verify only one transformation occurs (no circular behavior)
        transformations = 0
        for i in range(1, len(pgr_series)):
            if pgr_series.iloc[i] != pgr_series.iloc[i - 1] and pgr_series.iloc[i] > 0:
                transformations += 1

        # Should have at most 2 transitions: original->zero (downtime) and zero->premium
        assert transformations <= 2, "Should not have circular transformations"


class TestEdgeCaseDocumentation:
    """Documentation and validation of other edge cases."""

    def test_capital_plan_timing_independence(self):
        """Document that capital plan timing is independent of lease timing."""

        # This test documents expected behavior: Capital plans and lease transformations
        # are independent. Users are responsible for coordinating timing.
        # This is by design - it gives users full control over renovation spending patterns.

        plan_id = uuid4()
        absorption_plan = ResidentialAbsorptionPlan(
            uid=plan_id,
            name="Renovation Plan",
            start_date_anchor=StartDateAnchorEnum.ANALYSIS_START,
            pace=FixedQuantityPace(quantity=1, unit="Units", frequency_months=1),
            leasing_assumptions=ResidentialDirectLeaseTerms(
                monthly_rent=2500.0,
                stabilized_renewal_probability=0.8,
                stabilized_downtime_months=1,
            ),
            stabilized_expenses=ResidentialExpenses(operating_expenses=[]),
            stabilized_losses=ResidentialLosses(
                general_vacancy={"rate": 0.05, "method": "Potential Gross Revenue"},
                collection_loss={"rate": 0.02, "basis": "egi"},
            ),
            stabilized_misc_income=[],
        )

        rollover_profile = ResidentialRolloverProfile(
            name="Renovation Profile",
            term_months=12,
            renewal_probability=0.0,
            downtime_months=2,  # Downtime June-July 2024
            market_terms=ResidentialRolloverLeaseTerms(
                market_rent=2200.0, term_months=12
            ),
            renewal_terms=ResidentialRolloverLeaseTerms(
                market_rent=2100.0, term_months=12
            ),
            upon_expiration=UponExpirationEnum.REABSORB,
            target_absorption_plan_id=plan_id,
        )

        unit_spec = ResidentialUnitSpec(
            unit_type_name="Timing Test Unit",
            unit_count=1,
            avg_area_sf=800.0,
            current_avg_monthly_rent=2000.0,
            rollover_profile=rollover_profile,
            lease_start_date=date(2023, 6, 1),  # Expires June 2024
        )

        capital_timeline = Timeline(start_date=date(2024, 1, 1), duration_months=3)
        capital_plan = CapitalPlan(
            name="Misaligned Renovation Spending",
            capital_items=[
                CapitalItem(
                    name="Early Renovation Spending",
                    reference=PropertyAttributeKey.UNIT_COUNT,
                    value=15000.0,  # Spent Jan-Mar 2024 (before lease expires)
                    timeline=capital_timeline,
                )
            ],
        )

        property_model = ResidentialProperty(
            name="Timing Independence Property",
            address=Address(
                street="123 Timing St",
                city="Test",
                state="CA",
                zip_code="90210",
                country="USA",
            ),
            gross_area=800.0,
            net_rentable_area=800.0,
            unit_mix=ResidentialRentRoll(unit_specs=[unit_spec]),
            capital_plans=[capital_plan],  # Misaligned capital plan
            absorption_plans=[absorption_plan],
            expenses=ResidentialExpenses(operating_expenses=[]),
            losses=ResidentialLosses(
                general_vacancy={"rate": 0.0, "method": "Potential Gross Revenue"},
                collection_loss={"rate": 0.0, "basis": "egi"},
            ),
            miscellaneous_income=[],
        )

        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=24)
        settings = GlobalSettings()

        # Should work fine - capital spending and lease timing are independent
        scenario = run(model=property_model, timeline=timeline, settings=settings)
        cash_flow_summary = scenario.get_cash_flow_summary()

        pgr_series = cash_flow_summary["Potential Gross Revenue"]

        # Revenue transformation should occur per lease schedule (June 2024)
        # regardless of when capital was spent (Jan-Mar 2024)
        assert (
            pgr_series.iloc[4] == 2000.0
        ), "Should have original rent in month 5 (before expiration)"
        assert (
            pgr_series.iloc[5] == 0.0
        ), "Should have no revenue in month 6 (expiration + downtime)"
        assert (
            pgr_series.iloc[6] == 0.0
        ), "Should have no revenue in month 7 (downtime continues)"
        assert (
            pgr_series.iloc[7] == 2500.0
        ), "Should have premium rent in month 8 (after transformation)"

        # This documents expected behavior: Users control timing coordination
        # The system doesn't enforce timing alignment between capital and leases
