import logging
from datetime import date
from typing import TYPE_CHECKING, Dict, List, Optional, Union
from uuid import UUID

import pandas as pd

# Import necessary models
from ._expense import ExpenseItem, OpExItem

if TYPE_CHECKING:
    from ._property import Property
    # Avoid circular import Property <-> Lease <-> RecoveryMethod -> _calc_utils
    
logger = logging.getLogger(__name__)

# TODO: Add docstrings explaining purpose and usage

def _get_period_occupancy(
    property_data: 'Property', 
    period_start: date, 
    period_end: date,
    frequency: str = 'M' # Default to Monthly
    ) -> Optional[pd.Series]:
    """
    Calculates the physical occupancy rate series for a specific time period.

    Mirrors the logic in CashFlowAnalysis._calculate_occupancy_series but operates 
    on potentially historical dates defined by period_start and period_end. It uses
    the *initial* rent roll defined in property_data, as it's intended for historical
    or base year calculations, not forward projections with rollovers.

    Args:
        property_data: The Property object containing the rent roll and NRA.
        period_start: The start date of the period of interest.
        period_end: The end date (inclusive) of the period of interest.
        frequency: The pandas frequency string for the resulting series ('M', 'A', etc.).

    Returns:
        A pandas Series containing the calculated occupancy rate for the specified
        period and frequency, indexed by pd.PeriodIndex. Returns None if NRA is zero
        or calculation fails.
    """
    logger.debug(f"Calculating occupancy for period: {period_start} to {period_end}")
    
    if period_start >= period_end:
        logger.error("Occupancy calculation requires period_start < period_end.")
        return None
        
    total_nra = property_data.net_rentable_area
    if total_nra <= 0:
        logger.warning(f"Property NRA is {total_nra}. Cannot calculate occupancy.")
        # Return a series of zeros with the correct index structure? Or None?
        # Returning None seems clearer that calculation wasn't possible.
        return None 

    # Create a timeline for the specific period
    try:
         target_periods = pd.period_range(start=period_start, end=period_end, freq=frequency)
    except ValueError as e:
         logger.error(f"Failed to create period range for occupancy: {e}")
         return None
         
    occupied_area_series = pd.Series(0.0, index=target_periods)

    # Use the *initial* rent roll for historical/base year occupancy
    initial_leases = property_data.rent_roll.leases if property_data.rent_roll else []

    if not initial_leases:
         logger.debug("No initial leases found in rent roll. Occupancy is 0.")
         return pd.Series(0.0, index=target_periods, name="Occupancy Rate") # Return zero occupancy series

    for lease in initial_leases:
        try:
            # Get the lease's own timeline periods (usually monthly)
            lease_periods = lease.timeline.period_index 
            if lease_periods.empty: continue

            # Find periods where this lease is active *within the target period*
            active_periods_in_target = target_periods.intersection(lease_periods.asfreq(frequency, how='start')) # Ensure frequency match
            
            if not active_periods_in_target.empty:
                 # Add this lease's area to the occupied series for its active periods
                 # Use .loc for safe assignment
                 occupied_area_series.loc[active_periods_in_target] += lease.area
                 logger.debug(f"  Lease '{lease.name}' (Area: {lease.area}) active during {active_periods_in_target.min()} to {active_periods_in_target.max()}")
        except Exception as e:
            logger.warning(f"Could not process lease '{lease.name}' for occupancy calculation. Error: {e}", exc_info=True)
            continue # Skip problematic leases

    # Calculate occupancy rate
    occupancy_series = (occupied_area_series / total_nra).clip(0, 1)
    occupancy_series.name = "Occupancy Rate"
    logger.debug(f"Calculated occupancy series. Average: {occupancy_series.mean():.2%}")
    
    return occupancy_series


