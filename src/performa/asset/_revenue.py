from datetime import date, relativedelta, timedelta
from typing import Callable, Dict, List, Literal, Optional, Union

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
)
from ..core._model import Model
from ..core._timeline import Timeline
from ..core._types import (
    FloatBetween0And1,
    PositiveFloat,
    PositiveInt,
)
from ._lc import LeasingCommission
from ._recovery import RecoveryMethod
from ._rollover import RolloverProfile
from ._ti import TenantImprovementAllowance


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
    # suite: str

    # # Space
    # leased_area: PositiveFloat  # in square feet
    # percent_of_building: FloatBetween0And1

    # # Use
    # use_type: ProgramUseEnum

    # # Current Lease Terms
    # lease_start: date
    # lease_end: date
    # current_base_rent: PositiveFloat  # annual or monthly rent
    # rent_type: LeaseTypeEnum  # options: Gross, Net, Modified Gross
    # expense_base_year: Optional[int] = None

    # # Renewal Terms
    # # renewal_probability: FloatBetween0And1  # NOTE: this should only be in the lease model?
    # market_profile: MarketProfile  # reference to applicable market assumptions


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
    upon_expiration: Literal["market", "renew", "vacate", "option", "reconfigured"]
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
        tenant_name: str,
        suite: str,
        lease_start: date,
        lease_end: date,
        **kwargs
    ) -> "Lease":
        """
        Create a lease with specific start and end dates.
        
        Args:
            tenant_name: Name of the tenant
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
            kwargs["name"] = f"{tenant_name} - {suite}"
        
        # Create the timeline
        timeline = Timeline.from_dates(
            start_date=lease_start,
            end_date=lease_end
        )
        
        return cls(
            tenant_name=tenant_name,
            suite=suite,
            timeline=timeline,
            **kwargs
        )
    
    @classmethod
    def from_duration(
        cls,
        tenant_name: str,
        suite: str,
        lease_start: date,
        lease_term_months: PositiveInt,
        **kwargs
    ) -> "Lease":
        """
        Create a lease with start date and duration in months.
        
        Args:
            tenant_name: Name of the tenant
            suite: Suite/unit identifier
            lease_start: Start date of the lease
            lease_term_months: Duration of lease in months
            **kwargs: Additional arguments to pass to the Lease constructor
        
        Returns:
            A new Lease instance
        """
        # Set default name if not provided
        if "name" not in kwargs:
            kwargs["name"] = f"{tenant_name} - {suite}"
        
        # Create the timeline
        timeline = Timeline(
            start_date=lease_start,
            duration_months=lease_term_months
        )
        
        return cls(
            tenant_name=tenant_name,
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
        
        # Calculate recoveries if applicable
        # TODO: create a method to apply recoveries to the base rent
        recoveries = pd.Series(0, index=self.timeline.period_index)
        if self.recovery_method and property_area:
            recoveries = self.recovery_method.calculate_recoveries(
                tenant_area=self.area,
                property_area=property_area,
                timeline=self.timeline.period_index,
                occupancy_rate=occupancy_rate
            )
        
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
        revenue_cf = base_rent_with_escalations + recoveries
        expense_cf = ti_cf + lc_cf
        net_cf = revenue_cf - expense_cf
        
        # Return all components
        return {
            "base_rent": base_rent_with_escalations,
            "recoveries": recoveries,
            "revenue": revenue_cf,
            "ti_allowance": ti_cf,
            "leasing_commission": lc_cf,
            "expenses": expense_cf,
            "net": net_cf
        }
    # FIXME: dataframe all the things? how do we want to handle cash flow components for later disaggregation?

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
        
        # Start with the actual lease
        result_df = pd.DataFrame(self.compute_cf(property_area=property_area))
        
        # Determine if we need to project beyond the current lease
        if self.lease_end < projection_end_date:
            # Check the upon_expiration setting to determine what happens next
            if self.upon_expiration == "vacate":
                # No further leasing activity, return current lease only
                return result_df
            
            # Get renewal probability from the rollover profile
            renewal_probability = self.rollover_profile.renewal_probability
            
            # In deterministic modeling, we decide based on probability threshold
            # For Monte Carlo, we would use random sampling instead
            if self.upon_expiration == "renew" or renewal_probability > 0.5:  # Simple decision rule
                # Create renewal lease
                renewal_lease = self.create_renewal_lease(as_of_date=self.lease_end)
                
                # Recursively project the renewal lease's cash flows
                renewal_df = renewal_lease.project_future_cash_flows(
                    projection_end_date=projection_end_date,
                    property_area=property_area,
                    occupancy_projection=occupancy_projection
                )
                
                # Combine the results, making sure to handle index properly
                result_df = pd.concat([result_df, renewal_df], sort=True)
                
            elif self.upon_expiration == "market":
                # Create new market lease after vacancy
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
                
                # Combine the results, making sure to handle index properly
                result_df = pd.concat([result_df, new_lease_df], sort=True)
                
            elif self.upon_expiration == "option":
                # TODO: Implement option-based renewal logic
                ...
                
            elif self.upon_expiration == "reconfigured":
                # TODO: Implement reconfiguration logic (splitting/combining spaces)
                ...
        
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
        tenant = self.tenant.model_copy()
        
        # Create new TI allowance if specified in renewal terms
        ti_allowance = None
        if profile.renewal_terms.ti_allowance:
            ti_allowance = TenantImprovementAllowance(
                # Copy configuration from profile's renewal terms but update timeline
                **profile.renewal_terms.ti_allowance.model_dump(exclude={'timeline', 'reference'}),
                timeline=timeline,
                reference=self.area
            )
        
        # Create new leasing commission if specified in renewal terms
        leasing_commission = None
        if profile.renewal_terms.leasing_commission:
            # Calculate annual rent as basis for commission
            annual_rent = renewal_rate * self.area
            if profile.renewal_terms.frequency == FrequencyEnum.MONTHLY:
                annual_rent = annual_rent * 12
                
            leasing_commission = LeasingCommission(
                **profile.renewal_terms.leasing_commission.model_dump(exclude={'timeline', 'value'}),
                timeline=timeline,
                value=annual_rent
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
        
        # Calculate lease start date after expected downtime period
        lease_start = vacancy_start_date + relativedelta(months=profile.downtime_months)
        
        # Create timeline for the market lease
        timeline = Timeline(
            start_date=lease_start,
            duration_months=profile.term_months
        )
        
        # Determine market rent as of lease start date
        market_rate = profile.calculate_market_lease_rent(lease_start)
        
        # Create placeholder tenant for the speculative lease
        tenant = Tenant(
            id=f"speculative-{self.suite}-{lease_start}",
            name=f"Market Tenant ({self.suite})"
        )
        
        # Create TI allowance if specified in market terms
        ti_allowance = None
        if profile.market_terms.ti_allowance:
            ti_allowance = TenantImprovementAllowance(
                **profile.market_terms.ti_allowance.model_dump(exclude={'timeline', 'reference'}),
                timeline=timeline,
                reference=self.area
            )
        
        # Create leasing commission if specified in market terms
        leasing_commission = None
        if profile.market_terms.leasing_commission:
            # Calculate annual rent as basis for commission
            annual_rent = market_rate * self.area
            if profile.market_terms.frequency == FrequencyEnum.MONTHLY:
                annual_rent = annual_rent * 12
                
            leasing_commission = LeasingCommission(
                **profile.market_terms.leasing_commission.model_dump(exclude={'timeline', 'value'}),
                timeline=timeline,
                value=annual_rent
            )
        
        # Create and return the market lease with all appropriate attributes
        return Lease(
            name=f"Market Lease - {self.suite}",
            tenant=tenant,
            suite=self.suite,
            floor=self.floor,  # Maintain same floor
            use_type=self.use_type,  # Maintain same use type
            status=LeaseStatusEnum.SPECULATIVE,
            lease_type=LeaseTypeEnum.NET,  # Default lease type for market leases
            area=self.area,
            timeline=timeline,
            value=market_rate,
            unit_of_measure=UnitOfMeasureEnum.PSF,  # Use PSF for consistency
            frequency=FrequencyEnum.MONTHLY,  # Internal calculations use monthly
            
            # Apply market terms from profile
            rent_escalation=profile.market_terms.rent_escalation,
            rent_abatement=profile.market_terms.rent_abatement,
            recovery_method=profile.market_terms.recovery_method,
            
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
            **kwargs: Additional arguments to pass to the Lease constructor
            
        Returns:
            A new speculative Lease instance
        """
        # Create timeline for the market lease
        timeline = Timeline(
            start_date=lease_start,
            duration_months=rollover_profile.term_months
        )
        
        # Determine market rent
        market_rate = rollover_profile.calculate_market_lease_rent(lease_start)
        
        # Create placeholder tenant
        tenant = Tenant(
            id=f"speculative-{suite_id}-{lease_start}",
            name=f"Market Tenant ({suite_id})"
        )
        
        # Create TI allowance if specified
        ti_allowance = None
        if rollover_profile.market_terms.ti_allowance:
            ti_allowance = TenantImprovementAllowance(
                **rollover_profile.market_terms.ti_allowance.model_dump(exclude={'timeline', 'reference'}),
                timeline=timeline,
                reference=area
            )
        
        # Create leasing commission if specified
        leasing_commission = None
        if rollover_profile.market_terms.leasing_commission:
            # Calculate annual rent as basis for commission
            annual_rent = market_rate * area
            if rollover_profile.market_terms.frequency == FrequencyEnum.MONTHLY:
                annual_rent = annual_rent * 12
                
            leasing_commission = LeasingCommission(
                **rollover_profile.market_terms.leasing_commission.model_dump(exclude={'timeline', 'value'}),
                timeline=timeline,
                value=annual_rent
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
            unit_of_measure=UnitOfMeasureEnum.PSF,  # Use PSF for consistency
            frequency=FrequencyEnum.MONTHLY,  # Internal calculations use monthly
            
            # Apply market terms
            rent_escalation=rollover_profile.market_terms.rent_escalation,
            rent_abatement=rollover_profile.market_terms.rent_abatement,
            recovery_method=rollover_profile.market_terms.recovery_method,
            
            # Apply lease costs
            ti_allowance=ti_allowance,
            leasing_commission=leasing_commission,
            
            # Set rollover behavior
            upon_expiration=rollover_profile.upon_expiration,
            rollover_profile=rollover_profile,
            
            # Include any additional kwargs
            **kwargs
        )


