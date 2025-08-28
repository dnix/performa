# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Ledger semantic analysis and validation for financial model debugging.

This module provides comprehensive ledger analysis capabilities to identify:
- Cash flow patterns and anomalies
- Timeline validation issues
- Sign and magnitude problems
- Balance and consistency checks

Essential for validating that financial models produce mathematically sound
and institutionally reasonable cash flows.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from ...core.ledger import Ledger


def analyze_ledger_semantically(ledger: Ledger) -> Dict[str, Any]:
    """
    Comprehensive semantic analysis of ledger for debugging.

    Provides structured analysis to identify:
    - Cash flow patterns and anomalies
    - Timeline validation issues
    - Sign and magnitude problems
    - Balance and consistency checks

    Args:
        ledger: Ledger object to analyze

    Returns:
        Structured analysis dictionary with multiple analysis dimensions

    Example:
        ```python
        analysis = analyze_ledger_semantically(ledger)
        print(f"Revenue total: ${analysis['by_category']['Revenue']['total']:,.0f}")
        print(f"Timeline issues: {analysis['anomalies']['timeline']}")
        ```
    """
    # Get ledger DataFrame
    if hasattr(ledger, "_to_dataframe"):
        df = ledger._to_dataframe()
    elif isinstance(ledger, pd.DataFrame):
        df = ledger
    else:
        # Try to get DataFrame from ledger object
        df = getattr(ledger, "df", None) or getattr(ledger, "data", None)
        if df is None:
            return {
                "error": "Could not extract DataFrame from ledger",
                "ledger_type": type(ledger).__name__,
            }

    if df.empty:
        return {"error": "Ledger is empty", "record_count": 0}

    analysis = {
        "record_count": len(df),
        "date_range": {
            "start": df["date"].min(),
            "end": df["date"].max(),
            "span_months": None,
        },
        "by_category": {},
        "by_timeline": {},
        "anomalies": {},
        "balance_checks": {},
        "summary_stats": {},
    }

    # Calculate date span
    if pd.notnull(df["date"].min()) and pd.notnull(df["date"].max()):
        date_span = df["date"].max() - df["date"].min()
        analysis["date_range"]["span_months"] = (
            date_span.days / 30.44
        )  # Average month length

    # Analysis by financial category
    analysis["by_category"] = _analyze_by_category(df)

    # Analysis by timeline phases
    analysis["by_timeline"] = _analyze_by_timeline(df)

    # Anomaly detection
    analysis["anomalies"] = _detect_anomalies(df)

    # Balance validation
    analysis["balance_checks"] = _validate_balances(df)

    # Summary statistics
    analysis["summary_stats"] = _calculate_summary_stats(df)

    return analysis


def _analyze_by_category(df: pd.DataFrame) -> Dict[str, Any]:
    """Analyze ledger entries by financial category."""
    if "category" not in df.columns:
        return {"error": "No category column in ledger"}

    category_summary = {}

    for category in df["category"].unique():
        cat_data = df[df["category"] == category]

        category_summary[category] = {
            "total": cat_data["amount"].sum(),
            "count": len(cat_data),
            "avg_amount": cat_data["amount"].mean(),
            "date_range": {
                "first": cat_data["date"].min(),
                "last": cat_data["date"].max(),
            },
            "subcategories": {},
        }

        # Subcategory breakdown
        if "subcategory" in df.columns:
            for subcat in cat_data["subcategory"].unique():
                subcat_data = cat_data[cat_data["subcategory"] == subcat]
                category_summary[category]["subcategories"][subcat] = {
                    "total": subcat_data["amount"].sum(),
                    "count": len(subcat_data),
                }

    return category_summary


def _analyze_by_timeline(df: pd.DataFrame) -> Dict[str, Any]:
    """Analyze ledger entries by timeline phases."""
    timeline_analysis = {"by_year": {}, "by_month": {}, "cumulative_by_year": {}}

    # Convert dates for grouping
    df["year"] = pd.to_datetime(df["date"]).dt.year
    df["month"] = pd.to_datetime(df["date"]).dt.to_period("M")

    # Yearly analysis
    yearly = df.groupby("year")["amount"].sum()
    timeline_analysis["by_year"] = yearly.to_dict()

    # Monthly analysis (first 24 months only to avoid clutter)
    monthly = df.groupby("month")["amount"].sum()
    timeline_analysis["by_month"] = dict(monthly.head(24))

    # Cumulative by year
    cumulative = yearly.cumsum()
    timeline_analysis["cumulative_by_year"] = cumulative.to_dict()

    return timeline_analysis


def _detect_anomalies(df: pd.DataFrame) -> Dict[str, List[str]]:
    """Detect potential issues in ledger data."""
    warnings = {"magnitude": [], "timing": [], "sign": [], "balance": []}

    # Magnitude checks
    amounts = df["amount"].abs()
    if amounts.max() > amounts.median() * 100:
        warnings["magnitude"].append(
            f"Extreme outlier: ${amounts.max():,.0f} is {amounts.max() / amounts.median():.0f}x median"
        )

    # Sign checks (basic heuristics)
    if "category" in df.columns and "subcategory" in df.columns:
        # Revenue should generally be positive
        revenue_negative = df[(df["category"] == "Revenue") & (df["amount"] < 0)]
        if len(revenue_negative) > 0:
            warnings["sign"].append(
                f"Negative revenue entries: {len(revenue_negative)} records"
            )

        # Expenses should generally be negative
        expense_positive = df[(df["category"] == "Expense") & (df["amount"] > 0)]
        if len(expense_positive) > 0:
            warnings["sign"].append(
                f"Positive expense entries: {len(expense_positive)} records"
            )

    # Timeline checks
    if "date" in df.columns:
        # Check for future dates (potential config error)
        future_dates = df[pd.to_datetime(df["date"]) > datetime.now()]
        if len(future_dates) > 0:
            max_future = pd.to_datetime(future_dates["date"]).max()
            warnings["timing"].append(
                f"Future dates detected (latest: {max_future.date()})"
            )

        # Check for entries spanning > 20 years (potential config error)
        date_span_years = (
            pd.to_datetime(df["date"]).max() - pd.to_datetime(df["date"]).min()
        ).days / 365
        if date_span_years > 20:
            warnings["timing"].append(
                f"Very long timeline: {date_span_years:.1f} years"
            )

    return warnings


