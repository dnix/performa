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

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import pandas as pd

from ...core.ledger import Ledger

if TYPE_CHECKING:
    from ...deal.results import DealResults


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
    # DuckDB-only path: require active ledger connection and fail fast otherwise
    con, table = ledger.get_query_connection()
    df = con.execute(f"SELECT * FROM {table} ORDER BY date").df()

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


def validate_valuation_exclusion(
    df: pd.DataFrame, method_name: str = "unknown"
) -> None:
    """
    Validate that a DataFrame properly excludes valuation entries.

    This utility function helps prevent consistency issues where valuation
    entries (non-cash analytical snapshots) get included in cash flow
    calculations, which can cause ledger imbalances.

    Args:
        df: DataFrame that should have valuation entries excluded
        method_name: Name of the calling method for error reporting

    Raises:
        ValueError: If valuation entries are found in the DataFrame

    Example:
        # In any new reporting/analysis function:
        filtered_df = ledger[ledger["flow_purpose"] != "Valuation"]
        validate_valuation_exclusion(filtered_df, "my_new_analysis_function")
    """
    if "flow_purpose" in df.columns:
        valuation_count = (df["flow_purpose"] == "Valuation").sum()
        if valuation_count > 0:
            valuation_total = df[df["flow_purpose"] == "Valuation"]["amount"].sum()
            raise ValueError(
                f"Consistency error in {method_name}: Found {valuation_count} "
                f"valuation entries totaling ${valuation_total:,.0f}. These non-cash "
                f"analytical snapshots should be excluded using: "
                f"df[df['flow_purpose'] != 'Valuation']"
            )


