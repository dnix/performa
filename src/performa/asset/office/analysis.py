from __future__ import annotations

from typing import Any, Dict, List, Union
from uuid import UUID

from performa.analysis import register_scenario
from performa.common.base import LeaseSpecBase, RecoveryCalculationState
from performa.common.primitives import CashFlowModel

from ..commercial.analysis import CommercialAnalysisScenarioBase
from .expense import OfficeCapExItem, OfficeOpExItem
from .lease import OfficeLease
from .misc_income import OfficeMiscIncome
from .property import OfficeProperty


@register_scenario(OfficeProperty)
class OfficeAnalysisScenario(CommercialAnalysisScenarioBase):
    model: OfficeProperty

    def _pre_calculate_recoveries(self) -> Dict[UUID, RecoveryCalculationState]:
        """
        Pre-calculates base year stops for all recovery methods in the model.
        This is an office-specific implementation detail.
        """
        # This is a placeholder for the complex logic of calculating base year stops.
        # In a real implementation, this would iterate through all recovery methods,
        # find the ones with a 'base_year' structure, calculate the expenses for that
        # specific year, and store the result in a state object.
        return {}

    def _create_lease_from_spec(self, spec: LeaseSpecBase) -> CashFlowModel:
        # The `from_spec` method on OfficeLease needs a lookup function to resolve
        # references to rollover profiles, TIs, etc. We can define a simple one here
        # that looks up objects on the `OfficeProperty` model itself.
        def lookup_fn(ref: Union[str, UUID]) -> Any:
            if hasattr(self.model, ref):
                return getattr(self.model, ref)
            # This is a simplified lookup. A real one might check databases, etc.
            return None

        return OfficeLease.from_spec(
            spec=spec,
            analysis_start_date=self.timeline.start_date.to_timestamp().date(),
            timeline=self.timeline, # The from_spec method creates its own timeline, this is not ideal
            settings=self.settings,
            lookup_fn=lookup_fn
        )

    def _create_misc_income_models(self) -> List[CashFlowModel]:
        models = []
        if self.model.miscellaneous_income:
            for item in self.model.miscellaneous_income:
                # Here we would convert an OfficeMiscIncomeSpec into a real model
                # For now, assuming the items are already models.
                if isinstance(item, OfficeMiscIncome):
                    models.append(item)
        return models

    def _create_expense_models(self) -> List[CashFlowModel]:
        models = []
        if self.model.expenses:
            if self.model.expenses.operating_expenses:
                for item in self.model.expenses.operating_expenses:
                    if isinstance(item, OfficeOpExItem):
                        models.append(item)
            if self.model.expenses.capital_expenses:
                 for item in self.model.expenses.capital_expenses:
                    if isinstance(item, OfficeCapExItem):
                        models.append(item)
        return models

    def run(self) -> None:
        # Pre-calculate office-specific states before running the main analysis
        self._recovery_states = self._pre_calculate_recoveries()
        super().run()
