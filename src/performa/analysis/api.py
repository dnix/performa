# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Asset-level Analysis API

Public entry points for running unlevered asset analysis and obtaining
results backed by the transactional ledger. Deal-level functions live in
`performa.deal.api` to maintain clear module boundaries.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ..core.ledger import Ledger
from .registry import get_scenario_for_model
from .results import AssetAnalysisResult

if TYPE_CHECKING:
    from ..core.base.property import PropertyBaseModel
    from ..core.ledger import Ledger
    from ..core.primitives import GlobalSettings, Timeline


def run(
    model: 'PropertyBaseModel',
    timeline: 'Timeline',
    settings: 'GlobalSettings',
    ledger: Optional['Ledger'] = None,
) -> 'AssetAnalysisResult':
    """
    Run asset-level analysis and return results with ledger support.

    Workflow:
      1) Select scenario based on the property model
      2) Create scenario with the provided timeline, settings, and ledger
      3) Execute orchestration to compute cash flows
      4) Return results that query the ledger for metrics

    Args:
        model: Property model to analyze.
        timeline: Timeline for the analysis (monthly PeriodIndex expected downstream).
        settings: Global analysis settings.
        ledger: Optional ledger to use; when omitted, a new ledger is created.

    Returns:
        AssetAnalysisResult with scenario, ledger, models, and accessors for
        metrics drawn directly from the ledger.
    """
    # Step 1: Create or use existing Ledger
    if ledger is not None:
        # Use existing ledger
        current_ledger = ledger
    else:
        # Create new ledger
        current_ledger = Ledger()

    # Step 2: Get the appropriate scenario class from registry
    scenario_cls = get_scenario_for_model(model)

    # Step 3: Create scenario with current_ledger injected
    scenario = scenario_cls(
        model=model, timeline=timeline, settings=settings, ledger=current_ledger
    )

    # Step 4: Run scenario (current_ledger gets built during this!)
    scenario.run()

    # Step 5: Verify orchestrator was created
    orchestrator = scenario._orchestrator
    if not orchestrator:
        raise RuntimeError(
            f"Scenario {scenario_cls.__name__} failed to create orchestrator"
        )

    # Step 6: Extract additional data for comprehensive result
    models = orchestrator.models if hasattr(orchestrator, "models") else []

    # Step 7: Create elegant result with query-based properties
    # All financial metrics (NOI, EGI, UCF, etc.) are now computed on-demand
    # from the ledger, ensuring single source of truth
    return AssetAnalysisResult(
        # Transactional ledger
        ledger=current_ledger,
        # Core inputs
        property=model,
        timeline=timeline,
        # Full access to scenario and models
        scenario=scenario,
        models=models,
    )
