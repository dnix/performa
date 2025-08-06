# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Deal-level fee abstractions for Performa.

This module provides base classes and concrete implementations for various
deal-level fees including developer fees, asset management fees, and other
transaction-related costs using the flexible DrawSchedule system.

TODO: Consider integrating with LeveredAggregateLineKey for sophisticated
reference metric handling (% of TDC, % of GAV, etc.). This would require:
- Lookup methods to calculate deal-level metrics 
- Integration with deal analysis pipeline
- Clear enum-based reference definitions
- Only implement when we have a concrete need for this complexity
"""

from datetime import date
from typing import Dict, Optional, Union
from uuid import UUID, uuid4

import pandas as pd
from pydantic import Field, field_validator

from ..core.primitives.draw_schedule import (
    AnyDrawSchedule,
    FirstLastDrawSchedule,
    FirstOnlyDrawSchedule,
    LastOnlyDrawSchedule,
    UniformDrawSchedule,
)
from ..core.primitives.enums import FeeTypeEnum
from ..core.primitives.model import Model
from ..core.primitives.timeline import Timeline
from ..core.primitives.types import PositiveFloat
from ..core.primitives.validation import validate_monthly_period_index
from .entities import Entity


class DealFee(Model):
    """
    Deal-level fee with flexible payment timing via DrawSchedule.
    
    Supports dual-entry accounting where fees are simultaneously a USE of project
    funds and a SOURCE of income for specific partners (typically GP). Each fee
    must specify its payee Partner for proper allocation.
    
    Uses the DrawSchedule system to provide flexible payment patterns for
    developer fees, asset management fees, and other transaction-related costs.
    
    Usage Examples:
        # Create a partner first
        developer = Partner(name="Developer", kind="GP", share=0.25)
        
        # Upfront payment
        fee = DealFee.create_upfront_fee(
            name="Development Fee",
            value=500_000,
            payee=developer,
            timeline=project_timeline
        )
        
        # Complex split payment
        fee = DealFee.create_split_fee(
            name="Development Fee", 
            value=750_000,
            payee=developer,
            timeline=project_timeline,
            first_percentage=0.3
        )
        
        # Custom milestone payments
        fee = DealFee(
            name="Development Fee",
            value=1_000_000,
            payee=developer,
            timeline=project_timeline,
            draw_schedule=ManualDrawSchedule(values=[0.2, 0.0, 0.3, 0.0, 0.5])
        )
        
        # S-curve following construction activity
        fee = DealFee(
            name="Development Fee",
            value=750_000,
            payee=developer,
            timeline=project_timeline,
            draw_schedule=SCurveDrawSchedule(sigma=0.3)
        )
    
    Common Industry Patterns (for developer fees):
    - $500K - $2M for typical development deals
    - $100K - $500K for smaller projects
    - Payment timing varies: upfront, at completion, or split schedule
    - Typically paid as priority distributions to GP partners
    """
    
    # Core Identity
    uid: UUID = Field(default_factory=uuid4)
    name: str = Field(..., description="Fee name for identification")
    description: Optional[str] = Field(default=None, description="Fee description")
    
    # Partnership Information
    payee: Entity = Field(..., description="Entity that receives the fee payment")
    fee_type: Optional[FeeTypeEnum] = Field(
        default=None, 
        description="Optional fee categorization for accounting and reporting purposes"
    )
    
    # Fee Configuration
    value: Union[PositiveFloat, pd.Series, Dict[date, PositiveFloat]] = Field(
        ...,
        description="Fee amount in dollars (constant, monthly series, or milestone dict)"
    )
    
    # DrawSchedule Integration
    timeline: Timeline = Field(
        ...,
        description="Timeline for fee payment schedule"
    )
    
    draw_schedule: AnyDrawSchedule = Field(
        default_factory=UniformDrawSchedule,
        description="DrawSchedule pattern for fee payment timing"
    )
    
    # Factory Methods for Common Patterns
    @classmethod
    def create_upfront_fee(
        cls, 
        name: str, 
        value: Union[PositiveFloat, pd.Series, Dict[date, PositiveFloat]], 
        payee: Entity,
        timeline: Timeline,
        description: Optional[str] = None,
        fee_type: Optional[FeeTypeEnum] = None
    ) -> "DealFee":
        """
        Factory method for upfront fees.
        
        Args:
            name: Fee name
            value: Fee amount
            payee: Entity who receives the fee
            timeline: Project timeline
            description: Optional description
            fee_type: Optional fee categorization
            
        Returns:
            DealFee configured for upfront payment
        """
        return cls(
            name=name,
            value=value,
            payee=payee,
            timeline=timeline,
            draw_schedule=FirstOnlyDrawSchedule(),
            description=description,
            fee_type=fee_type
        )
    
    @classmethod
    def create_completion_fee(
        cls, 
        name: str, 
        value: Union[PositiveFloat, pd.Series, Dict[date, PositiveFloat]], 
        payee: Entity,
        timeline: Timeline,
        description: Optional[str] = None,
        fee_type: Optional[FeeTypeEnum] = None
    ) -> "DealFee":
        """
        Factory method for completion fees.
        
        Args:
            name: Fee name
            value: Fee amount
            payee: Entity that receives the fee
            timeline: Project timeline
            description: Optional description
            fee_type: Optional fee categorization
            
        Returns:
            DealFee configured for completion payment
        """
        return cls(
            name=name,
            value=value,
            payee=payee,
            timeline=timeline,
            draw_schedule=LastOnlyDrawSchedule(),
            description=description,
            fee_type=fee_type
        )
    
    @classmethod
    def create_split_fee(
        cls, 
        name: str, 
        value: Union[PositiveFloat, pd.Series, Dict[date, PositiveFloat]], 
        payee: Entity,
        timeline: Timeline,
        first_percentage: Optional[float] = None,
        last_percentage: Optional[float] = None,
        description: Optional[str] = None,
        fee_type: Optional[FeeTypeEnum] = None
    ) -> "DealFee":
        """
        Factory method for split fees.
        
        Args:
            name: Fee name
            value: Fee amount
            payee: Entity that receives the fee
            timeline: Project timeline
            first_percentage: Percentage paid upfront (mutually exclusive with last_percentage)
            last_percentage: Percentage paid at completion (mutually exclusive with first_percentage)
            description: Optional description
            fee_type: Optional fee categorization
            
        Returns:
            DealFee configured for split payment
        """
        if first_percentage is not None and last_percentage is not None:
            raise ValueError("Cannot specify both first_percentage and last_percentage")
        if first_percentage is None and last_percentage is None:
            raise ValueError("Must specify either first_percentage or last_percentage")
        
        if first_percentage is not None:
            draw_schedule = FirstLastDrawSchedule(first_percentage=first_percentage)
        else:
            draw_schedule = FirstLastDrawSchedule(last_percentage=last_percentage)
        
        return cls(
            name=name,
            value=value,
            payee=payee,
            timeline=timeline,
            draw_schedule=draw_schedule,
            description=description,
            fee_type=fee_type
        )
    
    @classmethod
    def create_uniform_fee(
        cls, 
        name: str, 
        value: Union[PositiveFloat, pd.Series, Dict[date, PositiveFloat]], 
        payee: Entity,
        timeline: Timeline,
        description: Optional[str] = None,
        fee_type: Optional[FeeTypeEnum] = None
    ) -> "DealFee":
        """
        Factory method for uniform fees.
        
        Args:
            name: Fee name
            value: Fee amount
            payee: Entity that receives the fee
            timeline: Project timeline
            description: Optional description
            fee_type: Optional fee categorization
            
        Returns:
            DealFee configured for uniform payment across timeline
        """
        return cls(
            name=name,
            value=value,
            payee=payee,
            timeline=timeline,
            draw_schedule=UniformDrawSchedule(),
            description=description,
            fee_type=fee_type
        )

    @field_validator("value")
    @classmethod
    def validate_value(cls, v: Union[PositiveFloat, pd.Series, Dict[date, PositiveFloat]]) -> Union[PositiveFloat, pd.Series, Dict[date, PositiveFloat]]:
        """Validate fee value format and constraints."""
        if isinstance(v, pd.Series):
            # Validate monthly PeriodIndex
            validate_monthly_period_index(v, field_name="fee value")
            
            # Ensure all values are non-negative
            if not pd.api.types.is_numeric_dtype(v.dtype):
                raise ValueError("Fee value Series must have numeric values")
            if (v < 0).any():
                raise ValueError("All fee values in Series must be non-negative")
        elif isinstance(v, dict):
            # Validate dict has date keys and positive values
            for key, val in v.items():
                if not isinstance(key, date):
                    raise ValueError(
                        f"Fee milestone dictionary keys must be dates, got {type(key)}"
                    )
                if not isinstance(val, (int, float)) or val < 0:
                    raise ValueError(f"Fee value for {key} must be non-negative, got {val}")
        elif isinstance(v, (int, float)):
            if v < 0:
                raise ValueError(f"Fee value must be non-negative, got {v}")
        else:
            raise TypeError(f"Fee value must be a positive number, pandas Series, or date->value dict, got {type(v)}")
        
        return v
    
    def calculate_total_fee(self) -> float:
        """
        Calculate the total dollar amount of the fee.
        
        For Series values, returns the sum of all values.
        For Dict values, returns the sum of all milestone payments.
        
        Returns:
            Total fee amount in dollars
        """
        if isinstance(self.value, pd.Series):
            return self.value.sum()
        elif isinstance(self.value, dict):
            return sum(self.value.values())
        return self.value
    
    def compute_cf(self, timeline: Optional[Timeline] = None) -> pd.Series:
        """
        Compute fee cash flows as a pandas Series.
        
        Args:
            timeline: Timeline to use (defaults to self.timeline)
            
        Returns:
            Series with fee cash flows for each period
        """
        # Use provided timeline or fall back to self.timeline
        effective_timeline = timeline or self.timeline
        
        return self.draw_schedule.apply_to_amount(
            amount=self.calculate_total_fee(),
            periods=effective_timeline.duration_months,
            index=effective_timeline.period_index
        )

    def calculate_total_fee_series(self, periods: int, index: Optional[pd.Index] = None) -> pd.Series:
        """
        Calculate the total fee as a pandas Series.
        
        For scalar values, repeats the value for each period.
        For Series values, returns the series itself (validated to have monthly PeriodIndex).
        For Dict values, creates a series with values at milestone dates and zeros elsewhere.
        
        Args:
            periods: Number of periods to create (ignored if value is already a Series)
            index: Optional index for the Series (must be PeriodIndex for dict values)
            
        Returns:
            Series with the fee value for each period
        """
        if isinstance(self.value, pd.Series):
            # Return the existing series (already validated to be monthly)
            return self.value
        elif isinstance(self.value, dict):
            # Convert milestone dict to series
            if index is None:
                raise ValueError("Index must be provided when value is a milestone dict")
            if not isinstance(index, pd.PeriodIndex):
                raise ValueError("Index must be a PeriodIndex when value is a milestone dict")
            
            # Create series with zeros
            series = pd.Series(0.0, index=index)
            
            # Fill in milestone values
            for milestone_date, amount in self.value.items():
                milestone_period = pd.Period(milestone_date, freq='M')
                if milestone_period in series.index:
                    series[milestone_period] = amount
            
            return series
        elif index is not None:
            if len(index) != periods:
                raise ValueError(f"Index length ({len(index)}) must match periods ({periods})")
            return pd.Series([self.value] * periods, index=index)
        else:
            return pd.Series([self.value] * periods)
    
    def upfront_amount(self) -> float:
        """Get the upfront fee amount."""
        cash_flows = self.compute_cf()
        return cash_flows.iloc[0] if len(cash_flows) > 0 else 0.0
    
    def completion_amount(self) -> float:
        """Get the completion fee amount."""
        cash_flows = self.compute_cf()
        return cash_flows.iloc[-1] if len(cash_flows) > 0 else 0.0

    def __str__(self) -> str:
        """
        Return string representation of the deal fee.
        
        Examples:
            "Development Fee: $750,000 (FirstLastDrawSchedule) -> Developer (GP)"
            "Developer Fee: $500,000 (UniformDrawSchedule) -> Developer (GP)"
            "Management Fee: $1,200,000 total (ManualDrawSchedule) -> Asset Manager (GP)"
        """
        if isinstance(self.value, pd.Series):
            total = self.value.sum()
            schedule_type = type(self.draw_schedule).__name__
            return f"{self.name}: ${total:,.0f} total ({schedule_type}) -> {self.payee.name} ({self.payee.kind})"
        else:
            schedule_type = type(self.draw_schedule).__name__
            return f"{self.name}: ${self.value:,.0f} ({schedule_type}) -> {self.payee.name} ({self.payee.kind})"
