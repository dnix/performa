# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Test utilities and fixtures for Performa testing.

This module provides convenient utilities for creating test objects
without dealing with complex required fields and dependencies.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd
import pytest

from performa.core.capital import CapitalPlan
from performa.core.ledger import Ledger
from performa.core.primitives import AssetTypeEnum, GlobalSettings, Timeline
from performa.deal import Deal
from performa.deal.acquisition import AcquisitionTerms
from performa.deal.distribution_calculator import DistributionCalculator
from performa.deal.entities import Partner
from performa.deal.orchestrator import DealContext
from performa.deal.partnership import CarryPromote, PartnershipStructure
from performa.development.project import DevelopmentProject


# Timeline Utilities
def simple_timeline(duration_months: int = 12) -> Timeline:
    """Create a simple timeline for testing without complexity."""
    return Timeline(
        start_date=pd.Timestamp("2024-01-01"), duration_months=duration_months
    )


def create_test_timeline(
    start_date: str = "2024-01-01", duration_months: int = 12
) -> Timeline:
    """
    Create a timeline for testing.

    Args:
        start_date: Start date in YYYY-MM-DD format
        duration_months: Duration in months

    Returns:
        Timeline object ready for testing

    Example:
        >>> timeline = create_test_timeline("2024-01-01", 24)
        >>> print(timeline.duration_months)
        24
    """
    return Timeline(
        start_date=pd.Timestamp(start_date), duration_months=duration_months
    )


# Partnership Utilities
def create_simple_partnership(
    lp_share: float = 0.8,
    gp_share: Optional[float] = None,
    distribution_method: str = "pari_passu",
) -> PartnershipStructure:
    """
    Create a basic LP/GP partnership for testing.

    Args:
        lp_share: LP ownership percentage (default 80%)
        gp_share: GP ownership percentage (default 1 - lp_share)
        distribution_method: "pari_passu" or "waterfall"

    Returns:
        PartnershipStructure ready for testing

    Example:
        >>> partnership = create_simple_partnership(0.75, distribution_method="waterfall")
        >>> len(partnership.partners)
        2
    """
    if gp_share is None:
        gp_share = 1.0 - lp_share

    lp = Partner(name="LP", kind="LP", share=lp_share)
    gp = Partner(name="GP", kind="GP", share=gp_share)

    return PartnershipStructure(
        partners=[lp, gp], distribution_method=distribution_method
    )


def create_waterfall_partnership(
    lp_share: float = 0.8,
    preferred_return_rate: float = 0.08,
    promote_rate: float = 0.20,
) -> PartnershipStructure:
    """
    Create a partnership with waterfall distribution for testing.

    Args:
        lp_share: LP ownership percentage
        preferred_return_rate: Preferred return rate (e.g., 0.08 for 8%)
        promote_rate: Promote rate for GP (e.g., 0.20 for 20%)

    Returns:
        PartnershipStructure with waterfall distribution

    Example:
        >>> partnership = create_waterfall_partnership()
        >>> partnership.has_promote
        True
    """
    lp = Partner(name="LP", kind="LP", share=lp_share)
    gp = Partner(name="GP", kind="GP", share=1.0 - lp_share)

    carry_promote = CarryPromote(
        pref_hurdle_rate=preferred_return_rate, promote_rate=promote_rate
    )

    return PartnershipStructure(
        partners=[lp, gp], distribution_method="waterfall", promote=carry_promote
    )


# Distribution Calculator Utilities
def create_distribution_calculator(
    distribution_method: str = "pari_passu", lp_share: float = 0.8, **kwargs
) -> DistributionCalculator:
    """
    Create a DistributionCalculator for testing.

    Args:
        distribution_method: "pari_passu" or "waterfall"
        lp_share: LP ownership percentage
        **kwargs: Additional arguments for waterfall (preferred_return_rate, promote_rate)

    Returns:
        DistributionCalculator ready for testing

    Example:
        >>> calc = create_distribution_calculator("waterfall", preferred_return_rate=0.10)
        >>> calc.partnership.distribution_method
        'waterfall'
    """
    if distribution_method == "pari_passu":
        partnership = create_simple_partnership(
            lp_share, distribution_method=distribution_method
        )
    else:
        partnership = create_waterfall_partnership(lp_share, **kwargs)

    return DistributionCalculator(partnership)


# Cash Flow Utilities
def create_simple_cash_flows(
    timeline: Timeline,
    investment_amount: float = 1_000_000,
    return_amount: float = 1_500_000,
) -> pd.Series:
    """
    Create simple cash flows for testing: investment at start, return at end.

    Args:
        timeline: Timeline object
        investment_amount: Initial investment (positive number, will be made negative)
        return_amount: Final return amount

    Returns:
        Series with investment at start and return at end

    Example:
        >>> timeline = create_test_timeline(duration_months=12)
        >>> cash_flows = create_simple_cash_flows(timeline, 1000, 1200)
        >>> cash_flows.iloc[0]
        -1000.0
        >>> cash_flows.iloc[-1]
        1200.0
    """
    cash_flows = pd.Series(0.0, index=timeline.period_index)
    cash_flows.iloc[0] = -investment_amount  # Investment (negative)
    cash_flows.iloc[-1] = return_amount  # Return (positive)
    return cash_flows


