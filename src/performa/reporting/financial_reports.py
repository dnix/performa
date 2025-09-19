# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Universal Financial Reports

Financial reports that work across all deal types, operating exclusively
on final DealResults objects from the analysis engine.
"""

from __future__ import annotations

import warnings
from typing import Dict, Optional

import pandas as pd

from ..core.primitives.timeline import normalize_frequency
from .base import BaseReport


class ProFormaReport(BaseReport):
    """
    Universal pro forma summary report.

    Generates presentation-ready financial summaries from analysis results,
    working across all deal types (office, residential, development, etc.).
    """

    def generate(self, frequency: str = "A") -> pd.DataFrame:
        """
        Generate a presentation-ready pro forma summary.

        Args:
            frequency: Resampling frequency ('A' for annual, 'Q' for quarterly, 'M' for monthly)

        Returns:
            DataFrame where rows are line items and columns are periods
        """
        # --- Asset-level aggregates (from LedgerQueries) ---
        queries = self._results.queries

        # Direct query-based extraction
        pgr = queries.pgr()
        abatement = queries.rental_abatement()
        vacancy = queries.vacancy_loss()
        collection = queries.credit_loss()
        misc_income = queries.misc_income()
        reimburse = queries.expense_reimbursements()
        egi = queries.egi()
        opex = queries.opex()
        noi = queries.noi()

        # --- Financing aggregates ---
        debt_service = queries.debt_service()

        # --- Levered cash flow ---
        lcf = self._results.levered_cash_flow

        # Assemble monthly DataFrame
        lines: Dict[str, Optional[pd.Series]] = {
            "Potential Gross Revenue": pgr,
            "Rental Abatement": abatement,
            "General Vacancy Loss": vacancy,
            "Credit Loss": collection,
            "Miscellaneous Income": misc_income,
            "Expense Reimbursements": reimburse,
            "Effective Gross Income": egi,
            "Total Operating Expenses": opex,
            "Net Operating Income": noi,
            "Debt Service": debt_service,
            "Levered Cash Flow": lcf,
        }

        # Determine a common index
        all_series = [s for s in lines.values() if isinstance(s, pd.Series)]
        if not all_series:
            return pd.DataFrame()

        base_index = all_series[0].index
        monthly = pd.DataFrame(index=base_index)

        for name, s in lines.items():
            if s is not None:
                monthly[name] = s.reindex(base_index, fill_value=0.0)
            else:
                monthly[name] = 0.0

        # Resample to requested frequency
        annual = self._resample_dataframe(monthly, frequency)

        # Transpose so that rows are line items, columns are periods
        return annual.T

    def _resample_dataframe(self, df: pd.DataFrame, frequency: str) -> pd.DataFrame:
        """Resample DataFrame to requested frequency."""
        if df.empty:
            return df

        # Convert user frequency to pandas alias
        pandas_freq = normalize_frequency(frequency)

        # Convert PeriodIndex to Timestamp index for resampling
        if hasattr(df.index, "to_timestamp"):
            idx = df.index.to_timestamp()
        else:
            idx = pd.to_datetime(df.index)
        df_ts = df.copy()
        df_ts.index = idx
        # Suppress pandas period frequency deprecation warnings (Y->YE, Q->QE)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*is deprecated.*", category=FutureWarning)
            return df_ts.resample(pandas_freq).sum()
