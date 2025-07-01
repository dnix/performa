"""Construction loan facilities"""

from typing import List, Literal

import numpy as np
import pandas as pd
from pydantic import Field, model_validator

from ..common.primitives import FloatBetween0And1, Model, PositiveFloat
from .debt_facility import DebtFacility
from .rates import InterestRate


class DebtTranche(Model):
    """
    Class representing a single debt tranche in a financing structure.

    Attributes:
        name (str): Tranche name (e.g. 'Senior', 'Mezzanine 1')
        interest_rate (InterestRate): Interest rate configuration
        fee_rate (FloatBetween0And1): Upfront fee as percentage of tranche amount
        ltc_threshold (FloatBetween0And1): Maximum LTC for this tranche, used for stacking

    Example:
        >>> senior = DebtTranche(
        ...     name="Senior",
        ...     interest_rate=InterestRate(
        ...         rate_type=InterestRateType.FLOATING,
        ...         base_rate=0.05,
        ...         spread=0.03
        ...     ),
        ...     fee_rate=0.01,
        ...     ltc_threshold=0.45
        ... )
    """

    name: str = Field(..., description="Tranche name (e.g. 'Senior', 'Mezzanine')")
    interest_rate: InterestRate
    fee_rate: FloatBetween0And1
    ltc_threshold: FloatBetween0And1 = Field(
        ..., description="Maximum LTC for this tranche"
    )
    # TODO: Add support for:
    # - Commitment fee rate for undrawn amounts
    # - Interest rate caps/floors
    # - PIK interest toggle
    # - DSCR covenant threshold
    # - Prepayment penalties/yield maintenance
    # - Extension options

    def __lt__(self, other: "DebtTranche") -> bool:
        """Compare tranches by LTC threshold for sorting"""
        return self.ltc_threshold < other.ltc_threshold

    def calculate_draw_amount(
        self,
        total_cost: PositiveFloat,
        cumulative_cost: PositiveFloat,
        cumulative_tranche: PositiveFloat,
        previous_ltc: FloatBetween0And1,
        remaining_cost: PositiveFloat,
    ) -> PositiveFloat:
        """
        Calculate available draw amount for this tranche.

        Determines the maximum amount that can be drawn from this tranche based on:
        - Total project cost and tranche's LTC threshold
        - Cumulative costs to date and LTC limits
        - Amount already drawn from this tranche
        - Remaining cost to be funded

        Args:
            total_cost: Total project cost
            cumulative_cost: Cumulative project costs to date
            cumulative_tranche: Amount already drawn from this tranche
            previous_ltc: Combined LTC thresholds of more senior tranches
            remaining_cost: Remaining cost to be funded in this period

        Returns:
            PositiveFloat: Amount available to draw from this tranche
        """
        tranche_ltc = self.ltc_threshold - previous_ltc
        max_tranche_amount = total_cost * tranche_ltc

        # Calculate available capacity
        available = min(
            max_tranche_amount - cumulative_tranche,  # Remaining in tranche
            (cumulative_cost * tranche_ltc) - cumulative_tranche,  # LTC limit
        )

        # Return draw amount
        return min(remaining_cost, available)

    def calculate_period_interest(
        self, drawn_balance: PositiveFloat, period_start: pd.Period
    ) -> float:
        """
        Calculate interest for a period based on drawn balance.

        Args:
            drawn_balance: Outstanding balance for the period
            period_start: Start of interest period (for floating rates)

        Returns:
            float: Interest amount for the period
        """
        # TODO: Implement floating rate logic:
        # - Add rate index lookup/time series (e.g., SOFR curve)
        # - Support forward curves and rate scenarios
        # - Add rate reset calculations
        # - Handle rate caps/floors
        return drawn_balance * (self.interest_rate.effective_rate / 12)

    def calculate_upfront_fee(self, amount: PositiveFloat) -> float:
        """
        Calculate upfront fee for a given amount.

        Args:
            amount: Amount to calculate fee on

        Returns:
            float: Fee amount
        """
        return amount * self.fee_rate


