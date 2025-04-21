import logging
from datetime import date, relativedelta, timedelta
from typing import Any, Callable, Dict, List, Literal, Optional, Union
from uuid import UUID

import numpy as np
import pandas as pd
from pydantic import model_validator

from ..core._cash_flow import CashFlowModel
from ..core._enums import (
    FrequencyEnum,
    LeaseStatusEnum,
    LeaseTypeEnum,
    ProgramUseEnum,
    RevenueSubcategoryEnum,
    UnitOfMeasureEnum,
    UponExpirationEnum,
)
from ..core._model import Model
from ..core._timeline import Timeline
from ..core._types import (
    FloatBetween0And1,
    PositiveFloat,
    PositiveInt,
)
from ._growth_rates import GrowthRate
from ._lc import LeasingCommission
from ._recovery import RecoveryMethod
from ._rollover import RolloverLeaseTerms, RolloverProfile
from ._ti import TenantImprovementAllowance

logger = logging.getLogger(__name__)


class Tenant(Model):
    """
    Individual tenant record representing a lease agreement.

    Attributes:
        id: Unique identifier
        name: Tenant name
    """

    # Identity
    id: str
    name: str
    # TODO: more fields?


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

    # TODO: confirm fields are thorough and DRY
    type: Literal["fixed", "percentage", "cpi"]
    amount: PositiveFloat
    unit_of_measure: UnitOfMeasureEnum
    is_relative: bool  # True for relative to base rent
    start_date: date
    recurring: bool = False
    frequency_months: Optional[int] = None


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


