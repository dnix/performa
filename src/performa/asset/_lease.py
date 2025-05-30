from __future__ import annotations

import logging
from datetime import date
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Union,
)
from uuid import UUID

import numpy as np
import pandas as pd
from pydantic import (
    Field,
)

# Core imports
from ..core._cash_flow import CashFlowModel
from ..core._enums import (
    FrequencyEnum,
    LeaseStatusEnum,
    LeaseTypeEnum,
    ProgramUseEnum,
    RevenueSubcategoryEnum,  # Used by Lease default
    UnitOfMeasureEnum,
    UponExpirationEnum,
)
from ..core._model import Model
from ..core._settings import GlobalSettings
from ..core._timeline import Timeline
from ..core._types import (
    FloatBetween0And1,
    PositiveFloat,
)
from ._lc import LeasingCommission
from ._lease_spec import LeaseSpec
from ._recovery import RecoveryCalculationState, RecoveryMethod
from ._rent_abatement import RentAbatement
from ._rent_escalation import RentEscalation
from ._rollover import RolloverLeaseTerms, RolloverProfile
from ._tenant import Tenant
from ._ti import TenantImprovementAllowance

if TYPE_CHECKING:
    from ._property import Property

logger = logging.getLogger(__name__)


# --- Lease ---
class Lease(CashFlowModel):
    """
    Represents a lease agreement and its projected cash flows.
    Instantiated from a LeaseSpec.

    The Lease object is responsible for calculating its own cash flows for its
    defined term and also for projecting subsequent lease terms (renewals or new
    market leases) upon its expiration, based on an associated `RolloverProfile`.
    This includes modeling downtime and re-absorption of the suite into the market.
    """

    # Basic fields from CashFlowModel
    name: str
    category: str = "Revenue"
    subcategory: RevenueSubcategoryEnum = RevenueSubcategoryEnum.LEASE
    timeline: Timeline
    value: Union[PositiveFloat, pd.Series, Dict, List]  # Base rent value/series
    unit_of_measure: UnitOfMeasureEnum
    frequency: FrequencyEnum = FrequencyEnum.MONTHLY

    # Tenant information
    tenant: Tenant
    suite: str
    floor: str
    use_type: ProgramUseEnum

    # Lease details
    status: LeaseStatusEnum
    lease_type: LeaseTypeEnum
    area: PositiveFloat

    # Rent modifications
    rent_escalation: Optional[RentEscalation] = None
    rent_abatement: Optional[RentAbatement] = None

    # Recovery
    recovery_method: Optional[RecoveryMethod] = None

    # TI and LC
    ti_allowance: Optional[TenantImprovementAllowance] = None
    leasing_commission: Optional[LeasingCommission] = None

    # Rollover attributes
    upon_expiration: UponExpirationEnum
    rollover_profile: Optional[RolloverProfile] = None

    # Link back to original definition (optional but useful for tracing)
    source_spec: Optional[LeaseSpec] = Field(default=None, exclude=True)

    @classmethod
    def from_spec(
        cls,
        spec: LeaseSpec,
        analysis_start_date: date,  # Needed to determine status
        lookup_fn: Optional[Callable[[Union[str, UUID]], Any]] = None,
    ) -> "Lease":
        """Creates a Lease instance from a LeaseSpec definition.

        This factory method translates the static definition (`LeaseSpec`) into
        a runtime `Lease` object ready for calculations. It sets the correct
        timeline, determines the initial status (Contract/Speculative), resolves
        the `rollover_profile_ref`, and creates context-specific copies of
        TI/LC components with updated timelines and references.
        """
        timeline = Timeline.from_dates(
            start_date=spec.start_date, end_date=spec.computed_end_date
        )

        # Create Tenant instance
        tenant_instance = Tenant(id=spec.tenant_name, name=spec.tenant_name)

        # Determine status
        status = (
            LeaseStatusEnum.CONTRACT
            if spec.start_date < analysis_start_date
            else LeaseStatusEnum.SPECULATIVE
        )

        # Fetch RolloverProfile
        rollover_profile_instance = None
        if spec.rollover_profile_ref and lookup_fn:
            try:
                # Ensure lookup returns the correct type
                fetched_profile = lookup_fn(spec.rollover_profile_ref)
                if isinstance(fetched_profile, RolloverProfile):
                    rollover_profile_instance = fetched_profile
                else:
                    logger.warning(
                        f"Lookup for rollover ref '{spec.rollover_profile_ref}' did not return RolloverProfile, got {type(fetched_profile)}"
                    )
            except Exception as e:
                logger.error(
                    f"Failed to lookup rollover ref '{spec.rollover_profile_ref}': {e}"
                )

        # Prepare TI/LC instances, ensuring correct context
        ti_instance = None
        if spec.ti_allowance:
            try:
                # Create a copy, updating timeline and reference (area)
                ti_instance = spec.ti_allowance.model_copy(
                    deep=True, update={"timeline": timeline, "reference": spec.area}
                )
                logger.debug(
                    f"  Created context-specific TI instance for Lease '{spec.tenant_name} - {spec.suite}'"
                )
            except Exception as e:
                logger.error(
                    f"  Failed to update context for TI Allowance: {e}", exc_info=True
                )
                if cls.model_config.get("validate_assignment", True):
                    raise

        lc_instance = None
        if spec.leasing_commission:
            try:
                # Calculate annual rent based on spec details for LC reference
                annual_rent = spec.base_rent_value
                if spec.base_rent_unit_of_measure == UnitOfMeasureEnum.PER_UNIT:
                    annual_rent *= spec.area
                # Convert to annual if necessary
                if spec.base_rent_frequency == FrequencyEnum.MONTHLY:
                    annual_rent *= 12
                elif spec.base_rent_frequency == FrequencyEnum.QUARTERLY:
                    annual_rent *= 4
                # Assuming ANNUAL frequency needs no adjustment for annual rent calc

                # Create a copy, updating timeline and value (annual rent)
                lc_instance = spec.leasing_commission.model_copy(
                    deep=True, update={"timeline": timeline, "value": annual_rent}
                )
                logger.debug(
                    f"  Created context-specific LC instance for Lease '{spec.tenant_name} - {spec.suite}'"
                )
            except Exception as e:
                logger.error(
                    f"  Failed to update context for Leasing Commission: {e}",
                    exc_info=True,
                )
                if cls.model_config.get("validate_assignment", True):
                    raise

        # TODO: Populate self.recoveries from self.recovery_method if needed -> No longer needed

        # Now return the new Lease instance using the context-specific ti_instance and lc_instance
        return cls(
            name=f"{spec.tenant_name} - {spec.suite}",
            tenant=tenant_instance,
            suite=spec.suite,
            floor=spec.floor,
            use_type=spec.use_type,
            area=spec.area,
            lease_type=spec.lease_type,
            timeline=timeline,
            value=spec.base_rent_value,  # Compute_cf will handle unit/freq conversion
            unit_of_measure=spec.base_rent_unit_of_measure,
            frequency=spec.base_rent_frequency,
            status=status,
            rent_escalation=spec.rent_escalation,
            rent_abatement=spec.rent_abatement,
            recovery_method=spec.recovery_method,  # Still pass method directly
            ti_allowance=ti_instance,  # Use updated instance
            leasing_commission=lc_instance,  # Use updated instance
            upon_expiration=spec.upon_expiration,
            rollover_profile=rollover_profile_instance,
            source_spec=spec,
        )

    @property
    def lease_start(self) -> date:
        return self.timeline.start_date.to_timestamp().date()

    @property
    def lease_end(self) -> date:
        return self.timeline.end_date.to_timestamp().date()

    @property
    def is_active(self, current_date: date) -> bool:
        """Checks if the lease is active on a specific date."""
        # Use analysis date passed as context, not date.today()
        return self.lease_start <= current_date <= self.lease_end

    @property
    def is_actual(self) -> bool:
        # Status reflects if it *started* before analysis date
        return self.status == LeaseStatusEnum.CONTRACT

    @property
    def is_speculative(self) -> bool:
        return self.status == LeaseStatusEnum.SPECULATIVE

    # --- Existing Methods --- #

    def _apply_escalations(self, base_flow: pd.Series) -> pd.Series:
        # (Implementation unchanged)
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
        # (Implementation unchanged)
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

    def compute_cf(
        self,
        property_data: Optional["Property"] = None,
        global_settings: Optional["GlobalSettings"] = None,
        occupancy_rate: Optional[Union[float, pd.Series]] = None,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Any]] = None,
        recovery_states: Optional[Dict[UUID, RecoveryCalculationState]] = None
    ) -> Dict[str, pd.Series]:
        """Computes cash flows for this specific lease term.

        Args:
            property_data: Optional `Property` instance providing context.
            global_settings: Optional `GlobalSettings` for analysis-wide parameters.
            occupancy_rate: Optional occupancy rate (float or Series) for adjusting
                            recoveries or variable components.
            lookup_fn: Optional callable to resolve references.
            recovery_states: Optional dictionary mapping Recovery model_ids to their
                             pre-calculated `RecoveryCalculationState` (base year stops, etc.),
                             primarily used by the associated `RecoveryMethod`.

        Returns:
            A dictionary where keys are cash flow component names (e.g., "base_rent",
            "recoveries") and values are pandas Series of monthly amounts.
        """
        # --- Base Rent Calculation ---
        # Assumes self.value holds the initial rent rate for the specified unit/freq
        if isinstance(self.value, (int, float)):
            initial_monthly_value = self.value
            if self.frequency == FrequencyEnum.ANNUAL:
                initial_monthly_value /= 12
            if self.unit_of_measure == UnitOfMeasureEnum.PER_UNIT:
                initial_monthly_value *= self.area
            elif self.unit_of_measure == UnitOfMeasureEnum.CURRENCY:
                pass  # Already monthly total amount
            else:
                raise NotImplementedError(
                    f"Base rent unit {self.unit_of_measure} conversion not implemented in compute_cf"
                )
            base_rent = pd.Series(
                initial_monthly_value, index=self.timeline.period_index
            )
        elif isinstance(self.value, pd.Series):
            # If a series is provided directly, use it (e.g., detailed steps)
            base_rent = self.value.copy()
            base_rent = base_rent.reindex(self.timeline.period_index, fill_value=0.0)
        else:
            # Fallback to CashFlowModel logic if value is Dict/List (less likely now)
            base_rent = super().compute_cf(lookup_fn=lookup_fn)

        base_rent_with_escalations = self._apply_escalations(base_rent)
        base_rent_final, abatement_cf = self._apply_abatements(
            base_rent_with_escalations
        )

        # --- Recovery Calculation ---
        recoveries_cf = pd.Series(0.0, index=self.timeline.period_index)
        if self.recovery_method:
            if property_data is None:
                logger.warning(
                    f"Recovery method present for lease '{self.name}' but property_data not provided. Recoveries will be zero."
                )
            else:
                # Calculate recoveries using the attached method instance
                if recovery_states is None:
                    logger.warning(f"Recovery states not provided for lease '{self.name}'. Recoveries may be incorrect if base year stops are needed.")
                    effective_recovery_states = {} 
                else:
                    effective_recovery_states = recovery_states

                recoveries_cf = self.recovery_method.calculate_recoveries(
                    tenant_area=self.area,
                    property_data=property_data,
                    timeline=self.timeline.period_index,
                    occupancy_rate=occupancy_rate,
                    lookup_fn=lookup_fn,
                    global_settings=global_settings,
                    recovery_states=effective_recovery_states
                )
                # TODO: Store the calculated Recovery objects in self.recoveries if needed?
                # self.recoveries = ...

            if self.rent_abatement and self.rent_abatement.includes_recoveries:
                # Abate calculated recoveries
                lease_start_period = pd.Period(self.lease_start, freq="M")
                abatement_start_month = self.rent_abatement.start_month - 1
                abatement_start_period = lease_start_period + abatement_start_month
                abatement_end_period = (
                    abatement_start_period + self.rent_abatement.months
                )
                abatement_mask = (recoveries_cf.index >= abatement_start_period) & (
                    recoveries_cf.index < abatement_end_period
                )
                recoveries_cf[abatement_mask] *= 1 - self.rent_abatement.abated_ratio

        # --- TI/LC Calculation ---
        ti_cf = pd.Series(0.0, index=self.timeline.period_index)
        if self.ti_allowance:
            # Ensure TI instance has correct context if needed (handled in from_spec or here?)
            # Assuming TI model's compute_cf is self-contained or context set previously.
            # Requires TI.compute_cf signature check.
            allowance_cf = self.ti_allowance.compute_cf(lookup_fn=lookup_fn)
            ti_cf = allowance_cf.reindex(self.timeline.period_index, fill_value=0.0)

        lc_cf = pd.Series(0.0, index=self.timeline.period_index)
        if self.leasing_commission:
            # Ensure LC instance has correct context
            # Requires LC.compute_cf signature check.
            commission_cf = self.leasing_commission.compute_cf(lookup_fn=lookup_fn)
            lc_cf = commission_cf.reindex(self.timeline.period_index, fill_value=0.0)

        # --- Final Aggregation ---
        revenue_cf = base_rent_final + recoveries_cf
        expense_cf = ti_cf + lc_cf  # TIs/LCs are typically negative cash flows
        net_cf = revenue_cf + expense_cf  # Add expenses as they are negative

        # Ensure all standard columns exist
        result = {
            "base_rent": base_rent_final.fillna(0.0),
            "abatement": abatement_cf.fillna(0.0),
            "recoveries": recoveries_cf.fillna(0.0),
            "revenue": revenue_cf.fillna(0.0),
            "ti_allowance": ti_cf.fillna(0.0),
            "leasing_commission": lc_cf.fillna(0.0),
            "expenses": expense_cf.fillna(0.0),
            "net": net_cf.fillna(0.0),
        }
        return result

    def _create_speculative_lease_instance(
        self,
        start_date: date,
        lease_terms: "RolloverLeaseTerms",  # Used string hint
        rent_rate: PositiveFloat,
        tenant: Tenant,
        name_suffix: str,
        default_lease_type: Optional[LeaseTypeEnum] = None,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Any]] = None,
    ) -> "Lease":
        """Creates the *next* speculative Lease instance based on rollover terms."""
        if not self.rollover_profile:
            raise ValueError("Rollover profile required to create speculative lease.")
        profile = self.rollover_profile

        # Create Timeline for the new lease term
        timeline = Timeline(start_date=start_date, duration_months=profile.term_months)

        # Instantiate TI/LC based on the *RolloverLeaseTerms*
        ti_allowance, leasing_commission = self._instantiate_lease_costs_from_terms(
            lease_terms=lease_terms,
            timeline=timeline,
            rent_rate=rent_rate,
            area=self.area,
            lookup_fn=lookup_fn,
        )

        # Determine Lease Name and Type
        lease_name = f"{tenant.name} - {self.suite}{name_suffix}"
        lease_type = (
            default_lease_type if default_lease_type is not None else self.lease_type
        )

        # Assemble the new Lease instance using its __init__
        return Lease(
            name=lease_name,
            tenant=tenant,
            suite=self.suite,
            floor=self.floor,
            use_type=self.use_type,
            status=LeaseStatusEnum.SPECULATIVE,
            lease_type=lease_type,
            area=self.area,
            timeline=timeline,
            value=rent_rate,  # Store monthly rate for the new term
            unit_of_measure=UnitOfMeasureEnum.PER_UNIT,  # Changed from PSF Rollover likely assumes PSF?
            frequency=FrequencyEnum.MONTHLY,
            rent_escalation=lease_terms.rent_escalation,
            rent_abatement=lease_terms.rent_abatement,
            recovery_method=lease_terms.recovery_method,
            ti_allowance=ti_allowance,
            leasing_commission=leasing_commission,
            upon_expiration=profile.upon_expiration,  # Inherit upon_expiration
            rollover_profile=profile,  # Inherit profile for subsequent rollovers
        )

    def project_future_cash_flows(
        self,
        projection_end_date: date,
        property_data: Optional["Property"] = None,
        global_settings: Optional["GlobalSettings"] = None,
        occupancy_projection: Optional[pd.Series] = None,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Any]] = None,
        recovery_states: Optional[Dict[UUID, RecoveryCalculationState]] = None
    ) -> pd.DataFrame:
        """Projects cash flows for this lease and subsequent rollovers until projection_end_date.

        This method orchestrates the cash flow projection for the entire chain of leases
        originating from this current lease instance. It calculates the cash flows for the
        current lease term and then, if the lease expires within the `projection_end_date`
        and a `RolloverProfile` is associated, it proceeds to model the next lease event.

        Rollover and Re-absorption (Market Re-Leasing) Logic:
        When an existing lease term ends, the method uses the `upon_expiration` status of
        the current lease and its associated `RolloverProfile` to determine the next steps:

        1.  **Downtime:** If the `upon_expiration` action (e.g., `MARKET`, `VACATE`, `REABSORB`)
            implies a vacancy period before a new lease commences, the `downtime_months`
            from the `RolloverProfile` is applied. During this downtime, vacancy loss is
            calculated based on potential market rent for the suite.

        2.  **New Lease Terms:** The `RolloverProfile` dictates the terms for the subsequent
            lease:
            *   `market_terms` (a `RolloverLeaseTerms` object) are used if the suite is
                going to market (e.g., `upon_expiration` is `MARKET`, `VACATE`, or `REABSORB`).
                These terms define the new rent, lease term length, TIs, LCs, escalations, etc.
            *   `renewal_terms` are used if `upon_expiration` is `RENEW`.
            *   `option_terms` are used if `upon_expiration` is `OPTION`.

        3.  **`UponExpirationEnum.REABSORB` Behavior:** When a lease's `upon_expiration` status
            is set to `REABSORB`, it triggers the standard market re-leasing process:
            downtime is applied (from `RolloverProfile.downtime_months`), followed by the
            creation of a new speculative lease based on the `market_terms` defined in the
            `RolloverProfile`.

        4.  **TI/LC Application:** Tenant Improvements (`ti_allowance`) and Leasing Commissions
            (`leasing_commission`) specified within the relevant `RolloverLeaseTerms` (e.g.,
            `market_terms` or `renewal_terms`) are instantiated and applied to the new
            speculative lease, ensuring these costs are captured for future terms.

        5.  **Recursive Projection:** The method then recursively calls itself for the newly
            created speculative lease, continuing the projection until the `projection_end_date`
            is reached or no further rollovers are defined.

        Args:
            projection_end_date: The final date for the cash flow projection horizon.
            property_data: Optional `Property` instance providing context like area, expense items.
            global_settings: Optional `GlobalSettings` for analysis-wide parameters.
            occupancy_projection: Optional `pd.Series` of occupancy rates over the analysis period.
            lookup_fn: Optional callable to resolve references (e.g., `RolloverProfile` names).
            recovery_states: Optional dictionary mapping Recovery model_ids to their
                             pre-calculated `RecoveryCalculationState` (base year stops, etc.).

        Returns:
            A pandas DataFrame containing all cash flow components (base rent,
            recoveries, TIs, LCs, vacancy loss, etc.) for the entire projected lease chain,
            indexed by monthly periods.
        """
        # Calculate CF for the current lease term
        current_cf_dict = self.compute_cf(
            property_data=property_data,
            global_settings=global_settings,
            occupancy_rate=occupancy_projection,
            lookup_fn=lookup_fn,
            recovery_states=recovery_states
        )
        result_df = pd.DataFrame(current_cf_dict)
        result_df["vacancy_loss"] = 0.0  # Initialize vacancy loss for this term

        # --- Rollover Logic --- #
        future_df = pd.DataFrame()
        vacancy_loss_series: Optional[pd.Series] = None
        next_lease: Optional[Lease] = None

        if self.rollover_profile and self.lease_end < projection_end_date:
            action = self.upon_expiration
            profile = self.rollover_profile
            logger.debug(
                f"Lease '{self.name}' expires {self.lease_end}. Action: {action}. Projecting rollover..."
            )

            # Determine downtime and next start date
            downtime_months = 0
            if action in [
                UponExpirationEnum.VACATE,
                UponExpirationEnum.MARKET,
            ]:
                downtime_months = profile.downtime_months
            next_lease_start_date = self.lease_end + pd.DateOffset(
                months=downtime_months
            )
            next_lease_start_date = next_lease_start_date.date()

            # Calculate market rent if needed for vacancy loss
            market_rent_during_downtime = 0.0
            if downtime_months > 0:
                market_rent_at_rollover = profile._calculate_rent(
                    profile.market_terms,
                    self.lease_end,
                    global_settings=global_settings,
                )
                market_rent_during_downtime = market_rent_at_rollover * self.area

                # Create vacancy loss series
                downtime_start_period = pd.Period(self.lease_end, freq="M") + 1
                downtime_end_period = pd.Period(next_lease_start_date, freq="M") - 1
                if downtime_start_period <= downtime_end_period:
                    downtime_index = pd.period_range(
                        start=downtime_start_period, end=downtime_end_period, freq="M"
                    )
                    vacancy_loss_series = pd.Series(
                        market_rent_during_downtime, index=downtime_index
                    )

            # Determine terms and tenant for the next lease
            next_lease_terms: Optional["RolloverLeaseTerms"] = None
            next_tenant: Optional[Tenant] = None
            next_name_suffix = ""
            next_lease_type: Optional[LeaseTypeEnum] = None

            if action == UponExpirationEnum.RENEW:
                next_lease_terms = profile.renewal_terms
                next_tenant = self.tenant  # Reuse tenant
                next_name_suffix = " (Renewal)"
                next_lease_type = self.lease_type
            elif action == UponExpirationEnum.VACATE:
                next_lease_terms = profile.market_terms
                next_tenant = Tenant(
                    id=f"Vacant-{self.suite}", name=f"Vacant - {self.suite}"
                )
                next_name_suffix = " - Vacant"
                next_lease_type = LeaseTypeEnum.NET  # Market typically Net?
            elif action == UponExpirationEnum.MARKET:
                # For MARKET action, use blended terms and apply market downtime.
                # The RolloverProfile.renewal_probability is used within blend_lease_terms.
                next_lease_terms = profile.blend_lease_terms()
                next_tenant = Tenant(
                    id=f"MarketBlended-{self.suite}", name=f"MarketBlended - {self.suite}"
                )
                next_name_suffix = " - MarketBlended"
                next_lease_type = LeaseTypeEnum.NET # FIXME Assuming blended still results in a NET type or similar default -- is this correct?
            elif action == UponExpirationEnum.OPTION:
                next_lease_terms = profile.option_terms
                next_tenant = self.tenant  # Reuse tenant
                next_name_suffix = " (Option)"
                next_lease_type = self.lease_type
            elif action == UponExpirationEnum.REABSORB:
                logger.debug(
                    f"Lease '{self.name}' set to REABSORB. Stopping projection for this chain. User to handle space manually."
                )
                # Ensure next_lease_terms and next_tenant remain None to stop chain
                pass
            else:
                logger.warning(
                    f"Unhandled UponExpirationEnum: {action} for lease '{self.name}'. Stopping projection."
                )

            # Create the next lease instance if applicable
            if next_lease_terms and next_tenant:
                next_rent_rate = profile._calculate_rent(
                    next_lease_terms, self.lease_end, global_settings=global_settings
                )
                next_lease = self._create_speculative_lease_instance(
                    start_date=next_lease_start_date,
                    lease_terms=next_lease_terms,
                    rent_rate=next_rent_rate,
                    tenant=next_tenant,
                    name_suffix=next_name_suffix,
                    default_lease_type=next_lease_type,
                    lookup_fn=lookup_fn,
                )

            # Recursively project future cash flows for the next lease
            if next_lease:
                future_df = next_lease.project_future_cash_flows(
                    projection_end_date=projection_end_date,
                    property_data=property_data,
                    global_settings=global_settings,
                    occupancy_projection=occupancy_projection,
                    lookup_fn=lookup_fn,
                    recovery_states=recovery_states
                )
        elif not self.rollover_profile:
            logger.debug(
                f"Lease '{self.name}' has no rollover profile. Projection stops at lease end."
            )
        else:  # Lease ends after projection end date
            logger.debug(
                f"Lease '{self.name}' ends ({self.lease_end}) at or after projection end date ({projection_end_date}). No rollover needed."
            )

        # --- Combine Results --- #
        combined_df = pd.concat([result_df, future_df], sort=True).fillna(0.0)

        # Add vacancy loss from downtime (use combine_first to avoid double counting if future_df had it)
        if vacancy_loss_series is not None:
            if "vacancy_loss" not in combined_df.columns:
                combined_df["vacancy_loss"] = 0.0
            combined_df["vacancy_loss"] = combined_df["vacancy_loss"].combine_first(
                vacancy_loss_series
            )

        # Ensure all columns exist and recalculate net
        required_cols = list(current_cf_dict.keys()) + ["vacancy_loss"]
        for col in required_cols:
            if col not in combined_df.columns:
                combined_df[col] = 0.0
        combined_df["net"] = (
            combined_df["revenue"]
            + combined_df["expenses"]
            - combined_df["vacancy_loss"]
        )

        # Reindex to full projection period and aggregate results
        full_projection_index = pd.period_range(
            start=self.timeline.start_date, end=projection_end_date, freq="M"
        )
        # Group by index (period) and sum in case concat created duplicate periods (shouldn't happen with proper timeline slicing)
        final_df = (
            combined_df.groupby(level=0)
            .sum()
            .reindex(full_projection_index, fill_value=0.0)
        )
        return final_df.sort_index()

    def _instantiate_lease_costs_from_terms(
        self,
        lease_terms: "RolloverLeaseTerms",  # Used string hint
        timeline: Timeline,
        rent_rate: PositiveFloat,  # Needed for LC calc
        area: PositiveFloat,  # Needed for TI calc
        lookup_fn: Optional[Callable[[Union[str, UUID]], Any]] = None,
    ) -> tuple[Optional[TenantImprovementAllowance], Optional[LeasingCommission]]:
        """Instantiates TI/LC objects based on configurations within RolloverLeaseTerms."""
        ti_allowance = None
        if lease_terms.ti_allowance:
            # Assume lease_terms.ti_allowance is an instance of TI
            # We need to potentially update its context (timeline, reference)
            ti_config = lease_terms.ti_allowance.model_copy(
                deep=True
            )  # Copy to avoid modifying original RLA
            ti_config.timeline = timeline
            ti_config.reference = area  # TI reference is typically area
            # Re-validate or recalculate internal state if necessary
            ti_allowance = ti_config
            # Alternatively, if TI had an update_context method:
            # ti_allowance.update_context(timeline=timeline, reference=area)

        leasing_commission = None
        if lease_terms.leasing_commission:
            # Assume lease_terms.leasing_commission is an instance of LC
            lc_config = lease_terms.leasing_commission.model_copy(deep=True)  # Copy
            annual_rent = rent_rate * area * 12  # Assuming rent_rate is monthly PSF
            lc_config.timeline = timeline
            lc_config.value = annual_rent  # LC reference is annual rent
            # Re-validate or recalculate internal state if necessary
            leasing_commission = lc_config
            # Alternatively, if LC had an update_context method:
            # leasing_commission.update_context(timeline=timeline, value=annual_rent)

        return ti_allowance, leasing_commission


# --- Security Deposit ---
class SecurityDeposit(Model):
    """
    Model representing the security deposit configuration for a tenant.

    Attributes:
        deposit_mode: Indicates if the security deposit is fully refundable,
            entirely non-refundable, or a hybrid approach
        deposit_unit: Unit used to express the deposit (months of rent,
            fixed dollar amount, or rate per square foot)
        deposit_amount: The total amount of the security deposit
        interest_rate: The interest rate applicable to the refundable portion
            of the deposit (only relevant for "Refundable" or "Hybrid" modes)
        percent_to_refund: The percentage of the deposit that is refundable
            (only relevant for "Hybrid" mode)
    """

    deposit_mode: Literal["Refundable", "Non-Refundable", "Hybrid"]
    deposit_unit: Literal["Months", "Dollar", "DollarPerSF"]
    deposit_amount: PositiveFloat
    interest_rate: Optional[FloatBetween0And1] = None
    percent_to_refund: Optional[FloatBetween0And1] = None
