from __future__ import annotations

import pytest

from performa.common.base._rollover_base import (
    RolloverLeaseTermsBase,
    RolloverProfileBase,
)
from performa.common.primitives import (
    FrequencyEnum,
    UnitOfMeasureEnum,
    UponExpirationEnum,
)


def test_rollover_profile_base_instantiation():
    """Test successful instantiation of RolloverProfileBase and its nested models."""
    market_terms = RolloverLeaseTermsBase(
        term_months=120,
        market_rent=65.0,
        unit_of_measure=UnitOfMeasureEnum.PER_UNIT,
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
