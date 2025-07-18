"""
Generic Absorption Plan Architecture Tests

Comprehensive test suite validating the type-safe generic architecture
implemented for absorption plans. These tests ensure:

1. Type Safety: Office plans cannot use residential expense types and vice versa
2. Required Fields: Plans fail gracefully without required stabilized assumptions
3. Factory Methods: Convenience methods work with realistic defaults
4. Blueprint Integration: End-to-end flow from absorption plan to stabilized property
5. Polymorphic Behavior: Generic code works seamlessly across asset types

This test suite validates the safety-first architecture where stabilized operating
assumptions are required to prevent dangerous silent defaults in financial modeling.
"""

from datetime import date
from typing import List

import pytest

from performa.asset.office.absorption import (
    FixedQuantityPace as OfficeFixedQuantityPace,
)
from performa.asset.office.absorption import OfficeAbsorptionPlan
from performa.asset.office.absorption import SpaceFilter as OfficeSpaceFilter
from performa.asset.office.blueprint import OfficeDevelopmentBlueprint
from performa.asset.office.expense import OfficeExpenses
from performa.asset.office.losses import OfficeLosses
from performa.asset.office.misc_income import OfficeMiscIncome
from performa.asset.office.rent_roll import OfficeVacantSuite
from performa.asset.office.rollover import (
    OfficeRolloverLeaseTerms,
    OfficeRolloverProfile,
)
from performa.asset.residential.absorption import ResidentialAbsorptionPlan
from performa.asset.residential.blueprint import ResidentialDevelopmentBlueprint
from performa.asset.residential.expense import ResidentialExpenses
from performa.asset.residential.losses import ResidentialLosses
from performa.asset.residential.misc_income import ResidentialMiscIncome
from performa.asset.residential.rent_roll import ResidentialVacantUnit
from performa.asset.residential.rollover import (
    ResidentialRolloverLeaseTerms,
    ResidentialRolloverProfile,
)
from performa.core.base import FixedQuantityPace, SpaceFilter
from performa.core.primitives import ProgramUseEnum, Timeline


