"""Permanent loan facilities"""

from typing import Literal

import pandas as pd
from pydantic import Field, model_validator

from ..core._types import FloatBetween0And1, PositiveFloat, PositiveInt
from ._amortization import LoanAmortization
from ._debt_facility import DebtFacility
from ._rates import InterestRate


class PermanentFacility(DebtFacility):
    """
    Class for permanent financing with fixed or floating rate loan.

    Handles permanent loan calculations including refinancing amount determination,
    loan amortization, and payment schedules.

    Attributes:
        interest_rate (InterestRate): Interest rate configuration
        fee_rate (FloatBetween0And1): Upfront fee as percentage of loan amount
        ltv_ratio (FloatBetween0And1): Maximum loan-to-value ratio, defaults to 0.75
        amortization (PositiveInt): Amortization term in years, defaults to 30

    Methods:
        calculate_refinance_amount: Calculate maximum loan amount based on NOI and cap rates
        generate_amortization: Generate detailed loan amortization schedule
    """

    kind: Literal["permanent"] = "permanent"
    interest_rate: InterestRate = Field(..., description="Interest rate configuration")
    fee_rate: FloatBetween0And1 = Field(
        ..., description="Upfront fee rate as percentage of loan amount"
    )
    ltv_ratio: FloatBetween0And1 = Field(
        default=0.75, description="Loan-to-value ratio"
    )
    amortization: PositiveInt = Field(
        default=30, description="Amortization term in years"
    )

    # TODO: Add support for:
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
        - Fee rate is reasonable (<=3%)
        """
        # TODO: review validations
        if self.ltv_ratio > 0.80:
            raise ValueError("LTV ratio cannot exceed 80%")

        if self.amortization > 40:
            raise ValueError("Amortization term cannot exceed 40 years")

        if self.fee_rate > 0.03:
            raise ValueError("Fee rate cannot exceed 3%")

        return self

    def calculate_interest(self) -> float:
        """Calculate interest for a period"""
        raise NotImplementedError("Use generate_amortization instead")

    def calculate_refinance_amount(
        self, noi_by_use: pd.Series, cap_rates: pd.Series
    ) -> float:
        """
        Calculate refinance amount based on NOI and cap rates.

        Calculates property value by capitalizing NOI for each program use,
        then applies the loan-to-value ratio to determine maximum loan amount.

        Args:
            noi_by_use: Series with NOI by program use
            cap_rates: Series with cap rates by program use

        Returns:
            float: Maximum refinance amount based on property value and LTV
        """
        refinance_values_by_use = noi_by_use / cap_rates.loc[noi_by_use.index]
        total_refinance_value = refinance_values_by_use.sum()
        return total_refinance_value * self.ltv_ratio

    def generate_amortization(
        self, loan_amount: PositiveFloat, start_date: pd.Period
    ) -> pd.DataFrame:
        """
        Generate permanent loan amortization schedule.

        Creates amortization schedule using the loan amount and permanent loan terms.

        Args:
            loan_amount: Loan amount to be amortized
            start_date: Start date for amortization schedule

        Returns:
            DataFrame containing the amortization schedule
        """
        amortization = LoanAmortization(
            loan_amount=loan_amount,
            term=self.amortization,
            interest_rate=self.interest_rate,
            start_date=start_date,
        )
        schedule, _ = amortization.amortization_schedule
        return schedule
