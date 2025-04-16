# Import inspect module
import inspect
from datetime import date
from graphlib import CycleError, TopologicalSorter
from typing import Any, Callable, Dict, List, Optional, Set, Union
from uuid import UUID

import pandas as pd
from pydantic import Field

from ..core._cash_flow import CashFlowModel
from ..core._enums import ExpenseSubcategoryEnum
from ..core._model import Model
from ..core._settings import GlobalSettings
from ..core._timeline import Timeline
from ._property import Property


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
    settings: GlobalSettings = Field(default_factory=GlobalSettings)
    analysis_start_date: date
    analysis_end_date: date
    
    # Cached results
    _cached_aggregated_flows: Optional[Dict[str, pd.Series]] = None
    _cached_cash_flow_dataframe: Optional[pd.DataFrame] = None
    _cached_occupancy_series: Optional[pd.Series] = None # Re-added cache

    # --- Private Helper: Iterative Computation ---

    def _compute_cash_flows_iterative(
        self, 
        all_models: List[CashFlowModel], 
        analysis_periods: pd.PeriodIndex,
        occupancy_series: pd.Series # Added occupancy series parameter
        ) -> Dict[UUID, Union[pd.Series, Dict[str, pd.Series]]]:
        """
        Internal helper: Compute cash flows using multi-pass iteration.

        This method serves as a fallback when `graphlib.TopologicalSorter` detects
        a cycle in the model dependencies based on `model_id` references. It iteratively
        attempts to compute models until no further progress can be made or a maximum
        number of passes is reached.

        Args:
            all_models: The list of all CashFlowModel instances to compute.
            analysis_periods: The PeriodIndex for the analysis timeline.
            occupancy_series: The pre-calculated occupancy series.

        Returns:
            A dictionary mapping model_id to its computed result (Series or Dict of Series).
            May contain fewer items than `all_models` if some models failed computation.
        """
        computed_results: Dict[UUID, Union[pd.Series, Dict[str, pd.Series]]] = {}
        remaining_models = {model.model_id: model for model in all_models}
        
        MAX_PASSES = len(all_models) + 1
        passes = 0
        progress_made_in_pass = True

        while remaining_models and passes < MAX_PASSES and progress_made_in_pass:
            passes += 1
            progress_made_in_pass = False
            models_computed_this_pass: List[UUID] = []
            lookup_errors_this_pass: Dict[UUID, str] = {}

            # Define lookup function (Handles UUID and property strings ONLY)
            def lookup_fn_iterative(key: Union[str, UUID]) -> Union[float, pd.Series, Dict, Any]:
                if isinstance(key, UUID):
                    if key in computed_results:
                        return computed_results[key]
                    else:
                        raise LookupError(f"Iterative: Dependency result for model ID {key} not yet computed.")
                elif isinstance(key, str):
                    if hasattr(self.property, key):
                        value = getattr(self.property, key)
                        if isinstance(value, (int, float, pd.Series, Dict, str, date)): 
                           return value
                        else:
                           raise TypeError(f"Iterative: Property attribute '{key}' has unsupported type {type(value)}.")
                    else:
                        raise LookupError(f"Iterative: Cannot resolve reference key '{key}' from property attributes.")
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
        return model.compute_cf(**kwargs)

    def _get_aggregated_flows(self) -> Dict[str, pd.Series]:
        """
        Internal method to compute or retrieve cached aggregated flows.

        Ensures that the main computation logic (`_compute_and_aggregate_flows`)
        is run only once per instance unless caches are explicitly cleared.
        Resets related caches (`_cached_cash_flow_dataframe`, `_cached_occupancy_series`)
        if recomputation is triggered.

        Returns:
            The dictionary of aggregated cash flow series (e.g., "Total Revenue").
        """
        if self._cached_aggregated_flows is None:
            # Reset related caches if recomputing flows
            self._cached_cash_flow_dataframe = None 
            self._cached_occupancy_series = None # Reset occupancy too if flows recomputed
            self._cached_aggregated_flows = self._compute_and_aggregate_flows()
        return self._cached_aggregated_flows
    
    def _compute_and_aggregate_flows(self) -> Dict[str, pd.Series]:
        """
        Core computation and aggregation engine.

        Orchestrates the calculation of all individual cash flows, handling dependencies
        and injecting context like occupancy. Aggregates results into standard lines.

        Steps:
        1. Create analysis timeline and calculate occupancy series.
        2. Collect all `CashFlowModel` instances.
        3. Define a `lookup_fn` capable of resolving `model.reference` attributes
           (UUIDs to other models' computed results, strings to property attributes).
        4. Attempt computation using `graphlib.TopologicalSorter` for single-pass efficiency.
           - Build dependency graph based on UUID references.
           - If successful (DAG), compute models in sorted order, injecting occupancy
             where needed via `_run_compute_cf`.
        5. If `TopologicalSorter` fails (cycle detected), fall back to the multi-pass
           iterative method (`_compute_cash_flows_iterative`), passing the occupancy series.
        6. Process the `computed_results` dictionary (from either TS or MPI path):
           - Handle single Series vs. Dict of Series outputs from models.
           - Map results/components to standard aggregate keys (e.g., "Total OpEx").
           - Align all series to the analysis timeline's PeriodIndex.
        7. Sum aligned series into the final `aggregated_flows` dictionary.

        Returns:
            A dictionary where keys are standard financial line items (str) and
            values are the corresponding aggregated pandas Series.
        """
        analysis_timeline = self._create_timeline()
        analysis_periods = analysis_timeline.period_index
        
        # Calculate occupancy series first
        occupancy_series = self._calculate_occupancy_series() 

        all_models = (
            self._collect_revenue_models() +
            self._collect_expense_models() +
            self._collect_other_cash_flow_models()
        )
        
        model_map = {model.model_id: model for model in all_models}
        computed_results: Dict[UUID, Union[pd.Series, Dict[str, pd.Series]]] = {}
        use_iterative_fallback = False
        
        # --- Define Lookup Function (Handles UUID and property strings ONLY) ---
        def lookup_fn(key: Union[str, UUID]) -> Union[float, pd.Series, Dict, Any]:
            if isinstance(key, UUID):
                if key in computed_results:
                    return computed_results[key]
                else:
                    raise LookupError(f"Dependency result for model ID {key} not available in this context.") 
            elif isinstance(key, str):
                if hasattr(self.property, key):
                    value = getattr(self.property, key)
                    if isinstance(value, (int, float, pd.Series, Dict, str, date)): 
                        return value
                    else:
                        raise TypeError(f"Property attribute '{key}' has unsupported type {type(value)}.")
                else:
                    raise LookupError(f"Cannot resolve reference key '{key}' from property attributes.")
            else:
                raise TypeError(f"Unsupported lookup key type: {type(key)}")

        # --- Attempt Topological Sort ---
        try:
            # 1. Build Dependency Graph
            graph: Dict[UUID, Set[UUID]] = {model.model_id: set() for model in all_models}
            for model_id, model in model_map.items():
                if isinstance(model.reference, UUID):
                    dependency_id = model.reference
                    if dependency_id in graph:
                        graph[model_id].add(dependency_id)
                    else:
                         print(f"Warning: Model '{model.name}' ({model_id}) references unknown model ID {dependency_id}. Ignoring dependency.")

            # 2. Perform Topological Sort
            ts = TopologicalSorter(graph)
            sorted_model_ids = list(ts.static_order())
            
            print("Info: Dependency graph is a DAG. Using single-pass computation.")

            # 3. Compute in Sorted Order - using helper for occupancy
            for model_id in sorted_model_ids:
                model = model_map[model_id]
                try:
                    # Use helper to call compute_cf with conditional occupancy
                    result = self._run_compute_cf(model, lookup_fn, occupancy_series) 
                    computed_results[model_id] = result
                except Exception as e:
                    print(f"Error computing model '{model.name}' ({model_id}) during sorted pass: {e}. Skipping model.")
                    if model_id in computed_results: del computed_results[model_id]

        except CycleError as e: 
            print(f"Warning: Circular dependency detected involving models: {e.args[1]}. Falling back to iterative computation.")
            use_iterative_fallback = True
        except Exception as graph_err:
             print(f"Error during graph processing: {graph_err}. Falling back to iterative computation.")
             use_iterative_fallback = True

        # --- Fallback to Iterative Method if Needed ---
        if use_iterative_fallback:
            print("Info: Using iterative multi-pass computation.")
            # Call iterative helper, passing occupancy series
            computed_results = self._compute_cash_flows_iterative(
                all_models, analysis_periods, occupancy_series 
            )

        # --- Process and Aggregate Results ---
        aggregate_keys = [
            "Total Revenue", "Total OpEx", "Total CapEx", 
            "Total TI Allowance", "Total Leasing Commission"
        ]
        aggregated_flows: Dict[str, pd.Series] = {
            key: pd.Series(0.0, index=analysis_periods) for key in aggregate_keys
        }
        for model_id, result in computed_results.items():
            original_model = model_map.get(model_id) 
            if not original_model: continue 
            results_to_process: Dict[str, pd.Series] = {}
            component_map: Dict[str, str] = {} 
            if isinstance(result, pd.Series):
                results_to_process = {"value": result}
                if original_model.category == "Revenue": component_map["value"] = "Total Revenue"
                elif isinstance(original_model.subcategory, ExpenseSubcategoryEnum):
                    if original_model.subcategory == ExpenseSubcategoryEnum.OPEX: component_map["value"] = "Total OpEx"
                    elif original_model.subcategory == ExpenseSubcategoryEnum.CAPEX: component_map["value"] = "Total CapEx"
            elif isinstance(result, dict):
                results_to_process = result
                component_map = { "base_rent": "Total Revenue", "recoveries": "Total Revenue", "ti_allowance": "Total TI Allowance", "leasing_commission": "Total Leasing Commission", }
            else: print(f"Warning: Unexpected type {type(result)} in final results for {original_model.name}. Skipping."); continue
            for component_name, series in results_to_process.items():
                target_aggregate_key = component_map.get(component_name)
                if target_aggregate_key is None: continue 
                if not isinstance(series, pd.Series): continue
                try:
                    if not isinstance(series.index, pd.PeriodIndex):
                         if isinstance(series.index, pd.DatetimeIndex): series.index = series.index.to_period(freq='M')
                         else: series.index = pd.PeriodIndex(series.index, freq='M')
                    aligned_series = series.reindex(analysis_periods, fill_value=0.0)
                except Exception as align_err: print(f"Warning: Could not align index for component '{component_name}' from {original_model.name}. Error: {align_err}. Skipping."); continue
                if target_aggregate_key in aggregated_flows: aggregated_flows[target_aggregate_key] = aggregated_flows[target_aggregate_key].add(aligned_series, fill_value=0.0)
                else: print(f"Warning: Target aggregation key '{target_aggregate_key}' not found. Skipping.")

        return aggregated_flows

    # --- Public Methods ---
    def create_cash_flow_dataframe(self) -> pd.DataFrame:
        """
        Generates or retrieves a cached DataFrame of the property's cash flows.

        Columns include standard aggregated lines (Total Revenue, Total OpEx, etc.)
        and calculated metrics (NOI, Unlevered Cash Flow). The index represents
        monthly periods over the analysis timeline.

        Returns:
            A pandas DataFrame summarizing the property's cash flows.
        """
        if self._cached_cash_flow_dataframe is None:
            flows = self._get_aggregated_flows()
            # Calculate derived metrics using .get for safety
            revenue = flows.get("Total Revenue", pd.Series(0.0, index=flows.get("Total Revenue", pd.Series()).index)) # Default to 0 series if key missing
            opex = flows.get("Total OpEx", pd.Series(0.0, index=revenue.index))
            capex = flows.get("Total CapEx", pd.Series(0.0, index=revenue.index))
            ti = flows.get("Total TI Allowance", pd.Series(0.0, index=revenue.index))
            lc = flows.get("Total Leasing Commission", pd.Series(0.0, index=revenue.index))
            
            noi = revenue - opex
            unlevered_cf = noi - capex - ti - lc
            
            # Define standard column order
            column_order = [
                "Total Revenue", "Total OpEx", "NOI", 
                "Total CapEx", "Total TI Allowance", "Total Leasing Commission", 
                "Unlevered Cash Flow"
            ]
            
            all_lines = {
                "Total Revenue": revenue, "Total OpEx": opex, "NOI": noi, 
                "Total CapEx": capex, "Total TI Allowance": ti, 
                "Total Leasing Commission": lc, "Unlevered Cash Flow": unlevered_cf 
            }
            
            # Create DataFrame with defined columns if they exist in all_lines
            cf_df = pd.DataFrame({k: all_lines[k] for k in column_order if k in all_lines}, index=revenue.index)
            cf_df.index.name = "Period"
            self._cached_cash_flow_dataframe = cf_df
            
        return self._cached_cash_flow_dataframe

    def net_operating_income(self) -> pd.Series:
        """Calculates or retrieves the Net Operating Income (NOI) series."""
        cf_df = self.create_cash_flow_dataframe()
        if "NOI" in cf_df.columns: return cf_df["NOI"]
        else: flows = self._get_aggregated_flows(); return flows.get("Total Revenue", 0) - flows.get("Total OpEx", 0)

    def cash_flow_from_operations(self) -> pd.Series:
        """
        Calculates or retrieves the Cash Flow From Operations series.
        (Currently defined as Unlevered Cash Flow).
        """
        cf_df = self.create_cash_flow_dataframe()
        if "Unlevered Cash Flow" in cf_df.columns: return cf_df["Unlevered Cash Flow"]
        else: raise NotImplementedError("Cannot calculate Cash Flow from Operations - UCF not available.")

    def unlevered_cash_flow(self) -> pd.Series:
        """Calculates or retrieves the Unlevered Cash Flow (UCF) series."""
        cf_df = self.create_cash_flow_dataframe()
        if "Unlevered Cash Flow" in cf_df.columns: return cf_df["Unlevered Cash Flow"]
        else: raise NotImplementedError("Cannot calculate Unlevered Cash Flow - required components missing.")

    def debt_service(self) -> pd.Series:
        """
        Calculates debt service (Placeholder: returns zeros).

        NOTE: This method currently returns a zero series. Full implementation requires
              integration with debt financing models.
              
        Returns:
            A pandas Series of zeros indexed by the analysis period.
        """
        analysis_timeline = self._create_timeline()
        return pd.Series(0.0, index=analysis_timeline.period_index, name="Debt Service")
    
    def levered_cash_flow(self) -> pd.Series:
        """Calculates Levered Cash Flow (Unlevered CF - Debt Service)."""
        ucf = self.unlevered_cash_flow()
        ds = self.debt_service() 
        aligned_ucf, aligned_ds = ucf.align(ds, join='left', fill_value=0.0)
        return aligned_ucf - aligned_ds
