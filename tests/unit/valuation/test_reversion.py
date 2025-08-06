# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Comprehensive Tests for ReversionValuation

Unit tests for universal reversion valuation covering exit strategy modeling
for any property type with cap rate methodologies.

Test Coverage:
1. Model instantiation and validation
2. Parameter validation (cap rates, transaction costs, hold periods)
3. Gross value calculations (simple and mixed-use)
4. Net proceeds calculations after transaction costs
5. Reversion metrics calculations
6. Cash flow computation (compute_cf method)
7. Factory methods (conservative, aggressive)
8. Edge cases and error handling
9. Mixed-use property scenarios
10. Integration with analysis context
"""

from datetime import date
from unittest.mock import Mock
from uuid import UUID

import pandas as pd
import pytest
from pydantic import ValidationError

from performa.core.primitives import GlobalSettings, Timeline, UnleveredAggregateLineKey
from performa.deal.results import UnleveredAnalysisResult
from performa.valuation.reversion import ReversionValuation


@pytest.fixture
def sample_timeline() -> Timeline:
    """Standard timeline for testing."""
    return Timeline(start_date=date(2024, 1, 1), duration_months=24)  # 2 years


@pytest.fixture
def sample_settings() -> GlobalSettings:
    """Standard settings for testing."""
    return GlobalSettings()


@pytest.fixture
def mock_analysis_context(sample_timeline: Timeline, sample_settings: GlobalSettings):
    """Mock analysis context for testing."""
    context = Mock()
    context.timeline = sample_timeline
    context.settings = sample_settings
    context.resolved_lookups = {}
    return context


@pytest.fixture
def sample_unlevered_analysis(sample_timeline: Timeline) -> UnleveredAnalysisResult:
    """Sample unlevered analysis with NOI data."""
    # Create realistic NOI progression with growth
    noi_values = [75000.0] * 12 + [80000.0] * 12  # Monthly NOI growing over time

    cash_flows = pd.DataFrame(
        {
            UnleveredAggregateLineKey.NET_OPERATING_INCOME.value: noi_values,
            UnleveredAggregateLineKey.EFFECTIVE_GROSS_INCOME.value: [110000.0] * 24,
            UnleveredAggregateLineKey.TOTAL_OPERATING_EXPENSES.value: [35000.0] * 12
            + [30000.0] * 12,
        },
        index=sample_timeline.period_index,
    )

    result = UnleveredAnalysisResult()
    result.cash_flows = cash_flows
    return result


class TestReversionValuationBasic:
    """Test basic ReversionValuation functionality."""

    def test_reversion_valuation_can_be_instantiated(self):
        """Test that ReversionValuation can be instantiated with basic parameters."""
        reversion = ReversionValuation(
            name="Standard Sale", cap_rate=0.065, transaction_costs_rate=0.025
        )

        assert reversion.name == "Standard Sale"
        assert reversion.cap_rate == 0.065
        assert reversion.transaction_costs_rate == 0.025
        assert reversion.kind == "reversion"
        assert isinstance(reversion.uid, UUID)
        assert reversion.hold_period_months is None
        assert reversion.cap_rates_by_use is None

    def test_reversion_valuation_with_optional_parameters(self):
        """Test ReversionValuation with all optional parameters."""
        cap_rates_by_use = {"office": 0.055, "retail": 0.070, "residential": 0.045}

        reversion = ReversionValuation(
            name="Mixed-Use Sale",
            cap_rate=0.060,
            transaction_costs_rate=0.030,
            hold_period_months=36,
            cap_rates_by_use=cap_rates_by_use,
        )

        assert reversion.name == "Mixed-Use Sale"
        assert reversion.cap_rate == 0.060
        assert reversion.transaction_costs_rate == 0.030
        assert reversion.hold_period_months == 36
        assert reversion.cap_rates_by_use == cap_rates_by_use

    def test_reversion_valuation_has_required_methods(self):
        """Test that ReversionValuation has expected methods."""
        reversion = ReversionValuation(name="Test", cap_rate=0.065)

        # Check for expected methods
        assert hasattr(reversion, "calculate_gross_value")
        assert callable(reversion.calculate_gross_value)
        assert hasattr(reversion, "calculate_net_proceeds")
        assert callable(reversion.calculate_net_proceeds)
        assert hasattr(reversion, "calculate_metrics")
        assert callable(reversion.calculate_metrics)
        assert hasattr(reversion, "compute_cf")
        assert callable(reversion.compute_cf)

        # Check for factory methods
        assert hasattr(ReversionValuation, "conservative")
        assert callable(ReversionValuation.conservative)
        assert hasattr(ReversionValuation, "aggressive")
        assert callable(ReversionValuation.aggressive)


class TestParameterValidation:
    """Test parameter validation for ReversionValuation."""

    def test_valid_cap_rate_range(self):
        """Test that valid cap rates are accepted."""
        valid_cap_rates = [0.01, 0.045, 0.065, 0.08, 0.12, 0.20]

        for cap_rate in valid_cap_rates:
            reversion = ReversionValuation(name="Test", cap_rate=cap_rate)
            assert reversion.cap_rate == cap_rate

    def test_invalid_cap_rate_too_low(self):
        """Test that cap rates below 1% are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ReversionValuation(name="Test", cap_rate=0.005)  # 0.5%

        assert "Cap rate (0.5%) should be between 1% and 20%" in str(exc_info.value)

    def test_invalid_cap_rate_too_high(self):
        """Test that cap rates above 20% are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ReversionValuation(name="Test", cap_rate=0.25)  # 25%

        assert "Cap rate (25.0%) should be between 1% and 20%" in str(exc_info.value)

    def test_valid_transaction_costs_range(self):
        """Test that valid transaction costs are accepted."""
        valid_costs = [0.005, 0.015, 0.025, 0.040, 0.075, 0.10]

        for cost_rate in valid_costs:
            reversion = ReversionValuation(
                name="Test", cap_rate=0.065, transaction_costs_rate=cost_rate
            )
            assert reversion.transaction_costs_rate == cost_rate

    def test_invalid_transaction_costs_too_low(self):
        """Test that transaction costs below 0.5% are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ReversionValuation(
                name="Test",
                cap_rate=0.065,
                transaction_costs_rate=0.002,  # 0.2%
            )

        assert "Transaction costs rate (0.2%) should be between 0.5% and 10%" in str(
            exc_info.value
        )

    def test_invalid_transaction_costs_too_high(self):
        """Test that transaction costs above 10% are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ReversionValuation(
                name="Test",
                cap_rate=0.065,
                transaction_costs_rate=0.15,  # 15%
            )

        assert "Transaction costs rate (15.0%) should be between 0.5% and 10%" in str(
            exc_info.value
        )

    def test_invalid_asset_specific_cap_rates(self):
        """Test validation of asset-specific cap rates."""
        with pytest.raises(ValidationError) as exc_info:
            ReversionValuation(
                name="Test",
                cap_rate=0.065,
                cap_rates_by_use={
                    "office": 0.055,
                    "retail": 0.25,  # Invalid - too high
                    "residential": 0.045,
                },
            )

        assert "Cap rate for retail (25.0%) should be between 1% and 20%" in str(
            exc_info.value
        )


class TestComputedProperties:
    """Test computed properties of ReversionValuation."""

    def test_net_sale_proceeds_rate(self):
        """Test net sale proceeds rate calculation."""
        test_cases = [
            (0.025, 0.975),  # 2.5% costs = 97.5% net
            (0.030, 0.970),  # 3.0% costs = 97.0% net
            (0.050, 0.950),  # 5.0% costs = 95.0% net
        ]

        for transaction_costs, expected_net_rate in test_cases:
            reversion = ReversionValuation(
                name="Test", cap_rate=0.065, transaction_costs_rate=transaction_costs
            )

            assert abs(reversion.net_sale_proceeds_rate - expected_net_rate) < 0.001


class TestGrossValueCalculations:
    """Test gross value calculation methods."""

    def test_calculate_gross_value_simple(self):
        """Test simple gross value calculation with single cap rate."""
        reversion = ReversionValuation(name="Test", cap_rate=0.065)

        test_cases = [
            (100000.0, 100000.0 / 0.065),  # $100k NOI
            (150000.0, 150000.0 / 0.065),  # $150k NOI
            (200000.0, 200000.0 / 0.065),  # $200k NOI
        ]

        for noi, expected_value in test_cases:
            gross_value = reversion.calculate_gross_value(noi)
            assert abs(gross_value - expected_value) < 1000.0

    def test_calculate_gross_value_mixed_use_with_specific_cap_rates(self):
        """Test gross value calculation for mixed-use with asset-specific cap rates."""
        reversion = ReversionValuation(
            name="Mixed-Use",
            cap_rate=0.065,  # Blended rate (not used when specific rates provided)
            cap_rates_by_use={"office": 0.055, "retail": 0.070, "residential": 0.045},
        )

        noi_by_use = {
            "office": 60000.0,  # $60k office NOI
            "retail": 30000.0,  # $30k retail NOI
            "residential": 40000.0,  # $40k residential NOI
        }

        # Expected: 60k/0.055 + 30k/0.070 + 40k/0.045
        expected_value = (60000.0 / 0.055) + (30000.0 / 0.070) + (40000.0 / 0.045)

        gross_value = reversion.calculate_gross_value(
            stabilized_noi=130000.0,  # Total NOI (should be ignored when noi_by_use provided)
            noi_by_use=noi_by_use,
        )

        assert abs(gross_value - expected_value) < 1000.0

    def test_calculate_gross_value_mixed_use_with_unknown_asset_type(self):
        """Test mixed-use calculation when some asset types don't have specific cap rates."""
        reversion = ReversionValuation(
            name="Mixed-Use",
            cap_rate=0.065,  # Fallback rate
            cap_rates_by_use={
                "office": 0.055,
                "retail": 0.070,
                # No rate for "industrial"
            },
        )

        noi_by_use = {
            "office": 60000.0,
            "retail": 30000.0,
            "industrial": 20000.0,  # Will use fallback cap rate
        }

        # Expected: 60k/0.055 + 30k/0.070 + 20k/0.065 (fallback)
        expected_value = (60000.0 / 0.055) + (30000.0 / 0.070) + (20000.0 / 0.065)

        gross_value = reversion.calculate_gross_value(
            stabilized_noi=110000.0, noi_by_use=noi_by_use
        )

        assert abs(gross_value - expected_value) < 1000.0

    def test_calculate_gross_value_zero_noi(self):
        """Test gross value calculation with zero NOI."""
        reversion = ReversionValuation(name="Test", cap_rate=0.065)

        gross_value = reversion.calculate_gross_value(0.0)
        assert gross_value == 0.0


