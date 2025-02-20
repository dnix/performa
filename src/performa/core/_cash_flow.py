from typing import Optional

import pandas as pd

from ..development._model import Model
from ._types import PositiveInt

########################
######### TIME #########
########################


class CashFlowModel(Model):
    """Class for a generic cash flow description"""

    # GENERAL
    name: str  # "Construction Cost"
    category: str  # category of the item (budget, revenue, expense, etc.)
    subcategory: str  # subcategory of the item (land, hard costs, soft costs, condo sales, apartment rental, etc.)
    notes: Optional[str] = None  # optional notes on the item

    # TIMELINE
    periods_until_start: PositiveInt  # months, from global start date of project
    active_duration: PositiveInt  # months

    @property
    def start_date(self) -> pd.Period:
        """Return the global start date (month zero)"""
        return pd.Period(ordinal=0, freq="M")

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
        return pd.period_range(
            self.start_date + self.periods_until_start,
            periods=self.active_duration,
            freq="M",
        )

    # TODO: consider property casting index to pd.DatetimeIndex from pd.PeriodIndex for later use but try to keep convenience of pd.PeriodIndex
