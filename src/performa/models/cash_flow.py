from typing import Optional
from pydantic import field_validator
import pandas as pd

from .model import Model
from ..utils.types import PositiveInt


########################
######### TIME #########
########################

class CashFlowItem(Model):
    """Class for a generic cash flow line item"""
    # GENERAL
    name: str  # "Construction Cost"
    category: str  # category of the item (budget, revenue, expense, etc.)
    subcategory: str  # subcategory of the item (land, hard costs, soft costs, condo sales, apartment rental, etc.)
    notes: Optional[str] = None  # optional notes on the item

    # TIMELINE
    start_date: pd.Period = pd.Period(ordinal=0, freq="M")  # month zero (need to shift to project start date)  # TODO: move to property? because not user-defined anymore
    periods_until_start: PositiveInt  # months, from global start date of project
    active_duration: PositiveInt  # months

    @property
    def total_duration(self) -> PositiveInt:
        """Total duration (number of periods) in months from global start date, including delay until start"""
        return self.periods_until_start + self.active_duration
    
    @property
    def timeline_total(self) -> pd.PeriodIndex:
        """Construct a timeline period index for total duration, including delay until start"""
        return pd.period_range(self.start_date, periods=self.total_duration, freq="M")
    
    @property
    def timeline_active(self) -> pd.PeriodIndex:
        """Construct a timeline period index for *active* duration only"""
        return pd.period_range(self.start_date + self.periods_until_start, periods=self.active_duration, freq="M")
        
    @field_validator("start_date", mode="before")
    def to_period(value) -> pd.Period:
        """Cast as a pandas period"""
        return pd.Period(value, freq="M")

    