# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Configuration intentionality analysis for financial model validation.

This module analyzes the configuration quality of Performa objects,
distinguishing between user-specified and system default parameters.
Important for financial modeling where defaults can be dangerous and
lead to unrealistic or inappropriate assumptions.

Provides risk assessment for critical parameters and actionable
recommendations for improving configuration quality.
"""

from typing import Any, Dict, List, Optional, Tuple

from .introspection import _classify_performa_object, dump_performa_object


def analyze_configuration_intentionality(
    obj: Any, critical_params: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Analyze configuration intentionality: what's user-specified vs defaulted.

    This analysis is essential for financial modeling where defaults can be
    dangerous and lead to unrealistic or inappropriate assumptions.

    Args:
        obj: Any Performa object to analyze
        critical_params: List of parameters that should rarely use defaults
                        (e.g., ['cap_rate', 'interest_rate', 'rent_psf'])

    Returns:
        Dict containing intentionality analysis with risk assessment

    Example:
        ```python
        analysis = analyze_configuration_intentionality(pattern,
            critical_params=['exit_cap_rate', 'target_rent', 'construction_cost_per_unit'])

        print(f"Configuration completeness: {analysis['completeness_score']:.1%}")
        print(f"Important defaults: {len(analysis['critical_defaults'])}")
        ```
    """
    # Get three views of the configuration
    user_only = dump_performa_object(obj, exclude_defaults=True, exclude_unset=True)
    user_and_set_defaults = dump_performa_object(
        obj, exclude_defaults=True, exclude_unset=False
    )
    full_config = dump_performa_object(obj, exclude_defaults=False, exclude_unset=False)

    analysis = {
        "configuration_views": {
            "user_explicit": user_only["config"],
            "user_plus_set_defaults": user_and_set_defaults["config"],
            "full_with_all_defaults": full_config["config"],
        },
        "intentionality_metrics": {},
        "risk_assessment": {},
        "recommendations": [],
    }

    # Calculate configuration metrics
    user_params = _count_config_parameters(user_only["config"])
    set_params = _count_config_parameters(user_and_set_defaults["config"])
    total_params = _count_config_parameters(full_config["config"])

    # Detect if this is a pattern-based object (high defaults usage is expected)
    is_pattern_based = _detect_pattern_based_object(obj, user_params, total_params)

    # Calculate appropriate quality scores based on object type
    if is_pattern_based:
        # For patterns: Quality = appropriate parameter specification, not override count
        quality_score = _calculate_pattern_quality_score(
            user_params, set_params, total_params
        )
        quality_interpretation = "Pattern Quality Score (defaults are a feature)"
    else:
        # For manual composition: Quality = explicit specification
        quality_score = user_params / total_params if total_params > 0 else 0
        quality_interpretation = "Configuration Completeness (explicit vs defaults)"

    analysis["intentionality_metrics"] = {
        "user_explicit_count": user_params,
        "user_plus_set_count": set_params,
        "total_available_count": total_params,
        "explicit_ratio": user_params / total_params if total_params > 0 else 0,
        "defaulted_ratio": (total_params - set_params) / total_params
        if total_params > 0
        else 0,
        "completeness_score": set_params / total_params
        if total_params > 0
        else 0,  # Legacy for compatibility
        "quality_score": quality_score,
        "quality_interpretation": quality_interpretation,
        "is_pattern_based": is_pattern_based,
    }

    # Identify defaulted parameters
    defaulted_params = _identify_defaulted_parameters(
        user_and_set_defaults["config"], full_config["config"]
    )

    # Risk assessment for critical parameters
    if critical_params:
        critical_defaults = []
        for param in critical_params:
            if _is_parameter_defaulted(
                param, user_and_set_defaults["config"], full_config["config"]
            ):
                critical_defaults.append(param)

        analysis["risk_assessment"] = {
            "critical_defaults": critical_defaults,
            "critical_default_count": len(critical_defaults),
            "critical_risk_score": len(critical_defaults) / len(critical_params)
            if critical_params
            else 0,
        }

        # Generate recommendations
        if critical_defaults:
            analysis["recommendations"].append(
                f"⚠️ RISK: {len(critical_defaults)} critical parameters using defaults: {critical_defaults}"
            )
            analysis["recommendations"].append(
                "💡 Review these defaults carefully - they may not suit your specific deal/market"
            )

    analysis["defaulted_parameters"] = defaulted_params

    # Configuration quality assessment using context-appropriate scoring
    quality_score = analysis["intentionality_metrics"]["quality_score"]
    is_pattern = analysis["intentionality_metrics"]["is_pattern_based"]

    if is_pattern:
        # Pattern-specific quality assessment
        if quality_score >= 0.9:
            analysis["recommendations"].append(
                "✅ EXCELLENT pattern configuration - optimal parameter specification"
            )
        elif quality_score >= 0.7:
            analysis["recommendations"].append(
                "📊 GOOD pattern configuration - well-targeted parameters"
            )
        else:
            analysis["recommendations"].append(
                "⚠️ Pattern configuration needs attention - check essential parameters"
            )
    elif quality_score >= 0.7:
        analysis["recommendations"].append(
            "✅ HIGH configuration completeness - well-specified manual model"
        )
    elif quality_score >= 0.4:
        analysis["recommendations"].append(
            "📊 MEDIUM configuration completeness - review key defaults"
        )
    else:
        analysis["recommendations"].append(
            "⚠️ LOW configuration completeness - many parameters using defaults"
        )

    return analysis


