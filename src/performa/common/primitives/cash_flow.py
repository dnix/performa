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

if TYPE_CHECKING:
    from performa.analysis import AnalysisContext


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
    adjustments (like occupancy).
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
    reference: Optional[UUID] = None
    settings: GlobalSettings = Field(default_factory=GlobalSettings)
    growth_rate: Optional[GrowthRate] = None

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
        if not isinstance(flow.index, pd.PeriodIndex) or flow.index.freq != 'M':
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
        1.  Determines the base value of the cash flow, resolving dependencies
            if necessary (`PER_UNIT` or `BY_PERCENT`).
        2.  Converts the value to a monthly frequency.
        3.  Casts the value into a pandas Series spanning the item's timeline.
        4.  Applies compounding growth if a `growth_rate` is present.

        Subclasses can call this method via `super().compute_cf(context)` to
        get a fully calculated and grown base cash flow series, upon which they
        can apply their own specific modifications (e.g., occupancy adjustments).
        """
        base_value = self.value

        if self.unit_of_measure == UnitOfMeasureEnum.PER_UNIT:
            # Property-level reference for PER_UNIT is NRA
            nra = context.property_data.net_rentable_area
            if nra > 0:
                base_value = self.value * nra
            else:
                base_value = 0.0
        elif self.unit_of_measure == UnitOfMeasureEnum.BY_PERCENT and self.reference:
            # Dependency is on another cash flow, which must have been pre-computed
            # by the orchestrator and stored in the context.
            dependency_cf = context.resolved_lookups.get(self.reference)
            if dependency_cf is None:
                raise ValueError(f"Unresolved dependency for '{self.name}': {self.reference}")
            base_value = dependency_cf * self.value
        
        monthly_value = self._convert_frequency(base_value)
        base_series = self._cast_to_flow(monthly_value)

        if self.growth_rate:
            base_series = self._apply_compounding_growth(
                base_series=base_series, growth_rate=self.growth_rate
            )
        
        return base_series 