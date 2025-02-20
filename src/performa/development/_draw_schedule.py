from typing import List, Literal, Union

from pydantic import Field
from typing_extensions import Annotated

from ..core._types import PositiveFloat
from ._enums import DrawScheduleKindEnum
from ._model import Model

##################################
######### DRAW SCHEDULE ##########
##################################


class DrawSchedule(Model):
    """Base class for all draw schedules."""

    kind: DrawScheduleKindEnum


class SCurveDrawSchedule(DrawSchedule):
    """S-curve draw schedule with a sigma parameter."""

    kind: Literal["s-curve"] = "s-curve"
    sigma: PositiveFloat


class UniformDrawSchedule(DrawSchedule):
    """Uniform draw schedule (evenly distributed)."""

    kind: Literal["uniform"] = "uniform"


class ManualDrawSchedule(DrawSchedule):
    """Manual draw schedule with user-defined values."""

    kind: Literal["manual"] = "manual"
    values: List[PositiveFloat]


# Union type for all draw schedules, using discriminator for type differentiation
AnyDrawSchedule = Annotated[
    Union[SCurveDrawSchedule, UniformDrawSchedule, ManualDrawSchedule],
    Field(discriminator="kind"),
]
