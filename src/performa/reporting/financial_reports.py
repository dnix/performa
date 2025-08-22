# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Universal Financial Reports

Financial reports that work across all deal types, operating exclusively
on final DealAnalysisResult objects from the analysis engine.
"""

from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

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
        # Map frequency strings to pandas aliases for compatibility
        frequency_mapping = {
            "A": "YE",  # Annual -> Year End
            "Q": "QE",  # Quarterly -> Quarter End
            "M": "ME",  # Monthly -> Month End (though M still works)
        }
        pandas_freq = frequency_mapping.get(frequency, frequency)
        # --- Asset-level aggregates (from elegant LedgerQueries) ---
        if (
            hasattr(self._results, "asset_analysis")
            and self._results.asset_analysis
            and hasattr(self._results.asset_analysis, "get_ledger_queries")
        ):
            # Use elegant LedgerQueries instead of complex summary_df extraction
            queries = self._results.asset_analysis.get_ledger_queries()

            # Direct query-based extraction (replaces complex column mapping)
            pgr = self._safe_series(queries.pgr())
            abatement = self._safe_series(queries.rental_abatement())
            vacancy = self._safe_series(queries.vacancy_loss())
            collection = self._safe_series(queries.credit_loss())
            misc_income = self._safe_series(queries.misc_income())
            reimburse = self._safe_series(queries.expense_reimbursements())
            egi = self._safe_series(queries.egi())
            opex = self._safe_series(queries.opex())
            noi = self._safe_series(queries.noi())

        else:
            raise ValueError(
                "asset_analysis with LedgerQueries is required for pro forma reports"
            )

        # --- Financing aggregates ---
        fin = getattr(self._results, "financing_analysis", None)
        debt_service = (
            self._sum_series_dict(getattr(fin, "debt_service", None)) if fin else None
        )

        # --- Levered cash flow ---
        lcf = self._safe_series(
            getattr(
                getattr(self._results, "levered_cash_flows", None),
                "levered_cash_flows",
                None,
            )
        )

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

    def _safe_series(self, series: Optional[pd.Series]) -> Optional[pd.Series]:
        """Safely validate and return a pandas Series."""
        if series is None:
            return None
        if not isinstance(series, pd.Series):
            return None
        return series

    def _sum_series_dict(
        self, series_dict: Optional[Dict[str, Optional[pd.Series]]]
    ) -> Optional[pd.Series]:
        """Sum multiple series from a dictionary, handling None values gracefully."""
        if not series_dict:
            return None
        total: Optional[pd.Series] = None
        for series in series_dict.values():
            safe_series = self._safe_series(series)
            if safe_series is None:
                continue
            total = (
                safe_series if total is None else total.add(safe_series, fill_value=0.0)
            )
        return total

    def _resample_dataframe(self, df: pd.DataFrame, frequency: str) -> pd.DataFrame:
        """Resample DataFrame to requested frequency."""
        if df.empty:
            return df

        # Map frequency strings to pandas aliases for compatibility
        frequency_mapping = {
            "A": "YE",  # Annual -> Year End
            "Q": "QE",  # Quarterly -> Quarter End
            "M": "ME",  # Monthly -> Month End (though M still works)
        }
        pandas_freq = frequency_mapping.get(frequency, frequency)

        # Convert PeriodIndex to Timestamp index for resampling
        if hasattr(df.index, "to_timestamp"):
            idx = df.index.to_timestamp()
        else:
            idx = pd.to_datetime(df.index)
        df_ts = df.copy()
        df_ts.index = idx
        return df_ts.resample(pandas_freq).sum()
