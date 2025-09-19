# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Object introspection and configuration analysis for Performa debugging.

This module provides polymorphic object dumping and classification capabilities
for any Performa object type, with specialized handling for different domains:
- Deal objects (full component analysis)
- Asset objects (property and project introspection)
- Pattern objects (high-level interface analysis)
- Primitive objects (Timeline, GlobalSettings, etc.)
- Debt objects (FinancingPlan, facilities, etc.)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

import pandas as pd
from pydantic import BaseModel

from ...core.primitives import GlobalSettings, Timeline
from ...debt.plan import FinancingPlan

if TYPE_CHECKING:
    from ...deal import Deal


def dump_deal_config(
    deal: Deal,
    exclude_defaults: bool = True,
    exclude_unset: bool = False,
    include_computed: bool = False,
) -> Dict[str, Any]:
    """
    Extract complete configuration from Deal and all components.

    Provides visibility into all Pydantic model parameters to spot
    unrealistic assumptions and configuration drift.

    Args:
        deal: Deal object to analyze
        exclude_defaults: Only show parameters that differ from defaults
        exclude_unset: Only show parameters explicitly set by user
        include_computed: Include computed/derived properties

    Returns:
        Nested dictionary of configuration parameters organized by component

    Example:
        ```python
        config = dump_deal_config(deal, exclude_defaults=True)
        print(f"Asset rent: ${config['asset']['target_rent_psf']}/SF")
        print(f"Exit cap: {config['exit']['cap_rate']:.1%}")
        ```
    """
    config = {}

    # Deal-level configuration with class info
    config["deal"] = {"_class_name": type(deal).__name__, "_object_type": "Deal"}
    deal_config = deal.model_dump(
        exclude_defaults=exclude_defaults,
        exclude_unset=exclude_unset,
        exclude={
            "asset",
            "financing",
            "equity_partners",
            "exit_valuation",
        },  # Handle separately
    )
    config["deal"].update(deal_config)

    # Asset configuration
    if deal.asset:
        config["asset"] = _extract_asset_config(
            deal.asset, exclude_defaults, exclude_unset, include_computed
        )

    # Acquisition configuration
    if deal.acquisition:
        config["acquisition"] = {
            "_class_name": type(deal.acquisition).__name__,
            "_object_type": _classify_performa_object(deal.acquisition),
        }
        acquisition_config = deal.acquisition.model_dump(
            exclude_defaults=exclude_defaults, exclude_unset=exclude_unset
        )
        config["acquisition"].update(acquisition_config)

    # Financing configuration
    if deal.financing:
        config["financing"] = _extract_financing_config(
            deal.financing, exclude_defaults, exclude_unset
        )

    # Partnership configuration
    if deal.equity_partners:
        config["partnership"] = _extract_partnership_config(
            deal.equity_partners, exclude_defaults, exclude_unset
        )

    # Exit configuration
    if deal.exit_valuation:
        config["exit"] = {
            "_class_name": type(deal.exit_valuation).__name__,
            "_object_type": _classify_performa_object(deal.exit_valuation),
        }
        exit_config = deal.exit_valuation.model_dump(
            exclude_defaults=exclude_defaults, exclude_unset=exclude_unset
        )
        config["exit"].update(exit_config)

    return config


