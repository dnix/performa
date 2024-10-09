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
        budget (str): Represents budget-related cash flows.
        expense (str): Represents expense-related cash flows.
        revenue (str): Represents revenue-related cash flows.
        other (str): Represents any other type of cash flows not covered by the above categories.
    """

    budget = "Budget"
    expense = "Expense"
    revenue = "Revenue"
    other = "Other"


##########################
######### PROGRAM #########
##########################


class ProgramUseEnum(str, Enum):
    """Enum for program uses"""

    residential = "Residential"
    affordable_residential = "Affordable Residential"
    office = "Office"
    retail = "Retail"
    amenity = "Amenity"
    other = "Other"


##########################
######### BUDGET #########
##########################


class BudgetSubcategoryEnum(str, Enum):
    """
    Enum for budget subcategories in real estate development projects.

    This enum represents the main subcategories of budget in a real estate development project.

    Attributes:
        sale (str): Represents revenue from property or unit sales.
        land (str): Represents revenue from the sale of land.
        hard_costs (str): Represents revenue from hard costs.
        soft_costs (str): Represents revenue from soft costs.
        other (str): Represents any other type of revenue not covered by the above categories.
    """

    sale = "Sale"
    land = "Land"
    hard_costs = "Hard Costs"
    soft_costs = "Soft Costs"
    other = "Other"


class DrawScheduleKindEnum(str, Enum):
    """
    Enum for draw schedule kinds in real estate development projects.

    This enum represents the different types of draw schedules that can be used in a real estate development project.

    Attributes:
        s_curve (str): Represents an S-curve draw schedule.
        uniform (str): Represents a uniform draw schedule.
        manual (str): Represents a manual draw schedule.
    """

    s_curve = "s-curve"
    uniform = "uniform"
    manual = "manual"


###########################
######### REVENUE #########
###########################


class RevenueSubcategoryEnum(str, Enum):
    """
    Enum for revenue subcategories in real estate development projects.

    This enum represents the primary types of revenue generation in real estate,
    distinguishing between one-time sales and ongoing lease arrangements.

    Attributes:
        `sale` (str): Revenue from property or unit SALES.
        `lease` (str): Revenue from property or unit LEASES.
    """

    sale = "Sale"
    lease = "Lease"


class RevenueMultiplicandEnum(str, Enum):
    """
    Enum for program unit kinds (what is being multiplied against).

    This enum represents the different units or bases against which revenue can be calculated.

    Attributes:
        whole (str): Represents revenue calculated per whole unit (e.g., per apartment, per house).
        rsf (str): Represents revenue calculated per Rentable Square Foot (RSF).
        parking_space (str): Represents revenue calculated per parking space.
        other (str): Represents any other basis for revenue calculation not covered by the above options.
    """

    whole = "Whole Unit"
    rsf = "RSF"  # rentable square feet
    parking_space = "Parking Space"
    other = "Other"


###########################
######### EXPENSE #########
###########################


class ExpenseSubcategoryEnum(str, Enum):
    """
    Enum for expense subcategories in real estate development projects.
    """

    op_ex = "OpEx"
    cap_ex = "CapEx"


class ExpenseKindEnum(str, Enum):
    """
    Enum for expense kinds in real estate development projects.
    """

    cost = "Cost"
    factor = "Factor"
