# Import inspect module
import inspect
from datetime import date
from graphlib import CycleError, TopologicalSorter
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
from uuid import UUID

import pandas as pd
from pydantic import Field

from ..core._cash_flow import CashFlowModel
from ..core._enums import AggregateLineKey, ExpenseSubcategoryEnum
from ..core._model import Model
from ..core._settings import GlobalSettings
from ..core._timeline import Timeline
from ._property import Property

# TODO: Add comprehensive unit and integration tests for CashFlowAnalysis logic.

class CashFlowAnalysis(Model):
    """
    Orchestrates the calculation and aggregation of property-level cash flows.

    This class computes cash flows over a specified analysis period by:
    1. Collecting all relevant `CashFlowModel` instances (Leases, Expenses, etc.)
       from the provided `Property` object.
    2. Calculating a dynamic occupancy series for the analysis period.
    3. Computing cash flows for each model, resolving dependencies:
        - Uses `lookup_fn` to resolve `reference` attributes (UUIDs for inter-model
          dependencies, strings for `Property` attributes).
        - Injects the calculated occupancy series as an argument to models that require it
          (e.g., `OpExItem`, `MiscIncome`) via signature inspection.
        - Employs `graphlib.TopologicalSorter` for efficient single-pass computation if
          model dependencies form a Directed Acyclic Graph (DAG).
        - Falls back to a multi-pass iterative calculation if cycles are detected
          (e.g., due to `model_id` reference cycles), issuing a warning.
    4. Aggregating the computed cash flows into standard financial line items
       (Revenue, OpEx, CapEx, TI Allowance, Leasing Commission).
    5. Providing access to these aggregated results via a DataFrame and specific
       metric calculation methods (NOI, Unlevered Cash Flow, etc.).

    Attributes:
        property: The input `Property` object containing asset details and base models.
        settings: Global settings potentially influencing calculations.
        analysis_start_date: The start date for the cash flow analysis period.
        analysis_end_date: The end date (inclusive) for the cash flow analysis period.
    """
    property: Property
    # TODO: Integrate self.settings to allow configuration of analysis behavior.
    settings: GlobalSettings = Field(default_factory=GlobalSettings)
    analysis_start_date: date
    analysis_end_date: date
    
    # --- Cached Results ---
    # NOTE: Basic caching implemented. Assumes inputs are immutable after instantiation.
    # TODO: Implement more robust cache invalidation if inputs can change.
    _cached_detailed_flows: Optional[List[Tuple[Dict, pd.Series]]] = None
    _cached_aggregated_flows: Optional[Dict[AggregateLineKey, pd.Series]] = None
    _cached_cash_flow_dataframe: Optional[pd.DataFrame] = None
    _cached_detailed_cash_flow_dataframe: Optional[pd.DataFrame] = None
    _cached_occupancy_series: Optional[pd.Series] = None

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
        computed_results: Dict[UUID, Union[pd.Series, Dict[str, pd.Series]]] = {}
        remaining_models = {model.model_id: model for model in all_models}
        model_map = {model.model_id: model for model in all_models} # Keep original map
        analysis_periods = occupancy_series.index # Use occupancy index as timeline ref
        current_aggregates: Dict[str, pd.Series] = {} # Store aggregates calculated each pass
        
        MAX_PASSES = len(all_models) + 1
        passes = 0
        progress_made_in_pass = True

        while remaining_models and passes < MAX_PASSES and progress_made_in_pass:
            passes += 1
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
                        # Check aggregates from the *previous* pass (keyed by Enum member)
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
                try:
                    # Use helper to call compute_cf with conditional occupancy
                    result = self._run_compute_cf(model, lookup_fn_iterative, occupancy_series) 
                    computed_results[model_id] = result
                    models_computed_this_pass.append(model_id)
                    progress_made_in_pass = True
                except LookupError as le:
                    lookup_errors_this_pass[model_id] = str(le)
                except NotImplementedError:
                    print(f"Warning (Iterative): compute_cf not implemented for model '{model.name}' ({model.model_id}). Removing.")
                    models_computed_this_pass.append(model_id) 
                except Exception as e:
                    print(f"Error (Iterative): computing '{model.name}' ({model.model_id}): {e}. Removing.")
                    models_computed_this_pass.append(model_id) 

            for computed_id in models_computed_this_pass:
                remaining_models.pop(computed_id, None)

            # --- Recalculate Aggregates for the NEXT pass ---
            # Process current computed results into detailed flow format for aggregation
            detailed_flows_this_pass: List[Tuple[Dict, pd.Series]] = []
            for res_model_id, result in computed_results.items():
                 original_model = model_map.get(res_model_id) 
                 if not original_model: continue 
                 results_to_process: Dict[str, pd.Series] = {}
                 if isinstance(result, pd.Series): results_to_process = {"value": result}
                 elif isinstance(result, dict): results_to_process = result
                 else: continue # Skip unexpected types

                 for component_name, series in results_to_process.items():
                     if not isinstance(series, pd.Series): continue
                     try:
                         # Align index - crucial for aggregation
                         if not isinstance(series.index, pd.PeriodIndex):
                              if isinstance(series.index, pd.DatetimeIndex): series.index = series.index.to_period(freq='M')
                              else: series.index = pd.PeriodIndex(series.index, freq='M')
                         # Use the main analysis_periods derived earlier
                         aligned_series = series.reindex(analysis_periods, fill_value=0.0) 
                     except Exception: 
                         # If alignment fails, we can't reliably aggregate this component in this pass
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

        if remaining_models:
            print(f"Warning (Iterative): Could not compute all models after {passes} passes.")
            for model_id, reason in lookup_errors_this_pass.items():
                 if model_id in remaining_models:
                     model_name = remaining_models[model_id].name
                     print(f"  - Iterative: Model '{model_name}' ({model_id}) failed. Last error: {reason}")
        
        return computed_results

    # --- Private Methods ---
    def _create_timeline(self) -> Timeline:
        """Creates a unified monthly timeline for the analysis period."""
        if self.analysis_start_date >= self.analysis_end_date:
            raise ValueError("Analysis start date must be before end date")
        return Timeline.from_dates(
            start_date=self.analysis_start_date,
            end_date=self.analysis_end_date,
            # Default monthly frequency assumed
        )
        
    # Re-added occupancy calculation method
    def _calculate_occupancy_series(self) -> pd.Series:
        """
        Calculates the physical occupancy rate series over the analysis timeline.

        This implementation derives occupancy solely based on the active periods of
        leases defined in the `property.rent_roll`. It sums the area of leases
        active in each period and divides by the property's net rentable area.

        NOTE: This is a simplified calculation. It does not yet account for
              lease rollover projections, absorption of vacant space, or different
              occupancy types (e.g., economic vs. physical). Caches the result.
              
        Returns:
            A pandas Series indexed by the analysis period, containing the
            calculated occupancy rate (0.0 to 1.0) for each period.
        """
        if self._cached_occupancy_series is None:
            analysis_periods = self._create_timeline().period_index
            occupied_area_series = pd.Series(0.0, index=analysis_periods)

            if self.property.rent_roll and self.property.rent_roll.leases:
                for lease in self.property.rent_roll.leases:
                    lease_periods = lease.timeline.period_index
                    # Ensure lease periods are monthly for comparison
                    if lease_periods.freqstr != 'M':
                         # Attempt conversion or handle error if needed
                         try:
                             lease_periods = lease_periods.asfreq('M', how='start') # Or appropriate conversion
                         except ValueError:
                             print(f"Warning: Lease '{lease.name}' timeline frequency ({lease_periods.freqstr}) not monthly. Skipping for occupancy calc.")
                             continue

                    active_periods = analysis_periods.intersection(lease_periods)
                    if not active_periods.empty:
                         occupied_area_series.loc[active_periods] += lease.area
            
            total_nra = self.property.net_rentable_area
            if total_nra > 0:
                 occupancy_series = (occupied_area_series / total_nra).clip(0, 1)
            else:
                 occupancy_series = pd.Series(0.0, index=analysis_periods)
                 
            occupancy_series.name = "Occupancy Rate"
            self._cached_occupancy_series = occupancy_series

        return self._cached_occupancy_series

    def _collect_revenue_models(self) -> List[CashFlowModel]:
        """Extracts all revenue models from the property."""
        revenue_models: List[CashFlowModel] = []
        if self.property.rent_roll and self.property.rent_roll.leases:
            revenue_models.extend(self.property.rent_roll.leases)
        if self.property.miscellaneous_income and self.property.miscellaneous_income.income_items:
            revenue_models.extend(self.property.miscellaneous_income.income_items)
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
        return expense_models

    def _collect_other_cash_flow_models(self) -> List[CashFlowModel]:
        """Extracts any other cash flow models."""
        # TODO: Implement collection logic if/when debt or other non-property models are added.
        return []

    # Re-added helper to inject occupancy via arguments
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

        Args:
            model: The CashFlowModel instance to compute.
            lookup_fn: The function to resolve references (UUIDs, property strings).
            occupancy_series: The pre-calculated occupancy series for the analysis period.

        Returns:
            The result from `model.compute_cf` (either a Series or Dict of Series).
        """
        sig = inspect.signature(model.compute_cf)
        params = sig.parameters
        kwargs = {"lookup_fn": lookup_fn}
        if "occupancy_rate" in params or "occupancy_series" in params:
            kwargs["occupancy_rate"] = occupancy_series
        # TODO: Consider passing other contextual series if needed (e.g., calculated EGI?)
        return model.compute_cf(**kwargs)

    def _compute_detailed_flows(self) -> List[Tuple[Dict, pd.Series]]:
        """
        Computes all individual cash flows, handling dependencies and context injection.
        Returns a detailed list of results, each tagged with metadata.
        """
        if self._cached_detailed_flows is None:
            analysis_timeline = self._create_timeline()
            analysis_periods = analysis_timeline.period_index
            occupancy_series = self._calculate_occupancy_series() 
            all_models = ( self._collect_revenue_models() + self._collect_expense_models() + self._collect_other_cash_flow_models() )
            model_map = {model.model_id: model for model in all_models}
            computed_results: Dict[UUID, Union[pd.Series, Dict[str, pd.Series]]] = {}
            use_iterative_fallback = False
            
            # --- Define Lookup Function ---
            def lookup_fn(key: Union[str, UUID]) -> Union[float, pd.Series, Dict, Any]:
                # This lookup is used in the single-pass (DAG) computation.
                # It should NOT resolve aggregate keys, as those imply cycles.
                if isinstance(key, UUID):
                    # Look up previously computed results within this DAG pass
                    if key in computed_results: return computed_results[key]
                    # If not found, it's an error in the DAG structure or definition
                    else: raise LookupError(f"(DAG Path) Dependency result for model ID {key} not available.") 
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
                else: raise TypeError(f"(DAG Path) Unsupported lookup key type: {type(key)}")

            # --- Attempt Topological Sort ---
            try:
                graph: Dict[UUID, Set[UUID]] = {m_id: set() for m_id in model_map.keys()}
                for model_id, model in model_map.items():
                    if isinstance(model.reference, UUID):
                        dependency_id = model.reference
                        if dependency_id in graph: graph[model_id].add(dependency_id)
                        else: print(f"Warning: Model '{model.name}' ({model_id}) refs unknown ID {dependency_id}. Ignored.")
                ts = TopologicalSorter(graph); sorted_model_ids = list(ts.static_order())
                print("Info: Dependency graph is a DAG. Using single-pass computation.")
                for model_id in sorted_model_ids:
                    model = model_map[model_id]
                    try: result = self._run_compute_cf(model, lookup_fn, occupancy_series); computed_results[model_id] = result
                    except Exception as e: print(f"Error computing '{model.name}' ({model_id}) in TS pass: {e}. Skipped."); computed_results.pop(model_id, None)
            # --- Fallback to Iterative on Cycle or Graph Error ---
            except CycleError as e: print(f"Warning: Cycle detected: {e.args[1]}. Falling back to iteration."); use_iterative_fallback = True
            except Exception as graph_err: print(f"Error during graph processing: {graph_err}. Falling back to iteration."); use_iterative_fallback = True
            if use_iterative_fallback:
                print("Info: Using iterative multi-pass computation.")
                computed_results = self._compute_cash_flows_iterative( all_models, occupancy_series )

            # --- Process computed results into the detailed list ---
            processed_flows: List[Tuple[Dict, pd.Series]] = []
            for model_id, result in computed_results.items():
                original_model = model_map.get(model_id) 
                if not original_model: continue 
                results_to_process: Dict[str, pd.Series] = {}
                if isinstance(result, pd.Series): results_to_process = {"value": result}
                elif isinstance(result, dict): results_to_process = result
                else: print(f"Warning: Unexpected type {type(result)} for {original_model.name}. Skipped."); continue

                for component_name, series in results_to_process.items():
                    if not isinstance(series, pd.Series): continue
                    try:
                        # Align index
                        if not isinstance(series.index, pd.PeriodIndex):
                             if isinstance(series.index, pd.DatetimeIndex): series.index = series.index.to_period(freq='M')
                             else: series.index = pd.PeriodIndex(series.index, freq='M')
                        aligned_series = series.reindex(analysis_periods, fill_value=0.0)
                    except Exception as align_err: print(f"Warning: Align failed for {component_name} from {original_model.name}. Error: {align_err}. Skipped."); continue
                    
                    # Create metadata dictionary for this specific series
                    metadata = {
                        "model_id": str(model_id), # Store UUID as string for potential non-python use
                        "name": original_model.name,
                        "category": original_model.category,
                        "subcategory": str(original_model.subcategory), # Ensure string
                        "component": component_name,
                    }
                    processed_flows.append((metadata, aligned_series))
            
            self._cached_detailed_flows = processed_flows # Cache the result
        
        return self._cached_detailed_flows

    def _aggregate_detailed_flows(self, detailed_flows: List[Tuple[Dict, pd.Series]]) -> Dict[AggregateLineKey, pd.Series]:
        """Aggregates detailed flows into standard financial line items using AggregateLineKey."""
        # TODO: Incorporate GENERAL_VACANCY_LOSS and RENTAL_ABATEMENT when implemented
        # TODO: Allow for more flexible aggregation rules or custom groupings?
        analysis_periods = self._create_timeline().period_index # Get timeline for initialization
        
        # Initialize all keys from the enum with zero series
        aggregated_flows: Dict[AggregateLineKey, pd.Series] = {
            key: pd.Series(0.0, index=analysis_periods, name=key.value) 
            for key in AggregateLineKey
        }

        # --- Pass 1: Sum detailed flows into RAW intermediate keys --- 
        for metadata, series in detailed_flows:
            category = metadata["category"]
            subcategory = metadata["subcategory"] # Already stringified
            component = metadata["component"]
            target_aggregate_key: Optional[AggregateLineKey] = None

            # Map detailed flows to the appropriate RAW aggregate key
            if category == "Revenue":
                if component in ("base_rent", "value"): # 'value' for MiscIncome? Needs review.
                    # TODO: Distinguish Base Rent (for PGR) and Misc Income?
                    # For now, lump into Raw Revenue. PGR/Misc separation needed later.
                    target_aggregate_key = AggregateLineKey._RAW_TOTAL_REVENUE
                elif component == "recoveries":
                    target_aggregate_key = AggregateLineKey._RAW_TOTAL_RECOVERIES
                # TODO: Handle RENTAL_ABATEMENT component if added to Lease output

            elif category == "Expense":
                 if subcategory == str(ExpenseSubcategoryEnum.OPEX) and component == "value":
                     target_aggregate_key = AggregateLineKey._RAW_TOTAL_OPEX
                 elif subcategory == str(ExpenseSubcategoryEnum.CAPEX) and component == "value":
                     target_aggregate_key = AggregateLineKey._RAW_TOTAL_CAPEX
                 # Check specific components from Lease dictionary output (if applicable)
                 elif component == "ti_allowance":
                     target_aggregate_key = AggregateLineKey._RAW_TOTAL_TI
                 elif component == "leasing_commission":
                     target_aggregate_key = AggregateLineKey._RAW_TOTAL_LC
            
            # Add to the target aggregate series if found
            if target_aggregate_key is not None:
                 # Ensure series index matches (should already be aligned)
                 safe_series = series.reindex(analysis_periods, fill_value=0.0)
                 aggregated_flows[target_aggregate_key] = aggregated_flows[target_aggregate_key].add(safe_series, fill_value=0.0)
            # else: # Optional: Warn if a computed flow wasn't mapped to an aggregate
            #     print(f"Debug: Flow {metadata['name']}/{component} not mapped to RAW aggregate.")

        # --- Pass 2: Calculate standard lines from RAW aggregates and assumptions --- 
        # Note: Assumes Vacancy/Abatement are zero for now.
        # These calculations follow the standard real estate waterfall.
        
        # Copy raw sums to their final destinations if they represent the total
        aggregated_flows[AggregateLineKey.TOTAL_OPERATING_EXPENSES] = aggregated_flows[AggregateLineKey._RAW_TOTAL_OPEX]
        aggregated_flows[AggregateLineKey.TOTAL_CAPITAL_EXPENDITURES] = aggregated_flows[AggregateLineKey._RAW_TOTAL_CAPEX]
        aggregated_flows[AggregateLineKey.TOTAL_TENANT_IMPROVEMENTS] = aggregated_flows[AggregateLineKey._RAW_TOTAL_TI]
        aggregated_flows[AggregateLineKey.TOTAL_LEASING_COMMISSIONS] = aggregated_flows[AggregateLineKey._RAW_TOTAL_LC]
        aggregated_flows[AggregateLineKey.EXPENSE_REIMBURSEMENTS] = aggregated_flows[AggregateLineKey._RAW_TOTAL_RECOVERIES]
        # TODO: Separate Misc Income from Raw Revenue when detailed flows allow
        aggregated_flows[AggregateLineKey.MISCELLANEOUS_INCOME] = pd.Series(0.0, index=analysis_periods) # Placeholder
        aggregated_flows[AggregateLineKey.POTENTIAL_GROSS_REVENUE] = aggregated_flows[AggregateLineKey._RAW_TOTAL_REVENUE] # Placeholder - Assumes Raw = PGR

        # Placeholder for Vacancy and Abatement (needs proper calculation model)
        aggregated_flows[AggregateLineKey.GENERAL_VACANCY_LOSS] = pd.Series(0.0, index=analysis_periods) # Placeholder
        aggregated_flows[AggregateLineKey.RENTAL_ABATEMENT] = pd.Series(0.0, index=analysis_periods) # Placeholder

        # Calculate Effective Gross Revenue (EGR)
        aggregated_flows[AggregateLineKey.EFFECTIVE_GROSS_REVENUE] = (
            aggregated_flows[AggregateLineKey.POTENTIAL_GROSS_REVENUE]
            + aggregated_flows[AggregateLineKey.MISCELLANEOUS_INCOME]
            - aggregated_flows[AggregateLineKey.RENTAL_ABATEMENT] 
            # Note: Vacancy is subtracted *after* EGR to get Total EGI
        )

        # Calculate Total Effective Gross Income (Total EGI)
        aggregated_flows[AggregateLineKey.TOTAL_EFFECTIVE_GROSS_INCOME] = (
            aggregated_flows[AggregateLineKey.EFFECTIVE_GROSS_REVENUE]
            - aggregated_flows[AggregateLineKey.GENERAL_VACANCY_LOSS]
            + aggregated_flows[AggregateLineKey.EXPENSE_REIMBURSEMENTS]
        )

        # Calculate Net Operating Income (NOI)
        aggregated_flows[AggregateLineKey.NET_OPERATING_INCOME] = (
            aggregated_flows[AggregateLineKey.TOTAL_EFFECTIVE_GROSS_INCOME]
            - aggregated_flows[AggregateLineKey.TOTAL_OPERATING_EXPENSES]
        )

        # Calculate Unlevered Cash Flow (UCF)
        aggregated_flows[AggregateLineKey.UNLEVERED_CASH_FLOW] = (
            aggregated_flows[AggregateLineKey.NET_OPERATING_INCOME]
            - aggregated_flows[AggregateLineKey.TOTAL_TENANT_IMPROVEMENTS]
            - aggregated_flows[AggregateLineKey.TOTAL_LEASING_COMMISSIONS]
            - aggregated_flows[AggregateLineKey.TOTAL_CAPITAL_EXPENDITURES]
        )

        # Placeholder for Debt Service (Needs Debt Model Integration)
        aggregated_flows[AggregateLineKey.TOTAL_DEBT_SERVICE] = pd.Series(0.0, index=analysis_periods) # Placeholder

        # Calculate Levered Cash Flow (LCF)
        aggregated_flows[AggregateLineKey.LEVERED_CASH_FLOW] = (
            aggregated_flows[AggregateLineKey.UNLEVERED_CASH_FLOW]
            - aggregated_flows[AggregateLineKey.TOTAL_DEBT_SERVICE]
        )
        
        # Optional: Could remove internal _RAW keys before returning if desired
        # final_aggregates = {k: v for k, v in aggregated_flows.items() if not AggregateLineKey.is_internal_key(k)}
        # return final_aggregates

        return aggregated_flows # Return the full dict including RAW keys for now

    def _get_aggregated_flows(self) -> Dict[AggregateLineKey, pd.Series]:
        """Computes/retrieves detailed flows, then computes/retrieves aggregated flows using Enum keys."""
        # Ensure detailed flows are computed and cached
        # This will run _compute_detailed_flows which uses TS or MPI. 
        # The MPI internally calculates aggregates for lookups, but the final 
        # result here depends on the *final* detailed flows.
        detailed_flows = self._compute_detailed_flows() 
        
        # Compute/cache aggregated flows from the *final* detailed flows
        if self._cached_aggregated_flows is None:
            # This now returns Dict[AggregateLineKey, pd.Series]
            self._cached_aggregated_flows = self._aggregate_detailed_flows(detailed_flows)
            
        return self._cached_aggregated_flows

    # --- Public Methods ---
    def create_detailed_cash_flow_dataframe(self) -> pd.DataFrame:
        """
        Generates or retrieves a cached DataFrame of granular cash flows.

        The DataFrame's columns form a MultiIndex based on the metadata
        (Category, Subcategory, Name, Component) associated with each
        individual computed cash flow series. The index represents
        monthly periods over the analysis timeline.

        Returns:
            A detailed pandas DataFrame suitable for in-depth analysis and auditing.
        """
        # TODO: Consider performance for very large numbers of detailed flows.
        if self._cached_detailed_cash_flow_dataframe is None:
            detailed_flows = self._compute_detailed_flows()
            
            if not detailed_flows: # Handle case with no results
                return pd.DataFrame(index=self._create_timeline().period_index)

            # Prepare data for DataFrame construction
            data_dict = {}
            index = detailed_flows[0][1].index # Use index from first series
            tuples = []
            
            for metadata, series in detailed_flows:
                 # Create tuple for MultiIndex
                 col_tuple = (
                     metadata['category'], 
                     metadata['subcategory'], 
                     metadata['name'], 
                     metadata['component']
                 )
                 tuples.append(col_tuple)
                 # Ensure series aligns with the common index (should be guaranteed by _compute_detailed_flows)
                 data_dict[col_tuple] = series.reindex(index, fill_value=0.0)

            multi_index = pd.MultiIndex.from_tuples(tuples, names=['Category', 'Subcategory', 'Name', 'Component'])
            
            df = pd.DataFrame(data_dict, index=index)
            df.columns = multi_index
            df.index.name = "Period"
            
            # Sort columns for consistent presentation (optional but nice)
            df = df.sort_index(axis=1) 
            
            self._cached_detailed_cash_flow_dataframe = df

        return self._cached_detailed_cash_flow_dataframe

    def create_cash_flow_dataframe(self) -> pd.DataFrame:
        """
        Generates or retrieves a cached DataFrame of the property's cash flows.

        Columns include standard aggregated lines (Total Revenue, Total OpEx, etc.)
        and calculated metrics (NOI, Unlevered Cash Flow), keyed by AggregateLineKey values.
        The index represents monthly periods over the analysis timeline.

        Returns:
            A pandas DataFrame summarizing the property's cash flows.
        """
        if self._cached_cash_flow_dataframe is None:
            # _get_aggregated_flows now returns Dict[AggregateLineKey, pd.Series]
            flows: Dict[AggregateLineKey, pd.Series] = self._get_aggregated_flows()
            
            # Define standard column order using Enum values for DataFrame columns
            # Use AggregateLineKey.get_display_keys() potentially?
            # For now, be explicit with the keys we want in the summary.
            column_order = [
                AggregateLineKey.POTENTIAL_GROSS_REVENUE, 
                AggregateLineKey.RENTAL_ABATEMENT,
                AggregateLineKey.MISCELLANEOUS_INCOME,
                AggregateLineKey.EFFECTIVE_GROSS_REVENUE,
                AggregateLineKey.GENERAL_VACANCY_LOSS, 
                AggregateLineKey.EXPENSE_REIMBURSEMENTS, 
                AggregateLineKey.TOTAL_EFFECTIVE_GROSS_INCOME, 
                AggregateLineKey.TOTAL_OPERATING_EXPENSES, 
                AggregateLineKey.NET_OPERATING_INCOME, 
                AggregateLineKey.TOTAL_TENANT_IMPROVEMENTS, 
                AggregateLineKey.TOTAL_LEASING_COMMISSIONS, 
                AggregateLineKey.TOTAL_CAPITAL_EXPENDITURES, 
                AggregateLineKey.UNLEVERED_CASH_FLOW,
                AggregateLineKey.TOTAL_DEBT_SERVICE,
                AggregateLineKey.LEVERED_CASH_FLOW,
            ]
            
            # Create DataFrame using Enum values as column headers
            # Ensure all keys exist in the flows dict, default to zero series if not
            df_data = {}
            ref_index = self._create_timeline().period_index # Use a reference index
            for key in column_order:
                df_data[key.value] = flows.get(key, pd.Series(0.0, index=ref_index, name=key.value))
            
            cf_df = pd.DataFrame(df_data, index=ref_index)
            # Order columns as defined above
            cf_df = cf_df[[key.value for key in column_order]]
            cf_df.index.name = "Period"
            
            self._cached_cash_flow_dataframe = cf_df
            
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
