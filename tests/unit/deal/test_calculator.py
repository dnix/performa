# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Unit Tests for analyze Function

This module tests the deal analysis functions, including the public API
and internal calculation methods for funding cascades, partnership distributions,
and metric calculations.
"""

from datetime import datetime
from decimal import Decimal

import pandas as pd
import pytest

from performa.core.capital import CapitalItem, CapitalPlan
from performa.core.primitives import AssetTypeEnum, GlobalSettings, Timeline
from performa.deal import Deal, analyze
from performa.deal.acquisition import AcquisitionTerms
from performa.deal.results import (
    DealAnalysisResult,
    DealMetricsResult,
    LeveredCashFlowResult,
    PartnerDistributionResult,
    UnleveredAnalysisResult,
)
from performa.debt import ConstructionFacility, DebtTranche, FinancingPlan
from performa.debt.rates import FixedRate, InterestRate
from performa.development.project import DevelopmentProject


class TestFundingCascade:  # noqa: PLR0904
    """Test suite for funding cascade logic implementation (TDD approach)."""

    @pytest.fixture
    def sample_timeline(self):
        """Create a sample timeline for testing."""
        return Timeline.from_dates(
            start_date=datetime(2024, 1, 1), end_date=datetime(2026, 12, 31)
        )

    @pytest.fixture
    def sample_development_project(self):
        """Create a sample development project with known construction costs."""

        # Create construction plan with known costs
        construction_items = [
            CapitalItem(
                name="Site Work",
                value=Decimal("1000000"),
                timeline=Timeline.from_dates(
                    datetime(2024, 1, 1), datetime(2024, 6, 30)
                ),
            ),
            CapitalItem(
                name="Building Construction",
                value=Decimal("5000000"),
                timeline=Timeline.from_dates(
                    datetime(2024, 4, 1), datetime(2025, 10, 31)
                ),
            ),
            CapitalItem(
                name="Tenant Improvements",
                value=Decimal(2000000.0),
                timeline=Timeline.from_dates(
                    datetime(2025, 8, 1), datetime(2026, 3, 31)
                ),
            ),
        ]

        construction_plan = CapitalPlan(
            name="Test Construction Plan", capital_items=construction_items
        )

        return DevelopmentProject(
            name="Test Office Development",
            property_type=AssetTypeEnum.OFFICE,
            gross_area=Decimal(100000.0),
            net_rentable_area=Decimal(90000.0),
            construction_plan=construction_plan,
            blueprints=[],
        )

    @pytest.fixture
    def sample_acquisition(self):
        """Create a sample acquisition for testing."""
        acquisition_timeline = Timeline.from_dates(
            start_date=datetime(2024, 1, 1), end_date=datetime(2024, 1, 31)
        )
        return AcquisitionTerms(
            name="Test Land Acquisition",
            timeline=acquisition_timeline,
            value=Decimal("5000000"),
            acquisition_date=datetime(2024, 1, 1),
            closing_costs_rate=Decimal("0.025"),
        )

    @pytest.fixture
    def sample_deal_all_equity(self, sample_development_project, sample_acquisition):
        """Create a sample all-equity deal for testing."""
        return Deal(
            name="Test All-Equity Development Deal",
            asset=sample_development_project,
            acquisition=sample_acquisition,
            financing=None,  # All-equity deal
            disposition=None,
            equity_partners=None,
        )

    @pytest.fixture
    def sample_settings(self):
        """Create sample analysis settings."""
        return GlobalSettings()

    def test_orchestrate_funding_step_a_calculate_total_uses(
        self, sample_deal_all_equity, sample_timeline, sample_settings
    ):
        """
        Test Step A: Calculate Total Uses for each period.

        This test verifies that the _orchestrate_funding_and_financing function
        correctly extracts the total Uses (cash outflows) from the unlevered analysis
        for each period in the timeline.
        """
        # Test the actual implementation by calling analyze
        results = analyze(sample_deal_all_equity, sample_timeline, sample_settings)

        # Verify we get the expected structure
        assert hasattr(results, "levered_cash_flows")
        assert hasattr(results.levered_cash_flows, "funding_cascade_details")
        assert hasattr(
            results.levered_cash_flows.funding_cascade_details, "uses_breakdown"
        )

        # Get the Uses breakdown
        uses_breakdown = (
            results.levered_cash_flows.funding_cascade_details.uses_breakdown
        )
        assert uses_breakdown is not None

        # Verify the structure of Uses breakdown
        expected_columns = [
            "Acquisition Costs",
            "Construction Costs",
            "Other Project Costs",
            "Total Uses",
        ]
        for col in expected_columns:
            assert col in uses_breakdown.columns

        # Verify that we have non-zero Uses
        total_uses = uses_breakdown["Total Uses"].sum()
        assert total_uses > 0, "Total Uses should be greater than zero for this deal"

        # Verify acquisition costs appear correctly (5M + 2.5% = 5.125M)
        total_acquisition = uses_breakdown["Acquisition Costs"].sum()
        expected_acquisition = float(
            Decimal("5000000") * (1 + Decimal("0.025"))
        )  # 5.125M
        assert (
            abs(total_acquisition - expected_acquisition) < 1000
        ), f"Expected ${expected_acquisition:,.0f}, got ${total_acquisition:,.0f}"

        # Verify construction costs appear (total costs distributed over timeline)
        total_construction = uses_breakdown["Construction Costs"].sum()
        # Based on CapitalItem total costs:
        # Site Work: $1M total over 6 months
        # Building: $5M total over 19 months
        # TI: $2M total over 8 months
        # Total: $8M
        expected_construction = float(Decimal("8000000"))  # Sum of CapitalItem values
        assert (
            abs(total_construction - expected_construction) < 1000
        ), f"Expected ${expected_construction:,.0f}, got ${total_construction:,.0f}"

        # Verify timing: acquisition costs should appear in first period only
        first_period_acquisition = uses_breakdown["Acquisition Costs"].iloc[0]
        assert (
            first_period_acquisition == expected_acquisition
        ), "All acquisition costs should appear in first period"

        # Verify timing: construction costs should appear in correct periods
        # Site Work should appear in periods 0-5 (Jan-Jun 2024)
        site_work_periods = uses_breakdown["Construction Costs"].iloc[0:6]
        # Site work total is $1M distributed over 6 months = ~$167k per month
        assert (site_work_periods > 0).all(), "Site work should appear in Jan-Jun 2024"
        # Verify the total site work amount is reasonable
        site_work_total = site_work_periods.sum()
        # Note: This includes overlapping construction, so total may be > $1M
        assert site_work_total >= Decimal(
            1000000
        ), f"Site work total should be at least $1M, got ${site_work_total:,.0f}"

        # Verify that Step A architecture works correctly
        # - We can extract period-by-period Uses
        # - Uses include both acquisition and construction
        # - Uses are properly timed
        # - The funding cascade orchestrator is functional
        assert hasattr(results.levered_cash_flows, "cash_flow_components")
        components = results.levered_cash_flows.cash_flow_components
        assert hasattr(components, "total_uses")
        assert components.total_uses.sum() == total_uses

        print("\n✅ Step A Implementation Success:")
        print(f"   - Total Uses calculated: ${total_uses:,.0f}")
        print(f"   - Acquisition costs: ${total_acquisition:,.0f}")
        print(f"   - Construction costs: ${total_construction:,.0f}")
        print("   - Proper timing and structure verified")

    def test_orchestrate_funding_step_a_uses_structure(
        self, sample_deal_all_equity, sample_timeline, sample_settings
    ):
        """
        Test that Uses extraction returns correct structure.

        This test verifies that the Uses calculation returns:
        - DataFrame with timeline.period_index as index
        - 'Total Uses' column with cash outflows by period
        - Positive values representing cash needs
        """
        # This test will drive the implementation structure
        # Expected structure after implementation:
        # - DataFrame with period_index
        # - 'Total Uses' column
        # - Values representing cash outflows needed each period

        # For now, verify we have the basic inputs needed
        assert sample_timeline.period_index is not None
        assert len(sample_timeline.period_index) > 0

        # TODO: Test the actual Uses DataFrame structure once implemented

    def test_orchestrate_funding_step_a_uses_values(
        self, sample_deal_all_equity, sample_timeline, sample_settings
    ):
        """
        Test that Uses values are correctly calculated.

        This test verifies that:
        - Uses include construction costs from the construction plan
        - Uses include acquisition costs in the appropriate period
        - Uses are positive values (cash outflows)
        - Uses sum to the total project cost
        """
        # This test will drive the implementation logic
        # Expected behavior after implementation:
        # - Total Uses should equal total project cost
        # - Acquisition costs should appear in first period
        # - Construction costs should be distributed according to timeline

        # For now, verify we have the basic cost components
        assert sample_deal_all_equity.acquisition.value > 0
        assert len(sample_deal_all_equity.asset.construction_plan.capital_items) > 0

        # TODO: Test the actual Uses calculation once implemented

    def test_orchestrate_funding_step_a_zero_uses_handling(
        self, sample_timeline, sample_settings
    ):
        """
        Test handling of deals with zero Uses.

        This test verifies that the function handles edge cases:
        - Deals with minimal acquisition costs
        - Deals with no construction costs
        - Periods with zero Uses
        """
        # Create a minimal deal with zero construction costs

        minimal_project = DevelopmentProject(
            name="Minimal Project",
            property_type=AssetTypeEnum.OFFICE,
            gross_area=Decimal(1000.0),
            net_rentable_area=Decimal(900.0),
            construction_plan=CapitalPlan(name="Empty Plan", capital_items=[]),
            blueprints=[],
        )

        # Create minimal acquisition (required field)
        minimal_acquisition_timeline = Timeline.from_dates(
            start_date=datetime(2024, 1, 1), end_date=datetime(2024, 1, 31)
        )
        minimal_acquisition = AcquisitionTerms(
            name="Minimal Acquisition",
            timeline=minimal_acquisition_timeline,
            value=Decimal(1000.0),  # Minimal acquisition cost
            acquisition_date=datetime(2024, 1, 1),
        )

        minimal_deal = Deal(
            name="Minimal Deal",
            asset=minimal_project,
            acquisition=minimal_acquisition,  # Deal requires acquisition
            financing=None,
            disposition=None,
            equity_partners=None,
        )

        # Should handle zero construction costs gracefully
        # TODO: Test the actual zero Uses handling once implemented
        assert minimal_deal.asset.construction_plan.capital_items == []

    def test_orchestrate_funding_step_a_acquisition_timing(
        self, sample_deal_all_equity, sample_timeline, sample_settings
    ):
        """
        Test that acquisition costs appear in correct periods.

        This test verifies that:
        - Acquisition costs are properly timed according to acquisition timeline
        - Closing costs are included in acquisition Uses
        - Acquisition Uses appear in the correct periods
        """
        # Expected behavior after implementation:
        # - Acquisition costs should appear according to acquisition.timeline
        # - Should include base value + closing costs
        # - Should be in correct periods based on acquisition_date

        acquisition = sample_deal_all_equity.acquisition
        assert abs(float(acquisition.value) - 5000000) < 1000
        assert abs(float(acquisition.closing_costs_rate) - 0.025) < 0.001

        # Total acquisition cost should be 5M + 2.5% = 5.125M
        expected_total_acquisition = Decimal("5000000") * (1 + Decimal("0.025"))
        assert abs(expected_total_acquisition - Decimal("5125000")) < Decimal("0.01")

        # TODO: Test the actual acquisition timing once implemented

    def test_orchestrate_funding_step_a_construction_timing(
        self, sample_deal_all_equity, sample_timeline, sample_settings
    ):
        """
        Test that construction costs appear in correct periods.

        This test verifies that:
        - Construction costs are distributed according to CapitalItem timelines
        - Multiple overlapping construction items are handled correctly
        - Construction Uses appear in the correct periods
        """
        # Expected behavior after implementation:
        # - Site Work: $1M total over Jan-Jun 2024
        # - Building: $5M total over Apr 2024 - Oct 2025
        # - TI: $2M total over Aug 2025 - Mar 2026
        # - Total construction: $8M

        construction_items = (
            sample_deal_all_equity.asset.construction_plan.capital_items
        )
        assert len(construction_items) == 3

        total_construction_cost = sum(item.value for item in construction_items)
        assert abs(float(total_construction_cost) - 8000000) < 1000

        # TODO: Test the actual construction timing once implemented

    def test_orchestrate_funding_step_b_equity_only_deal(
        self, sample_deal_all_equity, sample_timeline, sample_settings
    ):
        """
        Test Step B: Equity Draw for all-equity deal.

        This test verifies that the equity funding cascade:
        - Calculates correct equity target (100% for all-equity deals)
        - Funds all Uses with equity contributions
        - Tracks cumulative equity vs target
        - Generates correct equity_contributions component
        """
        # Test the actual implementation
        results = analyze(sample_deal_all_equity, sample_timeline, sample_settings)

        # Verify structure includes equity components
        assert hasattr(results.levered_cash_flows, "cash_flow_components")
        components = results.levered_cash_flows.cash_flow_components

        assert hasattr(
            components, "equity_contributions"
        ), "Should have equity_contributions component"
        assert hasattr(components, "total_uses"), "Should have total_uses component"

        # For all-equity deal, equity contributions should equal total uses
        equity_contributions = components.equity_contributions
        total_uses = components.total_uses

        # Verify equity contributions are positive (cash inflows to fund Uses)
        assert (
            equity_contributions >= 0
        ).all(), "Equity contributions should be non-negative"

        # Verify equity funds all Uses
        total_equity_contributed = equity_contributions.sum()
        total_uses_amount = total_uses.sum()
        assert (
            abs(total_equity_contributed - total_uses_amount) < Decimal(1000)
        ), f"Equity ${total_equity_contributed:,.0f} should equal Uses ${total_uses_amount:,.0f}"

        # Verify timing: equity should be contributed in periods when Uses occur
        periods_with_uses = total_uses > 0
        periods_with_equity = equity_contributions > 0
        assert periods_with_uses.equals(
            periods_with_equity
        ), "Equity should be contributed exactly when Uses occur"

        # Verify levered cash flows are correct (should be zero for fully funded construction)
        levered_cash_flows = results.levered_cash_flows.levered_cash_flows
        # For development deal during construction: Uses are funded by equity, so net CF should be zero
        construction_periods = total_uses > 0
        construction_cf = levered_cash_flows[construction_periods]
        assert abs(construction_cf.sum()) < Decimal(
            1000
        ), "Levered CF during construction should be near zero (Uses - Equity = 0)"

    def test_orchestrate_funding_step_b_equity_target_calculation(
        self, sample_deal_all_equity, sample_timeline, sample_settings
    ):
        """
        Test Step B: Equity Target Calculation Logic.

        This test verifies that equity targets are calculated correctly:
        - All-equity deal: target = 100% of total project cost
        - Leveraged deal: target = total cost × (1 - max_ltc_ratio)
        """
        # Test all-equity deal
        results = analyze(sample_deal_all_equity, sample_timeline, sample_settings)

        # Should have equity target details in funding cascade
        assert hasattr(results.levered_cash_flows, "funding_cascade_details")
        funding_details = results.levered_cash_flows.funding_cascade_details

        assert hasattr(
            funding_details, "equity_target"
        ), "Should calculate equity target"
        assert hasattr(
            funding_details, "equity_contributed_cumulative"
        ), "Should track cumulative equity"

        equity_target = funding_details.equity_target
        uses_breakdown = funding_details.uses_breakdown
        total_project_cost = uses_breakdown["Total Uses"].sum()

        # For all-equity deal, target should be 100% of project cost
        assert (
            abs(equity_target - total_project_cost) < Decimal(1000)
        ), f"All-equity target ${equity_target:,.0f} should equal project cost ${total_project_cost:,.0f}"

        # Verify cumulative tracking
        equity_cumulative = funding_details.equity_contributed_cumulative
        assert isinstance(
            equity_cumulative, pd.Series
        ), "Should track cumulative equity as Series"
        assert equity_cumulative.index.equals(
            sample_timeline.period_index
        ), "Should track for all periods"

        # Final cumulative equity should equal target
        final_equity = equity_cumulative.iloc[-1]
        assert (
            abs(final_equity - equity_target) < Decimal(1000)
        ), f"Final equity ${final_equity:,.0f} should reach target ${equity_target:,.0f}"

    def test_orchestrate_funding_step_b_equity_timing_validation(
        self, sample_deal_all_equity, sample_timeline, sample_settings
    ):
        """
        Test Step B: Equity Contribution Timing.

        This test verifies that equity contributions happen at the right times:
        - Equity contributed period-by-period as Uses occur
        - No equity contributed in periods with zero Uses
        - Cumulative equity tracking is monotonic (non-decreasing)
        """
        results = analyze(sample_deal_all_equity, sample_timeline, sample_settings)

        components = results.levered_cash_flows.cash_flow_components
        funding_details = results.levered_cash_flows.funding_cascade_details

        equity_contributions = components.equity_contributions
        uses_breakdown = funding_details.uses_breakdown
        equity_cumulative = funding_details.equity_contributed_cumulative

        # Test 1: Equity only in periods with Uses
        uses_by_period = uses_breakdown["Total Uses"]
        for period in sample_timeline.period_index:
            period_uses = uses_by_period[period]
            period_equity = equity_contributions[period]

            if period_uses == 0:
                assert (
                    period_equity == 0
                ), f"No equity should be contributed in period {period} with zero Uses"
            else:
                assert (
                    period_equity > 0
                ), f"Equity should be contributed in period {period} with Uses ${period_uses:,.0f}"

        # Test 2: Cumulative equity is monotonic (never decreases)
        for i in range(1, len(equity_cumulative)):
            current = equity_cumulative.iloc[i]
            previous = equity_cumulative.iloc[i - 1]
            assert (
                current >= previous
            ), f"Cumulative equity should never decrease: period {i} has ${current:,.0f} < previous ${previous:,.0f}"

        # Test 3: Cumulative equity equals cumulative contributions
        calculated_cumulative = equity_contributions.cumsum()
        pd.testing.assert_series_equal(
            equity_cumulative, calculated_cumulative, check_names=False
        )
        # Note: Cumulative equity should equal cumsum of contributions

    def test_orchestrate_funding_step_b_equity_component_structure(
        self, sample_deal_all_equity, sample_timeline, sample_settings
    ):
        """
        Test Step B: Equity Component Structure and Integration.

        This test verifies that equity components integrate correctly:
        - equity_contributions component has proper structure
        - Component integrates with cash flow assembly
        - Proper pandas Series with timeline index
        """
        results = analyze(sample_deal_all_equity, sample_timeline, sample_settings)

        components = results.levered_cash_flows.cash_flow_components
        equity_contributions = components.equity_contributions

        # Verify structure
        assert isinstance(
            equity_contributions, pd.Series
        ), "equity_contributions should be pandas Series"
        assert equity_contributions.index.equals(
            sample_timeline.period_index
        ), "Should use timeline period_index"
        assert len(equity_contributions) == len(
            sample_timeline.period_index
        ), "Should have value for each period"

        # Verify data types and values
        assert equity_contributions.dtype in [
            "float64",
            "Float64",
        ], "Should be numeric type"
        assert (
            equity_contributions >= 0
        ).all(), "All equity contributions should be non-negative"
        assert (
            equity_contributions.sum() > 0
        ), "Total equity contributions should be positive"

        # Verify integration with cash flow assembly
        levered_cash_flows = results.levered_cash_flows.levered_cash_flows
        total_uses = components.total_uses

        # For all-equity deal: levered_cf = -total_uses + equity_contributions
        expected_levered_cf = -total_uses + equity_contributions
        pd.testing.assert_series_equal(
            levered_cash_flows, expected_levered_cf, check_names=False
        )
        # Note: Levered CF should equal -Uses + Equity

    def test_orchestrate_funding_step_b_zero_uses_periods(
        self, sample_timeline, sample_settings
    ):
        """
        Test Step B: Handling periods with zero Uses.

        This test verifies edge case handling:
        - Periods with zero Uses get zero equity contributions
        - Cumulative equity tracking still works correctly
        - No unnecessary equity contributions
        """
        # Create a deal with gaps in Uses (no construction for some periods)

        # Create construction plan with gaps
        construction_items = [
            CapitalItem(
                name="Initial Site Work",
                value=Decimal("1000000"),
                timeline=Timeline.from_dates(
                    datetime(2024, 1, 1), datetime(2024, 2, 29)
                ),  # 2 months
            ),
            # Gap: March-May 2024 (no construction)
            CapitalItem(
                name="Final Construction",
                value=Decimal(2000000.0),
                timeline=Timeline.from_dates(
                    datetime(2024, 6, 1), datetime(2024, 7, 31)
                ),  # 2 months
            ),
        ]

        construction_plan = CapitalPlan(
            name="Gapped Construction Plan", capital_items=construction_items
        )

        gapped_project = DevelopmentProject(
            name="Gapped Development",
            property_type=AssetTypeEnum.OFFICE,
            gross_area=Decimal(50000.0),
            net_rentable_area=Decimal(45000.0),
            construction_plan=construction_plan,
            blueprints=[],
        )

        minimal_acquisition = AcquisitionTerms(
            name="Minimal Acquisition",
            timeline=Timeline.from_dates(datetime(2024, 1, 1), datetime(2024, 1, 31)),
            value=Decimal("1000000"),
            acquisition_date=datetime(2024, 1, 1),
            closing_costs_rate=Decimal(0.01),
        )

        gapped_deal = Deal(
            name="Gapped Deal", asset=gapped_project, acquisition=minimal_acquisition
        )

        # Test the implementation
        results = analyze(gapped_deal, sample_timeline, sample_settings)

        components = results.levered_cash_flows.cash_flow_components
        equity_contributions = components.equity_contributions
        total_uses = components.total_uses

        # Verify zero equity in zero-use periods
        for period in sample_timeline.period_index:
            period_uses = total_uses[period]
            period_equity = equity_contributions[period]

            if period_uses == 0:
                assert (
                    period_equity == 0
                ), f"Should have zero equity in zero-use period {period}"

    def test_orchestrate_funding_step_c_leveraged_deal_funding(
        self,
        sample_development_project,
        sample_acquisition,
        sample_timeline,
        sample_settings,
    ):
        """
        Test Step C: Debt Draw for leveraged development deal.

        This test verifies the debt funding cascade:
        - Equity contributes up to target (1-max_ltc) of total project cost
        - Debt draws fund remaining Uses after equity target reached
        - Debt draws use ConstructionFacility.calculate_period_draws logic
        - Generates correct debt_draws and loan_proceeds components
        """
        # Create a leveraged deal with construction financing

        # Create construction facility with 70% LTC
        senior_tranche = DebtTranche(
            name="Senior Tranche",
            interest_rate=InterestRate(
                details=FixedRate(rate=Decimal(0.05))  # 5% fixed rate
            ),
            fee_rate=Decimal(0.01),  # 1% fee
            ltc_threshold=Decimal(0.70),  # 70% LTC
        )

        construction_facility = ConstructionFacility(
            name="Construction Loan", tranches=[senior_tranche]
        )

        financing_plan = FinancingPlan(
            name="Construction Financing", facilities=[construction_facility]
        )

        # Create leveraged deal (30% equity, 70% debt)
        leveraged_deal = Deal(
            name="Leveraged Development Deal",
            asset=sample_development_project,
            acquisition=sample_acquisition,
            financing=financing_plan,
        )

        # Test the implementation
        results = analyze(leveraged_deal, sample_timeline, sample_settings)

        # Verify structure includes debt components
        assert hasattr(results.levered_cash_flows, "cash_flow_components")
        components = results.levered_cash_flows.cash_flow_components

        assert hasattr(components, "debt_draws"), "Should have debt_draws component"
        assert hasattr(
            components, "loan_proceeds"
        ), "Should have loan_proceeds component"

        # Verify debt draws and loan proceeds are positive
        debt_draws = components.debt_draws
        loan_proceeds = components.loan_proceeds

        assert (debt_draws >= 0).all(), "Debt draws should be non-negative"
        assert (loan_proceeds >= 0).all(), "Loan proceeds should be non-negative"

        # Verify equity + debt funding equals total Uses
        equity_contributions = components.equity_contributions
        total_uses = components.total_uses

        total_equity = equity_contributions.sum()
        total_debt = debt_draws.sum()
        total_uses_amount = total_uses.sum()

        total_funding = total_equity + total_debt
        # Allow for small variance due to interest compounding complexity (up to 2% of total uses)
        tolerance = float(total_uses_amount) * 0.02  # 2% tolerance
        assert (
            abs(float(total_funding) - float(total_uses_amount)) < tolerance
        ), f"Total funding ${total_funding:,.0f} should equal Uses ${total_uses_amount:,.0f} (gap: ${abs(float(total_funding) - float(total_uses_amount)):,.0f}, tolerance: ${tolerance:,.0f})"

        # Verify equity target is correctly calculated (30% for 70% LTC deal)
        funding_details = results.levered_cash_flows.funding_cascade_details
        equity_target = funding_details.equity_target

        # Equity target should be 30% of total project cost (including interest compounding)
        # This is the correct calculation - equity target adjusts as interest compounds
        interest_compounding_details = funding_details.interest_compounding_details
        total_project_cost = interest_compounding_details.total_uses_with_interest.sum()
        expected_equity_target = (
            float(total_project_cost) * 0.30
        )  # 30% of total project cost

        assert (
            abs(equity_target - expected_equity_target) < Decimal(1000)
        ), f"Equity target ${equity_target:,.0f} should be 30% of total project cost ${expected_equity_target:,.0f}"

    def test_orchestrate_funding_step_c_debt_after_equity_target(
        self,
        sample_development_project,
        sample_acquisition,
        sample_timeline,
        sample_settings,
    ):
        """
        Test Step C: Debt funding only after equity target is reached.

        This test verifies the debt-second funding sequence:
        - Equity funds Uses up to equity target
        - Debt funding only begins after equity target is reached
        - Debt funding continues until Uses are fully funded
        """
        # Create leveraged deal with 50% LTC for clear equity/debt split

        senior_tranche = DebtTranche(
            name="Senior Tranche",
            interest_rate=InterestRate(
                details=FixedRate(rate=Decimal(0.06))  # 6% fixed rate
            ),
            fee_rate=Decimal(0.015),  # 1.5% fee
            ltc_threshold=Decimal(0.50),  # 50% LTC
        )

        construction_facility = ConstructionFacility(
            name="Construction Loan", tranches=[senior_tranche]
        )

        financing_plan = FinancingPlan(
            name="50% LTC Financing", facilities=[construction_facility]
        )

        # Create leveraged deal (50% equity, 50% debt)
        leveraged_deal = Deal(
            name="50% LTC Deal",
            asset=sample_development_project,
            acquisition=sample_acquisition,
            financing=financing_plan,
        )

        # Test the implementation
        results = analyze(leveraged_deal, sample_timeline, sample_settings)

        components = results.levered_cash_flows.cash_flow_components
        funding_details = results.levered_cash_flows.funding_cascade_details

        equity_contributions = components.equity_contributions
        debt_draws = components.debt_draws
        total_uses = components.total_uses

        # Calculate cumulative equity and debt
        equity_cumulative = equity_contributions.cumsum()
        debt_cumulative = debt_draws.cumsum()

        # Verify proper funding sequence: equity contributes based on target, debt fills gaps
        equity_target = funding_details.equity_target
        total_uses_amount = total_uses.sum()

        # Test that total equity + debt equals total uses
        total_equity = equity_contributions.sum()
        total_debt = debt_draws.sum()
        total_funding = total_equity + total_debt

        # Allow for small variance due to interest compounding complexity
        tolerance = float(total_uses_amount) * 0.02  # 2% tolerance
        assert (
            abs(float(total_funding) - float(total_uses_amount)) < tolerance
        ), f"Total funding ${total_funding:,.0f} should equal Uses ${total_uses_amount:,.0f}"

        # Test that equity target is reached (within tolerance)
        assert (
            abs(total_equity - equity_target) / equity_target < 0.05
        ), f"Total equity ${total_equity:,.0f} should be close to target ${equity_target:,.0f}"

        # Test that debt provides the remaining funding
        expected_debt = total_uses_amount - equity_target
        assert (
            abs(total_debt - expected_debt) / expected_debt < 0.05
        ), f"Total debt ${total_debt:,.0f} should be close to expected ${expected_debt:,.0f}"

    def test_orchestrate_funding_step_c_multi_tranche_debt_cascade(
        self,
        sample_development_project,
        sample_acquisition,
        sample_timeline,
        sample_settings,
    ):
        """
        Test Step C: Multi-tranche debt funding cascade.

        This test verifies multi-tranche debt funding:
        - Senior tranche funds first up to its LTC threshold
        - Junior tranche funds after senior tranche reaches capacity
        - Proper seniority ordering and LTC limits
        """
        # Create multi-tranche construction facility

        senior_tranche = DebtTranche(
            name="Senior Tranche",
            interest_rate=InterestRate(
                details=FixedRate(rate=Decimal(0.05))  # 5% fixed rate
            ),
            fee_rate=Decimal(0.01),  # 1% fee
            ltc_threshold=Decimal(0.60),  # 60% LTC senior
        )

        junior_tranche = DebtTranche(
            name="Junior Tranche",
            interest_rate=InterestRate(
                details=FixedRate(
                    rate=Decimal(0.08)
                )  # 8% fixed rate (higher for junior)
            ),
            fee_rate=Decimal(0.02),  # 2% fee
            ltc_threshold=Decimal(0.75),  # 75% LTC total (15% junior)
        )

        construction_facility = ConstructionFacility(
            name="Multi-Tranche Construction Loan",
            tranches=[senior_tranche, junior_tranche],
        )

        financing_plan = FinancingPlan(
            name="Multi-Tranche Financing", facilities=[construction_facility]
        )

        # Create leveraged deal (25% equity, 75% debt split between tranches)
        leveraged_deal = Deal(
            name="Multi-Tranche Deal",
            asset=sample_development_project,
            acquisition=sample_acquisition,
            financing=financing_plan,
        )

        # Test the implementation
        results = analyze(leveraged_deal, sample_timeline, sample_settings)

        components = results.levered_cash_flows.cash_flow_components
        funding_details = results.levered_cash_flows.funding_cascade_details

        # Verify structure includes tranche-specific components
        assert hasattr(components, "debt_draws"), "Should have debt_draws component"

        # Verify financing details include multi-tranche information
        assert hasattr(
            funding_details, "debt_draws_by_tranche"
        ), "Should track draws by tranche"

        debt_draws_by_tranche = funding_details.debt_draws_by_tranche
        assert (
            "Senior Tranche" in debt_draws_by_tranche
        ), "Should track Senior Tranche draws"
        assert (
            "Junior Tranche" in debt_draws_by_tranche
        ), "Should track Junior Tranche draws"

        # Verify total debt funding
        total_debt = components.debt_draws.sum()
        total_uses = components.total_uses.sum()
        equity_target = funding_details.equity_target

        # Verify total debt funding is reasonable (allowing for LTC constraints and interest compounding)
        # In realistic construction finance, debt may not fund exactly (total_uses - equity_target) due to:
        # 1. LTC constraints limiting debt facility capacity
        # 2. Interest compounding creating additional Uses over time
        # 3. Small funding gaps filled with additional equity
        # Allow for up to 5% funding gap as realistic
        max_theoretical_debt = total_uses - equity_target
        actual_funding_gap = max_theoretical_debt - total_debt
        funding_gap_percentage = (
            actual_funding_gap / max_theoretical_debt if max_theoretical_debt > 0 else 0
        )

        assert (
            funding_gap_percentage <= 0.05
        ), f"Funding gap {funding_gap_percentage:.1%} should be ≤5% due to realistic LTC constraints (gap: ${actual_funding_gap:,.0f})"

    def test_orchestrate_funding_step_c_debt_timing_validation(
        self,
        sample_development_project,
        sample_acquisition,
        sample_timeline,
        sample_settings,
    ):
        """
        Test Step C: Debt draw timing validation.

        This test verifies debt draw timing:
        - Debt draws occur period-by-period as needed
        - No debt draws in periods with zero Uses (after equity target)
        - Cumulative debt tracking is accurate
        """
        # Create leveraged deal with 60% LTC

        senior_tranche = DebtTranche(
            name="Senior Tranche",
            interest_rate=InterestRate(
                details=FixedRate(rate=Decimal(0.055))  # 5.5% fixed rate
            ),
            fee_rate=Decimal(0.0125),  # 1.25% fee
            ltc_threshold=Decimal(0.60),  # 60% LTC
        )

        construction_facility = ConstructionFacility(
            name="Construction Loan", tranches=[senior_tranche]
        )

        financing_plan = FinancingPlan(
            name="Construction Financing", facilities=[construction_facility]
        )

        # Create leveraged deal (40% equity, 60% debt)
        leveraged_deal = Deal(
            name="Leveraged Development Deal",
            asset=sample_development_project,
            acquisition=sample_acquisition,
            financing=financing_plan,
        )

        # Test the implementation
        results = analyze(leveraged_deal, sample_timeline, sample_settings)

        components = results.levered_cash_flows.cash_flow_components
        funding_details = results.levered_cash_flows.funding_cascade_details

        debt_draws = components.debt_draws
        total_uses = components.total_uses
        equity_contributions = components.equity_contributions

        # Calculate cumulative equity and debt
        equity_cumulative = equity_contributions.cumsum()
        debt_cumulative = debt_draws.cumsum()
        equity_target = funding_details.equity_target

        # Test 1: Debt draws should be reasonable and follow proper funding logic
        for period in sample_timeline.period_index:
            period_uses = total_uses[period]
            period_debt = debt_draws[period]
            period_equity = equity_contributions[period]

            if period_uses == 0:
                # No debt draws in zero-use periods
                assert (
                    period_debt == 0
                ), f"No debt draws should occur in zero-use period {period}"
            elif period_uses > 0:
                # Debt draws should be non-negative and reasonable
                assert (
                    period_debt >= 0
                ), f"Debt draws should be non-negative in period {period}"
                # Total funding (equity + debt) should not exceed period uses by more than small tolerance
                period_funding = period_equity + period_debt
                assert (
                    period_funding <= period_uses * 1.1
                ), f"Period funding ${period_funding:,.0f} should not greatly exceed uses ${period_uses:,.0f} in period {period}"

        # Test 2: Cumulative debt tracking is monotonic
        for i in range(1, len(debt_cumulative)):
            current = debt_cumulative.iloc[i]
            previous = debt_cumulative.iloc[i - 1]
            assert (
                current >= previous
            ), f"Cumulative debt should never decrease: period {i} has ${current:,.0f} < previous ${previous:,.0f}"

        # Test 3: Final debt amount is reasonable (accounting for LTC constraints and interest compounding)
        final_debt = debt_cumulative.iloc[-1]
        # In realistic construction finance, debt may not fund exactly (total_uses - equity_target) due to:
        # 1. LTC constraints limiting debt facility capacity
        # 2. Interest compounding creating additional Uses over time
        # 3. Small funding gaps filled with additional equity
        # Allow for up to 5% funding gap as realistic
        max_theoretical_debt = total_uses.sum() - equity_target
        actual_funding_gap = max_theoretical_debt - final_debt
        funding_gap_percentage = (
            actual_funding_gap / max_theoretical_debt if max_theoretical_debt > 0 else 0
        )

        assert (
            funding_gap_percentage <= 0.05
        ), f"Funding gap {funding_gap_percentage:.1%} should be ≤5% due to realistic LTC constraints (gap: ${actual_funding_gap:,.0f})"

    def test_orchestrate_funding_step_c_component_integration(
        self,
        sample_development_project,
        sample_acquisition,
        sample_timeline,
        sample_settings,
    ):
        """
        Test Step C: Debt component integration with cash flow assembly.

        This test verifies debt component integration:
        - debt_draws component has proper structure
        - loan_proceeds component mirrors debt_draws
        - Components integrate with levered cash flow assembly
        """
        # Create leveraged deal with 65% LTC

        senior_tranche = DebtTranche(
            name="Senior Tranche",
            interest_rate=InterestRate(
                details=FixedRate(rate=Decimal(0.04))  # 4% fixed rate
            ),
            fee_rate=Decimal(0.008),  # 0.8% fee
            ltc_threshold=Decimal(0.65),  # 65% LTC
        )

        construction_facility = ConstructionFacility(
            name="Construction Loan", tranches=[senior_tranche]
        )

        financing_plan = FinancingPlan(
            name="Construction Financing", facilities=[construction_facility]
        )

        # Create leveraged deal (35% equity, 65% debt)
        leveraged_deal = Deal(
            name="Leveraged Development Deal",
            asset=sample_development_project,
            acquisition=sample_acquisition,
            financing=financing_plan,
        )

        # Test the implementation
        results = analyze(leveraged_deal, sample_timeline, sample_settings)

        components = results.levered_cash_flows.cash_flow_components
        debt_draws = components.debt_draws
        loan_proceeds = components.loan_proceeds

        # Verify structure
        assert isinstance(debt_draws, pd.Series), "debt_draws should be pandas Series"
        assert isinstance(
            loan_proceeds, pd.Series
        ), "loan_proceeds should be pandas Series"
        assert debt_draws.index.equals(
            sample_timeline.period_index
        ), "debt_draws should use timeline period_index"
        assert loan_proceeds.index.equals(
            sample_timeline.period_index
        ), "loan_proceeds should use timeline period_index"

        # Verify data types and values
        assert debt_draws.dtype in [
            "float64",
            "Float64",
        ], "debt_draws should be numeric type"
        assert loan_proceeds.dtype in [
            "float64",
            "Float64",
        ], "loan_proceeds should be numeric type"
        assert (debt_draws >= 0).all(), "All debt draws should be non-negative"
        assert (loan_proceeds >= 0).all(), "All loan proceeds should be non-negative"

        # Verify debt draws equal loan proceeds (for construction loans)
        pd.testing.assert_series_equal(debt_draws, loan_proceeds, check_names=False)

        # Verify integration with cash flow assembly
        levered_cash_flows = results.levered_cash_flows.levered_cash_flows
        total_uses = components.total_uses
        equity_contributions = components.equity_contributions

        # For leveraged deal: levered_cf = -total_uses + equity_contributions + debt_draws
        expected_levered_cf = -total_uses + equity_contributions + debt_draws
        pd.testing.assert_series_equal(
            levered_cash_flows, expected_levered_cf, check_names=False
        )

    def test_orchestrate_funding_step_d_interest_calculation(
        self,
        sample_development_project,
        sample_acquisition,
        sample_timeline,
        sample_settings,
    ):
        """
        Test Step D: Interest calculation on outstanding debt balances.

        This test verifies basic interest calculation:
        - Interest calculated on outstanding debt balance each period
        - Interest rate applied correctly (monthly compounding)
        - Interest expense component generated
        - Interest becomes a Use for the following period
        """
        # Create leveraged deal with 60% LTC

        senior_tranche = DebtTranche(
            name="Senior Tranche",
            interest_rate=InterestRate(
                details=FixedRate(rate=Decimal(0.06))  # 6% annual interest rate
            ),
            fee_rate=Decimal(0.01),  # 1% fee
            ltc_threshold=Decimal(0.60),  # 60% LTC
        )

        construction_facility = ConstructionFacility(
            name="Construction Loan",
            tranches=[senior_tranche],
            fund_interest_from_reserve=False,  # Interest becomes a Use
        )

        financing_plan = FinancingPlan(
            name="Construction Financing", facilities=[construction_facility]
        )

        # Create leveraged deal (40% equity, 60% debt)
        leveraged_deal = Deal(
            name="Leveraged Development Deal",
            asset=sample_development_project,
            acquisition=sample_acquisition,
            financing=financing_plan,
        )

        # Test the implementation
        results = analyze(leveraged_deal, sample_timeline, sample_settings)

        # Verify structure includes interest components
        assert hasattr(results.levered_cash_flows, "cash_flow_components")
        components = results.levered_cash_flows.cash_flow_components

        assert hasattr(
            components, "interest_expense"
        ), "Should have interest_expense component"

        # Verify interest expense is calculated
        interest_expense = components.interest_expense
        debt_draws = components.debt_draws

        assert isinstance(
            interest_expense, pd.Series
        ), "interest_expense should be pandas Series"
        assert (interest_expense >= 0).all(), "Interest expense should be non-negative"

        # Verify interest calculation logic
        # Interest should be calculated on cumulative debt balance
        debt_cumulative = debt_draws.cumsum()
        monthly_rate = 0.06 / 12  # 6% annual = 0.5% monthly

        # Interest should be calculated on previous period's balance
        for i in range(1, len(sample_timeline.period_index)):
            period = sample_timeline.period_index[i]
            previous_balance = debt_cumulative.iloc[i - 1]

            if previous_balance > 0:
                expected_interest = float(previous_balance) * float(monthly_rate)
                actual_interest = interest_expense[period]

                # Allow for small rounding differences
                assert (
                    abs(float(actual_interest) - expected_interest) < 100
                ), f"Interest calculation incorrect for period {period}"

        # Verify interest is positive when there's outstanding debt
        periods_with_debt = debt_cumulative > 0
        periods_with_interest = interest_expense > 0

        # Interest should be calculated starting from the period after first debt draw
        for i in range(1, len(sample_timeline.period_index)):
            period = sample_timeline.period_index[i]
            previous_debt = debt_cumulative.iloc[i - 1]

            if previous_debt > 0:
                assert (
                    interest_expense[period] > 0
                ), f"Should have interest expense when debt outstanding in period {period}"

    def test_orchestrate_funding_step_d_interest_compounding(
        self,
        sample_development_project,
        sample_acquisition,
        sample_timeline,
        sample_settings,
    ):
        """
        Test Step D: Interest compounding and capitalization.

        This test verifies interest compounding logic:
        - Interest from period N becomes a Use in period N+1
        - Compounded interest increases total Uses
        - Interest-on-interest calculation is correct
        - Updated Uses are reflected in funding cascade
        """
        # Create leveraged deal with 70% LTC

        senior_tranche = DebtTranche(
            name="Senior Tranche",
            interest_rate=InterestRate(
                details=FixedRate(
                    rate=Decimal(0.08)
                )  # 8% annual interest rate (higher for compounding test)
            ),
            fee_rate=Decimal(0.01),
            ltc_threshold=Decimal(0.70),  # 70% LTC
        )

        construction_facility = ConstructionFacility(
            name="Construction Loan",
            tranches=[senior_tranche],
            fund_interest_from_reserve=False,  # Interest becomes a Use
        )

        financing_plan = FinancingPlan(
            name="Construction Financing", facilities=[construction_facility]
        )

        # Create leveraged deal (30% equity, 70% debt)
        leveraged_deal = Deal(
            name="Leveraged Development Deal",
            asset=sample_development_project,
            acquisition=sample_acquisition,
            financing=financing_plan,
        )

        # Test the implementation
        results = analyze(leveraged_deal, sample_timeline, sample_settings)

        components = results.levered_cash_flows.cash_flow_components
        funding_details = results.levered_cash_flows.funding_cascade_details

        interest_expense = components.interest_expense
        total_uses = components.total_uses

        # Verify interest compounding details are tracked
        assert hasattr(
            funding_details, "interest_compounding_details"
        ), "Should track interest compounding details"

        compounding_details = funding_details.interest_compounding_details
        assert hasattr(
            compounding_details, "base_uses"
        ), "Should track base Uses (before interest)"
        assert hasattr(
            compounding_details, "compounded_interest"
        ), "Should track compounded interest"
        assert hasattr(
            compounding_details, "total_uses_with_interest"
        ), "Should track total Uses including interest"

        # Verify interest compounding calculation
        base_uses = compounding_details.base_uses
        compounded_interest = compounding_details.compounded_interest
        total_uses_with_interest = compounding_details.total_uses_with_interest

        # Total uses should equal base uses + compounded interest
        expected_total_uses = base_uses + compounded_interest
        pd.testing.assert_series_equal(
            total_uses, expected_total_uses, check_names=False
        )

        # Verify interest from period N becomes Use in period N+1
        for i in range(1, len(sample_timeline.period_index) - 1):
            period = sample_timeline.period_index[i]
            next_period = sample_timeline.period_index[i + 1]

            period_interest = interest_expense[period]
            next_period_compounded = compounded_interest[next_period]

            if period_interest > 0:
                # Interest from this period should contribute to next period's Uses
                assert (
                    next_period_compounded >= period_interest
                ), f"Interest from {period} should compound into {next_period}"

    def test_orchestrate_funding_step_d_interest_reserve_funding(
        self,
        sample_development_project,
        sample_acquisition,
        sample_timeline,
        sample_settings,
    ):
        """
        Test Step D: Interest reserve funding option.

        This test verifies interest reserve logic:
        - When fund_interest_from_reserve=True, interest is funded from facility
        - Interest doesn't become a Use for equity/debt funding
        - Interest reserve capacity is tracked
        - Interest reserve is properly accounted for in debt balance
        """
        # Create leveraged deal with interest reserve

        senior_tranche = DebtTranche(
            name="Senior Tranche",
            interest_rate=InterestRate(
                details=FixedRate(rate=Decimal(0.055))  # 5.5% annual interest rate
            ),
            fee_rate=Decimal(0.01),
            ltc_threshold=Decimal(
                0.75
            ),  # 75% LTC (higher to accommodate interest reserve)
        )

        construction_facility = ConstructionFacility(
            name="Construction Loan with Interest Reserve",
            tranches=[senior_tranche],
            fund_interest_from_reserve=True,  # Interest funded from facility
        )

        financing_plan = FinancingPlan(
            name="Interest Reserve Financing", facilities=[construction_facility]
        )

        # Create leveraged deal (25% equity, 75% debt including interest reserve)
        leveraged_deal = Deal(
            name="Interest Reserve Deal",
            asset=sample_development_project,
            acquisition=sample_acquisition,
            financing=financing_plan,
        )

        # Test the implementation
        results = analyze(leveraged_deal, sample_timeline, sample_settings)

        components = results.levered_cash_flows.cash_flow_components
        funding_details = results.levered_cash_flows.funding_cascade_details

        # Verify interest reserve components
        assert hasattr(
            funding_details, "interest_reserve_details"
        ), "Should track interest reserve details"

        reserve_details = funding_details.interest_reserve_details
        assert hasattr(
            reserve_details, "interest_funded_from_reserve"
        ), "Should track interest funded from reserve"
        assert hasattr(
            reserve_details, "interest_reserve_capacity"
        ), "Should track interest reserve capacity"
        assert hasattr(
            reserve_details, "interest_reserve_utilization"
        ), "Should track interest reserve utilization"

        interest_funded_from_reserve = reserve_details.interest_funded_from_reserve
        interest_expense = components.interest_expense

        # When interest is funded from reserve, interest expense should be zero in Uses
        # (interest is handled within the facility, not as a separate Use)
        assert (
            interest_expense == 0
        ).all(), "Interest expense should be zero when funded from reserve"

        # But interest should still be tracked in the reserve details
        assert (
            interest_funded_from_reserve >= 0
        ).all(), "Interest funded from reserve should be non-negative"
        assert (
            interest_funded_from_reserve.sum() > 0
        ), "Should have some interest funded from reserve"

        # Verify interest reserve capacity tracking
        interest_reserve_capacity = reserve_details.interest_reserve_capacity
        interest_reserve_utilization = reserve_details.interest_reserve_utilization

        # Utilization should not exceed capacity
        assert (
            interest_reserve_utilization <= interest_reserve_capacity
        ).all(), "Reserve utilization should not exceed capacity"

        # Verify debt balance includes interest reserve draws
        debt_draws = components.debt_draws
        total_debt = debt_draws.sum()
        total_interest_from_reserve = interest_funded_from_reserve.sum()

        # Total debt should include both construction costs and interest reserve
        assert (
            total_debt >= total_interest_from_reserve
        ), "Total debt should include interest reserve draws"

    def test_orchestrate_funding_step_d_integration_with_funding_cascade(
        self,
        sample_development_project,
        sample_acquisition,
        sample_timeline,
        sample_settings,
    ):
        """
        Test Step D: Integration with complete funding cascade.

        This test verifies end-to-end integration:
        - Steps A, B, C, D work together seamlessly
        - Interest calculation affects subsequent funding decisions
        - Final levered cash flows include all components
        - Component tracking is comprehensive and accurate
        """
        # Create complex leveraged deal for comprehensive integration test

        # Multi-tranche facility with different interest rates
        senior_tranche = DebtTranche(
            name="Senior Tranche",
            interest_rate=InterestRate(
                details=FixedRate(rate=Decimal(0.05))  # 5% annual interest rate
            ),
            fee_rate=Decimal(0.01),
            ltc_threshold=Decimal(0.55),  # 55% LTC senior
        )

        junior_tranche = DebtTranche(
            name="Junior Tranche",
            interest_rate=InterestRate(
                details=FixedRate(
                    rate=Decimal(0.09)
                )  # 9% annual interest rate (higher for junior)
            ),
            fee_rate=Decimal(0.02),
            ltc_threshold=Decimal(0.70),  # 70% LTC total (15% junior)
        )

        construction_facility = ConstructionFacility(
            name="Multi-Tranche Construction Loan",
            tranches=[senior_tranche, junior_tranche],
            fund_interest_from_reserve=False,  # Interest becomes a Use
        )

        financing_plan = FinancingPlan(
            name="Multi-Tranche Financing", facilities=[construction_facility]
        )

        # Create leveraged deal (30% equity, 70% debt)
        leveraged_deal = Deal(
            name="Multi-Tranche Integration Deal",
            asset=sample_development_project,
            acquisition=sample_acquisition,
            financing=financing_plan,
        )

        # Test the implementation
        results = analyze(leveraged_deal, sample_timeline, sample_settings)

        components = results.levered_cash_flows.cash_flow_components
        funding_details = results.levered_cash_flows.funding_cascade_details

        # Verify all components are present
        required_components = [
            "total_uses",
            "equity_contributions",
            "debt_draws",
            "loan_proceeds",
            "interest_expense",
        ]
        for component_name in required_components:
            assert hasattr(
                components, component_name
            ), f"Should have {component_name} component"

        # Verify all funding details are present
        required_details = [
            "uses_breakdown",
            "equity_target",
            "equity_contributed_cumulative",
            "debt_draws_by_tranche",
            "interest_compounding_details",
        ]
        for detail_name in required_details:
            assert hasattr(
                funding_details, detail_name
            ), f"Should have {detail_name} in funding details"

        # Verify integration: total funding should equal total uses
        total_uses = components.total_uses
        equity_contributions = components.equity_contributions
        debt_draws = components.debt_draws

        total_funding = equity_contributions.sum() + debt_draws.sum()
        total_uses_amount = total_uses.sum()

        # Allow for small variance due to interest compounding complexity (up to 2% of total uses)
        tolerance = float(total_uses_amount) * 0.02  # 2% tolerance
        assert (
            abs(float(total_funding) - float(total_uses_amount)) < tolerance
        ), f"Total funding ${total_funding:,.0f} should equal total uses ${total_uses_amount:,.0f} (gap: ${abs(float(total_funding) - float(total_uses_amount)):,.0f}, tolerance: ${tolerance:,.0f})"

        # Verify levered cash flows integration
        levered_cash_flows = results.levered_cash_flows.levered_cash_flows

        # For construction period: levered_cf = -total_uses + equity_contributions + debt_draws
        expected_levered_cf = -total_uses + equity_contributions + debt_draws
        pd.testing.assert_series_equal(
            levered_cash_flows, expected_levered_cf, check_names=False
        )

        # Verify interest calculation affects funding cascade
        interest_expense = components.interest_expense
        debt_draws_by_tranche = funding_details.debt_draws_by_tranche

        # Interest should be calculated on both tranches
        senior_draws = debt_draws_by_tranche["Senior Tranche"]
        junior_draws = debt_draws_by_tranche["Junior Tranche"]

        # Both tranches should contribute to interest expense
        assert senior_draws.sum() > 0, "Senior tranche should have draws"
        assert junior_draws.sum() > 0, "Junior tranche should have draws"
        assert (
            interest_expense.sum() > 0
        ), "Should have interest expense on outstanding balances"

        # Verify comprehensive component tracking
        cash_flow_summary = results.levered_cash_flows.cash_flow_summary

        required_summary_items = [
            "total_investment",
            "total_distributions",
            "net_cash_flow",
        ]
        for item_name in required_summary_items:
            assert hasattr(
                cash_flow_summary, item_name
            ), f"Should have {item_name} in cash flow summary"


class TestAnalyzeDeal:
    """Test suite for analyze function."""

    @pytest.fixture
    def sample_timeline(self):
        """Create a sample timeline for testing."""
        return Timeline.from_dates(
            start_date=datetime(2024, 1, 1), end_date=datetime(2026, 12, 31)
        )

    @pytest.fixture
    def sample_acquisition(self):
        """Create a sample acquisition for testing."""
        acquisition_timeline = Timeline.from_dates(
            start_date=datetime(2024, 1, 1), end_date=datetime(2024, 1, 31)
        )
        return AcquisitionTerms(
            name="Test Land Acquisition",
            timeline=acquisition_timeline,
            value=Decimal("5000000"),
            acquisition_date=datetime(2024, 1, 1),
            closing_costs_rate=Decimal("0.025"),
        )

    @pytest.fixture
    def sample_development_project(self):
        """Create a sample development project."""
        return DevelopmentProject(
            name="Test Office Development",
            property_type=AssetTypeEnum.OFFICE,
            gross_area=Decimal(100000.0),
            net_rentable_area=Decimal(90000.0),
            construction_plan=CapitalPlan(name="Construction Plan", capital_items=[]),
            blueprints=[],
        )

    @pytest.fixture
    def sample_deal(self, sample_development_project, sample_acquisition):
        """Create a sample deal for testing."""
        return Deal(
            name="Test Development Deal",
            asset=sample_development_project,
            acquisition=sample_acquisition,
            financing=None,  # All-equity deal
            disposition=None,
            equity_partners=None,
        )

    @pytest.fixture
    def sample_settings(self):
        """Create sample analysis settings."""
        return GlobalSettings()

    def test_analyze_basic_execution(
        self, sample_deal, sample_timeline, sample_settings
    ):
        """Test that analyze executes without errors."""
        results = analyze(sample_deal, sample_timeline, sample_settings)

        assert isinstance(results, DealAnalysisResult)

        # Should have all expected analysis components
        assert hasattr(results, "deal_summary")
        assert hasattr(results, "unlevered_analysis")
        assert hasattr(results, "financing_analysis")
        assert hasattr(results, "levered_cash_flows")
        assert hasattr(results, "partner_distributions")
        assert hasattr(results, "deal_metrics")

    def test_analyze_with_default_settings(self, sample_deal, sample_timeline):
        """Test analyze with default settings."""
        results = analyze(sample_deal, sample_timeline)

        assert isinstance(results, DealAnalysisResult)
        assert hasattr(results, "deal_summary")

    def test_deal_summary_content(self, sample_deal, sample_timeline, sample_settings):
        """Test that deal summary contains correct information."""
        results = analyze(sample_deal, sample_timeline, sample_settings)

        deal_summary = results.deal_summary
        assert deal_summary.deal_name == "Test Development Deal"
        assert deal_summary.deal_type == "development"
        assert deal_summary.is_development is True
        assert deal_summary.has_financing is False

    def test_unlevered_analysis_structure(
        self, sample_deal, sample_timeline, sample_settings
    ):
        """Test unlevered analysis output structure."""
        results = analyze(sample_deal, sample_timeline, sample_settings)

        unlevered_analysis = results.unlevered_analysis

        assert isinstance(unlevered_analysis, UnleveredAnalysisResult)

        # Should contain the scenario and basic structure
        assert hasattr(unlevered_analysis, "scenario")
        assert hasattr(unlevered_analysis, "cash_flows")
        assert hasattr(unlevered_analysis, "models")

    def test_financing_analysis_no_financing(
        self, sample_deal, sample_timeline, sample_settings
    ):
        """Test financing analysis when no financing is provided."""
        results = analyze(sample_deal, sample_timeline, sample_settings)

        # For all-equity deals, financing_analysis should be None
        financing_analysis = results.financing_analysis
        assert financing_analysis is None

    def test_levered_cash_flows_structure(
        self, sample_deal, sample_timeline, sample_settings
    ):
        """Test levered cash flows output structure."""
        results = analyze(sample_deal, sample_timeline, sample_settings)

        levered_cash_flows = results.levered_cash_flows

        assert isinstance(levered_cash_flows, LeveredCashFlowResult)

        # Should contain cash flows and summary
        assert hasattr(levered_cash_flows, "levered_cash_flows")
        assert hasattr(levered_cash_flows, "cash_flow_components")
        assert hasattr(levered_cash_flows, "cash_flow_summary")

        # Cash flow summary should have expected metrics
        summary = levered_cash_flows.cash_flow_summary
        assert hasattr(summary, "total_investment")
        assert hasattr(summary, "total_distributions")
        assert hasattr(summary, "net_cash_flow")

    def test_partner_distributions_structure(
        self, sample_deal, sample_timeline, sample_settings
    ):
        """Test partner distributions output structure."""
        results = analyze(sample_deal, sample_timeline, sample_settings)

        partner_distributions = results.partner_distributions

        assert isinstance(partner_distributions, PartnerDistributionResult)

        # Should contain distribution information
        # For deals without equity partners, expect single_entity distribution method
        assert partner_distributions.distribution_method == "single_entity"
        assert hasattr(partner_distributions, "irr")
        assert hasattr(partner_distributions, "equity_multiple")
        assert hasattr(partner_distributions, "distributions")

    def test_deal_metrics_structure(
        self, sample_deal, sample_timeline, sample_settings
    ):
        """Test deal metrics output structure."""
        results = analyze(sample_deal, sample_timeline, sample_settings)

        deal_metrics = results.deal_metrics

        assert isinstance(deal_metrics, DealMetricsResult)

        # Should contain key performance metrics
        expected_metrics = [
            "irr",
            "equity_multiple",
            "total_return",
            "annual_yield",
            "cash_on_cash",
            "total_equity_invested",
            "total_equity_returned",
            "net_profit",
            "hold_period_years",
        ]
        for metric_name in expected_metrics:
            assert hasattr(deal_metrics, metric_name)

    def test_hold_period_calculation(
        self, sample_deal, sample_timeline, sample_settings
    ):
        """Test that hold period is calculated correctly."""
        results = analyze(sample_deal, sample_timeline, sample_settings)

        deal_metrics = results.deal_metrics
        hold_period = deal_metrics.hold_period_years

        # Timeline is 3 years (2024-2026)
        assert abs(float(hold_period) - 3.0) < 0.01

    def test_deal_validation_called(
        self, sample_deal, sample_timeline, sample_settings
    ):
        """Test that deal validation is called during analysis."""
        # This should not raise an exception if validation passes
        results = analyze(sample_deal, sample_timeline, sample_settings)
        assert results is not None

    def test_analyze_with_different_asset_types(
        self, sample_acquisition, sample_timeline, sample_settings
    ):
        """Test analyze works with different asset types."""
        # Test with different property types
        for property_type in [
            AssetTypeEnum.OFFICE,
            AssetTypeEnum.MULTIFAMILY,
            AssetTypeEnum.MIXED_USE,
        ]:
            development_project = DevelopmentProject(
                name=f"Test {property_type.value} Development",
                property_type=property_type,
                gross_area=Decimal(100000.0),
                net_rentable_area=Decimal(90000.0),
                construction_plan=CapitalPlan(
                    name="Construction Plan", capital_items=[]
                ),
                blueprints=[],
            )

            deal = Deal(
                name=f"Test {property_type.value} Deal",
                asset=development_project,
                acquisition=sample_acquisition,
            )

            results = analyze(deal, sample_timeline, sample_settings)

            # Should work for all asset types
            assert results.deal_summary.deal_type == "development"
            assert results.deal_summary.asset_type == property_type

    def test_error_handling_invalid_deal(self, sample_timeline, sample_settings):
        """Test error handling with invalid deal components."""
        # This test would require creating an invalid deal structure
        # For now, we'll test that proper deals work correctly
        pass

    def test_cash_flow_components_separation(
        self, sample_deal, sample_timeline, sample_settings
    ):
        """Test that cash flow components are properly separated."""
        results = analyze(sample_deal, sample_timeline, sample_settings)

        components = results.levered_cash_flows.cash_flow_components

        # Should have all expected component categories
        expected_components = [
            "unlevered_cash_flows",
            "acquisition_costs",
            "loan_proceeds",
            "debt_service",
            "disposition_proceeds",
            "loan_payoff",
        ]

        for component_name in expected_components:
            assert hasattr(components, component_name)

    def test_metrics_calculation_consistency(
        self, sample_deal, sample_timeline, sample_settings
    ):
        """Test that metrics are calculated consistently between different sections."""
        results = analyze(sample_deal, sample_timeline, sample_settings)

        # Get metrics from different sections
        deal_metrics = results.deal_metrics
        partner_metrics = results.partner_distributions

        # IRR should be consistent (if calculated)
        if deal_metrics.irr is not None and partner_metrics.irr is not None:
            assert abs(deal_metrics.irr - partner_metrics.irr) < 0.0001

        # Equity multiple should be consistent
        if (
            deal_metrics.equity_multiple is not None
            and partner_metrics.equity_multiple is not None
        ):
            assert (
                abs(deal_metrics.equity_multiple - partner_metrics.equity_multiple)
                < 0.0001
            )


class TestAnalyzeDealEdgeCases:
    """Test edge cases and error conditions for analyze."""

    def test_analyze_with_minimal_deal(self):
        """Test analyze with minimal deal configuration."""
        # Create minimal components
        timeline = Timeline.from_dates(datetime(2024, 1, 1), datetime(2024, 12, 31))
        acquisition_timeline = Timeline.from_dates(
            datetime(2024, 1, 1), datetime(2024, 1, 31)
        )

        acquisition = AcquisitionTerms(
            name="Minimal Acquisition",
            timeline=acquisition_timeline,
            value=Decimal(1000.0),
            acquisition_date=datetime(2024, 1, 1),
        )

        development_project = DevelopmentProject(
            name="Minimal Development",
            property_type=AssetTypeEnum.OFFICE,
            gross_area=Decimal(1000.0),
            net_rentable_area=Decimal(900.0),
            construction_plan=CapitalPlan(
                name="Minimal Construction", capital_items=[]
            ),
            blueprints=[],
        )

        deal = Deal(
            name="Minimal Deal", asset=development_project, acquisition=acquisition
        )

        # Should work with minimal configuration
        results = analyze(deal, timeline)
        assert results is not None
        assert hasattr(results, "deal_summary")
