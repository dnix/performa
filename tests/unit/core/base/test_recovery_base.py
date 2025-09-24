# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import date

import pytest

from performa.core.base import (
    ExpensePoolBase,
    OpExItemBase,
    RecoveryBase,
    RecoveryMethodBase,
)
from performa.core.primitives import Timeline


@pytest.fixture
def sample_expense(sample_timeline: Timeline) -> OpExItemBase:
    return OpExItemBase(
        name="Test Expense",
        timeline=sample_timeline,
        value=10000,
    )


@pytest.fixture
def sample_timeline() -> Timeline:
    """Provides a sample Timeline fixture for tests."""
    return Timeline(start_date=date(2024, 1, 1), duration_months=12)


def test_recovery_base_instantiation(sample_expense: OpExItemBase):
    """Test successful instantiation of RecoveryBase."""
    rec = RecoveryBase(
        expenses=sample_expense,
        structure="net",
    )
    assert rec.structure == "net"
    assert isinstance(rec.expense_pool, ExpensePoolBase)


def test_recovery_method_base_instantiation(sample_expense: OpExItemBase):
    """Test successful instantiation of RecoveryMethodBase."""
    rec_item = RecoveryBase(expenses=sample_expense, structure="net")
    method = RecoveryMethodBase(name="Test Method", recoveries=[rec_item])
    assert method.name == "Test Method"
    assert len(method.recoveries) == 1


def test_recovery_base_validator_base_stop_fails(sample_expense: OpExItemBase):
    """Test validator fails for base_stop structure without base_amount."""
    with pytest.raises(ValueError, match="base_amount is required for base_stop"):
        RecoveryBase(
            expenses=sample_expense,
            structure="base_stop",
            base_amount=None,  # Should fail
        )


def test_recovery_base_validator_base_stop_succeeds(sample_expense: OpExItemBase):
    """Test validator succeeds for base_stop structure with base_amount."""
    RecoveryBase(
        expenses=sample_expense,
        structure="base_stop",
        base_amount=10.0,  # Should succeed
    )


def test_recovery_base_validator_fixed_fails(sample_expense: OpExItemBase):
    """Test validator fails for fixed structure without base_amount."""
    with pytest.raises(ValueError, match="base_amount is required for fixed"):
        RecoveryBase(
            expenses=sample_expense,
            structure="fixed",
        )


def test_recovery_base_validator_base_year_fails(sample_expense: OpExItemBase):
    """Test validator fails for base_year structure without base_year."""
    with pytest.raises(ValueError, match="base_year is required for base_year"):
        RecoveryBase(
            expenses=sample_expense,
            structure="base_year",
            base_year=None,  # Should fail
        )


def test_recovery_base_validator_base_year_succeeds(sample_expense: OpExItemBase):
    """Test validator succeeds for base_year structure with base_year."""
    RecoveryBase(
        expenses=sample_expense,
        structure="base_year",
        base_year=2024,  # Should succeed
    )
