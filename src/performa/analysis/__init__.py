# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Performa Analysis Engine

Core analysis engine implementing the orchestrator pattern for cash flow calculations
and the scenario pattern for property analysis.

v3.2 Update: Now includes transactional ledger support for asset-level analysis.
"""

from .api import run
from .orchestrator import AnalysisContext, CashFlowOrchestrator
from .registry import get_scenario_for_model, register_scenario
from .results import AssetAnalysisResult
from .scenario import AnalysisScenarioBase

__all__ = [
    # Main API functions
    "run",
    
    # Core orchestration
    "AnalysisContext",
    "CashFlowOrchestrator",
    
    # Results
    "AssetAnalysisResult",
    
    # Scenario pattern
    "get_scenario_for_model",
    "register_scenario", 
    "AnalysisScenarioBase",
]