class TestNetProceedsCalculations:
    """Test net proceeds calculation methods."""

    def test_calculate_net_proceeds_simple(self):
        """Test simple net proceeds calculation."""
        reversion = ReversionValuation(
            name="Test",
            cap_rate=0.065,
            transaction_costs_rate=0.025,  # 2.5%
        )

        noi = 100000.0
        gross_value = noi / 0.065  # ≈ $1,538,462
        expected_net_proceeds = gross_value * 0.975  # After 2.5% costs

        net_proceeds = reversion.calculate_net_proceeds(noi)
        assert abs(net_proceeds - expected_net_proceeds) < 1000.0

    def test_calculate_net_proceeds_mixed_use(self):
        """Test net proceeds calculation for mixed-use property."""
        reversion = ReversionValuation(
            name="Mixed-Use",
            cap_rate=0.065,
            transaction_costs_rate=0.030,  # 3.0%
            cap_rates_by_use={"office": 0.055, "retail": 0.070},
        )

        noi_by_use = {"office": 80000.0, "retail": 40000.0}

        # Calculate expected gross value
        gross_value = (80000.0 / 0.055) + (40000.0 / 0.070)
        expected_net_proceeds = gross_value * 0.970  # After 3.0% costs

        net_proceeds = reversion.calculate_net_proceeds(
            stabilized_noi=120000.0, noi_by_use=noi_by_use
        )

        assert abs(net_proceeds - expected_net_proceeds) < 1000.0


