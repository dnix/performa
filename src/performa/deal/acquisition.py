# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Acquisition Terms Model

Models the initial acquisition of an asset or land, including the purchase price
and associated closing costs, preserving the timing of all outflows.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Optional

import pandas as pd
from pydantic import Field, model_validator

from ..core.primitives import (
    CashFlowModel,
    FloatBetween0And1,
    FrequencyEnum,
    Timeline,
    UnitOfMeasureEnum,
)

if TYPE_CHECKING:
    from ..analysis import AnalysisContext


class AcquisitionTerms(CashFlowModel):
    """
    Models the initial acquisition of an asset or land, including the purchase price
    and associated closing costs, preserving the timing of all outflows.
    
    The 'value' field can be:
    - A float for a single, lump-sum purchase price.
    - A pandas.Series with a PeriodIndex for multi-payment acquisitions.
    
    Key Features:
    - Preserves cash flow timing (no flattening like .sum())
    - Calculates closing costs as percentage of each payment
    - Generates negative cash flows (outflows) for all acquisition costs
    - Supports both simple and complex purchase structures
    
    Examples:
        # Simple lump-sum purchase
        acquisition = AcquisitionTerms(
            name="Property Purchase",
            timeline=Timeline(start_date=date(2024, 3, 1), duration_months=1),
            value=10_000_000,
            acquisition_date=date(2024, 3, 1),
            closing_costs_rate=0.025
        )
        
        # Complex multi-payment structure
        payments = pd.Series([2_000_000, 8_000_000], 
                           index=pd.period_range('2024-03', periods=2, freq='M'))
        acquisition = AcquisitionTerms(
            name="Phased Acquisition",
            timeline=Timeline(start_date=date(2024, 3, 1), duration_months=2),
            value=payments,
            closing_costs_rate=0.02
        )
    """
    
    # Override CashFlowModel defaults for acquisition context
    category: str = "Acquisition"
    subcategory: str = "Purchase"
    frequency: FrequencyEnum = FrequencyEnum.MONTHLY
    unit_of_measure: UnitOfMeasureEnum = UnitOfMeasureEnum.CURRENCY
    
    # Acquisition-specific fields
    closing_costs_rate: FloatBetween0And1 = Field(
        default=0.02, 
        description="Closing costs as percentage of purchase price (default 2%)"
    )
    
    # The acquisition_date is optional. It's only needed if `value` is a single float.
    # If `value` is a Series, the Series index defines the payment dates.
    acquisition_date: Optional[date] = Field(
        default=None,
        description="Date of acquisition (required when value is a single amount)"
    )
    
    @model_validator(mode="after")
    def validate_acquisition_timing(self) -> "AcquisitionTerms":
        """
        Ensures that the timing of the acquisition is specified unambiguously.
        """
        is_scalar_value = isinstance(self.value, (int, float))
        has_acquisition_date = self.acquisition_date is not None

        if is_scalar_value and not has_acquisition_date:
            raise ValueError(
                "'acquisition_date' is required when 'value' is a single number."
            )
        
        if not is_scalar_value and has_acquisition_date:
            raise ValueError(
                "'acquisition_date' must not be provided when 'value' is a "
                "Series or dict, as timing is defined by the data structure's index."
            )
        return self
    
    def compute_cf(self, context: "AnalysisContext") -> pd.Series:
        """
        Calculates the acquisition costs as negative cash flows. This specialized
        implementation handles event-based outflows following the same pattern as CapExItemBase.
        
        Returns:
            pd.Series: Negative cash flows representing acquisition outflows
        """
        # For simple float values, place the payment at the acquisition_date
        if isinstance(self.value, (int, float)):
            if not self.acquisition_date:
                raise ValueError("'acquisition_date' is required when 'value' is a single number.")
            
            # Create a payment dict to use _cast_to_flow
            payment_period = pd.Period(self.acquisition_date, freq="M")
            payment_dict = {payment_period: self.value}
            base_price_series = self._cast_to_flow(payment_dict)
        else:
            # For Series/Dict values, _cast_to_flow handles the timing automatically
            base_price_series = self._cast_to_flow(self.value)
        
        # Calculate closing costs for each payment in the series
        closing_costs_series = base_price_series * self.closing_costs_rate
        total_outflow_series = base_price_series + closing_costs_series
        
        # Return as negative values to represent cash outflows
        return total_outflow_series * -1 