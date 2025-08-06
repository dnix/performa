# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import date
from typing import Dict, Optional, Union

import pandas as pd
from pydantic import field_validator

from .model import Model
from .types import FloatBetween0And1, PositiveFloat
from .validation import validate_monthly_period_index


class GrowthRateBase(Model):
    """
    Base class for all growth/escalation rate types.
    
    Provides common interface for rate objects that can represent
    time-varying values for financial modeling.
    """
    # TODO: add a discriminator field to the model on `kind`?
    name: str


class PercentageGrowthRate(GrowthRateBase):
    """
    Growth rate for percentage-based escalations (0-1 constraint).
    
    Used for percentage escalations where rates represent proportional changes
    (e.g., 0.03 for 3% annual growth).
    
    Attributes:
        name: Name of the growth rate (e.g., "Market Rent Growth")
        value: The growth rate value(s), which can be:
            - A single float value (constant rate, e.g., 0.02 for 2%)
            - A pandas Series (time-based rates) with MONTHLY period index
            - A dictionary with date keys and rate values
    """
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
            # Validate monthly PeriodIndex
            validate_monthly_period_index(v, field_name="PercentageGrowthRate value")
            
            # Ensure all series values are between 0 and 1
            if not pd.api.types.is_numeric_dtype(v.dtype):
                raise ValueError("Growth rate Series must have numeric values")
            if (v < 0).any() or (v > 1).any():
                raise ValueError("Growth rates in Series must be between 0 and 1")
        elif not isinstance(v, (int, float)):
            raise TypeError(f"Unsupported type for PercentageGrowthRate value: {type(v)}")

        return v


class FixedGrowthRate(GrowthRateBase):
    """
    Growth rate for fixed dollar amount escalations (positive constraint only).
    
    Used for fixed dollar escalations where rates represent absolute amounts
    (e.g., 1.50 for $1.50/SF annual increase).
    
    Attributes:
        name: Name of the growth rate (e.g., "Fixed Escalation")
        value: The growth rate value(s), which can be:
            - A single positive float (constant amount)
            - A pandas Series (time-based amounts) with MONTHLY period index
            - A dictionary with date keys and amount values
    """
    value: Union[PositiveFloat, pd.Series, Dict[date, PositiveFloat]]

    @field_validator("value")
    @classmethod
    def validate_value(
        cls,
        v: Union[PositiveFloat, pd.Series, Dict],
    ) -> Union[PositiveFloat, pd.Series, Dict]:
        """Validate that value has the correct format and constraints"""
        if isinstance(v, dict):
            # Ensure all dict values are positive
            for key, rate in v.items():
                if not isinstance(key, date):
                    raise ValueError(
                        f"Fixed growth rate dictionary keys must be dates, got {type(key)}"
                    )
                if not isinstance(rate, (int, float)) or rate < 0:
                    raise ValueError(
                        f"Fixed growth rate for {key} must be non-negative, got {rate}"
                    )
        elif isinstance(v, pd.Series):
            # Validate monthly PeriodIndex
            validate_monthly_period_index(v, field_name="FixedGrowthRate value")
            
            # Ensure all series values are positive
            if not pd.api.types.is_numeric_dtype(v.dtype):
                raise ValueError("Fixed growth rate Series must have numeric values")
            if (v < 0).any():
                raise ValueError("Fixed growth rates in Series must be non-negative")
        elif not isinstance(v, (int, float)) or v < 0:
            raise ValueError(f"Fixed growth rate must be non-negative, got {v}")

        return v


class GrowthRates(Model):
    """Base collection of growth rate profiles for different aspects of an asset"""

    default_rate: Optional[FloatBetween0And1] = None
    general_growth: PercentageGrowthRate
    market_rent_growth: PercentageGrowthRate
    misc_income_growth: PercentageGrowthRate
    operating_expense_growth: PercentageGrowthRate
    leasing_costs_growth: PercentageGrowthRate
    capital_expense_growth: PercentageGrowthRate
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
            general_growth=PercentageGrowthRate(name="General", value=default_rate),
            market_rent_growth=PercentageGrowthRate(name="Market Rent", value=default_rate),
            misc_income_growth=PercentageGrowthRate(name="Misc Income", value=default_rate),
            operating_expense_growth=PercentageGrowthRate(name="Operating Expenses", value=default_rate),
            leasing_costs_growth=PercentageGrowthRate(name="Leasing Costs", value=default_rate),
            capital_expense_growth=PercentageGrowthRate(name="Capital Expenses", value=default_rate),
        )

    @classmethod
    def with_custom_rates(
        cls, extra_rates: Optional[Dict[str, PercentageGrowthRate]] = None, **kwargs
    ) -> "GrowthRates":
        """
        Create a dynamic GrowthRates instance supporting arbitrary growth rate fields.
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
                "general_growth": PercentageGrowthRate(name="General", value=default_rate),
                "market_rent_growth": PercentageGrowthRate(name="Market Rent", value=default_rate),
                "misc_income_growth": PercentageGrowthRate(name="Misc Income", value=default_rate),
                "operating_expense_growth": PercentageGrowthRate(name="Operating Expenses", value=default_rate),
                "leasing_costs_growth": PercentageGrowthRate(name="Leasing Costs", value=default_rate),
                "capital_expense_growth": PercentageGrowthRate(name="Capital Expenses", value=default_rate),
            }
        
        # Combine base data with user-provided kwargs, kwargs take precedence
        instance_data = {**base_data, **kwargs, **extra_rates}
        
        dynamic_fields = {name: (PercentageGrowthRate, ...) for name in extra_rates.keys()}
        DynamicGrowthRates = create_model("DynamicGrowthRates", __base__=cls, **dynamic_fields)

        return DynamicGrowthRates.model_validate(instance_data)


# Legacy aliases for backward compatibility
GrowthRate = PercentageGrowthRate
GrowthRates = GrowthRates 