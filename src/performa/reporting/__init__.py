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

from .assumptions import generate_assumptions_report
from .base import BaseReport, ReportTemplate
from .debug import (
    analyze_configuration_intentionality,
    analyze_ledger_semantically,
    compare_configuration_intentionality,
    compare_deal_configs,
    create_actionable_config_summary,
    dump_deal_config,
    dump_performa_object,
    format_config_analysis,
    format_ledger_analysis,
    format_performa_object,
    generate_configuration_report,
    ledger_sanity_check,
)
from .interface import ReportingInterface

__all__ = [
    # Base classes for custom reports
    "BaseReport",
    "ReportTemplate",
    # Fluent interface (exposed via DealAnalysisResult.reporting)
    "ReportingInterface",
    # Model assumptions reporting
    "generate_assumptions_report",
    # Debug utilities
    "analyze_configuration_intentionality",
    "analyze_ledger_semantically",
    "compare_configuration_intentionality",
    "compare_deal_configs",
    "create_actionable_config_summary",
    "dump_deal_config",
    "dump_performa_object",
    "format_config_analysis",
    "format_ledger_analysis",
    "format_performa_object",
    "generate_configuration_report",
    "ledger_sanity_check",
]
