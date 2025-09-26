# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Asset-level analysis API.

This module provides clean, user-facing API functions for asset-only analysis,
maintaining strict module boundaries by keeping deal-related functions in
the deal module.
"""

from typing import Optional

from performa.core.base.property import PropertyBaseModel
from performa.core.ledger import Ledger
from performa.core.primitives import GlobalSettings, Timeline

from .registry import get_scenario_for_model
from .results import AssetAnalysisResult


def run(
    model: PropertyBaseModel,
    timeline: Timeline,
    settings: GlobalSettings,
    ledger: Optional[Ledger] = None,
) -> AssetAnalysisResult:
    """
    Run asset-level analysis with full scenario execution and ledger generation.

    This function executes the complete analysis workflow:
    1. Selects the appropriate scenario based on property type
    2. Runs the scenario (prepare_models, orchestration, etc.)
    3. Generates the transactional ledger
    4. Returns comprehensive results with ledger-based data

    Args:
        model: Property model to analyze
        timeline: Analysis timeline
        settings: Global analysis settings
        ledger_settings: Optional ledger generation settings

    Returns:
        AssetAnalysisResult containing scenario, ledger, cash flows, and key metrics

    Note:
        This function provides comprehensive analysis results with full ledger support.
        The result includes the full scenario for detailed model introspection.
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
