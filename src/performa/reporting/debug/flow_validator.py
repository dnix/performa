# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Flow Validation Debug Utilities

Debugging capabilities for validating cash flow reasonableness and aggregate
flow patterns. These utilities provide sanity checks and benchmarking against
industry standards for different deal types.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from performa.deal.results import DealResults

logger = logging.getLogger(__name__)


def validate_flow_reasonableness(
    results: "DealResults",
    deal_type: Optional[str] = None,
    property_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Validate that cash flows are reasonable for the deal type.

    This utility performs sanity checks against industry benchmarks to identify
    flows that may indicate configuration errors or unrealistic assumptions.

    Args:
        results: DealResults to validate
        deal_type: Type of deal ('stabilized', 'development', 'value_add')
        property_type: Type of property ('office', 'multifamily', 'retail')

    Returns:
        Dict containing flow validation results with warnings and recommendations

    Example:
        ```python
        validation = validate_flow_reasonableness(
            results,
            deal_type="stabilized_acquisition",
            property_type="multifamily"
        )

        if validation['has_warnings']:
            print(f"⚠️ Flow issues detected: {validation['summary']}")
            for warning in validation['warnings']:
                print(f"  - {warning['message']}")
        ```
    """
    ledger_queries = results.queries
    ledger_df = ledger_queries.ledger

    validation = {
        "revenue_analysis": _validate_revenue_flows(
            ledger_df, deal_type, property_type
        ),
        "expense_analysis": _validate_expense_flows(
            ledger_df, deal_type, property_type
        ),
        "financing_analysis": _validate_financing_flows(ledger_df, deal_type),
        "capital_analysis": _validate_capital_flows(ledger_df, deal_type),
        "overall_analysis": _validate_overall_flows(results, deal_type),
        "warnings": [],
        "has_warnings": False,
        "summary": "",
        "recommendations": [],
    }

    # Aggregate warnings from all analyses
    for analysis_type in [
        "revenue_analysis",
        "expense_analysis",
        "financing_analysis",
        "capital_analysis",
    ]:
        analysis_warnings = validation[analysis_type].get("warnings", [])
        validation["warnings"].extend(analysis_warnings)

    validation["has_warnings"] = len(validation["warnings"]) > 0

    # Generate summary
    if validation["has_warnings"]:
        validation["summary"] = (
            f"{len(validation['warnings'])} flow reasonableness issues detected"
        )
        validation["recommendations"] = _generate_flow_recommendations(
            validation["warnings"], deal_type
        )
    else:
        validation["summary"] = "All flows appear reasonable for deal type"

    return validation


def validate_aggregate_flows(results: "DealResults") -> Dict[str, Any]:
    """
    Validate aggregate flow patterns and balances.

    This utility checks overall flow balance, category distributions,
    and identifies potential double-counting or missing flows.

    Args:
        results: DealResults to validate

    Returns:
        Dict containing aggregate flow validation results

    Example:
        ```python
        validation = validate_aggregate_flows(results)
        if validation['balance_issues']:
            print(f"⚠️ Balance issues: {validation['balance_summary']}")
        ```
    """
    ledger_queries = results.queries
    ledger_df = ledger_queries.ledger

    # Calculate aggregate flows
    total_inflows = ledger_df[ledger_df["amount"] > 0]["amount"].sum()
    total_outflows = ledger_df[ledger_df["amount"] < 0]["amount"].sum()
    net_flow = total_inflows + total_outflows

    # Category analysis
    category_flows = (
        ledger_df.groupby("category", observed=True)["amount"].sum().to_dict()
    )

    # Sources and uses analysis
    sources = {
        "loan_proceeds": ledger_df[ledger_df["subcategory"] == "Loan Proceeds"][
            "amount"
        ].sum(),
        "equity_contributions": ledger_df[
            ledger_df["subcategory"] == "Equity Contribution"
        ]["amount"].sum(),
        "revenue": category_flows.get("Revenue", 0),
        "exit_proceeds": ledger_df[ledger_df["subcategory"] == "Other"][
            "amount"
        ].sum(),  # Gross sale proceeds
    }

    uses = {
        "purchase_price": abs(
            ledger_df[ledger_df["subcategory"] == "Purchase Price"]["amount"].sum()
        ),
        "operating_expenses": abs(category_flows.get("Expense", 0)),
        "debt_service": abs(
            ledger_df[ledger_df["subcategory"] == "Interest Payment"]["amount"].sum()
        )
        + abs(
            ledger_df[ledger_df["subcategory"] == "Principal Payment"]["amount"].sum()
        ),
        "equity_distributions": abs(
            ledger_df[ledger_df["subcategory"] == "Equity Distribution"]["amount"].sum()
        ),
    }

    # Validation checks
    validation = {
        "flow_summary": {
            "total_inflows": total_inflows,
            "total_outflows": total_outflows,
            "net_flow": net_flow,
        },
        "sources_analysis": sources,
        "uses_analysis": uses,
        "balance_checks": _perform_balance_checks(sources, uses, results.deal_metrics),
        "balance_issues": [],
        "balance_summary": "",
        "recommendations": [],
    }

    # Perform balance validation
    total_sources = sum(v for v in sources.values() if v > 0)
    total_uses = sum(v for v in uses.values() if v > 0)

    balance_diff = abs(total_sources - total_uses)
    balance_ratio = balance_diff / max(total_sources, 1) * 100

    if balance_ratio > 5:  # > 5% imbalance
        validation["balance_issues"].append({
            "issue": "sources_uses_imbalance",
            "sources": total_sources,
            "uses": total_uses,
            "difference": balance_diff,
            "percentage": balance_ratio,
        })

    # Generate summary
    if validation["balance_issues"]:
        validation["balance_summary"] = (
            f"Balance issues detected: {balance_ratio:.1f}% imbalance"
        )
        validation["recommendations"] = [
            "Check for missing cash flows in ledger",
            "Verify equity contribution timing",
            "Validate exit proceeds calculation",
            "Review debt payoff mechanics",
        ]
    else:
        validation["balance_summary"] = "Sources and uses appear balanced"

    return validation


def _validate_revenue_flows(
    ledger_df, deal_type: str, property_type: str
) -> Dict[str, Any]:
    """Validate revenue flows against industry benchmarks."""
    revenue_flows = ledger_df[ledger_df["category"] == "Revenue"]["amount"].sum()

    analysis = {"total_revenue": revenue_flows, "warnings": [], "benchmarks": {}}

    # Add property-specific benchmarks
    if property_type == "multifamily":
        # Typical revenue ranges
        lease_flows = ledger_df[ledger_df["subcategory"] == "Lease"]["amount"].sum()
        analysis["lease_revenue"] = lease_flows

        # Revenue should be positive and substantial
        if revenue_flows <= 0:
            analysis["warnings"].append({
                "type": "no_revenue",
                "message": "No revenue flows detected",
            })
        elif revenue_flows < 100000:  # < $100K total
            analysis["warnings"].append({
                "type": "low_revenue",
                "message": f"Very low revenue: ${revenue_flows:,.0f}",
            })

    return analysis


def _validate_expense_flows(
    ledger_df, deal_type: str, property_type: str
) -> Dict[str, Any]:
    """Validate expense flows against benchmarks."""
    expense_flows = ledger_df[ledger_df["category"] == "Expense"]["amount"].sum()

    analysis = {"total_expenses": abs(expense_flows), "warnings": []}

    # Basic expense validation
    if expense_flows > 0:  # Expenses should be negative
        analysis["warnings"].append({
            "type": "positive_expenses",
            "message": "Expenses recorded as positive flows (should be negative)",
        })

    return analysis


def _validate_financing_flows(ledger_df, deal_type: str) -> Dict[str, Any]:
    """Validate financing flows for internal consistency."""
    financing_flows = ledger_df[ledger_df["category"] == "Financing"]

    loan_proceeds = financing_flows[financing_flows["subcategory"] == "Loan Proceeds"][
        "amount"
    ].sum()
    interest_payments = financing_flows[
        financing_flows["subcategory"] == "Interest Payment"
    ]["amount"].sum()
    principal_payments = financing_flows[
        financing_flows["subcategory"] == "Principal Payment"
    ]["amount"].sum()
    prepayments = financing_flows[financing_flows["subcategory"] == "Prepayment"][
        "amount"
    ].sum()

    analysis = {
        "loan_proceeds": loan_proceeds,
        "interest_payments": abs(interest_payments),
        "principal_payments": abs(principal_payments),
        "prepayments": abs(prepayments),
        "warnings": [],
    }

    # Validation checks
    if loan_proceeds > 0 and abs(interest_payments) == 0:
        analysis["warnings"].append({
            "type": "no_interest_on_loan",
            "message": "Loan proceeds without interest payments detected",
        })

    if (
        loan_proceeds > 0
        and abs(prepayments) == 0
        and deal_type in ["stabilized", "value_add"]
    ):
        analysis["warnings"].append({
            "type": "no_loan_payoff",
            "message": "Loan proceeds without payoff at exit (check disposition)",
        })

    return analysis


def _validate_capital_flows(ledger_df, deal_type: str) -> Dict[str, Any]:
    """Validate capital flows."""
    capital_flows = ledger_df[ledger_df["category"] == "Capital"]

    purchase_price = capital_flows[capital_flows["subcategory"] == "Purchase Price"][
        "amount"
    ].sum()
    exit_proceeds = capital_flows[capital_flows["subcategory"] == "Other"][
        "amount"
    ].sum()  # Usually gross sale

    analysis = {
        "purchase_price": abs(purchase_price),
        "exit_proceeds": exit_proceeds,
        "warnings": [],
    }

    # Basic validation
    if purchase_price == 0:
        analysis["warnings"].append({
            "type": "no_purchase_price",
            "message": "No purchase price recorded in ledger",
        })

    if deal_type in ["stabilized", "value_add"] and exit_proceeds <= 0:
        analysis["warnings"].append({
            "type": "no_exit_proceeds",
            "message": "No exit proceeds recorded (check valuation)",
        })

    return analysis


def _validate_overall_flows(results: "DealResults", deal_type: str) -> Dict[str, Any]:
    """Validate overall deal flow patterns."""
    metrics = results.deal_metrics

    analysis = {
        "irr": metrics.get("levered_irr"),
        "equity_multiple": metrics.get("equity_multiple"),
        "warnings": [],
    }

    # IRR reasonableness by deal type
    levered_irr = metrics.get("levered_irr")
    if deal_type == "stabilized" and levered_irr:
        if levered_irr < 0.05:  # < 5%
            analysis["warnings"].append({
                "type": "low_irr",
                "message": f"Low IRR for stabilized deal: {levered_irr:.1%}",
            })
        elif levered_irr > 0.40:  # > 40%
            analysis["warnings"].append({
                "type": "unrealistic_irr",
                "message": f"Unrealistically high IRR: {levered_irr:.1%}",
            })

    # Equity multiple reasonableness
    equity_multiple = metrics.get("equity_multiple")
    if equity_multiple and equity_multiple < 0.5:
        analysis["warnings"].append({
            "type": "low_equity_multiple",
            "message": f"Low equity multiple: {equity_multiple:.2f}x",
        })
    elif equity_multiple and equity_multiple > 10.0:
        analysis["warnings"].append({
            "type": "high_equity_multiple",
            "message": f"Very high equity multiple: {equity_multiple:.2f}x",
        })

    return analysis


def _perform_balance_checks(
    sources: Dict[str, float], uses: Dict[str, float], metrics: Any
) -> Dict[str, Any]:
    """Perform balance checks between sources and uses."""
    total_sources = sum(v for v in sources.values() if v > 0)
    total_uses = sum(v for v in uses.values() if v > 0)

    return {
        "total_sources": total_sources,
        "total_uses": total_uses,
        "difference": total_sources - total_uses,
        "balance_ratio": total_sources / max(total_uses, 1),
        "expected_difference": getattr(metrics, "net_profit", 0),
        "balance_check_passes": abs(
            (total_sources - total_uses) - getattr(metrics, "net_profit", 0)
        )
        < 10000,
    }


def _generate_flow_recommendations(
    warnings: List[Dict[str, Any]], deal_type: str
) -> List[str]:
    """Generate recommendations based on flow warnings."""
    recommendations = []

    warning_types = [w["type"] for w in warnings]

    if "no_revenue" in warning_types or "low_revenue" in warning_types:
        recommendations.append("🔍 Check asset rent roll and occupancy assumptions")

    if "no_purchase_price" in warning_types:
        recommendations.append("🚨 CRITICAL: Verify acquisition terms are configured")

    if "unrealistic_irr" in warning_types:
        recommendations.append("🔍 Validate exit cap rate and financing assumptions")

    if "no_interest_on_loan" in warning_types:
        recommendations.append(
            "🔍 Check debt facility configuration and compute_cf execution"
        )

    return recommendations