class TestReversionMetrics:
    """Test reversion metrics calculation."""

    def test_calculate_metrics_basic(self):
        """Test basic reversion metrics calculation."""
        reversion = ReversionValuation(
            name="Test", cap_rate=0.065, transaction_costs_rate=0.025
        )

        stabilized_noi = 100000.0  # $100k annual NOI
        total_cost_basis = 1200000.0  # $1.2M total cost

        metrics = reversion.calculate_metrics(stabilized_noi, total_cost_basis)

        # Verify all expected metrics are present
        expected_keys = [
            "gross_reversion_value",
            "net_reversion_proceeds",
            "transaction_costs",
            "total_profit",
            "profit_margin",
            "reversion_cap_rate",
            "stabilized_yield_on_cost",
        ]

        for key in expected_keys:
            assert key in metrics
            assert isinstance(metrics[key], (int, float))

        # Verify specific calculations
        gross_value = stabilized_noi / 0.065  # ≈ $1,538,462
        net_proceeds = gross_value * 0.975  # After 2.5% costs

        assert abs(metrics["gross_reversion_value"] - gross_value) < 1000.0
        assert abs(metrics["net_reversion_proceeds"] - net_proceeds) < 1000.0
        assert abs(metrics["transaction_costs"] - (gross_value - net_proceeds)) < 1000.0
        assert abs(metrics["total_profit"] - (net_proceeds - total_cost_basis)) < 1000.0
        assert (
            abs(
                metrics["profit_margin"]
                - ((net_proceeds - total_cost_basis) / total_cost_basis)
            )
            < 0.01
        )
        assert metrics["reversion_cap_rate"] == 0.065
        assert (
            abs(
                metrics["stabilized_yield_on_cost"]
                - (stabilized_noi / total_cost_basis)
            )
            < 0.001
        )

    def test_calculate_metrics_with_mixed_use(self):
        """Test metrics calculation with mixed-use property."""
        reversion = ReversionValuation(
            name="Mixed-Use",
            cap_rate=0.065,
            transaction_costs_rate=0.030,
            cap_rates_by_use={"office": 0.055, "retail": 0.070},
        )

        noi_by_use = {"office": 70000.0, "retail": 30000.0}
        total_cost_basis = 1800000.0

        metrics = reversion.calculate_metrics(
            stabilized_noi=100000.0,
            total_cost_basis=total_cost_basis,
            noi_by_use=noi_by_use,
        )

        # Should use mixed-use calculation
        expected_gross_value = (70000.0 / 0.055) + (30000.0 / 0.070)
        expected_net_proceeds = expected_gross_value * 0.970

        assert abs(metrics["gross_reversion_value"] - expected_gross_value) < 1000.0
        assert abs(metrics["net_reversion_proceeds"] - expected_net_proceeds) < 1000.0

    def test_calculate_metrics_zero_cost_basis(self):
        """Test metrics calculation with zero cost basis."""
        reversion = ReversionValuation(name="Test", cap_rate=0.065)

        metrics = reversion.calculate_metrics(
            stabilized_noi=100000.0, total_cost_basis=0.0
        )

        # Should handle division by zero gracefully
        assert metrics["profit_margin"] == 0.0
        assert metrics["stabilized_yield_on_cost"] == 0.0
        assert (
            metrics["total_profit"] > 0
        )  # Should still have profit (net proceeds - 0)


