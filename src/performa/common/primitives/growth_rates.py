from __future__ import annotations

from datetime import date
from typing import Dict, Optional, Union

import pandas as pd
from pydantic import field_validator

from .model import Model
from .types import FloatBetween0And1


class GrowthRate(Model):
    """
    Individual growth rate profile with flexible value representation

    Attributes:
        name: Name of the growth rate (e.g., "Market Rent Growth")
        value: The growth rate value(s), which can be:
            - A single float value (constant **annual** rate, e.g., 0.02 for 2%)
            - A pandas Series (time-based rates). The rates are assumed to be at the
              frequency implied by the Series index (e.g., provide monthly rates if the index
              is monthly). Index should be convertible to `pd.PeriodIndex`.
            - A dictionary with date keys and rate values. Rates are assumed to be
              effective for the period containing the date key (typically monthly).
              Keys should be convertible to `pd.PeriodIndex`.
    """

    name: str
    value: Union[FloatBetween0And1, pd.Series, Dict[date, FloatBetween0And1]]

    @field_validator("value")
    @classmethod
    def validate_value(
        cls,
        v: Union[FloatBetween0And1, pd.Series, Dict],
    ) -> Union[FloatBetween0And1, pd.Series, Dict]:
        """Validate that value has the correct format and constraints"""
        if isinstance(v, dict):
            # Ensure all dict values are between 0 and 1
            for key, rate in v.items():
                if not isinstance(key, date):
                    raise ValueError(
                        f"Growth rate dictionary keys must be dates, got {type(key)}"
                    )
                if not isinstance(rate, (int, float)) or not (0 <= rate <= 1):
                    raise ValueError(
                        f"Growth rate for {key} must be between 0 and 1, got {rate}"
                    )
        elif isinstance(v, pd.Series):
            # Ensure all series values are between 0 and 1
            if not pd.api.types.is_numeric_dtype(v.dtype):
                raise ValueError("Growth rate Series must have numeric values")
            if (v < 0).any() or (v > 1).any():
                raise ValueError("Growth rates in Series must be between 0 and 1")
        elif not isinstance(v, (int, float)):
            raise TypeError(f"Unsupported type for GrowthRate value: {type(v)}")

        return v


class GrowthRatesBase(Model):
    """Base collection of growth rate profiles for different aspects of an asset"""

    default_rate: Optional[FloatBetween0And1] = None
    general_growth: GrowthRate
    market_rent_growth: GrowthRate
    misc_income_growth: GrowthRate
    operating_expense_growth: GrowthRate
    leasing_costs_growth: GrowthRate
    capital_expense_growth: GrowthRate
    # FIXME: add support for inflation rate, here and in settings and analysis

    @classmethod
    def with_default_rate(cls, default_rate: FloatBetween0And1) -> "GrowthRatesBase":
        """
        Create growth rates initialized with default values.

        Args:
            default_rate: Default growth rate to use

        Returns:
            GrowthRatesBase instance with default values
        """

        return cls(
            default_rate=default_rate,
            general_growth=GrowthRate(name="General", value=default_rate),
            market_rent_growth=GrowthRate(name="Market Rent", value=default_rate),
            misc_income_growth=GrowthRate(name="Misc Income", value=default_rate),
            operating_expense_growth=GrowthRate(name="Operating Expenses", value=default_rate),
            leasing_costs_growth=GrowthRate(name="Leasing Costs", value=default_rate),
            capital_expense_growth=GrowthRate(name="Capital Expenses", value=default_rate),
        )

    @classmethod
    def with_custom_rates(
        cls, extra_rates: Optional[Dict[str, GrowthRate]] = None, **kwargs
    ) -> "GrowthRatesBase":
        """
        Create a dynamic GrowthRatesBase instance supporting arbitrary growth rate fields.
        Any standard fields not provided in kwargs will be populated using the default_rate,
        which must be provided if not all standard fields are specified.
        """
        from pydantic import create_model

        extra_rates = extra_rates or {}

        # Use a default rate if provided, otherwise check if all fields are covered
        default_rate = kwargs.get("default_rate")
        
        # Populate standard fields that are not explicitly provided in kwargs
        standard_fields = {
            "general_growth", "market_rent_growth", "misc_income_growth",
            "operating_expense_growth", "leasing_costs_growth", "capital_expense_growth"
        }

        if not standard_fields.issubset(kwargs.keys()) and default_rate is None:
            raise ValueError("A 'default_rate' must be provided if not all standard growth rates are specified.")

        base_data = {}
        if default_rate is not None:
            base_data = {
                "general_growth": GrowthRate(name="General", value=default_rate),
                "market_rent_growth": GrowthRate(name="Market Rent", value=default_rate),
                "misc_income_growth": GrowthRate(name="Misc Income", value=default_rate),
                "operating_expense_growth": GrowthRate(name="Operating Expenses", value=default_rate),
                "leasing_costs_growth": GrowthRate(name="Leasing Costs", value=default_rate),
                "capital_expense_growth": GrowthRate(name="Capital Expenses", value=default_rate),
            }
        
        # Combine base data with user-provided kwargs, kwargs take precedence
        instance_data = {**base_data, **kwargs, **extra_rates}
        
        dynamic_fields = {name: (GrowthRate, ...) for name in extra_rates.keys()}
        DynamicGrowthRates = create_model("DynamicGrowthRates", __base__=cls, **dynamic_fields)

        return DynamicGrowthRates.model_validate(instance_data) 
