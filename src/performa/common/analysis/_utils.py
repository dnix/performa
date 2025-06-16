# src/performa/common/analysis/_utils.py
# This file will house common calculation utilities for the analysis engine. 

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING, Dict, List, Optional, Union
from uuid import UUID

import pandas as pd

if TYPE_CHECKING:
    from ..base._expense_base import ExpenseItemBase, OpExItemBase
    from ..base._property_base import PropertyBaseModel
    from ..base._recovery_base import RecoveryBase, RecoveryCalculationState
    from ..primitives._timeline import Timeline


logger = logging.getLogger(__name__)


def pre_calculate_all_base_year_stops(
    property_data: "PropertyBaseModel",
    analysis_timeline: "Timeline"
) -> Dict[UUID, "RecoveryCalculationState"]:
    """
    Pre-calculates all base year and base stop amounts for all relevant leases.
    FIXME: This is a placeholder implementation.
    """
    #
    # Full logic would involve:
    # 1. Finding all leases with base_year or base_stop recovery methods.
    # 2. For each lease, identifying the relevant base year.
    # 3. Looking up historical expense data for that year.
    # 4. Applying gross-up logic if necessary.
    # 5. Storing the calculated stop amount in a RecoveryCalculationState object.
    #
    return {}


def get_period_occupancy(
    property_data: "PropertyBaseModel",
    period_start: date,
    period_end: date,
    frequency: str = "M",
) -> Optional[pd.Series]:
    # Logic from get_period_occupancy, adapted for PropertyBaseModel
    return None


def get_period_expenses(
    property_data: "PropertyBaseModel",
    period_start: date,
    period_end: date,
    expense_item_ids: List[UUID],
    frequency: str = "M",
) -> Optional[Dict[UUID, pd.Series]]:
    # Logic from get_period_expenses, adapted for PropertyBaseModel
    return None


def gross_up_period_expenses(
    raw_expenses: Dict[UUID, pd.Series],
    occupancy_series: pd.Series,
    expense_items_map: Dict[UUID, "ExpenseItemBase"],
    gross_up_target_rate: float = 0.95,
) -> Dict[UUID, pd.Series]:
    # Logic from gross_up_period_expenses, adapted for ExpenseItemBase/OpExItemBase
    return {}
