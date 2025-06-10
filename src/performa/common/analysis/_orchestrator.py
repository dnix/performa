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
from ..primitives._enums import AggregateLineKey
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
        graph = {model_id: set() for model_id in model_map}
        for model_id, model in model_map.items():
            if isinstance(model.reference, UUID):
                if model.reference in model_map:
                    graph[model_id].add(model.reference)
        return graph

    def _run_compute_cf(
        self, model: CashFlowModel, lookup_fn: Callable, **kwargs
    ) -> Union[pd.Series, Dict[str, pd.Series]]:
        # Logic from _run_compute_cf
        return model.compute_cf(lookup_fn=lookup_fn, **kwargs)

    def _compute_cash_flows_iterative(
        self, all_models: List[CashFlowModel], **kwargs
    ) -> Dict[UUID, Union[pd.Series, Dict[str, pd.Series]]]:
        # Logic from _compute_cash_flows_iterative
        return {}

    def _aggregate_detailed_flows(
        self, detailed_flows: List[Tuple[Dict, pd.Series]]
    ) -> Dict[AggregateLineKey, pd.Series]:
        # Logic from _aggregate_detailed_flows
        return {}

    def compute_all(self, **kwargs) -> None:
        """
        Main method to run the full cash flow computation and aggregation.
        """
        model_map = {model.model_id: model for model in self.cash_flow_models}
        graph = self._build_dependency_graph(model_map)
        
        computed_results: Dict[UUID, Union[pd.Series, Dict[str, pd.Series]]] = {}

        def lookup_fn(identifier: Union[str, UUID]):
            if isinstance(identifier, UUID):
                return computed_results.get(identifier)
            # Placeholder for other lookups (e.g., from property)
            return None

        try:
            ts = TopologicalSorter(graph)
            sorted_nodes = list(ts.static_order())
            
            for model_id in sorted_nodes:
                model = model_map[model_id]
                computed_results[model_id] = self._run_compute_cf(model, lookup_fn, **kwargs)

        except CycleError:
            # Fallback to iterative computation if a cycle is detected
            # For now, we'll just log it. The iterative logic will be added later.
            logger.warning("Circular dependency detected. Iterative calculation required but not yet implemented.")
            self._cached_detailed_flows = []
            return

        # Simplified flow processing for now
        detailed_flows = []
        for result in computed_results.values():
            # This logic is incomplete; needs to handle dicts and metadata
            if isinstance(result, pd.Series):
                 # This is a simplification; need to extract metadata from the model
                metadata = {} 
                detailed_flows.append((metadata, result))

        self._cached_detailed_flows = detailed_flows
        self._cached_aggregated_flows = self._aggregate_detailed_flows(detailed_flows) 