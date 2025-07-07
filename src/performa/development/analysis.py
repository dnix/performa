"""
Development Analysis Scenario - Unlevered Asset Analysis

The DevelopmentAnalysisScenario orchestrates development analysis,
focusing on construction costs and operational cash flows for the development
project lifecycle from construction through stabilized operations.

This scenario integrates construction modeling with stabilized asset operations
to provide complete development project cash flow analysis.
"""

from __future__ import annotations

from datetime import date
from typing import Any, List

import pandas as pd

from ..analysis import AnalysisScenarioBase, register_scenario
from ..common.primitives import CashFlowModel, Timeline
from .project import DevelopmentProject


@register_scenario(DevelopmentProject)
class DevelopmentAnalysisScenario(AnalysisScenarioBase):
    """
    Development Analysis Scenario - Complete Development Project Analysis
    
    This scenario coordinates the complete development project analysis including:
    - Construction costs (from CapitalPlan)
    - Lease-up and absorption (from component absorption plans)  
    - Stabilized operations (transition to normal asset operations)
    
    The analysis handles the full development lifecycle from ground-breaking
    through lease-up to stabilized operations, providing comprehensive
    cash flow modeling for development projects.
    
    Implementation:
    a. Construction: Extract CapitalItem objects from construction plan
    b. Lease-Up: Execute absorption plans using blueprint factories
    c. Operations: Generate stabilized operational cash flows
    
    This integrates construction and operational phases to provide complete
    development project financial modeling.
    """
    
    model: DevelopmentProject

    def prepare_models(self) -> List[CashFlowModel]:
        """
        Orchestrates development analysis by assembling cash flow models
        from the project's construction and blueprint components.
        
        The analysis includes:
        - Construction costs from the construction plan
        - Stabilized asset operations from development blueprints
        """
        all_models = []

        # Development Construction Costs
        all_models.extend(self._prepare_construction_models())

        # Asset Creation and Stabilization (The Polymorphic Loop)
        for blueprint in self.model.blueprints:
            stabilization_start_date = self._get_stabilization_date_for_blueprint(blueprint)
            stabilized_timeline = Timeline.from_dates(
                start_date=stabilization_start_date,
                end_date=self.timeline.end_date.to_timestamp().date()
            )

            # The blueprint itself is the factory for its stabilized asset.
            stabilized_asset = blueprint.to_stabilized_asset(timeline=stabilized_timeline)

            if stabilized_asset:
                # Use the existing analysis API to get the correct sub-scenario.
                # This integrates with the asset analysis engine.
                from performa.analysis import run
                asset_scenario = run(
                    model=stabilized_asset,
                    timeline=stabilized_timeline,
                    settings=self.settings
                )
                # Append all models (leases, OpEx, etc.) from the stabilized analysis.
                all_models.extend(asset_scenario._orchestrator.models)
        
        return all_models

    def _get_stabilization_date_for_blueprint(self, blueprint) -> date:
        """
        Calculates when a specific component is ready for stabilization.
        This can be enhanced with more sophisticated logic, but for now, we can
        base it on the available_date of its inventory.
        """
        # A simple implementation: find the latest available_date in the inventory.
        latest_date = self.timeline.start_date.to_timestamp().date()
        if hasattr(blueprint, 'vacant_inventory') and blueprint.vacant_inventory:
            available_dates = []
            for inv in blueprint.vacant_inventory:
                # Office inventory has available_date, residential might not
                if hasattr(inv, 'available_date') and inv.available_date:
                    available_dates.append(inv.available_date)
            if available_dates:
                latest_date = max(available_dates)
        return latest_date
    
    def _prepare_construction_models(self) -> List[CashFlowModel]:
        """
        Prepare construction cash flow models from the development's construction plan.
        
        Extracts CapitalItem objects directly from the construction plan,
        following existing asset module patterns for capital expenditure modeling.
        """
        construction_models = []
        
        if self.model.construction_plan and self.model.construction_plan.capital_items:
            # Extract capital items from construction plan
            for capital_item in self.model.construction_plan.capital_items:
                construction_models.append(capital_item)
        
        return construction_models
    
    # === HELPER METHODS ===
    
    def _get_construction_start_date(self) -> date:
        """
        Get the construction start date from the development project.
        
        Currently uses the earliest capital item start date as the construction start.
        
        Note: This implementation assumes a simple construction schedule.
        Future enhancements could include:
        - Explicit construction start date specification
        - Pre-construction phase modeling (permitting, design, etc.)
        - Phased construction with multiple start dates
        - Construction schedule dependencies and critical path
        """
        if self.model.construction_plan and self.model.construction_plan.capital_items:
            earliest_start = min(
                item.timeline.start_date.to_timestamp().date() 
                for item in self.model.construction_plan.capital_items
            )
            return earliest_start
        # Fallback to analysis start date if no capital items are present
        return self.timeline.start_date.to_timestamp().date()
    
    def _get_construction_end_date(self) -> date:
        """
        Get the construction completion date from the development project.
        
        Currently uses the latest capital item end date as construction completion.
        
        Note: This implementation assumes all capital items complete construction.
        Future enhancements could include:
        - Explicit construction completion date specification
        - Construction sequencing and critical path analysis
        - Partial completion and phased delivery
        - Construction milestone tracking
        - Certificate of occupancy and permit dependencies
        """
        if self.model.construction_plan and self.model.construction_plan.capital_items:
            latest_end = max(
                item.timeline.end_date.to_timestamp().date() 
                for item in self.model.construction_plan.capital_items
            )
            return latest_end
        # Fallback to analysis start date + 1 year if no capital items are present
        # Note: This is a conservative assumption for basic modeling
        return self.timeline.start_date.to_timestamp().date() + pd.DateOffset(years=1) 