def compare_configuration_intentionality(
    obj1: Any, obj2: Any, name1: str = "Object 1", name2: str = "Object 2"
) -> Dict[str, Any]:
    """
    Compare configuration intentionality between two similar objects.

    Critical for validating that pattern and compositional approaches
    have equivalent levels of configuration intentionality, not just
    equivalent outputs.

    Args:
        obj1: First object to compare
        obj2: Second object to compare
        name1: Label for first object
        name2: Label for second object

    Returns:
        Dict containing comparative intentionality analysis

    Example:
        ```python
        comparison = compare_configuration_intentionality(
            comp_deal, pattern_deal, "Composition", "Pattern"
        )

        if comparison['intentionality_parity']:
            print("✅ Both approaches have equivalent configuration depth")
        else:
            print(f"⚠️ Configuration depth mismatch: {comparison['differences']}")
        ```
    """
    analysis1 = analyze_configuration_intentionality(obj1)
    analysis2 = analyze_configuration_intentionality(obj2)

    comparison = {
        "objects": {name1: analysis1, name2: analysis2},
        "metrics_comparison": {},
        "intentionality_parity": False,
        "differences": [],
        "recommendations": [],
    }

    # Compare key metrics
    metrics1 = analysis1["intentionality_metrics"]
    metrics2 = analysis2["intentionality_metrics"]

    comparison["metrics_comparison"] = {
        "completeness_scores": {
            name1: metrics1["completeness_score"],
            name2: metrics2["completeness_score"],
        },
        "explicit_ratios": {
            name1: metrics1["explicit_ratio"],
            name2: metrics2["explicit_ratio"],
        },
        "defaulted_ratios": {
            name1: metrics1["defaulted_ratio"],
            name2: metrics2["defaulted_ratio"],
        },
    }

    # Check for intentionality parity (within 10% tolerance)
    completeness_diff = abs(
        metrics1["completeness_score"] - metrics2["completeness_score"]
    )
    explicit_diff = abs(metrics1["explicit_ratio"] - metrics2["explicit_ratio"])

    comparison["intentionality_parity"] = (
        completeness_diff < 0.1 and explicit_diff < 0.1
    )

    if not comparison["intentionality_parity"]:
        comparison["differences"].append(
            f"Completeness gap: {name1} {metrics1['completeness_score']:.1%} vs "
            f"{name2} {metrics2['completeness_score']:.1%}"
        )
        comparison["differences"].append(
            f"Explicit config gap: {name1} {metrics1['explicit_ratio']:.1%} vs "
            f"{name2} {metrics2['explicit_ratio']:.1%}"
        )

    # Risk comparison
    risk1 = analysis1.get("risk_assessment", {})
    risk2 = analysis2.get("risk_assessment", {})

    if risk1.get("critical_defaults") or risk2.get("critical_defaults"):
        comparison["recommendations"].append(
            "⚠️ One or both objects have critical parameters using defaults"
        )

    return comparison