def dump_performa_object(
    obj: Any,
    exclude_defaults: bool = True,
    exclude_unset: bool = False,
    include_computed: bool = False,
    include_class_info: bool = True,
) -> Dict[str, Any]:
    """
    Polymorphic debug utility for any Performa object.

    Handles all Performa object types with appropriate introspection:
    - Deal objects (full deal analysis)
    - Asset objects (property, development project, etc.)
    - Primitive objects (Timeline, GlobalSettings, etc.)
    - Pattern objects (ResidentialDevelopmentPattern, etc.)
    - Construct results (FinancingPlan, etc.)

    Args:
        obj: Any Performa object to analyze
        exclude_defaults: Only show parameters that differ from defaults
        exclude_unset: Only show parameters explicitly set by user
        include_computed: Include computed/derived properties
        include_class_info: Include class name and type information

    Returns:
        Dictionary with object configuration and metadata

    Example:
        ```python
        # Debug any object type
        config = dump_performa_object(timeline)
        config = dump_performa_object(residential_pattern)
        config = dump_performa_object(financing_plan)
        config = dump_performa_object(deal)
        ```
    """
    result = {}

    # Add class information
    if include_class_info:
        result["_object_info"] = {
            "class_name": type(obj).__name__,
            "module": type(obj).__module__,
            "object_type": _classify_performa_object(obj),
        }

    # Dispatch to appropriate handler based on object type
    # NOTE: Order matters! More specific checks must come before generic ones
    if type(obj).__name__ == "Deal":
        result["config"] = _handle_deal_object(
            obj, exclude_defaults, exclude_unset, include_computed
        )

    elif isinstance(obj, FinancingPlan):
        # Handle FinancingPlan before generic Pydantic check
        result["config"] = _handle_financing_plan(obj, exclude_defaults, exclude_unset)

    elif isinstance(obj, (Timeline, GlobalSettings)):
        result["config"] = _handle_primitive_object(
            obj, exclude_defaults, exclude_unset
        )

    elif hasattr(obj, "model_dump") and callable(obj.model_dump):
        # Generic Pydantic model (assets, patterns, etc.) - must come after specific checks
        result["config"] = _handle_pydantic_object(
            obj, exclude_defaults, exclude_unset, include_computed
        )

    else:
        # Fallback: try to extract what we can
        result["config"] = _handle_generic_object(obj, exclude_defaults, exclude_unset)

    return result


def _classify_performa_object(obj: Any) -> str:
    """
    Classify Performa object type for appropriate debugging strategy.

    This classification system enables the debug utility to apply the most
    appropriate introspection method for each object category.

    Args:
        obj: Any object to classify

    Returns:
        str: Object classification for debugging strategy

    Classification Categories:
        - Deal: Complete deal objects requiring full component analysis
        - Pattern: High-level pattern interfaces (ResidentialDevelopmentPattern, etc.)
        - Asset: Property and project objects (ResidentialProperty, DevelopmentProject, etc.)
        - Primitive: Core system objects (Timeline, GlobalSettings, etc.)
        - Debt: Financing objects (FinancingPlan, PermanentFacility, etc.)
        - Valuation: Exit valuation models (DirectCapValuation, etc.)
        - Partnership: Equity structure objects (PartnershipStructure, etc.)
        - Unknown: Fallback for unrecognized objects

    Example:
        ```python
        obj_type = _classify_performa_object(residential_pattern)
        # Returns: "Pattern"

        obj_type = _classify_performa_object(timeline)
        # Returns: "Primitive"
        ```
    """
    obj_type = type(obj).__name__

    # Deal objects: Complete deal structures requiring comprehensive analysis
    if (
        obj_type == "Deal"
        or "Deal" in obj_type
        or any("Deal" in base.__name__ for base in type(obj).__mro__)
    ):
        return "Deal"

    # Pattern objects: High-level interfaces for rapid deal creation
    if "Pattern" in obj_type:
        return "Pattern"

    # Asset objects: Properties and development projects
    if any(
        asset_indicator in obj_type
        for asset_indicator in ["Property", "Project", "Blueprint"]
    ):
        return "Asset"

    # Primitive objects: Core system components
    if any(primitive in obj_type for primitive in ["Timeline", "Settings", "Context"]):
        return "Primitive"

    # Debt objects: Financing facilities and plans
    if any(
        debt_indicator in obj_type for debt_indicator in ["Facility", "Plan", "Tranche"]
    ):
        return "Debt"

    # Valuation objects: Exit valuation models
    if "Valuation" in obj_type:
        return "Valuation"

    # Partnership objects: Equity structure and waterfall models
    if any(
        partnership_indicator in obj_type
        for partnership_indicator in ["Partnership", "Partner"]
    ):
        return "Partnership"

    # Fallback for unrecognized objects
    return "Unknown"


