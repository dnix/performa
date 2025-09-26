#!/usr/bin/env python3
"""
Generate Ledger Performance Baselines

This script runs complex deal examples to capture baseline performance metrics
and save normalized ledger DataFrames for parity testing. The baselines are used
to validate that performance optimizations produce identical results.

Baseline Deals:
1. Value Add Multifamily - Riverside Gardens ($11.5M acquisition + renovation)
2. Office Development - Metro Office Tower ($16.7M development)  
3. Residential Development - Institutional project ($28.7M development)

The script measures timing and saves both performance metrics and ledger data
for comprehensive validation of future optimizations.
"""

import sys
import time
from pathlib import Path

# Add the examples directory to path so we can import the pattern examples
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "examples" / "patterns"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

try:
    from office_development_comparison import (
        demonstrate_pattern_interface as create_office_dev_deal,
    )
    from residential_development_comparison import (
        create_deal_via_convention as create_residential_dev_deal,
    )
    from value_add_comparison import (
        create_deal_via_composition as create_value_add_deal,
    )

    from performa.core.primitives import GlobalSettings
    from performa.deal import analyze
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure you're running from the project root and all dependencies are installed")
    sys.exit(1)

import pandas as pd

FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"


def normalize_ledger_for_baseline(df: pd.DataFrame, deal_type: str) -> pd.DataFrame:
    """
    Normalize a ledger DataFrame for consistent baseline comparison.
    
    This ensures that baseline and optimized DataFrames can be compared
    bit-for-bit despite potential dtype and structural differences.
    """
    if df is None or df.empty:
        return df
    
    # Make a copy to avoid modifying the original
    normalized = df.copy()
    
    # 1. Reset index to make 'date' a regular column (if it's an index)
    if 'date' not in normalized.columns and normalized.index.name == 'date':
        normalized.reset_index(inplace=True)
    
    # 2. Convert UUIDs and enums to strings for consistent types
    uuid_cols = ['source_id', 'asset_id', 'deal_id', 'entity_id', 'transaction_id']
    enum_cols = ['category', 'subcategory', 'flow_purpose', 'entity_type']
    
    for col in uuid_cols + enum_cols:
        if col in normalized.columns:
            if pd.api.types.is_categorical_dtype(normalized[col]):
                normalized[col] = normalized[col].astype(str)
            elif not pd.api.types.is_string_dtype(normalized[col]):
                normalized[col] = normalized[col].astype(str)
    
    # 3. Ensure consistent datetime handling
    if 'date' in normalized.columns:
        normalized['date'] = pd.to_datetime(normalized['date'])
    
    # 4. Sort for deterministic ordering  
    sort_cols = ['date']
    if 'item_name' in normalized.columns:
        sort_cols.append('item_name')
    if 'amount' in normalized.columns:
        sort_cols.append('amount')
    
    normalized = normalized.sort_values(by=sort_cols)
    normalized.reset_index(drop=True, inplace=True)
    
    print(f"✅ Normalized {deal_type} ledger: {len(normalized)} transactions")
    return normalized


def run_deal_analysis_with_timing(deal_creator, deal_name: str):
    """Run a deal analysis and capture both results and timing."""
    print(f"\n🏗️ Running {deal_name} analysis...")
    
    try:
        # Create deal - handle different return types
        start_create = time.perf_counter()
        result = deal_creator()
        create_time = time.perf_counter() - start_create
        
        # Extract deal and pattern from different return formats
        deal = None
        pattern = None
        
        if isinstance(result, tuple) and len(result) == 2:
            # Handle (pattern, deal) or (deal, pattern) returns
            first, second = result
            if hasattr(first, 'name') and hasattr(first, 'asset'):  # first is deal
                deal = first
                pattern = second
            elif hasattr(second, 'name') and hasattr(second, 'asset'):  # second is deal
                deal = second
                pattern = first
            else:
                raise ValueError(f"Could not extract deal from tuple return: {type(first)}, {type(second)}")
        else:
            # Assume it's just a deal
            deal = result
        
        # Get timeline from pattern if available, otherwise from deal
        timeline = None
        if pattern and hasattr(pattern, 'get_timeline'):
            timeline = pattern.get_timeline()
        elif hasattr(deal, 'timeline'):
            timeline = deal.timeline
        
        settings = GlobalSettings()
        
        # Run analysis
        start_analysis = time.perf_counter()
        results = analyze(deal, timeline, settings)
        analysis_time = time.perf_counter() - start_analysis
        
        total_time = create_time + analysis_time
        ledger_size = len(results.ledger_df) if results.ledger_df is not None else 0
        
        print(f"✅ {deal_name} completed:")
        print(f"   - Deal creation: {create_time * 1000:.1f}ms")
        print(f"   - Analysis: {analysis_time * 1000:.1f}ms") 
        print(f"   - Total: {total_time * 1000:.1f}ms")
        print(f"   - Ledger size: {ledger_size:,} transactions")
        
        return results, {
            'deal_name': deal_name,
            'create_time_ms': create_time * 1000,
            'analysis_time_ms': analysis_time * 1000,
            'total_time_ms': total_time * 1000,
            'ledger_transactions': ledger_size
        }
        
    except Exception as e:
        print(f"❌ Error running {deal_name}: {e}")
        import traceback
        traceback.print_exc()
        return None, None