def _validate_balances(df: pd.DataFrame) -> Dict[str, Any]:
    """Validate mathematical balances in ledger (excluding non-cash valuation entries).

    Important: Always exclude flow_purpose="Valuation" entries from balance calculations.
    Valuation entries are non-cash analytical snapshots recorded for audit trail and API
    consistency, but they represent property appraisals, not actual cash flows.

    Including them can create ledger imbalances that don't reflect the actual financial
    position. This exclusion pattern should be consistent across all reporting, analysis,
    and cash flow calculation methods.

    See also: LedgerQueries.project_cash_flow(), equity_partner_flows(), operational_cash_flow()
    which all use this same exclusion pattern for consistency.
    """
    # Exclude non-cash valuation entries from balance calculation
    # This maintains consistency with all cash flow query methods in LedgerQueries
    cash_flow_df = (
        df[df["flow_purpose"] != "Valuation"] if "flow_purpose" in df.columns else df
    )

    balances = {
        "total_net_flow": cash_flow_df["amount"].sum(),
        "positive_flows": cash_flow_df[cash_flow_df["amount"] > 0]["amount"].sum(),
        "negative_flows": cash_flow_df[cash_flow_df["amount"] < 0]["amount"].sum(),
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
        warnings.append("❌ Warning: Ledger is empty")
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


def generate_ledger_pivot_analysis(
    ledger_df: pd.DataFrame, top_n: int = 15
) -> Dict[str, Any]:
    """
    Generate comprehensive pivot table analysis similar to notebook debug utilities.

    Provides semantic groupings and summaries for deep dive analysis:
    - Category-level aggregation
    - Category + Subcategory breakdown
    - Semantic summaries (construction costs, debt flows, etc.)
    - Key financial metrics and validation

    Args:
        ledger_df: Ledger DataFrame with transaction records
        top_n: Number of top entries to show in detailed breakdowns

    Returns:
        Dictionary with comprehensive pivot analysis

    Example:
        ```python
        pivot_analysis = generate_ledger_pivot_analysis(results.ledger_df)
        print(f"Construction costs: ${pivot_analysis['semantic_totals']['construction_costs']:,.0f}")
        print(f"Debt service: ${pivot_analysis['semantic_totals']['debt_service']:,.0f}")
        ```
    """
    analysis = {}

    # Basic stats
    analysis["basic_stats"] = {
        "total_entries": len(ledger_df),
        "date_range": {
            "start": ledger_df["date"].min() if not ledger_df.empty else None,
            "end": ledger_df["date"].max() if not ledger_df.empty else None,
        },
        "total_amount": ledger_df["amount"].sum(),
    }

    # Category-level aggregation
    try:
        category_pivot = (
            ledger_df.groupby("category", observed=True)["amount"]
            .agg(["count", "sum"])
            .round(0)
        )
        analysis["by_category"] = {}
        for cat, row in category_pivot.iterrows():
            analysis["by_category"][str(cat)] = {
                "entries": int(row["count"]),
                "total": float(row["sum"]),
                "percentage": float(row["sum"] / ledger_df["amount"].sum() * 100)
                if ledger_df["amount"].sum() != 0
                else 0,
            }
    except Exception as e:
        analysis["by_category"] = {"error": str(e)}

    # Category + Subcategory detailed breakdown (top N by absolute value)
    try:
        subcat_pivot = (
            ledger_df.groupby(["category", "subcategory"], observed=True)["amount"]
            .agg(["count", "sum"])
            .round(0)
        )
        subcat_pivot["abs_sum"] = abs(subcat_pivot["sum"])
        subcat_pivot_sorted = subcat_pivot.sort_values("abs_sum", ascending=False).head(
            top_n
        )

        analysis["by_category_subcategory"] = {}
        for (cat, subcat), row in subcat_pivot_sorted.iterrows():
            key = f"{cat}|{subcat}"
            analysis["by_category_subcategory"][key] = {
                "entries": int(row["count"]),
                "total": float(row["sum"]),
                "abs_total": float(row["abs_sum"]),
            }
    except Exception as e:
        analysis["by_category_subcategory"] = {"error": str(e)}

    # Semantic summaries (key financial metrics)
    semantic_totals = {}
    try:
        # Construction costs
        construction_mask = ledger_df["subcategory"].str.contains(
            "Construction|Hard Costs|Soft Costs", case=False, na=False
        )
        semantic_totals["construction_costs"] = abs(
            ledger_df[construction_mask]["amount"].sum()
        )

        # Acquisition costs
        acquisition_mask = ledger_df["subcategory"].isin([
            "Purchase Price",
            "Closing Costs",
            "Transaction Costs",
        ])
        semantic_totals["acquisition_costs"] = abs(
            ledger_df[acquisition_mask]["amount"].sum()
        )

        # Disposition proceeds
        disposition_mask = (ledger_df["subcategory"] == "Other") & (
            ledger_df["amount"] > 0
        )
        semantic_totals["disposition_proceeds"] = ledger_df[disposition_mask][
            "amount"
        ].sum()

        # Debt flows
        semantic_totals["debt_proceeds"] = ledger_df[
            ledger_df["subcategory"] == "Loan Proceeds"
        ]["amount"].sum()
        debt_service_mask = ledger_df["subcategory"].isin([
            "Interest Payment",
            "Principal Payment",
        ])
        semantic_totals["debt_service"] = abs(
            ledger_df[debt_service_mask]["amount"].sum()
        )

        # Equity flows
        semantic_totals["equity_contributions"] = ledger_df[
            ledger_df["subcategory"] == "Equity Contribution"
        ]["amount"].sum()
        semantic_totals["equity_distributions"] = abs(
            ledger_df[ledger_df["subcategory"] == "Equity Distribution"]["amount"].sum()
        )

        # NOI and OpEx
        noi_mask = ledger_df["item_name"].str.contains("NOI", case=False, na=False)
        semantic_totals["total_noi"] = ledger_df[noi_mask]["amount"].sum()

        opex_mask = ledger_df["subcategory"] == "OpEx"
        semantic_totals["total_opex"] = abs(ledger_df[opex_mask]["amount"].sum())

    except Exception as e:
        semantic_totals["error"] = str(e)

    analysis["semantic_totals"] = semantic_totals

    # Key ratios and validation metrics
    validation_metrics = {}
    try:
        # Debt service coverage (if we have both NOI and debt service)
        if (
            semantic_totals.get("total_noi", 0) > 0
            and semantic_totals.get("debt_service", 0) > 0
        ):
            validation_metrics["dscr_implied"] = (
                semantic_totals["total_noi"] / semantic_totals["debt_service"]
            )

        # Equity multiple implied (distributions / contributions)
        if semantic_totals.get("equity_contributions", 0) > 0:
            validation_metrics["equity_multiple_implied"] = (
                semantic_totals.get("equity_distributions", 0)
                / semantic_totals["equity_contributions"]
            )

        # Net equity flow
        validation_metrics["net_equity_flow"] = semantic_totals.get(
            "equity_distributions", 0
        ) - semantic_totals.get("equity_contributions", 0)

        # Project cost total
        validation_metrics["total_project_cost"] = semantic_totals.get(
            "acquisition_costs", 0
        ) + semantic_totals.get("construction_costs", 0)

    except Exception as e:
        validation_metrics["error"] = str(e)

    analysis["validation_metrics"] = validation_metrics

    return analysis


def analyze_cash_flow_timeline(
    results: "DealResults", deal_archetype: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analyze cash flow sign patterns against deal timeline to validate timing expectations.

    This debugging utility examines when cash flows flip between positive/negative
    and validates against typical deal phases:
    - Construction/Development: Negative UCF (capital outflows)
    - Operations: Positive UCF (NOI inflows)
    - Exit: Large positive UCF (disposition proceeds)
    - LCF: Similar pattern but modified by debt service

    Args:
        results: DealResults object containing cash flows and timeline
        deal_archetype: Optional archetype hint ("development", "stabilized", "value_add")

    Returns:
        Dictionary with timeline analysis, sign flip validation, and warnings

    Example:
        ```python
        timeline_analysis = analyze_cash_flow_timeline(results, "development")
        if timeline_analysis['warnings']:
            print("⚠️  Timeline issues detected:")
            for warning in timeline_analysis['warnings']:
                print(f"  - {warning}")
        ```
    """
    try:
        # Get cash flows
        ucf = results.unlevered_cash_flow
        lcf = results.levered_cash_flow

        # Get basic timeline info
        timeline_start = ucf.index[0] if len(ucf) > 0 else None
        timeline_end = ucf.index[-1] if len(ucf) > 0 else None
        total_periods = len(ucf)

        analysis = {
            "basic_info": {
                "start_period": timeline_start,
                "end_period": timeline_end,
                "total_periods": total_periods,
                "deal_archetype": deal_archetype,
            },
            "ucf_analysis": _analyze_cash_flow_signs(ucf, "UCF"),
            "lcf_analysis": _analyze_cash_flow_signs(lcf, "LCF"),
            "sign_flip_analysis": {},
            "timeline_validation": {},
            "warnings": [],
            "insights": [],
        }

        # Analyze sign flips
        analysis["sign_flip_analysis"] = _analyze_sign_flips(ucf, lcf)

        # Timeline-based validation
        analysis["timeline_validation"] = _validate_timeline_expectations(
            ucf, lcf, deal_archetype, timeline_start, timeline_end
        )

        # Generate warnings and insights
        _generate_timeline_warnings(analysis)

        return analysis

    except Exception as e:
        return {
            "error": f"Cash flow timeline analysis failed: {str(e)}",
            "basic_info": {"deal_archetype": deal_archetype},
            "warnings": [f"Analysis failed: {str(e)}"],
        }


def _analyze_cash_flow_signs(cash_flow: pd.Series, flow_name: str) -> Dict[str, Any]:
    """Analyze sign patterns in a cash flow series."""
    if cash_flow.empty:
        return {"error": f"{flow_name} is empty"}

    positive_periods = cash_flow > 0
    negative_periods = cash_flow < 0
    zero_periods = cash_flow == 0

    return {
        "total_flow": float(cash_flow.sum()),
        "positive_periods": int(positive_periods.sum()),
        "negative_periods": int(negative_periods.sum()),
        "zero_periods": int(zero_periods.sum()),
        "first_period_sign": "positive"
        if cash_flow.iloc[0] > 0
        else "negative"
        if cash_flow.iloc[0] < 0
        else "zero",
        "last_period_sign": "positive"
        if cash_flow.iloc[-1] > 0
        else "negative"
        if cash_flow.iloc[-1] < 0
        else "zero",
        "first_period_value": float(cash_flow.iloc[0]),
        "last_period_value": float(cash_flow.iloc[-1]),
        "max_positive": float(cash_flow.max()),
        "max_negative": float(cash_flow.min()),
        "avg_positive": float(cash_flow[positive_periods].mean())
        if positive_periods.any()
        else 0.0,
        "avg_negative": float(cash_flow[negative_periods].mean())
        if negative_periods.any()
        else 0.0,
    }


def _analyze_sign_flips(ucf: pd.Series, lcf: pd.Series) -> Dict[str, Any]:
    """Analyze when cash flows flip between positive and negative."""
    sign_flips = {}

    for flow_name, flow in [("UCF", ucf), ("LCF", lcf)]:
        if flow.empty:
            sign_flips[flow_name] = {"error": "Empty cash flow"}
            continue

        # Find sign changes
        signs = flow.apply(lambda x: 1 if x > 0 else -1 if x < 0 else 0)
        sign_changes = signs.diff() != 0
        flip_periods = flow.index[sign_changes].tolist()

        # Identify major phases
        phases = []
        current_sign = signs.iloc[0]
        phase_start = flow.index[0]

        for i in range(1, len(signs)):
            if signs.iloc[i] != current_sign:
                phases.append({
                    "start": phase_start,
                    "end": flow.index[i - 1],
                    "sign": "positive"
                    if current_sign > 0
                    else "negative"
                    if current_sign < 0
                    else "zero",
                    "periods": i - flow.index.get_loc(phase_start),
                    "total_flow": float(
                        flow.iloc[flow.index.get_loc(phase_start) : i].sum()
                    ),
                })
                current_sign = signs.iloc[i]
                phase_start = flow.index[i]

        # Add final phase
        if len(flow) > 0:
            phases.append({
                "start": phase_start,
                "end": flow.index[-1],
                "sign": "positive"
                if current_sign > 0
                else "negative"
                if current_sign < 0
                else "zero",
                "periods": len(flow) - flow.index.get_loc(phase_start),
                "total_flow": float(flow.iloc[flow.index.get_loc(phase_start) :].sum()),
            })

        sign_flips[flow_name] = {
            "flip_periods": flip_periods,
            "total_flips": len(flip_periods)
            - 1,  # First one is always a "change" from nothing
            "phases": phases,
        }

    return sign_flips


def _validate_timeline_expectations(
    ucf: pd.Series,
    lcf: pd.Series,
    deal_archetype: Optional[str],
    timeline_start,
    timeline_end,
) -> Dict[str, Any]:
    """Validate cash flow patterns against expected timeline phases."""
    validation = {
        "construction_phase": {},
        "operational_phase": {},
        "exit_phase": {},
        "overall_pattern": {},
    }

    if ucf.empty:
        return {"error": "Cannot validate empty cash flows"}

    total_periods = len(ucf)

    # Estimate deal phases based on archetype and patterns
    if deal_archetype == "development":
        # Development: typically 12-36 months construction, then operations, then exit
        construction_periods = min(36, total_periods // 3)
        exit_periods = max(1, total_periods // 10)  # Last 10% for exit
    elif deal_archetype == "stabilized":
        # Stabilized: immediate operations, maybe minimal initial CapEx
        construction_periods = max(1, total_periods // 12)  # Minimal initial period
        exit_periods = max(1, total_periods // 10)
    else:
        # Generic/unknown: make reasonable assumptions
        construction_periods = min(24, total_periods // 4)
        exit_periods = max(1, total_periods // 8)

    operational_periods = total_periods - construction_periods - exit_periods

    # Analyze each phase
    if construction_periods > 0:
        construction_ucf = ucf.iloc[:construction_periods]
        validation["construction_phase"] = {
            "expected_sign": "negative",
            "actual_sign": "positive" if construction_ucf.mean() > 0 else "negative",
            "average_flow": float(construction_ucf.mean()),
            "total_flow": float(construction_ucf.sum()),
            "periods_analyzed": construction_periods,
            "meets_expectation": construction_ucf.mean() < 0,
        }

    if operational_periods > 0:
        operational_ucf = ucf.iloc[
            construction_periods : construction_periods + operational_periods
        ]
        validation["operational_phase"] = {
            "expected_sign": "positive",
            "actual_sign": "positive" if operational_ucf.mean() > 0 else "negative",
            "average_flow": float(operational_ucf.mean()),
            "total_flow": float(operational_ucf.sum()),
            "periods_analyzed": operational_periods,
            "meets_expectation": operational_ucf.mean() > 0,
        }

    if exit_periods > 0:
        exit_ucf = ucf.iloc[-exit_periods:]
        validation["exit_phase"] = {
            "expected_sign": "large_positive",
            "actual_sign": "large_positive"
            if exit_ucf.max() > ucf.std() * 2
            else "positive"
            if exit_ucf.mean() > 0
            else "negative",
            "max_flow": float(exit_ucf.max()),
            "total_flow": float(exit_ucf.sum()),
            "periods_analyzed": exit_periods,
            "meets_expectation": exit_ucf.max()
            > ucf.std() * 2,  # Exit should be materially larger
        }

    # Overall pattern validation
    validation["overall_pattern"] = {
        "total_ucf_positive": ucf.sum() > 0,
        "reasonable_progression": _check_reasonable_progression(ucf, deal_archetype),
        "lcf_follows_ucf": abs(ucf.sum() - lcf.sum())
        < abs(ucf.sum()) * 0.5,  # LCF shouldn't be wildly different
    }

    return validation


def _check_reasonable_progression(
    ucf: pd.Series, deal_archetype: Optional[str]
) -> bool:
    """Check if cash flow progression makes sense."""
    if ucf.empty or len(ucf) < 3:
        return True  # Too short to evaluate

    # For development deals, expect negative early, positive later
    if deal_archetype == "development":
        early_periods = ucf.iloc[: len(ucf) // 3].mean()
        later_periods = ucf.iloc[len(ucf) // 2 :].mean()
        return early_periods < 0 and later_periods > 0

    # For stabilized deals, expect mostly positive with exit bump
    elif deal_archetype == "stabilized":
        middle_periods = ucf.iloc[1:-2].mean() if len(ucf) > 3 else ucf.mean()
        return middle_periods > 0

    # Generic: just check that it's not all negative or all positive
    all_positive = (ucf > 0).all()
    all_negative = (ucf < 0).all()
    return not (all_positive or all_negative)


def _generate_timeline_warnings(analysis: Dict[str, Any]) -> None:
    """Generate warnings based on timeline analysis."""
    warnings = []
    insights = []

    # Check UCF patterns
    ucf_analysis = analysis.get("ucf_analysis", {})
    if ucf_analysis and not ucf_analysis.get("error"):
        # Warning: First period positive for development
        if (
            analysis["basic_info"].get("deal_archetype") == "development"
            and ucf_analysis.get("first_period_sign") == "positive"
        ):
            warnings.append(
                "Development UCF positive in first period - unusual, expect negative construction costs"
            )

        # Warning: Last period negative
        if (
            ucf_analysis.get("last_period_sign") == "negative"
            and abs(ucf_analysis.get("last_period_value", 0)) > 1_000_000
        ):
            warnings.append(
                f"UCF strongly negative in final period (${ucf_analysis.get('last_period_value', 0):,.0f}) - missing exit proceeds?"
            )

        # Warning: No positive periods
        if ucf_analysis.get("positive_periods", 0) == 0:
            warnings.append(
                "UCF never positive - no operating cash flows or exit proceeds detected"
            )

    # Check phase validation
    timeline_validation = analysis.get("timeline_validation", {})
    for phase_name, phase_data in timeline_validation.items():
        if isinstance(phase_data, dict) and "meets_expectation" in phase_data:
            if not phase_data["meets_expectation"]:
                expected = phase_data.get("expected_sign", "unknown")
                actual = phase_data.get("actual_sign", "unknown")
                warnings.append(
                    f"{phase_name.title()}: Expected {expected} cash flows, got {actual}"
                )

    # Generate insights
    sign_flips = analysis.get("sign_flip_analysis", {})
    if "UCF" in sign_flips and "phases" in sign_flips["UCF"]:
        phases = sign_flips["UCF"]["phases"]
        if len(phases) >= 3:
            insights.append(
                f"UCF shows {len(phases)} distinct phases: {' → '.join([p['sign'] for p in phases])}"
            )
        elif len(phases) == 2:
            insights.append(
                f"UCF shows 2-phase pattern: {phases[0]['sign']} then {phases[1]['sign']}"
            )

    # Add warnings and insights to analysis
    analysis["warnings"].extend(warnings)
    analysis["insights"].extend(insights)
