from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from graphlib import CycleError, TopologicalSorter
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union
from uuid import UUID

import pandas as pd

from performa.common.primitives import AggregateLineKey

if TYPE_CHECKING:
    from performa.common.base import (
        LeaseBase,
        PropertyBaseModel,
        RecoveryCalculationState,
    )
    from performa.common.primitives import (
        CashFlowModel,
        ExpenseSubcategoryEnum,
        GlobalSettings,
        RevenueSubcategoryEnum,
        Timeline,
    )

@dataclass
class AnalysisContext:
    """
    A mutable container for the complete state of a single analysis run.
    It bundles configuration, pre-calculated static state, and dynamically
    calculated per-period state, and serves as the single source of truth
    for all `compute_cf` methods.
    """
    # --- Configuration (Set at creation) ---
    timeline: "Timeline"
    settings: "GlobalSettings"
    property_data: "PropertyBaseModel"

    # --- Pre-Calculated Static State (Set by Scenario before run) ---
    recovery_states: Dict[UUID, "RecoveryCalculationState"] = field(default_factory=dict)

    # --- Dynamic Per-Period State (Calculated and managed by Orchestrator) ---
    occupancy_rate_series: Optional[pd.Series] = None

    # --- The Calculation Cache (Managed by Orchestrator) ---
    resolved_lookups: Dict[UUID, Union[pd.Series, Dict[str, pd.Series]]] = field(default_factory=dict)


logger = logging.getLogger(__name__)

