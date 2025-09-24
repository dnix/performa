# Performa `asset` Models

This module provides comprehensive real estate asset modeling capabilities across
all major property types. Each asset module implements property-specific modeling
logic while maintaining consistency through shared base classes and patterns.

## Supported Asset Types

### Office (`performa.asset.office`)
- Multi-tenant commercial office buildings
- Complex lease structures with escalations and recovery methods
- Tenant improvement and leasing commission modeling
- Rollover analysis with renewal vs. market scenarios
- Absorption planning for vacant space lease-up

### Residential (`performa.asset.residential`)
- Multifamily residential properties
- Unit-centric modeling approach (unit mix vs. individual leases)
- Residential-specific rollover and absorption modeling
- Simplified lease structures appropriate for residential

### Coming Soon
- **Retail**: Shopping centers and retail properties
- **Industrial**: Warehouse and distribution facilities  
- **Hotel**: Hospitality asset modeling
- and more...

## Architecture

Each asset module follows consistent patterns:
- **Property model** as the main container
- **Analysis scenario** for cash flow orchestration
- **Asset-specific lease, expense, and revenue models**
- **Blueprint classes** for development modeling
- **Rollover profiles** for lease transition modeling

## Key Design Principles

- **Property-type expertise** through specialized models
- **Shared foundation** via core base classes
- **Consistent analysis patterns** across asset types
- **Flexible modeling** for simple to complex scenarios
- **Industry-standard terminology** and methodologies

## Example Usage

```python
from performa.asset.office import OfficeProperty, OfficeAnalysisScenario
from performa.asset.residential import ResidentialProperty
from performa.analysis import run

# Office property analysis
office_scenario = run(office_property, timeline, settings)

# Residential property analysis  
residential_scenario = run(residential_property, timeline, settings)
```

The asset module enables sophisticated modeling while maintaining simplicity
for straightforward analyses, supporting everything from single-tenant net
lease properties to complex mixed-use developments. 