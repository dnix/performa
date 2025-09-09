# Pattern Comparison Scripts

This directory contains validation scripts that compare pattern-based approaches with manual compositional assembly. Each script achieves 0.0000% IRR difference, confirming patterns are mathematically identical to composition with different syntax.

Scripts are validated using debug utilities to achieve dollar-for-dollar parity.

## Available Comparisons

### **`office_development_comparison.py`**
**Office Development Pattern Validation**

Compares `OfficeDevelopmentPattern` against manual assembly:
- Manual Assembly: Compositional approach (~200 lines of configuration)  
- Pattern Approach: Parameterized interface (~50 parameters)
- Validation: 0.0000% IRR difference, 16.13% IRR, 1.90x EM

### **`residential_development_comparison.py`**  
**Residential Development Pattern Validation**

Validates `ResidentialDevelopmentPattern` implementation:
- Parity: 0.0000% IRR difference after fixing $725K loan amount mismatch
- Returns: 14.67% IRR, 2.08x EM  
- Architecture: Pattern encapsulates manual assembly
- Integration: Construction-to-permanent financing workflows

### **`value_add_comparison.py`**
**Value-Add Acquisition Pattern Validation**

Compares `ValueAddAcquisitionPattern` against compositional equivalent:
- Parity: 0.0000% IRR difference after fixing 0.5% interest rate mismatch (8.0%→7.5%)
- Returns: 15.47% IRR, 2.00x EM 
- Configuration: Renovation timeline and partnership structures

### **`stabilized_comparison.py`**
**Stabilized Acquisition Pattern Validation**

Compares `StabilizedAcquisitionPattern` against manual approach:
- Parity: 0.0000% IRR difference, mathematical equivalence
- Returns: 18.85% IRR, 2.00x EM  
- Configuration: Stabilized cash flow modeling

## Validation Framework

### Mathematical Validation
All comparison scripts verify:
- Ledger Parity: Identical cash flow records between pattern and compositional approaches
- Return Validation: Tests confirming return calculations
- Configuration Consistency: Parameter alignment and assumption validation

### Debug Integration
Scripts use Performa's debug utilities:

```python
from performa.reporting.debug import analyze_ledger_semantically, dump_performa_object

# Ledger parity verification
comp_analysis = analyze_ledger_semantically(comp_results.ledger)
pattern_analysis = analyze_ledger_semantically(pattern_results.ledger)

# Configuration analysis  
comp_config = dump_performa_object(comp_deal)
pattern_config = dump_performa_object(pattern)
```

### Validation Outcomes

| Script | Parity Status | IRR Performance | Key Fix Applied |
|--------|---------------|-----------------|------------------|
| Office Development | 0.0000% difference | 16.13% IRR, 1.90x EM | Market assumptions |
| Residential Development | 0.0000% difference | 14.67% IRR, 2.08x EM | Fixed $725K loan amount mismatch |  
| Value-Add Acquisition | 0.0000% difference | 15.47% IRR, 2.00x EM | Fixed 0.5% interest rate mismatch |
| Stabilized Acquisition | 0.0000% difference | 18.85% IRR, 2.00x EM | No fix required |

All scripts achieve mathematical parity using debug utility validation.

## Parity Validation Methodology

Parity validation uses Performa's debug utilities:

### 1. Configuration Comparison
```python
from performa.reporting.debug import compare_deal_configurations

# Find exact parameter differences
config_diff = compare_deal_configurations(comp_deal, pattern_deal)
# Debug utilities identified specific mismatches like:
# - permanent_loan_amount: $20,115,200 vs $20,840,960 (residential)
# - interest_rate: 8.0% vs 7.5% (value-add)
```

### 2. Parameter Fixing
Each identified difference was traced to its root cause:
- Residential: Pattern uses loan sizing logic; composition needed exact match
- Value-Add: Interest rate parameter inconsistency between approaches  
- Parameter validation: `extra="forbid"` caught silent parameter failures

### 3. Validation Verification
```python
# Confirm 0.0000% differences achieved
assert abs(comp_results.deal_metrics.irr - pattern_results.deal_metrics.irr) < 0.000001
assert abs(comp_results.deal_metrics.total_equity_invested - pattern_results.deal_metrics.total_equity_invested) < 1
```

This methodology ensures patterns are mathematically identical to composition.

## Usage

Run comparison scripts directly:
```bash
python examples/patterns/office_development_comparison.py      # Office comparison
python examples/patterns/residential_development_comparison.py # Residential validation
python examples/patterns/value_add_comparison.py              # Value-add validation
python examples/patterns/stabilized_comparison.py             # Stabilized validation
```

### Expected Output

Each script provides:
- Configuration summary for both approaches
- Return metrics (IRR, Equity Multiple, Cash-on-Cash)
- Ledger parity confirmation (record counts, category totals)
- Validation status (Pass/Fail)

All scripts validate that pattern classes achieve mathematical equivalence with manual assembly.
