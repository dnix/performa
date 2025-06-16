from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import date
from typing import TYPE_CHECKING, Dict, Optional

import numpy as np
import pandas as pd

from performa.common.base import LeaseBase, RolloverLeaseTermsBase
from performa.common.primitives import (
    FrequencyEnum,
    UnitOfMeasureEnum,
    UponExpirationEnum,
)

if TYPE_CHECKING:
    from performa.analysis import AnalysisContext


logger = logging.getLogger(__name__)


class CommercialLeaseBase(LeaseBase, ABC):
    
    def _apply_escalations(self, base_flow: pd.Series) -> pd.Series:
        if not self.rent_escalation:
            return base_flow
        rent_with_escalations = base_flow.copy()
        periods = self.timeline.period_index
        if self.rent_escalation:
            start_period = pd.Period(self.rent_escalation.start_date, freq="M")
            mask = periods >= start_period
            if self.rent_escalation.type == "percentage":
                if self.rent_escalation.recurring:
                    freq = self.rent_escalation.frequency_months or 12
                    months_elapsed = np.array([(p - start_period).n for p in periods])
                    cycles = np.floor(months_elapsed / freq)
                    cycles[~mask] = 0
                    if self.rent_escalation.is_relative:
                        growth_factor = np.power(
                            1 + (self.rent_escalation.amount / 100), cycles
                        )
                        rent_with_escalations = rent_with_escalations * growth_factor
                    else:
                        growth_factor = np.power(
                            1 + (self.rent_escalation.amount / 100), cycles
                        )
                        escalation_series = base_flow * (growth_factor - 1)
                        rent_with_escalations += escalation_series
                elif self.rent_escalation.is_relative:
                    growth_factor = 1 + (self.rent_escalation.amount / 100)
                    rent_with_escalations[mask] *= growth_factor
                else:
                    growth_factor = self.rent_escalation.amount / 100
                    escalation_series = pd.Series(0.0, index=periods)
                    escalation_series[mask] = base_flow[mask] * growth_factor
                    rent_with_escalations += escalation_series
            elif self.rent_escalation.type == "fixed":
                monthly_amount = (
                    self.rent_escalation.amount / 12
                    if self.rent_escalation.unit_of_measure == UnitOfMeasureEnum.CURRENCY
                    else self.rent_escalation.amount
                )
                if self.rent_escalation.recurring:
                    freq = self.rent_escalation.frequency_months or 12
                    months_elapsed = np.array([(p - start_period).n for p in periods])
                    cycles = np.floor(months_elapsed / freq)
                    cycles[~mask] = 0
                    cumulative_increases = cycles * monthly_amount
                    escalation_series = pd.Series(cumulative_increases, index=periods)
                    rent_with_escalations += escalation_series
                else:
                    escalation_series = pd.Series(0.0, index=periods)
                    escalation_series[mask] = monthly_amount
                    rent_with_escalations += escalation_series
            elif self.rent_escalation.type == "cpi":
                raise NotImplementedError(
                    "CPI-based escalations are not yet implemented"
                )
        return rent_with_escalations

    def _apply_abatements(self, rent_flow: pd.Series) -> tuple[pd.Series, pd.Series]:
        if not self.rent_abatement:
            return rent_flow, pd.Series(0.0, index=rent_flow.index)
        abated_rent_flow = rent_flow.copy()
        abatement_amount_series = pd.Series(0.0, index=rent_flow.index)
        periods = self.timeline.period_index
        lease_start_period = pd.Period(self.lease_start, freq="M")
        abatement_start_month = self.rent_abatement.start_month - 1
        abatement_start_period = lease_start_period + abatement_start_month
        abatement_end_period = abatement_start_period + self.rent_abatement.months
        abatement_mask = (periods >= abatement_start_period) & (
            periods < abatement_end_period
        )
        abatement_reduction = (
            abated_rent_flow[abatement_mask] * self.rent_abatement.abated_ratio
        )
        abated_rent_flow[abatement_mask] -= abatement_reduction
        abatement_amount_series[abatement_mask] = abatement_reduction
        return abated_rent_flow, abatement_amount_series

    def compute_cf(self, context: "AnalysisContext") -> Dict[str, pd.Series]:
        # --- Base Rent Calculation ---
        if isinstance(self.value, (int, float)):
            initial_monthly_value = self.value
            if self.frequency == FrequencyEnum.ANNUAL:
                initial_monthly_value /= 12
            if self.unit_of_measure == UnitOfMeasureEnum.PER_UNIT:
                initial_monthly_value *= self.area
            elif self.unit_of_measure == UnitOfMeasureEnum.CURRENCY:
                pass
            else:
                raise NotImplementedError(f"Base rent unit {self.unit_of_measure} not implemented")
            base_rent = pd.Series(initial_monthly_value, index=self.timeline.period_index)
        elif isinstance(self.value, pd.Series):
            base_rent = self.value.copy()
            base_rent = base_rent.reindex(self.timeline.period_index, fill_value=0.0)
        else:
            base_rent = super().compute_cf(context=context)

        base_rent_with_escalations = self._apply_escalations(base_rent)
        base_rent_final, abatement_cf = self._apply_abatements(base_rent_with_escalations)

        # --- Recovery Calculation ---
        recoveries_cf = pd.Series(0.0, index=self.timeline.period_index)
        if self.recovery_method:
            # The new context-based approach, now passing self
            recoveries_cf = self.recovery_method.compute_cf(context=context, lease=self)

            if self.rent_abatement and self.rent_abatement.includes_recoveries:
                lease_start_period = pd.Period(self.lease_start, freq="M")
                abatement_start_month = self.rent_abatement.start_month - 1
                abatement_start_period = lease_start_period + abatement_start_month
                abatement_end_period = (abatement_start_period + self.rent_abatement.months)
                abatement_mask = (recoveries_cf.index >= abatement_start_period) & (recoveries_cf.index < abatement_end_period)
                recoveries_cf[abatement_mask] *= 1 - self.rent_abatement.abated_ratio

        # --- TI/LC Calculation ---
        ti_cf = pd.Series(0.0, index=self.timeline.period_index)
        if self.ti_allowance:
            allowance_cf = self.ti_allowance.compute_cf(context=context)
            ti_cf = allowance_cf.reindex(self.timeline.period_index, fill_value=0.0)

        lc_cf = pd.Series(0.0, index=self.timeline.period_index)
        if self.leasing_commission:
            commission_cf = self.leasing_commission.compute_cf(context=context)
            lc_cf = commission_cf.reindex(self.timeline.period_index, fill_value=0.0)

        result = {
            "base_rent": base_rent_final.fillna(0.0),
            "abatement": abatement_cf.fillna(0.0),
            "recoveries": recoveries_cf.fillna(0.0),
            "revenue": (base_rent_final + recoveries_cf).fillna(0.0),
            "ti_allowance": ti_cf.fillna(0.0),
            "leasing_commission": lc_cf.fillna(0.0),
            "expenses": (ti_cf + lc_cf).fillna(0.0),
            "net": (base_rent_final + recoveries_cf - ti_cf - lc_cf).fillna(0.0),
        }
        return result

    def project_future_cash_flows(self, context: "AnalysisContext") -> pd.DataFrame:
        """
        Projects cash flows for this lease and subsequent rollovers.
        This is a complex method that will be implemented based on the deprecated logic,
        but adapted for the new context-based engine.
        """
        # TODO: Port the recursive rollover logic from the deprecated Lease class.
        # This will involve:
        # 1. Calling self.compute_cf(context) for the current term.
        # 2. Checking if the lease expires within the main analysis timeline.
        # 3. If so, using the self.rollover_profile to determine the next action.
        # 4. Calculating downtime/vacancy loss.
        # 5. Creating a new speculative lease instance.
        # 6. Recursively calling project_future_cash_flows on the new lease.
        # 7. Combining the DataFrames.
        raise NotImplementedError("Future cash flow projection is not yet implemented.")

    @abstractmethod
    def _create_speculative_lease_instance(
        self,
        start_date: date,
        lease_terms: "RolloverLeaseTermsBase",
        rent_rate: float,
        tenant_name: str,
        name_suffix: str,
    ) -> "LeaseBase":
        pass
