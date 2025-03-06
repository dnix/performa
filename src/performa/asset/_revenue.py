import math
from datetime import date
from typing import Callable, Dict, List, Literal, Optional, Union

import numpy as np
import pandas as pd
from pydantic import Field, model_validator

from ..core._cash_flow import CashFlowModel
from ..core._enums import (
    FrequencyEnum,
    LeaseStatusEnum,
    LeaseTypeEnum,
    ProgramUseEnum,
    RevenueSubcategoryEnum,
    UnitOfMeasureEnum,
)
from ..core._model import Model
from ..core._timeline import Timeline
from ..core._types import (
    FloatBetween0And1,
    PositiveFloat,
    PositiveInt,
)
from ._recovery import RecoveryMethod


class Tenant(Model):
    """
    Individual tenant record representing a lease agreement.

    Attributes:
        id: Unique identifier
        name: Tenant name
    """

    # Identity
    id: str
    name: str
    # suite: str

    # # Space
    # leased_area: PositiveFloat  # in square feet
    # percent_of_building: FloatBetween0And1

    # # Use
    # use_type: ProgramUseEnum

    # # Current Lease Terms
    # lease_start: date
    # lease_end: date
    # current_base_rent: PositiveFloat  # annual or monthly rent
    # rent_type: LeaseTypeEnum  # options: Gross, Net, Modified Gross
    # expense_base_year: Optional[int] = None

    # # Renewal Terms
    # # renewal_probability: FloatBetween0And1  # NOTE: this should only be in the lease model?
    # market_profile: MarketProfile  # reference to applicable market assumptions


class RentEscalation(Model):
    """
    Rent increase structure for a lease.

    Attributes:
        type: Type of escalation (fixed, CPI, percentage)
        amount: Amount of increase (percentage or fixed amount)
        unit_of_measure: Units for the amount
        is_relative: Whether amount is relative to previous rent
        start_date: When increase takes effect
        recurring: Whether increase repeats
        frequency_months: How often increase occurs if recurring
    """

    # TODO: confirm fields are thorough and DRY
    type: Literal["fixed", "percentage", "cpi"]
    amount: PositiveFloat
    unit_of_measure: UnitOfMeasureEnum
    is_relative: bool  # True for relative to base rent
    start_date: date
    recurring: bool = False
    frequency_months: Optional[int] = None


class RentAbatement(Model):
    """
    Structured rent abatement (free rent) periods.

    Attributes:
        months: Duration of free rent
        includes_recoveries: Whether recoveries are also abated
        start_month: When free rent begins (relative to lease start)
        abated_ratio: Portion of rent that is abated
    """

    months: int
    includes_recoveries: bool = False
    start_month: int = 1
    abated_ratio: FloatBetween0And1 = 1.0


