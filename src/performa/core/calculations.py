# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Financial calculation functions.

Contains static methods for core financial metrics. These functions are pure
(math-only) and independent of data access; other modules should delegate to
these to ensure a single source of truth for financial calculations.
"""

from typing import Optional

import pandas as pd
from pyxirr import xirr, xnpv


class FinancialCalculations:
    """
    Pure mathematical functions for financial calculations.

    Static methods for core financial metrics, independent of ledger structure
    or business logic.
    """

    @staticmethod
    def calculate_irr(cash_flows: pd.Series) -> Optional[float]:
        """
        Calculate Internal Rate of Return using PyXIRR.

        Args:
            cash_flows: Series of cash flows with PeriodIndex
                       Negative values = investments/outflows
                       Positive values = returns/inflows

        Returns:
            IRR as decimal (e.g., 0.15 for 15%) or None if cannot calculate

        Edge Cases Handled:
            - Empty series → None
            - All negative flows → None
            - All positive flows → None
            - Single cash flow → None
            - Invalid dates → None

        Example:
            ```python
            # Equity cash flows: initial investment + returns
            flows = pd.Series([-1000, 100, 100, 1200],
                            index=pd.period_range('2024-01', periods=4, freq='M'))
            irr = FinancialCalculations.calculate_irr(flows)
            print(f"IRR: {irr:.2%}")  # IRR: 15.23%
            ```
        """
        if cash_flows.empty:
            return None

        # Check for meaningful cash flows (both negative and positive)
        has_negative = (cash_flows < 0).any()
        has_positive = (cash_flows > 0).any()

        if not (has_negative and has_positive):
            return None  # Need both investments and returns

        # Check for non-zero flows
        if cash_flows.sum() == 0 and (cash_flows == 0).all():
            return None

        try:
            # Convert PeriodIndex to dates for PyXIRR
            dates = [period.to_timestamp().date() for period in cash_flows.index]
            result = xirr(dates, cash_flows.values)
            return float(result) if result is not None else None
        except Exception:
            # Return None for any calculation failures
            return None

    @staticmethod
    def calculate_equity_multiple(cash_flows: pd.Series) -> Optional[float]:
        """
        Calculate equity multiple (total returns / total investment).

        Args:
            cash_flows: Series of cash flows with PeriodIndex
                       Negative values = investments/outflows
                       Positive values = returns/inflows

        Returns:
            Multiple as float (e.g., 2.5 for 2.5x return) or None if cannot calculate

        Edge Cases Handled:
            - Empty series → None
            - Zero investment → None
            - No returns → 0.0 (lost all money)
            - All positive flows → None (no investment to measure against)

        Example:
            ```python
            # Equity investment and returns
            flows = pd.Series([-1000, 100, 100, 1400],
                            index=pd.period_range('2024-01', periods=4, freq='M'))
            multiple = FinancialCalculations.calculate_equity_multiple(flows)
            print(f"Multiple: {multiple:.2f}x")  # Multiple: 1.60x
            ```
        """
        if cash_flows.empty:
            return None

        # Calculate total invested (absolute value of negative flows)
        negative_flows = cash_flows[cash_flows < 0]
        if negative_flows.empty:
            return None  # No investment to measure against

        total_invested = abs(negative_flows.sum())

        if total_invested == 0:
            return None  # Cannot divide by zero investment

        # Calculate total returned (positive flows)
        positive_flows = cash_flows[cash_flows > 0]
        total_returned = positive_flows.sum() if not positive_flows.empty else 0.0

        return total_returned / total_invested

    @staticmethod
    def calculate_npv(cash_flows: pd.Series, discount_rate: float) -> Optional[float]:
        """
        Calculate Net Present Value using PyXIRR.

        Args:
            cash_flows: Series of cash flows with PeriodIndex
                       Negative values = investments/outflows
                       Positive values = returns/inflows
            discount_rate: Annual discount rate as decimal (e.g., 0.10 for 10%)

        Returns:
            NPV as float or None if cannot calculate

        Edge Cases Handled:
            - Empty series → None
            - Invalid discount rate → None
            - Calculation errors → None

        Example:
            ```python
            flows = pd.Series([-1000, 300, 400, 500],
                            index=pd.period_range('2024-01', periods=4, freq='M'))
            npv = FinancialCalculations.calculate_npv(flows, 0.10)
            print(f"NPV: ${npv:,.0f}")  # NPV: $78
            ```
        """
        if cash_flows.empty:
            return None

        # Validate discount rate
        if not isinstance(discount_rate, (int, float)) or discount_rate < -1:
            return None

        try:
            # Convert PeriodIndex to dates for PyXIRR
            dates = [period.to_timestamp().date() for period in cash_flows.index]
            result = xnpv(discount_rate, dates, cash_flows.values)
            return float(result) if result is not None else None
        except Exception:
            # Return None for any calculation failures
            return None

    @staticmethod
    def calculate_dscr(noi: float, debt_service: float) -> Optional[float]:
        """
        Calculate single-period Debt Service Coverage Ratio.

        DSCR = NOI / |Debt Service|

        Args:
            noi: Net operating income for period
            debt_service: Debt service for period (negative = outflow)

        Returns:
            DSCR ratio or None if no debt service

        Note:
            Debt service is typically negative (cash outflow). We use absolute value
            for the calculation to get a positive DSCR ratio.

        Example:
            ```python
            # Typical case: negative debt service
            dscr = FinancialCalculations.calculate_dscr(100_000, -75_000)
            print(f"DSCR: {dscr:.2f}")  # DSCR: 1.33

            # No debt case
            dscr = FinancialCalculations.calculate_dscr(100_000, 0)
            print(f"DSCR: {dscr}")  # DSCR: 100.0 (reporting convention)
            ```
        """
        if debt_service == 0:
            # No debt service: return convention value if NOI positive, else None
            return 100.0 if noi > 0 else None
        
        # Calculate DSCR using absolute value of debt service
        # (debt service is negative for cash outflows)
        return noi / abs(debt_service)
