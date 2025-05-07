from enum import Enum
from typing import List, Optional


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
        CURRENCY: Absolute currency amount (e.g., total dollars)
        PER_UNIT: Amount per defined unit (e.g., $/sqft, $/unit)
        BY_FACTOR: Factor relative to a reference amount (e.g., 1.1x)
        BY_PERCENT: Percentage relative to a reference amount (e.g., 5% of EGI)
    """

    # amount (direct amt, as in $/yr or $/mo)
    CURRENCY = "currency"  # Formerly AMOUNT / $
    # unitized (usually, $/sf or $/unit)
    PER_UNIT = "per_unit" # Formerly "$/Unit"
    # by factor (compared to a reference) or percentage
    BY_FACTOR = "factor"  # Formerly "Factor"
    BY_PERCENT = "percent"  # Formerly "%"


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
        ANNUAL: Yearly / Annually
    """

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual" # Formerly YEARLY / yearly

class UponExpirationEnum(str, Enum):
    """
    Defines behavior when a lease expires, controlling how the space is treated in rollover scenarios.
    
    Options:
        MARKET: Weighted average approach based on market conditions, reflecting both new tenant and 
               renewal probabilities. Creates a speculative lease with blended terms.
        RENEW: Assumes 100% renewal probability, extending the lease under predetermined terms.
               Creates a renewal lease using either contractual terms or renewal market assumptions.
        VACATE: Assumes 0% renewal probability, with space immediately available for new tenant.
                Creates a new speculative lease at current market rates after downtime.
        OPTION: Models a contractual renewal option as a distinct lease. Treats the option terms
                as a separate lease record that activates upon expiration if exercised.
        REABSORB: Space remains vacant without automatic re-tenanting, pending either manual
                  re-leasing input or processing through a space absorption model. No speculative
                  lease is created automatically.
    """
    MARKET = "market"     # Weighted average approach using market conditions
    RENEW = "renew"       # 100% renewal with predetermined terms
    VACATE = "vacate"     # 0% renewal, immediate repositioning with new tenant
    OPTION = "option"     # Explicit modeling of contractual renewal options
    REABSORB = "reabsorb" # Space remains vacant pending separate re-leasing process


class VacancyLossMethodEnum(str, Enum):
    """How General Vacancy is calculated and applied in the waterfall."""
    POTENTIAL_GROSS_REVENUE = "Potential Gross Revenue" # % of PGR line
    EFFECTIVE_GROSS_REVENUE = "Effective Gross Revenue" # % of (PGR + Misc Inc - Abatement)


class AggregateLineKey(str, Enum):
    """Defines standard keys for aggregated financial line items."""

    # --- Revenue Side ---
    POTENTIAL_GROSS_REVENUE = "Potential Gross Revenue"       # Sum of potential base rent (often contractual)
    RENTAL_ABATEMENT = "Rental Abatement / Concessions"      # Free rent periods
    MISCELLANEOUS_INCOME = "Miscellaneous Income"          # Parking, laundry, fees, etc.
    EFFECTIVE_GROSS_REVENUE = "Effective Gross Revenue"     # Potential + Misc - Abatement (BEFORE Vacancy/Recoveries)
    GENERAL_VACANCY_LOSS = "General Vacancy & Credit Loss"  # Allowance based on market/assumptions
    COLLECTION_LOSS = "Collection Loss"                 # Allowance for uncollectible income
    EXPENSE_REIMBURSEMENTS = "Expense Reimbursements"       # Recoveries from tenants
    TOTAL_EFFECTIVE_GROSS_INCOME = "Total Effective Gross Income" # EGR - Vacancy + Recoveries (often called EGI)

    # --- Expense Side ---
    TOTAL_OPERATING_EXPENSES = "Total Operating Expenses"     # Sum of all OpEx items

    # --- Profitability Metrics ---
    NET_OPERATING_INCOME = "Net Operating Income"           # Total EGI - Total OpEx

    # --- Capital & Leasing Costs ---
    TOTAL_TENANT_IMPROVEMENTS = "Total Tenant Improvements"     # TIs
    TOTAL_LEASING_COMMISSIONS = "Total Leasing Commissions"   # LCs
    TOTAL_CAPITAL_EXPENDITURES = "Total Capital Expenditures"    # CapEx (incl. reserves maybe)

    # --- Cash Flow Metrics ---
    UNLEVERED_CASH_FLOW = "Unlevered Cash Flow"           # NOI - TIs - LCs - CapEx
    TOTAL_DEBT_SERVICE = "Total Debt Service"             # Principal + Interest
    LEVERED_CASH_FLOW = "Levered Cash Flow"             # UCF - Debt Service

    # --- Raw Aggregates (Less commonly referenced directly, but needed for calculation) ---
    _RAW_TOTAL_REVENUE = "_RAW Total Revenue" # Intermediate sum of all revenue components (rent, misc)
    _RAW_TOTAL_RECOVERIES = "_RAW Total Recoveries" # Intermediate sum of all recovery components
    _RAW_TOTAL_OPEX = "_RAW Total OpEx"       # Intermediate sum used above
    _RAW_TOTAL_CAPEX = "_RAW Total CapEx"     # Intermediate sum used above
    _RAW_TOTAL_TI = "_RAW Total TI"         # Intermediate sum used above
    _RAW_TOTAL_LC = "_RAW Total LC"         # Intermediate sum used above

    # Vacancy & Loss Specifics
    DOWNTIME_VACANCY_LOSS = "Downtime Vacancy Loss" # Added for initial vacancy
    ROLLOVER_VACANCY_LOSS = "Rollover Vacancy Loss" # Placeholder if aggregated separately

    @classmethod
    def from_value(cls, value: str) -> Optional['AggregateLineKey']:
        """Look up enum member by its string value."""
        for member in cls:
            if member.value == value:
                return member
        return None

    # Helper to check if a key is intended for internal calculation steps
    @classmethod
    def is_internal_key(cls, key: 'AggregateLineKey') -> bool:
        """Check if the key is prefixed for internal calculation use."""
        return key.value.startswith("_RAW")

    # Helper to get display keys (excluding internal ones)
    @classmethod
    def get_display_keys(cls) -> List["AggregateLineKey"]:
        """Return a list of keys suitable for display/reporting."""
        return [k for k in cls if not cls.is_internal_key(k)]