class TenantImprovementAllowance(CashFlowModel):
    """
    Represents tenant improvement allowance provided by landlord.
    
    Extends CashFlowModel to leverage existing cash flow calculation capabilities.
    
    Attributes:
        category: Fixed as "Expense"
        subcategory: Fixed as "TI Allowance"
        payment_method: How TI is paid (upfront or amortized)
        payment_date: When upfront payment is made (defaults to lease start)
        interest_rate: Interest rate for amortization (if applicable)
        amortization_term_months: Period over which to amortize (if applicable)
    """
    # Inherit core fields from CashFlowModel
    # category will be fixed as "Expense"
    category: str = "Expense"
    subcategory: str = "TI Allowance"
    
    # TI-specific fields
    payment_method: Literal["upfront", "amortized"] = "upfront"
    payment_date: Optional[date] = None
    interest_rate: Optional[FloatBetween0And1] = None
    amortization_term_months: Optional[PositiveInt] = None
    
    @model_validator(mode='after')
    def validate_amortization(self) -> 'TenantImprovementAllowance':
        """Validate that amortization parameters are provided when needed."""
        if self.payment_method == "amortized":
            if self.interest_rate is None:
                raise ValueError("interest_rate is required for amortized TI")
            if self.amortization_term_months is None:
                raise ValueError("amortization_term_months is required for amortized TI")
        return self
    
    def compute_cf(
        self,
        lookup_fn: Optional[Callable[[str], Union[float, pd.Series]]] = None
    ) -> pd.Series:
        """
        Compute TI cash flow series, handling both upfront and amortized payment methods.
        
        For upfront payments, returns a single payment at the specified date.
        For amortized payments, calculates a loan-like payment schedule.
        
        Args:
            lookup_fn: Optional function to resolve references
            
        Returns:
            Monthly cash flow series
        """
        # Get the base cash flow using CashFlowModel logic
        base_cf = super().compute_cf(lookup_fn)
        
        # If upfront payment, we return a single payment at the specified date
        if self.payment_method == "upfront":
            payment_date = self.payment_date or self.timeline.start_date.to_timestamp().date()
            payment_period = pd.Period(payment_date, freq="M")
            
            # Create a series with zero values except for the payment period
            ti_cf = pd.Series(0, index=self.timeline.period_index)
            if payment_period in ti_cf.index:
                # Put the entire TI amount in the payment period
                total_amount = base_cf.sum()
                ti_cf[payment_period] = total_amount
            
            return ti_cf
        
        # If amortized, we calculate a loan-like payment schedule
        elif self.payment_method == "amortized":
            assert self.interest_rate is not None
            assert self.amortization_term_months is not None
            
            # Calculate total TI amount
            total_amount = base_cf.sum()
            
            # Calculate monthly payment using standard loan amortization formula
            monthly_rate = self.interest_rate / 12
            monthly_payment = total_amount * (monthly_rate * (1 + monthly_rate) ** self.amortization_term_months) / \
                             ((1 + monthly_rate) ** self.amortization_term_months - 1)
            
            # Create a series with the calculated monthly payments
            # restricted to the amortization period
            amort_end = self.timeline.start_date + self.amortization_term_months - 1
            amort_periods = pd.period_range(
                start=self.timeline.start_date,
                end=min(amort_end, self.timeline.end_date),
                freq="M"
            )
            
            ti_cf = pd.Series(0, index=self.timeline.period_index)
            ti_cf.loc[amort_periods] = monthly_payment
            
            return ti_cf
        
        # This should never happen due to the validator, but included for completeness
        else:
            return pd.Series(0, index=self.timeline.period_index)


class CommissionTier(Model):
    """
    Represents a tier in the leasing commission structure.
    
    Attributes:
        year_start: First lease year this commission applies to (default: 1)
        year_end: Last lease year this commission applies to (None means all remaining years)
        rate: Commission rate as percentage of rent
    """
    # FIXME: revisit this definition
    year_start: PositiveInt = 1
    year_end: Optional[PositiveInt] = None
    rate: FloatBetween0And1
    
    @property
    def years_description(self) -> str:
        """
        Human-readable description of the years range.
        
        Returns:
            String representation of the years range (e.g., "1+", "1", "1-5")
        """
        if self.year_end is None:
            return f"{self.year_start}+"
        elif self.year_start == self.year_end:
            return f"{self.year_start}"
        else:
            return f"{self.year_start}-{self.year_end}"


