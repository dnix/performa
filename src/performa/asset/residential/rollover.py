from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from pydantic import Field, computed_field

from ...common.base import RolloverLeaseTermsBase, RolloverProfileBase
from ...common.primitives import (
    FrequencyEnum,
    GlobalSettings,
    GrowthRate,
    PositiveFloat,
    PositiveInt,
    UnitOfMeasureEnum,
)

logger = logging.getLogger(__name__)


class ResidentialRolloverLeaseTerms(RolloverLeaseTermsBase):
    """
    Simplified rollover lease terms for residential properties.
    
    Key Simplifications vs. Commercial:
    - No TI/LC per square foot (use fixed per-unit costs instead)
    - No complex recovery methods (residents don't pay building expenses)
    - No rent escalations during term (typically flat rent)
    - Optional post-renovation rent premiums for value-add scenarios
    """
    
    # === RENT TERMS ===
    market_rent: PositiveFloat  # Current market rent for this unit type
    market_rent_growth: Optional[GrowthRate] = None
    renewal_rent_increase_percent: PositiveFloat = 0.04  # 4% typical renewal increase
    
    # === CONCESSIONS ===
    concessions_months: PositiveInt = 0  # Free rent months
    
    # === TURNOVER COSTS (Per Unit) ===
    make_ready_cost_per_unit: PositiveFloat = 1500.0  # Unit preparation costs
    leasing_fee_per_unit: PositiveFloat = 500.0  # Leasing commission costs
    
    # === VALUE-ADD CAPABILITIES ===
    post_renovation_rent_premium: PositiveFloat = Field(
        default=0.0,
        description="Rent premium percentage (as decimal) to apply after renovation (e.g., 0.15 for 15% increase)"
    )
    post_renovation_market_rent: Optional[PositiveFloat] = Field(
        default=None,
        description="Absolute market rent override after renovation (takes precedence over percentage premium)"
    )
    
    # Override base class defaults for residential
    unit_of_measure: UnitOfMeasureEnum = UnitOfMeasureEnum.CURRENCY  # Monthly rent is currency
    frequency: FrequencyEnum = FrequencyEnum.MONTHLY  # Residential rent is monthly
    
    @computed_field
    @property
    def effective_market_rent(self) -> float:
        """
        Calculate the effective market rent accounting for renovations.
        
        Priority order:
        1. post_renovation_market_rent (absolute override)
        2. market_rent + post_renovation_rent_premium (percentage increase)
        3. market_rent (base case)
        """
        if self.post_renovation_market_rent is not None:
            return self.post_renovation_market_rent
        elif self.post_renovation_rent_premium > 0:
            return self.market_rent * (1 + self.post_renovation_rent_premium)
        else:
            return self.market_rent


