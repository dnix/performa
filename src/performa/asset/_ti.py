import logging
from datetime import date
from typing import Callable, Literal, Optional, Union

import pandas as pd
from pydantic import model_validator

from ..core._cash_flow import CashFlowModel
from ..core._types import FloatBetween0And1, PositiveInt

logger = logging.getLogger(__name__)


class TenantImprovementAllowance(CashFlowModel):
    """
    Represents tenant improvement allowance provided by landlord.
    
    Extends CashFlowModel. The base `compute_cf` method is used to determine the 
    *total* TI amount, potentially based on a `reference` (e.g., to Property area 
    if TI is $/SF, or an aggregate if TI is % of something, though less common).
    The overridden `compute_cf` then distributes this total amount based on payment terms.
    
    The `reference` attribute, if a string, can refer to either:
      - An attribute of the `Property` object (e.g., "net_rentable_area").
      - The string value of an `AggregateLineKey` enum member.
      The base `compute_cf` call within this class expects the lookup to return a scalar 
      value or a type compatible with the `unit_of_measure` calculation for total amount.
    
    Attributes:
        category: Fixed as "Expense"
        subcategory: Fixed as "TI Allowance"
        payment_method: How TI is paid (upfront or amortized)
        payment_date: When upfront payment is made (defaults to lease start)
        interest_rate: Interest rate for amortization (if applicable)
        amortization_term_months: Period over which to amortize (if applicable)
    """
    # Inherit core fields from CashFlowModel
    # category will be fixed as "Expense"
    category: str = "Expense"
    subcategory: str = "TI Allowance"
    
    # TI-specific fields
    payment_method: Literal["upfront", "amortized"] = "upfront"
    payment_date: Optional[date] = None
    interest_rate: Optional[FloatBetween0And1] = None
    amortization_term_months: Optional[PositiveInt] = None
    
    @model_validator(mode='after')
    def validate_amortization(self) -> 'TenantImprovementAllowance':
        """Validate that amortization parameters are provided when needed."""
        if self.payment_method == "amortized":
            if self.interest_rate is None:
                raise ValueError("interest_rate is required for amortized TI")
            if self.amortization_term_months is None:
                raise ValueError("amortization_term_months is required for amortized TI")
        return self
    
    def compute_cf(
        self,
        lookup_fn: Optional[Callable[[str], Union[float, pd.Series]]] = None
    ) -> pd.Series:
        """
        Compute TI cash flow series, handling both upfront and amortized payment methods.
        
        For upfront payments, returns a single payment at the specified date.
        For amortized payments, calculates a loan-like payment schedule.
        
        Args:
            lookup_fn: Optional function to resolve references
            
        Returns:
            Monthly cash flow series
        """
        # Get the base cash flow using CashFlowModel logic
        logger.debug(f"Computing cash flow for TI Allowance: '{self.name}' ({self.model_id})")
        logger.debug(f"  Payment Method: {self.payment_method}")
        logger.debug("  Calculating base total TI amount using super().compute_cf.")
        base_cf = super().compute_cf(lookup_fn)
        total_amount = base_cf.sum()
        logger.debug(f"  Calculated base total TI amount: {total_amount:.2f}")
        
        # If upfront payment, we return a single payment at the specified date
        if self.payment_method == "upfront":
            payment_date = self.payment_date or self.timeline.start_date.to_timestamp().date()
            payment_period = pd.Period(payment_date, freq="M")
            
            # Create a series with zero values except for the payment period
            ti_cf = pd.Series(0, index=self.timeline.period_index)
            if payment_period in ti_cf.index:
                # Put the entire TI amount in the payment period
                total_amount = base_cf.sum()
                ti_cf[payment_period] = total_amount
            
            logger.debug(f"  Upfront payment of {total_amount:.2f} scheduled for {payment_period}.")
            return ti_cf
        
        # If amortized, we calculate a loan-like payment schedule
        elif self.payment_method == "amortized":
            assert self.interest_rate is not None
            assert self.amortization_term_months is not None
            
            # Calculate total TI amount
            total_amount = base_cf.sum()
            
            # Calculate monthly payment using standard loan amortization formula
            monthly_rate = self.interest_rate / 12
            monthly_payment = total_amount * (monthly_rate * (1 + monthly_rate) ** self.amortization_term_months) / \
                             ((1 + monthly_rate) ** self.amortization_term_months - 1)
            
            # Create a series with the calculated monthly payments
            # restricted to the amortization period
            amort_end = self.timeline.start_date + self.amortization_term_months - 1
            amort_periods = pd.period_range(
                start=self.timeline.start_date,
                end=min(amort_end, self.timeline.end_date),
                freq="M"
            )
            
            ti_cf = pd.Series(0, index=self.timeline.period_index)
            ti_cf.loc[amort_periods] = monthly_payment
            
            logger.debug(f"  Amortized payment calculated: {monthly_payment:.2f} per month for {self.amortization_term_months} months.")
            return ti_cf
        
        # This should never happen due to the validator, but included for completeness
        else:
            return pd.Series(0, index=self.timeline.period_index)

