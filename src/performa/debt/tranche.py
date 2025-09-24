# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Debt Tranche - Individual tranche for multi-layered construction financing.

This module provides the DebtTranche class for modeling complex capital structures
with multiple financing layers (senior, mezzanine, preferred equity) each with
their own LTC thresholds, interest rates, and fee structures.
"""

from typing import Union

import pandas as pd
from pydantic import Field

from ..core.primitives import Model, Timeline
from .rates import InterestRate


class DebtTranche(Model):
    """
    Individual debt tranche for multi-layered construction financing.

    Each tranche has its own LTC threshold, rate, and fees, enabling
    complex capital structures like senior/mezzanine/preferred equity.

    Required by tests in:
    - test_debt_features.py
    - test_debt_integration_comprehensive.py
    - test_asset_factory_validation.py

    Attributes:
        name: Tranche identifier (e.g., "Senior Construction", "Mezzanine")
        ltc_threshold: Loan-to-cost threshold as decimal (0.0 to 1.0)
        interest_rate: Interest rate structure (float or InterestRate object)
        fee_rate: Origination fee rate as decimal (0.0 to 0.1)

    Example:
        # Senior construction tranche
        senior_tranche = DebtTranche(
            name="Senior Construction",
            ltc_threshold=0.75,  # 75% LTC
            interest_rate=InterestRate(details=FixedRate(rate=0.065)),
            fee_rate=0.01  # 1% origination fee
        )

        # Mezzanine tranche
        mezz_tranche = DebtTranche(
            name="Mezzanine Debt",
            ltc_threshold=0.85,  # 85% LTC (higher threshold)
            interest_rate=0.12,  # 12% simple rate
            fee_rate=0.02  # 2% origination fee
        )
    """

    name: str = Field(..., description="Tranche identifier")
    ltc_threshold: float = Field(
        ..., ge=0, le=1.0, description="Loan-to-cost threshold (0.0 to 1.0)"
    )
    interest_rate: Union[float, InterestRate] = Field(
        ...,
        description="Interest rate structure (simple float or complex InterestRate)",
    )
    fee_rate: float = Field(
        0.0, ge=0, le=0.1, description="Origination fee rate (0.0 to 0.1)"
    )

    def calculate_available_proceeds(self, project_costs: pd.Series) -> pd.Series:
        """
        Calculate cumulative available proceeds up to LTC threshold.

        For each period, determines the maximum loan proceeds available based
        on cumulative project costs and this tranche's LTC threshold.

        Args:
            project_costs: Series of project costs by period (cumulative)

        Returns:
            pd.Series: Maximum available proceeds by period

        Example:
            # Project costs: $0, $2M, $5M, $8M over 4 periods
            # 75% LTC tranche
            costs = pd.Series([0, 2_000_000, 5_000_000, 8_000_000])
            proceeds = tranche.calculate_available_proceeds(costs)
            # Result: [0, $1.5M, $3.75M, $6M]
        """
        # Ensure cumulative costs (in case provided costs are not cumulative)
        cumulative_costs = project_costs.cummax()

        # Calculate maximum proceeds based on LTC threshold
        max_tranche_proceeds = cumulative_costs * self.ltc_threshold

        return max_tranche_proceeds

    def calculate_interest_on_draws(
        self, draws: pd.Series, timeline: Timeline
    ) -> pd.Series:
        """
        Calculate interest payments on outstanding drawn balance.

        For construction facilities, interest is typically paid monthly on the
        outstanding loan balance (sum of all draws to date).

        Args:
            draws: Series of draw amounts by period
            timeline: Timeline for interest calculations

        Returns:
            pd.Series: Interest payment amounts by period

        Example:
            # Draws: $1M, $1M, $1M over 3 months
            # 8% annual rate = 0.67% monthly
            draws = pd.Series([1_000_000, 1_000_000, 1_000_000])
            interest = tranche.calculate_interest_on_draws(draws, timeline)
            # Result: [$6,667, $13,333, $20,000] (interest on cumulative balance)
        """
        interest_payments = pd.Series(0.0, index=timeline.period_index)
        outstanding_balance = 0.0

        effective_rate = self._get_effective_rate()
        monthly_rate = effective_rate / 12

        for i, period in enumerate(timeline.period_index):
            # Add this period's draw to outstanding balance
            if i < len(draws):
                outstanding_balance += draws.iloc[i]

            # Calculate interest payment on outstanding balance
            interest_payment = outstanding_balance * monthly_rate
            interest_payments.iloc[i] = interest_payment

        return interest_payments

    def calculate_origination_fees(self, loan_amount: float) -> float:
        """
        Calculate total origination fees for this tranche.

        Args:
            loan_amount: Total loan amount for fee calculation

        Returns:
            float: Total origination fees
        """
        return loan_amount * self.fee_rate

    def _get_effective_rate(self) -> float:
        """
        Get effective annual interest rate handling both float and InterestRate.

        Returns:
            float: Annual interest rate as decimal
        """
        if isinstance(self.interest_rate, (int, float)):
            return float(self.interest_rate)
        else:
            # InterestRate object - use effective_rate property
            return self.interest_rate.effective_rate

    def __str__(self) -> str:
        """String representation for debugging and logging."""
        rate_str = f"{self._get_effective_rate():.2%}"
        return f"{self.name} ({self.ltc_threshold:.1%} LTC, {rate_str} rate)"

    def __repr__(self) -> str:
        """Detailed representation for debugging."""
        return (
            f"DebtTranche(name='{self.name}', "
            f"ltc_threshold={self.ltc_threshold}, "
            f"interest_rate={self.interest_rate!r}, "
            f"fee_rate={self.fee_rate})"
        )
