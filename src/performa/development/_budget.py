from typing import Optional

import numpy as np
import pandas as pd
from pydantic import Field, field_validator
from scipy.stats import norm

from ..core._cash_flow import CashFlowModel
from ..core._enums import BudgetSubcategoryEnum, CashFlowCategoryEnum
from ..core._types import PositiveFloat, PositiveInt
from ._draw_schedule import (
    AnyDrawSchedule,
    ManualDrawSchedule,
    SCurveDrawSchedule,
    UniformDrawSchedule,
)
from ._model import Model

##########################
######### BUDGET #########
##########################


class BudgetItem(CashFlowModel):
    """
    Class for a generic cost line item in a budget.

    Inputs coming from parent class CashFlowModel:
    - name: str  # "Construction Cost"
    - notes: Optional[str] = None  # optional notes on the item
    - start_date: pd.Period  # month zero (need to shift to project start date)
    - periods_until_start: PositiveInt  # months, from global start date of project
    - active_duration: PositiveInt  # months
    """

    # GENERAL
    category: CashFlowCategoryEnum = "Budget"
    subcategory: BudgetSubcategoryEnum  # "Land", "Hard Costs", "Soft Costs", "Other"

    # COST
    cost_total: PositiveFloat  # Total cost of the budget item, e.g., 1_000_000.00

    # DRAW SCHEDULE
    draw_schedule: Optional[AnyDrawSchedule] = Field(
        default=None,
        description="Draw schedule for the budget item. Defaults to UniformDrawSchedule if not specified.",
    )

    @field_validator("draw_schedule")
    @classmethod
    def validate_draw_schedule(cls, v, info):
        """Validate the draw schedule, ensuring it's set and consistent with active_duration."""
        if v is None:
            return UniformDrawSchedule()
        if isinstance(v, ManualDrawSchedule):
            if len(v.values) != info.data["active_duration"]:
                raise ValueError(
                    "Manual draw schedule length must match active_duration"
                )
        return v

    @property
    def budget_df(self) -> pd.DataFrame:
        """Construct cash flow for budget costs with categories and subcategories."""
        draw_schedule = self.draw_schedule or UniformDrawSchedule()
        # Calculate cash flow based on draw schedule type
        if isinstance(draw_schedule, SCurveDrawSchedule):
            cf = self._calculate_s_curve(draw_schedule)
        elif isinstance(draw_schedule, UniformDrawSchedule):
            cf = self._calculate_uniform()
        elif isinstance(draw_schedule, ManualDrawSchedule):
            cf = self._calculate_manual(draw_schedule)

        # Create a dataframe with the cash flow and add category and subcategory
        df = pd.DataFrame(cf)
        df["Name"] = self.name
        df["Category"] = self.category
        df["Subcategory"] = self.subcategory
        return df

    def _calculate_s_curve(self, draw_schedule: SCurveDrawSchedule) -> pd.Series:
        """Calculate S-curve distribution."""
        timeline_int = np.arange(0, self.active_duration)
        return pd.Series(
            (
                norm.cdf(
                    timeline_int + 1, self.active_duration / 2, draw_schedule.sigma
                )
                - norm.cdf(timeline_int, self.active_duration / 2, draw_schedule.sigma)
            )
            / (1 - 2 * norm.cdf(0, self.active_duration / 2, draw_schedule.sigma))
            * self.cost_total,
            index=self.timeline_active,
        )

    def _calculate_uniform(self) -> pd.Series:
        """Calculate uniform distribution."""
        return pd.Series(
            np.ones(self.active_duration) * self.cost_total / self.active_duration,
            index=self.timeline_active,
        )

    def _calculate_manual(self, draw_schedule: ManualDrawSchedule) -> pd.Series:
        """Calculate manual draw schedule."""
        total_manual = sum(draw_schedule.values)
        return pd.Series(
            np.array(draw_schedule.values) * (self.cost_total / total_manual),
            index=self.timeline_active,
        )

    @classmethod
    def from_unitized(
        cls,
        name: str,
        subcategory: BudgetSubcategoryEnum,
        unitized_cost: PositiveFloat,  # Cost per unit (e.g., per GSF, NSF/SSF/RSF, unit)
        unit_count: PositiveInt,  # Number of units or area
        periods_until_start: PositiveInt,
        active_duration: PositiveInt,
        draw_schedule: Optional[AnyDrawSchedule] = None,
        notes: Optional[str] = None,
    ) -> "BudgetItem":
        """Construct a budget item from unitized cost and count"""
        cost_total = unitized_cost * unit_count
        return cls(
            name=name,
            subcategory=subcategory,
            notes=notes,
            cost_total=cost_total,
            periods_until_start=periods_until_start,
            active_duration=active_duration,
            draw_schedule=draw_schedule,
        )

    @classmethod
    def from_reference_items(
        cls,
        name: str,
        subcategory: BudgetSubcategoryEnum,
        reference_budget_items: list["BudgetItem"],
        reference_factor: PositiveFloat,
        periods_until_start: PositiveInt,
        active_duration: PositiveInt,
        draw_schedule: Optional[AnyDrawSchedule] = None,
        notes: Optional[str] = None,
    ) -> "BudgetItem":
        """Construct a budget item as a percentage of the sum of reference budget items"""
        cost_total = (
            sum([item.cost_total for item in reference_budget_items])
            * reference_factor
        )
        return cls(
            name=name,
            subcategory=subcategory,
            notes=notes,
            cost_total=cost_total,
            periods_until_start=periods_until_start,
            active_duration=active_duration,
            draw_schedule=draw_schedule,
        )


class Budget(Model):
    """Class representing the entire budget, composed of multiple BudgetItems"""

    budget_items: list[BudgetItem]

    @property
    def budget_df(self) -> pd.DataFrame:
        """Combine all budget items into a single DataFrame"""
        return pd.concat([item.budget_df for item in self.budget_items])
        # TODO: just use a list for performance? (pd.concat copies data...)
