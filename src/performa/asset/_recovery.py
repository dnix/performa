from typing import List, Literal, Optional

from ..utils._model import Model
from ..utils._types import FloatBetween0And1, PositiveFloat
from ._growth import GrowthRate
from ._line_item import LineItem


class ExpensePool(Model):
    """Group of related expenses for recovery"""

    name: str
    expenses: List[LineItem]


class Recovery(Model):
    # Recovery pools, structure, & admin fees
    expense_pool: ExpensePool
    structure: Literal[
        "net",
        "base_stop",
        "fixed",
        "base_year",
        "base_year_plus1",
        "base_year_minus1",
    ]
    base_amount: Optional[PositiveFloat] = None  # For base stop
    growth_rate: Optional[GrowthRate] = None

    # Adjustments
    contribution_deduction: Optional[PositiveFloat] = None
    admin_fee_percent: Optional[FloatBetween0And1] = None

    # Prorata share & denominator
    prorata_share: Optional[PositiveFloat] = None  # lease area
    denominator: Optional[PositiveFloat] = None  # property area

    # YoY growth limits
    yoy_min_growth: Optional[FloatBetween0And1] = None
    yoy_max_growth: Optional[FloatBetween0And1] = None

    # Recovery floors & ceilings
    recovery_floor: Optional[PositiveFloat] = None
    recovery_ceiling: Optional[PositiveFloat] = None

    # TODO: validations. are any of the fields mutually exclusive?


class RecoveryMethod(Model):
    """How expenses are recovered from tenants"""

    name: str

    # Gross up
    gross_up: bool = True
    gross_up_percent: Optional[FloatBetween0And1] = None

    # Recoveries
    recoveries: List[Recovery]
