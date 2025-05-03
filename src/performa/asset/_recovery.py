import logging
from datetime import date
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Literal, Optional, Union
from uuid import UUID

import pandas as pd
from pydantic import model_validator

from ..core._model import Model
from ..core._settings import GlobalSettings
from ..core._types import FloatBetween0And1, PositiveFloat
from ._expense import ExpenseItem, OpExItem
from ._growth_rates import GrowthRate

if TYPE_CHECKING:
    from ._property import Property

logger = logging.getLogger(__name__)

class ExpensePool(Model):
    """
    Group of related expenses for recovery.
    
    An expense pool represents a group of expenses that are recovered together.
    This can be defined either by including actual expense items or by specifying
    expense categories that should be included.
    
    Attributes:
        name: Name of the expense pool (e.g., "Operating Expenses", "Tax", "Insurance")
        expenses: One or more expense items in this pool
        pool_size_override: Optional denominator override
    """
    name: str
    expenses: Union[ExpenseItem, List[ExpenseItem]]
    pool_size_override: Optional[PositiveFloat] = None # Optional denominator override
    
    def compute_cf(
        self, 
        timeline: pd.PeriodIndex, 
        occupancy_rate: Optional[Union[float, pd.Series]] = None,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Any]] = None,
        global_settings: Optional[GlobalSettings] = None
    ) -> pd.Series:
        """
        Calculate total expenses in this pool.
        
        Args:
            timeline: PeriodIndex to align expense cash flows
            occupancy_rate: Optional occupancy rate for variable expenses
            lookup_fn: Optional lookup function to resolve expense item references.
            global_settings: Optional global settings for underlying item calculations.
            
        Returns:
            Series of total expenses by period
        """
        # Initialize with zeros for the timeline
        pool_cf = pd.Series(0, index=timeline)
        
        # Handle single expense case
        if isinstance(self.expenses, ExpenseItem):
            expense_cf = self.expenses.compute_cf(
                occupancy_rate=occupancy_rate,
                lookup_fn=lookup_fn,
                global_settings=global_settings
            )
            expense_cf = expense_cf.reindex(timeline, fill_value=0)
            return expense_cf
            
        # Handle list of expenses
        for expense in self.expenses:
            expense_cf = expense.compute_cf(
                occupancy_rate=occupancy_rate,
                lookup_fn=lookup_fn,
                global_settings=global_settings
            )
            # Reindex to match timeline
            expense_cf = expense_cf.reindex(timeline, fill_value=0)
            pool_cf += expense_cf
            
        return pool_cf
    

