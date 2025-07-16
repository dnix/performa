"""
Deal Analysis Specialist Services

This module provides the specialist services that handle different aspects of deal analysis 
with clean separation of concerns and domain-driven design principles.

The analysis workflow follows a systematic multi-pass approach:
1. **Asset Analysis** - Unlevered asset performance analysis
2. **Valuation Analysis** - Property valuation and disposition proceeds
3. **Debt Analysis** - Financing structure and debt service calculations
4. **Cash Flow Analysis** - Institutional-grade funding cascade
5. **Partnership Analysis** - Equity waterfall and partner distributions

Architecture:
    - Each service is a focused specialist with clear responsibilities
    - Services use dataclass patterns for runtime state management
    - All services return strongly-typed Pydantic models
    - Services can be used independently or orchestrated together

Example:
    ```python
    from performa.deal.analysis import (
        AssetAnalyzer, DebtAnalyzer, CashFlowEngine, 
        PartnershipAnalyzer, ValuationEngine
    )
    
    # Independent usage
    asset_analyzer = AssetAnalyzer(deal, timeline, settings)
    unlevered_results = asset_analyzer.analyze_unlevered_asset()
    
    # Orchestrated usage (see orchestrator.py)
    debt_analyzer = DebtAnalyzer(deal, timeline, settings)
    financing_results = debt_analyzer.analyze_financing_structure(
        property_value_series, noi_series, unlevered_results
    )
    ```

Design Principles:
    - **Single Responsibility**: Each service handles one aspect of analysis
    - **Dependency Injection**: Services receive dependencies through constructor
    - **Immutable Results**: All results are returned as immutable models
    - **Type Safety**: Comprehensive type hints and Pydantic validation
    - **Error Handling**: Graceful degradation with detailed error reporting
    - **Institutional Grade**: Implements real-world financial modeling standards
"""

from .asset import AssetAnalyzer
from .cash_flow import CashFlowEngine
from .debt import DebtAnalyzer
from .partnership import PartnershipAnalyzer
from .valuation import ValuationEngine

__all__ = [
    "AssetAnalyzer",
    "CashFlowEngine", 
    "DebtAnalyzer",
    "PartnershipAnalyzer",
    "ValuationEngine",
] 