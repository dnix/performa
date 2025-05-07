import logging
from datetime import date
from typing import TYPE_CHECKING, Dict, List, Optional, Union

import pandas as pd
from dateutil.relativedelta import relativedelta

from ..core._enums import FrequencyEnum, UnitOfMeasureEnum, UponExpirationEnum
from ..core._model import Model
from ..core._settings import GlobalSettings
from ..core._types import FloatBetween0And1, PositiveFloat, PositiveInt
from ._growth_rates import GrowthRate
from ._lc import (
    LeasingCommission,
)
from ._lease import RentAbatement, RentEscalation
from ._recovery import RecoveryMethod
from ._ti import TenantImprovementAllowance

if TYPE_CHECKING:
    pass # RentAbatement, RentEscalation are now top-level for model_rebuild

logger = logging.getLogger(__name__) # Initialize logger at module level

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
    unit_of_measure: UnitOfMeasureEnum = UnitOfMeasureEnum.PER_UNIT
    frequency: FrequencyEnum = FrequencyEnum.ANNUAL

    # Growth parameter
    growth_rate: Optional[GrowthRate] = None

    # Lease modification terms
    rent_escalation: Optional["RentEscalation"] = None
    rent_abatement: Optional["RentAbatement"] = None
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
    
    The profile supports different rollover methodologies common in real estate modeling:
    - RENEW: Force renewal with renewal terms (100% probability)
    - VACATE: Force vacancy followed by market lease (0% renewal)
    - MARKET: Probability-weighted blend of renewal and market scenarios
    - OPTION: Exercise option terms when available
    - REABSORB: Space remains vacant for custom reabsorption
    
    For MARKET methodology, the profile uses a blended terms approach where
    lease parameters are blended based on renewal probability, rather than
    blending resulting cash flows. This industry-standard approach provides
    more accurate modeling and better reflects real-world leasing dynamics.
    
    Attributes:
        name: Identifier for this rollover profile
        term_months: Standard lease term duration in months
        renewal_probability: Probability that a tenant will renew their lease
        downtime_months: Expected vacancy period between leases
        market_terms: Terms to apply for new market leases
        renewal_terms: Terms to apply if lease is renewed
        option_terms: Terms to apply if option is exercised
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

    def _calculate_rent(
        self, 
        terms: RolloverLeaseTerms, 
        as_of_date: date,
        global_settings: Optional[GlobalSettings] = None,
    ) -> PositiveFloat:
        """
        Calculate the market rent as of a specific date, applying growth factors.
        
        Args:
            terms: The lease terms containing market rent configuration
            as_of_date: The date to calculate market rent for
            global_settings: Optional global settings (e.g., for analysis start date as base).
            
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
                # --- Start Implementation --- 
                growth_profile = terms.growth_rate
                growth_value = growth_profile.value

                # Determine Growth Base Date
                growth_base_date: Optional[date] = None
                if global_settings and global_settings.analysis_start_date:
                    growth_base_date = global_settings.analysis_start_date
                else:
                    # Default to as_of_date if no context provided, implying no growth interval
                    growth_base_date = as_of_date 
                    logger.warning(
                        f"Cannot determine growth base date for RolloverProfile '{self.name}' "
                        f"(Terms: {terms.model_id}). Missing global_settings.analysis_start_date. "
                        f"Growth will effectively be 0% for date {as_of_date}."
                    )
                    
                # If as_of_date is before the base date, no growth applies
                if as_of_date < growth_base_date:
                    logger.debug(f"as_of_date {as_of_date} is before growth_base_date {growth_base_date}. No growth applied.")
                    return base_market_rent
                
                # Create period range for growth calculation
                try:
                    growth_periods = pd.period_range(start=growth_base_date, end=as_of_date, freq='M')
                except Exception as e:
                    logger.error(f"Error creating period range for growth calculation: {e}")
                    return base_market_rent # Cannot calculate growth

                # Prepare Period-Based Growth Rates over the relevant range
                period_rates = pd.Series(0.0, index=growth_periods) # Initialize with 0% growth

                if isinstance(growth_value, (float, int)):
                    # Constant annual rate - convert to monthly
                    monthly_rate = float(growth_value) / 12.0
                    # Apply only to periods within our range (already implicitly handled by index)
                    period_rates[:] = monthly_rate 
                elif isinstance(growth_value, pd.Series):
                    aligned_rates = growth_value
                    if not isinstance(aligned_rates.index, pd.PeriodIndex):
                        try:
                            aligned_rates.index = pd.PeriodIndex(aligned_rates.index, freq='M')
                        except Exception as e:
                            logger.error(f"Growth Series index cannot be converted to PeriodIndex: {e}")
                            return base_market_rent # Cannot apply growth
                    # Reindex to our specific growth period range and forward-fill
                    aligned_rates = aligned_rates.reindex(growth_periods, method='ffill')
                    aligned_rates = aligned_rates.fillna(0.0) # Fill initial NaNs
                    period_rates = aligned_rates
                elif isinstance(growth_value, dict):
                    try:
                        dict_series = pd.Series(growth_value)
                        dict_series.index = pd.PeriodIndex(dict_series.index, freq='M')
                    except Exception as e:
                        logger.error(f"Growth Dict keys cannot be converted to PeriodIndex: {e}")
                        return base_market_rent # Cannot apply growth
                    aligned_rates = dict_series.reindex(growth_periods, method='ffill')
                    aligned_rates = aligned_rates.fillna(0.0)
                    period_rates = aligned_rates
                else:
                    logger.error(f"Unsupported type for GrowthRate value: {type(growth_value)}")
                    return base_market_rent # Cannot apply growth
                
                # Calculate period-over-period growth factors (1 + monthly_rate)
                growth_factors = 1.0 + period_rates
                
                # Calculate cumulative factor up to the as_of_date
                # The cumulative product gives the factor to apply to the base value at the base date
                # to get the value at each subsequent date.
                cumulative_growth_factor = growth_factors.prod() 
                # Alternative using cumprod if we needed intermediate values: 
                # cumulative_factors = growth_factors.cumprod()
                # final_factor = cumulative_factors.iloc[-1] if not cumulative_factors.empty else 1.0
                
                # Apply the cumulative factor
                grown_rent = base_market_rent * cumulative_growth_factor
                logger.debug(f"Applied growth factor {cumulative_growth_factor:.4f} to base rent {base_market_rent:.2f} (Base Date: {growth_base_date}, As Of: {as_of_date})")
                return grown_rent
                # --- End Implementation --- 
            else:
                return base_market_rent
                
        elif isinstance(terms.market_rent, pd.Series):
            # If market rent is provided as a Series, assume these are the final 
            # values for specific periods and ignore the terms.growth_rate.
            # Growth should be baked into the Series values themselves if needed.
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
            # If market rent is provided as a Dict, assume these are the final
            # values for specific periods and ignore the terms.growth_rate.
            # Convert the dictionary to a Series and recursively call this method
            temp_series = pd.Series(terms.market_rent)
            # Create a copy of the terms with the Series
            temp_terms = terms.copy(update={"market_rent": temp_series})
            return self._calculate_rent(temp_terms, as_of_date, global_settings)
            
        elif isinstance(terms.market_rent, list):
            # We need context (timeline) to interpret a list, so this is not supported directly
            raise ValueError("List format for market_rent requires a timeline context. Use a Series or dictionary instead.")
            
        else:
            raise ValueError(f"Unsupported market_rent type: {type(terms.market_rent)}")
    
    def calculate_market_rent(
        self, 
        as_of_date: date,
        global_settings: Optional[GlobalSettings] = None,
    ) -> PositiveFloat:
        """
        Calculate the market rent for a new market lease.
        
        Args:
            as_of_date: The date to calculate market rent for
            global_settings: Optional global settings.
            
        Returns:
            The market rent value
        """
        return self._calculate_rent(self.market_terms, as_of_date, global_settings)
    
    def calculate_renewal_rent(
        self, 
        as_of_date: date,
        global_settings: Optional[GlobalSettings] = None,
    ) -> PositiveFloat:
        """
        Calculate the rent for a renewal lease.
        
        Args:
            as_of_date: The date to calculate renewal rent for
            global_settings: Optional global settings.
            
        Returns:
            The renewal rent value
        """
        return self._calculate_rent(self.renewal_terms, as_of_date, global_settings)

    def calculate_option_rent(
        self, 
        as_of_date: date,
        global_settings: Optional[GlobalSettings] = None,
    ) -> PositiveFloat:
        """
        Calculate the rent for an option lease.
        
        Args:
            as_of_date: The date to calculate option rent for
            global_settings: Optional global settings.
            
        Returns:
            The option rent value
        """
        return self._calculate_rent(self.option_terms, as_of_date, global_settings)

    def blend_lease_terms(self) -> RolloverLeaseTerms:
        """
        Blend market and renewal terms based on renewal probability.
        
        Creates a weighted average of lease terms for MARKET case scenarios.
        This produces a single blended set of terms rather than blending 
        the resultant cash flows, which is more efficient and accurate.
        
        Example:
            For a profile with:
            - Market Terms: $30.00 PSF, 3% annual growth, 2 months free rent at 100%
            - Renewal Terms: $28.00 PSF, 2% annual growth, 1 month free rent at 100%
            - Renewal Probability: 60%
            
            The blended results would be:
            - Rent: $28.80 PSF (28.00 x 0.6 + 30.00 x 0.4)
            - Growth Rate: 2.4% (2% x 0.6 + 3% x 0.4)
            - Free Rent: 1 month (rounded from 1.4 = 1 x 0.6 + 2 x 0.4)
            - TI Allowance: Values would be blended similarly
            
            For boolean properties like abatement.includes_recoveries, 
            the method uses the dominant scenario (renewal in this case).
            
            For complex objects like recovery_method that can't be directly 
            blended numerically, the method uses the term from the scenario
            with higher probability (renewal in this case).
        
        Returns:
            A new RolloverLeaseTerms object with blended values
        """
        # Skip blending if probability is 0 or 1
        if self.renewal_probability == 0:
            return self.market_terms
        elif self.renewal_probability == 1:
            return self.renewal_terms
            
        # Blend the market rent
        blended_market_rent = None
        if isinstance(self.market_terms.market_rent, (int, float)) and isinstance(self.renewal_terms.market_rent, (int, float)):
            # Simple weighted average for scalar values
            blended_market_rent = (
                self.renewal_terms.market_rent * self.renewal_probability +
                self.market_terms.market_rent * (1 - self.renewal_probability)
            )
        elif isinstance(self.market_terms.market_rent, pd.Series) and isinstance(self.renewal_terms.market_rent, pd.Series):
            # Align series and calculate weighted average
            renewal_reindexed = self.renewal_terms.market_rent.reindex(
                self.market_terms.market_rent.index.union(self.renewal_terms.market_rent.index)
            )
            market_reindexed = self.market_terms.market_rent.reindex(
                self.market_terms.market_rent.index.union(self.renewal_terms.market_rent.index)
            )
            
            # Fill NaN values with the last valid value
            renewal_reindexed = renewal_reindexed.fillna(method='ffill').fillna(method='bfill')
            market_reindexed = market_reindexed.fillna(method='ffill').fillna(method='bfill')
            
            # Calculate weighted average
            blended_market_rent = (
                renewal_reindexed * self.renewal_probability +
                market_reindexed * (1 - self.renewal_probability)
            )
        else:
            # Default to market terms if types don't match
            blended_market_rent = self.market_terms.market_rent
            
        # Blend the growth rate if both are defined
        blended_growth_rate = None
        if self.renewal_terms.growth_rate is not None and self.market_terms.growth_rate is not None:
            blended_growth_rate = (
                self.renewal_terms.growth_rate * self.renewal_probability +
                self.market_terms.growth_rate * (1 - self.renewal_probability)
            )
        else:
            # Use market terms if either is None
            blended_growth_rate = self.market_terms.growth_rate
            
        # Blend the rent escalation
        blended_rent_escalation = None
        if self.renewal_terms.rent_escalation and self.market_terms.rent_escalation:
            # Both terms have rent escalation, so blend their values
            if (self.renewal_terms.rent_escalation.type == self.market_terms.rent_escalation.type and
                self.renewal_terms.rent_escalation.unit_of_measure == self.market_terms.rent_escalation.unit_of_measure):
                # If types and units match, we can blend the amount
                blended_rent_escalation = self.market_terms.rent_escalation.model_copy(deep=True)
                blended_rent_escalation.amount = (
                    self.renewal_terms.rent_escalation.amount * self.renewal_probability +
                    self.market_terms.rent_escalation.amount * (1 - self.renewal_probability)
                )
            else:
                # If types don't match, use market terms weighted by probability
                # This is a simplification - in reality one might be completely ignored
                if self.renewal_probability > 0.5:
                    blended_rent_escalation = self.renewal_terms.rent_escalation
                else:
                    blended_rent_escalation = self.market_terms.rent_escalation
        elif self.renewal_terms.rent_escalation:
            # Only renewal terms have rent escalation
            # Weight its impact by renewal probability
            if self.renewal_probability > 0.5:
                blended_rent_escalation = self.renewal_terms.rent_escalation
        elif self.market_terms.rent_escalation:
            # Only market terms have rent escalation
            # Weight its impact by market probability
            if (1 - self.renewal_probability) > 0.5:
                blended_rent_escalation = self.market_terms.rent_escalation
        
        # Blend rent abatement
        blended_rent_abatement = None
        if self.renewal_terms.rent_abatement and self.market_terms.rent_abatement:
            # Both have abatement, blend the key numeric values
            blended_rent_abatement = self.market_terms.rent_abatement.model_copy(deep=True)
            # Blend months of free rent
            blended_rent_abatement.months = round(
                self.renewal_terms.rent_abatement.months * self.renewal_probability +
                self.market_terms.rent_abatement.months * (1 - self.renewal_probability)
            )
            # Blend abatement ratio
            blended_rent_abatement.abated_ratio = (
                self.renewal_terms.rent_abatement.abated_ratio * self.renewal_probability +
                self.market_terms.rent_abatement.abated_ratio * (1 - self.renewal_probability)
            )
            # For includes_recoveries, use whichever dominates
            blended_rent_abatement.includes_recoveries = (
                self.renewal_terms.rent_abatement.includes_recoveries 
                if self.renewal_probability > 0.5 
                else self.market_terms.rent_abatement.includes_recoveries
            )
        elif self.renewal_terms.rent_abatement:
            # Only renewal has abatement
            if self.renewal_probability > 0.5:
                blended_rent_abatement = self.renewal_terms.rent_abatement
        elif self.market_terms.rent_abatement:
            # Only market has abatement
            if (1 - self.renewal_probability) > 0.5:
                blended_rent_abatement = self.market_terms.rent_abatement
        
        # For recovery method, it's harder to blend directly due to complexity
        # Use the dominant scenario's recovery method
        blended_recovery_method = None
        if self.renewal_terms.recovery_method and self.market_terms.recovery_method:
            blended_recovery_method = (
                self.renewal_terms.recovery_method
                if self.renewal_probability > 0.5
                else self.market_terms.recovery_method
            )
        elif self.renewal_terms.recovery_method:
            if self.renewal_probability > 0.5:
                blended_recovery_method = self.renewal_terms.recovery_method
        elif self.market_terms.recovery_method:
            if (1 - self.renewal_probability) > 0.5:
                blended_recovery_method = self.market_terms.recovery_method
        
        # For TI and LC, weight the amounts if both are defined
        blended_ti = None
        if self.renewal_terms.ti_allowance and self.market_terms.ti_allowance:
            # Create a copy of market TI as the base
            blended_ti = self.market_terms.ti_allowance.model_copy(deep=True)
            
            # Blend the value if both are using the same unit of measure
            if (blended_ti.unit_of_measure == self.renewal_terms.ti_allowance.unit_of_measure and 
                isinstance(blended_ti.value, (int, float)) and 
                isinstance(self.renewal_terms.ti_allowance.value, (int, float))):
                
                blended_ti.value = (
                    self.renewal_terms.ti_allowance.value * self.renewal_probability +
                    self.market_terms.ti_allowance.value * (1 - self.renewal_probability)
                )
        elif self.renewal_terms.ti_allowance:
            if self.renewal_probability > 0.5:
                blended_ti = self.renewal_terms.ti_allowance
        elif self.market_terms.ti_allowance:
            if (1 - self.renewal_probability) > 0.5:
                blended_ti = self.market_terms.ti_allowance
        
        # Similar approach for leasing commission
        blended_lc = None
        if self.renewal_terms.leasing_commission and self.market_terms.leasing_commission:
            # Create a copy of market LC as the base
            blended_lc = self.market_terms.leasing_commission.model_copy(deep=True)
            
            # Blend the rates if structure is the same
            if hasattr(blended_lc, 'rate') and hasattr(self.renewal_terms.leasing_commission, 'rate'):
                if isinstance(blended_lc.rate, (int, float)) and isinstance(self.renewal_terms.leasing_commission.rate, (int, float)):
                    blended_lc.rate = (
                        self.renewal_terms.leasing_commission.rate * self.renewal_probability +
                        self.market_terms.leasing_commission.rate * (1 - self.renewal_probability)
                    )
        elif self.renewal_terms.leasing_commission:
            if self.renewal_probability > 0.5:
                blended_lc = self.renewal_terms.leasing_commission
        elif self.market_terms.leasing_commission:
            if (1 - self.renewal_probability) > 0.5:
                blended_lc = self.market_terms.leasing_commission
        
        # Create new blended terms
        return RolloverLeaseTerms(
            market_rent=blended_market_rent,
            frequency=self.market_terms.frequency,  # Use market frequency for consistency
            growth_rate=blended_growth_rate,
            rent_escalation=blended_rent_escalation,
            rent_abatement=blended_rent_abatement,
            recovery_method=blended_recovery_method,
            ti_allowance=blended_ti,
            leasing_commission=blended_lc
        )

    def calculate_lease_start_after_vacancy(self, vacancy_start_date: date) -> date:
        """
        Calculate the lease start date after downtime period.
        
        Args:
            vacancy_start_date: Date when space becomes vacant
            
        Returns:
            Date when new lease would start after downtime
        """
        return vacancy_start_date + relativedelta(months=self.downtime_months)

# Resolve forward references
RolloverLeaseTerms.model_rebuild()
RolloverProfile.model_rebuild()