def generate_configuration_report(
    obj: Any,
    critical_params: Optional[List[str]] = None,
    include_recommendations: bool = True,
) -> str:
    """
    Generate comprehensive configuration intentionality report.

    Provides actionable insights about configuration quality and potential
    risks from over-reliance on defaults in financial modeling.

    Args:
        obj: Object to analyze
        critical_params: Parameters that should rarely use defaults
        include_recommendations: Include actionable recommendations

    Returns:
        Formatted report string with configuration analysis

    Example:
        ```python
        report = generate_configuration_report(
            residential_pattern,
            critical_params=['exit_cap_rate', 'target_rent', 'construction_cost_per_unit']
        )
        print(report)
        ```
    """
    analysis = analyze_configuration_intentionality(obj, critical_params)

    # Object identification
    obj_info = dump_performa_object(obj)["_object_info"]
    title = f"{obj_info['class_name']} Configuration Analysis"

    output = [f"# {title}\n"]

    # Object metadata
    output.append("## Object Information")
    output.append(f"- **Class**: `{obj_info['class_name']}`")
    output.append(f"- **Type**: {obj_info['object_type']}")
    output.append(f"- **Module**: `{obj_info['module']}`")
    output.append("")

    # Configuration metrics
    metrics = analysis["intentionality_metrics"]
    output.append("## Configuration Metrics")
    output.append(f"- **User Explicit Parameters**: {metrics['user_explicit_count']}")
    output.append(
        f"- **Total Available Parameters**: {metrics['total_available_count']}"
    )
    output.append(
        f"- **Configuration Completeness**: {metrics['completeness_score']:.1%}"
    )
    output.append(f"- **Explicit Configuration**: {metrics['explicit_ratio']:.1%}")
    output.append(f"- **Using Defaults**: {metrics['defaulted_ratio']:.1%}")
    output.append("")

    # Risk assessment
    if "risk_assessment" in analysis and analysis["risk_assessment"]:
        risk = analysis["risk_assessment"]
        output.append("## ⚠️ Risk Assessment")
        output.append(
            f"- **Critical Defaults Count**: {risk['critical_default_count']}"
        )
        output.append(f"- **Critical Risk Score**: {risk['critical_risk_score']:.1%}")

        if risk["critical_defaults"]:
            output.append("- **Critical Parameters Using Defaults**:")
            for param in risk["critical_defaults"]:
                output.append(f"  - `{param}`")
        output.append("")

    # Defaulted parameters (non-critical)
    defaulted = analysis["defaulted_parameters"]
    if defaulted:
        output.append("## Parameters Using Defaults")
        output.append(
            "Parameters relying on system defaults (review for appropriateness):"
        )
        output.append("")
        for param in sorted(defaulted)[:10]:  # Show first 10 to avoid clutter
            output.append(f"- `{param}`")

        if len(defaulted) > 10:
            output.append(f"- ... and {len(defaulted) - 10} more")
        output.append("")

    # Recommendations
    if include_recommendations and analysis["recommendations"]:
        output.append("## 💡 Recommendations")
        for rec in analysis["recommendations"]:
            output.append(f"- {rec}")
        output.append("")

    return "\n".join(output)


def _count_config_parameters(config: Dict[str, Any]) -> int:
    """
    Count total parameters in configuration dictionary.

    Recursively counts parameters while excluding metadata fields
    that start with underscore.

    Args:
        config: Configuration dictionary to count

    Returns:
        Total count of configuration parameters
    """
    count = 0

    for key, value in config.items():
        # Skip metadata fields
        if key.startswith("_"):
            continue

        if isinstance(value, dict):
            # Recursively count nested dictionaries
            count += _count_config_parameters(value)
        elif isinstance(value, list):
            # Count list items that are dictionaries
            for item in value:
                if isinstance(item, dict):
                    count += _count_config_parameters(item)
                else:
                    count += 1
        else:
            count += 1

    return count


