# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Reporting Interface

Provides the fluent API for accessing reports from DealResults objects.
This is the primary user-facing interface for the reporting system.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

import pandas as pd

# Import all report classes at the top level
from .assumptions import AssumptionsReport
from .development_reports import SourcesAndUsesReport
from .financial_reports import ProFormaReport
from .pivot_report import PivotTableReport

if TYPE_CHECKING:
    from ..deal.results import DealResults


class ReportingInterface:
    """
    Fluent interface for accessing standardized reports.

    This class is exposed via the `reporting` property on DealResults
    and provides access to various report formatters.

    Example:
        results = analyze(deal, timeline)
        pro_forma_df = results.reporting.pro_forma_summary()
        sources_uses_dict = results.reporting.sources_and_uses()
    """

    def __init__(self, results: "DealResults"):
        """
        Initialize with analysis results.

        Args:
            results: Complete DealResults from performa.deal.analyze()
        """
        self._results = results

    def pro_forma_summary(self, frequency: str = "A") -> pd.DataFrame:
        """
        Generate a presentation-ready pro forma financial summary.

        This is a universal report that works across all deal types
        (office, residential, development, etc.).

        Args:
            frequency: Resampling frequency:
                - 'A' for annual (default)
                - 'Q' for quarterly
                - 'M' for monthly

        Returns:
            DataFrame where rows are line items (revenue, expenses, etc.)
            and columns are time periods

        Example:
            results = analyze(deal, timeline)
            annual_summary = results.reporting.pro_forma_summary()
            quarterly_summary = results.reporting.pro_forma_summary('Q')
        """
        report = ProFormaReport(self._results)
        return report.generate(frequency=frequency)

    def sources_and_uses(self) -> Dict[str, Any]:
        """
        Generate an industry-standard Sources & Uses report.

        This report is specific to development deals and shows the
        breakdown of project costs (uses) and financing sources.

        Returns:
            Dictionary with structured Sources & Uses data

        Raises:
            TypeError: If called on non-development deals

        Example:
            results = analyze(development_deal, timeline)
            if results.deal_summary.is_development:
                sources_uses = results.reporting.sources_and_uses()
        """
        report = SourcesAndUsesReport(self._results)
        return report.generate()

    def assumptions_summary(
        self,
        include_risk_assessment: bool = True,
        include_defaults_detail: bool = False,
        focus_components: Optional[List[str]] = None,
        formatted: bool = True,
    ) -> Union[str, Dict[str, Any]]:
        """
        Generate comprehensive model assumptions documentation.

        Suitable for due diligence, audit trails, and
        configuration analysis requirements. Shows user-specified vs default
        parameters with risk assessment.

        Args:
            include_risk_assessment: Include risk flagging for critical defaults
            include_defaults_detail: Include detailed list of defaulted parameters
            focus_components: Limit to specific components ('asset', 'financing', 'exit', 'partnership')
            formatted: Return formatted text (True) or raw data dict (False)

        Returns:
            Formatted assumptions report or structured data dictionary

        Example:
            ```python
            results = analyze(deal, timeline)

            # Formatted report for presentations
            assumptions_doc = results.reporting.assumptions_summary()
            print(assumptions_doc)

            # Raw data for further processing
            assumptions_data = results.reporting.assumptions_summary(formatted=False)
            quality_score = assumptions_data['quality_assessment']['overall_score']
            ```
        """
        report = AssumptionsReport(self._results)

        if formatted:
            return report.generate_formatted(
                include_risk_assessment=include_risk_assessment,
                include_defaults_detail=include_defaults_detail,
                focus_components=focus_components,
            )
        else:
            return report.generate(
                include_risk_assessment=include_risk_assessment,
                include_defaults_detail=include_defaults_detail,
                focus_components=focus_components,
            )

    def pivot_table(
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

        Transforms the transactional ledger into familiar Excel pro forma format
        with periods as columns and financial line items as rows. This provides
        "Glass Box" transparency by showing every transaction.

        Args:
            frequency: Period frequency ('M' monthly, 'Q' quarterly, 'A' annual)
            include_subtotals: Add subtotal rows for each category
            include_totals_column: Add total column on right
            currency_format: Apply currency formatting to values
            categories: Filter to specific categories (Revenue, Expense, etc.)
            subcategories: Filter to specific subcategories

        Returns:
            DataFrame in Excel pro forma format with periods as columns

        Example:
            ```python
            results = analyze(deal, timeline)

            # Monthly detail for operations teams
            monthly_detail = results.reporting.pivot_table(frequency="M")

            # Quarterly summary for board presentations
            quarterly_summary = results.reporting.pivot_table(
                frequency="Q",
                include_subtotals=True
            )

            # Annual for investment committee
            annual_view = results.reporting.pivot_table(
                frequency="A",
                categories=["Revenue", "Expense"]
            )
            ```
        """
        report = PivotTableReport(self._results)
        return report.generate(
            frequency=frequency,
            include_subtotals=include_subtotals,
            include_totals_column=include_totals_column,
            currency_format=currency_format,
            categories=categories,
            subcategories=subcategories,
        )

    # Additional report methods can be added here as needed