def _handle_deal_object(
    deal: Deal, exclude_defaults: bool, exclude_unset: bool, include_computed: bool
) -> Dict[str, Any]:
    """
    Handle Deal objects using comprehensive component analysis.

    Deal objects require special handling because they contain multiple
    complex components (asset, financing, partnership, etc.) that need
    individual introspection and class identification.

    Args:
        deal: Deal object to analyze
        exclude_defaults: Filter out default parameter values
        exclude_unset: Filter out unset parameter values
        include_computed: Include computed/derived properties

    Returns:
        Dict containing complete deal configuration with component class info
    """
    return dump_deal_config(deal, exclude_defaults, exclude_unset, include_computed)


def _handle_pydantic_object(
    obj: BaseModel, exclude_defaults: bool, exclude_unset: bool, include_computed: bool
) -> Dict[str, Any]:
    """
    Handle generic Pydantic model objects (patterns, assets, etc.).

    This handler works with any Pydantic-based Performa object and provides
    standardized configuration extraction plus computed properties for
    objects that support them (patterns, assets, etc.).

    Args:
        obj: Pydantic BaseModel object to analyze
        exclude_defaults: Filter out default parameter values
        exclude_unset: Filter out unset parameter values
        include_computed: Include computed/derived properties

    Returns:
        Dict containing object configuration and optional computed properties

    Supported Computed Properties:
        - total_project_cost: For objects with cost calculations
        - net_rentable_area: For property objects with area calculations
        - total_units: For residential objects with unit calculations
        - derived_timeline: For pattern objects with timeline derivation
    """
    try:
        config = obj.model_dump(
            exclude_defaults=exclude_defaults, exclude_unset=exclude_unset
        )
    except (ValueError, TypeError) as e:
        if "ambiguous" in str(e) or "Series" in str(e):
            # Handle pandas Series edge case by using mode='python' for safer serialization
            try:
                config = obj.model_dump(
                    exclude_defaults=exclude_defaults,
                    exclude_unset=exclude_unset,
                    mode="python",
                )
            except Exception:
                # Final fallback: dump only simple fields
                config = {
                    field_name: getattr(obj, field_name)
                    for field_name in obj.model_fields.keys()
                    if hasattr(obj, field_name)
                    and not isinstance(
                        getattr(obj, field_name), (pd.Series, pd.DataFrame)
                    )
                }
        else:
            raise

    # Add computed properties for specific object types
    if include_computed:
        computed = {}

        # Asset objects
        if hasattr(obj, "total_project_cost"):
            computed["total_project_cost"] = obj.total_project_cost
        if hasattr(obj, "net_rentable_area"):
            computed["net_rentable_area"] = obj.net_rentable_area
        if hasattr(obj, "total_units"):
            computed["total_units"] = obj.total_units

        # Pattern objects
        if hasattr(obj, "_derive_timeline"):
            try:
                timeline = obj._derive_timeline()
                computed["derived_timeline"] = {
                    "duration_months": timeline.duration_months,
                    "start_date": str(timeline.start_date),
                }
            except:
                pass

        if computed:
            config["_computed"] = computed

    return config


def _handle_financing_plan(
    plan: FinancingPlan, exclude_defaults: bool, exclude_unset: bool
) -> Dict[str, Any]:
    """
    Handle FinancingPlan objects with facility class identification.

    FinancingPlan objects contain multiple debt facilities that need individual
    class identification for proper debugging and cash-out refinancing analysis.

    Args:
        plan: FinancingPlan object to analyze
        exclude_defaults: Filter out default parameter values
        exclude_unset: Filter out unset parameter values

    Returns:
        Dict containing plan configuration with facility class information

    Example Output Structure:
        ```python
        {
            "_class_name": "FinancingPlan",
            "_object_type": "Debt",
            "name": "Construction-to-Permanent",
            "facilities": [
                {
                    "_class_name": "ConstructionFacility",
                    "_object_type": "Debt",
                    "name": "Construction Loan",
                    "loan_amount": 15000000,
                    # ... other config
                },
                {
                    "_class_name": "PermanentFacility",
                    "_object_type": "Debt",
                    "name": "Permanent Loan",
                    "loan_amount": 18000000,
                    # ... other config
                }
            ]
        }
        ```
    """
    return _extract_financing_config(plan, exclude_defaults, exclude_unset)


