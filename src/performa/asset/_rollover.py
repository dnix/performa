from datetime import date
from typing import Dict, List, Optional, Union

import pandas as pd

from ..core._enums import FrequencyEnum, UnitOfMeasureEnum, UponExpirationEnum
from ..core._model import Model
from ..core._types import FloatBetween0And1, PositiveFloat, PositiveInt
from ._lc import (
    LeasingCommission,
)
from ._recovery import RecoveryMethod
from ._revenue import (
    RentAbatement,
    RentEscalation,
)
from ._ti import TenantImprovementAllowance


class RolloverLeaseTerms(Model):
    """
    Base class for lease terms applied in different scenarios.
    
    Contains common fields needed for any lease creation scenario, whether
    market lease or renewal. Models market rent with the same flexibility as
    CashFlowModel to enable easy translation into Lease instances.
    
    Attributes:
        rent_escalation: Rent increase structure for the lease term
        rent_abatement: Free rent periods applied to this lease
        recovery_method: Method for calculating expense recoveries
        ti_allowance: Tenant improvement allowance configuration
        leasing_commission: Leasing commission structure
        market_rent: Market rent value (can be a single value, series, or reference)
        unit_of_measure: Units for market rent (PSF, amount, etc.)
        frequency: Frequency of the market rent (monthly, annual)
        growth_rate: Annual growth rate for market rent
    """
    # Market rent (paralleling CashFlowModel for flexibility)
    market_rent: Optional[Union[PositiveFloat, pd.Series, Dict, List]] = None
    unit_of_measure: UnitOfMeasureEnum = UnitOfMeasureEnum.PSF
    frequency: FrequencyEnum = FrequencyEnum.ANNUAL

    # Growth parameter
    growth_rate: Optional[FloatBetween0And1] = None  # TODO: support GrowthRates

    # Lease modification terms
    rent_escalation: Optional[RentEscalation] = None
    rent_abatement: Optional[RentAbatement] = None
    recovery_method: Optional[RecoveryMethod] = None
    
    # Lease costs
    ti_allowance: Optional[TenantImprovementAllowance] = None
    leasing_commission: Optional[LeasingCommission] = None
    
    @property
    def has_free_rent(self) -> bool:
        """
        Check if these terms include free rent.
        
        Returns:
            Boolean indicating whether rent abatement is specified
        """
        return self.rent_abatement is not None
    
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
    
    @property
    def market_rent_psf(self) -> Optional[PositiveFloat]:
        """
        Get the market rent as a PSF value, for backwards compatibility.
        If market_rent is a Series, dict, or list, returns None.
        
        Returns:
            Market rent per square foot, if available as a single value
        """
        if isinstance(self.market_rent, (int, float)):
            if self.unit_of_measure == UnitOfMeasureEnum.PSF:
                return self.market_rent
            # TODO: Consider conversion logic if needed
        return None


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
    """
    name: str

    # Market assumptions
    term_months: PositiveInt
    renewal_probability: FloatBetween0And1
    downtime_months: int  # months between vacancy and lease start
    
    # Lease terms for different scenarios
    market_terms: RolloverLeaseTerms
    renewal_terms: RolloverLeaseTerms
    option_terms: RolloverLeaseTerms  # TODO: implement option terms just like renewal terms (with 100% probability)
    
    # Rollover behavior
    upon_expiration: UponExpirationEnum = UponExpirationEnum.MARKET
    next_profile: Optional[str] = None  # Name of next profile to use if chaining

    # Projection limits
    max_projection_years: int = 99  # NOTE: do we need this?
    
    def _calculate_market_rent(self, terms: RolloverLeaseTerms, as_of_date: date) -> PositiveFloat:
        """
        Calculate the market rent as of a specific date, applying growth factors.
        
        Args:
            terms: The lease terms containing market rent configuration
            as_of_date: The date to calculate market rent for
            
        Returns:
            The market rent per square foot as of the given date
            
        Raises:
            ValueError: If market rent is not defined in the terms
        """
        if terms.market_rent is None:
            raise ValueError("Market rent not defined in lease terms")
            
        # Handle different market rent types
        if isinstance(terms.market_rent, (int, float)):
            base_market_rent = terms.market_rent
            
            # Convert from annual to monthly if needed
            if terms.frequency == FrequencyEnum.ANNUAL:
                base_market_rent = base_market_rent / 12
            
            # Apply growth rate if specified
            if terms.growth_rate:
                # Calculate years from today to as_of_date
                today = date.today()
                years_difference = (as_of_date.year - today.year) + (as_of_date.month - today.month) / 12
                
                # Apply growth compounding
                market_rent = base_market_rent * (1 + terms.growth_rate) ** years_difference
                return market_rent
            else:
                return base_market_rent
                
        elif isinstance(terms.market_rent, pd.Series):
            # If market rent is a series, look up the value at the given date
            as_of_period = pd.Period(as_of_date, freq="M")
            
            # Try to find the exact period or the most recent previous period
            if as_of_period in terms.market_rent.index:
                rent = terms.market_rent[as_of_period]
            else:
                # Find the most recent period before as_of_period
                earlier_periods = terms.market_rent.index[terms.market_rent.index < as_of_period]
                if len(earlier_periods) > 0:
                    latest_period = earlier_periods[-1]
                    rent = terms.market_rent[latest_period]
                else:
                    # No earlier periods, use the earliest available
                    earliest_period = terms.market_rent.index[0]
                    rent = terms.market_rent[earliest_period]
            
            # Convert from annual to monthly if needed
            if terms.frequency == FrequencyEnum.ANNUAL:
                rent = rent / 12
                
            return rent
            
        elif isinstance(terms.market_rent, dict):
            # Convert the dictionary to a Series and recursively call this method
            temp_series = pd.Series(terms.market_rent)
            # Create a copy of the terms with the Series
            temp_terms = terms.model_copy(update={"market_rent": temp_series})
            return self._calculate_market_rent(temp_terms, as_of_date)
            
        elif isinstance(terms.market_rent, list):
            # We need context (timeline) to interpret a list, so this is not supported directly
            raise ValueError("List format for market_rent requires a timeline context. Use a Series or dictionary instead.")
            
        else:
            raise ValueError(f"Unsupported market_rent type: {type(terms.market_rent)}")
    
    def calculate_market_rent(self, as_of_date: date) -> PositiveFloat:
        """
        Calculate the market rent for a new market lease.
        
        Args:
            as_of_date: The date to calculate market rent for
            
        Returns:
            The market rent value
        """
        return self._calculate_market_rent(self.market_terms, as_of_date)
    
    def calculate_renewal_rent(self, as_of_date: date) -> PositiveFloat:
        """
        Calculate the rent for a renewal lease.
        
        Args:
            as_of_date: The date to calculate renewal rent for
            
        Returns:
            The renewal rent value
        """
        return self._calculate_market_rent(self.renewal_terms, as_of_date)

    def calculate_option_rent(self, as_of_date: date) -> PositiveFloat:
        """
        Calculate the rent for an option lease.
        
        Args:
            as_of_date: The date to calculate option rent for
            
        Returns:
            The option rent value
        """
        return self._calculate_market_rent(self.option_terms, as_of_date)
