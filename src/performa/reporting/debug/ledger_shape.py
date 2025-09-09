# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Ledger Shape Analysis Debug Utilities

Debugging capabilities for ledger structure analysis in financial model validation.
These utilities identify transaction count differences, flow patterns, and 
structural mismatches between ledgers.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict

import pandas as pd

if TYPE_CHECKING:
    from performa.deal.results import DealAnalysisResult

logger = logging.getLogger(__name__)


def analyze_ledger_shape(results: "DealAnalysisResult") -> Dict[str, Any]:
    """
    Analyze the shape and structure of a ledger for debugging.
    
    This utility provides comprehensive analysis of ledger transaction patterns,
    counts, timing, and flow characteristics to identify potential issues.
    
    Args:
        results: DealAnalysisResult containing ledger data
        
    Returns:
        Dict containing comprehensive ledger shape analysis
        
    Example:
        ```python
        shape = analyze_ledger_shape(results)
        print(f"Total transactions: {shape['transaction_summary']['total_count']}")
        if shape['warnings']:
            print(f"⚠️ Issues detected: {shape['warnings']}")
        ```
    """
    # Get ledger data
    ledger_queries = results.asset_analysis.get_ledger_queries()
    ledger_df = ledger_queries.ledger
    
    analysis = {
        'transaction_summary': _analyze_transaction_counts(ledger_df),
        'flow_summary': _analyze_flow_patterns(ledger_df),
        'timeline_coverage': _analyze_timeline_coverage(ledger_df),
        'balance_analysis': _analyze_balance_patterns(ledger_df),
        'warnings': [],
        'recommendations': []
    }
    
    # Generate warnings and recommendations
    _generate_shape_warnings(analysis)
    
    return analysis


def compare_ledger_shapes(results1: "DealAnalysisResult", results2: "DealAnalysisResult") -> Dict[str, Any]:
    """
    Compare ledger shapes between two deal analysis results.
    
    This utility identifies differences in transaction patterns that can help
    diagnose why two supposedly equivalent deals produce different results.
    
    Args:
        results1: First deal analysis results
        results2: Second deal analysis results
        
    Returns:
        Dict containing shape comparison with difference analysis
        
    Example:
        ```python
        comparison = compare_ledger_shapes(comp_results, pattern_results)
        if comparison['significant_differences']:
            print(f"Root cause: {comparison['likely_cause']}")
        ```
    """
    shape1 = analyze_ledger_shape(results1)
    shape2 = analyze_ledger_shape(results2)
    
    ledger1 = results1.asset_analysis.get_ledger_queries().ledger
    ledger2 = results2.asset_analysis.get_ledger_queries().ledger
    
    comparison = {
        'shape1': shape1,
        'shape2': shape2,
        'transaction_count_diff': _compare_transaction_counts(ledger1, ledger2),
        'flow_amount_diff': _compare_flow_amounts(ledger1, ledger2),
        'significant_differences': [],
        'likely_cause': '',
        'recommendations': []
    }
    
    # Identify significant differences
    _identify_significant_differences(comparison)
    
    return comparison


def _analyze_transaction_counts(ledger_df: pd.DataFrame) -> Dict[str, Any]:
    """Analyze transaction count patterns."""
    total_count = len(ledger_df)
    
    # Count by category
    category_counts = ledger_df.groupby('category', observed=True).size().to_dict()
    
    # Count by subcategory
    subcategory_counts = ledger_df.groupby('subcategory', observed=True).size().to_dict()
    
    # Count by date (timeline coverage)
    date_counts = ledger_df.groupby('date', observed=True).size()
    
    return {
        'total_count': total_count,
        'by_category': category_counts,
        'by_subcategory': subcategory_counts,
        'timeline_periods': len(date_counts),
        'transactions_per_period': {
            'mean': date_counts.mean(),
            'min': date_counts.min(),
            'max': date_counts.max(),
            'std': date_counts.std()
        }
    }


