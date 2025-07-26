# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import pandas as pd

from performa.core.base import LeaseBase, OpExItemBase, RecoveryMethodBase

if TYPE_CHECKING:
    from performa.analysis import AnalysisContext


logger = logging.getLogger(__name__)


class CommercialRecoveryMethodBase(RecoveryMethodBase):

    def compute_cf(self, context: AnalysisContext, lease: "LeaseBase") -> pd.Series:
        total_recoveries = pd.Series(0.0, index=context.timeline.period_index)
        logger.debug(f"Calculating recoveries for method '{self.name}' on lease '{lease.name}'")

        if self.gross_up and context.occupancy_rate_series is None:
            logger.warning(f"Gross-up enabled for '{self.name}' but occupancy_rate_series not available in context.")

        for recovery_item in self.recoveries:
            logger.debug(f"Processing recovery for expense pool: {recovery_item.expense_pool.name}, Structure: {recovery_item.structure}")

            current_recovery_state = context.recovery_states.get(recovery_item.uid)
            if current_recovery_state is None:
                logger.warning(f"No recovery state found for recovery model ID {recovery_item.uid}. Skipping.")
                continue

            expense_pool = recovery_item.expense_pool
            items_in_pool = expense_pool.expenses if isinstance(expense_pool.expenses, list) else [expense_pool.expenses]
            pool_expense_cf = pd.Series(0.0, index=context.timeline.period_index)

            for item in items_in_pool:
                is_opex_item = isinstance(item, OpExItemBase)
                variable_ratio = item.variable_ratio if is_opex_item and item.variable_ratio is not None else 0.0

                try:
                    raw_item_cf = context.resolved_lookups[item.uid]
                    if not isinstance(raw_item_cf, pd.Series):
                        raise TypeError(f"Resolved lookup for {item.name} is not a Series.")
                except (KeyError, TypeError) as e:
                    logger.error(f"Failed to resolve cash flow for expense item {item.name} ({item.uid}). Error: {e}")
                    continue
                
                item_cf_to_add = raw_item_cf
                if self.gross_up and is_opex_item and item.is_recoverable:
                    if context.occupancy_rate_series is not None:
                        target_occupancy = self.gross_up_percent or 0.95
                        
                        if isinstance(context.occupancy_rate_series, pd.Series):
                            needs_gross_up = context.occupancy_rate_series < target_occupancy
                            # Only apply gross-up when occupancy is below target
                            if needs_gross_up.any():
                                safe_occupancy = context.occupancy_rate_series.where(context.occupancy_rate_series > 0, 0.0001)
                                
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
                        elif context.occupancy_rate_series < target_occupancy:
                            safe_occupancy = context.occupancy_rate_series if context.occupancy_rate_series > 0 else 0.0001

                            if variable_ratio > 0:
                                # Traditional variable/fixed split logic
                                fixed_part = raw_item_cf * (1.0 - variable_ratio)
                                variable_part = raw_item_cf * variable_ratio
                                grossed_up_variable = variable_part / safe_occupancy
                                item_cf_to_add = fixed_part + grossed_up_variable
                            else:
                                # Gross-up entire recoverable expense
                                item_cf_to_add = raw_item_cf / safe_occupancy * target_occupancy

                pool_expense_cf = pool_expense_cf.add(item_cf_to_add, fill_value=0.0)
            
            denominator = context.property_data.net_rentable_area
            if expense_pool.pool_size_override is not None and expense_pool.pool_size_override > 0:
                denominator = expense_pool.pool_size_override
            
            if denominator <= 0:
                logger.error(f"Invalid denominator ({denominator}) for recovery pool {expense_pool.name}. Skipping.")
                continue

            pro_rata = recovery_item.prorata_share or (lease.area / denominator)
            
            recovery_cf = pd.Series(0.0, index=context.timeline.period_index)
            if recovery_item.structure == "net":
                recovery_cf = pool_expense_cf * pro_rata
            elif recovery_item.structure == "base_stop":
                tenant_annual_stop = (recovery_item.base_amount * pro_rata) if recovery_item.base_amount_unit == "total" else (recovery_item.base_amount * lease.area)
                monthly_stop = tenant_annual_stop / 12.0
                recovery_cf = (pool_expense_cf * pro_rata - monthly_stop).clip(lower=0)
            elif recovery_item.structure in ["base_year", "base_year_plus1", "base_year_minus1"]:
                annual_base_year_stop = current_recovery_state.calculated_annual_base_year_stop
                if annual_base_year_stop is not None:
                    monthly_stop = annual_base_year_stop / 12.0
                    share_to_use = current_recovery_state.frozen_base_year_pro_rata or pro_rata
                    monthly_recoverable = (pool_expense_cf - monthly_stop).clip(lower=0)
                    
                    # Apply year-over-year cap if specified
                    if recovery_item.yoy_max_growth is not None and recovery_item.yoy_max_growth > 0:
                        # Calculate years from base year to current analysis period
                        base_year = recovery_item.base_year
                        if base_year:
                            current_year = context.timeline.start_date.year
                            years_from_base = current_year - base_year
                            
                            if years_from_base > 0:
                                # Calculate maximum allowable annual expense under cap
                                # Formula: base_year × (1 + cap)^years
                                max_annual_under_cap = annual_base_year_stop * ((1 + recovery_item.yoy_max_growth) ** years_from_base)
                                max_monthly_under_cap = max_annual_under_cap / 12.0
                                
                                # Cap the pool expense to prevent excessive increases
                                # Cap applies to total pool expense, not just the recoverable portion
                                current_monthly_expense = pool_expense_cf
                                capped_monthly_expense = pd.Series(max_monthly_under_cap, index=context.timeline.period_index)
                                
                                # Use the lesser of actual expense or capped expense
                                pool_expense_cf_capped = pd.Series(index=context.timeline.period_index, dtype=float)
                                for period in context.timeline.period_index:
                                    pool_expense_cf_capped[period] = min(current_monthly_expense[period], capped_monthly_expense[period])
                                
                                # Recalculate recoverable with capped expenses
                                monthly_recoverable = (pool_expense_cf_capped - monthly_stop).clip(lower=0)
                    
                    recovery_cf = monthly_recoverable * share_to_use
            elif recovery_item.structure == "fixed":
                recovery_cf = pd.Series(recovery_item.base_amount / 12.0, index=context.timeline.period_index)

            if recovery_item.admin_fee_percent:
                recovery_cf *= (1.0 + recovery_item.admin_fee_percent)
            if recovery_item.recovery_ceiling:
                recovery_cf = recovery_cf.clip(upper=recovery_item.recovery_ceiling / 12.0)
            if recovery_item.recovery_floor:
                recovery_cf = recovery_cf.clip(lower=recovery_item.recovery_floor / 12.0)

            total_recoveries = total_recoveries.add(recovery_cf, fill_value=0.0)

        return total_recoveries