class ResidentialRolloverProfile(RolloverProfileBase):
    """
    Residential-specific profile for lease rollovers and renewals.
    
    Captures the typical multifamily leasing patterns:
    - Higher renewal probability than commercial (60-70% typical)
    - Shorter downtime (1-2 months vs. 3-6 for commercial)
    - Simplified cost structures
    """
    
    # Residential-specific defaults
    renewal_probability: float = 0.60  # 60% renewal probability
    downtime_months: int = 1  # 1 month typical downtime
    term_months: PositiveInt = 12  # 12-month leases typical
    
    # Typed terms for residential
    market_terms: ResidentialRolloverLeaseTerms
    renewal_terms: ResidentialRolloverLeaseTerms
    option_terms: Optional[ResidentialRolloverLeaseTerms] = None

    def _calculate_rent(
        self,
        terms: ResidentialRolloverLeaseTerms,
        as_of_date: date,
        global_settings: Optional[GlobalSettings] = None,
    ) -> float:
        """
        Calculate the market rent as of a specific date for residential units.
        
        Residential rent calculation is simpler than commercial:
        - Usually a base monthly rent with growth applied
        - Renewal increases are percentage-based
        - No complex lease structures or recovery methods
        """
        if terms.market_rent is None:
            raise ValueError("Market rent not defined in residential lease terms")

        # For residential, market_rent should be monthly currency amount
        if isinstance(terms.market_rent, (int, float)):
            base_monthly_rent = terms.market_rent
            
            # Apply growth if specified and if we have a growth rate
            if terms.market_rent_growth and global_settings:
                growth_base_date = global_settings.analysis_start_date
                if as_of_date >= growth_base_date:
                    # Calculate growth from base date to as_of_date
                    import pandas as pd
                    growth_periods = pd.period_range(start=growth_base_date, end=as_of_date, freq="M")
                    
                    if len(growth_periods) > 0:
                        growth_value = terms.market_rent_growth.value
                        
                        if isinstance(growth_value, (float, int)):
                            # Simple compound growth
                            months_elapsed = len(growth_periods)
                            monthly_growth_rate = float(growth_value) / 12.0
                            growth_factor = (1.0 + monthly_growth_rate) ** months_elapsed
                            base_monthly_rent *= growth_factor
            
            return base_monthly_rent
        
        # TODO: Add support for Series and Dict rent schedules if needed
        raise NotImplementedError(f"Unsupported market_rent type for residential: {type(terms.market_rent)}")

    def blend_lease_terms(self) -> ResidentialRolloverLeaseTerms:
        """
        Blend market and renewal terms based on renewal probability.
        
        Residential blending is simpler than commercial since the terms
        are less complex (no complex TI/LC structures).
        """
        if self.renewal_probability == 0:
            return self.market_terms.model_copy(deep=True)
        if self.renewal_probability == 1:
            return self.renewal_terms.model_copy(deep=True)

        market_prob = 1 - self.renewal_probability
        renewal_prob = self.renewal_probability
        
        market_terms = self.market_terms
        renewal_terms = self.renewal_terms

        # Blend market rent
        blended_rent = None
        if isinstance(market_terms.market_rent, (int, float)) and isinstance(renewal_terms.market_rent, (int, float)):
            blended_rent = (renewal_terms.market_rent * renewal_prob) + (market_terms.market_rent * market_prob)
        else:
            blended_rent = market_terms.market_rent

        # Blend growth rates
        blended_growth = None
        if (market_terms.market_rent_growth and renewal_terms.market_rent_growth and 
            isinstance(market_terms.market_rent_growth.value, (int, float)) and 
            isinstance(renewal_terms.market_rent_growth.value, (int, float))):
            blended_rate_value = (renewal_terms.market_rent_growth.value * renewal_prob) + (market_terms.market_rent_growth.value * market_prob)
            blended_growth = GrowthRate(name="Blended Growth", value=blended_rate_value)
        else:
            blended_growth = market_terms.market_rent_growth or renewal_terms.market_rent_growth

        # Blend renewal increase percentage
        blended_renewal_increase = (renewal_terms.renewal_rent_increase_percent * renewal_prob) + (market_terms.renewal_rent_increase_percent * market_prob)
        
        # Blend concessions (round to whole months)
        blended_concessions = round((renewal_terms.concessions_months * renewal_prob) + (market_terms.concessions_months * market_prob))
        
        # Blend turnover costs
        blended_make_ready = (renewal_terms.make_ready_cost_per_unit * renewal_prob) + (market_terms.make_ready_cost_per_unit * market_prob)
        blended_leasing_fee = (renewal_terms.leasing_fee_per_unit * renewal_prob) + (market_terms.leasing_fee_per_unit * market_prob)
        
        # Blend term length
        blended_term_months = market_terms.term_months
        if renewal_terms.term_months and market_terms.term_months:
            blended_term_months = round((renewal_terms.term_months * renewal_prob) + (market_terms.term_months * market_prob))

        return ResidentialRolloverLeaseTerms(
            market_rent=blended_rent,
            unit_of_measure=market_terms.unit_of_measure,
            frequency=market_terms.frequency,
            market_rent_growth=blended_growth,
            renewal_rent_increase_percent=blended_renewal_increase,
            concessions_months=blended_concessions,
            make_ready_cost_per_unit=blended_make_ready,
            leasing_fee_per_unit=blended_leasing_fee,
            term_months=blended_term_months
        ) 