def _handle_primitive_object(
    obj: Any, exclude_defaults: bool, exclude_unset: bool
) -> Dict[str, Any]:
    """
    Handle primitive Performa objects (Timeline, GlobalSettings, etc.).

    Primitive objects are core system components that provide foundational
    functionality. They may or may not be Pydantic models.

    Args:
        obj: Primitive object to analyze (Timeline, GlobalSettings, etc.)
        exclude_defaults: Filter out default parameter values
        exclude_unset: Filter out unset parameter values

    Returns:
        Dict containing primitive object configuration

    Supported Primitives:
        - Timeline: Project timeline with dates and duration
        - GlobalSettings: System-wide configuration settings
        - AnalysisContext: Analysis execution context (future)
        - Other core system objects
    """
    if hasattr(obj, "model_dump"):
        return obj.model_dump(
            exclude_defaults=exclude_defaults, exclude_unset=exclude_unset
        )
    else:
        # For non-Pydantic primitives, extract what we can
        return {
            attr: getattr(obj, attr)
            for attr in dir(obj)
            if not attr.startswith("_") and not callable(getattr(obj, attr))
        }


def _handle_generic_object(
    obj: Any, exclude_defaults: bool, exclude_unset: bool
) -> Dict[str, Any]:
    """
    Fallback handler for unknown or non-Performa object types.

    This handler attempts to extract useful information from any object
    type that doesn't fit into the standard Performa categories. It tries
    multiple extraction strategies to provide useful debugging information.

    Args:
        obj: Unknown object to analyze
        exclude_defaults: Filter out default parameter values (if applicable)
        exclude_unset: Filter out unset parameter values (if applicable)

    Returns:
        Dict containing extracted object information with fallback note

    Extraction Strategy:
        1. Try Pydantic model_dump() if available
        2. Fall back to basic attribute extraction for simple types
        3. Include diagnostic note about handler used

    Example Output:
        ```python
        {
            "_note": "Generic handler for CustomClass",
            "some_attr": "value",
            "numeric_attr": 42
        }
        ```
    """
    config = {"_note": f"Generic handler for {type(obj).__name__}"}

    # Try Pydantic model_dump first
    if hasattr(obj, "model_dump"):
        try:
            config.update(
                obj.model_dump(
                    exclude_defaults=exclude_defaults, exclude_unset=exclude_unset
                )
            )
        except:
            pass

    # Fallback to basic attribute extraction
    if len(config) == 1:  # Only has the _note
        for attr in dir(obj):
            if not attr.startswith("_") and not callable(getattr(obj, attr)):
                try:
                    value = getattr(obj, attr)
                    # Only include simple types
                    if isinstance(value, (str, int, float, bool, type(None))):
                        config[attr] = value
                except:
                    pass

    return config


