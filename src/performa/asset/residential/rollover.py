# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, Optional

import pandas as pd
from pydantic import Field

from ...core.base import RolloverLeaseTermsBase, RolloverProfileBase
from ...core.primitives import (
    FrequencyEnum,
    GlobalSettings,
    PercentageGrowthRate,
    PositiveFloat,
    PositiveInt,
)

logger = logging.getLogger(__name__)


class ResidentialRolloverLeaseTerms(RolloverLeaseTermsBase):
    """
    Simplified rollover lease terms for residential properties.

    Key Simplifications vs. Commercial:
    - No TI/LC per square foot (use CapitalPlan for all costs)
    - No complex recovery methods (residents don't pay building expenses)
    - No rent escalations during term (typically flat rent)
    - Universal CapitalPlan primitive for all capital outlays
    """

    # === RENT TERMS ===
    market_rent: PositiveFloat  # Current market rent for this unit type
    market_rent_growth: Optional[PercentageGrowthRate] = None
    renewal_rent_increase_percent: PositiveFloat = 0.04  # 4% typical renewal increase

    # === CONCESSIONS ===
    concessions_months: PositiveInt = 0  # Free rent months

    # Override base class defaults for residential rent
    frequency: FrequencyEnum = FrequencyEnum.MONTHLY  # Residential rent is monthly


class ResidentialRolloverProfile(RolloverProfileBase):
    """
    Residential-specific profile for lease rollovers and renewals.

    ROLLOVER MODELING:
    Each profile represents a complete set of assumptions for a unit type.
    State transitions are modeled through development scenarios using blueprints and absorption plans.

    Captures the typical multifamily leasing patterns:
    - Higher renewal probability than commercial (60-70% typical)
    - Shorter downtime (1-2 months vs. 3-6 for commercial)
    - Simplified cost structures

    TODO: FUTURE ENHANCEMENT - ROLLOVER CHAIN OVERRIDES:
    The optional override_config field provides a future extension point for:
    - Time-based assumption schedules (e.g., declining renewal rates as building ages)
    - Property-type specific behaviors (student housing, senior housing, etc.)
    - Scenario-based modeling (economic cycles, market stress tests)
    - Stochastic analysis integration (Monte Carlo, unit-level variability)
    - Manual rollover chain specification for special cases
    """

    # Residential-specific defaults
    renewal_probability: float = 0.60  # 60% renewal probability
    downtime_months: int = 1  # 1 month typical downtime
    term_months: PositiveInt = 12  # 12-month leases typical

    # Typed terms for residential
    market_terms: ResidentialRolloverLeaseTerms
    renewal_terms: ResidentialRolloverLeaseTerms

    # TODO: Future enhancement - Rollover chain override capabilities
    # This field will enable:
    # - Time-based assumption evolution (renewal rates declining with building age)
    # - Property-type specialization (student housing, senior housing behaviors)
    # - Scenario-based overrides (economic cycles, stress testing)
    # - Unit-level variability for Monte Carlo analysis
    # - Manual rollover chain specification for complex modeling scenarios
    override_config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional configuration for overriding default rollover behavior",
    )
    option_terms: Optional[ResidentialRolloverLeaseTerms] = None

    # === STATE TRANSITIONS ===
    # Note: State transitions can be modeled through development scenarios
    # using ResidentialDevelopmentBlueprint + ResidentialAbsorptionPlan

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
                    growth_periods = pd.period_range(
                        start=growth_base_date, end=as_of_date, freq="M"
                    )

                    if len(growth_periods) > 0:
                        growth_value = terms.market_rent_growth.value

                        if isinstance(growth_value, (float, int)):
                            # Simple compound growth
                            months_elapsed = len(growth_periods)
                            monthly_growth_rate = float(growth_value) / 12.0
                            growth_factor = (
                                1.0 + monthly_growth_rate
                            ) ** months_elapsed
                            base_monthly_rent *= growth_factor

            return base_monthly_rent

        # TODO: Add support for Series and Dict rent schedules if needed
        # Currently supported: int, float (with growth rate application)
        # Future enhancement: pd.Series rent schedules, Dict-based rent structures, complex growth patterns
        raise NotImplementedError(
            f"Market rent type {type(terms.market_rent)} not yet supported for residential rollover. "
            f"Currently supported: int, float with growth rates."
        )

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
        if isinstance(market_terms.market_rent, (int, float)) and isinstance(
            renewal_terms.market_rent, (int, float)
        ):
            blended_rent = (renewal_terms.market_rent * renewal_prob) + (
                market_terms.market_rent * market_prob
            )
        else:
            blended_rent = market_terms.market_rent

        # Blend growth rates
        blended_growth = None
        if (
            market_terms.market_rent_growth
            and renewal_terms.market_rent_growth
            and isinstance(market_terms.market_rent_growth.value, (int, float))
            and isinstance(renewal_terms.market_rent_growth.value, (int, float))
        ):
            blended_rate_value = (
                renewal_terms.market_rent_growth.value * renewal_prob
            ) + (market_terms.market_rent_growth.value * market_prob)
            blended_growth = PercentageGrowthRate(
                name="Blended Growth", value=blended_rate_value
            )
        else:
            blended_growth = (
                market_terms.market_rent_growth or renewal_terms.market_rent_growth
            )

        # Blend renewal increase percentage
        blended_renewal_increase = (
            renewal_terms.renewal_rent_increase_percent * renewal_prob
        ) + (market_terms.renewal_rent_increase_percent * market_prob)

        # Blend concessions (round to whole months)
        blended_concessions = round(
            (renewal_terms.concessions_months * renewal_prob)
            + (market_terms.concessions_months * market_prob)
        )

        # Blend term length - ensure we always have a valid term_months
        blended_term_months = self.term_months  # Use profile default as fallback

        if market_terms.term_months and renewal_terms.term_months:
            blended_term_months = round(
                (renewal_terms.term_months * renewal_prob)
                + (market_terms.term_months * market_prob)
            )
        elif market_terms.term_months:
            blended_term_months = market_terms.term_months
        elif renewal_terms.term_months:
            blended_term_months = renewal_terms.term_months

        # Final fallback to ensure we never return None
        if blended_term_months is None:
            blended_term_months = 12  # Standard residential lease term

        return ResidentialRolloverLeaseTerms(
            market_rent=blended_rent,
            reference=market_terms.reference,
            frequency=market_terms.frequency,
            market_rent_growth=blended_growth,
            renewal_rent_increase_percent=blended_renewal_increase,
            concessions_months=blended_concessions,
            term_months=blended_term_months,
        )
