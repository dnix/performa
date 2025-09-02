# Performa Reporting - Fluent Interface Architecture

Modern reporting system that transforms `DealAnalysisResult` objects into presentation-ready formats through a fluent interface, ensuring reports operate on final analysis data rather than input specifications.

## Architecture Overview

### Design Philosophy

**Separation of Concerns**: Reports format and present data; they never perform calculations. All financial computations occur during analysis, with reports extracting and presenting results.

**Fluent Interface Pattern**: Chainable method calls provide intuitive access to reporting capabilities directly from analysis results.

**Data Flow Integrity**: Reports operate exclusively on `DealAnalysisResult` objects, ensuring consistency between analysis and presentation.

### Core Components

```
DealAnalysisResult → .reporting → ReportingInterface → Specific Reports → Formatted Output
```

- **`DealAnalysisResult`**: Container for all analysis outputs (NOI, cash flows, metrics, etc.)
- **`ReportingInterface`**: Fluent API surface providing access to report generators
- **`BaseReport`**: Abstract base class enforcing consistent report architecture
- **Report Implementations**: Specific formatters for different output types

## Fluent Interface Usage

### Basic Pattern

```python
from datetime import date
from performa.deal import analyze
from performa.patterns import ValueAddAcquisitionPattern
from performa.core.primitives import Timeline
from performa.reporting import generate_assumptions_report

# Create and analyze deal
pattern = ValueAddAcquisitionPattern(
    property_name="Riverside Gardens",
    acquisition_date=date(2024, 1, 1),
    acquisition_price=10_000_000,
    renovation_budget=1_500_000,
    current_avg_rent=1_800,
    target_avg_rent=2_200,
    hold_period_years=7,
    ltv_ratio=0.75
)
deal = pattern.create()

timeline = Timeline.from_dates("2024-01-01", "2030-12-31")
results = analyze(deal, timeline)

# ESSENTIAL: Validate assumptions for model confidence
assumptions_doc = generate_assumptions_report(deal, include_risk_assessment=True)
print(assumptions_doc)  # Suitable for due diligence documentation

# Generate reports via fluent interface
annual_summary = results.reporting.pro_forma_summary()              # Default: annual
assumptions_summary = results.reporting.assumptions_summary()       # Assumptions summary
quarterly_detail = results.reporting.pro_forma_summary(frequency="Q")  # Quarterly breakdown
monthly_detail = results.reporting.pro_forma_summary(frequency="M")    # Monthly detail
```

### Interface Caching

The reporting interface is cached for performance:

```python
# Same interface instance returned
interface1 = results.reporting
interface2 = results.reporting
assert interface1 is interface2  # True - cached instance
```

### Report Persistence

Reports reflect analysis results at generation time:

```python
# Reports contain final analysis outputs
pro_forma = results.reporting.pro_forma_summary()
print(f"Year 5 NOI: ${pro_forma.loc['Net Operating Income', '2028-12-31']:,.0f}")

# No recalculation occurs - data extracted from results
assert 'Net Operating Income' in pro_forma.index
assert pro_forma.shape[1] >= 5  # At least 5 years of data
```

## Available Reports

### Model Documentation & Debugging

#### Assumptions Summary (`assumptions_summary()`)

**MODEL VALIDATION TOOL**: Comprehensive documentation of model assumptions with risk assessment.

**Parameters**:
- `include_risk_assessment`: Flag critical parameters using defaults (default: `True`)
- `include_defaults_detail`: Include full list of defaulted parameters (default: `False`)
- `focus_components`: Limit to specific components (optional)
- `formatted`: Return formatted text (`True`) or raw data dict (`False`)

**Output**: Formatted markdown report or structured data dictionary

**Key Features**:
- Configuration completeness scoring  
- Critical defaults risk flagging
- Component-by-component analysis with class visibility
- User-specified vs system default parameter visibility
- Suitable for due diligence packages and audit trails

