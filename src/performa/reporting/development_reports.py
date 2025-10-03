# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Development reports.

Transforms ledger-backed analysis results into standard Sources & Uses reporting
with industry terminology.
"""

from datetime import date
from typing import Any, Dict

import pandas as pd

from ..core.ledger import LedgerQueries
from .base import BaseReport


class SourcesAndUsesReport(BaseReport):
    """
    Sources & Uses report for completed analyses.

    Extracts capital uses and funding sources from the ledger to produce a
    standard Sources & Uses summary.
    """

    def generate(self) -> Dict[str, Any]:
        """
        Generate Sources & Uses report from the ledger.

        Returns:
            Dictionary with structured Sources & Uses data.
        """
        # Create queries directly from the Ledger (avoid DataFrame materialization)
        queries = LedgerQueries(self._results.ledger)

        # Extract uses and sources from ledger
        uses_data = queries.capital_uses_by_category()
        sources_data = queries.capital_sources_by_category()

        if uses_data.empty and sources_data.empty:
            raise ValueError("No capital transactions found in ledger")

        # Map ledger subcategories to industry-standard categories
        uses = self._map_uses_to_standard_categories(uses_data)
        sources = self._map_sources_to_standard_categories(sources_data)

        total_uses = sum(uses.values()) if uses else 0.0
        total_sources = sum(sources.values()) if sources else 0.0

        return {
            "project_info": {
                "project_name": self._results.deal_summary.deal_name
                or "Development Project",
                "asset_type": self._results.deal_summary.asset_type,
                "report_date": date.today().strftime("%B %d, %Y"),
            },
            "uses": {
                "Land Acquisition": self._format_currency(
                    uses.get("purchase_price", 0)
                ),
                "Direct Construction Costs": self._format_currency(
                    uses.get("hard_costs", 0)
                ),
                "Indirect/Soft Costs": self._format_currency(uses.get("soft_costs", 0)),
                "Closing Costs": self._format_currency(uses.get("closing_costs", 0)),
                "Due Diligence": self._format_currency(uses.get("due_diligence", 0)),
                "Other Costs": self._format_currency(uses.get("other", 0)),
                "Total Project Cost": self._format_currency(total_uses),
            },
            "sources": {
                "Equity Investment": f"{self._format_currency(sources.get('equity', 0))} ({sources.get('equity', 0) / total_uses:.1%})"
                if total_uses > 0
                else f"{self._format_currency(sources.get('equity', 0))} (0.0%)",
                "Debt Financing": f"{self._format_currency(sources.get('debt', 0))} ({sources.get('debt', 0) / total_uses:.1%})"
                if total_uses > 0
                else f"{self._format_currency(sources.get('debt', 0))} (0.0%)",
                "Other Sources": f"{self._format_currency(sources.get('other', 0))}",
                "Total Sources": self._format_currency(total_sources),
            },
            "key_metrics": {
                "Loan-to-Cost": self._format_percentage(
                    sources.get("debt", 0) / total_uses if total_uses > 0 else 0
                ),
                "Equity Requirement": self._format_percentage(
                    sources.get("equity", 0) / total_uses if total_uses > 0 else 0
                ),
            },
            "validation": {
                "sources_equal_uses": abs(total_sources - total_uses)
                < 1000,  # Within $1,000
                "variance": total_sources - total_uses,
                "funding_gap": total_uses - total_sources,
            },
        }

    def _map_uses_to_standard_categories(
        self, uses_data: pd.Series
    ) -> Dict[str, float]:
        """
        Map ledger subcategories to industry-standard Sources & Uses categories.

        Args:
            uses_data: Series with subcategory as index and amounts as values

        Returns:
            Dictionary with standardized category names and amounts
        """
        # Initialize standard categories
        mapped_uses = {
            "purchase_price": 0.0,
            "hard_costs": 0.0,
            "soft_costs": 0.0,
            "closing_costs": 0.0,
            "due_diligence": 0.0,
            "other": 0.0,
        }

        # Map ledger subcategories to standard categories
        # Using the CapitalSubcategoryEnum values
        for subcategory, amount in uses_data.items():
            if subcategory in ["Purchase Price"]:
                mapped_uses["purchase_price"] += amount
            elif subcategory in ["Hard Costs"]:
                mapped_uses["hard_costs"] += amount
            elif subcategory in ["Soft Costs"]:
                mapped_uses["soft_costs"] += amount
            elif subcategory in ["Closing Costs"]:
                mapped_uses["closing_costs"] += amount
            elif subcategory in ["Due Diligence"]:
                mapped_uses["due_diligence"] += amount
            else:
                mapped_uses["other"] += amount

        return mapped_uses

    def _map_sources_to_standard_categories(
        self, sources_data: pd.Series
    ) -> Dict[str, float]:
        """
        Map ledger subcategories to industry-standard Sources categories.

        Args:
            sources_data: Series with subcategory as index and amounts as values

        Returns:
            Dictionary with standardized category names and amounts
        """
        # Initialize standard categories
        mapped_sources = {
            "equity": 0.0,
            "debt": 0.0,
            "other": 0.0,
        }

        # Map ledger subcategories to standard categories
        # Using the FinancingSubcategoryEnum values
        for subcategory, amount in sources_data.items():
            if subcategory in ["Equity Contribution"]:
                mapped_sources["equity"] += amount
            elif subcategory in ["Loan Proceeds", "Debt"]:
                mapped_sources["debt"] += amount
            else:
                mapped_sources["other"] += amount

        return mapped_sources

    def _format_currency(self, value: float) -> str:
        """Format currency values."""
        return f"${value:,.0f}"

    def _format_percentage(self, value: float) -> str:
        """Format percentage values."""
        return f"{value:.1%}"
