from datetime import date
from enum import Enum
from typing import Optional

from ._enums import FrequencyEnum
from ._model import Model


class DayCountConvention(str, Enum):
    """Day count conventions for financial calculations"""
    # FIXME: actually add support for these
    THIRTY_360 = "30/360"
    ACTUAL_365 = "Actual/365"
    ACTUAL_360 = "Actual/360"
    ACTUAL_ACTUAL = "Actual/Actual"


class GlobalSettings(Model):
    """Global model settings

    Configures global parameters that affect the entire financial model.
    """
    # FIXME: actually add support for these modeling policies
    
    # FIXME: we should have reasonable default settings for each modeling policy,
    # FIXME: so we require minimal config here

    # Analysis period configuration
    analysis_start_date: date
    analysis_period_months: int = 120  # 10 years default
    inflation_month: Optional[int] = None
    
    # Fiscal and calendar settings
    fiscal_year_start_month: int = 1  # January
    day_count_convention: DayCountConvention = DayCountConvention.ACTUAL_ACTUAL
    
    # Calculation settings
    calculation_frequency: FrequencyEnum = FrequencyEnum.MONTHLY
    reporting_frequency: FrequencyEnum = FrequencyEnum.ANNUAL
    decimal_precision: int = 2
    
    # # Currency and internationalization
    # currency_code: str = "USD"  # TODO: add enum (and support for non-USD)
    # enable_multi_currency: bool = False
    
    # # Taxation settings
    # include_tax_calculations: bool = False
    # default_tax_rate: Optional[float] = None


# class VacancySettings(Model):
#     """Vacancy and collection loss settings"""

#     vacancy_loss_method: Literal["potential_gross", "effective_gross", "noi"]
#     gross_up_by_downtime: bool = False
#     reduce_vacancy_by_downtime: bool = False


# class PercentageRentSettings(Model):
#     """Percentage rent and occupancy cost settings"""

#     in_use: bool = False
#     adjustment_direction: Literal["downward"] = "downward"
#     include_recoveries: bool = True
#     adjust_during: Literal["rollover"] = "rollover"
