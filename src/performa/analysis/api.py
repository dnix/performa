# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Asset-level analysis API.

This module provides clean, user-facing API functions for asset-only analysis,
maintaining strict module boundaries by keeping deal-related functions in 
the deal module.
"""


import pandas as pd

from performa.core.ledger import LedgerBuilder, LedgerGenerationSettings
from performa.core.primitives import GlobalSettings, Timeline

from .results import AssetAnalysisResult


def run(
    model,  # PropertyBaseModel - avoiding import cycles
    timeline: Timeline,
    settings: GlobalSettings,
    ledger_settings: LedgerGenerationSettings = None,
) -> AssetAnalysisResult:
    """
    Run asset-level analysis with full scenario execution and ledger generation.
    
    This function executes the complete analysis workflow:
    1. Selects the appropriate scenario based on property type
    2. Runs the scenario (prepare_models, orchestration, etc.)
    3. Generates the transactional ledger
    4. Returns comprehensive results including both legacy and ledger data
    
    Args:
        model: Property model to analyze
        timeline: Analysis timeline
        settings: Global analysis settings
        ledger_settings: Optional ledger generation settings
        
    Returns:
        AssetAnalysisResult containing scenario, ledger, cash flows, and key metrics
        
    Note:
        This replaces the legacy run() function while adding ledger support.
        The result includes the full scenario for backward compatibility.
    """
    # Step 1: Get the appropriate scenario class from registry
    from .registry import get_scenario_for_model
    scenario_cls = get_scenario_for_model(model)
    
    # Step 2: Create and run the scenario
    # This executes ALL the property-specific logic (prepare_models, etc.)
    scenario = scenario_cls(
        model=model,
        timeline=timeline,
        settings=settings
    )
    scenario.run()
    
    # Step 3: Verify orchestrator was created
    orchestrator = scenario._orchestrator
    if not orchestrator:
        raise RuntimeError(f"Scenario {scenario_cls.__name__} failed to create orchestrator")
    
    # Step 4: Build the ledger from orchestrator data
    if ledger_settings is None:
        ledger_settings = LedgerGenerationSettings()
    
    builder = LedgerBuilder(settings=ledger_settings)
    
    # Extract series with metadata for ledger building
    series_pairs = orchestrator.get_series_with_metadata(
        asset_id=model.id,
        deal_id=None  # Asset-only analysis
    )
    builder.add_series_batch(series_pairs)
    
    # Step 5: Calculate NOI from ledger or fallback to orchestrator
    ledger = builder.get_current_ledger()
    if not ledger.empty:
        operating = ledger[ledger['flow_purpose'] == 'Operating']
        noi = operating.groupby('date')['amount'].sum()
    elif orchestrator.summary_df is not None and 'Net Operating Income' in orchestrator.summary_df.columns:
        noi = orchestrator.summary_df['Net Operating Income']
    else:
        noi = pd.Series(0.0, index=timeline.period_index)
    
    # Step 6: Extract additional data for comprehensive result
    summary_df = orchestrator.summary_df if orchestrator.summary_df is not None else pd.DataFrame()
    models = orchestrator.models if hasattr(orchestrator, 'models') else []
    
    return AssetAnalysisResult(
        # Ledger data
        ledger_builder=builder,
        noi=noi,
        # Core inputs
        property=model,
        timeline=timeline,
        # Full access to everything
        scenario=scenario,
        summary_df=summary_df,
        models=models
    )

