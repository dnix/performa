# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from enum import Enum
from typing import List, Optional


class OrchestrationPass(Enum):
    """
    Defines the orchestration passes for model execution order.
    Ensures dependencies are resolved before dependent models run.
    """

    INDEPENDENT_MODELS = 1
    DEPENDENT_MODELS = 2


class CalculationPhase(Enum):
    """
    Defines the calculation phases for deal analysis.
    Each phase calculates specific deal components in sequence.
    """

    ASSET_ANALYSIS = 1  # Calculate asset-level cash flows
    ACQUISITION = 2  # Calculate acquisition costs
    FUNDING_CASCADE = 3  # Calculate funding requirements
    FINANCING = 4  # Calculate debt and equity flows
    PARTNERSHIP = 5  # Calculate partner distributions
    VALUATION = 6  # Calculate exit values and returns


class CashFlowCategoryEnum(str, Enum):
    """
    Primary categories for cash flow transactions in real estate development.

    These categories are used with amount signs to derive TransactionPurpose:
    - CAPITAL + negative amount → CAPITAL_USE (acquisition, construction costs)
    - CAPITAL + positive amount → CAPITAL_SOURCE (sale proceeds, equity contributions)
    - FINANCING + negative amount → FINANCING_SERVICE (debt service, loan fees)
    - FINANCING + positive amount → CAPITAL_SOURCE (loan proceeds, refinancing)
    - REVENUE/EXPENSE → OPERATING (day-to-day operations)
    - VALUATION → VALUATION (asset appraisals, mark-to-market, non-cash records)

    Note: Loan transactions are dual-nature:
    - Loan draws/proceeds: FINANCING category + positive amount = CAPITAL_SOURCE
    - Debt service payments: FINANCING category + negative amount = FINANCING_SERVICE
    This enables proper funding cascade analysis where loan proceeds fund capital uses.
    """

    CAPITAL = "Capital"
    EXPENSE = "Expense"
    REVENUE = "Revenue"
    FINANCING = "Financing"
    VALUATION = "Valuation"
    OTHER = "Other"


class CapitalSubcategoryEnum(str, Enum):
    """
    Subcategories for capital expenditure transactions.

    These subcategories provide detailed classification of capital outflows
    for acquisition, construction, disposition, and other capital activities.

    Attributes:
        PURCHASE_PRICE: Property acquisition purchase price (negative outflow)
        CLOSING_COSTS: Acquisition closing costs and fees (negative outflow)
        DUE_DILIGENCE: Due diligence and inspection costs (negative outflow)
        TRANSACTION_COSTS: Disposition broker fees, legal costs (negative outflow)
        HARD_COSTS: Direct construction costs - materials, labor (negative outflow)
        SOFT_COSTS: Indirect construction costs - permits, professional fees (negative)
        SITE_WORK: Site preparation and infrastructure work (negative outflow)
        OTHER: Miscellaneous capital expenditures (negative outflow)
    """

    # Acquisition subcategories
    PURCHASE_PRICE = "Purchase Price"
    CLOSING_COSTS = "Closing Costs"
    DUE_DILIGENCE = "Due Diligence"
    
    # Disposition subcategories
    TRANSACTION_COSTS = "Transaction Costs"

    # Construction subcategories
    HARD_COSTS = "Hard Costs"
    SOFT_COSTS = "Soft Costs"
    SITE_WORK = "Site Work"

    # Other capital uses
    OTHER = "Other"


class RevenueSubcategoryEnum(str, Enum):
    """
    Enum for revenue subcategories in real estate development projects.

    This enum represents revenue categories including positive revenue sources
    and negative revenue adjustments (losses/reductions).

    Attributes:
        SALE (str): Revenue from property or unit sales.
        LEASE (str): Revenue from property or unit leases.
        MISC (str): Miscellaneous income sources like parking, vending, antenna income, etc.
        RECOVERY (str): Expense recoveries from tenants (CAM, taxes, insurance, etc.).
        SECURITY_DEPOSIT (str): Security deposits collected from tenants.
        VACANCY_LOSS (str): Vacancy loss (revenue reduction from vacant units/space).
        CREDIT_LOSS (str): Credit loss (revenue reduction from uncollectable rent).
        ABATEMENT (str): Rent abatement/concessions (revenue reduction from free rent periods).
    """

    SALE = "Sale"
    LEASE = "Lease"
    MISC = "Miscellaneous"
    RECOVERY = "Recovery"
    SECURITY_DEPOSIT = "Security Deposit"

    # Revenue Adjustments (Contra-Revenue)
    VACANCY_LOSS = "Vacancy Loss"
    CREDIT_LOSS = "Credit Loss"
    ABATEMENT = "Abatement"