class Recovery(Model):
    """
    Model for cost recovery as defined by Argus Enterprise/Valuation DCF.

    Attributes:
        expenses: Expense pool or individual expense item to recover
        structure: Indicates the recovery structure, which can be one of:
            "net", "base_stop", "fixed", "base_year",
            "base_year_plus1", or "base_year_minus1", mapping directly to Argus options.
        base_amount: Base amount used in fixed or base-stop recovery calculations.
        base_amount_unit: Unit for base_amount (Total $ or $/SF)
        growth_rate: Optional growth rate applied to recoveries.
        contribution_deduction: Deduction applied (if any) to tenant contributions.
        admin_fee_percent: Administrative fee percent applied on recoveries.
        prorata_share: The lease-specific share for allocation.
        denominator: The overall property area used in the allocation process.
        yoy_min_growth: Minimum allowed year-over-year recovery growth.
        yoy_max_growth: Maximum allowed year-over-year recovery growth.
        recovery_floor: Minimum recovery limit (floor).
        recovery_ceiling: Maximum recovery limit (ceiling).
    """
    expenses: Union[ExpensePool, ExpenseItem]
    structure: Literal[
        "net", 
        "base_stop",
        "fixed",
        "base_year", 
        "base_year_plus1",
        "base_year_minus1",
    ]
    base_amount: Optional[PositiveFloat] = None  # For base stop or fixed
    base_amount_unit: Optional[Literal['total', 'psf']] = 'psf' # Unit for base_amount (Total $ or $/SF)
    base_year: Optional[int] = None  # For base year calculations
    growth_rate: Optional[GrowthRate] = None

    # Adjustments
    contribution_deduction: Optional[PositiveFloat] = None
    admin_fee_percent: Optional[FloatBetween0And1] = None

    # Prorata share & denominator
    prorata_share: Optional[PositiveFloat] = None  # lease area
    denominator: Optional[PositiveFloat] = None  # property area

    # YoY growth limits
    yoy_min_growth: Optional[FloatBetween0And1] = None
    yoy_max_growth: Optional[FloatBetween0And1] = None

    # Recovery floors & ceilings
    recovery_floor: Optional[PositiveFloat] = None
    recovery_ceiling: Optional[PositiveFloat] = None
    
    # Internal state for calculated base year stop
    # Populated by Lease/Analysis logic before recovery calculation
    _calculated_annual_base_year_stop: Optional[float] = None 
    _frozen_base_year_pro_rata: Optional[float] = None # Populated if freeze_share_at_baseyear is True
    
    @property
    def expense_pool(self) -> ExpensePool:
        """Get the expense pool for this recovery."""
        if isinstance(self.expenses, ExpenseItem):
            # Use the base expense item name if creating a pool on the fly
            pool_name = self.expenses.name 
            return ExpensePool(name=f"{pool_name} Pool", expenses=self.expenses)
        return self.expenses
    
    @model_validator(mode='after')
    def validate_structure_requirements(self) -> 'Recovery':
        """Validate that required fields are provided for each structure."""
        if self.structure == "base_stop" and self.base_amount is None:
            raise ValueError("base_amount is required for base_stop recovery structure")
        if self.structure == "fixed" and self.base_amount is None:
            raise ValueError("base_amount is required for fixed recovery structure")
        if self.structure in ["base_year", "base_year_plus1", "base_year_minus1"] and self.base_year is None:
            raise ValueError(f"base_year is required for {self.structure} recovery structure")
        return self


