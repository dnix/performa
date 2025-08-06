# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Union
from uuid import UUID, uuid4

import pandas as pd
from pydantic import Field, computed_field, field_validator

from .enums import (
    CalculationPass,
    FrequencyEnum,
    PropertyAttributeKey,
    UnleveredAggregateLineKey,
)
from .growth_rates import GrowthRate
from .model import Model
from .settings import GlobalSettings
from .timeline import Timeline
from .types import PositiveFloat
from .validation import validate_monthly_period_index

if TYPE_CHECKING:
    from performa.analysis import AnalysisContext


# Union type for all possible calculation references
# Deliberately type-safe: only explicit enum values allowed
ReferenceKey = Union[PropertyAttributeKey, UnleveredAggregateLineKey]


class CashFlowModel(Model):
    """
    Base class for any cash flow description.

    Provides a concrete base implementation for cash flow calculation,
    including unit-based resolution and growth application. This class is
    intended to be subclassed for specific cash flow types (e.g., OpExItem,
    Lease, etc.).

    The core calculation logic resides in the `compute_cf` method, which can be
    called by subclasses via `super().compute_cf(context)` to get a base,
    grown cash flow series. Subclasses can then apply their own specific
    adjustments (like occupancy-based adjustments).
    
    Notes:
        - ANNUAL frequency: Value divided by 12 and applied evenly each month
        - One-time expenses: Use CapitalItem, or pd.Series/dict with specific timing
        
    Reference Field:
        The `reference` field supports three types of calculations:
        - PropertyAttributeKey: Multiply by property attributes (e.g., unit_count, net_rentable_area)
        - UnleveredAggregateLineKey: Calculate percentage of financial aggregates (e.g., % of EGI)
        - None: Direct currency amount (no multiplication)
        
    Examples:
        # Per dwelling unit calculation
        reference=PropertyAttributeKey.UNIT_COUNT
        
        # Per square foot calculation  
        reference=PropertyAttributeKey.NET_RENTABLE_AREA
        
        # Percentage of effective gross income
        reference=UnleveredAggregateLineKey.EFFECTIVE_GROSS_INCOME
        
        # Direct currency amount
        reference=None
    """

    uid: UUID = Field(
        default_factory=uuid4,
        description="Stable unique identifier for this model instance",
    )
    name: str
    category: str
    subcategory: str
    description: Optional[str] = None
    account: Optional[str] = None
    timeline: Timeline
    value: Union[PositiveFloat, pd.Series, Dict, List]
    frequency: FrequencyEnum = FrequencyEnum.MONTHLY
    reference: Optional[ReferenceKey] = None
    settings: GlobalSettings = Field(default_factory=GlobalSettings)
    growth_rate: Optional[GrowthRate] = None
    
    @field_validator("value")
    @classmethod
    def validate_value(cls, v: Union[PositiveFloat, pd.Series, Dict, List]) -> Union[PositiveFloat, pd.Series, Dict, List]:
        """
        Validate the value format and constraints.
        
        For Series inputs, ensures they have monthly PeriodIndex to prevent
        data loss during reindexing operations.
        """
        if isinstance(v, pd.Series):
            # Validate monthly PeriodIndex for Series
            validate_monthly_period_index(v, field_name="CashFlowModel value")
            # Ensure all values are non-negative
            if not pd.api.types.is_numeric_dtype(v.dtype):
                raise ValueError("CashFlowModel value Series must have numeric values")
            if (v < 0).any():
                raise ValueError("All values in CashFlowModel Series must be non-negative")
        elif isinstance(v, dict):
            # Validate dict values are non-negative
            for key, val in v.items():
                if not isinstance(val, (int, float)) or val < 0:
                    raise ValueError(f"Dict value for {key} must be non-negative, got {val}")
        elif isinstance(v, list):
            # Validate list values are non-negative
            for i, val in enumerate(v):
                if not isinstance(val, (int, float)) or val < 0:
                    raise ValueError(f"List value at index {i} must be non-negative, got {val}")
        elif isinstance(v, (int, float)):
            # Scalar values are already validated by PositiveFloat type
            pass
        else:
            raise TypeError(f"Unsupported type for CashFlowModel value: {type(v)}")
        
        return v

    @computed_field
    @property
    def calculation_pass(self) -> CalculationPass:
        """
        Determines the calculation phase for this model based on its dependencies.
        
        This computed property categorizes models into calculation phases for the
        two-phase execution system:
        
        - INDEPENDENT_VALUES: Models that can be calculated first (Phase 1)
          - No aggregate references (self.reference is None)
          - Examples: Base rent, base operating expenses, property taxes
          
        - DEPENDENT_VALUES: Models requiring aggregated results (Phase 2)  
          - Has aggregate reference (self.reference is not None)
          - Examples: Admin fees (% of Total OpEx), management fees (% of NOI)
        
        This classification enables:
        1. Topological execution ordering to resolve dependencies
        2. Defensive validation of dependency complexity limits
        3. Proper aggregate calculation between phases
        4. Prevention of circular dependency issues
        
        Returns:
            CalculationPass enum indicating when this model should be executed
            
        Note:
            This is a computed field that automatically updates if the reference
            property changes, ensuring models are always correctly classified.
        
        Examples:
            # Independent model - calculated in Phase 1
            base_opex = OpExItem(name="Utilities", value=5000, reference=None)
            assert base_opex.calculation_pass == CalculationPass.INDEPENDENT_VALUES
            
            # Dependent model - calculated in Phase 2 after aggregation
            admin_fee = OpExItem(name="Admin Fee", value=0.05, reference=UnleveredAggregateLineKey.TOTAL_OPERATING_EXPENSES)
            assert admin_fee.calculation_pass == CalculationPass.DEPENDENT_VALUES
        """
        if self.reference is not None and isinstance(self.reference, UnleveredAggregateLineKey):
            # Models with UnleveredAggregateLineKey references depend on aggregated values
            return CalculationPass.DEPENDENT_VALUES
        return CalculationPass.INDEPENDENT_VALUES

    def _convert_frequency(
        self, value: Union[float, pd.Series]
    ) -> Union[float, pd.Series]:
        """
        Convert value from specified frequency to monthly frequency.
        
        Annual values are evenly distributed across all months (value / 12).
        For one-time expenses, use CapitalItem, pd.Series, or dict instead.
        """
        if self.frequency == FrequencyEnum.ANNUAL:
            return value / 12.0  # Evenly distribute annual amount across 12 months
        return value  # Monthly frequency requires no conversion

    def _cast_to_flow(self, value: Union[float, pd.Series, Dict, List]) -> pd.Series:
        """
        Cast value into a pandas Series spanning the model's timeline.
        
        - Scalar: Applied uniformly to each month (post frequency conversion)
        - pd.Series/Dict: Custom timing for one-time or irregular expenses
        - List: Values applied sequentially to timeline periods
        """
        periods = self.timeline.period_index
        if isinstance(value, dict):
            try:
                flow_series = pd.Series(value)
                if not isinstance(flow_series.index, pd.PeriodIndex):
                    flow_series.index = pd.PeriodIndex(flow_series.index, freq="M")
            except Exception as e:
                raise ValueError(
                    "Could not convert provided dict keys to a PeriodIndex with monthly frequency."
                ) from e
            return flow_series.reindex(periods, fill_value=0)
        elif isinstance(value, (int, float)):
            # Apply the monthly value to each period in timeline
            return pd.Series([value] * len(periods), index=periods)
        elif isinstance(value, pd.Series):
            return self._align_flow_series(value)  # Align series to the model's timeline
        elif isinstance(value, list):
            if len(value) != len(periods):
                raise ValueError(f"List length {len(value)} does not match timeline length {len(periods)}.")
            return pd.Series(value, index=periods)
        else:
            raise ValueError("Unsupported value type for casting to flow.")

    def _align_flow_series(self, flow: pd.Series) -> pd.Series:
        """
        Align a flow series to the model's timeline.
        
        Validates that the input series has a monthly PeriodIndex before aligning.
        This ensures data integrity and prevents silent data loss from reindexing
        non-monthly data.
        
        Args:
            flow: Series with monthly PeriodIndex
            
        Returns:
            Series aligned to timeline with 0-filled gaps
            
        Raises:
            ValueError: If series doesn't have monthly PeriodIndex
        """
        # Validate that the series has monthly PeriodIndex
        validate_monthly_period_index(flow, field_name="flow series")
        
        # Now we can safely reindex knowing the frequency matches
        return flow.reindex(self.timeline.period_index, fill_value=0.0)

    def _apply_compounding_growth(
        self,
        base_series: pd.Series,
        growth_rate: "GrowthRate",
    ) -> pd.Series:
        if not isinstance(base_series.index, pd.PeriodIndex):
            raise ValueError("Base series index must be a monthly PeriodIndex.")
        growth_value = growth_rate.value
        periods = base_series.index
        if isinstance(growth_value, (float, int)):
            monthly_rate = float(growth_value) / 12.0
            period_rates = pd.Series(monthly_rate, index=periods)
        elif isinstance(growth_value, pd.Series):
            aligned_rates = growth_value.reindex(periods, method="ffill").fillna(0)
            period_rates = aligned_rates
        elif isinstance(growth_value, dict):
            dict_series = pd.Series(growth_value)
            if not isinstance(dict_series.index, pd.PeriodIndex):
                dict_series.index = pd.PeriodIndex(dict_series.index, freq='M')
            aligned_rates = dict_series.reindex(periods, method="ffill").fillna(0)
            period_rates = aligned_rates
        else:
            raise TypeError(f"Unsupported type for GrowthRate value: {type(growth_value)}")
        compounding_factors = (1 + period_rates).cumprod()
        return base_series * compounding_factors

    def compute_cf(
        self, context: AnalysisContext
    ) -> Union[pd.Series, Dict[str, pd.Series]]:
        """
        Computes the cash flow for this model instance.

        This base implementation serves as the primary engine for most cash flow
        calculations. It performs the following steps:
        1.  Determines the base value by resolving the reference:
            - PropertyAttributeKey: Multiply by property attribute (e.g., unit_count)
            - UnleveredAggregateLineKey: Calculate percentage of aggregate (e.g., % of EGI)
            - None: Use direct currency amount
        2.  Converts the value to a monthly frequency.
        3.  Casts the value into a pandas Series spanning the item's timeline.
        4.  Applies compounding growth if a `growth_rate` is present.

        Subclasses can call this method via `super().compute_cf(context)` to
        get a fully calculated and grown base cash flow series, upon which they
        can apply their own specific modifications (e.g., occupancy adjustments).
        """
        base_value = self.value

        # New unified reference-based calculation system
        if self.reference is None:
            # Direct currency amount - no multiplication needed
            pass
            
        elif isinstance(self.reference, PropertyAttributeKey):
            # Property attribute calculation (replaces PER_UNIT)
            if hasattr(context.property_data, self.reference.value):
                multiplier = getattr(context.property_data, self.reference.value)
                base_value = self.value * float(multiplier) if multiplier else 0.0
            else:
                raise AttributeError(
                    f"Property '{getattr(context.property_data, 'name', 'Unknown')}' "
                    f"missing attribute '{self.reference.value}' for calculation '{self.name}'. "
                    f"Available attributes: {[attr for attr in dir(context.property_data) if not attr.startswith('_')]}"
                )
                
        elif isinstance(self.reference, UnleveredAggregateLineKey):
            # Financial aggregate calculation (replaces BY_PERCENT)
            dependency_cf = context.resolved_lookups.get(self.reference.value)
            if dependency_cf is None:
                raise ValueError(f"Unresolved aggregate dependency for '{self.name}': {self.reference.value}")
            base_value = dependency_cf * self.value
            
        else:
            raise TypeError(
                f"Unsupported reference type for '{self.name}': {type(self.reference)}. "
                f"Expected PropertyAttributeKey, UnleveredAggregateLineKey, or None."
            )
        
        monthly_value = self._convert_frequency(base_value)
        base_series = self._cast_to_flow(monthly_value)

        if self.growth_rate:
            base_series = self._apply_compounding_growth(
                base_series=base_series, growth_rate=self.growth_rate
            )
        
        return base_series 