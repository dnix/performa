# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Performa Deal Analysis API

Main entry point for deal-level analysis functionality.
"""

from typing import TYPE_CHECKING, Optional

from performa.core.ledger import Ledger, LedgerGenerationSettings
from performa.core.primitives import GlobalSettings, Timeline
from performa.deal.deal import Deal
from performa.deal.orchestrator import DealCalculator
from performa.deal.results import DealAnalysisResult

if TYPE_CHECKING:
    from performa.analysis.results import AssetAnalysisResult
    from performa.core.ledger import Ledger


def analyze(
    deal: Deal,
    timeline: Timeline,
    settings: Optional[GlobalSettings] = None,
    asset_analysis: Optional["AssetAnalysisResult"] = None,
    ledger: Optional["Ledger"] = None,
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
        asset_analysis: Optional pre-computed asset analysis result to reuse.
            If provided, its ledger will be used (Pass-the-Builder pattern).
            If not provided, a new analysis will be run on deal.asset.
        ledger: Optional Ledger to use for the analysis.
            Priority: asset_analysis.ledger > ledger > new Ledger.
            This enables maximum flexibility for testing and complex workflows.

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

    # Determine ledger source with validation (Pass-the-Builder pattern)
    # This supports maximum flexibility while preventing ambiguous cases

    if asset_analysis is not None and ledger is not None:
        # CASE: Both asset_analysis and ledger provided
        # Validate they're the same instance to prevent confusion
        if asset_analysis.ledger is not ledger:
            raise ValueError(
                "Conflicting ledgers provided. When both asset_analysis and "
                "ledger are specified, they must be the same instance. "
                "Use either asset_analysis (to reuse existing analysis) or "
                "ledger (for custom ledger), but not both with different instances."
            )
        # Same instance - use it (explicit validation passed)
        current_ledger = asset_analysis.ledger
        calculator = DealCalculator(
            deal, timeline, settings, asset_analysis=asset_analysis
        )

    elif asset_analysis is not None:
        # CASE: Only asset_analysis provided - reuse existing analysis
        # Use the ledger from the pre-computed asset analysis
        current_ledger = asset_analysis.ledger
        calculator = DealCalculator(
            deal, timeline, settings, asset_analysis=asset_analysis
        )

    elif ledger is not None:
        # CASE: Only ledger provided - use custom ledger
        # Run fresh asset analysis with the provided ledger
        current_ledger = ledger
        calculator = DealCalculator(deal, timeline, settings)

    else:
        # CASE: Neither provided - create fresh analysis
        # Create new ledger for complete fresh analysis
        current_ledger = Ledger(settings=LedgerGenerationSettings())
        calculator = DealCalculator(deal, timeline, settings)

    # Run deal analysis with the determined ledger
    return calculator.run(ledger=current_ledger)