class ExpenseSubcategoryEnum(str, Enum):
    """
    Enum for expense subcategories in real estate development projects.

    Attributes:
        OPEX (str): Represents operational expenses.
        CAPEX (str): Represents capital expenses.
    """

    OPEX = "OpEx"
    CAPEX = "CapEx"


class ValuationSubcategoryEnum(str, Enum):
    """
    Subcategories for valuation transactions in the ledger.

    Enables detailed classification of asset valuation methods and sources
    for proper tracking, analysis, and audit trails.

    Valuation Method Subcategories:
        ASSET_VALUATION: Direct asset appraisals and valuations
        COMPARABLE_SALES: Market-based comparable sales analysis
        DCF_VALUATION: Discounted cash flow valuations
        DIRECT_CAP_VALUATION: Direct capitalization method valuations
        COST_APPROACH: Cost approach valuations
        BROKER_OPINION: Broker price opinions and estimates
    """

    ASSET_VALUATION = "Asset Valuation"
    COMPARABLE_SALES = "Comparable Sales"
    DCF_VALUATION = "DCF Valuation"
    DIRECT_CAP_VALUATION = "Direct Cap Valuation"
    COST_APPROACH = "Cost Approach"
    BROKER_OPINION = "Broker Opinion"


class FinancingSubcategoryEnum(str, Enum):
    """
    Subcategories for financing transactions in the ledger.

    Enables detailed classification of debt and equity flows for proper
    tracking, reporting, and analysis. All debt facilities should use
    these subcategories when writing to the ledger.

    Debt Flow Subcategories:
        LOAN_PROCEEDS: Initial loan funding at origination (positive inflow)
        DEBT_SERVICE: **DEPRECATED** - Use INTEREST_PAYMENT + PRINCIPAL_PAYMENT instead
        PRINCIPAL_PAYMENT: Principal portion for balance tracking (negative outflow)
        INTEREST_PAYMENT: Interest portion, actual cash expense (negative outflow)
        INTEREST_RESERVE: Interest reserve funding or draws
        PREPAYMENT: Loan payoff at property sale/disposition (negative outflow)
        REFINANCING_PROCEEDS: New loan proceeds replacing old loan (positive inflow)
        REFINANCING_PAYOFF: Old loan payoff in refinancing transaction (negative outflow)

    Equity Flow Subcategories:
        EQUITY_CONTRIBUTION: Partner capital contributions (positive inflow)
        EQUITY_DISTRIBUTION: Distributions to equity partners (negative outflow)
        PREFERRED_RETURN: Preferred return payments (negative outflow)
        PROMOTE: Carried interest/promote payments (negative outflow)

    Fee Flow Subcategories:
        ORIGINATION_FEE: Loan origination fees (negative outflow)
        EXIT_FEE: Loan exit fees (negative outflow)
        PREPAYMENT_PENALTY: Early repayment penalties (negative outflow)
    
    Usage Notes:
        - Use PREPAYMENT for disposition, REFINANCING_PAYOFF for refinancing
        - PRINCIPAL_PAYMENT tracks balance and is a cash outflow
        - All facilities should use disaggregated I&P approach for consistency
    """

    # Core debt flows
    LOAN_PROCEEDS = "Loan Proceeds"
    # DEBT_SERVICE = "Debt Service"  # DEPRECATED: Use INTEREST_PAYMENT + PRINCIPAL_PAYMENT
    PRINCIPAL_PAYMENT = "Principal Payment"
    INTEREST_PAYMENT = "Interest Payment"
    INTEREST_RESERVE = "Interest Reserve"
    PREPAYMENT = "Prepayment"

    # Refinancing flows
    REFINANCING_PROCEEDS = "Refinancing Proceeds"
    REFINANCING_PAYOFF = "Refinancing Payoff"

    # Equity flows
    EQUITY_CONTRIBUTION = "Equity Contribution"
    EQUITY_DISTRIBUTION = "Equity Distribution"
    PREFERRED_RETURN = "Preferred Return"
    PROMOTE = "Promote"

    # Fee flows
    ORIGINATION_FEE = "Origination Fee"
    EXIT_FEE = "Exit Fee"
    PREPAYMENT_PENALTY = "Prepayment Penalty"


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
    that cash flow models can multiply against for precise calculations.

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

    Covers all major categories of capital improvements and renovations
    in commercial real estate development and operations.
    """

    BUILDING = "building"
    MECHANICAL = "mechanical"
    TENANT = "tenant"
    SITE = "site"
    RENOVATION = "renovation"
    MAJOR_REPAIRS = "major_repairs"
    SYSTEM_UPGRADES = "system_upgrades"
    LEASING_COSTS = "leasing_costs"


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
        MARKET:   Weighted average approach based on market conditions, reflecting both new tenant and
                  renewal probabilities. Creates a speculative lease with blended terms.
        RENEW:    Assumes 100% renewal probability, extending the lease under predetermined terms.
                  Creates a renewal lease using either contractual terms or renewal market assumptions.
        VACATE:   Assumes 0% renewal probability, with space immediately available for new tenant.
                  Creates a new speculative lease at current market rates after downtime.
        OPTION:   Models a contractual renewal option as a distinct lease. Treats the option terms
                  as a separate lease record that activates upon expiration if exercised.
        REABSORB: Triggers a unit transformation workflow. The unit is taken offline and made
                  available to an AbsorptionPlan for re-leasing, typically after renovation.
                  When used with optional RolloverProfile.target_absorption_plan_id, this enables
                  modeling of rolling value-add scenarios where units are sequentially
                  renovated and re-leased at premium rents. No speculative lease is created
                  automatically - the transformation is handled by the specified AbsorptionPlan.
    """

    MARKET = "market"  # Weighted average approach using market conditions
    RENEW = "renew"  # 100% renewal with predetermined terms
    VACATE = "vacate"  # 0% renewal, immediate repositioning with new tenant
    OPTION = "option"  # Explicit modeling of contractual renewal options
    REABSORB = "reabsorb"  # Space remains vacant pending separate re-leasing process


