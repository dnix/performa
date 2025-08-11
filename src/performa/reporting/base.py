# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Base reporting classes for industry-standard report generation.

These classes provide the foundation for translating Performa's internal
models into familiar real estate industry formats and terminology.
"""



from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ..deal.results import DealAnalysisResult


class ReportTemplate(BaseModel):
    """
    Template configuration for report generation.

    Allows customization of report formats, terminology, and styling
    without changing the underlying data logic.
    """

    name: str
    template_type: str  # "sources_and_uses", "development_summary", etc.
    version: str = "1.0"

    # Terminology mappings - translate internal names to industry terms
    terminology: Dict[str, str] = Field(default_factory=dict)

    # Formatting options
    currency_format: str = "${:,.0f}"
    percentage_format: str = "{:.1%}"
    date_format: str = "%B %Y"

    # Report sections to include/exclude
    sections: List[str] = Field(default_factory=list)

    # Custom styling/branding
    styling: Dict[str, Any] = Field(default_factory=dict)


class BaseReport(ABC):
    """
    Abstract base class for all report formatters.

    Reports operate on final DealAnalysisResult objects and transform
    them into presentation-ready formats. Reports should only format
    and present data, never perform calculations.
    """

    def __init__(self, results: "DealAnalysisResult"):
        """
        Initialize report with analysis results.

        Args:
            results: Complete DealAnalysisResult from performa.deal.analyze()
        """
        # Import at runtime to avoid circular dependencies
        from ..deal.results import DealAnalysisResult  # noqa: PLC0415

        if not isinstance(results, DealAnalysisResult):
            raise TypeError("BaseReport requires a DealAnalysisResult object")
        self._results = results

    @abstractmethod
    def generate(self, **kwargs) -> Any:
        """
        Generate the formatted report output.

        This method should transform the analysis results into the
        appropriate output format (DataFrame, dict, etc.) without
        performing any financial calculations.
        """
        pass


class IndustryMetrics:
    """
    Utility class for calculating industry-standard development metrics.

    Provides methods to calculate common real estate development ratios
    and returns in familiar terminology.
    """

    @staticmethod
    def calculate_profit_on_cost(stabilized_noi: float, total_cost: float) -> float:
        """Calculate profit on cost (development yield)"""
        if total_cost <= 0:
            return 0.0
        return stabilized_noi / total_cost

    @staticmethod
    def calculate_development_yield(stabilized_noi: float, total_cost: float) -> float:
        """Alias for profit on cost - common industry term"""
        return IndustryMetrics.calculate_profit_on_cost(stabilized_noi, total_cost)

    @staticmethod
    def calculate_ltc_ratio(total_debt: float, total_cost: float) -> float:
        """Calculate loan-to-cost ratio"""
        if total_cost <= 0:
            return 0.0
        return total_debt / total_cost

    @staticmethod
    def calculate_equity_multiple(
        distributions: float, equity_invested: float
    ) -> float:
        """Calculate equity multiple"""
        if equity_invested <= 0:
            return 0.0
        return distributions / equity_invested

    @staticmethod
    def stabilization_metrics(
        current_occupancy: float,
        target_occupancy: float = 0.95,
        current_noi: float = 0.0,
        stabilized_noi: float = 0.0,
    ) -> Dict[str, Any]:
        """Calculate stabilization progress metrics"""
        occupancy_progress = (
            current_occupancy / target_occupancy if target_occupancy > 0 else 0
        )
        noi_progress = current_noi / stabilized_noi if stabilized_noi > 0 else 0

        return {
            "current_occupancy": current_occupancy,
            "target_occupancy": target_occupancy,
            "occupancy_to_stabilization": target_occupancy - current_occupancy,
            "occupancy_progress": occupancy_progress,
            "current_noi": current_noi,
            "stabilized_noi": stabilized_noi,
            "noi_to_stabilization": stabilized_noi - current_noi,
            "noi_progress": noi_progress,
            "is_stabilized": occupancy_progress >= 1.0 and noi_progress >= 0.95,
        }
