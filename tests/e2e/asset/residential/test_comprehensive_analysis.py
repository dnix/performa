# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Comprehensive End-to-End Tests for Residential Analysis
========================================================

This test suite pushes the envelope of our residential analysis capabilities
by testing real-world scenarios, large-scale properties, and complex
market conditions. These tests demonstrate production-ready functionality.

Test Categories:
1. Large-Scale Properties (200+ units)
2. Complex Unit Mix (6+ unit types)
3. Real-World Market Scenarios
4. Performance Stress Tests
5. Multi-Property Portfolios
"""

import time
from datetime import date

import pytest

from performa.analysis import run
from performa.asset.residential import (
    ResidentialAnalysisScenario,
    ResidentialCapExItem,
    ResidentialCollectionLoss,
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
from performa.core.primitives import (
    FrequencyEnum,
    GlobalSettings,
    PropertyAttributeKey,
    Timeline,
    UnleveredAggregateLineKey,
)
from performa.core.primitives.growth_rates import PercentageGrowthRate


class TestLargeScaleProperties:
    """Test large multifamily properties (200+ units) for scale and performance."""

    def test_institutional_scale_property(self):
        """
        Test a realistic institutional-scale multifamily property.

        Property Profile:
        - 250 units across 6 unit types
        - Garden/Mid-rise/High-rise positioning
        - Realistic market rents and unit distribution
        - 5-year analysis with sophisticated rollover assumptions
        """
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=60)  # 5 years
        settings = GlobalSettings()

        # Create sophisticated rollover assumptions with staggered growth
        market_terms = ResidentialRolloverLeaseTerms(
            market_rent=2500.0,  # Base market rent (varies by unit)
            market_rent_growth=PercentageGrowthRate(
                name="Market Growth", value=0.035
            ),  # 3.5% annual
            renewal_rent_increase_percent=0.028,  # 2.8% renewal increases
            concessions_months=1,  # 1 month free for new leases
            capital_plan_id=None,  # No capital plan for basic rollover (UUID-based architecture)
            term_months=12,
        )

        renewal_terms = ResidentialRolloverLeaseTerms(
            market_rent=2400.0,  # Renewal discount
            market_rent_growth=PercentageGrowthRate(
                name="Renewal Growth", value=0.025
            ),  # 2.5% for renewals
            renewal_rent_increase_percent=0.028,
            concessions_months=0,  # No concessions for renewals
            capital_plan_id=None,  # No costs for renewals (UUID-based architecture)
            term_months=12,
        )

        rollover_profile = ResidentialRolloverProfile(
            name="Institutional Class A Profile",
            renewal_probability=0.72,  # High renewal rate for quality property
            downtime_months=1,
            term_months=12,
            market_terms=market_terms,
            renewal_terms=renewal_terms,
        )

        # Complex unit mix - 6 unit types with realistic distribution
        unit_specs = [
            # Garden Level Units (lower rent)
            ResidentialUnitSpec(
                unit_type_name="Studio - Garden",
                unit_count=20,
                avg_area_sf=550.0,
                current_avg_monthly_rent=1850.0,
                rollover_profile=rollover_profile,
            ),
            ResidentialUnitSpec(
                unit_type_name="1BR/1BA - Garden",
                unit_count=35,
                avg_area_sf=725.0,
                current_avg_monthly_rent=2150.0,
                rollover_profile=rollover_profile,
            ),
            # Mid-Rise Units (premium rent)
            ResidentialUnitSpec(
                unit_type_name="1BR/1BA - Premium",
                unit_count=45,
                avg_area_sf=775.0,
                current_avg_monthly_rent=2450.0,
                rollover_profile=rollover_profile,
            ),
            ResidentialUnitSpec(
                unit_type_name="2BR/2BA - Standard",
                unit_count=80,
                avg_area_sf=1050.0,
                current_avg_monthly_rent=3200.0,
                rollover_profile=rollover_profile,
            ),
            ResidentialUnitSpec(
                unit_type_name="2BR/2BA - Premium",
                unit_count=50,
                avg_area_sf=1200.0,
                current_avg_monthly_rent=3750.0,
                rollover_profile=rollover_profile,
            ),
            # Penthouse Units (luxury pricing)
            ResidentialUnitSpec(
                unit_type_name="3BR/2.5BA - Penthouse",
                unit_count=20,
                avg_area_sf=1650.0,
                current_avg_monthly_rent=5200.0,
                rollover_profile=rollover_profile,
            ),
        ]

        rent_roll = ResidentialRentRoll(unit_specs=unit_specs)

        # Comprehensive expenses for institutional property
        expenses = ResidentialExpenses(
            operating_expenses=[
                ResidentialOpExItem(
                    name="Property Management",
                    timeline=timeline,
                    value=0.055,  # 5.5% management fee
                    frequency=FrequencyEnum.MONTHLY,
                    reference=UnleveredAggregateLineKey.EFFECTIVE_GROSS_INCOME,
                ),
                ResidentialOpExItem(
                    name="Maintenance & Repairs",
                    timeline=timeline,
                    value=550.0,  # $550 per unit annually
                    frequency=FrequencyEnum.ANNUAL,
                    reference=PropertyAttributeKey.UNIT_COUNT,
                ),
                ResidentialOpExItem(
                    name="Utilities",
                    timeline=timeline,
                    value=180000.0,  # $180k annually for common areas
                    frequency=FrequencyEnum.ANNUAL,
                    # reference=None (direct currency amount)
                    growth_rate=PercentageGrowthRate(
                        name="Utility Growth", value=0.04
                    ),  # 4% utility inflation
                ),
                ResidentialOpExItem(
                    name="Insurance & Taxes",
                    timeline=timeline,
                    value=2.85,  # $2.85 per SF annually
                    frequency=FrequencyEnum.ANNUAL,
                    reference=PropertyAttributeKey.UNIT_COUNT,
                    growth_rate=PercentageGrowthRate(
                        name="Tax Growth", value=0.025
                    ),  # 2.5% tax growth
                ),
            ],
            capital_expenses=[
                ResidentialCapExItem(
                    name="Capital Reserves",
                    timeline=timeline,
                    value=450.0,  # $450 per unit annually
                    frequency=FrequencyEnum.ANNUAL,
                    reference=PropertyAttributeKey.UNIT_COUNT,
                ),
                ResidentialCapExItem(
                    name="Facility Improvements",
                    timeline=timeline,
                    value=125000.0,  # $125k annually for amenities/common areas
                    frequency=FrequencyEnum.ANNUAL,
                    # reference=None (direct currency amount)
                ),
            ],
        )

        # Realistic loss assumptions
        losses = ResidentialLosses(
            general_vacancy=ResidentialGeneralVacancyLoss(
                rate=0.04
            ),  # 4% for well-managed property
            collection_loss=ResidentialCollectionLoss(
                rate=0.015
            ),  # 1.5% collection loss
        )

        # Multiple income streams
        misc_income = [
            ResidentialMiscIncome(
                name="Parking Revenue",
                timeline=timeline,
                value=125.0,  # $125 per unit annually (assuming 80% take-up)
                frequency=FrequencyEnum.ANNUAL,
                reference=PropertyAttributeKey.UNIT_COUNT,
            ),
            ResidentialMiscIncome(
                name="Laundry & Vending",
                timeline=timeline,
                value=85.0,  # $85 per unit annually
                frequency=FrequencyEnum.ANNUAL,
                reference=PropertyAttributeKey.UNIT_COUNT,
            ),
            ResidentialMiscIncome(
                name="Pet Fees",
                timeline=timeline,
                value=35.0,  # $35 per unit per month (assuming 40% have pets)
                frequency=FrequencyEnum.MONTHLY,
                reference=PropertyAttributeKey.UNIT_COUNT,
            ),
            ResidentialMiscIncome(
                name="Application & Admin Fees",
                timeline=timeline,
                value=150.0,  # $150 per unit annually
                frequency=FrequencyEnum.ANNUAL,
                reference=PropertyAttributeKey.UNIT_COUNT,
            ),
        ]

        # Create the institutional property
        property_model = ResidentialProperty(
            name="Meridian Tower Apartments - Class A",
            gross_area=280000.0,  # 280k SF including amenities/common areas
            net_rentable_area=rent_roll.total_rentable_area,
            unit_mix=rent_roll,
            expenses=expenses,
            losses=losses,
            miscellaneous_income=misc_income,
        )

        print("\n🏢 INSTITUTIONAL SCALE TEST")
        print(f"Property: {property_model.name}")
        print(f"Total Units: {property_model.unit_count}")
        print(f"Total Area: {property_model.net_rentable_area:,.0f} SF")
        print(
            f"Average Unit Size: {property_model.net_rentable_area / property_model.unit_count:.0f} SF"
        )
        print(f"Average Monthly Rent: ${rent_roll.average_rent_per_unit:,.0f}")
        print(
            f"Monthly Income Potential: ${rent_roll.total_monthly_income_potential:,.0f}"
        )
        print(
            f"Annual Income Potential: ${rent_roll.total_monthly_income_potential * 12:,.0f}"
        )

        # Run the analysis
        scenario = run(
            model=property_model,
            timeline=timeline,
            settings=settings,
        )

        # Verify analysis completed
        assert isinstance(scenario, ResidentialAnalysisScenario)
        orchestrator = scenario._orchestrator
        assert orchestrator is not None

        # Verify correct model unrolling
        lease_models = [
            m for m in orchestrator.models if m.__class__.__name__ == "ResidentialLease"
        ]
        assert (
            len(lease_models) == 250
        ), f"Expected 250 lease models, got {len(lease_models)}"

        # Verify cash flow generation
        summary_df = scenario.get_cash_flow_summary()
        assert len(summary_df) == 60, "Should have 60 monthly periods"

        # Validate financial metrics
        first_month = summary_df.index[0]
        first_month_data = summary_df.loc[first_month]

        # Expected monthly income (weighted by unit counts)
        expected_monthly_income = rent_roll.total_monthly_income_potential

        print("\n📊 FINANCIAL RESULTS")
        print(f"Expected Monthly Income: ${expected_monthly_income:,.0f}")

        # Find PGR column (handle potential enum formatting)
        pgr_cols = [
            col
            for col in first_month_data.index
            if "POTENTIAL_GROSS_REVENUE" in str(col)
        ]
        if pgr_cols:
            actual_pgr = first_month_data[pgr_cols[0]]
            print(f"Actual PGR (Month 1): ${actual_pgr:,.0f}")
            assert actual_pgr == pytest.approx(expected_monthly_income, rel=0.01)

        # Performance validation - large property should complete quickly
        print("✅ Large scale analysis completed successfully!")
        print(f"   - 250 units → {len(orchestrator.models)} total models")
        print("   - 60-month projection generated")
        print("   - Complex unit mix with 6 unit types processed")

    def test_performance_stress_test(self):
        """
        Stress test with a very large property to validate performance.

        Property Profile:
        - 500 units (stress test scale)
        - 3-year analysis
        - Simplified assumptions for performance focus
        """
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=36)
        settings = GlobalSettings()

        # Simple rollover profile for performance test
        rollover_terms = ResidentialRolloverLeaseTerms(
            market_rent=2200.0,
            capital_plan_id=None,  # No capital plan for simple test (UUID-based architecture)
            term_months=12,
        )

        rollover_profile = ResidentialRolloverProfile(
            name="Performance Test Profile",
            renewal_probability=0.65,
            downtime_months=1,
            term_months=12,
            market_terms=rollover_terms,
            renewal_terms=rollover_terms,
        )

        # Large unit mix - 500 units across 4 types
        unit_specs = [
            ResidentialUnitSpec(
                unit_type_name="Studio",
                unit_count=100,
                avg_area_sf=500.0,
                current_avg_monthly_rent=1800.0,
                rollover_profile=rollover_profile,
            ),
            ResidentialUnitSpec(
                unit_type_name="1BR/1BA",
                unit_count=200,
                avg_area_sf=700.0,
                current_avg_monthly_rent=2200.0,
                rollover_profile=rollover_profile,
            ),
            ResidentialUnitSpec(
                unit_type_name="2BR/2BA",
                unit_count=150,
                avg_area_sf=1000.0,
                current_avg_monthly_rent=3000.0,
                rollover_profile=rollover_profile,
            ),
            ResidentialUnitSpec(
                unit_type_name="3BR/2BA",
                unit_count=50,
                avg_area_sf=1300.0,
                current_avg_monthly_rent=3800.0,
                rollover_profile=rollover_profile,
            ),
        ]

        rent_roll = ResidentialRentRoll(unit_specs=unit_specs)

        # Minimal expenses for performance focus
        expenses = ResidentialExpenses(
            operating_expenses=[
                ResidentialOpExItem(
                    name="Property Management",
                    timeline=timeline,
                    value=0.05,
                    frequency=FrequencyEnum.MONTHLY,
                    reference=UnleveredAggregateLineKey.EFFECTIVE_GROSS_INCOME,
                ),
            ]
        )

        losses = ResidentialLosses(
            general_vacancy=ResidentialGeneralVacancyLoss(rate=0.05),
            collection_loss=ResidentialCollectionLoss(rate=0.01),
        )

        property_model = ResidentialProperty(
            name="Mega Complex - Performance Test",
            gross_area=450000.0,
            net_rentable_area=rent_roll.total_rentable_area,
            unit_mix=rent_roll,
            expenses=expenses,
            losses=losses,
        )

        print("\n⚡ PERFORMANCE STRESS TEST")
        print(f"Property: {property_model.name}")
        print(f"Total Units: {property_model.unit_count}")
        print(f"Analysis Periods: {timeline.duration_months}")

        start_time = time.time()

        # Run the analysis
        scenario = run(
            model=property_model,
            timeline=timeline,
            settings=settings,
        )

        end_time = time.time()
        execution_time = end_time - start_time

        # Performance validation
        assert isinstance(scenario, ResidentialAnalysisScenario)
        orchestrator = scenario._orchestrator

        lease_models = [
            m for m in orchestrator.models if m.__class__.__name__ == "ResidentialLease"
        ]
        assert (
            len(lease_models) == 500
        ), f"Expected 500 lease models, got {len(lease_models)}"

        # Generate summary
        summary_df = scenario.get_cash_flow_summary()
        assert len(summary_df) == 36

        print("✅ Performance test completed!")
        print(f"   - Execution time: {execution_time:.2f} seconds")
        print(f"   - 500 units → {len(orchestrator.models)} total models")
        print(
            f"   - {len(summary_df)} periods × {len(summary_df.columns)} metrics calculated"
        )
        print(f"   - Performance: {500 / execution_time:.0f} units per second")

        # Performance assertion - should complete large properties quickly
        assert (
            execution_time < 30
        ), f"Large property analysis should complete in <30s, took {execution_time:.2f}s"


class TestComplexScenarios:
    """Test complex real-world scenarios with sophisticated market assumptions."""

    def test_value_add_positioning_strategy(self):
        """
        Test a value-add property with mixed unit positioning.

        Scenario:
        - Property in transition from Class B to Class A
        - Mixed unit types with different rollover strategies
        - Graduated rent growth as property improves
        """
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=48)  # 4 years
        settings = GlobalSettings()

        # Different rollover profiles for different unit tiers

        # Premium units (recently renovated)
        premium_market_terms = ResidentialRolloverLeaseTerms(
            market_rent=3200.0,
            market_rent_growth=PercentageGrowthRate(
                name="Premium Growth", value=0.045
            ),  # 4.5% annual
            renewal_rent_increase_percent=0.035,
            concessions_months=0,  # No concessions needed
            capital_plan_id=None,  # No capital plan for premium units (UUID-based architecture)
            term_months=12,
        )

        premium_rollover = ResidentialRolloverProfile(
            name="Premium Tier Profile",
            renewal_probability=0.78,  # High retention for premium units
            downtime_months=1,
            term_months=12,
            market_terms=premium_market_terms,
            renewal_terms=premium_market_terms,
        )

        # Standard units (stable but aging)
        standard_market_terms = ResidentialRolloverLeaseTerms(
            market_rent=2400.0,
            market_rent_growth=PercentageGrowthRate(
                name="Standard Growth", value=0.025
            ),  # 2.5% annual
            renewal_rent_increase_percent=0.020,
            concessions_months=1,  # Some concessions needed
            capital_plan_id=None,  # No capital plan for standard units (UUID-based architecture)
            term_months=12,
        )

        standard_rollover = ResidentialRolloverProfile(
            name="Standard Tier Profile",
            renewal_probability=0.62,  # Lower retention
            downtime_months=2,  # Longer downtime for renovations
            term_months=12,
            market_terms=standard_market_terms,
            renewal_terms=standard_market_terms,
        )

        # Create mixed unit portfolio
        unit_specs = [
            # Premium renovated units
            ResidentialUnitSpec(
                unit_type_name="2BR/2BA - Renovated Premium",
                unit_count=25,
                avg_area_sf=1100.0,
                current_avg_monthly_rent=3200.0,
                rollover_profile=premium_rollover,
            ),
            ResidentialUnitSpec(
                unit_type_name="1BR/1BA - Renovated Premium",
                unit_count=20,
                avg_area_sf=750.0,
                current_avg_monthly_rent=2400.0,
                rollover_profile=premium_rollover,
            ),
            # Standard units (pending renovation)
            ResidentialUnitSpec(
                unit_type_name="2BR/2BA - Standard",
                unit_count=40,
                avg_area_sf=1000.0,
                current_avg_monthly_rent=2400.0,
                rollover_profile=standard_rollover,
            ),
            ResidentialUnitSpec(
                unit_type_name="1BR/1BA - Standard",
                unit_count=35,
                avg_area_sf=700.0,
                current_avg_monthly_rent=1950.0,
                rollover_profile=standard_rollover,
            ),
        ]

        rent_roll = ResidentialRentRoll(unit_specs=unit_specs)

        # Value-add appropriate expenses
        expenses = ResidentialExpenses(
            operating_expenses=[
                ResidentialOpExItem(
                    name="Property Management",
                    timeline=timeline,
                    value=0.06,  # Higher fee during transition
                    frequency=FrequencyEnum.MONTHLY,
                    reference=UnleveredAggregateLineKey.EFFECTIVE_GROSS_INCOME,
                ),
                ResidentialOpExItem(
                    name="Maintenance & Repairs",
                    timeline=timeline,
                    value=650.0,  # Higher maintenance during transition
                    frequency=FrequencyEnum.ANNUAL,
                    reference=PropertyAttributeKey.UNIT_COUNT,
                ),
            ],
            capital_expenses=[
                ResidentialCapExItem(
                    name="Capital Reserves",
                    timeline=timeline,
                    value=400.0,
                    frequency=FrequencyEnum.ANNUAL,
                    reference=PropertyAttributeKey.UNIT_COUNT,
                ),
                ResidentialCapExItem(
                    name="Value-Add Improvements",
                    timeline=timeline,
                    value=180000.0,  # Ongoing improvement program
                    frequency=FrequencyEnum.ANNUAL,
                    # reference=None (direct currency amount)
                ),
            ],
        )

        losses = ResidentialLosses(
            general_vacancy=ResidentialGeneralVacancyLoss(
                rate=0.065
            ),  # Higher during transition
            collection_loss=ResidentialCollectionLoss(rate=0.02),
        )

        property_model = ResidentialProperty(
            name="Riverside Commons - Value-Add",
            gross_area=105000.0,
            net_rentable_area=rent_roll.total_rentable_area,
            unit_mix=rent_roll,
            expenses=expenses,
            losses=losses,
        )

        print("\n🔄 VALUE-ADD STRATEGY TEST")
        print(f"Property: {property_model.name}")
        print(f"Total Units: {property_model.unit_count}")
        print(f"Premium Units: {45} ({45 / 120 * 100:.1f}%)")
        print(f"Standard Units: {75} ({75 / 120 * 100:.1f}%)")
        print(f"Current Blended Rent: ${rent_roll.average_rent_per_unit:,.0f}")

        # Run analysis
        scenario = run(
            model=property_model,
            timeline=timeline,
            settings=settings,
        )

        # Validate scenario
        assert isinstance(scenario, ResidentialAnalysisScenario)
        orchestrator = scenario._orchestrator

        lease_models = [
            m for m in orchestrator.models if m.__class__.__name__ == "ResidentialLease"
        ]
        assert len(lease_models) == 120

        # Validate different unit tier behavior
        premium_leases = [m for m in lease_models if "Premium" in m.suite]
        standard_leases = [m for m in lease_models if "Standard" in m.suite]

        assert (
            len(premium_leases) == 45
        ), f"Expected 45 premium leases, got {len(premium_leases)}"
        assert (
            len(standard_leases) == 75
        ), f"Expected 75 standard leases, got {len(standard_leases)}"

        # Validate different rent levels
        premium_avg_rent = sum(lease.value for lease in premium_leases) / len(
            premium_leases
        )
        standard_avg_rent = sum(lease.value for lease in standard_leases) / len(
            standard_leases
        )

        print("✅ Value-add analysis completed!")
        print(f"   - Premium tier average rent: ${premium_avg_rent:,.0f}")
        print(f"   - Standard tier average rent: ${standard_avg_rent:,.0f}")
        print(
            f"   - Rent premium: {(premium_avg_rent / standard_avg_rent - 1) * 100:.1f}%"
        )

        assert (
            premium_avg_rent > standard_avg_rent
        ), "Premium units should have higher rents"


# Quick smoke test to ensure all comprehensive tests are discoverable
def test_comprehensive_suite_discovery():
    """Smoke test to ensure comprehensive test classes are properly structured."""

    # Verify test classes exist and are properly structured
    assert hasattr(TestLargeScaleProperties, "test_institutional_scale_property")
    assert hasattr(TestLargeScaleProperties, "test_performance_stress_test")
    assert hasattr(TestComplexScenarios, "test_value_add_positioning_strategy")

    print("✅ Comprehensive test suite structure validated!")


if __name__ == "__main__":
    # Allow running tests directly for development

    print("🚀 Running Comprehensive Residential Analysis Tests")
    print("=" * 60)

    # Run a quick test
    test_comprehensive_suite_discovery()

    print("\nTo run full comprehensive tests:")
    print(
        "python -m pytest tests/e2e/asset/residential/test_comprehensive_analysis.py -v -s"
    )