# Validation Utilities
def validate_distribution_results_structure(results: dict) -> bool:
    """
    Validate that distribution results have the expected structure.

    Args:
        results: Results from DistributionCalculator

    Returns:
        True if structure is valid

    Raises:
        AssertionError: If structure is invalid

    Example:
        >>> calc = create_distribution_calculator()
        >>> timeline = create_test_timeline()
        >>> cash_flows = create_simple_cash_flows(timeline)
        >>> results = calc.calculate_pari_passu_distribution(cash_flows, timeline)
        >>> validate_distribution_results_structure(results)
        True
    """
    required_keys = [
        "distribution_method",
        "partner_distributions",
        "total_metrics",
        "partnership_summary",
    ]

    for key in required_keys:
        assert key in results, f"Missing key: {key}"

    # Check partner_distributions structure
    assert isinstance(results["partner_distributions"], dict), (
        "partner_distributions must be dict"
    )

    for partner_name, partner_data in results["partner_distributions"].items():
        partner_required_keys = [
            "partner_info",
            "cash_flows",
            "total_investment",
            "total_distributions",
            "net_profit",
            "equity_multiple",
            "irr",
            "ownership_percentage",
        ]

        for key in partner_required_keys:
            assert key in partner_data, f"Missing partner key {key} for {partner_name}"

    return True


def validate_cash_flow_conservation(
    results: dict, original_cash_flows: pd.Series
) -> bool:
    """
    Validate that total distributions equal positive cash flows (conservation).

    Args:
        results: Results from DistributionCalculator
        original_cash_flows: Original cash flow series

    Returns:
        True if conservation holds

    Example:
        >>> calc = create_distribution_calculator()
        >>> timeline = create_test_timeline()
        >>> cash_flows = create_simple_cash_flows(timeline)
        >>> results = calc.calculate_pari_passu_distribution(cash_flows, timeline)
        >>> validate_cash_flow_conservation(results, cash_flows)
        True
    """
    total_distributions = results["total_metrics"]["total_distributions"]
    positive_cash_flows = original_cash_flows[original_cash_flows > 0].sum()

    # Allow small rounding errors
    assert abs(total_distributions - positive_cash_flows) < 1.0, (
        f"Conservation error: {total_distributions} vs {positive_cash_flows}"
    )

    return True


# Pytest Fixtures
@pytest.fixture
def sample_timeline():
    """Create a 48-month timeline for testing."""
    return create_test_timeline("2024-01-01", 48)


@pytest.fixture
def sample_settings():
    """Create default global settings for testing."""
    return GlobalSettings()


@pytest.fixture
def sample_ledger():
    """Create an empty ledger for testing."""
    return Ledger()


@pytest.fixture
def sample_deal(sample_timeline):
    """
    Create a minimal deal for testing construction loans.

    Uses a minimal DevelopmentProject as the asset since Deal requires a proper asset type.
    Construction loan tests focus on debt logic, so the asset can be minimal.
    """
    # Create minimal development project
    project = DevelopmentProject(
        name="Test Development Project",
        property_type=AssetTypeEnum.MULTIFAMILY,
        gross_area=10000.0,
        net_rentable_area=8500.0,
        construction_plan=CapitalPlan(name="Test Construction Plan", capital_items=[]),
        blueprints=[],
    )

    # Create minimal acquisition
    acquisition = AcquisitionTerms(
        name="Test Land Acquisition",
        timeline=sample_timeline,
        value=3_500_000.0,
        acquisition_date=date(2024, 1, 1),
        closing_costs_rate=0.03,
    )

    return Deal(
        name="Test Deal - Construction Loan Testing",
        asset=project,
        acquisition=acquisition,
        # Optional fields - can be added in specific tests
        # financing=None,  # Default
        # exit_valuation=None,  # Default
        # equity_partners=None,  # Default
    )


@pytest.fixture
def sample_deal_context(sample_timeline, sample_settings, sample_ledger, sample_deal):
    """
    Create a minimal DealContext for testing construction loan functionality.

    This fixture provides everything needed to test construction facility methods:
    - Timeline for period calculations
    - Settings for global configuration
    - Ledger for transaction recording
    - Deal object for deal-level data

    The context is intentionally minimal - test-specific data (NOI, property value, etc.)
    should be added in individual tests as needed.

    Example:
        ```python
        def test_something(sample_deal_context):
            # Add test-specific NOI data
            noi = pd.Series(10000, index=sample_deal_context.timeline.period_index)
            sample_deal_context.noi_series = noi

            # Use context with facility
            facility.compute_cf(sample_deal_context)
        ```
    """
    return DealContext(
        timeline=sample_timeline,
        settings=sample_settings,
        ledger=sample_ledger,
        deal=sample_deal,
        noi_series=None,  # Test-specific - populate as needed
        project_costs=None,  # Test-specific - populate as needed
    )


# Export commonly used utilities at module level
__all__ = [
    "create_test_timeline",
    "create_simple_partnership",
    "create_waterfall_partnership",
    "create_distribution_calculator",
    "create_simple_cash_flows",
    "validate_distribution_results_structure",
    "validate_cash_flow_conservation",
    # Fixtures
    "sample_timeline",
    "sample_settings",
    "sample_ledger",
    "sample_deal",
    "sample_deal_context",
]
