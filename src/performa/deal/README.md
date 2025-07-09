# Performa `deal` Models - Deal Structuring & Analysis

This module provides comprehensive deal-level modeling capabilities for real estate
transactions, supporting everything from simple acquisitions to complex multi-partner
development ventures with sophisticated waterfall structures.

## Key Components

### Core Deal Structure
- **Deal**: Complete deal container with asset, debt, equity, and partnership integration
- **AcquisitionTerms**: Purchase price, closing costs, and transaction timing
- **DealFee**: Flexible fee structures (acquisition, asset management, disposition)

### Partnership & Waterfalls
- **Partner**: Individual or entity with capital contributions and return expectations
- **PartnershipStructure**: Multi-partner deals with capital stack management
- **WaterfallTier**: Individual waterfall hurdles with IRR thresholds
- **WaterfallPromote**: Preferred return and promote distribution logic
- **CarryPromote**: Carried interest calculations for fund structures

### Analysis Engine
- **DistributionCalculator**: Cash flow distribution engine with waterfall mechanics
- **analyze_deal**: Main analysis function for complete deal scenarios

## Architecture

The deal module implements a sophisticated layered architecture:

1. **Asset-level cash flows** from property operations and development
2. **Debt-level cash flows** from financing facilities
3. **Equity-level cash flows** from partners and investors
4. **Distribution-level cash flows** through waterfall structures

## Design Principles

- Separation of asset performance from deal structure
- Flexible partnership configurations (50/50 to complex promotes)
- Industry-standard waterfall mechanics (preferred return, catch-up, promote)
- Scalable from single-asset to portfolio-level deals
- Integration with development and asset modules

## Key Features

- Multi-tier waterfall structures with IRR hurdles
- Carried interest and promote calculations
- Capital contribution tracking and return attribution
- Disposition proceeds allocation
- Partnership accounting and reporting

## Example Usage

```python
from performa.deal import (
    Deal, PartnershipStructure, Partner, WaterfallPromote, analyze_deal
)
from performa.asset.office import OfficeProperty
from performa.debt import PermanentFacility

# Create partnership structure
partnership = PartnershipStructure(
    partners=[
        Partner(name="GP", capital_contribution=500_000),
        Partner(name="LP", capital_contribution=4_500_000)
    ],
    waterfall=WaterfallPromote(
        preferred_return=0.08,
        promote_percentage=0.20,
        catch_up_percentage=1.0
    )
)

# Create deal
deal = Deal(
    name="Downtown Office Acquisition",
    asset=office_property,
    debt_facility=permanent_facility,
    partnership_structure=partnership,
    acquisition_terms=acquisition_terms
)

# Analyze deal returns
deal_results = analyze_deal(deal, timeline, settings)
partner_returns = deal_results.get_partner_distributions()
```

## Integration

This module integrates seamlessly with:
- **Asset modules** for property-level cash flows
- **Debt module** for financing structures
- **Development module** for construction and lease-up
- **Valuation module** for exit scenarios

The deal module enables institutional-grade financial analysis while
remaining accessible for simpler transactions and joint ventures. 