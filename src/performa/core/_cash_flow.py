from abc import ABC, abstractmethod
from datetime import date
from typing import Callable, Dict, List, Optional, Union
from uuid import UUID, uuid4

import pandas as pd
from pydantic import Field, FieldValidationInfo, field_validator

from ..asset._growth_rates import GrowthRate
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
            - str: Identifier expected to be resolved by `lookup_fn`. Can be:
                - A property attribute name (e.g., "net_rentable_area").
                - The string value of an `AggregateLineKey` enum member (e.g., "Net Operating Income").
            - UUID: The `model_id` of another `CashFlowModel` instance. `lookup_fn` is expected
              to resolve this to the computed cash flow result (often a pd.Series) of that other model instance.
            The resolution logic and handling of the returned type (scalar vs. Series) are handled
            by the `lookup_fn` provided during computation and potentially overridden in the 
            `compute_cf` method of subclasses.
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
        lookup_fn: Optional[Callable[[Union[str, UUID]], Union[float, pd.Series, Dict, None]]] = None
    ) -> Optional[Union[float, pd.Series, Dict]]:
        """
        Resolves the reference attribute using the provided lookup function.
        
        - If the reference is a direct value (numeric, Series, Dict), returns it directly.
        - If it is a string identifier (e.g., "net_rentable_area") or a UUID
          (referencing another model's `model_id`), it calls the provided `lookup_fn`.
          
        Args:
            lookup_fn: A callable that accepts a string or UUID and returns the
                corresponding resolved value (float, Series, Dict, None). The implementation
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
        Convert the value from its original frequency (e.g., annual) to monthly.
        
        - If the frequency is ANNUAL, a conversion factor of 1/12 is used.
        - For pandas Series:
            - If the index is detected as annual (PeriodIndex freq 'A' or DatetimeIndex inferred 'A'),
              it's assumed the values represent annual totals. The Series is upsampled to monthly,
              and the annual values are divided by 12 and distributed evenly across the months
              of their respective year.
            - Otherwise (e.g., monthly or other frequencies), the values are simply multiplied
              by the conversion factor (1 for monthly, 1/12 for annual).
        - For dicts, keys are assumed convertible to monthly periods, and values are multiplied
          by the conversion factor.
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
            is_period_index = isinstance(value.index, pd.PeriodIndex)
            is_datetime_index = isinstance(value.index, pd.DatetimeIndex)

            if is_period_index:
                index_freq = value.index.freqstr
            elif is_datetime_index:
                # Ensure index is sorted for reliable frequency inference and resampling
                value = value.sort_index()
                index_freq = pd.infer_freq(value.index)
            
            if index_freq and index_freq.startswith("A"):
                # Convert annual Series to monthly by distributing value/12
                
                # Ensure we have a DatetimeIndex for resampling
                if is_period_index:
                    # Ensure start_time aligns with the beginning of the year for proper month distribution
                    ts_index = value.index.to_timestamp(freq='M', how='start').normalize() 
                else: # Already DatetimeIndex
                    ts_index = value.index.normalize()
                    
                temp_series = pd.Series(value.values, index=ts_index)
                
                # Upsample to daily first to easily find year boundaries, then resample to monthly
                # Fill NaNs with 0 temporarily before dividing
                daily_upsampled = temp_series.resample('D').ffill().fillna(0) 
                
                # Assign the divided value to each day within the year
                daily_distributed = daily_upsampled / daily_upsampled.groupby(daily_upsampled.index.year).transform('size') * 12

                # Resample daily to monthly, summing the daily distributed values
                monthly_series = daily_distributed.resample('M').sum()
                
                # Convert the index back to a monthly PeriodIndex
                monthly_series.index = monthly_series.index.to_period("M")
                return monthly_series
            else:
                # Apply simple conversion factor for non-annual or undetected frequencies
                return value * conversion_factor

        elif isinstance(value, dict):
            # Assumes keys are monthly periods or convertible
            return {k: v * conversion_factor for k, v in value.items()}

        return value # Should not be reached for supported types

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
        elif isinstance(v, pd.Series):
             # Validate Series index type
             if not isinstance(v.index, (pd.PeriodIndex, pd.DatetimeIndex)):
                  raise ValueError(
                       "Series value must have a PeriodIndex or DatetimeIndex."
                  )
             # Ensure index is monotonic increasing if it's a DatetimeIndex
             # PeriodIndex is implicitly sorted
             if isinstance(v.index, pd.DatetimeIndex) and not v.index.is_monotonic_increasing:
                  raise ValueError("DatetimeIndex must be monotonic increasing.")
                  
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

    def _apply_compounding_growth(
        self,
        base_series: pd.Series,
        growth_profile: GrowthRate,
        growth_start_date: date
    ) -> pd.Series:
        """
        Apply compounding growth to a base cash flow series.

        Handles constant (annual float), pandas Series, and dictionary-based growth profiles.
        The growth is applied month-over-month starting from the `growth_start_date`.

        **Assumptions & Behavior:**
        - Base series index must be a monthly `pd.PeriodIndex` or convertible to one.
        - Constant float rates (`growth_profile.value`) are assumed to be **annual** and 
          are automatically converted to monthly (divided by 12) for compounding.
        - Rates in `pd.Series` or `dict` values (`growth_profile.value`) are assumed 
          to be **already at the intended frequency** for their respective periods (typically monthly).
          For example, if a Series has a monthly PeriodIndex, the rates are assumed to be monthly rates.
          The method aligns these to the base series' monthly timeline using forward-fill 
          (filling NaNs before the first rate with 0%). No automatic annual-to-monthly 
          conversion is performed for Series/Dict rates.
        - Growth is applied starting from the **period containing** `growth_start_date`.
        
        Args:
            base_series: The un-grown, period-indexed series (monthly).
            growth_profile: The GrowthRate object containing the rate definition.
            growth_start_date: The date from which compounding should begin.
            
        Returns:
            A new pandas Series with compounding growth applied.
            
        Raises:
            TypeError: If the growth_profile.value is an unsupported type.
            ValueError: If base_series index is not a PeriodIndex.
        """
        if not isinstance(base_series.index, pd.PeriodIndex):
            # Ensure the index is a PeriodIndex for reliable period arithmetic
            try:
                base_series.index = pd.PeriodIndex(base_series.index, freq='M')
            except ValueError:
                raise ValueError("Base series index must be convertible to a monthly PeriodIndex.")
                
        if not pd.api.types.is_numeric_dtype(base_series):
             raise ValueError("Base series must have numeric dtype to apply growth.")

        grown_series = base_series.copy()
        periods = base_series.index
        growth_start_period = pd.Period(growth_start_date, freq=periods.freq)
        
        # Create mask for periods on or after the growth start date
        growth_mask = periods >= growth_start_period
        
        if not growth_mask.any():
            return grown_series # No growth applicable within the series timeline

        growth_value = growth_profile.value
        
        # --- Prepare Period-Based Growth Rates --- 
        period_rates = pd.Series(0.0, index=periods) # Initialize with 0% growth
        
        if isinstance(growth_value, (float, int)):
            # Constant annual rate - convert to monthly
            monthly_rate = float(growth_value) / 12.0
            period_rates[growth_mask] = monthly_rate
        elif isinstance(growth_value, pd.Series):
            # Align growth series to base series timeline (monthly)
            aligned_rates = growth_value
            # Ensure growth series index is PeriodIndex
            if not isinstance(aligned_rates.index, pd.PeriodIndex):
                 # Attempt conversion assuming date-like keys
                 try:
                      aligned_rates.index = pd.PeriodIndex(aligned_rates.index, freq='M')
                 except Exception as e:
                      raise ValueError("Growth Series index must be convertible to PeriodIndex.") from e
            # Reindex and forward-fill rates
            aligned_rates = aligned_rates.reindex(periods, method='ffill')
            aligned_rates = aligned_rates.fillna(0.0) # Fill any remaining NaNs (e.g., before first rate) with 0%
            # Convert annual rates in series to monthly if necessary (Assume annual if not specified otherwise? Needs clarification or explicit flag in GrowthRate)
            # **Decision:** Assume rates in Series/Dict are *already at the intended frequency* (e.g., monthly if index is monthly). 
            # If annual rates are provided in a Series, they should be pre-converted to monthly by the user.
            # annual_to_monthly_factor = 1/12 # Example if conversion was needed
            period_rates[growth_mask] = aligned_rates[growth_mask] # * annual_to_monthly_factor 
        elif isinstance(growth_value, dict):
            # Convert dict to series and align
            try:
                 dict_series = pd.Series(growth_value)
                 dict_series.index = pd.PeriodIndex(dict_series.index, freq='M')
            except Exception as e:
                 raise ValueError("Growth Dict keys must be convertible to PeriodIndex.") from e
            # Reindex and forward-fill rates
            aligned_rates = dict_series.reindex(periods, method='ffill')
            aligned_rates = aligned_rates.fillna(0.0)
            # Assume rates are already monthly if dict keys are dates/periods
            # If annual rates are provided via dict, they should be pre-converted.
            period_rates[growth_mask] = aligned_rates[growth_mask]
        else:
            raise TypeError(f"Unsupported type for GrowthRate value: {type(growth_value)}")
            
        # --- Apply Compounding Growth --- 
        # Calculate period-over-period growth factors (1 + monthly_rate)
        growth_factors = 1.0 + period_rates
        
        # Calculate cumulative growth factors starting from the growth_start_period
        # Initialize cumulative factor series
        cumulative_factors = pd.Series(1.0, index=periods)

        # Find the integer index location of the start period
        try:
            start_idx_loc = periods.get_loc(growth_start_period)
        except KeyError:
             # Start period is outside the series index, no growth applies
             return grown_series 

        # Iterate from the start index location
        for i in range(start_idx_loc, len(periods)):
            if i == start_idx_loc:
                # First period's factor is just (1 + rate[start_idx_loc])
                cumulative_factors.iloc[i] = growth_factors.iloc[i]
            else:
                # Subsequent periods: previous cumulative factor * current period factor
                cumulative_factors.iloc[i] = cumulative_factors.iloc[i-1] * growth_factors.iloc[i]

        # Apply cumulative factors only to periods on or after the start date
        # The factor for periods *before* start_idx_loc remains 1.0
        grown_series[growth_mask] = base_series[growth_mask] * cumulative_factors[growth_mask]
        
        return grown_series
