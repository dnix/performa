from __future__ import annotations

from enum import Enum
from typing import List, Optional


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


class UnitOfMeasureEnum(str, Enum):
    """
    Units for amounts.

    Options:
        CURRENCY: Absolute currency amount (e.g., total dollars)
        PER_UNIT: Amount per defined unit (e.g., $/sqft, $/unit)
        BY_FACTOR: Factor relative to a reference amount (e.g., 1.1x)
        BY_PERCENT: Percentage relative to a reference amount (e.g., 5% of EGI)
    """

    CURRENCY = "currency"
    PER_UNIT = "per_unit"
    BY_FACTOR = "factor"
    BY_PERCENT = "percent"


class AssetTypeEnum(str, Enum):
    """
    Type of real estate asset.
    """

    OFFICE = "office"
    RETAIL = "retail"
    INDUSTRIAL = "industrial"
    MULTIFAMILY = "multifamily"
    MIXED_USE = "mixed_use"


class ProgramUseEnum(str, Enum):
    """
    Specific program use type within an asset.
    """

    OFFICE = "office"
    RETAIL = "retail"
    RESIDENTIAL = "residential"
    INDUSTRIAL = "industrial"
    STORAGE = "storage"
    PARKING = "parking"
    AMENITY = "amenity"


class UponExpirationEnum(str, Enum):
    """
    Defines behavior when a lease expires.
    """

    MARKET = "market"
    RENEW = "renew"
    VACATE = "vacate"
    OPTION = "option"
    REABSORB = "reabsorb"


class LeaseStatusEnum(str, Enum):
    """
    Status of a lease.
    """

    CONTRACT = "contract"
    SPECULATIVE = "speculative"


class AggregateLineKey(str, Enum):
    """Defines standard keys for aggregated financial line items."""

    POTENTIAL_GROSS_REVENUE = "Potential Gross Revenue"
    RENTAL_ABATEMENT = "Rental Abatement / Concessions"
    MISCELLANEOUS_INCOME = "Miscellaneous Income"
    EFFECTIVE_GROSS_REVENUE = "Effective Gross Revenue"
    GENERAL_VACANCY_LOSS = "General Vacancy & Credit Loss"
    COLLECTION_LOSS = "Collection Loss"
    EXPENSE_REIMBURSEMENTS = "Expense Reimbursements"
    TOTAL_EFFECTIVE_GROSS_INCOME = "Total Effective Gross Income"
    TOTAL_OPERATING_EXPENSES = "Total Operating Expenses"
    NET_OPERATING_INCOME = "Net Operating Income"
    TOTAL_TENANT_IMPROVEMENTS = "Total Tenant Improvements"
    TOTAL_LEASING_COMMISSIONS = "Total Leasing Commissions"
    TOTAL_CAPITAL_EXPENDITURES = "Total Capital Expenditures"
    UNLEVERED_CASH_FLOW = "Unlevered Cash Flow"
    TOTAL_DEBT_SERVICE = "Total Debt Service"
    LEVERED_CASH_FLOW = "Levered Cash Flow"
    _RAW_TOTAL_REVENUE = "_RAW Total Revenue"
    _RAW_TOTAL_RECOVERIES = "_RAW Total Recoveries"
    _RAW_TOTAL_OPEX = "_RAW Total OpEx"
    _RAW_TOTAL_CAPEX = "_RAW Total CapEx"
    _RAW_TOTAL_TI = "_RAW Total TI"
    _RAW_TOTAL_LC = "_RAW Total LC"
    DOWNTIME_VACANCY_LOSS = "Downtime Vacancy Loss"
    ROLLOVER_VACANCY_LOSS = "Rollover Vacancy Loss"

    @classmethod
    def from_value(cls, value: str) -> Optional["AggregateLineKey"]:
        for member in cls:
            if member.value == value:
                return member
        return None

    @classmethod
    def is_internal_key(cls, key: "AggregateLineKey") -> bool:
        return key.value.startswith("_RAW")

    @classmethod
    def get_display_keys(cls) -> List["AggregateLineKey"]:
        return [k for k in cls if not cls.is_internal_key(k)]


class StartDateAnchorEnum(str, Enum):
    """Defines how the absorption start date is determined."""

    ANALYSIS_START = "AnalysisStart" 