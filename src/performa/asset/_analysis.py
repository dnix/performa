# Import inspect module
import inspect
import logging  # <-- Import logging
from datetime import date, timedelta  # Added timedelta
from graphlib import CycleError, TopologicalSorter
from typing import (  # Added TYPE_CHECKING
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)
from uuid import UUID

import pandas as pd
from dateutil.relativedelta import relativedelta  # Added relativedelta
from pydantic import Field

from ..core._cash_flow import CashFlowModel
from ..core._enums import (
    AggregateLineKey,
    ExpenseSubcategoryEnum,
    RevenueSubcategoryEnum,
    UponExpirationEnum,
    VacancyLossMethodEnum,
)
from ..core._model import Model
from ..core._settings import GlobalSettings
from ..core._timeline import Timeline

# Add utils imports
from ._calc_utils import (
    _get_period_expenses,
    _get_period_occupancy,
    _gross_up_period_expenses,
)
from ._lease import Lease  # TODO: Keep for now, might move to TYPE_CHECKING

# Asset imports
from ._property import Property

# Handle potential circular imports for type hints
if TYPE_CHECKING:
    from ._expense import ExpenseItem
    from ._lease import Lease
    from ._recovery import Recovery

# TODO: Add comprehensive unit and integration tests for CashFlowAnalysis logic.

logger = logging.getLogger(__name__) # <-- Setup logger

