from enum import Enum


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


class ExpenseSubcategoryEnum(str, Enum):
    """
    Enum for expense subcategories in real estate development projects.

    Attributes:
        OPEX (str): Represents operational expenses.
        CAPEX (str): Represents capital expenses.
    """

    OPEX = "OpEx"
    CAPEX = "CapEx"
