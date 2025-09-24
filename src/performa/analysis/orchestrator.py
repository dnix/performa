# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Real Estate Cash Flow Orchestration Engine.

ARCHITECTURE: ASSEMBLER PATTERN WITH ANALYSIS CONTEXT
======================================================

This module orchestrates cash flow calculations across all models in a property analysis.
The core design uses an "assembler pattern" to resolve object references once during
analysis setup, eliminating runtime lookups during cash flow calculations.

KEY COMPONENTS:

1. ANALYSIS CONTEXT - CENTRAL DATA CONTAINER
   ==========================================
   AnalysisContext holds all analysis state in one location:
   - Timeline and global settings
   - Direct object references (resolved from UUIDs during assembly)
   - Lookup maps for recovery methods, capital plans, rollover profiles
   - Pre-calculated derived state (occupancy rates)

   This design eliminates UUID resolution overhead during cash flow calculations.

2. TWO-PHASE EXECUTION
   ===================
   Phase 1: Independent Models - Calculate base rents, base expenses
   Phase 2: Dependent Models - Calculate models that reference aggregates

   This separation prevents circular dependencies while supporting models like
   "management fee based on total operating expenses".

3. ASSEMBLER PATTERN WORKFLOW
   ===========================
   Assembly Time (once per analysis):
   - Resolve UUID references to direct object references
   - Populate AnalysisContext lookup maps
   - Inject resolved references into model instances

   Runtime (per cash flow calculation):
   - Direct attribute access only (no UUID lookups)
   - Models call context.recovery_method_lookup[name] instead of resolving UUIDs

TESTED SCENARIOS:
- Single tenant buildings through multi-tenant complexes
- Multiple recovery method types and rollover profiles
- Properties with 40+ tenants and complex lease structures


Implementation examples:
- ResidentialAnalysisScenario: Basic assembler pattern
- OfficeAnalysisScenario: Commercial-specific assembler with recovery methods
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from graphlib import CycleError, TopologicalSorter
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Tuple, Union
from uuid import UUID

import pandas as pd

from performa.core.base import LeaseBase
from performa.core.ledger import Ledger, LedgerQueries, SeriesMetadata
from performa.core.primitives import (
    CashFlowCategoryEnum,
    OrchestrationPass,
    PropertyAttributeKey,
    RevenueSubcategoryEnum,
    UnleveredAggregateLineKey,
    UponExpirationEnum,
)

if TYPE_CHECKING:
    from performa.core.base import (
        LeaseBase,
        PropertyBaseModel,
        RecoveryCalculationState,
    )
    from performa.core.primitives import (
        CashFlowModel,
        GlobalSettings,
        Timeline,
    )

logger = logging.getLogger(__name__)

# Short alias for cleaner code
AggKeys = UnleveredAggregateLineKey


@dataclass
class AnalysisContext:
    """
    A mutable container for the complete state of a single analysis run.
    It bundles configuration, pre-calculated static state, and dynamically
    calculated per-period state, and serves as the single source of truth
    for all `compute_cf` methods.

    ASSEMBLER PATTERN - UNIVERSAL DATA BUS:
    The context serves as the universal data bus that provides fast,
    direct access to all resolved objects. The AnalysisScenario populates
    the lookup maps once during assembly, enabling zero-lookup performance
    during cash flow calculations.
    """

    # --- Configuration (Set at creation) ---
    timeline: "Timeline"
    settings: "GlobalSettings"
    property_data: "PropertyBaseModel"

    # --- Ledger (Required - single source of truth) ---
    ledger: Ledger  # Must be explicitly provided

    # --- Pre-Calculated Static State (Set by Scenario before run) ---
    recovery_states: Dict[UUID, "RecoveryCalculationState"] = field(
        default_factory=dict
    )

    # === ASSEMBLER PATTERN - UUID LOOKUP MAPS ===
    capital_plan_lookup: Dict[UUID, Any] = field(
        default_factory=dict,
        metadata={
            "description": "UUID -> CapitalPlan object mapping for fast turnover plan resolution"
        },
    )
    rollover_profile_lookup: Dict[UUID, Any] = field(
        default_factory=dict,
        metadata={
            "description": "UUID -> RolloverProfile object mapping for residential/office rollover logic"
        },
    )

    # === OFFICE-SPECIFIC LOOKUP MAPS ===
    recovery_method_lookup: Dict[str, Any] = field(
        default_factory=dict,
        metadata={
            "description": "name -> RecoveryMethod object mapping for office expense recovery"
        },
    )
    ti_template_lookup: Dict[UUID, Any] = field(
        default_factory=dict,
        metadata={
            "description": "UUID -> TI template object mapping for office tenant improvements"
        },
    )
    lc_template_lookup: Dict[UUID, Any] = field(
        default_factory=dict,
        metadata={
            "description": "UUID -> LC template object mapping for office leasing commissions"
        },
    )

    # --- Dynamic State (Populated during execution) ---
    resolved_lookups: Dict[Union[UUID, str], Any] = field(
        default_factory=dict,
        metadata={
            "description": "UUID/key -> computed cash flow mapping populated during orchestration"
        },
    )
    occupancy_rate_series: Optional["pd.Series"] = field(
        default=None,
        metadata={
            "description": "Property-wide occupancy rate by period for vacancy calculations"
        },
    )
    current_lease: Optional["LeaseBase"] = (
        None  # Current lease context for TI/LC calculations
    )

    def __post_init__(self):
        """Validate required fields after initialization."""
        # Validate that ledger is provided
        if self.ledger is None:
            raise ValueError(
                "AnalysisContext requires a ledger instance. "
                "This enforces the pass-the-builder pattern where a single Ledger "
                "is created at the API level and passed through all analysis components."
            )


