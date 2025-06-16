# src/performa/asset/office/lease.py 
from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Union
from uuid import UUID

import numpy as np
import pandas as pd
from pydantic import Field

from ...common.base import LeaseBase
from ...common.primitives import (
    CashFlowModel,
    FrequencyEnum,
    LeaseStatusEnum,
    Timeline,
    UnitOfMeasureEnum,
    UponExpirationEnum,
)
from .lc import OfficeLeasingCommission
from .lease_spec import OfficeLeaseSpec
from .ti import OfficeTenantImprovement

if TYPE_CHECKING:
    from ...asset.office.property import OfficeProperty
    from ...asset.office.recovery import OfficeRecoveryMethod, RecoveryCalculationState
    from ...asset.office.rollover import (
        OfficeRolloverLeaseTerms,
        OfficeRolloverProfile,
    )
    from ...common.primitives import GlobalSettings


logger = logging.getLogger(__name__)


class OfficeLease(LeaseBase):
    """
    Office-specific lease model.
    """

    upon_expiration: UponExpirationEnum
    rollover_profile: Optional[OfficeRolloverProfile] = None
    recovery_method: Optional[OfficeRecoveryMethod] = None
    ti_allowance: Optional[OfficeTenantImprovement] = None
    leasing_commission: Optional[OfficeLeasingCommission] = None

    source_spec: Optional[OfficeLeaseSpec] = Field(default=None, exclude=True)

    @classmethod
    def from_spec(
        cls,
        spec: OfficeLeaseSpec,
        analysis_start_date: date,
        timeline: Timeline,
        settings: Optional[GlobalSettings] = None,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Any]] = None,
    ) -> OfficeLease:
        """
        Creates an OfficeLease instance from a specification.
        """
        lease_timeline = Timeline(start_date=spec.start_date, duration_months=spec.term_months)
        status = (
            LeaseStatusEnum.CONTRACT
            if spec.start_date < analysis_start_date
            else LeaseStatusEnum.SPECULATIVE
        )

        rollover_profile_instance = None
        if spec.rollover_profile_ref and lookup_fn:
            fetched_profile = lookup_fn(spec.rollover_profile_ref)
            if fetched_profile.__class__.__name__ == "OfficeRolloverProfile":
                rollover_profile_instance = fetched_profile
        
        recovery_method_instance = None
        if spec.recovery_method_ref and lookup_fn:
            fetched_recovery = lookup_fn(spec.recovery_method_ref)
            if isinstance(fetched_recovery, OfficeRecoveryMethod):
                recovery_method_instance = fetched_recovery

        ti_instance = None
        if spec.ti_allowance_ref and lookup_fn:
             ti_config = lookup_fn(spec.ti_allowance_ref)
             ti_instance = OfficeTenantImprovement.model_validate(ti_config).model_copy(
                 deep=True, update={"timeline": lease_timeline, "reference": spec.area}
             )

        lc_instance = None
        if spec.lc_ref and lookup_fn:
            lc_config = lookup_fn(spec.lc_ref)
            annual_rent = spec.base_rent_value
            if spec.base_rent_unit_of_measure == UnitOfMeasureEnum.PER_UNIT:
                annual_rent *= spec.area
            
            lc_instance = OfficeLeasingCommission.model_validate(lc_config).model_copy(
                deep=True, update={"timeline": lease_timeline, "value": annual_rent}
            )

        return cls(
            timeline=lease_timeline,
            name=spec.tenant_name,
            status=status,
            area=spec.area,
            value=spec.base_rent_value,
            unit_of_measure=spec.base_rent_unit_of_measure,
            frequency=spec.base_rent_frequency,
            rent_escalation=spec.rent_escalation,
            rent_abatement=spec.rent_abatement,
            upon_expiration=spec.upon_expiration,
            rollover_profile=rollover_profile_instance,
            source_spec=spec,
            settings=settings or GlobalSettings(),
            recovery_method=recovery_method_instance,
            ti_allowance=ti_instance,
            leasing_commission=lc_instance,
        )

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
        lease_start_period = self.timeline.start_date
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

    def compute_cf(
        self,
        property_data: Optional["OfficeProperty"] = None,
        global_settings: Optional[GlobalSettings] = None,
        occupancy_rate: Optional[Union[float, pd.Series]] = None,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Any]] = None,
        recovery_states: Optional[Dict[UUID, "RecoveryCalculationState"]] = None,
    ) -> Dict[str, pd.Series]:
        """Computes cash flows for this specific lease term."""
        if isinstance(self.value, (int, float)):
            initial_monthly_value = self.value
            if self.frequency == FrequencyEnum.ANNUAL:
                initial_monthly_value /= 12
            if self.unit_of_measure == UnitOfMeasureEnum.PER_UNIT:
                initial_monthly_value *= self.area
            elif self.unit_of_measure == UnitOfMeasureEnum.CURRENCY:
                pass
            else:
                raise NotImplementedError(f"Base rent unit {self.unit_of_measure} conversion not implemented")
            base_rent = pd.Series(
                initial_monthly_value, index=self.timeline.period_index
            )
        elif isinstance(self.value, pd.Series):
            base_rent = self.value.copy().reindex(
                self.timeline.period_index, fill_value=0.0
            )
        else:
            base_rent = super().compute_cf(lookup_fn=lookup_fn)

        base_rent_with_escalations = self._apply_escalations(base_rent)
        base_rent_final, abatement_cf = self._apply_abatements(
            base_rent_with_escalations
        )

        recoveries_cf = pd.Series(0.0, index=self.timeline.period_index)
        if self.recovery_method:
            if property_data is None:
                logger.warning(f"Recovery method for lease '{self.name}' requires property_data.")
            else:
                recoveries_cf = self.recovery_method.calculate_recoveries(
                    tenant_area=self.area,
                    property_data=property_data,
                    timeline=self.timeline,
                    recovery_states=recovery_states,
                    occupancy_rate=occupancy_rate,
                    lookup_fn=lookup_fn,
                    global_settings=global_settings,
                )
            if self.rent_abatement and self.rent_abatement.includes_recoveries:
                lease_start_period = self.timeline.start_date
                abatement_start_month = self.rent_abatement.start_month - 1
                abatement_start_period = lease_start_period + abatement_start_month
                abatement_end_period = (
                    abatement_start_period + self.rent_abatement.months
                )
                abatement_mask = (recoveries_cf.index >= abatement_start_period) & (
                    recoveries_cf.index < abatement_end_period
                )
                recoveries_cf[abatement_mask] *= 1 - self.rent_abatement.abated_ratio


        ti_cf = pd.Series(0.0, index=self.timeline.period_index)
        if self.ti_allowance:
            ti_cf = self.ti_allowance.compute_cf(lookup_fn=lookup_fn).reindex(self.timeline.period_index, fill_value=0.0)

        lc_cf = pd.Series(0.0, index=self.timeline.period_index)
        if self.leasing_commission:
            lc_cf = self.leasing_commission.compute_cf(lookup_fn=lookup_fn).reindex(self.timeline.period_index, fill_value=0.0)

        revenue_cf = base_rent_final + recoveries_cf
        expense_cf = ti_cf + lc_cf
        net_cf = revenue_cf - expense_cf 

        return {
            "base_rent": base_rent_final.fillna(0.0),
            "abatement": abatement_cf.fillna(0.0),
            "recoveries": recoveries_cf.fillna(0.0),
            "revenue": revenue_cf.fillna(0.0),
            "ti_allowance": ti_cf.fillna(0.0),
            "leasing_commission": lc_cf.fillna(0.0),
            "expenses": expense_cf.fillna(0.0),
            "net": net_cf.fillna(0.0),
        }

    def _create_speculative_lease_instance(
        self,
        start_date: date,
        lease_terms: "OfficeRolloverLeaseTerms",
        rent_rate: float,
        tenant_name: str,
        name_suffix: str,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Any]] = None,
    ) -> "OfficeLease":
        """Creates the *next* speculative Lease instance based on rollover terms."""
        if not self.rollover_profile:
            raise ValueError("Rollover profile required to create speculative lease.")
        profile = self.rollover_profile

        new_timeline = Timeline(start_date=start_date, duration_months=lease_terms.term_months or profile.term_months)

        ti_allowance, leasing_commission = self._instantiate_lease_costs_from_terms(
            lease_terms=lease_terms,
            timeline=new_timeline,
            rent_rate=rent_rate,
            area=self.area,
            lookup_fn=lookup_fn,
        )

        lease_name = f"{tenant_name}{name_suffix}"

        return OfficeLease(
            name=lease_name,
            status=LeaseStatusEnum.SPECULATIVE,
            area=self.area,
            timeline=new_timeline,
            value=rent_rate,
            unit_of_measure=UnitOfMeasureEnum.PER_UNIT,
            frequency=FrequencyEnum.MONTHLY,
            rent_escalation=lease_terms.rent_escalation,
            rent_abatement=lease_terms.rent_abatement,
            upon_expiration=profile.upon_expiration,
            rollover_profile=profile,
            recovery_method=lease_terms.recovery_method,
            ti_allowance=ti_allowance,
            leasing_commission=leasing_commission,
            source_spec=self.source_spec,
        )

    def _instantiate_lease_costs_from_terms(
        self,
        lease_terms: "OfficeRolloverLeaseTerms",
        timeline: Timeline,
        rent_rate: float,
        area: float,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Any]] = None,
    ) -> tuple[Optional[OfficeTenantImprovement], Optional[OfficeLeasingCommission]]:
        """Instantiates TI/LC objects based on configurations within RolloverLeaseTerms."""
        ti_allowance = None
        if lease_terms.ti_allowance:
            ti_config = lease_terms.ti_allowance
            ti_value = ti_config.value
            if ti_config.unit_of_measure == UnitOfMeasureEnum.PER_UNIT:
                 ti_value = ti_config.value * area
            
            ti_allowance = OfficeTenantImprovement(
                name=f"TI for {timeline.start_date}",
                timeline=timeline,
                value=ti_value,
                payment_method=ti_config.payment_method,
                interest_rate=ti_config.interest_rate,
                amortization_term_months=ti_config.amortization_term_months,
                unit_of_measure=ti_config.unit_of_measure,
            )

        leasing_commission = None
        if lease_terms.leasing_commission:
            lc_config = lease_terms.leasing_commission
            annual_rent = rent_rate * area * 12
            
            leasing_commission = OfficeLeasingCommission(
                name=f"LC for {timeline.start_date}",
                timeline=timeline,
                value=annual_rent,
                unit_of_measure=UnitOfMeasureEnum.CURRENCY,
                tiers=lc_config.tiers
            )

        return ti_allowance, leasing_commission

    def project_future_cash_flows(
        self,
        analysis_timeline: Timeline,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Any]] = None,
        global_settings: Optional[GlobalSettings] = None,
    ) -> List[CashFlowModel]:
        """
        Projects future cash flows (speculative leases, costs) upon expiration.
        """
        future_cash_flows: List[CashFlowModel] = []
        lease_end_date = self.timeline.end_date.to_timestamp().date()

        if not self.rollover_profile or lease_end_date >= analysis_timeline.end_date.to_timestamp().date():
            return future_cash_flows

        action = self.upon_expiration
        profile = self.rollover_profile

        downtime_months = 0
        if action in [UponExpirationEnum.VACATE, UponExpirationEnum.MARKET]:
            downtime_months = profile.downtime_months

        next_lease_start_date = (
            pd.Period(lease_end_date, freq="M") + 1 + downtime_months
        ).start_time.date()

        if downtime_months > 0:
            market_rent_at_rollover = profile._calculate_rent(
                profile.market_terms, lease_end_date, global_settings
            )
            monthly_vacancy_loss = market_rent_at_rollover * self.area
            
            downtime_start_period = pd.Period(lease_end_date, freq="M") + 1
            downtime_end_period = downtime_start_period + downtime_months -1
            downtime_timeline = Timeline.from_dates(downtime_start_period.start_time.date(), downtime_end_period.end_time.date())
            
            from .expense import OfficeOpExItem
            
            vacancy_loss_item = OfficeOpExItem(
                name=f"Vacancy Loss - {self.name}",
                timeline=downtime_timeline,
                value=monthly_vacancy_loss,
                unit_of_measure=UnitOfMeasureEnum.CURRENCY,
                frequency=FrequencyEnum.MONTHLY,
                category="expense",
                subcategory="OpEx",
            )
            future_cash_flows.append(vacancy_loss_item)

        next_lease_terms: Optional["OfficeRolloverLeaseTerms"] = None
        next_tenant_name: Optional[str] = None
        next_name_suffix = ""

        if action == UponExpirationEnum.RENEW:
            next_lease_terms = profile.renewal_terms
            next_tenant_name = self.name
            next_name_suffix = " (Renewal)"
        elif action in [UponExpirationEnum.VACATE, UponExpirationEnum.MARKET]:
            next_lease_terms = profile.market_terms if action == UponExpirationEnum.VACATE else profile.blend_lease_terms()
            next_tenant_name = f"Market Lease - {self.source_spec.suite}"
            next_name_suffix = " (Market)" if action == UponExpirationEnum.VACATE else " (Blended)"
        elif action == UponExpirationEnum.OPTION:
            if not profile.option_terms:
                return future_cash_flows
            next_lease_terms = profile.option_terms
            next_tenant_name = self.name
            next_name_suffix = " (Option)"
        
        if next_lease_terms and next_tenant_name:
            next_rent_rate = profile._calculate_rent(
                next_lease_terms, lease_end_date, global_settings
            )
            
            next_lease = self._create_speculative_lease_instance(
                start_date=next_lease_start_date,
                lease_terms=next_lease_terms,
                rent_rate=next_rent_rate,
                tenant_name=next_tenant_name,
                name_suffix=next_name_suffix,
                lookup_fn=lookup_fn,
            )
            future_cash_flows.append(next_lease)

            if next_lease.ti_allowance:
                future_cash_flows.append(next_lease.ti_allowance)
            if next_lease.leasing_commission:
                future_cash_flows.append(next_lease.leasing_commission)

            future_cash_flows.extend(
                next_lease.project_future_cash_flows(
                    analysis_timeline, lookup_fn, global_settings
                )
            )

        return future_cash_flows 