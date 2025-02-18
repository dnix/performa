from datetime import date
from typing import Literal, Optional

from ..utils._model import Model
from ..utils._types import FloatBetween0And1


class GlobalSettings(Model):
    """Global model settings"""

    analysis_start_date: date
    analysis_period_months: int = 120  # 10 years default
    inflation_month: Optional[int] = None
    allow_specific_dates: bool = False
    allow_manual_property_size: bool = False


class VacancySettings(Model):
    """Vacancy and collection loss settings"""

    vacancy_loss_method: Literal["potential_gross", "effective_gross", "noi"]
    gross_up_by_downtime: bool = False
    reduce_vacancy_by_downtime: bool = False


class PercentageRentSettings(Model):
    """Percentage rent and occupancy cost settings"""

    in_use: bool = False
    adjustment_direction: Literal["downward"] = "downward"
    include_recoveries: bool = True
    adjust_during: Literal["rollover"] = "rollover"


class RecoverySettings(Model):
    """Recovery calculation settings"""

    admin_fee_timing: Literal["before", "after"] = "after"
    treat_circular_refs_as: Literal["error", "warning"] = "error"


class RolloverSettings(Model):
    """Rollover lease settings"""

    start_on_first_of_month: bool = False
    renewal_probability: FloatBetween0And1
    default_term_months: int
    downtime_months: int