class LeasingCommission(CashFlowModel):
    """
    Represents leasing commissions paid to brokers.
    
    Extends CashFlowModel to leverage existing cash flow calculation capabilities.
    
    Attributes:
        category: Fixed as "Expense"
        subcategory: Fixed as "Leasing Commission"
        tiers: Commission tiers (different rates for different lease years)
        landlord_broker_percentage: Percentage of commission going to landlord's broker (default: 0.5)
        tenant_broker_percentage: Percentage of commission going to tenant's broker (default: 0.5)
        payment_timing: When commissions are paid (default: "signing")
        renewal_rate: Commission rate for renewal (if different)
    """
    # FIXME: revisit this class
    # Inherit core fields from CashFlowModel
    # category will be fixed as "Expense"
    category: str = "Expense"
    subcategory: str = "Leasing Commission"
    
    # LC-specific fields
    tiers: List[CommissionTier]
    landlord_broker_percentage: FloatBetween0And1 = 0.5
    tenant_broker_percentage: FloatBetween0And1 = 0.5
    payment_timing: Literal["signing", "commencement"] = "signing"
    renewal_rate: Optional[FloatBetween0And1] = None
    
    # For LC, the value will represent the rent series used to calculate commissions
    # This will typically be a reference to the lease's base rent
    
    @model_validator(mode='after')
    def validate_broker_percentages(self) -> 'LeasingCommission':
        """
        Validate that broker percentages sum to 1.0.
        
        Returns:
            The validated LeasingCommission instance
            
        Raises:
            ValueError: If broker percentages don't sum to 1.0
        """
        if not math.isclose(self.landlord_broker_percentage + self.tenant_broker_percentage, 1.0):
            raise ValueError("Broker percentages must sum to 1.0")
        return self
    
    def compute_cf(
        self,
        lookup_fn: Optional[Callable[[str], Union[float, pd.Series]]] = None
    ) -> pd.Series:
        """
        Compute leasing commission cash flow.
        
        Uses the reference (typically the lease's base rent) to calculate
        commissions based on the defined tiers.
        
        Args:
            lookup_fn: Optional function to resolve references
            
        Returns:
            Monthly cash flow series
        """
        # Get the base rent series using CashFlowModel logic to resolve the reference
        rent_series = super().compute_cf(lookup_fn)
        
        # Initialize commission cash flow series
        lc_cf = pd.Series(0, index=self.timeline.period_index)
        
        # Get total months in lease and convert to years
        lease_months = len(self.timeline.period_index)
        lease_years = math.ceil(lease_months / 12)
        
        # Calculate commission for each tier
        for tier in self.tiers:
            # Determine which months this tier applies to
            start_month = (tier.year_start - 1) * 12
            if tier.year_end is None:
                end_month = lease_months
            else:
                end_month = min(tier.year_end * 12, lease_months)
            
            # Skip if outside lease term
            if start_month >= lease_months or end_month <= 0:
                continue
            
            # Get the periods for this tier
            tier_periods = self.timeline.period_index[start_month:end_month]
            
            # Calculate commission for this tier
            tier_rent = rent_series.loc[tier_periods]
            tier_commission = tier_rent.sum() * tier.rate
            
            # Determine payment period based on payment timing
            if self.payment_timing == "signing":
                # FIXME: should this be the first period of the lease?
                payment_period = self.timeline.period_index[0]
            else:  # "commencement"
                # Find the first period of the tier
                payment_period = tier_periods[0]
            
            # Add commission to the cash flow series
            if payment_period in lc_cf.index:
                lc_cf[payment_period] += tier_commission
        
        return lc_cf


