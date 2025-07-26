# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Performa Deal Analysis API

Main entry point for deal-level analysis functionality.
"""

from typing import Optional

from ..core.primitives import GlobalSettings, Timeline
from .deal import Deal
from .orchestrator import DealCalculator
from .results import DealAnalysisResult


def analyze(
    deal: Deal,
    timeline: Timeline,
    settings: Optional[GlobalSettings] = None
) -> DealAnalysisResult:
    """
    Analyze a complete real estate deal with strongly-typed results.
    
    This is the public API for comprehensive deal-level analysis, providing 
    strongly-typed Pydantic models for all analysis components.
    
    The analysis orchestrates the complete workflow from unlevered asset analysis
    through financing integration to final partner distributions using the
    DealCalculator service class.
    
    Args:
        deal: Complete Deal specification with asset, financing, and equity structure
        timeline: Analysis timeline for cash flow projections
        settings: Optional analysis settings (defaults to standard settings)
        
    Returns:
        DealAnalysisResult containing strongly-typed analysis components:
        - deal_summary: Deal metadata and characteristics
        - unlevered_analysis: Asset-level analysis results
        - financing_analysis: Debt service and facility information
        - levered_cash_flows: Cash flows after debt service
        - partner_distributions: Equity waterfall results
        - deal_metrics: IRR, equity multiple, and other deal-level metrics
        
    Example:
        ```python
        from performa.deal import Deal, analyze
        from performa.asset.office import OfficeProperty
        from performa.debt import FinancingPlan
        from performa.core.primitives import Timeline
        
        # Create deal structure
        deal = Deal(
            name="Office Acquisition",
            asset=office_property,
            acquisition=acquisition_terms,
            financing=FinancingPlan(facilities=[permanent_loan]),
            disposition=disposition_valuation
        )
        
        # Analyze with strongly-typed results
        timeline = Timeline.from_dates('2024-01-01', '2033-12-31')
        results = analyze(deal, timeline)
        
        # Access results with IDE autocompletion
        print(f"Deal IRR: {results.deal_metrics.irr:.2%}")
        print(f"Equity Multiple: {results.deal_metrics.equity_multiple:.2f}x")
        
        # Access partner-specific results
        if results.partner_distributions and results.partner_distributions.distribution_method == "waterfall":
            waterfall_details = results.partner_distributions.waterfall_details
            for partner_name, partner_result in waterfall_details.partner_results.items():
                print(f"{partner_name} IRR: {partner_result.irr:.2%}")
        ```
    """
    # Initialize default settings if not provided
    if settings is None:
        settings = GlobalSettings()
    
    # Create and run the DealCalculator service
    calculator = DealCalculator(deal, timeline, settings)
    return calculator.run() 