class TestCashFlowComputation:
    """Test cash flow computation (compute_cf method)."""

    def test_compute_cf_with_unlevered_analysis(
        self, mock_analysis_context, sample_unlevered_analysis
    ):
        """Test compute_cf with unlevered analysis data."""
        reversion = ReversionValuation(
            name="Test Sale", cap_rate=0.065, transaction_costs_rate=0.025
        )

        # Set up context with unlevered analysis
        mock_analysis_context.unlevered_analysis = sample_unlevered_analysis

        # Execute cash flow computation
        cf_series = reversion.compute_cf(mock_analysis_context)

        assert isinstance(cf_series, pd.Series)
        assert len(cf_series) == 24  # 2 years of monthly periods

        # Should have disposition proceeds in the last period
        assert cf_series.iloc[-1] > 0  # Last period should have proceeds
        assert cf_series.iloc[:-1].sum() == 0.0  # All other periods should be zero

        # Verify the calculation: last NOI ($80k monthly) * 12 / cap_rate * net_rate
        expected_annual_noi = 80000.0 * 12  # $960k annual
        expected_gross_value = expected_annual_noi / 0.065
        expected_net_proceeds = expected_gross_value * 0.975  # After 2.5% costs

        assert abs(cf_series.iloc[-1] - expected_net_proceeds) < 10000.0

    def test_compute_cf_with_resolved_lookups_fallback(
        self, mock_analysis_context, sample_timeline
    ):
        """Test compute_cf fallback to resolved lookups when unlevered analysis unavailable."""
        reversion = ReversionValuation(name="Test", cap_rate=0.065)

        # Set up context without unlevered_analysis, but with resolved lookups
        mock_analysis_context.unlevered_analysis = None

        # Create NOI series in resolved lookups
        noi_series = pd.Series([75000.0] * 24, index=sample_timeline.period_index)
        mock_analysis_context.resolved_lookups = {
            UnleveredAggregateLineKey.NET_OPERATING_INCOME.value: noi_series
        }

        cf_series = reversion.compute_cf(mock_analysis_context)

        assert isinstance(cf_series, pd.Series)
        assert cf_series.iloc[-1] > 0  # Should have disposition proceeds

        # Verify calculation using fallback data
        expected_annual_noi = 75000.0 * 12  # Last period NOI annualized
        expected_net_proceeds = (expected_annual_noi / 0.065) * 0.975

        assert abs(cf_series.iloc[-1] - expected_net_proceeds) < 10000.0

    def test_compute_cf_with_empty_noi_data(self, mock_analysis_context):
        """Test compute_cf when NOI data is empty."""
        reversion = ReversionValuation(name="Test", cap_rate=0.065)

        # Set up context with empty NOI data
        empty_analysis = UnleveredAnalysisResult()
        empty_analysis.cash_flows = pd.DataFrame()
        mock_analysis_context.unlevered_analysis = empty_analysis

        cf_series = reversion.compute_cf(mock_analysis_context)

        assert isinstance(cf_series, pd.Series)
        assert (cf_series == 0.0).all()  # Should be all zeros

    def test_compute_cf_with_zero_noi(self, mock_analysis_context, sample_timeline):
        """Test compute_cf when NOI is zero."""
        reversion = ReversionValuation(name="Test", cap_rate=0.065)

        # Create analysis with zero NOI
        zero_noi_series = pd.Series([0.0] * 24, index=sample_timeline.period_index)
        zero_cash_flows = pd.DataFrame(
            {UnleveredAggregateLineKey.NET_OPERATING_INCOME.value: zero_noi_series},
            index=sample_timeline.period_index,
        )

        zero_analysis = UnleveredAnalysisResult()
        zero_analysis.cash_flows = zero_cash_flows
        mock_analysis_context.unlevered_analysis = zero_analysis

        cf_series = reversion.compute_cf(mock_analysis_context)

        assert isinstance(cf_series, pd.Series)
        assert (cf_series == 0.0).all()  # Should be all zeros since NOI is zero

    def test_compute_cf_error_handling(self, mock_analysis_context):
        """Test compute_cf error handling when analysis fails."""
        reversion = ReversionValuation(name="Test", cap_rate=0.065)

        # Create context that will cause an error
        mock_analysis_context.unlevered_analysis = None
        mock_analysis_context.resolved_lookups = (
            None  # This should cause an AttributeError
        )

        # Should handle the error gracefully and return zeros
        cf_series = reversion.compute_cf(mock_analysis_context)

        assert isinstance(cf_series, pd.Series)
        assert (cf_series == 0.0).all()  # Should fall back to zeros

    def test_compute_cf_with_empty_noi_series_in_unlevered_analysis(
        self, mock_analysis_context, sample_timeline
    ):
        """Test compute_cf when unlevered analysis has empty NOI series (covers line 228)."""
        reversion = ReversionValuation(name="Test", cap_rate=0.065)

        # Create a mock unlevered analysis that returns an empty NOI series
        mock_unlevered_analysis = Mock()
        mock_unlevered_analysis.get_series.return_value = pd.Series(
            dtype=float
        )  # Empty series

        mock_analysis_context.unlevered_analysis = mock_unlevered_analysis

        cf_series = reversion.compute_cf(mock_analysis_context)

        assert isinstance(cf_series, pd.Series)
        assert (cf_series == 0.0).all()  # Should be all zeros due to empty NOI series

        # Verify get_series was called correctly
        mock_unlevered_analysis.get_series.assert_called_once_with(
            UnleveredAggregateLineKey.NET_OPERATING_INCOME,
            mock_analysis_context.timeline,
        )

    def test_compute_cf_with_empty_resolved_lookups_fallback(
        self, mock_analysis_context, sample_timeline
    ):
        """Test compute_cf fallback when resolved lookups has empty NOI series (covers line 236)."""
        reversion = ReversionValuation(name="Test", cap_rate=0.065)

        # Set up context without unlevered_analysis to trigger fallback
        mock_analysis_context.unlevered_analysis = None

        # Create empty NOI series in resolved lookups to trigger line 236
        empty_noi_series = pd.Series(dtype=float)  # Empty series
        mock_analysis_context.resolved_lookups = {
            UnleveredAggregateLineKey.NET_OPERATING_INCOME.value: empty_noi_series
        }

        cf_series = reversion.compute_cf(mock_analysis_context)

        assert isinstance(cf_series, pd.Series)
        assert (
            cf_series == 0.0
        ).all()  # Should be all zeros due to empty fallback NOI series

    def test_compute_cf_with_invalid_resolved_lookups_fallback(
        self, mock_analysis_context, sample_timeline
    ):
        """Test compute_cf fallback when resolved lookups contains invalid NOI data (covers line 236)."""
        reversion = ReversionValuation(name="Test", cap_rate=0.065)

        # Set up context without unlevered_analysis to trigger fallback
        mock_analysis_context.unlevered_analysis = None

        # Create resolved lookups with invalid NOI data (not a Series) to trigger line 236
        mock_analysis_context.resolved_lookups = {
            UnleveredAggregateLineKey.NET_OPERATING_INCOME.value: "invalid_data"  # Not a Series
        }

        cf_series = reversion.compute_cf(mock_analysis_context)

        assert isinstance(cf_series, pd.Series)
        assert (
            cf_series == 0.0
        ).all()  # Should be all zeros due to invalid fallback data


