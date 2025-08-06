# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Test utilities and fixtures for Performa testing.

This module provides convenient utilities for creating test objects
without dealing with complex required fields and dependencies.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from performa.core.primitives import Timeline
from performa.deal.distribution_calculator import DistributionCalculator
from performa.deal.entities import Partner
from performa.deal.partnership import CarryPromote, PartnershipStructure


# Timeline Utilities  
def simple_timeline(duration_months: int = 12) -> Timeline:
    """Create a simple timeline for testing without complexity."""
    return Timeline(
        start_date=pd.Timestamp("2024-01-01"),
        duration_months=duration_months
    )


def create_test_timeline(
    start_date: str = "2024-01-01", 
    duration_months: int = 12
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
        start_date=pd.Timestamp(start_date),
        duration_months=duration_months
    )


# Partnership Utilities
def create_simple_partnership(
    lp_share: float = 0.8,
    gp_share: Optional[float] = None,
    distribution_method: str = "pari_passu"
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
        partners=[lp, gp],
        distribution_method=distribution_method
    )


def create_waterfall_partnership(
    lp_share: float = 0.8,
    preferred_return_rate: float = 0.08,
    promote_rate: float = 0.20
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
        preferred_return_rate=preferred_return_rate,
        promote_rate=promote_rate
    )
    
    return PartnershipStructure(
        partners=[lp, gp],
        distribution_method="waterfall",
        promote=carry_promote
    )


# Distribution Calculator Utilities
def create_distribution_calculator(
    distribution_method: str = "pari_passu",
    lp_share: float = 0.8,
    **kwargs
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
        partnership = create_simple_partnership(lp_share, distribution_method=distribution_method)
    else:
        partnership = create_waterfall_partnership(lp_share, **kwargs)
    
    return DistributionCalculator(partnership)


# Cash Flow Utilities
def create_simple_cash_flows(
    timeline: Timeline,
    investment_amount: float = 1_000_000,
    return_amount: float = 1_500_000
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
    cash_flows.iloc[-1] = return_amount      # Return (positive)
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
    required_keys = ["distribution_method", "partner_distributions", "total_metrics", "partnership_summary"]
    
    for key in required_keys:
        assert key in results, f"Missing key: {key}"
    
    # Check partner_distributions structure
    assert isinstance(results["partner_distributions"], dict), "partner_distributions must be dict"
    
    for partner_name, partner_data in results["partner_distributions"].items():
        partner_required_keys = [
            "partner_info", "cash_flows", "total_investment", 
            "total_distributions", "net_profit", "equity_multiple", 
            "irr", "ownership_percentage"
        ]
        
        for key in partner_required_keys:
            assert key in partner_data, f"Missing partner key {key} for {partner_name}"
    
    return True


def validate_cash_flow_conservation(results: dict, original_cash_flows: pd.Series) -> bool:
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
    assert abs(total_distributions - positive_cash_flows) < 1.0, \
        f"Conservation error: {total_distributions} vs {positive_cash_flows}"
    
    return True


# Export commonly used utilities at module level
__all__ = [
    "create_test_timeline",
    "create_simple_partnership", 
    "create_waterfall_partnership",
    "create_distribution_calculator",
    "create_simple_cash_flows",
    "validate_distribution_results_structure",
    "validate_cash_flow_conservation"
] 