class RecoveryMethod(Model):
    """
    How expenses are recovered from tenants.
    
    Attributes:
        name: Name of this recovery method
        gross_up: Whether expenses should be grossed up
        gross_up_percent: Target occupancy for gross-up calculations
        recoveries: List of recovery calculations to apply
    """
    name: str

    # Gross up
    gross_up: bool = True
    gross_up_percent: Optional[FloatBetween0And1] = None

    # Recoveries
    recoveries: List[Recovery]
    
    def calculate_recoveries(
        self, 
        tenant_area: PositiveFloat,
        property_data: Optional['Property'], # Ensure original hint is used
        timeline: pd.PeriodIndex,
        occupancy_rate: Optional[Union[float, pd.Series]] = None,
        lookup_fn: Optional[Callable[[Union[str, UUID]], Union[float, int, str, date, pd.Series, Dict, Any]]] = None,
        global_settings: Optional[GlobalSettings] = None
    ) -> pd.Series:
        """
        Calculate total recoveries for a tenant.
        
        Args:
            tenant_area: Tenant's leased area in square feet
            property_data: The full property context, providing access to area etc.
            timeline: Time periods to calculate recoveries for
            occupancy_rate: Optional property occupancy rate series/float.
            lookup_fn: Function to fetch computed cash flows and potentially model details.
            global_settings: Optional global settings, providing analysis dates, recovery flags etc.
            
        Returns:
            Monthly recovery cash flow series
            
        Raises:
            LookupError: If lookup_fn is required but not provided, or fails.
            ValueError: If required data (like occupancy for gross-up) is missing.
        """
        total_recoveries = pd.Series(0.0, index=timeline)
        logger.debug(f"Calculating recoveries for method '{self.name}' over timeline: {timeline.min()} to {timeline.max()}")
        
        if self.gross_up and occupancy_rate is None:
            logger.warning(f"Gross-up enabled for '{self.name}' but occupancy_rate was not provided. Gross-up will be skipped.")
            
        if lookup_fn is None:
            raise LookupError("lookup_fn is required by calculate_recoveries to fetch expense details.")

        for recovery in self.recoveries:
            logger.debug(f"Processing recovery for expense pool: {recovery.expense_pool.name}, Structure: {recovery.structure}")
            
            expense_pool = recovery.expense_pool
            items_in_pool = expense_pool.expenses if isinstance(expense_pool.expenses, list) else [expense_pool.expenses]
            
            pool_expense_cf = pd.Series(0.0, index=timeline) 
            
            for item in items_in_pool:
                is_opex_item = isinstance(item, OpExItem) 
                variable_ratio = item.variable_ratio if is_opex_item and item.variable_ratio is not None else 0.0
                
                logger.debug(f"  Fetching raw CF for item: {item.name} ({item.model_id}), Variable: {variable_ratio:.1%}")
                try:
                    raw_item_cf = lookup_fn(item.model_id)
                    if not isinstance(raw_item_cf, pd.Series):
                        logger.warning(f"    Lookup for item {item.name} did not return a Series (type: {type(raw_item_cf)}). Attempting to create Series.")
                        if isinstance(raw_item_cf, (int, float)):
                            raw_item_cf = pd.Series(float(raw_item_cf), index=timeline)
                        else:
                            raise TypeError("Cannot handle non-Series, non-scalar lookup result for expense item CF.")
                                
                except LookupError as e:
                    logger.error(f"    Failed to lookup cash flow for expense item {item.name} ({item.model_id}). Skipping item. Error: {e}")
                    continue
                except Exception as e:
                    logger.error(f"    Unexpected error processing item {item.name} ({item.model_id}). Skipping item. Error: {e}", exc_info=True)
                    continue

                item_cf_to_add = raw_item_cf
                
                # Apply gross-up only to recoverable, variable OpEx items
                is_eligible_for_grossup = (
                    self.gross_up 
                    and is_opex_item 
                    and item.is_recoverable
                    and variable_ratio > 0
                 )
                 
                if is_eligible_for_grossup:
                    if occupancy_rate is None:
                        logger.debug(f"    Skipping gross-up for item {item.name} as occupancy_rate is None.")
                    elif isinstance(occupancy_rate, pd.Series):
                        aligned_occupancy = occupancy_rate.reindex(timeline, method='ffill').fillna(1.0)
                        
                        target_occupancy = self.gross_up_percent or 0.95
                        
                        fixed_part = raw_item_cf * (1.0 - variable_ratio)
                        variable_part = raw_item_cf * variable_ratio
                        
                        needs_gross_up = aligned_occupancy < target_occupancy
                        
                        safe_occupancy = aligned_occupancy.where(aligned_occupancy > 0, 0.0001) 
                        grossed_up_variable = variable_part / safe_occupancy
                        
                        item_cf_to_add = fixed_part + variable_part.where(~needs_gross_up, grossed_up_variable)
                        
                        periods_grossed_up = needs_gross_up.sum()
                        if periods_grossed_up > 0:
                            logger.debug(f"    Applied gross-up for item {item.name} ({periods_grossed_up} periods). Target: {target_occupancy:.1%}. Raw Sum: {raw_item_cf.sum():.2f}, Grossed-Up Sum: {item_cf_to_add.sum():.2f}")

                    elif isinstance(occupancy_rate, (float, int)):
                        target_occupancy = self.gross_up_percent or 0.95
                        current_occupancy = float(occupancy_rate)
                        if current_occupancy < target_occupancy:
                            if current_occupancy <= 0:
                                logger.warning(f"    Occupancy rate is {current_occupancy} for item {item.name}. Gross-up calculation might yield unexpected results or errors. Clamping to 0.0001 for division.")
                                current_occupancy = 0.0001
                                
                            fixed_part = raw_item_cf * (1.0 - variable_ratio)
                            variable_part = raw_item_cf * variable_ratio
                            grossed_up_variable = variable_part / current_occupancy
                            item_cf_to_add = fixed_part + grossed_up_variable
                            logger.debug(f"    Applied gross-up for item {item.name} (constant occupancy {current_occupancy:.1%}). Target: {target_occupancy:.1%}. Raw Sum: {raw_item_cf.sum():.2f}, Grossed-Up Sum: {item_cf_to_add.sum():.2f}")
                        else:
                            logger.debug(f"    Skipping gross-up for item {item.name} as constant occupancy {current_occupancy:.1%} >= target {target_occupancy:.1%}.")
                    else:
                        logger.warning(f"    Unsupported occupancy_rate type ({type(occupancy_rate)}) for gross-up calculation on item {item.name}.")
                
                pool_expense_cf = pool_expense_cf.add(item_cf_to_add, fill_value=0.0)
            
            logger.debug(f"  Calculated final pool expense CF sum (after potential gross-up): {pool_expense_cf.sum():.2f}")

            if property_data is None or property_data.property_area <= 0:
                logger.error(f"Invalid property_area ({property_data.property_area}) for recovery {recovery.expense_pool.name}. Cannot calculate pro-rata share. Skipping recovery.")
                continue
                
            # Determine the denominator for pro-rata calculation
            denominator = property_data.property_area # Default to property NRA
            if expense_pool.pool_size_override is not None:
                 if expense_pool.pool_size_override > 0:
                     denominator = expense_pool.pool_size_override
                     logger.debug(f"  Using pool size override ({denominator}) as denominator.")
                 else:
                     logger.warning(f"  Expense pool '{expense_pool.name}' has invalid pool_size_override ({expense_pool.pool_size_override}). Using property area {property_data.property_area} instead.")
            
            # Calculate pro-rata share using the determined denominator
            pro_rata = recovery.prorata_share or (tenant_area / denominator)
            logger.debug(f"  Calculated pro-rata share: {pro_rata:.4f} (Tenant Area: {tenant_area}, Denominator: {denominator:.2f})")
            
            recovery_cf = pd.Series(0.0, index=timeline)
            if recovery.structure == "net":
                logger.debug("  Applying 'net' recovery structure.")
                recovery_cf = pool_expense_cf * pro_rata
                
            elif recovery.structure == "base_stop":
                logger.debug("  Applying 'base_stop' recovery structure.")
                assert recovery.base_amount is not None
                
                # Calculate tenant's specific annual stop amount
                tenant_annual_stop: float
                if recovery.base_amount_unit == 'total':
                     # Stop is total $, tenant stop is their pro-rata share of that
                     tenant_annual_stop = recovery.base_amount * pro_rata 
                     logger.debug(f"    Base Amount (Total $/Yr): {recovery.base_amount:.2f}, Tenant Annual Stop: {tenant_annual_stop:.2f} (Pro-rata: {pro_rata:.4f})")
                else: # Default or explicit 'psf'
                     # Stop is $/SF/Yr, tenant stop is $/SF * Tenant Area
                     tenant_annual_stop = recovery.base_amount * tenant_area 
                     logger.debug(f"    Base Amount ($/SF/Yr): {recovery.base_amount:.2f}, Tenant Annual Stop: {tenant_annual_stop:.2f} (Area: {tenant_area})")
                
                monthly_stop = tenant_annual_stop / 12.0
                
                # Tenant pays the amount of their share of expenses *over* their stop amount
                tenant_share_of_expenses = pool_expense_cf * pro_rata
                recovery_cf = tenant_share_of_expenses - monthly_stop
                recovery_cf = recovery_cf.clip(lower=0)  # No negative recoveries
                
            elif recovery.structure in ["base_year", "base_year_plus1", "base_year_minus1"]:
                logger.debug(f"  Applying '{recovery.structure}' recovery structure.")
                # Base year stop should have been pre-calculated and stored
                annual_base_year_stop = recovery._calculated_annual_base_year_stop
                
                if annual_base_year_stop is None:
                     logger.error(f"Base year stop for pool '{recovery.expense_pool.name}' (Structure: {recovery.structure}) was not pre-calculated. Returning zero recovery.")
                     recovery_cf = pd.Series(0.0, index=timeline)
                else:
                     monthly_stop = annual_base_year_stop / 12.0
                     logger.debug(f"    Using Pre-calculated Annual Stop: {annual_base_year_stop:.2f}, Monthly Stop: {monthly_stop:.2f}")
                     
                     # Tenant pays the amount of the current (grossed-up) pool expense *over* the monthly stop
                     # Determine which pro-rata share to use
                     frozen_share = recovery._frozen_base_year_pro_rata
                     
                     # Check global setting for freeze_share_at_baseyear (passed via global_settings)
                     freeze_share_flag = False
                     if global_settings and hasattr(global_settings, 'recoveries') and hasattr(global_settings.recoveries, 'freeze_share_at_baseyear'):
                         freeze_share_flag = global_settings.recoveries.freeze_share_at_baseyear
                     elif global_settings and hasattr(global_settings, 'freeze_share_at_baseyear'): # Check top level
                         freeze_share_flag = global_settings.freeze_share_at_baseyear

                     if freeze_share_flag and frozen_share is not None:
                          share_to_use = frozen_share
                          logger.debug(f"    Using frozen base year pro-rata share: {share_to_use:.4f}")
                     else:
                          share_to_use = pro_rata # Use the current period's pro-rata
                          if freeze_share_flag and frozen_share is None:
                              logger.warning(f"    Freeze share setting is ON, but no frozen share was calculated/stored for recovery '{recovery.expense_pool.name}'. Using current pro-rata {pro_rata:.4f}.")
                     
                     monthly_recoverable_amount = (pool_expense_cf - monthly_stop).clip(lower=0)
                     recovery_cf = monthly_recoverable_amount * share_to_use
                 
            elif recovery.structure == "fixed":
                logger.debug("  Applying 'fixed' recovery structure.")
                assert recovery.base_amount is not None
                monthly_fixed = recovery.base_amount / 12.0
                logger.debug(f"    Fixed Amount (Annual): {recovery.base_amount:.2f}, Monthly Fixed Recovery: {monthly_fixed:.2f}")
                recovery_cf = pd.Series(monthly_fixed, index=timeline)
                
                if recovery.growth_rate is not None:
                    logger.warning(f"Growth rate application on 'fixed' recovery structure not implemented for pool '{expense_pool.name}'.")
                    pass
            
            else:
                logger.warning(f"Unknown recovery structure '{recovery.structure}' encountered for pool '{expense_pool.name}'. Returning zero recovery.")
                recovery_cf = pd.Series(0.0, index=timeline)
            
            logger.debug(f"  Calculated base recovery CF sum (before admin/caps/floors): {recovery_cf.sum():.2f}")
            
            if recovery.admin_fee_percent is not None and recovery.admin_fee_percent > 0:
                admin_factor = (1.0 + recovery.admin_fee_percent)
                recovery_cf *= admin_factor
                logger.debug(f"  Applied admin fee ({recovery.admin_fee_percent:.1%}). Factor: {admin_factor:.4f}, New CF sum: {recovery_cf.sum():.2f}")
            
            if recovery.recovery_ceiling is not None:
                monthly_ceiling = recovery.recovery_ceiling / 12.0
                recovery_cf = recovery_cf.clip(upper=monthly_ceiling)
                logger.debug(f"  Applied ceiling ({recovery.recovery_ceiling:.2f} annual -> {monthly_ceiling:.2f} monthly). New CF sum: {recovery_cf.sum():.2f}")
                
            if recovery.recovery_floor is not None:
                monthly_floor = recovery.recovery_floor / 12.0
                recovery_cf = recovery_cf.clip(lower=monthly_floor)
                logger.debug(f"  Applied floor ({recovery.recovery_floor:.2f} annual -> {monthly_floor:.2f} monthly). New CF sum: {recovery_cf.sum():.2f}")
            
            total_recoveries = total_recoveries.add(recovery_cf, fill_value=0.0)
            logger.debug(f"  Recovery CF added. Cumulative total sum for method '{self.name}': {total_recoveries.sum():.2f}")
        
        return total_recoveries
