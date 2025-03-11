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
    including one-time sales, ongoing lease arrangements, and other income sources.

    Attributes:
        SALE (str): Revenue from property or unit sales.
        LEASE (str): Revenue from property or unit leases.
        MISC (str): Miscellaneous income sources like parking, vending, antenna income, etc.
        RECOVERY (str): Expense recoveries from tenants (CAM, taxes, insurance, etc.).
        SECURITY_DEPOSIT (str): Security deposits collected from tenants.
    """

    SALE = "Sale"
    LEASE = "Lease"
    MISC = "Miscellaneous"
    RECOVERY = "Recovery"
    SECURITY_DEPOSIT = "Security Deposit"


class ExpenseSubcategoryEnum(str, Enum):
    """
    Enum for expense subcategories in real estate development projects.

    Attributes:
        OPEX (str): Represents operational expenses.
        CAPEX (str): Represents capital expenses.
    """

    OPEX = "OpEx"
    CAPEX = "CapEx"


class AssetTypeEnum(str, Enum):
    """
    Type of real estate asset.

    Options:
        OFFICE: Office building used primarily for professional/business purposes
        RETAIL: Retail property or shopping center for commercial sales
        INDUSTRIAL: Industrial or warehouse property for manufacturing/distribution
        MULTIFAMILY: Multi-unit residential rental property
        MIXED_USE: Property combining multiple use types in one development
    """

    OFFICE = "office"
    RETAIL = "retail"
    INDUSTRIAL = "industrial"
    MULTIFAMILY = "multifamily"
    MIXED_USE = "mixed_use"


class ProgramUseEnum(str, Enum):
    """
    Specific program use type within an asset.

    Options:
        OFFICE: Professional office space
        RETAIL: Commercial retail space
        RESIDENTIAL: Residential living units
        INDUSTRIAL: Industrial or warehouse space
        STORAGE: Storage or locker space
        PARKING: Vehicle parking facilities
        AMENITY: Common area amenities and facilities
    """

    OFFICE = "office"
    RETAIL = "retail"
    RESIDENTIAL = "residential"
    INDUSTRIAL = "industrial"
    STORAGE = "storage"
    PARKING = "parking"
    AMENITY = "amenity"
    # TODO: add other types of program uses (hotel, etc.)


class LeaseTypeEnum(str, Enum):
    """
    Type of lease structure.

    Options:
        GROSS: Full service lease where landlord pays all operating expenses
        NET: Lease where tenant is responsible for operating expenses
        MODIFIED_GROSS: Hybrid lease with shared operating expense responsibilities
    """

    GROSS = "gross"
    NET = "net"
    MODIFIED_GROSS = "modified_gross"


class RecoveryTypeEnum(str, Enum):
    """
    Type of expense recovery.

    Options:
        NONE: No expense recovery from tenant
        NET: Tenant pays expenses directly
        BASE_YEAR: Tenant pays increases over base year amount
        BASE_STOP: Tenant pays increases over fixed base stop amount
        FIXED: Tenant pays fixed recovery amount
        BASE_YEAR_PLUS1: Base year is set to second year of lease term
        BASE_YEAR_MINUS1: Base year is set to year prior to lease start
    """

    NONE = "none"
    NET = "net"
    BASE_YEAR = "base_year"
    BASE_STOP = "base_stop"
    FIXED = "fixed"
    BASE_YEAR_PLUS1 = "base_year_plus1"
    BASE_YEAR_MINUS1 = "base_year_minus1"


class ExpenseCategoryEnum(str, Enum):
    """
    Categories of operating expenses.

    Options:
        TAXES: Property and real estate taxes
        INSURANCE: Property and liability insurance
        UTILITIES: Electricity, water, gas and other utilities
        MAINTENANCE: Regular building maintenance and repairs
        MANAGEMENT: Property management fees and expenses
        CAM: Common area maintenance expenses
    """

    TAXES = "taxes"
    INSURANCE = "insurance"
    UTILITIES = "utilities"
    MAINTENANCE = "maintenance"
    MANAGEMENT = "management"
    CAM = "cam"


class CapExCategoryEnum(str, Enum):
    """
    Types of capital expenditures.

    Options:
        BUILDING: Major building components like structure, roof, facade
        MECHANICAL: Building systems like HVAC, elevators, electrical
        TENANT: Tenant improvements and common area renovations
        SITE: Site improvements like parking, landscaping, hardscape
    """

    BUILDING = "building"
    MECHANICAL = "mechanical"
    TENANT = "tenant"
    SITE = "site"


class UnitOfMeasureEnum(str, Enum):
    """
    Units for amounts.

    Options:
        AMOUNT: Absolute dollar amount
        PER_UNIT: Dollars per unit
        BY_FACTOR: Factor of a reference amount
        BY_PERCENT: Percentage of a reference amount
    """

    # FIXME: let's standardize this (and in development) to use unitized with another enum for unit type
    # amount (direct amt, as in $/yr or $/mo)
    AMOUNT = "$"  # TODO: rename CURRENCY
    # unitized (usually, $/sf or $/unit)
    PER_UNIT = "$/Unit"
    # by factor (compared to a reference) or percentage
    BY_FACTOR = "Factor"  # e.g. 1.25, 0.85, etc. of a reference amount
    BY_PERCENT = "%"  # e.g. % of a reference amount (e.g. % of EGR, % of Line, etc.)


class UnitOfMeasureTypeEnum(str, Enum):
    """
    Type of unit of measure.

    Options:
        AREA: Square footage, area, etc.
        UNIT: Number of units, parking spaces, etc.
    """

    AREA = "area"
    UNIT = "unit"
    # TODO: parking space, storage space, etc.


class LeaseStatusEnum(str, Enum):
    """
    Status of a lease.

    Options:
        CONTRACT: Executed lease agreement in place
        SPECULATIVE: Lease is not yet in place, defer to market assumptions
    """

    CONTRACT = "contract"
    SPECULATIVE = "speculative"


class FrequencyEnum(str, Enum):
    """
    Frequency of a recurring event.

    Options:
        MONTHLY: Monthly
        QUARTERLY: Quarterly
        YEARLY: Yearly
    """

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"

class UponExpirationEnum(str, Enum):
    """
    What happens to a lease when it expires.

    Options:
        MARKET: Lease expires and is not renewed, market assumptions apply (use Lease logic)
        RENEW: Lease is renewed under the same terms (use Lease logic)
        VACATE: Lease expires and is not renewed, market assumptions apply (use Lease logic)
        OPTION: Lease expires and is not renewed, tenant has the right to renew under the same terms (use Lease logic)
        REABSORB: Lease expires and is not renewed, market assumptions apply (use Reabsorption logic)
    """

    MARKET = "market"
    RENEW = "renew"
    VACATE = "vacate"
    OPTION = "option"
    REABSORB = "reabsorb"
