# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from enum import Enum
from typing import List, Optional


class CalculationPass(Enum):
    """
    Defines the explicit waterfall of calculation passes for the analysis engine.
    This ensures that prerequisite calculations (like base expenses) are completed
    before dependent calculations (like recoveries) begin.
    """
    INDEPENDENT_VALUES = 1
    DEPENDENT_VALUES = 2


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


class PropertyAttributeKey(str, Enum):
    """
    Property attributes that can be used as calculation bases.
    
    This enum provides explicit references to property characteristics
    that cash flow models can multiply against, replacing the ambiguous
    UnitOfMeasureEnum.PER_UNIT system.
    
    Industry Standard Measurements:
    - UNIT_COUNT: Dwelling units (residential), office suites, retail spaces
    - NET_RENTABLE_AREA: Leasable square footage (most common)  
    - GROSS_AREA: Total building area including common areas
    - PARKING_SPACES: Parking stalls/spaces
    - FLOORS: Building floors (for certain building-level expenses)
    
    Usage Examples:
        # Residential maintenance: $400 per dwelling unit
        expense = ResidentialOpExItem(value=400, reference=PropertyAttributeKey.UNIT_COUNT)
        
        # Office insurance: $2.50 per square foot
        expense = OfficeOpExItem(value=2.50, reference=PropertyAttributeKey.NET_RENTABLE_AREA)
        
        # Parking income: $100 per parking space  
        income = MiscIncomeItem(value=100, reference=PropertyAttributeKey.PARKING_SPACES)
    """
    
    # === UNIT-BASED ATTRIBUTES ===
    UNIT_COUNT = "unit_count"
    """
    Number of units in the property.
    - Residential: Dwelling units (apartments, condos, etc.)
    - Office: Suite count or office spaces
    - Retail: Individual retail spaces
    - Industrial: Warehouse bays or tenant spaces
    """
    
    # === AREA-BASED ATTRIBUTES ===  
    NET_RENTABLE_AREA = "net_rentable_area"
    """
    Net rentable square footage - the most common calculation base.
    - Excludes common areas, mechanical spaces, etc.
    - Industry standard for most per-SF calculations
    - Available on all property types via PropertyBaseModel
    """
    
    GROSS_AREA = "gross_area"
    """
    Total building area including all space.
    - Includes common areas, mechanical, circulation, etc.
    - Used for certain building-level expenses (utilities, cleaning)
    - Available on all property types via PropertyBaseModel
    """
    
    # === ADDITIONAL ATTRIBUTES ===
    PARKING_SPACES = "parking_spaces"
    """
    Number of parking stalls/spaces.
    - Used for parking-related income or expenses
    - Not all properties have parking (will be 0 or None)
    """
    
    FLOORS = "floors"
    """
    Number of building floors.
    - Used for floor-based expenses (elevator maintenance, etc.)
    - Available through computed fields on property models
    """


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
    FIXME: remove this now-deprecated enum
    DEPRECATED: Unit of measure enumeration for cash flow models.
    
    This enum is being phased out in favor of the new PropertyAttributeKey and 
    ReferenceKey system which provides more explicit and type-safe references.
    
    Migration Guide:
    - UnitOfMeasureEnum.CURRENCY -> reference=None  
    - UnitOfMeasureEnum.PER_UNIT -> reference=PropertyAttributeKey.UNIT_COUNT (residential) 
                                    or PropertyAttributeKey.NET_RENTABLE_AREA (office)
    - UnitOfMeasureEnum.BY_PERCENT -> reference=UnleveredAggregateLineKey.EFFECTIVE_GROSS_INCOME
    - UnitOfMeasureEnum.BY_FACTOR -> reference=UnleveredAggregateLineKey.* (specific aggregate)
    
    Do not use in new code. Use CashFlowModel.reference field instead.
    
    IMPORTANT: PER_UNIT behavior changed in Phase 1 bug fix (Dec 2024).
    See: validation_results/2-1-1_per_unit_calculation_fix_plan.md

    Options:
        CURRENCY: Absolute currency amount (e.g., total dollars)
        PER_UNIT: Smart property-type detection for unitized calculations:
            - Residential properties: per dwelling unit (unit_count)  
            - Office properties: per square foot (net_rentable_area)
        BY_FACTOR: Factor relative to a reference amount (e.g., 1.1x)
        BY_PERCENT: Percentage relative to a reference amount (e.g., 5% of EGI)
        
    Migration Plan:
        Phase 1 (CURRENT): Smart defaults fix critical calculation bug
        Phase 2 (FUTURE): Full migration to PropertyAttributeKey reference system
    """

    # amount (direct amt, as in $/yr or $/mo)
    CURRENCY = "currency"  # Formerly AMOUNT / $
    # Smart defaults: per dwelling unit for residential, per SF for office
    PER_UNIT = "per_unit"  # TODO: Replace with PropertyAttributeKey system (Phase 2)
    # by factor (compared to a reference) or percentage
    BY_FACTOR = "factor"
    BY_PERCENT = "percent"



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
    ANNUAL = "annual"


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

    MARKET = "market"  # Weighted average approach using market conditions
    RENEW = "renew"  # 100% renewal with predetermined terms
    VACATE = "vacate"  # 0% renewal, immediate repositioning with new tenant
    OPTION = "option"  # Explicit modeling of contractual renewal options
    REABSORB = "reabsorb"  # Space remains vacant pending separate re-leasing process


class VacancyLossMethodEnum(str, Enum):
    """How General Vacancy is calculated and applied in the waterfall."""
    POTENTIAL_GROSS_REVENUE = "Potential Gross Revenue" # % of PGR line
    EFFECTIVE_GROSS_INCOME = "Effective Gross Income" # % of (PGR + Misc Inc - Abatement)


class UnleveredAggregateLineKey(str, Enum):
    """
    Asset-level financial line items calculated before financing.
    
    These aggregates represent the unlevered performance of the real estate asset,
    including all revenue, expenses, and capital costs but excluding debt service.
    Asset-level models (OpEx, leases, etc.) can only reference these keys.
    
    ARCHITECTURAL CONSTRAINT: Asset-level CashFlowModel instances can ONLY reference
    UnleveredAggregateLineKey values to prevent circular dependencies.
    """

    # --- Revenue Side ---
    POTENTIAL_GROSS_REVENUE = "Potential Gross Revenue"           # Sum of potential base rent (often contractual)
    RENTAL_ABATEMENT = "Rental Abatement / Concessions"           # Free rent periods
    MISCELLANEOUS_INCOME = "Miscellaneous Income"                 # Parking, laundry, fees, etc.
    GENERAL_VACANCY_LOSS = "General Vacancy & Credit Loss"        # Allowance based on market/assumptions
    COLLECTION_LOSS = "Collection Loss"                           # Allowance for uncollectible income
    EXPENSE_REIMBURSEMENTS = "Expense Reimbursements"             # Recoveries from tenants
    EFFECTIVE_GROSS_INCOME = "Effective Gross Income"             # PGR + Misc - Abatement - Vacancy + Recoveries (industry standard EGI)

    # --- Expense Side ---
    TOTAL_OPERATING_EXPENSES = "Total Operating Expenses"  # Sum of all OpEx items

    # --- Profitability Metrics ---
    NET_OPERATING_INCOME = "Net Operating Income"  # Total EGI - Total OpEx

    # --- Capital & Leasing Costs ---
    TOTAL_TENANT_IMPROVEMENTS = "Total Tenant Improvements"  # TIs
    TOTAL_LEASING_COMMISSIONS = "Total Leasing Commissions"  # LCs
    TOTAL_CAPITAL_EXPENDITURES = "Total Capital Expenditures"  # CapEx (incl. reserves maybe)

    # --- Unlevered Cash Flow ---
    UNLEVERED_CASH_FLOW = "Unlevered Cash Flow"  # NOI - TIs - LCs - CapEx

    # --- Raw Aggregates (Less commonly referenced directly, but needed for calculation) ---
    _RAW_TOTAL_REVENUE = "_RAW Total Revenue"  # Intermediate sum of all revenue components (rent, misc)
    _RAW_TOTAL_RECOVERIES = "_RAW Total Recoveries"  # Intermediate sum of all recovery components
    _RAW_TOTAL_OPEX = "_RAW Total OpEx"  # Intermediate sum used above
    _RAW_TOTAL_CAPEX = "_RAW Total CapEx"  # Intermediate sum used above
    _RAW_TOTAL_TI = "_RAW Total TI"  # Intermediate sum used above
    _RAW_TOTAL_LC = "_RAW Total LC"  # Intermediate sum used above

    # Vacancy & Loss Specifics
    DOWNTIME_VACANCY_LOSS = "Downtime Vacancy Loss"  # Added for initial vacancy
    ROLLOVER_VACANCY_LOSS = "Rollover Vacancy Loss"  # Placeholder if aggregated separately

    @classmethod
    def from_value(cls, value: str) -> Optional["UnleveredAggregateLineKey"]:
        """Look up enum member by its string value."""
        for member in cls:
            if member.value == value:
                return member
        return None

    # Helper to check if a key is intended for internal calculation steps
    @classmethod
    def is_internal_key(cls, key: "UnleveredAggregateLineKey") -> bool:
        """Check if the key is prefixed for internal calculation use."""
        return key.value.startswith("_RAW")

    # Helper to get display keys (excluding internal ones)
    @classmethod
    def get_display_keys(cls) -> List["UnleveredAggregateLineKey"]:
        """Return a list of keys suitable for display/reporting."""
        return [k for k in cls if not cls.is_internal_key(k)]


class LeveredAggregateLineKey(str, Enum):
    """
    Deal-level financial line items calculated after financing.
    
    These aggregates represent the levered performance of the investment deal,
    including debt service and final levered cash flows. Only deal-level
    calculations can reference or produce these keys.
    
    ARCHITECTURAL CONSTRAINT: Deal-level calculations produce these aggregates.
    Asset-level models CANNOT reference these keys.
    """

    # --- Financing Components ---
    TOTAL_DEBT_SERVICE = "Total Debt Service"  # Principal + Interest
    LEVERED_CASH_FLOW = "Levered Cash Flow"  # UCF - Debt Service

    # --- Raw Aggregates ---
    _RAW_TOTAL_DEBT_SERVICE = "_RAW Total Debt Service"  # Intermediate sum of all debt service

    @classmethod
    def from_value(cls, value: str) -> Optional["LeveredAggregateLineKey"]:
        """Look up enum member by its string value."""
        for member in cls:
            if member.value == value:
                return member
        return None

    # Helper to check if a key is intended for internal calculation steps
    @classmethod
    def is_internal_key(cls, key: "LeveredAggregateLineKey") -> bool:
        """Check if the key is prefixed for internal calculation use."""
        return key.value.startswith("_RAW")

    # Helper to get display keys (excluding internal ones)
    @classmethod
    def get_display_keys(cls) -> List["LeveredAggregateLineKey"]:
        """Return a list of keys suitable for display/reporting."""
        return [k for k in cls if not cls.is_internal_key(k)]


class StartDateAnchorEnum(str, Enum):
    """Defines how the absorption start date is determined."""

    ANALYSIS_START = "AnalysisStart"
    # RELATIVE_DATE = "RelativeDate" # TODO: Placeholder: Start after a specific offset from analysis start.
    # MILESTONE = "Milestone" # TODO: Placeholder: Start relative to a development milestone.
    # FIXED_DATE = "FixedDate" # TODO: Implicitly handled by passing a date object.


class DrawScheduleKindEnum(str, Enum):
    """
    Type of draw schedule for capital expenditures.
    
    Options:
        UNIFORM: Evenly distributed draws across the timeline
        S_CURVE: S-curve distribution following construction spending patterns
        MANUAL: Custom user-defined draw schedule
        FIRST_LAST: Split between first and last periods
        FIRST_ONLY: Single draw in the first period
        LAST_ONLY: Single draw in the last period
    """
    
    UNIFORM = "uniform"
    S_CURVE = "s-curve"
    MANUAL = "manual"
    FIRST_LAST = "first-last"
    FIRST_ONLY = "first-only"
    LAST_ONLY = "last-only"


class FeeTypeEnum(str, Enum):
    """
    Standard fee type categories for real estate deals.
    
    This enum standardizes fee categorization for proper accounting, reporting,
    and analytics. Fees are broadly categorized as either partner fees (paid to
    equity participants) or third-party fees (paid to external service providers).
    
    Partner Fee Types:
        DEVELOPER: Development and construction management fees
        ASSET_MANAGEMENT: Ongoing asset management and oversight fees
        ACQUISITION: Acquisition and due diligence fees
        DISPOSITION: Sale and disposition fees
        PROMOTE: Carried interest and performance fees
        
    Third-Party Fee Types:
        PROFESSIONAL_SERVICES: Architecture, engineering, consulting
        BROKERAGE: Leasing commissions and sales brokerage
        LEGAL: Legal services and transaction costs
        FINANCING: Loan origination and financing fees
        CONSTRUCTION_MANAGEMENT: Third-party construction management
        PROPERTY_MANAGEMENT: Third-party property management services
        
    General:
        OTHER: Any fee type not covered by the above categories
    """
    
    # Partner Fee Types (typically paid to GP/LP equity participants)
    DEVELOPER = "Developer"
    ASSET_MANAGEMENT = "Asset Management"
    ACQUISITION = "Acquisition"
    DISPOSITION = "Disposition"
    PROMOTE = "Promote"
    
    # Third-Party Fee Types (typically paid to external service providers)
    PROFESSIONAL_SERVICES = "Professional Services"
    BROKERAGE = "Brokerage"
    LEGAL = "Legal"
    FINANCING = "Financing"
    CONSTRUCTION_MANAGEMENT = "Construction Management"
    PROPERTY_MANAGEMENT = "Property Management"
    
    # General
    OTHER = "Other"
    
    @classmethod
    def get_partner_fee_types(cls) -> List["FeeTypeEnum"]:
        """Return fee types typically paid to equity partners."""
        return [
            cls.DEVELOPER,
            cls.ASSET_MANAGEMENT,
            cls.ACQUISITION,
            cls.DISPOSITION,
            cls.PROMOTE,
        ]
    
    @classmethod
    def get_third_party_fee_types(cls) -> List["FeeTypeEnum"]:
        """Return fee types typically paid to third-party service providers."""
        return [
            cls.PROFESSIONAL_SERVICES,
            cls.BROKERAGE,
            cls.LEGAL,
            cls.FINANCING,
            cls.CONSTRUCTION_MANAGEMENT,
            cls.PROPERTY_MANAGEMENT,
        ]
    
    @classmethod
    def is_partner_fee_type(cls, fee_type: "FeeTypeEnum") -> bool:
        """Check if a fee type is typically paid to equity partners."""
        return fee_type in cls.get_partner_fee_types()
    
    @classmethod
    def is_third_party_fee_type(cls, fee_type: "FeeTypeEnum") -> bool:
        """Check if a fee type is typically paid to third-party providers."""
        return fee_type in cls.get_third_party_fee_types()