class Lease(CashFlowModel):
    """
    Represents a lease agreement.
    
    This model handles the key lease attributes and cash flow modeling,
    building on the CashFlowModel base class for timeline and computation.
    
    Attributes:
        name: Name of the lease (typically tenant name + suite)
        category: Fixed as "Revenue"
        subcategory: Revenue subcategory (Office, Retail, etc.)
        timeline: Timeline for the lease
        value: Base rent value (can be a single value, series, or reference)
        unit_of_measure: Units for the value
        frequency: Frequency of the value (default: monthly)
        tenant: The tenant entity
        suite: Suite/unit identifier
        floor: Floor number or identifier (optional)
        use_type: Type of use (office, retail, etc.)
        status: Current status of the lease
        lease_type: Type of lease arrangement (gross, net, etc.)
        area: Square footage leased by tenant
        rent_escalations: List of rent escalations applied to this lease
        recovery_method: Method for calculating expense recoveries
        ti_allowance: Tenant improvement allowance (optional)
        leasing_commission: Leasing commission structure (optional)
    """
    # Basic fields from CashFlowModel
    name: str
    category: str = "Revenue"
    subcategory: RevenueSubcategoryEnum = RevenueSubcategoryEnum.LEASE
    timeline: Timeline
    value: Union[PositiveFloat, pd.Series, Dict, List]
    unit_of_measure: UnitOfMeasureEnum
    frequency: FrequencyEnum = FrequencyEnum.MONTHLY

    # Tenant information
    tenant: Tenant
    suite: str
    floor: Optional[str] = None
    use_type: ProgramUseEnum
    
    # Lease details
    status: LeaseStatusEnum
    lease_type: LeaseTypeEnum
    area: PositiveFloat  # in square feet

    # Rent modifications
    rent_escalations: Optional[List[RentEscalation]] = Field(default_factory=list)
    # free_rent: Optional[List[RentAbatement]] = Field(default_factory=list)

    # Recovery
    recovery_method: Optional[RecoveryMethod] = None

    # TI and LC
    ti_allowance: Optional[TenantImprovementAllowance] = None
    leasing_commission: Optional[LeasingCommission] = None

    # TODO: Add renewal options
    # TODO: Add special provisions (percentage rent, etc.)
    # TODO: Add rollover assumptions

    # # Rollover
    # upon_expiration: Literal["market", "renew", "vacate", "option", "reconfigured"]
    # rollover_assumption: Optional[str]  # Reference to RLA

    @property
    def lease_start(self) -> date:
        """
        Get the start date of the lease.
        
        Returns:
            Date object representing the lease start date
        """
        return self.timeline.start_date.to_timestamp().date()
    
    @property
    def lease_end(self) -> date:
        """
        Get the end date of the lease.
        
        Returns:
            Date object representing the lease end date
        """
        return self.timeline.end_date.to_timestamp().date()
    
    @property
    def is_active(self) -> bool:
        """
        Check if the lease is currently active.
        
        Returns:
            True if today's date is within the lease term, False otherwise
        """
        today = date.today()
        return self.lease_start <= today <= self.lease_end
    
    @classmethod
    def from_dates(
        cls,
        tenant_name: str,
        suite: str,
        lease_start: date,
        lease_end: date,
        **kwargs
    ) -> "Lease":
        """
        Create a lease with specific start and end dates.
        
        Args:
            tenant_name: Name of the tenant
            suite: Suite/unit identifier
            lease_start: Start date of the lease
            lease_end: End date of the lease
            **kwargs: Additional arguments to pass to the Lease constructor
        
        Returns:
            A new Lease instance
            
        Raises:
            ValueError: If lease_start is after lease_end
        """
        if lease_start >= lease_end:
            raise ValueError("Lease start date must be before end date")
        
        # Set default name if not provided
        if "name" not in kwargs:
            kwargs["name"] = f"{tenant_name} - {suite}"
        
        # Create the timeline
        timeline = Timeline.from_dates(
            start_date=lease_start,
            end_date=lease_end
        )
        
        return cls(
            tenant_name=tenant_name,
            suite=suite,
            timeline=timeline,
            **kwargs
        )
    
    @classmethod
    def from_duration(
        cls,
        tenant_name: str,
        suite: str,
        lease_start: date,
        lease_term_months: PositiveInt,
        **kwargs
    ) -> "Lease":
        """
        Create a lease with start date and duration in months.
        
        Args:
            tenant_name: Name of the tenant
            suite: Suite/unit identifier
            lease_start: Start date of the lease
            lease_term_months: Duration of lease in months
            **kwargs: Additional arguments to pass to the Lease constructor
        
        Returns:
            A new Lease instance
        """
        # Set default name if not provided
        if "name" not in kwargs:
            kwargs["name"] = f"{tenant_name} - {suite}"
        
        # Create the timeline
        timeline = Timeline(
            start_date=lease_start,
            duration_months=lease_term_months
        )
        
        return cls(
            tenant_name=tenant_name,
            suite=suite,
            timeline=timeline,
            **kwargs
        )
    
    def _apply_escalations(self, base_flow: pd.Series) -> pd.Series:
        """
        Apply all rent escalations to the base rent flow.
        
        Args:
            base_flow: Base rent cash flow series
            
        Returns:
            Modified cash flow with all escalations applied
        """
        if not self.rent_escalations:
            return base_flow
        
        rent_with_escalations = base_flow.copy()
        periods = self.timeline.period_index
        
        for escalation in self.rent_escalations:
            # Convert start date to period
            start_period = pd.Period(escalation.start_date, freq="M")
            
            # Create mask for periods where the escalation applies
            mask = periods >= start_period
            
            if escalation.type == "percentage":
                if escalation.recurring:
                    # For recurring percentage increases, calculate compound growth
                    freq = escalation.frequency_months or 12  # Default to annual
                    # Calculate how many escalation cycles for each period
                    months_elapsed = np.array([(p - start_period).n for p in periods])
                    cycles = np.floor(months_elapsed / freq) 
                    cycles[~mask] = 0  # Zero out cycles outside the mask
                    
                    # Apply compound growth: (1 + rate)^cycles
                    # For relative escalations, use compound growth
                    if escalation.is_relative:
                        growth_factor = np.power(1 + (escalation.amount / 100), cycles)
                        rent_with_escalations = rent_with_escalations * growth_factor
                    else:
                        # For absolute escalations, apply to base rent
                        growth_factor = np.power(1 + (escalation.amount / 100), cycles)
                        escalation_series = base_flow * (growth_factor - 1)
                        rent_with_escalations += escalation_series
                else:
                    # For one-time percentage increases
                    if escalation.is_relative:
                        # Apply to the current rent
                        growth_factor = 1 + (escalation.amount / 100)
                        rent_with_escalations[mask] *= growth_factor
                    else:
                        # Apply to the base rent
                        growth_factor = escalation.amount / 100
                        escalation_series = pd.Series(0, index=periods)
                        escalation_series[mask] = base_flow[mask] * growth_factor
                        rent_with_escalations += escalation_series
                
            elif escalation.type == "fixed":
                # For fixed amount escalations
                if escalation.recurring:
                    # For recurring fixed increases, calculate step increases
                    freq = escalation.frequency_months or 12  # Default to annual
                    months_elapsed = np.array([(p - start_period).n for p in periods])
                    cycles = np.floor(months_elapsed / freq)
                    cycles[~mask] = 0  # Zero out cycles outside the mask
                    
                    # Monthly equivalent of the fixed amount
                    monthly_amount = escalation.amount / 12 if escalation.unit_of_measure == UnitOfMeasureEnum.AMOUNT else escalation.amount
                    
                    # For relative increases, each cycle adds another increment
                    if escalation.is_relative:
                        cumulative_increases = cycles * monthly_amount
                        escalation_series = pd.Series(cumulative_increases, index=periods)
                        rent_with_escalations += escalation_series
                    else:
                        # For absolute increases, apply to the base
                        cumulative_increases = cycles * monthly_amount
                        escalation_series = pd.Series(cumulative_increases, index=periods)
                        rent_with_escalations += escalation_series
                else:
                    # For one-time fixed increases
                    # Monthly equivalent of the fixed amount
                    monthly_amount = escalation.amount / 12 if escalation.unit_of_measure == UnitOfMeasureEnum.AMOUNT else escalation.amount
                    escalation_series = pd.Series(0, index=periods)
                    escalation_series[mask] = monthly_amount
                    rent_with_escalations += escalation_series
                    
            elif escalation.type == "cpi":
                # TODO: Implement CPI-based escalations
                # This would require a CPI index reference
                raise NotImplementedError("CPI-based escalations are not yet implemented")
        
        return rent_with_escalations
    
    def compute_cf(
        self,
        property_area: Optional[PositiveFloat] = None,
        occupancy_rate: Optional[float] = None,
        lookup_fn: Optional[Callable[[str], Union[float, pd.Series]]] = None
    ) -> Dict[str, pd.Series]:
        """
        Compute cash flows for the lease including base rent, recoveries, TI, and LC.
        
        Args:
            property_area: Total property area for recovery calculations
            occupancy_rate: Current or projected occupancy rate
            lookup_fn: Optional function to resolve references
            
        Returns:
            Dictionary of cash flow series by type (base_rent, recoveries, revenue, 
            ti_allowance, leasing_commission, expenses, net)
        """
        # Get base cash flows using existing implementation
        base_rent = super().compute_cf(lookup_fn)
        base_rent_with_escalations = self._apply_escalations(base_rent)
        
        # Calculate recoveries if applicable
        # TODO: create a method to apply recoveries to the base rent
        recoveries = pd.Series(0, index=self.timeline.period_index)
        if self.recovery_method and property_area:
            recoveries = self.recovery_method.calculate_recoveries(
                tenant_area=self.area,
                property_area=property_area,
                timeline=self.timeline.period_index,
                occupancy_rate=occupancy_rate
            )
        
        # Calculate TI cash flows if applicable
        # TODO: create a method to apply TI to the base rent
        ti_cf = pd.Series(0, index=self.timeline.period_index)
        if self.ti_allowance:
            # Ensure TI timeline matches the lease timeline
            ti_cf = self.ti_allowance.compute_cf(lookup_fn)
            # Align to lease timeline in case of differences
            ti_cf = ti_cf.reindex(self.timeline.period_index, fill_value=0)
        
        # Calculate LC cash flows if applicable
        # TODO: create a method to apply LC to the base rent
        lc_cf = pd.Series(0, index=self.timeline.period_index)
        if self.leasing_commission:
            # Ensure LC timeline matches the lease timeline
            lc_cf = self.leasing_commission.compute_cf(lookup_fn)
            # Align to lease timeline in case of differences
            lc_cf = lc_cf.reindex(self.timeline.period_index, fill_value=0)
        
        # Calculate total cash flows
        revenue_cf = base_rent_with_escalations + recoveries
        expense_cf = ti_cf + lc_cf
        net_cf = revenue_cf - expense_cf
        
        # Return all components
        return {
            "base_rent": base_rent_with_escalations,
            "recoveries": recoveries,
            "revenue": revenue_cf,
            "ti_allowance": ti_cf,
            "leasing_commission": lc_cf,
            "expenses": expense_cf,
            "net": net_cf
        }
    # FIXME: dataframe all the things? how do we want to handle cash flow components for later disaggregation?


