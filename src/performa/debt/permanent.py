"""Permanent loan facilities"""

from typing import Literal, Optional

import pandas as pd
from pydantic import Field, model_validator

from ..core.primitives import FloatBetween0And1, PositiveFloat, PositiveInt
from .amortization import LoanAmortization
from .debt_facility import DebtFacility
from .rates import InterestRate


class PermanentFacility(DebtFacility):
    """
    Class for permanent financing with fixed or floating rate loan.

    Handles permanent loan calculations including refinancing amount determination,
    loan amortization, and payment schedules. Now supports institutional-grade
    sizing using the complete "Sizing Trifecta": LTV, DSCR, and Debt Yield constraints.
    
    Also supports continuous covenant monitoring for active risk management throughout
    the loan lifecycle.

    Attributes:
        kind: Discriminator field for union types
        name: Name of the permanent facility
        interest_rate: Interest rate configuration
        loan_term_years: Total loan term in years
        amortization_years: Amortization period in years (defaults to loan term)
        ltv_ratio: Maximum loan-to-value ratio (for sizing)
        dscr_hurdle: Minimum debt service coverage ratio (for sizing)
        debt_yield_hurdle: Minimum debt yield hurdle (for sizing, optional)
        loan_amount: Fixed loan amount (optional - overrides automatic sizing)
        refinance_timing: When to refinance (months from start)
        ongoing_ltv_max: Maximum LTV for ongoing covenant monitoring (optional)
        ongoing_dscr_min: Minimum DSCR for ongoing covenant monitoring (optional)
        ongoing_debt_yield_min: Minimum debt yield for ongoing covenant monitoring (optional)
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

    # Underwriting constraints - The "Sizing Trifecta"
    ltv_ratio: FloatBetween0And1 = Field(
        ...,
        description="Maximum loan-to-value ratio for sizing"
    )
    dscr_hurdle: PositiveFloat = Field(
        ...,
        description="Minimum debt service coverage ratio for sizing"
    )
    debt_yield_hurdle: Optional[PositiveFloat] = Field(
        default=None,
        description="Minimum debt yield hurdle for sizing (e.g., 0.08 for 8% debt yield)"
    )

    # Sizing method (auto vs manual)
    sizing_method: Literal['auto', 'manual'] = Field(
        default='auto',
        description="Sizing method: 'auto' for automatic sizing using trifecta, 'manual' for fixed amount"
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
    
    # Interest-only periods (institutional feature)
    interest_only_months: Optional[PositiveInt] = Field(
        default=None,
        description="Number of initial months with interest-only payments"
    )

    # Ongoing covenant monitoring hurdles (for continuous risk management)
    ongoing_ltv_max: Optional[FloatBetween0And1] = Field(
        default=None,
        description="Maximum LTV ratio that must be maintained during loan lifecycle (ongoing covenant)"
    )
    ongoing_dscr_min: Optional[PositiveFloat] = Field(
        default=None,
        description="Minimum DSCR that must be maintained during loan lifecycle (ongoing covenant)"
    )
    ongoing_debt_yield_min: Optional[PositiveFloat] = Field(
        default=None,
        description="Minimum debt yield that must be maintained during loan lifecycle (ongoing covenant)"
    )

    # TODO: Add support for:
    # - Lockout periods
    # - Defeasance calculations
    # - Yield maintenance calculations
    # - Extension options
    # - Future funding components
    # - Multiple notes/components (A/B/C notes)
    # - Ongoing debt service reserve requirements

    @model_validator(mode="after")
    def validate_financing_terms(self) -> "PermanentFacility":
        """
        Validate permanent financing terms.

        Validates:
        - LTV ratio is reasonable (<=0.80)
        - Amortization term is reasonable (<=40 years)
        - Loan term is reasonable (<=30 years)
        - DSCR hurdle is reasonable (>=1.00)
        """
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
        Calculate the loan amount using either manual override or automatic "Sizing Trifecta":
        LTV, DSCR, and Debt Yield constraints.

        For manual sizing, returns the specified loan_amount.
        For automatic sizing, models the actual underwriting process where lenders evaluate:
        1. LTV: Maximum loan based on property value and LTV ratio
        2. DSCR: Maximum loan based on projected Year 1 stabilized NOI and DSCR hurdle  
        3. Debt Yield: Maximum loan based on NOI and minimum debt yield hurdle

        The loan amount is the most restrictive (minimum) of these three constraints,
        ensuring the loan meets all underwriting standards.

        Args:
            property_value: The appraised or calculated value of the property for LTV purposes
            forward_stabilized_noi: The projected annual NOI for the first year of stabilized operations

        Returns:
            float: Loan amount based on sizing method (manual override or most restrictive constraint)
        """
        # Check for manual sizing override
        if self.sizing_method == 'manual':
            if self.loan_amount is None:
                raise ValueError("Manual sizing requires loan_amount to be specified")
            return self.loan_amount
        
        # Automatic sizing using Sizing Trifecta
        # 1. LTV Sizing Constraint
        max_loan_from_ltv = property_value * self.ltv_ratio

        # 2. DSCR Sizing Constraint
        max_supportable_debt_service = forward_stabilized_noi / self.dscr_hurdle

        # Calculate annual debt constant using efficient direct calculation
        # Annual debt constant = Annual debt service / Loan amount
        annual_debt_constant = self._calculate_annual_debt_constant()
        
        # Max loan = Max supportable debt service / debt constant
        max_loan_from_dscr = max_supportable_debt_service / annual_debt_constant
        
        # 3. Debt Yield Sizing Constraint
        # Debt Yield = NOI / Loan Amount, so Max Loan = NOI / Debt Yield Hurdle
        max_loan_from_debt_yield = float('inf')  # Default to no constraint
        if self.debt_yield_hurdle and self.debt_yield_hurdle > 0:
            max_loan_from_debt_yield = forward_stabilized_noi / self.debt_yield_hurdle
        
        # Return the most restrictive constraint (minimum of all three)
        return min(max_loan_from_ltv, max_loan_from_dscr, max_loan_from_debt_yield)

    def _calculate_annual_debt_constant(self) -> float:
        """
        Calculate the annual debt constant (annual debt service per dollar of loan).
        
        This is the ratio of annual debt service to loan amount, calculated using
        standard financial formulas without generating full amortization schedules.
        
        Returns:
            float: Annual debt constant (debt service per dollar of loan)
        """
        # Get effective annual interest rate
        annual_rate = self.interest_rate.effective_rate
        
        # Get amortization term (defaults to loan term if not specified)
        amortization_years = self.amortization_years or self.loan_term_years
        
        if annual_rate == 0:
            # Handle zero interest rate case
            return 1.0 / amortization_years
        
        # Calculate monthly payment factor using standard PMT formula
        monthly_rate = annual_rate / 12
        num_payments = amortization_years * 12
        
        # Monthly payment per dollar of loan = PMT(rate, nper, pv=-1, fv=0)
        # Using standard financial formula: PMT = PV * [r(1+r)^n] / [(1+r)^n - 1]
        monthly_payment_factor = (
            monthly_rate * (1 + monthly_rate) ** num_payments
        ) / ((1 + monthly_rate) ** num_payments - 1)
        
        # Annual debt constant = monthly payment factor * 12
        annual_debt_constant = monthly_payment_factor * 12
        
        # Handle balloon payment case (loan term < amortization term)
        if self.loan_term_years < amortization_years:
            # For balloon loans, we need to add the balloon payment component
            # This is a simplified calculation - in practice, balloon sizing is complex
            # For now, use the fully amortizing debt constant as a conservative approach
            # TODO: Implement actual balloon payment calculation
            pass
        
        return annual_debt_constant

    def generate_amortization(
        self, loan_amount: PositiveFloat, start_date: pd.Period, index_curve: Optional[pd.Series] = None
    ) -> pd.DataFrame:
        """
        Generate permanent loan amortization schedule.

        Creates amortization schedule using the loan amount and permanent loan terms.
        The schedule will reflect the term/amortization distinction for balloon payments.

        Args:
            loan_amount: Loan amount to be amortized
            start_date: Start date for amortization schedule
            index_curve: Optional index curve for floating rate calculations

        Returns:
            DataFrame containing the amortization schedule
        """
        amortization = LoanAmortization(
            loan_amount=loan_amount,
            term=self.amortization_years or self.loan_term_years,
            interest_rate=self.interest_rate,
            start_date=start_date,
            interest_only_periods=self.interest_only_months or 0,
            index_curve=index_curve,
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

    def calculate_covenant_monitoring(
        self,
        timeline,
        property_value_series: pd.Series,
        noi_series: pd.Series,
        loan_amount: Optional[float] = None,
        index_curve: Optional[pd.Series] = None
    ) -> pd.DataFrame:
        """
        Calculate continuous covenant monitoring metrics throughout the loan lifecycle.
        
        This method generates time series for LTV, DSCR, and Debt Yield ratios and
        compares them against ongoing covenant hurdles to identify potential breaches.
        
        This is the core of active risk management - transforming the loan from a
        simple calculation into a living contract with ongoing obligations.
        
        Args:
            timeline: Timeline object with period_index
            property_value_series: Time series of property values by period
            noi_series: Time series of Net Operating Income by period
            loan_amount: Loan amount for calculations (uses self.loan_amount if not provided)
            
        Returns:
            DataFrame with covenant monitoring results containing:
            - LTV: Loan-to-Value ratio for each period
            - DSCR: Debt Service Coverage Ratio for each period
            - Debt_Yield: Debt Yield ratio for each period
            - LTV_Breach: Boolean flag for LTV covenant breach
            - DSCR_Breach: Boolean flag for DSCR covenant breach
            - Debt_Yield_Breach: Boolean flag for Debt Yield covenant breach
            - Covenant_Status: Overall covenant status for each period
            
        Raises:
            ValueError: If covenant monitoring fields are not configured or required data is missing
        """
        # Validate covenant monitoring is configured
        if not any([self.ongoing_ltv_max, self.ongoing_dscr_min, self.ongoing_debt_yield_min]):
            raise ValueError(
                "Covenant monitoring requires at least one ongoing covenant hurdle to be configured. "
                "Set ongoing_ltv_max, ongoing_dscr_min, or ongoing_debt_yield_min on PermanentFacility."
            )
        
        # Determine loan amount
        if loan_amount is None:
            if self.loan_amount is None:
                raise ValueError(
                    "Loan amount must be provided either as parameter or set on PermanentFacility "
                    "for covenant monitoring calculations."
                )
            loan_amount = self.loan_amount
        
        # Generate amortization schedule to get outstanding balances
        start_period = timeline.period_index[0]
        amortization_schedule = self.generate_amortization(loan_amount, start_period, index_curve)
        
        # Initialize covenant monitoring DataFrame
        covenant_results = pd.DataFrame(index=timeline.period_index)
        
        # Calculate covenant metrics for each period
        for period in timeline.period_index:
            # Get outstanding loan balance for this period
            if period in amortization_schedule.index:
                outstanding_balance = amortization_schedule.loc[period, "Begin Balance"]
            else:
                # For periods beyond loan term, balance is zero
                outstanding_balance = 0.0
            
            # Get property value and NOI for this period
            try:
                property_value = property_value_series.loc[period]
                noi = noi_series.loc[period]
            except KeyError:
                # Handle missing data by using forward fill
                property_value = property_value_series.reindex([period], method='ffill').iloc[0]
                noi = noi_series.reindex([period], method='ffill').iloc[0]
            
            # Calculate covenant metrics
            ltv = outstanding_balance / property_value if property_value > 0 else 0.0
            
            # Calculate debt service for DSCR
            debt_service = 0.0
            if period in amortization_schedule.index:
                # Get annual debt service (multiply monthly by 12)
                monthly_debt_service = amortization_schedule.loc[period, "Payment"]
                debt_service = monthly_debt_service * 12
            
            dscr = noi / debt_service if debt_service > 0 else float('inf')
            debt_yield = noi / outstanding_balance if outstanding_balance > 0 else float('inf')
            
            # Store metrics
            covenant_results.loc[period, "LTV"] = ltv
            covenant_results.loc[period, "DSCR"] = dscr
            covenant_results.loc[period, "Debt_Yield"] = debt_yield
            covenant_results.loc[period, "Outstanding_Balance"] = outstanding_balance
            covenant_results.loc[period, "Property_Value"] = property_value
            covenant_results.loc[period, "NOI"] = noi
            covenant_results.loc[period, "Debt_Service"] = debt_service
            
            # Check for covenant breaches
            ltv_breach = self.ongoing_ltv_max is not None and ltv > self.ongoing_ltv_max
            dscr_breach = self.ongoing_dscr_min is not None and dscr < self.ongoing_dscr_min
            debt_yield_breach = self.ongoing_debt_yield_min is not None and debt_yield < self.ongoing_debt_yield_min
            
            covenant_results.loc[period, "LTV_Breach"] = ltv_breach
            covenant_results.loc[period, "DSCR_Breach"] = dscr_breach
            covenant_results.loc[period, "Debt_Yield_Breach"] = debt_yield_breach
            
            # Overall covenant status
            if any([ltv_breach, dscr_breach, debt_yield_breach]):
                covenant_status = "BREACH"
            elif outstanding_balance == 0:
                covenant_status = "PAID_OFF"
            else:
                covenant_status = "COMPLIANT"
            
            covenant_results.loc[period, "Covenant_Status"] = covenant_status
        
        return covenant_results
    
    def get_covenant_breach_summary(self, covenant_results: pd.DataFrame) -> pd.Series:
        """
        Generate a summary of covenant breaches from monitoring results.
        
        Args:
            covenant_results: DataFrame from calculate_covenant_monitoring()
            
        Returns:
            Series with breach summary statistics
        """
        breach_periods = covenant_results[covenant_results["Covenant_Status"] == "BREACH"]
        
        summary = pd.Series({
            "Total_Periods": len(covenant_results),
            "Breach_Periods": len(breach_periods),
            "Breach_Rate": len(breach_periods) / len(covenant_results) if len(covenant_results) > 0 else 0.0,
            "First_Breach_Period": breach_periods.index[0] if len(breach_periods) > 0 else None,
            "Last_Breach_Period": breach_periods.index[-1] if len(breach_periods) > 0 else None,
            "Max_LTV": covenant_results["LTV"].max(),
            "Min_DSCR": covenant_results["DSCR"].min(),
            "Min_Debt_Yield": covenant_results["Debt_Yield"].min(),
            "LTV_Breach_Count": covenant_results["LTV_Breach"].sum(),
            "DSCR_Breach_Count": covenant_results["DSCR_Breach"].sum(),
            "Debt_Yield_Breach_Count": covenant_results["Debt_Yield_Breach"].sum(),
        })
        
        return summary
