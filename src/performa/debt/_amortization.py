"""Loan amortization calculations"""

from typing import Tuple

import numpy as np
import pandas as pd
from pydantic import Field
from pyxirr import pmt

from ..utils._model import Model
from ..utils._types import PositiveFloat, PositiveInt
from ._rates import InterestRate


class LoanAmortization(Model):
    """
    Class representing loan amortization schedule and calculations.

    Handles the generation of detailed loan amortization schedules including payment,
    interest, and principal calculations over time.

    Attributes:
        loan_amount (PositiveFloat): Initial loan amount
        term (PositiveInt): Loan term in years
        interest_rate (InterestRate): Interest rate configuration
        start_date (pd.Period): Start date of amortization, defaults to current month

    Example:
        >>> amortization = LoanAmortization(
        ...     loan_amount=1000000.0,
        ...     term=30,
        ...     interest_rate=InterestRate(
        ...         rate_type="fixed",
        ...         base_rate=0.05
        ...     ),
        ...     start_date=pd.Period("2024-01", freq="M")
        ... )
        >>> schedule, summary = amortization.amortization_schedule
    """

    loan_amount: PositiveFloat
    term: PositiveInt  # in years
    interest_rate: InterestRate
    start_date: pd.Period = Field(default_factory=lambda: pd.Period.now(freq="M"))

    # TODO: Add support for:
    # - Interest-only periods
    # - Balloon payments
    # - Custom payment schedules
    # - Different payment frequencies (annual, quarterly, etc.)
    # - Different day count conventions

    @property
    def amortization_schedule(self) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Generate detailed loan amortization schedule.

        Calculates monthly payments, interest, principal, and balances over the loan term.
        Uses constant monthly payments based on the effective interest rate.

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
            - Series with summary statistics:
                - Payoff Date: Final payment date
                - Total Payments: Sum of all payments
                - Total Principal Paid: Sum of principal
                - Total Interest Paid: Sum of interest
                - Last Payment Amount: Final payment
        """
        monthly_rate = self.interest_rate.effective_rate / 12
        total_payments = self.term * 12
        payment = pmt(monthly_rate, total_payments, self.loan_amount) * -1

        # Time array for the payment schedule
        months = pd.period_range(self.start_date, periods=total_payments, freq="M")

        # Payments are constant
        payments = np.full(shape=(total_payments,), fill_value=payment)

        # Calculate interest for each period
        interest_paid = np.empty(shape=(total_payments,))
        balances = np.empty(shape=(total_payments,))

        balances[0] = self.loan_amount
        for i in range(total_payments):
            interest_paid[i] = balances[i] * monthly_rate
            principal_paid = payments[i] - interest_paid[i]
            if i < total_payments - 1:
                balances[i + 1] = balances[i] - principal_paid

        # Final balance is zero
        balances[-1] = 0

        # Create DataFrame
        df = pd.DataFrame(
            {
                "Period": np.arange(1, total_payments + 1),
                "Month": months,
                "Begin Balance": np.roll(balances, 1),
                "Payment": payments,
                "Interest": interest_paid,
                "Principal": payments - interest_paid,
                "End Balance": balances,
            }
        )
        df.iloc[0, df.columns.get_loc("Begin Balance")] = self.loan_amount
        df.set_index("Month", inplace=True)

        # Summary statistics
        summary = pd.Series(
            {
                "Payoff Date": df.index[-1],
                "Total Payments": df["Payment"].sum(),
                "Total Principal Paid": df["Principal"].sum(),
                "Total Interest Paid": df["Interest"].sum(),
                "Last Payment Amount": df["Payment"].iloc[-1],
            }
        )

        return df, summary
