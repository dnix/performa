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
- Maintains backward compatibility with existing models

Implementation examples:
- ResidentialAnalysisScenario: Basic assembler pattern
- OfficeAnalysisScenario: Commercial-specific assembler with recovery methods
"""

from __future__ import annotations

import inspect
import logging
import time
from dataclasses import dataclass, field
from graphlib import CycleError, TopologicalSorter
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union
from uuid import UUID

import pandas as pd

from performa.core.primitives import (
    CalculationPass,
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
        ExpenseSubcategoryEnum,
        GlobalSettings,
        RevenueSubcategoryEnum,
        Timeline,
    )

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

    # --- Pre-Calculated Static State (Set by Scenario before run) ---
    recovery_states: Dict[UUID, "RecoveryCalculationState"] = field(default_factory=dict)
    
    # === ASSEMBLER PATTERN - UUID LOOKUP MAPS ===
    capital_plan_lookup: Dict[UUID, Any] = field(
        default_factory=dict,
        metadata={"description": "UUID -> CapitalPlan object mapping for fast turnover plan resolution"}
    )
    rollover_profile_lookup: Dict[UUID, Any] = field(
        default_factory=dict,
        metadata={"description": "UUID -> RolloverProfile object mapping for residential/office rollover logic"}
    )
    
    # === OFFICE-SPECIFIC LOOKUP MAPS ===
    recovery_method_lookup: Dict[str, Any] = field(
        default_factory=dict,
        metadata={"description": "name -> RecoveryMethod object mapping for office expense recovery"}
    )
    ti_template_lookup: Dict[UUID, Any] = field(
        default_factory=dict,
        metadata={"description": "UUID -> TI template object mapping for office tenant improvements"}
    )
    lc_template_lookup: Dict[UUID, Any] = field(
        default_factory=dict,
        metadata={"description": "UUID -> LC template object mapping for office leasing commissions"}
    )

    # --- Dynamic State (Populated during execution) ---
    resolved_lookups: Dict[Union[UUID, str], Any] = field(
        default_factory=dict,
        metadata={"description": "UUID/key -> computed cash flow mapping populated during orchestration"}
    )
    occupancy_rate_series: Optional["pd.Series"] = field(
        default=None,
        metadata={"description": "Property-wide occupancy rate by period for vacancy calculations"}
    )
    current_lease: Optional["LeaseBase"] = None  # Current lease context for TI/LC calculations

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
        logger.info(f"Analysis timeline: {self.context.timeline.start_date} to {self.context.timeline.end_date}")
        logger.info(f"Timeline periods: {len(self.context.timeline.period_index)}")

        # === PHASE 0: DEFENSIVE VALIDATION ===
        logger.info("Phase 0: Validating dependency complexity for safety...")
        validation_start = time.time()
        self._validate_dependency_complexity()
        validation_time = time.time() - validation_start
        logger.info(f"Phase 0 completed in {validation_time:.3f}s - All dependency chains within safe limits")

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
        logger.debug(f"  Occupancy calculated for {occupancy_periods} periods, average: {avg_occupancy:.1%}")

        # === PHASE 1: INDEPENDENT VALUES ===
        logger.info("Phase 1: Calculating independent models (no aggregate dependencies)...")
        phase1_start = time.time()
        
        # Models that can be calculated without referring to aggregated results
        independent_models = [
            m for m in self.models
            if m.calculation_pass == CalculationPass.INDEPENDENT_VALUES
        ]
        
        logger.info(f"  Processing {len(independent_models)} independent models:")
        for model in independent_models:
            logger.debug(f"    - {model.name} ({model.category}/{model.subcategory})")
        
        self._compute_model_subset(independent_models)
        
        phase1_time = time.time() - phase1_start
        logger.info(f"Phase 1 completed in {phase1_time:.3f}s - {len(independent_models)} models computed")

        # === INTERMEDIATE PHASE: AGGREGATE FOR DEPENDENT MODELS ===
        logger.info("Intermediate Phase: Computing aggregates for dependent model references...")
        intermediate_start = time.time()
        
        # Create intermediate aggregates that dependent models will reference
        # Example: Total OpEx aggregate needed by admin fee models
        self._compute_intermediate_aggregates()
        
        # Count available aggregates for dependent models
        aggregate_count = sum(1 for key in self.context.resolved_lookups.keys() 
                            if isinstance(key, str) and not key.startswith('_'))
        
        intermediate_time = time.time() - intermediate_start
        logger.info(f"Intermediate Phase completed in {intermediate_time:.3f}s - {aggregate_count} aggregates computed")

        # === PHASE 2: DEPENDENT VALUES ===
        logger.info("Phase 2: Calculating dependent models (require aggregate references)...")
        phase2_start = time.time()
        
        # Models that depend on aggregate results from Phase 1
        dependent_models = [
            m for m in self.models
            if m.calculation_pass == CalculationPass.DEPENDENT_VALUES
        ]
        
        logger.info(f"  Processing {len(dependent_models)} dependent models:")
        for model in dependent_models:
            # Handle both UnleveredAggregateLineKey and other reference types safely
            ref_name = model.reference.value if (model.reference and hasattr(model.reference, 'value')) else str(model.reference) if model.reference else "None"
            logger.debug(f"    - {model.name} → references [{ref_name}]")
        
        self._compute_model_subset(dependent_models)
        
        phase2_time = time.time() - phase2_start
        logger.info(f"Phase 2 completed in {phase2_time:.3f}s - {len(dependent_models)} models computed")

        # === FINAL PHASE: COMPLETE AGGREGATION ===
        logger.info("Final Phase: Aggregating all results into summary views...")
        final_start = time.time()
        
        # Create final summary DataFrame with all aggregate lines
        self._aggregate_flows()
        
        # Count summary lines for reporting
        summary_lines = len(self.summary_df.columns) if self.summary_df is not None else 0
        
        final_time = time.time() - final_start
        logger.info(f"Final Phase completed in {final_time:.3f}s - {summary_lines} summary lines computed")

        # === EXECUTION SUMMARY ===
        total_time = time.time() - execution_start_time
        logger.info("=== Orchestrator Execution Completed Successfully ===")
        logger.info(f"Total execution time: {total_time:.3f}s")
        logger.info("Phase breakdown:")
        logger.info(f"  Validation: {validation_time:.3f}s ({validation_time/total_time:.1%})")
        logger.info(f"  Pre-Phase:  {pre_phase_time:.3f}s ({pre_phase_time/total_time:.1%})")
        logger.info(f"  Phase 1:    {phase1_time:.3f}s ({phase1_time/total_time:.1%})")
        logger.info(f"  Intermediate: {intermediate_time:.3f}s ({intermediate_time/total_time:.1%})")
        logger.info(f"  Phase 2:    {phase2_time:.3f}s ({phase2_time/total_time:.1%})")
        logger.info(f"  Final:      {final_time:.3f}s ({final_time/total_time:.1%})")
        
        # Log key results for verification
        if self.summary_df is not None:
            logger.debug("Key calculation results:")
            timeline = self.context.timeline
            first_period = timeline.period_index[0]
            
            if 'Net Operating Income' in self.summary_df.columns:
                first_noi = self.summary_df['Net Operating Income'][first_period]
                logger.debug(f"  First period NOI: ${first_noi:,.0f}")
            
            if 'Unlevered Cash Flow' in self.summary_df.columns:
                first_ucf = self.summary_df['Unlevered Cash Flow'][first_period]
                logger.debug(f"  First period UCF: ${first_ucf:,.0f}")

        logger.info("Analysis ready for consumption via summary_df and detailed_df")

    # --- CRITICAL METHOD 2: _calculate_occupancy_series() ---
    def _calculate_occupancy_series(self) -> pd.Series:
        """Calculates the property-wide occupancy rate for each period."""
        from performa.core.base import LeaseBase
        total_occupied_area = pd.Series(0.0, index=self.context.timeline.period_index)
        lease_models = [m for m in self.models if isinstance(m, LeaseBase)]
        
        for lease in lease_models:
            lease_area_series = pd.Series(lease.area, index=lease.timeline.period_index)
            total_occupied_area = total_occupied_area.add(lease_area_series, fill_value=0.0)
            
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
            # Handle UnleveredAggregateLineKey references for dependency resolution
            if m.reference is not None:
                if isinstance(m.reference, UnleveredAggregateLineKey):
                    # UnleveredAggregateLineKey references are resolved from previous phases
                    # No intra-phase dependency needed since aggregates are computed after phases
                    pass
                else:
                    # Unsupported reference type - should not happen with Pydantic validator
                    raise ValueError(f"Unsupported reference type in model '{m.name}': {type(m.reference)}. Expected UnleveredAggregateLineKey.")
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
            from performa.core.base import LeaseBase
            if (isinstance(model, LeaseBase) and 
                hasattr(model, 'rollover_profile') and 
                model.rollover_profile and 
                model.upon_expiration in [
                    UponExpirationEnum.RENEW,
                    UponExpirationEnum.MARKET,
                    UponExpirationEnum.VACATE,
                    UponExpirationEnum.OPTION,
                    UponExpirationEnum.REABSORB,
                ]
            ):
                
                logger.debug(f"Using project_future_cash_flows for lease {model.name} with rollover profile")
                future_df = model.project_future_cash_flows(context=self.context)
                
                # Convert DataFrame back to the dict format expected by aggregation
                result = {}
                for column in future_df.columns:
                    result[column] = future_df[column]
                    
            else:
                result = model.compute_cf(context=self.context)
                
            self.context.resolved_lookups[model.uid] = result

    # --- CRITICAL METHOD 4: _aggregate_flows() ---
    def _aggregate_flows(self) -> None:
        """Aggregates all computed cash flows into summary and detailed dataframes."""
        # This logic is ported directly from the old orchestrator, but now reads
        # from self.context.resolved_lookups and writes to self.summary_df.
        
        # 1. Initialize summary lines
        analysis_periods = self.context.timeline.period_index
        agg_flows: Dict[UnleveredAggregateLineKey, pd.Series] = {
            key: pd.Series(0.0, index=analysis_periods, name=key.value)
            for key in UnleveredAggregateLineKey if not key.value.startswith("_")
        }
        
        detailed_flows_list = []

        # 2. Iterate through resolved lookups to populate raw aggregates
        for lookup_key, result in self.context.resolved_lookups.items():
            # Handle both UUID and string keys in resolved_lookups
            if isinstance(lookup_key, UUID):
                model = self.model_map[lookup_key]
                if isinstance(result, dict): # E.g., a lease with multiple components
                    for component, series in result.items():
                        # Detailed logging
                        detailed_flows_list.append({"name": model.name, "uid": lookup_key, "category": model.category, "subcategory": model.subcategory, "component": component, "series": series})
                        # Aggregation
                        target_key = self._get_aggregate_key(model.category, model.subcategory, component)
                        if target_key:
                            agg_flows[target_key] = agg_flows[target_key].add(series.reindex(analysis_periods, fill_value=0.0), fill_value=0.0)
                elif isinstance(result, pd.Series): # A simple cash flow
                    detailed_flows_list.append({"name": model.name, "uid": lookup_key, "category": model.category, "subcategory": model.subcategory, "component": "value", "series": result})
                    target_key = self._get_aggregate_key(model.category, model.subcategory)
                    if target_key:
                        agg_flows[target_key] = agg_flows[target_key].add(result.reindex(analysis_periods, fill_value=0.0), fill_value=0.0)

        # 3. Apply property-level losses
        self._apply_property_losses(agg_flows)

        # 4. Calculate derived summary lines (NOI, UCF, etc.)
        
        # Calculate canonical Effective Gross Income (industry standard)
        agg_flows[UnleveredAggregateLineKey.EFFECTIVE_GROSS_INCOME] = (
            agg_flows[UnleveredAggregateLineKey.POTENTIAL_GROSS_REVENUE] 
            - agg_flows[UnleveredAggregateLineKey.RENTAL_ABATEMENT] 
            - agg_flows[UnleveredAggregateLineKey.GENERAL_VACANCY_LOSS]
            - agg_flows[UnleveredAggregateLineKey.COLLECTION_LOSS]
            + agg_flows[UnleveredAggregateLineKey.MISCELLANEOUS_INCOME] 
            + agg_flows[UnleveredAggregateLineKey.EXPENSE_REIMBURSEMENTS]
        )
        agg_flows[UnleveredAggregateLineKey.NET_OPERATING_INCOME] = agg_flows[UnleveredAggregateLineKey.EFFECTIVE_GROSS_INCOME] - agg_flows[UnleveredAggregateLineKey.TOTAL_OPERATING_EXPENSES]
        agg_flows[UnleveredAggregateLineKey.UNLEVERED_CASH_FLOW] = agg_flows[UnleveredAggregateLineKey.NET_OPERATING_INCOME] - agg_flows[UnleveredAggregateLineKey.TOTAL_CAPITAL_EXPENDITURES] - agg_flows[UnleveredAggregateLineKey.TOTAL_TENANT_IMPROVEMENTS] - agg_flows[UnleveredAggregateLineKey.TOTAL_LEASING_COMMISSIONS]
        
        # 5. Store aggregate results in resolved_lookups for cross-reference
        for key, series in agg_flows.items():
            self.context.resolved_lookups[key.value] = series
        
        # 6. Store final DataFrames
        self.summary_df = pd.DataFrame(agg_flows)
        # self.detailed_df = ... (logic to create detailed dataframe from detailed_flows_list)
    
    def _apply_property_losses(self, agg_flows: Dict[UnleveredAggregateLineKey, pd.Series]) -> None:
        """Apply property-level vacancy and collection losses."""
        if not hasattr(self.context.property_data, 'losses') or not self.context.property_data.losses:
            return
        
        losses = self.context.property_data.losses
        
        # Calculate General Vacancy Loss
        if losses.general_vacancy and losses.general_vacancy.rate > 0:
            vacancy_rate = losses.general_vacancy.rate
            
            # Apply vacancy loss to the appropriate basis
            if losses.general_vacancy.method.value == "Potential Gross Revenue":
                basis = agg_flows[UnleveredAggregateLineKey.POTENTIAL_GROSS_REVENUE]
            else:  # Effective Gross Revenue method
                basis = (agg_flows[UnleveredAggregateLineKey.POTENTIAL_GROSS_REVENUE] 
                        + agg_flows[UnleveredAggregateLineKey.MISCELLANEOUS_INCOME] 
                        - agg_flows[UnleveredAggregateLineKey.RENTAL_ABATEMENT])
            
            vacancy_loss = basis * vacancy_rate
            agg_flows[UnleveredAggregateLineKey.GENERAL_VACANCY_LOSS] = vacancy_loss
        
        # Calculate Collection Loss
        if losses.collection_loss and losses.collection_loss.rate > 0:
            collection_rate = losses.collection_loss.rate
            
            # Apply collection loss to the appropriate basis
            if losses.collection_loss.basis == "pgr":
                basis = agg_flows[UnleveredAggregateLineKey.POTENTIAL_GROSS_REVENUE]
            elif losses.collection_loss.basis == "scheduled_income":
                basis = (agg_flows[UnleveredAggregateLineKey.POTENTIAL_GROSS_REVENUE] 
                        - agg_flows[UnleveredAggregateLineKey.RENTAL_ABATEMENT])
            else:  # "egi" - Effective Gross Income
                basis = (agg_flows[UnleveredAggregateLineKey.POTENTIAL_GROSS_REVENUE] 
                        - agg_flows[UnleveredAggregateLineKey.RENTAL_ABATEMENT]
                        - agg_flows[UnleveredAggregateLineKey.GENERAL_VACANCY_LOSS]
                        + agg_flows[UnleveredAggregateLineKey.MISCELLANEOUS_INCOME])
            
            collection_loss = basis * collection_rate
            agg_flows[UnleveredAggregateLineKey.COLLECTION_LOSS] = collection_loss

    def _get_aggregate_key(self, category: str, subcategory: str, component: str = 'value') -> Optional[UnleveredAggregateLineKey]:
        # Mapping logic from raw categories to summary lines
        from performa.core.primitives import (
            ExpenseSubcategoryEnum,
            RevenueSubcategoryEnum,
        )
        if category == "Revenue":
            if subcategory == RevenueSubcategoryEnum.LEASE:
                if component == "base_rent": return UnleveredAggregateLineKey.POTENTIAL_GROSS_REVENUE
                if component == "recoveries": return UnleveredAggregateLineKey.EXPENSE_REIMBURSEMENTS
                if component == "abatement": return UnleveredAggregateLineKey.RENTAL_ABATEMENT
            elif subcategory == RevenueSubcategoryEnum.MISC:
                return UnleveredAggregateLineKey.MISCELLANEOUS_INCOME
        elif category == "Expense":
            if subcategory == ExpenseSubcategoryEnum.OPEX: return UnleveredAggregateLineKey.TOTAL_OPERATING_EXPENSES
            if subcategory == ExpenseSubcategoryEnum.CAPEX: return UnleveredAggregateLineKey.TOTAL_CAPITAL_EXPENDITURES
            # Handle special leasing costs from lease object
            if subcategory == "Lease" and component == "ti_allowance": return UnleveredAggregateLineKey.TOTAL_TENANT_IMPROVEMENTS
            if subcategory == "Lease" and component == "leasing_commission": return UnleveredAggregateLineKey.TOTAL_LEASING_COMMISSIONS
        return None

    def _compute_intermediate_aggregates(self) -> None:
        """Compute aggregate values from independent models for use by dependent models."""
        analysis_periods = self.context.timeline.period_index
        
        # Initialize aggregate flows for intermediate computation
        intermediate_agg_flows: Dict[UnleveredAggregateLineKey, pd.Series] = {
            key: pd.Series(0.0, index=analysis_periods, name=key.value)
            for key in UnleveredAggregateLineKey if not key.value.startswith("_")
        }
        
        # Only process independent models that have already been computed
        independent_models = [
            m for m in self.models 
            if m.calculation_pass == CalculationPass.INDEPENDENT_VALUES
        ]
        
        for model in independent_models:
            if model.uid not in self.context.resolved_lookups:
                continue  # Skip if not computed yet
                
            result = self.context.resolved_lookups[model.uid]
            
            if isinstance(result, dict):  # E.g., a lease with multiple components
                for component, series in result.items():
                    target_key = self._get_aggregate_key(model.category, model.subcategory, component)
                    if target_key:
                        intermediate_agg_flows[target_key] = intermediate_agg_flows[target_key].add(
                            series.reindex(analysis_periods, fill_value=0.0), fill_value=0.0
                        )
            elif isinstance(result, pd.Series):  # A simple cash flow
                target_key = self._get_aggregate_key(model.category, model.subcategory)
                if target_key:
                    intermediate_agg_flows[target_key] = intermediate_agg_flows[target_key].add(
                        result.reindex(analysis_periods, fill_value=0.0), fill_value=0.0
                    )
        
        # Calculate derived aggregates that dependent models need to reference
        # Calculate canonical Effective Gross Income for dependent models
        intermediate_agg_flows[UnleveredAggregateLineKey.EFFECTIVE_GROSS_INCOME] = (
            intermediate_agg_flows[UnleveredAggregateLineKey.POTENTIAL_GROSS_REVENUE]
            - intermediate_agg_flows[UnleveredAggregateLineKey.RENTAL_ABATEMENT] 
            - intermediate_agg_flows[UnleveredAggregateLineKey.GENERAL_VACANCY_LOSS]
            - intermediate_agg_flows[UnleveredAggregateLineKey.COLLECTION_LOSS]
            + intermediate_agg_flows[UnleveredAggregateLineKey.MISCELLANEOUS_INCOME] 
            + intermediate_agg_flows[UnleveredAggregateLineKey.EXPENSE_REIMBURSEMENTS]
        )
        
        # CRITICAL: Calculate other derived aggregates that dependent models need
        # Net Operating Income = EGI - Total OpEx  
        intermediate_agg_flows[UnleveredAggregateLineKey.NET_OPERATING_INCOME] = (
            intermediate_agg_flows[UnleveredAggregateLineKey.EFFECTIVE_GROSS_INCOME] - 
            intermediate_agg_flows[UnleveredAggregateLineKey.TOTAL_OPERATING_EXPENSES]
        )
        
        # Unlevered Cash Flow = NOI - CapEx - TI - LC
        intermediate_agg_flows[UnleveredAggregateLineKey.UNLEVERED_CASH_FLOW] = (
            intermediate_agg_flows[UnleveredAggregateLineKey.NET_OPERATING_INCOME] - 
            intermediate_agg_flows[UnleveredAggregateLineKey.TOTAL_CAPITAL_EXPENDITURES] - 
            intermediate_agg_flows[UnleveredAggregateLineKey.TOTAL_TENANT_IMPROVEMENTS] - 
            intermediate_agg_flows[UnleveredAggregateLineKey.TOTAL_LEASING_COMMISSIONS]
        )
        
        # Store intermediate aggregate results in resolved_lookups for dependent models
        for key, series in intermediate_agg_flows.items():
            self.context.resolved_lookups[key.value] = series

    def _validate_dependency_complexity(self) -> None:
        """
        Validate that dependency chains don't exceed configured complexity limits.
        
        This defensive validation prevents several issues:
        1. Circular dependencies that could cause infinite loops
        2. Overly complex calculation graphs that impact performance  
        3. Hard-to-debug dependency chains in Monte Carlo scenarios
        4. Architectural problems that should be restructured
        
        The validation uses configurable limits from CalculationSettings:
        - max_dependency_depth: Maximum allowed chain length (default=2)
        - allow_complex_dependencies: Safety flag for 3+ level chains (default=False)
        
        Examples of dependency chains:
        - Level 0: Base OpEx (Independent)
        - Level 1: Admin Fee → Total OpEx (depends on Level 0 aggregate)
        - Level 2: Mgmt Fee → NOI (depends on Level 1 via Total OpEx)
        
        Raises:
            ValueError: If dependency chains exceed configured limits with detailed
                       guidance on how to resolve the issue.
        
        Note:
            Self-referential aggregates (e.g., Admin Fee contributing to the Total OpEx
            it depends on) are handled correctly and don't count as circular dependencies.
        """
        # Extract configuration from calculation settings
        max_depth = self.context.settings.calculation.max_dependency_depth
        allow_complex = self.context.settings.calculation.allow_complex_dependencies
        
        logger.debug(f"Starting dependency validation: max_depth={max_depth}, allow_complex={allow_complex}")
        
        # Safety override: Prevent accidental complex dependencies without explicit opt-in
        if max_depth > 2 and not allow_complex:
            logger.warning(
                f"max_dependency_depth={max_depth} but allow_complex_dependencies=False. "
                f"Enforcing max_depth=2 for safety. Set allow_complex_dependencies=True to override."
            )
            max_depth = 2
        
        # Validate each model with aggregate references
        models_with_references = [m for m in self.models if m.reference]
        logger.debug(f"Validating {len(models_with_references)} models with aggregate references")
        
        for model in models_with_references:
            # Calculate dependency depth for this model
            depth = self._calculate_dependency_depth(model, set())
            logger.debug(f"Model '{model.name}' has dependency depth: {depth}")
            
            if depth > max_depth:
                # Generate dependency chain for detailed error reporting
                chain = self._trace_dependency_chain(model)
                
                # Provide contextual guidance based on complexity level
                if depth > 2:
                    # Complex dependency guidance - architectural suggestions
                    guidance = (
                        f"Consider:\n"
                        f"  1. Set allow_complex_dependencies=True in CalculationSettings if this is intentional\n"
                        f"  2. Increase max_dependency_depth to {depth} or higher\n"
                        f"  3. Restructure the model to reduce dependency complexity\n"
                        f"  4. Move complex calculations to Deal-level (outside Property model)"
                    )
                else:
                    # Simple dependency guidance - just increase limit
                    guidance = f"Set max_dependency_depth to {depth} or higher in CalculationSettings to allow this dependency chain."
                
                # Log the violation before raising
                logger.error(f"Dependency validation failed for '{model.name}': {depth}-level chain exceeds limit of {max_depth}")
                
                raise ValueError(
                    f"Model '{model.name}' creates a {depth}-level dependency chain: {' → '.join(chain)}. "
                    f"Maximum allowed depth is {max_depth}.\n{guidance}"
                )
        
        # Log successful validation with appropriate level based on complexity
        if max_depth > 2:
            logger.info(f"Complex dependency validation passed (max_depth={max_depth}) for {len(models_with_references)} models")
        else:
            logger.debug(f"Dependency complexity validation passed for {len(models_with_references)} models")

    def _calculate_dependency_depth(self, model: "CashFlowModel", visited: set) -> int:
        """
        Recursively calculate the dependency depth of a model.
        
        This method determines how many levels deep a model's dependencies go by
        analyzing what aggregates it depends on and what models contribute to those aggregates.
        
        Algorithm:
        1. Check for circular dependencies (model already in visited set)
        2. If no reference, it's independent (depth 0)
        3. Find models that contribute to the referenced aggregate
        4. Exclude self to handle valid self-referential aggregates
        5. Recursively calculate max depth of contributing models
        6. Return max contributor depth + 1
        
        Args:
            model: The CashFlowModel to analyze for dependency depth
            visited: Set of model UIDs already visited (prevents infinite recursion)
            
        Returns:
            The dependency depth:
            - 0 = Independent (no aggregate references)
            - 1 = Depends on independent aggregates only
            - 2 = Depends on aggregates that themselves have dependencies
            - 3+ = Complex nested dependencies
        
        Raises:
            ValueError: If circular dependency detected (should not happen with
                       proper self-referential exclusion)
        
        Example:
            Base OpEx (no reference) → depth 0
            Admin Fee → Total OpEx (depends on Base OpEx) → depth 1  
            Mgmt Fee → NOI (depends on Total OpEx from Admin Fee) → depth 2
        """
        # Circular dependency protection - should never trigger with proper exclusion logic
        if model.uid in visited:
            logger.error(f"Circular dependency detected involving model '{model.name}' (UID: {model.uid})")
            raise ValueError(f"Circular dependency detected involving model '{model.name}'")
        
        # Base case: models without aggregate references are independent
        if not model.reference:
            logger.debug(f"Model '{model.name}' is independent (no reference)")
            return 0
        
        # Find all models that contribute to the aggregate this model depends on
        contributing_models = self._find_models_contributing_to_aggregate(model.reference)
        
        # CRITICAL: Exclude the current model to handle valid self-referential aggregates
        # Example: Admin Fee depends on Total OpEx but also contributes to Total OpEx
        # This is valid in our 2-phase system and should not be considered circular
        contributing_models = [m for m in contributing_models if m.uid != model.uid]
        
        # Handle both AggregateLineKey and other reference types safely
        reference_display = model.reference.value if hasattr(model.reference, 'value') else str(model.reference)
        logger.debug(f"Model '{model.name}' depends on '{reference_display}' with {len(contributing_models)} contributing models")
        
        if not contributing_models:
            # References external aggregate or aggregate from previous phases only
            logger.debug(f"Model '{model.name}' references external/previous-phase aggregate → depth 1")
            return 1
        
        # Calculate max depth of all contributing models recursively
        visited_with_current = visited | {model.uid}  # Add current model to visited set
        max_contributor_depth = 0
        
        for contributor in contributing_models:
            contributor_depth = self._calculate_dependency_depth(contributor, visited_with_current)
            max_contributor_depth = max(max_contributor_depth, contributor_depth)
            logger.debug(f"  Contributor '{contributor.name}' has depth {contributor_depth}")
        
        result_depth = max_contributor_depth + 1
        logger.debug(f"Model '{model.name}' final calculated depth: {result_depth}")
        return result_depth

    def _find_models_contributing_to_aggregate(self, aggregate_key: UnleveredAggregateLineKey) -> List["CashFlowModel"]:
        """
        Find all models in the current analysis that contribute to a specific aggregate.
        
        This method identifies which models feed into a given aggregate line by analyzing
        their category, subcategory, and output components. It handles both simple cash 
        flow models and complex models like leases that produce multiple components.
        
        Args:
            aggregate_key: The AggregateLineKey to analyze (e.g., TOTAL_OPERATING_EXPENSES)
            
        Returns:
            List of CashFlowModel instances that contribute to the specified aggregate.
            Empty list if no models contribute (references external aggregate).
        
        Examples:
            TOTAL_OPERATING_EXPENSES ← [Base OpEx, Admin Fee, Property Management]
            POTENTIAL_GROSS_REVENUE ← [Lease1.base_rent, Lease2.base_rent]
            EXPENSE_REIMBURSEMENTS ← [Lease1.recoveries, Lease2.recoveries]
        
        Note:
            Uses the same aggregation logic as _get_aggregate_key() but in reverse -
            finding what maps TO an aggregate rather than what an item maps to.
        """
        contributing_models = []
        
        # Handle both AggregateLineKey and other reference types safely
        aggregate_display = aggregate_key.value if hasattr(aggregate_key, 'value') else str(aggregate_key)
        logger.debug(f"Finding contributors to aggregate: {aggregate_display}")
        
        for model in self.models:
            # Skip models without proper categorization
            if not (hasattr(model, 'category') and hasattr(model, 'subcategory')):
                continue
                
            # Check if this model's primary output maps to the target aggregate
            target_key = self._get_aggregate_key(model.category, model.subcategory)
            
            # Handle complex models (like leases) that produce multiple components
            from performa.core.base import LeaseBase
            if isinstance(model, LeaseBase):
                # Leases can contribute to multiple aggregates through different components
                lease_components = ['base_rent', 'recoveries', 'abatement', 'ti_allowance', 'leasing_commission']
                for component in lease_components:
                    component_target = self._get_aggregate_key(model.category, model.subcategory, component)
                    if component_target == aggregate_key:
                        contributing_models.append(model)
                        logger.debug(f"  Lease '{model.name}' contributes via component '{component}'")
                        break  # Only add the lease once, even if multiple components match
                continue
            
            # Handle simple cash flow models
            if target_key == aggregate_key:
                contributing_models.append(model)
                logger.debug(f"  Model '{model.name}' contributes directly")
        
        aggregate_display_final = aggregate_key.value if hasattr(aggregate_key, 'value') else str(aggregate_key)
        logger.debug(f"Found {len(contributing_models)} contributors to {aggregate_display_final}")
        return contributing_models

    def _trace_dependency_chain(self, model: "CashFlowModel") -> List[str]:
        """
        Trace and format a dependency chain for clear error reporting.
        
        This method creates a human-readable representation of a dependency chain
        to help users understand complex relationships when validation fails.
        
        Args:
            model: The CashFlowModel to trace dependencies for
            
        Returns:
            List of strings representing the dependency chain from the model
            down to its deepest dependencies. Format: ["Model Name", "[Aggregate]", "Contributing Model"]
        
        Example:
            ["Management Fee", "[Net Operating Income]", "Admin Fee", "[Total Operating Expenses]", "Base OpEx"]
            
        Note:
            For simplicity, only traces the first contributor when multiple models
            contribute to an aggregate. In practice, the full dependency graph
            may have multiple parallel contributors.
        """
        chain = [model.name]
        
        # Base case: no reference means end of chain
        if not model.reference:
            return chain
        
        # Add the aggregate this model depends on (handle both AggregateLineKey and other types)
        reference_display = model.reference.value if hasattr(model.reference, 'value') else str(model.reference)
        chain.append(f"[{reference_display}]")
        
        # Find what feeds into that aggregate and trace recursively
        contributing_models = self._find_models_contributing_to_aggregate(model.reference)
        if contributing_models:
            # For simplicity, trace the first contributor
            # In complex scenarios, multiple models might contribute
            first_contributor = contributing_models[0]
            sub_chain = self._trace_dependency_chain(first_contributor)
            chain.extend(sub_chain)
        
        return chain
