# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Deal Parity Validation Debug Utilities

Debugging capabilities for deal comparison and parity validation in financial
model development. These utilities provide automated parity checking with
configurable tolerances and root cause analysis.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from performa.deal.results import DealResults

logger = logging.getLogger(__name__)


def validate_deal_parity(
    results1: "DealResults", 
    results2: "DealResults",
    tolerance: Optional[Dict[str, float]] = None,
    label1: str = "Deal 1",
    label2: str = "Deal 2"
) -> Dict[str, Any]:
    """
    Validate parity between two deal analysis results.
    
    This utility performs comprehensive parity validation with configurable
    tolerances and provides actionable insights for achieving parity.
    
    Args:
        results1: First deal analysis results
        results2: Second deal analysis results  
        tolerance: Dict with keys 'irr', 'em', 'equity' specifying max differences
        label1: Label for first deal (e.g., "Composition")
        label2: Label for second deal (e.g., "Pattern")
        
    Returns:
        Dict containing parity validation results with recommendations
        
    Example:
        ```python
        parity = validate_deal_parity(
            comp_results, pattern_results, 
            tolerance={'irr': 0.001, 'em': 0.01, 'equity': 1000},
            label1="Composition", label2="Pattern"
        )
        
        if not parity['passes']:
            print(f"Parity issues: {parity['summary']}")
            for fix in parity['recommended_fixes']:
                print(f"  • {fix}")
        ```
    """
    # Default tolerance
    if tolerance is None:
        tolerance = {
            'irr': 0.01,      # 1% absolute IRR difference
            'em': 0.05,       # 5% absolute EM difference  
            'equity': 50000   # $50K equity difference
        }
    
    # Extract metrics
    metrics1 = results1.deal_metrics
    metrics2 = results2.deal_metrics
    
    # Calculate differences
    irr1 = metrics1.get("levered_irr") or 0
    irr2 = metrics2.get("levered_irr") or 0
    irr_diff = abs(irr1 - irr2)
    
    em1 = metrics1.get("equity_multiple") or 0
    em2 = metrics2.get("equity_multiple") or 0
    em_diff = abs(em1 - em2)
    
    equity1 = metrics1.get("total_investment") or 0
    equity2 = metrics2.get("total_investment") or 0
    equity_diff = abs(equity1 - equity2)
    
    profit1 = metrics1.get("net_profit") or 0
    profit2 = metrics2.get("net_profit") or 0
    profit_diff = abs(profit1 - profit2)
    
    # Check each metric against tolerance
    checks = {
        'irr': {
            'passes': irr_diff < tolerance['irr'],
            'difference': irr_diff,
            'percentage': (irr_diff / max(irr2, 0.001)) * 100,  # Avoid division by zero
            'values': (irr1, irr2),
            'tolerance': tolerance['irr']
        },
        'equity_multiple': {
            'passes': em_diff < tolerance['em'],
            'difference': em_diff,
            'percentage': (em_diff / max(em2, 0.001)) * 100,
            'values': (em1, em2),
            'tolerance': tolerance['em']
        },
        'equity_invested': {
            'passes': equity_diff < tolerance['equity'],
            'difference': equity_diff,
            'percentage': (equity_diff / max(equity2, 1)) * 100,
            'values': (equity1, equity2),
            'tolerance': tolerance['equity']
        }
    }
    
    # Overall parity assessment
    all_pass = all(check['passes'] for check in checks.values())
    
    result = {
        'passes': all_pass,
        'checks': checks,
        'summary': _generate_parity_summary(checks, label1, label2),
        'parity_level': _assess_parity_level(checks),
        'recommended_fixes': _recommend_parity_fixes(checks, all_pass),
        'deal_labels': (label1, label2)
    }
    
    return result


def _generate_parity_summary(checks: Dict[str, Any], label1: str, label2: str) -> str:
    """Generate human-readable parity summary."""
    lines = [f"Parity Validation: {label1} vs {label2}"]
    
    for metric, check in checks.items():
        status = "✅ PASS" if check['passes'] else "❌ FAIL"
        val1, val2 = check['values']
        diff_pct = check['percentage']
        
        if metric == 'irr':
            lines.append(f"  IRR: {val1:.2%} vs {val2:.2%} ({diff_pct:.1f}% diff) {status}")
        elif metric == 'equity_multiple':
            lines.append(f"  EM: {val1:.2f}x vs {val2:.2f}x ({diff_pct:.1f}% diff) {status}")
        elif metric == 'equity_invested':
            lines.append(f"  Equity: ${val1:,.0f} vs ${val2:,.0f} ({diff_pct:.1f}% diff) {status}")
    
    return "\n".join(lines)


def _assess_parity_level(checks: Dict[str, Any]) -> str:
    """Assess overall parity level."""
    max_percentage = max(check['percentage'] for check in checks.values())
    
    if max_percentage < 0.1:
        return "perfect"
    elif max_percentage < 1.0:
        return "excellent"  
    elif max_percentage < 5.0:
        return "good"
    elif max_percentage < 10.0:
        return "acceptable"
    else:
        return "poor"


def _recommend_parity_fixes(checks: Dict[str, Any], all_pass: bool) -> List[str]:
    """Recommend specific fixes for parity issues."""
    if all_pass:
        return ["✅ Parity achieved - no fixes needed"]
    
    recommendations = []
    
    # Check each failing metric
    for metric, check in checks.items():
        if not check['passes']:
            if metric == 'irr' and check['percentage'] > 5:
                recommendations.append("🎯 HIGH PRIORITY: Check exit cap rate and financing terms")
            elif metric == 'irr' and check['percentage'] > 1:
                recommendations.append("🎯 MEDIUM: Check timeline duration and operating assumptions")
            elif metric == 'equity_multiple' and check['percentage'] > 5:
                recommendations.append("🎯 HIGH PRIORITY: Check financing configuration and equity distributions")
            elif metric == 'equity_invested' and check['percentage'] > 10:
                recommendations.append("🎯 HIGH PRIORITY: Check financing auto-sizing and LTV calculations")
    
    # General recommendations
    if any(not check['passes'] for check in checks.values()):
        recommendations.extend([
            "📋 Run compare_deal_configurations() to identify parameter differences",
            "📋 Run compare_deal_timelines() to check timeline alignment", 
            "📋 Run compare_ledger_shapes() to analyze transaction patterns"
        ])
    
    return recommendations


def quick_parity_check(results1: "DealResults", results2: "DealResults") -> bool:
    """
    Quick boolean parity check with default tolerances.
    
    Args:
        results1: First deal results
        results2: Second deal results
        
    Returns:
        True if deals are within reasonable parity, False otherwise
    """
    validation = validate_deal_parity(results1, results2)
    return validation['passes'] and validation['parity_level'] in ['perfect', 'excellent', 'good']


def format_parity_validation(validation: Dict[str, Any]) -> str:
    """Format parity validation results for display."""
    lines = ["🔍 Deal Parity Validation Results"]
    lines.append("=" * 50)
    
    lines.append(validation['summary'])
    lines.append(f"\nOverall Parity Level: {validation['parity_level'].upper()}")
    
    if not validation['passes']:
        lines.append("\nRecommended Fixes:")
        for fix in validation['recommended_fixes']:
            lines.append(f"  {fix}")
    
    return "\n".join(lines)
