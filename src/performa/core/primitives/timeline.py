# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional, Union

import pandas as pd
from pydantic import field_validator, model_validator

from .model import Model
from .types import PositiveInt
from .validation import validate_monthly_period_index


class Timeline(Model):
    """
    Represents a timeline for financial analysis, which can be either absolute
    (tied to specific dates) or relative (tied to an offset from a master timeline).

    A timeline must be defined with either a `start_date` (for absolute timelines)
    or a `start_offset_months` (for relative timelines), but not both.

    Attributes:
        start_date: Analysis start date (for absolute timelines).
        start_offset_months: Month offset from a master timeline start (for relative timelines).
        duration_months: Length of timeline in months.

    Examples:
        Create an absolute timeline (most common usage):

        >>> import pandas as pd
        >>> from performa.core.primitives import Timeline
        >>>
        >>> # 24-month analysis starting January 2024
        >>> timeline = Timeline(
        ...     start_date=pd.Timestamp("2024-01-01"),
        ...     duration_months=24
        ... )
        >>> print(f"Timeline: {timeline.duration_months} months")
        Timeline: 24 months

        Create a relative timeline (for sub-analysis):

        >>> # 12-month period starting 6 months into master timeline
        >>> sub_timeline = Timeline(
        ...     start_offset_months=6,
        ...     duration_months=12
        ... )
        >>> print(f"Sub-timeline: offset {sub_timeline.start_offset_months}")
        Sub-timeline: offset 6

        IMPORTANT: Cannot specify both start_date and start_offset_months:

        >>> # This will raise ValueError
        >>> try:
        ...     Timeline(start_date=pd.Timestamp("2024-01-01"), start_offset_months=6)
        ... except ValueError as e:
        ...     print("Error:", str(e)[:50] + "...")
        Error: Timeline must be initialized with either 'start_...
    """

    start_date: Optional[pd.Period] = None
    start_offset_months: Optional[int] = None
    duration_months: PositiveInt

    @model_validator(mode="before")
    @classmethod
    def check_start_definition(cls, data: Any) -> Any:
        if isinstance(data, dict):
            start_date = data.get("start_date")
            start_offset = data.get("start_offset_months")
            if (start_date is None and start_offset is None) or (
                start_date is not None and start_offset is not None
            ):
                raise ValueError(
                    "Timeline must be initialized with either 'start_date' or 'start_offset_months', but not both."
                )
        return data

    @field_validator("start_date", mode="before")
    @classmethod
    def normalize_start_date(cls, v: Union[date, pd.Period]) -> pd.Period:
        """Ensure start_date is a monthly pd.Period."""
        if v is None:
            return None
        if isinstance(v, date):
            return pd.Period(v, freq="M")
        if isinstance(v, pd.Period) and v.freq != "M":
            return pd.Period(v.to_timestamp(), freq="M")
        return v

    @property
    def is_relative(self) -> bool:
        """Check if the timeline is relative (defined by an offset)."""
        return self.start_offset_months is not None

    def _get_absolute_start(self) -> pd.Period:
        """Internal helper to get the start date, raising error if relative."""
        if self.is_relative:
            raise ValueError(
                "Cannot get a start date from a relative timeline. It must be shifted first."
            )
        return self.start_date

    @property
    def end_date(self) -> pd.Period:
        """Calculate the end date based on duration (only for absolute timelines)."""
        start = self._get_absolute_start()
        if start is None:
            return None
        return start + (self.duration_months - 1)

    @property
    def period_index(self) -> pd.PeriodIndex:
        """Generate a monthly PeriodIndex for the timeline (only for absolute timelines)."""
        start = self._get_absolute_start()
        return pd.period_range(start=start, periods=self.duration_months, freq="M")

    @property
    def date_index(self) -> pd.DatetimeIndex:
        """Generate a DatetimeIndex for the timeline (only for absolute timelines)."""
        return self.period_index.to_timestamp()

    def align_series(self, series: pd.Series, fill_value: float = 0.0) -> pd.Series:
        """
        Align a series to this timeline's period index (only for absolute timelines).

        Enhanced with efficient pandas operations and configurable fill values.
        Automatically converts datetime.date and DatetimeIndex to PeriodIndex before aligning.

        Args:
            series: Series to align (any date-like index)
            fill_value: Value to use for missing periods (default: 0.0)

        Returns:
            Series aligned to timeline's period index with specified fill value

        Raises:
            ValueError: If series doesn't have appropriate monthly frequency
        """
        period_index = self.period_index  # Will raise ValueError if relative

        # Fast path for empty series
        if series.empty:
            return pd.Series(fill_value, index=period_index, name=series.name, dtype=float)

        # Handle datetime.date index (most common case in our system)
        if hasattr(series.index, '__getitem__') and len(series.index) > 0:
            import datetime
            if isinstance(series.index[0], datetime.date):
                series = series.copy()
                series.index = pd.PeriodIndex([pd.Period(d, 'M') for d in series.index], freq='M')

        # Handle DatetimeIndex by converting to PeriodIndex (pandas built-in)
        elif isinstance(series.index, pd.DatetimeIndex):
            series = series.copy()
            series.index = series.index.to_period(freq="M")

        # Validate monthly PeriodIndex
        validate_monthly_period_index(series, field_name="series to align")

        # Use pandas reindex with fill_value for efficiency
        return series.reindex(period_index, fill_value=fill_value)

    def resample(self, freq: str) -> pd.PeriodIndex:
        """Resample timeline to a different frequency (only for absolute timelines)."""
        return self.period_index.asfreq(freq, how="start").unique()

    @classmethod
    def from_dates(
        cls,
        start_date: Union[date, pd.Period],
        end_date: Union[date, pd.Period],
    ) -> "Timeline":
        """
        Create an absolute timeline from start and end dates.
        
        Uses pandas built-in period arithmetic for more robust calculation.
        """
        start_period = pd.Period(start_date, freq="M")
        end_period = pd.Period(end_date, freq="M")
        
        # Use pandas period arithmetic - more robust than manual calculation
        duration = len(pd.period_range(start=start_period, end=end_period, freq="M"))
        
        return cls(start_date=start_period, duration_months=duration)

    @classmethod
    def from_relative(
        cls,
        months_until_start: int,
        duration_months: int,
    ) -> "Timeline":
        """Create a relative timeline using an offset and duration."""
        return cls(
            start_offset_months=months_until_start, duration_months=duration_months
        )

    def shift_to_index(
        self, reference_index: Union[pd.PeriodIndex, pd.DatetimeIndex]
    ) -> "Timeline":
        """Creates a new, absolute timeline by shifting this relative timeline."""
        if not self.is_relative:
            raise ValueError("Can only shift relative timelines.")

        if isinstance(reference_index, pd.DatetimeIndex):
            reference_index = reference_index.to_period(freq="M")

        new_start_date = reference_index[0] + self.start_offset_months
        return Timeline(start_date=new_start_date, duration_months=self.duration_months)

    def clip_to(self, bounds: "Timeline") -> "Timeline":
        """
        Clip this timeline to fit within the bounds of another timeline.

        Uses pandas PeriodIndex.intersection() for efficient period overlap calculation.
        If this timeline already fits within the bounds, it is returned unchanged.

        Args:
            bounds: The timeline defining the clipping boundaries

        Returns:
            New Timeline clipped to the bounds, or self if no clipping needed

        Raises:
            ValueError: If either timeline is relative (both must be absolute)

        Example:
            ```python
            # 60-month lease starting Jan 2020
            lease_timeline = Timeline.from_dates('2020-01-01', '2024-12-31')

            # 24-month analysis period starting Jan 2024
            analysis_timeline = Timeline.from_dates('2024-01-01', '2025-12-31')

            # Clip lease to analysis period (Jan 2024 - Dec 2024)
            clipped = lease_timeline.clip_to(analysis_timeline)
            ```
        """
        if self.is_relative or bounds.is_relative:
            raise ValueError(
                "Cannot clip relative timelines. Both timelines must be absolute."
            )

        # Use pandas built-in intersection for period overlap
        intersection = self.period_index.intersection(bounds.period_index)

        # If no intersection, return empty timeline
        if len(intersection) == 0:
            raise ValueError("Timelines do not overlap - cannot clip")

        # If intersection equals original timeline, no clipping needed
        if len(intersection) == len(self.period_index):
            return self

        # Create new timeline from intersection
        return Timeline.from_dates(intersection[0], intersection[-1])

    def align_multiple(self, series_dict: Dict[str, pd.Series], fill_value: float = 0.0) -> pd.DataFrame:
        """
        Efficiently align multiple series to this timeline in one operation.
        
        This is more efficient than calling align_series multiple times
        when you have many series to align (common in DealResults).
        
        Args:
            series_dict: Dictionary mapping column names to Series
            fill_value: Value to use for missing periods (default: 0.0)
            
        Returns:
            DataFrame with all series aligned to timeline's period index
            
        Example:
            ```python
            timeline = Timeline.from_dates('2024-01-01', '2025-12-31')
            series_dict = {
                'NOI': noi_series,
                'CapEx': capex_series,
                'Debt Service': debt_service_series
            }
            aligned_df = timeline.align_multiple(series_dict)
            ```
        """
        period_index = self.period_index  # Will raise ValueError if relative
        
        # Fast path for empty input
        if not series_dict:
            return pd.DataFrame(index=period_index)
        
        # Use pandas concat for efficient alignment
        aligned_series = {}
        for name, series in series_dict.items():
            aligned_series[name] = self.align_series(series, fill_value=fill_value)
        
        return pd.DataFrame(aligned_series, index=period_index)

    @classmethod
    def for_deal_analysis(
        cls,
        start_date: Union[date, pd.Period],
        hold_period_years: Union[int, float],
    ) -> "Timeline":
        """
        Create a timeline optimized for deal analysis.
        
        Convenience method that handles common deal analysis timeline patterns.
        Uses month-end periods which are standard for real estate analysis.
        
        Args:
            start_date: Deal analysis start date
            hold_period_years: Hold period in years (can be fractional)
            
        Returns:
            Timeline configured for deal analysis
            
        Example:
            ```python
            # 5-year hold starting January 2024
            timeline = Timeline.for_deal_analysis('2024-01-01', 5.0)
            
            # 3.5-year hold for development deal  
            timeline = Timeline.for_deal_analysis('2024-06-01', 3.5)
            ```
        """
        start_period = pd.Period(start_date, freq="M")
        duration_months = int(hold_period_years * 12)
        
        return cls(start_date=start_period, duration_months=duration_months)

    @property
    def years_duration(self) -> float:
        """
        Duration in years (fractional).
        
        Useful for annualized calculations and IRR computations.
        
        Returns:
            Duration as fractional years (e.g., 2.5 for 30 months)
        """
        return self.duration_months / 12.0

    def contains_period(self, period: Union[pd.Period, date]) -> bool:
        """
        Check if a specific period falls within this timeline.
        
        Args:
            period: Period or date to check
            
        Returns:
            True if period is within timeline bounds
            
        Example:
            ```python
            timeline = Timeline.from_dates('2024-01-01', '2024-12-31')
            assert timeline.contains_period('2024-06-15')  # True
            assert not timeline.contains_period('2025-01-01')  # False
            ```
        """
        if self.is_relative:
            raise ValueError("Cannot check period containment for relative timeline")
            
        period_to_check = pd.Period(period, freq="M")
        return period_to_check in self.period_index


# =============================================================================
# FREQUENCY MAPPING UTILITIES
# =============================================================================

# Simple frequency mapping - works for all pandas operations
# Note: Deprecation warnings for Y/Q/M in resample are red herrings 
# (pandas team has no current plans to remove them)
FREQUENCY_MAPPING = {
    "A": "Y",   # Annual
    "Q": "Q",   # Quarterly
    "M": "M",   # Monthly
}

# Legacy alias (for backward compatibility)
PANDAS_FREQUENCY_MAPPING = FREQUENCY_MAPPING


def normalize_frequency(frequency: str) -> str:
    """
    Convert user-friendly frequency to pandas frequency alias.
    
    Args:
        frequency: User-friendly frequency ('A', 'Q', 'M')
        
    Returns:
        Pandas-compatible frequency string
        
    Note:
        Uses Y/Q/M forms which work for both resample and period operations.
        Resample operations may show deprecation warnings, but these are red herrings.
    """
    return FREQUENCY_MAPPING.get(frequency, frequency)
