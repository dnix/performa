# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Asset Analysis Specialist

This module provides the AssetAnalyzer service that handles unlevered asset performance analysis.
The service bridges the gap between deal-level analysis and the core asset analysis engine,
providing clean integration with the broader deal analysis workflow.

Key responsibilities:
- Asset scenario class resolution and instantiation
- Unlevered cash flow analysis execution
- Asset performance metrics calculation
- Scenario orchestration and model management

The AssetAnalyzer uses the existing performa.analysis infrastructure to perform robust
asset analysis while maintaining clean separation from financing and partnership concerns.

Example:
    ```python
    from performa.deal.analysis import AssetAnalyzer
    from performa.deal.deal import Deal
    from performa.core.primitives import Timeline, GlobalSettings
    
    # Create analyzer
    analyzer = AssetAnalyzer(deal, timeline, settings)
    
    # Execute analysis
    results = analyzer.analyze_unlevered_asset()
    
    # Access results
    print(f"Cash flows: {results.cash_flows}")
    print(f"Models: {len(results.models)}")
    ```

Architecture:
    - Uses dataclass pattern for runtime service state
    - Delegates to existing analysis engine for actual computation
    - Returns strongly-typed UnleveredAnalysisResult
    - Handles scenario resolution and validation automatically
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from performa.core.primitives import GlobalSettings, Timeline
    from performa.deal.deal import Deal

from performa.analysis import get_scenario_for_model
from performa.deal.results import UnleveredAnalysisResult


@dataclass
class AssetAnalyzer:
    """
    Specialist service for analyzing unlevered asset performance.
    
    This service provides a clean interface to the core asset analysis engine,
    handling scenario resolution and execution for deal-level analysis workflows.
    It focuses exclusively on asset operations without financing or partnership concerns.
    
    Key features:
    - Automatic scenario class resolution based on asset type
    - Robust error handling with graceful degradation
    - Integration with existing analysis infrastructure
    - Clean separation of concerns from debt and partnership analysis
    
    Attributes:
        deal: The deal containing the asset to analyze
        timeline: Analysis timeline defining the evaluation period
        settings: Global settings for analysis configuration
        result: Runtime state populated during analysis (internal use)
    
    Example:
        ```python
        analyzer = AssetAnalyzer(deal, timeline, settings)
        results = analyzer.analyze_unlevered_asset()
        
        # Access scenario details
        scenario = results.scenario
        print(f"Scenario type: {type(scenario).__name__}")
        
        # Access cash flows
        if results.cash_flows is not None:
            print(f"Total cash flows: {results.cash_flows.sum()}")
        ```
    """
    
    # Input parameters - injected dependencies
    deal: Deal
    timeline: Timeline
    settings: GlobalSettings
    
    # Runtime state (populated during analysis) - internal use only
    result: UnleveredAnalysisResult = field(init=False, repr=False, default_factory=UnleveredAnalysisResult)
    
    def analyze_unlevered_asset(self) -> UnleveredAnalysisResult:
        """
        Analyze the unlevered asset performance using the core analysis engine.
        
        This method provides the main entry point for asset analysis. It leverages
        the existing asset analysis infrastructure to generate clean, unlevered
        cash flows that can be integrated with financing and partnership analysis.
        
        The process includes:
        1. Scenario class resolution based on asset type
        2. Scenario instantiation with proper validation
        3. Analysis execution through the scenario orchestrator
        4. Result collection and standardization
        
        Returns:
            UnleveredAnalysisResult containing:
                - scenario: The executed scenario instance
                - cash_flows: Unlevered cash flow summary (if available)
                - models: List of component models used in analysis
        
        Raises:
            ValueError: If asset type is not supported or scenario creation fails
            RuntimeError: If analysis execution fails
            
        Example:
            ```python
            analyzer = AssetAnalyzer(deal, timeline, settings)
            results = analyzer.analyze_unlevered_asset()
            
            # Check if analysis was successful
            if results.cash_flows is not None:
                print(f"Analysis completed successfully")
                print(f"Net cash flows: {results.cash_flows.sum()}")
            else:
                print("Analysis completed but no cash flows available")
            ```
        """
        # Step 1: Resolve scenario class based on asset type
        # This uses the public helper function to maintain consistency
        # with the broader analysis framework
        scenario_cls = get_scenario_for_model(self.deal.asset)
        
        # Step 2: Create scenario instance using dict representation
        # Note: We use dict representation to avoid Pydantic validation issues
        # during the round-trip serialization process
        # TODO: Review this approach for potential round-trip issues in future versions
        scenario_data = {
            'model': self.deal.asset.model_dump(),
            'timeline': self.timeline.model_dump(),
            'settings': self.settings.model_dump()
        }
        
        # Step 3: Instantiate and validate scenario
        scenario = scenario_cls.model_validate(scenario_data)
        
        # Step 4: Execute scenario analysis
        # This runs the complete asset analysis workflow including
        # all component models and orchestration
        scenario.run()
        
        # Step 5: Collect results and populate typed result model
        self.result.scenario = scenario
        
        # Extract cash flow summary if available
        # Some scenarios may not have cash flow summary methods
        if hasattr(scenario, 'get_cash_flow_summary'):
            self.result.cash_flows = scenario.get_cash_flow_summary()
        else:
            self.result.cash_flows = None
            
        # Extract component models if orchestrator is available
        # This provides access to the detailed component analysis
        if scenario._orchestrator:
            self.result.models = scenario._orchestrator.models
        else:
            self.result.models = []
        
        return self.result 