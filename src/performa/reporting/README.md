# Performa `reporting` Module - Industry Interface Layer

This module serves as the primary industry-facing interface for Performa,
translating internal architecture into familiar real estate terminology and formats.

## Key Principles

- **Keep internal models clean** and focused
- **Present industry-standard terminology** to users
- **Generate familiar report formats** (Argus-style, etc.)
- **Enable easy export** to Excel, PDF, PowerPoint

## Key Components

### Base Classes
- **Report**: Base class for all report types
- **ReportTemplate**: Template system for consistent formatting

### Development Reports
- **SourcesAndUsesReport**: Industry-standard Sources & Uses reporting
- **DevelopmentSummaryReport**: Development project summary with industry metrics
- **ConstructionDrawReport**: Monthly construction draw requests
- **LeasingStatusReport**: Market leasing status reporting

## Factory Functions (Primary User Interface)

### Industry-Standard Report Creation

```python
# Sources & Uses Report
from performa.reporting import create_sources_and_uses_report

sources_uses = create_sources_and_uses_report(development_project, template=None)

# Development Summary
from performa.reporting import create_development_summary

summary = create_development_summary(development_project, template=None)

# Construction Draw Request
from performa.reporting import create_draw_request

draw_request = create_draw_request(development_project, period, template=None)

# Leasing Status Report
from performa.reporting import create_leasing_status_report

leasing_status = create_leasing_status_report(
    development_project, 
    as_of_date, 
    template=None
)
```

## Architecture

The reporting module acts as a translation layer between Performa's internal
object model and industry-standard reporting formats, ensuring users receive
familiar, professional reports while maintaining clean internal architecture.

**Note**: This module is currently focused on development reporting but will
expand to support all asset types and analysis scenarios. 