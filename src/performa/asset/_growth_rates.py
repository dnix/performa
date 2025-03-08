from datetime import date
from typing import Dict, Literal, Optional

from ..core._model import Model
from ..core._types import FloatBetween0And1


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
