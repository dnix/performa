# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import date
from typing import List, Optional, Union

from ...core.base import RentEscalationBase
from ...core.primitives import PropertyAttributeKey
from ...core.primitives.cash_flow import ReferenceKey
from ...core.primitives.growth_rates import FixedGrowthRate, PercentageGrowthRate


class OfficeRentEscalation(RentEscalationBase):
    """
    Office-specific rent escalation structure.
    Inherits all behavior from the base class for now.
    """
    pass


# Helper functions for common escalation patterns

def create_stepped_percentage_escalations(
    start_month: int,
    annual_rates: List[float],
    years_per_step: int = 1
) -> List[OfficeRentEscalation]:
    """
    Create stepped percentage escalations (most common pattern).
    
    Args:
        start_month: Month when escalations begin (1-indexed from lease start)
        annual_rates: List of annual percentage rates (e.g., [0.02, 0.03, 0.025])
        years_per_step: Years each rate applies (default: 1 year per step)
        
    Returns:
        List of OfficeRentEscalation objects
        
    Example:
        # 2% in year 2, 3% in year 3, 2.5% in year 4+
        escalations = create_stepped_percentage_escalations(
            start_month=13,  # Start in month 13 (year 2)
            annual_rates=[0.02, 0.03, 0.025]
        )
    """
    escalations = []
    current_month = start_month
    
    for i, rate in enumerate(annual_rates):
        is_final = (i == len(annual_rates) - 1)
        
        escalation = OfficeRentEscalation(
            type="percentage",
            rate=rate,
            is_relative=True,
            start_month=current_month,
            recurring=is_final,  # Only the final rate should be recurring
            frequency_months=12 if is_final else None
        )
        escalations.append(escalation)
        
        if not is_final:
            current_month += years_per_step * 12
    
    return escalations


def create_stepped_fixed_escalations(
    start_month: int,
    annual_amounts: List[float],
    reference: Optional[ReferenceKey] = PropertyAttributeKey.NET_RENTABLE_AREA,
    years_per_step: int = 1
) -> List[OfficeRentEscalation]:
    """
    Create stepped fixed dollar escalations.
    
    Args:
        start_month: Month when escalations begin (1-indexed from lease start)
        annual_amounts: List of annual dollar amounts (e.g., [1.50, 1.75, 2.00])
        unit_of_measure: PER_UNIT ($/SF) or CURRENCY (total $)
        years_per_step: Years each amount applies (default: 1 year per step)
        
    Returns:
        List of OfficeRentEscalation objects
        
    Example:
        # $1.50/SF in year 2, $1.75/SF in year 3, $2.00/SF in year 4+
        escalations = create_stepped_fixed_escalations(
            start_month=13,
            annual_amounts=[1.50, 1.75, 2.00],
            reference=PropertyAttributeKey.NET_RENTABLE_AREA
        )
    """
    escalations = []
    current_month = start_month
    
    for i, amount in enumerate(annual_amounts):
        is_final = (i == len(annual_amounts) - 1)
        
        escalation = OfficeRentEscalation(
            type="fixed",
            rate=amount,
            reference=reference,
            is_relative=False,
            start_month=current_month,
            recurring=is_final,  # Only the final amount should be recurring
            frequency_months=12 if is_final else None
        )
        escalations.append(escalation)
        
        if not is_final:
            current_month += years_per_step * 12
    
    return escalations


def create_simple_annual_escalation(
    rate: float,
    escalation_type: str = "percentage",
    start_month: int = 13,
    reference: Optional[ReferenceKey] = None
) -> OfficeRentEscalation:
    """
    Create a simple recurring annual escalation.
    
    Args:
        rate: The escalation rate (0-1 for percentage, dollar amount for fixed)
        escalation_type: "percentage" or "fixed"
        start_month: Month when escalations begin (default: 13 = year 2)
        reference: Reference for the escalation (PropertyAttributeKey, UnleveredAggregateLineKey, or None)
        
    Returns:
        Single OfficeRentEscalation object
        
    Example:
        # Simple 3% annual escalation starting in year 2
        escalation = create_simple_annual_escalation(0.03)
    """
    return OfficeRentEscalation(
        type=escalation_type,
        rate=rate,
        reference=reference,
        is_relative=(escalation_type == "percentage"),
        start_month=start_month,
        recurring=True,
        frequency_months=12
    )


def create_escalations_from_absolute_dates(
    escalation_schedule: List[tuple[date, float, str]],
    reference: Optional[ReferenceKey] = None
) -> List[OfficeRentEscalation]:
    """
    Create escalations based on absolute dates (less common, but supported).
    
    Args:
        escalation_schedule: List of (date, rate, type) tuples
        unit_of_measure: Unit of measure for the escalations
        
    Returns:
        List of OfficeRentEscalation objects
        
    Example:
        # Specific date-based escalations
        escalations = create_escalations_from_absolute_dates([
            (date(2025, 1, 1), 0.02, "percentage"),
            (date(2026, 1, 1), 0.03, "percentage"),
            (date(2027, 1, 1), 0.025, "percentage")
        ])
    """
    escalations = []
    
    for i, (escalation_date, rate, escalation_type) in enumerate(escalation_schedule):
        is_final = (i == len(escalation_schedule) - 1)
        
        escalation = OfficeRentEscalation(
            type=escalation_type,
            rate=rate,
            reference=reference,
            is_relative=(escalation_type == "percentage"),
            start_date=escalation_date,
            recurring=is_final,  # Only the final escalation should be recurring
            frequency_months=12 if is_final else None
        )
        escalations.append(escalation)
    
    return escalations 