**Example**:
```python
# Model documentation
assumptions_doc = results.reporting.assumptions_summary()
print(assumptions_doc)

# Due diligence package with full defaults detail
full_doc = results.reporting.assumptions_summary(
    include_defaults_detail=True,
    focus_components=['asset', 'financing', 'exit']
)

# Raw data for further analysis
assumptions_data = results.reporting.assumptions_summary(formatted=False)
quality_score = assumptions_data['quality_assessment']['overall_score']
```

### Debug & Model Validation Utilities

Performa includes sophisticated debugging and model validation tools essential for financial modeling workflows and LLM development.

#### Polymorphic Object Introspection

**`dump_performa_object(obj, exclude_defaults=True, include_computed=False, include_class_info=True)`**

Polymorphic debugging utility that can introspect any Performa object type:

- **Deal objects**: Complete deal analysis with component breakdown
- **Asset objects**: Property models, development projects, blueprints  
- **Pattern objects**: High-level deal patterns (ResidentialDevelopmentPattern, etc.)
- **Primitive objects**: Core system components (Timeline, GlobalSettings, etc.)
- **Debt objects**: Financing plans and facility structures
- **Construct results**: Factory function outputs

**Key Features**:
- Automatic object type classification and appropriate handler dispatch
- Class name visibility for understanding object hierarchy
- Configuration parameter extraction with defaults filtering
- Computed property access for complex derived metrics

**Example**:
```python
from performa.reporting.debug import dump_performa_object

# Debug any object type
timeline_config = dump_performa_object(timeline)
pattern_config = dump_performa_object(residential_pattern) 
deal_config = dump_performa_object(complete_deal)

print(f"Object type: {pattern_config['_object_info']['object_type']}")
print(f"Class: {pattern_config['_object_info']['class_name']}")
```

#### Configuration Intentionality Analysis

**`analyze_configuration_intentionality(obj, critical_params=None)`**

Analyzes what's user-specified vs system defaults to identify potential configuration risks:

- **Configuration completeness scoring**: Percentage of parameters explicitly set
- **Critical defaults risk assessment**: Flags key parameters using potentially dangerous defaults
- **User specification ratio**: Explicit vs defaulted parameter visibility
- **Actionable recommendations**: Specific steps to improve configuration quality

**Example**:
```python
from performa.reporting.debug import analyze_configuration_intentionality

# Analyze configuration intentionality
analysis = analyze_configuration_intentionality(
    pattern, 
    critical_params=['exit_cap_rate', 'target_rent', 'interest_rate']
)

print(f"Configuration completeness: {analysis['intentionality_metrics']['completeness_score']:.1%}")
print(f"Critical defaults: {len(analysis['risk_assessment']['critical_defaults'])}")

# Compare two approaches
from performa.reporting.debug import compare_configuration_intentionality
comparison = compare_configuration_intentionality(
    comp_deal, pattern_deal, "Composition", "Pattern"
)
print(f"Intentionality parity: {comparison['intentionality_parity']}")
```

#### Ledger Analysis & Validation

**`analyze_ledger_semantically(ledger)`**

Comprehensive semantic analysis of financial ledger data for debugging and validation:

- **Cash flow pattern analysis**: Timeline validation and flow categorization
- **Anomaly detection**: Magnitude, sign, and timing issue identification  
- **Balance validation**: Mathematical consistency checks
- **Category breakdown**: Analysis by financial category and subcategory

**Example**:
```python
from performa.reporting.debug import analyze_ledger_semantically, ledger_sanity_check

# Semantic ledger analysis
analysis = analyze_ledger_semantically(results.ledger)
print(f"Total records: {analysis['record_count']:,}")
print(f"Timeline span: {analysis['date_range']['span_months']:.1f} months")

# Quick sanity check
warnings = ledger_sanity_check(results.ledger, expected_returns={"irr": 0.18})
for warning in warnings:
    print(warning)
```

### Universal Reports

#### Pro Forma Summary (`pro_forma_summary()`)

Comprehensive financial summary supporting multiple time frequencies.

**Parameters**:
- `frequency`: `'A'` (annual, default), `'Q'` (quarterly), `'M'` (monthly)

**Output**: `pandas.DataFrame` with financial line items as index and time periods as columns.

