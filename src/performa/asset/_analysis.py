from __future__ import annotations

import inspect
import logging
from datetime import date, timedelta
from graphlib import CycleError, TopologicalSorter
from typing import (
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
from dateutil.relativedelta import relativedelta
from pydantic import Field

from ..core._cash_flow import CashFlowModel
from ..core._enums import (
    AggregateLineKey,
    ExpenseSubcategoryEnum,
    FrequencyEnum,
    RevenueSubcategoryEnum,
    UnitOfMeasureEnum,
    VacancyLossMethodEnum,
)
from ..core._model import Model
from ..core._settings import GlobalSettings
from ..core._timeline import Timeline
from ._absorption import AbsorptionPlan
from ._calc_utils import (
    get_period_expenses,
    get_period_occupancy,
    gross_up_period_expenses,
)
from ._lease import (
    Lease,
    LeaseSpec,
)
from ._property import Property
from ._recovery import Recovery, RecoveryCalculationState

if TYPE_CHECKING:
    from ._expense import ExpenseItem
    from ._recovery import Recovery

# TODO: Add comprehensive unit and integration tests for CashFlowAnalysis logic.

logger = logging.getLogger(__name__)


class CashFlowAnalysis(Model):
    """
    Orchestrates the calculation and aggregation of property-level cash flows.

    This class computes cash flows over a specified analysis period by:
    1. Preparing lease definitions (`LeaseSpec`) from inputs (`RentRoll.leases`
       containing `LeaseSpec`s, including those representing initial vacancy
       with future start dates) and generating additional `LeaseSpec`s from
       `AbsorptionPlan` configurations.
    2. Instantiating initial `Lease` objects from the combined list of `LeaseSpec`s.
    3. Projecting full cash flow chains (including rollovers specified by
       `RolloverProfile`s) for each initial `Lease` using `Lease.project_future_cash_flows()`.
    4. Collecting all other relevant `CashFlowModel` instances (Expenses, MiscIncome, etc.)
       associated with the property or the initial leases (e.g., TIs, LCs).
    5. Calculating a dynamic occupancy series based on the *initial* lease set
       (using `_cached_initial_lease_objects`).
    6. Computing cash flows for non-lease models, resolving dependencies using
       DAG (TopologicalSorter) or iterative fallback if cycles are detected.
    7. Combining the results from the projected lease chains and the computed non-lease
       models into a detailed list of `(metadata, series)` tuples.
    8. Aggregating the combined detailed cash flows into standard financial line items
       (`AggregateLineKey`), including calculations for Downtime Vacancy, General Vacancy
       (with optional reduction by specific losses), and Collection Loss.
    9. Providing access to these aggregated results via DataFrames (`create_cash_flow_dataframe`,
       `create_detailed_cash_flow_dataframe`) and specific metric methods (`net_operating_income`, etc.).

    Attributes:
        property: The input `Property` object containing asset details and base models.
                  Its `rent_roll.leases` attribute must now contain `LeaseSpec` objects.
        settings: Global settings potentially influencing calculations.
        analysis_start_date: The start date for the cash flow analysis period.
        analysis_end_date: The end date (inclusive) for the cash flow analysis period.
        absorption_plans: Optional list of `AbsorptionPlan` objects used to generate
                          speculative leases for vacant space.
    """

    property: Property
    settings: GlobalSettings = Field(default_factory=GlobalSettings)
    analysis_start_date: date
    analysis_end_date: date
    absorption_plans: Optional[List["AbsorptionPlan"]] = (
        None  # Add absorption plans input
    )

    # --- Cached Results ---
    # Remove cache related to old projection method
    # _cached_projected_leases: Optional[List['Lease']] = None
    _cached_detailed_flows: Optional[List[Tuple[Dict, pd.Series]]] = None
    _cached_aggregated_flows: Optional[Dict[AggregateLineKey, pd.Series]] = None
    _cached_cash_flow_dataframe: Optional[pd.DataFrame] = None
    _cached_detailed_cash_flow_dataframe: Optional[pd.DataFrame] = None
    _cached_occupancy_series: Optional[pd.Series] = None
    # Cache for the *instantiated* initial lease objects (used by occupancy, expense collection)
    _cached_initial_lease_objects: Optional[List["Lease"]] = None

    # --- Private Helper: Iterative Computation ---
    def _compute_cash_flows_iterative(
        self, all_models: List[CashFlowModel], occupancy_series: pd.Series
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
        logger.debug(
            f"Starting iterative computation for {len(all_models)} models."
        )  # DEBUG: Entry
        computed_results: Dict[UUID, Union[pd.Series, Dict[str, pd.Series]]] = {}
        remaining_models = {model.model_id: model for model in all_models}
        model_map = {model.model_id: model for model in all_models}  # Keep original map
        analysis_periods = occupancy_series.index  # Use occupancy index as timeline ref
        current_aggregates: Dict[
            AggregateLineKey, pd.Series
        ] = {}  # Store aggregates calculated each pass (keyed by Enum)

        MAX_PASSES = len(all_models) + 1
        passes = 0
        progress_made_in_pass = True

        while remaining_models and passes < MAX_PASSES and progress_made_in_pass:
            passes += 1
            logger.debug(
                f"Iterative Pass {passes}/{MAX_PASSES}. Models remaining: {len(remaining_models)}"
            )  # DEBUG: Pass start
            progress_made_in_pass = False
            models_computed_this_pass: List[UUID] = []
            lookup_errors_this_pass: Dict[UUID, str] = {}

            # Define lookup function (Handles UUID, aggregate strings, and property strings)
            def lookup_fn_iterative(
                key: Union[str, UUID],
            ) -> Union[float, pd.Series, Dict, Any]:
                # This lookup is used in the multi-pass iterative computation.
                if isinstance(key, UUID):
                    if key in computed_results:
                        return computed_results[key]
                    else:
                        # Should not happen if all_models is consistent, but handles edge cases
                        raise LookupError(
                            f"Iterative: Dependency result for model ID {key} is unknown (not computed or remaining)."
                        )
                elif isinstance(key, str):
                    # 1. Check if key matches an AggregateLineKey value
                    matched_agg_key = AggregateLineKey.from_value(key)

                    if matched_agg_key is not None:
                        # Check aggregates calculated in the *previous* pass
                        if matched_agg_key in current_aggregates:
                            return current_aggregates[matched_agg_key]
                        else:
                            # Aggregate key valid, but not calculated yet in previous pass
                            raise LookupError(
                                f"Iterative: Aggregate line '{key}' not yet available in pass {passes}."
                            )

                    # 2. Check Property attributes (if not an aggregate key)
                    if hasattr(self.property, key):
                        value = getattr(self.property, key)
                        # Validate that the retrieved property attribute has a simple, expected type
                        if isinstance(value, (int, float, str, date)):
                            return value
                        else:
                            # Raise error if property attribute is a complex object or unexpected type
                            raise TypeError(
                                f"Iterative: Property attribute '{key}' has unexpected type {type(value)}. Expected simple scalar/string/date."
                            )
                    # If not found in property attributes, raise error
                    else:
                        raise LookupError(
                            f"Iterative: Cannot resolve string reference '{key}' in pass {passes}. "
                            f"It is not a resolved AggregateLineKey or a known Property attribute."
                        )
                else:
                    raise TypeError(
                        f"Iterative: Unsupported lookup key type: {type(key)}"
                    )

            for model_id, model in list(remaining_models.items()):
                logger.debug(
                    f"  Attempting iterative compute: '{model.name}' ({model_id})"
                )  # DEBUG: Model attempt
                try:
                    # Use helper to call compute_cf with conditional occupancy
                    result = self._run_compute_cf(
                        model, lookup_fn_iterative, occupancy_series
                    )
                    computed_results[model_id] = result
                    models_computed_this_pass.append(model_id)
                    progress_made_in_pass = True
                    logger.debug(
                        f"    Success: '{model.name}' ({model_id}) computed."
                    )  # DEBUG: Model success
                except LookupError as le:
                    lookup_errors_this_pass[model_id] = str(le)
                    logger.debug(
                        f"    Lookup Error: '{model.name}' ({model_id}) - waiting for dependency: {le}"
                    )  # DEBUG: Model lookup fail
                except NotImplementedError:
                    # Log warning instead of print
                    logger.warning(
                        f"(Iterative) compute_cf not implemented for model '{model.name}' ({model.model_id}). Treating as zero flow."
                    )
                    # Still mark as computed to prevent infinite loops if it was the cause of stalling
                    computed_results[model_id] = pd.Series(0.0, index=analysis_periods)
                    models_computed_this_pass.append(model_id)
                    progress_made_in_pass = (
                        True  # Mark progress even if not implemented
                    )
                except Exception as e:
                    # Log error with exception info instead of print
                    logger.error(
                        f"(Iterative) Error computing '{model.name}' ({model.model_id}). Skipping.",
                        exc_info=True,
                    )
                    # Optionally raise the error based on settings
                    if self.settings.calculation.fail_on_error:  # Check setting
                        raise e
                    # Mark as computed (with error state represented by absence in computed_results) to avoid looping
                    models_computed_this_pass.append(model_id)
                    progress_made_in_pass = True  # Mark progress even if error occurred

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
                    logger.warning(
                        f"Unexpected result type {type(result)} for model '{original_model.name}'. Skipped processing."
                    )
                    continue

                for component_name, series in results_to_process.items():
                    if not isinstance(series, pd.Series):
                        continue
                    try:
                        # Align index - crucial for aggregation
                        if not isinstance(series.index, pd.PeriodIndex):
                            if isinstance(series.index, pd.DatetimeIndex):
                                series.index = series.index.to_period(freq="M")
                            else:
                                series.index = pd.PeriodIndex(series.index, freq="M")
                        # Use the main analysis_periods derived earlier
                        aligned_series = series.reindex(
                            analysis_periods, fill_value=0.0
                        )
                    except Exception:
                        # Log warning with exception info instead of print
                        logger.warning(
                            f"Alignment failed for component '{component_name}' from model '{original_model.name}'. Skipping component.",
                            exc_info=True,
                        )
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
            current_aggregates = self._aggregate_detailed_flows(
                detailed_flows_this_pass
            )
            # End of Pass Aggregation
            logger.debug(
                f"  Pass {passes} finished. Computed {len(models_computed_this_pass)} models this pass."
            )  # DEBUG: Pass end metrics

        if remaining_models:
            # Log warning instead of print
            logger.warning(
                f"(Iterative) Could not compute all models after {passes} passes."
            )
            for model_id, reason in lookup_errors_this_pass.items():
                if model_id in remaining_models:
                    model_name = remaining_models[model_id].name
                    # Log warning instead of print
                    logger.warning(
                        f"  - Iterative: Model '{model_name}' ({model_id}) failed. Last error: {reason}"
                    )

        logger.debug("Finished iterative computation.")  # DEBUG: Exit
        return computed_results

    # --- Private Helper: Base Year Stop Pre-calculation ---
    def _pre_calculate_all_base_year_stops(
        self, all_models: List[CashFlowModel]
    ) -> Dict[UUID, RecoveryCalculationState]:
        """
        Iterates through leases in all_models and calculates base year stops.

        This should be called once before dependency-based computation begins.
        It finds Leases with base year recovery structures, calculates the
        annual base year stop amount and any frozen pro-rata share, and returns
        this information in a dictionary mapping each Recovery object's model_id
        to a RecoveryCalculationState object containing these pre-calculated values.
        This method does not modify the Recovery objects themselves.

        Args:
            all_models: List containing all CashFlowModel instances for the analysis,
                       including projected leases and their associated recovery rules.
        Returns:
            A dictionary mapping Recovery model_id to its RecoveryCalculationState.
        """
        logger.info("Starting pre-calculation of base year stops...")
        recovery_states_map: Dict[UUID, RecoveryCalculationState] = {}

        # Imports moved to top level

        # Cache data fetched per base year to avoid redundant lookups
        base_year_data_cache: Dict[int, Dict[str, Any]] = {}

        # Iterate through all models provided
        # Use string hint 'Lease' as it's imported under TYPE_CHECKING
        leases_to_process = [model for model in all_models if isinstance(model, Lease)]
        logger.debug(
            f"Found {len(leases_to_process)} Lease instances to check for base year recoveries."
        )

        for lease in leases_to_process:
            if not lease.recoveries:
                continue  # Skip leases with no recovery definitions

            recoveries_needing_calc: List[Recovery] = []
            all_by_expense_items_for_lease: Dict[UUID, ExpenseItem] = {}

            # Check if this lease has relevant recovery structures and hasn't been calculated yet
            for recovery in lease.recoveries:
                # Initialize state for every recovery object encountered that needs calculation
                current_state = recovery_states_map.get(recovery.model_id, RecoveryCalculationState(recovery_model_id=recovery.model_id))
                recovery_states_map[recovery.model_id] = current_state

                if recovery.structure in [
                    "base_year",
                    "base_year_plus1",
                    "base_year_minus1",
                 ]:
                    # Check cache *on the recovery object* first -> This check is no longer valid here, pre-calc state is external
                    # if recovery._calculated_annual_base_year_stop is not None:
                    #     logger.debug(
                    #         f"  Stop already calculated for Lease '{lease.name}', Recovery Pool '{recovery.expense_pool.name}'. Skipping."
                    #     )
                    #     continue

                    if recovery.base_year is None:
                        logger.error(
                            f"  Recovery '{recovery.expense_pool.name}' for lease '{lease.name}' is Base Year type but missing base_year value."
                        )
                        # current_state.calculated_annual_base_year_stop remains None
                        continue

                    recoveries_needing_calc.append(recovery)
                    pool_items = recovery.expense_pool.expenses
                    if not isinstance(pool_items, list):
                        pool_items = [pool_items]
                    for item in pool_items:
                        # Check type using string hint if necessary, or rely on structure
                        # Assuming items in pool are ExpenseItem-like for now
                        if hasattr(item, "model_id"):  # Duck-typing check
                            if item.model_id not in all_by_expense_items_for_lease:
                                all_by_expense_items_for_lease[item.model_id] = item
                        else:
                            logger.warning(
                                f"Item '{getattr(item, 'name', 'Unknown')}' in pool '{recovery.expense_pool.name}' does not have model_id. Skipping."
                            )
            if not recoveries_needing_calc:
                continue  # No base year recoveries needing calculation for this lease

            logger.debug(f"Calculating base year stops for Lease '{lease.name}'...")
            lease_start_year = (
                lease.lease_start.year
            )  # Use the specific lease's start year

            # Use string hint 'Recovery' when iterating
            for recovery in recoveries_needing_calc:
                current_state = recovery_states_map[recovery.model_id] # Should exist
                year_offset = 0
                if recovery.structure == "base_year_plus1":
                    year_offset = 1
                elif recovery.structure == "base_year_minus1":
                    year_offset = -1
                target_base_year = lease_start_year + year_offset

                # Check cache for the target year's data first
                if target_base_year not in base_year_data_cache:
                    logger.debug(
                        f"  Cache miss for base year {target_base_year}. Fetching data..."
                    )
                    base_year_data_cache[target_base_year] = {
                        "occupancy": None,
                        "expenses": None,
                    }

                    # Determine calendar mode and fiscal start month from analysis settings
                    calendar_mode = (
                        self.settings.recoveries.calendar_mode.lower()
                        if self.settings.recoveries
                        else "calendar"
                    )
                    fiscal_start_month = 1
                    if calendar_mode == "fiscal":
                        if self.settings.analysis_start_date:
                            fiscal_start_month = self.settings.analysis_start_date.month
                        else:
                            logger.warning(
                                "Fiscal calendar_mode requires global_settings.analysis_start_date. Defaulting to January fiscal start."
                            )

                    # Define the base year period
                    if calendar_mode == "fiscal":
                        by_start = date(target_base_year, fiscal_start_month, 1)
                        by_end = by_start + relativedelta(years=1) - timedelta(days=1)
                    else:  # Default to Calendar
                        by_start = date(target_base_year, 1, 1)
                        by_end = date(target_base_year, 12, 31)
                    logger.debug(
                        f"    Base year {target_base_year} period: {by_start} to {by_end} ({calendar_mode} mode)."
                    )

                    # Fetch occupancy
                    monthly_occupancy = get_period_occupancy(
                        self.property, by_start, by_end, frequency="M"
                    )
                    if monthly_occupancy is None:
                        logger.error(
                            f"    Failed to get occupancy for base year {target_base_year}."
                        )
                        # current_state.calculated_annual_base_year_stop remains None
                        continue
                    base_year_data_cache[target_base_year]["occupancy"] = (
                        monthly_occupancy
                    )

                    # Fetch expenses for *all* potential items needed for this lease
                    expense_ids_to_fetch = list(all_by_expense_items_for_lease.keys())
                    monthly_expenses = get_period_expenses(
                        self.property,
                        by_start,
                        by_end,
                        expense_ids_to_fetch,
                        frequency="M",
                    )
                    if monthly_expenses is None:
                        logger.error(
                            f"    Failed to get expenses for base year {target_base_year}."
                        )
                        # current_state.calculated_annual_base_year_stop remains None
                        continue
                    base_year_data_cache[target_base_year]["expenses"] = (
                        monthly_expenses
                    )
                    logger.debug(
                        f"  Fetched and cached data for base year {target_base_year}."
                    )

                # --- Use cached data to calculate stop for this recovery ---
                cached_data = base_year_data_cache[target_base_year]
                base_year_occupancy = cached_data["occupancy"]
                base_year_expenses = cached_data["expenses"]

                if base_year_occupancy is None or base_year_expenses is None:
                    logger.warning(
                        f"  Skipping stop calculation for recovery '{recovery.expense_pool.name}' due to missing cached data for base year {target_base_year}."
                    )
                    # current_state.calculated_annual_base_year_stop remains None
                    continue

                # Filter expenses relevant to *this* recovery's pool
                pool_items = recovery.expense_pool.expenses
                if not isinstance(pool_items, list):
                    pool_items = [pool_items]
                pool_item_ids = {
                    item.model_id for item in pool_items if hasattr(item, "model_id")
                }
                pool_expenses_raw: Dict[UUID, pd.Series] = {
                    item_id: series
                    for item_id, series in base_year_expenses.items()
                    if item_id in pool_item_ids
                }
                pool_items_map: Dict[UUID, ExpenseItem] = {
                    item.model_id: item
                    for item in all_by_expense_items_for_lease.values()
                    if item.model_id in pool_item_ids
                }

                if not pool_expenses_raw:
                    logger.warning(
                        f"  No expense data found for pool '{recovery.expense_pool.name}' in base year {target_base_year}. Setting stop to 0."
                    )
                    current_state.calculated_annual_base_year_stop = 0.0
                    continue

                # Perform Gross-up
                gross_up_this_recovery = (
                    lease.recovery_method.gross_up if lease.recovery_method else False
                )
                gross_up_target = (
                    lease.recovery_method.gross_up_percent
                    if lease.recovery_method
                    and lease.recovery_method.gross_up_percent is not None
                    else 0.95
                )

                pool_expenses_grossed_up: Dict[UUID, pd.Series]
                if gross_up_this_recovery:
                    logger.debug(
                        f"    Applying gross-up to base year {target_base_year} expenses for pool '{recovery.expense_pool.name}' (Target: {gross_up_target:.1%})"
                    )
                    pool_expenses_grossed_up = gross_up_period_expenses(
                        pool_expenses_raw,
                        base_year_occupancy,
                        expense_items_map=pool_items_map,  # Use map for items in this lease
                        gross_up_target_rate=gross_up_target,
                    )
                else:
                    pool_expenses_grossed_up = pool_expenses_raw

                # Aggregate the grossed-up expenses for the pool
                total_pool_by_grossed_up = pd.Series(
                    0.0, index=base_year_occupancy.index
                )
                for series in pool_expenses_grossed_up.values():
                    total_pool_by_grossed_up = total_pool_by_grossed_up.add(
                        series.reindex(total_pool_by_grossed_up.index, fill_value=0.0),
                        fill_value=0.0,
                    )

                # Perform Annualization
                base_period_start_month = 0
                if recovery.structure == "base_year_plus1":
                    base_period_start_month = 12
                elif recovery.structure == "base_year_minus1":
                    base_period_start_month = -12

                base_period_start_date = lease.lease_start + relativedelta(
                    months=base_period_start_month
                )
                base_period_end_date = (
                    base_period_start_date
                    + relativedelta(months=12)
                    - timedelta(days=1)
                )

                try:
                    precise_base_periods = pd.period_range(
                        start=base_period_start_date, end=base_period_end_date, freq="M"
                    )
                    if len(precise_base_periods) > 12:
                        precise_base_periods = precise_base_periods[:12]
                except Exception as e:
                    logger.error(
                        f"    Could not create precise base period range for {recovery.expense_pool.name}. Cannot annualize. Error: {e}"
                    )
                    # current_state.calculated_annual_base_year_stop remains None
                    continue

                sliced_base_year_total = total_pool_by_grossed_up.reindex(
                    precise_base_periods, fill_value=0.0
                )
                months_in_slice = len(sliced_base_year_total)
                calculated_sum = sliced_base_year_total.sum()
                annual_stop_amount = 0.0
                if months_in_slice == 0:
                    logger.warning(
                        f"    No data found for base period of pool '{recovery.expense_pool.name}'. Setting stop to 0."
                    )
                elif months_in_slice < 12:
                    annual_stop_amount = (calculated_sum / months_in_slice) * 12
                    logger.warning(
                        f"    Partial data ({months_in_slice}/12 months) for base period of pool '{recovery.expense_pool.name}'. Annualized sum {annual_stop_amount:.2f}."
                    )
                else:
                    annual_stop_amount = calculated_sum

                logger.debug(
                    f"    Calculated Annual Stop for pool '{recovery.expense_pool.name}': {annual_stop_amount:.2f}"
                )
                current_state.calculated_annual_base_year_stop = annual_stop_amount

                # --- Check for Frozen Pro-rata Share ---
                freeze_share_flag = False
                if (
                    self.settings
                    and hasattr(self.settings, "recoveries")
                    and hasattr(self.settings.recoveries, "freeze_share_at_baseyear")
                ):
                    freeze_share_flag = (
                        self.settings.recoveries.freeze_share_at_baseyear
                    )
                elif self.settings and hasattr(
                    self.settings, "freeze_share_at_baseyear"
                ):
                    freeze_share_flag = self.settings.freeze_share_at_baseyear

                if freeze_share_flag:
                    current_nra = self.property.net_rentable_area
                    if current_nra > 0:
                        base_year_pro_rata = lease.area / current_nra
                        current_state.frozen_base_year_pro_rata = base_year_pro_rata
                        logger.debug(
                            f"    Storing frozen base year pro-rata share: {base_year_pro_rata:.4f}"
                        )
                    else:
                        logger.warning(
                            f"    Cannot calculate base year pro-rata share for freezing (Property NRA={current_nra})."
                        )
                        current_state.frozen_base_year_pro_rata = None
                else:
                    current_state.frozen_base_year_pro_rata = None

        logger.info("Finished pre-calculation of base year stops.")
        return recovery_states_map

    # --- Private Methods ---
    def _create_timeline(self) -> Timeline:
        """Creates a unified monthly timeline for the analysis period."""
        logger.debug(
            f"Creating timeline from {self.analysis_start_date} to {self.analysis_end_date}."
        )
        if self.analysis_start_date >= self.analysis_end_date:
            raise ValueError("Analysis start date must be before end date")
        return Timeline.from_dates(
            start_date=self.analysis_start_date,
            end_date=self.analysis_end_date,
            # Default monthly frequency assumed
        )

    def _calculate_occupancy_series(self) -> pd.Series:
        """Calculates the physical occupancy rate series over the analysis timeline
        using the initial lease set (input + absorption). Caches the result.
        """
        logger.debug(
            "Calculating occupancy series (using initial leases - checking cache)."
        )
        if self._cached_occupancy_series is None:
            logger.debug("Occupancy cache miss. Calculating now.")
            analysis_periods = self._create_timeline().period_index
            occupied_area_series = pd.Series(0.0, index=analysis_periods)

            # Use the initial lease objects (populated by _prepare_initial_lease_objects)
            initial_leases = self._cached_initial_lease_objects
            if initial_leases is None:
                logger.warning(
                    "Initial lease object cache is empty during occupancy calculation. Running preparation step."
                )
                # Ensure initial lease objects are prepared and cached
                initial_leases = self._prepare_initial_lease_objects()
                # No need to access cache again, use the returned list directly
                if initial_leases is None:  # Should not happen if preparation works
                    logger.error(
                        "Failed to get initial lease objects for occupancy calculation."
                    )
                    initial_leases = []  # Avoid error downstream

            # Sum area from the *initial* leases over their respective timelines
            if initial_leases:
                for lease in initial_leases:
                    lease_periods = lease.timeline.period_index
                    # Ensure monthly frequency for alignment
                    if lease_periods.freqstr != "M":
                        try:
                            lease_periods = lease_periods.asfreq("M", how="start")
                        except ValueError:
                            logger.warning(
                                f"Lease '{lease.name}' timeline frequency ({lease_periods.freqstr}) not monthly. Skipping for occupancy calc."
                            )
                            continue
                    # Find intersection with the main analysis timeline
                    active_periods = analysis_periods.intersection(lease_periods)
                    if not active_periods.empty:
                        # Add the lease's area to the series for the active periods
                        occupied_area_series.loc[active_periods] += lease.area

            total_nra = self.property.net_rentable_area
            if total_nra > 0:
                occupancy_series = (occupied_area_series / total_nra).clip(0, 1)
            else:
                occupancy_series = pd.Series(0.0, index=analysis_periods)
            occupancy_series.name = "Occupancy Rate"
            self._cached_occupancy_series = occupancy_series
            logger.debug(
                f"Calculated occupancy series. Average: {occupancy_series.mean():.2%}"
            )

        return self._cached_occupancy_series

    def _collect_expense_models(
        self, initial_lease_objects: List["Lease"]
    ) -> List[CashFlowModel]:
        """Extracts all expense models from the property and associated initial leases."""
        expense_models: List[CashFlowModel] = []
        if self.property.expenses:
            if self.property.expenses.operating_expenses:
                expense_models.extend(
                    self.property.expenses.operating_expenses.expense_items or []
                )
            if self.property.expenses.capital_expenses:
                expense_models.extend(
                    self.property.expenses.capital_expenses.expense_items or []
                )
        for lease in initial_lease_objects:
            if lease.ti_allowance:
                expense_models.append(lease.ti_allowance)
            if lease.leasing_commission:
                expense_models.append(lease.leasing_commission)
        return expense_models

    def _collect_other_cash_flow_models(self) -> List[CashFlowModel]:
        """Extracts any other (non-lease, non-expense, non-misc-income) cash flow models."""
        # Currently returns empty, placeholder for future models like Debt
        return []

    def _run_compute_cf(
        self, model: CashFlowModel, lookup_fn: Callable, occupancy_series: pd.Series
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
        logger.debug(
            f"Running compute_cf for model '{model.name}' ({model.model_id})"
        )  # DEBUG: Entry
        sig = inspect.signature(model.compute_cf)
        params = sig.parameters
        kwargs = {"lookup_fn": lookup_fn}

        # Inject occupancy if needed
        if "occupancy_rate" in params or "occupancy_series" in params:
            kwargs["occupancy_rate"] = occupancy_series  # Pass the series
            logger.debug(
                f"  Injecting occupancy_rate into '{model.name}'.compute_cf"
            )  # DEBUG: Occupancy injection

        # Inject property_area if needed (e.g., for Lease compute_cf calling RecoveryMethod)
        if "property_area" in params:
            kwargs["property_area"] = self.property.net_rentable_area
            logger.debug(
                f"  Injecting property_area ({self.property.net_rentable_area}) into '{model.name}'.compute_cf"
            )

        result = model.compute_cf(**kwargs)
        logger.debug(
            f"  Finished compute_cf for '{model.name}'. Result type: {type(result).__name__}"
        )  # DEBUG: Exit
        return result

    def _compute_detailed_flows(self) -> List[Tuple[Dict, pd.Series]]:
        """Computes all individual cash flows, handling dependencies and context injection.
        Returns a detailed list of results, each tagged with metadata. Caches results.

        Workflow using LeaseSpec:
        1. Calls `_prepare_initial_lease_objects()` to get/generate all `LeaseSpec`s
           (input & absorption) and instantiate the initial `Lease` objects.
        2. Collects non-lease models (Expenses, MiscIncome, etc.).
        3. Calculates occupancy based on the *initial* lease objects.
        4. Pre-calculates base year stops for recoveries using initial models.
        5. Iterates through initial `Lease` objects, calling `project_future_cash_flows()`
           on each to get the full cash flow DataFrame for the *entire lease chain*
           (including rollovers).
        6. Computes cash flows for non-lease models using DAG/iteration.
        7. Processes results from lease chains (extracting components like base_rent,
           recoveries, ti_allowance, etc., from the chain DataFrames) and non-lease
           models into a unified list of `(metadata, series)` tuples, aligning
           indices to the analysis timeline.
        8. Caches and returns this detailed list.
        """
        logger.debug("Starting computation of detailed flows (checking cache).")
        if self._cached_detailed_flows is not None:
            logger.debug("Returning cached detailed flows.")
            return self._cached_detailed_flows

        logger.debug("Detailed flows cache miss. Computing now.")
        analysis_timeline = self._create_timeline()
        analysis_periods = analysis_timeline.period_index

        # --- Prepare Initial Lease Objects (Handles Specs, Instantiation, Caching) --- #
        initial_lease_objects = self._prepare_initial_lease_objects()
        # Now self._cached_initial_lease_objects is populated

        # --- Collect Non-Lease Models --- #
        # Pass the initial objects to collect associated TIs/LCs
        expense_models = self._collect_expense_models(initial_lease_objects)
        misc_income_models = self.property.miscellaneous_income or []
        other_models = self._collect_other_cash_flow_models()
        non_lease_models = expense_models + misc_income_models + other_models
        all_initial_models = (
            initial_lease_objects + non_lease_models
        )  # For base year stop calc
        model_map = {model.model_id: model for model in all_initial_models}

        # --- Calculate Occupancy --- #
        # Uses self._cached_initial_lease_objects implicitly now
        occupancy_series = self._calculate_occupancy_series()

        # --- Pre-calculate Base Year Stops --- #
        # Uses the combined list including initial leases and their expenses
        recovery_states_map = self._pre_calculate_all_base_year_stops(all_initial_models)

        # --- Project Full Lease Chains --- #
        logger.info(
            f"Projecting cash flows for {len(initial_lease_objects)} initial lease chains..."
        )
        # Store results as: {initial_lease_id: full_chain_df}
        lease_chain_results_map: Dict[UUID, pd.DataFrame] = {}
        for initial_lease in initial_lease_objects:
            try:
                # Build lookup potentially needed by project_future_cash_flows internals
                # For now, assume a simple one might suffice or isn't strictly needed for THIS call
                proj_lookup_fn = self._build_lookup_fn({})  # Placeholder
                full_chain_cf_df = initial_lease.project_future_cash_flows(
                    projection_end_date=self.analysis_end_date,
                    property_data=self.property,
                    global_settings=self.settings,
                    occupancy_projection=occupancy_series,  # Pass calculated occupancy
                    lookup_fn=proj_lookup_fn,
                    recovery_states=recovery_states_map
                )
                # Ensure the result DF index matches the analysis periods
                full_chain_cf_df = full_chain_cf_df.reindex(
                    analysis_periods, fill_value=0.0
                )
                lease_chain_results_map[initial_lease.model_id] = full_chain_cf_df
                logger.debug(
                    f"  Projected chain for: '{initial_lease.name}' ({initial_lease.model_id})"
                )
            except Exception as e:
                logger.error(
                    f"Error projecting full cash flow chain for lease '{initial_lease.name}': {e}",
                    exc_info=True,
                )
                if self.settings.calculation.fail_on_error:
                    raise
        logger.info(f"Finished projecting {len(lease_chain_results_map)} lease chains.")

        # --- Compute Non-Lease Models (Expenses, Misc Inc, Other) --- #
        logger.info(f"Computing flows for {len(non_lease_models)} non-lease models...")
        non_lease_computed_results: Dict[
            UUID, Union[pd.Series, Dict[str, pd.Series]]
        ] = {}
        if non_lease_models:
            non_lease_model_map = {model.model_id: model for model in non_lease_models}
            use_iterative_fallback = False
            # Build lookup using only non-lease results computed so far
            computation_lookup_fn = self._build_lookup_fn(non_lease_computed_results)

            try:
                graph = self._build_dependency_graph(non_lease_model_map)
                ts = TopologicalSorter(graph)
                ts.prepare()
                logger.info("Attempting topological sort for non-lease models.")
                while ts.is_active():
                    node_group = ts.get_ready()
                    for model_id in node_group:
                        model = non_lease_model_map[model_id]
                        try:
                            result = self._run_compute_cf(
                                model, computation_lookup_fn, occupancy_series
                            )
                            non_lease_computed_results[model_id] = result
                        except Exception as e:
                            logger.error(
                                f"(DAG Path) Error computing non-lease model '{model.name}' ({model_id}). Skipped.",
                                exc_info=True,
                            )
                            if self.settings.calculation.fail_on_error:
                                raise e
                            non_lease_computed_results.pop(model_id, None)
                    ts.done(*node_group)
                logger.info("Non-lease models: DAG computation successful.")
            except CycleError:
                logger.warning(
                    "Non-lease models: Cycle detected. Falling back to iteration."
                )
                use_iterative_fallback = True
            except Exception as graph_err:
                logger.error(
                    f"Non-lease models: Error during graph processing: {graph_err}. Falling back to iteration.",
                    exc_info=True,
                )
                use_iterative_fallback = True

            if use_iterative_fallback:
                logger.info("Non-lease models: Using iterative multi-pass computation.")
                non_lease_computed_results = self._compute_cash_flows_iterative(
                    non_lease_models, occupancy_series
                )
        logger.info(
            f"Finished computing {len(non_lease_computed_results)} non-lease models."
        )

        # --- Process & Combine All Results into Detailed Flows --- #
        processed_flows: List[Tuple[Dict, pd.Series]] = []

        # 1. Process Lease Chain Results
        for initial_lease_id, chain_df in lease_chain_results_map.items():
            # Find the original initial lease object for metadata
            initial_lease = model_map.get(initial_lease_id)
            if not initial_lease or not isinstance(initial_lease, Lease):
                logger.warning(
                    f"Could not find initial Lease object for ID {initial_lease_id} when processing chain results."
                )
                continue
            # Extract components from the DataFrame
            for component_name in chain_df.columns:
                if component_name in ["net"]:
                    continue  # Skip derived total
                series = chain_df[component_name]
                metadata = {
                    "model_id": str(initial_lease_id),
                    "name": initial_lease.name,
                    "category": "Revenue"
                    if component_name
                    in ["base_rent", "recoveries", "revenue", "vacancy_loss"]
                    else "Expense",
                    "subcategory": str(initial_lease.subcategory),
                    "component": component_name,
                }
                # Refine category/subcategory for specific components
                if component_name in ["ti_allowance", "leasing_commission"]:
                    metadata["category"] = "Expense"
                    metadata["subcategory"] = component_name.replace("_", " ").title()
                elif component_name == "vacancy_loss":
                    metadata["subcategory"] = "Rollover Vacancy"
                elif component_name == "abatement":
                    metadata["subcategory"] = "Rental Abatement"

                processed_flows.append((metadata, series))  # Already aligned

        # 2. Process Non-Lease Model Results
        processed_flows.extend(
            self._process_computed_results(
                non_lease_computed_results, model_map, analysis_periods
            )
        )

        # --- Cache and Return Detailed Flows --- #
        self._cached_detailed_flows = processed_flows
        logger.debug(
            f"Finished computation. Generated {len(processed_flows)} detailed series."
        )
        return self._cached_detailed_flows

    # --- Helper method to build lookup_fn (can be expanded) --- #
    def _build_lookup_fn(self, computed_results_map: Dict[UUID, Any]) -> Callable:
        """Builds the lookup function required by compute_cf and resolution methods.

        FIXME: This lookup_fn is a placeholder. It currently only reliably resolves
               RolloverProfile names (from Property.rollover_profiles by name) and
               direct Property attributes. It does NOT support looking up arbitrary
               CashFlowModel results by ID (unless passed in computed_results_map,
               which is context-specific) or AggregateLineKeys during the main projection
               path. This needs to be made robust if future models within lease chains
               or non-lease DAGs require more complex dynamic lookups.

        TODO: Extend _build_lookup_fn to allow resolution of computed CashFlowModel
              results by model_id (potentially requiring access to a broader model_map
              than just `computed_results_map` passed here) and AggregateLineKey
              values (potentially needing context of current_aggregates if used
              outside the iterative solver).
        """
        # This is a simplified placeholder. A real implementation needs robust
        # handling of property attributes, aggregates (if iterative), profiles etc.
        # It might need access to more context.
        profile_map = {
            prof.name: prof for prof in getattr(self.property, "rollover_profiles", [])
        }  # Example

        def lookup(key: Union[str, UUID]) -> Any:
            if isinstance(key, UUID):
                if (
                    key in computed_results_map
                ):  # This primarily serves the non-lease DAG solver
                    return computed_results_map[key]
                else:
                    # TODO: Attempt to find model_id in a broader model_map if available
                    #       (e.g., self.model_map if accessible and appropriate for this context)
                    raise LookupError(
                        f"Lookup: Model ID {key} not found in provided computed_results_map."
                    )
            elif isinstance(key, str):
                # Check profiles first (used by Lease.from_spec, AbsorptionPlan)
                if key in profile_map:
                    return profile_map[key]
                # Check property attributes
                if hasattr(self.property, key):
                    val = getattr(self.property, key)
                    if isinstance(val, (int, float, str, date)):
                        return val
                    else:
                        raise TypeError(
                            f"Lookup: Property attribute '{key}' has complex type {type(val)}"
                        )

                # TODO: Consider if AggregateLineKey resolution is needed here for non-iterative contexts.
                #       Currently, only lookup_fn_iterative handles AggregateLineKeys.

                raise LookupError(
                    f"Lookup: Cannot resolve string key '{key}'. Not a known Profile name or Property attribute."
                )
            else:
                raise TypeError(f"Lookup: Unsupported key type {type(key)}")

        return lookup

    # --- Helper method to process computed results --- #
    def _process_computed_results(
        self,
        computed_results: Dict[UUID, Any],
        model_map: Dict[UUID, CashFlowModel],
        analysis_periods: pd.PeriodIndex,
    ) -> List[Tuple[Dict, pd.Series]]:
        """Processes the raw computed results into the detailed flow format."""
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
            else:
                logger.warning(
                    f"Unexpected result type {type(result)} processing model '{original_model.name}'. Skipping."
                )
                continue

            for component_name, series in results_to_process.items():
                if not isinstance(series, pd.Series):
                    logger.warning(
                        f"Item '{component_name}' in result for model '{original_model.name}' is not a pd.Series. Skipping."
                    )
                    continue

                aligned_series: pd.Series
                try:
                    # Ensure index is a monthly PeriodIndex before reindexing
                    if (
                        not isinstance(series.index, pd.PeriodIndex)
                        or series.index.freqstr != "M"
                    ):
                        if isinstance(series.index, pd.DatetimeIndex):
                            series.index = series.index.to_period(freq="M")
                        else:
                            # Attempt conversion if not DatetimeIndex either
                            series.index = pd.PeriodIndex(series.index, freq="M")
                    # Align to the analysis timeline, filling missing periods with 0
                    aligned_series = series.reindex(analysis_periods, fill_value=0.0)
                except Exception as e:
                    logger.warning(
                        f"Alignment/Reindexing failed for component '{component_name}' from model '{original_model.name}'. Skipping component. Error: {e}",
                        exc_info=True,
                    )
                    continue

                # Create metadata dictionary for this specific series
                metadata = {
                    "model_id": str(model_id),
                    "name": original_model.name,
                    "category": original_model.category,
                    "subcategory": str(original_model.subcategory),
                    "component": component_name,
                }
                processed_flows.append((metadata, aligned_series))

        return processed_flows

    # --- Helper method to build dependency graph --- #
    def _build_dependency_graph(
        self, model_map: Dict[UUID, CashFlowModel]
    ) -> Dict[UUID, Set[UUID]]:
        """Builds the dependency graph based on model_id references."""
        graph: Dict[UUID, Set[UUID]] = {m_id: set() for m_id in model_map.keys()}
        for model_id, model in model_map.items():
            # Check direct reference
            if hasattr(model, "reference") and isinstance(model.reference, UUID):
                dependency_id = model.reference
                if dependency_id in graph:
                    graph[model_id].add(dependency_id)
                else:
                    logger.warning(
                        f"Model '{model.name}' ({model_id}) refs unknown ID {dependency_id}. Ignored in dependency graph."
                    )
            # Check TI reference
            if (
                hasattr(model, "ti_allowance")
                and model.ti_allowance
                and isinstance(model.ti_allowance.reference, UUID)
            ):
                dependency_id = model.ti_allowance.reference
                ti_model_id = model.ti_allowance.model_id
                if dependency_id in graph and ti_model_id in graph:
                    graph[ti_model_id].add(dependency_id)
            # Check LC reference
            if (
                hasattr(model, "leasing_commission")
                and model.leasing_commission
                and isinstance(model.leasing_commission.reference, UUID)
            ):
                dependency_id = model.leasing_commission.reference
                lc_model_id = model.leasing_commission.model_id
                if dependency_id in graph and lc_model_id in graph:
                    graph[lc_model_id].add(dependency_id)
            # TODO: Check other potential UUID references (e.g., within RecoveryMethod?)
        return graph

    def _aggregate_detailed_flows(
        self, detailed_flows: List[Tuple[Dict, pd.Series]]
    ) -> Dict[AggregateLineKey, pd.Series]:
        """Aggregates detailed flows into standard financial line items using AggregateLineKey.

        This method performs the core aggregation logic:
        1. Maps individual cash flow series (from Leases, Expenses, etc.) to
           standard AggregateLineKey categories.
        2. Calculates derived lines like EGR, EGI, NOI, and UCF.
        3. Calculates General Vacancy and Collection Loss based on property settings.
           - If configured, reduces General Vacancy by specific Rollover Vacancy Loss
             to prevent double-counting.

        Args:
            detailed_flows: A list where each item is a tuple containing:
                            - metadata (Dict): Info about the cash flow source.
                            - series (pd.Series): The calculated monthly cash flow.

        Returns:
            A dictionary where keys are AggregateLineKey enums and values are
            the corresponding aggregated pandas Series over the analysis timeline.
        """
        logger.debug(
            f"Starting aggregation of {len(detailed_flows)} detailed flows."
        )  # DEBUG: Entry
        # TODO: Allow for more flexible aggregation rules or custom groupings?
        analysis_periods = (
            self._create_timeline().period_index
        )  # Get timeline for initialization

        # Initialize all *display* keys from the enum with zero series
        # We will populate these directly now, removing the need for _RAW_ keys
        aggregated_flows: Dict[AggregateLineKey, pd.Series] = {
            key: pd.Series(0.0, index=analysis_periods, name=key.value)
            for key in AggregateLineKey.get_display_keys()  # Use display keys
        }

        # --- Map detailed flows directly to final aggregate lines ---
        # Get set of MiscIncome model IDs for quick lookup
        misc_income_models = (
            set(m.model_id for m in self.property.miscellaneous_income)
            if self.property.miscellaneous_income
            else set()
        )  # Iterate directly over list

        for metadata, series in detailed_flows:
            model_id = UUID(metadata["model_id"])  # Convert back to UUID for lookup
            category = metadata["category"]
            subcategory = metadata["subcategory"]  # Already stringified
            component = metadata["component"]
            target_aggregate_key: Optional[AggregateLineKey] = None

            # Map detailed flows to the appropriate aggregate key
            if category == "Revenue":
                # Check if it's Misc Income based on model_id
                if model_id in misc_income_models:
                    if (
                        component == "value"
                    ):  # Assume 'value' is the main component for MiscIncome
                        target_aggregate_key = AggregateLineKey.MISCELLANEOUS_INCOME
                # Otherwise assume it's Lease related
                elif subcategory == str(
                    RevenueSubcategoryEnum.LEASE
                ):  # Explicitly check subcategory
                    if component == "base_rent":
                        target_aggregate_key = AggregateLineKey.POTENTIAL_GROSS_REVENUE
                    elif component == "recoveries":
                        target_aggregate_key = AggregateLineKey.EXPENSE_REIMBURSEMENTS
                    elif component == "abatement":  # Capture abatement separately
                        target_aggregate_key = AggregateLineKey.RENTAL_ABATEMENT
                    elif (
                        component == "revenue"
                    ):  # Skip component: 'revenue' is derived (rent+recov-abate) within Lease.compute_cf
                        pass
                    # Removed dead code block for component == "value" as Lease.compute_cf doesn't return it.

            elif category == "Expense":
                if (
                    subcategory == str(ExpenseSubcategoryEnum.OPEX)
                    and component == "value"
                ):
                    target_aggregate_key = AggregateLineKey.TOTAL_OPERATING_EXPENSES
                elif (
                    subcategory == str(ExpenseSubcategoryEnum.CAPEX)
                    and component == "value"
                ):
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
                aggregated_flows[target_aggregate_key] = aggregated_flows[
                    target_aggregate_key
                ].add(safe_series, fill_value=0.0)
            else:
                logger.debug(
                    f"Flow {metadata['name']}/{component} (Cat: {category}, Sub: {subcategory}) not mapped to aggregate."
                )

        # --- Calculate Downtime Vacancy --- #
        logger.debug("Calculating Downtime Vacancy Loss...")
        downtime_vacancy_loss_series = pd.Series(
            0.0,
            index=analysis_periods,
            name=AggregateLineKey.DOWNTIME_VACANCY_LOSS.value,
        )
        # Use the cached initial lease objects
        initial_leases = self._cached_initial_lease_objects or []

        for lease in initial_leases:
            # Check if lease starts after the analysis begins
            if lease.lease_start > self.analysis_start_date:
                # Determine the downtime periods
                downtime_start_period = pd.Period(self.analysis_start_date, freq="M")
                # End period is the month *before* the lease starts
                downtime_end_period = pd.Period(lease.lease_start, freq="M") - 1

                if downtime_start_period <= downtime_end_period:
                    downtime_periods = pd.period_range(
                        start=downtime_start_period, end=downtime_end_period, freq="M"
                    )
                    # Filter downtime periods to be within the analysis timeline
                    valid_downtime_periods = analysis_periods.intersection(
                        downtime_periods
                    )

                    if not valid_downtime_periods.empty:
                        # Calculate potential monthly rent for this lease during downtime
                        # Replicates the logic from compute_cf's start
                        potential_monthly_rent = 0.0
                        if isinstance(lease.value, (int, float)):
                            potential_monthly_rent = lease.value
                            if lease.frequency == FrequencyEnum.ANNUAL:
                                potential_monthly_rent /= 12
                            if lease.unit_of_measure == UnitOfMeasureEnum.PSF:
                                potential_monthly_rent *= lease.area
                            elif lease.unit_of_measure == UnitOfMeasureEnum.AMOUNT:
                                pass  # Already monthly total
                            else:
                                logger.warning(
                                    f"Cannot calculate potential rent for downtime vacancy for lease '{lease.name}' due to unsupported unit: {lease.unit_of_measure}"
                                )
                                potential_monthly_rent = 0.0
                        else:
                            # Cannot easily determine potential rent from Series/Dict/List for downtime
                            logger.warning(
                                f"Cannot calculate potential rent for downtime vacancy for lease '{lease.name}' as initial value is not scalar."
                            )

                        # Add loss to the aggregate series for the valid downtime periods
                        if potential_monthly_rent > 0:
                            downtime_vacancy_loss_series.loc[
                                valid_downtime_periods
                            ] += potential_monthly_rent
                            logger.debug(
                                f"  Added downtime loss for Lease '{lease.name}' ({len(valid_downtime_periods)} periods): {potential_monthly_rent * len(valid_downtime_periods):.2f}"
                            )

        # Store the calculated series
        aggregated_flows[AggregateLineKey.DOWNTIME_VACANCY_LOSS] = (
            downtime_vacancy_loss_series
        )
        logger.debug(
            f"Total calculated Downtime Vacancy Loss: {downtime_vacancy_loss_series.sum():.2f}"
        )

        # --- Calculate derived lines (EGR first) --- #
        # EGR = PGR + Misc - Abatement
        pgr = aggregated_flows.get(
            AggregateLineKey.POTENTIAL_GROSS_REVENUE,
            pd.Series(0.0, index=analysis_periods),
        )
        misc = aggregated_flows.get(
            AggregateLineKey.MISCELLANEOUS_INCOME,
            pd.Series(0.0, index=analysis_periods),
        )
        abate = aggregated_flows.get(
            AggregateLineKey.RENTAL_ABATEMENT, pd.Series(0.0, index=analysis_periods)
        )
        # NOTE: Downtime Vacancy is NOT subtracted here; it's treated like General Vacancy below.
        aggregated_flows[AggregateLineKey.EFFECTIVE_GROSS_REVENUE] = pgr + misc - abate

        # --- Calculate Vacancy & Collection Loss (using property.losses) --- #
        logger.debug(
            "Calculating General Vacancy and Collection Loss based on property loss settings."
        )
        loss_config = self.property.losses
        # Get pre-calculated Downtime Vacancy
        downtime_vacancy_loss_series = aggregated_flows.get(
            AggregateLineKey.DOWNTIME_VACANCY_LOSS,
            pd.Series(0.0, index=analysis_periods),
        )
        # Get pre-calculated or mapped Rollover Vacancy
        rollover_vacancy_loss_series = aggregated_flows.get(
            AggregateLineKey.ROLLOVER_VACANCY_LOSS,
            pd.Series(0.0, index=analysis_periods),
        )

        # --- General Vacancy Loss --- #
        vacancy_basis_series: pd.Series
        if (
            loss_config.general_vacancy.method
            == VacancyLossMethodEnum.POTENTIAL_GROSS_REVENUE
        ):
            vacancy_basis_series = aggregated_flows.get(
                AggregateLineKey.POTENTIAL_GROSS_REVENUE,
                pd.Series(0.0, index=analysis_periods),
            )
        elif (
            loss_config.general_vacancy.method
            == VacancyLossMethodEnum.EFFECTIVE_GROSS_REVENUE
        ):
            vacancy_basis_series = aggregated_flows.get(
                AggregateLineKey.EFFECTIVE_GROSS_REVENUE,
                pd.Series(0.0, index=analysis_periods),
            )
        else:
            logger.warning(
                f"Unknown vacancy_loss_method: '{loss_config.general_vacancy.method}'. Defaulting to PGR."
            )
            vacancy_basis_series = aggregated_flows.get(
                AggregateLineKey.POTENTIAL_GROSS_REVENUE,
                pd.Series(0.0, index=analysis_periods),
            )

        gross_general_vacancy_loss = (
            vacancy_basis_series * loss_config.general_vacancy.rate
        )
        logger.debug(
            f"  Calculated Gross General Vacancy Loss (Rate: {loss_config.general_vacancy.rate:.1%}): {gross_general_vacancy_loss.sum():.2f}"
        )

        # --- Apply reduction by specific losses (Downtime and Rollover) --- #
        final_general_vacancy_loss: pd.Series
        # Assuming reuse of the existing flag for now
        if loss_config.general_vacancy.reduce_general_vacancy_by_rollover_vacancy:
            # Combine Downtime and Rollover vacancy before subtracting
            specific_vacancy_loss = downtime_vacancy_loss_series.add(
                rollover_vacancy_loss_series, fill_value=0.0
            )
            logger.debug(
                f"  Reducing general vacancy by combined specific vacancy loss (Downtime+Rollover Sum: {specific_vacancy_loss.sum():.2f})."
            )

            # Ensure alignment before subtraction (left join to keep all gross periods)
            aligned_gross_vac, aligned_specific_vac = gross_general_vacancy_loss.align(
                specific_vacancy_loss, join="left", fill_value=0.0
            )
            # Subtract combined specific loss, clipping at zero
            net_general_vacancy_loss = (aligned_gross_vac - aligned_specific_vac).clip(
                lower=0
            )
            final_general_vacancy_loss = net_general_vacancy_loss
            logger.debug(
                f"    Net General Vacancy Loss after reduction: {net_general_vacancy_loss.sum():.2f}"
            )
        else:
            # If reduction flag is off, use the gross amount
            logger.debug(
                "  Reduction by specific vacancy is disabled. Using gross general vacancy."
            )
            final_general_vacancy_loss = gross_general_vacancy_loss

        aggregated_flows[AggregateLineKey.GENERAL_VACANCY_LOSS] = (
            final_general_vacancy_loss
        )

        # --- Collection Loss --- #
        # ... (Existing logic for calculating calculated_collection_loss remains the same)
        collection_basis_series: pd.Series
        if loss_config.collection_loss.basis == "pgr":
            collection_basis_series = aggregated_flows.get(
                AggregateLineKey.POTENTIAL_GROSS_REVENUE,
                pd.Series(0.0, index=analysis_periods),
            )
        elif loss_config.collection_loss.basis == "egi":
            egr = aggregated_flows.get(
                AggregateLineKey.EFFECTIVE_GROSS_REVENUE,
                pd.Series(0.0, index=analysis_periods),
            )
            gen_vac = aggregated_flows.get(
                AggregateLineKey.GENERAL_VACANCY_LOSS,
                pd.Series(0.0, index=analysis_periods),
            )
            downtime_vac = aggregated_flows.get(
                AggregateLineKey.DOWNTIME_VACANCY_LOSS,
                pd.Series(0.0, index=analysis_periods),
            )
            recov = aggregated_flows.get(
                AggregateLineKey.EXPENSE_REIMBURSEMENTS,
                pd.Series(0.0, index=analysis_periods),
            )
            # EGI before collection loss = EGR - General Vacancy - Downtime Vacancy + Reimbursements
            collection_basis_series = egr - gen_vac - downtime_vac + recov
        else:  # Default or unknown basis
            logger.warning(
                f"Unsupported collection_loss_basis: '{loss_config.collection_loss.basis}'. Defaulting to EGI."
            )
            egr = aggregated_flows.get(
                AggregateLineKey.EFFECTIVE_GROSS_REVENUE,
                pd.Series(0.0, index=analysis_periods),
            )
            gen_vac = aggregated_flows.get(
                AggregateLineKey.GENERAL_VACANCY_LOSS,
                pd.Series(0.0, index=analysis_periods),
            )
            downtime_vac = aggregated_flows.get(
                AggregateLineKey.DOWNTIME_VACANCY_LOSS,
                pd.Series(0.0, index=analysis_periods),
            )
            recov = aggregated_flows.get(
                AggregateLineKey.EXPENSE_REIMBURSEMENTS,
                pd.Series(0.0, index=analysis_periods),
            )
            collection_basis_series = egr - gen_vac - downtime_vac + recov
        calculated_collection_loss = (
            collection_basis_series * loss_config.collection_loss.rate
        )
        aggregated_flows[AggregateLineKey.COLLECTION_LOSS] = calculated_collection_loss

        # --- Recalculate derived lines using final calculated losses --- #
        # Total Effective Gross Income (Total EGI)
        egr = aggregated_flows.get(
            AggregateLineKey.EFFECTIVE_GROSS_REVENUE,
            pd.Series(0.0, index=analysis_periods),
        )
        gen_vac = aggregated_flows.get(
            AggregateLineKey.GENERAL_VACANCY_LOSS,
            pd.Series(0.0, index=analysis_periods),
        )
        downtime_vac = aggregated_flows.get(
            AggregateLineKey.DOWNTIME_VACANCY_LOSS,
            pd.Series(0.0, index=analysis_periods),
        )
        coll_loss = aggregated_flows.get(
            AggregateLineKey.COLLECTION_LOSS, pd.Series(0.0, index=analysis_periods)
        )
        recov = aggregated_flows.get(
            AggregateLineKey.EXPENSE_REIMBURSEMENTS,
            pd.Series(0.0, index=analysis_periods),
        )
        # EGI = EGR - General Vacancy - Downtime Vacancy - Collection Loss + Reimbursements
        aggregated_flows[AggregateLineKey.TOTAL_EFFECTIVE_GROSS_INCOME] = (
            egr - gen_vac - downtime_vac - coll_loss + recov
        )

        # Net Operating Income (NOI)
        # ... (NOI calc remains the same: EGI - OpEx)
        egi = aggregated_flows.get(
            AggregateLineKey.TOTAL_EFFECTIVE_GROSS_INCOME,
            pd.Series(0.0, index=analysis_periods),
        )
        opex = aggregated_flows.get(
            AggregateLineKey.TOTAL_OPERATING_EXPENSES,
            pd.Series(0.0, index=analysis_periods),
        )
        aggregated_flows[AggregateLineKey.NET_OPERATING_INCOME] = egi - opex

        # Unlevered Cash Flow (UCF)
        # ... (UCF calc remains the same: NOI - TIs - LCs - CapEx)
        noi = aggregated_flows.get(
            AggregateLineKey.NET_OPERATING_INCOME,
            pd.Series(0.0, index=analysis_periods),
        )
        tis = aggregated_flows.get(
            AggregateLineKey.TOTAL_TENANT_IMPROVEMENTS,
            pd.Series(0.0, index=analysis_periods),
        )
        lcs = aggregated_flows.get(
            AggregateLineKey.TOTAL_LEASING_COMMISSIONS,
            pd.Series(0.0, index=analysis_periods),
        )
        capex = aggregated_flows.get(
            AggregateLineKey.TOTAL_CAPITAL_EXPENDITURES,
            pd.Series(0.0, index=analysis_periods),
        )
        aggregated_flows[AggregateLineKey.UNLEVERED_CASH_FLOW] = (
            noi - tis - lcs - capex
        )  # Note: TIs/LCs/CapEx are negative flows

        # Levered Cash Flow (LCF)
        # ... (LCF calc remains the same: UCF - Debt Service)
        ucf = aggregated_flows.get(
            AggregateLineKey.UNLEVERED_CASH_FLOW, pd.Series(0.0, index=analysis_periods)
        )
        debt = aggregated_flows.get(
            AggregateLineKey.TOTAL_DEBT_SERVICE, pd.Series(0.0, index=analysis_periods)
        )
        aggregated_flows[AggregateLineKey.LEVERED_CASH_FLOW] = ucf - debt

        # Final result contains only the display keys initialized at the start
        final_aggregates = aggregated_flows

        # DEBUG: Log aggregate values calculated this pass
        if logger.isEnabledFor(logging.DEBUG):
            agg_summary = {
                k.value: f"{v.sum():.2f}"
                for k, v in final_aggregates.items()
                if v.sum() != 0
            }
            logger.debug(f"Final aggregated values: {agg_summary}")

        return final_aggregates  # Return only display keys

    def _get_aggregated_flows(self) -> Dict[AggregateLineKey, pd.Series]:
        """Computes/retrieves detailed flows, then computes/retrieves aggregated flows using Enum keys."""
        logger.debug("Getting aggregated flows (checking cache).")  # DEBUG: Entry
        # Ensure detailed flows are computed and cached
        detailed_flows = self._compute_detailed_flows()

        # Compute/cache aggregated flows from the *final* detailed flows
        if self._cached_aggregated_flows is None:
            logger.debug(
                "Aggregated flows cache miss. Computing now."
            )  # DEBUG: Cache miss
            self._cached_aggregated_flows = self._aggregate_detailed_flows(
                detailed_flows
            )

        logger.debug("Finished getting aggregated flows.")  # DEBUG: Exit
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
        logger.debug(
            "Creating detailed cash flow DataFrame (checking cache)."
        )  # DEBUG: Entry
        if self._cached_detailed_cash_flow_dataframe is None:
            logger.debug("Detailed DF cache miss. Computing now.")  # DEBUG: Cache miss
            detailed_flows = self._compute_detailed_flows()

            if not detailed_flows:  # Handle case with no results
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
                    metadata["category"],
                    metadata["subcategory"],
                    metadata["name"],
                    metadata["component"],
                )
                # Prevent duplicate columns by checking if tuple already exists
                if col_tuple not in tuples:
                    tuples.append(col_tuple)
                    # Ensure series aligns with the common index
                    data_dict[col_tuple] = series.reindex(index, fill_value=0.0)
                else:
                    # If tuple exists, add series to existing column data
                    data_dict[col_tuple] = data_dict[col_tuple].add(
                        series.reindex(index, fill_value=0.0), fill_value=0.0
                    )
                    logger.debug(f"Aggregating duplicate column: {col_tuple}")

            if not tuples:  # Check if tuples list is empty
                logger.debug("No valid columns generated for detailed DataFrame.")
                return pd.DataFrame(index=index)

            multi_index = pd.MultiIndex.from_tuples(
                tuples, names=["Category", "Subcategory", "Name", "Component"]
            )

            # Create DataFrame from the potentially aggregated data_dict keys
            df = pd.DataFrame({col: data_dict[col] for col in tuples}, index=index)
            df.columns = multi_index
            df.index.name = "Period"

            # Sort columns for consistent presentation (optional but nice)
            df = df.sort_index(axis=1)

            self._cached_detailed_cash_flow_dataframe = df

        logger.debug("Finished creating detailed cash flow DataFrame.")  # DEBUG: Exit
        return self._cached_detailed_cash_flow_dataframe

    def create_cash_flow_dataframe(self) -> pd.DataFrame:
        """Generates or retrieves a cached DataFrame of the property's cash flows.

        Columns include standard aggregated lines (Total Revenue, Total OpEx, etc.)
        and calculated metrics (NOI, Unlevered Cash Flow), keyed by AggregateLineKey values.
        The index represents monthly periods over the analysis timeline.

        Returns:
            A pandas DataFrame summarizing the property's cash flows.
        """
        logger.debug(
            "Creating summary cash flow DataFrame (checking cache)."
        )  # DEBUG: Entry
        if self._cached_cash_flow_dataframe is None:
            logger.debug("Summary DF cache miss. Computing now.")  # DEBUG: Cache miss
            # _get_aggregated_flows now returns Dict[AggregateLineKey, pd.Series]
            flows: Dict[AggregateLineKey, pd.Series] = self._get_aggregated_flows()

            # Use display keys from Enum for standard column order
            column_order = AggregateLineKey.get_display_keys()

            # Create DataFrame using Enum values as column headers
            # Ensure all keys exist in the flows dict, default to zero series if not
            df_data = {}
            ref_index = self._create_timeline().period_index  # Use a reference index
            for key in column_order:
                # Use the key's value (string) for the DataFrame column name
                df_data[key.value] = flows.get(
                    key, pd.Series(0.0, index=ref_index, name=key.value)
                )

            cf_df = pd.DataFrame(df_data, index=ref_index)
            # Order columns as defined above
            cf_df = cf_df[[key.value for key in column_order]]
            cf_df.index.name = "Period"

            self._cached_cash_flow_dataframe = cf_df

        logger.debug("Finished creating summary cash flow DataFrame.")  # DEBUG: Exit
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
            return flows.get(
                AggregateLineKey.NET_OPERATING_INCOME,
                pd.Series(0.0, index=self._create_timeline().period_index),
            )

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
            return flows.get(
                AggregateLineKey.UNLEVERED_CASH_FLOW,
                pd.Series(0.0, index=self._create_timeline().period_index),
            )

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
        return flows.get(
            AggregateLineKey.TOTAL_DEBT_SERVICE,
            pd.Series(0.0, index=self._create_timeline().period_index),
        )

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
            aligned_ucf, aligned_ds = ucf.align(ds, join="left", fill_value=0.0)
            return aligned_ucf - aligned_ds

    # --- Private Helper: Lease Spec Generation & Initial Lease Instantiation --- #
    def _prepare_initial_lease_objects(self) -> List["Lease"]:
        """Generates LeaseSpecs from plans and instantiates initial Lease objects.

        1. Gets input LeaseSpecs directly from RentRoll.
        2. Generates LeaseSpecs from any AbsorptionPlans.
        3. Combines all LeaseSpecs.
        4. Instantiates Lease objects from specs that overlap the analysis period.
        5. Caches the instantiated Lease objects.

        Returns:
            A list of instantiated Lease objects representing the first term
            of each relevant lease chain.
        """
        # Check cache first
        if self._cached_initial_lease_objects is not None:
            logger.debug("Returning cached initial lease objects.")
            return self._cached_initial_lease_objects

        logger.info("Preparing initial Lease objects from specs...")

        # --- Step 1: Get LeaseSpecs from Input RentRoll --- #
        input_lease_specs = (
            self.property.rent_roll.leases if self.property.rent_roll else []
        )
        logger.debug(
            f"Retrieved {len(input_lease_specs)} LeaseSpecs from input RentRoll."
        )

        # --- Step 2: Generate LeaseSpecs from Absorption Plans --- #
        absorption_lease_specs: List["LeaseSpec"] = []
        if self.absorption_plans:
            logger.debug(
                f"Processing {len(self.absorption_plans)} absorption plan(s)..."
            )
            vacant_inventory = (
                self.property.rent_roll.vacant_suites if self.property.rent_roll else []
            )

            # Precedence Check: Filter inventory based on input specs
            input_spec_suites = {
                spec.suite
                for spec in input_lease_specs
                if spec.start_date >= self.analysis_start_date
            }
            available_inventory = [
                suite
                for suite in vacant_inventory
                if suite.suite not in input_spec_suites
            ]
            if len(available_inventory) < len(vacant_inventory):
                logger.debug(
                    f"  Filtered vacant inventory from {len(vacant_inventory)} to {len(available_inventory)} based on input lease specs."
                )

            # Overlap Check & Generation
            processed_suites_by_plans: Set[str] = set()
            current_inventory = available_inventory.copy()
            # Build a basic lookup just for profile resolution if needed by absorption
            plan_lookup_fn = self._build_lookup_fn({})  # Placeholder

            for i, plan in enumerate(self.absorption_plans):
                logger.debug(f"  Running plan {i+1}: '{plan.name}'")
                plan_target_suites_ids = {
                    suite.suite
                    for suite in current_inventory
                    if plan.space_filter.matches(suite)
                }
                overlap = plan_target_suites_ids.intersection(processed_suites_by_plans)
                if overlap:
                    raise ValueError(
                        f"AbsorptionPlan '{plan.name}' targets suites already targeted by a previous plan: {overlap}"
                    )

                plan_specs = plan.generate_lease_specs(
                    available_vacant_suites=current_inventory,
                    analysis_start_date=self.analysis_start_date,
                    analysis_end_date=self.analysis_end_date,
                    lookup_fn=plan_lookup_fn,
                    global_settings=self.settings,
                )
                absorption_lease_specs.extend(plan_specs)

                leased_suites_in_plan = {spec.suite for spec in plan_specs}
                processed_suites_by_plans.update(leased_suites_in_plan)
                current_inventory = [
                    suite
                    for suite in current_inventory
                    if suite.suite not in leased_suites_in_plan
                ]
                logger.debug(
                    f"  Plan '{plan.name}' generated {len(plan_specs)} specs. {len(current_inventory)} suites remaining."
                )

        # --- Step 3: Combine All LeaseSpecs --- #
        all_lease_specs = input_lease_specs + absorption_lease_specs
        logger.debug(f"Total LeaseSpecs prepared: {len(all_lease_specs)}")

        # --- Step 4: Instantiate Lease Objects from Specs --- #
        # Build the main lookup function needed for Lease.from_spec (if it needs profile lookup)
        main_lookup_fn = self._build_lookup_fn({})  # Placeholder for robust lookup

        initial_lease_objects: List["Lease"] = []
        for spec in all_lease_specs:
            spec_end_date = spec.computed_end_date
            # Instantiate only if the *first term* overlaps the analysis period
            if (
                spec.start_date <= self.analysis_end_date
                and spec_end_date >= self.analysis_start_date
            ):
                try:
                    lease_obj = Lease.from_spec(
                        spec=spec,
                        analysis_start_date=self.analysis_start_date,
                        lookup_fn=main_lookup_fn,
                    )
                    initial_lease_objects.append(lease_obj)
                except Exception as e:
                    logger.error(
                        f"Failed to instantiate Lease from spec for tenant '{spec.tenant_name}', suite '{spec.suite}': {e}",
                        exc_info=True,
                    )
                    if self.settings.calculation.fail_on_error:
                        raise
            else:
                logger.debug(
                    f"Skipping instantiation for spec '{spec.tenant_name}' ({spec.start_date} - {spec_end_date}) as its first term falls outside analysis period."
                )

        logger.info(
            f"Prepared {len(initial_lease_objects)} initial Lease objects relevant to analysis period."
        )

        # --- Step 5: Cache the result --- #
        self._cached_initial_lease_objects = initial_lease_objects
        # Clear downstream caches that depend on this
        self._cached_occupancy_series = None
        self._cached_detailed_flows = None
        self._cached_aggregated_flows = None
        self._cached_cash_flow_dataframe = None
        self._cached_detailed_cash_flow_dataframe = None

        return initial_lease_objects