class ConstructionFacility(DebtFacility):
    """
    Class for construction financing with multiple debt tranches.

    Manages the stacking and interaction of multiple debt tranches during construction.
    Tranches are ordered by seniority based on their LTC thresholds.

    Attributes:
        tranches (List[DebtTranche]): List of debt tranches, ordered by seniority

    Properties:
        max_ltc (FloatBetween0And1): Maximum total LTC across all tranches

    Methods:
        calculate_tranche_amounts: Calculate maximum amounts for each tranche
        calculate_interest: Calculate period interest for drawn amounts
        calculate_fees: Calculate upfront fees for each tranche
    """

    kind: Literal["construction"] = "construction"
    tranches: List[DebtTranche] = Field(
        ..., description="List of debt tranches, ordered by seniority (LTC threshold)"
    )
    # TODO: Add support for:
    # - Draw order logic (sequential vs simultaneous) per intercreditor agreement
    # - Interest reserve calculations and tracking
    # - Construction loan extension options
    # - Draw request documentation and tracking
    # - Construction budget reallocation rules
    # - Retainage calculations
    # - Lien waivers tracking

    @model_validator(mode="after")
    def sort_and_validate_tranches(self) -> "ConstructionFacility":
        """
        Sort tranches by LTC threshold and validate stacking.

        Validates:
        - Tranches are properly stacked (increasing LTC thresholds)
        - No tranche exceeds 100% LTC
        - No gaps in the capital stack
        """
        # Sort tranches by LTC threshold
        self.tranches.sort()

        # Validate LTC thresholds are increasing and <= 1
        previous_ltc = 0.0
        for tranche in self.tranches:
            if tranche.ltc_threshold <= previous_ltc:
                raise ValueError(
                    f"Tranche {tranche.name} LTC threshold must be greater than "
                    f"previous tranche threshold of {previous_ltc}"
                )
            if tranche.ltc_threshold > 1.0:
                raise ValueError(
                    f"Tranche {tranche.name} LTC threshold cannot exceed 1.0"
                )
            previous_ltc = tranche.ltc_threshold

        return self

    def calculate_interest(self) -> float:
        """Calculate interest for a period"""
        raise NotImplementedError("Use calculate_financing_cash_flows instead")

    @property
    def max_ltc(self) -> FloatBetween0And1:
        """Maximum total LTC across all tranches"""
        return max(tranche.ltc_threshold for tranche in self.tranches)

    def calculate_tranche_amounts(self, total_cost: PositiveFloat) -> pd.Series:
        """
        Calculate the maximum amount available for each tranche based on total cost

        Args:
            total_cost: Total project cost

        Returns:
            pd.Series with tranche names as index and maximum amounts as values
        """
        amounts = {}
        previous_ltc = 0.0

        for tranche in self.tranches:
            tranche_ltc = tranche.ltc_threshold - previous_ltc
            amounts[tranche.name] = total_cost * tranche_ltc
            previous_ltc = tranche.ltc_threshold

        return pd.Series(amounts)

    def calculate_fees(self, tranche_amounts: pd.Series) -> pd.Series:
        """
        Calculate upfront fees for each tranche

        Args:
            tranche_amounts: Series with tranche names as index and amounts as values

        Returns:
            pd.Series with tranche names as index and fee amounts as values
        """
        fee_rates = pd.Series(
            {tranche.name: tranche.fee_rate for tranche in self.tranches}
        )
        return tranche_amounts * fee_rates[tranche_amounts.index]

    def calculate_financing_cash_flows(
        self,
        total_project_cost: PositiveFloat,
        budget_cash_flows: pd.DataFrame,
        debt_to_equity: FloatBetween0And1,
        project_timeline: pd.PeriodIndex,
    ) -> pd.DataFrame:
        """
        Calculate detailed construction financing cash flows.

        Manages the complex interaction between equity and debt tranches during construction:
        - Draws equity first until equity portion is reached
        - Then draws from debt tranches in order of seniority
        - Calculates interest on drawn balances
        - Applies financing fees when crossing from equity to debt

        Args:
            total_project_cost: Total project cost
            budget_cash_flows: DataFrame of budget costs over time
            debt_to_equity: Project's debt-to-equity ratio
            project_timeline: Project timeline PeriodIndex

        Returns:
            DataFrame with columns:
            - Total Costs Before Financing: Period construction costs
            - Cumulative Costs: Running total of costs
            - Equity Draw: Equity funding in period
            - {Tranche Name} Draw: Draw amount for each tranche
            - {Tranche Name} Interest: Interest for each tranche
            - Interest Reserve: Total interest across tranches
            - Financing Fees: Upfront fees when debt is first drawn
        """
        equity_portion = total_project_cost * (1 - debt_to_equity)

        # Initialize DataFrame
        df = pd.DataFrame(index=project_timeline)
        df["Total Costs Before Financing"] = (
            budget_cash_flows.sum(axis=1).reindex(project_timeline).fillna(0)
        )
        df["Cumulative Costs"] = df["Total Costs Before Financing"].cumsum()

        # Initialize draw and interest columns
        df["Equity Draw"] = 0.0
        for tranche in self.tranches:
            df[f"{tranche.name} Draw"] = 0.0
            df[f"{tranche.name} Interest"] = 0.0

        for period in df.index:
            current_cost = df.loc[period, "Total Costs Before Financing"]
            if current_cost == 0:
                continue

            cumulative_cost = df.loc[period, "Cumulative Costs"]
            cumulative_equity = df.loc[:period, "Equity Draw"].sum()

            # Calculate draws for this period
            remaining_cost = current_cost

            # 1. Draw equity until equity portion is reached
            if cumulative_equity < equity_portion:
                equity_draw = min(remaining_cost, equity_portion - cumulative_equity)
                df.loc[period, "Equity Draw"] = equity_draw
                remaining_cost -= equity_draw

            # 2. Draw debt tranches in order
            previous_ltc = 0.0
            for tranche in self.tranches:
                if remaining_cost <= 0:
                    break

                cumulative_tranche = df.loc[:period, f"{tranche.name} Draw"].sum()

                tranche_draw = tranche.calculate_draw_amount(
                    total_project_cost,
                    cumulative_cost,
                    cumulative_tranche,
                    previous_ltc,
                    remaining_cost,
                )

                if tranche_draw > 0:
                    df.loc[period, f"{tranche.name} Draw"] = tranche_draw
                    remaining_cost -= tranche_draw

                # Calculate interest on cumulative balance
                if period > df.index[0]:
                    previous_balance = df.loc[
                        : period - 1, f"{tranche.name} Draw"
                    ].sum()
                    if previous_balance > 0:
                        df.loc[period, f"{tranche.name} Interest"] = (
                            tranche.calculate_period_interest(previous_balance, period)
                        )

                previous_ltc = tranche.ltc_threshold

            # Any remaining cost goes back to equity
            if remaining_cost > 0:
                df.loc[period, "Equity Draw"] += remaining_cost

        # Aggregate interest across tranches
        df["Interest Reserve"] = df[[f"{t.name} Interest" for t in self.tranches]].sum(
            axis=1
        )

        # Calculate fees when crossing from equity to debt
        df["Financing Fees"] = np.where(
            (df["Cumulative Costs"].shift(1, fill_value=0) < equity_portion)
            & (df["Cumulative Costs"] >= equity_portion),
            pd.Series(
                self.calculate_fees(
                    self.calculate_tranche_amounts(total_project_cost * debt_to_equity)
                )
            ).sum(),
            0,
        )

        return df
