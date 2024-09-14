from typing import Literal, Optional

import numpy as np
import pandas as pd
from scipy.stats import norm

from ..utils.types import PositiveFloat, PositiveInt
from .cash_flow import CashFlowModel
from .model import Model

##########################
######### BUDGET #########
##########################


class BudgetItem(CashFlowModel):
    """Class for a generic cost line item"""

    # TODO: subclass for specific budget line items (Developer, A&E, Soft Costs, FF&E, Other)
    # TODO: add optional details list for more granular budgeting (i.e., rolling-up to a parent budget item)
    # GENERAL
    category: Literal["Budget"] = "Budget"
    subcategory: Literal["Land", "Hard Costs", "Soft Costs", "Other"]
    # subcategory: Optional[BudgetSubcategoryEnum] = None

    # COST
    cost_total: PositiveFloat  # 1_000_000.00
    # DRAW SCHEDULE
    draw_sched_kind: Literal[
        "s-curve", "uniform", "manual"
    ]  # TODO: use enum? add triang? others?
    draw_sched_sigma: Optional[PositiveFloat]  # more info for s-curve (and others?)
    # draw_sched_manual: Optional[np.ndarray]  # full cash flow manual input

    @property
    def budget_df(self) -> pd.DataFrame:
        """Construct cash flow for budget costs with categories and subcategories"""
        if self.draw_sched_kind == "s-curve":
            timeline_int = np.arange(0, self.active_duration)
            cf = pd.Series(
                (
                    norm.cdf(
                        timeline_int + 1,
                        self.active_duration / 2,
                        self.draw_sched_sigma,
                    )
                    - norm.cdf(
                        timeline_int, self.active_duration / 2, self.draw_sched_sigma
                    )
                )
                / (1 - 2 * norm.cdf(0, self.active_duration / 2, self.draw_sched_sigma))
                * self.cost_total,
                index=self.timeline_active,
            )
        elif self.draw_sched_kind == "uniform":
            cf = pd.Series(
                np.ones(self.active_duration) * self.cost_total / self.active_duration,
                index=self.timeline_active,
            )
        # elif self.draw_sched_kind == "manual":
        #     cf = pd.Series(self.draw_sched_manual,
        #                    index=self.timeline)
        # TODO: curve shaping of draws https://www.adventuresincre.com/draw-schedule-custom-cash-flows/
        # create a dataframe with the cash flow and add category and subcategory for downstream analysis
        df = pd.DataFrame(cf)
        # add name, category and subcategory
        df["Name"] = self.name
        df["Category"] = self.category
        df["Subcategory"] = self.subcategory
        return df

    # CONSTRUCTORS
    @classmethod
    def from_unitized(
        cls,
        name: str,
        # category: Literal["Budget"],
        subcategory: Literal["Land", "Hard Costs", "Soft Costs", "Other"],
        unitized_cost: PositiveFloat,  # by GSF, NSF/SSF/RSF, unit, etc. as desired
        unit_count: PositiveInt,  # number of units or area
        periods_until_start: PositiveInt,
        active_duration: PositiveInt,
        draw_sched_kind: Literal["s-curve", "uniform", "manual"],
        # start_date: Optional[pd.Period] = None,
        notes: Optional[str] = None,
        draw_sched_sigma: Optional[PositiveFloat] = None,
    ) -> "BudgetItem":
        """Construct a budget item from unitized cost and count"""
        cost_total = unitized_cost * unit_count
        return cls(
            name=name,
            # category=category,
            subcategory=subcategory,
            notes=notes,
            cost_total=cost_total,
            # start_date=start_date,
            periods_until_start=periods_until_start,
            active_duration=active_duration,
            draw_sched_kind=draw_sched_kind,
            draw_sched_sigma=draw_sched_sigma,
        )

    @classmethod
    def from_reference_items(
        cls,
        name: str,
        # category: Literal["Budget"],
        subcategory: Literal["Land", "Hard Costs", "Soft Costs", "Other"],
        reference_budget_items: list["BudgetItem"],
        reference_kind: Literal["sum", "passthrough"],
        reference_percentage: PositiveFloat,
        periods_until_start: PositiveInt,
        active_duration: PositiveInt,
        draw_sched_kind: Literal["s-curve", "uniform", "manual"],
        # start_date: Optional[pd.Period] = None,
        notes: Optional[str] = None,
        draw_sched_sigma: Optional[PositiveFloat] = None,
    ) -> "BudgetItem":
        """Construct a budget item as a percentage of another budget item or multiple items"""
        if reference_kind == "sum":
            cost_total = (
                sum([item.cost_total for item in reference_budget_items])
                * reference_percentage
            )
        elif reference_kind == "passthrough":
            cost_total = reference_budget_items[0].cost_total * reference_percentage
        return cls(
            name=name,
            # category=category,
            subcategory=subcategory,
            notes=notes,
            cost_total=cost_total,
            # start_date=start_date,
            periods_until_start=periods_until_start,
            active_duration=active_duration,
            draw_sched_kind=draw_sched_kind,
            draw_sched_sigma=draw_sched_sigma,
        )

    # TODO: just consider a factor-like approach a la opex items below


class Budget(Model):
    budget_items: list[BudgetItem]

    @property
    def budget_df(self) -> pd.DataFrame:
        return pd.concat([item.budget_df for item in self.budget_items])
        # TODO: just use a list for performance? (pd.concat copies data...)

    # TODO: individual cash flow items for each budget item?

    # TODO: add methods to sum up budget items by category and subcategory after shifting to project start date
