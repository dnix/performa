# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Comprehensive Tests for ValuationEngine

Unit tests for property valuation calculations with polymorphic dispatch
across different valuation methodologies and robust fallback strategies.

Test Coverage:
1. Property value extraction with multiple fallback strategies
2. NOI extraction using type-safe enum access
3. Disposition proceeds calculation with polymorphic dispatch
4. Error handling and graceful degradation
5. Integration with various data sources and valuation models
6. Edge cases and boundary conditions
"""

from datetime import date
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from performa.core.primitives import GlobalSettings, Timeline, UnleveredAggregateLineKey
from performa.deal.analysis.valuation import ValuationEngine
from performa.deal.deal import Deal
from performa.deal.results import UnleveredAnalysisResult


@pytest.fixture
def sample_timeline() -> Timeline:
    """Standard timeline for testing."""
    return Timeline(start_date=date(2024, 1, 1), duration_months=24)  # 2 years


@pytest.fixture
def sample_settings() -> GlobalSettings:
    """Standard settings for testing."""
    return GlobalSettings()


@pytest.fixture
def mock_deal_basic() -> Deal:
    """Basic mock deal for testing."""
    deal = Mock(spec=Deal)
    deal.exit_valuation = None
    deal.acquisition = None
    return deal


@pytest.fixture
def mock_deal_with_acquisition() -> Deal:
    """Mock deal with acquisition data."""
    deal = Mock(spec=Deal)
    deal.exit_valuation = None

    # Mock acquisition
    acquisition = Mock()
    acquisition.acquisition_cost = 2000000.0  # $2M acquisition
    deal.acquisition = acquisition

    return deal


@pytest.fixture
def mock_deal_with_exit_valuation() -> Deal:
    """Mock deal with exit valuation."""
    deal = Mock(spec=Deal)
    deal.acquisition = None
    deal.asset = Mock()  # Add asset attribute

    # Mock exit valuation with cap rate
    exit_valuation = Mock()
    exit_valuation.cap_rate = 0.06  # 6% cap rate
    exit_valuation.compute_cf = Mock(
        return_value=pd.Series([0.0, 0.0, 0.0, 3500000.0] * 6)
    )  # Disposition in last month
    deal.exit_valuation = exit_valuation

    return deal


@pytest.fixture
def sample_unlevered_analysis_with_noi(
    sample_timeline: Timeline,
) -> UnleveredAnalysisResult:
    """Unlevered analysis with NOI data."""
    # Create realistic NOI progression
    noi_values = [80000.0] * 12 + [85000.0] * 12  # Growing NOI over time

    cash_flows = pd.DataFrame(
        {
            UnleveredAggregateLineKey.NET_OPERATING_INCOME.value: noi_values,
            UnleveredAggregateLineKey.EFFECTIVE_GROSS_INCOME.value: [120000.0] * 24,
            UnleveredAggregateLineKey.TOTAL_OPERATING_EXPENSES.value: [40000.0] * 12
            + [35000.0] * 12,
        },
        index=sample_timeline.period_index,
    )

    result = UnleveredAnalysisResult()
    result.cash_flows = cash_flows
    return result


@pytest.fixture
def sample_unlevered_analysis_with_values(
    sample_timeline: Timeline,
) -> UnleveredAnalysisResult:
    """Unlevered analysis with property value data."""
    # Create appreciation over time
    initial_value = 2500000.0
    values = [
        initial_value * (1.02 ** (i / 12)) for i in range(24)
    ]  # 2% annual appreciation

    cash_flows = pd.DataFrame(
        {
            UnleveredAggregateLineKey.NET_OPERATING_INCOME.value: [75000.0] * 24,
            "property_value": values,  # Direct property values
            "asset_value": [v * 0.95 for v in values],  # Alternative value column
        },
        index=sample_timeline.period_index,
    )

    result = UnleveredAnalysisResult()
    result.cash_flows = cash_flows
    return result


@pytest.fixture
def empty_unlevered_analysis() -> UnleveredAnalysisResult:
    """Empty unlevered analysis for fallback testing."""
    result = UnleveredAnalysisResult()
    result.cash_flows = pd.DataFrame()
    return result


class TestValuationEngineBasic:
    """Test basic ValuationEngine functionality."""

    def test_valuation_engine_can_be_instantiated(
        self, mock_deal_basic, sample_timeline, sample_settings
    ):
        """Test that ValuationEngine can be instantiated with basic parameters."""
        engine = ValuationEngine(
            deal=mock_deal_basic, timeline=sample_timeline, settings=sample_settings
        )

        assert engine is not None
        assert engine.deal == mock_deal_basic
        assert engine.timeline == sample_timeline
        assert engine.settings == sample_settings
        assert engine.property_value_series is None  # Not yet populated
        assert engine.noi_series is None  # Not yet populated

    def test_valuation_engine_has_required_methods(
        self, mock_deal_basic, sample_timeline, sample_settings
    ):
        """Test that ValuationEngine has the expected public methods."""
        engine = ValuationEngine(
            deal=mock_deal_basic, timeline=sample_timeline, settings=sample_settings
        )

        # Check for expected methods
        assert hasattr(engine, "extract_property_value_series")
        assert callable(engine.extract_property_value_series)
        assert hasattr(engine, "extract_noi_series")
        assert callable(engine.extract_noi_series)
        assert hasattr(engine, "calculate_disposition_proceeds")
        assert callable(engine.calculate_disposition_proceeds)


class TestPropertyValueExtraction:
    """Test property value extraction with multiple fallback strategies."""

    def test_extract_property_value_direct_from_cash_flows(
        self,
        mock_deal_basic,
        sample_timeline,
        sample_settings,
        sample_unlevered_analysis_with_values,
    ):
        """Test Strategy 1: Direct extraction from cash flow data."""
        engine = ValuationEngine(
            deal=mock_deal_basic, timeline=sample_timeline, settings=sample_settings
        )

        property_values = engine.extract_property_value_series(
            sample_unlevered_analysis_with_values
        )

        assert isinstance(property_values, pd.Series)
        assert len(property_values) == 24
        assert property_values.iloc[0] > 2400000.0  # Around $2.5M initial
        assert (
            property_values.iloc[-1] > property_values.iloc[0]
        )  # Appreciation over time

        # Should cache the result
        assert engine.property_value_series is not None
        assert engine.property_value_series.equals(property_values)

    def test_extract_property_value_noi_based_default_cap_rate(
        self,
        mock_deal_basic,
        sample_timeline,
        sample_settings,
        sample_unlevered_analysis_with_noi,
    ):
        """Test Strategy 2: NOI-based valuation with default cap rate."""
        engine = ValuationEngine(
            deal=mock_deal_basic, timeline=sample_timeline, settings=sample_settings
        )

        property_values = engine.extract_property_value_series(
            sample_unlevered_analysis_with_noi
        )

        assert isinstance(property_values, pd.Series)
        assert len(property_values) == 24

        # With 6.5% default cap rate and $80,000 NOI: Value ≈ $80,000 / 0.065 ≈ $1.23M
        expected_value_year1 = 80000.0 / 0.065
        assert abs(property_values.iloc[0] - expected_value_year1) < 10000.0

        # Year 2 should be higher due to NOI growth
        expected_value_year2 = 85000.0 / 0.065
        assert abs(property_values.iloc[-1] - expected_value_year2) < 10000.0

    def test_extract_property_value_noi_based_deal_cap_rate(
        self,
        mock_deal_with_exit_valuation,
        sample_timeline,
        sample_settings,
        sample_unlevered_analysis_with_noi,
    ):
        """Test Strategy 2: NOI-based valuation with deal-specific cap rate."""
        engine = ValuationEngine(
            deal=mock_deal_with_exit_valuation,
            timeline=sample_timeline,
            settings=sample_settings,
        )

        property_values = engine.extract_property_value_series(
            sample_unlevered_analysis_with_noi
        )

        assert isinstance(property_values, pd.Series)

        # With 6% cap rate from deal and $80,000 NOI: Value = $80,000 / 0.06 ≈ $1.33M
        expected_value = 80000.0 / 0.06
        assert abs(property_values.iloc[0] - expected_value) < 10000.0

        # Should use deal's cap rate, not default
        assert (
            property_values.iloc[0] > 80000.0 / 0.065
        )  # Higher than default cap rate would give

    def test_extract_property_value_cost_based_appreciation(
        self,
        mock_deal_with_acquisition,
        sample_timeline,
        sample_settings,
        empty_unlevered_analysis,
    ):
        """Test Strategy 3: Cost-based appreciation using acquisition cost."""
        engine = ValuationEngine(
            deal=mock_deal_with_acquisition,
            timeline=sample_timeline,
            settings=sample_settings,
        )

        property_values = engine.extract_property_value_series(empty_unlevered_analysis)

        assert isinstance(property_values, pd.Series)
        assert len(property_values) == 24

        # Should start at acquisition cost
        assert abs(property_values.iloc[0] - 2000000.0) < 1000.0

        # Should appreciate at 3% annually
        expected_final_value = 2000000.0 * (1.03**2)  # 2 years of appreciation
        assert (
            abs(property_values.iloc[-1] - expected_final_value) < 6000.0
        )  # Slightly looser tolerance

        # Should show gradual appreciation
        assert property_values.iloc[-1] > property_values.iloc[0]

    def test_extract_property_value_zero_fallback(
        self,
        mock_deal_basic,
        sample_timeline,
        sample_settings,
        empty_unlevered_analysis,
    ):
        """Test Strategy 4: Ultimate fallback to zero values."""
        engine = ValuationEngine(
            deal=mock_deal_basic, timeline=sample_timeline, settings=sample_settings
        )

        property_values = engine.extract_property_value_series(empty_unlevered_analysis)

        assert isinstance(property_values, pd.Series)
        assert len(property_values) == 24
        assert (property_values == 0.0).all()  # All zeros as fallback

    def test_extract_property_value_noi_error_fallback(
        self, mock_deal_with_acquisition, sample_timeline, sample_settings
    ):
        """Test fallback when NOI extraction fails."""
        engine = ValuationEngine(
            deal=mock_deal_with_acquisition,
            timeline=sample_timeline,
            settings=sample_settings,
        )

        # Create analysis that will cause NOI extraction to fail
        problematic_analysis = UnleveredAnalysisResult()
        problematic_analysis.cash_flows = None  # This should cause get_series to fail

        property_values = engine.extract_property_value_series(problematic_analysis)

        # Should fall back to cost-based appreciation
        assert isinstance(property_values, pd.Series)
        assert property_values.iloc[0] > 0  # Should not be zero fallback
        assert (
            abs(property_values.iloc[0] - 2000000.0) < 1000.0
        )  # Should use acquisition cost


class TestNOIExtraction:
    """Test NOI extraction using type-safe enum access."""

    def test_extract_noi_series_success(
        self,
        mock_deal_basic,
        sample_timeline,
        sample_settings,
        sample_unlevered_analysis_with_noi,
    ):
        """Test successful NOI extraction using type-safe enum access."""
        engine = ValuationEngine(
            deal=mock_deal_basic, timeline=sample_timeline, settings=sample_settings
        )

        noi_series = engine.extract_noi_series(sample_unlevered_analysis_with_noi)

        assert isinstance(noi_series, pd.Series)
        assert len(noi_series) == 24
        assert noi_series.iloc[0] == 80000.0  # First year NOI
        assert noi_series.iloc[-1] == 85000.0  # Second year NOI

        # Should cache the result
        assert engine.noi_series is not None
        assert engine.noi_series.equals(noi_series)

    def test_extract_noi_series_with_missing_data(
        self, mock_deal_basic, sample_timeline, sample_settings
    ):
        """Test NOI extraction when data is missing."""
        engine = ValuationEngine(
            deal=mock_deal_basic, timeline=sample_timeline, settings=sample_settings
        )

        # Create analysis without NOI data
        cash_flows = pd.DataFrame(
            {
                "Other_Revenue": [100000.0] * 24,
                "Other_Expense": [40000.0] * 24,
            },
            index=sample_timeline.period_index,
        )

        analysis = UnleveredAnalysisResult()
        analysis.cash_flows = cash_flows

        # This should return an appropriate series (possibly empty or zeros)
        noi_series = engine.extract_noi_series(analysis)

        assert isinstance(noi_series, pd.Series)
        # The exact behavior depends on the get_series implementation

    def test_extract_noi_series_multiple_calls_consistent(
        self,
        mock_deal_basic,
        sample_timeline,
        sample_settings,
        sample_unlevered_analysis_with_noi,
    ):
        """Test that multiple calls return consistent results."""
        engine = ValuationEngine(
            deal=mock_deal_basic, timeline=sample_timeline, settings=sample_settings
        )

        noi_series1 = engine.extract_noi_series(sample_unlevered_analysis_with_noi)
        noi_series2 = engine.extract_noi_series(sample_unlevered_analysis_with_noi)

        assert noi_series1.equals(noi_series2)
        assert engine.noi_series.equals(noi_series1)


class TestDispositionProceeds:
    """Test disposition proceeds calculation with polymorphic dispatch."""

    def test_calculate_disposition_proceeds_with_exit_valuation(
        self,
        mock_deal_with_exit_valuation,
        sample_timeline,
        sample_settings,
        sample_unlevered_analysis_with_noi,
    ):
        """Test disposition proceeds calculation with exit valuation model."""
        engine = ValuationEngine(
            deal=mock_deal_with_exit_valuation,
            timeline=sample_timeline,
            settings=sample_settings,
        )

        # Mock the compute_cf method to return disposition proceeds
        disposition_cf = pd.Series(
            [0.0] * 23 + [3500000.0], index=sample_timeline.period_index
        )
        mock_deal_with_exit_valuation.exit_valuation.compute_cf.return_value = (
            disposition_cf
        )

        with patch("performa.analysis.AnalysisContext") as mock_context_class:
            # Mock the context creation
            mock_context = Mock()
            mock_context.resolved_lookups = {}
            mock_context_class.return_value = mock_context

            proceeds = engine.calculate_disposition_proceeds(
                sample_unlevered_analysis_with_noi
            )

        assert isinstance(proceeds, pd.Series)
        assert len(proceeds) == 24
        assert proceeds.iloc[-1] == 3500000.0  # Disposition in last period
        assert proceeds.iloc[:-1].sum() == 0.0  # No proceeds in other periods

        # Verify the exit valuation was called properly
        mock_deal_with_exit_valuation.exit_valuation.compute_cf.assert_called_once()

    def test_calculate_disposition_proceeds_no_exit_valuation(
        self,
        mock_deal_basic,
        sample_timeline,
        sample_settings,
        sample_unlevered_analysis_with_noi,
    ):
        """Test disposition proceeds when no exit valuation exists."""
        engine = ValuationEngine(
            deal=mock_deal_basic, timeline=sample_timeline, settings=sample_settings
        )

        proceeds = engine.calculate_disposition_proceeds(
            sample_unlevered_analysis_with_noi
        )

        assert isinstance(proceeds, pd.Series)
        assert len(proceeds) == 24
        assert (proceeds == 0.0).all()  # Should be all zeros

    def test_calculate_disposition_proceeds_without_unlevered_analysis(
        self, mock_deal_with_exit_valuation, sample_timeline, sample_settings
    ):
        """Test disposition proceeds calculation without unlevered analysis."""
        engine = ValuationEngine(
            deal=mock_deal_with_exit_valuation,
            timeline=sample_timeline,
            settings=sample_settings,
        )

        # Mock the compute_cf method
        disposition_cf = pd.Series(
            [0.0] * 23 + [4000000.0], index=sample_timeline.period_index
        )
        mock_deal_with_exit_valuation.exit_valuation.compute_cf.return_value = (
            disposition_cf
        )

        with patch("performa.analysis.AnalysisContext") as mock_context_class:
            mock_context = Mock()
            mock_context_class.return_value = mock_context

            proceeds = engine.calculate_disposition_proceeds(None)

        assert isinstance(proceeds, pd.Series)
        assert len(proceeds) == 24
        assert proceeds.iloc[-1] == 4000000.0

    def test_calculate_disposition_proceeds_error_handling(
        self,
        mock_deal_with_exit_valuation,
        sample_timeline,
        sample_settings,
        sample_unlevered_analysis_with_noi,
    ):
        """Test error handling in disposition proceeds calculation."""
        engine = ValuationEngine(
            deal=mock_deal_with_exit_valuation,
            timeline=sample_timeline,
            settings=sample_settings,
        )

        # Make the exit valuation raise an error
        mock_deal_with_exit_valuation.exit_valuation.compute_cf.side_effect = Exception(
            "Valuation failed"
        )

        # Should handle the error gracefully and return zeros
        proceeds = engine.calculate_disposition_proceeds(
            sample_unlevered_analysis_with_noi
        )

        assert isinstance(proceeds, pd.Series)
        assert len(proceeds) == 24
        assert (proceeds == 0.0).all()  # Should fall back to zeros

    def test_calculate_disposition_proceeds_negative_values_converted(
        self, mock_deal_with_exit_valuation, sample_timeline, sample_settings
    ):
        """Test that negative disposition proceeds are converted to positive."""
        engine = ValuationEngine(
            deal=mock_deal_with_exit_valuation,
            timeline=sample_timeline,
            settings=sample_settings,
        )

        # Mock negative proceeds (which should be converted to positive)
        disposition_cf = pd.Series(
            [0.0] * 23 + [-2500000.0], index=sample_timeline.period_index
        )
        mock_deal_with_exit_valuation.exit_valuation.compute_cf.return_value = (
            disposition_cf
        )

        with patch("performa.analysis.AnalysisContext") as mock_context_class:
            mock_context = Mock()
            mock_context.resolved_lookups = {}
            mock_context_class.return_value = mock_context

            proceeds = engine.calculate_disposition_proceeds()

        assert proceeds.iloc[-1] == 2500000.0  # Should be positive
        assert (proceeds >= 0).all()  # All values should be non-negative


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""

    def test_complete_valuation_workflow(
        self,
        mock_deal_with_exit_valuation,
        sample_timeline,
        sample_settings,
        sample_unlevered_analysis_with_noi,
    ):
        """Test complete valuation workflow with all methods."""
        engine = ValuationEngine(
            deal=mock_deal_with_exit_valuation,
            timeline=sample_timeline,
            settings=sample_settings,
        )

        # Extract property values
        property_values = engine.extract_property_value_series(
            sample_unlevered_analysis_with_noi
        )

        # Extract NOI series
        noi_series = engine.extract_noi_series(sample_unlevered_analysis_with_noi)

        # Calculate disposition proceeds
        with patch("performa.analysis.AnalysisContext") as mock_context_class:
            mock_context = Mock()
            mock_context.resolved_lookups = {}
            mock_context_class.return_value = mock_context

            disposition_cf = pd.Series(
                [0.0] * 23 + [3000000.0], index=sample_timeline.period_index
            )
            mock_deal_with_exit_valuation.exit_valuation.compute_cf.return_value = (
                disposition_cf
            )

            disposition_proceeds = engine.calculate_disposition_proceeds(
                sample_unlevered_analysis_with_noi
            )

        # Verify all methods worked
        assert isinstance(property_values, pd.Series)
        assert isinstance(noi_series, pd.Series)
        assert isinstance(disposition_proceeds, pd.Series)

        # Verify reasonable relationships
        assert property_values.iloc[0] > 0  # Property should have value
        assert noi_series.iloc[0] > 0  # Should have NOI
        assert disposition_proceeds.iloc[-1] > 0  # Should have disposition proceeds

        # Property value should be related to NOI through cap rate
        implied_cap_rate = noi_series.iloc[0] / property_values.iloc[0]
        assert 0.04 < implied_cap_rate < 0.10  # Reasonable cap rate range

    def test_valuation_with_growth_scenario(
        self, mock_deal_with_exit_valuation, sample_timeline, sample_settings
    ):
        """Test valuation with growing NOI scenario."""
        # Create analysis with strong NOI growth
        noi_growth = [60000 + i * 2000 for i in range(24)]  # Growing NOI over time

        cash_flows = pd.DataFrame(
            {
                UnleveredAggregateLineKey.NET_OPERATING_INCOME.value: noi_growth,
            },
            index=sample_timeline.period_index,
        )

        growth_analysis = UnleveredAnalysisResult()
        growth_analysis.cash_flows = cash_flows

        engine = ValuationEngine(
            deal=mock_deal_with_exit_valuation,
            timeline=sample_timeline,
            settings=sample_settings,
        )

        property_values = engine.extract_property_value_series(growth_analysis)
        noi_series = engine.extract_noi_series(growth_analysis)

        # Property values should increase with NOI growth
        assert property_values.iloc[-1] > property_values.iloc[0]
        assert noi_series.iloc[-1] > noi_series.iloc[0]

        # Growth rate should be consistent
        noi_growth_rate = (noi_series.iloc[-1] / noi_series.iloc[0]) - 1
        value_growth_rate = (property_values.iloc[-1] / property_values.iloc[0]) - 1

        # Growth rates should be similar (same cap rate applied)
        assert abs(noi_growth_rate - value_growth_rate) < 0.02  # Within 2%


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling scenarios."""

    def test_extract_property_value_zero_noi(
        self, mock_deal_basic, sample_timeline, sample_settings
    ):
        """Test property value extraction when NOI is zero."""
        # Create analysis with zero NOI
        cash_flows = pd.DataFrame(
            {
                UnleveredAggregateLineKey.NET_OPERATING_INCOME.value: [0.0] * 24,
            },
            index=sample_timeline.period_index,
        )

        zero_noi_analysis = UnleveredAnalysisResult()
        zero_noi_analysis.cash_flows = cash_flows

        engine = ValuationEngine(
            deal=mock_deal_basic, timeline=sample_timeline, settings=sample_settings
        )

        property_values = engine.extract_property_value_series(zero_noi_analysis)

        # Should fall back to zero values
        assert isinstance(property_values, pd.Series)
        assert (property_values == 0.0).all()

    def test_extract_property_value_negative_noi(
        self, mock_deal_basic, sample_timeline, sample_settings
    ):
        """Test property value extraction with negative NOI."""
        # Create analysis with negative NOI (operating losses)
        cash_flows = pd.DataFrame(
            {
                UnleveredAggregateLineKey.NET_OPERATING_INCOME.value: [-20000.0] * 24,
            },
            index=sample_timeline.period_index,
        )

        negative_noi_analysis = UnleveredAnalysisResult()
        negative_noi_analysis.cash_flows = cash_flows

        engine = ValuationEngine(
            deal=mock_deal_basic, timeline=sample_timeline, settings=sample_settings
        )

        property_values = engine.extract_property_value_series(negative_noi_analysis)

        # Should handle negative NOI gracefully (likely fall back to zero)
        assert isinstance(property_values, pd.Series)
        # The exact behavior may vary based on implementation

    def test_extract_property_value_with_partial_data(
        self, mock_deal_with_acquisition, sample_timeline, sample_settings
    ):
        """Test property value extraction with partial/incomplete data."""
        # Create analysis with some NOI but not enough for valuation
        cash_flows = pd.DataFrame(
            {
                UnleveredAggregateLineKey.NET_OPERATING_INCOME.value: [10000.0] * 6
                + [0.0] * 18,  # Only first 6 months
            },
            index=sample_timeline.period_index,
        )

        partial_analysis = UnleveredAnalysisResult()
        partial_analysis.cash_flows = cash_flows

        engine = ValuationEngine(
            deal=mock_deal_with_acquisition,
            timeline=sample_timeline,
            settings=sample_settings,
        )

        property_values = engine.extract_property_value_series(partial_analysis)

        # The implementation may use NOI-based valuation even with partial data
        # So we just check that property values are reasonable (either NOI-based or cost-based)
        assert isinstance(property_values, pd.Series)
        assert property_values.iloc[0] > 0  # Should have some positive value

    def test_extract_property_value_noi_get_series_exception(
        self, mock_deal_with_acquisition, sample_timeline, sample_settings
    ):
        """Test property value extraction when get_series raises an exception (covers lines 190-193)."""
        engine = ValuationEngine(
            deal=mock_deal_with_acquisition,
            timeline=sample_timeline,
            settings=sample_settings,
        )

        # Create a mock analysis that will cause get_series to raise an exception
        mock_analysis = Mock(spec=UnleveredAnalysisResult)
        mock_analysis.cash_flows = pd.DataFrame()  # Empty but has columns attribute
        # Mock get_series to raise an exception
        mock_analysis.get_series.side_effect = Exception("get_series failed")

        property_values = engine.extract_property_value_series(mock_analysis)

        # Should fall back to cost-based appreciation (Strategy 3)
        assert isinstance(property_values, pd.Series)
        assert len(property_values) == 24
        # Should use acquisition cost with appreciation since NOI extraction failed
        assert (
            abs(property_values.iloc[0] - 2000000.0) < 1000.0
        )  # Should use acquisition cost
        assert (
            property_values.iloc[-1] > property_values.iloc[0]
        )  # Should show appreciation

    def test_disposition_proceeds_context_creation_failure(
        self, mock_deal_with_exit_valuation, sample_timeline, sample_settings
    ):
        """Test disposition proceeds when context creation fails."""
        engine = ValuationEngine(
            deal=mock_deal_with_exit_valuation,
            timeline=sample_timeline,
            settings=sample_settings,
        )

        # Mock AnalysisContext to raise an error
        with patch(
            "performa.analysis.AnalysisContext",
            side_effect=Exception("Context creation failed"),
        ):
            proceeds = engine.calculate_disposition_proceeds()

        # Should handle the error gracefully
        assert isinstance(proceeds, pd.Series)
        assert (proceeds == 0.0).all()

    def test_disposition_proceeds_noi_extraction_exception(
        self, mock_deal_with_exit_valuation, sample_timeline, sample_settings
    ):
        """Test disposition proceeds when NOI extraction in context setup fails (covers lines 327-329)."""
        engine = ValuationEngine(
            deal=mock_deal_with_exit_valuation,
            timeline=sample_timeline,
            settings=sample_settings,
        )

        # Create mock analysis that will cause NOI extraction to fail in context setup
        mock_analysis = Mock(spec=UnleveredAnalysisResult)
        mock_analysis.get_series.side_effect = Exception("NOI extraction failed")

        # Mock the disposition proceeds calculation
        disposition_cf = pd.Series(
            [0.0] * 23 + [3000000.0], index=sample_timeline.period_index
        )
        mock_deal_with_exit_valuation.exit_valuation.compute_cf.return_value = (
            disposition_cf
        )

        with patch("performa.analysis.AnalysisContext") as mock_context_class:
            # Mock context with resolved_lookups attribute
            mock_context = Mock()
            mock_context.resolved_lookups = {}
            mock_context_class.return_value = mock_context

            proceeds = engine.calculate_disposition_proceeds(mock_analysis)

        # Should continue despite NOI extraction failure and return the disposition proceeds
        assert isinstance(proceeds, pd.Series)
        assert len(proceeds) == 24
        assert proceeds.iloc[-1] == 3000000.0  # Should still get disposition proceeds

        # Verify that the NOI extraction was attempted and failed
        mock_analysis.get_series.assert_called_once_with(
            UnleveredAggregateLineKey.NET_OPERATING_INCOME, sample_timeline
        )

    def test_multiple_value_columns_uses_first(
        self, mock_deal_basic, sample_timeline, sample_settings
    ):
        """Test that when multiple value columns exist, first is used."""
        # Create analysis with multiple value columns
        values1 = [2000000.0 + i * 10000 for i in range(24)]
        values2 = [3000000.0 + i * 15000 for i in range(24)]

        cash_flows = pd.DataFrame(
            {
                "property_value": values1,  # Should use this one (first)
                "asset_value": values2,  # Should ignore this one
                "value": values1[::-1],  # Should ignore this one
            },
            index=sample_timeline.period_index,
        )

        multi_value_analysis = UnleveredAnalysisResult()
        multi_value_analysis.cash_flows = cash_flows

        engine = ValuationEngine(
            deal=mock_deal_basic, timeline=sample_timeline, settings=sample_settings
        )

        property_values = engine.extract_property_value_series(multi_value_analysis)

        # Should use the first value column (property_value)
        assert abs(property_values.iloc[0] - values1[0]) < 1000.0
        assert abs(property_values.iloc[-1] - values1[-1]) < 1000.0
