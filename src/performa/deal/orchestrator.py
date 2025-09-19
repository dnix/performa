# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Deal Analysis Orchestrator

This module provides the DealCalculator service that orchestrates the complete deal analysis workflow
by delegating to specialist services while maintaining a clean public API and comprehensive functionality.

The DealCalculator serves as the central orchestrator for the entire deal analysis framework, coordinating
the execution of specialist services in the proper sequence to produce comprehensive deal analysis results.
It implements the multi-pass analysis approach that ensures all components have access to the data they need.

The orchestrator follows the established analysis workflow:
1. **Unlevered Asset Analysis** - Pure asset performance without financing effects
2. **Valuation Analysis** - Property value estimation and disposition proceeds calculation
3. **Debt Analysis** - Financing structure analysis with DSCR and covenant monitoring
4. **Cash Flow Analysis** - Institutional-grade funding cascade and levered cash flows
5. **Partnership Analysis** - Equity waterfall and partner distribution calculations
6. **Deal Metrics** - Comprehensive deal-level performance metrics

Key capabilities:
- **Multi-Pass Analysis**: Systematic execution of analysis services in proper sequence
- **Typed State Management**: Maintains strongly-typed intermediate results during analysis
- **Comprehensive Results**: Returns complete DealResults with all analysis components
- **Error Handling**: Robust error handling with graceful degradation and detailed error reporting

The orchestrator implements the "orchestration pattern" where it coordinates specialist services
without duplicating their logic, ensuring clean separation of concerns and maintainability.

Example:
    ```python
    from performa.deal.orchestrator import DealCalculator

    # Create orchestrator with dependencies
    calculator = DealCalculator(deal, timeline, settings)

    # Execute complete analysis workflow
    results = calculator.run()

    # Access comprehensive results
    print(f"Deal IRR: {results.deal_metrics.irr:.2%}")
    print(f"DSCR minimum: {results.financing_analysis.dscr_summary.minimum_dscr:.2f}")
    print(f"Partner count: {len(results.partner_distributions.waterfall_details.partner_results)}")
    ```

Architecture:
    - Uses dataclass pattern for runtime service orchestration
    - Maintains typed state during multi-pass analysis execution
    - Delegates to specialist services for domain-specific logic
    - Returns strongly-typed results with comprehensive component access

Integration:
    - Integrates with all specialist services in the analysis module
    - Provides comprehensive error handling and logging
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

import pandas as pd

from performa.analysis import run
from performa.analysis.orchestrator import AnalysisContext
from performa.core.primitives import (
    GlobalSettings,
    Timeline,
)
from performa.deal.analysis import (
    AcquisitionAnalyzer,
    CashFlowEngine,
    DebtAnalyzer,
    DispositionAnalyzer,
    PartnershipAnalyzer,
    ValuationEngine,
)

if TYPE_CHECKING:
    from performa.analysis.results import AssetAnalysisResult
    from performa.core.ledger import Ledger
    from performa.deal.deal import Deal
    from performa.deal.results import DealResults

logger = logging.getLogger(__name__)


@dataclass
class DealContext:
    """
    A mutable container for the complete state of a deal-level analysis run.

    This is the deal-level parallel to AnalysisContext, designed specifically
    for deal-level models like debt facilities, valuations, fees, and partnerships.
    Unlike AnalysisContext which focuses on asset-level operations (leases, expenses),
    DealContext provides deal-centric data and eliminates the semantic mismatch
    that was causing frozen model mutations and defensive programming.

    ARCHITECTURE - DUAL CONTEXT PATTERN:
    - AnalysisContext: For asset-level models (leases, expenses, recovery)
    - DealContext: For deal-level models (debt, valuation, fees, partnership)

    This separation provides:
    - Clean interfaces without defensive hasattr() checks
    - No frozen model mutations (object.__setattr__ hacks)
    - Clear semantic meaning for each model type
    - Proper data access patterns for each domain

    Key Design Principles:
    - Single source of truth via ledger (Pass-the-Builder pattern)
    - Deal-centric data access (full Deal object, not just asset)
    - Deal-level metrics readily available (property value, NOI, project costs)
    - Clean separation from asset-specific data (no recovery states, lease contexts)

    Example:
        ```python
        # Create context for deal-level analysis
        context = DealContext(
            timeline=timeline,
            settings=settings,
            ledger=ledger,
            deal=deal,
            property_value=valuation_series,
            noi_series=noi_series,
            project_costs=total_development_cost
        )

        # Use with deal-level models
        debt_service = facility.compute_cf(context)  # No more hacks!
        disposition_value = reversion.calculate(context)
        ```
    """

    # --- Configuration (Set at creation) ---
    timeline: "Timeline"
    settings: "GlobalSettings"
    ledger: "Ledger"
    deal: "Deal"

    # --- Deal-Level Metrics (Optional - populated as needed) ---
    noi_series: Optional[pd.Series] = None
    project_costs: Optional[float] = None

    # --- Valuation-Specific Metrics ---
    refi_property_value: Optional[pd.Series] = (
        None  # Conservative valuation for refinancing/LTV
    )
    exit_gross_proceeds: Optional[pd.Series] = (
        None  # Exit proceeds from user-defined valuation
    )

    def __post_init__(self):
        """Validate required fields after initialization."""
        # Validate that ledger is provided (critical for Pass-the-Builder pattern)
        if self.ledger is None:
            raise ValueError(
                "DealContext requires a ledger instance. "
                "This enforces the Pass-the-Builder pattern where a single Ledger "
                "is created at the API level and passed through all deal analysis components."
            )

        # Validate that deal is provided
        if self.deal is None:
            raise ValueError(
                "DealContext requires a deal instance for deal-level operations."
            )

    @classmethod
    def from_analysis_context(
        cls,
        analysis_context: AnalysisContext,
        deal: "Deal",
        noi_series: Optional[pd.Series] = None,
        project_costs: Optional[float] = None,
        refi_property_value: Optional[pd.Series] = None,
        exit_gross_proceeds: Optional[pd.Series] = None,
    ) -> "DealContext":
        """
        Factory method to create DealContext from existing AnalysisContext.

        This provides a migration path during the transition period and enables
        creating deal contexts from asset analysis results.

        Args:
            analysis_context: Existing AnalysisContext from asset analysis
            deal: Deal object for deal-level operations
            property_value: Optional property value series for valuations
            noi_series: Optional NOI series for debt analysis
            project_costs: Optional total project costs for development deals

        Returns:
            New DealContext with deal-specific configuration

        Example:
            ```python
            # Convert asset context to deal context
            deal_context = DealContext.from_analysis_context(
                analysis_context=asset_context,
                deal=deal,
                noi_series=noi_from_asset_analysis,
                property_value=property_value_series
            )

            # Now use with deal models
            debt_service = facility.compute_cf(deal_context)
            ```
        """
        return cls(
            timeline=analysis_context.timeline,
            settings=analysis_context.settings,
            ledger=analysis_context.ledger,
            deal=deal,
            noi_series=noi_series,
            project_costs=project_costs,
            refi_property_value=refi_property_value,
            exit_gross_proceeds=exit_gross_proceeds,
        )