class VacancyLossMethodEnum(str, Enum):
    """How General Vacancy is calculated and applied in the waterfall."""

    POTENTIAL_GROSS_REVENUE = "Potential Gross Revenue"  # % of PGR line
    EFFECTIVE_GROSS_INCOME = (
        "Effective Gross Income"  # % of (PGR + Misc Inc - Abatement)
    )


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
    GROSS_POTENTIAL_RENT = (
        "Gross Potential Rent"  # Base rent only at 100% physical occupancy
    )
    POTENTIAL_GROSS_REVENUE = "Potential Gross Revenue"  # All revenue at 100% occupancy (rent + recoveries + other income)
    TENANT_REVENUE = "Tenant Revenue"  # Rent + recoveries (excludes non-tenant income like parking/antenna)
    RENTAL_ABATEMENT = "Rental Abatement / Concessions"  # Free rent periods
    MISCELLANEOUS_INCOME = "Miscellaneous Income"  # Parking, laundry, fees, etc.
    GENERAL_VACANCY_LOSS = (
        "General Vacancy & Credit Loss"  # Allowance based on market/assumptions
    )
    CREDIT_LOSS = "Credit Loss"  # Allowance for uncollectible income
    EXPENSE_REIMBURSEMENTS = "Expense Reimbursements"  # Recoveries from tenants
    EFFECTIVE_GROSS_INCOME = "Effective Gross Income"  # PGR + Misc - Abatement - Vacancy + Recoveries (industry standard EGI)

    # --- Expense Side ---
    TOTAL_OPERATING_EXPENSES = "Total Operating Expenses"  # Sum of all OpEx items

    # --- Profitability Metrics ---
    NET_OPERATING_INCOME = "Net Operating Income"  # Total EGI - Total OpEx

    # --- Capital & Leasing Costs ---
    TOTAL_TENANT_IMPROVEMENTS = "Total Tenant Improvements"  # TIs
    TOTAL_LEASING_COMMISSIONS = "Total Leasing Commissions"  # LCs
    TOTAL_CAPITAL_EXPENDITURES = (
        "Total Capital Expenditures"  # CapEx (incl. reserves maybe)
    )

    # --- Unlevered Cash Flow ---
    UNLEVERED_CASH_FLOW = "Unlevered Cash Flow"  # NOI - TIs - LCs - CapEx

    # Vacancy & Loss Specifics
    DOWNTIME_VACANCY_LOSS = "Downtime Vacancy Loss"  # Added for initial vacancy
    ROLLOVER_VACANCY_LOSS = (
        "Rollover Vacancy Loss"  # Placeholder if aggregated separately
    )

    @classmethod
    def from_value(cls, value: str) -> Optional["UnleveredAggregateLineKey"]:
        """Look up enum member by its string value."""
        for member in cls:
            if member.value == value:
                return member
        return None


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

    @classmethod
    def from_value(cls, value: str) -> Optional["LeveredAggregateLineKey"]:
        """Look up enum member by its string value."""
        for member in cls:
            if member.value == value:
                return member
        return None


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


