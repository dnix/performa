# Performa - Open-Source Real Estate Financial Modeling Framework

Performa is a comprehensive real estate financial modeling framework that provides
the building blocks for sophisticated real estate analysis, from simple property
valuations to complex development projects and institutional-grade deal structuring.

## Key Features

- **Asset-centric modeling** for office, residential, retail, and mixed-use properties
- **Development project modeling** with construction and lease-up phases
- **Deal-level analysis** with debt structuring and partner waterfalls
- **Flexible capital planning** with renovation and improvement modeling
- **Industry-standard reporting** and valuation methodologies

## Architecture

- **Core primitives** for cash flow modeling and timeline management
- **Asset-specific models** with property type expertise
- **Analysis engine** with dependency resolution and cash flow orchestration
- **Deal-level abstractions** for financing and partnership structures
- **Valuation tools** for DCF, direct cap, and sales comparison methods

## Example Usage

```python
from performa.asset.office import OfficeProperty
from performa.analysis import run
from performa.core.primitives import Timeline, GlobalSettings

# Create property model
property = OfficeProperty(...)

# Run analysis
timeline = Timeline.from_dates('2024-01-01', '2033-12-31')
scenario = run(property, timeline, GlobalSettings())

# Get results
cash_flows = scenario.summary_df
```

## Module Structure

- **`analysis/`** - Analysis engine and cash flow orchestration
- **`asset/`** - Asset-specific modeling (office, residential, retail, etc.)
- **`core/`** - Core primitives, base classes, and capital planning
- **`deal/`** - Deal-level structuring and partnership analysis
- **`debt/`** - Real estate finance and debt structuring
- **`development/`** - Development project modeling
- **`reporting/`** - Industry-standard reporting interface and debug utilities  
- **`valuation/`** - Property valuation methods

For detailed documentation and examples, see the individual module documentation. 