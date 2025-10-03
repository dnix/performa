# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
import traceback
from abc import abstractmethod
from typing import List, Optional

from ...analysis import AnalysisScenarioBase
from ...analysis.orchestrator import AnalysisContext
from ...core.base import LeaseSpecBase
from ...core.base.loss import CreditLossModel, VacancyLossModel
from ...core.primitives import CashFlowModel

logger = logging.getLogger(__name__)


class CommercialAnalysisScenarioBase(AnalysisScenarioBase):
    """
    Base class for commercial asset analysis scenarios with assembler pattern support.

    COMMERCIAL ASSEMBLER IMPLEMENTATION
    ====================================

    This base class implements the assembler pattern for commercial real estate analysis,
    handling the complexity common to office, retail, and industrial properties.

    COMMERCIAL-SPECIFIC FEATURES:

    1. CONTEXT PREPARATION
       ===================
       - Recovery method lookup maps (name-based for expense recovery)
       - TI/LC template resolution (UUID to direct object references)
       - Rollover profile management (renewal vs market scenarios)
       - Multi-phase dependency handling for commercial expense structures

    2. ASSEMBLER PATTERN IMPLEMENTATION
       =================================
       Assembly time:
       - Resolve recovery method names to objects
       - Resolve capital plan UUIDs to direct references
       - Populate AnalysisContext with commercial-specific lookup maps
       - Inject direct references into lease and expense models

       Runtime:
       - Direct attribute access (context.recovery_method_lookup[name])
       - No UUID resolution overhead during cash flow calculations

    3. COMMERCIAL MODELING SUPPORT
       ============================
       - Expense recovery calculations (base year, net, gross-up)
       - Tenant improvement and leasing commission modeling
       - Complex rollover scenarios with state transitions
       - Multi-tenant lease structure support

    COMPATIBILITY:
    - Maintains backward compatibility with existing commercial models
    - Supports single tenant through multi-tenant properties
    - Enables scenario modeling for commercial portfolios
    - No breaking changes to existing analysis workflows

    This foundation supports office, retail, and industrial analysis scenarios
    while maintaining the modeling capabilities required for commercial real estate analysis.
    """

    @abstractmethod
    def _create_lease_from_spec(
        self, spec: LeaseSpecBase, context: Optional[AnalysisContext] = None
    ) -> CashFlowModel:
        """
        Abstract method for creating a lease from a spec.

        Args:
            spec: The lease specification to create a lease from
            context: Optional AnalysisContext for object injection and UUID resolution

        Returns:
            CashFlowModel instance representing the lease
        """
        pass

    @abstractmethod
    def _create_misc_income_models(
        self, context: Optional[AnalysisContext] = None
    ) -> List[CashFlowModel]:
        """
        Abstract method for creating miscellaneous income models.

        Args:
            context: Optional AnalysisContext for enhanced performance

        Returns:
            List of miscellaneous income CashFlowModel instances
        """
        pass

    @abstractmethod
    def _create_expense_models(
        self, context: Optional[AnalysisContext] = None
    ) -> List[CashFlowModel]:
        """
        Abstract method for creating expense models.

        Args:
            context: Optional AnalysisContext for enhanced performance

        Returns:
            List of expense CashFlowModel instances
        """
        pass

    @abstractmethod
    def _create_loss_models(
        self, context: Optional[AnalysisContext] = None
    ) -> List[CashFlowModel]:
        """
        Abstract method for creating loss models.

        Args:
            context: Optional AnalysisContext for enhanced performance

        Returns:
            List of loss CashFlowModel instances
        """
        pass

    def prepare_models(
        self, context: Optional[AnalysisContext] = None
    ) -> List[CashFlowModel]:
        """
        Prepares all cash flow models for the analysis with enhanced context support.

        ASSEMBLER PATTERN IMPLEMENTATION:
        Uses the provided AnalysisContext to perform UUID resolution and
        object injection for maximum runtime performance.

        Args:
            context: Optional AnalysisContext containing pre-built lookup maps

        Returns:
            List of all CashFlowModel instances for the analysis
        """
        all_models: List[CashFlowModel] = []

        # 1. Leases from Rent Roll
        if hasattr(self.model, "rent_roll") and self.model.rent_roll:
            for lease_spec in self.model.rent_roll.leases:
                lease_model = self._create_lease_from_spec(lease_spec, context)
                all_models.append(lease_model)

                # Also add the TI and LC models if they exist
                # These are typically created by the lease during construction
                if hasattr(lease_model, "ti_allowance") and lease_model.ti_allowance:
                    all_models.append(lease_model.ti_allowance)
                if (
                    hasattr(lease_model, "leasing_commission")
                    and lease_model.leasing_commission
                ):
                    all_models.append(lease_model.leasing_commission)

            # Process absorption plans for vacant suites
            # Generate lease models from absorption plan specs for revenue generation

            # Get absorption plans from different sources depending on asset type
            absorption_plans = []

            # Method 1: Direct absorption_plans attribute (office properties)
            if hasattr(self.model, "absorption_plans") and self.model.absorption_plans:
                absorption_plans.extend(self.model.absorption_plans)

            # Method 2: Blueprint absorption_plan (development projects)
            if hasattr(self.model, "blueprints") and self.model.blueprints:
                for blueprint in self.model.blueprints:
                    if (
                        hasattr(blueprint, "absorption_plan")
                        and blueprint.absorption_plan
                    ):
                        absorption_plans.append(blueprint.absorption_plan)

            if absorption_plans:
                # TODO: REABSORB→Absorption Transformation Support (Office)
                # ============================================================
                # Currently, office properties do NOT support the REABSORB→absorption workflow
                # that residential properties have. When an office lease expires with
                # upon_expiration=REABSORB, the space simply disappears - it doesn't become
                # available to absorption plans.
                #
                # To implement (following residential pattern in ResidentialAnalysisScenario):
                # 1. Track leases with upon_expiration=REABSORB during prepare_models()
                # 2. Calculate when they expire and how much space becomes available
                # 3. Convert expired REABSORB space to temporary vacant suites
                # 4. Pass both static vacant suites AND dynamic REABSORB suites to absorption plans
                # 5. Optional: Support target_absorption_plan_id for specific plan targeting
                #
                # This would enable value-add office scenarios like:
                # - Tenant departure → renovation → re-lease at higher rates
                # - Phased building repositioning with rolling lease expirations
                # - Coordination with capital plans during vacancy periods
                #
                # See ResidentialAnalysisScenario._find_transformative_leases() and
                # _create_post_renovation_lease() for reference implementation.

                for absorption_plan in absorption_plans:
                    try:
                        # Get vacant suites from appropriate source
                        vacant_suites = []

                        # Method 1: From rent roll (stabilized properties)
                        if hasattr(self.model, "rent_roll") and self.model.rent_roll:
                            if hasattr(self.model.rent_roll, "vacant_suites"):
                                vacant_suites = self.model.rent_roll.vacant_suites or []

                        # Method 2: From blueprint vacant inventory (development projects)
                        if (
                            not vacant_suites
                            and hasattr(self.model, "blueprints")
                            and self.model.blueprints
                        ):
                            for blueprint in self.model.blueprints:
                                if (
                                    hasattr(blueprint, "vacant_inventory")
                                    and blueprint.vacant_inventory
                                ):
                                    vacant_suites.extend(blueprint.vacant_inventory)

                        # Generate lease specs from absorption plan
                        # NOTE: Currently only passes static vacant_suites, not REABSORB space
                        generated_specs = absorption_plan.generate_lease_specs(
                            available_vacant_suites=vacant_suites,
                            analysis_start_date=self.timeline.start_date.to_timestamp().date(),
                            analysis_end_date=self.timeline.end_date.to_timestamp().date(),
                            lookup_fn=None,
                            global_settings=None,
                        )

                        logger.info(
                            f"Absorption plan '{absorption_plan.name}' generated {len(generated_specs)} lease specs"
                        )

                        # Create lease models from specs and add TI/LC models
                        for spec in generated_specs:
                            lease_model = self._create_lease_from_spec(spec, context)
                            all_models.append(lease_model)

                            # Add TI/LC models if present
                            if (
                                hasattr(lease_model, "ti_allowance")
                                and lease_model.ti_allowance
                            ):
                                all_models.append(lease_model.ti_allowance)
                            if (
                                hasattr(lease_model, "leasing_commission")
                                and lease_model.leasing_commission
                            ):
                                all_models.append(lease_model.leasing_commission)

                        # CRITICAL FIX: Process absorption plan stabilized losses
                        if (
                            hasattr(absorption_plan, "stabilized_losses")
                            and absorption_plan.stabilized_losses
                        ):
                            absorption_losses = absorption_plan.stabilized_losses

                            # Create vacancy loss model if configured
                            if (
                                hasattr(absorption_losses, "general_vacancy")
                                and absorption_losses.general_vacancy
                                and absorption_losses.general_vacancy.rate > 0
                            ):
                                vacancy_model = VacancyLossModel(
                                    name=f"{absorption_plan.name} - Vacancy Loss",
                                    timeline=self.timeline,
                                    rate=absorption_losses.general_vacancy.rate,
                                    reference_line=absorption_losses.general_vacancy.method.value,
                                )
                                all_models.append(vacancy_model)
                                logger.info(
                                    f"Added vacancy loss model: {vacancy_model.name} ({vacancy_model.rate:.1%})"
                                )

                            # Create credit loss model if configured
                            if (
                                hasattr(absorption_losses, "credit_loss")
                                and absorption_losses.credit_loss
                                and absorption_losses.credit_loss.rate > 0
                            ):
                                credit_model = CreditLossModel(
                                    name=f"{absorption_plan.name} - Credit Loss",
                                    timeline=self.timeline,
                                    rate=absorption_losses.credit_loss.rate,
                                    reference_line=absorption_losses.credit_loss.basis.value,
                                )
                                all_models.append(credit_model)
                                logger.info(
                                    f"Added credit loss model: {credit_model.name} ({credit_model.rate:.1%})"
                                )

                    except Exception as e:
                        logger.error(
                            f"Failed to process absorption plan '{absorption_plan.name}': {e}"
                        )
                        logger.error(traceback.format_exc())
                        # Continue processing other plans

        # 2. Miscellaneous Income
        if hasattr(self.model, "miscellaneous_income"):
            all_models.extend(self._create_misc_income_models(context))

        # 3. Expenses
        all_models.extend(self._create_expense_models(context))

        # 4. Losses
        if hasattr(self.model, "losses") and self.model.losses:
            all_models.extend(self._create_loss_models(context))

        return all_models
