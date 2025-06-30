from enum import Enum

# enums for choices of (typically) three of more options (otherwise use Literal[])


##########################
######### PROGRAM #########
##########################


class ProgramUseEnum(str, Enum):
    """Enum for program uses"""

    RESIDENTIAL = "Residential"
    AFFORDABLE_RESIDENTIAL = "Affordable Residential"
    OFFICE = "Office"
    RETAIL = "Retail"
    AMENITY = "Amenity"
    OTHER = "Other"


##########################
######### BUDGET #########
##########################


class DrawScheduleKindEnum(str, Enum):
    """
    Enum for draw schedule kinds in real estate development projects.

    This enum represents the different types of draw schedules that can be used in a real estate development project.

    Attributes:
        S_CURVE (str): Represents an S-curve draw schedule.
        UNIFORM (str): Represents a uniform draw schedule.
        MANUAL (str): Represents a manual draw schedule.
    """

    S_CURVE = "s-curve"
    UNIFORM = "uniform"
    MANUAL = "manual"


###########################
######### REVENUE #########
###########################

class RevenueMultiplicandEnum(str, Enum):
    """
    Enum for program unit kinds (what is being multiplied against).

    This enum represents the different units or bases against which revenue can be calculated.

    Attributes:
        WHOLE_UNIT (str): Represents revenue calculated per whole unit (e.g., per apartment, per house).
        RSF (str): Represents revenue calculated per Rentable Square Foot (RSF).
        PARKING_SPACE (str): Represents revenue calculated per parking space.
        OTHER (str): Represents any other basis for revenue calculation not covered by the above options.
    """

    WHOLE_UNIT = "Whole Unit"
    RSF = "RSF"  # rentable square feet
    PARKING_SPACE = "Parking Space"
    OTHER = "Other"


###########################
######### EXPENSE #########
###########################

class ExpenseKindEnum(str, Enum):
    """
    Enum for expense kinds in real estate development projects.

    Attributes:
        COST (str): Represents cost-based expenses.
        FACTOR (str): Represents factor-based expenses.
    """

    COST = "Cost"
    FACTOR = "Factor"
