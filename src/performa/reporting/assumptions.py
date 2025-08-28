# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Assumptions Report for Model Documentation

Generates comprehensive assumptions documentation for due diligence,
audit trails, and configuration analysis requirements.

Provides both standalone functions (flexible) and BaseReport class (reporting interface).
"""

from datetime import date
from typing import Any, Dict, List, Optional

import pandas as pd

from .base import BaseReport
from .debug import (
    analyze_configuration_intentionality,
    compare_configuration_intentionality,
    dump_performa_object,
)
from .debug.introspection import _classify_performa_object


def generate_assumptions_report(
    deal_or_object: Any,
    title: Optional[str] = None,
    include_risk_assessment: bool = True,
    include_defaults_detail: bool = False,
    focus_components: Optional[List[str]] = None,
) -> str:
    """
    Generate comprehensive assumptions report for any Performa object.

    Standalone function that works with deals, patterns, or individual components.
    Suitable for due diligence documentation and audit trails.

    Args:
        deal_or_object: Any Performa object (Deal, Pattern, Asset, etc.)
        title: Custom report title (auto-generated if None)
        include_risk_assessment: Flag critical parameters using defaults
        include_defaults_detail: Include full list of defaulted parameters
        focus_components: Limit analysis to specific components (for Deal objects)

    Returns:
        Formatted assumptions report as markdown text

    Example:
        ```python
        # For any object type
        report = generate_assumptions_report(residential_pattern)
        report = generate_assumptions_report(deal, focus_components=['asset', 'exit'])
        report = generate_assumptions_report(timeline, "Project Timeline Assumptions")
        ```
    """
    # Object identification
    obj_info = dump_performa_object(deal_or_object)["_object_info"]

    if title is None:
        title = f"{obj_info['class_name']} Assumptions Report"

    output = [
        f"# {title}",
        f"*Generated {date.today().strftime('%B %d, %Y')}*\n",
        "## Object Information",
        f"- **Class**: `{obj_info['class_name']}`",
        f"- **Type**: {obj_info['object_type']}",
        f"- **Module**: `{obj_info['module']}`",
        "",
    ]

    # Configuration analysis
    critical_params = _get_critical_params_for_object(deal_or_object)
    analysis = analyze_configuration_intentionality(deal_or_object, critical_params)

    # Configuration metrics
    metrics = analysis["intentionality_metrics"]
    output.extend([
        "## Configuration Summary",
        f"- **Total Parameters**: {metrics['total_available_count']}",
        f"- **User-Specified**: {metrics['user_explicit_count']} ({metrics['explicit_ratio']:.1%})",
        f"- **Using Defaults**: {metrics['total_available_count'] - metrics['user_plus_set_count']} ({metrics['defaulted_ratio']:.1%})",
        f"- **Quality Score**: {metrics['completeness_score']:.1%}",
        "",
    ])

    # Risk assessment
    if include_risk_assessment and "risk_assessment" in analysis:
        risk = analysis["risk_assessment"]
        output.append("## ⚠️ Risk Assessment")

        if risk.get("critical_defaults"):
            output.append(
                f"**Critical Parameters Using Defaults**: {len(risk['critical_defaults'])}"
            )
            for param in risk["critical_defaults"]:
                output.append(f"- `{param}` - Review for market appropriateness")
            output.append("")
        else:
            output.append(
                "✅ **No Critical Defaults**: All critical parameters explicitly specified"
            )
            output.append("")

    # Key user assumptions
    user_config = dump_performa_object(
        deal_or_object, exclude_defaults=True, exclude_unset=True
    )["config"]
    key_assumptions = _format_key_assumptions(user_config, obj_info["object_type"])

    if key_assumptions:
        output.append("## Key Assumptions (User-Specified)")
        output.extend(key_assumptions)
        output.append("")

    # Component breakdown (for Deal objects)
    if obj_info["object_type"] == "Deal" and hasattr(deal_or_object, "asset"):
        components_analysis = _analyze_deal_components(deal_or_object, focus_components)

        if components_analysis:
            output.append("## Component Analysis")
            for component_name, comp_data in components_analysis.items():
                output.append(f"### {component_name.title()}")
                output.append(f"- **Class**: `{comp_data['class_name']}`")
                output.append(
                    f"- **Configuration**: {comp_data['completeness']:.1%} complete"
                )

                if comp_data["key_assumptions"]:
                    output.append("- **Key Parameters**:")
                    for assumption in comp_data["key_assumptions"][:3]:  # Top 3
                        output.append(f"  - {assumption}")
                output.append("")

    # Defaults detail (optional)
    if include_defaults_detail:
        defaulted = analysis["defaulted_parameters"]
        if defaulted:
            output.append("## Parameters Using Defaults")
            output.append("*Review these for market/deal appropriateness*")
            output.append("")

            # Group by component if possible
            grouped_defaults = _group_defaults_by_component(defaulted)

            for group_name, params in grouped_defaults.items():
                if params:
                    output.append(f"### {group_name}")
                    for param in params[:8]:  # Limit for readability
                        output.append(f"- `{param}`")
                    if len(params) > 8:
                        output.append(f"- *... and {len(params) - 8} more*")
                    output.append("")

    # Recommendations
    if analysis["recommendations"]:
        output.append("## 💡 Recommendations")
        for rec in analysis["recommendations"]:
            output.append(f"- {rec}")
        output.append("")

    output.append("---")
    output.append(
        "*This report provides visibility into model assumptions and parameter sources for audit requirements.*"
    )

    return "\n".join(output)


def _get_critical_params_for_object(obj: Any) -> List[str]:
    """Get critical parameters based on object type."""
    obj_type = _classify_performa_object(obj)

    critical_by_type = {
        "Pattern": [
            "exit_cap_rate",
            "target_rent",
            "construction_cost_per_unit",
            "land_cost",
            "interest_rate",
        ],
        "Deal": ["acquisition.purchase_price", "exit.cap_rate", "financing.facilities"],
        "Asset": ["rent_roll", "expenses"],
        "Debt": ["loan_amount", "interest_rate", "ltv_ratio"],
        "Valuation": ["cap_rate", "hold_period_months"],
    }

    return critical_by_type.get(obj_type, [])


def _format_key_assumptions(config: Dict[str, Any], obj_type: str) -> List[str]:
    """Format key user-specified assumptions for display."""
    assumptions = []

    # Extract relevant parameters based on object type
    key_params = {
        "Pattern": [
            "project_name",
            "land_cost",
            "total_units",
            "exit_cap_rate",
            "hold_period_years",
        ],
        "Deal": ["name", "acquisition", "exit_valuation"],
        "Asset": ["net_rentable_area", "property_type"],
        "Debt": ["name", "loan_amount", "interest_rate"],
        "Valuation": ["name", "cap_rate", "hold_period_months"],
    }

    relevant_params = key_params.get(obj_type, list(config.keys())[:5])

    for param in relevant_params:
        if param in config:
            value = config[param]
            formatted = _format_assumption_value(param, value)
            if formatted:
                assumptions.append(
                    f"- **{param.replace('_', ' ').title()}**: {formatted}"
                )

    return assumptions


def _format_assumption_value(param: str, value: Any) -> str:
    """Format assumption value based on parameter type."""
    if isinstance(value, (int, float)):
        if "rate" in param.lower() or "ratio" in param.lower():
            return f"{value:.1%}"
        elif any(keyword in param.lower() for keyword in ["price", "cost", "amount"]):
            return f"${value:,.0f}"
        elif "months" in param.lower() or "years" in param.lower():
            return str(value)
        else:
            return f"{value:,.0f}"
    elif isinstance(value, str):
        return value
    elif isinstance(value, list):
        return f"{len(value)} items"
    elif isinstance(value, dict):
        return f"{len(value)} parameters"
    else:
        return str(value)[:50]  # Truncate


def _analyze_deal_components(
    deal, focus_components: Optional[List[str]] = None
) -> Dict[str, Dict[str, Any]]:
    """Analyze individual deal components."""
    components = {}

    # Component mapping
    component_map = {
        "asset": getattr(deal, "asset", None),
        "acquisition": getattr(deal, "acquisition", None),
        "financing": getattr(deal, "financing", None),
        "exit": getattr(deal, "exit_valuation", None),
        "partnership": getattr(deal, "equity_partners", None),
    }

    # Filter if focus specified
    if focus_components:
        component_map = {
            k: v for k, v in component_map.items() if k in focus_components
        }

    for name, component in component_map.items():
        if component is not None:
            obj_info = dump_performa_object(component)["_object_info"]

            # Component-specific critical params
            critical_params = _get_critical_params_for_object(component)
            analysis = analyze_configuration_intentionality(component, critical_params)

            # Key assumptions
            user_config = dump_performa_object(
                component, exclude_defaults=True, exclude_unset=True
            )["config"]
            key_assumptions = _format_key_assumptions(
                user_config, obj_info["object_type"]
            )

            components[name] = {
                "class_name": obj_info["class_name"],
                "object_type": obj_info["object_type"],
                "completeness": analysis["intentionality_metrics"][
                    "completeness_score"
                ],
                "key_assumptions": key_assumptions,
                "critical_defaults": analysis.get("risk_assessment", {}).get(
                    "critical_defaults", []
                ),
            }

    return components


def _group_defaults_by_component(defaulted_params: List[str]) -> Dict[str, List[str]]:
    """Group defaulted parameters by component for better organization."""
    groups = {
        "Asset Parameters": [],
        "Financing Parameters": [],
        "Timeline Parameters": [],
        "Other Parameters": [],
    }

    for param in defaulted_params:
        if any(
            keyword in param.lower()
            for keyword in ["rent", "expense", "area", "occupancy"]
        ):
            groups["Asset Parameters"].append(param)
        elif any(
            keyword in param.lower()
            for keyword in ["loan", "debt", "rate", "ltv", "facility"]
        ):
            groups["Financing Parameters"].append(param)
        elif any(
            keyword in param.lower()
            for keyword in ["date", "month", "duration", "timeline"]
        ):
            groups["Timeline Parameters"].append(param)
        else:
            groups["Other Parameters"].append(param)

    # Remove empty groups
    return {k: v for k, v in groups.items() if v}


class AssumptionsReport(BaseReport):
    """
    Comprehensive assumptions report for due diligence and analysis.

    Generates complete documentation of all model assumptions,
    highlighting user-specified vs default parameters with risk assessment.
    Suitable for presentations and audit requirements.
    """

    def generate(
        self,
        include_risk_assessment: bool = True,
        include_defaults_detail: bool = False,
        focus_components: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Generate comprehensive assumptions documentation.

        Args:
            include_risk_assessment: Include risk flagging for critical defaults
            include_defaults_detail: Include detailed list of defaulted parameters
            focus_components: Limit to specific components ('asset', 'financing', 'exit', 'partnership')

        Returns:
            Dictionary with structured assumptions documentation

        Example:
            ```python
            results = analyze(deal, timeline)
            assumptions = results.reporting.assumptions_summary()

            print(assumptions['executive_summary'])
            print(f"Configuration Quality: {assumptions['quality_score']:.1%}")
            ```
        """
        # Get deal components for analysis
        deal = self._results.deal

        report = {
            "report_metadata": self._generate_report_metadata(),
            "executive_summary": self._generate_executive_summary(deal),
            "configuration_overview": self._generate_configuration_overview(deal),
            "component_analysis": self._generate_component_analysis(
                deal, focus_components
            ),
            "quality_assessment": self._generate_quality_assessment(
                deal, include_risk_assessment
            ),
        }

        if include_defaults_detail:
            report["defaults_detail"] = self._generate_defaults_detail(deal)

        return report

    def generate_formatted(
        self,
        include_risk_assessment: bool = True,
        include_defaults_detail: bool = False,
        focus_components: Optional[List[str]] = None,
    ) -> str:
        """
        Generate formatted assumptions report as readable text.

        Suitable for presentations, due diligence packages,
        and audit documentation.

        Args:
            include_risk_assessment: Include risk flagging for critical defaults
            include_defaults_detail: Include detailed list of defaulted parameters
            focus_components: Limit to specific components

        Returns:
            Formatted markdown string suitable for documentation
        """
        data = self.generate(
            include_risk_assessment, include_defaults_detail, focus_components
        )

        output = []

        # Header
        metadata = data["report_metadata"]
        output.append(f"# Model Assumptions Summary")
        output.append(f"## {metadata['deal_name']}")
        output.append(f"**Report Date**: {metadata['report_date']}")
        output.append(f"**Deal Type**: {metadata['deal_type']}")
        output.append("")

        # Executive summary
        output.append("## Executive Summary")
        output.append(data["executive_summary"])
        output.append("")

        # Configuration overview
        overview = data["configuration_overview"]
        output.append("## Configuration Overview")
        output.append(f"- **Total Parameters**: {overview['total_parameters']}")
        output.append(
            f"- **User-Specified**: {overview['user_specified']} ({overview['explicit_ratio']:.1%})"
        )
        output.append(
            f"- **Using Defaults**: {overview['defaulted_count']} ({overview['defaulted_ratio']:.1%})"
        )
        output.append(f"- **Configuration Quality**: {overview['quality_score']:.1%}")
        output.append("")

        # Component analysis
        output.append("## Component Analysis")
        for component, analysis in data["component_analysis"].items():
            output.append(f"### {component.title()}")
            output.append(f"- **Class**: `{analysis['class_name']}`")
            output.append(
                f"- **Configuration**: {analysis['completeness']:.1%} complete"
            )

            # Key assumptions
            if analysis["key_assumptions"]:
                output.append("- **Key Assumptions**:")
                for assumption in analysis["key_assumptions"][:5]:  # Top 5
                    output.append(f"  - {assumption}")
            output.append("")

        # Quality assessment
        quality = data["quality_assessment"]
        output.append("## Quality Assessment")
        output.append(f"- **Overall Score**: {quality['overall_score']:.1%}")

        if include_risk_assessment and quality.get("critical_risks"):
            output.append("- **⚠️ Critical Risks**:")
            for risk in quality["critical_risks"]:
                output.append(f"  - {risk}")

        output.append("- **Recommendations**:")
        for rec in quality["recommendations"]:
            output.append(f"  - {rec}")
        output.append("")

        # Defaults detail if requested
        if include_defaults_detail and "defaults_detail" in data:
            output.append("## Parameters Using Defaults")
            output.append("*Review these defaults for market appropriateness*")
            output.append("")

            defaults = data["defaults_detail"]
            for component, params in defaults.items():
                if params:
                    output.append(f"### {component.title()}")
                    for param in params[:10]:  # Limit to avoid clutter
                        output.append(f"- `{param}`")
                    if len(params) > 10:
                        output.append(f"- *... and {len(params) - 10} more*")
                    output.append("")

        return "\n".join(output)

    def _generate_report_metadata(self) -> Dict[str, str]:
        """Generate report metadata."""
        deal_summary = self._results.deal_summary

        return {
            "report_date": date.today().strftime("%B %d, %Y"),
            "deal_name": deal_summary.deal_name or "Untitled Deal",
            "deal_type": deal_summary.asset_type or "Unknown",
            "report_type": "Model Assumptions Summary",
        }

    def _generate_executive_summary(self, deal) -> str:
        """Generate executive summary of assumptions."""
        # Basic deal info
        obj_info = dump_performa_object(deal)["_object_info"]

        # Configuration overview
        analysis = analyze_configuration_intentionality(deal)
        metrics = analysis["intentionality_metrics"]

        lines = [
            f"This {obj_info['class_name']} contains {metrics['total_available_count']} configurable parameters.",
            f"Of these, {metrics['user_explicit_count']} ({metrics['explicit_ratio']:.1%}) are user-specified,",
            f"while {metrics['total_available_count'] - metrics['user_plus_set_count']} ({metrics['defaulted_ratio']:.1%}) rely on system defaults.",
        ]

        # Risk assessment
        risk_assessment = analysis.get("risk_assessment", {})
        if risk_assessment.get("critical_defaults"):
            critical_count = len(risk_assessment["critical_defaults"])
            lines.append(
                f"⚠️ {critical_count} critical parameters are using defaults and require review."
            )
        else:
            lines.append("✅ All critical parameters have been explicitly specified.")

        return " ".join(lines)

    def _generate_configuration_overview(self, deal) -> Dict[str, Any]:
        """Generate overall configuration metrics."""
        analysis = analyze_configuration_intentionality(deal)
        metrics = analysis["intentionality_metrics"]

        return {
            "total_parameters": metrics["total_available_count"],
            "user_specified": metrics["user_explicit_count"],
            "explicit_ratio": metrics["explicit_ratio"],
            "defaulted_count": metrics["total_available_count"]
            - metrics["user_plus_set_count"],
            "defaulted_ratio": metrics["defaulted_ratio"],
            "quality_score": metrics["completeness_score"],
        }

    def _generate_component_analysis(
        self, deal, focus_components: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """Generate analysis for individual deal components."""
        components = {}

        # Define component mapping
        component_map = {
            "asset": deal.asset,
            "acquisition": deal.acquisition,
            "financing": deal.financing,
            "exit": deal.exit_valuation,
            "partnership": deal.equity_partners,
        }

        # Filter to focus components if specified
        if focus_components:
            component_map = {
                k: v for k, v in component_map.items() if k in focus_components
            }

        for name, component in component_map.items():
            if component is not None:
                components[name] = self._analyze_component(component, name)

        return components

    def _analyze_component(self, component, component_name: str) -> Dict[str, Any]:
        """Analyze individual component configuration."""
        obj_info = dump_performa_object(component)["_object_info"]

        # Get critical params based on component type
        critical_params = self._get_component_critical_params(component_name)

        analysis = analyze_configuration_intentionality(component, critical_params)
        metrics = analysis["intentionality_metrics"]

        # Extract key assumptions (user-specified parameters)
        user_config = dump_performa_object(
            component, exclude_defaults=True, exclude_unset=True
        )["config"]
        key_assumptions = self._extract_key_assumptions(user_config, component_name)

        return {
            "class_name": obj_info["class_name"],
            "object_type": obj_info["object_type"],
            "completeness": metrics["completeness_score"],
            "explicit_ratio": metrics["explicit_ratio"],
            "key_assumptions": key_assumptions,
            "critical_defaults": analysis.get("risk_assessment", {}).get(
                "critical_defaults", []
            ),
        }

    def _extract_key_assumptions(
        self, config: Dict[str, Any], component_name: str
    ) -> List[str]:
        """Extract key assumptions for display."""
        assumptions = []

        # Component-specific key parameters to highlight
        key_params_by_component = {
            "asset": ["net_rentable_area", "rent_roll", "expenses", "property_type"],
            "acquisition": ["purchase_price", "closing_costs_rate", "closing_date"],
            "financing": ["facilities", "total_loan_amount"],
            "exit": ["cap_rate", "hold_period_months", "transaction_costs_rate"],
            "partnership": ["gp_equity_percentage", "preferred_return_rate"],
        }

        key_params = key_params_by_component.get(component_name, [])

        for param in key_params:
            if param in config:
                value = config[param]
                assumptions.append(self._format_assumption(param, value))

        # Add any other user-specified parameters
        other_params = [
            k for k in config.keys() if k not in key_params and not k.startswith("_")
        ]
        for param in other_params[:3]:  # Limit to avoid clutter
            if param in config:
                value = config[param]
                assumptions.append(self._format_assumption(param, value))

        return assumptions

    def _format_assumption(self, param: str, value: Any) -> str:
        """Format individual assumption for display."""
        # Format parameter name
        param_display = param.replace("_", " ").title()

        # Format value based on type and name
        if isinstance(value, (int, float)):
            if "rate" in param.lower() or "ratio" in param.lower():
                return f"{param_display}: {value:.1%}"
            elif (
                "price" in param.lower()
                or "cost" in param.lower()
                or "amount" in param.lower()
            ):
                return f"{param_display}: ${value:,.0f}"
            elif "months" in param.lower() or "years" in param.lower():
                return f"{param_display}: {value}"
            else:
                return f"{param_display}: {value:,.0f}"
        elif isinstance(value, str):
            return f"{param_display}: {value}"
        elif isinstance(value, list) and len(value) <= 3:
            return f"{param_display}: {len(value)} items"
        elif isinstance(value, dict):
            return f"{param_display}: {len(value)} parameters"
        else:
            return f"{param_display}: {str(value)[:50]}"  # Truncate long values

    def _get_component_critical_params(self, component_name: str) -> List[str]:
        """Get critical parameters by component name."""
        critical_by_component = {
            "asset": ["rent_roll", "expenses", "net_rentable_area"],
            "acquisition": ["purchase_price"],
            "financing": ["loan_amount", "interest_rate", "ltv_ratio"],
            "exit": ["cap_rate", "hold_period_months"],
            "partnership": ["gp_equity_percentage"],
        }

        return critical_by_component.get(component_name, [])

    def _generate_quality_assessment(
        self, deal, include_risk_assessment: bool
    ) -> Dict[str, Any]:
        """Generate overall quality assessment."""
        analysis = analyze_configuration_intentionality(deal)
        metrics = analysis["intentionality_metrics"]

        assessment = {
            "overall_score": metrics["completeness_score"],
            "recommendations": analysis["recommendations"],
        }

        if include_risk_assessment:
            # Analyze each component for critical risks
            critical_risks = []

            components = {
                "Asset": deal.asset,
                "Financing": deal.financing,
                "Exit": deal.exit_valuation,
                "Partnership": deal.equity_partners,
            }

            for name, component in components.items():
                if component:
                    comp_analysis = analyze_configuration_intentionality(
                        component, self._get_component_critical_params(name.lower())
                    )

                    risk_assessment = comp_analysis.get("risk_assessment", {})
                    if risk_assessment.get("critical_defaults"):
                        for param in risk_assessment["critical_defaults"]:
                            critical_risks.append(
                                f"{name}: {param} using default value"
                            )

            assessment["critical_risks"] = critical_risks

        return assessment

    def _generate_defaults_detail(self, deal) -> Dict[str, List[str]]:
        """Generate detailed list of defaulted parameters by component."""
        defaults_by_component = {}

        components = {
            "asset": deal.asset,
            "acquisition": deal.acquisition,
            "financing": deal.financing,
            "exit": deal.exit_valuation,
            "partnership": deal.equity_partners,
        }

        for name, component in components.items():
            if component:
                analysis = analyze_configuration_intentionality(component)
                defaults_by_component[name] = analysis["defaulted_parameters"]

        return defaults_by_component


def create_assumptions_comparison(
    deal1, deal2, name1: str = "Deal 1", name2: str = "Deal 2"
) -> str:
    """
    Create side-by-side assumptions comparison for validation.

    Suitable for comparing pattern vs composition approaches or
    validating that different deal structures have appropriate
    assumption differences.

    Args:
        deal1: First deal to compare
        deal2: Second deal to compare
        name1: Label for first deal
        name2: Label for second deal

    Returns:
        Formatted comparison report

    Example:
        ```python
        comparison = create_assumptions_comparison(
            comp_deal, pattern_deal, "Composition", "Pattern"
        )
        print(comparison)
        ```
    """
    comparison = compare_configuration_intentionality(deal1, deal2, name1, name2)

    output = [
        f"# Assumptions Comparison: {name1} vs {name2}\n",
        "## Configuration Intentionality Metrics",
        "",
    ]

    # Comparison table
    metrics = comparison["metrics_comparison"]
    comp_data = {
        "Metric": [
            "Configuration Completeness",
            "Explicit Configuration",
            "Using Defaults",
        ],
        name1: [
            f"{metrics['completeness_scores'][name1]:.1%}",
            f"{metrics['explicit_ratios'][name1]:.1%}",
            f"{metrics['defaulted_ratios'][name1]:.1%}",
        ],
        name2: [
            f"{metrics['completeness_scores'][name2]:.1%}",
            f"{metrics['explicit_ratios'][name2]:.1%}",
            f"{metrics['defaulted_ratios'][name2]:.1%}",
        ],
    }

    # Create comparison table
    df = pd.DataFrame(comp_data)
    output.append(df.to_string(index=False))
    output.append("")

    # Parity assessment
    if comparison["intentionality_parity"]:
        output.append("## ✅ Intentionality Parity")
        output.append(
            "Both approaches have equivalent configuration depth and parameter visibility."
        )
    else:
        output.append("## ⚠️ Intentionality Differences")
        output.append("Configuration depth varies between approaches:")
        for diff in comparison["differences"]:
            output.append(f"- {diff}")

    output.append("")

    # Recommendations
    if comparison["recommendations"]:
        output.append("## Recommendations")
        for rec in comparison["recommendations"]:
            output.append(f"- {rec}")

    return "\n".join(output)
