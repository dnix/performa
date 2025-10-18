# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Deal Analysis API

Public entry point for running complete deal analyses, including asset,
financing, and partnership flows, with results backed by the transactional
ledger. Asset-only analysis is provided in `performa.analysis.api`.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING, Optional

import pandas as pd

from performa.core.ledger import Ledger
from performa.core.primitives import GlobalSettings, Timeline
from performa.deal.orchestrator import DealCalculator

# Localize heavy imports to call-sites to reduce import-time overhead
if TYPE_CHECKING:  # keep type checking-friendly without runtime import side effects
    from performa.analysis.results import AssetAnalysisResult
    from performa.deal.deal import Deal
    from performa.deal.results import DealResults

logger = logging.getLogger(__name__)


def _extract_exit_period(deal: "Deal", timeline: Timeline) -> Optional[pd.Period]:
    """
    Extract exit period from deal's exit valuation if it occurs before timeline end.

    This prevents post-disposition phantom transactions by allowing the timeline
    to be clipped at the known exit date before asset analysis runs.

    Args:
        deal: Deal with potential exit valuation
        timeline: Analysis timeline

    Returns:
        Exit period if exit occurs before timeline end, None otherwise

    Returns None when:
    - No exit valuation exists (asset-only case)
    - Exit is at or beyond timeline end (no clipping needed)
    - Valuation doesn't specify hold_period_months
    """
    # Safely check for exit_valuation attribute and value
    exit_valuation = getattr(deal, "exit_valuation", None)
    if exit_valuation is None:
        return None  # Asset-only case or no exit planned

    # Check if valuation has hold_period_months attribute
    hold_months = getattr(exit_valuation, "hold_period_months", None)
    if hold_months is None:
        return None  # Exit at timeline end (default behavior) or doesn't specify timing

    if hold_months >= timeline.duration_months:
        return None  # Exit at or beyond timeline end

    # Exit occurs before timeline end → return exit period for clipping
    return timeline.period_index[hold_months]


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
      0) Clip timeline at exit date if deal has early disposition
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

    Note:
        If deal has exit_valuation with hold_period_months < timeline duration,
        the timeline is automatically clipped to prevent post-disposition phantom
        transactions. Asset-only cases (no exit_valuation) use full timeline.
    """
    # Initialize default settings if not provided
    if settings is None:
        settings = GlobalSettings()
    
    # CRITICAL FIX: Sync analysis_start_date with timeline if using default (today)
    # This ensures rent growth calculations are based on actual deal timeline, not current date
    if settings.analysis_start_date == date.today():
        settings = settings.model_copy(
            update={"analysis_start_date": timeline.start_date.to_timestamp().date()}
        )

    # Clip timeline at exit date if disposition occurs before timeline end
    exit_period = _extract_exit_period(deal, timeline)

    if exit_period is not None:
        # Exit occurs before timeline end - clip to prevent post-disposition transactions
        logger.info(
            f"Clipping timeline at disposition (period {exit_period}). "
            f"Original duration: {timeline.duration_months} months, "
            f"Effective duration: {timeline.period_index.get_loc(exit_period) + 1} months"
        )

        # Create exit-bounded timeline
        exit_timeline = Timeline.from_dates(timeline.start_date, exit_period)
        effective_timeline = timeline.clip_to(exit_timeline)
    else:
        # No early exit - use full timeline
        effective_timeline = timeline

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
            deal, effective_timeline, settings, asset_analysis=asset_analysis
        )

    elif asset_analysis is not None:
        # CASE: Only asset_analysis provided - reuse existing analysis
        # Use the ledger from the pre-computed asset analysis
        current_ledger = asset_analysis.ledger
        calculator = DealCalculator(
            deal, effective_timeline, settings, asset_analysis=asset_analysis
        )

    elif ledger is not None:
        # CASE: Only ledger provided - use custom ledger
        # Run fresh asset analysis with the provided ledger
        current_ledger = ledger
        calculator = DealCalculator(deal, effective_timeline, settings)

    else:
        # CASE: Neither provided - create fresh analysis
        # Create new ledger for complete fresh analysis
        current_ledger = Ledger()
        calculator = DealCalculator(deal, effective_timeline, settings)

    # Run deal analysis with the determined ledger
    return calculator.run(ledger=current_ledger)