def _extract_asset_config(
    asset, exclude_defaults: bool, exclude_unset: bool, include_computed: bool
) -> Dict[str, Any]:
    """Extract configuration from asset and its components."""
    config = {
        "_class_name": type(asset).__name__,
        "_object_type": _classify_performa_object(asset),
    }

    asset_config = asset.model_dump(
        exclude_defaults=exclude_defaults,
        exclude_unset=exclude_unset,
        exclude={"capital_plans", "absorption_plans", "unit_mix", "expenses", "losses"},
    )
    config.update(asset_config)

    # Add computed properties if requested
    if include_computed:
        computed = {}
        if hasattr(asset, "total_project_cost"):
            computed["total_project_cost"] = asset.total_project_cost
        if hasattr(asset, "construction_plan") and asset.construction_plan:
            computed["total_construction_cost"] = asset.construction_plan.total_cost
        config["_computed"] = computed

    # Capital plans
    if hasattr(asset, "capital_plans") and asset.capital_plans:
        config["capital_plans"] = []
        for plan in asset.capital_plans:
            plan_config = plan.model_dump(
                exclude_defaults=exclude_defaults, exclude_unset=exclude_unset
            )
            config["capital_plans"].append(plan_config)

    # Construction plan (for development assets)
    if hasattr(asset, "construction_plan") and asset.construction_plan:
        config["construction_plan"] = asset.construction_plan.model_dump(
            exclude_defaults=exclude_defaults, exclude_unset=exclude_unset
        )

    # Absorption plans
    if hasattr(asset, "absorption_plans") and asset.absorption_plans:
        config["absorption_plans"] = []
        for plan in asset.absorption_plans:
            plan_config = plan.model_dump(
                exclude_defaults=exclude_defaults, exclude_unset=exclude_unset
            )
            config["absorption_plans"].append(plan_config)

    # Operating assumptions (expenses, losses)
    if hasattr(asset, "expenses") and asset.expenses:
        config["expenses"] = asset.expenses.model_dump(
            exclude_defaults=exclude_defaults, exclude_unset=exclude_unset
        )

    if hasattr(asset, "losses") and asset.losses:
        config["losses"] = asset.losses.model_dump(
            exclude_defaults=exclude_defaults, exclude_unset=exclude_unset
        )

    return config


def _extract_financing_config(
    financing, exclude_defaults: bool, exclude_unset: bool
) -> Dict[str, Any]:
    """Extract financing configuration including all facilities."""
    config = {
        "_class_name": type(financing).__name__,
        "_object_type": _classify_performa_object(financing),
    }

    financing_config = financing.model_dump(
        exclude_defaults=exclude_defaults,
        exclude_unset=exclude_unset,
        exclude={"facilities"},
    )
    config.update(financing_config)

    # Facilities
    config["facilities"] = []
    for facility in financing.facilities:
        facility_config = facility.model_dump(
            exclude_defaults=exclude_defaults, exclude_unset=exclude_unset
        )

        # Add facility class information
        facility_config["_class_name"] = type(facility).__name__
        facility_config["_object_type"] = _classify_performa_object(facility)

        config["facilities"].append(facility_config)

    return config


def _extract_partnership_config(
    partnership, exclude_defaults: bool, exclude_unset: bool
) -> Dict[str, Any]:
    """Extract partnership configuration including partners and promotes."""
    config = {
        "_class_name": type(partnership).__name__,
        "_object_type": _classify_performa_object(partnership),
    }

    partnership_config = partnership.model_dump(
        exclude_defaults=exclude_defaults, exclude_unset=exclude_unset
    )
    config.update(partnership_config)

    return config


def compare_deal_configs(
    deal1: Deal, deal2: Deal, name1: str = "Deal 1", name2: str = "Deal 2"
) -> Dict[str, Any]:
    """
    Compare configurations between two deals to spot differences.

    Args:
        deal1: First deal to compare
        deal2: Second deal to compare
        name1: Label for first deal
        name2: Label for second deal

    Returns:
        Dictionary showing parameter differences between deals
    """
    config1 = dump_deal_config(deal1, exclude_defaults=True)
    config2 = dump_deal_config(deal2, exclude_defaults=True)

    differences = {}

    # Compare each section
    for section in config1.keys():
        if section in config2:
            section_diffs = _compare_dict_values(
                config1[section],
                config2[section],
                f"{name1}.{section}",
                f"{name2}.{section}",
            )
            if section_diffs:
                differences[section] = section_diffs
        else:
            differences[section] = {f"missing_in_{name2}": config1[section]}

    # Check for sections only in deal2
    for section in config2.keys():
        if section not in config1:
            differences[section] = {f"missing_in_{name1}": config2[section]}

    return differences


