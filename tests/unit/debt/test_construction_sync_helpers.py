# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for construction loan synchronous calculation helper methods.

Tests the private helper methods used in the synchronous interest-covenant calculation:
- _extract_capital_uses_by_period()
- _calculate_covenant_adjustments()
"""

import pandas as pd
import pytest

from performa.debt.construction import ConstructionFacility
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

    @pytest.mark.skip(
        reason="Validation now requires either loan_amount or ltc_ratio - no default LTC anymore"
    )
    def test_uses_default_ltc_when_none(self):
        """Should use 0.70 default LTC when ltc_ratio is None."""
        facility = ConstructionFacility(
            name="Test",
            interest_rate=InterestRate(details=FixedRate(rate=0.07)),
            ltc_ratio=None,  # No LTC specified
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
        assert result[periods[0]] == pytest.approx(1_000_000 * 0.70)

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

        # Mock minimal context
        pytest.skip("Requires mock context - implement after fixture setup")

    def test_prepay_sweep_returns_adjustments(self):
        """PREPAY sweep with excess cash should return adjustments."""
        pytest.skip("Requires mock context - implement after fixture setup")

    def test_trap_sweep_returns_zeros(self):
        """TRAP sweep should return zeros (separate posting)."""
        pytest.skip("Requires mock context - implement after fixture setup")

    def test_insufficient_cash_returns_zeros(self):
        """Insufficient NOI should return zeros."""
        pytest.skip("Requires mock context - implement after fixture setup")