# Placeholder for the expense calculation utility
def _get_period_expenses(
    property_data: 'Property', 
    period_start: date, 
    period_end: date, 
    expense_item_ids: List[UUID],
    frequency: str = 'M' # Default to Monthly
    ) -> Optional[Dict[UUID, pd.Series]]:
    """
    Calculates the raw cash flows for specific expense items over a given period.

    Finds the specified ExpenseItem models within property_data, calls their
    compute_cf method using a simplified lookup (resolving only basic 
    property attributes), and returns the results sliced and aligned to the 
    requested period and frequency.

    Args:
        property_data: The Property object containing expense definitions.
        period_start: The start date of the period of interest.
        period_end: The end date (inclusive) of the period of interest.
        expense_item_ids: List of UUIDs for the ExpenseItems to calculate.
        frequency: The pandas frequency string for the resulting series ('M', 'A', etc.).
        
    Returns:
        A dictionary mapping ExpenseItem UUIDs to their calculated cash flow Series
        for the specified period, or None if calculation fails.
    """
    logger.debug(f"Calculating expenses for items {expense_item_ids} over period: {period_start} to {period_end}")
    
    if period_start >= period_end:
        logger.error("Expense calculation requires period_start < period_end.")
        return None
        
    # --- 1. Find Expense Items --- 
    all_expenses: List[ExpenseItem] = []
    if property_data.expenses:
        if property_data.expenses.operating_expenses:
             all_expenses.extend(property_data.expenses.operating_expenses.expense_items or [])
        if property_data.expenses.capital_expenses:
             # Note: Base year stops usually apply to OpEx, but technically could include CapEx?
             # For now, include both OpEx and CapEx items if requested by ID.
             all_expenses.extend(property_data.expenses.capital_expenses.expense_items or [])
             
    target_items_map: Dict[UUID, ExpenseItem] = {
         item.model_id: item for item in all_expenses if item.model_id in expense_item_ids
    }
    
    found_ids = set(target_items_map.keys())
    missing_ids = set(expense_item_ids) - found_ids
    if missing_ids:
         logger.warning(f"Could not find requested expense item IDs: {missing_ids}")
         
    if not target_items_map:
         logger.warning("No matching expense items found for the given IDs.")
         return {}
         
    # --- 2. Create Simplified Lookup Function --- 
    def simple_lookup_fn(key: Union[str, UUID]) -> Union[float, int, str, date, None]:
         """Resolves only basic property attributes, returns None for UUIDs/Aggregates."""
         if isinstance(key, str):
             if hasattr(property_data, key):
                  value = getattr(property_data, key)
                  # Only return simple scalar types expected by base compute_cf
                  if isinstance(value, (int, float, str, date)): 
                      return value
                  else: 
                      logger.warning(f"Simple lookup accessed property attribute '{key}' with complex type {type(value)}. Returning None.")
                      return None
             else:
                  # Could be an AggregateLineKey, but we don't resolve those here
                  logger.debug(f"Simple lookup cannot resolve string key '{key}' (not a direct property attribute).")
                  return None
         elif isinstance(key, UUID):
              logger.debug(f"Simple lookup does not resolve model UUIDs ({key}). Returning None.")
              return None
         else:
              logger.warning(f"Simple lookup received unexpected key type: {type(key)}")
              return None
              
    # --- 3. Create Target Timeline --- 
    try:
         target_periods = pd.period_range(start=period_start, end=period_end, freq=frequency)
    except ValueError as e:
         logger.error(f"Failed to create period range for expense calculation: {e}")
         return None
         
    # --- 4 & 5. Calculate, Slice, Align, and Store --- 
    results: Dict[UUID, pd.Series] = {}
    
    for item_id, item in target_items_map.items():
         try:
             logger.debug(f"  Calculating CF for item '{item.name}' ({item_id})")
             # Calculate full CF using item's internal timeline
             full_cf = item.compute_cf(lookup_fn=simple_lookup_fn)
             
             if not isinstance(full_cf.index, pd.PeriodIndex):
                  logger.warning(f"    Expense item '{item.name}' compute_cf did not return PeriodIndex. Attempting conversion.")
                  try:
                       full_cf.index = pd.PeriodIndex(full_cf.index, freq='M') # Assume monthly base
                  except Exception as e:
                       logger.error(f"    Failed to convert index for item '{item.name}'. Skipping. Error: {e}")
                       continue
                       
             # Slice the result to the target period range
             # Ensure target_periods aligns frequency if needed (e.g., item is monthly, target is annual)
             target_periods_monthly = target_periods.asfreq('M', how='start') # Use monthly for slicing base CF
             sliced_cf = full_cf[target_periods_monthly.min():target_periods_monthly.max()] 
             
             # Align/Resample to the requested final frequency
             if frequency == 'M':
                 aligned_cf = sliced_cf.reindex(target_periods, fill_value=0.0)
             else: # Need resampling (e.g., to Annual)
                 # Resample monthly slice to target frequency (e.g., 'A') by summing
                 # Ensure index is timestamp for resampling
                 timestamp_index_cf = sliced_cf.copy()
                 timestamp_index_cf.index = sliced_cf.index.to_timestamp(how='start')
                 resampled_cf = timestamp_index_cf.resample(frequency).sum()
                 # Convert back to PeriodIndex matching target_periods
                 resampled_cf.index = resampled_cf.index.to_period(frequency)
                 aligned_cf = resampled_cf.reindex(target_periods, fill_value=0.0)
             
             results[item_id] = aligned_cf
             logger.debug(f"    Successfully calculated and aligned CF for item '{item.name}'. Sum: {aligned_cf.sum():.2f}")
             
         except Exception as e:
             logger.error(f"  Failed to calculate expenses for item '{item.name}' ({item_id}). Error: {e}", exc_info=True)
             # Decide whether to return partial results or None if any item fails
             # Returning partial results seems more useful.
             continue 
             
    logger.debug(f"Finished calculating period expenses. Results for {len(results)} items.")
    return results 