def _compare_dict_values(
    dict1: Dict, dict2: Dict, path1: str, path2: str
) -> Dict[str, Any]:
    """Recursively compare dictionary values and return differences."""
    differences = {}

    all_keys = set(dict1.keys()) | set(dict2.keys())

    for key in all_keys:
        if key not in dict1:
            differences[key] = {path2: dict2[key], path1: "<MISSING>"}
        elif key not in dict2:
            differences[key] = {path1: dict1[key], path2: "<MISSING>"}
        elif dict1[key] != dict2[key]:
            if isinstance(dict1[key], dict) and isinstance(dict2[key], dict):
                # Recursive comparison for nested dicts
                nested_diffs = _compare_dict_values(
                    dict1[key], dict2[key], f"{path1}.{key}", f"{path2}.{key}"
                )
                if nested_diffs:
                    differences[key] = nested_diffs
            else:
                differences[key] = {path1: dict1[key], path2: dict2[key]}

    return differences


def format_config_analysis(
    config: Dict[str, Any], title: str = "Deal Configuration"
) -> str:
    """
    Format configuration analysis as readable text.

    Args:
        config: Configuration dictionary from dump_deal_config()
        title: Title for the analysis output

    Returns:
        Formatted string suitable for printing or logging
    """
    output = [f"# {title}\n"]

    # Deal-level info
    if "deal" in config:
        output.append("## Deal Overview")
        deal_info = config["deal"]
        if "name" in deal_info:
            output.append(f"- **Name**: {deal_info['name']}")
        if "description" in deal_info:
            output.append(f"- **Description**: {deal_info['description']}")
        output.append("")

    # Asset configuration
    if "asset" in config:
        output.append("## Asset Configuration")
        asset = config["asset"]

        # Basic property info
        if "net_rentable_area" in asset:
            output.append(
                f"- **Net Rentable Area**: {asset['net_rentable_area']:,.0f} SF"
            )
        if "property_type" in asset:
            output.append(f"- **Property Type**: {asset['property_type']}")

        # Construction costs (for development)
        if "_computed" in asset:
            computed = asset["_computed"]
            if "total_project_cost" in computed:
                output.append(
                    f"- **Total Project Cost**: ${computed['total_project_cost']:,.0f}"
                )
            if "total_construction_cost" in computed:
                output.append(
                    f"- **Construction Cost**: ${computed['total_construction_cost']:,.0f}"
                )

        output.append("")

    # Financing configuration
    if "financing" in config:
        output.append("## Financing Configuration")
        financing = config["financing"]

        if "facilities" in financing:
            for i, facility in enumerate(financing["facilities"]):
                facility_type = facility.get("_facility_type", "Facility")
                output.append(f"### {facility_type} {i + 1}")

                if "loan_amount" in facility:
                    output.append(f"- **Loan Amount**: ${facility['loan_amount']:,.0f}")
                if "interest_rate" in facility:
                    rate = facility["interest_rate"]
                    if isinstance(rate, dict):
                        # Handle complex rate structures
                        if "details" in rate and "rate" in rate["details"]:
                            output.append(
                                f"- **Interest Rate**: {rate['details']['rate']:.2%}"
                            )
                    else:
                        output.append(f"- **Interest Rate**: {rate:.2%}")
                if "ltv_ratio" in facility:
                    output.append(f"- **LTV Ratio**: {facility['ltv_ratio']:.1%}")
                if "loan_term_years" in facility:
                    output.append(
                        f"- **Loan Term**: {facility['loan_term_years']} years"
                    )

        output.append("")

    # Exit configuration
    if "exit" in config:
        output.append("## Exit Configuration")
        exit_config = config["exit"]

        if "cap_rate" in exit_config:
            output.append(f"- **Exit Cap Rate**: {exit_config['cap_rate']:.2%}")
        if "hold_period_months" in exit_config:
            output.append(
                f"- **Hold Period**: {exit_config['hold_period_months']} months"
            )
        if "transaction_costs_rate" in exit_config:
            output.append(
                f"- **Transaction Costs**: {exit_config['transaction_costs_rate']:.1%}"
            )

        output.append("")

    return "\n".join(output)


