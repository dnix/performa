# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import date

import pytest

from performa.core.base import (
    AbsorptionPlanBase,
    FixedQuantityPace,
    SpaceFilter,
)
from performa.core.primitives import Model, ProgramUseEnum, StartDateAnchorEnum

# --- Mocks and Fixtures ---

class MockVacantSuite(Model):
    """A mock VacantSuiteBase for testing the SpaceFilter."""
    suite: str
    floor: str
    area: float
    use_type: ProgramUseEnum

class MockModel(Model):
    """A simple mock model for testing stabilized assumptions."""
    pass

@pytest.fixture
def sample_vacant_suite() -> MockVacantSuite:
    return MockVacantSuite(
        suite="101",
        floor="1",
        area=1500.0,
        use_type=ProgramUseEnum.OFFICE
    )

# --- SpaceFilter Tests ---

def test_space_filter_matches_all(sample_vacant_suite: MockVacantSuite):
    """Test that an empty filter matches any suite."""
    filt = SpaceFilter()
    assert filt.matches(sample_vacant_suite)

def test_space_filter_matches_by_suite_id(sample_vacant_suite: MockVacantSuite):
    """Test filtering by suite ID."""
    filt_pass = SpaceFilter(suite_ids=["101", "202"])
    filt_fail = SpaceFilter(suite_ids=["301", "404"])
    assert filt_pass.matches(sample_vacant_suite)
    assert not filt_fail.matches(sample_vacant_suite)

def test_space_filter_matches_by_use_type(sample_vacant_suite: MockVacantSuite):
    """Test filtering by program use type."""
    filt_pass = SpaceFilter(use_types=[ProgramUseEnum.OFFICE, ProgramUseEnum.RETAIL])
    filt_fail = SpaceFilter(use_types=[ProgramUseEnum.INDUSTRIAL])
    assert filt_pass.matches(sample_vacant_suite)
    assert not filt_fail.matches(sample_vacant_suite)

def test_space_filter_matches_by_area(sample_vacant_suite: MockVacantSuite):
    """Test filtering by min and max area."""
    filt_pass_min = SpaceFilter(min_area=1000)
    filt_fail_min = SpaceFilter(min_area=2000)
    assert filt_pass_min.matches(sample_vacant_suite)
    assert not filt_fail_min.matches(sample_vacant_suite)

    filt_pass_max = SpaceFilter(max_area=2000)
    filt_fail_max = SpaceFilter(max_area=1000)
    assert filt_pass_max.matches(sample_vacant_suite)
    assert not filt_fail_max.matches(sample_vacant_suite)

    filt_pass_both = SpaceFilter(min_area=1200, max_area=1800)
    filt_fail_both = SpaceFilter(min_area=1600, max_area=1800)
    assert filt_pass_both.matches(sample_vacant_suite)
    assert not filt_fail_both.matches(sample_vacant_suite)

def test_space_filter_matches_multiple_criteria(sample_vacant_suite: MockVacantSuite):
    """Test filtering by multiple criteria at once."""
    filt_pass = SpaceFilter(use_types=[ProgramUseEnum.OFFICE], min_area=1000)
    filt_fail = SpaceFilter(use_types=[ProgramUseEnum.RETAIL], min_area=1000)
    assert filt_pass.matches(sample_vacant_suite)
    assert not filt_fail.matches(sample_vacant_suite)

# --- AbsorptionPlanBase Tests ---

def test_absorption_plan_base_instantiation():
    """Test successful instantiation of AbsorptionPlanBase."""
    # Create mock stabilized assumptions
    mock_expenses = MockModel()  # Simple mock for expenses
    mock_losses = MockModel()    # Simple mock for losses
    mock_misc_income = []        # Empty list for misc income
    
    plan = AbsorptionPlanBase(
        name="Office Lease-Up",
        space_filter=SpaceFilter(use_types=[ProgramUseEnum.OFFICE]),
        start_date_anchor=StartDateAnchorEnum.ANALYSIS_START,
        pace=FixedQuantityPace(type="FixedQuantity", quantity=10000, unit="SF", frequency_months=3),
        leasing_assumptions="Standard Office Rollover", # Using identifier string
        stabilized_expenses=mock_expenses,
        stabilized_losses=mock_losses,
        stabilized_misc_income=mock_misc_income
    )
    assert plan.name == "Office Lease-Up"
    assert plan.pace.quantity == 10000
