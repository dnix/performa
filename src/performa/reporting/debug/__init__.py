# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Debug utilities for financial model validation and troubleshooting.

This module provides comprehensive debugging capabilities for Performa objects:
- Object introspection and configuration analysis
- Ledger semantic analysis and validation  
- Configuration intentionality assessment
- Deal comparison and parity validation
- Timeline analysis and mismatch detection
- Flow validation and reasonableness checks

Supports polymorphic object introspection - can debug any Performa component:
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

### Deal Comparison
- `compare_deal_configurations`: Deep configuration diff showing ALL parameter differences
- `compare_deal_timelines`: Timeline mismatch detection and impact assessment
- `validate_deal_parity`: Automated parity validation with configurable tolerances

### Ledger Analysis
- `analyze_ledger_semantically`: Deep ledger inspection for debugging
- `analyze_ledger_shape`: Transaction pattern analysis and structure validation
- `compare_ledger_shapes`: Ledger structure comparison for parity debugging
- `ledger_sanity_check`: Quick validation of common ledger issues
- `format_ledger_analysis`: Readable ledger analysis formatting

### Flow Validation
- `validate_flow_reasonableness`: Industry benchmark validation by deal type
- `validate_aggregate_flows`: Sources & uses balance validation
- `quick_parity_check`: Fast boolean parity check with default tolerances

### Configuration Analysis
- `analyze_configuration_intentionality`: Context-aware quality scoring (pattern vs manual)
- `compare_configuration_intentionality`: Compare configuration quality between objects
- `generate_configuration_report`: Comprehensive configuration documentation
- `create_actionable_config_summary`: Focused insights with actionable items

### Timeline Analysis
- `extract_component_timelines`: Component-by-component timeline extraction
- `format_timeline_comparison`: Human-readable timeline diff formatting

All functions maintain backward compatibility - existing imports continue to work.
"""

# Import all public functions for backward compatibility
from .config_analysis import (
    analyze_configuration_intentionality,
    compare_configuration_intentionality,
    create_actionable_config_summary,
    generate_configuration_report,
)
from .config_diff import (
    compare_deal_configurations,
)
from .flow_validator import (
    validate_aggregate_flows,
    validate_flow_reasonableness,
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
from .ledger_shape import (
    analyze_ledger_shape,
    compare_ledger_shapes,
    format_ledger_shape_comparison,
)
from .parity_validator import (
    format_parity_validation,
    quick_parity_check,
    validate_deal_parity,
)
from .timeline_analysis import (
    compare_deal_timelines,
    extract_component_timelines,
    format_timeline_comparison,
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
    # Advanced debug utilities
    "compare_deal_configurations",
    "compare_deal_timelines", 
    "extract_component_timelines",
    "format_timeline_comparison",
    "analyze_ledger_shape",
    "compare_ledger_shapes", 
    "format_ledger_shape_comparison",
    "validate_deal_parity",
    "quick_parity_check",
    "format_parity_validation",
    "validate_flow_reasonableness",
    "validate_aggregate_flows",
]
