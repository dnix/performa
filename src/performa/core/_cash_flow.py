from datetime import date
from typing import List, Optional, Union

import pandas as pd

from ._model import Model
from ._timeline import Timeline

########################
######### TIME #########
########################


class CashFlowModel(Model):
    """
    Base class for any cash flow description.
    
    Uses Timeline for date/period handling while focusing on cash flow specific logic.
    All cash flows use monthly frequency internally.
    
    Attributes:
        name: Name of the cash flow item
        category: Category of the item (budget, revenue, expense, etc.)
        subcategory: Subcategory of the item (land, hard costs, soft costs, condo sales, apartment rental, etc.)
        notes: Optional notes
        timeline: Timeline configuration for the cash flows
    """

    # GENERAL
    name: str  # "Construction Cost"
    category: str  # category of the item (budget, revenue, expense, etc.)
    subcategory: str  # subcategory of the item (land, hard costs, soft costs, condo sales, apartment rental, etc.)
    notes: Optional[str] = None  # optional notes on the item

    # TIMELINE
    timeline: Timeline

    @property
    def is_relative(self) -> bool:
        """Check if cash flow uses relative timeline"""
        return self.timeline.is_relative

    # Timeline delegation methods
    @property
    def start_date(self) -> pd.Period:
        """Get start date from timeline"""
        return self.timeline.start_date
    
    @property
    def end_date(self) -> pd.Period:
        """Get end date from timeline"""
        return self.timeline.end_date

    @property
    def period_index(self) -> pd.PeriodIndex:
        """Get period index from timeline"""
        return self.timeline.period_index

    @property
    def date_index(self) -> pd.DatetimeIndex:
        """Get datetime index from timeline"""
        return self.timeline.date_index

    def align_series(self, series: pd.Series) -> pd.Series:
        """Align a series to this cash flow's period index"""
        return self.timeline.align_series(series)

    def relative_period(self, months_offset: int) -> pd.Period:
        """Get a period relative to start_date"""
        return self.timeline.relative_period(months_offset)

    def resample(self, freq: str) -> pd.DatetimeIndex:
        """Resample cash flow timeline to a different frequency"""
        return self.timeline.resample(freq)

    def shift_to_index(self, reference_index: Union[pd.PeriodIndex, pd.DatetimeIndex]) -> None:
        """
        Shift cash flow timeline to align with a reference index.
        
        Args:
            reference_index: Index to align with
        """
        self.timeline.shift_to_index(reference_index)

    # Aggregation methods
    # TODO: revisit these methods when starting to implement cash flow aggregation
    def sum_by_category(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Sum cash flows by category.
        
        Args:
            df: DataFrame with Category column and values to sum
            
        Returns:
            DataFrame with periods as index and categories as columns
        """
        return df.pivot_table(
            values=0,
            index=self.period_index,
            columns=["Category"],
            aggfunc="sum"
        ).fillna(0)

    def sum_by_subcategory(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Sum cash flows by subcategory within category.
        
        Args:
            df: DataFrame with Category and Subcategory columns and values to sum
            
        Returns:
            DataFrame with periods as index and (category, subcategory) as columns
        """
        return df.pivot_table(
            values=0,
            index=self.period_index,
            columns=["Category", "Subcategory"],
            aggfunc="sum"
        ).fillna(0)

    # Factory methods
    @classmethod
    def from_dates(
        cls,
        name: str,
        category: str,
        subcategory: str,
        start_date: Union[date, pd.Period],
        end_date: Union[date, pd.Period],
        notes: Optional[str] = None,
    ) -> "CashFlowModel":
        """Create cash flow model from start and end dates"""
        timeline = Timeline.from_dates(
            start_date=start_date,
            end_date=end_date,
        )
        
        return cls(
            name=name,
            category=category,
            subcategory=subcategory,
            timeline=timeline,
            notes=notes
        )

    @classmethod
    def from_relative(
        cls,
        name: str,
        category: str,
        subcategory: str,
        months_until_start: int = 0,
        active_duration: int = 1,
        notes: Optional[str] = None,
    ) -> "CashFlowModel":
        """Create cash flow model using relative timing"""
        timeline = Timeline.from_relative(
            months_until_start=months_until_start,
            duration_months=active_duration
        )
        
        return cls(
            name=name,
            category=category,
            subcategory=subcategory,
            timeline=timeline,
            notes=notes
        )

    @classmethod
    def align_multiple(
        cls,
        cash_flows: List["CashFlowModel"],
        reference_index: Optional[Union[pd.PeriodIndex, pd.DatetimeIndex]] = None
    ) -> pd.PeriodIndex:
        """
        Align multiple cash flows to a common timeline.
        If no reference_index provided, uses the earliest start and latest end across all cash flows.
        
        Args:
            cash_flows: List of cash flows to align
            reference_index: Optional reference index to align to
            
        Returns:
            Common PeriodIndex for all cash flows
        """
        if not reference_index:
            # Find common timeline from all cash flows
            start = min(cf.start_date for cf in cash_flows)
            end = max(cf.end_date for cf in cash_flows)
            reference_index = pd.period_range(start=start, end=end, freq="M")
        
        # Shift all relative cash flows to reference timeline
        for cf in cash_flows:
            if cf.is_relative:
                cf.shift_to_index(reference_index)
                
        return reference_index

    # TODO: consider property casting index to pd.DatetimeIndex from pd.PeriodIndex for later use but try to keep convenience of pd.PeriodIndex
