from __future__ import annotations

from typing import Any, Callable, List, Union
from uuid import UUID

import pandas as pd

from performa.asset.office.lease import OfficeLease
from performa.asset.office.property import OfficeProperty
from performa.common.analysis import CashFlowOrchestrator
from performa.common.primitives import CashFlowModel, GlobalSettings, Timeline


class AssetAnalysisWrapper:
    def __init__(
        self,
        property_data: OfficeProperty,
        timeline: Timeline,
        settings: GlobalSettings | None = None,
    ):
        self.property_data = property_data
        self.timeline = timeline
        self.settings = settings or GlobalSettings()
        self.orchestrator: CashFlowOrchestrator | None = None
        self._all_cash_flows: List[CashFlowModel] = []
        self._lookup_cache = {}

    def _lookup_fn(self, identifier: Union[str, UUID]) -> Any:
        # Simple cache for computed results
        if identifier in self._lookup_cache:
            return self._lookup_cache[identifier]
        # In a real scenario, this would be more robust, accessing
        # property attributes or other model outputs.
        return None

    def run(self):
        # 1. Collect static cash flows from the property
        if self.property_data.expenses:
            self._all_cash_flows.extend(self.property_data.expenses.operating_expenses)
            self._all_cash_flows.extend(self.property_data.expenses.capital_expenses)
        if self.property_data.miscellaneous_income:
            self._all_cash_flows.extend(self.property_data.miscellaneous_income)

        # 2. Run absorption plans to generate new lease specs
        generated_lease_specs: List[OfficeLeaseSpec] = []
        if self.property_data.absorption_plans:
            for plan in self.property_data.absorption_plans:
                generated_lease_specs.extend(plan.generate_lease_specs(
                    available_vacant_suites=self.property_data.rent_roll.vacant_suites,
                    analysis_start_date=self.timeline.start_date.to_timestamp().date(),
                    analysis_end_date=self.timeline.end_date.to_timestamp().date(),
                    lookup_fn=self._lookup_fn,
                    global_settings=self.settings,
                ))
        
        all_lease_specs = self.property_data.rent_roll.leases + generated_lease_specs

        # 3. Process the rent roll (including newly generated specs)
        for lease_spec in all_lease_specs:
            initial_lease = OfficeLease.from_spec(
                spec=lease_spec,
                analysis_start_date=self.timeline.start_date.to_timestamp().date(),
                timeline=Timeline.from_dates(lease_spec.start_date, lease_spec.computed_end_date),
                settings=self.settings,
                lookup_fn=self._lookup_fn
            )
            self._all_cash_flows.append(initial_lease)
            
            # 3. Project future leases
            future_flows = initial_lease.project_future_cash_flows(
                analysis_timeline=self.timeline,
                lookup_fn=self._lookup_fn,
                global_settings=self.settings,
            )
            self._all_cash_flows.extend(future_flows)

        # 4. Instantiate and run the orchestrator
        self.orchestrator = CashFlowOrchestrator(
            subject_model=self.property_data,
            cash_flow_models=self._all_cash_flows,
            timeline=self.timeline,
            settings=self.settings,
        )
        self.orchestrator.compute_all()

    def get_cash_flow_dataframe(self):
        if not self.orchestrator or self.orchestrator._cached_aggregated_flows is None:
            # Re-running if it hasn't been run
            self.run()
        
        if self.orchestrator and self.orchestrator._cached_aggregated_flows is not None:
             return pd.DataFrame(self.orchestrator._cached_aggregated_flows)
        return None
