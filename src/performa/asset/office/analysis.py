from __future__ import annotations

from typing import Any, Dict, List, Union
from uuid import UUID

from performa.analysis import register_scenario
from performa.common.base import LeaseSpecBase
from performa.common.primitives import CashFlowModel

from ..commercial.analysis import CommercialAnalysisScenarioBase
from .expense import OfficeCapExItem, OfficeOpExItem
from .lease import OfficeLease
from .misc_income import OfficeMiscIncome
from .property import OfficeProperty
from .recovery import RecoveryCalculationState


@register_scenario(OfficeProperty)
class OfficeAnalysisScenario(CommercialAnalysisScenarioBase):
    model: OfficeProperty

    def _pre_calculate_recoveries(self) -> Dict[UUID, RecoveryCalculationState]:
        """
        Pre-calculates base year stops for all recovery methods in the model.
        Creates recovery states for all recovery items found in lease specs.
        """
        recovery_states = {}
        
        # Iterate through all lease specs to find recovery methods
        if hasattr(self.model, "rent_roll") and self.model.rent_roll:
            for lease_spec in self.model.rent_roll.leases:
                if lease_spec.recovery_method:
                    # Iterate through all recovery items in this recovery method
                    for recovery_item in lease_spec.recovery_method.recoveries:
                        if recovery_item.uid not in recovery_states:
                            # Create a basic recovery state for this recovery item
                            recovery_states[recovery_item.uid] = RecoveryCalculationState(
                                recovery_uid=recovery_item.uid,
                                calculated_annual_base_year_stop=None,  # For base year structures
                                frozen_base_year_pro_rata=None,         # For base year structures
                            )
        
        return recovery_states

    def _create_lease_from_spec(self, spec: LeaseSpecBase) -> CashFlowModel:
        # Create OfficeLease directly from spec using attached objects
        return OfficeLease.from_spec(
            spec=spec,
            analysis_start_date=self.timeline.start_date.to_timestamp().date(),
            timeline=self.timeline,
            settings=self.settings,
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
