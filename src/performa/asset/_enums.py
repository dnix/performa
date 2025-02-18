from enum import Enum


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


class AssetUseEnum(str, Enum):
    """
    Specific use type within an asset.

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
        PER_AREA: Dollars per square foot/meter of area
        PCT_EGR: Percentage of effective gross revenue
        PCT_LINE: Percentage of another line item amount
    """

    AMOUNT = "$"
    PER_AREA = "$/Area"
    PCT_EGR = "% of EGR"
    PCT_LINE = "% of Line"


class LeaseStatusEnum(str, Enum):
    """
    Status of a lease.

    Options:
        CONTRACT: Executed lease agreement in place
        PROPOSAL: Proposed lease under negotiation
        LETTER_OF_INTENT: Non-binding letter of intent stage
        OPTION: Option period of existing lease
        HOLDOVER: Tenant remaining after lease expiration
        MONTH_TO_MONTH: Monthly periodic tenancy
    """

    CONTRACT = "contract"
    PROPOSAL = "proposal"
    LETTER_OF_INTENT = "letter_of_intent"
    OPTION = "option"
    HOLDOVER = "holdover"
    MONTH_TO_MONTH = "month_to_month"
