from enum import Enum
from typing import Annotated, Literal, Optional, Union

import numpy as np
import pandas as pd
from pydantic import Field

from ..utils.types import FloatBetween0And1, PositiveFloat, PositiveInt
from .cash_flow import CashFlowModel
from .model import Model
from .program import Program

###########################
######### REVENUE #########
###########################


class RevenueCategoryEnum(str, Enum):
    """Enum for revenue categories"""

    sale = "Sale"
    lease = "Lease"
    # TODO: make category models with subcategories built-in (and maybe a hierarchy)


class RevenueSubcategoryEnum(str, Enum):
    """Enum for revenue subcategories"""

    # TODO: develop more subcategories


class RevenueMultiplicandEnum(str, Enum):
    """Enum for program unit kinds (what is being multiplied against)"""

    whole = "Whole Unit"
    rsf = "RSF"  # rentable square feet
    parking_space = "Parking Space"
    other = "Other"


class RevenueItem(CashFlowModel):  # use abstract class?
    """Class for a generic revenue line item"""

    # GENERAL
    category: Literal["Revenue"] = "Revenue"
    subcategory: Literal["Sale", "Lease"]  # "Sale" or "Lease"
    # subcategory: Optional[str] = None  # TBD use, maybe: unit type, use, etc.

    # PROGRAM
    program: Program  # program generating the revenue

    # REVENUE
    # revenue_multiplicand: RevenueMultiplicandEnum  # whole unit, rsf, parking space, etc.
    revenue_multiplicand: Literal["Whole Unit", "RSF", "Parking Space", "Other"]
    revenue_multiplier: (
        PositiveFloat  # sales: $/{unit,space}; rental: $/{unit,rsf,space}/mo
    )


class SalesRevenueItem(RevenueItem):
    """Class for a sales revenue line item"""

    # GENERAL
    subcategory: Literal["Sale"]
    # REVENUE/SALES SCHEDULE
    revenue_sched_kind: Literal["s-curve", "uniform", "manual"]
    revenue_sched_sigma: Optional[PositiveFloat]
    # revenue_sched_manual: Optional[np.ndarray]  # full cash flow manual input

    # TODO: if Program uses units, then revenue CF is a function of unit count and price
    # thus the revenue schedule is a function of the program timeline and unit count
    # if Program uses area, then revenue CF is a function of area and price

    # TODO: revisit pre-sales logic

    @property
    def revenue_total(self) -> PositiveFloat:
        # compute multiplier based on multiplicand
        if self.revenue_multiplicand in ("Whole Unit", "Parking Space"):
            return self.revenue_multiplier * self.program.unit_count
        elif self.revenue_multiplicand == "RSF":
            return self.revenue_multiplier * self.program.net_area
        else:  # "Other" TODO: revisit this logic
            return self.revenue_multiplier * 1.0

    @property
    def revenue_df(self) -> pd.DataFrame:
        """Construct cash flow for sales revenue with categories and subcategories"""
        # TODO: curve shaping
        # TODO: schedule by unit if applicable (discrete distribution function), not just dollars
        # uniform sales, for now:
        cf = pd.Series(
            np.ones(self.active_duration) * self.revenue_total / self.active_duration,
            index=self.timeline_active,
        )
        df = pd.DataFrame(cf)
        # add name, category and subcategory columns
        df["Name"] = self.name
        df["Category"] = self.category
        df["Subcategory"] = self.subcategory
        df["Use"] = self.program.use  # "Residential", "Office", "Retail", etc.
        return df


class RentalRevenueItem(RevenueItem):
    """Class for a rental revenue line item"""

    # FIXME: revisit pre-lease, lease-up pace logic
    # TODO: full lease config (lease-up, rollover, downtime, LC, TI, etc.)

    # GENERAL
    subcategory: Literal["Lease"]
    # TIMING
    active_duration: PositiveInt = (
        30 * 12
    )  # default 30 years (in months) - effectively infinite
    # RENTAL GROWTH
    revenue_growth_rate: FloatBetween0And1 = 0.03  # rental growth, simple annual
    # STRUCTURAL LOSSES
    vacancy_rate: FloatBetween0And1 = 0.05  # 5% vacancy/credit loss rate

    @property
    def initial_rent_rate(self) -> PositiveFloat:
        # compute multiplier based on multiplicand
        if self.revenue_multiplicand in ("Whole Unit", "Parking Space"):
            return (
                self.revenue_multiplier * self.program.unit_count
            )  # $/unit/mo -> $/mo
        elif self.revenue_multiplicand == "RSF":
            return self.revenue_multiplier * self.program.net_area  # $/sf/mo -> $/mo
        else:  # "Other" TODO: revisit this logic
            return self.revenue_multiplier * 1.0  # $/mo

    @property
    def revenue_df(self) -> pd.DataFrame:
        """Construct cash flow for rental revenue, with growth, with categories and subcategories"""
        # build rental cash flow from initial rent and growth rate
        growth_factors = np.ones(self.active_duration)
        growth_factors[12::12] = (
            1 + self.revenue_growth_rate
        )  # Apply growth factor at the beginning of each year after the first year
        cumulative_growth = np.cumprod(growth_factors)
        monthly_rents = self.initial_rent_rate * cumulative_growth
        cf = pd.Series(monthly_rents, index=self.timeline_active)
        df = pd.DataFrame(cf)
        # add name, category and subcategory columns
        df["Name"] = self.name
        df["Category"] = self.category
        df["Subcategory"] = self.subcategory
        df["Use"] = self.program.use  # "Residential", "Office", "Retail", etc.
        return df
        # FIXME: concatenate a vacancy/credit loss schedule df, if applicable

    # THIS IS TOTAL POTENTIAL INCOME

    @property
    def structural_losses_df(self) -> pd.Series:
        """Construct cash flow for vacancy/credit losses"""
        cf = self.revenue_df[0] * self.vacancy_rate
        df = pd.DataFrame(cf)
        # add name, category and subcategory columns
        df["Name"] = self.name
        df["Category"] = "Losses"
        df["Subcategory"] = self.subcategory
        df["Use"] = self.program.use  # "Residential", "Office", "Retail", etc.
        return df

    # THIS IS (THE DELTA FOR) EFFECTIVE GROSS REVENUE


AnyRevenueItem = Union[SalesRevenueItem, RentalRevenueItem]


class Revenue(Model):
    """Wrapper class for revenue items"""

    # REVENUE
    revenue_items: list[
        Annotated[AnyRevenueItem, Field(..., discriminator="subcategory")]
    ]

    # TODO: apply sales commissions at Project level (disposition cost of sales too)

    @property
    def revenue_df(self) -> pd.DataFrame:
        return pd.concat([item.revenue_df for item in self.revenue_items])
        # TODO: just use a list for performance? (pd.concat copies data...)

    @property
    def structural_losses_df(self) -> pd.Series:
        return pd.concat(
            [
                item.structural_losses_df
                for item in self.revenue_items
                if hasattr(item, "structural_losses_df")
            ]
        )

    # TODO: relationships between revenue and program (e.g., revenue per unit, sf, etc.)

    @property
    def program_summary(self) -> pd.DataFrame:
        """Summarize programs in the revenue items"""
        programs = list(
            set([item.program for item in self.revenue_items])
        )  # unique programs
        return pd.DataFrame(
            [
                {
                    "Use": program.use,
                    "Gross Area": program.gross_area,
                    "Net Area": program.net_area,
                    "Unit Count": program.unit_count,
                }
                for program in programs
            ]
        )

    # TODO: trended vs untrended revenue metrics (parameterize year?)
    # method to get summary metrics with time (toward getting  trended vs untrended)
