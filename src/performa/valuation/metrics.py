# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Universal Property Metrics - Financial Performance Calculations

Provides standardized financial metrics calculations that work across
all property types and investment scenarios.
"""

from __future__ import annotations

from typing import Dict, Optional, Union

import pandas as pd
from pyxirr import xirr

from ..core.primitives.validation import validate_monthly_period_index


class PropertyMetrics:
    """
    Universal property financial metrics calculator.

    Provides standardized calculations for key real estate metrics
    that work across all asset types and scenarios.
    """

    @staticmethod
    def calculate_noi(
        revenues: Union[pd.Series, float],
        operating_expenses: Union[pd.Series, float],
        timeline: Optional[pd.PeriodIndex] = None,
    ) -> Union[pd.Series, float]:
        """
        Calculate Net Operating Income (NOI).

        Args:
            revenues: Revenue series or annual amount
            operating_expenses: Operating expense series or annual amount
            timeline: Period index for series calculations

        Returns:
            NOI series or annual NOI
        """
        # Validate Series inputs have monthly PeriodIndex
        if isinstance(revenues, pd.Series):
            validate_monthly_period_index(revenues, field_name="revenues")
        if isinstance(operating_expenses, pd.Series):
            validate_monthly_period_index(
                operating_expenses, field_name="operating_expenses"
            )

        if isinstance(revenues, pd.Series) and isinstance(
            operating_expenses, pd.Series
        ):
            return revenues - operating_expenses
        elif isinstance(revenues, (int, float)) and isinstance(
            operating_expenses, (int, float)
        ):
            return revenues - operating_expenses
        else:
            raise ValueError(
                "Revenues and operating_expenses must be the same type (both Series or both numbers)"
            )

    @staticmethod
    def calculate_stabilized_noi(
        cash_flows: pd.DataFrame, stabilization_period: Optional[pd.Period] = None
    ) -> float:
        """
        Calculate stabilized NOI from cash flow analysis.

        Args:
            cash_flows: DataFrame with revenue and expense components
            stabilization_period: Period to use for stabilization (default: last period)

        Returns:
            Annualized stabilized NOI
        """
        # Validate DataFrame has monthly PeriodIndex
        if not isinstance(cash_flows.index, pd.PeriodIndex):
            raise ValueError("cash_flows DataFrame must have a PeriodIndex")
        if cash_flows.index.freq != "M":
            raise ValueError("cash_flows DataFrame must have monthly frequency ('M')")

        # Default to last period if not specified
        if stabilization_period is None:
            stabilization_period = cash_flows.index[-1]

        # Calculate NOI for the stabilization period
        revenues = cash_flows.get("revenue", pd.Series(0, index=cash_flows.index))
        expenses = cash_flows.get("expenses", pd.Series(0, index=cash_flows.index))

        if stabilization_period in cash_flows.index:
            monthly_noi = (
                revenues[stabilization_period] - expenses[stabilization_period]
            )
            return monthly_noi * 12  # Annualize
        else:
            raise ValueError(
                f"Stabilization period {stabilization_period} not found in cash flows"
            )

    @staticmethod
    def calculate_irr(
        cash_flows: pd.Series, dates: Optional[pd.Series] = None
    ) -> float:
        """
        Calculate Internal Rate of Return using PyXIRR.

        Args:
            cash_flows: Series of cash flows (negative for investments)
            dates: Series of dates corresponding to cash flows

        Returns:
            IRR as decimal (e.g., 0.15 for 15%)
        """
        # Validate cash_flows Series if it has a PeriodIndex
        if isinstance(cash_flows.index, pd.PeriodIndex):
            validate_monthly_period_index(cash_flows, field_name="cash_flows")

        if dates is None:
            # Use cash flow index as dates
            dates = pd.to_datetime(cash_flows.index.to_timestamp())

        return xirr(dates, cash_flows)

    @staticmethod
    def calculate_yield_on_cost(stabilized_noi: float, total_cost: float) -> float:
        """
        Calculate yield on cost (development yield).

        Args:
            stabilized_noi: Stabilized annual NOI
            total_cost: Total development/acquisition cost

        Returns:
            Yield on cost as decimal
        """
        if total_cost <= 0:
            return 0.0
        return stabilized_noi / total_cost

    @staticmethod
    def calculate_cash_on_cash_return(
        first_year_cash_flow: float, initial_equity: float
    ) -> float:
        """
        Calculate cash-on-cash return.

        Args:
            first_year_cash_flow: Cash flow after debt service in first year
            initial_equity: Initial equity investment

        Returns:
            Cash-on-cash return as decimal
        """
        if initial_equity <= 0:
            return 0.0
        return first_year_cash_flow / initial_equity

    @staticmethod
    def calculate_comprehensive_metrics(
        cash_flows: pd.DataFrame,
        initial_investment: float,
        disposition_value: Optional[float] = None,
        disposition_date: Optional[pd.Period] = None,
    ) -> Dict[str, float]:
        """
        Calculate comprehensive property metrics from cash flow analysis.

        Args:
            cash_flows: DataFrame with revenue, expense, and net cash flow components
            initial_investment: Initial investment amount (positive)
            disposition_value: Net disposition proceeds (optional)
            disposition_date: Date of disposition (optional)

        Returns:
            Dictionary of calculated metrics
        """
        metrics = {}

        # Extract cash flow components
        revenue = cash_flows.get("revenue", pd.Series(0, index=cash_flows.index))
        expenses = cash_flows.get("expenses", pd.Series(0, index=cash_flows.index))
        net_cf = cash_flows.get("net_cash_flow", revenue - expenses)

        # Calculate stabilized NOI (using last period)
        stabilized_noi = PropertyMetrics.calculate_stabilized_noi(cash_flows)
        metrics["stabilized_noi"] = stabilized_noi

        # Calculate yield on cost
        metrics["yield_on_cost"] = PropertyMetrics.calculate_yield_on_cost(
            stabilized_noi, initial_investment
        )

        # Calculate first year metrics
        if len(net_cf) > 0:
            first_year_cf = (
                net_cf.iloc[:12].sum() if len(net_cf) >= 12 else net_cf.sum()
            )
            metrics["first_year_cash_flow"] = first_year_cf
            metrics["cash_on_cash_return"] = (
                PropertyMetrics.calculate_cash_on_cash_return(
                    first_year_cf, initial_investment
                )
            )

        # Calculate IRR if disposition is provided
        if disposition_value is not None and disposition_date is not None:
            # Create IRR cash flow series
            irr_cash_flows = net_cf.copy()

            # Add initial investment as negative cash flow
            initial_date = cash_flows.index[0]
            irr_series = pd.Series([-initial_investment], index=[initial_date])
            irr_series = pd.concat([irr_series, irr_cash_flows])

            # Add disposition as final positive cash flow
            if disposition_date in irr_series.index:
                irr_series[disposition_date] += disposition_value
            else:
                irr_series[disposition_date] = disposition_value

            try:
                metrics["irr"] = PropertyMetrics.calculate_irr(irr_series)
            except Exception:
                metrics["irr"] = None  # IRR calculation failed

        # Calculate profit metrics if disposition provided
        if disposition_value is not None:
            total_cash_flows = net_cf.sum()
            total_return = total_cash_flows + disposition_value - initial_investment
            metrics["total_return"] = total_return
            metrics["total_return_multiple"] = (
                total_return + initial_investment
            ) / initial_investment

        return metrics
