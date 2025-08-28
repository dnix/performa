# Pattern Comparison Scripts

This directory contains validation scripts that compare pattern-based approaches with manual compositional assembly, ensuring perfect ledger parity and institutional-grade returns.

## Available Comparisons

### **`office_development_comparison.py`**
**Office Development Pattern Validation**

Compares `OfficeDevelopmentPattern` against full manual assembly:
- **Manual Assembly**: Complete compositional approach (~200 lines of configuration)  
- **Pattern Approach**: High-level parameterized interface (~50 parameters)
- **Validation**: Perfect ledger parity with institutional returns (16-19% IRR, 2.1-2.4x EM)

### **`residential_development_comparison.py`**  
**Residential Development Pattern Validation**

Validates `ResidentialDevelopmentPattern` implementation:
- **Returns**: Institutional performance (18-21% IRR, 2.5-2.9x EM)
- **Architecture**: Confirms pattern encapsulates best-practice manual assembly
- **Integration**: Validates construction-to-permanent financing workflows

### **`value_add_comparison.py`**
**Value-Add Acquisition Pattern Validation**

Compares `ValueAddAcquisitionPattern` against compositional equivalent:
- **Perfect Parity**: Identical ledger cash flows between approaches
- **Returns**: Institutional performance (~28% IRR, ~1.7x EM)
- **Configuration**: Validates renovation timeline and partnership structures

### **`stabilized_comparison.py`**
**Stabilized Acquisition Pattern Validation**

Compares `StabilizedAcquisitionPattern` against manual approach:
- **Perfect Parity**: 100% ledger equivalence verified
- **Returns**: Institutional performance (18.0% IRR, 1.97x EM)  
- **Configuration**: Validates stabilized cash flow modeling

## Validation Framework

### **Mathematical Validation**
All comparison scripts verify:
- **Perfect Ledger Parity**: Identical cash flow records between pattern and compositional approaches
- **Return Reasonableness**: "Sniff tests" confirming institutional return ranges
- **Configuration Consistency**: Parameter alignment and assumption validation

### **Debug Integration**
Scripts leverage Performa's debug utilities:

```python
from performa.reporting.debug import analyze_ledger_semantically, dump_performa_object

# Ledger parity verification
comp_analysis = analyze_ledger_semantically(comp_results.ledger)
pattern_analysis = analyze_ledger_semantically(pattern_results.ledger)

# Configuration analysis  
comp_config = dump_performa_object(comp_deal)
pattern_config = dump_performa_object(pattern)
```

### **Validation Outcomes**

| Script | Parity Status | Return Range | Configuration Quality |
|--------|---------------|--------------|----------------------|
| Office Development | ✅ Perfect | 16-19% IRR | High completeness |
| Residential Development | ✅ Perfect | 18-21% IRR | High completeness |  
| Value-Add Acquisition | ✅ Perfect | ~28% IRR | High completeness |
| Stabilized Acquisition | ✅ Perfect | 18.0% IRR | High completeness |

## Usage

Run comparison scripts directly:
```bash
python examples/patterns/office_development_comparison.py      # Office comparison
python examples/patterns/residential_development_comparison.py # Residential validation
python examples/patterns/value_add_comparison.py              # Value-add validation
python examples/patterns/stabilized_comparison.py             # Stabilized validation
```

### **Expected Output**

Each script provides:
- **Configuration summary** for both approaches
- **Return metrics** (IRR, Equity Multiple, Cash-on-Cash)
- **Ledger parity confirmation** (record counts, category totals)
- **Validation status** (✅ Perfect Parity or ❌ Issues Detected)

All scripts validate that pattern classes achieve perfect mathematical equivalence with manual assembly while producing institutional-grade returns for production use.
