# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, List, Literal, Optional, Union
from uuid import UUID, uuid4

import pandas as pd
from pydantic import Field

from ...core.base import ExpensePoolBase as CoreExpensePoolBase
from ...core.base import OpExItemBase, RecoveryBase
from ...core.primitives import GlobalSettings, PercentageGrowthRate
from ..commercial.recovery import CommercialRecoveryMethodBase

logger = logging.getLogger(__name__)


@dataclass
class RecoveryCalculationState:
    """
    Holds pre-calculated, mutable state for a Recovery object during analysis.
    """

    recovery_uid: UUID
    calculated_annual_base_year_stop: Optional[float] = None
    frozen_base_year_pro_rata: Optional[float] = None


class ExpensePool(CoreExpensePoolBase):
    def compute_cf(
        self,
        timeline: pd.PeriodIndex,
        occupancy_rate: Optional[Union[float, pd.Series]] = None,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Any]] = None,
        global_settings: Optional[GlobalSettings] = None,
    ) -> pd.Series:
        pool_cf = pd.Series(0, index=timeline)
        expenses_to_process = (
            self.expenses if isinstance(self.expenses, list) else [self.expenses]
        )

        for expense in expenses_to_process:
            expense_cf = expense.compute_cf(
                occupancy_rate=occupancy_rate,
                lookup_fn=lookup_fn,
                global_settings=global_settings,
            )
            expense_cf = expense_cf.reindex(timeline, fill_value=0)
            pool_cf += expense_cf
        return pool_cf


class Recovery(RecoveryBase):
    uid: UUID = Field(default_factory=uuid4)
    expenses: Union[ExpensePool, OpExItemBase]
    structure: Literal[
        "net", "base_stop", "fixed", "base_year", "base_year_plus1", "base_year_minus1"
    ]
    base_amount: Optional[float] = None
    base_amount_unit: Optional[Literal["total", "psf"]] = "psf"
    base_year: Optional[int] = None
    growth_rate: Optional[PercentageGrowthRate] = None
    admin_fee_percent: Optional[float] = None
    prorata_share: Optional[float] = None
    denominator: Optional[float] = None
    yoy_max_growth: Optional[float] = None
    recovery_ceiling: Optional[float] = None
    recovery_floor: Optional[float] = None

    @property
    def expense_pool(self) -> ExpensePool:
        if isinstance(self.expenses, OpExItemBase):
            return ExpensePool(
                name=f"{self.expenses.name} Pool", expenses=[self.expenses]
            )
        return self.expenses


class OfficeRecoveryMethod(CommercialRecoveryMethodBase):
    """
    Office-specific recovery method.

    Inherits all recovery calculation logic from CommercialRecoveryMethodBase,
    including support for multiple recovery structures (net, base_stop, base_year,
    fixed), gross-up functionality, frozen pro-rata shares for base year recoveries,
    and year-over-year growth caps.
    """

    recoveries: List[RecoveryBase]
