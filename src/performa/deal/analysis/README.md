# Deal Analysis Specialist Services

This module provides the specialist services that handle different aspects of deal analysis with clean separation of concerns and domain-driven design principles.

## Overview

The deal analysis workflow follows a systematic multi-pass approach that ensures all components have access to the data they need:

1. **Asset Analysis** - Unlevered asset performance analysis
2. **Valuation Analysis** - Property valuation and disposition proceeds
3. **Debt Analysis** - Financing structure and debt service calculations
4. **Cash Flow Analysis** - Institutional-grade funding cascade
5. **Partnership Analysis** - Equity waterfall and partner distributions

## Architecture

- **Specialist Services**: Each service is a focused specialist with clear responsibilities
- **Dataclass Pattern**: Services use dataclass patterns for runtime state management
- **Typed Results**: All services return strongly-typed Pydantic models
- **Independent Usage**: Services can be used independently or orchestrated together
- **Institutional Standards**: Implements real-world financial modeling standards

## Services

### AssetAnalyzer

Handles unlevered asset performance analysis including scenario resolution and execution.

```python
from performa.deal.analysis import AssetAnalyzer

analyzer = AssetAnalyzer(deal, timeline, settings)
results = analyzer.analyze_unlevered_asset()
```

**Key Features:**
- Automatic scenario class resolution based on asset type
- Integration with existing analysis infrastructure
- Clean separation from financing and partnership concerns

### ValuationEngine

Handles property valuation calculations with sophisticated polymorphic dispatch across different valuation methodologies.

```python
from performa.deal.analysis import ValuationEngine

engine = ValuationEngine(deal, timeline, settings)
property_values = engine.extract_property_value_series(unlevered_analysis)
disposition_proceeds = engine.calculate_disposition_proceeds(unlevered_analysis)
```

**Key Features:**
- Intelligent property value estimation with multiple fallback strategies
- Type-safe NOI extraction using enum-based keys
- Polymorphic dispatch across different valuation models
- Sophisticated fallback and estimation strategies

### DebtAnalyzer

Handles comprehensive debt facility analysis including institutional-grade debt service calculations, refinancing transactions, and covenant monitoring.

```python
from performa.deal.analysis import DebtAnalyzer

debt_analyzer = DebtAnalyzer(deal, timeline, settings)
financing_results = debt_analyzer.analyze_financing_structure(
    property_value_series=property_values,
    noi_series=noi_series,
    unlevered_analysis=unlevered_results
)
```

**Key Features:**
- Enhanced debt service with floating rates and institutional features
- Comprehensive DSCR analysis with stress testing
- Refinancing transaction processing with cash flow impacts
- Institutional-grade covenant monitoring and breach detection

### CashFlowEngine

Handles institutional-grade funding cascade and levered cash flow calculations with comprehensive interest handling and equity/debt coordination.

```python
from performa.deal.analysis import CashFlowEngine

engine = CashFlowEngine(deal, timeline, settings)
levered_results = engine.calculate_levered_cash_flows(
    unlevered_analysis=unlevered_analysis,
    financing_analysis=financing_analysis,
    disposition_proceeds=disposition_proceeds
)
```

**Key Features:**
- Institutional funding cascade with equity-first, debt-second priority
- Multi-tranche debt funding with LTC threshold enforcement
- Comprehensive interest handling (cash vs. reserve-funded)
- Detailed component tracking for audit and analysis

### PartnershipAnalyzer

Handles complex partnership distribution calculations including sophisticated equity waterfall logic and fee distributions.

```python
from performa.deal.analysis import PartnershipAnalyzer

analyzer = PartnershipAnalyzer(deal, timeline, settings)
distribution_results = analyzer.calculate_partner_distributions(levered_cash_flows)
```

**Key Features:**
- Sophisticated IRR-based promote calculations with binary search precision
- Fee priority payment logic with actual payee allocation
- Comprehensive partner metrics calculation
- Support for complex promote structures with multiple hurdles

## Complete Workflow Example

```python
from performa.deal.analysis import (
    AssetAnalyzer, ValuationEngine, DebtAnalyzer, 
    CashFlowEngine, PartnershipAnalyzer
)

# 1. Asset Analysis
asset_analyzer = AssetAnalyzer(deal, timeline, settings)
unlevered_analysis = asset_analyzer.analyze_unlevered_asset()

# 2. Valuation Analysis
valuation_engine = ValuationEngine(deal, timeline, settings)
property_values = valuation_engine.extract_property_value_series(unlevered_analysis)
noi_series = valuation_engine.extract_noi_series(unlevered_analysis)
disposition_proceeds = valuation_engine.calculate_disposition_proceeds(unlevered_analysis)

# 3. Debt Analysis
debt_analyzer = DebtAnalyzer(deal, timeline, settings)
financing_analysis = debt_analyzer.analyze_financing_structure(
    property_values, noi_series, unlevered_analysis
)

# 4. Cash Flow Analysis
cash_flow_engine = CashFlowEngine(deal, timeline, settings)
levered_cash_flows = cash_flow_engine.calculate_levered_cash_flows(
    unlevered_analysis, financing_analysis, disposition_proceeds
)

# 5. Partnership Analysis
partnership_analyzer = PartnershipAnalyzer(deal, timeline, settings)
partner_distributions = partnership_analyzer.calculate_partner_distributions(
    levered_cash_flows.levered_cash_flows
)
```

## Institutional Standards

All services implement institutional-grade standards used in commercial real estate finance:

- **DSCR Calculations**: Follow institutional lending standards with proper covenant monitoring
- **Funding Cascade**: Implements the standard equity-first, debt-second funding priority
- **Waterfall Logic**: Uses IRR-based promote calculations with binary search precision
- **Interest Handling**: Supports cash and reserve-funded interest per institutional practices
- **Audit Trails**: Maintains detailed tracking for institutional reporting requirements

## Error Handling

All services provide robust error handling with:

- Graceful degradation when data is unavailable
- Comprehensive logging for debugging and audit purposes
- Type-safe error reporting through result models
- Fallback strategies to ensure analysis can continue

## Integration

The services integrate seamlessly with:

- **Orchestrator**: Use `DealCalculator` for complete workflow orchestration
- **Results Models**: All services return strongly-typed Pydantic models
- **Existing Tests**: Backward compatibility maintained for existing test suites
- **Broader Framework**: Clean integration with the performa analysis framework 