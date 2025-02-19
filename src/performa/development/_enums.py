from enum import Enum

# enums for choices of (typically) three of more options (otherwise use Literal[])


#############################
######### CASH FLOW #########
#############################


class CashFlowCategoryEnum(str, Enum):
    """
    Enum for CashFlow categories.

    This enum represents the main categories of cash flows in a real estate development project.

    Attributes:
        BUDGET (str): Represents budget-related cash flows.
        EXPENSE (str): Represents expense-related cash flows.
        REVENUE (str): Represents revenue-related cash flows.
        OTHER (str): Represents any other type of cash flows not covered by the above categories.
    """

    BUDGET = "Budget"
    EXPENSE = "Expense"
    REVENUE = "Revenue"
    OTHER = "Other"


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


class BudgetSubcategoryEnum(str, Enum):
    """
    Enum for budget subcategories in real estate development projects.

    This enum represents the main subcategories of budget in a real estate development project.

    Attributes:
        SALE (str): Represents revenue from property or unit sales.
        LAND (str): Represents revenue from the sale of land.
        HARD_COSTS (str): Represents revenue from hard costs.
        SOFT_COSTS (str): Represents revenue from soft costs.
        OTHER (str): Represents any other type of revenue not covered by the above categories.
    """

    SALE = "Sale"
    LAND = "Land"
    HARD_COSTS = "Hard Costs"
    SOFT_COSTS = "Soft Costs"
    OTHER = "Other"


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


class RevenueSubcategoryEnum(str, Enum):
    """
    Enum for revenue subcategories in real estate development projects.

    This enum represents the primary types of revenue generation in real estate,
    distinguishing between one-time sales and ongoing lease arrangements.

    Attributes:
        SALE (str): Revenue from property or unit SALES.
        LEASE (str): Revenue from property or unit LEASES.
    """

    SALE = "Sale"
    LEASE = "Lease"


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


class ExpenseSubcategoryEnum(str, Enum):
    """
    Enum for expense subcategories in real estate development projects.

    Attributes:
        OP_EX (str): Represents operational expenses.
        CAP_EX (str): Represents capital expenses.
    """

    OP_EX = "OpEx"
    CAP_EX = "CapEx"


class ExpenseKindEnum(str, Enum):
    """
    Enum for expense kinds in real estate development projects.

    Attributes:
        COST (str): Represents cost-based expenses.
        FACTOR (str): Represents factor-based expenses.
    """

    COST = "Cost"
    FACTOR = "Factor"
