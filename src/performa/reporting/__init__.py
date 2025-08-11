# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Performa Reporting Module

Modern reporting interface using fluent API via DealAnalysisResult.reporting

The primary interface is the fluent API:
    results = analyze(deal, timeline)
    pro_forma = results.reporting.pro_forma_summary()
    sources_uses = results.reporting.sources_and_uses()  # for development deals

This module also exports base classes for custom report development.
"""

from .base import BaseReport, ReportTemplate
from .interface import ReportingInterface

__all__ = [
    # Base classes for custom reports
    "BaseReport",
    "ReportTemplate",
    # Fluent interface (exposed via DealAnalysisResult.reporting)
    "ReportingInterface",
]
