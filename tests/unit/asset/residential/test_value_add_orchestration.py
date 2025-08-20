# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for value-add orchestration logic in ResidentialAnalysisScenario.

These tests focus on the two-pass assembly logic and helper methods that enable
rolling value-add scenarios.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

from performa.analysis.orchestrator import AnalysisContext
from performa.asset.residential import (
    ResidentialAbsorptionPlan,
    ResidentialAnalysisScenario,
    ResidentialExpenses,
    ResidentialLease,
    ResidentialLosses,
    ResidentialMiscIncome,
    ResidentialProperty,
    ResidentialRentRoll,
    ResidentialRolloverLeaseTerms,
    ResidentialRolloverProfile,
    ResidentialUnitSpec,
)
from performa.asset.residential.absorption import ResidentialDirectLeaseTerms
from performa.core.base import Address
from performa.core.base.absorption import FixedQuantityPace
from performa.core.ledger import LedgerBuilder
from performa.core.primitives import (
    FrequencyEnum,
    GlobalSettings,
    LeaseStatusEnum,
    StartDateAnchorEnum,
    Timeline,
    UponExpirationEnum,
)


class TestValueAddOrchestration:
    """Test suite for value-add orchestration functionality."""

    def setup_method(self):
        """Set up common test fixtures."""
        self.timeline = Timeline(start_date=date(2024, 1, 1), duration_months=24)
        self.settings = GlobalSettings()

    def test_find_transformative_leases_business_logic(self):
        """Test that _find_transformative_leases correctly identifies value-add leases."""
        property_model = self._create_minimal_property()
        
        scenario = ResidentialAnalysisScenario(
            model=property_model, timeline=self.timeline, settings=self.settings,
            ledger_builder=LedgerBuilder()
        )

        # Create transformative lease (REABSORB + target_absorption_plan_id)
        target_plan_id = uuid4()
        transformative_profile = self._create_rollover_profile(
            upon_expiration=UponExpirationEnum.REABSORB,
            target_absorption_plan_id=target_plan_id,
        )
        transformative_lease = self._create_lease_with_rollover(
            transformative_profile, name="Value-Add Lease"
        )

        # Create regular lease (MARKET expiration)
        regular_profile = self._create_rollover_profile(
            upon_expiration=UponExpirationEnum.MARKET, target_absorption_plan_id=None
        )
        regular_lease = self._create_lease_with_rollover(
            regular_profile, name="Regular Lease"
        )

        # Create REABSORB lease without target plan (legacy behavior)
        legacy_profile = self._create_rollover_profile(
            upon_expiration=UponExpirationEnum.REABSORB, target_absorption_plan_id=None
        )
        legacy_lease = self._create_lease_with_rollover(
            legacy_profile, name="Legacy Lease"
        )

        # Create lease without rollover profile
        no_profile_lease = ResidentialLease(
            name="No Profile Lease",
            timeline=self.timeline,
            status=LeaseStatusEnum.CONTRACT,
            area=800.0,
            suite="101",
            floor="1",
            upon_expiration=UponExpirationEnum.MARKET,
            monthly_rent=2000.0,
            value=2000.0,
            frequency=FrequencyEnum.MONTHLY,
            rollover_profile=None,
        )

        # Create non-lease model to test filtering
        misc_income = ResidentialMiscIncome(
            name="Parking Income",
            timeline=self.timeline,
            value=100.0,
            frequency=FrequencyEnum.MONTHLY,
        )

        all_models = [
            transformative_lease,
            regular_lease,
            legacy_lease,
            no_profile_lease,
            misc_income,
        ]

        result = scenario._find_transformative_leases(all_models)

        # Should only return the transformative lease
        assert len(result) == 1
        assert result[0] == transformative_lease
        assert result[0].name == "Value-Add Lease"
        assert result[0].rollover_profile.upon_expiration == UponExpirationEnum.REABSORB
        assert result[0].rollover_profile.target_absorption_plan_id == target_plan_id

    def test_create_post_renovation_lease_error_handling(self):
        """Test _create_post_renovation_lease properly handles missing absorption plans."""
        property_model = self._create_minimal_property()
        
        scenario = ResidentialAnalysisScenario(
            model=property_model, timeline=self.timeline, settings=self.settings,
            ledger_builder=LedgerBuilder()
        )

        # Create context
        context = AnalysisContext(
            timeline=self.timeline,
            settings=self.settings,
            property_data=property_model,
            ledger_builder=LedgerBuilder(),
        )

        # Create lease with rollover profile pointing to non-existent plan
        missing_plan_id = uuid4()
        rollover_profile = self._create_rollover_profile(
            upon_expiration=UponExpirationEnum.REABSORB,
            target_absorption_plan_id=missing_plan_id,
        )

        lease = self._create_lease_with_rollover(rollover_profile)

        # Empty absorption plan lookup - this should raise an error
        absorption_plan_lookup = {}

        with pytest.raises(ValueError, match="Cannot find AbsorptionPlan"):
            scenario._create_post_renovation_lease(
                original_lease=lease,
                absorption_plan_lookup=absorption_plan_lookup,
                context=context,
            )

    # Helper methods

    def _create_minimal_property(self) -> ResidentialProperty:
        """Create a minimal residential property for testing."""
        unit_spec = ResidentialUnitSpec(
            unit_type_name="1BR/1BA",
            unit_count=1,
            avg_area_sf=800.0,
            current_avg_monthly_rent=2000.0,
            rollover_profile=self._create_rollover_profile(),
        )

        rent_roll = ResidentialRentRoll(unit_specs=[unit_spec])

        return ResidentialProperty(
            name="Test Property",
            address=Address(
                street="123 Test St",
                city="Test City",
                state="TS",
                zip_code="12345",
                country="USA",
            ),
            gross_area=1000.0,
            net_rentable_area=800.0,  # Match unit area
            unit_mix=rent_roll,
            expenses=ResidentialExpenses(),
            losses=ResidentialLosses(
                general_vacancy={"rate": 0.05, "method": "Potential Gross Revenue"},
                credit_loss={"rate": 0.02, "basis": "Potential Gross Revenue"},
            ),
            miscellaneous_income=[],
        )

    def _create_rollover_profile(
        self,
        upon_expiration: UponExpirationEnum = UponExpirationEnum.MARKET,
        target_absorption_plan_id: str = None,
        downtime_months: int = 1,
    ) -> ResidentialRolloverProfile:
        """Create a rollover profile for testing."""
        market_terms = ResidentialRolloverLeaseTerms(market_rent=2000.0, term_months=12)

        renewal_terms = ResidentialRolloverLeaseTerms(
            market_rent=1950.0, term_months=12
        )

        return ResidentialRolloverProfile(
            name="Test Rollover Profile",
            term_months=12,
            renewal_probability=0.6,
            downtime_months=downtime_months,
            market_terms=market_terms,
            renewal_terms=renewal_terms,
            upon_expiration=upon_expiration,
            target_absorption_plan_id=target_absorption_plan_id,
        )

    def _create_lease_with_rollover(
        self, rollover_profile: ResidentialRolloverProfile, name: str = "Test Lease"
    ) -> ResidentialLease:
        """Create a lease with the given rollover profile."""
        return ResidentialLease(
            name=name,
            timeline=self.timeline,
            status=LeaseStatusEnum.CONTRACT,
            area=800.0,
            suite="101",
            floor="1",
            upon_expiration=rollover_profile.upon_expiration,
            monthly_rent=2000.0,
            value=2000.0,
            frequency=FrequencyEnum.MONTHLY,
            rollover_profile=rollover_profile,
        )

    def _create_absorption_plan(self) -> ResidentialAbsorptionPlan:
        """Create a basic absorption plan for testing."""
        return ResidentialAbsorptionPlan(
            name="Test Absorption Plan",
            start_date_anchor=StartDateAnchorEnum.ANALYSIS_START,
            pace=FixedQuantityPace(quantity=1, unit="Units", frequency_months=1),
            leasing_assumptions=ResidentialDirectLeaseTerms(monthly_rent=2800.0),
            stabilized_expenses=ResidentialExpenses(),
            stabilized_losses=ResidentialLosses(
                general_vacancy={"rate": 0.05, "method": "Potential Gross Revenue"},
                credit_loss={"rate": 0.02, "basis": "Potential Gross Revenue"},
            ),
            stabilized_misc_income=[],
        )
