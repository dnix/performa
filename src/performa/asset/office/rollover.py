# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from datetime import date
from typing import Dict, List, Literal, Optional, Union

import pandas as pd

from ...core.base import RolloverLeaseTermsBase, RolloverProfileBase
from ...core.primitives import (
    FrequencyEnum,
    GlobalSettings,
    GrowthRate,
    Model,
    PositiveFloat,
)
from ...core.primitives.cash_flow import ReferenceKey
from .recovery import OfficeRecoveryMethod
from .rent_abatement import OfficeRentAbatement
from .rent_escalation import OfficeRentEscalation

logger = logging.getLogger(__name__)


class OfficeRolloverTenantImprovement(Model):
    """
    Configuration for tenant improvements in rollover scenarios.
    """
    value: PositiveFloat
    reference: Optional[ReferenceKey] = None
    payment_timing: Literal["signing", "commencement"] = "commencement"


class OfficeRolloverLeasingCommission(Model):
    """
    Configuration for leasing commissions in rollover scenarios.
    """
    tiers: List[float]  # Commission tiers as percentages


class OfficeRolloverLeaseTerms(RolloverLeaseTermsBase):
    """
    Office-specific lease terms for rollover scenarios.
    """
    market_rent: Optional[Union[float, pd.Series, Dict, List]] = None
    growth_rate: Optional[GrowthRate] = None
    
    # Multiple escalations support (new)
    rent_escalations: Optional[Union[OfficeRentEscalation, List[OfficeRentEscalation]]] = None
    
    rent_abatement: Optional[OfficeRentAbatement] = None
    recovery_method: Optional[OfficeRecoveryMethod] = None
    ti_allowance: Optional[OfficeRolloverTenantImprovement] = None
    leasing_commission: Optional[OfficeRolloverLeasingCommission] = None


