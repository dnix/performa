from datetime import date
from typing import Union

import pandas as pd
from pydantic import BaseModel, model_validator

from ._types import PositiveInt


class Timeline(BaseModel):
    """
    Represents a timeline for financial analysis.
    
    Handles both absolute dates and relative periods, with utilities for conversion
    and alignment. All timelines use monthly frequency internally.
    
    Attributes:
        start_date: Analysis start date
        duration_months: Length of timeline in months
    """
    
    start_date: Union[date, pd.Period]
    duration_months: PositiveInt
    
    @model_validator(mode="after")
    def validate_and_normalize_dates(self) -> "Timeline":
        """Ensure dates are properly formatted and normalized to monthly periods"""
        if isinstance(self.start_date, date):
            self.start_date = pd.Period(self.start_date, freq="M")
        elif self.start_date.freq != "M":
            self.start_date = pd.Period(self.start_date.to_timestamp(), freq="M")
        return self

    @property
    def is_relative(self) -> bool:
        """Check if timeline is relative (based on ordinal 0) or absolute"""
        return self.start_date.ordinal == 0
    
    @property
    def end_date(self) -> pd.Period:
        """Calculate the end date based on duration"""
        return self.start_date + (self.duration_months - 1)
    
    @property
    def period_index(self) -> pd.PeriodIndex:
        """Generate a monthly PeriodIndex for the timeline"""
        return pd.period_range(
            start=self.start_date,
            periods=self.duration_months,
            freq="M"
        )
    
    @property
    def date_index(self) -> pd.DatetimeIndex:
        """Generate a DatetimeIndex for the timeline"""
        return self.period_index.to_timestamp()
    
    def align_series(self, series: pd.Series) -> pd.Series:
        """
        Align a series to this timeline's period index.
        
        Args:
            series: Input series with datetime or period index
            
        Returns:
            Series aligned to this timeline's period index
        """
        # Convert series index to monthly PeriodIndex if it's DatetimeIndex
        if isinstance(series.index, pd.DatetimeIndex):
            series.index = series.index.to_period(freq="M")
            
        # Reindex to match this timeline
        return series.reindex(self.period_index)
    
    def relative_period(self, months_offset: int) -> pd.Period:
        """Get a period relative to start_date"""
        return self.start_date + months_offset

    def resample(self, freq: str) -> pd.DatetimeIndex:
        """
        Resample timeline to a different frequency.
        Useful for reporting and visualization.
        
        Args:
            freq: Pandas frequency string ('Q', 'Y', etc.)
            
        Returns:
            Resampled DatetimeIndex
        """
        return self.date_index.to_period(freq).to_timestamp()

    @classmethod
    def from_dates(
        cls,
        start_date: Union[date, pd.Period],
        end_date: Union[date, pd.Period],
    ) -> "Timeline":
        """
        Create timeline from start and end dates.
        
        Args:
            start_date: Start of analysis period
            end_date: End of analysis period
            
        Returns:
            Timeline instance
        """
        # Convert to periods if dates
        start_period = pd.Period(start_date, freq="M")
        end_period = pd.Period(end_date, freq="M")
        
        # Calculate duration
        duration = (end_period - start_period) + 1
        
        return cls(
            start_date=start_period,
            duration_months=duration
        )

    @classmethod
    def from_relative(
        cls,
        months_until_start: int = 0,
        duration_months: int = 1,
    ) -> "Timeline":
        """
        Create timeline using relative timing.
        Uses ordinal period 0 as reference start and defines duration from there.
        
        Args:
            months_until_start: Months offset from reference start (default 0)
            duration_months: Duration in months (default 1)
            
        Returns:
            Timeline instance with relative timeline
        """
        reference_start = pd.Period(ordinal=0, freq="M")
        start_date = reference_start + months_until_start
        
        return cls(
            start_date=start_date,
            duration_months=duration_months
        )

    def shift_to_index(self, reference_index: Union[pd.PeriodIndex, pd.DatetimeIndex]) -> None:
        """
        Shift timeline to align with a reference index, modifying in place.
        Particularly useful for converting relative timelines to absolute ones.
        
        Args:
            reference_index: Index to align with. If DatetimeIndex, will be converted to PeriodIndex
        """
        if isinstance(reference_index, pd.DatetimeIndex):
            reference_index = reference_index.to_period(freq="M")
            
        # Calculate offset needed
        if self.is_relative:
            # For relative timelines, shift to start at reference_index start
            offset = reference_index[0].ordinal - self.start_date.ordinal
            self.start_date = pd.Period(ordinal=self.start_date.ordinal + offset, freq="M")
        else:
            raise ValueError("Can only shift relative timelines. This timeline is absolute.")

    @property
    def duration(self) -> pd.Timedelta:
        """Get timeline duration as Timedelta"""
        return pd.Timedelta(months=self.duration_months) 
