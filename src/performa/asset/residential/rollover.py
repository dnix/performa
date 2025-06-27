from __future__ import annotations

import logging
from datetime import date
from typing import Optional
from uuid import UUID

from pydantic import Field, computed_field

from ...common.base import RolloverLeaseTermsBase, RolloverProfileBase
from ...common.capital import CapitalPlan
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
    - No TI/LC per square foot (use CapitalPlan for all costs)
    - No complex recovery methods (residents don't pay building expenses)
    - No rent escalations during term (typically flat rent)
    - Optional post-renovation rent premiums for value-add scenarios
    - Universal CapitalPlan primitive for all capital outlays
    """
    
    # === RENT TERMS ===
    market_rent: PositiveFloat  # Current market rent for this unit type
    market_rent_growth: Optional[GrowthRate] = None
    renewal_rent_increase_percent: PositiveFloat = 0.04  # 4% typical renewal increase
    
    # === CONCESSIONS ===
    concessions_months: PositiveInt = 0  # Free rent months
    
    # === UUID-BASED CAPITAL PLAN REFERENCE ===
    # REPLACES: turnover_plan field - now uses lightweight UUID reference
    capital_plan_id: Optional[UUID] = Field(
        default=None,
        description="UUID reference to CapitalPlan for turnover costs (make-ready, leasing, etc.)"
    )
    
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

    @classmethod
    def with_simple_turnover(
        cls,
        market_rent: float,
        make_ready_cost: float = 1500.0,
        leasing_fee: float = 500.0,
        duration_months: int = 1,
        **kwargs,
    ) -> "ResidentialRolloverLeaseTerms":
        """
        Convenience factory for creating lease terms with simple turnover costs.
        
        This method provides backward compatibility and ease of use for common scenarios
        where turnover costs are simple make-ready and leasing fees.
        
        Args:
            market_rent: Market rent for this unit type
            make_ready_cost: Unit preparation costs (painting, cleaning, repairs)
            leasing_fee: Leasing commission and marketing costs
            duration_months: Timeline for turnover work (default: 1 month)
            **kwargs: Additional fields for ResidentialRolloverLeaseTerms
            
        Returns:
            ResidentialRolloverLeaseTerms instance with CapitalPlan for turnover costs
            
        Example:
            terms = ResidentialRolloverLeaseTerms.with_simple_turnover(
                market_rent=2500.0,
                make_ready_cost=1200.0,
                leasing_fee=400.0,
                renewal_rent_increase_percent=0.035
            )
        """
        # Create CapitalPlan for turnover costs using concurrent pattern
        turnover_plan = None
        if make_ready_cost > 0 or leasing_fee > 0:
            costs = {}
            if make_ready_cost > 0:
                costs["Make-Ready"] = make_ready_cost
            if leasing_fee > 0:
                costs["Leasing Fee"] = leasing_fee
                
            turnover_plan = CapitalPlan.create_concurrent_renovation(
                name="Standard Unit Turnover",
                start_date=date(2000, 1, 1),  # Placeholder date - will be shifted by lease logic
                duration_months=duration_months,
                costs=costs,
                description=f"Turnover costs: Make-ready ${make_ready_cost:,.0f}, Leasing ${leasing_fee:,.0f}"
            )
        
        return cls(
            market_rent=market_rent,
            capital_plan_id=turnover_plan.uid if turnover_plan else None,
            **kwargs
        )


class ResidentialRolloverProfile(RolloverProfileBase):
    """
    Residential-specific profile for lease rollovers and renewals.
    
    STATE MACHINE ARCHITECTURE:
    Each profile represents a state a unit can be in (e.g., "Classic Unit", "Renovated Unit").
    The next_rollover_profile_id field enables declarative state transitions.
    
    Captures the typical multifamily leasing patterns:
    - Higher renewal probability than commercial (60-70% typical)
    - Shorter downtime (1-2 months vs. 3-6 for commercial)
    - Simplified cost structures
    - Declarative state transitions for value-add scenarios
    """
    
    # Residential-specific defaults
    renewal_probability: float = 0.60  # 60% renewal probability
    downtime_months: int = 1  # 1 month typical downtime
    term_months: PositiveInt = 12  # 12-month leases typical
    
    # Typed terms for residential
    market_terms: ResidentialRolloverLeaseTerms
    renewal_terms: ResidentialRolloverLeaseTerms
    option_terms: Optional[ResidentialRolloverLeaseTerms] = None
    
    # === STATE MACHINE TRANSITION ===
    next_rollover_profile_id: Optional[UUID] = Field(
        default=None,
        description="UUID of the rollover profile to use for the NEXT turnover (enables state transitions)"
    )

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
        
        # Blend turnover costs - use weighted selection approach
        blended_turnover = None
        if market_terms.capital_plan_id and renewal_terms.capital_plan_id:
            # For simplicity, use market terms plan when both exist (market rate turnovers typically more expensive)
            # Future enhancement: Could implement weighted blending of individual CapitalItems
            blended_turnover = market_terms.capital_plan_id
        elif market_terms.capital_plan_id:
            blended_turnover = market_terms.capital_plan_id
        elif renewal_terms.capital_plan_id:
            blended_turnover = renewal_terms.capital_plan_id

        # Blend term length - ensure we always have a valid term_months
        blended_term_months = self.term_months  # Use profile default as fallback
        
        if market_terms.term_months and renewal_terms.term_months:
            blended_term_months = round((renewal_terms.term_months * renewal_prob) + (market_terms.term_months * market_prob))
        elif market_terms.term_months:
            blended_term_months = market_terms.term_months
        elif renewal_terms.term_months:
            blended_term_months = renewal_terms.term_months
        
        # Final fallback to ensure we never return None
        if blended_term_months is None:
            blended_term_months = 12  # Standard residential lease term

        return ResidentialRolloverLeaseTerms(
            market_rent=blended_rent,
            unit_of_measure=market_terms.unit_of_measure,
            frequency=market_terms.frequency,
            market_rent_growth=blended_growth,
            renewal_rent_increase_percent=blended_renewal_increase,
            concessions_months=blended_concessions,
            capital_plan_id=blended_turnover,
            term_months=blended_term_months
        ) 