class VacantSuite(Model):
    """
    Represents a vacant leasable space.

    Attributes:
        suite_id: Unique identifier for the space
        area: Square footage
        use_type: Intended use
        asking_rent: Listed rental rate
        last_lease_end: When space became vacant (optional)
    """

    suite_id: str
    area: PositiveFloat
    use_type: ProgramUseEnum
    asking_rent: PositiveFloat
    last_lease_end: Optional[date] = None


class RentRoll(Model):
    """
    Collection of all leases and vacant spaces.
    
    Attributes:
        leases: List of all lease agreements
        vacant_suites: List of all vacant suites
    """

    leases: List[Lease]
    vacant_suites: List[VacantSuite]

    @property
    def total_occupied_area(self) -> PositiveFloat:
        """
        Calculate total leased area in square feet.
        
        Returns:
            Sum of all leased areas
        """
        return sum(lease.area for lease in self.leases)

    @property
    def occupancy_rate(self) -> FloatBetween0And1:
        """
        Calculate current occupancy rate as a decimal between 0 and 1.
        
        Returns:
            Occupancy rate (leased area / total area)
        """
        total_area = self.total_occupied_area + sum(
            suite.area for suite in self.vacant_suites
        )
        return self.total_occupied_area / total_area if total_area > 0 else 0.0

    @model_validator(mode="after")
    def validate_lease_tenant_mapping(self) -> "RentRoll":
        """
        Ensure all leases map to tenants in the rent roll.
        
        Returns:
            The validated RentRoll instance
            
        Raises:
            ValueError: If a lease references a tenant not found in the rent roll
        """
        tenant_names = {lease.tenant_name for lease in self.leases}
        for lease in self.leases:
            if lease.tenant_name not in tenant_names:
                raise ValueError(
                    f"Lease references tenant {lease.tenant_name} "
                    f"not found in rent roll"
                )
        return self

    # TODO: add validation for total area

    # TODO: property for all suites
    # TODO: property for stacked floors data (to enable viz)


