# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""Tests for DirectCapValuation - Income Approach Valuation."""

import warnings
from datetime import date
from unittest.mock import Mock
from uuid import uuid4

import pandas as pd
import pytest

from performa.core.ledger import Ledger
from performa.core.primitives import GlobalSettings, Timeline
from performa.deal.orchestrator import DealContext
from performa.valuation import DirectCapValuation


def create_test_context(timeline: Timeline, noi_series=None) -> DealContext:
    """Create a test DealContext with proper ledger and mock deal instance."""
    # Use mock deal to bypass complex validation
    mock_deal = Mock()
    mock_deal.name = "Test Deal"
    mock_deal.uid = uuid4()

    # Create ledger and context
    ledger = Ledger()
    return DealContext(
        timeline=timeline,
        settings=GlobalSettings(),
        noi_series=noi_series,
        deal=mock_deal,
        ledger=ledger,
    )


class TestDirectCapValuation:  # noqa: PLR0904
    """Test DirectCapValuation functionality."""

    def test_creation_basic(self):
        """Test basic DirectCapValuation creation."""
        valuation = DirectCapValuation(
            name="Test Valuation",
            cap_rate=0.065,
        )

        assert valuation.name == "Test Valuation"
        assert valuation.cap_rate == 0.065
        assert valuation.noi_basis_kind == "LTM"  # Default
        assert valuation.transaction_costs_rate == 0.025  # Default
        assert valuation.hold_period_months is None
        assert valuation.kind == "direct_cap"

    def test_creation_with_all_parameters(self):
        """Test DirectCapValuation creation with all parameters."""
        valuation = DirectCapValuation(
            name="Full Test",
            cap_rate=0.055,
            transaction_costs_rate=0.02,
            hold_period_months=84,
            noi_basis_kind="NTM",
            cap_rates_by_use={"office": 0.055, "retail": 0.07},
        )

        assert valuation.name == "Full Test"
        assert valuation.cap_rate == 0.055
        assert valuation.transaction_costs_rate == 0.02
        assert valuation.hold_period_months == 84
        assert valuation.noi_basis_kind == "NTM"
        assert valuation.cap_rates_by_use["office"] == 0.055

    @pytest.mark.filterwarnings("ignore:ALM.*unreliable:UserWarning")
    def test_noi_basis_options(self):
        """Test all NOI basis options."""
        for basis in ["LTM", "NTM", "Stabilized", "ALM"]:
            valuation = DirectCapValuation(
                name=f"Test {basis}", cap_rate=0.06, noi_basis_kind=basis
            )
            assert valuation.noi_basis_kind == basis

    def test_alm_warning(self):
        """Test that ALM basis triggers warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            DirectCapValuation(name="ALM Test", cap_rate=0.06, noi_basis_kind="ALM")

            assert len(w) == 1
            assert "unreliable" in str(w[0].message).lower()
            assert "ALM" in str(w[0].message)

    def test_validation_cap_rate_bounds(self):
        """Test cap rate validation."""
        # Too low
        with pytest.raises(ValueError, match="should be between 1% and 20%"):
            DirectCapValuation(name="Test", cap_rate=0.005)

        # Too high
        with pytest.raises(ValueError, match="should be between 1% and 20%"):
            DirectCapValuation(name="Test", cap_rate=0.25)

        # Valid bounds
        DirectCapValuation(name="Test", cap_rate=0.01)  # 1%
        DirectCapValuation(name="Test", cap_rate=0.20)  # 20%

    def test_validation_transaction_costs(self):
        """Test transaction costs validation."""
        # Too low
        with pytest.raises(ValueError, match="should be between 0.5% and 10%"):
            DirectCapValuation(name="Test", cap_rate=0.06, transaction_costs_rate=0.001)

        # Too high
        with pytest.raises(ValueError, match="should be between 0.5% and 10%"):
            DirectCapValuation(name="Test", cap_rate=0.06, transaction_costs_rate=0.15)

    def test_validation_cap_rates_by_use(self):
        """Test asset-specific cap rates validation."""
        with pytest.raises(ValueError, match="should be between 1% and 20%"):
            DirectCapValuation(
                name="Test",
                cap_rate=0.06,
                cap_rates_by_use={"office": 0.005},  # Too low
            )

    def test_net_sale_proceeds_rate(self):
        """Test net sale proceeds rate calculation."""
        valuation = DirectCapValuation(
            name="Test", cap_rate=0.06, transaction_costs_rate=0.025
        )
        assert valuation.net_sale_proceeds_rate == 0.975

    def test_get_noi_basis_ltm(self):
        """Test LTM (Last 12 Months) NOI basis extraction."""
        # Create mock context with NOI series
        timeline = Timeline.from_dates(date(2024, 1, 1), date(2024, 12, 31))
        noi_series = pd.Series([10000] * 12, index=timeline.period_index)
        context = create_test_context(timeline, noi_series)

        valuation = DirectCapValuation(
            name="LTM Test", cap_rate=0.06, noi_basis_kind="LTM"
        )

        noi_basis = valuation.get_noi_basis(context)
        assert noi_basis == 120000  # 12 months × 10,000

    def test_get_noi_basis_ltm_short_series(self):
        """Test LTM with fewer than 12 months (annualization)."""
        timeline = Timeline.from_dates(date(2024, 1, 1), date(2024, 6, 30))  # 6 months
        noi_series = pd.Series([10000] * 6, index=timeline.period_index)
        context = create_test_context(timeline, noi_series)

        valuation = DirectCapValuation(
            name="LTM Short Test", cap_rate=0.06, noi_basis_kind="LTM"
        )

        noi_basis = valuation.get_noi_basis(context)
        assert noi_basis == 120000  # 6 months × 10,000 × (12/6)

    def test_get_noi_basis_ntm(self):
        """Test NTM (Next 12 Months) NOI basis extraction."""
        timeline = Timeline.from_dates(
            date(2024, 1, 1), date(2025, 12, 31)
        )  # 24 months
        noi_series = pd.Series([8000] * 12 + [12000] * 12, index=timeline.period_index)
        context = create_test_context(timeline, noi_series)

        valuation = DirectCapValuation(
            name="NTM Test", cap_rate=0.06, noi_basis_kind="NTM"
        )

        noi_basis = valuation.get_noi_basis(context)
        assert noi_basis == 96000  # First 12 months × 8,000

    def test_get_noi_basis_stabilized(self):
        """Test Stabilized NOI basis (mean × 12)."""
        timeline = Timeline.from_dates(date(2024, 1, 1), date(2024, 12, 31))
        noi_series = pd.Series(
            [8000, 9000, 10000, 11000] * 3, index=timeline.period_index
        )
        context = create_test_context(timeline, noi_series)

        valuation = DirectCapValuation(
            name="Stabilized Test", cap_rate=0.06, noi_basis_kind="Stabilized"
        )

        noi_basis = valuation.get_noi_basis(context)
        expected = 9500 * 12  # Mean(8000, 9000, 10000, 11000) × 12
        assert noi_basis == expected

    @pytest.mark.filterwarnings("ignore:ALM.*unreliable:UserWarning")
    def test_get_noi_basis_alm_with_warning(self):
        """Test ALM (12× Last Month) with warning."""
        timeline = Timeline.from_dates(date(2024, 1, 1), date(2024, 12, 31))
        noi_series = pd.Series([8000] * 11 + [15000], index=timeline.period_index)
        context = create_test_context(timeline, noi_series)

        # Test that ALM creation triggers warning
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            valuation = DirectCapValuation(
                name="ALM Test", cap_rate=0.06, noi_basis_kind="ALM"
            )

            # Should have warning from creation
            assert len(w) >= 1
            assert "ALM" in str(w[0].message)
            assert "unreliable" in str(w[0].message).lower()

        # Test that calculation works correctly
        noi_basis = valuation.get_noi_basis(context)
        assert noi_basis == 180000  # 15,000 × 12 (last month)

    def test_get_noi_basis_missing_series(self):
        """Test error handling for missing NOI series."""
        timeline = Timeline.from_dates(date(2024, 1, 1), date(2024, 12, 31))
        context = create_test_context(timeline, None)  # Missing NOI series

        valuation = DirectCapValuation(name="Test", cap_rate=0.06)

        with pytest.raises(ValueError, match="NOI series required"):
            valuation.get_noi_basis(context)

    def test_calculate_gross_value_simple(self):
        """Test simple gross value calculation."""
        valuation = DirectCapValuation(name="Test", cap_rate=0.0625)

        gross_value = valuation.calculate_gross_value(noi_basis=625000)
        assert gross_value == 10000000  # 625,000 / 0.0625

    def test_calculate_gross_value_mixed_use(self):
        """Test mixed-use gross value with asset-specific cap rates."""
        valuation = DirectCapValuation(
            name="Mixed Use Test",
            cap_rate=0.06,  # Blended rate
            cap_rates_by_use={"office": 0.055, "retail": 0.07},
        )

        noi_by_use = {"office": 400000, "retail": 200000}
        gross_value = valuation.calculate_gross_value(
            noi_basis=600000, noi_by_use=noi_by_use
        )

        expected = (400000 / 0.055) + (200000 / 0.07)  # Office + Retail
        assert abs(gross_value - expected) < 1.0

    def test_calculate_net_proceeds(self):
        """Test net proceeds after transaction costs."""
        valuation = DirectCapValuation(
            name="Test", cap_rate=0.0625, transaction_costs_rate=0.025
        )

        net_proceeds = valuation.calculate_net_proceeds(noi_basis=625000)
        expected = (625000 / 0.0625) * 0.975  # Gross × (1 - transaction costs)
        assert abs(net_proceeds - expected) < 1.0

    def test_calculate_value_comprehensive(self):
        """Test comprehensive value calculation with context."""
        timeline = Timeline.from_dates(date(2024, 1, 1), date(2024, 12, 31))
        noi_series = pd.Series([50000] * 12, index=timeline.period_index)
        context = create_test_context(timeline, noi_series)

        valuation = DirectCapValuation(
            name="Test",
            cap_rate=0.06,
            transaction_costs_rate=0.025,
            noi_basis_kind="LTM",
        )

        results = valuation.calculate_value(context)

        assert "property_value" in results
        assert "gross_value" in results
        assert "net_proceeds" in results
        assert "noi_basis" in results
        assert "cap_rate" in results

        expected_noi = 600000  # 50,000 × 12
        expected_gross = 10000000  # 600,000 / 0.06
        expected_net = 9750000  # 10,000,000 × 0.975

        assert results["noi_basis"] == expected_noi
        assert results["gross_value"] == expected_gross
        assert results["net_proceeds"] == expected_net
        assert results["property_value"] == expected_net

    def test_calculate_metrics_with_cost_basis(self):
        """Test comprehensive metrics with cost basis."""
        timeline = Timeline.from_dates(date(2024, 1, 1), date(2024, 12, 31))
        noi_series = pd.Series([50000] * 12, index=timeline.period_index)
        context = create_test_context(timeline, noi_series)

        valuation = DirectCapValuation(name="Test", cap_rate=0.06)

        metrics = valuation.calculate_metrics(context, total_cost_basis=8000000)

        assert "total_cost_basis" in metrics
        assert "total_profit" in metrics
        assert "profit_margin" in metrics
        assert "yield_on_cost" in metrics

        assert metrics["total_cost_basis"] == 8000000
        assert metrics["yield_on_cost"] == 0.075  # 600,000 / 8,000,000

    def test_compute_cf_with_hold_period(self):
        """Test cash flow computation with specified hold period."""
        timeline = Timeline.from_dates(
            date(2024, 1, 1), date(2029, 12, 31)
        )  # 72 months
        noi_series = pd.Series([50000] * 72, index=timeline.period_index)
        context = create_test_context(timeline, noi_series)

        valuation = DirectCapValuation(
            name="Test",
            cap_rate=0.06,
            hold_period_months=60,  # Exit at month 60, not 72
        )

        cf_series = valuation.compute_cf(context)

        # Should have proceeds at month 60, not 72
        assert cf_series.sum() > 0
        assert cf_series.iloc[60] > 0  # Month 60 has proceeds
        assert cf_series.iloc[71] == 0  # Last month has no proceeds

    def test_compute_cf_default_timing(self):
        """Test cash flow computation with default timing (end of timeline)."""
        timeline = Timeline.from_dates(
            date(2024, 1, 1), date(2026, 12, 31)
        )  # 36 months
        noi_series = pd.Series([50000] * 36, index=timeline.period_index)
        context = create_test_context(timeline, noi_series)

        valuation = DirectCapValuation(name="Test", cap_rate=0.06)

        cf_series = valuation.compute_cf(context)

        # Should have proceeds at last period
        assert cf_series.sum() > 0
        assert cf_series.iloc[-1] > 0  # Last period has proceeds

    def test_compute_cf_missing_noi_fails_fast(self):
        """Test that missing NOI fails fast."""
        timeline = Timeline.from_dates(date(2024, 1, 1), date(2024, 12, 31))
        context = create_test_context(timeline, None)  # Missing NOI!

        valuation = DirectCapValuation(name="Test", cap_rate=0.06)

        with pytest.raises(RuntimeError, match="DirectCap valuation failed"):
            valuation.compute_cf(context)

    def test_factory_conservative(self):
        """Test conservative factory method."""
        valuation = DirectCapValuation.conservative(name="Conservative Test")

        assert valuation.name == "Conservative Test"
        assert valuation.cap_rate == 0.065
        assert valuation.transaction_costs_rate == 0.025
        assert valuation.noi_basis_kind == "LTM"

    def test_factory_aggressive(self):
        """Test aggressive factory method."""
        valuation = DirectCapValuation.aggressive(name="Aggressive Test")

        assert valuation.name == "Aggressive Test"
        assert valuation.cap_rate == 0.055
        assert valuation.transaction_costs_rate == 0.020
        assert valuation.noi_basis_kind == "NTM"

    def test_factory_exit_valuation(self):
        """Test exit valuation factory method."""
        valuation = DirectCapValuation.exit_valuation(
            name="Exit Test", hold_period_months=84
        )

        assert valuation.name == "Exit Test"
        assert valuation.cap_rate == 0.0625
        assert valuation.hold_period_months == 84
        assert valuation.noi_basis_kind == "LTM"

    @pytest.mark.filterwarnings("ignore:ALM.*unreliable:UserWarning")
    def test_noi_basis_integration_realistic_scenario(self):
        """Test NOI basis calculation in realistic property scenario."""
        # Create timeline with varying NOI (seasonal property)
        timeline = Timeline.from_dates(
            date(2024, 1, 1), date(2025, 12, 31)
        )  # 24 months

        # Simulate seasonal NOI: higher in summer, lower in winter
        seasonal_noi = (
            [40000] * 3  # Q1 (Jan-Mar): Lower
            + [60000] * 6  # Q2-Q3 (Apr-Sep): Higher
            + [45000] * 3  # Q4 (Oct-Dec): Medium
            + [42000] * 3  # Q1 Y2: Lower
            + [62000] * 6  # Q2-Q3 Y2: Higher
            + [47000] * 3  # Q4 Y2: Medium
        )

        noi_series = pd.Series(seasonal_noi, index=timeline.period_index)
        context = create_test_context(timeline, noi_series)

        # Test different basis calculations
        ltm_val = DirectCapValuation(name="LTM", cap_rate=0.06, noi_basis_kind="LTM")
        ntm_val = DirectCapValuation(name="NTM", cap_rate=0.06, noi_basis_kind="NTM")
        alm_val = DirectCapValuation(name="ALM", cap_rate=0.06, noi_basis_kind="ALM")

        ltm_basis = ltm_val.get_noi_basis(context)  # Last 12 months
        ntm_basis = ntm_val.get_noi_basis(context)  # First 12 months

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # Suppress ALM warning for test
            alm_basis = alm_val.get_noi_basis(context)  # Last month × 12

        # LTM should use last 12 months (months 12-23)
        expected_ltm = sum(seasonal_noi[12:24])  # 42k×3 + 62k×6 + 47k×3 = 639k
        assert ltm_basis == expected_ltm

        # NTM should use first 12 months (months 0-11)
        expected_ntm = sum(seasonal_noi[0:12])  # 40k×3 + 60k×6 + 45k×3 = 615k
        assert ntm_basis == expected_ntm

        # ALM should use last month × 12
        expected_alm = seasonal_noi[-1] * 12  # 47k × 12 = 564k
        assert alm_basis == expected_alm

        # They should all be different (realistic seasonal variation)
        assert ltm_basis != ntm_basis != alm_basis

    def test_invalid_noi_basis_kind(self):
        """Test error for invalid NOI basis kind."""
        # This should be caught by Pydantic validation
        with pytest.raises(ValueError):
            DirectCapValuation(
                name="Test",
                cap_rate=0.06,
                noi_basis_kind="INVALID",  # Not in Literal options
            )

    def test_edge_case_single_month_noi(self):
        """Test edge case with only one month of NOI."""
        timeline = Timeline.from_dates(date(2024, 1, 1), date(2024, 1, 31))  # 1 month
        noi_series = pd.Series([50000], index=timeline.period_index)
        context = create_test_context(timeline, noi_series)

        valuation = DirectCapValuation(name="Test", cap_rate=0.06, noi_basis_kind="LTM")

        # Should annualize the single month
        noi_basis = valuation.get_noi_basis(context)
        assert noi_basis == 600000  # 50,000 × (12/1)

    def test_comprehensive_real_world_scenario(self):
        """Test comprehensive real-world valuation scenario."""
        # 5-year timeline with realistic NOI growth
        timeline = Timeline.from_dates(date(2024, 1, 1), date(2028, 12, 31))

        # Simulate realistic NOI: starts at 45k/month, grows 3% annually
        base_monthly_noi = 45000
        monthly_noi = []
        for year in range(5):
            annual_growth = 1.03**year
            year_noi = base_monthly_noi * annual_growth
            monthly_noi.extend([year_noi] * 12)

        noi_series = pd.Series(monthly_noi, index=timeline.period_index)
        context = create_test_context(timeline, noi_series)

        valuation = DirectCapValuation(
            name="Real World Test",
            cap_rate=0.0625,
            transaction_costs_rate=0.025,
            hold_period_months=60,  # 5-year hold
            noi_basis_kind="LTM",
        )

        # Test value calculation
        results = valuation.calculate_value(context)

        # Should use trailing 12 months (year 5 NOI)
        expected_trailing_noi = base_monthly_noi * (1.03**4) * 12  # Year 5
        assert abs(results["noi_basis"] - expected_trailing_noi) < 100

        # Test cash flow placement (60-month timeline = indices 0-59)
        cf_series = valuation.compute_cf(context)
        assert cf_series.iloc[59] > 0  # Proceeds at month 59 (60th month, 0-based)
        assert cf_series.iloc[58] == 0  # No proceeds before

        # Proceeds should be realistic for institutional deal
        total_proceeds = cf_series.sum()
        assert 8000000 < total_proceeds < 12000000  # Reasonable range
