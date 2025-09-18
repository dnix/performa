# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Pivot Table Report for Excel-like Financial Statement Views

Transforms ledger data into familiar pivot table format with periods as columns
and financial line items as rows - the standard presentation for institutional
real estate pro formas.
"""

from __future__ import annotations

from typing import List, Optional

import pandas as pd

from ..core.primitives.timeline import normalize_frequency
from .base import BaseReport


class PivotTableReport(BaseReport):
    """
    Excel-style pivot table report for transactional ledger data.

    Transforms the transactional ledger into the familiar Excel pro forma format
    used throughout the real estate industry:
    - Periods (months/quarters/years) as columns
    - Financial line items (revenue, expenses, etc.) as rows
    - Proper subtotals and formatting
    - Compatible with Excel import/export

    This provides the "Glass Box" transparency by showing every transaction
    in a format familiar to real estate professionals.
    """

    def generate(
        self,
        frequency: str = "M",
        include_subtotals: bool = True,
        include_totals_column: bool = True,
        currency_format: bool = True,
        categories: Optional[List[str]] = None,
        subcategories: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        Generate Excel-style pivot table from ledger data.

        Args:
            frequency: Period frequency ('M' monthly, 'Q' quarterly, 'A' annual)
            include_subtotals: Add subtotal rows for each category
            include_totals_column: Add total column on right
            currency_format: Apply currency formatting to values
            categories: Filter to specific categories (Revenue, Expense, etc.)
            subcategories: Filter to specific subcategories

        Returns:
            DataFrame formatted like Excel pro forma with periods as columns

        Example:
            ```python
            results = analyze(deal, timeline)
            monthly_pivot = results.reporting.pivot_table(frequency="M")
            quarterly_pivot = results.reporting.pivot_table(frequency="Q", include_subtotals=True)
            ```
        """
        # Get ledger data
        ledger_df = self._results.ledger_df

        # Prepare and clean data
        cleaned_data = self._prepare_ledger_data(ledger_df, categories, subcategories)

        # Create period aggregation
        pivot_df = self._apply_period_aggregation(cleaned_data, frequency)

        # Add subtotals if requested
        if include_subtotals:
            pivot_df = self._add_subtotals(pivot_df)

        # Add totals column if requested
        if include_totals_column:
            pivot_df = self._add_totals_column(pivot_df)

        # Format for display
        if currency_format:
            pivot_df = self._format_for_display(pivot_df)

        return pivot_df


    def _prepare_ledger_data(
        self,
        ledger_df: pd.DataFrame,
        categories: Optional[List[str]] = None,
        subcategories: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        Clean and prepare ledger data for pivot table transformation.

        Args:
            ledger_df: Raw ledger DataFrame
            categories: Filter to specific categories
            subcategories: Filter to specific subcategories

        Returns:
            Cleaned DataFrame ready for pivot operations
        """
        df = ledger_df.copy()

        # Ensure required columns exist
        required_columns = ["date", "category", "subcategory", "amount"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Ledger missing required columns: {missing_columns}")

        # Convert date column to datetime
        df["date"] = pd.to_datetime(df["date"])

        # Filter by categories if specified
        if categories:
            df = df[df["category"].isin(categories)]

        # Filter by subcategories if specified
        if subcategories:
            df = df[df["subcategory"].isin(subcategories)]

        # Remove any rows with null amounts
        df = df.dropna(subset=["amount"])

        # Convert categorical columns to string for stable pivot operations
        df["category"] = df["category"].astype(str)
        df["subcategory"] = df["subcategory"].astype(str)

        return df

    def _apply_period_aggregation(
        self, df: pd.DataFrame, frequency: str
    ) -> pd.DataFrame:
        """
        Aggregate data by time periods and create pivot table structure.

        Args:
            df: Prepared ledger DataFrame
            frequency: Aggregation frequency ('M', 'Q', 'A')

        Returns:
            Pivot table with periods as columns and line items as rows
        """
        # Convert user frequency to pandas alias
        pandas_freq = normalize_frequency(frequency)

        # Create period grouping
        df["period"] = df["date"].dt.to_period(pandas_freq)

        # Create hierarchical index for categories and subcategories
        df["line_item"] = df["category"] + " → " + df["subcategory"]

        # Aggregate by period and line item
        pivot_df = df.pivot_table(
            index="line_item",
            columns="period",
            values="amount",
            aggfunc="sum",
            fill_value=0.0,
        )

        # Sort periods chronologically
        pivot_df = pivot_df.reindex(sorted(pivot_df.columns), axis=1)

        # Sort line items logically (Revenue first, then Expenses)
        line_items = pivot_df.index.tolist()
        sorted_line_items = self._sort_line_items(line_items)
        pivot_df = pivot_df.reindex(sorted_line_items)

        return pivot_df

    def _sort_line_items(self, line_items: List[str]) -> List[str]:
        """
        Sort line items in logical financial statement order.

        Args:
            line_items: List of category → subcategory line item names

        Returns:
            Sorted list with Revenue first, then Expenses, then other categories
        """
        revenue_items = [item for item in line_items if item.startswith("Revenue")]
        expense_items = [item for item in line_items if item.startswith("Expense")]
        capital_items = [item for item in line_items if item.startswith("Capital")]
        financing_items = [item for item in line_items if item.startswith("Financing")]
        other_items = [
            item
            for item in line_items
            if not any(
                item.startswith(prefix)
                for prefix in ["Revenue", "Expense", "Capital", "Financing"]
            )
        ]

        # Standard financial statement order
        return (
            sorted(revenue_items)
            + sorted(expense_items)
            + sorted(capital_items)
            + sorted(financing_items)
            + sorted(other_items)
        )

    def _add_subtotals(self, pivot_df: pd.DataFrame) -> pd.DataFrame:
        """
        Add subtotal rows for each category.

        Args:
            pivot_df: Pivot table DataFrame

        Returns:
            DataFrame with subtotal rows inserted
        """
        # Extract categories from line items
        categories = {}
        for line_item in pivot_df.index:
            category = line_item.split(" → ")[0]
            if category not in categories:
                categories[category] = []
            categories[category].append(line_item)

        # Build new DataFrame with subtotals
        new_rows = []
        new_index = []

        for category, items in categories.items():
            # Add individual line items
            for item in items:
                new_rows.append(pivot_df.loc[item])
                new_index.append(item)

            # Add subtotal row
            if len(items) > 1:  # Only add subtotal if multiple items
                subtotal_row = pivot_df.loc[items].sum()
                new_rows.append(subtotal_row)
                new_index.append(f"  {category} Subtotal")

        # Create new DataFrame
        result_df = pd.DataFrame(new_rows, index=new_index)
        result_df.columns = pivot_df.columns

        return result_df

    def _add_totals_column(self, pivot_df: pd.DataFrame) -> pd.DataFrame:
        """
        Add totals column showing row sums.

        Args:
            pivot_df: Pivot table DataFrame

        Returns:
            DataFrame with 'Total' column added
        """
        df_with_totals = pivot_df.copy()
        df_with_totals["Total"] = pivot_df.sum(axis=1)
        return df_with_totals

    def _format_for_display(self, pivot_df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply currency formatting and Excel-style presentation.

        Args:
            pivot_df: Raw pivot table DataFrame

        Returns:
            Formatted DataFrame ready for display
        """
        formatted_df = pivot_df.copy()

        # Apply currency formatting to numeric columns
        for col in formatted_df.columns:
            if col != "Total":  # Handle Total separately if needed
                formatted_df[col] = formatted_df[col].apply(self._format_currency)

        # Format Total column if it exists
        if "Total" in formatted_df.columns:
            formatted_df["Total"] = formatted_df["Total"].apply(self._format_currency)

        # Clean up index names for readability
        formatted_df.index = [
            self._clean_line_item_name(idx) for idx in formatted_df.index
        ]

        return formatted_df

    def _format_currency(self, value: float) -> str:
        """Format currency values for display."""
        if pd.isna(value) or value == 0:
            return "$0"
        elif abs(value) >= 1_000_000:
            return f"${value / 1_000_000:.1f}M"
        elif abs(value) >= 1_000:
            return f"${value:,.0f}"
        else:
            return f"${value:.0f}"

    def _clean_line_item_name(self, line_item: str) -> str:
        """Clean line item names for better readability."""
        # Remove category prefix if it's redundant
        if " → " in line_item:
            category, subcategory = line_item.split(" → ", 1)
            # If category and subcategory are very similar, just use subcategory
            if subcategory.lower().replace(" ", "") in category.lower().replace(
                " ", ""
            ):
                return subcategory
            else:
                return subcategory
        else:
            return line_item

    # TODO: add staticmethod for Excel file export and workbook.set_properties()?
    # per https://www.youtube.com/watch?v=InVKYPK73vg