def _analyze_flow_patterns(ledger_df: pd.DataFrame) -> Dict[str, Any]:
    """Analyze cash flow patterns and magnitudes."""
    # Total flows
    total_inflows = ledger_df[ledger_df['amount'] > 0]['amount'].sum()
    total_outflows = ledger_df[ledger_df['amount'] < 0]['amount'].sum()
    net_flow = total_inflows + total_outflows
    
    # Flow by category
    category_flows = ledger_df.groupby('category', observed=True)['amount'].sum().to_dict()
    
    # Flow by subcategory (top 10 by absolute value)
    subcategory_flows = ledger_df.groupby('subcategory', observed=True)['amount'].sum()
    top_subcategory_flows = subcategory_flows.reindex(
        subcategory_flows.abs().nlargest(10).index
    ).to_dict()
    
    return {
        'total_inflows': total_inflows,
        'total_outflows': total_outflows,
        'net_flow': net_flow,
        'by_category': category_flows,
        'top_subcategories': top_subcategory_flows
    }


def _analyze_timeline_coverage(ledger_df: pd.DataFrame) -> Dict[str, Any]:
    """Analyze how transactions are distributed across the timeline."""
    if ledger_df.empty:
        return {'period_count': 0, 'start_date': None, 'end_date': None}
    
    dates = sorted(ledger_df['date'].unique())
    
    return {
        'period_count': len(dates),
        'start_date': dates[0] if dates else None,
        'end_date': dates[-1] if dates else None,
        'date_range': dates[-1] - dates[0] if len(dates) > 1 else pd.Timedelta(0),
        'periods_with_transactions': len(dates),
        'transaction_frequency': len(ledger_df) / len(dates) if dates else 0
    }


def _analyze_balance_patterns(ledger_df: pd.DataFrame) -> Dict[str, Any]:
    """Analyze ledger balance and flow validation."""
    total_inflows = ledger_df[ledger_df['amount'] > 0]['amount'].sum()
    total_outflows = ledger_df[ledger_df['amount'] < 0]['amount'].sum()
    net_flow = total_inflows + total_outflows
    
    # Check for unusual balance patterns
    balance_ratio = abs(total_outflows) / total_inflows if total_inflows > 0 else 0
    
    return {
        'total_inflows': total_inflows,
        'total_outflows': total_outflows, 
        'net_flow': net_flow,
        'balance_ratio': balance_ratio,
        'flow_health': 'healthy' if 0.8 <= balance_ratio <= 1.2 else 'unusual'
    }


def _compare_transaction_counts(ledger1: pd.DataFrame, ledger2: pd.DataFrame) -> Dict[str, Any]:
    """Compare transaction counts between two ledgers."""
    counts1 = ledger1.groupby(['category', 'subcategory'], observed=True).size().reset_index(name='count1')
    counts2 = ledger2.groupby(['category', 'subcategory'], observed=True).size().reset_index(name='count2')
    
    # Merge to find differences
    merged = pd.merge(counts1, counts2, on=['category', 'subcategory'], how='outer')
    merged['count1'] = merged['count1'].fillna(0)
    merged['count2'] = merged['count2'].fillna(0)
    merged['count_diff'] = merged['count2'] - merged['count1']
    
    # Filter significant differences
    significant = merged[merged['count_diff'].abs() > 0]
    
    return {
        'total_count_diff': len(ledger2) - len(ledger1),
        'category_subcategory_diffs': significant.to_dict('records') if len(significant) > 0 else [],
        'has_significant_diffs': len(significant) > 0
    }


def _compare_flow_amounts(ledger1: pd.DataFrame, ledger2: pd.DataFrame) -> Dict[str, Any]:
    """Compare flow amounts between two ledgers by subcategory."""
    amounts1 = ledger1.groupby('subcategory', observed=True)['amount'].sum()
    amounts2 = ledger2.groupby('subcategory', observed=True)['amount'].sum()
    
    # Find all subcategories
    all_subcats = set(amounts1.index) | set(amounts2.index)
    
    differences = []
    for subcat in all_subcats:
        amt1 = amounts1.get(subcat, 0)
        amt2 = amounts2.get(subcat, 0)
        diff = abs(amt1 - amt2)
        
        if diff > 1000:  # > $1K difference
            differences.append({
                'subcategory': subcat,
                'amount1': amt1,
                'amount2': amt2,
                'difference': amt1 - amt2,
                'abs_difference': diff
            })
    
    # Sort by absolute difference
    differences.sort(key=lambda x: x['abs_difference'], reverse=True)
    
    return {
        'significant_amount_diffs': differences,
        'largest_difference': differences[0] if differences else None,
        'has_significant_diffs': len(differences) > 0
    }