class VacantSuite(Model):
    """
    Represents a vacant leasable space.

    Attributes:
        suite_id: Unique identifier for the space
        area: Square footage
        use_type: Intended use
        asking_rent: Listed rental rate
        last_lease_end: When space became vacant (optional)
    """
    # NOTE: this could be important with Space Absorption approach
    suite_id: str
    area: PositiveFloat
    use_type: ProgramUseEnum
    asking_rent: PositiveFloat
    last_lease_end: Optional[date] = None


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
        """
        Ensure all leases map to tenants in the rent roll.
        
        Returns:
            The validated RentRoll instance
            
        Raises:
            ValueError: If a lease references a tenant not found in the rent roll
        """
        tenant_names = {lease.tenant_name for lease in self.leases}
        for lease in self.leases:
            if lease.tenant_name not in tenant_names:
                raise ValueError(
                    f"Lease references tenant {lease.tenant_name} "
                    f"not found in rent roll"
                )
        return self

    # TODO: add validation for total area

    # TODO: property for all suites
    # TODO: property for stacked floors data (to enable viz)


class MiscIncome(CashFlowModel):
    """
    Represents miscellaneous income items like parking revenue, vending, antenna income, etc.

    Attributes:
        category: Fixed as "Revenue"
        subcategory: Revenue subcategory (e.g., "Miscellaneous")
        variable_ratio: Portion of income that varies with occupancy (0-1)
        growth_rate: Annual growth rate for income (e.g., 0.03 for 3% growth)
    """
    category: str = "Revenue"
    subcategory: RevenueSubcategoryEnum = "Miscellaneous"
    
    # For variable calculation
    variable_ratio: Optional[FloatBetween0And1] = None
    
    # For growth calculation
    growth_rate: Optional[FloatBetween0And1] = None
    
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
        lookup_fn: Optional[Callable[[str], Union[float, pd.Series]]] = None
    ) -> pd.Series:
        """
        Compute the cash flow for the miscellaneous income item with optional 
        occupancy and growth adjustments.
        
        Args:
            occupancy_rate: Current or projected occupancy rate (0-1)
            lookup_fn: Optional function to resolve references
            
        Returns:
            Monthly cash flow series
        """
        # Compute the base cash flow
        base_flow = super().compute_cf(lookup_fn)
        
        # Apply growth rate adjustment if provided
        if self.growth_rate is not None:
            months = np.arange(len(base_flow))
            growth_factors = np.power(1 + (self.growth_rate / 12), months)
            base_flow = base_flow * growth_factors

        # Apply occupancy adjustment if applicable
        if occupancy_rate is not None and self.is_variable:
            variable_ratio = self.variable_ratio
            adjustment_ratio = (1 - variable_ratio) + variable_ratio * occupancy_rate
            base_flow = base_flow * adjustment_ratio
        
        return base_flow


