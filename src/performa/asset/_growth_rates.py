from datetime import date
from typing import Dict, Optional, Union

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
                     raise ValueError(f"Growth rate dictionary keys must be dates, got {type(key)}")
                if not isinstance(rate, (int, float)) or not (0 <= rate <= 1):
                    raise ValueError(f"Growth rate for {key} must be between 0 and 1, got {rate}")
        elif isinstance(v, pd.Series):
            # Ensure all series values are between 0 and 1
            if not pd.api.types.is_numeric_dtype(v.dtype):
                raise ValueError("Growth rate Series must have numeric values")
            if (v < 0).any() or (v > 1).any():
                raise ValueError("Growth rates in Series must be between 0 and 1")
        elif not isinstance(v, (int, float)):
             raise TypeError(f"Unsupported type for GrowthRate value: {type(v)}")

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
    # FIXME: add support for inflation rate, here and in settings and analysis

    @classmethod
    def with_default_rate(cls, default_rate: FloatBetween0And1) -> "GrowthRates":
        """
        Create growth rates initialized with default values.

        Args:
            default_rate: Default growth rate to use

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
    def with_custom_rates(cls, extra_rates: Optional[Dict[str, GrowthRate]] = None, **default_rates) -> "GrowthRates":
        """
        Create a dynamic GrowthRates instance supporting arbitrary growth rate fields.
        
        This method leverages pydantic's create_model to extend the existing GrowthRates model
        with extra fields provided in extra_rates. The resulting model supports dot notation access
        for both the predefined static rates and any additional dynamic rates.
        
        Args:
            extra_rates: A dictionary where each key is the name of an extra growth rate and 
                         the value is a GrowthRate instance.
            default_rates: Keyword arguments for setting/overriding the static GrowthRates fields
                           (including default_rate or standard growth types).
        
        Returns:
            An instance of a dynamically generated GrowthRates model with the extra fields included.
            
        Example:
            ```python
            # Create growth rates with custom fields
            custom_rates = GrowthRates.with_custom_rates(
                # Add a custom growth rate for inflation
                extra_rates={
                    "inflation_rate": GrowthRate(name="Inflation", value=0.03)
                },
                # Override a standard field
                default_rate=0.025,
                market_rent_growth=GrowthRate(name="Market Rent Custom", value=0.035)
            )
            
            # Access both standard and custom fields with dot notation
            print(custom_rates.market_rent_growth.value)  # 0.035
            print(custom_rates.inflation_rate.value)  # 0.03
            print(custom_rates.default_rate) # 0.025
            # Access an untouched default field
            print(custom_rates.general_growth.value) # This would raise AttributeError unless provided in default_rates
            ```
        """
        from pydantic import create_model

        extra_rates = extra_rates or {}

        # Validate extra_rates values are GrowthRate instances
        for name, rate in extra_rates.items():
            if not isinstance(rate, GrowthRate):
                raise TypeError(f"Value for extra rate '{name}' must be a GrowthRate instance, got {type(rate)}")

        # Prepare fields for the dynamic model creation
        dynamic_fields = {name: (GrowthRate, ...) for name in extra_rates.keys()}

        # Create the dynamic model class
        DynamicGrowthRates = create_model(
            "DynamicGrowthRates",
            __base__=cls,
            **dynamic_fields
        )

        # Combine the provided default/static fields with the extra rates for instantiation
        # Ensure that keys in extra_rates properly override any conflicting keys in default_rates
        instance_data = {**default_rates, **extra_rates}

        # Instantiate the dynamic model using the combined data
        # Pydantic V2 uses model_validate
        return DynamicGrowthRates.model_validate(instance_data)
