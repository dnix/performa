from datetime import date
from typing import Dict, Literal, Optional

from ..core._model import Model
from ..core._types import FloatBetween0And1, PositiveFloat
from ._enums import ProgramUseEnum
from ._types import SquareFootRange


class GrowthRate(Model):
    """Individual growth rate profile"""

    name: str
    type: Literal["general", "direct"]  # Use general rate vs direct entry
    base_rate: Optional[FloatBetween0And1] = None  # For general type
    yearly_rates: Dict[date, FloatBetween0And1]  # Year-specific rates


class GrowthRates(Model):
    """Collection of growth rate profiles"""

    general_growth: GrowthRate
    market_rent_growth: GrowthRate
    misc_income_growth: GrowthRate
    operating_expense_growth: GrowthRate
    leasing_costs_growth: GrowthRate
    capital_expense_growth: GrowthRate
    # TODO: consider arbitrary kinds of growth rates

    def get_rate(self, name: str, date: date) -> FloatBetween0And1:
        """Get growth rate for a specific profile and date"""
        profile = getattr(self, name)
        if profile.type == "general":
            return profile.base_rate or self.general_growth.yearly_rates[date]
        return profile.yearly_rates[date]

    @classmethod
    def with_default_rate(cls, default_rate: FloatBetween0And1 = 0.02) -> "GrowthRates":
        """Create growth rates initialized with default values.

        Args:
            default_rate: Default growth rate to use (defaults to 2%)

        Returns:
            GrowthRates instance with default values
        """
        # FIXME: is this the best way to do this?
        return cls(
            general_growth=GrowthRate(
                name="General", type="general", base_rate=default_rate, yearly_rates={}
            ),
            market_rent_growth=GrowthRate(
                name="Market Rent",
                type="general",
                base_rate=default_rate,
                yearly_rates={},
            ),
            misc_income_growth=GrowthRate(
                name="Misc Income",
                type="general",
                base_rate=default_rate,
                yearly_rates={},
            ),
            operating_expense_growth=GrowthRate(
                name="Operating Expenses",
                type="general",
                base_rate=default_rate,
                yearly_rates={},
            ),
            leasing_costs_growth=GrowthRate(
                name="Leasing Costs",
                type="general",
                base_rate=default_rate,
                yearly_rates={},
            ),
            capital_expense_growth=GrowthRate(
                name="Capital Expenses",
                type="general",
                base_rate=default_rate,
                yearly_rates={},
            ),
        )


class MarketProfile(Model):
    """
    Market leasing assumptions.

    This model maps directly to the Argus Enterprise Market Leasing inputs.
    
    Attributes:
        base_rent: The market base rent per square foot (e.g., $/sq ft/year).
        rent_growth_rate: The annual growth rate applied to market rent.
        lease_term_months: The typical lease term duration in months.
        free_rent_months: The number of months of free rent offered.
        ti_allowance: The tenant improvement (TI) allowance per square foot.
        leasing_commission: The leasing commission expressed as a percentage.
        renewal_probability: The likelihood of lease renewal.
        downtime_months: The expected downtime (in months) between leases.
        space_type: The asset use type for which these assumptions apply.
        size_range: An optional field to restrict the market profile to a given square footage range.
    """

    # Market Rents
    base_rent: PositiveFloat  # per sq ft
    rent_growth_rate: FloatBetween0And1

    # Typical Terms
    lease_term_months: int
    free_rent_months: int = 0

    # Leasing Costs
    ti_allowance: PositiveFloat  # per sq ft
    leasing_commission: FloatBetween0And1  # percent of rent

    # Turnover
    renewal_probability: FloatBetween0And1
    downtime_months: int

    # Applies To
    space_type: ProgramUseEnum
    size_range: Optional[SquareFootRange] = None  # sq ft range
