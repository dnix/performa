from typing import Literal, Optional
from datetime import date, timedelta, relativedelta

from ..core._enums import UnitOfMeasureEnum, LeaseStatusEnum, LeaseTypeEnum, ProgramUseEnum
from ..core._model import Model
from ..core._timeline import Timeline
from ..core._types import FloatBetween0And1, PositiveFloat, PositiveInt

from ._recovery import RecoveryMethod
from ._ti import TenantImprovementAllowance
from ._lc import (
    LeasingCommission,
)
from ._revenue import (
    RentEscalation,
    RentAbatement,
    Lease,
    Tenant,
)


class LeaseTerms(Model):
    """
    Base class for lease terms applied in different scenarios.
    
    Contains common fields needed for any lease creation scenario, whether
    market lease or renewal.
    
    Attributes:
        rent_escalation: Rent increase structure for the lease term
        rent_abatement: Free rent periods applied to this lease
        recovery_method: Method for calculating expense recoveries
        ti_allowance: Tenant improvement allowance configuration
        leasing_commission: Leasing commission structure
    """
    rent_escalation: Optional[RentEscalation] = None
    rent_abatement: Optional[RentAbatement] = None
    recovery_method: Optional[RecoveryMethod] = None
    ti_allowance: Optional[TenantImprovementAllowance] = None
    leasing_commission: Optional[LeasingCommission] = None
    
    @property
    def has_free_rent(self) -> bool:
        """
        Check if these terms include free rent.
        
        Returns:
            Boolean indicating whether rent abatement is specified
        """
        return bool(self.rent_abatements)
    
    @property
    def has_ti(self) -> bool:
        """
        Check if these terms include TI allowance.
        
        Returns:
            Boolean indicating whether tenant improvement allowance is specified
        """
        return self.ti_allowance is not None
    
    @property
    def has_lc(self) -> bool:
        """
        Check if these terms include leasing commissions.
        
        Returns:
            Boolean indicating whether leasing commission is specified
        """
        return self.leasing_commission is not None
    