class CashFlowAnalysis(Model):
    """
    Orchestrates the calculation and aggregation of property-level cash flows.

    This class computes cash flows over a specified analysis period by:
    1. Generating the full sequence of actual and projected speculative leases 
       that overlap with the analysis period using rollover profiles.
    2. Collecting all relevant `CashFlowModel` instances (projected Leases, 
       Expenses, MiscIncome, etc.).
    3. Calculating a dynamic occupancy series based on the projected lease sequence.
    4. Computing cash flows for each model, resolving dependencies:
        - Uses `lookup_fn` to resolve `reference` attributes (UUIDs for inter-model
          dependencies, strings for `Property` attributes or AggregateLineKeys).
        - Injects the calculated occupancy series as an argument to models that require it
          (e.g., `OpExItem`, `MiscIncome`) via signature inspection.
        - Employs `graphlib.TopologicalSorter` for efficient single-pass computation if
          model dependencies form a Directed Acyclic Graph (DAG).
        - Falls back to a multi-pass iterative calculation if cycles are detected
          (e.g., due to `model_id` or aggregate references), issuing a warning.
    5. Aggregating the computed cash flows into standard financial line items
       (Revenue, OpEx, CapEx, TI Allowance, Leasing Commission).
    6. Providing access to these aggregated results via a DataFrame and specific
       metric calculation methods (NOI, Unlevered Cash Flow, etc.).

    Attributes:
        property: The input `Property` object containing asset details and base models.
        settings: Global settings potentially influencing calculations.
        analysis_start_date: The start date for the cash flow analysis period.
        analysis_end_date: The end date (inclusive) for the cash flow analysis period.
    """
    property: Property
    settings: GlobalSettings = Field(default_factory=GlobalSettings)
    analysis_start_date: date
    analysis_end_date: date
    
    # --- Cached Results ---
    # NOTE: Basic caching implemented. Assumes inputs are immutable after instantiation.
    # TODO: Implement more robust cache invalidation if inputs can change.
    _cached_projected_leases: Optional[List['Lease']] = None
    _cached_detailed_flows: Optional[List[Tuple[Dict, pd.Series]]] = None
    _cached_aggregated_flows: Optional[Dict[AggregateLineKey, pd.Series]] = None
    _cached_cash_flow_dataframe: Optional[pd.DataFrame] = None
    _cached_detailed_cash_flow_dataframe: Optional[pd.DataFrame] = None
    _cached_occupancy_series: Optional[pd.Series] = None
    # --- Add cache for rollover vacancy loss ---
    _cached_rollover_vacancy_loss_series: Optional[pd.Series] = None 

    # --- Private Helper: Iterative Computation ---

    def _compute_cash_flows_iterative(
        self, 
        all_models: List[CashFlowModel], 
        occupancy_series: pd.Series
        ) -> Dict[UUID, Union[pd.Series, Dict[str, pd.Series]]]:
        """
        Internal helper: Compute cash flows using multi-pass iteration.
        
        This method serves as a fallback when `graphlib.TopologicalSorter` detects
        a cycle in the model dependencies based on `model_id` references. It iteratively
        attempts to compute models until no further progress can be made or a maximum
        number of passes is reached. Aggregated cash flows are recalculated in each
        pass to allow models to depend on them.

        Args:
            all_models: The list of all CashFlowModel instances to compute.
            occupancy_series: The pre-calculated occupancy series.

        Returns:
            A dictionary mapping model_id to its computed result (Series or Dict of Series).
            May contain fewer items than `all_models` if some models failed computation.
        """
        logger.debug(f"Starting iterative computation for {len(all_models)} models.") # DEBUG: Entry
        computed_results: Dict[UUID, Union[pd.Series, Dict[str, pd.Series]]] = {}
        remaining_models = {model.model_id: model for model in all_models}
        model_map = {model.model_id: model for model in all_models} # Keep original map
        analysis_periods = occupancy_series.index # Use occupancy index as timeline ref
        current_aggregates: Dict[AggregateLineKey, pd.Series] = {} # Store aggregates calculated each pass (keyed by Enum)
        
        MAX_PASSES = len(all_models) + 1
        passes = 0
        progress_made_in_pass = True

        while remaining_models and passes < MAX_PASSES and progress_made_in_pass:
            passes += 1
            logger.debug(f"Iterative Pass {passes}/{MAX_PASSES}. Models remaining: {len(remaining_models)}") # DEBUG: Pass start
            progress_made_in_pass = False
            models_computed_this_pass: List[UUID] = []
            lookup_errors_this_pass: Dict[UUID, str] = {}

            # Define lookup function (Handles UUID, aggregate strings, and property strings)
            def lookup_fn_iterative(key: Union[str, UUID]) -> Union[float, pd.Series, Dict, Any]:
                # This lookup is used in the multi-pass iterative computation.
                if isinstance(key, UUID):
                    if key in computed_results:
                        return computed_results[key]
                    else:
                        # Should not happen if all_models is consistent, but handles edge cases
                         raise LookupError(f"Iterative: Dependency result for model ID {key} is unknown (not computed or remaining).")
                elif isinstance(key, str):
                    # 1. Check if key matches an AggregateLineKey value
                    matched_agg_key = AggregateLineKey.from_value(key)
                        
                    if matched_agg_key is not None:
                        # Check aggregates calculated in the *previous* pass
                        if matched_agg_key in current_aggregates:
                            return current_aggregates[matched_agg_key]
                        else:
                            # Aggregate key valid, but not calculated yet in previous pass
                            raise LookupError(f"Iterative: Aggregate line '{key}' not yet available in pass {passes}.")
                        
                    # 2. Check Property attributes (if not an aggregate key)
                    if hasattr(self.property, key):
                        value = getattr(self.property, key)
                        # Validate that the retrieved property attribute has a simple, expected type
                        if isinstance(value, (int, float, str, date)): 
                            return value
                        else: 
                            # Raise error if property attribute is a complex object or unexpected type
                            raise TypeError(f"Iterative: Property attribute '{key}' has unexpected type {type(value)}. Expected simple scalar/string/date.")
                    # If not found in property attributes, raise error
                    else: 
                        raise LookupError(
                            f"Iterative: Cannot resolve string reference '{key}' in pass {passes}. "
                            f"It is not a resolved AggregateLineKey or a known Property attribute."
                        )
                else:
                    raise TypeError(f"Iterative: Unsupported lookup key type: {type(key)}")

            for model_id, model in list(remaining_models.items()):
                logger.debug(f"  Attempting iterative compute: '{model.name}' ({model_id})") # DEBUG: Model attempt
                try:
                    # Use helper to call compute_cf with conditional occupancy
                    result = self._run_compute_cf(model, lookup_fn_iterative, occupancy_series) 
                    computed_results[model_id] = result
                    models_computed_this_pass.append(model_id)
                    progress_made_in_pass = True
                    logger.debug(f"    Success: '{model.name}' ({model_id}) computed.") # DEBUG: Model success
                except LookupError as le:
                    lookup_errors_this_pass[model_id] = str(le)
                    logger.debug(f"    Lookup Error: '{model.name}' ({model_id}) - waiting for dependency: {le}") # DEBUG: Model lookup fail
                except NotImplementedError:
                    # Log warning instead of print
                    logger.warning(f"(Iterative) compute_cf not implemented for model '{model.name}' ({model.model_id}). Treating as zero flow.")
                    # Still mark as computed to prevent infinite loops if it was the cause of stalling
                    computed_results[model_id] = pd.Series(0.0, index=analysis_periods) 
                    models_computed_this_pass.append(model_id) 
                    progress_made_in_pass = True # Mark progress even if not implemented
                except Exception as e:
                    # Log error with exception info instead of print
                    logger.error(f"(Iterative) Error computing '{model.name}' ({model.model_id}). Skipping.", exc_info=True)
                    # Optionally raise the error based on settings
                    if self.settings.calculation.fail_on_error: # Check setting
                        raise e
                    # Mark as computed (with error state represented by absence in computed_results) to avoid looping
                    models_computed_this_pass.append(model_id) 
                    progress_made_in_pass = True # Mark progress even if error occurred

            # Remove newly computed models from the remaining set
            for computed_id in models_computed_this_pass:
                remaining_models.pop(computed_id, None)

            # --- Recalculate Aggregates for the NEXT pass ---
            # Process ALL computed results so far into detailed flow format for aggregation
            detailed_flows_this_pass: List[Tuple[Dict, pd.Series]] = []
            for res_model_id, result in computed_results.items():
                 original_model = model_map.get(res_model_id) 
                 if not original_model: 
                     continue
                 results_to_process: Dict[str, pd.Series] = {}
                 if isinstance(result, pd.Series): 
                     results_to_process = {"value": result}
                 elif isinstance(result, dict): 
                     results_to_process = result
                 else: 
                     logger.warning(f"Unexpected result type {type(result)} for model '{original_model.name}'. Skipped processing.")
                     continue

                 for component_name, series in results_to_process.items():
                     if not isinstance(series, pd.Series): 
                         continue
                     try:
                         # Align index - crucial for aggregation
                         if not isinstance(series.index, pd.PeriodIndex):
                              if isinstance(series.index, pd.DatetimeIndex): 
                                  series.index = series.index.to_period(freq='M')
                              else: 
                                  series.index = pd.PeriodIndex(series.index, freq='M')
                         # Use the main analysis_periods derived earlier
                         aligned_series = series.reindex(analysis_periods, fill_value=0.0) 
                     except Exception: 
                         # Log warning with exception info instead of print
                         logger.warning(f"Alignment failed for component '{component_name}' from model '{original_model.name}'. Skipping component.", exc_info=True)
                         continue 
                    
                     metadata = {
                         "model_id": str(res_model_id),
                         "name": original_model.name,
                         "category": original_model.category,
                         "subcategory": str(original_model.subcategory),
                         "component": component_name,
                     }
                     detailed_flows_this_pass.append((metadata, aligned_series))
            
            # Calculate aggregates based on *all* results computed *so far*
            current_aggregates = self._aggregate_detailed_flows(detailed_flows_this_pass)
            # End of Pass Aggregation
            logger.debug(f"  Pass {passes} finished. Computed {len(models_computed_this_pass)} models this pass.") # DEBUG: Pass end metrics

        if remaining_models:
            # Log warning instead of print
            logger.warning(f"(Iterative) Could not compute all models after {passes} passes.")
            for model_id, reason in lookup_errors_this_pass.items():
                 if model_id in remaining_models:
                     model_name = remaining_models[model_id].name
                     # Log warning instead of print
                     logger.warning(f"  - Iterative: Model '{model_name}' ({model_id}) failed. Last error: {reason}")
        
        logger.debug("Finished iterative computation.") # DEBUG: Exit
        return computed_results

    # --- Private Helper: Base Year Stop Pre-calculation ---
    def _pre_calculate_all_base_year_stops(self, all_models: List[CashFlowModel]) -> None:
        """
        Iterates through leases in all_models and calculates/caches base year stops.
        
        This should be called once before dependency-based computation begins.
        It finds Leases with base year recovery structures and populates the 
        `_calculated_annual_base_year_stop` and `_frozen_base_year_pro_rata` 
        attributes on their associated Recovery objects.
        
        Args:
            all_models: List containing all CashFlowModel instances for the analysis,
                       including projected leases.
        """
        logger.info("Starting pre-calculation of base year stops...")
        
        # Imports moved to top level
            
        # Cache data fetched per base year to avoid redundant lookups
        base_year_data_cache: Dict[int, Dict[str, Any]] = {}
        
        # Iterate through all models provided
        # Use string hint 'Lease' as it's imported under TYPE_CHECKING
        leases_to_process = [model for model in all_models if isinstance(model, Lease)]
        logger.debug(f"Found {len(leases_to_process)} Lease instances to check for base year recoveries.")

        for lease in leases_to_process:
            if not lease.recoveries: 
                continue # Skip leases with no recovery definitions
                
            # Use string hint 'Recovery' here as well
            recoveries_needing_calc: List['Recovery'] = [] 
            # Use string hint 'ExpenseItem' if needed for type checking inside loop
            all_by_expense_items_for_lease: Dict[UUID, 'ExpenseItem'] = {}
            
            # Check if this lease has relevant recovery structures and hasn't been calculated yet
            for recovery in lease.recoveries:
                if recovery.structure in ["base_year", "base_year_plus1", "base_year_minus1"]:
                    # Check cache *on the recovery object* first
                    if recovery._calculated_annual_base_year_stop is not None: 
                        logger.debug(f"  Stop already calculated for Lease '{lease.name}', Recovery Pool '{recovery.expense_pool.name}'. Skipping.")
                        continue 
                    
                    if recovery.base_year is None:
                        logger.error(f"  Recovery '{recovery.expense_pool.name}' for lease '{lease.name}' is Base Year type but missing base_year value.")
                        continue
                        
                    recoveries_needing_calc.append(recovery)
                    pool_items = recovery.expense_pool.expenses
                    if not isinstance(pool_items, list): pool_items = [pool_items]
                    for item in pool_items:
                        # Check type using string hint if necessary, or rely on structure
                        # Assuming items in pool are ExpenseItem-like for now
                        if hasattr(item, 'model_id'): # Duck-typing check
                             if item.model_id not in all_by_expense_items_for_lease:
                                 all_by_expense_items_for_lease[item.model_id] = item
                        else:
                             logger.warning(f"Item '{getattr(item, "name", "Unknown")}' in pool '{recovery.expense_pool.name}' does not have model_id. Skipping.")
                             
            if not recoveries_needing_calc:
                continue # No base year recoveries needing calculation for this lease
                
            logger.debug(f"Calculating base year stops for Lease '{lease.name}'...")
            lease_start_year = lease.lease_start.year # Use the specific lease's start year

            # Use string hint 'Recovery' when iterating
            for recovery in recoveries_needing_calc: 
                 year_offset = 0
                 if recovery.structure == "base_year_plus1": year_offset = 1
                 elif recovery.structure == "base_year_minus1": year_offset = -1
                 target_base_year = lease_start_year + year_offset
                 
                 # Check cache for the target year's data first
                 if target_base_year not in base_year_data_cache:
                     logger.debug(f"  Cache miss for base year {target_base_year}. Fetching data...")
                     base_year_data_cache[target_base_year] = {"occupancy": None, "expenses": None}
                     
                     # Determine calendar mode and fiscal start month from analysis settings
                     calendar_mode = self.settings.recoveries.calendar_mode.lower() if self.settings.recoveries else 'calendar'
                     fiscal_start_month = 1
                     if calendar_mode == 'fiscal':
                         if self.settings.analysis_start_date:
                             fiscal_start_month = self.settings.analysis_start_date.month
                         else:
                             logger.warning("Fiscal calendar_mode requires global_settings.analysis_start_date. Defaulting to January fiscal start.")
                     
                     # Define the base year period
                     if calendar_mode == 'fiscal':
                         by_start = date(target_base_year, fiscal_start_month, 1)
                         by_end = by_start + relativedelta(years=1) - timedelta(days=1)
                     else: # Default to Calendar
                         by_start = date(target_base_year, 1, 1)
                         by_end = date(target_base_year, 12, 31)
                     logger.debug(f"    Base year {target_base_year} period: {by_start} to {by_end} ({calendar_mode} mode).")
                     
                     # Fetch occupancy
                     monthly_occupancy = _get_period_occupancy(self.property, by_start, by_end, frequency='M')
                     if monthly_occupancy is None: logger.error(f"    Failed to get occupancy for base year {target_base_year}."); continue
                     base_year_data_cache[target_base_year]["occupancy"] = monthly_occupancy
                     
                     # Fetch expenses for *all* potential items needed for this lease
                     expense_ids_to_fetch = list(all_by_expense_items_for_lease.keys())
                     monthly_expenses = _get_period_expenses(self.property, by_start, by_end, expense_ids_to_fetch, frequency='M')
                     if monthly_expenses is None: logger.error(f"    Failed to get expenses for base year {target_base_year}."); continue
                     base_year_data_cache[target_base_year]["expenses"] = monthly_expenses
                     logger.debug(f"  Fetched and cached data for base year {target_base_year}.")
                     
                 # --- Use cached data to calculate stop for this recovery --- 
                 cached_data = base_year_data_cache[target_base_year]
                 base_year_occupancy = cached_data["occupancy"]
                 base_year_expenses = cached_data["expenses"]
                 
                 if base_year_occupancy is None or base_year_expenses is None:
                     logger.warning(f"  Skipping stop calculation for recovery '{recovery.expense_pool.name}' due to missing cached data for base year {target_base_year}.")
                     recovery._calculated_annual_base_year_stop = None
                     continue
                     
                 # Filter expenses relevant to *this* recovery's pool
                 pool_items = recovery.expense_pool.expenses
                 if not isinstance(pool_items, list): pool_items = [pool_items]
                 pool_item_ids = {item.model_id for item in pool_items if hasattr(item, 'model_id')}
                 pool_expenses_raw: Dict[UUID, pd.Series] = { 
                      item_id: series 
                      for item_id, series in base_year_expenses.items() 
                      if item_id in pool_item_ids
                 }
                 pool_items_map: Dict[UUID, 'ExpenseItem'] = {item.model_id: item for item in all_by_expense_items_for_lease.values() if item.model_id in pool_item_ids}

                 if not pool_expenses_raw:
                      logger.warning(f"  No expense data found for pool '{recovery.expense_pool.name}' in base year {target_base_year}. Setting stop to 0.")
                      recovery._calculated_annual_base_year_stop = 0.0
                      continue

                 # Perform Gross-up
                 gross_up_this_recovery = lease.recovery_method.gross_up if lease.recovery_method else False
                 gross_up_target = lease.recovery_method.gross_up_percent if lease.recovery_method and lease.recovery_method.gross_up_percent is not None else 0.95
                 
                 pool_expenses_grossed_up: Dict[UUID, pd.Series]
                 if gross_up_this_recovery:
                      logger.debug(f"    Applying gross-up to base year {target_base_year} expenses for pool '{recovery.expense_pool.name}' (Target: {gross_up_target:.1%})")
                      pool_expenses_grossed_up = _gross_up_period_expenses(
                           pool_expenses_raw, base_year_occupancy, 
                           expense_items_map=pool_items_map, # Use map for items in this lease
                           gross_up_target_rate=gross_up_target
                      )
                 else:
                      pool_expenses_grossed_up = pool_expenses_raw
                      
                 # Aggregate the grossed-up expenses for the pool
                 total_pool_by_grossed_up = pd.Series(0.0, index=base_year_occupancy.index)
                 for series in pool_expenses_grossed_up.values():
                      total_pool_by_grossed_up = total_pool_by_grossed_up.add(series.reindex(total_pool_by_grossed_up.index, fill_value=0.0), fill_value=0.0)
                      
                 # Perform Annualization
                 base_period_start_month = 0
                 if recovery.structure == "base_year_plus1": base_period_start_month = 12
                 elif recovery.structure == "base_year_minus1": base_period_start_month = -12
                 
                 base_period_start_date = lease.lease_start + relativedelta(months=base_period_start_month)
                 base_period_end_date = base_period_start_date + relativedelta(months=12) - timedelta(days=1)
                 
                 try:
                      precise_base_periods = pd.period_range(start=base_period_start_date, end=base_period_end_date, freq='M')
                      if len(precise_base_periods) > 12: precise_base_periods = precise_base_periods[:12]
                 except Exception as e:
                      logger.error(f"    Could not create precise base period range for {recovery.expense_pool.name}. Cannot annualize. Error: {e}")
                      recovery._calculated_annual_base_year_stop = None; continue
                      
                 sliced_base_year_total = total_pool_by_grossed_up.reindex(precise_base_periods, fill_value=0.0)
                 months_in_slice = len(sliced_base_year_total)
                 calculated_sum = sliced_base_year_total.sum()
                 annual_stop_amount = 0.0
                 if months_in_slice == 0:
                      logger.warning(f"    No data found for base period of pool '{recovery.expense_pool.name}'. Setting stop to 0.")
                 elif months_in_slice < 12:
                      annual_stop_amount = (calculated_sum / months_in_slice) * 12
                      logger.warning(f"    Partial data ({months_in_slice}/12 months) for base period of pool '{recovery.expense_pool.name}'. Annualized sum {annual_stop_amount:.2f}.")
                 else:
                      annual_stop_amount = calculated_sum

                 logger.debug(f"    Calculated Annual Stop for pool '{recovery.expense_pool.name}': {annual_stop_amount:.2f}")
                 recovery._calculated_annual_base_year_stop = annual_stop_amount
                 
                 # --- Check for Frozen Pro-rata Share --- 
                 freeze_share_flag = False
                 if self.settings and hasattr(self.settings, 'recoveries') and hasattr(self.settings.recoveries, 'freeze_share_at_baseyear'):
                     freeze_share_flag = self.settings.recoveries.freeze_share_at_baseyear
                 elif self.settings and hasattr(self.settings, 'freeze_share_at_baseyear'): 
                     freeze_share_flag = self.settings.freeze_share_at_baseyear
                     
                 if freeze_share_flag:
                      current_nra = self.property.net_rentable_area
                      if current_nra > 0:
                           base_year_pro_rata = lease.area / current_nra
                           recovery._frozen_base_year_pro_rata = base_year_pro_rata
                           logger.debug(f"    Storing frozen base year pro-rata share: {base_year_pro_rata:.4f}")
                      else:
                           logger.warning(f"    Cannot calculate base year pro-rata share for freezing (Property NRA={current_nra}).")
                           recovery._frozen_base_year_pro_rata = None 
                 else:
                      recovery._frozen_base_year_pro_rata = None

        logger.info("Finished pre-calculation of base year stops.")

    # --- Private Methods ---
    def _create_timeline(self) -> Timeline:
        """Creates a unified monthly timeline for the analysis period."""
        logger.debug(f"Creating timeline from {self.analysis_start_date} to {self.analysis_end_date}.")
        if self.analysis_start_date >= self.analysis_end_date:
            raise ValueError("Analysis start date must be before end date")
        return Timeline.from_dates(
            start_date=self.analysis_start_date,
            end_date=self.analysis_end_date,
            # Default monthly frequency assumed
        )
        
    def _get_projected_leases(self) -> List['Lease']:
        """
        Generates the full sequence of actual and projected speculative leases 
        that overlap with the analysis period.

        Iterates through the initial rent roll and projects each lease forward
        using its rollover profile until the analysis end date is reached.
        
        As part of this process, it captures and aggregates any specific rollover 
        vacancy loss calculated by `Lease.create_market_lease` when a market 
        lease is projected after downtime.
        
        Caches both the resulting list of projected Lease objects and the 
        aggregated rollover vacancy loss series for use by other methods.

        TODO: Consider refactoring loss aggregation. This method could return 
              both leases and raw loss series, with aggregation handled elsewhere.
              
        Returns:
            A list containing all Lease instances (original and projected) 
            relevant to the analysis period.
        """
        logger.debug("Getting projected lease sequence (checking cache).")
        # Only recalculate if leases aren't cached (loss calculation depends on lease projection)
        if self._cached_projected_leases is None:
            logger.debug("Projected leases cache miss. Generating now.")
            analysis_timeline = self._create_timeline()
            analysis_periods = analysis_timeline.period_index
            analysis_end_date = analysis_timeline.end_date.to_timestamp().date() # Get analysis end date

            all_relevant_leases: List['Lease'] = []
            # List to store individual rollover loss series before aggregation
            collected_rollover_losses: List[pd.Series] = [] 
            
            initial_leases = self.property.rent_roll.leases if self.property.rent_roll else []

            for initial_lease in initial_leases:
                current_lease: Optional[Lease] = initial_lease # Type hint for clarity
                lease_chain: List['Lease'] = []

                while current_lease is not None:
                    # Check if the current lease overlaps with the analysis period at all
                    lease_periods = current_lease.timeline.period_index
                    
                    # Ensure lease periods are monthly for comparison/intersection
                    if lease_periods.freqstr != 'M':
                         try:
                             lease_periods = lease_periods.asfreq('M', how='start')
                         except ValueError:
                             logger.warning(f"Lease '{current_lease.name}' timeline frequency ({lease_periods.freqstr}) not monthly. Skipping for projection chain.")
                             break # Stop processing this chain

                    if analysis_periods.intersection(lease_periods).empty:
                        # If this lease doesn't even touch the analysis period, 
                        # stop processing its chain and move to the next initial lease.
                        current_lease = None # Stop the inner while loop for this initial_lease
                        continue # Proceed to the next initial_lease in the outer for loop

                    # Add the overlapping lease to our chain
                    lease_chain.append(current_lease)

                    # Check if we need to project further
                    lease_end_date = current_lease.lease_end
                    # Check if the lease ends *on or after* the analysis end date. If so, no more projection needed.
                    if lease_end_date >= analysis_end_date or current_lease.rollover_profile is None:
                        current_lease = None 
                    else:
                        # Project the next lease based on the upon_expiration rule
                        try:
                            upon_expiration = current_lease.upon_expiration
                            logger.debug(f"Projecting next lease for '{current_lease.name}' (ends {lease_end_date}). Upon Expiration: {upon_expiration}")
                            
                            # Initialize rollover loss for this step
                            rollover_loss_this_step: Optional[pd.Series] = None 

                            if upon_expiration == UponExpirationEnum.RENEW:
                                current_lease = current_lease.create_renewal_lease(as_of_date=lease_end_date)
                            elif upon_expiration == UponExpirationEnum.VACATE:
                                 # Now returns a tuple: (Lease, Optional[pd.Series])
                                 new_lease_tuple = current_lease.create_market_lease(
                                     vacancy_start_date=lease_end_date, 
                                     property_area=self.property.net_rentable_area # Pass NRA
                                 )
                                 current_lease = new_lease_tuple[0]
                                 rollover_loss_this_step = new_lease_tuple[1]
                            elif upon_expiration == UponExpirationEnum.MARKET:
                                 # Now returns a tuple: (Lease, Optional[pd.Series])
                                 new_lease_tuple = current_lease.create_market_lease(
                                     vacancy_start_date=lease_end_date, 
                                     property_area=self.property.net_rentable_area # Pass NRA
                                 )
                                 current_lease = new_lease_tuple[0]
                                 rollover_loss_this_step = new_lease_tuple[1]
                            elif upon_expiration == UponExpirationEnum.OPTION:
                                current_lease = current_lease.create_option_lease(as_of_date=lease_end_date)
                            elif upon_expiration == UponExpirationEnum.REABSORB:
                                logger.warning(f"REABSORB not implemented for lease '{current_lease.name}'. Stopping projection chain.")
                                current_lease = None # Stop chain if reabsorb hit
                            else:
                                logger.warning(f"Unknown UponExpirationEnum '{upon_expiration}' for lease '{current_lease.name}'. Stopping projection chain.")
                                current_lease = None
                            
                            # Collect the loss series if it was generated
                            if rollover_loss_this_step is not None:
                                collected_rollover_losses.append(rollover_loss_this_step)

                        except NotImplementedError as nie:
                             logger.error(f"Projection failed for lease '{current_lease.name}' due to NotImplementedError: {nie}. Stopping chain.")
                             current_lease = None
                        except Exception as e:
                            logger.error(f"Error projecting next lease state for '{current_lease.name}': {e}. Stopping chain.", exc_info=True)
                            current_lease = None
                
                # Add the generated chain (that overlaps the analysis period) to the main list
                all_relevant_leases.extend(lease_chain)

            # TODO: Handle initial vacant suites - need to create first market lease for them
            # This requires calling Lease.create_market_lease_for_vacant using rollover assumptions.
            # This is deferred for now but needs implementation for full vacant space handling.

            logger.debug(f"Generated {len(all_relevant_leases)} total lease instances for the analysis period.")
            self._cached_projected_leases = all_relevant_leases # Cache result

            # --- Aggregate and Cache Rollover Vacancy Loss --- 
            if collected_rollover_losses:
                # Create a zero series with the analysis timeline index
                total_rollover_loss = pd.Series(0.0, index=analysis_periods, name="Aggregated Rollover Vacancy Loss")
                for loss_series in collected_rollover_losses:
                     # Reindex each series to the analysis periods and add
                     total_rollover_loss = total_rollover_loss.add(loss_series.reindex(analysis_periods, fill_value=0.0), fill_value=0.0)
                self._cached_rollover_vacancy_loss_series = total_rollover_loss
                logger.debug(f"Aggregated total rollover vacancy loss: {total_rollover_loss.sum():.2f}")
            else:
                # If no losses were collected, cache an empty/zero series
                self._cached_rollover_vacancy_loss_series = pd.Series(0.0, index=analysis_periods, name="Aggregated Rollover Vacancy Loss")
                logger.debug("No specific rollover vacancy losses generated during projection.")

        return self._cached_projected_leases

    def _calculate_rollover_vacancy_loss_series(self) -> pd.Series:
        """Helper method to ensure projected leases (and thus rollover loss) are 
           calculated and return the cached rollover loss series."""
        # Ensure the projection runs, which calculates and caches the loss
        self._get_projected_leases() 
        # Return the cached series (guaranteed to exist after calling _get_projected_leases)
        return self._cached_rollover_vacancy_loss_series

    def _calculate_occupancy_series(self) -> pd.Series:
        """Calculates the physical occupancy rate series over the analysis timeline
           using the projected lease sequence. Caches the result.
        """
        logger.debug("Calculating occupancy series (using projected leases - checking cache).") # Updated logging
        
        if self._cached_occupancy_series is None:
            logger.debug("Occupancy cache miss. Calculating now.")
            analysis_periods = self._create_timeline().period_index
            occupied_area_series = pd.Series(0.0, index=analysis_periods)

            # Use the projected leases now
            projected_leases = self._get_projected_leases() 

            if projected_leases: # Check if list is not empty
                for lease in projected_leases:
                    # Existing logic to calculate active periods and sum area
                    lease_periods = lease.timeline.period_index
                    if lease_periods.freqstr != 'M':
                         try:
                             lease_periods = lease_periods.asfreq('M', how='start')
                         except ValueError:
                             logger.warning(f"Lease '{lease.name}' timeline frequency ({lease_periods.freqstr}) not monthly. Skipping for occupancy calc.")
                             continue

                    # Find periods where this specific lease is active within the analysis
                    active_periods = analysis_periods.intersection(lease_periods)
                    if not active_periods.empty:
                         # Add this lease's area to the occupied series for its active periods
                         occupied_area_series.loc[active_periods] += lease.area
            
            # Rest of the calculation remains the same
            total_nra = self.property.net_rentable_area
            if total_nra > 0:
                 # Clip occupancy between 0 and potentially > 1 if NRA definition issue, clip at 1 realistic max.
                 occupancy_series = (occupied_area_series / total_nra).clip(0, 1)
            else:
                 occupancy_series = pd.Series(0.0, index=analysis_periods)
                 
            occupancy_series.name = "Occupancy Rate"
            self._cached_occupancy_series = occupancy_series
            logger.debug(f"Calculated occupancy series using projected leases. Average: {occupancy_series.mean():.2%}") # Updated logging

        return self._cached_occupancy_series

    def _collect_revenue_models(self) -> List[CashFlowModel]:
        """Extracts all relevant projected revenue models for the analysis period."""
        logger.debug("Collecting revenue models (including projections).") # Added logging
        # Get the full list of actual and projected leases
        projected_leases = self._get_projected_leases() 
        revenue_models: List[CashFlowModel] = list(projected_leases) # Start with projected leases

        # Add miscellaneous income items (Property.miscellaneous_income is now List[MiscIncome])
        if self.property.miscellaneous_income: # Check if the list exists and is not empty
            revenue_models.extend(self.property.miscellaneous_income) # Extend directly with the list
        
        logger.debug(f"Collected {len(revenue_models)} total revenue models.") # Added logging
        return revenue_models

    def _collect_expense_models(self) -> List[CashFlowModel]:
        """Extracts all expense models from the property."""
        expense_models: List[CashFlowModel] = []
        if self.property.expenses and self.property.expenses.operating_expenses:
            op_ex_items = self.property.expenses.operating_expenses.expense_items
            if op_ex_items:
                expense_models.extend(op_ex_items)
        if self.property.expenses and self.property.expenses.capital_expenses:
            cap_ex_items = self.property.expenses.capital_expenses.expense_items
            if cap_ex_items:
                expense_models.extend(cap_ex_items)
        
        # Add TIs and LCs associated with the *projected* leases
        projected_leases = self._get_projected_leases()
        for lease in projected_leases:
             if lease.ti_allowance:
                 expense_models.append(lease.ti_allowance)
             if lease.leasing_commission:
                 expense_models.append(lease.leasing_commission)
                 
        return expense_models

    def _collect_other_cash_flow_models(self) -> List[CashFlowModel]:
        """Extracts any other cash flow models."""
        # TODO: Implement collection logic if/when debt or other non-property models are added.
        return []

    def _run_compute_cf(
        self, 
        model: CashFlowModel, 
        lookup_fn: Callable, 
        occupancy_series: pd.Series
        ) -> Union[pd.Series, Dict[str, pd.Series]]:
        """
        Helper to call model.compute_cf, injecting occupancy series if needed.

        Uses `inspect.signature` to check if the target model's `compute_cf` method
        accepts an `occupancy_rate` (or `occupancy_series`) keyword argument. If so,
        the pre-calculated `occupancy_series` is passed. Otherwise, `compute_cf`
        is called only with the `lookup_fn`.

        Also injects `property_area` if the signature includes it (needed for some models like RecoveryMethod).

        Args:
            model: The CashFlowModel instance to compute.
            lookup_fn: The function to resolve references (UUIDs, property strings, AggregateLineKeys).
            occupancy_series: The pre-calculated occupancy series for the analysis period.

        Returns:
            The result from `model.compute_cf` (either a Series or Dict of Series).
        """
        logger.debug(f"Running compute_cf for model '{model.name}' ({model.model_id})") # DEBUG: Entry
        sig = inspect.signature(model.compute_cf)
        params = sig.parameters
        kwargs = {"lookup_fn": lookup_fn}
        
        # Inject occupancy if needed
        if "occupancy_rate" in params or "occupancy_series" in params:
            kwargs["occupancy_rate"] = occupancy_series # Pass the series
            logger.debug(f"  Injecting occupancy_rate into '{model.name}'.compute_cf") # DEBUG: Occupancy injection
            
        # Inject property_area if needed (e.g., for Lease compute_cf calling RecoveryMethod)
        if "property_area" in params:
             kwargs["property_area"] = self.property.net_rentable_area
             logger.debug(f"  Injecting property_area ({self.property.net_rentable_area}) into '{model.name}'.compute_cf")

        result = model.compute_cf(**kwargs)
        logger.debug(f"  Finished compute_cf for '{model.name}'. Result type: {type(result).__name__}") # DEBUG: Exit
        return result

    def _compute_detailed_flows(self) -> List[Tuple[Dict, pd.Series]]:
        """Computes all individual cash flows, handling dependencies and context injection.
        Returns a detailed list of results, each tagged with metadata. Caches results.
        """
        logger.debug("Starting computation of detailed flows (checking cache).") # DEBUG: Entry
        if self._cached_detailed_flows is None:
            logger.debug("Detailed flows cache miss. Computing now.") # DEBUG: Cache miss
            analysis_timeline = self._create_timeline()
            analysis_periods = analysis_timeline.period_index
            # Calculate occupancy using projected leases BEFORE collecting models
            occupancy_series = self._calculate_occupancy_series() 
            # Collect ALL models, including projected leases and their associated TIs/LCs
            all_models = ( self._collect_revenue_models() + self._collect_expense_models() + self._collect_other_cash_flow_models() )
            logger.debug(f"Collected {len(all_models)} models for computation.") # DEBUG: Model count
            
            # --- Pre-calculate Base Year Stops --- 
            self._pre_calculate_all_base_year_stops(all_models)
            # -------------------------------------
            
            # Ensure all models have unique IDs (safeguard)
            model_ids = [m.model_id for m in all_models]
            if len(model_ids) != len(set(model_ids)):
                 logger.error("Duplicate model IDs detected in collected models. Aborting calculation.")
                 # Find duplicates for better error message
                 from collections import Counter
                 duplicates = [item for item, count in Counter(model_ids).items() if count > 1]
                 logger.error(f"Duplicate IDs: {duplicates}")
                 raise ValueError("Duplicate model IDs found during collection.")
                 
            model_map = {model.model_id: model for model in all_models}
            computed_results: Dict[UUID, Union[pd.Series, Dict[str, pd.Series]]] = {}
            use_iterative_fallback = False
            
            # --- Define Lookup Function ---
            def lookup_fn(key: Union[str, UUID]) -> Union[float, pd.Series, Dict, Any]:
                # This lookup is used in the single-pass (DAG) computation.
                # It should NOT resolve aggregate keys, as those imply cycles.
                if isinstance(key, UUID):
                    # Look up previously computed results within this DAG pass
                    if key in computed_results: 
                        return computed_results[key]
                    # If not found, it's an error in the DAG structure or definition
                    else: 
                        raise LookupError(f"(DAG Path) Dependency result for model ID {key} not available.")
                elif isinstance(key, str):
                    # Check if the string key matches a known Aggregate Line Key
                    matched_agg_key = AggregateLineKey.from_value(key)
                    if matched_agg_key is not None:
                        # If successful, raise error: aggregates shouldn't be needed in DAG path
                        raise LookupError(
                            f"(DAG Path) Attempted to look up aggregate line '{key}'. "
                            f"This indicates a dependency cycle requiring iterative calculation. "
                            # f"Model requesting: {model.name} ({model_id})" # model is not in scope here
                        )
                        
                    # Check Property attributes
                    if hasattr(self.property, key):
                        value = getattr(self.property, key)
                        # Validate that the retrieved property attribute has a simple, expected type
                        if isinstance(value, (int, float, str, date)): 
                            return value
                        else: 
                            # Raise error if property attribute is a complex object or unexpected type
                            raise TypeError(f"(DAG Path) Property attribute '{key}' has unexpected type {type(value)}. Expected simple scalar/string/date.")
                    # If not found as Aggregate or Property attribute, raise specific error
                    else: 
                        raise LookupError(
                            f"(DAG Path) Cannot resolve string reference '{key}'. "
                            f"It is not a valid AggregateLineKey value or a known Property attribute."
                        )
                else: 
                    raise TypeError(f"(DAG Path) Unsupported lookup key type: {type(key)}")

            # --- Attempt Topological Sort ---
            try:
                # Build dependency graph based on model_id references
                graph: Dict[UUID, Set[UUID]] = {m_id: set() for m_id in model_map.keys()}
                for model_id, model in model_map.items():
                    # Check if the model has a reference attribute that is a UUID
                    if hasattr(model, 'reference') and isinstance(model.reference, UUID):
                        dependency_id = model.reference
                        if dependency_id in graph: 
                             graph[model_id].add(dependency_id)
                             logger.debug(f"  Graph dependency: {model.name} ({model_id}) -> {model_map[dependency_id].name} ({dependency_id})")
                        else: 
                             logger.warning(f"Model '{model.name}' ({model_id}) refs unknown ID {dependency_id}. Ignored in dependency graph.")
                    # Also consider potential dependencies in TI/LC if they reference the Lease model_id
                    if hasattr(model, 'ti_allowance') and model.ti_allowance and isinstance(model.ti_allowance.reference, UUID):
                         dependency_id = model.ti_allowance.reference
                         if dependency_id in graph: 
                             graph[model.ti_allowance.model_id].add(dependency_id)
                    if hasattr(model, 'leasing_commission') and model.leasing_commission and isinstance(model.leasing_commission.reference, UUID):
                         dependency_id = model.leasing_commission.reference
                         if dependency_id in graph: 
                             graph[model.leasing_commission.model_id].add(dependency_id)
                         
                ts = TopologicalSorter(graph)
                # Prepare the graph for sorting
                ts.prepare()
                logger.info("Attempting topological sort for single-pass computation.")
                
                # Process models level by level according to the topological sort
                while ts.is_active():
                     node_group = ts.get_ready()
                     logger.debug(f"  Processing node group: {[model_map[node_id].name for node_id in node_group]}")
                     for model_id in node_group:
                         model = model_map[model_id]
                         logger.debug(f"    Attempting DAG compute: '{model.name}' ({model_id})")
                         try: 
                             result = self._run_compute_cf(model, lookup_fn, occupancy_series)
                             computed_results[model_id] = result
                             logger.debug(f"      Success: '{model.name}' ({model_id}) computed.")
                         except Exception as e: 
                             logger.error(f"(DAG Path) Error computing '{model.name}' ({model_id}). Skipped.", exc_info=True)
                             if self.settings.calculation.fail_on_error: 
                                 raise e
                         computed_results.pop(model_id, None)
                     ts.done(*node_group) # Mark nodes in the group as done

                # If topological sort completes, graph is a DAG
                logger.info("Dependency graph is a DAG. Single-pass computation successful.")

            # --- Fallback to Iterative on Cycle or Graph Error ---
            except CycleError as e: 
                # Log warning instead of print
                logger.warning(f"Cycle detected in model dependencies: {[model_map[node_id].name for node_id in e.args[1]]}. Falling back to iteration.")
                use_iterative_fallback = True
            # Log error with exception info instead of print
            except Exception as graph_err: 
                logger.error(f"Error during dependency graph processing ({graph_err}). Falling back to iteration.", exc_info=True)
                use_iterative_fallback = True
                
            if use_iterative_fallback:
                logger.info("Using iterative multi-pass computation due to cycle or graph error.")
                # Ensure occupancy_series uses the analysis_periods index
                occupancy_series = occupancy_series.reindex(analysis_periods, fill_value=0.0)
                computed_results = self._compute_cash_flows_iterative( all_models, occupancy_series )

            # --- Process computed results into the detailed list ---
            processed_flows: List[Tuple[Dict, pd.Series]] = []
            for model_id, result in computed_results.items():
                original_model = model_map.get(model_id) 
                if not original_model: 
                    continue
                results_to_process: Dict[str, pd.Series] = {}
                if isinstance(result, pd.Series): 
                    results_to_process = {"value": result}
                elif isinstance(result, dict): 
                    results_to_process = result
                # Log warning instead of print
                else: 
                    logger.warning(f"Unexpected result type {type(result)} for model '{original_model.name}'. Skipped processing.")
                    continue

                for component_name, series in results_to_process.items():
                    if not isinstance(series, pd.Series): 
                        continue
                    try:
                        # Align index
                        if not isinstance(series.index, pd.PeriodIndex):
                             if isinstance(series.index, pd.DatetimeIndex): 
                                 series.index = series.index.to_period(freq='M')
                             else: 
                                 series.index = pd.PeriodIndex(series.index, freq='M')
                        aligned_series = series.reindex(analysis_periods, fill_value=0.0)
                    # Log warning with exception info instead of print
                    except Exception: 
                        logger.warning(f"Alignment failed for component '{component_name}' from model '{original_model.name}'. Skipping component.", exc_info=True)
                        continue
                    
                    # Create metadata dictionary for this specific series
                    metadata = {
                        "model_id": str(model_id), # Store UUID as string for potential non-python use
                        "name": original_model.name,
                        "category": original_model.category,
                        "subcategory": str(original_model.subcategory), # Ensure string
                        "component": component_name,
                    }
                    processed_flows.append((metadata, aligned_series))
            
            logger.debug(f"Finished base computation. Got {len(computed_results)} results ({len(processed_flows)} detailed series).") # DEBUG: Computation end
            self._cached_detailed_flows = processed_flows # Cache the result
        
        logger.debug("Finished computation of detailed flows.") # DEBUG: Exit
        return self._cached_detailed_flows

    def _aggregate_detailed_flows(self, detailed_flows: List[Tuple[Dict, pd.Series]]) -> Dict[AggregateLineKey, pd.Series]:
        """Aggregates detailed flows into standard financial line items using AggregateLineKey.
        
        This method performs the core aggregation logic:
        1. Maps individual cash flow series (from Leases, Expenses, etc.) to 
           standard AggregateLineKey categories.
        2. Calculates derived lines like EGR, EGI, NOI, and UCF.
        3. Calculates General Vacancy and Collection Loss based on property settings.
           - If configured, reduces General Vacancy by specific Rollover Vacancy Loss 
             to prevent double-counting.
        4. Recalculates derived lines affected by vacancy/collection loss.
        
        Args:
            detailed_flows: A list where each item is a tuple containing:
                            - metadata (Dict): Info about the cash flow source.
                            - series (pd.Series): The calculated monthly cash flow.
                            
        Returns:
            A dictionary where keys are AggregateLineKey enums and values are 
            the corresponding aggregated pandas Series over the analysis timeline.
        """
        logger.debug(f"Starting aggregation of {len(detailed_flows)} detailed flows.") # DEBUG: Entry
        # TODO: Incorporate GENERAL_VACANCY_LOSS when implemented - Addressed below
        # TODO: Allow for more flexible aggregation rules or custom groupings?
        analysis_periods = self._create_timeline().period_index # Get timeline for initialization
        
        # Initialize all *display* keys from the enum with zero series
        # We will populate these directly now, removing the need for _RAW_ keys
        aggregated_flows: Dict[AggregateLineKey, pd.Series] = {
            key: pd.Series(0.0, index=analysis_periods, name=key.value) 
            for key in AggregateLineKey.get_display_keys() # Use display keys
        }

        # --- Map detailed flows directly to final aggregate lines --- 
        # Get set of MiscIncome model IDs for quick lookup
        misc_income_models = set(
            m.model_id for m in self.property.miscellaneous_income
        ) if self.property.miscellaneous_income else set() # Iterate directly over list

        for metadata, series in detailed_flows:
            model_id = UUID(metadata["model_id"]) # Convert back to UUID for lookup
            category = metadata["category"]
            subcategory = metadata["subcategory"] # Already stringified
            component = metadata["component"]
            target_aggregate_key: Optional[AggregateLineKey] = None

            # Map detailed flows to the appropriate aggregate key
            if category == "Revenue":
                 # Check if it's Misc Income based on model_id
                 if model_id in misc_income_models:
                     if component == "value": # Assume 'value' is the main component for MiscIncome
                         target_aggregate_key = AggregateLineKey.MISCELLANEOUS_INCOME
                 # Otherwise assume it's Lease related
                 elif subcategory == str(RevenueSubcategoryEnum.LEASE): # Explicitly check subcategory
                     if component == "base_rent":
                         target_aggregate_key = AggregateLineKey.POTENTIAL_GROSS_REVENUE
                     elif component == "recoveries":
                         target_aggregate_key = AggregateLineKey.EXPENSE_REIMBURSEMENTS
                     elif component == "abatement": # Capture abatement separately
                         target_aggregate_key = AggregateLineKey.RENTAL_ABATEMENT
                     elif component == "revenue": # Skip component: 'revenue' is derived (rent+recov-abate) within Lease.compute_cf
                         pass 
                     elif component == "value": 
                         # Skip component: Raw 'value' from Lease is not mapped here. 
                         # 'base_rent' (mapped above) reflects rent after abatements, used for PGR.
                         # FIXME: Mapping 'value' could double-count potential revenue.
                         logger.debug(f"Skipping mapping for Lease component 'value': {metadata['name']}")
                         pass

            elif category == "Expense":
                 if subcategory == str(ExpenseSubcategoryEnum.OPEX) and component == "value":
                     target_aggregate_key = AggregateLineKey.TOTAL_OPERATING_EXPENSES
                 elif subcategory == str(ExpenseSubcategoryEnum.CAPEX) and component == "value":
                     target_aggregate_key = AggregateLineKey.TOTAL_CAPITAL_EXPENDITURES
                 elif subcategory == "TI Allowance" and component == "value": 
                     target_aggregate_key = AggregateLineKey.TOTAL_TENANT_IMPROVEMENTS
                 elif subcategory == "Leasing Commission" and component == "value":
                     target_aggregate_key = AggregateLineKey.TOTAL_LEASING_COMMISSIONS
            
            # Add to the target aggregate series if found
            if target_aggregate_key is not None:
                 # Ensure series index matches (should already be aligned)
                 safe_series = series.reindex(analysis_periods, fill_value=0.0)
                 # Use .add() to accumulate, ensuring key exists (initialized above)
                 aggregated_flows[target_aggregate_key] = aggregated_flows[target_aggregate_key].add(safe_series, fill_value=0.0)
            else: 
                 logger.debug(f"Flow {metadata['name']}/{component} (Cat: {category}, Sub: {subcategory}) not mapped to aggregate.")


        # --- Calculate derived lines --- 
        # Placeholder for Vacancy (needs proper calculation model) - now calculated below
        # Ensure keys exist even if no items mapped to them initially
        aggregated_flows.setdefault(AggregateLineKey.GENERAL_VACANCY_LOSS, pd.Series(0.0, index=analysis_periods))
        # RENTAL_ABATEMENT should now be populated correctly if present in detailed flows
        aggregated_flows.setdefault(AggregateLineKey.RENTAL_ABATEMENT, pd.Series(0.0, index=analysis_periods)) 
        aggregated_flows.setdefault(AggregateLineKey.TOTAL_DEBT_SERVICE, pd.Series(0.0, index=analysis_periods)) # Ensure Debt Service placeholder exists

        # Calculate Effective Gross Revenue (EGR) - *Before* Vacancy/Collection Loss
        pgr = aggregated_flows.get(AggregateLineKey.POTENTIAL_GROSS_REVENUE, pd.Series(0.0, index=analysis_periods))
        misc = aggregated_flows.get(AggregateLineKey.MISCELLANEOUS_INCOME, pd.Series(0.0, index=analysis_periods))
        abate = aggregated_flows.get(AggregateLineKey.RENTAL_ABATEMENT, pd.Series(0.0, index=analysis_periods))
        aggregated_flows[AggregateLineKey.EFFECTIVE_GROSS_REVENUE] = pgr + misc - abate

        # Calculate Total Effective Gross Income (Total EGI) - Requires Vacancy, calculated later
        # Calculate Net Operating Income (NOI) - Requires EGI & OpEx, calculated later

        # --- Calculate Vacancy & Collection Loss (using property.losses) --- 
        logger.debug("Calculating Vacancy and Collection Loss based on property loss settings.")
        # Get loss config from property
        loss_config = self.property.losses 
        # Retrieve the pre-calculated specific rollover vacancy loss
        # This series contains potential rent lost ONLY during specific downtime periods.
        rollover_vacancy_loss_series = self._calculate_rollover_vacancy_loss_series()

        # --- General Vacancy Loss --- 
        # Determine the basis for the general vacancy calculation (PGR or EGR)
        vacancy_basis_series: pd.Series
        if loss_config.general_vacancy.method == VacancyLossMethodEnum.POTENTIAL_GROSS_REVENUE:
            vacancy_basis_series = aggregated_flows.get(AggregateLineKey.POTENTIAL_GROSS_REVENUE, pd.Series(0.0, index=analysis_periods))
            logger.debug(f"  Vacancy basis: PGR (Sum: {vacancy_basis_series.sum():.2f})")
        elif loss_config.general_vacancy.method == VacancyLossMethodEnum.EFFECTIVE_GROSS_REVENUE:
            # Use the EGR calculated *before* vacancy/collection loss application.
            vacancy_basis_series = aggregated_flows.get(AggregateLineKey.EFFECTIVE_GROSS_REVENUE, pd.Series(0.0, index=analysis_periods))
            logger.debug(f"  Vacancy basis: EGR (Sum: {vacancy_basis_series.sum():.2f})")
        else:
            # Default to PGR if method is unknown
            logger.warning(f"Unknown vacancy_loss_method: '{loss_config.general_vacancy.method}'. Defaulting to PGR.")
            vacancy_basis_series = aggregated_flows.get(AggregateLineKey.POTENTIAL_GROSS_REVENUE, pd.Series(0.0, index=analysis_periods))
        
        # Calculate the gross general vacancy allowance based on the rate and basis
        gross_general_vacancy_loss = vacancy_basis_series * loss_config.general_vacancy.rate
        logger.debug(f"  Calculated Gross General Vacancy Loss (Rate: {loss_config.general_vacancy.rate:.1%}): {gross_general_vacancy_loss.sum():.2f}")
        
        # Apply reduction by specific rollover vacancy loss if the flag is set
        final_general_vacancy_loss: pd.Series
        if loss_config.general_vacancy.reduce_general_vacancy_by_rollover_vacancy:
            logger.debug(f"  Reducing general vacancy by specific rollover vacancy loss (Sum: {rollover_vacancy_loss_series.sum():.2f}).")
            # Ensure alignment before subtraction (though should align via analysis_periods)
            aligned_gross_vac, aligned_rollover_vac = gross_general_vacancy_loss.align(
                rollover_vacancy_loss_series, join='left', fill_value=0.0
            )
            # Subtract specific loss from gross allowance, ensuring result >= 0
            net_general_vacancy_loss = (aligned_gross_vac - aligned_rollover_vac).clip(lower=0)
            final_general_vacancy_loss = net_general_vacancy_loss
            logger.debug(f"    Net General Vacancy Loss after reduction: {net_general_vacancy_loss.sum():.2f}")
        else:
            # If reduction is disabled, use the full gross general vacancy
            logger.debug("  Reduction by rollover vacancy is disabled. Using gross general vacancy.")
            final_general_vacancy_loss = gross_general_vacancy_loss
        
        # Assign the final calculated general vacancy loss (net or gross) to the aggregate results
        aggregated_flows[AggregateLineKey.GENERAL_VACANCY_LOSS] = final_general_vacancy_loss

        # --- Collection Loss --- 
        # Determine the basis for collection loss calculation
        collection_basis_series: pd.Series
        # FIXME: "scheduled_income" basis not implemented - requires summing specific rent components before loss/recovery
        if loss_config.collection_loss.basis == "pgr":
            collection_basis_series = aggregated_flows.get(AggregateLineKey.POTENTIAL_GROSS_REVENUE, pd.Series(0.0, index=analysis_periods))
            logger.debug(f"  Collection loss basis: PGR (Sum: {collection_basis_series.sum():.2f})")
        elif loss_config.collection_loss.basis == "egi":
            # Calculate EGI *before* collection loss but *after* General Vacancy
            # EGI = EGR - General Vacancy (final) + Reimbursements
            egr = aggregated_flows.get(AggregateLineKey.EFFECTIVE_GROSS_REVENUE, pd.Series(0.0, index=analysis_periods))
            # Use the *final* general vacancy loss calculated above
            vac = aggregated_flows.get(AggregateLineKey.GENERAL_VACANCY_LOSS, pd.Series(0.0, index=analysis_periods)) 
            recov = aggregated_flows.get(AggregateLineKey.EXPENSE_REIMBURSEMENTS, pd.Series(0.0, index=analysis_periods))
            collection_basis_series = egr - vac + recov # This is EGI *before* collection loss
            logger.debug(f"  Collection loss basis: EGI (Sum: {collection_basis_series.sum():.2f})")
        else: # Default or unknown basis
            logger.warning(f"Unsupported collection_loss_basis: '{loss_config.collection_loss.basis}'. Defaulting to EGI.")
            egr = aggregated_flows.get(AggregateLineKey.EFFECTIVE_GROSS_REVENUE, pd.Series(0.0, index=analysis_periods))
            vac = aggregated_flows.get(AggregateLineKey.GENERAL_VACANCY_LOSS, pd.Series(0.0, index=analysis_periods)) 
            recov = aggregated_flows.get(AggregateLineKey.EXPENSE_REIMBURSEMENTS, pd.Series(0.0, index=analysis_periods))
            collection_basis_series = egr - vac + recov # Default to EGI basis
        
        # Calculate collection loss amount
        calculated_collection_loss = collection_basis_series * loss_config.collection_loss.rate
        # Assign to the aggregate key
        if AggregateLineKey.COLLECTION_LOSS in aggregated_flows:
             aggregated_flows[AggregateLineKey.COLLECTION_LOSS] = calculated_collection_loss
             logger.debug(f"  Calculated Collection Loss (Rate: {loss_config.collection_loss.rate:.1%}): {calculated_collection_loss.sum():.2f}")
        else:
             # Ensure placeholder exists if COLLECTION_LOSS wasn't a display key initially
             aggregated_flows.setdefault(AggregateLineKey.COLLECTION_LOSS, calculated_collection_loss)
             logger.error("AggregateLineKey.COLLECTION_LOSS was not pre-initialized. Added dynamically.")


        # --- Recalculate derived lines using final calculated losses --- 
        # Effective Gross Revenue (EGR) - Remains the same (calculated before losses)
        # Already calculated above: aggregated_flows[AggregateLineKey.EFFECTIVE_GROSS_REVENUE] 

        # Total Effective Gross Income (Total EGI)
        egr = aggregated_flows.get(AggregateLineKey.EFFECTIVE_GROSS_REVENUE, pd.Series(0.0, index=analysis_periods))
        # Use the *final* vacancy and collection losses calculated above
        vac = aggregated_flows.get(AggregateLineKey.GENERAL_VACANCY_LOSS, pd.Series(0.0, index=analysis_periods))
        coll_loss = aggregated_flows.get(AggregateLineKey.COLLECTION_LOSS, pd.Series(0.0, index=analysis_periods))
        recov = aggregated_flows.get(AggregateLineKey.EXPENSE_REIMBURSEMENTS, pd.Series(0.0, index=analysis_periods))
        aggregated_flows[AggregateLineKey.TOTAL_EFFECTIVE_GROSS_INCOME] = egr - vac - coll_loss + recov # Subtract both losses

        # Net Operating Income (NOI)
        egi = aggregated_flows.get(AggregateLineKey.TOTAL_EFFECTIVE_GROSS_INCOME, pd.Series(0.0, index=analysis_periods))
        opex = aggregated_flows.get(AggregateLineKey.TOTAL_OPERATING_EXPENSES, pd.Series(0.0, index=analysis_periods))
        aggregated_flows[AggregateLineKey.NET_OPERATING_INCOME] = egi - opex

        # Calculate Unlevered Cash Flow (UCF)
        ucf = aggregated_flows.get(AggregateLineKey.NET_OPERATING_INCOME, pd.Series(0.0, index=analysis_periods))
        tis = aggregated_flows.get(AggregateLineKey.TOTAL_TENANT_IMPROVEMENTS, pd.Series(0.0, index=analysis_periods))
        lcs = aggregated_flows.get(AggregateLineKey.TOTAL_LEASING_COMMISSIONS, pd.Series(0.0, index=analysis_periods))
        capex = aggregated_flows.get(AggregateLineKey.TOTAL_CAPITAL_EXPENDITURES, pd.Series(0.0, index=analysis_periods))
        aggregated_flows[AggregateLineKey.UNLEVERED_CASH_FLOW] = ucf - tis - lcs - capex

        # Calculate Levered Cash Flow (LCF)
        ucf = aggregated_flows.get(AggregateLineKey.UNLEVERED_CASH_FLOW, pd.Series(0.0, index=analysis_periods))
        debt = aggregated_flows.get(AggregateLineKey.TOTAL_DEBT_SERVICE, pd.Series(0.0, index=analysis_periods))
        aggregated_flows[AggregateLineKey.LEVERED_CASH_FLOW] = ucf - debt
        
        # Final result contains only the display keys initialized at the start
        final_aggregates = aggregated_flows 

        # DEBUG: Log aggregate values calculated this pass
        if logger.isEnabledFor(logging.DEBUG):
             agg_summary = {k.value: f"{v.sum():.2f}" for k, v in final_aggregates.items() if v.sum() != 0}
             logger.debug(f"Final aggregated values: {agg_summary}")
        
        return final_aggregates # Return only display keys

    def _get_aggregated_flows(self) -> Dict[AggregateLineKey, pd.Series]:
        """Computes/retrieves detailed flows, then computes/retrieves aggregated flows using Enum keys."""
        logger.debug("Getting aggregated flows (checking cache).") # DEBUG: Entry
        # Ensure detailed flows are computed and cached
        detailed_flows = self._compute_detailed_flows() 
        
        # Compute/cache aggregated flows from the *final* detailed flows
        if self._cached_aggregated_flows is None:
            logger.debug("Aggregated flows cache miss. Computing now.") # DEBUG: Cache miss
            self._cached_aggregated_flows = self._aggregate_detailed_flows(detailed_flows)
            
        logger.debug("Finished getting aggregated flows.") # DEBUG: Exit
        return self._cached_aggregated_flows

    # --- Public Methods ---
    def create_detailed_cash_flow_dataframe(self) -> pd.DataFrame:
        """Generates or retrieves a cached DataFrame of granular cash flows.

        The DataFrame's columns form a MultiIndex based on the metadata
        (Category, Subcategory, Name, Component) associated with each
        individual computed cash flow series. The index represents
        monthly periods over the analysis timeline.

        Returns:
            A detailed pandas DataFrame suitable for in-depth analysis and auditing.
        """
        logger.debug("Creating detailed cash flow DataFrame (checking cache).") # DEBUG: Entry
        if self._cached_detailed_cash_flow_dataframe is None:
            logger.debug("Detailed DF cache miss. Computing now.") # DEBUG: Cache miss
            detailed_flows = self._compute_detailed_flows()
            
            if not detailed_flows: # Handle case with no results
                logger.debug("No detailed flows found, returning empty DataFrame.")
                # Return empty DF with correct index
                return pd.DataFrame(index=self._create_timeline().period_index)

            # Prepare data for DataFrame construction
            data_dict = {}
            # Use analysis timeline index consistently
            index = self._create_timeline().period_index 
            tuples = []
            
            for metadata, series in detailed_flows:
                 # Create tuple for MultiIndex
                 col_tuple = (
                     metadata['category'], 
                     metadata['subcategory'], 
                     metadata['name'], 
                     metadata['component']
                 )
                 # Prevent duplicate columns by checking if tuple already exists
                 if col_tuple not in tuples:
                     tuples.append(col_tuple)
                     # Ensure series aligns with the common index
                     data_dict[col_tuple] = series.reindex(index, fill_value=0.0)
                 else:
                     # If tuple exists, add series to existing column data
                     data_dict[col_tuple] = data_dict[col_tuple].add(series.reindex(index, fill_value=0.0), fill_value=0.0)
                     logger.debug(f"Aggregating duplicate column: {col_tuple}")

            if not tuples: # Check if tuples list is empty
                 logger.debug("No valid columns generated for detailed DataFrame.")
                 return pd.DataFrame(index=index)

            multi_index = pd.MultiIndex.from_tuples(tuples, names=['Category', 'Subcategory', 'Name', 'Component'])
            
            # Create DataFrame from the potentially aggregated data_dict keys
            df = pd.DataFrame({col: data_dict[col] for col in tuples}, index=index)
            df.columns = multi_index
            df.index.name = "Period"
            
            # Sort columns for consistent presentation (optional but nice)
            df = df.sort_index(axis=1) 
            
            self._cached_detailed_cash_flow_dataframe = df

        logger.debug("Finished creating detailed cash flow DataFrame.") # DEBUG: Exit
        return self._cached_detailed_cash_flow_dataframe

    def create_cash_flow_dataframe(self) -> pd.DataFrame:
        """Generates or retrieves a cached DataFrame of the property's cash flows.

        Columns include standard aggregated lines (Total Revenue, Total OpEx, etc.)
        and calculated metrics (NOI, Unlevered Cash Flow), keyed by AggregateLineKey values.
        The index represents monthly periods over the analysis timeline.

        Returns:
            A pandas DataFrame summarizing the property's cash flows.
        """
        logger.debug("Creating summary cash flow DataFrame (checking cache).") # DEBUG: Entry
        if self._cached_cash_flow_dataframe is None:
            logger.debug("Summary DF cache miss. Computing now.") # DEBUG: Cache miss
            # _get_aggregated_flows now returns Dict[AggregateLineKey, pd.Series]
            flows: Dict[AggregateLineKey, pd.Series] = self._get_aggregated_flows()
            
            # Use display keys from Enum for standard column order
            column_order = AggregateLineKey.get_display_keys()
            
            # Create DataFrame using Enum values as column headers
            # Ensure all keys exist in the flows dict, default to zero series if not
            df_data = {}
            ref_index = self._create_timeline().period_index # Use a reference index
            for key in column_order:
                # Use the key's value (string) for the DataFrame column name
                df_data[key.value] = flows.get(key, pd.Series(0.0, index=ref_index, name=key.value))
            
            cf_df = pd.DataFrame(df_data, index=ref_index)
            # Order columns as defined above
            cf_df = cf_df[[key.value for key in column_order]]
            cf_df.index.name = "Period"
            
            self._cached_cash_flow_dataframe = cf_df
            
        logger.debug("Finished creating summary cash flow DataFrame.") # DEBUG: Exit
        return self._cached_cash_flow_dataframe

    def net_operating_income(self) -> pd.Series:
        """Calculates or retrieves the Net Operating Income (NOI) series."""
        cf_df = self.create_cash_flow_dataframe()
        key = AggregateLineKey.NET_OPERATING_INCOME.value
        if key in cf_df.columns:
            return cf_df[key]
        else: 
            # Fallback if DataFrame doesn't have it (shouldn't happen now)
            flows = self._get_aggregated_flows()
            return flows.get(AggregateLineKey.NET_OPERATING_INCOME, pd.Series(0.0, index=self._create_timeline().period_index))

    def cash_flow_from_operations(self) -> pd.Series:
        """
        Calculates or retrieves the Cash Flow From Operations series.
        (Currently defined as Unlevered Cash Flow).
        """
        # TODO: Revisit if this definition should change
        return self.unlevered_cash_flow()

    def unlevered_cash_flow(self) -> pd.Series:
        """Calculates or retrieves the Unlevered Cash Flow (UCF) series."""
        cf_df = self.create_cash_flow_dataframe()
        key = AggregateLineKey.UNLEVERED_CASH_FLOW.value
        if key in cf_df.columns:
            return cf_df[key]
        else: 
            # Fallback
            flows = self._get_aggregated_flows()
            return flows.get(AggregateLineKey.UNLEVERED_CASH_FLOW, pd.Series(0.0, index=self._create_timeline().period_index))

    def debt_service(self) -> pd.Series:
        """
        Calculates debt service (Placeholder: returns the value from aggregated flows).

        NOTE: Full implementation requires integration with debt financing models.
              Currently returns the placeholder value calculated during aggregation.
              
        Returns:
            A pandas Series representing debt service.
        """
        # FIXME: Implement actual debt service calculation based on Debt Models.
        # For now, return the placeholder value calculated in _aggregate_detailed_flows
        flows = self._get_aggregated_flows()
        return flows.get(AggregateLineKey.TOTAL_DEBT_SERVICE, pd.Series(0.0, index=self._create_timeline().period_index))
    
    def levered_cash_flow(self) -> pd.Series:
        """Calculates Levered Cash Flow (UCF - Debt Service)."""
        cf_df = self.create_cash_flow_dataframe()
        ucf_key = AggregateLineKey.UNLEVERED_CASH_FLOW.value
        ds_key = AggregateLineKey.TOTAL_DEBT_SERVICE.value
        
        if ucf_key in cf_df.columns and ds_key in cf_df.columns:
             # Align handled by DataFrame construction now
             return cf_df[ucf_key] - cf_df[ds_key]
        else:
            # Fallback
            ucf = self.unlevered_cash_flow()
            ds = self.debt_service() 
            aligned_ucf, aligned_ds = ucf.align(ds, join='left', fill_value=0.0)
            return aligned_ucf - aligned_ds
