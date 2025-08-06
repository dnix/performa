# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from typing import List

from dateutil.relativedelta import relativedelta

from performa.analysis import AnalysisScenarioBase, register_scenario
from performa.analysis.orchestrator import AnalysisContext, CashFlowOrchestrator
from performa.core.primitives import (
    CashFlowModel,
    FrequencyEnum,
    LeaseStatusEnum,
    Timeline,
    UponExpirationEnum,
)

from .expense import ResidentialCapExItem, ResidentialOpExItem
from .lease import ResidentialLease
from .misc_income import ResidentialMiscIncome
from .property import ResidentialProperty
from .rent_roll import ResidentialUnitSpec, ResidentialVacantUnit
from .rollover import ResidentialRolloverLeaseTerms, ResidentialRolloverProfile

logger = logging.getLogger(__name__)


@register_scenario(ResidentialProperty)
class ResidentialAnalysisScenario(AnalysisScenarioBase):
    """
    Analysis scenario for residential multifamily properties.

    Converts aggregated unit specifications into individual lease models for precise analysis.
    Supports rolling value-add transformations through the REABSORB mechanism.

    Architecture:
    - Unit mix unrolling: UnitSpec(count=40) becomes 40 individual lease instances
    - Two-pass assembly: initial state models + transformed state models
    - Value-add workflow: REABSORB expiration + target_absorption_plan_id linkage
    - Circular reference prevention: post-renovation leases default to MARKET expiration
    - UUID resolution: efficient lookup tables for performance at scale
    """

    model: ResidentialProperty

    def run(self) -> None:
        """
        Execute residential analysis with enhanced assembler pattern.

        Creates UUID lookup tables for efficient resolution, then assembles
        all cash flow models through the two-pass approach.
        """

        # Create UUID lookup maps for efficient resolution
        capital_plan_lookup = {plan.uid: plan for plan in self.model.capital_plans}

        # Collect all rollover profiles from unit specs for UUID resolution
        rollover_profile_lookup = {}
        profiles_to_process = []

        if self.model.unit_mix:
            # Start with profiles from unit specs
            for unit_spec in self.model.unit_mix.unit_specs:
                profiles_to_process.append(unit_spec.rollover_profile)

        # Collect all rollover profiles for UUID resolution
        for profile in profiles_to_process:
            rollover_profile_lookup[profile.uid] = profile

        # Create analysis context with resolved references
        context = AnalysisContext(
            timeline=self.timeline,
            settings=self.settings,
            property_data=self.model,
            capital_plan_lookup=capital_plan_lookup,
            rollover_profile_lookup=rollover_profile_lookup,
        )

        # Assemble all cash flow models
        all_models = self.prepare_models(context)

        # Execute cash flow orchestration
        orchestrator = CashFlowOrchestrator(models=all_models, context=context)
        orchestrator.execute()
        self._orchestrator = orchestrator

    def prepare_models(self, context: AnalysisContext) -> List[CashFlowModel]:
        """
        Assemble cash flow models using two-pass approach for value-add scenarios.

        Pass 1: Initial state models
        - Operating expenses and capital expenditures
        - Miscellaneous income streams
        - Current lease instances from unit mix
        - Vacant unit absorption

        Pass 2: Transformed state models
        - Identify leases with REABSORB + target_absorption_plan_id
        - Calculate post-renovation timing and rent premiums
        - Generate new lease models for transformed units
        """
        all_models: List[CashFlowModel] = []
        prop: ResidentialProperty = self.model

        # Pass 1: Initial state models
        logger.debug("Pass 1: Assembling initial state models")

        # Add expense items
        if prop.expenses.operating_expenses:
            all_models.extend(prop.expenses.operating_expenses)
        if prop.expenses.capital_expenses:
            all_models.extend(prop.expenses.capital_expenses)

        # Add miscellaneous income
        all_models.extend(prop.miscellaneous_income)

        # Add capital expenditures
        for capital_plan in prop.capital_plans:
            all_models.extend(capital_plan.capital_items)

        # Note: Losses handled separately by orchestrator

        # Unroll unit mix into individual leases
        if prop.unit_mix:
            for unit_spec in prop.unit_mix.unit_specs:
                for unit_index in range(unit_spec.unit_count):
                    lease_instance = self._create_lease_from_unit_spec(
                        unit_spec, unit_index, context
                    )
                    all_models.append(lease_instance)

        # Process absorption plans for vacant units
        if hasattr(prop, "absorption_plans") and prop.absorption_plans:
            for absorption_plan in prop.absorption_plans:
                try:
                    # Get available vacant units
                    available_vacant_units = []
                    if (
                        hasattr(prop.unit_mix, "vacant_units")
                        and prop.unit_mix.vacant_units
                    ):
                        available_vacant_units = prop.unit_mix.vacant_units

                    # Generate unit specs from absorption plan
                    generated_specs = absorption_plan.generate_unit_specs(
                        available_vacant_units=available_vacant_units,
                        analysis_start_date=self.timeline.start_date.to_timestamp().date(),
                        analysis_end_date=self.timeline.end_date.to_timestamp().date(),
                        global_settings=self.settings,
                    )

                    # Create lease models
                    for unit_spec in generated_specs:
                        for unit_index in range(unit_spec.unit_count):
                            lease_instance = self._create_lease_from_unit_spec(
                                unit_spec, unit_index, context
                            )
                            all_models.append(lease_instance)

                except Exception as e:
                    # Continue on absorption plan errors
                    logger.warning(
                        f"Failed to process absorption plan '{absorption_plan.name}': {e}"
                    )

        # Pass 2: Value-add transformations
        logger.debug("Pass 2: Assembling transformed state models")

        # Find transformative leases
        transformative_leases = self._find_transformative_leases(all_models)

        if transformative_leases:
            logger.info(
                f"Found {len(transformative_leases)} leases for value-add transformation"
            )

            # Create absorption plan lookup
            absorption_plan_lookup = {plan.uid: plan for plan in prop.absorption_plans}

            # Process transformative leases
            for lease in transformative_leases:
                try:
                    post_renovation_lease = self._create_post_renovation_lease(
                        original_lease=lease,
                        absorption_plan_lookup=absorption_plan_lookup,
                        context=context,
                    )
                    if post_renovation_lease:
                        all_models.append(post_renovation_lease)
                        logger.debug(f"Created post-renovation lease for {lease.name}")

                except Exception as e:
                    logger.warning(
                        f"Failed to create post-renovation lease for {lease.name}: {e}"
                    )

        logger.info(f"Assembly complete: {len(all_models)} total cash flow models")
        return all_models

    def _create_lease_from_unit_spec(
        self, unit_spec: ResidentialUnitSpec, unit_index: int, context: AnalysisContext
    ) -> ResidentialLease:
        """
        Create lease instance from unit specification.

        Handles progressive lease start dates for development projects
        and injects resolved object references for performance.
        """
        suite_id = f"{unit_spec.unit_type_name}_{unit_index + 1:03d}"

        # Configure lease term from rollover profile
        lease_term_months = unit_spec.rollover_profile.term_months

        # Create lease timeline with progressive start date support
        lease_start_date = (
            unit_spec.lease_start_date
            if unit_spec.lease_start_date is not None
            else self.timeline.start_date.to_timestamp().date()
        )

        lease_timeline = Timeline(
            start_date=lease_start_date, duration_months=lease_term_months
        )

        # Create lease instance
        lease = ResidentialLease(
            name=f"Resident {suite_id}",
            timeline=lease_timeline,
            status=LeaseStatusEnum.CONTRACT,  # In-place leases are contractual, not speculative
            area=unit_spec.avg_area_sf,
            suite=suite_id,
            floor="1",  # Simplified floor assignment for residential units
            upon_expiration=unit_spec.rollover_profile.upon_expiration,  # Use rollover profile setting
            monthly_rent=unit_spec.current_avg_monthly_rent,  # Monthly rent in dollars
            value=unit_spec.current_avg_monthly_rent,  # Same as monthly_rent for CashFlowModel
            frequency=FrequencyEnum.MONTHLY,
            rollover_profile=unit_spec.rollover_profile,
        )

        return lease

    def _find_transformative_leases(
        self, models: List[CashFlowModel]
    ) -> List[ResidentialLease]:
        """
        Find leases configured for value-add transformation.

        Filters for ResidentialLease instances with:
        - upon_expiration == REABSORB
        - rollover_profile.target_absorption_plan_id is set

        Args:
            models: List of cash flow models from Pass 1

        Returns:
            List of ResidentialLease instances ready for transformation
        """
        transformative_leases = []

        for model in models:
            if (
                isinstance(model, ResidentialLease)
                and hasattr(model, "rollover_profile")
                and model.rollover_profile
                and model.rollover_profile.upon_expiration
                == UponExpirationEnum.REABSORB
                and model.rollover_profile.target_absorption_plan_id is not None
            ):
                transformative_leases.append(model)
                logger.debug(
                    f"Found transformative lease: {model.name} with target plan {model.rollover_profile.target_absorption_plan_id}"
                )

        return transformative_leases

    def _create_post_renovation_lease(
        self,
        original_lease: ResidentialLease,
        absorption_plan_lookup: dict,
        context: AnalysisContext,
    ) -> ResidentialLease:
        """
        Create post-renovation lease for value-add transformation.

        Process:
        1. Calculate new lease start date (original end + downtime + 1 month)
        2. Resolve target absorption plan from lookup
        3. Create stabilized rollover profile (prevents circular references)
        4. Generate renovated unit spec via absorption plan
        5. Create new lease instance with premium rent

        Args:
            original_lease: Expiring lease triggering transformation
            absorption_plan_lookup: UUID to absorption plan mapping
            context: Analysis context

        Returns:
            New ResidentialLease for post-renovation unit

        Raises:
            ValueError: If target absorption plan not found
        """
        rollover_profile = original_lease.rollover_profile
        target_plan_id = rollover_profile.target_absorption_plan_id

        # Find the target absorption plan
        target_plan = absorption_plan_lookup.get(target_plan_id)
        if not target_plan:
            raise ValueError(
                f"Cannot find AbsorptionPlan with ID {target_plan_id} for lease {original_lease.name}. "
                f"Available plans: {list(absorption_plan_lookup.keys())}"
            )

        # Calculate the start date for the NEW, post-renovation lease
        # Formula: original_lease_end_date + downtime_months + 1
        renovation_downtime = rollover_profile.downtime_months or 0
        original_end_date = original_lease.timeline.end_date.to_timestamp().date()

        # Calculate new lease start: end date + downtime months
        new_lease_start_date = original_end_date + relativedelta(
            months=renovation_downtime + 1
        )

        logger.debug(f"Calculating post-renovation timing for {original_lease.name}:")
        logger.debug(f"  Original lease ends: {original_end_date}")
        logger.debug(f"  Downtime months: {renovation_downtime}")
        logger.debug(f"  New lease starts: {new_lease_start_date}")

        # Create stabilized post-renovation rollover profile
        lease_terms = target_plan.leasing_assumptions

        # Create rollover terms from absorption plan
        post_reno_market_terms = ResidentialRolloverLeaseTerms(
            market_rent=lease_terms.monthly_rent
            or rollover_profile.market_terms.market_rent,
            term_months=lease_terms.lease_term_months or 12,
            market_rent_growth=rollover_profile.market_terms.market_rent_growth,
            renewal_rent_increase_percent=rollover_profile.market_terms.renewal_rent_increase_percent,
        )

        post_reno_renewal_terms = ResidentialRolloverLeaseTerms(
            market_rent=lease_terms.monthly_rent
            or rollover_profile.renewal_terms.market_rent,
            term_months=lease_terms.lease_term_months or 12,
            market_rent_growth=rollover_profile.renewal_terms.market_rent_growth,
            renewal_rent_increase_percent=rollover_profile.renewal_terms.renewal_rent_increase_percent,
        )

        # Create post-renovation profile with explicit values
        stabilized_upon_expiration = (
            lease_terms.upon_expiration or UponExpirationEnum.MARKET
        )
        stabilized_renewal_probability = (
            lease_terms.stabilized_renewal_probability or 0.7
        )
        stabilized_downtime_months = lease_terms.stabilized_downtime_months or 1

        logger.debug(
            f"Post-renovation profile: {stabilized_upon_expiration}, renewal={stabilized_renewal_probability}, downtime={stabilized_downtime_months}"
        )

        post_reno_rollover_profile = ResidentialRolloverProfile(
            name=f"{rollover_profile.name} (Post-Renovation)",
            term_months=lease_terms.lease_term_months or rollover_profile.term_months,
            renewal_probability=stabilized_renewal_probability,
            downtime_months=stabilized_downtime_months,
            market_terms=post_reno_market_terms,
            renewal_terms=post_reno_renewal_terms,
            upon_expiration=stabilized_upon_expiration,
            target_absorption_plan_id=None,  # Prevents circular references
        )

        # Circular reference prevention: target_absorption_plan_id=None prevents infinite loops

        # Create transient vacant unit representing the renovated unit
        transient_vacant_unit = ResidentialVacantUnit(
            unit_type_name=f"{original_lease.suite}_renovated",
            unit_count=1,
            avg_area_sf=original_lease.area,
            market_rent=lease_terms.monthly_rent or 0,
            rollover_profile=post_reno_rollover_profile,
        )

        # Generate renovated unit spec via absorption plan
        generated_specs = target_plan.generate_unit_specs(
            available_vacant_units=[transient_vacant_unit],
            analysis_start_date=new_lease_start_date,
            analysis_end_date=context.timeline.end_date.to_timestamp().date(),
            global_settings=self.settings,
        )

        if not generated_specs:
            logger.warning(
                f"Absorption plan {target_plan.name} generated no unit specs for {original_lease.name}"
            )
            return None

        # Use first generated spec
        renovated_unit_spec = generated_specs[0]

        # Create post-renovation lease model
        post_renovation_lease = self._create_lease_from_unit_spec(
            unit_spec=renovated_unit_spec, unit_index=0, context=context
        )

        # Update lease name (immutable instance)
        post_renovation_lease = post_renovation_lease.model_copy(
            update={"name": f"{original_lease.name} (Post-Renovation)"}
        )

        logger.info(
            f"Created post-renovation lease: {post_renovation_lease.name} starting {new_lease_start_date}"
        )
        logger.debug(
            f"  Premium rent: ${post_renovation_lease.monthly_rent:,.0f}/month"
        )
        logger.debug(f"  Original rent: ${original_lease.monthly_rent:,.0f}/month")

        return post_renovation_lease

    def _create_expense_models(self) -> List[CashFlowModel]:
        """
        Create residential expense models.

        Residential expenses are typically calculated per-unit rather than
        per-square-foot (common in office properties).

        Returns:
            List of expense CashFlowModel instances
        """
        models = []

        if self.model.expenses:
            # Operating expenses
            if self.model.expenses.operating_expenses:
                for expense_item in self.model.expenses.operating_expenses:
                    if isinstance(expense_item, ResidentialOpExItem):
                        models.append(expense_item)
                        logger.debug(f"Added operating expense: {expense_item.name}")

            # Capital expenses
            if self.model.expenses.capital_expenses:
                for expense_item in self.model.expenses.capital_expenses:
                    if isinstance(expense_item, ResidentialCapExItem):
                        models.append(expense_item)
                        logger.debug(f"Added capital expense: {expense_item.name}")

        logger.info(f"Added {len(models)} expense models")
        return models

    def _create_misc_income_models(self) -> List[CashFlowModel]:
        """
        Create miscellaneous income models for residential property.

        Common sources: laundry, parking, pet fees, application fees.

        Returns:
            List of miscellaneous income CashFlowModel instances
        """
        models = []

        if self.model.miscellaneous_income:
            for income_item in self.model.miscellaneous_income:
                if isinstance(income_item, ResidentialMiscIncome):
                    models.append(income_item)
                    logger.debug(f"Added miscellaneous income: {income_item.name}")

        logger.info(f"Added {len(models)} miscellaneous income models")
        return models