**Key Line Items**:
- Potential Gross Revenue
- Effective Gross Income  
- Total Operating Expenses
- Net Operating Income
- Capital Expenditures
- Unlevered Cash Flow

**Example**:
```python
# Annual summary for executive presentations
annual_pf = results.reporting.pro_forma_summary(frequency="A")
print(annual_pf)

#                          2024-12-31   2025-12-31   2026-12-31   ...
# Potential Gross Revenue    2,100,000    2,100,000    2,100,000
# Effective Gross Income     1,932,000    1,932,000    1,932,000  
# Total Operating Expenses     517,200      517,200      517,200
# Net Operating Income       1,414,800    1,414,800    1,414,800
# ...

# Quarterly detail for operational planning
quarterly_pf = results.reporting.pro_forma_summary(frequency="Q")
assert quarterly_pf.shape[1] >= annual_pf.shape[1] * 4  # More periods
```

### Development Reports

#### Sources and Uses (`sources_and_uses()`)

Industry-standard development financing breakdown.

**Availability**: Development deals only
**Output**: `Dict[str, Any]` with structured sources/uses data

**Example**:
```python
if hasattr(results, 'development_analysis'):
    sources_uses = results.reporting.sources_and_uses()
    print(sources_uses)
    
    #                     Amount
    # USES
    # Land Acquisition   5,000,000
    # Construction      15,000,000  
    # Soft Costs         2,000,000
    # ...
    # SOURCES  
    # Equity             7,000,000
    # Construction Loan 15,000,000
    # ...
```

## Custom Report Development

### BaseReport Implementation

All reports inherit from `BaseReport` to ensure consistent architecture:

```python
from performa.reporting import BaseReport
import pandas as pd

class CustomMetricsReport(BaseReport):
    """Custom report showing key investment metrics."""
    
    def generate(self, **kwargs) -> pd.DataFrame:
        """
        Generate investment metrics summary.
        
        Returns:
            DataFrame with investment metrics and values
        """
        # Access analysis results via self._results
        deal_metrics = self._results.deal_metrics
        
        metrics_data = {
            'Metric': [
                'IRR',
                'Equity Multiple', 
                'Cash-on-Cash (Year 1)',
                'Total Return',
                'Total Equity Invested'
            ],
            'Value': [
                f"{deal_metrics.irr:.2%}",
                f"{deal_metrics.equity_multiple:.2f}x",
                f"{deal_metrics.cash_on_cash:.2%}",
                f"{deal_metrics.total_return:.2%}",
                f"${deal_metrics.total_equity_invested:,.0f}"
            ]
        }
        
        return pd.DataFrame(metrics_data)

# Usage
class CustomReportingInterface:
    def __init__(self, results):
        self._results = results
    
    def investment_metrics(self):
        return CustomMetricsReport(self._results).generate()

# Integration with results
custom_interface = CustomReportingInterface(results)
metrics_report = custom_interface.investment_metrics()
```

### Report Registration

Extend the standard interface by subclassing `ReportingInterface`:

```python
from performa.reporting.interface import ReportingInterface

class ExtendedReportingInterface(ReportingInterface):
    """Extended reporting with custom reports."""
    
    def investment_metrics(self):
        """Generate investment metrics summary."""
        return CustomMetricsReport(self._results).generate()
    
    def cash_flow_detail(self, annual_only=True):
        """Generate detailed cash flow analysis."""
        frequency = "A" if annual_only else "M"
        # Custom implementation
        pass

# Usage would require modifying DealAnalysisResult.reporting property
```

## Architecture Benefits

### Data Integrity

**Single Source of Truth**: Reports extract data from completed analysis results, eliminating calculation inconsistencies.

**No Recalculation**: Reports format existing data rather than recalculating, ensuring performance and accuracy.

**Validation Upstream**: Analysis engine validates all calculations before reporting, catching errors early.

### User Experience

**Intuitive Access**: `results.reporting.method()` pattern provides discoverable interface.

**Flexible Formatting**: Multiple frequency options support different use cases without API complexity.

**Consistent Interface**: All reports follow same access pattern regardless of deal type or complexity.

### Maintainability

**Separation of Concerns**: Report logic separate from analysis logic enables independent evolution.

