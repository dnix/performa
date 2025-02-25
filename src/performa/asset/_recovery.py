from typing import List, Literal, Optional

from ..core._model import Model
from ..core._types import FloatBetween0And1, PositiveFloat
from ._expense import ExpenseItem
from ._market import GrowthRate


class ExpensePool(Model):
    """Group of related expenses for recovery"""

    name: str
    expenses: List[ExpenseItem]


class Recovery(Model):
    """
    Model for cost recovery as defined by Argus Enterprise/Valuation DCF.

    Attributes:
        expense_pool: Represents the expense pool associated with this recovery.
        structure: Indicates the recovery structure, which can be one of:
            "net", "base_stop", "fixed", "base_year",
            "base_year_plus1", or "base_year_minus1", mapping directly to Argus options.
        base_amount: Base amount used in fixed or base-stop recovery calculations.
        growth_rate: Optional growth rate applied to recoveries.
        contribution_deduction: Deduction applied (if any) to tenant contributions.
        admin_fee_percent: Administrative fee percent applied on recoveries.
        prorata_share: The lease-specific share for allocation.
        denominator: The overall property area used in the allocation process.
        yoy_min_growth: Minimum allowed year-over-year recovery growth.
        yoy_max_growth: Maximum allowed year-over-year recovery growth.
        recovery_floor: Minimum recovery limit (floor).
        recovery_ceiling: Maximum recovery limit (ceiling).
    """
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
