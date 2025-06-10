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


logger = logging.getLogger(__name__)


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