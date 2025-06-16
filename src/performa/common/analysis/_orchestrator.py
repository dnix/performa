from __future__ import annotations

import inspect
import logging
from datetime import date
from graphlib import CycleError, TopologicalSorter
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)
from uuid import UUID

import pandas as pd

from ..base._property_base import PropertyBaseModel
from ..primitives._cash_flow import CashFlowModel
from ..primitives._enums import (
    AggregateLineKey,
    ExpenseSubcategoryEnum,
    RevenueSubcategoryEnum,
)
from ..primitives._model import Model
from ..primitives._settings import GlobalSettings
from ..primitives._timeline import Timeline

if TYPE_CHECKING:
    from ..base._property_base import PropertyBaseModel


logger = logging.getLogger(__name__)


class CashFlowOrchestrator(Model):
    """
    Orchestrates the calculation and aggregation of cash flows.
    """

    subject_model: PropertyBaseModel
    cash_flow_models: List[CashFlowModel]
    timeline: Timeline
    settings: GlobalSettings = GlobalSettings()

    _cached_detailed_flows: Optional[List[Tuple[Dict, pd.Series]]] = None
    _cached_aggregated_flows: Optional[Dict[AggregateLineKey, pd.Series]] = None

    def _build_dependency_graph(
        self, model_map: Dict[UUID, CashFlowModel]
    ) -> Dict[UUID, Set[UUID]]:
        """Builds a dependency graph from the cash flow models."""
        graph = {uid: set() for uid in model_map}
        for uid, model in model_map.items():
            if hasattr(model, "reference") and isinstance(model.reference, UUID):
                if model.reference in model_map:
                    graph[uid].add(model.reference)
        return graph

    def _run_compute_cf(
        self, model: CashFlowModel, lookup_fn: Callable, **kwargs
    ) -> Union[pd.Series, Dict[str, pd.Series]]:
        sig = inspect.signature(model.compute_cf)
        params_to_pass = {"lookup_fn": lookup_fn}
        for param_name, param_val in kwargs.items():
            if param_name in sig.parameters:
                params_to_pass[param_name] = param_val
        return model.compute_cf(**params_to_pass)

    def _compute_cash_flows_iterative(
        self, all_models: List[CashFlowModel], **kwargs
    ) -> Dict[UUID, Union[pd.Series, Dict[str, pd.Series]]]:
        computed_results: Dict[UUID, Union[pd.Series, Dict[str, pd.Series]]] = {}
        remaining_models = {model.uid: model for model in all_models}
        max_passes = len(all_models) + 1
        passes = 0
        
        while remaining_models and passes < max_passes:
            passes += 1
            progress_made = False
            for model_id, model in list(remaining_models.items()):
                try:
                    def lookup_fn(identifier: Union[str, UUID]):
                        if isinstance(identifier, UUID) and identifier in computed_results:
                            return computed_results[identifier]
                        return None 

                    result = self._run_compute_cf(model, lookup_fn, **kwargs)
                    computed_results[model_id] = result
                    del remaining_models[model_id]
                    progress_made = True
                except (LookupError, AttributeError):
                    continue
            if not progress_made:
                break
        
        if remaining_models:
            logger.warning(f"Could not compute all models iteratively. Remaining: {len(remaining_models)}")
            
        return computed_results

    def _aggregate_detailed_flows(
        self, detailed_flows: List[Tuple[Dict, pd.Series]]
    ) -> Dict[AggregateLineKey, pd.Series]:
        analysis_periods = self.timeline.period_index
        aggregated_flows: Dict[AggregateLineKey, pd.Series] = {
            key: pd.Series(0.0, index=analysis_periods, name=key.value)
            for key in AggregateLineKey
        }

        for metadata, series in detailed_flows:
            category = metadata["category"]
            subcategory = metadata.get("subcategory")
            component = metadata.get("component")
            target_key: Optional[AggregateLineKey] = None

            if category == "Revenue":
                if subcategory == RevenueSubcategoryEnum.LEASE:
                    if component == "base_rent":
                        target_key = AggregateLineKey.POTENTIAL_GROSS_REVENUE
                    elif component == "recoveries":
                        target_key = AggregateLineKey.EXPENSE_REIMBURSEMENTS
                    elif component == "abatement":
                        target_key = AggregateLineKey.RENTAL_ABATEMENT
                elif subcategory == RevenueSubcategoryEnum.MISC:
                    target_key = AggregateLineKey.MISCELLANEOUS_INCOME
            elif category == "Expense":
                if subcategory == ExpenseSubcategoryEnum.OPEX:
                     target_key = AggregateLineKey.TOTAL_OPERATING_EXPENSES
                elif subcategory == ExpenseSubcategoryEnum.CAPEX:
                    target_key = AggregateLineKey.TOTAL_CAPITAL_EXPENDITURES
                elif subcategory == "ti_allowance":
                    target_key = AggregateLineKey.TOTAL_TENANT_IMPROVEMENTS
                elif subcategory == "leasing_commission":
                    target_key = AggregateLineKey.TOTAL_LEASING_COMMISSIONS

            if target_key:
                safe_series = series.reindex(analysis_periods, fill_value=0.0)
                aggregated_flows[target_key] = aggregated_flows[target_key].add(safe_series, fill_value=0.0)

        # Calculate derived lines
        pgr = aggregated_flows[AggregateLineKey.POTENTIAL_GROSS_REVENUE]
        misc_inc = aggregated_flows[AggregateLineKey.MISCELLANEOUS_INCOME]
        abate = aggregated_flows[AggregateLineKey.RENTAL_ABATEMENT]
        reimburse = aggregated_flows[AggregateLineKey.EXPENSE_REIMBURSEMENTS]
        opex = aggregated_flows[AggregateLineKey.TOTAL_OPERATING_EXPENSES]
        capex = aggregated_flows[AggregateLineKey.TOTAL_CAPITAL_EXPENDITURES]
        ti = aggregated_flows[AggregateLineKey.TOTAL_TENANT_IMPROVEMENTS]
        lc = aggregated_flows[AggregateLineKey.TOTAL_LEASING_COMMISSIONS]

        # Note: Vacancy/Collection Loss logic would go here if defined in this scope
        effective_gross_revenue = pgr + misc_inc - abate
        total_effective_gross_income = effective_gross_revenue + reimburse
        net_operating_income = total_effective_gross_income - opex
        unlevered_cash_flow = net_operating_income - capex - ti - lc

        aggregated_flows[AggregateLineKey.EFFECTIVE_GROSS_REVENUE] = effective_gross_revenue
        aggregated_flows[AggregateLineKey.TOTAL_EFFECTIVE_GROSS_INCOME] = total_effective_gross_income
        aggregated_flows[AggregateLineKey.NET_OPERATING_INCOME] = net_operating_income
        aggregated_flows[AggregateLineKey.UNLEVERED_CASH_FLOW] = unlevered_cash_flow

        return aggregated_flows


    def compute_all(self, **kwargs) -> None:
        model_map = {model.uid: model for model in self.cash_flow_models}
        graph = self._build_dependency_graph(model_map)
        computed_results: Dict[UUID, Union[pd.Series, Dict[str, pd.Series]]] = {}

        def lookup_fn(identifier: Union[str, UUID]):
            if isinstance(identifier, UUID) and identifier in computed_results:
                return computed_results[identifier]
            return None

        try:
            ts = TopologicalSorter(graph)
            sorted_nodes = list(ts.static_order())
            for model_uid in sorted_nodes:
                model = model_map[model_uid]
                computed_results[model_uid] = self._run_compute_cf(model, lookup_fn, **kwargs)
        except CycleError:
            logger.warning("Circular dependency detected. Falling back to iterative computation.")
            computed_results = self._compute_cash_flows_iterative(self.cash_flow_models, **kwargs)

        detailed_flows = []
        for model_uid, result in computed_results.items():
            model = model_map[model_uid]
            if isinstance(result, dict):
                for component, series in result.items():
                    if isinstance(series, pd.Series):
                        metadata = {"category": model.category, "subcategory": model.subcategory, "component": component}
                        detailed_flows.append((metadata, series))
            elif isinstance(result, pd.Series):
                metadata = {"category": model.category, "subcategory": model.subcategory, "component": "value"}
                detailed_flows.append((metadata, result))

        self._cached_detailed_flows = detailed_flows
        self._cached_aggregated_flows = self._aggregate_detailed_flows(detailed_flows) 