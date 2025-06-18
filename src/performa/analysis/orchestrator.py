from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from graphlib import CycleError, TopologicalSorter
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union
from uuid import UUID

import pandas as pd

from performa.common.primitives import (
    AggregateLineKey,
    CalculationPass,
    UponExpirationEnum,
)

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
    resolved_lookups: Dict[Union[UUID, str], Union[pd.Series, Dict[str, pd.Series]]] = field(default_factory=dict)


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

        # Pre-Phase: Calculate derived system-wide state like occupancy.
        # This can be done first as it only depends on static model attributes (area, timeline),
        # not on calculated cash flows.
        logger.info("Executing Pre-Phase: Calculating Derived State (Occupancy).")
        self.context.occupancy_rate_series = self._calculate_occupancy_series()

        # Phase 1: Calculate all independent base values (e.g., base expenses).
        # These may depend on occupancy, but not on other calculated cash flows.
        logger.info("Executing Pass: INDEPENDENT_VALUES")
        independent_models = [
            m
            for m in self.models
            if m.calculation_pass == CalculationPass.INDEPENDENT_VALUES
        ]
        self._compute_model_subset(independent_models)

        # Intermediate Phase: Compute aggregate values from independent models
        # These aggregates will be needed by dependent models
        logger.info("Intermediate Phase: Computing aggregate values for dependent models")
        self._compute_intermediate_aggregates()

        # Phase 2: Calculate all dependent values (e.g., leases with recoveries).
        # These depend on the results of the INDEPENDENT_VALUES pass.
        logger.info("Executing Pass: DEPENDENT_VALUES")
        dependent_models = [
            m
            for m in self.models
            if m.calculation_pass == CalculationPass.DEPENDENT_VALUES
        ]
        self._compute_model_subset(dependent_models)

        # Final Phase: Aggregate all results into summary views.
        logger.info("Final Phase: Aggregating all cash flows.")
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

    def _compute_model_subset(self, model_subset: List["CashFlowModel"]) -> None:
        """Builds dependency graph and computes a subset of models in order."""
        if not model_subset:
            logger.info("No models to compute in this subset, skipping.")
            return

        subset_uids = {m.uid for m in model_subset}
        graph = {}
        for m in model_subset:
            deps = set()
            # Handle AggregateLineKey references for dependency resolution
            if m.reference is not None:
                if isinstance(m.reference, AggregateLineKey):
                    # AggregateLineKey references are resolved from previous phases
                    # No intra-phase dependency needed since aggregates are computed after phases
                    pass
                else:
                    # Unsupported reference type - should not happen with Pydantic validator
                    raise ValueError(f"Unsupported reference type in model '{m.name}': {type(m.reference)}. Expected AggregateLineKey.")
            graph[m.uid] = deps

        try:
            ts = TopologicalSorter(graph)
            sorted_uids = list(ts.static_order())
        except CycleError as e:
            # Add more context to the error
            cycle_nodes = e.args[1]
            cycle_names = [self.model_map[uid].name for uid in cycle_nodes]
            logger.error(
                f"Circular dependency detected in model subset: {' -> '.join(cycle_names)}"
            )
            raise

        for model_uid in sorted_uids:
            model = self.model_map[model_uid]
            
            # For leases with rollover profiles, use project_future_cash_flows to handle renewals
            from performa.common.base import LeaseBase
            if (isinstance(model, LeaseBase) and 
                hasattr(model, 'rollover_profile') and 
                model.rollover_profile and 
                model.upon_expiration in [
                    UponExpirationEnum.RENEW,
                    UponExpirationEnum.MARKET,
                    UponExpirationEnum.VACATE,
                    UponExpirationEnum.OPTION,
                    UponExpirationEnum.REABSORB,
                ]
            ):
                
                logger.debug(f"Using project_future_cash_flows for lease {model.name} with rollover profile")
                future_df = model.project_future_cash_flows(context=self.context)
                
                # Convert DataFrame back to the dict format expected by aggregation
                result = {}
                for column in future_df.columns:
                    result[column] = future_df[column]
                    
            else:
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
        for lookup_key, result in self.context.resolved_lookups.items():
            # Handle both UUID and string keys in resolved_lookups
            if isinstance(lookup_key, UUID):
                model = self.model_map[lookup_key]
                if isinstance(result, dict): # E.g., a lease with multiple components
                    for component, series in result.items():
                        # Detailed logging
                        detailed_flows_list.append({"name": model.name, "uid": lookup_key, "category": model.category, "subcategory": model.subcategory, "component": component, "series": series})
                        # Aggregation
                        target_key = self._get_aggregate_key(model.category, model.subcategory, component)
                        if target_key:
                            agg_flows[target_key] = agg_flows[target_key].add(series.reindex(analysis_periods, fill_value=0.0), fill_value=0.0)
                elif isinstance(result, pd.Series): # A simple cash flow
                    detailed_flows_list.append({"name": model.name, "uid": lookup_key, "category": model.category, "subcategory": model.subcategory, "component": "value", "series": result})
                    target_key = self._get_aggregate_key(model.category, model.subcategory)
                    if target_key:
                        agg_flows[target_key] = agg_flows[target_key].add(result.reindex(analysis_periods, fill_value=0.0), fill_value=0.0)

        # 3. Apply property-level losses
        self._apply_property_losses(agg_flows)

        # 4. Calculate derived summary lines (NOI, UCF, etc.)
        agg_flows[AggregateLineKey.TOTAL_EFFECTIVE_GROSS_INCOME] = (
            agg_flows[AggregateLineKey.POTENTIAL_GROSS_REVENUE] 
            - agg_flows[AggregateLineKey.RENTAL_ABATEMENT] 
            - agg_flows[AggregateLineKey.GENERAL_VACANCY_LOSS]
            - agg_flows[AggregateLineKey.COLLECTION_LOSS]
            + agg_flows[AggregateLineKey.MISCELLANEOUS_INCOME] 
            + agg_flows[AggregateLineKey.EXPENSE_REIMBURSEMENTS]
        )
        agg_flows[AggregateLineKey.NET_OPERATING_INCOME] = agg_flows[AggregateLineKey.TOTAL_EFFECTIVE_GROSS_INCOME] - agg_flows[AggregateLineKey.TOTAL_OPERATING_EXPENSES]
        agg_flows[AggregateLineKey.UNLEVERED_CASH_FLOW] = agg_flows[AggregateLineKey.NET_OPERATING_INCOME] - agg_flows[AggregateLineKey.TOTAL_CAPITAL_EXPENDITURES] - agg_flows[AggregateLineKey.TOTAL_TENANT_IMPROVEMENTS] - agg_flows[AggregateLineKey.TOTAL_LEASING_COMMISSIONS]
        
        # 5. Store aggregate results in resolved_lookups for cross-reference
        for key, series in agg_flows.items():
            self.context.resolved_lookups[key.value] = series
        
        # 6. Store final DataFrames
        self.summary_df = pd.DataFrame(agg_flows)
        # self.detailed_df = ... (logic to create detailed dataframe from detailed_flows_list)
    
    def _apply_property_losses(self, agg_flows: Dict[AggregateLineKey, pd.Series]) -> None:
        """Apply property-level vacancy and collection losses."""
        if not hasattr(self.context.property_data, 'losses') or not self.context.property_data.losses:
            return
        
        losses = self.context.property_data.losses
        
        # Calculate General Vacancy Loss
        if losses.general_vacancy and losses.general_vacancy.rate > 0:
            vacancy_rate = losses.general_vacancy.rate
            
            # Apply vacancy loss to the appropriate basis
            if losses.general_vacancy.method.value == "Potential Gross Revenue":
                basis = agg_flows[AggregateLineKey.POTENTIAL_GROSS_REVENUE]
            else:  # Effective Gross Revenue method
                basis = (agg_flows[AggregateLineKey.POTENTIAL_GROSS_REVENUE] 
                        + agg_flows[AggregateLineKey.MISCELLANEOUS_INCOME] 
                        - agg_flows[AggregateLineKey.RENTAL_ABATEMENT])
            
            vacancy_loss = basis * vacancy_rate
            agg_flows[AggregateLineKey.GENERAL_VACANCY_LOSS] = vacancy_loss
        
        # Calculate Collection Loss
        if losses.collection_loss and losses.collection_loss.rate > 0:
            collection_rate = losses.collection_loss.rate
            
            # Apply collection loss to the appropriate basis
            if losses.collection_loss.basis == "pgr":
                basis = agg_flows[AggregateLineKey.POTENTIAL_GROSS_REVENUE]
            elif losses.collection_loss.basis == "scheduled_income":
                basis = (agg_flows[AggregateLineKey.POTENTIAL_GROSS_REVENUE] 
                        - agg_flows[AggregateLineKey.RENTAL_ABATEMENT])
            else:  # "egi" - Effective Gross Income
                basis = (agg_flows[AggregateLineKey.POTENTIAL_GROSS_REVENUE] 
                        - agg_flows[AggregateLineKey.RENTAL_ABATEMENT]
                        - agg_flows[AggregateLineKey.GENERAL_VACANCY_LOSS]
                        + agg_flows[AggregateLineKey.MISCELLANEOUS_INCOME])
            
            collection_loss = basis * collection_rate
            agg_flows[AggregateLineKey.COLLECTION_LOSS] = collection_loss

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

    def _compute_intermediate_aggregates(self) -> None:
        """Compute aggregate values from independent models for use by dependent models."""
        analysis_periods = self.context.timeline.period_index
        
        # Initialize aggregate flows for intermediate computation
        intermediate_agg_flows: Dict[AggregateLineKey, pd.Series] = {
            key: pd.Series(0.0, index=analysis_periods, name=key.value)
            for key in AggregateLineKey if not key.value.startswith("_")
        }
        
        # Only process independent models that have already been computed
        independent_models = [
            m for m in self.models 
            if m.calculation_pass == CalculationPass.INDEPENDENT_VALUES
        ]
        
        for model in independent_models:
            if model.uid not in self.context.resolved_lookups:
                continue  # Skip if not computed yet
                
            result = self.context.resolved_lookups[model.uid]
            
            if isinstance(result, dict):  # E.g., a lease with multiple components
                for component, series in result.items():
                    target_key = self._get_aggregate_key(model.category, model.subcategory, component)
                    if target_key:
                        intermediate_agg_flows[target_key] = intermediate_agg_flows[target_key].add(
                            series.reindex(analysis_periods, fill_value=0.0), fill_value=0.0
                        )
            elif isinstance(result, pd.Series):  # A simple cash flow
                target_key = self._get_aggregate_key(model.category, model.subcategory)
                if target_key:
                    intermediate_agg_flows[target_key] = intermediate_agg_flows[target_key].add(
                        result.reindex(analysis_periods, fill_value=0.0), fill_value=0.0
                    )
        
        # Store intermediate aggregate results in resolved_lookups for dependent models
        for key, series in intermediate_agg_flows.items():
            self.context.resolved_lookups[key.value] = series
