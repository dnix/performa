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
    PositiveInt,
)

# Asset-level imports needed by Lease or its components
# from ._growth_rates import GrowthRate # Not directly used by moved classes
from ._lc import LeasingCommission
from ._recovery import (  # Recovery needed for Lease._calculate...
    Recovery,
    RecoveryMethod,
)
from ._rollover import (  # RolloverLeaseTerms needed for type hint
    RolloverLeaseTerms,
    RolloverProfile,
)
from ._ti import TenantImprovementAllowance

# from ._expense import ExpenseItem # Removed as unused

# Avoid circular imports
if TYPE_CHECKING:
    from ._property import Property

logger = logging.getLogger(__name__)


# --- Tenant ---
class Tenant(Model):
    """
    Individual tenant record representing a lease agreement.

    Attributes:
        id: Unique identifier
        name: Tenant name
    """
    id: str
    name: str
    # TODO: more fields?


# --- Rent Escalation ---
class RentEscalation(Model):
    """
    Rent increase structure for a lease.

    Attributes:
        type: Type of escalation (fixed, CPI, percentage)
        amount: Amount of increase (percentage or fixed amount)
        unit_of_measure: Units for the amount
        is_relative: Whether amount is relative to previous rent
        start_date: When increase takes effect
        recurring: Whether increase repeats
        frequency_months: How often increase occurs if recurring
    """
    type: Literal["fixed", "percentage", "cpi"]
    amount: PositiveFloat
    unit_of_measure: UnitOfMeasureEnum
    is_relative: bool  # True for relative to base rent
    start_date: date
    recurring: bool = False
    frequency_months: Optional[int] = None


# --- Rent Abatement ---
class RentAbatement(Model):
    """
    Structured rent abatement (free rent) periods.

    Attributes:
        months: Duration of free rent
        includes_recoveries: Whether recoveries are also abated
        start_month: When free rent begins (relative to lease start)
        abated_ratio: Portion of rent that is abated
    """
    months: int
    includes_recoveries: bool = False
    start_month: int = 1
    abated_ratio: FloatBetween0And1 = 1.0