class RolloverProfile(Model):
    """
    Comprehensive profile for lease rollovers, renewals and market assumptions.
    
    Used to project speculative/market leases after actual/contractual lease expiration.
    This profile contains all parameters needed to model future leasing scenarios.
    
    Attributes:
        name: Identifier for this rollover profile
        term_months: Standard lease term duration in months
        renewal_probability: Probability that a tenant will renew their lease
        downtime_months: Expected vacancy period between leases
        market_terms: Terms to apply for new market leases
        renewal_terms: Terms to apply if lease is renewed
        upon_expiration: Action to take when projected lease expires
        next_profile: Profile to use after this one (if chaining)
        max_projection_years: Maximum number of years to project leases
    """
    name: str

    # Market assumptions
    term_months: PositiveInt
    renewal_probability: FloatBetween0And1
    downtime_months: int  # months between vacancy and lease start
    
    # Lease terms for different scenarios
    market_terms: LeaseTerms
    renewal_terms: LeaseTerms
    
    # Rollover behavior
    upon_expiration: Literal["market", "renew", "vacate", "option", "reconfigured"] = "market"
    next_profile: Optional[str] = None  # Name of next profile to use if chaining
    
    # Projection limits
    max_projection_years: int = 99

    def create_renewal_lease(self, original_lease: "Lease", as_of_date: date) -> "Lease":
        """
        Create a renewal lease based on the original lease and renewal terms.
        
        This method generates a new lease that represents a tenant renewing their
        existing lease, applying the renewal terms from this profile.
        
        Args:
            original_lease: The existing lease that is being renewed
            as_of_date: The date to use for market rent calculations
            
        Returns:
            A new Lease object representing the renewal
        """
        # Calculate renewal start - day after original lease ends
        renewal_start = original_lease.lease_end + timedelta(days=1)
        
        # Create timeline for the renewal
        timeline = Timeline.from_dates(
            start_date=renewal_start, 
            end_date=renewal_start + relativedelta(months=self.term_months)
        )
        
        # Apply discount to market rate for renewal scenario
        market_rate = self._calculate_market_rent(as_of_date)
        renewal_rate = market_rate * 0.95  # 5% discount for renewals
        
        # Create tenant copy since models are immutable
        tenant = original_lease.tenant.model_copy()
        
        # Create new TI allowance if specified in renewal terms
        ti_allowance = None
        if self.renewal_terms.ti_allowance:
            ti_allowance = TenantImprovementAllowance(
                # Copy configuration from profile's renewal terms
                **self.renewal_terms.ti_allowance.model_dump(exclude={'timeline', 'reference'}),
                # Set appropriate timeline and area reference
                timeline=timeline,
                reference=original_lease.area
            )
        
        # Create new leasing commission if specified in renewal terms
        leasing_commission = None
        if self.renewal_terms.leasing_commission:
            # Calculate annual rent as basis for commission
            annual_rent = renewal_rate * original_lease.area
            
            leasing_commission = LeasingCommission(
                **self.renewal_terms.leasing_commission.model_dump(exclude={'timeline', 'value'}),
                timeline=timeline,
                value=annual_rent
            )
        
        # Create and return the renewal lease with all appropriate attributes
        return Lease(
            name=f"{original_lease.tenant.name} - {original_lease.suite} (Renewal)",
            tenant=tenant,
            suite=original_lease.suite,
            floor=original_lease.floor,
            use_type=original_lease.use_type,
            status=LeaseStatusEnum.SPECULATIVE,
            lease_type=original_lease.lease_type,
            area=original_lease.area,
            timeline=timeline,
            value=renewal_rate,
            unit_of_measure=UnitOfMeasureEnum.PSF,
            
            # Apply renewal terms (immutable objects can be referenced directly)
            rent_escalation=self.renewal_terms.rent_escalation,
            rent_abatement=self.renewal_terms.rent_abatement,
            recovery_method=self.renewal_terms.recovery_method,
            
            # Apply newly created instances with proper timeline/reference
            ti_allowance=ti_allowance,
            leasing_commission=leasing_commission,
            
            # Set rollover behavior for future projections
            upon_expiration=self.upon_expiration,
            rollover_profile=self
        )
    
    def create_market_lease(
        self, 
        suite: str, 
        suite_area: PositiveFloat,
        vacancy_start_date: date, 
        property_area: Optional[PositiveFloat] = None
    ) -> "Lease":
        """
        Create a new market lease for a vacant space.
        
        This method generates a speculative lease based on market assumptions
        for a space that is or will become vacant.
        
        Args:
            suite: Suite identifier for the vacant space
            suite_area: Area of the suite in square feet
            vacancy_start_date: Date when the space becomes vacant
            property_area: Total property area (optional, for percentage calculations)
            
        Returns:
            A new Lease object representing the market lease
        """
        # Calculate lease start date after expected downtime period
        lease_start = vacancy_start_date + relativedelta(months=self.downtime_months)
        
        # Create timeline for the market lease
        timeline = Timeline(
            start_date=lease_start,
            duration_months=self.term_months
        )
        
        # Determine market rent as of lease start date
        market_rate = self._calculate_market_rent(lease_start)
        
        # Create placeholder tenant for the speculative lease
        tenant = Tenant(
            id=f"speculative-{suite}-{lease_start}",
            name=f"Market Tenant ({suite})"
        )
        
        # Create TI allowance if specified in market terms
        ti_allowance = None
        if self.market_terms.ti_allowance:
            ti_allowance = TenantImprovementAllowance(
                **self.market_terms.ti_allowance.model_dump(exclude={'timeline', 'reference'}),
                timeline=timeline,
                reference=suite_area
            )
        
        # Create leasing commission if specified in market terms
        leasing_commission = None
        if self.market_terms.leasing_commission:
            annual_rent = market_rate * suite_area
            leasing_commission = LeasingCommission(
                **self.market_terms.leasing_commission.model_dump(exclude={'timeline', 'value'}),
                timeline=timeline,
                value=annual_rent
            )
        
        # Create and return the market lease with all appropriate attributes
        return Lease(
            name=f"Market Lease - {suite}",
            tenant=tenant,
            suite=suite,
            use_type=ProgramUseEnum.OFFICE,  # Default use type
            status=LeaseStatusEnum.SPECULATIVE,
            lease_type=LeaseTypeEnum.NET,  # Default lease type for market leases
            area=suite_area,
            timeline=timeline,
            value=market_rate,
            unit_of_measure=UnitOfMeasureEnum.PSF,
            
            # Apply market terms (immutable objects can be referenced directly)
            rent_escalation=self.market_terms.rent_escalation,
            rent_abatement=self.market_terms.rent_abatement,
            recovery_method=self.market_terms.recovery_method,
            
            # Apply newly created instances with proper timeline/reference
            ti_allowance=ti_allowance,
            leasing_commission=leasing_commission,
            
            # Set rollover behavior for future projections
            upon_expiration=self.upon_expiration,
            rollover_profile=self
        )
