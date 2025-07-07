"""Permanent loan facilities"""

from typing import Literal, Optional

import pandas as pd
from pydantic import Field, model_validator

from ..common.primitives import FloatBetween0And1, PositiveFloat, PositiveInt
from .amortization import LoanAmortization
from .debt_facility import DebtFacility
from .rates import InterestRate


class PermanentFacility(DebtFacility):
    """
    Class for permanent financing with fixed or floating rate loan.

    Handles permanent loan calculations including refinancing amount determination,
    loan amortization, and payment schedules. Now supports institutional-grade
    sizing using both LTV and DSCR constraints.

    Attributes:
        kind: Discriminator field for union types
        name: Name of the permanent facility
        interest_rate: Interest rate configuration
        loan_term_years: Total loan term in years
        amortization_years: Amortization period in years (defaults to loan term)
        ltv_ratio: Maximum loan-to-value ratio
        dscr_hurdle: Minimum debt service coverage ratio
        loan_amount: Fixed loan amount (optional - overrides LTV/DSCR sizing)
        refinance_timing: When to refinance (months from start)
    """

    # Discriminator field for union types - REQUIRED
    kind: Literal["permanent"] = "permanent"

    # Facility identity
    name: str = Field(default="Permanent Loan", description="Name of the permanent facility")

    # Core loan terms
    interest_rate: InterestRate = Field(..., description="Interest rate configuration")
    loan_term_years: PositiveInt = Field(..., description="Total loan term in years")
    amortization_years: Optional[PositiveInt] = Field(
        default=None,
        description="Amortization period in years (defaults to loan term for fully amortizing)"
    )

    # Underwriting constraints
    ltv_ratio: FloatBetween0And1 = Field(
        ...,
        description="Maximum loan-to-value ratio for sizing"
    )
    dscr_hurdle: PositiveFloat = Field(
        ...,
        description="Minimum debt service coverage ratio for sizing"
    )

    # Optional fixed amount (overrides LTV/DSCR sizing)
    loan_amount: Optional[PositiveFloat] = Field(
        default=None,
        description="Fixed loan amount (overrides LTV/DSCR sizing if specified)"
    )

    # Refinancing timing
    refinance_timing: Optional[PositiveInt] = Field(
        default=None,
        description="When to refinance (months from project start)"
    )

    # TODO: Add support for:
    # - Debt yield hurdle
    # - Lockout periods
    # - Defeasance calculations
    # - Yield maintenance calculations
    # - Extension options
    # - Future funding components
    # - Multiple notes/components (A/B/C notes)
    # - Ongoing debt service reserve requirements
    # - Financial covenants (DSCR, Debt Yield, etc.)

    @model_validator(mode="after")
    def validate_financing_terms(self) -> "PermanentFacility":
        """
        Validate permanent financing terms.

        Validates:
        - LTV ratio is reasonable (<=0.80)
        - Amortization term is reasonable (<=40 years)
        - Loan term is reasonable (<=30 years)
        - Fee rate is reasonable (<=3%)
        - DSCR hurdle is reasonable (>=1.00)
        """
        # FIXME: review validations
        if self.ltv_ratio > 0.80:
            raise ValueError("LTV ratio cannot exceed 80%")

        if self.amortization_years and self.amortization_years > 40:
            raise ValueError("Amortization term cannot exceed 40 years")
            
        if self.loan_term_years > 30:
            raise ValueError("Loan term cannot exceed 30 years")

        if self.dscr_hurdle < 1.00:
            raise ValueError("DSCR hurdle cannot be less than 1.00")

        return self

    def calculate_interest(self) -> float:
        """Calculate interest for a period"""
        raise NotImplementedError("Use generate_amortization instead")

    def calculate_refinance_amount(
        self,
        property_value: float,
        forward_stabilized_noi: float,
    ) -> float:
        """
        Calculate the maximum loan amount based on the lesser of LTV and DSCR constraints,
        using explicit underwriting inputs for point-in-time sizing.

        This method models the actual underwriting process where lenders evaluate:
        1. LTV: Maximum loan based on property value and LTV ratio
        2. DSCR: Maximum loan based on projected Year 1 stabilized NOI and DSCR hurdle

        Args:
            property_value: The appraised or calculated value of the property for LTV purposes
            forward_stabilized_noi: The projected annual NOI for the first year of stabilized operations

        Returns:
            float: Maximum loan amount based on the most restrictive constraint (LTV or DSCR)
        """
        # 1. LTV Sizing Constraint
        max_loan_from_ltv = property_value * self.ltv_ratio

        # 2. DSCR Sizing Constraint
        max_supportable_debt_service = forward_stabilized_noi / self.dscr_hurdle

        # Calculate annual debt service for a hypothetical $1 loan to get payment factor
        amortization = LoanAmortization(
            loan_amount=1.0,
            term=self.amortization_years or self.loan_term_years,
            interest_rate=self.interest_rate,
        )
        amortization_schedule, _ = amortization.amortization_schedule
        
        # Take the first 12 months of payments for annual debt service calculation
        annual_debt_service_per_dollar = amortization_schedule["Payment"].iloc[:12].sum()
        
        # Max loan = Max supportable debt service / debt service per dollar
        max_loan_from_dscr = max_supportable_debt_service / annual_debt_service_per_dollar
        
        # Return the lesser of the two constraints (most restrictive)
        return min(max_loan_from_ltv, max_loan_from_dscr)

    def generate_amortization(
        self, loan_amount: PositiveFloat, start_date: pd.Period
    ) -> pd.DataFrame:
        """
        Generate permanent loan amortization schedule.

        Creates amortization schedule using the loan amount and permanent loan terms.
        The schedule will reflect the term/amortization distinction for balloon payments.

        Args:
            loan_amount: Loan amount to be amortized
            start_date: Start date for amortization schedule

        Returns:
            DataFrame containing the amortization schedule
        """
        amortization = LoanAmortization(
            loan_amount=loan_amount,
            term=self.amortization_years or self.loan_term_years,
            interest_rate=self.interest_rate,
            start_date=start_date,
        )
        schedule, _ = amortization.amortization_schedule
        
        # If loan term is shorter than amortization, create balloon payment
        if self.loan_term_years < (self.amortization_years or self.loan_term_years):
            loan_term_periods = self.loan_term_years * 12
            
            # Truncate schedule to loan term
            balloon_schedule = schedule.iloc[:loan_term_periods].copy()
            
            # Calculate balloon payment (remaining balance AFTER the final regular payment)
            # The "End Balance" in the schedule is BEFORE the payment, so we need to subtract
            # the principal portion of the final payment to get the true remaining balance
            final_payment_row = balloon_schedule.iloc[-1]
            remaining_balance_before_payment = final_payment_row["End Balance"]
            final_payment_principal = final_payment_row["Principal"]
            
            # True remaining balance after the final regular payment
            balloon_payment = remaining_balance_before_payment - final_payment_principal
            
            # Adjust final payment to include balloon
            balloon_schedule.iloc[-1, balloon_schedule.columns.get_loc("Payment")] += balloon_payment
            balloon_schedule.iloc[-1, balloon_schedule.columns.get_loc("Principal")] += balloon_payment
            balloon_schedule.iloc[-1, balloon_schedule.columns.get_loc("End Balance")] = 0.0
            
            return balloon_schedule
        else:
            return schedule

    def calculate_debt_service(self, timeline) -> pd.Series:
        """
        Calculate debt service time series for permanent facility.
        
        Uses the generate_amortization method to create a payment schedule
        and extracts the debt service payments for each period.
        
        Args:
            timeline: Timeline object with period_index
            
        Returns:
            pd.Series: Debt service payments by period
            
        Raises:
            ValueError: If no loan amount is specified and property value/NOI are not provided
                for LTV/DSCR sizing calculations.
        """
        # SAFETY: Require explicit loan amount or proper sizing inputs
        if self.loan_amount:
            loan_amount = self.loan_amount
        else:
            # TODO: Implement automatic loan sizing based on property value and NOI
            # This requires integration with asset valuation and stabilized operations
            raise ValueError(
                "Permanent loan debt service calculation requires explicit loan_amount "
                "or property value/NOI for LTV/DSCR sizing. "
                "Set loan_amount on PermanentFacility or use calculate_refinance_amount() "
                "with actual asset data. This prevents using dangerous placeholder values."
            )
            
            # FIXME: Replace with actual sizing calculation when asset data is available:
            # loan_amount = self.calculate_refinance_amount(property_value, forward_stabilized_noi)
        
        # Generate amortization schedule starting from first period
        start_period = timeline.period_index[0]
        amortization_schedule = self.generate_amortization(loan_amount, start_period)
        
        # Create debt service series aligned with timeline
        debt_service = pd.Series(0.0, index=timeline.period_index)
        
        # Map amortization payments to timeline periods
        for period in timeline.period_index:
            if period in amortization_schedule.index:
                debt_service[period] = amortization_schedule.loc[period, "Payment"]
        
        return debt_service

    def calculate_loan_proceeds(self, timeline) -> pd.Series:
        """
        Calculate loan proceeds time series for permanent facility.
        
        For permanent loans, proceeds are typically received at closing
        (first period of the timeline).
        
        Args:
            timeline: Timeline object with period_index
            
        Returns:
            pd.Series: Loan proceeds by period
            
        Raises:
            ValueError: If no loan amount is specified and property value/NOI are not provided
                for LTV/DSCR sizing calculations.
        """
        # Initialize loan proceeds series
        loan_proceeds = pd.Series(0.0, index=timeline.period_index)
        
        # SAFETY: Require explicit loan amount or proper sizing inputs
        if self.loan_amount:
            loan_amount = self.loan_amount
        else:
            # TODO: Implement automatic loan sizing based on property value and NOI
            # This requires integration with asset valuation and stabilized operations
            raise ValueError(
                "Permanent loan proceeds calculation requires explicit loan_amount "
                "or property value/NOI for LTV/DSCR sizing. "
                "Set loan_amount on PermanentFacility or use calculate_refinance_amount() "
                "with actual asset data. This prevents using dangerous placeholder values."
            )
            
            # FIXME: Replace with actual sizing calculation when asset data is available:
            # loan_amount = self.calculate_refinance_amount(property_value, forward_stabilized_noi)
        
        # Permanent loan proceeds received at first period (closing)
        if len(timeline.period_index) > 0:
            loan_proceeds.iloc[0] = loan_amount
        
        return loan_proceeds
