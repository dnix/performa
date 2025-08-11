# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Reporting Interface

Provides the fluent API for accessing reports from DealAnalysisResult objects.
This is the primary user-facing interface for the reporting system.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

import pandas as pd

# Import all report classes at the top level
from .development_reports import SourcesAndUsesReport
from .financial_reports import ProFormaReport

if TYPE_CHECKING:
    from ..deal.results import DealAnalysisResult


class ReportingInterface:
    """
    Fluent interface for accessing standardized reports.

    This class is exposed via the `reporting` property on DealAnalysisResult
    and provides access to various report formatters.

    Example:
        results = analyze(deal, timeline)
        pro_forma_df = results.reporting.pro_forma_summary()
        sources_uses_dict = results.reporting.sources_and_uses()
    """

    def __init__(self, results: "DealAnalysisResult"):
        """
        Initialize with analysis results.

        Args:
            results: Complete DealAnalysisResult from performa.deal.analyze()
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

    # Additional report methods can be added here as needed
