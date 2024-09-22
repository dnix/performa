from typing import List, Literal, Optional

import numpy as np
import pandas as pd
from pydantic import Field, ValidationInfo, field_validator, model_validator
from scipy.stats import norm

from ..utils.types import PositiveFloat, PositiveInt
from .cash_flow import CashFlowModel
from .model import Model

##########################
######### BUDGET #########
##########################


class BudgetItem(CashFlowModel):
    """Class for a generic cost line item in a budget"""

    # TODO: subclass for specific budget line items (Developer, A&E, Soft Costs, FF&E, Other)
    # TODO: add optional details list for more granular budgeting (i.e., rolling-up to a parent budget item)
    # GENERAL
    category: Literal["Budget"] = "Budget"
    subcategory: Literal["Land", "Hard Costs", "Soft Costs", "Other"]
    # subcategory: Optional[BudgetSubcategoryEnum] = None

    # COST
    cost_total: PositiveFloat  # Total cost of the budget item, e.g., 1_000_000.00

    # DRAW SCHEDULE
    draw_sched_kind: Literal["s-curve", "uniform", "manual"]  # Type of draw schedule
    # TODO: use enum? add triang? others?
    draw_sched_sigma: Optional[PositiveFloat] = Field(
        None, description="Required for s-curve, optional for others"
    )
    draw_sched_manual: Optional[List[PositiveFloat]] = (
        None  # Manual draw schedule values
    )

    @field_validator("draw_sched_sigma")
    @classmethod
    def validate_draw_sched_sigma(cls, v, info: ValidationInfo):
        """Ensure draw_sched_sigma is provided when using s-curve draw schedule"""
        if info.data["draw_sched_kind"] == "s-curve" and v is None:
            raise ValueError(
                "draw_sched_sigma is required when draw_sched_kind is 's-curve'"
            )
        return v

    @field_validator("draw_sched_manual")
    @classmethod
    def validate_manual_draw_schedule(cls, v, info: ValidationInfo):
        """Validate manual draw schedule when provided"""
        if info.data["draw_sched_kind"] == "manual":
            if v is None:
                raise ValueError(
                    "Manual draw schedule must be provided when draw_sched_kind is 'manual'"
                )
            if len(v) != info.data["active_duration"]:
                raise ValueError(
                    "Manual draw schedule length must match active_duration"
                )
            if (
                abs(sum(v) - info.data["cost_total"]) > 1e-6
            ):  # Allow for small floating-point errors
                raise ValueError("Sum of manual draw schedule must equal cost_total")
        return v

    @model_validator(mode="before")
    @classmethod
    def check_draw_sched_sigma(cls, values):
        """Set draw_sched_sigma to None if not using s-curve"""
        if values.get("draw_sched_kind") != "s-curve":
            values["draw_sched_sigma"] = None
        return values

    @property
    def budget_df(self) -> pd.DataFrame:
        """Construct cash flow for budget costs with categories and subcategories"""
        if self.draw_sched_kind == "s-curve":
            # Calculate s-curve distribution
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
            # Calculate uniform distribution
            cf = pd.Series(
                np.ones(self.active_duration) * self.cost_total / self.active_duration,
                index=self.timeline_active,
            )
        elif self.draw_sched_kind == "manual":
            # Use provided manual draw schedule
            # Inspo: curve shaping of draws https://www.adventuresincre.com/draw-schedule-custom-cash-flows/
            cf = pd.Series(self.draw_sched_manual, index=self.timeline_active)

        # Create a dataframe with the cash flow and add category and subcategory for downstream analysis
        df = pd.DataFrame(cf)
        # Add name, category and subcategory
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
        unitized_cost: PositiveFloat,  # Cost per unit (e.g., per GSF, NSF/SSF/RSF, unit)
        unit_count: PositiveInt,  # Number of units or area
        periods_until_start: PositiveInt,
        active_duration: PositiveInt,
        draw_sched_kind: Literal["s-curve", "uniform", "manual"],
        # start_date: Optional[pd.Period] = None,
        notes: Optional[str] = None,
        draw_sched_sigma: Optional[PositiveFloat] = None,
        draw_sched_manual: Optional[List[PositiveFloat]] = None,
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
            draw_sched_manual=draw_sched_manual,
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
        draw_sched_manual: Optional[List[PositiveFloat]] = None,
    ) -> "BudgetItem":
        """Construct a budget item as a percentage of another budget item or multiple items"""
        if reference_kind == "sum":
            # Calculate cost as a percentage of the sum of reference items
            cost_total = (
                sum([item.cost_total for item in reference_budget_items])
                * reference_percentage
            )
        elif reference_kind == "passthrough":
            # Calculate cost as a percentage of the first reference item
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
            draw_sched_manual=draw_sched_manual,
        )

    # TODO: just consider a factor-like approach a la opex items below


class Budget(Model):
    """Class representing the entire budget, composed of multiple BudgetItems"""

    budget_items: list[BudgetItem]

    @property
    def budget_df(self) -> pd.DataFrame:
        """Combine all budget items into a single DataFrame"""
        return pd.concat([item.budget_df for item in self.budget_items])
        # TODO: just use a list for performance? (pd.concat copies data...)

    # TODO: individual cash flow items for each budget item?

    # TODO: add methods to sum up budget items by category and subcategory after shifting to project start date
