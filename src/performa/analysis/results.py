# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Asset-level analysis result models.

This module provides result classes for asset-only analysis, maintaining
clean module boundaries by keeping deal-related results in the deal module.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, List

import pandas as pd

from performa.core.ledger import Ledger, LedgerQueries
from performa.core.primitives import Timeline
from performa.core.primitives.enums import UnleveredAggregateLineKey

if TYPE_CHECKING:
    from performa.analysis.scenario import AnalysisScenarioBase
    from performa.core.base import PropertyBaseModel
    from performa.core.primitives import CashFlowModel


@dataclass
class AssetAnalysisResult:
    """
    Results from asset-level (unlevered) analysis.

    Uses query-based properties for all financial metrics, computed on-demand
    from the transactional ledger. This ensures single source of truth and
    eliminates pre-computed DataFrames that can become stale.

    Attributes:
        ledger: Transactional ledger
        property: Property model used in analysis
        timeline: Timeline used for the analysis
        scenario: The executed analysis scenario with full orchestrator access
        models: Direct access to all prepared CashFlowModel instances
    """

    # Core ledger-based architecture
    ledger: Ledger

    # Core inputs
    property: "PropertyBaseModel"
    timeline: Timeline

    # Full scenario and orchestrator access
    scenario: "AnalysisScenarioBase"  # Full scenario with _orchestrator
    models: List["CashFlowModel"]  # Direct access to all models

    @property
    def get_ledger_df(self) -> pd.DataFrame:
        """
        Convenience accessor for the current ledger.

        Returns:
            The complete transactional ledger DataFrame
        """
        return self.ledger.ledger_df()

    def get_ledger_queries(self):
        """
        Create a LedgerQueries instance for comprehensive ledger analysis.

        Returns the single canonical DuckDBquery implementation.

        Returns:
            LedgerQueries instance with all financial metrics available
        """
        return LedgerQueries(self.ledger)

    # === Query-Based Financial Properties ===
    # All metrics computed on-demand from ledger (single source of truth)

    @property
    def noi(self) -> pd.Series:
        """
        Net Operating Income computed from ledger.

        Returns:
            Time series of NOI by period
        """
        return self.get_ledger_queries().noi()

    @property
    def egi(self) -> pd.Series:
        """
        Effective Gross Income computed from ledger.

        Returns:
            Time series of EGI by period
        """
        return self.get_ledger_queries().egi()

    @property
    def pgr(self) -> pd.Series:
        """
        Potential Gross Revenue computed from ledger.

        Returns:
            Time series of PGR by period
        """
        return self.get_ledger_queries().pgr()

    @property
    def opex(self) -> pd.Series:
        """
        Operating expenses computed from ledger.

        Returns:
            Time series of operating expenses by period
        """
        return self.get_ledger_queries().opex()

    @property
    def capex(self) -> pd.Series:
        """
        Capital expenditures computed from ledger.

        Returns:
            Time series of capital expenditures by period
        """
        return self.get_ledger_queries().capex()

    @property
    def ucf(self) -> pd.Series:
        """
        Unlevered Cash Flow computed from ledger (project-level, pre-debt).

        Alias to project_cash_flow() for legacy callers.
        """
        return self.get_ledger_queries().project_cash_flow()

    @cached_property
    def summary_df(self) -> pd.DataFrame:
        """
        Cash flow summary DataFrame generated from ledger queries.

        Returns:
            DataFrame with key financial metrics by period (PeriodIndex)

        Note:
            This replaces the old pre-computed summary_df with an on-demand
            version built from ledger queries, ensuring consistency.
        """
        queries = self.get_ledger_queries()

        # Build summary from query results, converting to PeriodIndex
        # Use enum values for column names to match expected test format
        # NOTE: signs are preserved according to accounting conventions:
        #   - Revenues and recoveries: positive
        #   - Losses: positive magnitudes for display (vacancy, credit, abatement)
        #   - Operating expenses: negative (cost)
        summary_data = {
            UnleveredAggregateLineKey.POTENTIAL_GROSS_REVENUE.value: self._to_period_series(
                queries.pgr()
            ),
            UnleveredAggregateLineKey.RENTAL_ABATEMENT.value: self._to_period_series(
                queries.rental_abatement().abs()
            ),
            UnleveredAggregateLineKey.MISCELLANEOUS_INCOME.value: self._to_period_series(
                queries.misc_income()
            ),
            UnleveredAggregateLineKey.GENERAL_VACANCY_LOSS.value: self._to_period_series(
                queries.vacancy_loss().abs()
            ),
            UnleveredAggregateLineKey.CREDIT_LOSS.value: self._to_period_series(
                queries.credit_loss().abs()
            ),
            UnleveredAggregateLineKey.EXPENSE_REIMBURSEMENTS.value: self._to_period_series(
                queries.expense_reimbursements()
            ),
            UnleveredAggregateLineKey.EFFECTIVE_GROSS_INCOME.value: self._to_period_series(
                queries.egi()
            ),
            UnleveredAggregateLineKey.TOTAL_OPERATING_EXPENSES.value: self._to_period_series(
                queries.opex()
            ),
            UnleveredAggregateLineKey.NET_OPERATING_INCOME.value: self._to_period_series(
                queries.noi()
            ),
            UnleveredAggregateLineKey.TOTAL_CAPITAL_EXPENDITURES.value: self._to_period_series(
                queries.capex().abs()
            ),
            UnleveredAggregateLineKey.TOTAL_TENANT_IMPROVEMENTS.value: self._to_period_series(
                queries.ti().abs()
            ),
            UnleveredAggregateLineKey.TOTAL_LEASING_COMMISSIONS.value: self._to_period_series(
                queries.lc().abs()
            ),
            UnleveredAggregateLineKey.UNLEVERED_CASH_FLOW.value: self._to_period_series(
                queries.project_cash_flow()
            ),
        }

        # Create DataFrame with PeriodIndex
        summary_df = pd.DataFrame(summary_data, index=self.timeline.period_index)

        # Fill NaN values with 0 for clean presentation
        return summary_df.fillna(0.0)

    def _to_period_series(self, series: pd.Series) -> pd.Series:
        """
        Convert series with date index to PeriodIndex matching timeline.

        Args:
            series: Input series with date index

        Returns:
            Series with PeriodIndex matching timeline
        """
        # Handle empty series
        if series.empty:
            return pd.Series(0.0, index=self.timeline.period_index)

        # Create a new series with proper PeriodIndex
        result = pd.Series(0.0, index=self.timeline.period_index)
        for date_val, amount in series.items():
            # Convert date to period
            period = pd.Period(date_val, freq="M")
            if period in result.index:
                result[period] = amount
        return result

    def summary_stats(self) -> dict:
        """
        Generate summary statistics for the analysis using query-based properties.

        Returns:
            Dictionary with key analysis metrics
        """
        stats = {
            "total_records": len(self.ledger),
            "analysis_periods": len(self.timeline.period_index),
            "noi_total": self.noi.sum() if not self.noi.empty else 0.0,
            "noi_average": self.noi.mean() if not self.noi.empty else 0.0,
            "egi_total": self.egi.sum() if not self.egi.empty else 0.0,
            "ucf_total": self.ucf.sum() if not self.ucf.empty else 0.0,
        }

        # Add capital flow statistics if available
        if not self.ledger.empty:
            queries = self.get_ledger_queries()
            stats["capital_uses"] = (
                queries.total_uses().sum() if not queries.total_uses().empty else 0.0
            )
            stats["capital_sources"] = (
                queries.total_sources().sum()
                if not queries.total_sources().empty
                else 0.0
            )

        return stats

    def __str__(self) -> str:
        """String representation showing key metrics."""
        stats = self.summary_stats()
        return (
            f"AssetAnalysisResult(\n"
            f"  NOI Total: ${stats['noi_total']:,.2f}\n"
            f"  NOI Average: ${stats['noi_average']:,.2f}\n"
            f"  Total Records: {stats['total_records']}\n"
            f"  Analysis Periods: {stats['analysis_periods']}\n"
            f")"
        )