def format_performa_object(obj: Any, title: Optional[str] = None) -> str:
    """
    Format any Performa object analysis as readable text.

    Args:
        obj: Any Performa object to analyze and format
        title: Optional title for the output

    Returns:
        Formatted string showing object class info and key parameters

    Example:
        ```python
        print(format_performa_object(residential_pattern))
        print(format_performa_object(timeline, "Project Timeline"))
        ```
    """
    analysis = dump_performa_object(obj, exclude_defaults=True, include_computed=True)

    # Generate title
    if title is None:
        class_name = analysis["_object_info"]["class_name"]
        object_type = analysis["_object_info"]["object_type"]
        title = f"{class_name} ({object_type})"

    output = [f"# {title}\n"]

    # Object metadata
    obj_info = analysis["_object_info"]
    output.append("## Object Information")
    output.append(f"- **Class**: `{obj_info['class_name']}`")
    output.append(f"- **Type**: {obj_info['object_type']}")
    output.append(f"- **Module**: `{obj_info['module']}`")
    output.append("")

    # Configuration summary
    config = analysis["config"]
    output.append("## Configuration")

    # Handle different object types appropriately
    if obj_info["object_type"] == "Pattern":
        _format_pattern_config(config, output)
    elif obj_info["object_type"] == "Asset":
        _format_asset_config(config, output)
    elif obj_info["object_type"] == "Debt":
        _format_debt_config(config, output)
    elif obj_info["object_type"] == "Primitive":
        _format_primitive_config(config, output)
    else:
        _format_generic_config(config, output)

    return "\n".join(output)


def _format_pattern_config(config: Dict[str, Any], output: List[str]) -> None:
    """
    Format pattern object configuration for readable output.

    Pattern objects (ResidentialDevelopmentPattern, OfficeDevelopmentPattern, etc.)
    have specific high-level parameters that are most relevant for debugging.
    This formatter extracts and displays the key pattern parameters in a
    structured, human-readable format.

    Args:
        config: Pattern configuration dictionary from dump_performa_object
        output: List to append formatted lines to (modified in-place)

    Key Parameters Displayed:
        - project_name: Deal/project identifier
        - total_units: Unit count (for residential patterns)
        - net_rentable_area: Area in SF (for office patterns)
        - land_cost: Land acquisition cost
        - Computed properties: total_project_cost, derived_timeline
    """
    # Key pattern parameters
    if "project_name" in config:
        output.append(f"- **Project**: {config['project_name']}")
    if "total_units" in config:
        output.append(f"- **Units**: {config['total_units']:,}")
    if "net_rentable_area" in config:
        output.append(f"- **Area**: {config['net_rentable_area']:,} SF")
    if "land_cost" in config:
        output.append(f"- **Land Cost**: ${config['land_cost']:,}")

    # Computed properties
    if "_computed" in config:
        computed = config["_computed"]
        if "total_project_cost" in computed:
            output.append(
                f"- **Total Project Cost**: ${computed['total_project_cost']:,}"
            )
        if "derived_timeline" in computed:
            timeline = computed["derived_timeline"]
            output.append(f"- **Timeline**: {timeline['duration_months']} months")


