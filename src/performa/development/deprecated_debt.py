from enum import Enum
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
from pydantic import Field, model_validator
from pyxirr import pmt

from ..core._types import FloatBetween0And1, PositiveFloat, PositiveInt
from ._model import Model

########################
######### DEBT #########
########################

class InterestRateType(str, Enum):
    """Type of interest rate"""
    FIXED = "fixed"
    FLOATING = "floating"
    # TODO: implement floating rate logic:
    # - Add rate index lookup/time series (e.g., SOFR curve)
    # - Add rate caps/floors
    # - Add rate reset frequency (e.g., monthly, quarterly)
    # - Support forward curves and rate scenarios


class InterestRate(Model):
    """Base class for interest rates"""
    rate_type: InterestRateType
    base_rate: FloatBetween0And1
    spread: Optional[FloatBetween0And1] = Field(
        None, 
        description="Spread over base rate for floating rates"
    )
    # TODO: Add fields for floating rate configuration:
    # - rate_index (e.g., SOFR, LIBOR)
    # - reset_frequency
    # - rate_cap
    # - rate_floor
    # TODO: Add fields for interest calculation conventions:
    # - day_count_convention (e.g., 30/360, Actual/365)
    # - payment_frequency
    # - accrual_method
    
    @model_validator(mode='after')
    def validate_spread_for_floating(self) -> 'InterestRate':
        """Ensure spread is provided for floating rates"""
        if self.rate_type == InterestRateType.FLOATING and self.spread is None:
            raise ValueError("Spread must be provided for floating rate loans")
        return self
    
    @property
    def effective_rate(self) -> FloatBetween0And1:
        """Calculate effective interest rate"""
        if self.rate_type == InterestRateType.FIXED:
            return self.base_rate
        return self.base_rate + (self.spread or 0.0)


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
                
        Example:
            >>> schedule, summary = amortization.amortization_schedule
            >>> schedule.head()
                        Period  Begin Balance    Payment   Interest  Principal  End Balance
            2024-01    1       1000000.00     5368.22    4166.67   1201.55    998798.45
            2024-02    2       998798.45      5368.22    4161.66   1206.56    997591.89
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

    # TODO: Add support for:
    # - Interest-only periods
    # - Balloon payments
    # - Custom payment schedules
    # - Different payment frequencies (annual, quarterly, etc.)
    # - Different day count conventions


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
        ..., 
        description="Maximum LTC for this tranche"
    )
    # TODO: Add support for:
    # - Commitment fee rate for undrawn amounts
    # - Interest rate caps/floors
    # - PIK interest toggle
    # - DSCR covenant threshold
    # - Prepayment penalties/yield maintenance
    # - Extension options
    
    def __lt__(self, other: 'DebtTranche') -> bool:
        """Compare tranches by LTC threshold for sorting"""
        return self.ltc_threshold < other.ltc_threshold

    def calculate_draw_amount(
        self, 
        total_cost: PositiveFloat,
        cumulative_cost: PositiveFloat,
        cumulative_tranche: PositiveFloat,
        previous_ltc: FloatBetween0And1,
        remaining_cost: PositiveFloat
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
            
        Example:
            >>> tranche = DebtTranche(
            ...     name="Senior",
            ...     interest_rate=InterestRate(rate_type="fixed", base_rate=0.05),
            ...     fee_rate=0.01,
            ...     ltc_threshold=0.65
            ... )
            >>> draw = tranche.calculate_draw_amount(
            ...     total_cost=1000000,
            ...     cumulative_cost=500000,
            ...     cumulative_tranche=200000,
            ...     previous_ltc=0.0,
            ...     remaining_cost=100000
            ... )
        """
        tranche_ltc = self.ltc_threshold - previous_ltc
        max_tranche_amount = total_cost * tranche_ltc
        
        # Calculate available capacity
        available = min(
            max_tranche_amount - cumulative_tranche,  # Remaining in tranche
            (cumulative_cost * tranche_ltc) - cumulative_tranche  # LTC limit
        )
        
        # Return draw amount
        return min(remaining_cost, available)

    def calculate_period_interest(
        self,
        drawn_balance: PositiveFloat,
        period_start: pd.Period
    ) -> float:
        """
        Calculate interest for a period based on drawn balance.
        
        Args:
            drawn_balance: Outstanding balance for the period
            period_start: Start of interest period (for floating rates)
            
        Returns:
            float: Interest amount for the period
            
        Example:
            >>> tranche = DebtTranche(...)
            >>> interest = tranche.calculate_period_interest(
            ...     drawn_balance=1000000,
            ...     period_start=pd.Period("2024-01", freq="M")
            ... )
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
            
        Example:
            >>> tranche = DebtTranche(...)
            >>> fee = tranche.calculate_upfront_fee(1000000)
        """
        return amount * self.fee_rate


class ConstructionFinancing(Model):
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
        
    Example:
        >>> construction_financing = ConstructionFinancing(
        ...     tranches=[
        ...         DebtTranche(name="Senior", ltc_threshold=0.45, ...),
        ...         DebtTranche(name="Mezzanine", ltc_threshold=0.60, ...)
        ...     ]
        ... )
    """
    tranches: List[DebtTranche] = Field(
        ...,
        description="List of debt tranches, ordered by seniority (LTC threshold)"
    )
    # TODO: Add support for:
    # - Draw order logic (sequential vs simultaneous) per intercreditor agreement
    # - Interest reserve calculations and tracking
    # - Construction loan extension options
    # - Draw request documentation and tracking
    # - Construction budget reallocation rules
    # - Retainage calculations
    # - Lien waivers tracking
    
    @model_validator(mode='after')
    def sort_and_validate_tranches(self) -> 'ConstructionFinancing':
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
    
    def calculate_interest(
        self, 
        drawn_amounts: dict[str, float],
        period_start: pd.Period,  # Keep for future floating rate implementation
    ) -> pd.Series:
        """
        Calculate interest for each tranche based on drawn amounts
        
        Args:
            drawn_amounts: Dictionary mapping tranche names to drawn amounts
            period_start: Start of interest period (used for floating rates)
            
        Returns:
            pd.Series with tranche names as index and interest amounts as values
        """
        # Use simple monthly interest (annual rate / 12) for consistency
        rates = pd.Series({
            tranche.name: tranche.interest_rate.effective_rate / 12
            for tranche in self.tranches
        })
        amounts = pd.Series(drawn_amounts)
        
        return amounts * rates
    
    def calculate_fees(self, tranche_amounts: pd.Series) -> pd.Series:
        """
        Calculate upfront fees for each tranche
        
        Args:
            tranche_amounts: Series with tranche names as index and amounts as values
            
        Returns:
            pd.Series with tranche names as index and fee amounts as values
        """
        fee_rates = pd.Series({
            tranche.name: tranche.fee_rate 
            for tranche in self.tranches
        })
        return tranche_amounts * fee_rates[tranche_amounts.index]

    def calculate_financing_cash_flows(
        self,
        total_project_cost: PositiveFloat,
        budget_cash_flows: pd.DataFrame,
        debt_to_equity: FloatBetween0And1,
        project_timeline: pd.PeriodIndex
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
            
        Example:
            >>> financing = ConstructionFinancing(tranches=[...])
            >>> cf = financing.calculate_financing_cash_flows(
            ...     total_project_cost=20000000,
            ...     budget_cash_flows=budget_df,
            ...     debt_to_equity=0.65,
            ...     project_timeline=timeline
            ... )
        """
        equity_portion = total_project_cost * (1 - debt_to_equity)

        # Initialize DataFrame
        df = pd.DataFrame(index=project_timeline)
        df["Total Costs Before Financing"] = (
            budget_cash_flows.sum(axis=1)
            .reindex(project_timeline)
            .fillna(0)
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
                equity_draw = min(
                    remaining_cost,
                    equity_portion - cumulative_equity
                )
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
                    remaining_cost
                )
                
                if tranche_draw > 0:
                    df.loc[period, f"{tranche.name} Draw"] = tranche_draw
                    remaining_cost -= tranche_draw
                
                # Calculate interest on cumulative balance
                if period > df.index[0]:
                    previous_balance = df.loc[:period-1, f"{tranche.name} Draw"].sum()
                    if previous_balance > 0:
                        interest_dict = self.calculate_interest(
                            {tranche.name: previous_balance},
                            period_start=period,
                        )
                        df.loc[period, f"{tranche.name} Interest"] = interest_dict[tranche.name]
                
                previous_ltc = tranche.ltc_threshold
            
            # Any remaining cost goes back to equity
            if remaining_cost > 0:
                df.loc[period, "Equity Draw"] += remaining_cost
        
        # Aggregate interest across tranches
        df["Interest Reserve"] = df[[f"{t.name} Interest" for t in self.tranches]].sum(axis=1)

        # Calculate fees when crossing from equity to debt
        df["Financing Fees"] = np.where(
            (df["Cumulative Costs"].shift(1, fill_value=0) < equity_portion) &
            (df["Cumulative Costs"] >= equity_portion),
            pd.Series(self.calculate_fees(
                self.calculate_tranche_amounts(total_project_cost * debt_to_equity)
            )).sum(),
            0
        )

        return df


class PermanentFinancing(Model):
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
        
    Example:
        >>> permanent_financing = PermanentFinancing(
        ...     interest_rate=InterestRate(
        ...         rate_type="fixed",
        ...         base_rate=0.05
        ...     ),
        ...     fee_rate=0.01,
        ...     ltv_ratio=0.65,
        ...     amortization=30
        ... )
    """
    interest_rate: InterestRate = Field(
        ...,
        description="Interest rate configuration"
    )
    fee_rate: FloatBetween0And1 = Field(
        ...,
        description="Upfront fee rate as percentage of loan amount"
    )
    ltv_ratio: FloatBetween0And1 = Field(
        default=0.75,
        description="Loan-to-value ratio"
    )
    amortization: PositiveInt = Field(
        default=30,
        description="Amortization term in years"
    )
    
    @model_validator(mode='after')
    def validate_financing_terms(self) -> 'PermanentFinancing':
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

    def calculate_refinance_amount(
        self, 
        noi_by_use: pd.Series,
        cap_rates: pd.Series
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
            
        Example:
            >>> financing = PermanentFinancing(...)
            >>> amount = financing.calculate_refinance_amount(
            ...     noi_by_use=pd.Series({"Office": 1000000, "Retail": 500000}),
            ...     cap_rates=pd.Series({"Office": 0.05, "Retail": 0.06})
            ... )
        """
        refinance_values_by_use = noi_by_use / cap_rates.loc[noi_by_use.index]
        total_refinance_value = refinance_values_by_use.sum()
        return total_refinance_value * self.ltv_ratio

    def generate_amortization(
        self,
        loan_amount: PositiveFloat,
        start_date: pd.Period
    ) -> pd.DataFrame:
        """
        Generate permanent loan amortization schedule.
        
        Creates amortization schedule using the loan amount and permanent loan terms.
        
        Args:
            loan_amount: Loan amount to be amortized
            start_date: Start date for amortization schedule
            
        Returns:
            DataFrame containing the amortization schedule
            
        Example:
            >>> financing = PermanentFinancing(...)
            >>> schedule = financing.generate_amortization(
            ...     loan_amount=35000000,
            ...     start_date=pd.Period("2024-01", freq="M")
            ... )
        """
        amortization = LoanAmortization(
            loan_amount=loan_amount,
            term=self.amortization,
            interest_rate=self.interest_rate,
            start_date=start_date
        )
        schedule, _ = amortization.amortization_schedule
        return schedule

    # TODO: Add support for:
    # - Lockout periods
    # - Defeasance calculations
    # - Yield maintenance calculations
    # - Extension options
    # - Future funding components
    # - Multiple notes/components (A/B/C notes)
    # - Ongoing debt service reserve requirements
    # - Financial covenants (DSCR, Debt Yield, etc.)
