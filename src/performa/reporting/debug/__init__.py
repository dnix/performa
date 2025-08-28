# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Debug utilities for financial model validation and troubleshooting.

This module provides comprehensive debugging capabilities for Performa objects:
- Object introspection and configuration analysis
- Ledger semantic analysis and validation
- Configuration intentionality assessment

Enhanced with polymorphic object introspection - can debug any Performa component:
- Assets (ResidentialProperty, OfficeDevelopmentProject, etc.)
- Deals (complete Deal objects)
- Primitives (Timeline, GlobalSettings, etc.)
- Patterns (ResidentialDevelopmentPattern, etc.)
- Constructs (FinancingPlan, etc.)

## Public API

### Core Introspection
- `dump_performa_object`: Polymorphic object configuration dumping
- `dump_deal_config`: Comprehensive deal configuration extraction
- `compare_deal_configs`: Side-by-side deal configuration comparison
- `format_performa_object`: Readable object analysis formatting

### Ledger Analysis
- `analyze_ledger_semantically`: Deep ledger inspection for debugging
- `ledger_sanity_check`: Quick validation of common ledger issues
- `format_ledger_analysis`: Readable ledger analysis formatting

### Configuration Analysis
- `analyze_configuration_intentionality`: User vs default parameter analysis
- `compare_configuration_intentionality`: Compare configuration quality between objects
- `generate_configuration_report`: Comprehensive configuration documentation
- `create_actionable_config_summary`: Focused insights with actionable items

All functions maintain backward compatibility - existing imports continue to work.
"""

# Import all public functions for backward compatibility
from .config_analysis import (
    analyze_configuration_intentionality,
    compare_configuration_intentionality,
    create_actionable_config_summary,
    generate_configuration_report,
)
from .introspection import (
    _classify_performa_object,  # Exported for test compatibility
    _extract_asset_config,  # Exported for test compatibility
    _extract_financing_config,  # Exported for test compatibility
    _extract_partnership_config,  # Exported for test compatibility
    _handle_deal_object,  # Exported for test compatibility
    _handle_financing_plan,  # Exported for test compatibility
    _handle_generic_object,  # Exported for test compatibility
    _handle_primitive_object,  # Exported for test compatibility
    _handle_pydantic_object,  # Exported for test compatibility
    compare_deal_configs,
    dump_deal_config,
    dump_performa_object,
    format_config_analysis,
    format_performa_object,
)
from .ledger_analysis import (
    analyze_ledger_semantically,
    format_ledger_analysis,
    ledger_sanity_check,
)

# Re-export everything for backward compatibility
__all__ = [
    # Core introspection
    "dump_performa_object",
    "dump_deal_config",
    "compare_deal_configs",
    "format_performa_object",
    "format_config_analysis",
    "_classify_performa_object",  # For test compatibility
    "_extract_asset_config",  # For test compatibility
    "_extract_financing_config",  # For test compatibility
    "_extract_partnership_config",  # For test compatibility
    "_handle_deal_object",  # For test compatibility
    "_handle_financing_plan",  # For test compatibility
    "_handle_generic_object",  # For test compatibility
    "_handle_pydantic_object",  # For test compatibility
    "_handle_primitive_object",  # For test compatibility
    # Ledger analysis
    "analyze_ledger_semantically",
    "ledger_sanity_check",
    "format_ledger_analysis",
    # Configuration analysis
    "analyze_configuration_intentionality",
    "compare_configuration_intentionality",
    "generate_configuration_report",
    "create_actionable_config_summary",
]
