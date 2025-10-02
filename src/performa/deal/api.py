# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Deal Analysis API

Public entry point for running complete deal analyses, including asset,
financing, and partnership flows, with results backed by the transactional
ledger. Asset-only analysis is provided in `performa.analysis.api`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from performa.core.ledger import Ledger
from performa.core.primitives import GlobalSettings, Timeline
from performa.deal.orchestrator import DealCalculator

# Localize heavy imports to call-sites to reduce import-time overhead
if TYPE_CHECKING:  # keep type checking-friendly without runtime import side effects
    from performa.analysis.results import AssetAnalysisResult
    from performa.deal.deal import Deal
    from performa.deal.results import DealResults


def analyze(
    deal: "Deal",
    timeline: "Timeline",
    settings: Optional["GlobalSettings"] = None,
    asset_analysis: Optional["AssetAnalysisResult"] = None,
    ledger: Optional["Ledger"] = None,
) -> "DealResults":
    """
    Analyze a complete real estate deal and return strongly-typed results.

    Workflow:
      1) Run asset analysis (or reuse an existing asset_analysis)
      2) Execute deal-level analyzers (debt, cash flow, partnership)
      3) Return a DealResults object backed by the ledger

    Args:
        deal: Complete deal specification (asset, acquisition, financing, equity).
        timeline: Timeline for the analysis (monthly PeriodIndex expected downstream).
        settings: Optional global settings; created if not provided.
        asset_analysis: Optional asset-level result to reuse; when present, its
            ledger is used to ensure a single source of truth.
        ledger: Optional ledger instance; used when asset_analysis is not given.

    Returns:
        DealResults with summary, unlevered and levered flows, financing details,
        partner distributions, and deal metrics. All series are derived from the ledger.
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
        current_ledger = Ledger()
        calculator = DealCalculator(deal, timeline, settings)

    # Run deal analysis with the determined ledger
    return calculator.run(ledger=current_ledger)
