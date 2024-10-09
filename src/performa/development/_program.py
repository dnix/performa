from typing import Optional

from pydantic import ConfigDict

from ..utils._types import PositiveFloat, PositiveInt
from ._enums import ProgramUseEnum
from ._model import Model

###########################
######### PROGRAM #########
###########################


class Program(Model):  # CashFlowModel???
    """Class for a generic sellable/rentable program"""

    # PROGRAM BASICS
    name: str  # "Studio Apartments"
    use: ProgramUseEnum  # use of the program (residential, office, retail, etc.)

    # UNITS/AREA
    gross_area: Optional[PositiveFloat]  # gross area in square feet
    net_area: PositiveFloat  # net sellable/rentable area in square feet
    unit_count: PositiveInt  # number of income-generating units/spaces
    # program_multiplier: PositiveInt = 1  # if modeling more than one of the same program

    model_config = ConfigDict(
        frozen=True,  # make the program object immutable to enable hashing/set operations
    )
