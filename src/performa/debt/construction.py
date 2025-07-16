"""Construction loan facilities"""

from datetime import date
from typing import Dict, List, Literal, Optional

import numpy as np
import pandas as pd
from pydantic import Field, model_validator

from ..core.primitives import FloatBetween0And1, Model, PositiveFloat
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
        # NOTE: Advanced interest features not included in MVP
        commitment_fee_rate (Optional[FloatBetween0And1]): Commitment fee rate for advanced features
        exit_fee_rate (Optional[FloatBetween0And1]): Exit fee rate for advanced features

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
    
    # Advanced features for institutional parity
    # NOTE: Advanced interest features not included in MVP
    commitment_fee_rate: Optional[FloatBetween0And1] = Field(
        None, description="Annual fee on the undrawn loan commitment"
    )
    exit_fee_rate: Optional[FloatBetween0And1] = Field(
        None, description="Fee as a percentage of loan amount, paid at exit/refinancing"
    )

    # TODO: Add support for:
    # - Interest rate caps/floors
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
    Construction loan facility with multiple debt tranches.
    
    This class has been architecturally purified to act as a 'subcontractor'
    rather than an orchestrator. It responds to funding requests from the
    deal calculator by determining how much each tranche can provide based
    on LTC limits and current state.
    
    Key Features:
    - Multi-tranche construction financing
    - LTC-based draw controls
    - Interest capitalization and advanced payment options
    - Commitment fees and exit fees
    - Interest reserve funding capability with configurable reserve rate
    
    Attributes:
        kind: Discriminator field for union types
        name: Name of the construction facility
        tranches: List of debt tranches ordered by seniority
        fund_interest_from_reserve: Whether to fund interest from facility or require equity
        interest_reserve_rate: Interest reserve as percentage of total facility capacity (default 15%)
    """
    
    # Discriminator field for union types - REQUIRED
    kind: Literal["construction"] = "construction"
    
    # Facility identity
    name: str = Field(default="Construction Loan", description="Name of the construction facility")
    
    # Construction-specific attributes
    tranches: List[DebtTranche] = Field(
        ...,
        description="List of debt tranches ordered by seniority (senior first)",
        min_length=1
    )
    
    fund_interest_from_reserve: bool = Field(
        default=False,
        description="Whether to fund interest payments from debt facility or require equity"
    )
    
    interest_reserve_rate: FloatBetween0And1 = Field(
        default=0.15,
        description="Interest reserve as percentage of total facility capacity (default 15%)"
    )

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
        raise NotImplementedError("Use calculate_period_draws and get_outstanding_balance instead")

    @property
    def max_ltc(self) -> FloatBetween0And1:
        """Maximum total LTC across all tranches"""
        return max(tranche.ltc_threshold for tranche in self.tranches)

    def calculate_period_draws(
        self,
        funding_needed: float,
        total_project_cost: float,
        cumulative_costs_to_date: float,
        cumulative_draws_by_tranche: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Calculates the available draws from each tranche for a single period,
        given a specific funding requirement.
        
        This method is the focused "subcontractor" response to funding requests from
        the deal orchestrator. It determines how much each tranche can provide based
        on its LTC limits and current state.

        Args:
            funding_needed: Amount of funding needed for this period
            total_project_cost: Total project cost
            cumulative_costs_to_date: Cumulative project costs to date
            cumulative_draws_by_tranche: Dict mapping tranche names to cumulative draws

        Returns:
            Dict mapping tranche names to available draw amounts for this period
        """
        period_draws = {tranche.name: 0.0 for tranche in self.tranches}
        remaining_funding_need = funding_needed
        previous_ltc = 0.0

        for tranche in self.tranches:
            if remaining_funding_need <= 0:
                break
            
            cumulative_tranche_draw = cumulative_draws_by_tranche.get(tranche.name, 0.0)
            
            # Calculate available draw for this tranche
            tranche_draw = tranche.calculate_draw_amount(
                total_cost=total_project_cost,
                cumulative_cost=cumulative_costs_to_date,
                cumulative_tranche=cumulative_tranche_draw,
                previous_ltc=previous_ltc,
                remaining_cost=remaining_funding_need
            )
            
            if tranche_draw > 0:
                period_draws[tranche.name] = tranche_draw
                remaining_funding_need -= tranche_draw
            
            previous_ltc = tranche.ltc_threshold
            
        return period_draws

    def get_outstanding_balance(
        self,
        as_of_date: date,
        financing_cash_flows: pd.DataFrame
    ) -> float:
        """
        Calculates the total outstanding balance (principal + accrued interest)
        as of a specific date.
        
        This method provides the critical link for refinancing by calculating
        the total payoff amount needed to clear the construction facility.

        Args:
            as_of_date: Date as of which to calculate the balance
            financing_cash_flows: DataFrame with historical financing flows

        Returns:
            float: Total outstanding balance including principal and accrued interest
        """
        # Ensure the DataFrame index is compatible
        as_of_period = pd.Period(as_of_date, freq='M')
        relevant_flows = financing_cash_flows.loc[:as_of_period]
        
        total_principal_drawn = 0.0
        total_interest_accrued = 0.0
        
        for tranche in self.tranches:
            # Sum up principal draws for this tranche
            if f"{tranche.name} Draw" in relevant_flows.columns:
                total_principal_drawn += relevant_flows[f"{tranche.name} Draw"].sum()
            
            # Sum up accrued interest for this tranche
            if f"{tranche.name} Interest" in relevant_flows.columns:
                total_interest_accrued += relevant_flows[f"{tranche.name} Interest"].sum()
            
        # Payoff amount is principal drawn plus any accrued interest not yet paid
        payoff_amount = total_principal_drawn + total_interest_accrued
        return payoff_amount

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

    def calculate_debt_service(self, timeline) -> pd.Series:
        """
        Calculate debt service time series for construction facility.
        
        During construction, debt service is typically interest-only, 
        with principal due at maturity/refinancing. For construction loans,
        interest and principal payments are handled by the deal orchestrator
        rather than this facility method.
        
        Args:
            timeline: Timeline object with period_index
            
        Returns:
            pd.Series: Debt service by period (intentionally zero - handled by orchestrator)
            
        Note:
            This method intentionally returns zero because construction loan
            interest is calculated and compounded by the deal orchestrator
            in _calculate_funding_cascade_with_interest_compounding().
        """
        # Initialize debt service series
        debt_service = pd.Series(0.0, index=timeline.period_index)
        
        # For construction loans, interest and principal are handled by the 
        # deal orchestrator based on actual draws and interest accrual.
        # This architectural choice prevents double-counting of interest.
        return debt_service

    def calculate_loan_proceeds(self, timeline) -> pd.Series:
        """
        Calculate loan proceeds time series for construction facility.
        
        For construction loans, proceeds are driven by the construction schedule
        and draw requests, which are handled by the deal orchestrator through
        the calculate_period_draws() method.
        
        Args:
            timeline: Timeline object with period_index
            
        Returns:
            pd.Series: Loan proceeds by period (intentionally zero - handled by orchestrator)
            
        Note:
            This method intentionally returns zero because construction loan
            proceeds are calculated by the deal orchestrator based on actual
            funding needs and draw requests in _orchestrate_funding_and_financing().
        """
        # Initialize loan proceeds series
        loan_proceeds = pd.Series(0.0, index=timeline.period_index)
        
        # For construction loans, proceeds are driven by the construction 
        # schedule and draw requests, which are handled by the deal orchestrator
        # through calculate_period_draws(). This architectural choice ensures
        # proceeds match actual funding needs rather than predetermined schedules.
        return loan_proceeds
