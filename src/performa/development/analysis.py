"""
Development Analysis Scenario - The Assembler for Natural Transition

The DevelopmentAnalysisScenario orchestrates the natural transition from development
specifications to stabilized asset analysis. It is the "Assembler" that reads the
DevelopmentProject blueprint and returns a flat list of CashFlowModel objects 
representing the entire project lifecycle.

This is the high-level "assembler" that uses the same fundamental, hardened 
primitives we have engineered across the library, guaranteeing consistency 
and leveraging our best work.
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
    DevelopmentAnalysisScenario - Development Project Cash Flow Orchestrator
    
    The core orchestrator for development project cash flow analysis.
    
    ARCHITECTURE: "Development Project as Asset Factory"
    This assembler coordinates the complete development lifecycle:
    - Construction (from CapitalPlan)
    - Financing (from ConstructionFacility) 
    - Lease-up (from component absorption plans)
    - Operations (natural transition to stabilized asset)
    - Disposition (from DispositionValuation)
    
    DESIGN PHILOSOPHY:
    Development projects are temporary "asset factories" that produce stabilized 
    real estate assets. This assembler orchestrates that production process using
    existing primitives without reinventing core functionality.
    
    The resulting cash flows should be identical to what the same stabilized
    asset would produce, validating the "natural transition" concept.
    
    IMPLEMENTATION APPROACH:
    a. Construction: Extract CapitalItem objects from development construction plan
    b. Financing: Add equity and debt draws from financing_plan
    c. Lease-Up: Execute component absorption and convert specs to lease models
    d. Operations: Generate operating expense models for stabilized operations
    e. Disposition: Create disposition cash flow models from DispositionValuation
    
    This approach leverages all existing asset module functionality while adding
    the temporal complexity of development project lifecycle management.
    """
    
    model: DevelopmentProject

    def prepare_models(self) -> List[CashFlowModel]:
        """
        Orchestrates the full development lifecycle by assembling cash flow models
        from the project's construction, financing, and blueprint components.
        """
        all_models = []

        # Development Costs & Funding
        all_models.extend(self._prepare_construction_models())
        all_models.extend(self._prepare_financing_models()) # Acknowledging FIXME here

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
                # Use the existing `run` API to get the correct sub-scenario.
                # This is the "handoff" to the battle-tested asset analysis engine.
                from performa.analysis import run
                asset_scenario = run(
                    model=stabilized_asset,
                    timeline=stabilized_timeline,
                    settings=self.settings
                )
                # Append all models (leases, OpEx, etc.) from the stabilized analysis.
                all_models.extend(asset_scenario._orchestrator.models)

        # Disposition
        all_models.extend(self._prepare_disposition_models())
        
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
    
    def _prepare_financing_models(self) -> List[CashFlowModel]:
        """
        Prepare financing cash flow models for development funding.
        
        Integrates with ConstructionFacility to generate proper financing cash flows
        with multi-tranche debt, interest calculations, and equity waterfalls.
        """
        financing_models = []
        
        if not self.model.financing_plan:
            return financing_models
            
        # Handle ConstructionFacility integration
        if hasattr(self.model.financing_plan, 'calculate_financing_cash_flows'):
            try:
                # Calculate total project cost from construction plan
                total_project_cost = sum(
                    item.value if isinstance(item.value, (int, float)) else 0.0
                    for item in (self.model.construction_plan.capital_items or [])
                )
                
                if total_project_cost > 0:
                    # Create budget cash flows DataFrame from construction plan
                    budget_cash_flows = self._create_budget_cash_flows()
                    
                    # Calculate financing cash flows using the proper facility method
                    financing_df = self.model.financing_plan.calculate_financing_cash_flows(
                        total_project_cost=total_project_cost,
                        budget_cash_flows=budget_cash_flows,
                        debt_to_equity=self.model.financing_plan.max_ltc,  # Use max LTC as debt ratio
                        project_timeline=self.timeline.period_index
                    )
                    
                    # Convert DataFrame columns to CashFlowModel objects
                    financing_models.extend(self._convert_financing_df_to_models(financing_df))
                    
            except Exception:
                # Fallback: Skip financing if calculation fails
                # TODO: Add proper logging/warning for debugging
                pass
        
        return financing_models
    
    def _create_budget_cash_flows(self) -> pd.DataFrame:
        """Create budget cash flows DataFrame from construction plan for financing calculations."""
        budget_df = pd.DataFrame(index=self.timeline.period_index)
        
        if self.model.construction_plan and self.model.construction_plan.capital_items:
            for item in self.model.construction_plan.capital_items:
                # Get cash flows for this capital item
                item_cf = pd.Series(0.0, index=self.timeline.period_index)
                
                # Simple implementation: distribute value over item timeline
                if hasattr(item, 'timeline') and item.timeline:
                    item_periods = item.timeline.period_index
                    if len(item_periods) > 0:
                        monthly_value = item.value / len(item_periods)
                        for period in item_periods:
                            if period in item_cf.index:
                                item_cf[period] = monthly_value
                
                budget_df[item.name] = item_cf
        
        return budget_df
    
    def _convert_financing_df_to_models(self, financing_df: pd.DataFrame) -> List[CashFlowModel]:
        """Convert financing DataFrame columns to CashFlowModel objects."""
        from ..common.primitives import Timeline
        
        models = []
        
        for column in financing_df.columns:
            if financing_df[column].sum() != 0:  # Only create models for non-zero flows
                # Determine category and subcategory based on column name
                if "Equity" in column:
                    category = "Financing"
                    subcategory = "Equity"
                elif "Draw" in column:
                    category = "Financing" 
                    subcategory = "Debt"
                elif "Interest" in column:
                    category = "Expense"
                    subcategory = "Interest"
                elif "Fees" in column:
                    category = "Expense"
                    subcategory = "Financing"
                else:
                    category = "Financing"
                    subcategory = "Other"
                
                # Create a simple CashFlowModel with the series data
                model = type('FinancingCashFlowModel', (CashFlowModel,), {
                    'compute_cf': lambda self, context: financing_df[column]
                })(
                    name=column,
                    category=category,
                    subcategory=subcategory,
                    timeline=self.timeline,
                    value=financing_df[column].sum(),  # Use total as value
                    unit_of_measure="currency",
                    frequency="monthly"
                )
                models.append(model)
        
        return models
    

    
    # Absorption and lease creation replaced by polymorphic blueprint pattern.
    # Each blueprint handles its own stabilized asset creation via the
    # blueprint.to_stabilized_asset() method, delegating to existing asset analysis.
    
    def _prepare_disposition_models(self) -> List[CashFlowModel]:
        """
        Prepare disposition models for development exit.
        
        FIXME: This currently skips disposition entirely if explicit parameters 
        are not provided, which may not be the desired behavior for all use cases.
        
        TODO: Add support for:
        - Integration with proper NOI calculation from cash flow analysis
        - Default cap rate assumptions based on asset type and market data
        - Multiple disposition scenarios (base, upside, downside)
        - Disposition timing optimization based on market conditions
        - Tax considerations and depreciation recapture
        """
        disposition_models = []
        
        # FIXME: Skip disposition if not properly specified - may be too restrictive
        if not self.model.disposition_valuation:
            # TODO: Should we create default disposition logic or require explicit specification?
            return disposition_models
            
        disp_val = self.model.disposition_valuation
        
        # FIXME: Require explicit cap rate specification - no market defaults
        if not (hasattr(disp_val, 'cap_rate') and disp_val.cap_rate):
            # TODO: Should we provide market-based cap rate defaults by asset type?
            return disposition_models
        
        # FIXME: Get NOI for valuation - require explicit specification
        # TODO: This should integrate with actual cash flow analysis results
        stabilized_noi = self._estimate_stabilized_noi()
        if stabilized_noi <= 0:
            if hasattr(disp_val, 'explicit_noi') and disp_val.explicit_noi:
                stabilized_noi = disp_val.explicit_noi
            else:
                # FIXME: Skip disposition rather than using calculated NOI
                # TODO: Integrate with proper NOI calculation from cash flow analysis
                return disposition_models
        
        # Calculate sale value
        cap_rate = disp_val.cap_rate
        sale_value = stabilized_noi / cap_rate
        
        # Apply transaction costs if specified
        transaction_costs_rate = getattr(disp_val, 'transaction_costs_rate', 0.0)
        net_sale_proceeds = sale_value * (1.0 - transaction_costs_rate)
        
        from ..common.primitives import Timeline
        from ..valuation import DirectCapValuation
        
        # Create disposition timeline
        disposition_date = disp_val.disposition_date
        disposition_timeline = Timeline.from_dates(disposition_date, disposition_date)
        
        disposition_model = DirectCapValuation(
            name="Development Disposition",
            timeline=disposition_timeline,
            value=net_sale_proceeds,
            cap_rate=cap_rate,
            noi=stabilized_noi,
            transaction_costs_rate=transaction_costs_rate
        )
        
        disposition_models.append(disposition_model)
        
        return disposition_models
    
    def _estimate_stabilized_noi(self) -> float:
        """
        Estimate stabilized NOI using aggregated cash flow results.
        
        FIXME: This is currently a placeholder that returns zero. Need to implement
        proper integration with the analysis orchestrator to get actual NOI values.
        
        TODO: This needs to be integrated with the analysis orchestrator
        to get actual NOI from AggregateLineKey.NET_OPERATING_INCOME
        
        TODO: Proper implementation should:
        - Run the development cash flow analysis
        - Identify the stabilized operations period
        - Extract NOI from aggregated cash flow results
        - Handle multiple asset types in mixed-use developments
        - Account for lease-up timing and absorption
        """
        # FIXME: Return zero to force explicit NOI specification
        # TODO: In a proper implementation, this would:
        # 1. Run the development cash flow analysis
        # 2. Get stabilized period results  
        # 3. Extract NOI from AggregateLineKey.NET_OPERATING_INCOME
        
        return 0.0
    
    def _get_stabilized_noi_from_analysis(self) -> float:
        """
        Get stabilized NOI from aggregated cash flow analysis.
        
        FIXME: This is completely unimplemented and raises NotImplementedError.
        This is the proper way to get NOI but requires significant integration work.
        
        TODO: Implement proper integration with analysis orchestrator:
        - Create and run complete cash flow analysis
        - Use proper AggregateLineKey.NET_OPERATING_INCOME extraction
        - Handle timing of stabilized operations identification
        - Support mixed-use NOI aggregation across components
        """
        from ..common.primitives import AggregateLineKey
        
        # TODO: This would be the proper implementation:
        # 1. Get cash flow summary from analysis
        # 2. Find stabilized operations period 
        # 3. Extract NOI from AggregateLineKey.NET_OPERATING_INCOME
        #
        # cash_flow_summary = self.get_cash_flow_summary()
        # stabilized_period = self._find_stabilized_period(cash_flow_summary)
        # stabilized_noi = cash_flow_summary.loc[stabilized_period, AggregateLineKey.NET_OPERATING_INCOME.value]
        #
        # return stabilized_noi
        
        # FIXME: For now, require explicit specification
        raise NotImplementedError(
            "Stabilized NOI calculation needs proper integration with analysis orchestrator. "
            "Please specify NOI explicitly in disposition valuation or development project."
        )
    
    def _calculate_total_cost_basis(self) -> float:
        """Calculate total cost basis for the development project."""
        # Sum all construction costs
        total_cost = sum(
            item.value if isinstance(item.value, (int, float)) else 0.0
            for item in self.model.construction_plan.capital_items
        )
        
        return total_cost
    
    # === HELPER METHODS ===
    
    def _get_construction_start_date(self) -> date:
        """
        Get the construction start date from the development project.
        
        FIXME: This assumes the earliest capital item start date is the construction start.
        May not handle complex phased construction or pre-construction activities properly.
        
        TODO: Enhance to support:
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
        # FIXME: Fallback to analysis start date - may not be appropriate
        return self.timeline.start_date.to_timestamp().date()
    
    def _get_construction_end_date(self) -> date:
        """
        Get the construction completion date from the development project.
        
        FIXME: This assumes the latest capital item end date is construction completion.
        Doesn't account for construction sequencing, dependencies, or completion criteria.
        
        TODO: Enhance to support:
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
        # FIXME: Fallback to analysis start date + 1 year - arbitrary assumption
        # TODO: Should this raise an error instead of providing arbitrary fallback?
        return self.timeline.start_date.to_timestamp().date() + pd.DateOffset(years=1) 