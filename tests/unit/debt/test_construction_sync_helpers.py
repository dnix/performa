# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for construction loan synchronous calculation helper methods.

Tests the private helper methods used in the synchronous interest-covenant calculation:
- _extract_capital_uses_by_period()
- _calculate_covenant_adjustments()
"""
from datetime import date
from unittest.mock import Mock

import pandas as pd
import pytest

from performa.core.ledger import Ledger
from performa.core.primitives import GlobalSettings, Timeline
from performa.deal.orchestrator import DealContext
from performa.debt.construction import ConstructionFacility
from performa.debt.covenants import CashSweep, SweepMode
from performa.debt.rates import FixedRate, InterestRate


class TestExtractCapitalUsesByPeriod:
    """Tests for _extract_capital_uses_by_period() helper method."""

    def test_empty_ledger_returns_empty_dict(self):
        """Empty ledger should return empty dict."""
        facility = ConstructionFacility(
            name="Test",
            interest_rate=InterestRate(details=FixedRate(rate=0.07)),
            ltc_ratio=0.75,
            loan_term_months=18,
        )

        # Create empty DataFrame with correct schema
        empty_df = pd.DataFrame({
            "date": pd.Series([], dtype="datetime64[ns]"),
            "amount": pd.Series([], dtype="float64"),
            "flow_purpose": pd.Series([], dtype="str"),
        })

        result = facility._extract_capital_uses_by_period(empty_df)

        assert result == {}, "Empty ledger should return empty dict"

    def test_extracts_capital_uses_correctly(self):
        """Should extract and group capital uses by period."""
        facility = ConstructionFacility(
            name="Test",
            interest_rate=InterestRate(details=FixedRate(rate=0.07)),
            ltc_ratio=0.75,
            loan_term_months=18,
        )

        # Create mock ledger with capital uses
        dates = pd.date_range("2024-01-01", periods=3, freq="MS")
        ledger_df = pd.DataFrame({
            "date": dates,
            "amount": [-1_000_000, -2_000_000, -1_500_000],  # Negative for costs
            "flow_purpose": ["Capital Use", "Capital Use", "Capital Use"],
        })

        result = facility._extract_capital_uses_by_period(ledger_df)

        # Method returns Period keys, not Timestamp (critical bug fix)
        periods = dates.to_period("M")

        # Check debt-funded portion (75% LTC)
        assert result[periods[0]] == pytest.approx(1_000_000 * 0.75)
        assert result[periods[1]] == pytest.approx(2_000_000 * 0.75)
        assert result[periods[2]] == pytest.approx(1_500_000 * 0.75)

    def test_applies_ltc_ratio_correctly(self):
        """Should apply LTC ratio to get debt-funded portion."""
        facility = ConstructionFacility(
            name="Test",
            interest_rate=InterestRate(details=FixedRate(rate=0.07)),
            ltc_ratio=0.80,  # 80% LTC
            loan_term_months=18,
        )

        dates = pd.date_range("2024-01-01", periods=1, freq="MS")
        ledger_df = pd.DataFrame({
            "date": dates,
            "amount": [-1_000_000],
            "flow_purpose": ["Capital Use"],
        })

        result = facility._extract_capital_uses_by_period(ledger_df)

        # Method returns Period keys
        periods = dates.to_period("M")
        assert result[periods[0]] == pytest.approx(1_000_000 * 0.80)

    def test_filters_non_capital_uses(self):
        """Should only include Capital Use transactions."""
        facility = ConstructionFacility(
            name="Test",
            interest_rate=InterestRate(details=FixedRate(rate=0.07)),
            ltc_ratio=0.75,
            loan_term_months=18,
        )

        dates = pd.date_range("2024-01-01", periods=3, freq="MS")
        ledger_df = pd.DataFrame({
            "date": dates,
            "amount": [-1_000_000, -500_000, -200_000],
            "flow_purpose": ["Capital Use", "Operating Expense", "Interest Payment"],
        })

        result = facility._extract_capital_uses_by_period(ledger_df)

        # Only first transaction should be included
        assert len(result) == 1
        # Method returns Period keys
        periods = dates.to_period("M")
        assert result[periods[0]] == pytest.approx(1_000_000 * 0.75)


class TestCalculateCovenantAdjustments:
    """Tests for _calculate_covenant_adjustments() helper method."""

    def test_no_sweep_returns_zeros(self):
        """No sweep configured should return zero adjustments."""
        
        facility = ConstructionFacility(
            name="Test",
            interest_rate=InterestRate(details=FixedRate(rate=0.07)),
            ltc_ratio=0.75,
            loan_term_months=18,
            cash_sweep=None,  # No sweep
        )

        # Mock context
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
        settings = GlobalSettings()
        ledger = Ledger()
        mock_deal = Mock()
        mock_deal.name = "Test Deal"
        context = DealContext(
            timeline=timeline,
            settings=settings,
            deal=mock_deal,
            ledger=ledger,
        )
        
        # Call method
        adjustments = facility._calculate_covenant_adjustments(
            period=pd.Timestamp("2024-01-01"),
            raw_interest=10_000.0,
            balance=1_000_000.0,
            period_noi=50_000.0,
            context=context,
        )
        
        # Should return zero adjustments
        assert adjustments.interest_paid_by_sweep == 0.0
        assert adjustments.principal_prepayment == 0.0

    def test_prepay_sweep_returns_adjustments(self):
        """PREPAY sweep with excess cash should return adjustments."""
        
        # Facility with PREPAY sweep
        facility = ConstructionFacility(
            name="Prepay Sweep Test",
            interest_rate=InterestRate(details=FixedRate(rate=0.07)),
            ltc_ratio=0.75,
            loan_term_months=18,
            cash_sweep=CashSweep(mode=SweepMode.PREPAY, end_month=12),
        )
        
        # Mock context
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
        settings = GlobalSettings()
        ledger = Ledger()
        mock_deal = Mock()
        mock_deal.name = "Test Deal"
        context = DealContext(
            timeline=timeline,
            settings=settings,
            deal=mock_deal,
            ledger=ledger,
        )
        
        # Call with excess NOI (enough to pay interest + prepay principal)
        period = pd.Timestamp("2024-01-01")
        adjustments = facility._calculate_covenant_adjustments(
            period=period,
            raw_interest=10_000.0,
            balance=1_000_000.0,
            period_noi=50_000.0,  # Excess cash after interest
            context=context,
        )
        
        # Should return adjustments (interest paid + principal prepayment)
        assert adjustments.interest_paid_by_sweep >= 0.0
        assert adjustments.principal_prepayment >= 0.0
        # If excess cash available, at least one should be non-zero
        assert (adjustments.interest_paid_by_sweep + adjustments.principal_prepayment) > 0.0

    def test_trap_sweep_returns_zeros(self):
        """TRAP sweep should return zeros (separate posting)."""
        
        # Facility with TRAP sweep
        facility = ConstructionFacility(
            name="Trap Sweep Test",
            interest_rate=InterestRate(details=FixedRate(rate=0.07)),
            ltc_ratio=0.75,
            loan_term_months=18,
            cash_sweep=CashSweep(mode=SweepMode.TRAP, end_month=12),
        )
        
        # Mock context
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
        settings = GlobalSettings()
        ledger = Ledger()
        mock_deal = Mock()
        mock_deal.name = "Test Deal"
        context = DealContext(
            timeline=timeline,
            settings=settings,
            deal=mock_deal,
            ledger=ledger,
        )
        
        # Call with excess NOI
        period = pd.Timestamp("2024-01-01")
        adjustments = facility._calculate_covenant_adjustments(
            period=period,
            raw_interest=10_000.0,
            balance=1_000_000.0,
            period_noi=50_000.0,
            context=context,
        )
        
        # TRAP mode doesn't return adjustments (posts separately via process())
        assert adjustments.interest_paid_by_sweep == 0.0
        assert adjustments.principal_prepayment == 0.0

    def test_insufficient_cash_returns_zeros(self):
        """Insufficient NOI should return zeros."""
        
        # Facility with PREPAY sweep
        facility = ConstructionFacility(
            name="Insufficient Cash Test",
            interest_rate=InterestRate(details=FixedRate(rate=0.07)),
            ltc_ratio=0.75,
            loan_term_months=18,
            cash_sweep=CashSweep(mode=SweepMode.PREPAY, end_month=12),
        )
        
        # Mock context
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
        settings = GlobalSettings()
        ledger = Ledger()
        mock_deal = Mock()
        mock_deal.name = "Test Deal"
        context = DealContext(
            timeline=timeline,
            settings=settings,
            deal=mock_deal,
            ledger=ledger,
        )
        
        # Call with insufficient NOI (less than interest)
        period = pd.Timestamp("2024-01-01")
        adjustments = facility._calculate_covenant_adjustments(
            period=period,
            raw_interest=10_000.0,
            balance=1_000_000.0,
            period_noi=5_000.0,  # Not enough to cover full interest
            context=context,
        )
        
        # Waterfall: NOI covers partial interest, no excess for prepayment
        # Cash to interest: min(5000, 10000) = 5000
        # Interest from reserve: 10000 - 5000 = 5000
        # Excess for prepayment: max(0, 5000 - 5000) = 0
        assert adjustments.interest_paid_by_sweep == 5_000.0  # Partial interest payment
        assert adjustments.principal_prepayment == 0.0  # No excess cash for prepayment