def main():
    """Generate baseline performance metrics and fixture files."""
    print("🎯 Generating Ledger Performance Baselines")
    print("=" * 50)
    
    # Ensure fixtures directory exists
    FIXTURES_DIR.mkdir(exist_ok=True, parents=True)
    
    # Deal definitions with their creators
    deal_configs = [
        (create_value_add_deal, "Value Add Multifamily"),
        (create_office_dev_deal, "Office Development"), 
        (create_residential_dev_deal, "Residential Development")
    ]
    
    baseline_metrics = []
    successful_baselines = 0
    
    # Run each deal analysis
    for deal_creator, deal_name in deal_configs:
        results, metrics = run_deal_analysis_with_timing(deal_creator, deal_name)
        
        if results is not None and metrics is not None:
            # Normalize and save the ledger DataFrame
            normalized_ledger = normalize_ledger_for_baseline(results.ledger_df, deal_name)
            
            # Create filename-safe version of deal name
            filename = deal_name.lower().replace(" ", "_")
            filepath = FIXTURES_DIR / f"baseline_ledger_{filename}.pkl"
            
            normalized_ledger.to_pickle(filepath)
            print(f"💾 Saved baseline to {filepath}")
            
            baseline_metrics.append(metrics)
            successful_baselines += 1
        else:
            print(f"⚠️ Skipping {deal_name} due to errors")
    
    # Generate summary report
    if baseline_metrics:
        print(f"\n📊 Baseline Performance Summary")
        print("=" * 50)
        
        total_transactions = sum(m['ledger_transactions'] for m in baseline_metrics)
        avg_analysis_time = sum(m['analysis_time_ms'] for m in baseline_metrics) / len(baseline_metrics)
        
        print(f"Successful baselines: {successful_baselines}/3")
        print(f"Total transactions: {total_transactions:,}")
        print(f"Average analysis time: {avg_analysis_time:.1f}ms")
        print()
        
        for metrics in baseline_metrics:
            print(f"{metrics['deal_name']:.<25} {metrics['total_time_ms']:>8.1f}ms ({metrics['ledger_transactions']:>5,} txns)")
    
        # Save metrics to markdown file
        metrics_file = PROJECT_ROOT / "BASELINE_METRICS.md"
        with open(metrics_file, 'w') as f:
            f.write("# Ledger Performance Baseline Metrics\n\n")
            f.write(f"**Generated:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("## Individual Deal Performance\n\n")
            f.write("| Deal Type | Total Time (ms) | Analysis (ms) | Transactions | Rate (txns/ms) |\n")
            f.write("|-----------|----------------|---------------|-------------|---------------|\n")
            
            for m in baseline_metrics:
                rate = m['ledger_transactions'] / m['analysis_time_ms'] if m['analysis_time_ms'] > 0 else 0
                f.write(f"| {m['deal_name']} | {m['total_time_ms']:.1f} | {m['analysis_time_ms']:.1f} | {m['ledger_transactions']:,} | {rate:.2f} |\n")
            
            f.write(f"\n## Summary Statistics\n\n")
            f.write(f"- **Total Transactions:** {total_transactions:,}\n")
            f.write(f"- **Average Analysis Time:** {avg_analysis_time:.1f}ms\n")
            f.write(f"- **Baseline Performance:** ~{total_transactions / avg_analysis_time:.1f} transactions per millisecond\n")
            f.write(f"\n**Target Performance (10x improvement):** ~{(total_transactions / avg_analysis_time) * 10:.1f} transactions per millisecond\n")
        
        print(f"📋 Performance metrics saved to {metrics_file}")
        
    else:
        print("❌ No successful baselines generated!")
        return 1
    
    print(f"\n✅ Baseline generation complete!")
    print(f"📂 Files saved to: {FIXTURES_DIR}")
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
