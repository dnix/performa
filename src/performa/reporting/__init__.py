# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Performa Reporting Module

Modern reporting interface using fluent API via DealResults.reporting

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
    # Advanced debug utilities  
    analyze_ledger_shape,
    compare_configuration_intentionality,
    compare_deal_configs,
    compare_deal_configurations,
    compare_deal_timelines,
    compare_ledger_shapes,
    create_actionable_config_summary,
    dump_deal_config,
    dump_performa_object,
    extract_component_timelines,
    format_config_analysis,
    format_ledger_analysis,
    format_ledger_shape_comparison,
    format_parity_validation,
    format_performa_object,
    format_timeline_comparison,
    generate_configuration_report,
    ledger_sanity_check,
    quick_parity_check,
    validate_aggregate_flows,
    validate_deal_parity,
    validate_flow_reasonableness,
)
from .interface import ReportingInterface
from .pivot_report import PivotTableReport

__all__ = [
    # Base classes for custom reports
    "BaseReport",
    "ReportTemplate",
    # Fluent interface (exposed via DealResults.reporting)
    "ReportingInterface",
    # Core reports
    "PivotTableReport",
    # Model assumptions reporting
    "generate_assumptions_report",
    # Debug utilities
    "analyze_configuration_intentionality",
    "analyze_ledger_semantically",
    "analyze_ledger_shape",
    "compare_configuration_intentionality",
    "compare_deal_configs",
    "compare_deal_configurations",
    "compare_deal_timelines",
    "compare_ledger_shapes",
    "create_actionable_config_summary",
    "dump_deal_config",
    "dump_performa_object",
    "extract_component_timelines",
    "format_config_analysis",
    "format_ledger_analysis",
    "format_ledger_shape_comparison",
    "format_parity_validation",
    "format_performa_object",
    "format_timeline_comparison",
    "generate_configuration_report",
    "ledger_sanity_check",
    "quick_parity_check",
    "validate_aggregate_flows",
    "validate_deal_parity",
    "validate_flow_reasonableness",
]
