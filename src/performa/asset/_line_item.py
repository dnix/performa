from typing import Literal, Optional

from pydantic import model_validator

from ..utils._model import Model
from ..utils._types import FloatBetween0And1, PositiveFloat
from ._enums import UnitOfMeasureEnum


class LineItem(Model):
    # TODO: consider using CashFlowModel for line items (after moving to `core`)
    """
    Base model for any income/expense line item.
    
    Attributes:
        type: The type of line item.
        description: A description of the line item.
        account: Account mapping (chart-of-accounts).
        amount: Monetary amount.
        unit_of_measure: Unit for the amount (e.g. SF, Unit).
        frequency: "monthly" or "yearly".
        area: Area value used for area‐based calculations.
        growth_rate: Can be a fixed rate or a GrowthRates instance.
        is_variable: Flag for variable behavior (e.g. percentage ties).
        percent_variable: If variable, the percentage tied.
    """

    type: str
    description: str
    account: str
    amount: PositiveFloat
    unit_of_measure: UnitOfMeasureEnum
    frequency: Literal["monthly", "yearly"]
    area: Optional[PositiveFloat]
    growth_rate: float  # or a GrowthRates instance (see project types)
    is_variable: bool = False
    percent_variable: Optional[FloatBetween0And1] = None

    @model_validator(mode="after")
    def validate_variable(cls, values):
        """
        Ensure that if the line item is flagged as variable, a percent_variable is provided.
        """
        if values.get("is_variable") and values.get("percent_variable") is None:
            raise ValueError("percent_variable must be provided when is_variable is True.")
        return values

    # TODO: class constructor method for line item based on another line item(s)
