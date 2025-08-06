# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Base reporting classes for industry-standard report generation.

These classes provide the foundation for translating Performa's internal
models into familiar real estate industry formats and terminology.
"""

# FIXME: this whole file needs some deep thinking to be sure it hits all the use cases

from abc import ABC, abstractmethod
from datetime import date
from typing import Any, Dict, List, Optional, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


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


class Report(BaseModel, ABC):
    """
    Base class for all industry-standard reports.

    Provides common functionality for data translation, formatting,
    and export while allowing specific report types to customize
    their presentation and terminology.
    """

    # Report metadata
    report_id: UUID = Field(default_factory=uuid4)
    report_type: str
    title: str
    generated_date: date = Field(default_factory=date.today)

    # Source data reference
    source_project_id: Optional[UUID] = None
    as_of_date: Optional[date] = None

    # Template and formatting
    template: Optional[ReportTemplate] = None

    # Project reference (for report classes that need to store the project)
    project: Optional[Any] = None
    period: Optional[Any] = None  # For period-specific reports

    @abstractmethod
    def generate_data(self) -> Dict[str, Any]:
        """
        Generate the report data in industry-standard format.

        This method should transform internal Performa models into
        dictionaries using familiar real estate terminology.
        """
        pass

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary format for export"""
        return {
            "metadata": {
                "report_id": str(self.report_id),
                "report_type": self.report_type,
                "title": self.title,
                "generated_date": self.generated_date.isoformat(),
                "as_of_date": self.as_of_date.isoformat() if self.as_of_date else None,
            },
            "data": self.generate_data(),
        }

    def to_excel_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Format data for Excel export.

        Returns dictionary where keys are sheet names and values are
        lists of row dictionaries suitable for pandas DataFrame creation.
        """
        data = self.generate_data()
        return {"Report": [data]}  # Default single sheet

    def format_currency(self, value: Union[float, int]) -> str:
        """Format currency using template formatting"""
        if self.template and hasattr(self.template, "currency_format"):
            return self.template.currency_format.format(value)
        return f"${value:,.0f}"

    def format_percentage(self, value: float) -> str:
        """Format percentage using template formatting"""
        if self.template and hasattr(self.template, "percentage_format"):
            return self.template.percentage_format.format(value)
        return f"{value:.1%}"

    def translate_term(self, internal_term: str) -> str:
        """
        Translate internal terminology to industry-standard terms.

        Uses template terminology mapping or falls back to defaults.
        """
        if self.template and internal_term in self.template.terminology:
            return self.template.terminology[internal_term]

        # Default terminology mappings
        default_mappings = {
            "capital_plan": "Sources & Uses",
            "construction_plan": "Construction Budget",
            "absorption_plan": "Market Leasing",
            "lease_up_plan": "Space Absorption",
            "disposition_assumptions": "Reversion Analysis",
            "hard_costs": "Direct Construction Costs",
            "soft_costs": "Indirect Costs",
            "ltc_ratio": "Loan-to-Cost",
            "completion_date": "Substantial Completion",
        }

        return default_mappings.get(
            internal_term, internal_term.replace("_", " ").title()
        )


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
