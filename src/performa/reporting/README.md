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
from performa.deal import analyze
from performa.patterns import create_value_add_acquisition_deal
from performa.core.primitives import Timeline

# Create and analyze deal
deal = create_value_add_acquisition_deal(
    property_name="Riverside Gardens",
    acquisition_price=10_000_000,
    renovation_budget=1_500_000,
    stabilized_noi=1_470_000,
    hold_period_years=7,
    ltv_ratio=0.75
)

timeline = Timeline.from_dates("2024-01-01", "2030-12-31")
results = analyze(deal, timeline)

# Generate reports via fluent interface
annual_summary = results.reporting.pro_forma_summary()              # Default: annual
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
**Output**: `pandas.DataFrame` with sources/uses categories and amounts

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
                'Unlevered IRR',
                'Levered IRR', 
                'Cash-on-Cash (Year 1)',
                'Total Return Multiple',
                'Peak Equity Requirement'
            ],
            'Value': [
                f"{deal_metrics.unlevered_irr:.2%}",
                f"{deal_metrics.levered_irr:.2%}",
                f"{deal_metrics.year_1_coc:.2%}",
                f"{deal_metrics.total_return:.2f}x",
                f"${deal_metrics.peak_equity:,.0f}"
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

## Migration from Legacy Patterns

### Old Pattern (Deprecated)
```python
# OLD: Factory functions operating on input specifications
from performa.reporting import create_pro_forma_summary

# Required manual data extraction and calculation
summary = create_pro_forma_summary(
    property_model=deal.asset,
    timeline=timeline,
    # ... many manual parameters
)
```

### New Pattern (Current)
```python
# NEW: Fluent interface operating on analysis results
results = analyze(deal, timeline)
summary = results.reporting.pro_forma_summary()

# Benefits:
# - Automatic data extraction from results
# - No manual parameter coordination
# - Guaranteed consistency with analysis
# - Intuitive, discoverable interface
```

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
    from performa.patterns import create_value_add_acquisition_deal
    from performa.deal import analyze
    from performa.core.primitives import Timeline
    
    # Create deal via pattern
    deal = create_value_add_acquisition_deal(
        property_name="Test Property",
        acquisition_price=5_000_000,
        renovation_budget=800_000,
        stabilized_noi=450_000,
        hold_period_years=5,
        ltv_ratio=0.75
    )
    
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

This reporting architecture ensures reliable, maintainable, and user-friendly report generation while maintaining strict separation between analysis calculations and presentation formatting. 