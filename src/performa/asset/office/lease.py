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
    GlobalSettings,
    LeaseStatusEnum,
    Timeline,
    UnitOfMeasureEnum,
    UponExpirationEnum,
)
from ..commercial.lease import CommercialLeaseBase
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


logger = logging.getLogger(__name__)


class OfficeLease(CommercialLeaseBase):
    """
    Office-specific lease model. Inherits core calculation logic from CommercialLeaseBase.
    """
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
            suite=spec.suite,
            floor=spec.floor,
            status=status,
            area=spec.area,
            upon_expiration=spec.upon_expiration,
            value=spec.base_rent_value,
            unit_of_measure=spec.base_rent_unit_of_measure,
            frequency=spec.base_rent_frequency,
            rent_escalation=spec.rent_escalation,
            rent_abatement=spec.rent_abatement,
            rollover_profile=rollover_profile_instance,
            source_spec=spec,
            settings=settings or GlobalSettings(),
            recovery_method=recovery_method_instance,
            ti_allowance=ti_instance,
            leasing_commission=lc_instance,
        )

    def _create_speculative_lease_instance(
        self,
        start_date: date,
        lease_terms: "OfficeRolloverLeaseTerms",
        rent_rate: float,
        tenant_name: str,
        name_suffix: str,
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
        )

        lease_name = f"{tenant_name}{name_suffix}"

        return OfficeLease(
            name=lease_name,
            status=LeaseStatusEnum.SPECULATIVE,
            area=self.area,
            suite=self.suite,
            floor=self.floor,
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
                unit_of_measure=ti_config.unit_of_measure,
                payment_timing=ti_config.payment_timing,
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