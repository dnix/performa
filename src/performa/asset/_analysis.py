from datetime import date

# Direct import since Python >= 3.10 is required
from graphlib import CycleError, TopologicalSorter
from typing import Any, Dict, List, Optional, Set, Union
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
    Orchestration layer for a property's cash flow analysis.
    """

    property: Property
    settings: GlobalSettings = Field(default_factory=GlobalSettings)

    # timing
    analysis_start_date: date
    analysis_end_date: date

    # Cached results to avoid recomputation
    _cached_aggregated_flows: Optional[Dict[str, pd.Series]] = None
    _cached_cash_flow_dataframe: Optional[pd.DataFrame] = None

    def _create_timeline(self) -> Timeline:
        """Creates a unified timeline for all cash flows based on analysis dates."""
        if self.analysis_start_date >= self.analysis_end_date:
            raise ValueError("Analysis start date must be before end date")
            
        return Timeline.from_dates(
            start_date=self.analysis_start_date,
            end_date=self.analysis_end_date,
        )

    def _collect_revenue_models(self) -> List[CashFlowModel]:
        """Extracts all revenue models from the property's rent roll and misc income."""
        revenue_models: List[CashFlowModel] = []

        # 1. Get Lease models from RentRoll
        if self.property.rent_roll and self.property.rent_roll.leases:
            # Leases are already CashFlowModel instances
            revenue_models.extend(self.property.rent_roll.leases)

        # 2. Get MiscIncome models
        if self.property.miscellaneous_income and self.property.miscellaneous_income.income_items:
             # MiscIncome items are already CashFlowModel instances
            revenue_models.extend(self.property.miscellaneous_income.income_items)

        return revenue_models
    
    def _collect_expense_models(self) -> List[CashFlowModel]:
        """Extracts all expense models from the property."""
        expense_models: List[CashFlowModel] = []

        # 1. Get Operating Expense items
        if self.property.expenses and self.property.expenses.operating_expenses:
            op_ex_items = self.property.expenses.operating_expenses.expense_items
            if op_ex_items:
                 # OpExItem inherits from CashFlowModel
                expense_models.extend(op_ex_items)

        # 2. Get Capital Expense items
        if self.property.expenses and self.property.expenses.capital_expenses:
            cap_ex_items = self.property.expenses.capital_expenses.expense_items
            if cap_ex_items:
                 # CapExItem inherits from CashFlowModel
                expense_models.extend(cap_ex_items)
        
        return expense_models
    
    def _collect_other_cash_flow_models(self) -> List[CashFlowModel]:
        """Extracts any other cash flow models (capital, investment, etc.).
        
        Currently assumes analysis is purely property-level. Debt/Equity models
        are expected to be handled at a higher investment/project level or passed
        in explicitly if needed.
        """
        # Return empty list for now.
        return []
    
    def _compute_cash_flows_iterative(
        self, 
        all_models: List[CashFlowModel], 
        analysis_periods: pd.PeriodIndex
        ) -> Dict[UUID, Union[pd.Series, Dict[str, pd.Series]]]:
        """
        Compute cash flows using multi-pass iteration (handles cycles).
        Internal helper method. Used as fallback when cycles detected by TS.
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
                    result = model.compute_cf(lookup_fn=lookup_fn_iterative)
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

    def _compute_and_aggregate_flows(self) -> Dict[str, pd.Series]:
        """
        Compute all individual cash flows, process results, and aggregate
        into standard financial line items (Revenue, OpEx, CapEx, TI, LC).
        Uses TS or MPI for computation based on dependency structure.
        """
        analysis_timeline = self._create_timeline()
        analysis_periods = analysis_timeline.period_index

        all_models = (
            self._collect_revenue_models() +
            self._collect_expense_models() +
            self._collect_other_cash_flow_models()
        )
        
        model_map = {model.model_id: model for model in all_models}
        computed_results: Dict[UUID, Union[pd.Series, Dict[str, pd.Series]]] = {}
        use_iterative_fallback = False
        
        # --- Define Lookup Function ---
        def lookup_fn(key: Union[str, UUID]) -> Union[float, pd.Series, Dict, Any]:
            if isinstance(key, UUID):
                if key in computed_results:
                    return computed_results[key]
                else:
                    raise LookupError(f"Dependency result for model ID {key} not available.")
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

            # 3. Compute in Sorted Order (Single Pass)
            for model_id in sorted_model_ids:
                model = model_map[model_id]
                try:
                    result = model.compute_cf(lookup_fn=lookup_fn)
                    computed_results[model_id] = result
                except Exception as e:
                    print(f"Error computing model '{model.name}' ({model_id}) during sorted pass: {e}. Skipping model.")
                    if model_id in computed_results: del computed_results[model_id]

        except CycleError as e: 
            print(f"Warning: Circular dependency detected involving models: {e.args[1]}. Falling back to iterative computation.")
            use_iterative_fallback = True
        except Exception as graph_err: # Catch other potential graph errors
             print(f"Error during graph processing: {graph_err}. Falling back to iterative computation.")
             use_iterative_fallback = True

        # --- Fallback to Iterative Method if Needed ---
        if use_iterative_fallback:
            print("Info: Using iterative multi-pass computation.")
            computed_results = self._compute_cash_flows_iterative(all_models, analysis_periods)

        # --- Process and Aggregate Results into Standard Lines ---
        # Initialize aggregate series with zeros
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
            component_map: Dict[str, str] = {} # Maps component name to aggregation key

            # --- Determine how to handle the result based on model type/output ---
            if isinstance(result, pd.Series):
                 # Single series result (e.g., from MiscIncome, OpExItem, CapExItem)
                results_to_process = {"value": result}
                if original_model.category == "Revenue":
                     component_map["value"] = "Total Revenue"
                # Use subcategory enum for reliable check
                elif isinstance(original_model.subcategory, ExpenseSubcategoryEnum):
                    if original_model.subcategory == ExpenseSubcategoryEnum.OPEX:
                        component_map["value"] = "Total OpEx"
                    elif original_model.subcategory == ExpenseSubcategoryEnum.CAPEX:
                        component_map["value"] = "Total CapEx"
                # Add handling for other categories/subcategories if needed
                
            elif isinstance(result, dict):
                # Dictionary result (typically from Lease)
                results_to_process = result
                # Map lease components to standard aggregate lines
                component_map = {
                    "base_rent": "Total Revenue",
                    "recoveries": "Total Revenue",
                    "revenue": None, # Don't aggregate the pre-summed 'revenue' component
                    "ti_allowance": "Total TI Allowance",
                    "leasing_commission": "Total Leasing Commission",
                    "expenses": None, # Don't aggregate the pre-summed 'expenses' component
                    "net": None, # Don't aggregate the pre-summed 'net' component
                }
            else:
                print(f"Warning: Unexpected type {type(result)} in final results for {original_model.name}. Skipping.")
                continue

            # --- Process and Add to Aggregates ---
            for component_name, series in results_to_process.items():
                target_aggregate_key = component_map.get(component_name)
                
                # Skip if component is not meant for aggregation (e.g., 'revenue', 'net' from Lease)
                if target_aggregate_key is None:
                    continue 
                    
                if not isinstance(series, pd.Series):
                    print(f"Warning: Expected Series for component '{component_name}' from {original_model.name}. Skipping.")
                    continue
                
                try:
                    # Align index
                    if not isinstance(series.index, pd.PeriodIndex):
                         if isinstance(series.index, pd.DatetimeIndex):
                             series.index = series.index.to_period(freq='M')
                         else:
                             series.index = pd.PeriodIndex(series.index, freq='M')
                             
                    aligned_series = series.reindex(analysis_periods, fill_value=0.0)
                except Exception as align_err:
                     print(f"Warning: Could not align index for component '{component_name}' from {original_model.name}. Error: {align_err}. Skipping.")
                     continue
                
                # Add to the target aggregate series
                if target_aggregate_key in aggregated_flows:
                    aggregated_flows[target_aggregate_key] = aggregated_flows[target_aggregate_key].add(aligned_series, fill_value=0.0)
                else:
                     print(f"Warning: Target aggregation key '{target_aggregate_key}' not found for component '{component_name}' from {original_model.name}. Skipping.")

        return aggregated_flows

    def create_cash_flow_dataframe(self) -> pd.DataFrame:
        """
        Create the master cash flow dataframe with standard financial line items.
        
        Returns:
            A pandas DataFrame indexed by monthly periods, with columns for
            Total Revenue, Total OpEx, Total CapEx, Total TI Allowance, 
            Total Leasing Commission, NOI, and Unlevered Cash Flow.
        """
        if self._cached_cash_flow_dataframe is None:
            flows = self._compute_and_aggregate_flows()
            
            # Calculate derived metrics
            noi = flows.get("Total Revenue", 0) - flows.get("Total OpEx", 0)
            # Unlevered CF = NOI - CapEx - TI - LC 
            # Note: TI/LC are typically treated as negative cash flows here
            unlevered_cf = noi - flows.get("Total CapEx", 0) \
                           - flows.get("Total TI Allowance", 0) \
                           - flows.get("Total Leasing Commission", 0)
            
            # Combine base flows and derived metrics
            all_lines = {
                "Total Revenue": flows.get("Total Revenue"),
                "Total OpEx": flows.get("Total OpEx"),
                "NOI": noi, # Add NOI
                "Total CapEx": flows.get("Total CapEx"),
                "Total TI Allowance": flows.get("Total TI Allowance"),
                "Total Leasing Commission": flows.get("Total Leasing Commission"),
                "Unlevered Cash Flow": unlevered_cf # Add Unlevered CF
            }
            
            # Filter out any potential None values if a category had zero items
            valid_lines = {k: v for k, v in all_lines.items() if isinstance(v, pd.Series)}

            # Create DataFrame
            cf_df = pd.DataFrame(valid_lines)
            cf_df.index.name = "Period"
            self._cached_cash_flow_dataframe = cf_df
            
        return self._cached_cash_flow_dataframe
    
    def net_operating_income(self) -> pd.Series:
        """Calculate net operating income series (Total Revenue - Total OpEx)."""
        # Retrieve from the cached DataFrame if available, otherwise calculate
        cf_df = self.create_cash_flow_dataframe()
        if "NOI" in cf_df.columns:
             return cf_df["NOI"]
        else:
             # Should not happen if create_cash_flow_dataframe works correctly
             flows = self._compute_and_aggregate_flows()
             return flows.get("Total Revenue", 0) - flows.get("Total OpEx", 0)

    def cash_flow_from_operations(self) -> pd.Series:
        """Calculate cash flow from operations."""
        # Often defined similarly to Unlevered Cash Flow, but definitions can vary.
        # Using Unlevered CF definition for now.
        # NOI - CapEx - TI - LC
        cf_df = self.create_cash_flow_dataframe()
        if "Unlevered Cash Flow" in cf_df.columns:
            return cf_df["Unlevered Cash Flow"]
        else:
             raise NotImplementedError("Cannot calculate Cash Flow from Operations - Unlevered CF not available.")

    def unlevered_cash_flow(self) -> pd.Series:
        """Calculate unlevered cash flow (NOI - CapEx - TI - LC)."""
        cf_df = self.create_cash_flow_dataframe()
        if "Unlevered Cash Flow" in cf_df.columns:
            return cf_df["Unlevered Cash Flow"]
        else:
             raise NotImplementedError("Cannot calculate Unlevered Cash Flow - required components missing.")
    
    def debt_service(self) -> pd.Series:
        """Calculate debt service."""
        # Needs integration of debt models or external input
        # For now, return zeros aligned to timeline
        analysis_timeline = self._create_timeline()
        return pd.Series(0.0, index=analysis_timeline.period_index, name="Debt Service")
        # raise NotImplementedError("debt_service is not yet implemented") 
    
    def levered_cash_flow(self) -> pd.Series:
        """Calculate levered cash flow (Unlevered CF - Debt Service)."""
        ucf = self.unlevered_cash_flow()
        ds = self.debt_service() # Assumes debt_service returns zeros for now
        # Ensure alignment before subtraction
        aligned_ucf, aligned_ds = ucf.align(ds, join='left', fill_value=0.0)
        return aligned_ucf - aligned_ds

    def _get_aggregated_flows(self) -> Dict[str, pd.Series]:
        """
        Internal method to compute or retrieve cached aggregated flows.
        """
        if self._cached_aggregated_flows is None:
            self._cached_aggregated_flows = self._compute_and_aggregate_flows()
        return self._cached_aggregated_flows
