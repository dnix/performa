from datetime import date
from typing import Dict, List, Optional, Union

import pandas as pd
from pydantic import field_validator

from ..core._model import Model
from ..core._types import FloatBetween0And1


class GrowthRate(Model):
    """
    Individual growth rate profile with flexible value representation
    
    Attributes:
        name: Name of the growth rate (e.g., "Market Rent Growth")
        value: The growth rate value(s), which can be:
            - A single float value (constant rate)
            - A pandas Series (time-based rates)
            - A dictionary with date keys and rate values
            - A list of rate values (corresponding to timeline periods)
    """
    name: str
    value: Union[FloatBetween0And1, pd.Series, Dict[date, FloatBetween0And1], List[FloatBetween0And1]]
    
    @field_validator("value")
    @classmethod
    def validate_value(
        cls, 
        v: Union[FloatBetween0And1, pd.Series, Dict, List],
    ) -> Union[FloatBetween0And1, pd.Series, Dict, List]:
        """Validate that value has the correct format and constraints"""
        if isinstance(v, dict):
            # Ensure all dict values are between 0 and 1
            for key, rate in v.items():
                if not isinstance(rate, (int, float)) or not (0 <= rate <= 1):
                    raise ValueError(f"Growth rate for {key} must be between 0 and 1, got {rate}")
        elif isinstance(v, list):
            # Ensure all list values are between 0 and 1
            for i, rate in enumerate(v):
                if not isinstance(rate, (int, float)) or not (0 <= rate <= 1):
                    raise ValueError(f"Growth rate at index {i} must be between 0 and 1, got {rate}")
        elif isinstance(v, pd.Series):
            # Ensure all series values are between 0 and 1
            if (v < 0).any() or (v > 1).any():
                raise ValueError("Growth rates in Series must be between 0 and 1")
                
        return v


class GrowthRates(Model):
    """Collection of growth rate profiles for different aspects of an asset"""

    default_rate: Optional[FloatBetween0And1] = None
    general_growth: GrowthRate
    market_rent_growth: GrowthRate
    misc_income_growth: GrowthRate
    operating_expense_growth: GrowthRate
    leasing_costs_growth: GrowthRate
    capital_expense_growth: GrowthRate

    def get_rate(self, name: str, date: date) -> FloatBetween0And1:
        """
        Get growth rate for a specific profile and date
        
        Args:
            name: Name of the growth rate profile (e.g., "market_rent_growth")
            date: The date to get the rate for
            
        Returns:
            The growth rate value for the specified profile and date
        """
        profile = getattr(self, name)
        
        if isinstance(profile.value, (int, float)):
            return profile.value
        elif isinstance(profile.value, pd.Series):
            # Try to find the closest date in the series
            try:
                period = pd.Period(date, freq="M")
                if period in profile.value.index:
                    return profile.value[period]
                # Fall back to the default rate if date not found
                return self.default_rate or 0.0
            except Exception:
                return self.default_rate or 0.0
        elif isinstance(profile.value, dict):
            # Try to get the exact date, or fall back to default
            return profile.value.get(date, self.default_rate or 0.0)
        elif isinstance(profile.value, list):
            # Without context of which position in the list corresponds to which date,
            # we can't reliably get a rate for a specific date from a list.
            # This would require additional context like a timeline.
            # Fall back to default rate
            return self.default_rate or 0.0
        
        # Fallback
        return self.default_rate or 0.0

    @classmethod
    def with_default_rate(cls, default_rate: FloatBetween0And1 = 0.02) -> "GrowthRates":
        """
        Create growth rates initialized with default values.

        Args:
            default_rate: Default growth rate to use (defaults to 2%)

        Returns:
            GrowthRates instance with default values
        """
        return cls(
            default_rate=default_rate,
            general_growth=GrowthRate(
                name="General", 
                value=default_rate
            ),
            market_rent_growth=GrowthRate(
                name="Market Rent",
                value=default_rate
            ),
            misc_income_growth=GrowthRate(
                name="Misc Income",
                value=default_rate
            ),
            operating_expense_growth=GrowthRate(
                name="Operating Expenses",
                value=default_rate
            ),
            leasing_costs_growth=GrowthRate(
                name="Leasing Costs",
                value=default_rate
            ),
            capital_expense_growth=GrowthRate(
                name="Capital Expenses",
                value=default_rate
            ),
        )

    @classmethod
    def create_dynamic(cls, extra_rates: Optional[Dict[str, GrowthRate]] = None, **static_fields) -> "GrowthRates":
        """
        Create a dynamic GrowthRates instance supporting arbitrary growth rate fields.
        
        This method leverages pydantic's create_model to extend the existing GrowthRates model
        with extra fields provided in extra_rates. The resulting model supports dot notation access
        for both the predefined static rates and any additional dynamic rates.
        
        Args:
            extra_rates: A dictionary where each key is the name of an extra growth rate and 
                         the value is a GrowthRate instance.
            static_fields: Keyword arguments for setting/overriding the static GrowthRates fields.
        
        Returns:
            An instance of a dynamically generated GrowthRates model with the extra fields included.
        """
        from pydantic import create_model
        extra_rates = extra_rates or {}
        DynamicGrowthRates = create_model(
            "DynamicGrowthRates",
            __base__=cls,
            **{name: (GrowthRate, rate) for name, rate in extra_rates.items()}
        )
        data = {**static_fields, **extra_rates}
        return DynamicGrowthRates.parse_obj(data)
