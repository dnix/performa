import logging
import math
from typing import Callable, List, Literal, Optional, Union

import pandas as pd
from pydantic import FloatBetween0And1, PositiveInt, model_validator

from ..core._cash_flow import CashFlowModel
from ..core._model import Model

logger = logging.getLogger(__name__)

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
    
    Extends CashFlowModel. The `compute_cf` method expects the `reference` 
    attribute to point to the relevant rent series (e.g., via the Lease's model_id
    or potentially an aggregate key if rent itself is aggregate-based, though less common).
    The base `CashFlowModel.compute_cf` is used to resolve this reference and 
    retrieve the rent series, which is then used for tier calculations.
    
    The `reference` attribute, if a string, can refer to either:
      - An attribute of the `Property` object (unlikely for LC calculation base).
      - The string value of an `AggregateLineKey` enum member.
      The base `compute_cf` expects the lookup to return a pandas Series representing rent.
    
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
        logger.debug(f"Computing cash flow for Leasing Commission: '{self.name}' ({self.model_id})")
        logger.debug("  Calculating base rent series using super().compute_cf.")
        rent_series = super().compute_cf(lookup_fn)
        logger.debug(f"  Calculated base rent series. Total Rent: {rent_series.sum():.2f}")
        
        # Initialize commission cash flow series
        lc_cf = pd.Series(0, index=self.timeline.period_index)
        
        # Get total months in lease and convert to years
        lease_months = len(self.timeline.period_index)
        lease_years = math.ceil(lease_months / 12)
        
        logger.debug(f"  Applying commission tiers. Payment Timing: {self.payment_timing}")
        # Calculate commission for each tier
        total_commission_calculated = 0.0
        for tier in self.tiers:
            logger.debug(f"    Processing Tier: Years {tier.years_description}, Rate: {tier.rate:.1%}")
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
            total_commission_calculated += tier_commission
            logger.debug(f"      Tier Commission: {tier_commission:.2f} (Based on rent sum: {tier_rent.sum():.2f})")
            
            # Determine payment period based on payment timing
            if self.payment_timing == "signing":
                # FIXME: should this be the first period of the lease?
                payment_period = self.timeline.period_index[0]
            else:  # "commencement"
                # Find the first period of the tier
                payment_period = tier_periods[0]
            
            logger.debug(f"      Payment Period: {payment_period}")
            
            # Add commission to the cash flow series
            if payment_period in lc_cf.index:
                lc_cf[payment_period] += tier_commission
        
        logger.debug(f"Finished computing cash flow for Leasing Commission: '{self.name}'. Total Calculated: {total_commission_calculated:.2f}, Final CF Sum: {lc_cf.sum():.2f}")
        return lc_cf
