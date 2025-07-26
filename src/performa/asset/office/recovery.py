# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Literal, Optional, Union
from uuid import UUID, uuid4

import pandas as pd
from pydantic import Field, model_validator

from ...core.base import ExpensePoolBase as CoreExpensePoolBase
from ...core.base import OpExItemBase, RecoveryBase, RecoveryMethodBase
from ...core.primitives import GlobalSettings, GrowthRate, Model
from ..commercial.recovery import CommercialRecoveryMethodBase

if TYPE_CHECKING:
    from .property import OfficeProperty

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
        expenses_to_process = self.expenses if isinstance(self.expenses, list) else [self.expenses]

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
    growth_rate: Optional[GrowthRate] = None
    admin_fee_percent: Optional[float] = None
    prorata_share: Optional[float] = None
    denominator: Optional[float] = None
    yoy_max_growth: Optional[float] = None
    recovery_ceiling: Optional[float] = None
    recovery_floor: Optional[float] = None

    @property
    def expense_pool(self) -> ExpensePool:
        if isinstance(self.expenses, OpExItemBase):
            return ExpensePool(name=f"{self.expenses.name} Pool", expenses=[self.expenses])
        return self.expenses


class OfficeRecoveryMethod(CommercialRecoveryMethodBase):
    """
    Office-specific recovery method. Inherits core calculation logic 
    from CommercialRecoveryMethodBase.
    
    TODO: Future GlobalSettings integration for cap functionality
    Currently caps are implemented at the Recovery level via yoy_max_growth.
    Future enhancement could integrate with GlobalSettings.recoveries for:
    - Portfolio-wide default cap rates
    - Property-type specific cap policies  
    - Cap validation and business logic enforcement
    - Standardized cap methodologies across portfolio
    """
    recoveries: List[RecoveryBase]

    def calculate_recoveries(
        self,
        tenant_area: float,
        property_data: OfficeProperty,
        timeline: pd.PeriodIndex,
        recovery_states: Dict[UUID, RecoveryCalculationState],
        occupancy_rate: Optional[Union[float, pd.Series]] = None,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Any]] = None,
        global_settings: Optional[GlobalSettings] = None,
    ) -> pd.Series:
        total_recoveries = pd.Series(0.0, index=timeline)
        if lookup_fn is None:
            raise LookupError("lookup_fn is required for recovery calculations.")

        for recovery_item in self.recoveries:
            state = recovery_states.get(recovery_item.uid)
            if not state:
                logger.warning(f"No state for recovery {recovery_item.uid}, skipping.")
                continue

            pool_cf = self._get_pool_cash_flow(recovery_item, timeline, occupancy_rate, lookup_fn, global_settings)
            
            pro_rata = tenant_area / (recovery_item.denominator or property_data.net_rentable_area)

            recovery_cf = pd.Series(0.0, index=timeline)
            if recovery_item.structure == "net":
                recovery_cf = pool_cf * pro_rata
            elif recovery_item.structure == "base_stop":
                monthly_stop = (recovery_item.base_amount * (tenant_area if recovery_item.base_amount_unit == 'psf' else pro_rata)) / 12
                recovery_cf = (pool_cf * pro_rata - monthly_stop).clip(lower=0)
            elif recovery_item.structure in ["base_year", "base_year_plus1", "base_year_minus1"]:
                monthly_stop = (state.calculated_annual_base_year_stop or 0) / 12
                recovery_cf = (pool_cf - monthly_stop).clip(lower=0) * pro_rata
            elif recovery_item.structure == "fixed":
                recovery_cf = pd.Series((recovery_item.base_amount or 0) / 12, index=timeline)
            
            if recovery_item.admin_fee_percent:
                recovery_cf *= (1 + recovery_item.admin_fee_percent)
            if recovery_item.recovery_ceiling:
                recovery_cf = recovery_cf.clip(upper=recovery_item.recovery_ceiling / 12)
            if recovery_item.recovery_floor:
                recovery_cf = recovery_cf.clip(lower=recovery_item.recovery_floor / 12)

            total_recoveries += recovery_cf
        return total_recoveries

    def _get_pool_cash_flow(self, recovery_item, timeline, occupancy_rate, lookup_fn, global_settings):
        pool_expense_cf = pd.Series(0.0, index=timeline)
        expense_pool = recovery_item.expense_pool
        items_in_pool = expense_pool.expenses if isinstance(expense_pool.expenses, list) else [expense_pool.expenses]

        for item in items_in_pool:
            raw_item_cf = lookup_fn(item.uid)
            item_cf_to_add = raw_item_cf

            if isinstance(item, OpExItemBase) and item.is_recoverable and self.gross_up and occupancy_rate is not None:
                variable_ratio = item.variable_ratio or 0.0
                target_occupancy = self.gross_up_percent or 0.95
                
                if isinstance(occupancy_rate, pd.Series):
                    aligned_occupancy = occupancy_rate.reindex(timeline, method="ffill").fillna(1.0)
                    needs_gross_up = aligned_occupancy < target_occupancy
                    # Only apply gross-up when occupancy is below target
                    if needs_gross_up.any():
                        safe_occupancy = aligned_occupancy.where(aligned_occupancy > 0, 0.0001)
                        
                        if variable_ratio > 0:
                            # For expenses with explicit variable_ratio, use traditional logic
                            fixed_part = raw_item_cf * (1.0 - variable_ratio)
                            variable_part = raw_item_cf * variable_ratio
                            grossed_up_variable = variable_part / safe_occupancy
                            item_cf_to_add = fixed_part + variable_part.where(~needs_gross_up, grossed_up_variable)
                        else:
                            # For recoverable expenses without explicit variable_ratio,
                            # apply gross-up to entire expense when occupancy < target
                            grossed_up_amount = raw_item_cf / safe_occupancy * target_occupancy
                            item_cf_to_add = raw_item_cf.where(~needs_gross_up, grossed_up_amount)
                elif occupancy_rate < target_occupancy:
                    safe_occupancy = occupancy_rate if occupancy_rate > 0 else 0.0001
                    
                    if variable_ratio > 0:
                        # Traditional variable/fixed split logic
                        fixed_part = raw_item_cf * (1.0 - variable_ratio)
                        variable_part = raw_item_cf * variable_ratio
                        grossed_up_variable = variable_part / safe_occupancy
                        item_cf_to_add = fixed_part + grossed_up_variable
                    else:
                        # Gross-up entire recoverable expense
                        item_cf_to_add = raw_item_cf / safe_occupancy * target_occupancy

            pool_expense_cf += item_cf_to_add.reindex(timeline, fill_value=0.0)
        return pool_expense_cf 