class MiscIncome(CashFlowModel):
    """
    Represents miscellaneous income items like parking revenue, vending, antenna income, etc.

    Attributes:
        category: Fixed as "Revenue"
        subcategory: Revenue subcategory (e.g., "Miscellaneous")
        variable_ratio: Portion of income that varies with occupancy (0-1)
        growth_rate: Annual growth rate for income (e.g., 0.03 for 3% growth)
    """
    category: str = "Revenue"
    subcategory: RevenueSubcategoryEnum = "Miscellaneous"
    
    # For variable calculation
    variable_ratio: Optional[FloatBetween0And1] = None
    
    # For growth calculation
    growth_rate: Optional[FloatBetween0And1] = None
    
    # TODO: Add support for expense offsetting in recovery calculations
    # TODO: Add support for revenue sharing with tenants
    # TODO: Add support for percentage rent exclusions
    
    @property
    def is_variable(self) -> bool:
        """
        Check if the income is variable with occupancy.
        
        Returns:
            True if variable_ratio is set, False otherwise
        """
        return self.variable_ratio is not None
    
    def compute_cf(
        self,
        occupancy_rate: Optional[float] = None,
        lookup_fn: Optional[Callable[[str], Union[float, pd.Series]]] = None
    ) -> pd.Series:
        """
        Compute the cash flow for the miscellaneous income item with optional 
        occupancy and growth adjustments.
        
        Args:
            occupancy_rate: Current or projected occupancy rate (0-1)
            lookup_fn: Optional function to resolve references
            
        Returns:
            Monthly cash flow series
        """
        # Compute the base cash flow
        base_flow = super().compute_cf(lookup_fn)
        
        # Apply growth rate adjustment if provided
        if self.growth_rate is not None:
            months = np.arange(len(base_flow))
            growth_factors = np.power(1 + (self.growth_rate / 12), months)
            base_flow = base_flow * growth_factors

        # Apply occupancy adjustment if applicable
        if occupancy_rate is not None and self.is_variable:
            variable_ratio = self.variable_ratio
            adjustment_ratio = (1 - variable_ratio) + variable_ratio * occupancy_rate
            base_flow = base_flow * adjustment_ratio
        
        return base_flow


