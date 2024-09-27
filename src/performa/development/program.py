from enum import Enum
from typing import Optional

from ..utils.types import PositiveFloat, PositiveInt
from .model import Model

###########################
######### PROGRAM #########
###########################


class ProgramUseEnum(str, Enum):
    """Enum for program uses"""

    residential = "Residential"
    affordable_residential = "Affordable Residential"
    office = "Office"
    retail = "Retail"
    amenity = "Amenity"
    other = "Other"


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
