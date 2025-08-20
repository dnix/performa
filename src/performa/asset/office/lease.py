# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING, Optional

import pandas as pd
from pydantic import Field

from ...core.base import CommissionTier
from ...core.primitives import (
    FrequencyEnum,
    GlobalSettings,
    LeaseStatusEnum,
    PropertyAttributeKey,
    Timeline,
)
from ..commercial.lease import CommercialLeaseBase
from .lc import OfficeLeasingCommission
from .lease_spec import OfficeLeaseSpec
from .ti import OfficeTenantImprovement

if TYPE_CHECKING:
    from ...asset.office.recovery import OfficeRecoveryMethod
    from ...asset.office.rollover import (
        OfficeRolloverLeaseTerms,
        OfficeRolloverProfile,
    )


logger = logging.getLogger(__name__)


class OfficeLease(CommercialLeaseBase):
    """
    Office-specific lease model with commercial real estate modeling capabilities.

    OFFICE LEASE IMPLEMENTATION
    ============================

    This class implements commercial office lease modeling including commission payments,
    tenant improvements, and speculative lease creation logic.

    KEY FEATURES:

    1. COMMISSION PAYMENT TIMING
       ==========================
       - Supports split payments: 50% at signing, 50% at commencement
       - Automatically generates signing dates for speculative leases (3-month lead time)
       - Handles multi-tier commission structures
       - Avoids circular reference issues in TI/LC models

    2. TI MODEL CREATION
       ==================
       - Creates TI models with area fields instead of float references
       - Prevents dependency conflicts in orchestrator
       - Supports proper architectural separation

    3. SPECULATIVE LEASE LOGIC
       ========================
       - Calculates realistic signing dates for future leases
       - Handles rollover scenarios with TI/LC instantiation
       - Manages lease transitions and state changes

    INTEGRATION:
    - Inherits calculation logic from CommercialLeaseBase
    - Works with AnalysisContext assembler pattern
    - Maintains compatibility with existing lease specifications
    - Supports single tenant through multi-tenant properties
    """

    signing_date: Optional[date] = None
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
    ) -> OfficeLease:
        """
        Creates an OfficeLease instance from a specification.
        """
        lease_timeline = Timeline(
            start_date=spec.start_date, duration_months=spec.computed_term_months
        )
        status = (
            LeaseStatusEnum.CONTRACT
            if spec.start_date < analysis_start_date
            else LeaseStatusEnum.SPECULATIVE
        )

        # Direct object association
        rollover_profile_instance = spec.rollover_profile
        recovery_method_instance = spec.recovery_method

        ti_instance = None
        if spec.ti_allowance:
            # Clone TI allowance with updated timeline and area (TI models should be independent, no reference)
            ti_instance = spec.ti_allowance.model_copy(
                deep=True, update={"timeline": lease_timeline, "area": spec.area}
            )

        lc_instance = None
        if spec.leasing_commission:
            # Calculate annual rent for leasing commission
            annual_rent = spec.base_rent_value
            if spec.base_rent_reference == PropertyAttributeKey.NET_RENTABLE_AREA:
                annual_rent *= spec.area
            # Clone LC with updated timeline and value
            lc_instance = spec.leasing_commission.model_copy(
                deep=True, update={"timeline": lease_timeline, "value": annual_rent}
            )

        return cls(
            timeline=lease_timeline,
            name=spec.tenant_name,
            suite=spec.suite,
            floor=spec.floor,
            status=status,
            area=spec.area,
            signing_date=spec.signing_date,
            upon_expiration=spec.upon_expiration,
            value=spec.base_rent_value,
            reference=spec.base_rent_reference,
            frequency=spec.base_rent_frequency,
            rent_escalations=spec.rent_escalations,
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

        new_timeline = Timeline(
            start_date=start_date,
            duration_months=lease_terms.term_months or profile.term_months,
        )

        ti_allowance, leasing_commission = self._instantiate_lease_costs_from_terms(
            lease_terms=lease_terms,
            timeline=new_timeline,
            rent_rate=rent_rate,
            area=self.area,
        )

        lease_name = f"{tenant_name}{name_suffix}"

        # For speculative leases, set signing_date to ensure proper TI/LC timing
        # Industry standard: Sign 2-6 months before commencement for office leases
        # This ensures realistic commission payment timing
        signing_lead_time_months = 3  # Conservative 3-month lead time
        speculative_signing_date = (
            (pd.Period(start_date, freq="M") - signing_lead_time_months)
            .to_timestamp()
            .date()
        )

        return OfficeLease(
            name=lease_name,
            status=LeaseStatusEnum.SPECULATIVE,
            area=self.area,
            suite=self.suite,
            floor=self.floor,
            timeline=new_timeline,
            signing_date=speculative_signing_date,
            value=rent_rate,
            reference=PropertyAttributeKey.NET_RENTABLE_AREA,
            frequency=FrequencyEnum.MONTHLY,
            rent_escalations=lease_terms.rent_escalations,
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
            if ti_config.reference == PropertyAttributeKey.NET_RENTABLE_AREA:
                ti_value = ti_config.value * area

            ti_allowance = OfficeTenantImprovement(
                name=f"TI for {timeline.start_date}",
                timeline=timeline,
                area=area,
                value=ti_value,
                reference=ti_config.reference,
                payment_timing=ti_config.payment_timing,
            )

        leasing_commission = None
        if lease_terms.leasing_commission:
            lc_config = lease_terms.leasing_commission
            annual_rent = rent_rate * area * 12

            # Convert float list to CommissionTier objects with realistic payment timing
            # Industry standard: 50% at signing, 50% at commencement for office leases
            commission_tiers = [
                CommissionTier(
                    year_start=i + 1,
                    rate=rate,
                    signing_percentage=0.5,
                    commencement_percentage=0.5,
                )
                for i, rate in enumerate(lc_config.tiers)
            ]

            leasing_commission = OfficeLeasingCommission(
                name=f"LC for {timeline.start_date}",
                timeline=timeline,
                value=annual_rent,
                tiers=commission_tiers,
            )

        return ti_allowance, leasing_commission
