# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Tests for DCF Valuation module.
"""

import pandas as pd
import pytest
from pydantic import ValidationError

from performa.valuation import DCFValuation


class TestDCFValuation:
    """Tests for DCF valuation functionality."""

    def test_dcf_creation_basic(self):
        """Test basic DCF creation."""
        dcf = DCFValuation(
            name="Test DCF",
            discount_rate=0.08,
            terminal_cap_rate=0.065,
            hold_period_years=10,
        )

        assert dcf.name == "Test DCF"
        assert dcf.discount_rate == 0.08
        assert dcf.terminal_cap_rate == 0.065
        assert dcf.hold_period_years == 10
        assert dcf.terminal_growth_rate is None
        assert dcf.reversion_costs_rate == 0.025  # default

    def test_dcf_validation_discount_rate(self):
        """Test discount rate validation."""
        # Valid discount rate
        dcf = DCFValuation(
            name="Test",
            discount_rate=0.08,
            terminal_cap_rate=0.065,
            hold_period_years=10,
        )
        assert dcf.discount_rate == 0.08

        # Invalid discount rate - too low
        with pytest.raises(
            ValidationError, match="Discount rate.*should be between 2% and 25%"
        ):
            DCFValuation(
                name="Test",
                discount_rate=0.01,
                terminal_cap_rate=0.065,
                hold_period_years=10,
            )

        # Invalid discount rate - too high
        with pytest.raises(
            ValidationError, match="Discount rate.*should be between 2% and 25%"
        ):
            DCFValuation(
                name="Test",
                discount_rate=0.30,
                terminal_cap_rate=0.065,
                hold_period_years=10,
            )

    def test_dcf_validation_cap_rate(self):
        """Test terminal cap rate validation."""
        # Valid cap rate
        dcf = DCFValuation(
            name="Test",
            discount_rate=0.08,
            terminal_cap_rate=0.065,
            hold_period_years=10,
        )
        assert dcf.terminal_cap_rate == 0.065

        # Invalid cap rate - too low
        with pytest.raises(
            ValidationError, match="Terminal cap rate.*should be between 1% and 20%"
        ):
            DCFValuation(
                name="Test",
                discount_rate=0.08,
                terminal_cap_rate=0.005,
                hold_period_years=10,
            )

    def test_dcf_validation_growth_rate(self):
        """Test terminal growth rate validation."""
        # Valid growth rate
        dcf = DCFValuation(
            name="Test",
            discount_rate=0.08,
            terminal_cap_rate=0.065,
            hold_period_years=10,
            terminal_growth_rate=0.02,
        )
        assert dcf.terminal_growth_rate == 0.02

        # Growth rate >= discount rate should fail
        with pytest.raises(
            ValidationError,
            match="Terminal growth rate.*must be less than.*discount rate",
        ):
            DCFValuation(
                name="Test",
                discount_rate=0.08,
                terminal_cap_rate=0.065,
                hold_period_years=10,
                terminal_growth_rate=0.09,
            )

        # Growth rate too high (>10%) should fail
        with pytest.raises(
            ValidationError, match="Terminal growth rate.*should be between 0% and 10%"
        ):
            DCFValuation(
                name="Test",
                discount_rate=0.15,
                terminal_cap_rate=0.065,
                hold_period_years=10,
                terminal_growth_rate=0.12,
            )

        # Negative growth rate should fail (at Pydantic field level)
        with pytest.raises(
            ValidationError, match="Input should be greater than or equal to 0"
        ):
            DCFValuation(
                name="Test",
                discount_rate=0.08,
                terminal_cap_rate=0.065,
                hold_period_years=10,
                terminal_growth_rate=-0.01,
            )

    def test_dcf_validation_hold_period(self):
        """Test hold period validation."""
        # Valid hold period
        dcf = DCFValuation(
            name="Test",
            discount_rate=0.08,
            terminal_cap_rate=0.065,
            hold_period_years=5,
        )
        assert dcf.hold_period_years == 5

        # Invalid hold period - too short
        with pytest.raises(
            ValidationError, match="Hold period.*should be between 1 and 50 years"
        ):
            DCFValuation(
                name="Test",
                discount_rate=0.08,
                terminal_cap_rate=0.065,
                hold_period_years=0,
            )

    def test_dcf_validation_reversion_costs(self):
        """Test reversion costs rate validation."""
        # Valid reversion costs rate
        dcf = DCFValuation(
            name="Test",
            discount_rate=0.08,
            terminal_cap_rate=0.065,
            hold_period_years=10,
            reversion_costs_rate=0.025,
        )
        assert dcf.reversion_costs_rate == 0.025

        # Reversion costs too low (<0.5%) should fail
        with pytest.raises(
            ValidationError,
            match="Reversion costs rate.*should be between 0.5% and 10%",
        ):
            DCFValuation(
                name="Test",
                discount_rate=0.08,
                terminal_cap_rate=0.065,
                hold_period_years=10,
                reversion_costs_rate=0.003,
            )

        # Reversion costs too high (>10%) should fail
        with pytest.raises(
            ValidationError,
            match="Reversion costs rate.*should be between 0.5% and 10%",
        ):
            DCFValuation(
                name="Test",
                discount_rate=0.08,
                terminal_cap_rate=0.065,
                hold_period_years=10,
                reversion_costs_rate=0.12,
            )

    def test_computed_properties(self):
        """Test computed properties."""
        dcf = DCFValuation(
            name="Test",
            discount_rate=0.08,
            terminal_cap_rate=0.065,
            hold_period_years=5,
            reversion_costs_rate=0.025,
        )

        assert dcf.net_terminal_proceeds_rate == 0.975  # 1.0 - 0.025
        assert abs(dcf.terminal_discount_factor - (1.0 / (1.08**5))) < 0.0001

    def test_calculate_present_value_basic(self):
        """Test basic present value calculation."""
        dcf = DCFValuation(
            name="Test",
            discount_rate=0.08,
            terminal_cap_rate=0.065,
            hold_period_years=5,
        )

        cash_flows = pd.Series([100000, 105000, 110000, 115000, 120000])
        terminal_noi = 125000

        result = dcf.calculate_present_value(cash_flows, terminal_noi)

        # Check result structure
        assert "present_value" in result
        assert "pv_operations" in result
        assert "pv_terminal" in result
        assert "gross_terminal_value" in result
        assert "net_terminal_value" in result
        assert "terminal_noi" in result
        assert "operations_percentage" in result
        assert "terminal_percentage" in result

        # Check calculations are reasonable
        assert result["present_value"] > 0
        assert result["pv_operations"] > 0
        assert result["pv_terminal"] > 0
        assert (
            result["present_value"] == result["pv_operations"] + result["pv_terminal"]
        )
        assert result["operations_percentage"] + result["terminal_percentage"] == 100.0

        # Terminal value should be NOI / cap rate
        expected_gross_terminal = terminal_noi / dcf.terminal_cap_rate
        assert abs(result["gross_terminal_value"] - expected_gross_terminal) < 1.0

    def test_calculate_present_value_with_growth(self):
        """Test present value calculation with terminal growth."""
        dcf = DCFValuation(
            name="Test",
            discount_rate=0.08,
            terminal_cap_rate=0.065,
            hold_period_years=5,
            terminal_growth_rate=0.02,
        )

        cash_flows = pd.Series([100000, 105000, 110000, 115000, 120000])
        terminal_noi = 125000

        result = dcf.calculate_present_value(cash_flows, terminal_noi)

        # With growth, terminal NOI should be grown
        expected_grown_noi = terminal_noi * ((1.02) ** 5)
        assert abs(result["terminal_noi"] - expected_grown_noi) < 1.0

    def test_calculate_present_value_edge_cases(self):
        """Test edge cases for present value calculation."""
        dcf = DCFValuation(
            name="Test",
            discount_rate=0.08,
            terminal_cap_rate=0.065,
            hold_period_years=5,
        )

        # Empty cash flows should raise error
        with pytest.raises(ValueError, match="Cash flows cannot be empty"):
            dcf.calculate_present_value(pd.Series([]), 125000)

        # Too many cash flows should truncate
        long_cash_flows = pd.Series([100000] * 10)  # 10 years but hold period is 5
        result = dcf.calculate_present_value(long_cash_flows, 125000)
        assert result["present_value"] > 0  # Should still work

    def test_calculate_metrics(self):
        """Test comprehensive metrics calculation."""
        dcf = DCFValuation(
            name="Test",
            discount_rate=0.08,
            terminal_cap_rate=0.065,
            hold_period_years=5,
        )

        cash_flows = pd.Series([100000, 105000, 110000, 115000, 120000])
        terminal_noi = 125000
        initial_investment = 1500000

        metrics = dcf.calculate_metrics(cash_flows, terminal_noi, initial_investment)

        # Check all expected metrics are present
        expected_keys = [
            "present_value",
            "pv_operations",
            "pv_terminal",
            "gross_terminal_value",
            "net_terminal_value",
            "terminal_noi",
            "operations_percentage",
            "terminal_percentage",
            "npv",
            "value_per_dollar_invested",
            "initial_investment",
            "profit",
            "profit_margin",
        ]

        for key in expected_keys:
            assert key in metrics

        # Check relationships
        assert metrics["npv"] == metrics["present_value"] - initial_investment
        assert metrics["profit"] == metrics["npv"]
        assert (
            metrics["value_per_dollar_invested"]
            == metrics["present_value"] / initial_investment
        )
        assert metrics["initial_investment"] == initial_investment

    def test_sensitivity_analysis(self):
        """Test sensitivity analysis."""
        dcf = DCFValuation(
            name="Test",
            discount_rate=0.08,
            terminal_cap_rate=0.065,
            hold_period_years=5,
        )

        cash_flows = pd.Series([100000, 105000, 110000, 115000, 120000])
        terminal_noi = 125000

        sensitivity = dcf.calculate_sensitivity_analysis(
            cash_flows,
            terminal_noi,
            discount_rate_range=(-0.01, 0.01),
            cap_rate_range=(-0.005, 0.005),
            steps=3,
        )

        # Should return a DataFrame
        assert isinstance(sensitivity, pd.DataFrame)
        assert len(sensitivity) == 9  # 3x3 grid

        # Check columns
        expected_cols = [
            "discount_rate",
            "terminal_cap_rate",
            "present_value",
            "discount_rate_delta",
            "cap_rate_delta",
        ]
        for col in expected_cols:
            assert col in sensitivity.columns

        # Check that values vary
        assert (
            sensitivity["present_value"].nunique() > 1
        )  # Should have different values

    def test_factory_methods(self):
        """Test factory methods."""
        # Conservative factory
        conservative = DCFValuation.conservative()
        assert conservative.name == "Conservative DCF"
        assert conservative.discount_rate == 0.09
        assert conservative.terminal_cap_rate == 0.07
        assert conservative.hold_period_years == 10
        assert conservative.reversion_costs_rate == 0.025
        assert conservative.terminal_growth_rate is None

        # Aggressive factory
        aggressive = DCFValuation.aggressive()
        assert aggressive.name == "Aggressive DCF"
        assert aggressive.discount_rate == 0.075
        assert aggressive.terminal_cap_rate == 0.055
        assert aggressive.hold_period_years == 7
        assert aggressive.terminal_growth_rate == 0.02
        assert aggressive.reversion_costs_rate == 0.020

        # Custom parameters
        custom_conservative = DCFValuation.conservative(
            name="Custom", discount_rate=0.10, hold_period_years=15
        )
        assert custom_conservative.name == "Custom"
        assert custom_conservative.discount_rate == 0.10
        assert custom_conservative.hold_period_years == 15

    def test_model_immutability(self):
        """Test that DCF models are immutable."""
        dcf = DCFValuation(
            name="Test",
            discount_rate=0.08,
            terminal_cap_rate=0.065,
            hold_period_years=5,
        )

        # Should not be able to modify attributes directly (frozen model)
        with pytest.raises((AttributeError, TypeError, ValidationError)):
            dcf.discount_rate = 0.10

        # But should be able to create copies with modifications
        modified_dcf = dcf.model_copy(update={"discount_rate": 0.10})
        assert modified_dcf.discount_rate == 0.10
        assert dcf.discount_rate == 0.08  # Original unchanged


class TestDCFContextIntegration:
    """Tests for DCF integration with AnalysisContext."""

    def test_compute_cf_with_unlevered_analysis(self):
        """Test compute_cf with unlevered analysis data."""
        from datetime import datetime
        from unittest.mock import Mock

        from performa.core.primitives import Timeline, UnleveredAggregateLineKey

        dcf = DCFValuation(
            name="Test",
            discount_rate=0.08,
            terminal_cap_rate=0.065,
            hold_period_years=5,
        )

        # Create mock context with unlevered analysis
        mock_context = Mock()

        # Create a timeline for the mock
        timeline = Timeline(start_date=datetime(2024, 1, 1), duration_months=60)
        mock_context.timeline = timeline

        # Create mock unlevered analysis with NOI series
        mock_unlevered_analysis = Mock()

        # Create realistic monthly NOI series
        monthly_noi = [10000] * 60  # $10k per month for 5 years
        noi_series = pd.Series(monthly_noi, index=timeline.period_index)

        mock_unlevered_analysis.get_series.return_value = noi_series
        mock_context.unlevered_analysis = mock_unlevered_analysis

        # Run compute_cf
        result = dcf.compute_cf(mock_context)

        # Verify results
        assert isinstance(result, pd.Series)
        assert len(result) == len(timeline.period_index)
        assert result.sum() > 0  # Should have disposition proceeds

        # Verify that disposition proceeds are placed at the end of hold period
        non_zero_periods = result[result > 0]
        assert len(non_zero_periods) == 1  # Should have exactly one disposition period

        # Verify mock was called correctly
        mock_unlevered_analysis.get_series.assert_called_once_with(
            UnleveredAggregateLineKey.NET_OPERATING_INCOME, timeline
        )

    def test_compute_cf_with_resolved_lookups_fallback(self):
        """Test compute_cf fallback to resolved lookups when no unlevered analysis."""
        from datetime import datetime
        from unittest.mock import Mock

        from performa.core.primitives import Timeline, UnleveredAggregateLineKey

        dcf = DCFValuation(
            name="Test",
            discount_rate=0.08,
            terminal_cap_rate=0.065,
            hold_period_years=3,
        )

        # Create mock context without unlevered analysis
        mock_context = Mock()
        timeline = Timeline(start_date=datetime(2024, 1, 1), duration_months=36)
        mock_context.timeline = timeline
        mock_context.unlevered_analysis = None

        # Create resolved lookups with NOI data
        monthly_noi = [8000] * 36  # $8k per month for 3 years
        noi_lookup = pd.Series(monthly_noi, index=timeline.period_index)

        mock_context.resolved_lookups = {
            UnleveredAggregateLineKey.NET_OPERATING_INCOME.value: noi_lookup
        }

        # Run compute_cf
        result = dcf.compute_cf(mock_context)

        # Verify results
        assert isinstance(result, pd.Series)
        assert len(result) == len(timeline.period_index)
        assert result.sum() > 0  # Should have disposition proceeds

        # Should have disposition at end of 3-year hold period
        non_zero_periods = result[result > 0]
        assert len(non_zero_periods) == 1

    def test_compute_cf_with_empty_noi_series(self):
        """Test compute_cf with empty NOI series."""
        from datetime import datetime
        from unittest.mock import Mock

        from performa.core.primitives import Timeline

        dcf = DCFValuation(
            name="Test",
            discount_rate=0.08,
            terminal_cap_rate=0.065,
            hold_period_years=5,
        )

        # Create mock context with empty NOI series
        mock_context = Mock()
        timeline = Timeline(start_date=datetime(2024, 1, 1), duration_months=60)
        mock_context.timeline = timeline

        mock_unlevered_analysis = Mock()
        mock_unlevered_analysis.get_series.return_value = pd.Series(
            [], dtype=float
        )  # Empty series
        mock_context.unlevered_analysis = mock_unlevered_analysis

        # Run compute_cf
        result = dcf.compute_cf(mock_context)

        # Should return all zeros when no NOI data
        assert isinstance(result, pd.Series)
        assert len(result) == len(timeline.period_index)
        assert result.sum() == 0.0  # No disposition proceeds

    def test_compute_cf_with_no_analysis_data(self):
        """Test compute_cf with no analysis data available."""
        from datetime import datetime
        from unittest.mock import Mock

        from performa.core.primitives import Timeline, UnleveredAggregateLineKey

        dcf = DCFValuation(
            name="Test",
            discount_rate=0.08,
            terminal_cap_rate=0.065,
            hold_period_years=5,
        )

        # Create mock context with no unlevered analysis and no resolved lookups
        mock_context = Mock()
        timeline = Timeline(start_date=datetime(2024, 1, 1), duration_months=60)
        mock_context.timeline = timeline
        mock_context.unlevered_analysis = None
        mock_context.resolved_lookups = {
            UnleveredAggregateLineKey.NET_OPERATING_INCOME.value: None
        }

        # Run compute_cf
        result = dcf.compute_cf(mock_context)

        # Should return all zeros when no data available
        assert isinstance(result, pd.Series)
        assert len(result) == len(timeline.period_index)
        assert result.sum() == 0.0

    def test_compute_cf_with_exception_handling(self):
        """Test compute_cf handles exceptions gracefully."""
        from datetime import datetime
        from unittest.mock import Mock

        from performa.core.primitives import Timeline

        dcf = DCFValuation(
            name="Test",
            discount_rate=0.08,
            terminal_cap_rate=0.065,
            hold_period_years=5,
        )

        # Create mock context that raises exception
        mock_context = Mock()
        timeline = Timeline(start_date=datetime(2024, 1, 1), duration_months=60)
        mock_context.timeline = timeline

        # Mock unlevered analysis that raises exception
        mock_unlevered_analysis = Mock()
        mock_unlevered_analysis.get_series.side_effect = Exception("Test exception")
        mock_context.unlevered_analysis = mock_unlevered_analysis

        # Run compute_cf - should not raise exception
        result = dcf.compute_cf(mock_context)

        # Should return all zeros when exception occurs
        assert isinstance(result, pd.Series)
        assert len(result) == len(timeline.period_index)
        assert result.sum() == 0.0

    def test_compute_cf_with_short_hold_period(self):
        """Test compute_cf with hold period shorter than timeline."""
        from datetime import datetime
        from unittest.mock import Mock

        from performa.core.primitives import Timeline

        dcf = DCFValuation(
            name="Test",
            discount_rate=0.08,
            terminal_cap_rate=0.065,
            hold_period_years=2,  # Short period
        )

        # Create mock context with longer timeline
        mock_context = Mock()
        timeline = Timeline(
            start_date=datetime(2024, 1, 1), duration_months=60
        )  # 5 years
        mock_context.timeline = timeline

        # Create mock unlevered analysis
        mock_unlevered_analysis = Mock()
        monthly_noi = [15000] * 60  # $15k per month for 5 years
        noi_series = pd.Series(monthly_noi, index=timeline.period_index)
        mock_unlevered_analysis.get_series.return_value = noi_series
        mock_context.unlevered_analysis = mock_unlevered_analysis

        # Run compute_cf
        result = dcf.compute_cf(mock_context)

        # Verify results
        assert isinstance(result, pd.Series)
        assert result.sum() > 0

        # Disposition should occur at end of 2-year hold period (month 24), not at end of timeline
        non_zero_periods = result[result > 0]
        assert len(non_zero_periods) == 1
        disposition_period = non_zero_periods.index[0]
        # Should be at or before month 24 (2 years * 12 months)
        position = timeline.period_index.get_loc(disposition_period)
        assert position < 24  # Should be within the hold period

    def test_compute_cf_edge_case_zero_hold_period_end(self):
        """Test compute_cf when hold_period_end calculation results in zero."""
        from datetime import datetime
        from unittest.mock import Mock

        from performa.core.primitives import Timeline

        dcf = DCFValuation(
            name="Test",
            discount_rate=0.08,
            terminal_cap_rate=0.065,
            hold_period_years=1,
        )

        # Create mock context with very short timeline (shorter than hold period)
        mock_context = Mock()
        timeline = Timeline(
            start_date=datetime(2024, 1, 1), duration_months=6
        )  # Only 6 months
        mock_context.timeline = timeline

        # Create mock unlevered analysis
        mock_unlevered_analysis = Mock()
        monthly_noi = [5000] * 6
        noi_series = pd.Series(monthly_noi, index=timeline.period_index)
        mock_unlevered_analysis.get_series.return_value = noi_series
        mock_context.unlevered_analysis = mock_unlevered_analysis

        # Run compute_cf
        result = dcf.compute_cf(mock_context)

        # Should still work and place disposition at end of available timeline
        assert isinstance(result, pd.Series)
        assert len(result) == len(timeline.period_index)