def _format_asset_config(config: Dict[str, Any], output: List[str]) -> None:
    """
    Format asset object configuration for readable output.

    Asset objects (ResidentialProperty, DevelopmentProject, etc.) have
    property-specific parameters that are crucial for understanding the
    underlying real estate asset being modeled.

    Args:
        config: Asset configuration dictionary from dump_performa_object
        output: List to append formatted lines to (modified in-place)

    Key Parameters Displayed:
        - net_rentable_area: Leasable area in square feet
        - property_type: Asset type (RESIDENTIAL, OFFICE, etc.)
        - Computed properties: total_project_cost (for development assets)
    """
    # Asset basics
    if "net_rentable_area" in config:
        output.append(f"- **Net Rentable Area**: {config['net_rentable_area']:,} SF")
    if "property_type" in config:
        output.append(f"- **Property Type**: {config['property_type']}")

    # Computed properties
    if "_computed" in config:
        computed = config["_computed"]
        if "total_project_cost" in computed:
            output.append(
                f"- **Total Project Cost**: ${computed['total_project_cost']:,}"
            )


def _format_debt_config(config: Dict[str, Any], output: List[str]) -> None:
    """
    Format debt object configuration for readable output.

    Debt objects (FinancingPlan, ConstructionFacility, PermanentFacility, etc.)
    have financing-specific parameters that are essential for understanding
    deal leverage, cash-out refinancing potential, and debt service coverage.

    Args:
        config: Debt configuration dictionary from dump_performa_object
        output: List to append formatted lines to (modified in-place)

    Key Parameters Displayed:
        - name: Financing plan or facility name
        - facilities: Individual debt facilities with class identification
        - loan_amount: Principal amount for each facility
        - interest_rate: Borrowing cost for each facility

    Special Focus:
        - Class identification for each facility (critical for cash-out analysis)
        - Loan amounts for construction vs permanent (enables cash-out calculation)
    """
    if "name" in config:
        output.append(f"- **Name**: {config['name']}")

    # Facilities
    if "facilities" in config:
        facilities = config["facilities"]
        output.append(f"- **Facilities**: {len(facilities)} facilities")
        output.append("")
        output.append("### Facilities")

        for i, facility in enumerate(facilities):
            facility_class = facility.get("_class_name", "Unknown")
            facility_name = facility.get("name", "Unnamed")
            output.append(f"#### {i + 1}. {facility_class}")
            output.append(f"- **Name**: {facility_name}")

            if "loan_amount" in facility:
                output.append(f"- **Loan Amount**: ${facility['loan_amount']:,}")
            if "interest_rate" in facility:
                rate = facility["interest_rate"]
                if isinstance(rate, (int, float)):
                    output.append(f"- **Interest Rate**: {rate:.2%}")
            output.append("")


def _format_primitive_config(config: Dict[str, Any], output: List[str]) -> None:
    """
    Format primitive object configuration for readable output.

    Primitive objects (Timeline, GlobalSettings, etc.) have system-level
    parameters that affect analysis behavior and execution context.

    Args:
        config: Primitive configuration dictionary from dump_performa_object
        output: List to append formatted lines to (modified in-place)

    Key Parameters Displayed:
        - duration_months: Timeline duration for project analysis
        - start_date/end_date: Project timeline boundaries
        - period_frequency: Analysis frequency (monthly, quarterly, etc.)
        - Other system configuration parameters
    """
    # Show key primitive parameters
    key_params = ["duration_months", "start_date", "end_date", "period_frequency"]
    for param in key_params:
        if param in config:
            output.append(f"- **{param.replace('_', ' ').title()}**: {config[param]}")


def _format_generic_config(config: Dict[str, Any], output: List[str]) -> None:
    """
    Format unknown object configuration for readable output.

    This formatter handles objects that don't fit into standard Performa
    categories, providing basic parameter visibility for debugging purposes.

    Args:
        config: Generic configuration dictionary from dump_performa_object
        output: List to append formatted lines to (modified in-place)

    Display Strategy:
        - Shows generic object note
        - Lists first few public parameters for inspection
        - Provides minimal useful information for debugging
    """
    output.append("- **Configuration**: Generic object")

    # Show first few non-private keys
    public_keys = [k for k in config.keys() if not k.startswith("_")][:5]
    if public_keys:
        output.append(f"- **Key Parameters**: {', '.join(public_keys)}")