class MiscIncomeCollection(Model):
    """
    Collection of miscellaneous income items.
    
    Attributes:
        income_items: List of miscellaneous income items
    """
    income_items: List[MiscIncome]
    
    @property
    def total_annual_income(self) -> PositiveFloat:
        """
        Calculate total annual base income by summing the cash flows of all income items.
        
        Returns:
            Total annual income as a positive float
            
        Raises:
            ValueError: If no income items are provided
        """
        if not self.income_items:
            raise ValueError("No income items provided")
        
        # Sum the cash flows of all income items
        return sum(item.compute_cf() for item in self.income_items)
    
    @property
    def total_annual_income_df(self) -> pd.DataFrame:
        """
        Calculate total annual base income using pandas DataFrame approach.
        
        Returns:
            DataFrame with income items and their values
            
        Raises:
            ValueError: If no income items are provided
        """
        if not self.income_items:
            raise ValueError("No income items provided")
        
        # Create a DataFrame with income items and their values
        df = pd.DataFrame({
            'name': [item.name for item in self.income_items],
            'value': [item.value for item in self.income_items]
        })
        
        return df
    
    # TODO: Add methods for handling expense offsetting income
    # TODO: Add methods for handling percentage rent eligible income
    # TODO: Add methods for handling revenue sharing calculations


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


class Revenues(Model):
    """
    Represents the revenue generated by an asset.

    Attributes:
        revenue_items: List of revenue line items as CashFlowModel instances
    """
    # FIXME: develop this further

    revenue_items: List[CashFlowModel]

    @property
    def total_revenue(self) -> PositiveFloat:
        """
        Calculate total revenue by summing all revenue items.
        
        Returns:
            Total revenue as a positive float
        """
        return sum(item.amount for item in self.line_items)

# FIXME: add support for space absorption approach (esp for development)
# FIXME: add support for market/absorption profile approach for space absorption
