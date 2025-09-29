# Stabilized Acquisition Baseline

## Generation Information

- **Generated**: 2025-09-28T11:10:35.207249
- **Git Branch**: main
- **Git Commit**: 632e006bfab676745700dff6458fbd7d71aec6de

## Example Details

- **Script**: `examples/patterns/stabilized_comparison.py`
- **Function**: `create_deal_via_composition() + direct analyze()`
- **Deal Type**: stabilized_acquisition
- **Approach**: composition_manual_assembly
- **Timeline**: 2024-01-01, 60 months

## Core Metrics (MAIN BRANCH BASELINE)

- **IRR**: 0.0914 (9.14%)
- **Equity Multiple**: 4.4077x
- **Total Equity**: $3,815,680
- **Net Profit**: $5,948,058
- **Timeline**: 60 months (2024-01 to 2028-12)

## Ledger Statistics

- **Total Transactions**: 7,108
- **Date Range**: 2024-01-01 to 2028-12-01
- **Total Amount** (including valuations): $1,052,023,417
- **Cash Flow Amount**: $-6,124,737

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

1. **IRR should be within 1%** of 9.14%
2. **Equity Multiple should be within 0.05** of 4.41x  
3. **Total Equity should be within $10,000** of $3,815,680
4. **Net Profit should be within 5%** of $5,948,058
5. **Transaction count should match** 7,108 transactions

Any significant deviation indicates a calculation integrity issue in the performance branch.