class InterestCalculationMethod(str, Enum):
    """
    Method for calculating construction interest and debt sizing.

    Provides a complexity dial for construction financing to match
    project sophistication needs while maintaining industry alignment.

    Methods:
        NONE: No interest calculation - draws only
        SIMPLE: Quick percentage-based reserve estimate (industry: 8-12%)
        SCHEDULED: Sophisticated draw-based calculation using actual schedules (industry standard)
        ITERATIVE: Full multi-pass iteration for maximum precision (future enhancement)
    """

    NONE = "none"
    SIMPLE = "simple"

    SCHEDULED = "scheduled"
    ITERATIVE = "iterative"


class TransactionPurpose(str, Enum):
    """
    High-level classification of transaction purposes in the ledger.

    Provides unambiguous categorization of financial flows following
    standard real estate accounting principles.

    Categories:
        OPERATING: Day-to-day property operations (revenue and expenses)
        CAPITAL_USE: Capital deployed for acquisition, improvements, or development
        CAPITAL_SOURCE: Capital raised from sales, refinancing, or equity contributions
        FINANCING_SERVICE: Debt service payments and financing-related flows
    """

    OPERATING = "Operating"
    """
    Day-to-day property operations including all revenue and operating expenses.
    - Revenue: Rent, miscellaneous income, expense recoveries
    - Expenses: Property taxes, insurance, utilities, maintenance, management
    - Both positive (income) and negative (expense) amounts
    """

    CAPITAL_USE = "Capital Use"
    """
    Capital deployed for property acquisition, improvements, or development.
    - Acquisition costs and fees
    - Tenant improvements and leasing commissions
    - Capital expenditures and major renovations
    - Development costs and construction
    - Typically negative amounts (cash outflows)
    """

    CAPITAL_SOURCE = "Capital Source"
    """
    Capital raised from asset sales, refinancing, equity, or debt financing.
    - Property sale proceeds
    - Loan proceeds and refinancing (gross)
    - Equity contributions from partners
    - Return of capital to partners
    - Debt draws during construction/development
    - Typically positive amounts (cash inflows that fund capital uses)
    """

    FINANCING_SERVICE = "Financing Service"
    """
    Debt service payments and financing-related obligations.
    - Principal and interest payments
    - Loan fees and financing costs
    - Prepayment penalties
    - Typically negative amounts (cash outflows)
    """

    VALUATION = "Valuation"
    # FIXME: are we sure this should be a transaction purpose? is this the right name?
    """
    Asset valuation and appraisal records for ledger-based analytics.
    - Property appraisals and market valuations
    - DCF-based valuations
    - Comparable sales valuations
    - Internal mark-to-market adjustments
    - Zero cash flow impact (non-transactional)
    """


# =============================================================================
# ENUM UTILITIES FOR PANDAS COMPATIBILITY
# =============================================================================


def enum_to_string(value) -> str:
    """
    Convert enum values to their string representation for pandas storage.

    This ensures consistent string-based operations in DataFrames while
    maintaining the semantic meaning of enum values.

    Args:
        value: Any value, but primarily expected to be enum instances

    Returns:
        String representation of the enum value, or str(value) for non-enums

    Examples:
        >>> enum_to_string(CashFlowCategoryEnum.EXPENSE)
        'Expense'
        >>> enum_to_string("already_string")
        'already_string'
    """
    if isinstance(value, Enum):
        return value.value  # Get the actual string value (e.g., "Expense")
    return str(value)
