# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Performa Reporting Module

Industry-facing interface for Performa, translating internal architecture
into familiar real estate terminology and report formats.
"""

# FIXME: this whole file needs some deep thinking to be sure it hits all the use cases and also not just development

from .base import Report, ReportTemplate
from .development import (
    ConstructionDrawReport,
    DevelopmentSummaryReport,
    LeasingStatusReport,
    SourcesAndUsesReport,
)


# Industry-standard report factories
def create_sources_and_uses_report(development_project, template=None):
    """Create industry-standard Sources & Uses report"""
    return SourcesAndUsesReport.from_development_project(development_project, template)


def create_development_summary(development_project, template=None):
    """Create development project summary with industry metrics"""
    return DevelopmentSummaryReport.from_development_project(
        development_project, template
    )


def create_draw_request(development_project, period, template=None):
    """Create monthly construction draw request"""
    return ConstructionDrawReport.from_development_project(
        development_project, period, template
    )


def create_leasing_status_report(development_project, as_of_date, template=None):
    """Create market leasing status report"""
    return LeasingStatusReport.from_development_project(
        development_project, as_of_date, template
    )


__all__ = [
    # Base classes
    "Report",
    "ReportTemplate",
    # Development reports
    "SourcesAndUsesReport",
    "DevelopmentSummaryReport",
    "ConstructionDrawReport",
    "LeasingStatusReport",
    # Factory functions (primary user interface)
    "create_sources_and_uses_report",
    "create_development_summary",
    "create_draw_request",
    "create_leasing_status_report",
]
