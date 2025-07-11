"""Loan amortization calculations"""

from typing import Optional, Tuple

import numpy as np
import pandas as pd
from pydantic import Field
from pyxirr import pmt

from ..core.primitives import Model, PositiveFloat, PositiveInt
from .rates import InterestRate


class LoanAmortization(Model):
    """
    Class representing loan amortization schedule and calculations.

    Handles the generation of detailed loan amortization schedules including payment,
    interest, and principal calculations over time. Supports institutional loan
    features including interest-only periods and dynamic rate calculations for
    floating rate loans.

    Attributes:
        loan_amount (PositiveFloat): Initial loan amount
        term (PositiveInt): Loan term in years
        interest_rate (InterestRate): Interest rate configuration
        start_date (pd.Period): Start date of amortization, defaults to current month
        interest_only_periods (PositiveInt): Number of initial months with interest-only payments
        index_curve (Optional[pd.Series]): Time series of index rates for floating rate calculations

    Examples:
        >>> # Standard fully amortizing loan
        >>> amortization = LoanAmortization(
        ...     loan_amount=1000000.0,
        ...     term=30,
        ...     interest_rate=InterestRate(details=FixedRate(rate=0.05)),
        ...     start_date=pd.Period("2024-01", freq="M")
        ... )
        
        >>> # Institutional loan with 3-year interest-only period
        >>> io_amortization = LoanAmortization(
        ...     loan_amount=1000000.0,
        ...     term=10,
        ...     interest_rate=InterestRate(details=FixedRate(rate=0.065)),
        ...     start_date=pd.Period("2024-01", freq="M"),
        ...     interest_only_periods=36  # 3 years I/O, then 7 years amortizing
        ... )
        
        >>> # Floating rate loan with SOFR index
        >>> sofr_curve = pd.Series([0.045, 0.048, 0.050], 
        ...                       index=pd.period_range("2024-01", periods=3, freq="M"))
        >>> floating_amortization = LoanAmortization(
        ...     loan_amount=1000000.0,
        ...     term=5,
        ...     interest_rate=InterestRate(details=FloatingRate(
        ...         rate_index=RateIndexEnum.SOFR_30_DAY_AVG,
        ...         spread=0.0275,
        ...         interest_rate_cap=0.08
        ...     )),
        ...     start_date=pd.Period("2024-01", freq="M"),
        ...     index_curve=sofr_curve
        ... )
        >>> schedule, summary = floating_amortization.amortization_schedule
    """

    loan_amount: PositiveFloat
    term: PositiveInt  # in years
    interest_rate: InterestRate
    start_date: pd.Period = Field(default_factory=lambda: pd.Period.now(freq="M"))
    interest_only_periods: PositiveInt = Field(
        default=0,
        description="Number of initial periods with interest-only payments (in months)"
    )
    index_curve: Optional[pd.Series] = Field(
        default=None,
        description="Time series of index rates for floating rate calculations (required for floating rates)"
    )

    # TODO: Add support for:
    # - Balloon payments
    # - Custom payment schedules
    # - Different payment frequencies (annual, quarterly, etc.)
    # - Different day count conventions

    @property
    def amortization_schedule(self) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Generate detailed loan amortization schedule with support for interest-only periods
        and dynamic rate calculations for floating rate loans.

        Calculates monthly payments, interest, principal, and balances over the loan term.
        For floating rate loans, interest rates are calculated dynamically for each period
        using the provided index curve.
        
        Handles two phases:
        1. Interest-only periods: Payment = Interest only (no principal reduction)
        2. Amortizing periods: Payment = Principal + Interest based on remaining term

        Returns:
            Tuple containing:
            - DataFrame with columns:
                - Period: Payment period number
                - Month: Payment date
                - Begin Balance: Starting balance
                - Payment: Total payment amount
                - Interest: Interest portion
                - Principal: Principal portion
                - End Balance: Ending balance
                - Rate: Effective interest rate for the period (annual)
            - Series with summary statistics:
                - Payoff Date: Final payment date
                - Total Payments: Sum of all payments
                - Total Principal Paid: Sum of principal
                - Total Interest Paid: Sum of interest
                - Last Payment Amount: Final payment
                - Average Rate: Average interest rate over the loan term
        """
        total_payments = self.term * 12
        
        # Time array for the payment schedule
        months = pd.period_range(self.start_date, periods=total_payments, freq="M")

        # Initialize arrays for calculations
        payments = np.zeros(total_payments)
        interest_paid = np.zeros(total_payments)
        principal_paid = np.zeros(total_payments)
        balances = np.zeros(total_payments + 1)  # Extra element for initial balance
        rates = np.zeros(total_payments)  # Track effective rates for each period
        
        # Set initial balance
        balances[0] = self.loan_amount
        
        # Calculate payment schedule period by period
        for i in range(total_payments):
            current_balance = balances[i]
            current_period = months[i]
            
            # Get dynamic rate for this period
            annual_rate = self.interest_rate.get_rate_for_period(current_period, self.index_curve)
            monthly_rate = annual_rate / 12
            rates[i] = annual_rate
            
            # Interest for this period
            interest_payment = current_balance * monthly_rate
            interest_paid[i] = interest_payment
            
            if i < self.interest_only_periods:
                # INTEREST-ONLY PHASE: Payment = Interest only
                payment = interest_payment
                principal_payment = 0.0
            else:
                # AMORTIZING PHASE: Calculate payment for remaining term
                remaining_periods = total_payments - i
                
                if remaining_periods > 0 and monthly_rate > 0:
                    # Calculate payment for remaining term using PMT formula
                    payment = pmt(monthly_rate, remaining_periods, current_balance) * -1
                    principal_payment = payment - interest_payment
                else:
                    # Final payment or zero rate case
                    payment = current_balance + interest_payment
                    principal_payment = current_balance
            
            # Store values
            payments[i] = payment
            principal_paid[i] = principal_payment
            
            # Update balance for next period
            balances[i + 1] = current_balance - principal_payment
        
        # Ensure final balance is zero (handle rounding)
        balances[-1] = 0.0

        # Create DataFrame
        df = pd.DataFrame(
            {
                "Period": np.arange(1, total_payments + 1),
                "Month": months,
                "Begin Balance": balances[:-1],  # Exclude the final balance
                "Payment": payments,
                "Interest": interest_paid,
                "Principal": principal_paid,
                "End Balance": balances[1:],  # Exclude the initial balance
                "Rate": rates,  # Annual rate for each period
            }
        )
        df.set_index("Month", inplace=True)

        # Summary statistics
        summary = pd.Series(
            {
                "Payoff Date": df.index[-1],
                "Total Payments": df["Payment"].sum(),
                "Total Principal Paid": df["Principal"].sum(),
                "Total Interest Paid": df["Interest"].sum(),
                "Last Payment Amount": df["Payment"].iloc[-1],
                "Interest Only Periods": self.interest_only_periods,
                "Amortizing Periods": total_payments - self.interest_only_periods,
                "Average Rate": rates.mean(),  # Average rate over loan term
            }
        )

        return df, summary