def _identify_defaulted_parameters(
    user_config: Dict[str, Any], full_config: Dict[str, Any]
) -> List[str]:
    """
    Identify parameters that are using defaults (not explicitly set by user).

    Compares user-specified configuration against full configuration to
    identify parameters that are relying on system defaults.

    Args:
        user_config: Configuration with user-specified values only
        full_config: Complete configuration including defaults

    Returns:
        List of parameter names that are using defaults
    """
    defaulted = []

    def _find_defaulted_recursive(
        user_dict: Dict[str, Any], full_dict: Dict[str, Any], prefix: str = ""
    ):
        for key, full_value in full_dict.items():
            # Skip metadata fields
            if key.startswith("_"):
                continue

            full_key = f"{prefix}.{key}" if prefix else key

            if key not in user_dict:
                # Parameter exists in full but not in user config = defaulted
                defaulted.append(full_key)
            elif isinstance(full_value, dict) and isinstance(user_dict.get(key), dict):
                # Recursively check nested dictionaries
                _find_defaulted_recursive(user_dict[key], full_value, full_key)
            elif isinstance(full_value, list) and isinstance(user_dict.get(key), list):
                # Handle lists (like facilities, unit_mix, etc.)
                user_list = user_dict[key]
                full_list = full_value

                for i, full_item in enumerate(full_list):
                    if (
                        i < len(user_list)
                        and isinstance(full_item, dict)
                        and isinstance(user_list[i], dict)
                    ):
                        _find_defaulted_recursive(
                            user_list[i], full_item, f"{full_key}[{i}]"
                        )

    _find_defaulted_recursive(user_config, full_config)
    return defaulted


def _is_parameter_defaulted(
    param_name: str, user_config: Dict[str, Any], full_config: Dict[str, Any]
) -> bool:
    """
    Check if a specific parameter is using defaults.

    Args:
        param_name: Name of parameter to check (supports dot notation for nested)
        user_config: User-specified configuration
        full_config: Full configuration including defaults

    Returns:
        True if parameter is using defaults, False if user-specified
    """

    # Handle dot notation for nested parameters (e.g., "exit.cap_rate")
    def _get_nested_value(config: Dict[str, Any], path: str) -> Any:
        keys = path.split(".")
        value = config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        return value

    user_value = _get_nested_value(user_config, param_name)
    full_value = _get_nested_value(full_config, param_name)

    # Parameter is defaulted if it exists in full config but not in user config
    return full_value is not None and user_value is None


def create_actionable_config_summary(
    obj: Any, focus_areas: Optional[List[str]] = None
) -> Tuple[str, List[str]]:
    """
    Create actionable configuration summary with specific next steps.

    Provides focused insights and concrete actions for improving
    configuration quality and reducing reliance on potentially
    inappropriate defaults.

    Args:
        obj: Object to analyze
        focus_areas: Specific parameter categories to focus on
                    (e.g., ['financing', 'exit', 'asset'])

    Returns:
        Tuple of (summary_text, action_items)

    Example:
        ```python
        summary, actions = create_actionable_config_summary(
            pattern, focus_areas=['financing', 'exit']
        )

        print(summary)
        for action in actions:
            print(f"TODO: {action}")
        ```
    """
    # Define critical parameters by object type
    obj_type = _classify_performa_object(obj)
    critical_params = _get_critical_params_by_type(obj_type, focus_areas)

    analysis = analyze_configuration_intentionality(obj, critical_params)

    # Generate summary
    obj_info = dump_performa_object(obj)["_object_info"]
    metrics = analysis["intentionality_metrics"]

    summary_lines = [
        f"📊 **{obj_info['class_name']}** Configuration Summary",
        f"   • Completeness: {metrics['completeness_score']:.1%}",
        f"   • Explicit: {metrics['explicit_ratio']:.1%}",
        f"   • Using Defaults: {metrics['defaulted_ratio']:.1%}",
    ]

    # Risk summary
    if (
        "risk_assessment" in analysis
        and analysis["risk_assessment"]["critical_defaults"]
    ):
        critical_count = analysis["risk_assessment"]["critical_default_count"]
        summary_lines.append(f"   • ⚠️ Critical Defaults: {critical_count}")
    else:
        summary_lines.append("   • ✅ No Critical Defaults")

    summary = "\n".join(summary_lines)

    # Generate actionable items
    action_items = []

    # Configuration completeness actions
    if metrics["completeness_score"] < 0.5:
        action_items.append(
            f"Review {obj_info['class_name']} configuration - low completeness ({metrics['completeness_score']:.1%})"
        )

    # Critical defaults actions
    if "risk_assessment" in analysis:
        for param in analysis["risk_assessment"].get("critical_defaults", []):
            action_items.append(
                f"Specify explicit value for critical parameter: {param}"
            )

    # General recommendations
    action_items.extend(analysis["recommendations"])

    return summary, action_items


