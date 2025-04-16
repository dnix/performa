from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional, Union
from uuid import UUID, uuid4

import pandas as pd
from pydantic import Field, FieldValidationInfo, field_validator

from ..core._enums import FrequencyEnum, UnitOfMeasureEnum
from ._model import Model
from ._settings import GlobalSettings
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

    Attributes:
        model_id (UUID): Stable unique identifier for this model instance. Used for referencing
            the output of this model instance from other models.
        name (str): Name of the cash flow item (e.g., "Construction Cost").
        category (str): Category of the item (investment, budget, revenue, expense, etc.).
        subcategory (str): Subcategory of the item (land, hard costs, soft costs, etc.).
        description (Optional[str]): Optional description of the cash flow item.
        account (Optional[str]): Optional account number for reference.
        timeline (Timeline): Timeline object defining the dates/periods for the cash flow.
        value (Union[PositiveFloat, pd.Series, dict, list]): The cash flow value(s).
            The interpretation depends on `unit_of_measure` and potential `reference`.
        unit_of_measure (UnitOfMeasureEnum): Unit of measure for the value (e.g., currency, area).
            Determines the calculation strategy (DirectAmount, Unitized, PercentFactor).
        frequency (FrequencyEnum): Frequency of the cash flow, defaults to monthly. Used
            for potential conversion to internal monthly representation.
        reference (Optional[Union[float, pd.Series, str, UUID]]): Optional reference value or identifier
            used for relative calculations (e.g., PER_UNIT, BY_PERCENT).
            - float, pd.Series: Direct value used in calculation.
            - str: Identifier expected to be resolved by `lookup_fn` against a known namespace
              (e.g., property attributes like "net_rentable_area").
            - UUID: The `model_id` of another `CashFlowModel` instance. `lookup_fn` is expected
              to resolve this to the computed cash flow result of that other model instance.
            The resolution logic is handled by the `lookup_fn` provided during computation.
    """

    # GENERAL
    model_id: UUID = Field(default_factory=uuid4, description="Stable unique identifier for this model instance")
    name: str  # e.g., "Construction Cost"
    category: str  # category of the item (investment, budget, revenue, expense, etc.)
    subcategory: str  # subcategory of the item (land, hard costs, soft costs, etc.)
    description: Optional[str] = None  # optional description
    account: Optional[str] = None  # optional account number

    # TIMELINE
    timeline: Timeline

    # VALUE
    value: Union[PositiveFloat, pd.Series, Dict, List]
    unit_of_measure: UnitOfMeasureEnum
    frequency: FrequencyEnum = FrequencyEnum.MONTHLY
    reference: Optional[Union[float, pd.Series, str, UUID]] = None

    # SETTINGS
    settings: GlobalSettings = Field(default_factory=GlobalSettings)

    @property
    def runtime_id(self) -> str:
        """Unique runtime identifier for the cash flow item instance."""
        return str(uuid4())

    @property
    def is_relative_timeline(self) -> bool:
        """Check if cash flow uses relative timeline."""
        return self.timeline.is_relative

    def resolve_reference(
        self,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Union[float, pd.Series, Dict]]] = None
    ) -> Optional[Union[float, pd.Series, Dict]]:
        """
        Resolves the reference attribute using the provided lookup function.
        
        - If the reference is a direct value (numeric, Series, Dict), returns it directly.
        - If it is a string identifier (e.g., "net_rentable_area") or a UUID
          (referencing another model's `model_id`), it calls the provided `lookup_fn`.
          
        Args:
            lookup_fn: A callable that accepts a string or UUID and returns the
                corresponding resolved value (float, Series, Dict). The implementation
                of this function typically resides in the orchestration layer (e.g., CashFlowAnalysis)
                and needs access to the relevant context (property attributes, computed results registry).
                
        Returns:
            The resolved value (float, Series, Dict) or None if reference is None.
            
        Raises:
            ValueError: If a string or UUID reference is provided but `lookup_fn` is None.
            Exception: Potentially raises exceptions from the `lookup_fn` itself if resolution fails.
        """
        if isinstance(self.reference, (int, float, pd.Series, Dict)):
            return self.reference
        elif isinstance(self.reference, (str, UUID)):
            if lookup_fn is None:
                raise ValueError("A lookup function is required to resolve string or UUID references.")
            return lookup_fn(self.reference)
        return None

    def _convert_frequency(
        self, value: Union[float, pd.Series, Dict]
    ) -> Union[float, pd.Series, Dict]:
        """
        Convert the value from its current frequency (e.g. annual) to monthly.
        
        If the frequency is ANNUAL, a conversion factor of 1/12 is used.
        For pandas Series, if the index is identified as having an annual frequency,
        the series is upsampled to monthly frequency using resample and ffill.
        """
        if self.frequency.name == "ANNUAL":
            conversion_factor = 1 / 12
        else:
            conversion_factor = 1

        if isinstance(value, (int, float)):
            return value * conversion_factor

        elif isinstance(value, pd.Series):
            # Try to detect if the series has an annual frequency
            index_freq = None
            if isinstance(value.index, pd.PeriodIndex):
                index_freq = value.index.freqstr
            elif isinstance(value.index, pd.DatetimeIndex):
                index_freq = pd.infer_freq(value.index)
            
            if index_freq and index_freq.startswith("A"):
                # Convert to DatetimeIndex for resampling if necessary
                if isinstance(value.index, pd.PeriodIndex):
                    ts_index = value.index.to_timestamp()
                else:
                    ts_index = value.index
                temp_series = pd.Series(value.values, index=ts_index)
                # Upsample from annual to monthly using resample and ffill
                monthly_series = temp_series.resample("M").ffill()
                monthly_series = monthly_series * conversion_factor
                # Convert the index back to a monthly PeriodIndex
                monthly_series.index = monthly_series.index.to_period("M")
                return monthly_series
            else:
                return value * conversion_factor

        elif isinstance(value, dict):
            return {k: v * conversion_factor for k, v in value.items()}

        return value

    @field_validator("value")
    @classmethod
    def validate_value(
        cls, 
        v: Union[PositiveFloat, pd.Series, Dict, List], 
        info: FieldValidationInfo
    ) -> Union[PositiveFloat, pd.Series, Dict, List]:
        """
        Validate that the value is one of the allowed types.
        
        For dicts: Validate that keys can be converted to a monthly Period and that
        each value is numeric and positive.
        For lists: Validate that the list length matches the timeline period index length.
        """
        # NOTE: consider spinning this out as a reusable validator function/class
        if isinstance(v, dict):
            for key, amount in v.items():
                try:
                    pd.Period(key, freq="M")
                except Exception as e:
                    raise ValueError(
                        f"Invalid key in value dict: {key!r} cannot be converted to a monthly period."
                    ) from e
                if not isinstance(amount, (int, float)):
                    raise ValueError(
                        f"Invalid value for key {key!r}: Must be numeric, got {type(amount).__name__}."
                    )
                if amount <= 0:
                    raise ValueError(
                        f"Invalid value for key {key!r}: Must be positive, got {amount}."
                    )
        elif isinstance(v, list):
            timeline = info.data.get("timeline")
            if timeline is None:
                raise ValueError("Timeline must be provided for list type values.")
            expected_length = len(timeline.period_index)
            if len(v) != expected_length:
                raise ValueError(
                    f"List length {len(v)} does not match timeline length {expected_length}."
                )
        # TODO: more validation, e.g., for Series, check that the index is a PeriodIndex
        return v

    def _cast_to_flow(
        self, value: Union[float, pd.Series, Dict, List]
    ) -> pd.Series:
        """
        Cast a scalar, pandas Series, dict, or list value into a full flow series spanning the model's timeline.
        
        For a dict, the keys are expected to be dates (or strings representing dates) that can be converted to a
        PeriodIndex with monthly frequency.
        
        For a list, the list is directly cast to a pandas Series using the timeline's period index.
        """
        periods = self.timeline.period_index
        if isinstance(value, dict):
            try:
                flow_series = pd.Series(value)
                # Convert the index to a PeriodIndex if necessary.
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
            return value.reindex(periods, fill_value=0)
        elif isinstance(value, list):
            return pd.Series(value, index=periods)
        else:
            raise ValueError("Unsupported value type for casting to flow.")

    def align_flow_series(self, flow: pd.Series) -> pd.Series:
        """
        Align the provided flow series to the model's timeline via the Timeline helper.
        """
        return self.timeline.align_series(flow)

    def compute_cf(
        self,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Union[float, pd.Series]]] = None # Updated lookup_fn type hint
        # NOTE: consider functools.partial to pass callable to lookup_fn
    ) -> pd.Series:
        """
        Compute the final cash flow as a time series using the model's built-in timeline.
        
        This method performs these steps:
          - Resolves any reference required to compute the value using the lookup_fn.
          - Selects an appropriate strategy based on unit_of_measure.
          - Converts frequency as needed (e.g. from annual to monthly).
          - Casts the resulting value into a full flow series spanning the timeline.
          - Aligns the resulting series using the Timeline helper.
          
        The returned series represents the cash flow over the model's timeline.
        """
        # Pass the potentially complex lookup_fn down
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
