import logging
from typing import List, Literal, Optional, Union

import pandas as pd
from pydantic import model_validator

from ..core._model import Model
from ..core._types import FloatBetween0And1, PositiveFloat
from ._expense import ExpenseItem
from ._growth_rates import GrowthRate

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
    """
    name: str
    expenses: Union[ExpenseItem, List[ExpenseItem]]
    
    def compute_cf(self, timeline: pd.PeriodIndex, occupancy_rate: Optional[float] = None) -> pd.Series:
        """
        Calculate total expenses in this pool.
        
        Args:
            timeline: PeriodIndex to align expense cash flows
            occupancy_rate: Optional occupancy rate for variable expenses
            
        Returns:
            Series of total expenses by period
        """
        # Initialize with zeros for the timeline
        pool_cf = pd.Series(0, index=timeline)
        
        # Handle single expense case
        if isinstance(self.expenses, ExpenseItem):
            expense_cf = self.expenses.compute_cf(occupancy_rate=occupancy_rate)
            expense_cf = expense_cf.reindex(timeline, fill_value=0)
            return expense_cf
            
        # Handle list of expenses
        for expense in self.expenses:
            expense_cf = expense.compute_cf(occupancy_rate=occupancy_rate)
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
        property_area: PositiveFloat,
        timeline: pd.PeriodIndex,
        occupancy_rate: Optional[float] = None
    ) -> pd.Series:
        """
        Calculate total recoveries for a tenant.
        
        Args:
            tenant_area: Tenant's leased area in square feet
            property_area: Total property area in square feet
            timeline: Time periods to calculate recoveries for
            occupancy_rate: Optional property occupancy rate
            
        Returns:
            Monthly recovery cash flow series
        """
        total_recoveries = pd.Series(0, index=timeline)
        logger.debug(f"Calculating recoveries for method '{self.name}' over timeline: {timeline.min()} to {timeline.max()}")
        
        for recovery in self.recoveries:
            logger.debug(f"Processing recovery for expense pool: {recovery.expense_pool.name}, Structure: {recovery.structure}")
            # Get expense pool cash flow
            expense_pool = recovery.expense_pool
            pool_expense_cf = expense_pool.compute_cf(timeline, occupancy_rate)
            logger.debug(f"  Raw pool expense CF sum: {pool_expense_cf.sum():.2f}")
            
            # Apply gross-up if applicable
            if self.gross_up:
                if occupancy_rate is not None and occupancy_rate < 1.0:
                    target = self.gross_up_percent or 0.95
                    if occupancy_rate < target:
                        # FIXME: implement this fully - Identify variable expenses
                        logger.warning(f"Applying simplified gross-up for '{expense_pool.name}'. Assumes entire pool is variable.")
                        gross_up_factor = min(target / occupancy_rate, 1.25)  # Limit to reasonable factor
                        pool_expense_cf = pool_expense_cf * gross_up_factor
                        logger.debug(f"  Applied gross-up factor: {gross_up_factor:.4f}, Grossed-up CF sum: {pool_expense_cf.sum():.2f}")
                    else:
                        logger.debug(f"  Occupancy {occupancy_rate:.1%} >= target {target:.1%}. No gross-up applied.")
                else:
                     logger.debug("  Gross-up enabled but occupancy is 100% or None. No gross-up applied.")
            else:
                logger.debug("  Gross-up is disabled for this method.")
            
            # Calculate tenant's pro-rata share
            pro_rata = recovery.prorata_share or (tenant_area / property_area)
            logger.debug(f"  Calculated pro-rata share: {pro_rata:.4f} (Tenant Area: {tenant_area}, Property Area: {property_area})")
            
            # Calculate recoverable amount based on recovery structure
            recovery_cf = pd.Series(0.0, index=timeline)
            if recovery.structure == "net":
                logger.debug("  Applying 'net' recovery structure.")
                # Net lease - tenant pays full pro-rata share
                recovery_cf = pool_expense_cf * pro_rata
                
            elif recovery.structure == "base_stop":
                logger.debug("  Applying 'base_stop' recovery structure.")
                # Base stop - tenant pays amounts over the stop
                assert recovery.base_amount is not None
                # Calculate monthly base stop amount adjusted by pro-rata share
                monthly_base = (recovery.base_amount / 12) * pro_rata 
                logger.debug(f"    Base Amount (Annual): {recovery.base_amount:.2f}, Monthly Pro-rata Stop: {monthly_base:.2f}")
                # Tenant pays the amount *over* the stop
                recovery_cf = (pool_expense_cf * pro_rata) - monthly_base
                recovery_cf = recovery_cf.clip(lower=0)  # No negative recoveries
                
            elif recovery.structure in ["base_year", "base_year_plus1", "base_year_minus1"]:
                # Base year - needs expense history for comparison
                # FIXME: implement base year recoveries fully
                logger.error(f"Base year recovery structure ('{recovery.structure}') not implemented for pool '{expense_pool.name}'. Returning zero recovery.")
                # Raise error? Or return zeros?
                # For now, return zero to allow calculation to proceed, but log error.
                # raise NotImplementedError("Base year recoveries not implemented")
                recovery_cf = pd.Series(0.0, index=timeline)
                
            elif recovery.structure == "fixed":
                logger.debug("  Applying 'fixed' recovery structure.")
                # Fixed recovery amount
                assert recovery.base_amount is not None
                # Assume base_amount is annual fixed amount *for the tenant* (not per SF)
                monthly_fixed = recovery.base_amount / 12
                logger.debug(f"    Fixed Amount (Annual): {recovery.base_amount:.2f}, Monthly Fixed Recovery: {monthly_fixed:.2f}")
                recovery_cf = pd.Series(monthly_fixed, index=timeline)
                
                # Apply growth rate if provided
                if recovery.growth_rate is not None:
                    # FIXME: Implement growth rate application on fixed amount
                    logger.warning(f"Growth rate application on 'fixed' recovery structure not implemented for pool '{expense_pool.name}'.")
                    pass
            
            else:
                # Unknown recovery structure
                logger.warning(f"Unknown recovery structure '{recovery.structure}' encountered for pool '{expense_pool.name}'. Returning zero recovery.")
                recovery_cf = pd.Series(0.0, index=timeline)
            
            logger.debug(f"  Calculated base recovery CF sum: {recovery_cf.sum():.2f}")
            
            # Apply admin fee if specified
            if recovery.admin_fee_percent is not None and recovery.admin_fee_percent > 0:
                admin_factor = (1 + recovery.admin_fee_percent)
                recovery_cf *= admin_factor
                logger.debug(f"  Applied admin fee ({recovery.admin_fee_percent:.1%}). Factor: {admin_factor:.4f}, New CF sum: {recovery_cf.sum():.2f}")
            
            # Apply caps and floors if defined
            # Note: These are typically annual amounts
            if recovery.recovery_ceiling is not None:
                monthly_ceiling = recovery.recovery_ceiling / 12
                recovery_cf = recovery_cf.clip(upper=monthly_ceiling)
                logger.debug(f"  Applied ceiling ({recovery.recovery_ceiling:.2f} annual -> {monthly_ceiling:.2f} monthly). New CF sum: {recovery_cf.sum():.2f}")
                
            if recovery.recovery_floor is not None:
                monthly_floor = recovery.recovery_floor / 12
                recovery_cf = recovery_cf.clip(lower=monthly_floor)
                logger.debug(f"  Applied floor ({recovery.recovery_floor:.2f} annual -> {monthly_floor:.2f} monthly). New CF sum: {recovery_cf.sum():.2f}")
            
            # Add to total recoveries
            total_recoveries = total_recoveries.add(recovery_cf, fill_value=0.0)
            logger.debug(f"  Recovery CF added. Cumulative total sum: {total_recoveries.sum():.2f}")
        
        return total_recoveries
