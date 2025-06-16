from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Union
from uuid import UUID, uuid4

import pandas as pd
from pydantic import Field

from .enums import FrequencyEnum, UnitOfMeasureEnum
from .growth_rates import GrowthRate
from .model import Model
from .settings import GlobalSettings
from .timeline import Timeline
from .types import PositiveFloat


class CashFlowModel(Model, ABC):
    """
    Base Abstract class for any cash flow description.
    
    Subclasses must implement the compute_cf method. This base class is not
    intended for direct instantiation.
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
    unit_of_measure: UnitOfMeasureEnum
    frequency: FrequencyEnum = FrequencyEnum.MONTHLY
    reference: Optional[Union[float, pd.Series, str, UUID]] = None
    settings: GlobalSettings = Field(default_factory=GlobalSettings)

    def resolve_reference(
        self,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Union[float, pd.Series, Dict, None]]] = None
    ) -> Optional[Union[float, pd.Series, Dict]]:
        if isinstance(self.reference, (int, float, pd.Series, Dict)):
            return self.reference
        elif isinstance(self.reference, (str, UUID)):
            if lookup_fn is None:
                raise ValueError(
                    "A lookup function is required to resolve string or UUID references."
                )
            return lookup_fn(self.reference)
        return None

    def _convert_frequency(
        self, value: Union[float, pd.Series]
    ) -> Union[float, pd.Series]:
        if self.frequency == FrequencyEnum.ANNUAL:
            return value / 12.0
        return value

    def _cast_to_flow(self, value: Union[float, pd.Series, Dict, List]) -> pd.Series:
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
            return pd.Series([value] * len(periods), index=periods)
        elif isinstance(value, pd.Series):
            return self._align_flow_series(value) # Align series to the model's timeline
        elif isinstance(value, list):
            if len(value) != len(periods):
                raise ValueError(f"List length {len(value)} does not match timeline length {len(periods)}.")
            return pd.Series(value, index=periods)
        else:
            raise ValueError("Unsupported value type for casting to flow.")

    def _align_flow_series(self, flow: pd.Series) -> pd.Series:
        """
        Align the provided flow series to the model's timeline.
        """
        if not isinstance(flow.index, pd.PeriodIndex) or flow.index.freq != 'M':
             # Attempt to convert DatetimeIndex or other PeriodIndex to monthly PeriodIndex
            try:
                flow.index = flow.index.to_period('M')
            except AttributeError:
                 raise ValueError("Flow series index must be a PeriodIndex or DatetimeIndex.")
        return flow.reindex(self.timeline.period_index, fill_value=0.0)

    def _apply_compounding_growth(
        self,
        base_series: pd.Series,
        growth_rate: "GrowthRate",
    ) -> pd.Series:
        """
        Apply compounding growth to a base cash flow series.
        Growth is applied period-over-period. The value in each period is
        the value of the prior period multiplied by (1 + growth_rate).
        """
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

        # Create compounding factors. The value at period `t` is the cumulative
        # product of (1 + rate) up to `t`.
        compounding_factors = (1 + period_rates).cumprod()

        # Apply the compounding factors to the base series.
        # This assumes the base_series contains the starting values for each period
        # before any growth is applied.
        return base_series * compounding_factors

    def compute_cf(
        self,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Any]] = None,
        **kwargs: Any,
    ) -> Union[pd.Series, Dict[str, pd.Series]]:
        """
        Compute the cash flow for this model instance.
        """
        resolved_value = self.value
        if self.reference and lookup_fn:
            resolved_reference = self.resolve_reference(lookup_fn)
            if self.unit_of_measure == UnitOfMeasureEnum.PER_UNIT and isinstance(resolved_reference, (int,float)):
                 resolved_value = self.value * resolved_reference
            # Other reference-based calculations would go here
        
        monthly_value = self._convert_frequency(resolved_value)
        return self._cast_to_flow(monthly_value) 