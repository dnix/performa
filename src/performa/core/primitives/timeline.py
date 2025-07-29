# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import date
from typing import Any, Optional, Union

import pandas as pd
from pydantic import Field, computed_field, field_validator, model_validator

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
            if (start_date is None and start_offset is None) or \
               (start_date is not None and start_offset is not None):
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
            raise ValueError("Cannot get a start date from a relative timeline. It must be shifted first.")
        return self.start_date

    @computed_field
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
        return pd.period_range(
            start=start, periods=self.duration_months, freq="M"
        )

    @property
    def date_index(self) -> pd.DatetimeIndex:
        """Generate a DatetimeIndex for the timeline (only for absolute timelines)."""
        return self.period_index.to_timestamp()

    def align_series(self, series: pd.Series) -> pd.Series:
        """
        Align a series to this timeline's period index (only for absolute timelines).
        
        Validates that the input series has a monthly PeriodIndex before aligning.
        For DatetimeIndex, converts to monthly PeriodIndex first.
        
        Args:
            series: Series to align (must have monthly frequency)
            
        Returns:
            Series aligned to timeline's period index
            
        Raises:
            ValueError: If series doesn't have appropriate monthly frequency
        """
        period_index = self.period_index  # Will raise ValueError if relative
        
        # Handle DatetimeIndex by converting to PeriodIndex
        if isinstance(series.index, pd.DatetimeIndex):
            series = series.copy()
            series.index = series.index.to_period(freq="M")
        
        # Validate monthly PeriodIndex
        validate_monthly_period_index(series, field_name="series to align")
        
        return series.reindex(period_index)

    def resample(self, freq: str) -> pd.PeriodIndex:
        """Resample timeline to a different frequency (only for absolute timelines)."""
        return self.period_index.asfreq(freq, how='start').unique()

    @classmethod
    def from_dates(
        cls,
        start_date: Union[date, pd.Period],
        end_date: Union[date, pd.Period],
    ) -> "Timeline":
        """Create an absolute timeline from start and end dates."""
        start_period = pd.Period(start_date, freq="M")
        end_period = pd.Period(end_date, freq="M")
        duration = (end_period.year - start_period.year) * 12 + (end_period.month - start_period.month) + 1
        return cls(start_date=start_period, duration_months=duration)

    @classmethod
    def from_relative(
        cls,
        months_until_start: int,
        duration_months: int,
    ) -> "Timeline":
        """Create a relative timeline using an offset and duration."""
        return cls(start_offset_months=months_until_start, duration_months=duration_months)

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