**Extensible Design**: `BaseReport` framework supports custom reports without core modifications.

**Cache Optimization**: Interface caching reduces object creation overhead for multiple report generation.



## Performance Considerations

### Caching Strategy

- **Interface Caching**: `ReportingInterface` instances cached on `DealAnalysisResult`
- **Data Reuse**: Reports extract from pre-calculated analysis results  
- **Lazy Generation**: Reports generated only when requested

### Memory Management

- **Result References**: Reports hold references to analysis results, not copies
- **DataFrame Efficiency**: Reports return pandas DataFrames for optimal memory usage
- **Streaming Friendly**: Large datasets can be processed in chunks if needed

## Testing Reports

### Unit Testing Pattern

```python
import pytest
# Note: ProFormaReport is internal - for custom reports, extend ReportingInterface instead
from performa.reporting.financial_reports import ProFormaReport

def test_pro_forma_report_generation(sample_analysis_results):
    """Test pro forma report generates correctly."""
    report = ProFormaReport(sample_analysis_results)
    summary = report.generate(frequency="A")
    
    # Validate structure
    assert isinstance(summary, pd.DataFrame)
    assert 'Net Operating Income' in summary.index
    assert summary.shape[1] >= 5  # At least 5 years
    
    # Validate data integrity
    noi_values = summary.loc['Net Operating Income']
    assert all(noi_values > 0)  # Positive NOI expected
    
def test_fluent_interface_caching(sample_analysis_results):
    """Test reporting interface caching."""
    interface1 = sample_analysis_results.reporting
    interface2 = sample_analysis_results.reporting
    assert interface1 is interface2
```

### Integration Testing

```python
def test_end_to_end_reporting_workflow():
    """Test complete analysis to reporting workflow."""
    from datetime import date
    from performa.patterns import ValueAddAcquisitionPattern
    from performa.deal import analyze
    from performa.core.primitives import Timeline
    
    # Create deal via pattern
    pattern = ValueAddAcquisitionPattern(
        property_name="Test Property",
        acquisition_date=date(2024, 1, 1),
        acquisition_price=5_000_000,
        renovation_budget=800_000,
        current_avg_rent=1_500,
        target_avg_rent=1_800,
        hold_period_years=5,
        ltv_ratio=0.75
    )
    deal = pattern.create()
    
    # Analyze deal
    timeline = Timeline.from_dates("2024-01-01", "2029-12-31")
    results = analyze(deal, timeline)
    
    # Generate reports
    annual_pf = results.reporting.pro_forma_summary(frequency="A")
    quarterly_pf = results.reporting.pro_forma_summary(frequency="Q")
    
    # Validate consistency
    assert annual_pf.shape[0] == quarterly_pf.shape[0]  # Same line items
    assert quarterly_pf.shape[1] >= annual_pf.shape[1] * 4  # More periods
```

## Debug Module Architecture

The debug utilities have been refactored into a clean nested module structure for maintainability:

```
src/performa/reporting/debug/
├── __init__.py              # Public API + backward compatibility
├── introspection.py         # Object dumping & classification  
├── ledger_analysis.py       # Ledger semantic analysis
└── config_analysis.py       # Configuration intentionality
```

### Backward Compatibility

All existing imports continue to work through the public API:

```python
# These imports work exactly as before
from performa.reporting.debug import dump_performa_object
from performa.reporting.debug import analyze_ledger_semantically
from performa.reporting.debug import analyze_configuration_intentionality

# New imports also work for direct module access
from performa.reporting.debug.introspection import _classify_performa_object
from performa.reporting.debug.config_analysis import generate_configuration_report
```

### LLM Development Integration

The debug utilities are specifically designed to support LLM development workflows:

**CLAUDE.md Integration**: Enhanced with debugging guidance for LLM agents
**Cursor Rules**: Model validation requirements for consistent LLM output
**Configuration Analysis**: Automated detection of parameter quality issues
**Ledger Validation**: Mathematical soundness verification for all scenarios

This architecture ensures reliable, maintainable, and user-friendly report generation while maintaining strict separation between analysis calculations and presentation formatting. 