def _gross_up_period_expenses(
    raw_expenses: Dict[UUID, pd.Series], 
    occupancy_series: pd.Series, 
    expense_items_map: Dict[UUID, 'ExpenseItem'],
    gross_up_target_rate: float = 0.95 # Default target
    ) -> Dict[UUID, pd.Series]:
    """
    Applies gross-up calculation to raw expense series based on occupancy.
    
    Used primarily for calculating grossed-up base year expenses.
    
    Args:
        raw_expenses: Dict mapping ExpenseItem UUID to its raw calculated expense Series.
        occupancy_series: Series of occupancy rates for the same period as raw_expenses.
                      Index must align with raw_expenses series.
        expense_items_map: Dict mapping ExpenseItem UUID to the full ExpenseItem object 
                           (needed to get variable_ratio).
        gross_up_target_rate: The occupancy threshold below which gross-up applies.
        
    Returns:
        A dictionary mapping ExpenseItem UUIDs to their grossed-up expense Series.
    """
    grossed_up_results: Dict[UUID, pd.Series] = {}
    if occupancy_series is None or occupancy_series.empty:
        logger.warning("Cannot perform gross-up without occupancy series. Returning raw expenses.")
        return raw_expenses
        
    for item_id, raw_cf in raw_expenses.items():
        item = expense_items_map.get(item_id)
        # Default to raw if item details missing or not OpEx/Variable/Recoverable
        item_cf_to_add = raw_cf 
        
        # Only apply gross-up to recoverable OpEx items with a variable portion
        if item and isinstance(item, OpExItem) and item.is_recoverable and item.variable_ratio is not None and item.variable_ratio > 0:
            variable_ratio = item.variable_ratio
            timeline = raw_cf.index # Assume index is consistent
            
            # Align occupancy series
            # Ensure occupancy is also PeriodIndex if raw_cf is
            if isinstance(timeline, pd.PeriodIndex) and not isinstance(occupancy_series.index, pd.PeriodIndex):
                 try:
                     occupancy_series.index = pd.PeriodIndex(occupancy_series.index, freq=timeline.freq)
                 except Exception as e:
                      logger.error(f"Failed to align occupancy index to PeriodIndex for gross-up of {item_id}. Skipping gross-up. Error: {e}")
                      grossed_up_results[item_id] = item_cf_to_add
                      continue
                      
            aligned_occupancy = occupancy_series.reindex(timeline, method='ffill').fillna(1.0)
            
            # Vectorized calculation
            fixed_part = raw_cf * (1.0 - variable_ratio)
            variable_part = raw_cf * variable_ratio
            
            # Create boolean series where gross-up applies
            needs_gross_up = aligned_occupancy < gross_up_target_rate
            
            # Calculate grossed-up variable part safely
            safe_occupancy = aligned_occupancy.where(aligned_occupancy > 0, 0.0001)
            grossed_up_variable = variable_part / safe_occupancy
            
            # Combine based on condition
            item_cf_to_add = fixed_part + variable_part.where(~needs_gross_up, grossed_up_variable)
            
            periods_grossed_up = needs_gross_up.sum()
            if periods_grossed_up > 0:
                 logger.debug(f"    Util: Applied gross-up for item {item.name} ({periods_grossed_up} periods). Target: {gross_up_target_rate:.1%}. Raw Sum: {raw_cf.sum():.2f}, Grossed-Up Sum: {item_cf_to_add.sum():.2f}")
                 
        grossed_up_results[item_id] = item_cf_to_add
        
    return grossed_up_results 