# --- Lease ---
class Lease(CashFlowModel):
    """
    Represents a lease agreement.
    
    Handles key lease attributes and cash flow modeling. Supports rollover projections.
    (See original file for full docstring)
    """
    # Basic fields from CashFlowModel
    name: str
    category: str = "Revenue"
    subcategory: RevenueSubcategoryEnum = RevenueSubcategoryEnum.LEASE
    timeline: Timeline
    value: Union[PositiveFloat, pd.Series, Dict, List]
    unit_of_measure: UnitOfMeasureEnum
    frequency: FrequencyEnum = FrequencyEnum.MONTHLY

    # Tenant information
    tenant: Tenant
    suite: str
    floor: str
    use_type: ProgramUseEnum

    # Lease details
    status: LeaseStatusEnum = LeaseStatusEnum.CONTRACT
    lease_type: LeaseTypeEnum
    area: PositiveFloat

    # Rent modifications
    rent_escalation: Optional[RentEscalation] = None
    rent_abatement: Optional[RentAbatement] = None

    # Recovery
    # Store the RecoveryMethod config; calculation happens elsewhere
    recovery_method: Optional[RecoveryMethod] = None
    # Store related Recovery objects (needed for base year stop cache)
    recoveries: List[Recovery] = [] # Default empty, populated based on recovery_method

    # TI and LC
    ti_allowance: Optional[TenantImprovementAllowance] = None
    leasing_commission: Optional[LeasingCommission] = None

    # Rollover attributes
    upon_expiration: UponExpirationEnum
    rollover_profile: Optional[RolloverProfile] = None

    # TODO: Add model validator to populate self.recoveries from self.recovery_method if needed

    @property
    def lease_start(self) -> date:
        return self.timeline.start_date.to_timestamp().date()

    @property
    def lease_end(self) -> date:
        return self.timeline.end_date.to_timestamp().date()

    @property
    def is_active(self) -> bool:
        today = date.today()
        return self.lease_start <= today <= self.lease_end

    @property
    def is_actual(self) -> bool:
        return self.status == LeaseStatusEnum.CONTRACT

    @property
    def is_speculative(self) -> bool:
        return self.status == LeaseStatusEnum.SPECULATIVE

    @classmethod
    def from_dates(
        cls,
        tenant: Tenant,
        suite: str,
        lease_start: date,
        lease_end: date,
        **kwargs
    ) -> "Lease":
        if lease_start >= lease_end:
            raise ValueError("Lease start date must be before end date")
        if "name" not in kwargs:
            kwargs["name"] = f"{tenant.name} - {suite}"
        timeline = Timeline.from_dates(start_date=lease_start, end_date=lease_end)
        return cls(tenant=tenant, suite=suite, timeline=timeline, **kwargs)

    @classmethod
    def from_duration(
        cls,
        tenant: Tenant,
        suite: str,
        lease_start: date,
        lease_term_months: PositiveInt,
        **kwargs
    ) -> "Lease":
        if "name" not in kwargs:
            kwargs["name"] = f"{tenant.name} - {suite}"
        timeline = Timeline(start_date=lease_start, duration_months=lease_term_months)
        return cls(tenant=tenant, suite=suite, timeline=timeline, **kwargs)

    def _apply_escalations(self, base_flow: pd.Series) -> pd.Series:
        # (Keep implementation from _revenue.py)
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
                        growth_factor = np.power(1 + (self.rent_escalation.amount / 100), cycles)
                        rent_with_escalations = rent_with_escalations * growth_factor
                    else:
                        growth_factor = np.power(1 + (self.rent_escalation.amount / 100), cycles)
                        escalation_series = base_flow * (growth_factor - 1)
                        rent_with_escalations += escalation_series
                else:
                    if self.rent_escalation.is_relative:
                        growth_factor = 1 + (self.rent_escalation.amount / 100)
                        rent_with_escalations[mask] *= growth_factor
                    else:
                        growth_factor = self.rent_escalation.amount / 100
                        escalation_series = pd.Series(0.0, index=periods) # Use float
                        escalation_series[mask] = base_flow[mask] * growth_factor
                        rent_with_escalations += escalation_series
            elif self.rent_escalation.type == "fixed":
                monthly_amount = self.rent_escalation.amount / 12 if self.rent_escalation.unit_of_measure == UnitOfMeasureEnum.AMOUNT else self.rent_escalation.amount
                if self.rent_escalation.recurring:
                    freq = self.rent_escalation.frequency_months or 12
                    months_elapsed = np.array([(p - start_period).n for p in periods])
                    cycles = np.floor(months_elapsed / freq)
                    cycles[~mask] = 0
                    cumulative_increases = cycles * monthly_amount
                    escalation_series = pd.Series(cumulative_increases, index=periods)
                    rent_with_escalations += escalation_series # Absolute/relative distinction seems moot here? Both add.
                else:
                    escalation_series = pd.Series(0.0, index=periods) # Use float
                    escalation_series[mask] = monthly_amount
                    rent_with_escalations += escalation_series
            elif self.rent_escalation.type == "cpi":
                raise NotImplementedError("CPI-based escalations are not yet implemented")
        return rent_with_escalations


    def _apply_abatements(self, rent_flow: pd.Series) -> tuple[pd.Series, pd.Series]:
        # (Keep implementation from _revenue.py)
        if not self.rent_abatement:
            return rent_flow, pd.Series(0.0, index=rent_flow.index)
        abated_rent_flow = rent_flow.copy()
        abatement_amount_series = pd.Series(0.0, index=rent_flow.index)
        periods = self.timeline.period_index
        lease_start_period = pd.Period(self.lease_start, freq="M")
        abatement_start_month = self.rent_abatement.start_month - 1
        abatement_start_period = lease_start_period + abatement_start_month
        abatement_end_period = abatement_start_period + self.rent_abatement.months
        abatement_mask = (periods >= abatement_start_period) & (periods < abatement_end_period)
        abatement_reduction = abated_rent_flow[abatement_mask] * self.rent_abatement.abated_ratio
        abated_rent_flow[abatement_mask] -= abatement_reduction
        abatement_amount_series[abatement_mask] = abatement_reduction
        return abated_rent_flow, abatement_amount_series

    def compute_cf(
        self,
        property_data: Optional['Property'] = None,
        global_settings: Optional['GlobalSettings'] = None,
        occupancy_rate: Optional[Union[float, pd.Series]] = None,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Any]] = None
    ) -> Dict[str, pd.Series]:
        # (Keep implementation from _revenue.py, *excluding* base year stop calc)
        # --- Base Rent Calculation ---
        base_rent = super().compute_cf(lookup_fn=lookup_fn) # Use parent's compute_cf
        base_rent_with_escalations = self._apply_escalations(base_rent)
        base_rent_final, abatement_cf = self._apply_abatements(base_rent_with_escalations)

        # --- Recovery Calculation ---
        recoveries = pd.Series(0.0, index=self.timeline.period_index)
        if self.recovery_method:
            if property_data is None:
                 logger.error(f"Recovery method present for lease '{self.name}' but property_data not provided.")
            else:
                # Pass context down to recovery method calculation
                recoveries = self.recovery_method.calculate_recoveries(
                    tenant_area=self.area,
                    property_data=property_data, 
                    timeline=self.timeline.period_index,
                    occupancy_rate=occupancy_rate,
                    lookup_fn=lookup_fn,
                    global_settings=global_settings 
                )

            if self.rent_abatement and self.rent_abatement.includes_recoveries:
                lease_start_period = pd.Period(self.lease_start, freq="M")
                abatement_start_month = self.rent_abatement.start_month - 1
                abatement_start_period = lease_start_period + abatement_start_month
                abatement_end_period = abatement_start_period + self.rent_abatement.months
                abatement_mask = (recoveries.index >= abatement_start_period) & (recoveries.index < abatement_end_period)
                recoveries[abatement_mask] *= (1 - self.rent_abatement.abated_ratio)

        # --- TI/LC Calculation ---
        ti_cf = pd.Series(0.0, index=self.timeline.period_index)
        if self.ti_allowance:
            ti_cf = self.ti_allowance.compute_cf(lookup_fn=lookup_fn) # TI needs lookup
            ti_cf = ti_cf.reindex(self.timeline.period_index, fill_value=0.0)

        lc_cf = pd.Series(0.0, index=self.timeline.period_index)
        if self.leasing_commission:
            lc_cf = self.leasing_commission.compute_cf(lookup_fn=lookup_fn) # LC needs lookup
            lc_cf = lc_cf.reindex(self.timeline.period_index, fill_value=0.0)

        # --- Final Aggregation ---
        revenue_cf = base_rent_final + recoveries
        expense_cf = ti_cf + lc_cf
        net_cf = revenue_cf - expense_cf

        return {
            "base_rent": base_rent_final,
            "abatement": abatement_cf,
            "recoveries": recoveries,
            "revenue": revenue_cf,
            "ti_allowance": ti_cf,
            "leasing_commission": lc_cf,
            "expenses": expense_cf,
            "net": net_cf
        }

    # --- Lease Creation Helper --- 
    def _create_speculative_lease_instance(
        self,
        start_date: date,
        lease_terms: RolloverLeaseTerms,
        rent_rate: PositiveFloat,
        tenant: Tenant, # Pass the already created/copied tenant
        name_suffix: str, # e.g., "(Renewal)", "(Option)", " - Market"
        default_lease_type: Optional[LeaseTypeEnum] = None, # To override self.lease_type for market
        lookup_fn: Optional[Callable[[Union[str, UUID]], Any]] = None,
        # global_settings and property_data are not directly needed here
    ) -> "Lease":
        """Private helper to instantiate a speculative Lease object."""
        if not self.rollover_profile: # Safeguard, should be checked by caller
            raise ValueError("Rollover profile required to create speculative lease.")
        profile = self.rollover_profile
        
        # Create Timeline - Ensure correct duration calculation
        # Market lease used term_months-1, others used term_months. Let's standardize to term_months duration.
        timeline = Timeline(
            start_date=start_date, 
            duration_months=profile.term_months 
        )

        # Create Lease Costs
        ti_allowance, leasing_commission = self._create_lease_costs(
            lease_terms,
            timeline,
            rent_rate,
            self.area,
            lookup_fn=lookup_fn
        )

        # Determine Lease Name
        lease_name = f"{tenant.name} - {self.suite}{name_suffix}" 

        # Determine Lease Type
        lease_type = default_lease_type if default_lease_type is not None else self.lease_type

        # Instantiate Lease
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
            value=rent_rate, # Store monthly rate
            # TODO: Confirm _calculate_rent always returns monthly PSF rate?
            unit_of_measure=UnitOfMeasureEnum.PSF, 
            frequency=FrequencyEnum.MONTHLY, 
            
            # Apply terms from the selected lease terms object
            rent_escalation=lease_terms.rent_escalation,
            rent_abatement=lease_terms.rent_abatement,
            recovery_method=lease_terms.recovery_method,
            recoveries=lease_terms.recovery_method.recoveries if lease_terms.recovery_method else [], # Populate recoveries list
            
            # Apply newly created instances
            ti_allowance=ti_allowance,
            leasing_commission=leasing_commission,
            
            # Set rollover behavior for future projections
            upon_expiration=profile.upon_expiration, 
            rollover_profile=profile
        )

    # --- Rollover Projection Methods ---
    def project_future_cash_flows(
        self,
        projection_end_date: date,
        property_data: Optional['Property'] = None,
        global_settings: Optional['GlobalSettings'] = None,
        occupancy_projection: Optional[pd.Series] = None,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Any]] = None
    ) -> pd.DataFrame:
        # (Keep implementation from _revenue.py)
        if not self.rollover_profile:
            logger.debug(f"Lease '{self.name}' has no rollover profile. Projection stops at lease end.")
            current_cf = self.compute_cf(
                property_data=property_data,
                global_settings=global_settings,
                occupancy_rate=occupancy_projection,
                lookup_fn=lookup_fn
            )
            result_df = pd.DataFrame(current_cf)
            result_df['vacancy_loss'] = 0.0
            full_projection_index = pd.period_range(start=self.timeline.start_date, end=projection_end_date, freq='M')
            result_df = result_df.reindex(full_projection_index, fill_value=0.0)
            return result_df.sort_index()
            
        initial_cf_dict = self.compute_cf(
            property_data=property_data,
            global_settings=global_settings,
            occupancy_rate=occupancy_projection,
            lookup_fn=lookup_fn
        )
        result_df = pd.DataFrame(initial_cf_dict)
        result_df['vacancy_loss'] = 0.0
        
        future_df = pd.DataFrame()
        vacancy_loss_series: Optional[pd.Series] = None
        next_lease: Optional[Lease] = None

        if self.lease_end < projection_end_date:
            action = self.upon_expiration
            logger.debug(f"Lease '{self.name}' expires {self.lease_end}. Action: {action}. Projecting...")

            if action == UponExpirationEnum.RENEW:
                next_lease = self._create_speculative_lease_instance(
                    start_date=self.lease_end,
                    lease_terms=self.rollover_profile.renewal_terms,
                    rent_rate=self.rollover_profile.calculate_renewal_rent(self.lease_end, global_settings=global_settings),
                    tenant=self.tenant,
                    name_suffix=" (Renewal)",
                    lookup_fn=lookup_fn
                )
            elif action == UponExpirationEnum.VACATE:
                next_lease, vacancy_loss_series = self._create_speculative_lease_instance(
                    start_date=self.lease_end,
                    lease_terms=self.rollover_profile.market_terms,
                    rent_rate=self.rollover_profile._calculate_rent(self.rollover_profile.market_terms, self.lease_end, global_settings=global_settings),
                    tenant=self.tenant,
                    name_suffix=" - Market",
                    default_lease_type=LeaseTypeEnum.NET,
                    lookup_fn=lookup_fn
                )
            elif action == UponExpirationEnum.MARKET:
                next_lease, vacancy_loss_series = self._create_speculative_lease_instance(
                    start_date=self.lease_end,
                    lease_terms=self.rollover_profile.market_terms,
                    rent_rate=self.rollover_profile._calculate_rent(self.rollover_profile.market_terms, self.lease_end, global_settings=global_settings),
                    tenant=self.tenant,
                    name_suffix=" - Market",
                    default_lease_type=LeaseTypeEnum.NET,
                    lookup_fn=lookup_fn
                )
            elif action == UponExpirationEnum.OPTION:
                next_lease = self._create_speculative_lease_instance(
                    start_date=self.lease_end,
                    lease_terms=self.rollover_profile.option_terms,
                    rent_rate=self.rollover_profile.calculate_option_rent(self.lease_end, global_settings=global_settings),
                    tenant=self.tenant,
                    name_suffix=" (Option)",
                    lookup_fn=lookup_fn
                )
            elif action == UponExpirationEnum.REABSORB:
                logger.debug(f"Lease '{self.name}' set to REABSORB. Stopping projection.")
                next_lease = None
            else:
                logger.warning(f"Unhandled UponExpirationEnum: {action}. Stopping projection.")
                next_lease = None

            if next_lease:
                future_df = next_lease.project_future_cash_flows(
                    projection_end_date=projection_end_date,
                    property_data=property_data,
                    global_settings=global_settings,
                    occupancy_projection=occupancy_projection,
                    lookup_fn=lookup_fn # Pass lookup_fn recursively
                )
        else:
             logger.debug(f"Lease '{self.name}' ends ({self.lease_end}) at or after projection end date ({projection_end_date}).")

        combined_df = pd.concat([result_df, future_df], sort=True).fillna(0.0)
        if vacancy_loss_series is not None:
            if 'vacancy_loss' not in combined_df.columns: combined_df['vacancy_loss'] = 0.0
            combined_df['vacancy_loss'] = combined_df['vacancy_loss'].add(vacancy_loss_series, fill_value=0.0)

        required_cols = ['revenue', 'expenses', 'vacancy_loss']
        for col in required_cols:
            if col not in combined_df.columns: combined_df[col] = 0.0
        combined_df['net'] = combined_df['revenue'] - combined_df['expenses'] - combined_df['vacancy_loss']

        full_projection_index = pd.period_range(start=self.timeline.start_date, end=projection_end_date, freq='M')
        final_df = combined_df.groupby(level=0).sum().reindex(full_projection_index, fill_value=0.0)
        return final_df.sort_index()

    def _create_lease_costs(
        self,
        lease_terms: 'RolloverLeaseTerms',
        timeline: Timeline,
        rent_rate: PositiveFloat,
        area: PositiveFloat,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Any]] = None
    ) -> tuple[Optional[TenantImprovementAllowance], Optional[LeasingCommission]]:
        # (Keep implementation from _revenue.py)
        ti_allowance = None
        if lease_terms.ti_allowance:
            ti_allowance = TenantImprovementAllowance(
                **lease_terms.ti_allowance.model_dump(exclude={'timeline', 'reference'}),
                timeline=timeline,
                reference=area
            )
        leasing_commission = None
        if lease_terms.leasing_commission:
            annual_rent = rent_rate * area
            if lease_terms.frequency == FrequencyEnum.MONTHLY: # Use lease_terms freq
                annual_rent = annual_rent * 12
            leasing_commission = LeasingCommission(
                **lease_terms.leasing_commission.model_dump(exclude={'timeline', 'value'}),
                timeline=timeline,
                value=annual_rent
            )
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