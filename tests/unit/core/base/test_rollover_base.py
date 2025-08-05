# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest
from uuid import uuid4

from performa.core.base import (
    RolloverLeaseTermsBase,
    RolloverProfileBase,
)
from performa.core.primitives import (
    FrequencyEnum,
    UponExpirationEnum,
)


def test_rollover_profile_base_instantiation():
    """Test successful instantiation of RolloverProfileBase and its nested models."""
    market_terms = RolloverLeaseTermsBase(
        term_months=120,
        market_rent=65.0,
        frequency=FrequencyEnum.ANNUAL,
    )
    
    renewal_terms = RolloverLeaseTermsBase(
        term_months=60,
        market_rent=60.0,
    )

    profile = RolloverProfileBase(
        name="Standard Office Rollover",
        term_months=120, # This seems redundant with market_terms, but testing as is
        renewal_probability=0.75,
        downtime_months=6,
        market_terms=market_terms,
        renewal_terms=renewal_terms,
        option_terms=None, # Testing with None
        upon_expiration=UponExpirationEnum.MARKET,
    )

    assert profile.name == "Standard Office Rollover"
    assert profile.renewal_probability == 0.75
    assert profile.market_terms.term_months == 120
    assert profile.renewal_terms.market_rent == 60.0
    assert profile.target_absorption_plan_id is None  # Default should be None


def test_rollover_profile_target_absorption_plan_id():
    """Test target_absorption_plan_id field functionality for value-add scenarios."""
    market_terms = RolloverLeaseTermsBase(
        term_months=12,
        market_rent=2500.0,
        frequency=FrequencyEnum.MONTHLY,
    )
    
    renewal_terms = RolloverLeaseTermsBase(
        term_months=12,
        market_rent=2400.0,
    )

    # Test with target_absorption_plan_id set
    test_plan_id = uuid4()
    profile = RolloverProfileBase(
        name="Value-Add Renovation Profile",
        term_months=12,
        renewal_probability=0.0,  # No renewals during renovation
        downtime_months=2,  # 2 months for renovation
        market_terms=market_terms,
        renewal_terms=renewal_terms,
        upon_expiration=UponExpirationEnum.REABSORB,
        target_absorption_plan_id=test_plan_id
    )

    assert profile.target_absorption_plan_id == test_plan_id
    assert profile.upon_expiration == UponExpirationEnum.REABSORB
    assert profile.downtime_months == 2


def test_rollover_profile_reabsorb_validation_success():
    """Test that REABSORB + target_absorption_plan_id combination is allowed."""
    market_terms = RolloverLeaseTermsBase(
        term_months=12,
        market_rent=2500.0,
    )
    
    renewal_terms = RolloverLeaseTermsBase(
        term_months=12,
        market_rent=2400.0,
    )

    # This should work - REABSORB with target_absorption_plan_id
    test_plan_id = uuid4()
    profile = RolloverProfileBase(
        name="Valid Value-Add Profile",
        term_months=12,
        renewal_probability=0.0,
        downtime_months=3,
        market_terms=market_terms,
        renewal_terms=renewal_terms,
        upon_expiration=UponExpirationEnum.REABSORB,
        target_absorption_plan_id=test_plan_id
    )
    
    # Should not raise any validation errors
    assert profile.target_absorption_plan_id == test_plan_id


def test_rollover_profile_reabsorb_validation_none_target():
    """Test that REABSORB without target_absorption_plan_id is allowed (legacy behavior)."""
    market_terms = RolloverLeaseTermsBase(
        term_months=12,
        market_rent=2500.0,
    )
    
    renewal_terms = RolloverLeaseTermsBase(
        term_months=12,
        market_rent=2400.0,
    )

    # This should work - REABSORB without target_absorption_plan_id (legacy)
    profile = RolloverProfileBase(
        name="Legacy REABSORB Profile",
        term_months=12,
        renewal_probability=0.0,
        downtime_months=1,
        market_terms=market_terms,
        renewal_terms=renewal_terms,
        upon_expiration=UponExpirationEnum.REABSORB,
        target_absorption_plan_id=None
    )
    
    # Should not raise any validation errors
    assert profile.target_absorption_plan_id is None


def test_rollover_profile_target_absorption_plan_validation_error():
    """Test that target_absorption_plan_id with non-REABSORB status raises validation error."""
    market_terms = RolloverLeaseTermsBase(
        term_months=12,
        market_rent=2500.0,
    )
    
    renewal_terms = RolloverLeaseTermsBase(
        term_months=12,
        market_rent=2400.0,
    )

    test_plan_id = uuid4()
    
    # This should fail - target_absorption_plan_id with MARKET status
    with pytest.raises(ValueError, match="target_absorption_plan_id can only be specified when upon_expiration='reabsorb'"):
        RolloverProfileBase(
            name="Invalid Profile",
            term_months=12,
            renewal_probability=0.75,
            downtime_months=0,
            market_terms=market_terms,
            renewal_terms=renewal_terms,
            upon_expiration=UponExpirationEnum.MARKET,  # Wrong status
            target_absorption_plan_id=test_plan_id
        )


def test_rollover_profile_renew_downtime_validation():
    """Test that RENEW profiles with downtime raise validation error."""
    market_terms = RolloverLeaseTermsBase(
        term_months=12,
        market_rent=2500.0,
    )
    
    renewal_terms = RolloverLeaseTermsBase(
        term_months=12,
        market_rent=2400.0,
    )

    # This should fail - RENEW with downtime
    with pytest.raises(ValueError, match="RENEW upon_expiration requires downtime_months=0"):
        RolloverProfileBase(
            name="Invalid RENEW Profile",
            term_months=12,
            renewal_probability=1.0,
            downtime_months=2,  # Invalid - should be 0 for RENEW
            market_terms=market_terms,
            renewal_terms=renewal_terms,
            upon_expiration=UponExpirationEnum.RENEW,
        )