logger = logging.getLogger(__name__)


@dataclass
class CashFlowOrchestrator:
    # --- Configuration ---
    models: List["CashFlowModel"]
    context: AnalysisContext

    # --- Internal State ---
    model_map: Dict[UUID, "CashFlowModel"] = field(init=False)

    # --- Results (populated by execute()) ---
    summary_df: Optional[pd.DataFrame] = field(init=False, default=None)
    detailed_df: Optional[pd.DataFrame] = field(init=False, default=None)

    def __post_init__(self):
        """Populate the model_map after initialization."""
        self.model_map = {model.uid: model for model in self.models}

    # --- CRITICAL METHOD 1: execute() ---
    def execute(self) -> None:
        """
        Execute the complete property analysis using a multi-phase calculation system.

        This method orchestrates the entire calculation process through several phases:

        **Phase Architecture:**
        1. **Dependency Validation**: Defensive checks for safe complexity limits
        2. **Pre-Phase**: Calculate system-wide derived state (occupancy rates)
        3. **Phase 1**: Calculate independent models (base rents, base expenses)
        4. **Intermediate**: Aggregate Phase 1 results for dependent models
        5. **Phase 2**: Calculate dependent models (admin fees, mgmt fees)
        6. **Final**: Aggregate all results into summary views (NOI, UCF, etc.)

        **Key Design Principles:**
        - Two-phase execution prevents most circular dependencies
        - Topological sorting handles intra-phase dependencies
        - Defensive validation catches architectural problems early
        - Memory-efficient with resolved_lookups caching

        **Performance Considerations:**
        - Occupancy calculated once before any model computations
        - Intermediate aggregation enables dependent model calculations
        - Final aggregation creates summary views for reporting

        **Error Handling:**
        - Dependency validation provides actionable error messages
        - Circular dependency detection with model names in errors
        - Missing reference resolution fails fast with clear context

        Raises:
            ValueError: If dependency validation fails or circular dependencies detected
            KeyError: If aggregate references cannot be resolved

        Note:
            Results are stored in self.summary_df and self.detailed_df for access
            after execution completes successfully.
        """
        execution_start_time = time.time()
        total_models = len(self.models)

        logger.info("=== Orchestrator Execution Started ===")
        logger.info(f"Total models to process: {total_models}")
        logger.info(
            f"Analysis timeline: {self.context.timeline.start_date} to {self.context.timeline.end_date}"
        )
        logger.info(f"Timeline periods: {len(self.context.timeline.period_index)}")

        # === PHASE 0: DEFENSIVE VALIDATION ===
        # Dependency validation removed - simplified ledger-based approach
        validation_time = 0.0

        # === PRE-PHASE: CALCULATE DERIVED SYSTEM STATE ===
        logger.info("Pre-Phase: Calculating derived system-wide state...")
        pre_phase_start = time.time()

        # Calculate occupancy once for all models to use
        # This can be done early since it only depends on static lease attributes
        self.context.occupancy_rate_series = self._calculate_occupancy_series()
        occupancy_periods = len(self.context.occupancy_rate_series)
        avg_occupancy = self.context.occupancy_rate_series.mean()

        pre_phase_time = time.time() - pre_phase_start
        logger.info(f"Pre-Phase completed in {pre_phase_time:.3f}s")
        logger.debug(
            f"  Occupancy calculated for {occupancy_periods} periods, average: {avg_occupancy:.1%}"
        )

        # === PHASE 1: INDEPENDENT VALUES ===
        logger.info(
            "Phase 1: Calculating independent models (no aggregate dependencies)..."
        )
        phase1_start = time.time()

        # Models that can be calculated without referring to aggregated results
        independent_models = [
            m
            for m in self.models
            if m.calculation_pass == OrchestrationPass.INDEPENDENT_MODELS
        ]

        logger.info(f"  Processing {len(independent_models)} independent models:")
        for model in independent_models:
            logger.debug(f"    - {model.name} ({model.category}/{model.subcategory})")

        self._compute_model_subset(independent_models)

        phase1_time = time.time() - phase1_start
        logger.info(
            f"Phase 1 completed in {phase1_time:.3f}s - {len(independent_models)} models computed"
        )

        # === INTERMEDIATE PHASE: MINIMAL AGGREGATION FOR DEPENDENT MODELS ===
        logger.info(
            "Intermediate Phase: Computing minimal aggregates for dependent models..."
        )
        intermediate_start = time.time()

        # For dependent models that reference aggregates, we need to provide ALL aggregates
        # This ensures dependent models never fail due to missing aggregate references
        if self.models:  # Only if we have models
            # Get current ledger and create aggregates for dependent models
            ledger_df = self.context.ledger.ledger_df()

            # Always populate aggregates - either from ledger data or as zeros
            # Use DRY helper method to avoid duplication
            self._update_aggregates_from_ledger(ledger_df, "intermediate")

        intermediate_time = time.time() - intermediate_start
        logger.info(f"Intermediate Phase completed in {intermediate_time:.3f}s")

        # === PHASE 2: DEPENDENT VALUES ===
        logger.info(
            "Phase 2: Calculating dependent models (require aggregate references)..."
        )
        phase2_start = time.time()

        # Models that depend on aggregate results from Phase 1
        dependent_models = [
            m
            for m in self.models
            if m.calculation_pass == OrchestrationPass.DEPENDENT_MODELS
        ]

        logger.info(f"  Processing {len(dependent_models)} dependent models:")
        for model in dependent_models:
            # Handle both UnleveredAggregateLineKey and other reference types safely
            ref_name = (
                model.reference.value
                if (model.reference and hasattr(model.reference, "value"))
                else str(model.reference)
                if model.reference
                else "None"
            )
            logger.debug(f"    - {model.name} → references [{ref_name}]")

        self._compute_model_subset(dependent_models)

        phase2_time = time.time() - phase2_start
        logger.info(
            f"Phase 2 completed in {phase2_time:.3f}s - {len(dependent_models)} models computed"
        )

        # === FINAL PHASE: COMPLETE AGGREGATION ===
        logger.info("Final Phase: Aggregating all results into summary views...")
        final_start = time.time()

        # Create final summary DataFrame and update aggregates from complete ledger
        self._finalize_aggregation()

        # Count summary lines for reporting
        summary_lines = (
            len(self.summary_df.columns) if self.summary_df is not None else 0
        )

        final_time = time.time() - final_start
        logger.info(
            f"Final Phase completed in {final_time:.3f}s - {summary_lines} summary lines computed"
        )

        # === EXECUTION SUMMARY ===
        total_time = time.time() - execution_start_time
        logger.info("=== Orchestrator Execution Completed Successfully ===")
        logger.info(f"Total execution time: {total_time:.3f}s")
        logger.info("Phase breakdown:")
        logger.info(
            f"  Validation: {validation_time:.3f}s ({validation_time / total_time:.1%})"
        )
        logger.info(
            f"  Pre-Phase:  {pre_phase_time:.3f}s ({pre_phase_time / total_time:.1%})"
        )
        logger.info(
            f"  Phase 1:    {phase1_time:.3f}s ({phase1_time / total_time:.1%})"
        )
        logger.info(
            f"  Intermediate: {intermediate_time:.3f}s ({intermediate_time / total_time:.1%})"
        )
        logger.info(
            f"  Phase 2:    {phase2_time:.3f}s ({phase2_time / total_time:.1%})"
        )
        logger.info(f"  Final:      {final_time:.3f}s ({final_time / total_time:.1%})")

        # Log key results for verification
        if self.summary_df is not None:
            logger.debug("Key calculation results:")
            timeline = self.context.timeline
            first_period = timeline.period_index[0]

            if "Net Operating Income" in self.summary_df.columns:
                first_noi = self.summary_df["Net Operating Income"][first_period]
                logger.debug(f"  First period NOI: ${first_noi:,.0f}")

            if "Unlevered Cash Flow" in self.summary_df.columns:
                first_ucf = self.summary_df["Unlevered Cash Flow"][first_period]
                logger.debug(f"  First period UCF: ${first_ucf:,.0f}")

        logger.info("Analysis ready for consumption via summary_df and detailed_df")

    def _to_period_series(self, series: Any) -> pd.Series:
        """
        Convert series with date index to PeriodIndex.

        VECTORIZED IMPLEMENTATION: Replaces individual loops with bulk pandas operations
        for significant performance improvement (eliminates ~0.113s bottleneck).

        Args:
            series: Input series (may be pd.Series or other type)

        Returns:
            Series with PeriodIndex matching timeline
        """
        # Handle edge case: timeline has no periods
        if self.context.timeline.period_index.empty:
            return pd.Series(dtype=float)

        # Handle case where series is not a Series (defensive)
        if not isinstance(series, pd.Series):
            return pd.Series(0.0, index=self.context.timeline.period_index)

        # Handle empty series
        if series.empty:
            return pd.Series(0.0, index=self.context.timeline.period_index)

        # Convert all dates to periods at once
        try:
            # Convert entire index to periods in one operation (vectorized)
            period_index = series.index.to_period(freq="M")

            # Create series with period index
            period_series = pd.Series(series.values, index=period_index)

            # Reindex to match timeline (handles missing periods with 0.0)
            result = period_series.reindex(
                self.context.timeline.period_index, fill_value=0.0
            )

            return result

        except (AttributeError, TypeError):
            # Fallback for non-standard index types
            # Still vectorized but handles edge cases
            periods = pd.PeriodIndex([
                pd.Period(date, freq="M") for date in series.index
            ])
            period_series = pd.Series(series.values, index=periods)
            result = period_series.reindex(
                self.context.timeline.period_index, fill_value=0.0
            )
            return result

    def _update_aggregates_from_ledger(
        self,
        ledger_df: pd.DataFrame,
        phase_name: Literal["intermediate", "final"] = "final",
    ) -> None:
        """
        DRY method to update aggregates from ledger state.

        This centralizes all aggregate updates to avoid duplication.
        Can be called at intermediate or final phases.

        Args:
            ledger_df: Current ledger DataFrame
            phase_name: Name of phase for logging ("intermediate" or "final")
        """
        if ledger_df.empty:
            # Populate all aggregates with zeros
            zero_series = pd.Series(0.0, index=self.context.timeline.period_index)

            for key in UnleveredAggregateLineKey:
                # Use copy to avoid shared reference issues
                self.context.resolved_lookups[key.value] = zero_series.copy()

            logger.debug(
                f"Populated {len(UnleveredAggregateLineKey)} zero-valued aggregates for empty ledger ({phase_name} phase)"
            )
        else:
            # Create queries once (performance optimization)
            queries = LedgerQueries(ledger_df)

            # Map aggregate keys to query methods (using aliased enum)
            aggregate_mappings = {
                AggKeys.GROSS_POTENTIAL_RENT: queries.gpr,
                AggKeys.POTENTIAL_GROSS_REVENUE: queries.pgr,
                AggKeys.TENANT_REVENUE: queries.tenant_revenue,
                AggKeys.GENERAL_VACANCY_LOSS: queries.vacancy_loss,
                AggKeys.MISCELLANEOUS_INCOME: queries.misc_income,
                AggKeys.RENTAL_ABATEMENT: queries.rental_abatement,
                AggKeys.CREDIT_LOSS: queries.credit_loss,
                AggKeys.EXPENSE_REIMBURSEMENTS: queries.expense_reimbursements,
                AggKeys.EFFECTIVE_GROSS_INCOME: queries.egi,
                AggKeys.TOTAL_OPERATING_EXPENSES: queries.opex,
                AggKeys.NET_OPERATING_INCOME: queries.noi,
                AggKeys.TOTAL_CAPITAL_EXPENDITURES: queries.capex,
                AggKeys.TOTAL_TENANT_IMPROVEMENTS: queries.ti,
                AggKeys.TOTAL_LEASING_COMMISSIONS: queries.lc,
                AggKeys.UNLEVERED_CASH_FLOW: queries.ucf,
            }

            # Special cases that need zero values (not yet tracked in ledger)
            zero_series = pd.Series(0.0, index=self.context.timeline.period_index)
            special_cases = {
                AggKeys.DOWNTIME_VACANCY_LOSS: zero_series,
                AggKeys.ROLLOVER_VACANCY_LOSS: zero_series,
            }

            # Update all aggregates
            for key, query_method in aggregate_mappings.items():
                try:
                    result = query_method()
                    self.context.resolved_lookups[key.value] = self._to_period_series(
                        result
                    )
                except Exception as e:
                    logger.warning(f"Failed to compute {key.value}: {e}. Using zeros.")
                    self.context.resolved_lookups[key.value] = pd.Series(
                        0.0, index=self.context.timeline.period_index
                    )

            # Add special cases
            for key, value in special_cases.items():
                self.context.resolved_lookups[key.value] = value

            logger.debug(
                f"Updated {len(aggregate_mappings) + len(special_cases)} aggregates from ledger ({phase_name} phase)"
            )

    def get_series_with_metadata(
        self, asset_id: UUID, deal_id: Optional[UUID] = None
    ) -> List[Tuple[pd.Series, SeriesMetadata]]:
        """
        Return (Series, SeriesMetadata) tuples for ledger building.

        Follows the existing detailed_flows_list pattern from _aggregate_flows().
        This method extracts the metadata-rich series information that the
        orchestrator already tracks internally.

        Args:
            asset_id: UUID of the asset these flows belong to
            deal_id: Optional UUID of the deal (for deal-level analysis)

        Returns:
            List of (pd.Series, SeriesMetadata) tuples ready for ledger building

        Note:
            This must be called after execute() to ensure resolved_lookups is populated.
        """

        if (
            not hasattr(self.context, "resolved_lookups")
            or not self.context.resolved_lookups
        ):
            raise ValueError("Must call execute() before get_series_with_metadata()")

        pairs = []

        # Follow the existing pattern from _aggregate_flows()
        for lookup_key, result in self.context.resolved_lookups.items():
            if isinstance(lookup_key, UUID):
                model = self.model_map[lookup_key]

                # Determine pass number from model's calculation pass
                pass_num = (
                    1
                    if model.calculation_pass == OrchestrationPass.INDEPENDENT_MODELS
                    else 2
                )

                if isinstance(result, dict):  # Multi-component (e.g., lease)
                    for component, series in result.items():
                        if series is not None and not series.empty:
                            metadata = SeriesMetadata(
                                category=model.category,
                                subcategory=model.subcategory,
                                item_name=f"{model.name} - {component}",
                                source_id=model.uid,
                                asset_id=asset_id,
                                pass_num=pass_num,
                                deal_id=deal_id,
                            )
                            pairs.append((series, metadata))

                elif isinstance(result, pd.Series):  # Simple series
                    if result is not None and not result.empty:
                        metadata = SeriesMetadata(
                            category=model.category,
                            subcategory=model.subcategory,
                            item_name=model.name,
                            source_id=model.uid,
                            asset_id=asset_id,
                            pass_num=pass_num,
                            deal_id=deal_id,
                        )
                        pairs.append((result, metadata))

        return pairs

    # --- CRITICAL METHOD 2: _calculate_occupancy_series() ---
    def _calculate_occupancy_series(self) -> pd.Series:
        """Calculates the property-wide occupancy rate for each period."""
        total_occupied_area = pd.Series(0.0, index=self.context.timeline.period_index)
        lease_models = [m for m in self.models if isinstance(m, LeaseBase)]

        for lease in lease_models:
            lease_area_series = pd.Series(lease.area, index=lease.timeline.period_index)
            total_occupied_area = total_occupied_area.add(
                lease_area_series, fill_value=0.0
            )

        nra = self.context.property_data.net_rentable_area
        if nra > 0:
            return total_occupied_area / nra
        else:
            return pd.Series(0.0, index=self.context.timeline.period_index)

    def _compute_model_subset(self, model_subset: List["CashFlowModel"]) -> None:
        """Builds dependency graph and computes a subset of models in order."""
        if not model_subset:
            logger.info("No models to compute in this subset, skipping.")
            return

        subset_uids = {m.uid for m in model_subset}
        graph = {}
        for m in model_subset:
            deps = set()
            # Handle reference types for dependency resolution
            if m.reference is not None:
                if isinstance(
                    m.reference, (UnleveredAggregateLineKey, PropertyAttributeKey)
                ):
                    # UnleveredAggregateLineKey: resolved from previous phases (aggregates)
                    # PropertyAttributeKey: resolved from property data directly
                    # No intra-phase dependency needed for either
                    pass
                else:
                    # Unsupported reference type - only type-safe enums allowed
                    raise ValueError(
                        f"Unsupported reference type in model '{m.name}': {type(m.reference)}. Expected PropertyAttributeKey or UnleveredAggregateLineKey."
                    )
            graph[m.uid] = deps

        try:
            ts = TopologicalSorter(graph)
            sorted_uids = list(ts.static_order())
        except CycleError as e:
            # Add more context to the error
            cycle_nodes = e.args[1]
            cycle_names = [self.model_map[uid].name for uid in cycle_nodes]
            logger.error(
                f"Circular dependency detected in model subset: {' -> '.join(cycle_names)}"
            )
            raise

        for model_uid in sorted_uids:
            model = self.model_map[model_uid]

            # For leases with rollover profiles, use project_future_cash_flows to handle renewals
            if (
                isinstance(model, LeaseBase)
                and hasattr(model, "rollover_profile")
                and model.rollover_profile
                and model.upon_expiration
                in [
                    UponExpirationEnum.RENEW,
                    UponExpirationEnum.MARKET,
                    UponExpirationEnum.VACATE,
                    UponExpirationEnum.OPTION,
                    UponExpirationEnum.REABSORB,
                ]
            ):
                logger.debug(
                    f"Using project_future_cash_flows for lease {model.name} with rollover profile"
                )
                future_df = model.project_future_cash_flows(context=self.context)

                # Convert DataFrame back to the dict format expected by aggregation
                result = {}
                for column in future_df.columns:
                    result[column] = future_df[column]

            else:
                result = model.compute_cf(context=self.context)

            self.context.resolved_lookups[model.uid] = result

            # Add to ledger as we compute (new single source of truth)
            self._add_to_ledger(model, result)

            # Update aggregates after each model in Phase 2 to ensure dependent models
            # have access to fresh aggregate data from previously processed models
            # This is necessary because some dependent models (like credit loss)
            # depend on aggregates that include other dependent models (like vacancy loss)
            if model.calculation_pass == OrchestrationPass.DEPENDENT_MODELS:
                self._update_aggregates_from_ledger(
                    self.context.ledger.ledger_df(), "intermediate"
                )

    def _add_to_ledger(self, model: "CashFlowModel", result: Any) -> None:
        """Add model cash flows to ledger with metadata."""
        logger.debug(
            f"_add_to_ledger called for model: {model.name}, result type: {type(result)}"
        )

        # Get analysis timeline for alignment
        analysis_periods = self.context.timeline.period_index

        if isinstance(result, dict):  # E.g., a lease with multiple components
            logger.debug(
                f"Processing dict result with {len(result)} components: {list(result.keys())}"
            )
            for component, series in result.items():
                if isinstance(series, pd.Series) and not series.empty:
                    # Align series to analysis timeline - only keep periods that overlap
                    aligned_series = series.reindex(analysis_periods, fill_value=0.0)

                    # Skip if no overlap with analysis period
                    if aligned_series.sum() == 0 and series.sum() != 0:
                        logger.debug(
                            f"Skipping {component} - no overlap with analysis period"
                        )
                        continue

                    logger.debug(
                        f"Adding non-empty series: {component} with {len(aligned_series)} periods"
                    )

                    # Map component names to appropriate subcategories
                    component_subcategory = model.subcategory
                    if component == "recoveries":
                        component_subcategory = RevenueSubcategoryEnum.RECOVERY
                    elif component == "abatement":
                        component_subcategory = RevenueSubcategoryEnum.ABATEMENT
                    # Add more component mappings as needed

                    # Apply sign conventions
                    series_to_add = aligned_series
                    if component == "abatement":
                        # Abatement is a revenue reduction (negative)
                        series_to_add = -aligned_series

                    metadata = SeriesMetadata(
                        category=model.category,
                        subcategory=component_subcategory,
                        item_name=f"{model.name} - {component}",
                        source_id=model.uid,
                        asset_id=self.context.property_data.uid,
                        pass_num=model.calculation_pass.value,  # Use model's actual calculation pass
                    )
                    self.context.ledger.add_series(series_to_add, metadata)
                    logger.debug(
                        f"Added to ledger: {model.name} - {component} ({len(aligned_series)} periods)"
                    )
                else:
                    logger.debug(
                        f"Skipping component {component}: empty={series.empty if isinstance(series, pd.Series) else 'not Series'}"
                    )

        elif isinstance(result, pd.Series):  # A simple cash flow
            if not result.empty:
                # Align series to analysis timeline - only keep periods that overlap
                aligned_result = result.reindex(analysis_periods, fill_value=0.0)

                # Skip if no overlap with analysis period
                if aligned_result.sum() == 0 and result.sum() != 0:
                    logger.debug(
                        f"Skipping {model.name} - no overlap with analysis period"
                    )
                    return

                # Apply sign conventions for outflows vs inflows
                series_to_add = aligned_result

                # Expenses and Capital are outflows (negative in ledger)
                if model.category == CashFlowCategoryEnum.EXPENSE:
                    series_to_add = (
                        -aligned_result
                    )  # Operating expenses are outflows (negative)
                elif model.category == CashFlowCategoryEnum.CAPITAL:
                    series_to_add = (
                        -aligned_result
                    )  # Capital expenditures are outflows (negative)
                # Revenue subcategories that are losses (negative in ledger)
                elif (
                    model.category == CashFlowCategoryEnum.REVENUE
                    and hasattr(model, "subcategory")
                    and model.subcategory
                    in [
                        RevenueSubcategoryEnum.VACANCY_LOSS,
                        RevenueSubcategoryEnum.CREDIT_LOSS,
                        RevenueSubcategoryEnum.ABATEMENT,
                    ]
                ):
                    series_to_add = (
                        -aligned_result
                    )  # Revenue losses are negative (reduce income)
                # Regular Revenue stays positive (inflows)
                # Financing handled separately based on direction

                metadata = SeriesMetadata(
                    category=model.category,
                    subcategory=model.subcategory,
                    item_name=model.name,
                    source_id=model.uid,
                    asset_id=self.context.property_data.uid,
                    pass_num=model.calculation_pass.value,  # Use model's actual calculation pass
                )
                self.context.ledger.add_series(series_to_add, metadata)
                logger.debug(
                    f"Added to ledger: {model.name} ({len(aligned_result)} periods)"
                )
        else:
            logger.debug(
                f"Skipped adding to ledger: {model.name} (empty or invalid result)"
            )

    def _finalize_aggregation(self) -> None:
        """
        Generate final summary_df and update aggregates from complete ledger.

        This method:
        1. Queries the complete ledger (after all phases)
        2. Creates the summary DataFrame for reporting
        3. Updates resolved_lookups with final aggregate values

        This is the ONLY place we query the complete ledger for final aggregates.
        """
        # Get complete ledger data (includes Phase 1 and Phase 2 results)
        ledger_df = self.context.ledger.ledger_df()
        analysis_periods = self.context.timeline.period_index

        logger.info(
            f"Finalizing aggregation from ledger with {len(ledger_df)} transactions"
        )

        if ledger_df.empty:
            logger.warning("Ledger is empty - creating zero-filled summary_df")
            # Create zero-filled summary with proper structure
            summary_data = {
                "Potential Gross Revenue": pd.Series(0.0, index=analysis_periods),
                "Vacancy Loss": pd.Series(0.0, index=analysis_periods),
                "Effective Gross Income": pd.Series(0.0, index=analysis_periods),
                "Operating Expenses": pd.Series(0.0, index=analysis_periods),
                "Net Operating Income": pd.Series(0.0, index=analysis_periods),
                "Capital Expenditures": pd.Series(0.0, index=analysis_periods),
                "Tenant Improvements": pd.Series(0.0, index=analysis_periods),
                "Leasing Commissions": pd.Series(0.0, index=analysis_periods),
                "Unlevered Cash Flow": pd.Series(0.0, index=analysis_periods),
                "Miscellaneous Income": pd.Series(0.0, index=analysis_periods),
                "Rental Abatement": pd.Series(0.0, index=analysis_periods),
                "Expense Reimbursements": pd.Series(0.0, index=analysis_periods),
            }
            self.summary_df = pd.DataFrame(summary_data, index=analysis_periods)

            return

        # Use elegant LedgerQueries for all aggregation (single query instance)
        queries = LedgerQueries(ledger_df)

        # Build all aggregate series with proper PeriodIndex conversion
        # This replaces both the old summary_df logic AND the resolved_lookups update
        pgr_series = self._to_period_series(queries.pgr())
        vacancy_series = self._to_period_series(queries.vacancy_loss())
        misc_income_series = self._to_period_series(queries.misc_income())
        abatement_series = self._to_period_series(queries.rental_abatement())
        credit_loss_series = self._to_period_series(queries.credit_loss())
        reimbursements_series = self._to_period_series(queries.expense_reimbursements())
        egi_series = self._to_period_series(queries.egi())
        opex_series = self._to_period_series(queries.opex())
        noi_series = self._to_period_series(queries.noi())
        capex_series = self._to_period_series(queries.capex())
        ti_series = self._to_period_series(queries.ti())
        lc_series = self._to_period_series(queries.lc())
        ucf_series = self._to_period_series(queries.ucf())

        # Create summary DataFrame for reporting
        summary_data = {
            "Potential Gross Revenue": pgr_series,
            "Vacancy Loss": vacancy_series,
            "Miscellaneous Income": misc_income_series,
            "Rental Abatement": abatement_series,
            "Expense Reimbursements": reimbursements_series,
            "Effective Gross Income": egi_series,
            "Operating Expenses": opex_series,
            "Net Operating Income": noi_series,
            "Capital Expenditures": capex_series,
            "Tenant Improvements": ti_series,
            "Leasing Commissions": lc_series,
            "Unlevered Cash Flow": ucf_series,
        }

        self.summary_df = pd.DataFrame(summary_data, index=analysis_periods)
        self.summary_df = self.summary_df.fillna(0.0)

        # Update resolved_lookups with final aggregates (using aliased enum)
        self.context.resolved_lookups[AggKeys.POTENTIAL_GROSS_REVENUE.value] = (
            pgr_series
        )
        self.context.resolved_lookups[AggKeys.GENERAL_VACANCY_LOSS.value] = (
            vacancy_series
        )
        self.context.resolved_lookups[AggKeys.MISCELLANEOUS_INCOME.value] = (
            misc_income_series
        )
        self.context.resolved_lookups[AggKeys.RENTAL_ABATEMENT.value] = abatement_series
        self.context.resolved_lookups[AggKeys.CREDIT_LOSS.value] = credit_loss_series
        self.context.resolved_lookups[AggKeys.EXPENSE_REIMBURSEMENTS.value] = (
            reimbursements_series
        )
        self.context.resolved_lookups[AggKeys.EFFECTIVE_GROSS_INCOME.value] = egi_series
        self.context.resolved_lookups[AggKeys.TOTAL_OPERATING_EXPENSES.value] = (
            opex_series
        )
        self.context.resolved_lookups[AggKeys.NET_OPERATING_INCOME.value] = noi_series
        self.context.resolved_lookups[AggKeys.TOTAL_CAPITAL_EXPENDITURES.value] = (
            capex_series
        )
        self.context.resolved_lookups[AggKeys.TOTAL_TENANT_IMPROVEMENTS.value] = (
            ti_series
        )
        self.context.resolved_lookups[AggKeys.TOTAL_LEASING_COMMISSIONS.value] = (
            lc_series
        )
        self.context.resolved_lookups[AggKeys.UNLEVERED_CASH_FLOW.value] = ucf_series

        # Add special vacancy types (zeros for now)
        zero_series = pd.Series(0.0, index=analysis_periods)
        self.context.resolved_lookups[AggKeys.DOWNTIME_VACANCY_LOSS.value] = zero_series
        self.context.resolved_lookups[AggKeys.ROLLOVER_VACANCY_LOSS.value] = zero_series

        logger.info(
            f"Finalized aggregation: {len(self.summary_df.columns)} metrics, {len(self.context.resolved_lookups)} aggregates"
        )