@dataclass
class CashFlowOrchestrator:
    # --- Configuration (set via __init__) ---
    models: List["CashFlowModel"]
    context: AnalysisContext
    
    # --- Internal State ---
    model_map: Dict[UUID, "CashFlowModel"] = field(init=False)

    # --- Results (populated by execute()) ---
    summary_df: Optional[pd.DataFrame] = field(init=False, default=None)
    detailed_df: Optional[pd.DataFrame] = field(init=False, default=None)

    def __post_init__(self):
        """Populate the model_map after initialization."""
        self.model_map = {model.uid: model for model in self.models}
    
    # --- CRITICAL METHOD 1: execute() ---
    def execute(self) -> None:
        """Runs the full, phased calculation and aggregation process."""
        logger.info("Orchestrator execution started.")
        
        # PHASE 1: DERIVED STATE CALCULATION
        logger.info("Phase 1: Calculating derived state (e.g., occupancy).")
        self.context.occupancy_rate_series = self._calculate_occupancy_series()
        
        # PHASE 2: DEPENDENT CASH FLOW CALCULATION
        logger.info("Phase 2: Executing dependent cash flow calculations.")
        self._compute_all_models()
        
        # PHASE 3: AGGREGATION
        logger.info("Phase 3: Aggregating cash flows.")
        self._aggregate_flows()
        
        logger.info("Orchestrator execution finished.")

    # --- CRITICAL METHOD 2: _calculate_occupancy_series() ---
    def _calculate_occupancy_series(self) -> pd.Series:
        """Calculates the property-wide occupancy rate for each period."""
        from performa.common.base import LeaseBase
        total_occupied_area = pd.Series(0.0, index=self.context.timeline.period_index)
        lease_models = [m for m in self.models if isinstance(m, LeaseBase)]
        
        for lease in lease_models:
            lease_area_series = pd.Series(lease.area, index=lease.timeline.period_index)
            total_occupied_area = total_occupied_area.add(lease_area_series, fill_value=0.0)
            
        nra = self.context.property_data.net_rentable_area
        if nra > 0:
            return total_occupied_area / nra
        else:
            return pd.Series(0.0, index=self.context.timeline.period_index)

    # --- CRITICAL METHOD 3: _compute_all_models() ---
    def _compute_all_models(self) -> None:
        """Builds dependency graph and computes all models in order."""
        graph = {m.uid: {m.reference} for m in self.models if isinstance(m.reference, UUID) and m.reference in self.model_map}
        # Add models with no dependencies
        for m in self.models:
            if m.uid not in graph:
                graph[m.uid] = set()

        try:
            ts = TopologicalSorter(graph)
            sorted_uids = list(ts.static_order())
        except CycleError as e:
            logger.error(f"Circular dependency detected in cash flow models: {e}")
            raise

        for model_uid in sorted_uids:
            model = self.model_map[model_uid]
            # The context is now complete with all derived state
            result = model.compute_cf(context=self.context)
            self.context.resolved_lookups[model.uid] = result

    # --- CRITICAL METHOD 4: _aggregate_flows() ---
    def _aggregate_flows(self) -> None:
        """Aggregates all computed cash flows into summary and detailed dataframes."""
        # This logic is ported directly from the old orchestrator, but now reads
        # from self.context.resolved_lookups and writes to self.summary_df.
        
        # 1. Initialize summary lines
        analysis_periods = self.context.timeline.period_index
        agg_flows: Dict[AggregateLineKey, pd.Series] = {
            key: pd.Series(0.0, index=analysis_periods, name=key.value)
            for key in AggregateLineKey if not key.value.startswith("_")
        }
        
        detailed_flows_list = []

        # 2. Iterate through resolved lookups to populate raw aggregates
        for uid, result in self.context.resolved_lookups.items():
            model = self.model_map[uid]
            if isinstance(result, dict): # E.g., a lease with multiple components
                for component, series in result.items():
                    # Detailed logging
                    detailed_flows_list.append({"name": model.name, "uid": uid, "category": model.category, "subcategory": model.subcategory, "component": component, "series": series})
                    # Aggregation
                    target_key = self._get_aggregate_key(model.category, model.subcategory, component)
                    if target_key:
                        agg_flows[target_key] = agg_flows[target_key].add(series.reindex(analysis_periods, fill_value=0.0), fill_value=0.0)
            elif isinstance(result, pd.Series): # A simple cash flow
                detailed_flows_list.append({"name": model.name, "uid": uid, "category": model.category, "subcategory": model.subcategory, "component": "value", "series": result})
                target_key = self._get_aggregate_key(model.category, model.subcategory)
                if target_key:
                    agg_flows[target_key] = agg_flows[target_key].add(result.reindex(analysis_periods, fill_value=0.0), fill_value=0.0)

        # 3. Calculate derived summary lines (NOI, UCF, etc.)
        agg_flows[AggregateLineKey.TOTAL_EFFECTIVE_GROSS_INCOME] = agg_flows[AggregateLineKey.POTENTIAL_GROSS_REVENUE] - agg_flows[AggregateLineKey.RENTAL_ABATEMENT] + agg_flows[AggregateLineKey.MISCELLANEOUS_INCOME] + agg_flows[AggregateLineKey.EXPENSE_REIMBURSEMENTS]
        agg_flows[AggregateLineKey.NET_OPERATING_INCOME] = agg_flows[AggregateLineKey.TOTAL_EFFECTIVE_GROSS_INCOME] - agg_flows[AggregateLineKey.TOTAL_OPERATING_EXPENSES]
        agg_flows[AggregateLineKey.UNLEVERED_CASH_FLOW] = agg_flows[AggregateLineKey.NET_OPERATING_INCOME] - agg_flows[AggregateLineKey.TOTAL_CAPITAL_EXPENDITURES] - agg_flows[AggregateLineKey.TOTAL_TENANT_IMPROVEMENTS] - agg_flows[AggregateLineKey.TOTAL_LEASING_COMMISSIONS]
        
        # 4. Store final DataFrames
        self.summary_df = pd.DataFrame(agg_flows)
        # self.detailed_df = ... (logic to create detailed dataframe from detailed_flows_list)
    
    def _get_aggregate_key(self, category: str, subcategory: str, component: str = 'value') -> Optional[AggregateLineKey]:
        # Mapping logic from raw categories to summary lines
        from performa.common.primitives import (
            ExpenseSubcategoryEnum,
            RevenueSubcategoryEnum,
        )
        if category == "Revenue":
            if subcategory == RevenueSubcategoryEnum.LEASE:
                if component == "base_rent": return AggregateLineKey.POTENTIAL_GROSS_REVENUE
                if component == "recoveries": return AggregateLineKey.EXPENSE_REIMBURSEMENTS
                if component == "abatement": return AggregateLineKey.RENTAL_ABATEMENT
            elif subcategory == RevenueSubcategoryEnum.MISC:
                return AggregateLineKey.MISCELLANEOUS_INCOME
        elif category == "Expense":
            if subcategory == ExpenseSubcategoryEnum.OPEX: return AggregateLineKey.TOTAL_OPERATING_EXPENSES
            if subcategory == ExpenseSubcategoryEnum.CAPEX: return AggregateLineKey.TOTAL_CAPITAL_EXPENDITURES
            # Handle special leasing costs from lease object
            if subcategory == "Lease" and component == "ti_allowance": return AggregateLineKey.TOTAL_TENANT_IMPROVEMENTS
            if subcategory == "Lease" and component == "leasing_commission": return AggregateLineKey.TOTAL_LEASING_COMMISSIONS
        return None