class Lease(CashFlowModel):
    """
    Represents a lease agreement.
    
    This model handles the key lease attributes and cash flow modeling,
    building on the CashFlowModel base class for timeline and computation.
    
    The lease model supports projection of future cash flows beyond the
    contracted lease term through rollover modeling. This follows industry
    standard methodologies used in tools like Argus Enterprise and Rockport VAL:
    
    - RENEW: Tenant renews with 100% probability using renewal terms
    - VACATE: Tenant vacates with 100% probability, followed by market lease
    - MARKET: Probability-weighted blend of renewal and market scenarios
      (Blends terms rather than cash flows for better accuracy)
    - OPTION: Tenant exercises option with 100% probability
    - REABSORB: Space remains vacant for custom reabsorption
    
    Attributes:
        name: Name of the lease (typically tenant name + suite)
        category: Fixed as "Revenue"
        subcategory: Revenue subcategory (Office, Retail, etc.)
        timeline: Timeline for the lease
        value: Base rent value (can be a single value, series, or reference)
        unit_of_measure: Units for the value
        frequency: Frequency of the value (default: monthly)
        tenant: The tenant entity
        suite: Suite/unit identifier
        floor: Floor number or identifier (optional)
        use_type: Type of use (office, retail, etc.)
        status: Current status of the lease
        lease_type: Type of lease arrangement (gross, net, etc.)
        area: Square footage leased by tenant
        rent_escalations: List of rent escalations applied to this lease
        recovery_method: Method for calculating expense recoveries
        ti_allowance: Tenant improvement allowance (optional)
        leasing_commission: Leasing commission structure (optional)
        rollover_profile: Profile for future projections
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
    use_type: ProgramUseEnum  # TODO: pivot lease calculations based on use type (e.g., apartment, office, retail, etc.)
    
    # Lease details
    status: LeaseStatusEnum = LeaseStatusEnum.CONTRACT
    lease_type: LeaseTypeEnum
    area: PositiveFloat  # in square feet

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
    rollover_profile: Optional[RolloverProfile] = None  # Profile for future projections
    # TODO: support lookup for profile id?

    @property
    def lease_start(self) -> date:
        """
        Get the start date of the lease.
        
        Returns:
            Date object representing the lease start date
        """
        return self.timeline.start_date.to_timestamp().date()
    
    @property
    def lease_end(self) -> date:
        """
        Get the end date of the lease.
        
        Returns:
            Date object representing the lease end date
        """
        return self.timeline.end_date.to_timestamp().date()
    
    @property
    def is_active(self) -> bool:
        """
        Check if the lease is currently active.
        
        Returns:
            True if today's date is within the lease term, False otherwise
        """
        today = date.today()
        return self.lease_start <= today <= self.lease_end
    
    @property
    def is_actual(self) -> bool:
        """Check if this is an actual (contracted) lease."""
        return self.status == LeaseStatusEnum.CONTRACT
    
    @property
    def is_speculative(self) -> bool:
        """Check if this is a speculative/projected lease."""
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
        """
        Create a lease with specific start and end dates.
        
        Args:
            tenant: Tenant entity
            suite: Suite/unit identifier
            lease_start: Start date of the lease
            lease_end: End date of the lease
            **kwargs: Additional arguments to pass to the Lease constructor
        
        Returns:
            A new Lease instance
            
        Raises:
            ValueError: If lease_start is after lease_end
        """
        if lease_start >= lease_end:
            raise ValueError("Lease start date must be before end date")
        
        # Set default name if not provided
        if "name" not in kwargs:
            kwargs["name"] = f"{tenant.name} - {suite}"
        
        # Create the timeline
        timeline = Timeline.from_dates(
            start_date=lease_start,
            end_date=lease_end
        )
        
        return cls(
            tenant=tenant,
            suite=suite,
            timeline=timeline,
            **kwargs
        )
    
    @classmethod
    def from_duration(
        cls,
        tenant: Tenant,
        suite: str,
        lease_start: date,
        lease_term_months: PositiveInt,
        **kwargs
    ) -> "Lease":
        """
        Create a lease with start date and duration in months.
        
        Args:
            tenant: Tenant entity
            suite: Suite/unit identifier
            lease_start: Start date of the lease
            lease_term_months: Duration of lease in months
            **kwargs: Additional arguments to pass to the Lease constructor
        
        Returns:
            A new Lease instance
        """
        # Set default name if not provided
        if "name" not in kwargs:
            kwargs["name"] = f"{tenant.name} - {suite}"
        
        # Create the timeline
        timeline = Timeline(
            start_date=lease_start,
            duration_months=lease_term_months
        )
        
        return cls(
            tenant=tenant,
            suite=suite,
            timeline=timeline,
            **kwargs
        )
    
    def _apply_escalations(self, base_flow: pd.Series) -> pd.Series:
        """
        Apply all rent escalations to the base rent flow.
        
        Args:
            base_flow: Base rent cash flow series
            
        Returns:
            Modified cash flow with all escalations applied
        """
        if not self.rent_escalation:
            return base_flow
        
        rent_with_escalations = base_flow.copy()
        periods = self.timeline.period_index
        
        if self.rent_escalation:
            # Convert start date to period
            start_period = pd.Period(self.rent_escalation.start_date, freq="M")
            
            # Create mask for periods where the escalation applies
            mask = periods >= start_period
            
            if self.rent_escalation.type == "percentage":
                if self.rent_escalation.recurring:
                    # For recurring percentage increases, calculate compound growth
                    freq = self.rent_escalation.frequency_months or 12  # Default to annual
                    # Calculate how many escalation cycles for each period
                    months_elapsed = np.array([(p - start_period).n for p in periods])
                    cycles = np.floor(months_elapsed / freq) 
                    cycles[~mask] = 0  # Zero out cycles outside the mask
                    
                    # Apply compound growth: (1 + rate)^cycles
                    # For relative escalations, use compound growth
                    if self.rent_escalation.is_relative:
                        growth_factor = np.power(1 + (self.rent_escalation.amount / 100), cycles)
                        rent_with_escalations = rent_with_escalations * growth_factor
                    else:
                        # For absolute escalations, apply to base rent
                        growth_factor = np.power(1 + (self.rent_escalation.amount / 100), cycles)
                        escalation_series = base_flow * (growth_factor - 1)
                        rent_with_escalations += escalation_series
                else:
                    # For one-time percentage increases
                    if self.rent_escalation.is_relative:
                        # Apply to the current rent
                        growth_factor = 1 + (self.rent_escalation.amount / 100)
                        rent_with_escalations[mask] *= growth_factor
                    else:
                        # Apply to the base rent
                        growth_factor = self.rent_escalation.amount / 100
                        escalation_series = pd.Series(0, index=periods)
                        escalation_series[mask] = base_flow[mask] * growth_factor
                        rent_with_escalations += escalation_series
                
            elif self.rent_escalation.type == "fixed":
                # For fixed amount escalations
                if self.rent_escalation.recurring:
                    # For recurring fixed increases, calculate step increases
                    freq = self.rent_escalation.frequency_months or 12  # Default to annual
                    months_elapsed = np.array([(p - start_period).n for p in periods])
                    cycles = np.floor(months_elapsed / freq)
                    cycles[~mask] = 0  # Zero out cycles outside the mask
                    
                    # Monthly equivalent of the fixed amount
                    monthly_amount = self.rent_escalation.amount / 12 if self.rent_escalation.unit_of_measure == UnitOfMeasureEnum.AMOUNT else self.rent_escalation.amount
                    
                    # For relative increases, each cycle adds another increment
                    if self.rent_escalation.is_relative:
                        cumulative_increases = cycles * monthly_amount
                        escalation_series = pd.Series(cumulative_increases, index=periods)
                        rent_with_escalations += escalation_series
                    else:
                        # For absolute increases, apply to the base
                        cumulative_increases = cycles * monthly_amount
                        escalation_series = pd.Series(cumulative_increases, index=periods)
                        rent_with_escalations += escalation_series
                else:
                    # For one-time fixed increases
                    # Monthly equivalent of the fixed amount
                    monthly_amount = self.rent_escalation.amount / 12 if self.rent_escalation.unit_of_measure == UnitOfMeasureEnum.AMOUNT else self.rent_escalation.amount
                    escalation_series = pd.Series(0, index=periods)
                    escalation_series[mask] = monthly_amount
                    rent_with_escalations += escalation_series
                    
            elif self.rent_escalation.type == "cpi":
                # TODO: Implement CPI-based escalations
                # This would require a CPI index reference
                raise NotImplementedError("CPI-based escalations are not yet implemented")
        
        return rent_with_escalations
    
    def _apply_abatements(self, rent_flow: pd.Series) -> tuple[pd.Series, pd.Series]:
        """
        Apply rent abatements to the rent cash flow.
        
        Args:
            rent_flow: Rent cash flow series with escalations applied
            
        Returns:
            Modified cash flow with abatements applied
            Tuple containing:
             - pd.Series: Rent cash flow with abatements applied.
             - pd.Series: Abatement amounts (as positive values representing reduction).
        """
        if not self.rent_abatement:
            # Return original flow and zero abatement if no abatement defined
            return rent_flow, pd.Series(0.0, index=rent_flow.index)
        
        abated_rent_flow = rent_flow.copy()
        abatement_amount_series = pd.Series(0.0, index=rent_flow.index)
        periods = self.timeline.period_index
        
        # Calculate the abatement start period (relative to lease start)
        lease_start_period = pd.Period(self.lease_start, freq="M")
        abatement_start_month = self.rent_abatement.start_month - 1  # Convert to 0-indexed
        abatement_start_period = lease_start_period + abatement_start_month
        
        # Calculate the end period for the abatement
        abatement_end_period = abatement_start_period + self.rent_abatement.months
        
        # Create mask for periods where abatement applies
        abatement_mask = (periods >= abatement_start_period) & (periods < abatement_end_period)
        
        # Apply the abatement ratio to the applicable periods
        abatement_reduction = abated_rent_flow[abatement_mask] * self.rent_abatement.abated_ratio
        abated_rent_flow[abatement_mask] -= abatement_reduction # Subtract reduction from rent flow
        abatement_amount_series[abatement_mask] = abatement_reduction # Store positive abatement amount
        
        return abated_rent_flow, abatement_amount_series
    
    def compute_cf(
        self,
        property_area: Optional[PositiveFloat] = None,
        occupancy_rate: Optional[float] = None,
        lookup_fn: Optional[Callable[[str], Union[float, pd.Series]]] = None
    ) -> Dict[str, pd.Series]:
        """
        Compute cash flows for the lease including base rent, recoveries, TI, and LC.
        
        Args:
            property_area: Total property area for recovery calculations
            occupancy_rate: Current or projected occupancy rate
            lookup_fn: Optional function to resolve references
            
        Returns:
            Dictionary of cash flow series by type (base_rent, recoveries, revenue, 
            ti_allowance, leasing_commission, expenses, net)
        """
        # Get base cash flows using existing implementation
        base_rent = super().compute_cf(lookup_fn)
        base_rent_with_escalations = self._apply_escalations(base_rent)
        # Apply abatements and get both the abated rent and the abatement amount
        base_rent_final, abatement_cf = self._apply_abatements(base_rent_with_escalations)
        
        # Calculate recoveries if applicable
        recoveries = pd.Series(0, index=self.timeline.period_index)
        if self.recovery_method and property_area:
            # Calculate base recoveries
            recoveries = self.recovery_method.calculate_recoveries(
                tenant_area=self.area,
                property_area=property_area,
                timeline=self.timeline.period_index,
                occupancy_rate=occupancy_rate
            )
            
            # Apply abatement to recoveries if specified
            # NOTE: We apply the abatement ratio directly here, not the calculated abatement amount series
            if self.rent_abatement and self.rent_abatement.includes_recoveries:
                # Calculate abatement period mask again (could optimize)
                lease_start_period = pd.Period(self.lease_start, freq="M")
                abatement_start_month = self.rent_abatement.start_month - 1
                abatement_start_period = lease_start_period + abatement_start_month
                abatement_end_period = abatement_start_period + self.rent_abatement.months
                abatement_mask = (recoveries.index >= abatement_start_period) & (recoveries.index < abatement_end_period)
                # Apply abatement ratio
                recoveries[abatement_mask] *= (1 - self.rent_abatement.abated_ratio)
        
        # Calculate TI cash flows if applicable
        # TODO: create a method to apply TI to the base rent
        ti_cf = pd.Series(0, index=self.timeline.period_index)
        if self.ti_allowance:
            # Ensure TI timeline matches the lease timeline
            ti_cf = self.ti_allowance.compute_cf(lookup_fn)
            # Align to lease timeline in case of differences
            ti_cf = ti_cf.reindex(self.timeline.period_index, fill_value=0)
        
        # Calculate LC cash flows if applicable
        # TODO: create a method to apply LC to the base rent
        lc_cf = pd.Series(0, index=self.timeline.period_index)
        if self.leasing_commission:
            # Ensure LC timeline matches the lease timeline
            lc_cf = self.leasing_commission.compute_cf(lookup_fn)
            # Align to lease timeline in case of differences
            lc_cf = lc_cf.reindex(self.timeline.period_index, fill_value=0)
        
        # Calculate total cash flows
        revenue_cf = base_rent_final + recoveries
        expense_cf = ti_cf + lc_cf
        net_cf = revenue_cf - expense_cf
        
        # Return all components
        return {
            "base_rent": base_rent_final, # Rent after abatement
            "abatement": abatement_cf, # Abatement amount (positive value)
            "recoveries": recoveries,
            "revenue": revenue_cf, # Total revenue (abated rent + recoveries)
            "ti_allowance": ti_cf,
            "leasing_commission": lc_cf,
            "expenses": expense_cf,
            "net": net_cf
        }
    # FIXME: dataframe all the things? how do we want to handle cash flow components for later disaggregation?
    # TODO: we may want to retain more detailed cash flow components for later analysis/reporting

    # Methods for rollover/projections
    def project_future_cash_flows(
        self,
        projection_end_date: date,
        property_area: Optional[PositiveFloat] = None,
        occupancy_projection: Optional[pd.Series] = None
    ) -> pd.DataFrame:
        """
        Project lease cash flows into the future based on rollover assumptions.
        
        Creates a chain of actual and speculative leases extending to the 
        projection end date, following the rules in the rollover profile.
        
        For MARKET rollover scenarios, the method uses a blended terms approach that
        combines renewal and market terms based on renewal probability, rather than
        blending the resultant cash flows. This follows industry standards and produces
        more accurate results since the blending happens at the input/parameter level.
        
        Args:
            projection_end_date: How far into the future to project
            property_area: Total property area for recovery calculations
            occupancy_projection: Projected occupancy rates for variable recoveries
            
        Returns:
            DataFrame containing all cash flow components projected through the end date
        """
        # If no rollover profile is assigned, we can't project beyond the current lease
        if not self.rollover_profile:
            current_cf = self.compute_cf(property_area=property_area)
            return pd.DataFrame(current_cf)
        
        # Start with the actual lease cash flows
        result_df = pd.DataFrame(self.compute_cf(property_area=property_area))
        
        # Determine if we need to project beyond the current lease
        if self.lease_end < projection_end_date:
            # Get renewal probability from the rollover profile
            renewal_probability = self.rollover_profile.renewal_probability
            
            # Handle each expiration option differently according to specification
            if self.upon_expiration == UponExpirationEnum.RENEW:
                # RENEW: 100% renewal probability, create renewal lease
                renewal_lease = self.create_renewal_lease(as_of_date=self.lease_end)
                
                # Recursively project the renewal lease's cash flows
                renewal_df = renewal_lease.project_future_cash_flows(
                    projection_end_date=projection_end_date,
                    property_area=property_area,
                    occupancy_projection=occupancy_projection
                )
                
                # Combine the results, handling index properly
                result_df = pd.concat([result_df, renewal_df], sort=True)
                
            elif self.upon_expiration == UponExpirationEnum.VACATE:
                # VACATE: 0% renewal probability, create market lease after vacancy
                vacancy_start = self.lease_end
                new_lease = self.create_market_lease(
                    vacancy_start_date=vacancy_start,
                    property_area=property_area
                )
                
                # Recursively project the new lease's cash flows
                new_lease_df = new_lease.project_future_cash_flows(
                    projection_end_date=projection_end_date,
                    property_area=property_area,
                    occupancy_projection=occupancy_projection
                )
                
                # Combine the results, handling index properly
                result_df = pd.concat([result_df, new_lease_df], sort=True)
                
            elif self.upon_expiration == UponExpirationEnum.MARKET:
                # MARKET: Use single lease with blended terms instead of weighted cash flows
                market_lease = self.create_market_lease(
                    vacancy_start_date=self.lease_end,
                    property_area=property_area
                )
                
                # Recursively project the market lease's cash flows
                market_df = market_lease.project_future_cash_flows(
                    projection_end_date=projection_end_date,
                    property_area=property_area,
                    occupancy_projection=occupancy_projection
                )
                
                # Combine the results, handling index properly
                result_df = pd.concat([result_df, market_df], sort=True)
            
            elif self.upon_expiration == UponExpirationEnum.OPTION:
                # OPTION: Model tenant renewal option with 100% probability
                # Create a lease using option terms from the rollover profile
                option_lease = self.create_option_lease(as_of_date=self.lease_end)
                
                # Recursively project the option lease's cash flows
                option_df = option_lease.project_future_cash_flows(
                    projection_end_date=projection_end_date,
                    property_area=property_area,
                    occupancy_projection=occupancy_projection
                )
                
                # Combine the results, handling index properly
                result_df = pd.concat([result_df, option_df], sort=True)
                
            elif self.upon_expiration == UponExpirationEnum.REABSORB:
                # REABSORB: Space remains vacant, no automatic re-tenanting
                # The space is available for reabsorption through separate logic
                # For now, just return the original lease cash flows
                # Space will be vacant after lease_end
                raise NotImplementedError("Space reabsorption logic not implemented")
                # FIXME: implement space reabsorption logic throughout library
        
        return result_df
    
    def create_renewal_lease(self, as_of_date: date) -> "Lease":
        """
        Create a renewal lease based on this lease and the rollover profile.
        
        Args:
            as_of_date: The date to use for market rent calculations
            
        Returns:
            A new Lease object representing the renewal
            
        Raises:
            ValueError: If no rollover profile is defined for this lease
        """
        if not self.rollover_profile:
            raise ValueError("Cannot create renewal without a rollover profile")
        
        profile = self.rollover_profile
        
        # Calculate renewal start date (day after current lease ends)
        renewal_start = self.lease_end + timedelta(days=1)
        
        # Create timeline for the renewal
        timeline = Timeline.from_dates(
            start_date=renewal_start, 
            end_date=renewal_start + relativedelta(months=profile.term_months)
        )
        
        # Calculate renewal rent directly from the renewal terms
        renewal_rate = profile.calculate_renewal_rent(as_of_date)
        
        # Create tenant copy (since models are immutable)
        tenant = self.tenant.copy()
        
        # Create new TI allowance if specified in renewal terms
        ti_allowance, leasing_commission = self._create_lease_costs(
            profile.renewal_terms,
            timeline,
            renewal_rate,
            self.area
        )
        
        # Create and return the renewal lease with all appropriate attributes
        return Lease(
            name=f"{self.tenant.name} - {self.suite} (Renewal)",
            tenant=tenant,
            suite=self.suite,
            floor=self.floor,
            use_type=self.use_type,
            status=LeaseStatusEnum.SPECULATIVE,
            lease_type=self.lease_type,
            area=self.area,
            timeline=timeline,
            value=renewal_rate,
            unit_of_measure=UnitOfMeasureEnum.PSF,  # Use PSF for consistency
            frequency=FrequencyEnum.MONTHLY,  # Internal calculations use monthly
            
            # Apply renewal terms from profile
            rent_escalation=profile.renewal_terms.rent_escalation,
            rent_abatement=profile.renewal_terms.rent_abatement,
            recovery_method=profile.renewal_terms.recovery_method,
            
            # Apply newly created instances with proper timeline/reference
            ti_allowance=ti_allowance,
            leasing_commission=leasing_commission,
            
            # Set rollover behavior for future projections
            upon_expiration=profile.upon_expiration,
            rollover_profile=profile
        )
    
    def create_market_lease(
        self,
        vacancy_start_date: date,
        property_area: Optional[PositiveFloat] = None
    ) -> "Lease":
        """
        Create a new market lease for this space after vacancy.
        
        For MARKET rollover scenario, this creates a single lease with blended terms
        based on renewal probability, rather than creating separate leases and
        blending cash flows. This is more efficient and better matches industry
        standard practices.
        
        Args:
            vacancy_start_date: Date when the space becomes vacant
            property_area: Total property area (optional, for percentage calculations)
            
        Returns:
            A new Lease object representing the market lease
            
        Raises:
            ValueError: If no rollover profile is defined for this lease
        """
        if not self.rollover_profile:
            raise ValueError("Cannot create market lease without a rollover profile")
        
        profile = self.rollover_profile
        
        # Determine if we should use blended terms based on upon_expiration setting
        lease_terms = None
        if self.upon_expiration == UponExpirationEnum.MARKET:
            # For MARKET case, use blended terms
            lease_terms = profile.blend_lease_terms()
        else:
            # For other cases, use market terms
            lease_terms = profile.market_terms
        
        # Calculate lease start date after expected downtime period
        lease_start = vacancy_start_date + relativedelta(months=profile.downtime_months)
        
        # Create timeline for the market lease
        timeline = Timeline(
            start_date=lease_start,
            duration_months=profile.term_months
        )
        
        # Determine market rent using the selected terms
        market_rate = None
        if self.upon_expiration == UponExpirationEnum.MARKET:
            # For blended terms, calculate rent directly
            market_rate = profile._calculate_market_rent(lease_terms, lease_start)
        else:
            # For regular market terms, use the standard method
            market_rate = profile.calculate_market_rent(lease_start)
        
        # Create placeholder tenant for the speculative lease
        tenant = Tenant(
            id=f"speculative-{self.suite}-{lease_start}",
            name=f"Market Tenant ({self.suite})"
        )
        
        # Create TI allowance if specified in the lease terms
        ti_allowance, leasing_commission = self._create_lease_costs(
            lease_terms,
            timeline,
            market_rate,
            self.area
        )
        
        # Create and return the market lease with all appropriate attributes
        return Lease(
            name=f"Market Lease - {self.suite}",
            tenant=tenant,
            suite=self.suite,
            floor=self.floor,
            use_type=self.use_type,
            status=LeaseStatusEnum.SPECULATIVE,
            lease_type=LeaseTypeEnum.NET,  # Default lease type for market leases
            area=self.area,
            timeline=timeline,
            value=market_rate,
            unit_of_measure=UnitOfMeasureEnum.PSF,
            frequency=FrequencyEnum.MONTHLY,
            
            # Apply terms from the selected lease terms
            rent_escalation=lease_terms.rent_escalation,
            rent_abatement=lease_terms.rent_abatement,
            recovery_method=lease_terms.recovery_method,
            
            # Apply newly created instances with proper timeline/reference
            ti_allowance=ti_allowance,
            leasing_commission=leasing_commission,
            
            # Set rollover behavior for future projections
            upon_expiration=profile.upon_expiration,
            rollover_profile=profile
        )
    
    @classmethod
    def create_market_lease_for_vacant(
        cls,
        suite_id: str,
        area: PositiveFloat,
        use_type: ProgramUseEnum,
        lease_start: date,
        rollover_profile: 'RolloverProfile',
        floor: Optional[str] = None,
        upon_expiration: UponExpirationEnum = UponExpirationEnum.MARKET,
        **kwargs
    ) -> "Lease":
        """
        Create a speculative market lease for a vacant space.
        
        Args:
            suite_id: Suite/unit identifier
            area: Leasable area in square feet
            use_type: The intended use of the space
            lease_start: When the market lease begins
            rollover_profile: Profile containing market assumptions
            floor: Optional floor identifier
            upon_expiration: Behavior for rollover at expiration
            **kwargs: Additional arguments to pass to the Lease constructor
            
        Returns:
            A new speculative Lease instance
        """
        # Create timeline for the market lease
        timeline = Timeline(
            start_date=lease_start,
            duration_months=rollover_profile.term_months
        )
        
        # Determine if we should use blended terms
        lease_terms = None
        if upon_expiration == UponExpirationEnum.MARKET:
            # For MARKET case, use blended terms
            lease_terms = rollover_profile.blend_lease_terms()
        else:
            # For other cases, use market terms
            lease_terms = rollover_profile.market_terms
        
        # Determine market rent
        market_rate = rollover_profile._calculate_market_rent(lease_terms, lease_start)
        
        # Create placeholder tenant
        tenant = Tenant(
            id=f"speculative-{suite_id}-{lease_start}",
            name=f"Market Tenant ({suite_id})"
        )
        
        # Create TI allowance if specified
        ti_allowance, leasing_commission = cls._create_lease_costs(
            lease_terms,
            timeline,
            market_rate,
            area
        )
        
        # Create and return the market lease
        return cls(
            name=f"Market Lease - {suite_id}",
            tenant=tenant,
            suite=suite_id,
            floor=floor,
            use_type=use_type,
            status=LeaseStatusEnum.SPECULATIVE,
            lease_type=LeaseTypeEnum.NET,  # Default lease type for market leases
            area=area,
            timeline=timeline,
            value=market_rate,
            unit_of_measure=UnitOfMeasureEnum.PSF,
            frequency=FrequencyEnum.MONTHLY,
            
            # Apply terms from the selected lease terms
            rent_escalation=lease_terms.rent_escalation,
            rent_abatement=lease_terms.rent_abatement,
            recovery_method=lease_terms.recovery_method,
            
            # Apply lease costs
            ti_allowance=ti_allowance,
            leasing_commission=leasing_commission,
            
            # Set rollover behavior
            upon_expiration=upon_expiration,
            rollover_profile=rollover_profile,
            
            # Include any additional kwargs
            **kwargs
        )

    def create_option_lease(self, as_of_date: date) -> "Lease":
        """
        Create a lease based on option terms defined in the rollover profile.
        
        Args:
            as_of_date: The date to use for option rent calculations
            
        Returns:
            A new Lease object representing the option lease
            
        Raises:
            ValueError: If no rollover profile is defined for this lease
                       or if option_terms is not defined in the profile
        """
        if not self.rollover_profile:
            raise ValueError("Cannot create option lease without a rollover profile")
        
        profile = self.rollover_profile
        
        # Ensure option_terms exists
        if not hasattr(profile, 'option_terms'):
            raise ValueError("Option terms not defined in rollover profile")
        
        # Calculate option start date (day after current lease ends)
        option_start = self.lease_end + timedelta(days=1)
        
        # Create timeline for the option lease
        timeline = Timeline.from_dates(
            start_date=option_start, 
            end_date=option_start + relativedelta(months=profile.term_months)
        )
        
        # Calculate option rent directly from the option terms
        option_rate = profile.calculate_option_rent(as_of_date)
        
        # Create tenant copy (since models are immutable)
        tenant = self.tenant.copy()
        
        # Create new TI allowance if specified in option terms
        ti_allowance, leasing_commission = self._create_lease_costs(
            profile.option_terms,
            timeline,
            option_rate,
            self.area
        )
        
        # Create and return the option lease with all appropriate attributes
        return Lease(
            name=f"{self.tenant.name} - {self.suite} (Option)",
            tenant=tenant,
            suite=self.suite,
            floor=self.floor,
            use_type=self.use_type,
            status=LeaseStatusEnum.SPECULATIVE,
            lease_type=self.lease_type,
            area=self.area,
            timeline=timeline,
            value=option_rate,
            unit_of_measure=UnitOfMeasureEnum.PSF,  # Use PSF for consistency
            frequency=FrequencyEnum.MONTHLY,  # Internal calculations use monthly
            
            # Apply option terms from profile
            rent_escalation=profile.option_terms.rent_escalation,
            rent_abatement=profile.option_terms.rent_abatement,
            recovery_method=profile.option_terms.recovery_method,
            
            # Apply newly created instances with proper timeline/reference
            ti_allowance=ti_allowance,
            leasing_commission=leasing_commission,
            
            # Set rollover behavior for future projections
            upon_expiration=profile.upon_expiration,
            rollover_profile=profile
        )

    def _create_lease_costs(
        self,
        lease_terms: 'RolloverLeaseTerms',
        timeline: Timeline,
        rent_rate: PositiveFloat,
        area: PositiveFloat
    ) -> tuple:
        """
        Helper method to create TI and LC objects for lease creation.
        
        Args:
            lease_terms: Terms to use for TI and LC creation
            timeline: Timeline for the lease
            rent_rate: Rent rate used for LC calculations
            area: Leasable area in square feet
            
        Returns:
            Tuple of (ti_allowance, leasing_commission)
        """
        # Create TI allowance if specified
        ti_allowance = None
        if lease_terms.ti_allowance:
            ti_allowance = TenantImprovementAllowance(
                **lease_terms.ti_allowance.model_dump(exclude={'timeline', 'reference'}),
                timeline=timeline,
                reference=area
            )
        
        # Create leasing commission if specified
        leasing_commission = None
        if lease_terms.leasing_commission:
            # Calculate annual rent as basis for commission
            annual_rent = rent_rate * area
            if lease_terms.frequency == FrequencyEnum.MONTHLY:
                annual_rent = annual_rent * 12
            
            leasing_commission = LeasingCommission(
                **lease_terms.leasing_commission.model_dump(exclude={'timeline', 'value'}),
                timeline=timeline,
                value=annual_rent
            )
        
        return ti_allowance, leasing_commission


class VacantSuite(Model):
    """
    Represents a vacant leasable space.

    Attributes:
        suite: Unique identifier for the space
        floor: Floor number or identifier (optional)
        area: Square footage
        use_type: Intended use
    """
    # NOTE: this could be important with Space Absorption approach
    suite: str
    floor: str
    area: PositiveFloat
    use_type: ProgramUseEnum


class RentRoll(Model):
    """
    Collection of all leases and vacant spaces.
    
    Attributes:
        leases: List of all lease agreements
        vacant_suites: List of all vacant suites
    """

    leases: List[Lease]
    vacant_suites: List[VacantSuite]

    @property
    def total_occupied_area(self) -> PositiveFloat:
        """
        Calculate total leased area in square feet.
        
        Returns:
            Sum of all leased areas
        """
        return sum(lease.area for lease in self.leases)

    @property
    def occupancy_rate(self) -> FloatBetween0And1:
        """
        Calculate current occupancy rate as a decimal between 0 and 1.
        
        Returns:
            Occupancy rate (leased area / total area)
        """
        total_area = self.total_occupied_area + sum(
            suite.area for suite in self.vacant_suites
        )
        return self.total_occupied_area / total_area if total_area > 0 else 0.0

    @model_validator(mode="after")
    def validate_lease_tenant_mapping(self) -> "RentRoll":
        """Validate that all leases have a corresponding tenant."""
        # TODO: implement this
        # tenant_ids = {t.id for t in self.tenants}
        # for lease in self.leases:
        #     if lease.tenant_id not in tenant_ids:
        #         raise ValueError(f"Lease '{lease.name}' references unknown tenant ID '{lease.tenant_id}'")
        return self

    # TODO: add validation for total area

    # TODO: property for all suites
    # TODO: property for stacked floors data (to enable viz)


class MiscIncome(CashFlowModel):
    """
    Represents miscellaneous income items like parking revenue, vending, antenna income, etc.
    
    Inherits from CashFlowModel and includes standard attributes like `value`, 
    `timeline`, `unit_of_measure`, `reference`, etc.
    
    The `reference` attribute, if a string, can refer to either:
      - An attribute of the `Property` object (e.g., "gross_building_area").
      - The string value of an `AggregateLineKey` enum member (e.g., "Potential Gross Revenue").
      Handling of the looked-up value depends on the `compute_cf` implementation.

    Attributes:
        category: Fixed as "Revenue"
        subcategory: Revenue subcategory (e.g., "Miscellaneous")
        variable_ratio: Portion of income that varies with occupancy (0-1)
        growth_rate: Growth profile for the income (Optional)
        growth_start_date: Date from which growth starts applying (Optional)
    """
    category: str = "Revenue"
    subcategory: RevenueSubcategoryEnum = "Miscellaneous"
    
    # For variable calculation
    variable_ratio: Optional[FloatBetween0And1] = None
    
    # For growth calculation
    growth_rate: Optional[GrowthRate] = None
    growth_start_date: Optional[date] = None
    
    # TODO: Add support for expense offsetting in recovery calculations
    # TODO: Add support for revenue sharing with tenants
    # TODO: Add support for percentage rent exclusions
    
    @property
    def is_variable(self) -> bool:
        """
        Check if the income is variable with occupancy.
        
        Returns:
            True if variable_ratio is set, False otherwise
        """
        return self.variable_ratio is not None
    
    def compute_cf(
        self,
        occupancy_rate: Optional[float] = None,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Union[float, int, str, date, pd.Series, Dict, Any]]] = None
    ) -> pd.Series:
        """
        Compute the cash flow for the miscellaneous income item.
        
        Handles base value calculation (potentially using `reference` lookup),
        growth rate application, and occupancy adjustments.

        If `self.reference` is set and `lookup_fn` is provided:
          - If the lookup returns a pd.Series (e.g., an AggregateLineKey value):
            Uses the series as the base, potentially applying unit_of_measure 
            factors (like percentage).
          - If the lookup returns a scalar: 
            Passes the lookup to `super().compute_cf` to handle scalar-based 
            calculations (e.g., $/Unit based on property area).
        If `self.reference` is not set, calculates based on `self.value` and `self.timeline`.
        
        Args:
            occupancy_rate: Optional occupancy rate (as a float, typically 0-1) 
                            to adjust variable portions of the income.
            lookup_fn: Function provided by the analysis engine to resolve 
                       references (UUIDs, property attributes, or AggregateLineKeys).
                       
        Returns:
            A pandas Series representing the monthly cash flow for this income item.
            
        Raises:
            ValueError: If `reference` is set but `lookup_fn` is not provided.
            TypeError: If the type returned by `lookup_fn` is incompatible with the
                       `unit_of_measure` or calculation logic.
        """
        logger.debug(f"Computing cash flow for MiscIncome: '{self.name}' ({self.model_id})") # DEBUG: Entry
        calculated_flow: pd.Series
        base_value_source: Optional[Union[float, int, pd.Series]] = None

        # --- Determine Base Flow (Handles Reference) ---
        logger.debug(f"  Reference: {self.reference}, UnitOfMeasure: {self.unit_of_measure}") # DEBUG: Input info
        if self.reference is not None:
            if lookup_fn is None:
                raise ValueError(f"Reference '{self.reference}' is set for MiscIncome '{self.name}', but no lookup_fn was provided.")
            
            looked_up_value = lookup_fn(self.reference)
            
            if isinstance(looked_up_value, pd.Series):
                # --- Handle Reference to Aggregate (Series) --- 
                base_series = looked_up_value
                
                # Apply unit_of_measure logic (% or Factor of the aggregate series)
                if self.unit_of_measure == UnitOfMeasureEnum.BY_PERCENT and isinstance(self.value, (float, int)):
                    calculated_flow = base_series * (self.value / 100.0)
                elif self.unit_of_measure == UnitOfMeasureEnum.BY_FACTOR and isinstance(self.value, (float, int)):
                     calculated_flow = base_series * self.value
                elif self.unit_of_measure == UnitOfMeasureEnum.AMOUNT:
                      # Fall back to standard compute_cf if UoM is AMOUNT but ref is Series
                      calculated_flow = super().compute_cf(lookup_fn=lookup_fn)
                      # Log warning instead of print
                      logger.warning(f"MiscIncome '{self.name}' referenced an aggregate series '{self.reference}' but UnitOfMeasure was '{self.unit_of_measure}'. Using standard value calculation.")
                else: 
                    raise TypeError(f"MiscIncome '{self.name}' referenced an aggregate series '{self.reference}' with an unsupported UnitOfMeasure '{self.unit_of_measure}'.")
                
                # Ensure index alignment if MiscIncome has its own timeline
                if hasattr(self, 'timeline') and self.timeline is not None:
                    target_periods = self.timeline.period_index
                    calculated_flow = calculated_flow.reindex(target_periods, fill_value=0.0)
                
                base_value_source = looked_up_value

            elif isinstance(looked_up_value, (float, int, str, date, dict)): 
                # --- Handle Reference to Scalar or compatible type --- 
                calculated_flow = super().compute_cf(lookup_fn=lookup_fn)
                base_value_source = looked_up_value
            else:
                 raise TypeError(f"MiscIncome '{self.name}' received an unexpected type ({type(looked_up_value)}) from lookup_fn for reference '{self.reference}'.")
        else:
            # --- No Reference --- 
            logger.debug("  No reference set. Calculating base from self.value.") # DEBUG: No reference
            calculated_flow = super().compute_cf(lookup_fn=lookup_fn)

        # --- Apply Adjustments (Growth, Occupancy) --- 
        logger.debug("  Applying growth and occupancy adjustments.") # DEBUG: Adjustments start
        # --- Apply Growth (Using Helper - Placeholder for Step 4) ---
        if self.growth_rate is not None:
            # Determine the start date for growth application
            # Use the specific growth_start_date if provided, otherwise default to the item's timeline start
            effective_growth_start = self.growth_start_date or self.timeline.start_date.to_timestamp().date()
            logger.debug(f"  Applying growth profile '{self.growth_rate.name}' starting from {effective_growth_start}.")
            calculated_flow = self._apply_compounding_growth(
                base_series=calculated_flow,
                growth_profile=self.growth_rate,
                growth_start_date=effective_growth_start
            )
        else:
             logger.debug("  No growth profile specified.")
             
        # Apply occupancy adjustment if applicable.
        if occupancy_rate is not None and self.is_variable:
             if pd.api.types.is_numeric_dtype(calculated_flow) and self.variable_ratio is not None:
                 variable_ratio = self.variable_ratio
                 fixed_ratio = 1.0 - variable_ratio
                 current_occupancy = float(occupancy_rate)
                 # For income, adjustment increases with occupancy
                 adjustment_ratio = fixed_ratio + (variable_ratio * current_occupancy) 
                 calculated_flow = calculated_flow * adjustment_ratio
             else:
                 # Log warning instead of print
                 logger.warning(f"Cannot apply occupancy adjustment to non-numeric series or missing variable_ratio for MiscIncome '{self.name}'.")
        
        logger.debug(f"Finished computing cash flow for MiscIncome: '{self.name}'. Final Sum: {calculated_flow.sum():.2f}") # DEBUG: Exit
        return calculated_flow
    

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


# class Revenues(Model):
#     """
#     Represents the revenue generated by an asset.

#     Attributes:
#         revenue_items: List of revenue line items as CashFlowModel instances
#     """
#     # FIXME: develop this further

#     revenue_items: List[CashFlowModel]

#     @property
#     def total_revenue(self) -> PositiveFloat:
#         """
#         Calculate total revenue by summing all revenue items.
#         
#         Returns:
#             Total revenue as a positive float
#         """
#         # FIXME: Incorrect reference 'line_items' and 'amount'
#         return sum(item.amount for item in self.line_items)

# FIXME: add support for space absorption approach (esp for development)
# FIXME: add support for market/absorption profile approach for space absorption