class TestFactoryMethods:
    """Test factory methods for creating ReversionValuation instances."""

    def test_conservative_factory_method(self):
        """Test conservative factory method."""
        conservative = ReversionValuation.conservative()

        assert conservative.name == "Conservative Sale"
        assert conservative.cap_rate == 0.065  # 6.5% conservative cap rate
        assert conservative.transaction_costs_rate == 0.025  # 2.5% transaction costs
        assert conservative.kind == "reversion"

    def test_conservative_factory_method_with_overrides(self):
        """Test conservative factory method with parameter overrides."""
        conservative = ReversionValuation.conservative(
            name="Custom Conservative", cap_rate=0.070, hold_period_months=30
        )

        assert conservative.name == "Custom Conservative"
        assert conservative.cap_rate == 0.070  # Overridden cap rate
        assert conservative.transaction_costs_rate == 0.025  # Default transaction costs
        assert conservative.hold_period_months == 30  # Custom hold period

    def test_aggressive_factory_method(self):
        """Test aggressive factory method."""
        aggressive = ReversionValuation.aggressive()

        assert aggressive.name == "Aggressive Sale"
        assert aggressive.cap_rate == 0.055  # 5.5% aggressive cap rate
        assert aggressive.transaction_costs_rate == 0.020  # 2.0% transaction costs
        assert aggressive.kind == "reversion"

    def test_aggressive_factory_method_with_overrides(self):
        """Test aggressive factory method with parameter overrides."""
        aggressive = ReversionValuation.aggressive(
            name="Ultra Aggressive",
            cap_rate=0.050,
            hold_period_months=24,  # Use a different override instead of transaction_costs_rate
        )

        assert aggressive.name == "Ultra Aggressive"
        assert aggressive.cap_rate == 0.050  # Overridden cap rate
        assert aggressive.transaction_costs_rate == 0.020  # Default from factory method
        assert aggressive.hold_period_months == 24  # Custom hold period


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling scenarios."""

    def test_very_high_noi_calculation(self):
        """Test calculations with very high NOI values."""
        reversion = ReversionValuation(name="High NOI Test", cap_rate=0.065)

        high_noi = 10000000.0  # $10M annual NOI
        gross_value = reversion.calculate_gross_value(high_noi)
        net_proceeds = reversion.calculate_net_proceeds(high_noi)

        expected_gross = high_noi / 0.065
        expected_net = expected_gross * 0.975

        assert (
            abs(gross_value - expected_gross) < 100000.0
        )  # Allow for larger tolerance
        assert abs(net_proceeds - expected_net) < 100000.0

    def test_very_low_cap_rate_calculation(self):
        """Test calculations with very low (but valid) cap rates."""
        reversion = ReversionValuation(
            name="Low Cap Rate Test",
            cap_rate=0.015,  # 1.5% cap rate (minimum valid)
            transaction_costs_rate=0.005,  # 0.5% costs (minimum valid)
        )

        noi = 100000.0
        gross_value = reversion.calculate_gross_value(noi)
        net_proceeds = reversion.calculate_net_proceeds(noi)

        expected_gross = noi / 0.015  # Should be very high value
        expected_net = expected_gross * 0.995

        assert abs(gross_value - expected_gross) < 10000.0
        assert abs(net_proceeds - expected_net) < 10000.0
        assert gross_value > 6000000.0  # Should be over $6M with 1.5% cap rate

    def test_empty_cap_rates_by_use_dict(self):
        """Test behavior with empty cap_rates_by_use dictionary."""
        reversion = ReversionValuation(
            name="Empty Dict Test",
            cap_rate=0.065,
            cap_rates_by_use={},  # Empty dict
        )

        noi_by_use = {"office": 50000.0}

        # Should fall back to simple calculation since cap_rates_by_use is empty
        gross_value = reversion.calculate_gross_value(
            stabilized_noi=50000.0, noi_by_use=noi_by_use
        )

        expected_value = 50000.0 / 0.065  # Simple calculation
        assert abs(gross_value - expected_value) < 1000.0

    def test_mixed_use_with_empty_noi_by_use(self):
        """Test mixed-use calculation when noi_by_use is empty."""
        reversion = ReversionValuation(
            name="Empty NOI Test", cap_rate=0.065, cap_rates_by_use={"office": 0.055}
        )

        # Should fall back to simple calculation when noi_by_use is empty
        gross_value = reversion.calculate_gross_value(
            stabilized_noi=100000.0,
            noi_by_use={},  # Empty
        )

        expected_value = 100000.0 / 0.065  # Simple calculation
        assert abs(gross_value - expected_value) < 1000.0


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""

    def test_development_project_reversion_scenario(self, sample_timeline):
        """Test reversion for a development project scenario."""
        # Development project with growing NOI
        reversion = ReversionValuation(
            name="Development Exit",
            cap_rate=0.060,  # Lower cap rate for new development
            transaction_costs_rate=0.020,  # Lower costs for institutional sale
            hold_period_months=36,
        )

        # Create development NOI profile (lease-up scenario)
        lease_up_noi = [0.0] * 18 + [40000.0] * 3 + [60000.0] * 3  # Gradual lease-up
        noi_series = pd.Series(lease_up_noi, index=sample_timeline.period_index)

        development_cash_flows = pd.DataFrame(
            {UnleveredAggregateLineKey.NET_OPERATING_INCOME.value: lease_up_noi},
            index=sample_timeline.period_index,
        )

        development_analysis = UnleveredAnalysisResult()
        development_analysis.cash_flows = development_cash_flows

        # Create context
        context = Mock()
        context.timeline = sample_timeline
        context.unlevered_analysis = development_analysis

        cf_series = reversion.compute_cf(context)

        # Should have disposition proceeds based on stabilized NOI
        assert cf_series.iloc[-1] > 0

        # Calculate expected proceeds: $60k monthly * 12 / 6% cap rate * 98% net
        expected_annual_noi = 60000.0 * 12
        expected_gross_value = expected_annual_noi / 0.060
        expected_net_proceeds = expected_gross_value * 0.980

        assert abs(cf_series.iloc[-1] - expected_net_proceeds) < 50000.0

    def test_mixed_use_reversion_workflow(self):
        """Test complete mixed-use reversion workflow."""
        reversion = ReversionValuation(
            name="Mixed-Use Complex Sale",
            cap_rate=0.065,  # Blended rate
            transaction_costs_rate=0.025,
            cap_rates_by_use={
                "office": 0.055,  # Premium office space
                "retail": 0.075,  # Higher cap rate for retail
                "residential": 0.050,  # Lower cap rate for residential
            },
        )

        # Mixed-use NOI breakdown
        noi_by_use = {
            "office": 120000.0,  # $120k annual office NOI
            "retail": 60000.0,  # $60k annual retail NOI
            "residential": 180000.0,  # $180k annual residential NOI
        }

        total_cost_basis = 5000000.0  # $5M total development cost

        # Test all calculation methods
        gross_value = reversion.calculate_gross_value(
            stabilized_noi=360000.0,  # Total NOI
            noi_by_use=noi_by_use,
        )

        net_proceeds = reversion.calculate_net_proceeds(
            stabilized_noi=360000.0, noi_by_use=noi_by_use
        )

        metrics = reversion.calculate_metrics(
            stabilized_noi=360000.0,
            total_cost_basis=total_cost_basis,
            noi_by_use=noi_by_use,
        )

        # Verify calculations
        expected_gross = (120000.0 / 0.055) + (60000.0 / 0.075) + (180000.0 / 0.050)
        expected_net = expected_gross * 0.975

        assert abs(gross_value - expected_gross) < 10000.0
        assert abs(net_proceeds - expected_net) < 10000.0
        assert abs(metrics["gross_reversion_value"] - expected_gross) < 10000.0
        assert abs(metrics["net_reversion_proceeds"] - expected_net) < 10000.0

        # Verify profitability metrics
        assert metrics["total_profit"] == expected_net - total_cost_basis
        assert (
            abs(
                metrics["profit_margin"]
                - ((expected_net - total_cost_basis) / total_cost_basis)
            )
            < 0.01
        )