def _validate_balances(df: pd.DataFrame) -> Dict[str, Any]:
    """Validate mathematical balances in ledger."""
    balances = {
        "total_net_flow": df["amount"].sum(),
        "positive_flows": df[df["amount"] > 0]["amount"].sum(),
        "negative_flows": df[df["amount"] < 0]["amount"].sum(),
    }

    # Check if net flow is close to zero (should be for closed deals)
    balances["net_flow_close_to_zero"] = abs(balances["total_net_flow"]) < 1000
    balances["balance_ratio"] = (
        abs(balances["negative_flows"] / balances["positive_flows"])
        if balances["positive_flows"] > 0
        else None
    )

    return balances


def _calculate_summary_stats(df: pd.DataFrame) -> Dict[str, Any]:
    """Calculate high-level summary statistics."""
    stats = {
        "total_records": len(df),
        "total_amount": df["amount"].sum(),
        "amount_stats": {
            "mean": df["amount"].mean(),
            "median": df["amount"].median(),
            "std": df["amount"].std(),
            "min": df["amount"].min(),
            "max": df["amount"].max(),
        },
    }

    # Category counts
    if "category" in df.columns:
        stats["category_counts"] = df["category"].value_counts().to_dict()

    return stats


def format_ledger_analysis(
    analysis: Dict[str, Any], title: str = "Ledger Analysis"
) -> str:
    """
    Format ledger analysis as readable text.

    Args:
        analysis: Analysis dictionary from analyze_ledger_semantically()
        title: Title for the analysis output

    Returns:
        Formatted string suitable for printing or logging
    """
    if "error" in analysis:
        return f"# {title}\n\n❌ Error: {analysis['error']}"

    output = [f"# {title}\n"]

    # Basic info
    output.append(f"**Records**: {analysis['record_count']:,}")
    if analysis["date_range"]["span_months"]:
        output.append(
            f"**Timeline**: {analysis['date_range']['span_months']:.1f} months"
        )
    output.append("")

    # Category summary
    if "by_category" in analysis:
        output.append("## Cash Flow by Category")
        output.append("| Category | Total Amount | Count | Avg Amount |")
        output.append("|----------|--------------|-------|------------|")

        for category, data in analysis["by_category"].items():
            if isinstance(data, dict) and "total" in data:
                output.append(
                    f"| {category} | ${data['total']:,.0f} | {data['count']} | ${data['avg_amount']:,.0f} |"
                )

        output.append("")

    # Anomaly warnings
    if "anomalies" in analysis:
        anomalies = analysis["anomalies"]
        has_warnings = any(len(warnings) > 0 for warnings in anomalies.values())

        if has_warnings:
            output.append("## ⚠️ Anomalies Detected")
            for category, warnings in anomalies.items():
                if warnings:
                    output.append(f"### {category.title()} Issues")
                    for warning in warnings:
                        output.append(f"- {warning}")
            output.append("")

    # Balance validation
    if "balance_checks" in analysis:
        balances = analysis["balance_checks"]
        output.append("## Balance Validation")
        output.append(f"- **Net Flow**: ${balances['total_net_flow']:,.0f}")
        output.append(f"- **Positive Flows**: ${balances['positive_flows']:,.0f}")
        output.append(f"- **Negative Flows**: ${balances['negative_flows']:,.0f}")

        if balances["net_flow_close_to_zero"]:
            output.append("- **Balance Check**: ✅ Net flow ~$0 (good)")
        else:
            output.append(
                f"- **Balance Check**: ⚠️ Net flow ${balances['total_net_flow']:,.0f}"
            )

        output.append("")

    return "\n".join(output)


def ledger_sanity_check(
    ledger, expected_returns: Optional[Dict[str, float]] = None
) -> List[str]:
    """
    Quick sanity check for common ledger issues.

    Args:
        ledger: Ledger to check
        expected_returns: Optional dict with expected IRR/EM for validation
            e.g., {"irr": 0.12, "equity_multiple": 1.8}

    Returns:
        List of warning/error messages
    """
    warnings = []
    analysis = analyze_ledger_semantically(ledger)

    # Check for empty ledger
    if analysis.get("record_count", 0) == 0:
        warnings.append("❌ CRITICAL: Ledger is empty")
        return warnings

    # Check anomalies
    for category, issues in analysis.get("anomalies", {}).items():
        for issue in issues:
            warnings.append(f"⚠️ {category.title()}: {issue}")

    # Balance validation
    balance_checks = analysis.get("balance_checks", {})
    if not balance_checks.get("net_flow_close_to_zero", True):
        net_flow = balance_checks.get("total_net_flow", 0)
        warnings.append(f"⚠️ Balance: Net flow ${net_flow:,.0f} (should be ~$0)")

    # Expected returns validation
    if expected_returns:
        # We'd need to calculate actual returns from ledger here
        # This would require implementing IRR calculation from ledger cash flows
        pass  # TODO: Implement return calculation validation

    if not warnings:
        warnings.append("✅ No obvious ledger issues detected")

    return warnings
