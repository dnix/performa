# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import pandas as pd

from performa.core.base import RolloverLeaseTermsBase, RolloverProfileBase
from performa.core.primitives import (
    FrequencyEnum,
    GlobalSettings,
    PercentageGrowthRate,
)

logger = logging.getLogger(__name__)


class CommercialRolloverLeaseTermsBase(RolloverLeaseTermsBase):
    pass  # For now, this is a placeholder


class CommercialRolloverProfileBase(RolloverProfileBase):
    """
    Base class for commercial rollover profiles.
    Future logic for blending terms and calculating market rents will go here.
    """

    market_terms: CommercialRolloverLeaseTermsBase
    renewal_terms: CommercialRolloverLeaseTermsBase
    option_terms: Optional[CommercialRolloverLeaseTermsBase] = None

    def _calculate_rent(
        self,
        terms: CommercialRolloverLeaseTermsBase,
        as_of_date: date,
        global_settings: Optional[GlobalSettings] = None,
    ) -> float:
        if terms.market_rent is None:
            raise ValueError("Market rent not defined in lease terms")

        if isinstance(terms.market_rent, (int, float)):
            base_market_rent = terms.market_rent
            if terms.frequency == FrequencyEnum.ANNUAL:
                base_market_rent /= 12

            if not terms.growth_rate:
                return base_market_rent

            growth_base_date = (
                global_settings.analysis_start_date if global_settings else as_of_date
            )
            if as_of_date < growth_base_date:
                return base_market_rent

            growth_periods = pd.period_range(
                start=growth_base_date, end=as_of_date, freq="M"
            )
            growth_value = terms.growth_rate.value

            period_rates = pd.Series(0.0, index=growth_periods)

            if isinstance(growth_value, (float, int)):
                monthly_rate = float(growth_value) / 12.0
                period_rates[:] = monthly_rate
            elif isinstance(growth_value, pd.Series):
                aligned_rates = growth_value.reindex(
                    growth_periods, method="ffill"
                ).fillna(0.0)
                period_rates = aligned_rates

            cumulative_growth_factor = (1.0 + period_rates).prod()
            return base_market_rent * cumulative_growth_factor

        elif isinstance(terms.market_rent, pd.Series):
            as_of_period = pd.Period(as_of_date, freq="M")
            if as_of_period in terms.market_rent.index:
                rent = terms.market_rent[as_of_period]
            else:
                earlier_periods = terms.market_rent.index[
                    terms.market_rent.index < as_of_period
                ]
                rent = (
                    terms.market_rent[earlier_periods[-1]]
                    if len(earlier_periods) > 0
                    else terms.market_rent.iloc[0]
                )

            if terms.frequency == FrequencyEnum.ANNUAL:
                rent /= 12
            return rent

        # TODO: Add support for additional market rent types beyond int/float/Series/Dict
        # Currently supported: int, float (with growth rate), pd.Series, dict (converted to Series)
        # Future enhancement: Complex rent structures, dynamic pricing models, market-based adjustments
        raise NotImplementedError(
            f"Market rent type {type(terms.market_rent)} not yet supported for commercial rollover. "
            f"Currently supported: int, float, pd.Series, dict."
        )

    def blend_lease_terms(self) -> CommercialRolloverLeaseTermsBase:
        if self.renewal_probability == 0:
            return self.market_terms
        if self.renewal_probability == 1:
            return self.renewal_terms

        market_prob = 1 - self.renewal_probability

        blended_market_rent = (
            self.renewal_terms.market_rent * self.renewal_probability
        ) + (self.market_terms.market_rent * market_prob)

        blended_growth = None
        if self.renewal_terms.growth_rate and self.market_terms.growth_rate:
            blended_rate_value = (
                self.renewal_terms.growth_rate.value * self.renewal_probability
            ) + (self.market_terms.growth_rate.value * market_prob)
            blended_growth = PercentageGrowthRate(
                name="Blended Growth", value=blended_rate_value
            )

        # Simplified blending for other terms for now
        blended_abatement = (
            self.renewal_terms.rent_abatement
            if self.renewal_probability > 0.5
            else self.market_terms.rent_abatement
        )
        blended_ti = (
            self.renewal_terms.ti_allowance
            if self.renewal_probability > 0.5
            else self.market_terms.ti_allowance
        )
        blended_lc = (
            self.renewal_terms.leasing_commission
            if self.renewal_probability > 0.5
            else self.market_terms.leasing_commission
        )

        return CommercialRolloverLeaseTermsBase(
            market_rent=blended_market_rent,
            growth_rate=blended_growth,
            rent_abatement=blended_abatement,
            ti_allowance=blended_ti,
            leasing_commission=blended_lc,
        )
