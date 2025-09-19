# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Timeline Analysis Debug Utilities

Debugging capabilities for timeline-related issues in financial model validation.
These utilities identify timeline mismatches that can cause significant
differences in deal analysis results.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from performa.deal.deal import Deal

logger = logging.getLogger(__name__)


def compare_deal_timelines(deal1: "Deal", deal2: "Deal") -> Dict[str, Any]:
    """
    Compare timelines between two deals to identify mismatches.

    This utility extracts timelines from all deal components and identifies
    differences that could cause parity issues in analysis results.

    Args:
        deal1: First deal for comparison
        deal2: Second deal for comparison

    Returns:
        Dict containing timeline comparison results with mismatch detection

    Example:
        ```python
        timeline_diff = compare_deal_timelines(composition_deal, pattern_deal)
        if timeline_diff['has_mismatches']:
            print(f"Timeline issues: {timeline_diff['summary']}")
        ```
    """
    result = {
        "deal1_timelines": _extract_deal_timelines(deal1),
        "deal2_timelines": _extract_deal_timelines(deal2),
        "differences": [],
        "has_mismatches": False,
        "summary": "",
        "impact_assessment": "",
        "recommendations": [],
    }

    timelines1 = result["deal1_timelines"]
    timelines2 = result["deal2_timelines"]

    # Compare each timeline component
    all_components = set(timelines1.keys()) | set(timelines2.keys())

    for component in all_components:
        timeline1 = timelines1.get(component)
        timeline2 = timelines2.get(component)

        if timeline1 is None or timeline2 is None:
            diff = {
                "component": component,
                "issue": "missing_timeline",
                "deal1_value": timeline1,
                "deal2_value": timeline2,
                "impact": "high",
            }
            result["differences"].append(diff)
            result["has_mismatches"] = True
            continue

        # Compare timeline properties
        if timeline1.get("duration_months") != timeline2.get("duration_months"):
            diff = {
                "component": component,
                "issue": "duration_mismatch",
                "deal1_value": timeline1.get("duration_months"),
                "deal2_value": timeline2.get("duration_months"),
                "impact": "high"
                if abs(
                    (
                        timeline1.get("duration_months", 0)
                        - timeline2.get("duration_months", 0)
                    )
                )
                > 1
                else "medium",
            }
            result["differences"].append(diff)
            result["has_mismatches"] = True

        if timeline1.get("start_date") != timeline2.get("start_date"):
            diff = {
                "component": component,
                "issue": "start_date_mismatch",
                "deal1_value": timeline1.get("start_date"),
                "deal2_value": timeline2.get("start_date"),
                "impact": "high",
            }
            result["differences"].append(diff)
            result["has_mismatches"] = True

    # Generate summary and recommendations
    if result["has_mismatches"]:
        duration_diffs = [
            d for d in result["differences"] if d["issue"] == "duration_mismatch"
        ]
        if duration_diffs:
            max_diff = max(
                abs(d["deal1_value"] - d["deal2_value"])
                for d in duration_diffs
                if d["deal1_value"] and d["deal2_value"]
            )
            result["summary"] = (
                f"Timeline duration differences up to {max_diff} periods found"
            )
            result["impact_assessment"] = (
                f"Expected impact: ~{max_diff * 5}% transaction count difference"
            )
            result["recommendations"] = [
                "Use Timeline.from_dates() with same start/end dates for both deals",
                "Verify analysis timeline matches asset hold period",
                "Check for off-by-one errors in period calculations",
            ]
    else:
        result["summary"] = "All timelines match"
        result["impact_assessment"] = "No timeline-related parity issues expected"

    return result


