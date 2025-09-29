# Office Development Baseline

## Generation Information

- **Generated**: 2025-09-28T11:10:33.632421
- **Git Branch**: main
- **Git Commit**: 632e006bfab676745700dff6458fbd7d71aec6de

## Example Details

- **Script**: `examples/patterns/office_development_comparison.py`
- **Function**: `create_deal_via_composition() + analyze_composition_deal()`
- **Deal Type**: office_development
- **Approach**: composition_manual_assembly
- **Timeline**: 2024-01-01, 66 months

## Core Metrics (MAIN BRANCH BASELINE)

- **IRR**: 0.3739 (37.39%)
- **Equity Multiple**: 6.4406x
- **Total Equity**: $6,305,037
- **Net Profit**: $24,673,426
- **Timeline**: 66 months (2024-01 to 2029-06)

## Ledger Statistics

- **Total Transactions**: 1,157
- **Date Range**: 2024-01-01 to 2029-06-01
- **Total Amount** (including valuations): $1,243,245,566
- **Cash Flow Amount**: $-6,383,813

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

1. **IRR should be within 1%** of 37.39%
2. **Equity Multiple should be within 0.05** of 6.44x  
3. **Total Equity should be within $10,000** of $6,305,037
4. **Net Profit should be within 5%** of $24,673,426
5. **Transaction count should match** 1,157 transactions

Any significant deviation indicates a calculation integrity issue in the performance branch.
