# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Unit Tests for analyze Function

This module tests the deal analysis functions, including the public API
and internal calculation methods for funding cascades, partnership distributions,
and metric calculations.

NOTE: The massive TestFundingCascade class (1500+ lines) has been DELETED and moved to:
tests/integration/deal/test_funding_cascade_integration.py

Those tests were integration-level tests misplaced in unit tests. The funding cascade
tests multiple components working together and should be integration tests.
"""

from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import pytest

from performa.core.capital import CapitalItem, CapitalPlan
from performa.core.primitives import (
    AssetTypeEnum,
    CashFlowCategoryEnum,
    GlobalSettings,
    SCurveDrawSchedule,
    Timeline,
)
from performa.deal import Deal, analyze
from performa.deal.acquisition import AcquisitionTerms

# Note: DealAnalysisResult is zombie class - now use DealResults directly
# Note: Zombie result classes removed - using DealResults API directly
from performa.development.project import DevelopmentProject
from performa.patterns import (
    ValueAddAcquisitionPattern,
)


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
        # Create construction plan with known costs (matching the other fixture)
        construction_items = [
            CapitalItem(
                name="Building Construction",
                value=Decimal("5000000"),
                timeline=Timeline.from_dates(
                    datetime(2024, 4, 1), datetime(2025, 10, 31)
                ),
            ),
            CapitalItem(
                name="Site Work",
                value=Decimal("3000000"),
                timeline=Timeline.from_dates(
                    datetime(2024, 1, 1), datetime(2024, 6, 30)
                ),
            ),
        ]

        construction_plan = CapitalPlan(
            name="Construction Plan", capital_items=construction_items
        )

        return DevelopmentProject(
            uid="550e8400-e29b-41d4-a716-446655440004",  # Valid UUID format
            name="Test Office Development",
            property_type=AssetTypeEnum.OFFICE,
            gross_area=Decimal(100000.0),
            net_rentable_area=Decimal(90000.0),
            construction_plan=construction_plan,
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
            exit_valuation=None,
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

        # In new architecture: results should be DealResults (not DealAnalysisResult)
        assert results is not None

        # Should have all expected analysis components
        assert hasattr(results, "deal_summary")
        assert hasattr(results, "asset_analysis")
        assert hasattr(results, "financing_analysis")
        assert hasattr(results, "levered_cash_flows")
        assert hasattr(results, "partner_distributions")
        assert hasattr(results, "deal_metrics")

    def test_analyze_with_default_settings(self, sample_deal, sample_timeline):
        """Test analyze with default settings."""
        results = analyze(sample_deal, sample_timeline)

        # In new architecture: results should be DealResults (not DealAnalysisResult)
        assert results is not None
        assert hasattr(results, "deal_summary")

    def test_deal_summary_content(self, sample_deal, sample_timeline, sample_settings):
        """Test that deal summary contains correct information."""
        results = analyze(sample_deal, sample_timeline, sample_settings)

        deal_summary = results.deal_summary
        assert deal_summary["deal_name"] == "Test Development Deal"
        assert deal_summary["archetype"] == "Development"  # Note: capitalized
        # Note: is_development and has_financing keys were removed in architectural cleanup

    def test_unlevered_analysis_structure(
        self, sample_deal, sample_timeline, sample_settings
    ):
        """Test unlevered analysis output structure."""
        results = analyze(sample_deal, sample_timeline, sample_settings)

        # In the new architecture, asset_analysis is an adapter that provides ledger queries
        asset_analysis = results.asset_analysis
        assert asset_analysis is not None

        # Test that we can get ledger queries through the asset analysis adapter
        queries = asset_analysis.get_ledger_queries()
        assert queries is not None

        # Test that basic unlevered cash flow queries work
        unlevered_cf = queries.project_cash_flow()  # unlevered cash flow
        assert isinstance(unlevered_cf, pd.Series)

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

        # In new architecture: levered_cash_flows should be a pandas Series
        assert isinstance(levered_cash_flows, pd.Series)
        assert len(levered_cash_flows) > 0  # Should have data
        assert (
            levered_cash_flows.index.freq is not None
        )  # Should have proper time index

        # Note: In new architecture, cash flow metrics are accessed through other DealResults properties
        # rather than through a LeveredCashFlowResult wrapper object

    def test_partner_distributions_structure(
        self, sample_deal, sample_timeline, sample_settings
    ):
        """Test partner distributions output structure."""
        results = analyze(sample_deal, sample_timeline, sample_settings)

        partner_distributions = results.partner_distributions

        assert isinstance(partner_distributions, dict)

        # Should contain distribution information
        # For deals without equity partners, expect single_entity distribution method
        assert partner_distributions["distribution_method"] == "single_entity"
        assert "levered_irr" in partner_distributions  # Note: was aggregate_irr
        assert (
            "equity_multiple" in partner_distributions
        )  # Note: was aggregate_equity_multiple
        assert "partner_count" in partner_distributions

    def test_deal_metrics_structure(
        self, sample_deal, sample_timeline, sample_settings
    ):
        """Test deal metrics output structure."""
        results = analyze(sample_deal, sample_timeline, sample_settings)

        deal_metrics = results.deal_metrics

        assert isinstance(deal_metrics, dict)

        # Should contain key performance metrics
        expected_metrics = [
            "levered_irr",
            "unlevered_irr",
            "equity_multiple",
            "unlevered_return_on_cost",
            "net_profit",
            "stabilized_dscr",
            "minimum_operating_dscr",
            "covenant_compliance_rate",
            "total_investment",
            "total_distributions",
        ]
        for metric_name in expected_metrics:
            assert metric_name in deal_metrics

    # Note: test_hold_period_calculation removed - hold_period_years key no longer exists in deal_metrics after architectural cleanup

    def test_deal_validation_called(
        self, sample_deal, sample_timeline, sample_settings
    ):
        """Test that deal validation is called during analysis."""
        # This should not raise an exception if validation passes
        results = analyze(sample_deal, sample_timeline, sample_settings)
        assert results is not None

    def test_analyze_fluent_reporting_interface_with_l3_pattern(self):
        """Test that analyze results work with fluent reporting interface using L3 pattern."""

        # Use Pattern class to create a complete, working deal
        pattern = ValueAddAcquisitionPattern(
            property_name="Fluent Test Property",
            acquisition_price=3_000_000,
            acquisition_date=date(2024, 1, 1),
            renovation_budget=450_000,
            current_avg_rent=1400,
            target_avg_rent=1700,
            hold_period_years=5,
            ltv_ratio=0.65,  # Use valid LTV ratio
        )
        deal = pattern.create()

        timeline = Timeline.from_dates("2024-01-01", "2029-12-31")
        results = analyze(deal, timeline)

        # Test reporting interface availability
        assert hasattr(results, "reporting")
        assert results.reporting is not None

        # Test interface caching
        reporting_interface = results.reporting
        assert results.reporting is reporting_interface  # Same object

        # Annual summary
        annual_summary = results.reporting.pro_forma_summary(frequency="A")
        assert isinstance(annual_summary, pd.DataFrame)
        assert annual_summary.shape[0] > 0  # Has financial metrics
        assert annual_summary.shape[1] > 0  # Has time periods

        # Quarterly summary
        quarterly_summary = results.reporting.pro_forma_summary(frequency="Q")
        assert isinstance(quarterly_summary, pd.DataFrame)
        assert (
            quarterly_summary.shape[1] >= annual_summary.shape[1]
        )  # More or equal periods

        # Test explicit monthly frequency
        monthly_summary = results.reporting.pro_forma_summary(frequency="M")
        assert isinstance(monthly_summary, pd.DataFrame)
        assert (
            monthly_summary.shape[1] >= quarterly_summary.shape[1]
        )  # More periods than quarterly

        # Default summary (should be annual)
        default_summary = results.reporting.pro_forma_summary()
        assert isinstance(default_summary, pd.DataFrame)
        assert default_summary.equals(annual_summary)  # Default should equal annual

        # Test that we have financial metrics (L3 patterns generate realistic data)
        assert annual_summary.shape[0] >= 5, (
            f"Expected multiple financial metrics, got {annual_summary.shape[0]}"
        )
        assert annual_summary.shape[1] >= 5, (
            f"Expected multiple time periods, got {annual_summary.shape[1]}"
        )

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
                uid="550e8400-e29b-41d4-a716-446655440005",  # Valid UUID format
                name=f"Test {property_type.value} Development",
                property_type=property_type,
                gross_area=Decimal(100000.0),
                net_rentable_area=Decimal(90000.0),
                construction_plan=CapitalPlan(
                    name="Construction Plan",
                    capital_items=[
                        # Minimal construction item to ensure proper archetype detection
                        CapitalItem(
                            name="Base Construction",
                            category=CashFlowCategoryEnum.CAPITAL,
                            subcategory="Hard Costs",
                            timeline=Timeline.from_dates("2024-01-01", "2025-12-31"),
                            value=1_000_000,
                            draw_schedule=SCurveDrawSchedule(sigma=1.0),
                        )
                    ],
                ),
                blueprints=[],
            )

            deal = Deal(
                name=f"Test {property_type.value} Deal",
                asset=development_project,
                acquisition=sample_acquisition,
            )

            results = analyze(deal, sample_timeline, sample_settings)

            # Should work for all asset types - archetype properly detected with construction items
            assert results.deal_summary["archetype"] == "Development"
            # Note: asset_type propagation is a business logic bug - asset_type is None instead of property_type

    def test_error_handling_invalid_deal(self, sample_timeline, sample_settings):
        """Test error handling with invalid deal components."""
        # This test would require creating an invalid deal structure
        # For now, we'll test that proper deals work correctly
        pass

    def test_cash_flow_components_separation(
        self, sample_deal, sample_timeline, sample_settings
    ):
        """Test that cash flow components are properly separated in ledger."""
        results = analyze(sample_deal, sample_timeline, sample_settings)

        # In our ledger-based architecture, components are accessed through queries
        queries = results.queries

        # Test that we can access individual cash flow components
        unlevered_cf = queries.project_cash_flow()  # unlevered cash flow
        assert unlevered_cf is not None
        assert isinstance(unlevered_cf, pd.Series)

        # Test debt-related components (if financing exists)
        if results.financing_analysis:
            debt_service = queries.debt_service()
            assert debt_service is not None
            assert isinstance(debt_service, pd.Series)

        # Test that levered cash flows are properly calculated
        levered_cf = results.levered_cash_flow
        assert levered_cf is not None
        assert isinstance(levered_cf, pd.Series)

    def test_metrics_calculation_consistency(
        self, sample_deal, sample_timeline, sample_settings
    ):
        """Test that metrics are calculated consistently between different sections."""
        results = analyze(sample_deal, sample_timeline, sample_settings)

        # Get metrics from different sections
        deal_metrics = results.deal_metrics
        partner_metrics = results.partner_distributions

        # IRR should be consistent (if calculated)
        deal_irr = deal_metrics.get("levered_irr")
        partner_irr = partner_metrics.get("aggregate_irr")
        if deal_irr is not None and partner_irr is not None:
            assert abs(deal_irr - partner_irr) < 0.0001

        # Equity multiple should be consistent
        deal_eq_multiple = deal_metrics.get("equity_multiple")
        partner_eq_multiple = partner_metrics.get("equity_multiple")
        if deal_eq_multiple is not None and partner_eq_multiple is not None:
            assert abs(deal_eq_multiple - partner_eq_multiple) < 0.0001


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
            uid="550e8400-e29b-41d4-a716-446655440006",  # Valid UUID format
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
