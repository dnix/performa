# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

import pytest
from pydantic import ValidationError

from performa.debt import (
    ConstructionFacility,
    FinancingPlan,
    PermanentFacility,
    create_construction_to_permanent_plan,
)


def test_create_construction_to_permanent_plan_happy_path():
    construction_terms = {
        "name": "Construction Loan",
        "loan_term_months": 24,  # Add construction duration for smart timing
        "tranches": [
            {
                "name": "Senior",
                "interest_rate": {"details": {"rate_type": "fixed", "rate": 0.07}},
                "fee_rate": 0.01,
                "ltc_threshold": 0.60,
            },
            {
                "name": "Mezz",
                "interest_rate": {"details": {"rate_type": "fixed", "rate": 0.10}},
                "fee_rate": 0.02,
                "ltc_threshold": 0.75,
            },
        ],
        "fund_interest_from_reserve": True,
        "interest_reserve_rate": 0.15,
    }

    permanent_terms = {
        "name": "Permanent Loan",
        "interest_rate": {"details": {"rate_type": "fixed", "rate": 0.065}},
        "loan_term_years": 10,
        "ltv_ratio": 0.65,
        "dscr_hurdle": 1.25,
    }

    plan: FinancingPlan = create_construction_to_permanent_plan(
        construction_terms, permanent_terms
    )

    assert isinstance(plan, FinancingPlan)
    assert len(plan.facilities) == 2
    assert isinstance(plan.facilities[0], ConstructionFacility)
    assert isinstance(plan.facilities[1], PermanentFacility)
    assert plan.has_construction_financing is True
    assert plan.has_permanent_financing is True


def test_create_construction_to_permanent_plan_requires_tranches():
    construction_terms = {
        "name": "Construction Loan",
        "loan_term_months": 18,  # Add construction duration for smart timing
    }
    permanent_terms = {
        "name": "Permanent Loan",
        "interest_rate": {"details": {"rate_type": "fixed", "rate": 0.065}},
        "loan_term_years": 10,
        "ltv_ratio": 0.65,
        "dscr_hurdle": 1.25,
    }
    # Should raise ValidationError for incomplete construction parameters
    # (either tranches or full single-facility parameters including loan_amount required)
    with pytest.raises(ValidationError):
        create_construction_to_permanent_plan(construction_terms, permanent_terms)