@dataclass
class DealCalculator:
    """
    Service class that orchestrates the complete deal analysis workflow.

    This class encapsulates the multi-step analysis logic as internal state,
    providing a clean, maintainable structure for complex deal analysis.

    The analysis proceeds through distinct sequential steps:
    1. Unlevered asset analysis using the core analysis engine
    2. Financing integration and debt service calculations
    3. Performance metrics calculation (DSCR time series)
    4. Levered cash flow calculation with funding cascade
    5. Partner distribution calculations (equity waterfall)
    6. Deal-level performance metrics calculation

    Architecture:
    - Uses dataclass for runtime service (not a data model)
    - Maintains mutable typed state during analysis using Pydantic models
    - Returns strongly-typed result models
    - Delegates to specialist services for complex logic

    Example:
        ```python
        calculator = DealCalculator(deal, timeline, settings)
        results = calculator.run()

        # Access strongly-typed results
        print(f"Deal IRR: {results.deal_metrics.irr:.2%}")
        print(f"Partner count: {len(results.partner_distributions.partner_results)}")
        ```
    """

    # Input Parameters
    deal: Deal
    timeline: Timeline
    settings: GlobalSettings
    asset_analysis: Optional["AssetAnalysisResult"] = (
        None  # Pre-computed asset analysis to reuse
    )

    # === STATE VARIABLES ELIMINATED ===
    # Previously: 6 complex intermediate result objects stored state
    # Now: Stateless orchestrator - results come directly from ledger

    def run(self, ledger: "Ledger") -> "DealResults":
        """
        Orchestrate deal analysis through a predictable sequence.
        Each pass enriches the context and/or writes to the ledger.
        No defensive programming - we know what we need and when.

        Args:
            ledger: The analysis ledger (Pass-the-Builder pattern).
                Must be the same instance used throughout the analysis.

        Returns:
            DealResults containing all analysis results from the ledger

        Raises:
            ValueError: If deal structure is invalid
            RuntimeError: If analysis fails during execution
        """
        try:
            # === INITIALIZATION ===
            # Get or compute asset analysis (always needed)
            # TODO: refactor asset analysis to match deal orchestrator
            asset_result = self.asset_analysis or run(
                model=self.deal.asset,
                timeline=self.timeline,
                settings=self.settings,
                ledger=ledger,
            )

            # Initialize context that will be progressively enriched
            deal_context = DealContext(
                timeline=self.timeline,
                settings=self.settings,
                ledger=ledger,
                deal=self.deal,
            )

            # === ACQUISITION PASS ===
            # Process acquisition and calculate initial project costs
            AcquisitionAnalyzer(deal_context).process()
            # Context now contains project_costs

            # === VALUATION PASS ===
            # Always run - provides critical data for multiple downstream passes
            ValuationEngine(deal_context).process()
            # Context now contains property_value and gross_proceeds

            # === DEBT PASS ===
            # Always run - even if no debt, creates empty series for consistency
            DebtAnalyzer(deal_context).process()

            # === DISPOSITION PASS ===
            # Always run - processes exit if applicable
            DispositionAnalyzer(deal_context).process()

            # === CASH FLOW PASS ===
            # Always run - core calculation
            CashFlowEngine(deal_context).process()

            # === PARTNERSHIP PASS ===
            # Always run - handles single owner or complex waterfall
            PartnershipAnalyzer(deal_context).process()

            # Return clean results that query the ledger
            from performa.deal.results import DealResults
            return DealResults(self.deal, self.timeline, ledger)

        except Exception as e:
            raise RuntimeError(f"Deal analysis failed: {str(e)}") from e