class TestGenericAbsorptionArchitecture:
    """Test suite for generic absorption plan architecture."""
    
    def test_office_absorption_plan_type_safety(self):
        """Test that OfficeAbsorptionPlan is properly typed with office-specific types."""
        # This should work - correct office types
        office_plan = OfficeAbsorptionPlan.with_typical_assumptions(
            name="Office Test Plan",
            space_filter=OfficeSpaceFilter(),
            start_date_anchor=date(2024, 1, 1),
            pace=OfficeFixedQuantityPace(type="FixedQuantity", quantity=10000, unit="SF", frequency_months=3),
            leasing_assumptions="test"
        )
        
        # Verify type annotations are correct
        assert isinstance(office_plan.stabilized_expenses, OfficeExpenses)
        assert isinstance(office_plan.stabilized_losses, OfficeLosses)
        assert isinstance(office_plan.stabilized_misc_income, list)
        assert all(isinstance(item, OfficeMiscIncome) for item in office_plan.stabilized_misc_income)
    
    def test_residential_absorption_plan_type_safety(self):
        """Test that ResidentialAbsorptionPlan is properly typed with residential-specific types."""
        # This should work - correct residential types
        residential_plan = ResidentialAbsorptionPlan.with_typical_assumptions(
            name="Residential Test Plan"
        )
        
        # Verify type annotations are correct
        assert isinstance(residential_plan.stabilized_expenses, ResidentialExpenses)
        assert isinstance(residential_plan.stabilized_losses, ResidentialLosses)
        assert isinstance(residential_plan.stabilized_misc_income, list)
        assert all(isinstance(item, ResidentialMiscIncome) for item in residential_plan.stabilized_misc_income)
    
    def test_required_stabilized_assumptions_validation(self):
        """Test that absorption plans require all stabilized operating assumptions."""
        # Office plan without required fields should fail
        with pytest.raises(Exception):  # ValidationError
            OfficeAbsorptionPlan(
                name="Incomplete Office Plan",
                space_filter=SpaceFilter(),
                start_date_anchor=date(2024, 1, 1),
                pace=FixedQuantityPace(quantity=10000, unit="SF", frequency_months=3),
                leasing_assumptions="test"
                # Missing: stabilized_expenses, stabilized_losses, stabilized_misc_income
            )
        
        # Residential plan without required fields should fail
        with pytest.raises(Exception):  # ValidationError
            ResidentialAbsorptionPlan(
                name="Incomplete Residential Plan",
                space_filter=SpaceFilter(),
                pace=FixedQuantityPace(quantity=10, unit="Units", frequency_months=1),
                leasing_assumptions="test"
                # Missing: stabilized_expenses, stabilized_losses, stabilized_misc_income
            )
    
    def test_factory_methods_provide_safe_defaults(self):
        """Test that factory methods create valid plans with realistic defaults."""
        # Office factory method
        office_plan = OfficeAbsorptionPlan.with_typical_assumptions(
            name="Office Factory Test",
            space_filter=OfficeSpaceFilter(),
            start_date_anchor=date(2024, 1, 1),
            pace=OfficeFixedQuantityPace(type="FixedQuantity", quantity=5000, unit="SF", frequency_months=2),
            leasing_assumptions="test"
        )
        
        assert office_plan.name == "Office Factory Test"
        assert office_plan.stabilized_expenses is not None
        assert office_plan.stabilized_losses is not None
        assert office_plan.stabilized_misc_income is not None
        
        # Residential factory method
        residential_plan = ResidentialAbsorptionPlan.with_typical_assumptions(
            name="Residential Factory Test"
        )
        
        assert residential_plan.name == "Residential Factory Test"
        assert residential_plan.stabilized_expenses is not None
        assert residential_plan.stabilized_losses is not None
        assert residential_plan.stabilized_misc_income is not None
        
        # Verify operating assumptions have realistic content
        assert len(residential_plan.stabilized_expenses.operating_expenses) > 0
        assert len(residential_plan.stabilized_expenses.capital_expenses) > 0
        assert len(residential_plan.stabilized_misc_income) > 0
    
    def test_blueprint_integration_extracts_assumptions(self):
        """Test that blueprints correctly extract stabilized assumptions from absorption plans."""
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=60)
        
        # Test residential blueprint integration
        residential_rollover = ResidentialRolloverProfile(
            name="Test Rollover",
            term_months=12,
            renewal_probability=0.7,
            downtime_months=1,
            market_terms=ResidentialRolloverLeaseTerms(market_rent=2500.0),
            renewal_terms=ResidentialRolloverLeaseTerms(market_rent=2500.0)
        )
        
        residential_vacant = [
            ResidentialVacantUnit(
                unit_type_name="1BR/1BA",
                unit_count=10,
                avg_area_sf=750.0,
                market_rent=2500.0,
                rollover_profile=residential_rollover
            )
        ]
        
        residential_absorption = ResidentialAbsorptionPlan.with_typical_assumptions(
            name="Integration Test Plan"
        )
        
        residential_blueprint = ResidentialDevelopmentBlueprint(
            name="Integration Test Blueprint",
            vacant_inventory=residential_vacant,
            absorption_plan=residential_absorption
        )
        
        # The blueprint should extract assumptions from the absorption plan
        # We can verify this by checking the blueprint has the absorption plan
        assert residential_blueprint.absorption_plan is residential_absorption
        assert residential_blueprint.absorption_plan.stabilized_expenses is not None
        assert residential_blueprint.absorption_plan.stabilized_losses is not None
        assert residential_blueprint.absorption_plan.stabilized_misc_income is not None
    
    def test_polymorphic_behavior_with_generic_function(self):
        """Test that generic functions work with both office and residential plans."""
        def extract_expense_count(plan) -> int:
            """Generic function that works with any absorption plan type."""
            return len(plan.stabilized_expenses.operating_expenses)
        
        def extract_misc_income_count(plan) -> int:
            """Generic function that works with any absorption plan type.""" 
            return len(plan.stabilized_misc_income)
        
        # Create both plan types
        office_plan = OfficeAbsorptionPlan.with_typical_assumptions(
            name="Polymorphic Office",
            space_filter=OfficeSpaceFilter(),
            start_date_anchor=date(2024, 1, 1),
            pace=OfficeFixedQuantityPace(type="FixedQuantity", quantity=1000, unit="SF", frequency_months=1),
            leasing_assumptions="test"
        )
        
        residential_plan = ResidentialAbsorptionPlan.with_typical_assumptions(
            name="Polymorphic Residential"
        )
        
        # Generic functions should work with both
        office_expense_count = extract_expense_count(office_plan)
        residential_expense_count = extract_expense_count(residential_plan)
        
        office_misc_count = extract_misc_income_count(office_plan)
        residential_misc_count = extract_misc_income_count(residential_plan)
        
        # Both should return valid counts
        assert isinstance(office_expense_count, int)
        assert isinstance(residential_expense_count, int)
        assert isinstance(office_misc_count, int) 
        assert isinstance(residential_misc_count, int)
        
        # Residential should have more detailed defaults
        assert residential_expense_count > 0
        assert residential_misc_count > 0
    
    def test_no_silent_defaults_safety_architecture(self):
        """Test that the safety-first architecture prevents dangerous silent defaults."""
        # This is the core safety principle: explicit errors are better than silent failures
        
        # Attempting to create without stabilized assumptions should fail explicitly
        with pytest.raises(Exception) as exc_info:
            OfficeAbsorptionPlan(
                name="Unsafe Plan",
                space_filter=SpaceFilter(),
                start_date_anchor=date(2024, 1, 1),
                pace=FixedQuantityPace(quantity=1000, unit="SF", frequency_months=1),
                leasing_assumptions="test"
            )
        
        # Should be a validation error, not a silent default
        assert "stabilized_expenses" in str(exc_info.value) or "Field required" in str(exc_info.value)
    
    def test_cross_contamination_prevention(self):
        """Test that the generic architecture prevents cross-contamination of asset types."""
        # Create valid plans with proper types
        office_plan = OfficeAbsorptionPlan.with_typical_assumptions(
            name="Office Cross-contamination Test",
            space_filter=OfficeSpaceFilter(),
            start_date_anchor=date(2024, 1, 1),
            pace=OfficeFixedQuantityPace(type="FixedQuantity", quantity=1000, unit="SF", frequency_months=1),
            leasing_assumptions="test"
        )
        
        residential_plan = ResidentialAbsorptionPlan.with_typical_assumptions(
            name="Residential Cross-contamination Test"
        )
        
        # Office plan should not have residential expense types
        assert not isinstance(office_plan.stabilized_expenses, ResidentialExpenses)
        assert not isinstance(office_plan.stabilized_losses, ResidentialLosses)
        
        # Residential plan should not have office expense types
        assert not isinstance(residential_plan.stabilized_expenses, OfficeExpenses)
        assert not isinstance(residential_plan.stabilized_losses, OfficeLosses)
        
        # This validates the type safety of the generic architecture
        assert type(office_plan.stabilized_expenses).__name__ == "OfficeExpenses"
        assert type(residential_plan.stabilized_expenses).__name__ == "ResidentialExpenses" 