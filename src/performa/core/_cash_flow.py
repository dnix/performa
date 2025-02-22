from abc import ABC, abstractmethod
from typing import Callable, Optional, Union
from uuid import uuid4

import pandas as pd

from ._enums import FrequencyEnum, UnitOfMeasureEnum
from ._model import Model
from ._timeline import Timeline
from ._types import PositiveFloat


class CashFlowStrategy(ABC):
    @abstractmethod
    def compute(self, cash_flow_model: "CashFlowModel") -> Union[float, pd.Series]:
        """Compute the cash flow based on the model's state."""
        pass


class DirectAmountStrategy(CashFlowStrategy):
    def compute(self, cash_flow_model: "CashFlowModel") -> Union[float, pd.Series]:
        # Return the value stored on the model directly.
        return cash_flow_model.value


class UnitizedStrategy(CashFlowStrategy):
    def __init__(self, reference: Union[float, pd.Series]):
        self.reference = reference

    def compute(self, cash_flow_model: "CashFlowModel") -> Union[float, pd.Series]:
        # Multiply the per-unit rate with the resolved reference (e.g., rentable area).
        return cash_flow_model.value * self.reference


class PercentFactorStrategy(CashFlowStrategy):
    def __init__(self, reference: Union[float, pd.Series]):
        self.reference = reference

    def compute(self, cash_flow_model: "CashFlowModel") -> Union[float, pd.Series]:
        # Apply the percentage or factor to the resolved reference.
        return cash_flow_model.value * self.reference


class CashFlowModel(Model):
    """
    Base class for any cash flow description.
    
    Uses Timeline for date/period handling while focusing on cash flow specific logic.
    All cash flows use monthly frequency internally.
    """

    # GENERAL
    name: str  # e.g., "Construction Cost"
    category: str  # category of the item (investment, budget, revenue, expense, etc.)
    subcategory: str  # subcategory of the item (land, hard costs, soft costs, etc.)
    description: Optional[str] = None  # optional description
    account: Optional[str] = None  # optional account number

    # TIMELINE
    timeline: Timeline

    # VALUE
    value: Union[PositiveFloat, pd.Series]
    unit_of_measure: UnitOfMeasureEnum
    frequency: FrequencyEnum = FrequencyEnum.MONTHLY
    # An optional reference which might be a direct value, a Series,
    # or a string identifier for deferred resolution.
    reference: Optional[Union[float, pd.Series, str]] = None

    @property
    def id(self) -> str:
        """Unique identifier for the cash flow item."""
        return str(uuid4())

    @property
    def is_relative_timeline(self) -> bool:
        """Check if cash flow uses relative timeline."""
        return self.timeline.is_relative

    def resolve_reference(
        self,
        lookup_fn: Optional[Callable[[str], Union[float, pd.Series]]] = None
    ) -> Optional[Union[float, pd.Series]]:
        """
        Resolves the reference attribute.
        
        - If the reference is a numeric value or a pandas Series, returns it.
        - If it is a string identifier, uses the provided lookup function.
        """
        if isinstance(self.reference, (int, float, pd.Series)):
            return self.reference
        elif isinstance(self.reference, str):
            if lookup_fn is None:
                raise ValueError("A lookup function is required to resolve string references.")
            return lookup_fn(self.reference)
        return None

    def _convert_frequency(self, value: Union[float, pd.Series]) -> Union[float, pd.Series]:
        """
        Convert the value from its current frequency (e.g. annual) to monthly.
        """
        if self.frequency.name == "ANNUAL":
            conversion_factor = 1 / 12
        else:
            conversion_factor = 1
        if isinstance(value, (int, float)):
            return value * conversion_factor
        elif isinstance(value, pd.Series):
            return value * conversion_factor
        return value

    def _cast_to_flow(self, value: Union[float, pd.Series]) -> pd.Series:
        """
        Cast a scalar or series value into a full flow series spanning the model's timeline.
        """
        periods = self.timeline.period_index
        if isinstance(value, (int, float)):
            return pd.Series([value] * len(periods), index=periods)
        elif isinstance(value, pd.Series):
            return value.reindex(periods, fill_value=0)
        raise ValueError("Unsupported value type for casting to flow.")

    def align_flow_series(self, flow: pd.Series) -> pd.Series:
        """
        Align the provided flow series to the model's timeline via the Timeline helper.
        """
        return self.timeline.align_series(flow)

    def compute_cf(
        self,
        lookup_fn: Optional[Callable[[str], Union[float, pd.Series]]] = None
        # NOTE: consider functools.partial to pass callable to lookup_fn
    ) -> pd.Series:
        """
        Compute the final cash flow as a time series using the model's built-in timeline.
        
        This method performs these steps:
          - Resolves any reference required to compute the value.
          - Selects an appropriate strategy based on unit_of_measure.
          - Converts frequency as needed (for example, from annual to monthly).
          - Casts a scalar value into a full flow (time series) spanning self.timeline.
          - Aligns the resulting series using the Timeline helper.
          
        The returned series represents the cash flow over the model's timeline, which the orchestration
        layer can later align or stretch to match a global analysis timeframe.
        """
        resolved_reference = self.resolve_reference(lookup_fn)

        if self.unit_of_measure == UnitOfMeasureEnum.AMOUNT:
            strategy = DirectAmountStrategy()
        elif self.unit_of_measure == UnitOfMeasureEnum.PER_UNIT:
            if resolved_reference is None:
                raise ValueError("A reference is required for PER_UNIT calculations.")
            strategy = UnitizedStrategy(reference=resolved_reference)
        elif self.unit_of_measure in (UnitOfMeasureEnum.BY_FACTOR, UnitOfMeasureEnum.BY_PERCENT):
            if resolved_reference is None:
                raise ValueError("A reference is required for factor/percentage calculations.")
            strategy = PercentFactorStrategy(reference=resolved_reference)
        else:
            raise ValueError(f"Unsupported unit_of_measure: {self.unit_of_measure}")

        raw_value = strategy.compute(self)
        monthly_value = self._convert_frequency(raw_value)
        cash_flow_series = self._cast_to_flow(monthly_value)
        return self.align_flow_series(cash_flow_series)
