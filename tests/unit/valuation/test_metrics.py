# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Valuation Metrics Unit Tests

Unit tests for the PropertyMetrics class that handles financial performance
calculations for real estate investments.

Test Coverage:
1. Net Operating Income (NOI) calculations with various input types
2. Stabilized NOI calculations from cash flow analysis
3. Internal Rate of Return (IRR) calculations using PyXIRR
4. Yield on cost calculations for development projects
5. Cash-on-cash return calculations
6. Comprehensive metrics calculations with full scenarios
7. Edge cases and error handling
8. Validation of monthly period index requirements
"""

import pandas as pd
import pytest

from performa.valuation.metrics import PropertyMetrics


@pytest.fixture
def sample_monthly_index() -> pd.PeriodIndex:
    """Standard monthly period index for testing."""
    return pd.period_range(start="2024-01", periods=12, freq="M")


@pytest.fixture
def sample_revenue_series(sample_monthly_index: pd.PeriodIndex) -> pd.Series:
    """Sample monthly revenue series."""
    return pd.Series([10000.0] * 12, index=sample_monthly_index)


@pytest.fixture
def sample_expense_series(sample_monthly_index: pd.PeriodIndex) -> pd.Series:
    """Sample monthly expense series."""
    return pd.Series([6000.0] * 12, index=sample_monthly_index)


@pytest.fixture
def sample_cash_flows_df(sample_monthly_index: pd.PeriodIndex) -> pd.DataFrame:
    """Sample cash flows DataFrame for comprehensive testing."""
    return pd.DataFrame(
        {
            "revenue": [10000.0] * 12,
            "expenses": [6000.0] * 12,
            "net_cash_flow": [4000.0] * 12,
        },
        index=sample_monthly_index,
    )


@pytest.fixture
def irr_cash_flows() -> pd.Series:
    """Sample IRR cash flows with initial investment and returns."""
    dates = pd.period_range(start="2024-01", periods=13, freq="M")
    flows = (
        [-100000.0] + [8000.0] * 11 + [108000.0]
    )  # Initial investment + monthly flows + exit
    return pd.Series(flows, index=dates)


class TestCalculateNOI:
    """Test Net Operating Income calculations."""

    def test_noi_with_series_inputs(
        self, sample_revenue_series: pd.Series, sample_expense_series: pd.Series
    ):
        """Test NOI calculation with pandas Series inputs."""
        noi = PropertyMetrics.calculate_noi(
            sample_revenue_series, sample_expense_series
        )

        assert isinstance(noi, pd.Series)
        assert len(noi) == 12
        assert (noi == 4000.0).all()  # 10000 - 6000 = 4000
        pd.testing.assert_index_equal(noi.index, sample_revenue_series.index)

    def test_noi_with_scalar_inputs(self):
        """Test NOI calculation with scalar inputs."""
        revenue = 120000.0  # Annual revenue
        expenses = 72000.0  # Annual expenses

        noi = PropertyMetrics.calculate_noi(revenue, expenses)

        assert isinstance(noi, float)
        assert noi == 48000.0  # 120000 - 72000

    def test_noi_with_zero_values(self, sample_monthly_index: pd.PeriodIndex):
        """Test NOI calculation with zero values."""
        zero_revenue = pd.Series([0.0] * 12, index=sample_monthly_index)
        zero_expenses = pd.Series([0.0] * 12, index=sample_monthly_index)

        noi = PropertyMetrics.calculate_noi(zero_revenue, zero_expenses)

        assert (noi == 0.0).all()

        # Test scalar zeros
        noi_scalar = PropertyMetrics.calculate_noi(0.0, 0.0)
        assert noi_scalar == 0.0

    def test_noi_negative_result(self, sample_monthly_index: pd.PeriodIndex):
        """Test NOI calculation with negative result (expenses > revenue)."""
        revenue = pd.Series([5000.0] * 12, index=sample_monthly_index)
        expenses = pd.Series([8000.0] * 12, index=sample_monthly_index)

        noi = PropertyMetrics.calculate_noi(revenue, expenses)

        assert (noi == -3000.0).all()  # 5000 - 8000 = -3000

    def test_noi_mismatched_types_error(self, sample_revenue_series: pd.Series):
        """Test error when mixing Series and scalar types."""
        with pytest.raises(ValueError, match="must be the same type"):
            PropertyMetrics.calculate_noi(sample_revenue_series, 6000.0)

        with pytest.raises(ValueError, match="must be the same type"):
            PropertyMetrics.calculate_noi(10000.0, sample_revenue_series)

    def test_noi_invalid_series_index(self):
        """Test error with non-monthly PeriodIndex."""
        daily_index = pd.period_range(start="2024-01-01", periods=30, freq="D")
        revenue = pd.Series([100.0] * 30, index=daily_index)
        expenses = pd.Series([60.0] * 30, index=daily_index)

        with pytest.raises(ValueError, match="monthly frequency"):
            PropertyMetrics.calculate_noi(revenue, expenses)


class TestCalculateStabilizedNOI:
    """Test stabilized NOI calculations from cash flow analysis."""

    def test_stabilized_noi_basic(self, sample_cash_flows_df: pd.DataFrame):
        """Test basic stabilized NOI calculation."""
        stabilized_noi = PropertyMetrics.calculate_stabilized_noi(sample_cash_flows_df)

        # Should use last period: (10000 - 6000) * 12 = 48000
        assert stabilized_noi == 48000.0

    def test_stabilized_noi_specific_period(self, sample_cash_flows_df: pd.DataFrame):
        """Test stabilized NOI with specific stabilization period."""
        stabilization_period = sample_cash_flows_df.index[6]  # Mid-year

        stabilized_noi = PropertyMetrics.calculate_stabilized_noi(
            sample_cash_flows_df, stabilization_period=stabilization_period
        )

        assert stabilized_noi == 48000.0  # Same calculation for uniform data

    def test_stabilized_noi_missing_columns(self, sample_monthly_index: pd.PeriodIndex):
        """Test stabilized NOI with missing revenue/expense columns."""
        # DataFrame with only revenue
        revenue_only_df = pd.DataFrame(
            {"revenue": [10000.0] * 12}, index=sample_monthly_index
        )

        stabilized_noi = PropertyMetrics.calculate_stabilized_noi(revenue_only_df)
        assert stabilized_noi == 120000.0  # 10000 * 12 (no expenses)

        # DataFrame with only expenses
        expenses_only_df = pd.DataFrame(
            {"expenses": [6000.0] * 12}, index=sample_monthly_index
        )

        stabilized_noi = PropertyMetrics.calculate_stabilized_noi(expenses_only_df)
        assert stabilized_noi == -72000.0  # -6000 * 12 (no revenue)

    def test_stabilized_noi_invalid_period(self, sample_cash_flows_df: pd.DataFrame):
        """Test error with invalid stabilization period."""
        invalid_period = pd.Period("2025-01", freq="M")  # Not in index

        with pytest.raises(ValueError, match="not found in cash flows"):
            PropertyMetrics.calculate_stabilized_noi(
                sample_cash_flows_df, stabilization_period=invalid_period
            )

    def test_stabilized_noi_invalid_index_type(self):
        """Test error with non-PeriodIndex."""
        df = pd.DataFrame(
            {"revenue": [10000.0] * 12, "expenses": [6000.0] * 12}, index=range(12)
        )  # Regular integer index

        with pytest.raises(ValueError, match="must have a PeriodIndex"):
            PropertyMetrics.calculate_stabilized_noi(df)

    def test_stabilized_noi_invalid_frequency(self):
        """Test error with non-monthly frequency."""
        quarterly_index = pd.period_range(start="2024Q1", periods=4, freq="Q")
        df = pd.DataFrame(
            {"revenue": [30000.0] * 4, "expenses": [18000.0] * 4}, index=quarterly_index
        )

        with pytest.raises(ValueError, match="monthly frequency"):
            PropertyMetrics.calculate_stabilized_noi(df)


class TestCalculateIRR:
    """Test Internal Rate of Return calculations."""

    def test_irr_basic_calculation(self, irr_cash_flows: pd.Series):
        """Test basic IRR calculation with standard cash flows."""
        irr = PropertyMetrics.calculate_irr(irr_cash_flows)

        # Should return a reasonable IRR - the actual value will be high due to monthly compounding
        assert isinstance(irr, float)
        assert (
            0.5 < irr < 3.0
        )  # Adjusted range for this cash flow pattern with monthly compounding

    def test_irr_with_explicit_dates(self):
        """Test IRR calculation with explicit dates."""
        dates = pd.to_datetime(["2024-01-01", "2024-07-01", "2025-01-01"])
        cash_flows = pd.Series([-100000, 10000, 110000])  # Investment, interim, exit

        irr = PropertyMetrics.calculate_irr(cash_flows, dates)

        assert isinstance(irr, float)
        assert 0.05 < irr < 0.25  # Reasonable range

    def test_irr_no_solution(self):
        """Test IRR when no solution exists (all positive flows)."""
        cash_flows = pd.Series([10000, 10000, 10000])  # All positive flows

        # PyXIRR should raise an exception or return NaN for no solution
        with pytest.raises(Exception):  # PyXIRR raises various exceptions
            PropertyMetrics.calculate_irr(cash_flows)

    def test_irr_single_cash_flow(self):
        """Test IRR with single cash flow (should fail)."""
        cash_flows = pd.Series([-100000])  # Only investment

        with pytest.raises(Exception):  # Insufficient data for IRR
            PropertyMetrics.calculate_irr(cash_flows)

    def test_irr_period_index_validation(self, irr_cash_flows: pd.Series):
        """Test that PeriodIndex validation works correctly."""
        # Test with valid monthly PeriodIndex - should work
        irr = PropertyMetrics.calculate_irr(irr_cash_flows)
        assert isinstance(irr, float)

        # Test with invalid PeriodIndex frequency
        daily_index = pd.period_range(start="2024-01-01", periods=13, freq="D")
        invalid_flows = pd.Series([-100000.0] + [8000.0] * 12, index=daily_index)

        with pytest.raises(ValueError, match="monthly frequency"):
            PropertyMetrics.calculate_irr(invalid_flows)


class TestCalculateYieldOnCost:
    """Test yield on cost calculations."""

    def test_yield_on_cost_basic(self):
        """Test basic yield on cost calculation."""
        stabilized_noi = 48000.0
        total_cost = 600000.0

        yield_on_cost = PropertyMetrics.calculate_yield_on_cost(
            stabilized_noi, total_cost
        )

        assert yield_on_cost == 0.08  # 48000 / 600000 = 8%

    def test_yield_on_cost_zero_cost(self):
        """Test yield on cost with zero total cost."""
        stabilized_noi = 48000.0
        total_cost = 0.0

        yield_on_cost = PropertyMetrics.calculate_yield_on_cost(
            stabilized_noi, total_cost
        )

        assert yield_on_cost == 0.0  # Should return 0 for zero cost

    def test_yield_on_cost_negative_cost(self):
        """Test yield on cost with negative total cost."""
        stabilized_noi = 48000.0
        total_cost = -100000.0

        yield_on_cost = PropertyMetrics.calculate_yield_on_cost(
            stabilized_noi, total_cost
        )

        assert yield_on_cost == 0.0  # Should return 0 for negative cost

    def test_yield_on_cost_zero_noi(self):
        """Test yield on cost with zero NOI."""
        stabilized_noi = 0.0
        total_cost = 600000.0

        yield_on_cost = PropertyMetrics.calculate_yield_on_cost(
            stabilized_noi, total_cost
        )

        assert yield_on_cost == 0.0  # 0 / 600000 = 0

    def test_yield_on_cost_negative_noi(self):
        """Test yield on cost with negative NOI."""
        stabilized_noi = -12000.0  # Operating at a loss
        total_cost = 600000.0

        yield_on_cost = PropertyMetrics.calculate_yield_on_cost(
            stabilized_noi, total_cost
        )

        assert yield_on_cost == -0.02  # -12000 / 600000 = -2%


class TestCalculateCashOnCashReturn:
    """Test cash-on-cash return calculations."""

    def test_cash_on_cash_basic(self):
        """Test basic cash-on-cash return calculation."""
        first_year_cf = 24000.0
        initial_equity = 200000.0

        cash_on_cash = PropertyMetrics.calculate_cash_on_cash_return(
            first_year_cf, initial_equity
        )

        assert cash_on_cash == 0.12  # 24000 / 200000 = 12%

    def test_cash_on_cash_zero_equity(self):
        """Test cash-on-cash return with zero equity."""
        first_year_cf = 24000.0
        initial_equity = 0.0

        cash_on_cash = PropertyMetrics.calculate_cash_on_cash_return(
            first_year_cf, initial_equity
        )

        assert cash_on_cash == 0.0  # Should return 0 for zero equity

    def test_cash_on_cash_negative_equity(self):
        """Test cash-on-cash return with negative equity."""
        first_year_cf = 24000.0
        initial_equity = -50000.0

        cash_on_cash = PropertyMetrics.calculate_cash_on_cash_return(
            first_year_cf, initial_equity
        )

        assert cash_on_cash == 0.0  # Should return 0 for negative equity

    def test_cash_on_cash_zero_cash_flow(self):
        """Test cash-on-cash return with zero cash flow."""
        first_year_cf = 0.0
        initial_equity = 200000.0

        cash_on_cash = PropertyMetrics.calculate_cash_on_cash_return(
            first_year_cf, initial_equity
        )

        assert cash_on_cash == 0.0  # 0 / 200000 = 0

    def test_cash_on_cash_negative_cash_flow(self):
        """Test cash-on-cash return with negative cash flow."""
        first_year_cf = -12000.0  # Negative cash flow
        initial_equity = 200000.0

        cash_on_cash = PropertyMetrics.calculate_cash_on_cash_return(
            first_year_cf, initial_equity
        )

        assert cash_on_cash == -0.06  # -12000 / 200000 = -6%


class TestCalculateComprehensiveMetrics:
    """Test comprehensive metrics calculations."""

    def test_comprehensive_metrics_without_disposition(
        self, sample_cash_flows_df: pd.DataFrame
    ):
        """Test comprehensive metrics without disposition value."""
        initial_investment = 600000.0

        metrics = PropertyMetrics.calculate_comprehensive_metrics(
            sample_cash_flows_df, initial_investment
        )

        # Check expected metrics
        assert "stabilized_noi" in metrics
        assert metrics["stabilized_noi"] == 48000.0  # (10000 - 6000) * 12

        assert "yield_on_cost" in metrics
        assert metrics["yield_on_cost"] == 0.08  # 48000 / 600000

        assert "first_year_cash_flow" in metrics
        assert metrics["first_year_cash_flow"] == 48000.0  # 4000 * 12

        assert "cash_on_cash_return" in metrics
        assert metrics["cash_on_cash_return"] == 0.08  # 48000 / 600000

        # Should not have IRR or return metrics without disposition
        assert "irr" not in metrics
        assert "total_return" not in metrics
        assert "total_return_multiple" not in metrics

    def test_comprehensive_metrics_with_disposition(
        self, sample_cash_flows_df: pd.DataFrame
    ):
        """Test comprehensive metrics with disposition value."""
        initial_investment = 600000.0
        disposition_value = 750000.0
        disposition_date = sample_cash_flows_df.index[-1]  # Last period

        metrics = PropertyMetrics.calculate_comprehensive_metrics(
            sample_cash_flows_df,
            initial_investment,
            disposition_value=disposition_value,
            disposition_date=disposition_date,
        )

        # Should have all metrics including IRR and returns
        assert "stabilized_noi" in metrics
        assert "yield_on_cost" in metrics
        assert "first_year_cash_flow" in metrics
        assert "cash_on_cash_return" in metrics
        assert "total_return" in metrics
        assert "total_return_multiple" in metrics

        # Check return calculations
        total_cf = sample_cash_flows_df["net_cash_flow"].sum()  # 48000
        expected_total_return = total_cf + disposition_value - initial_investment
        # 48000 + 750000 - 600000 = 198000
        assert metrics["total_return"] == expected_total_return

        expected_multiple = (
            expected_total_return + initial_investment
        ) / initial_investment
        # (198000 + 600000) / 600000 = 1.33
        assert abs(metrics["total_return_multiple"] - expected_multiple) < 1e-10

        # IRR should be calculated (may be None if calculation fails)
        assert "irr" in metrics

    def test_comprehensive_metrics_disposition_date_not_in_index(
        self, sample_cash_flows_df: pd.DataFrame
    ):
        """Test comprehensive metrics with disposition date not in cash flow index."""
        initial_investment = 600000.0
        disposition_value = 750000.0
        # Use a date that's not in the original index to trigger the else clause
        disposition_date = pd.Period("2025-01", freq="M")  # After the cash flow period

        metrics = PropertyMetrics.calculate_comprehensive_metrics(
            sample_cash_flows_df,
            initial_investment,
            disposition_value=disposition_value,
            disposition_date=disposition_date,
        )

        # Should still calculate IRR with the new date added
        assert "irr" in metrics
        assert "total_return" in metrics
        assert "total_return_multiple" in metrics

    def test_comprehensive_metrics_irr_failure(
        self, sample_monthly_index: pd.PeriodIndex
    ):
        """Test comprehensive metrics when IRR calculation fails."""
        # Create cash flows that will cause IRR to fail (all zero cash flows)
        bad_cash_flows = pd.DataFrame(
            {
                "revenue": [0.0] * 12,
                "expenses": [0.0] * 12,
                "net_cash_flow": [0.0] * 12,
            },
            index=sample_monthly_index,
        )

        initial_investment = 100000.0
        disposition_value = 0.0  # Zero disposition value
        disposition_date = bad_cash_flows.index[-1]

        metrics = PropertyMetrics.calculate_comprehensive_metrics(
            bad_cash_flows,
            initial_investment,
            disposition_value=disposition_value,
            disposition_date=disposition_date,
        )

        # IRR should be None due to calculation failure (all zero flows except negative initial)
        assert metrics["irr"] is None

    def test_comprehensive_metrics_short_cash_flows(
        self, sample_monthly_index: pd.PeriodIndex
    ):
        """Test comprehensive metrics with less than 12 months of cash flows."""
        short_index = sample_monthly_index[:6]  # Only 6 months
        short_cash_flows = pd.DataFrame(
            {
                "revenue": [10000.0] * 6,
                "expenses": [6000.0] * 6,
                "net_cash_flow": [4000.0] * 6,
            },
            index=short_index,
        )

        initial_investment = 300000.0

        metrics = PropertyMetrics.calculate_comprehensive_metrics(
            short_cash_flows, initial_investment
        )

        # First year cash flow should be sum of all available flows
        assert metrics["first_year_cash_flow"] == 24000.0  # 4000 * 6
        assert metrics["cash_on_cash_return"] == 0.08  # 24000 / 300000

    def test_comprehensive_metrics_missing_columns(
        self, sample_monthly_index: pd.PeriodIndex
    ):
        """Test comprehensive metrics with missing DataFrame columns."""
        minimal_df = pd.DataFrame(index=sample_monthly_index)  # No columns

        initial_investment = 600000.0

        metrics = PropertyMetrics.calculate_comprehensive_metrics(
            minimal_df, initial_investment
        )

        # Should still calculate with defaults (zeros)
        assert "stabilized_noi" in metrics
        assert metrics["stabilized_noi"] == 0.0  # No revenue or expenses
        assert metrics["yield_on_cost"] == 0.0
        assert metrics["first_year_cash_flow"] == 0.0
        assert metrics["cash_on_cash_return"] == 0.0


class TestPropertyMetricsIntegration:
    """Test integration scenarios and edge cases."""

    def test_realistic_development_scenario(self):
        """Test a realistic development project scenario."""
        # 24-month development + operation period
        timeline = pd.period_range(start="2024-01", periods=24, freq="M")

        # Development phase (first 12 months): expenses but no revenue
        # Operation phase (next 12 months): revenue and expenses
        revenue = [0.0] * 12 + [15000.0] * 12
        expenses = [5000.0] * 12 + [8000.0] * 12  # Construction costs + operations
        net_cf = [r - e for r, e in zip(revenue, expenses)]

        cash_flows = pd.DataFrame(
            {"revenue": revenue, "expenses": expenses, "net_cash_flow": net_cf},
            index=timeline,
        )

        initial_investment = 800000.0
        disposition_value = 1200000.0
        disposition_date = timeline[-1]

        metrics = PropertyMetrics.calculate_comprehensive_metrics(
            cash_flows,
            initial_investment,
            disposition_value=disposition_value,
            disposition_date=disposition_date,
        )

        # Verify reasonable results for development scenario
        assert metrics["stabilized_noi"] == 84000.0  # (15000 - 8000) * 12
        assert 0.05 < metrics["yield_on_cost"] < 0.15  # Reasonable development yield
        assert (
            metrics["first_year_cash_flow"] < 84000.0
        )  # Lower due to development phase

        # Should have calculated IRR and returns
        assert "irr" in metrics
        assert "total_return" in metrics
        assert "total_return_multiple" in metrics

    def test_property_metrics_precision(self):
        """Test that calculations maintain proper precision."""
        # Test with fractional values that could cause precision issues
        revenue = 10333.33
        expenses = 6166.67

        noi = PropertyMetrics.calculate_noi(revenue, expenses)

        # Should maintain precision to reasonable decimal places
        expected_noi = 4166.66
        assert abs(noi - expected_noi) < 0.01  # Within 1 cent

    def test_property_metrics_large_numbers(self):
        """Test calculations with large numbers (institutional scale)."""
        # Large institutional property
        annual_revenue = 50_000_000.0  # $50M
        annual_expenses = 30_000_000.0  # $30M
        total_cost = 400_000_000.0  # $400M

        noi = PropertyMetrics.calculate_noi(annual_revenue, annual_expenses)
        yield_on_cost = PropertyMetrics.calculate_yield_on_cost(noi, total_cost)

        assert noi == 20_000_000.0  # $20M NOI
        assert yield_on_cost == 0.05  # 5% yield on cost

        # Should handle large numbers without precision loss
        assert isinstance(noi, float)
        assert isinstance(yield_on_cost, float)
