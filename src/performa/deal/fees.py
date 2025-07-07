"""
Developer Fee Models for Real Estate Deals

This module defines fee structures for real estate development and acquisition deals,
with support for flexible payment schedules and both fixed and percentage-based amounts.
"""

from typing import Literal, Optional, Union
from uuid import UUID, uuid4

from pydantic import Field, computed_field, field_validator, model_validator

from ..common.primitives import FloatBetween0And1, Model, PositiveFloat


class DeveloperFee(Model):
    """
    Developer fee model for real estate deals.
    
    Supports both fixed dollar amounts and percentage-based fees with flexible
    payment timing to match industry practice.
    
    Common Industry Patterns:
    - 3-5% of total project cost for development deals
    - 1-2% of acquisition price for acquisition deals
    - Payment timing varies: upfront, at completion, or split schedule
    
    Examples:
        # Fixed amount fee
        fee = DeveloperFee(
            name="Development Fee",
            amount=500_000,
            payment_timing="completion"
        )
        
        # Percentage-based fee (4% of total cost)
        fee = DeveloperFee(
            name="Development Fee", 
            amount=0.04,
            is_percentage=True,
            payment_timing="split"
        )
    """
    
    # Core Identity
    uid: UUID = Field(default_factory=uuid4)
    name: str = Field(default="Developer Fee", description="Fee name for identification")
    
    # Fee Structure
    amount: Union[PositiveFloat, FloatBetween0And1] = Field(
        ..., 
        description="Fee amount (fixed dollars or percentage of total cost)"
    )
    
    is_percentage: bool = Field(
        default=False,
        description="Whether amount is a percentage of total project cost"
    )
    
    payment_timing: Literal["upfront", "completion", "split"] = Field(
        default="completion",
        description="When the fee is paid during the project lifecycle"
    )
    
    # Split Payment Configuration (only used when payment_timing="split")
    upfront_percentage: FloatBetween0And1 = Field(
        default=0.5,
        description="Percentage paid upfront when using split payment timing"
    )
    
    # Optional Details
    description: Optional[str] = Field(
        default=None, 
        description="Additional fee description"
    )
    
    @model_validator(mode="after")
    def validate_percentage_amount_range(self) -> "DeveloperFee":
        """Validate amount is reasonable when it's a percentage."""
        if self.is_percentage:
            # For percentages, validate reasonable range (0.1% to 20%)
            if not (0.001 <= self.amount <= 0.20):
                raise ValueError(
                    f"Percentage-based fee amount must be between 0.1% and 20%, got {self.amount:.1%}"
                )
        return self
    
    @computed_field
    @property
    def completion_percentage(self) -> float:
        """Percentage paid at completion when using split payment timing."""
        return 1.0 - self.upfront_percentage
    
    def calculate_total_fee(self, total_project_cost: float) -> float:
        """
        Calculate the total dollar amount of the fee.
        
        Args:
            total_project_cost: Total project cost for percentage-based calculations
            
        Returns:
            Total fee amount in dollars
        """
        if self.is_percentage:
            return self.amount * total_project_cost
        else:
            return self.amount
    
    def calculate_upfront_fee(self, total_project_cost: float) -> float:
        """
        Calculate the upfront fee amount.
        
        Args:
            total_project_cost: Total project cost for percentage-based calculations
            
        Returns:
            Upfront fee amount in dollars
        """
        total_fee = self.calculate_total_fee(total_project_cost)
        
        if self.payment_timing == "upfront":
            return total_fee
        elif self.payment_timing == "completion":
            return 0.0
        else:  # split
            return total_fee * self.upfront_percentage
    
    def calculate_completion_fee(self, total_project_cost: float) -> float:
        """
        Calculate the completion fee amount.
        
        Args:
            total_project_cost: Total project cost for percentage-based calculations
            
        Returns:
            Completion fee amount in dollars
        """
        total_fee = self.calculate_total_fee(total_project_cost)
        
        if self.payment_timing == "upfront":
            return 0.0
        elif self.payment_timing == "completion":
            return total_fee
        else:  # split
            return total_fee * self.completion_percentage
    
    def __str__(self) -> str:
        if self.is_percentage:
            amount_str = f"{self.amount:.1%} of total cost"
        else:
            amount_str = f"${self.amount:,.0f}"
        
        return f"{self.name}: {amount_str} ({self.payment_timing})"


# Export the main classes
__all__ = [
    "DeveloperFee",
] 