def _generate_shape_warnings(analysis: Dict[str, Any]) -> None:
    """Generate warnings based on shape analysis."""
    warnings = analysis['warnings']
    recommendations = analysis['recommendations']
    
    # Check for unusual transaction counts
    total_count = analysis['transaction_summary']['total_count']
    if total_count > 10000:
        warnings.append(f"Very large ledger: {total_count:,} transactions")
        recommendations.append("Consider analysis timeline reduction if performance issues")
    
    # Check for balance issues
    balance = analysis['balance_analysis']
    if balance['flow_health'] == 'unusual':
        warnings.append(f"Unusual balance ratio: {balance['balance_ratio']:.2f}")
        recommendations.append("Verify deal structure and expected cash flow patterns")
    
    # Check timeline coverage
    timeline = analysis['timeline_coverage']
    if timeline['transaction_frequency'] > 200:
        warnings.append(f"High transaction frequency: {timeline['transaction_frequency']:.1f} txns/period")
        recommendations.append("Verify component configurations for excessive transaction creation")


def _identify_significant_differences(comparison: Dict[str, Any]) -> None:
    """Identify and categorize significant differences between ledgers."""
    significant_diffs = comparison['significant_differences']
    
    # Check total transaction count difference
    count_diff = comparison['transaction_count_diff']['total_count_diff']
    if abs(count_diff) > 50:
        significant_diffs.append({
            'type': 'transaction_count',
            'difference': count_diff,
            'severity': 'high' if abs(count_diff) > 100 else 'medium'
        })
    
    # Check for major flow differences
    flow_diffs = comparison['flow_amount_diff']['significant_amount_diffs']
    if flow_diffs:
        largest = flow_diffs[0]
        if largest['abs_difference'] > 100000:  # > $100K
            significant_diffs.append({
                'type': 'flow_amount',
                'subcategory': largest['subcategory'],
                'difference': largest['difference'],
                'severity': 'high'
            })
    
    # Determine likely cause
    if count_diff > 0:
        comparison['likely_cause'] = 'Timeline mismatch (deal1 has more periods)'
        comparison['recommendations'] = [
            'Check analysis timeline duration',
            'Verify Timeline.from_dates() vs Timeline(duration_months=X)',
            'Ensure both deals use identical analysis periods'
        ]
    elif any(d['type'] == 'flow_amount' for d in significant_diffs):
        comparison['likely_cause'] = 'Configuration parameter differences'
        comparison['recommendations'] = [
            'Compare financing configurations',
            'Check exit valuation parameters',
            'Verify operating assumption alignment'
        ]
    else:
        comparison['likely_cause'] = 'Minor implementation differences'


def format_ledger_shape_comparison(comparison: Dict[str, Any]) -> str:
    """Format ledger shape comparison for display."""
    if not comparison['significant_differences']:
        return "✅ Ledger Shape Comparison: Shapes match closely"
    
    output = ["🔍 Ledger Shape Comparison"]
    output.append("=" * 50)
    
    # Transaction count summary
    count_diff = comparison['transaction_count_diff']['total_count_diff']
    output.append(f"Transaction Count Difference: {count_diff:+,}")
    
    # Category/subcategory differences
    if comparison['transaction_count_diff']['has_significant_diffs']:
        output.append("\nTransaction Count Differences:")
        for diff in comparison['transaction_count_diff']['category_subcategory_diffs']:
            category = diff['category']
            subcategory = diff['subcategory']
            count_diff = diff['count_diff']
            output.append(f"  {category} -> {subcategory}: {count_diff:+.0f}")
    
    # Amount differences
    if comparison['flow_amount_diff']['has_significant_diffs']:
        output.append("\nTop Amount Differences:")
        for diff in comparison['flow_amount_diff']['significant_amount_diffs'][:5]:  # Top 5
            subcategory = diff['subcategory']
            amount_diff = diff['difference']
            output.append(f"  {subcategory}: ${amount_diff:+,.0f}")
    
    # Likely cause and recommendations
    if comparison['likely_cause']:
        output.append(f"\n🎯 Likely Cause: {comparison['likely_cause']}")
        
    if comparison['recommendations']:
        output.append("\nRecommendations:")
        for rec in comparison['recommendations']:
            output.append(f"  • {rec}")
    
    return "\n".join(output)
