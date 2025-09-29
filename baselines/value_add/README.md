# Value Add Baseline

## Generation Information

- **Generated**: 2025-09-28T11:10:35.945216
- **Git Branch**: main
- **Git Commit**: 632e006bfab676745700dff6458fbd7d71aec6de

## Example Details

- **Script**: `examples/patterns/value_add_comparison.py`
- **Function**: `create_deal_via_composition() + direct analyze()`
- **Deal Type**: value_add
- **Approach**: composition_manual_assembly
- **Timeline**: 2024-01-01, 84 months

## Core Metrics (MAIN BRANCH BASELINE)

- **IRR**: 0.0651 (6.51%)
- **Equity Multiple**: 4.8027x
- **Total Equity**: $5,678,520
- **Net Profit**: $5,913,094
- **Timeline**: 84 months (2024-01 to 2030-12)

## Ledger Statistics

- **Total Transactions**: 8,672
- **Date Range**: 2024-01-01 to 2030-12-01
- **Total Amount** (including valuations): $1,352,202,493
- **Cash Flow Amount**: $-8,406,207

## Files Generated

- `metrics.json` - Core metrics and metadata in JSON format
- `cash_flows.pkl` - All cash flow series (levered, equity, unlevered, etc.)
- `ledger.pkl` - Complete ledger DataFrame
- `deal_config.pkl` - Deal, timeline, and settings configuration
- `ledger_analysis.pkl` - Ledger semantic analysis (if available)

## Usage for Performance Branch Comparison

```python
import pickle
import pandas as pd

# Load baseline metrics
with open('metrics.json', 'r') as f:
    baseline_metrics = json.load(f)

# Load baseline cash flows  
with open('cash_flows.pkl', 'rb') as f:
    baseline_cash_flows = pickle.load(f)

# Load baseline ledger
baseline_ledger = pd.read_pickle('ledger.pkl')

# Compare with performance branch results
current_irr = your_performance_results.deal_metrics.get('levered_irr')
baseline_irr = baseline_metrics['core_metrics']['irr']
irr_ratio = current_irr / baseline_irr

print(f"IRR Performance: {irr_ratio:.1%} of baseline")
```

## Critical Validation Points

When comparing performance branch results against this baseline:

1. **IRR should be within 1%** of 6.51%
2. **Equity Multiple should be within 0.05** of 4.80x  
3. **Total Equity should be within $10,000** of $5,678,520
4. **Net Profit should be within 5%** of $5,913,094
5. **Transaction count should match** 8,672 transactions

Any significant deviation indicates a calculation integrity issue in the performance branch.
