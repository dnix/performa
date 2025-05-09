from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from ..core._enums import UnitOfMeasureEnum
from ..core._model import Model
from ..core._types import PositiveFloat


class RentEscalation(Model):
    """
    Rent increase structure for a lease.

    Attributes:
        type: Type of escalation (fixed, CPI, percentage)
        amount: Amount of increase (percentage or fixed amount)
        unit_of_measure: Units for the amount
        is_relative: Whether amount is relative to previous rent
        start_date: When increase takes effect
        recurring: Whether increase repeats
        frequency_months: How often increase occurs if recurring
    """

    type: Literal["fixed", "percentage", "cpi"]
    amount: PositiveFloat
    unit_of_measure: UnitOfMeasureEnum
    is_relative: bool
    start_date: date
    recurring: bool = False
    frequency_months: Optional[int] = None
