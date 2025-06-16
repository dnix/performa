from __future__ import annotations

from abc import abstractmethod
from typing import List

from performa.analysis import AnalysisScenarioBase
from performa.common.base import LeaseSpecBase
from performa.common.primitives import CashFlowModel


class CommercialAnalysisScenarioBase(AnalysisScenarioBase):
    
    @abstractmethod
    def _create_lease_from_spec(self, spec: LeaseSpecBase) -> CashFlowModel:
        """Abstract method for creating a lease from a spec."""
        pass

    @abstractmethod
    def _create_misc_income_models(self) -> List[CashFlowModel]:
        """Abstract method for creating miscellaneous income models."""
        pass

    @abstractmethod
    def _create_expense_models(self) -> List[CashFlowModel]:
        """Abstract method for creating expense models."""
        pass

    def prepare_models(self) -> List[CashFlowModel]:
        """
        Prepares all cash flow models for the analysis by delegating to
        abstract creation methods.
        """
        all_models: List[CashFlowModel] = []

        # 1. Leases from Rent Roll
        if hasattr(self.model, "rent_roll") and self.model.rent_roll:
            for lease_spec in self.model.rent_roll.leases:
                lease_model = self._create_lease_from_spec(lease_spec)
                all_models.append(lease_model)
                # Also add the TI and LC models if they exist
                if lease_model.ti_allowance:
                    all_models.append(lease_model.ti_allowance)
                if lease_model.leasing_commission:
                    all_models.append(lease_model.leasing_commission)
            # TODO: Handle vacant suite absorption modeling

        # 2. Miscellaneous Income
        if hasattr(self.model, "miscellaneous_income"):
            all_models.extend(self._create_misc_income_models())

        # 3. Expenses
        all_models.extend(self._create_expense_models())

        return all_models
