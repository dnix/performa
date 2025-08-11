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

from ..core.primitives import UnleveredAggregateLineKey
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
        # --- Unlevered aggregates (from asset-level summary) ---
        ua = getattr(self._results.unlevered_analysis, "cash_flows", None)
        if ua is None:
            ua = pd.DataFrame()

        def col(key: UnleveredAggregateLineKey) -> Optional[pd.Series]:
            return (
                ua[key.value]
                if (isinstance(ua, pd.DataFrame) and key.value in ua.columns)
                else None
            )

        # Extract core revenue/expense series
        pgr = self._safe_series(col(UnleveredAggregateLineKey.POTENTIAL_GROSS_REVENUE))
        abatement = self._safe_series(col(UnleveredAggregateLineKey.RENTAL_ABATEMENT))
        vacancy = self._safe_series(col(UnleveredAggregateLineKey.GENERAL_VACANCY_LOSS))
        collection = self._safe_series(col(UnleveredAggregateLineKey.COLLECTION_LOSS))
        misc_income = self._safe_series(
            col(UnleveredAggregateLineKey.MISCELLANEOUS_INCOME)
        )
        reimburse = self._safe_series(
            col(UnleveredAggregateLineKey.EXPENSE_REIMBURSEMENTS)
        )
        opex = self._safe_series(
            col(UnleveredAggregateLineKey.TOTAL_OPERATING_EXPENSES)
        )
        noi = self._safe_series(col(UnleveredAggregateLineKey.NET_OPERATING_INCOME))

        # Compute EGI if needed
        egi = self._safe_series(col(UnleveredAggregateLineKey.EFFECTIVE_GROSS_INCOME))
        if egi is None and pgr is not None:
            egi = pgr.copy()
            if abatement is not None:
                egi = egi.sub(abatement, fill_value=0.0)
            if vacancy is not None:
                egi = egi.sub(vacancy, fill_value=0.0)
            if collection is not None:
                egi = egi.sub(collection, fill_value=0.0)
            if misc_income is not None:
                egi = egi.add(misc_income, fill_value=0.0)
            if reimburse is not None:
                egi = egi.add(reimburse, fill_value=0.0)

        # Compute NOI if needed
        if noi is None and egi is not None and opex is not None:
            noi = egi.sub(opex, fill_value=0.0)

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
            "Collection Loss": collection,
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
