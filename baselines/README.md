# Comprehensive Baseline Generation System

## Overview

This directory contains systematic baselines generated from the `main` branch for all major example scripts in Performa. These baselines serve as the **ground truth** for performance branch comparison and data integrity validation.

## Generation Summary

- **Generated**: 2025-09-28T11:10:33 
- **Git Branch**: `main`
- **Git Commit**: `632e006bfab676745700dff6458fbd7d71aec6de`
- **Platform**: macOS-15.6.1-arm64-arm-64bit, Python 3.11.9
- **Generator**: `generate_comprehensive_baselines.py`

## Baseline Coverage

| Deal Type | Script | IRR | Equity Multiple | Total Equity | Transactions | Status |
|-----------|---------|-----|-----------------|--------------|--------------|--------|
| **Office Development** | `office_development_comparison.py` | **37.39%** | **6.44x** | **$6.3M** | **1,157** | ✅ Success |
| **Residential Development** | `residential_development_comparison.py` | **40.67%** | **6.84x** | **$9.7M** | **9,057** | ✅ Success |
| **Stabilized Acquisition** | `stabilized_comparison.py` | **9.14%** | **4.41x** | **$3.8M** | **7,108** | ✅ Success |
| **Value-Add** | `value_add_comparison.py` | **6.51%** | **4.80x** | **$5.7M** | **8,672** | ✅ Success |

### **Total Coverage**: 26,994 transactions across 4 deal types

## Deal Characteristics

### Office Development (66 months, 2024-01 to 2029-06)
- **Total Development Cost**: $11.7M
- **Net Rentable Area**: 45,000 SF  
- **Construction-to-permanent financing**
- **Highest IRR**: 37.39% (development premium)

### Residential Development (84 months, 2024-01 to 2030-12)  
- **Total Development Cost**: $29.8M
- **Units**: 120 mixed Studio/1BR/2BR/3BR
- **Institutional-grade development**
- **Highest Transaction Count**: 9,057 (monthly unit-level tracking)

### Stabilized Acquisition (60 months, 2024-01 to 2028-12)
- **Purchase Price**: $12.0M
- **Units**: 120 (95% occupied)
- **Permanent financing**
- **Lowest IRR**: 9.14% (stabilized return profile)

### Value-Add (84 months, 2024-01 to 2030-12)
- **Total Project Cost**: $12.5M ($11.5M + $1M renovation)
- **Units**: 100 with rent increases ($1,200→$1,320/month)
- **Construction-to-permanent financing**

## File Structure

Each baseline directory contains:
- `README.md` - Detailed documentation and validation points
- `metrics.json` - Core metrics in JSON format (easy parsing)
- `cash_flows.pkl` - All cash flow series (levered, equity, unlevered, etc.)
- `ledger.pkl` - Complete transaction ledger DataFrame  
- `deal_config.pkl` - Deal, timeline, and settings configuration
- `ledger_analysis.pkl` - Semantic ledger analysis from debug utilities

## Usage for Performance Branch Validation

### Load Baseline Data
```python
import json
import pickle
import pandas as pd

# Load specific baseline
baseline_type = "office_development"  # or residential_development, etc.

with open(f'baselines/{baseline_type}/metrics.json', 'r') as f:
    baseline_metrics = json.load(f)

baseline_ledger = pd.read_pickle(f'baselines/{baseline_type}/ledger.pkl')

with open(f'baselines/{baseline_type}/cash_flows.pkl', 'rb') as f:
    baseline_cash_flows = pickle.load(f)
```

### Performance Branch Comparison
```python
# Compare key metrics
current_irr = performance_results.deal_metrics.get('levered_irr')
baseline_irr = baseline_metrics['core_metrics']['irr']

print(f"IRR Comparison: {current_irr:.2%} vs {baseline_irr:.2%} baseline")
print(f"IRR Ratio: {current_irr/baseline_irr:.1%}")

# Transaction count integrity
current_txns = len(performance_results.ledger_df)  
baseline_txns = baseline_metrics['ledger_stats']['transaction_count']

print(f"Transaction Count: {current_txns:,} vs {baseline_txns:,} baseline")
```

### Critical Validation Thresholds

For **data integrity validation**, performance branch results should be:

1. **IRR within ±1%** of baseline values
2. **Equity Multiple within ±0.05** of baseline values  
3. **Total Equity within ±$10,000** of baseline values
4. **Transaction count exactly matching** baseline counts
5. **Net Profit within ±5%** of baseline values

**Any significant deviation indicates calculation integrity issues** in the performance branch requiring investigation.

## Regeneration

To regenerate baselines (e.g., after significant model changes):

```bash
cd /path/to/performa
git checkout main  # Ensure on main branch
uv run python3 generate_comprehensive_baselines.py
```

This will create a complete new baseline set with updated timestamps and git commit references.