class MiscIncomeCollection(Model):
    """
    Collection of miscellaneous income items.
    
    Attributes:
        income_items: List of miscellaneous income items
    """
    income_items: List[MiscIncome]
    
    @property
    def total_annual_income(self) -> PositiveFloat:
        """
        Calculate total annual base income by summing the cash flows of all income items.
        
        Returns:
            Total annual income as a positive float
            
        Raises:
            ValueError: If no income items are provided
        """
        if not self.income_items:
            raise ValueError("No income items provided")
        
        # Sum the cash flows of all income items
        return sum(item.compute_cf() for item in self.income_items)
    
    @property
    def total_annual_income_df(self) -> pd.DataFrame:
        """
        Calculate total annual base income using pandas DataFrame approach.
        
        Returns:
            DataFrame with income items and their values
            
        Raises:
            ValueError: If no income items are provided
        """
        if not self.income_items:
            raise ValueError("No income items provided")
        
        # Create a DataFrame with income items and their values
        df = pd.DataFrame({
            'name': [item.name for item in self.income_items],
            'value': [item.value for item in self.income_items]
        })
        
        return df
    
    # TODO: Add methods for handling expense offsetting income
    # TODO: Add methods for handling percentage rent eligible income
    # TODO: Add methods for handling revenue sharing calculations


class SecurityDeposit(Model):
    """
    Model representing the security deposit configuration for a tenant.

    Attributes:
        deposit_mode: Indicates if the security deposit is fully refundable, 
            entirely non-refundable, or a hybrid approach
        deposit_unit: Unit used to express the deposit (months of rent, 
            fixed dollar amount, or rate per square foot)
        deposit_amount: The total amount of the security deposit
        interest_rate: The interest rate applicable to the refundable portion
            of the deposit (only relevant for "Refundable" or "Hybrid" modes)
        percent_to_refund: The percentage of the deposit that is refundable
            (only relevant for "Hybrid" mode)
    """
    deposit_mode: Literal["Refundable", "Non-Refundable", "Hybrid"]
    deposit_unit: Literal["Months", "Dollar", "DollarPerSF"]
    deposit_amount: PositiveFloat
    interest_rate: Optional[FloatBetween0And1] = None
    percent_to_refund: Optional[FloatBetween0And1] = None


class Revenues(Model):
    """
    Represents the revenue generated by an asset.

    Attributes:
        revenue_items: List of revenue line items as CashFlowModel instances
    """
    # FIXME: develop this further

    revenue_items: List[CashFlowModel]

    @property
    def total_revenue(self) -> PositiveFloat:
        """
        Calculate total revenue by summing all revenue items.
        
        Returns:
            Total revenue as a positive float
        """
        return sum(item.amount for item in self.line_items)