class OfficeRolloverProfile(RolloverProfileBase):
    """
    Office-specific profile for lease rollovers and renewals.
    """
    market_terms: OfficeRolloverLeaseTerms
    renewal_terms: OfficeRolloverLeaseTerms
    option_terms: Optional[OfficeRolloverLeaseTerms] = None

    def _calculate_rent(
        self,
        terms: OfficeRolloverLeaseTerms,
        as_of_date: date,
        global_settings: Optional[GlobalSettings] = None,
    ) -> float:
        """
        Calculate the market rent as of a specific date, applying growth factors.
        """
        if terms.market_rent is None:
            raise ValueError("Market rent not defined in lease terms")

        if isinstance(terms.market_rent, (int, float)):
            base_market_rent = terms.market_rent
            if terms.frequency == FrequencyEnum.ANNUAL:
                base_market_rent /= 12

            if not terms.growth_rate:
                return base_market_rent

            growth_base_date = global_settings.analysis_start_date if global_settings else as_of_date
            if as_of_date < growth_base_date:
                return base_market_rent
            
            growth_periods = pd.period_range(start=growth_base_date, end=as_of_date, freq="M")
            growth_value = terms.growth_rate.value
            
            period_rates = pd.Series(0.0, index=growth_periods)

            if isinstance(growth_value, (float, int)):
                monthly_rate = float(growth_value) / 12.0
                period_rates[:] = monthly_rate
            elif isinstance(growth_value, pd.Series):
                aligned_rates = growth_value
                if not isinstance(aligned_rates.index, pd.PeriodIndex):
                    aligned_rates.index = pd.PeriodIndex(aligned_rates.index, freq="M")
                aligned_rates = aligned_rates.reindex(growth_periods, method="ffill").fillna(0.0)
                period_rates = aligned_rates
            elif isinstance(growth_value, dict):
                dict_series = pd.Series(growth_value)
                dict_series.index = pd.PeriodIndex(dict_series.index, freq="M")
                aligned_rates = dict_series.reindex(growth_periods, method="ffill").fillna(0.0)
                period_rates = aligned_rates
            else:
                raise TypeError(f"Unsupported type for GrowthRate value: {type(growth_value)}")

            growth_factors = 1.0 + period_rates
            cumulative_growth_factor = growth_factors.prod()
            return base_market_rent * cumulative_growth_factor
        
        elif isinstance(terms.market_rent, pd.Series):
            as_of_period = pd.Period(as_of_date, freq="M")
            if as_of_period in terms.market_rent.index:
                rent = terms.market_rent[as_of_period]
            else:
                earlier_periods = terms.market_rent.index[terms.market_rent.index < as_of_period]
                if len(earlier_periods) > 0:
                    latest_period = earlier_periods[-1]
                    rent = terms.market_rent[latest_period]
                else:
                    earliest_period = terms.market_rent.index[0]
                    rent = terms.market_rent[earliest_period]
            if terms.frequency == FrequencyEnum.ANNUAL:
                rent /= 12
            return rent
        
        elif isinstance(terms.market_rent, dict):
            temp_series = pd.Series(terms.market_rent)
            temp_terms = terms.model_copy(update={"market_rent": temp_series})
            return self._calculate_rent(temp_terms, as_of_date, global_settings)

        raise NotImplementedError(f"Unsupported market_rent type: {type(terms.market_rent)}")

    def blend_lease_terms(self) -> OfficeRolloverLeaseTerms:
        """
        Blend market and renewal terms based on renewal probability.
        """
        if self.renewal_probability == 0:
            return self.market_terms.model_copy(deep=True)
        if self.renewal_probability == 1:
            return self.renewal_terms.model_copy(deep=True)

        market_prob = 1 - self.renewal_probability
        renewal_prob = self.renewal_probability
        
        market_terms = self.market_terms
        renewal_terms = self.renewal_terms

        blended_rent = None
        if isinstance(market_terms.market_rent, (int, float)) and isinstance(renewal_terms.market_rent, (int, float)):
            blended_rent = (renewal_terms.market_rent * renewal_prob) + (market_terms.market_rent * market_prob)
        else:
            blended_rent = market_terms.market_rent

        blended_growth = None
        if market_terms.growth_rate and renewal_terms.growth_rate and isinstance(market_terms.growth_rate.value, (int, float)) and isinstance(renewal_terms.growth_rate.value, (int, float)):
            blended_rate_value = (renewal_terms.growth_rate.value * renewal_prob) + (market_terms.growth_rate.value * market_prob)
            blended_growth = GrowthRate(name="Blended Growth", value=blended_rate_value)
        else:
            blended_growth = market_terms.growth_rate

        blended_abatement = None
        if market_terms.rent_abatement and renewal_terms.rent_abatement:
            blended_months = round((renewal_terms.rent_abatement.months * renewal_prob) + (market_terms.rent_abatement.months * market_prob))
            blended_abatement = market_terms.rent_abatement.model_copy(update={'months': blended_months})
        elif renewal_prob > 0.5:
            blended_abatement = renewal_terms.rent_abatement
        else:
            blended_abatement = market_terms.rent_abatement

        # Handle escalations blending - use renewal terms if probability > 0.5, otherwise market terms
        blended_escalations = None
        if renewal_prob > 0.5:
            # Prefer renewal escalations
            blended_escalations = renewal_terms.rent_escalations
        else:
            # Prefer market escalations
            blended_escalations = market_terms.rent_escalations

        # Blend TI Allowance
        blended_ti = None
        market_ti_val = market_terms.ti_allowance.value if market_terms.ti_allowance and isinstance(market_terms.ti_allowance.value, (int, float)) else 0.0
        renewal_ti_val = renewal_terms.ti_allowance.value if renewal_terms.ti_allowance and isinstance(renewal_terms.ti_allowance.value, (int, float)) else 0.0
        
        if market_terms.ti_allowance or renewal_terms.ti_allowance:
            blended_ti_value = (renewal_ti_val * renewal_prob) + (market_ti_val * market_prob)
            # Use the market terms TI as a template, or renewal if market doesn't have one
            base_ti = market_terms.ti_allowance or renewal_terms.ti_allowance
            if blended_ti_value > 0 and base_ti:
                 blended_ti = base_ti.model_copy(update={'value': blended_ti_value})

        # Blend Leasing Commission
        blended_lc = None
        market_lc = market_terms.leasing_commission
        renewal_lc = renewal_terms.leasing_commission
        if market_lc or renewal_lc:
            # Simplified blend: use the one from the dominant probability
            if renewal_prob > market_prob:
                blended_lc = renewal_lc or market_lc
            else:
                blended_lc = market_lc or renewal_lc
        
        blended_recovery = renewal_terms.recovery_method if renewal_prob > 0.5 else market_terms.recovery_method
        
        blended_term_months = market_terms.term_months
        if renewal_terms.term_months and market_terms.term_months:
            blended_term_months = round((renewal_terms.term_months * renewal_prob) + (market_terms.term_months * market_prob))

        return OfficeRolloverLeaseTerms(
            market_rent=blended_rent,
            reference=market_terms.reference,
            frequency=market_terms.frequency,
            growth_rate=blended_growth,
            rent_escalations=blended_escalations,
            rent_abatement=blended_abatement,
            recovery_method=blended_recovery,
            ti_allowance=blended_ti,
            leasing_commission=blended_lc,
            term_months=blended_term_months
        )