def _get_critical_params_by_type(
    obj_type: str, focus_areas: Optional[List[str]] = None
) -> List[str]:
    """
    Get critical parameters that should rarely use defaults by object type.

    Args:
        obj_type: Object type from _classify_performa_object
        focus_areas: Specific areas to focus on (optional)

    Returns:
        List of critical parameter names for the object type
    """
    # Define critical parameters by object type - these should rarely use defaults
    critical_by_type = {
        "Pattern": [
            "exit_cap_rate",
            "target_rent",
            "construction_cost_per_unit",
            "land_cost",
            "interest_rate",
            "ltv_ratio",
            "purchase_price",
        ],
        "Deal": [
            "acquisition.purchase_price",
            "exit.cap_rate",
            "financing.facilities",
            "asset.rent_roll",
            "asset.expenses",
        ],
        "Asset": ["rent_roll", "expenses", "absorption_plans", "construction_plan"],
        "Debt": ["loan_amount", "interest_rate", "ltv_ratio", "dscr_hurdle"],
        "Valuation": ["cap_rate", "hold_period_months", "transaction_costs_rate"],
    }

    base_critical = critical_by_type.get(obj_type, [])

    # Filter by focus areas if specified
    if focus_areas:
        filtered = []
        for param in base_critical:
            for area in focus_areas:
                if area.lower() in param.lower():
                    filtered.append(param)
        return filtered

    return base_critical


def _detect_pattern_based_object(obj: Any, user_params: int, total_params: int) -> bool:
    """
    Detect if an object is pattern-based where defaults are a feature.

    Pattern objects are designed to use intelligent defaults, so low explicit
    parameter counts should be considered high quality, not low quality.
    """
    # Check class name for pattern indicators
    class_name = obj.__class__.__name__
    if "Pattern" in class_name:
        return True

    # Check for Deal objects created from patterns (high default usage)
    if class_name == "Deal" and hasattr(obj, "description"):
        description = getattr(obj, "description", "") or ""
        if "pattern" in description.lower() or "convention" in description.lower():
            return True

    # Check for very high default usage (>60%) which suggests pattern-based approach
    default_ratio = (
        (total_params - user_params) / total_params if total_params > 0 else 0
    )
    if default_ratio > 0.6:
        return True

    return False


def _calculate_pattern_quality_score(
    user_params: int, set_params: int, total_params: int
) -> float:
    """
    Calculate quality score appropriate for pattern-based objects.

    For patterns, quality comes from:
    1. Specifying the essential parameters (not all parameters)
    2. Leveraging intelligent defaults appropriately
    3. Avoiding over-specification that defeats the pattern purpose

    Returns a score from 0.0 to 1.0 where higher is better.
    """
    if total_params == 0:
        return 1.0

    # Essential parameters ratio (should be reasonable but not exhaustive)
    explicit_ratio = user_params / total_params

    # For patterns, optimal explicit ratio is 10-30% (hitting key parameters)
    if 0.1 <= explicit_ratio <= 0.3:
        # High quality: appropriate parameter targeting
        base_score = 1.0
    elif 0.05 <= explicit_ratio < 0.1:
        # Good quality: minimal but functional configuration
        base_score = 0.8
    elif 0.3 < explicit_ratio <= 0.5:
        # Good quality: more detailed configuration
        base_score = 0.9
    elif explicit_ratio > 0.5:
        # Lower quality: over-specified for a pattern (defeats the purpose)
        base_score = 0.6
    else:
        # Very low specification might indicate incomplete configuration
        base_score = 0.5

    return base_score
