# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Large Scale Rolling Renovation Performance Test

Tests the performance and correctness of rolling renovation scenarios at scale.
This addresses concerns about memory usage, processing time, and correctness
with large properties (1000+ units).
"""

import gc
import os
import time
from datetime import date
from uuid import uuid4

import psutil
import pytest

from performa.analysis import run
from performa.asset.residential import (
    ResidentialAbsorptionPlan,
    ResidentialExpenses,
    ResidentialLosses,
    ResidentialOpExItem,
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


class TestLargeScaleRollingRenovation:
    """Test rolling renovation at various scales."""

    def _create_value_add_property(self, unit_count: int, name_suffix: str = ""):
        """Create a value-add property with specified unit count."""

        # Create absorption plan for post-renovation
        plan_id = uuid4()
        absorption_plan = ResidentialAbsorptionPlan(
            uid=plan_id,
            name=f"Renovation Plan {name_suffix}",
            start_date_anchor=StartDateAnchorEnum.ANALYSIS_START,
            pace=FixedQuantityPace(
                quantity=min(unit_count, 10), unit="Units", frequency_months=1
            ),
            leasing_assumptions=ResidentialDirectLeaseTerms(
                monthly_rent=2500.0,  # Premium rent
                stabilized_renewal_probability=0.8,
                stabilized_downtime_months=1,
            ),
            stabilized_expenses=ResidentialExpenses(operating_expenses=[]),
            stabilized_losses=ResidentialLosses(
                general_vacancy={"rate": 0.05, "method": "Potential Gross Revenue"},
                credit_loss={"rate": 0.02, "basis": "Potential Gross Revenue"},
            ),
            stabilized_misc_income=[],
        )

        # Create rollover profile for value-add
        rollover_profile = ResidentialRolloverProfile(
            name=f"Value-Add Profile {name_suffix}",
            term_months=12,
            renewal_probability=0.0,
            downtime_months=2,  # Renovation downtime
            market_terms=ResidentialRolloverLeaseTerms(
                market_rent=2200.0, term_months=12
            ),
            renewal_terms=ResidentialRolloverLeaseTerms(
                market_rent=2100.0, term_months=12
            ),
            upon_expiration=UponExpirationEnum.REABSORB,
            target_absorption_plan_id=plan_id,
        )

        # Create unit specs (stagger lease start dates for rolling effect)
        unit_specs = []
        units_per_month = max(1, unit_count // 24)  # Spread over 24 months

        for i in range(unit_count):
            month_offset = (i // units_per_month) % 24
            start_date = date(2023, 1 + (month_offset % 12), 1)
            if month_offset >= 12:
                start_date = date(2024, 1 + (month_offset % 12), 1)

            unit_spec = ResidentialUnitSpec(
                unit_type_name=f"Unit-{i + 1}",
                unit_count=1,
                avg_area_sf=800.0,
                current_avg_monthly_rent=2000.0,
                rollover_profile=rollover_profile,
                lease_start_date=start_date,
            )
            unit_specs.append(unit_spec)

        # Create capital plan for renovations
        renovation_timeline = Timeline(start_date=date(2024, 1, 1), duration_months=36)
        capital_plan = CapitalPlan(
            name=f"Renovation Program {name_suffix}",
            capital_items=[
                CapitalItem(
                    name=f"Unit Renovations {name_suffix}",
                    reference=PropertyAttributeKey.UNIT_COUNT,
                    value=15000.0,  # $15k per unit
                    timeline=renovation_timeline,
                )
            ],
        )

        # Create operating expenses
        expenses = ResidentialExpenses(
            operating_expenses=[
                ResidentialOpExItem(
                    name="Property Management",
                    reference=PropertyAttributeKey.UNIT_COUNT,
                    value=100.0,  # $100/unit/month
                    timeline=renovation_timeline,
                ),
                ResidentialOpExItem(
                    name="Maintenance",
                    reference=PropertyAttributeKey.UNIT_COUNT,
                    value=50.0,  # $50/unit/month
                    timeline=renovation_timeline,
                ),
            ]
        )

        return ResidentialProperty(
            name=f"Large Scale Property {name_suffix} ({unit_count} units)",
            address=Address(
                street=f"123 Scale Test Blvd {name_suffix}",
                city="Test City",
                state="CA",
                zip_code="90210",
                country="USA",
            ),
            gross_area=float(unit_count * 800),
            net_rentable_area=float(unit_count * 800),
            unit_mix=ResidentialRentRoll(unit_specs=unit_specs),
            capital_plans=[capital_plan],
            absorption_plans=[absorption_plan],
            expenses=expenses,
            losses=ResidentialLosses(
                general_vacancy={"rate": 0.05, "method": "Potential Gross Revenue"},
                credit_loss={"rate": 0.02, "basis": "Potential Gross Revenue"},
            ),
            miscellaneous_income=[],
        )

    def _measure_performance(self, unit_count: int):
        """Measure performance metrics for given unit count."""

        # Measure memory before
        process = psutil.Process(os.getpid())
        memory_before = process.memory_info().rss / 1024 / 1024  # MB

        # Create property and run analysis
        start_time = time.time()

        property_model = self._create_value_add_property(
            unit_count, f"Scale-{unit_count}"
        )
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=48)
        settings = GlobalSettings()

        creation_time = time.time()

        scenario = run(model=property_model, timeline=timeline, settings=settings)
        cash_flow_summary = scenario.summary_df

        analysis_time = time.time()

        # Basic validation
        assert not cash_flow_summary.empty
        pgr_series = cash_flow_summary["Potential Gross Revenue"]
        assert len(pgr_series) > 0

        validation_time = time.time()

        # Measure memory after
        memory_after = process.memory_info().rss / 1024 / 1024  # MB

        return {
            "unit_count": unit_count,
            "creation_duration": creation_time - start_time,
            "analysis_duration": analysis_time - creation_time,
            "validation_duration": validation_time - analysis_time,
            "total_duration": validation_time - start_time,
            "memory_before_mb": memory_before,
            "memory_after_mb": memory_after,
            "memory_delta_mb": memory_after - memory_before,
            "revenue_months": len(pgr_series),
            "max_monthly_revenue": pgr_series.max(),
            "total_revenue": pgr_series.sum(),
        }

    @pytest.mark.parametrize("unit_count", [10, 25, 50, 100, 250])
    def test_scale_performance(self, unit_count):
        """Test performance at various scales."""

        metrics = self._measure_performance(unit_count)

        print(f"\n SCALE TEST RESULTS - {unit_count} Units:")
        print(f"   Creation Time: {metrics['creation_duration']:.2f}s")
        print(f"   Analysis Time: {metrics['analysis_duration']:.2f}s")
        print(f"   Total Time: {metrics['total_duration']:.2f}s")
        print(f"   Memory Delta: {metrics['memory_delta_mb']:.1f} MB")
        print(f"   Max Monthly Revenue: ${metrics['max_monthly_revenue']:,.0f}")

        # Performance assertions
        assert metrics["total_duration"] < 60.0, (
            f"Analysis took too long: {metrics['total_duration']:.2f}s"
        )
        assert metrics["memory_delta_mb"] < 500.0, (
            f"Memory usage too high: {metrics['memory_delta_mb']:.1f} MB"
        )

        # Financial validation
        expected_max_revenue = unit_count * 2500.0  # All units at premium rent
        revenue_ratio = metrics["max_monthly_revenue"] / expected_max_revenue

        assert 0.7 <= revenue_ratio <= 1.1, (
            f"Revenue seems incorrect: {revenue_ratio:.2%} of expected"
        )

    def test_very_large_scale_stress_test(self):
        """Stress test with 1000+ units (if system can handle it)."""

        unit_count = 1000

        try:
            print(f"\n🚀 STRESS TEST - {unit_count} Units")
            metrics = self._measure_performance(unit_count)

            print(f"    SUCCESS!")
            print(f"   Creation Time: {metrics['creation_duration']:.2f}s")
            print(f"   Analysis Time: {metrics['analysis_duration']:.2f}s")
            print(f"   Total Time: {metrics['total_duration']:.2f}s")
            print(f"   Memory Delta: {metrics['memory_delta_mb']:.1f} MB")
            print(f"   Max Monthly Revenue: ${metrics['max_monthly_revenue']:,.0f}")

            # Relaxed assertions for stress test
            assert metrics["total_duration"] < 300.0, "Stress test took over 5 minutes"
            assert metrics["memory_delta_mb"] < 2000.0, "Memory usage exceeded 2GB"

        except (MemoryError, TimeoutError) as e:
            pytest.skip(f"System cannot handle {unit_count} units: {e}")
        except Exception as e:
            pytest.fail(f"Unexpected error with {unit_count} units: {e}")

    def test_rolling_completion_rate_at_scale(self):
        """Test that rolling renovation completes properly at scale."""

        unit_count = 100
        property_model = self._create_value_add_property(unit_count, "Completion-Test")
        timeline = Timeline(
            start_date=date(2024, 1, 1), duration_months=60
        )  # Longer timeline
        settings = GlobalSettings()

        scenario = run(model=property_model, timeline=timeline, settings=settings)
        cash_flow_summary = scenario.summary_df

        pgr_series = cash_flow_summary["Potential Gross Revenue"]

        # Calculate completion metrics
        max_revenue = pgr_series.max()
        final_12_months_avg = pgr_series.tail(12).mean()

        expected_max_revenue = unit_count * 2500.0  # All units at premium
        completion_rate = final_12_months_avg / expected_max_revenue

        print(f"\n COMPLETION ANALYSIS - {unit_count} Units:")
        print(f"   Expected Max Revenue: ${expected_max_revenue:,.0f}")
        print(f"   Actual Max Revenue: ${max_revenue:,.0f}")
        print(f"   Final 12-Month Avg: ${final_12_months_avg:,.0f}")
        print(f"   Completion Rate: {completion_rate:.1%}")

        # Should achieve high completion rate
        assert completion_rate >= 0.85, f"Low completion rate: {completion_rate:.1%}"

        # Should show value creation
        initial_revenue = pgr_series.iloc[0]
        value_creation = (final_12_months_avg - initial_revenue) / initial_revenue
        print(f"   Value Creation: {value_creation:.1%}")

        assert value_creation >= 0.15, f"Low value creation: {value_creation:.1%}"


class TestScalabilityLimits:
    """Test system limits and edge cases at scale."""

    def test_many_absorption_plans(self):
        """Test property with many different absorption plans."""

        # Create multiple absorption plans
        absorption_plans = []
        for i in range(10):
            plan_id = uuid4()
            plan = ResidentialAbsorptionPlan(
                uid=plan_id,
                name=f"Plan-{i + 1}",
                start_date_anchor=StartDateAnchorEnum.ANALYSIS_START,
                pace=FixedQuantityPace(quantity=5, unit="Units", frequency_months=1),
                leasing_assumptions=ResidentialDirectLeaseTerms(
                    monthly_rent=2400.0 + (i * 50),  # Varying rents
                    stabilized_renewal_probability=0.75,
                    stabilized_downtime_months=1,
                ),
                stabilized_expenses=ResidentialExpenses(operating_expenses=[]),
                stabilized_losses=ResidentialLosses(
                    general_vacancy={"rate": 0.05, "method": "Potential Gross Revenue"},
                    credit_loss={"rate": 0.02, "basis": "Potential Gross Revenue"},
                ),
                stabilized_misc_income=[],
            )
            absorption_plans.append(plan)

        # Create units that target different plans
        unit_specs = []
        for i in range(50):
            plan_index = i % len(absorption_plans)
            target_plan_id = absorption_plans[plan_index].uid

            rollover_profile = ResidentialRolloverProfile(
                name=f"Profile-{i + 1}",
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
                target_absorption_plan_id=target_plan_id,
            )

            unit_spec = ResidentialUnitSpec(
                unit_type_name=f"Multi-Plan-Unit-{i + 1}",
                unit_count=1,
                avg_area_sf=800.0,
                current_avg_monthly_rent=2000.0,
                rollover_profile=rollover_profile,
                lease_start_date=date(2023, 1 + (i % 12), 1),
            )
            unit_specs.append(unit_spec)

        property_model = ResidentialProperty(
            name="Multi-Plan Property",
            address=Address(
                street="123 MultiPlan St",
                city="Test",
                state="CA",
                zip_code="90210",
                country="USA",
            ),
            gross_area=40000.0,
            net_rentable_area=40000.0,
            unit_mix=ResidentialRentRoll(unit_specs=unit_specs),
            capital_plans=[],
            absorption_plans=absorption_plans,
            expenses=ResidentialExpenses(operating_expenses=[]),
            losses=ResidentialLosses(
                general_vacancy={"rate": 0.05, "method": "Potential Gross Revenue"},
                credit_loss={"rate": 0.02, "basis": "Potential Gross Revenue"},
            ),
            miscellaneous_income=[],
        )

        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=36)
        settings = GlobalSettings()

        # Should handle multiple plans without issues
        scenario = run(model=property_model, timeline=timeline, settings=settings)
        cash_flow_summary = scenario.summary_df

        assert not cash_flow_summary.empty
        pgr_series = cash_flow_summary["Potential Gross Revenue"]

        # Should show revenue growth from transformations
        initial_revenue = pgr_series.iloc[0]
        final_revenue = pgr_series.iloc[-1]

        assert final_revenue > initial_revenue, "Should show revenue growth"

        print(f"\n🏢 MULTI-PLAN TEST:")
        print(f"   Plans: {len(absorption_plans)}")
        print(f"   Units: {len(unit_specs)}")
        print(f"   Initial Revenue: ${initial_revenue:,.0f}")
        print(f"   Final Revenue: ${final_revenue:,.0f}")
        print(f"   Growth: {((final_revenue / initial_revenue) - 1):.1%}")

    def test_memory_efficiency(self):
        """Test memory efficiency by creating and destroying large scenarios."""

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        memories = []

        # Create and destroy several large scenarios
        for i in range(5):
            gc.collect()  # Force garbage collection

            property_model = self._create_value_add_property(200, f"Memory-{i}")
            timeline = Timeline(start_date=date(2024, 1, 1), duration_months=24)
            settings = GlobalSettings()

            scenario = run(model=property_model, timeline=timeline, settings=settings)
            cash_flow_summary = scenario.summary_df

            # Validate it works
            assert not cash_flow_summary.empty

            current_memory = process.memory_info().rss / 1024 / 1024  # MB
            memories.append(current_memory)

            # Clean up references
            del property_model, scenario, cash_flow_summary

        gc.collect()  # Final cleanup
        final_memory = process.memory_info().rss / 1024 / 1024  # MB

        print(f"\n💾 MEMORY EFFICIENCY TEST:")
        print(f"   Initial Memory: {initial_memory:.1f} MB")
        print(f"   Peak Memory: {max(memories):.1f} MB")
        print(f"   Final Memory: {final_memory:.1f} MB")
        print(f"   Memory Growth: {final_memory - initial_memory:.1f} MB")

        # Should not have significant memory leaks
        memory_growth = final_memory - initial_memory
        assert memory_growth < 100.0, (
            f"Possible memory leak: {memory_growth:.1f} MB growth"
        )

    def _create_value_add_property(self, unit_count: int, name_suffix: str = ""):
        """Helper method to create value-add property (duplicated for memory test)."""

        plan_id = uuid4()
        absorption_plan = ResidentialAbsorptionPlan(
            uid=plan_id,
            name=f"Memory Test Plan {name_suffix}",
            start_date_anchor=StartDateAnchorEnum.ANALYSIS_START,
            pace=FixedQuantityPace(
                quantity=min(unit_count, 10), unit="Units", frequency_months=1
            ),
            leasing_assumptions=ResidentialDirectLeaseTerms(
                monthly_rent=2500.0,
                stabilized_renewal_probability=0.8,
                stabilized_downtime_months=1,
            ),
            stabilized_expenses=ResidentialExpenses(operating_expenses=[]),
            stabilized_losses=ResidentialLosses(
                general_vacancy={"rate": 0.05, "method": "Potential Gross Revenue"},
                credit_loss={"rate": 0.02, "basis": "Potential Gross Revenue"},
            ),
            stabilized_misc_income=[],
        )

        rollover_profile = ResidentialRolloverProfile(
            name=f"Memory Test Profile {name_suffix}",
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

        unit_specs = []
        for i in range(unit_count):
            unit_spec = ResidentialUnitSpec(
                unit_type_name=f"Memory-Unit-{i + 1}",
                unit_count=1,
                avg_area_sf=800.0,
                current_avg_monthly_rent=2000.0,
                rollover_profile=rollover_profile,
                lease_start_date=date(2023, 1 + (i % 12), 1),
            )
            unit_specs.append(unit_spec)

        return ResidentialProperty(
            name=f"Memory Test Property {name_suffix}",
            address=Address(
                street=f"123 Memory St {name_suffix}",
                city="Test",
                state="CA",
                zip_code="90210",
                country="USA",
            ),
            gross_area=float(unit_count * 800),
            net_rentable_area=float(unit_count * 800),
            unit_mix=ResidentialRentRoll(unit_specs=unit_specs),
            capital_plans=[],
            absorption_plans=[absorption_plan],
            expenses=ResidentialExpenses(operating_expenses=[]),
            losses=ResidentialLosses(
                general_vacancy={"rate": 0.05, "method": "Potential Gross Revenue"},
                credit_loss={"rate": 0.02, "basis": "Potential Gross Revenue"},
            ),
            miscellaneous_income=[],
        )