def extract_component_timelines(deal: "Deal") -> Dict[str, Any]:
    """
    Extract timelines from all deal components.

    This utility provides visibility into all timeline-related configurations
    within a deal to identify potential misalignments.

    Args:
        deal: Deal object to analyze

    Returns:
        Dict containing all timeline information from deal components

    Example:
        ```python
        timelines = extract_component_timelines(deal)
        print(f"Asset timeline: {timelines['asset']['duration_months']} months")
        if timelines['misalignment_warnings']:
            print("⚠️ Timeline misalignments detected")
        ```
    """
    timelines = _extract_deal_timelines(deal)

    # Add misalignment detection
    timelines["misalignment_warnings"] = []
    timelines["summary"] = {}

    # Check for common misalignments
    asset_duration = timelines.get("asset", {}).get("duration_months")
    exit_hold_period = timelines.get("exit", {}).get("hold_period_months")

    if asset_duration and exit_hold_period:
        if asset_duration != exit_hold_period:
            timelines["misalignment_warnings"].append({
                "issue": "asset_exit_mismatch",
                "asset_duration": asset_duration,
                "exit_hold_period": exit_hold_period,
                "description": "Asset timeline duration does not match exit hold period",
            })

    # Generate summary
    if timelines["misalignment_warnings"]:
        timelines["summary"]["status"] = "misalignments_detected"
        timelines["summary"]["warning_count"] = len(timelines["misalignment_warnings"])
    else:
        timelines["summary"]["status"] = "aligned"
        timelines["summary"]["warning_count"] = 0

    return timelines


def _extract_deal_timelines(deal: "Deal") -> Dict[str, Any]:
    """Extract timeline information from deal components."""
    timelines = {}

    # Asset timeline
    if deal.asset and hasattr(deal.asset, "timeline"):
        timeline = deal.asset.timeline
        if timeline:
            timelines["asset"] = {
                "duration_months": getattr(timeline, "duration_months", None),
                "start_date": getattr(timeline, "start_date", None),
                "end_date": getattr(timeline, "end_date", None),
                "source": "asset.timeline",
            }

    # Acquisition timeline
    if deal.acquisition and hasattr(deal.acquisition, "timeline"):
        timeline = deal.acquisition.timeline
        if timeline:
            timelines["acquisition"] = {
                "duration_months": getattr(timeline, "duration_months", None),
                "start_date": getattr(timeline, "start_date", None),
                "end_date": getattr(timeline, "end_date", None),
                "source": "acquisition.timeline",
            }

    # Financing timeline (from facilities)
    if (
        deal.financing
        and hasattr(deal.financing, "facilities")
        and deal.financing.facilities
    ):
        for i, facility in enumerate(deal.financing.facilities):
            loan_term_months = getattr(facility, "loan_term_months", None)
            if loan_term_months:
                timelines[f"financing_facility_{i}"] = {
                    "duration_months": loan_term_months,
                    "loan_term_years": getattr(facility, "loan_term_years", None),
                    "amortization_months": getattr(
                        facility, "amortization_months", None
                    ),
                    "source": f"financing.facilities[{i}]",
                }

    # Exit timeline
    if deal.exit_valuation and hasattr(deal.exit_valuation, "hold_period_months"):
        timelines["exit"] = {
            "hold_period_months": deal.exit_valuation.hold_period_months,
            "source": "exit_valuation.hold_period_months",
        }

    return timelines


def format_timeline_comparison(comparison: Dict[str, Any]) -> str:
    """Format timeline comparison results for display."""
    if not comparison["has_mismatches"]:
        return "✅ Timeline Comparison: All timelines match"

    output = ["🔍 Timeline Comparison Results"]
    output.append("=" * 50)

    output.append(f"Summary: {comparison['summary']}")
    output.append(f"Impact: {comparison['impact_assessment']}")

    output.append("\nDifferences Found:")
    for diff in comparison["differences"]:
        component = diff["component"]
        issue = diff["issue"].replace("_", " ").title()
        val1 = diff["deal1_value"]
        val2 = diff["deal2_value"]
        impact = diff["impact"].upper()

        output.append(f"  ❌ {component}: {issue}")
        output.append(f"     Deal 1: {val1}")
        output.append(f"     Deal 2: {val2}")
        output.append(f"     Impact: {impact}")

    if comparison["recommendations"]:
        output.append("\nRecommendations:")
        for rec in comparison["recommendations"]:
            output.append(f"  • {rec}")

    return "\n".join(output)
