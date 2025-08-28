# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
DirectCap Valuation - Income Approach

Single-period property valuation using the income approach:
Value = NOI_basis / Cap_Rate

Supports multiple NOI basis options to handle different
stabilization and timing scenarios.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Dict, Literal, Optional

import pandas as pd
from pydantic import Field, model_validator

from ..core.primitives import PositiveFloat
from .base.valuation import BaseValuation

if TYPE_CHECKING:
    from performa.deal.orchestrator import DealContext


class DirectCapValuation(BaseValuation):
    """
    Income approach valuation using direct capitalization.
    
    This is the standard real estate valuation method:
    Property Value = Net Operating Income / Capitalization Rate
    
    Supports multiple NOI basis options to handle different
    property timing and stabilization scenarios.
    
    Attributes:
        name: Human-readable name for the valuation
        cap_rate: Capitalization rate for valuation
        transaction_costs_rate: Transaction costs as % of sale price
        hold_period_months: When to place proceeds in timeline (optional)
        noi_basis_kind: Which NOI to use ("LTM", "NTM", "Stabilized", "ALM") 
        cap_rates_by_use: Asset-specific cap rates for mixed-use (optional)
        
    NOI Basis Options:
        - **LTM** (Last 12 Months): Trailing 12 months actual NOI [DEFAULT]
        - **NTM** (Next 12 Months): Forward 12 months projected NOI
        - **Stabilized**: Normalized/adjusted NOI for mature operations
        - **ALM** (12× Last Month): Simple annualization [WARNING: unreliable]
        
    Example:
        ```python
        # Standard stabilized valuation
        valuation = DirectCapValuation(
            name="Exit Valuation",
            cap_rate=0.0625,
            noi_basis_kind="LTM"  # Default: trailing 12 months
        )
        
        # Forward-looking valuation
        valuation = DirectCapValuation(
            name="Pro Forma Valuation", 
            cap_rate=0.06,
            noi_basis_kind="NTM"  # Next 12 months
        )
        ```
    """
    
    # === CORE IDENTITY ===
    kind: Literal["direct_cap"] = Field(
        default="direct_cap",
        description="Discriminator for polymorphic valuation"
    )
    
    # === VALUATION PARAMETERS ===
    cap_rate: PositiveFloat = Field(
        ..., description="Capitalization rate for property valuation"
    )
    transaction_costs_rate: PositiveFloat = Field(
        default=0.025, description="Transaction costs as percentage of sale price"  
    )
    hold_period_months: Optional[int] = Field(
        default=None, description="When to place proceeds in timeline (optional)"
    )
    noi_basis_kind: Literal["LTM", "NTM", "Stabilized", "ALM"] = Field(
        default="LTM", description="Which NOI basis to use for valuation"
    )
    
    # === ADVANCED PARAMETERS ===
    cap_rates_by_use: Optional[Dict[str, PositiveFloat]] = Field(
        default=None, description="Asset-specific cap rates for mixed-use properties"
    )
    
    # === VALIDATION ===
    @model_validator(mode="after") 
    def validate_parameters(self) -> "DirectCapValuation":
        """Validate valuation parameters are reasonable."""
        # Validate cap rate
        if not (0.01 <= self.cap_rate <= 0.20):
            raise ValueError(
                f"Cap rate ({self.cap_rate:.1%}) should be between 1% and 20%"
            )
            
        # Validate transaction costs
        if not (0.005 <= self.transaction_costs_rate <= 0.10):
            raise ValueError(
                f"Transaction costs ({self.transaction_costs_rate:.1%}) should be between 0.5% and 10%"
            )
            
        # Validate asset-specific cap rates if provided
        if self.cap_rates_by_use:
            for use_type, cap_rate in self.cap_rates_by_use.items():
                if not (0.01 <= cap_rate <= 0.20):
                    raise ValueError(
                        f"Cap rate for {use_type} ({cap_rate:.1%}) should be between 1% and 20%"
                    )
                    
        # Warn about ALM usage
        if self.noi_basis_kind == "ALM":
            warnings.warn(
                "ALM (12× last month) NOI basis can be unreliable for properties with "
                "revenue timing variations. Consider LTM or Stabilized instead.",
                UserWarning
            )
            
        return self
    
    # === COMPUTED PROPERTIES ===
    
    @property
    def net_sale_proceeds_rate(self) -> float:
        """Net proceeds rate after transaction costs."""
        return 1.0 - self.transaction_costs_rate
    
    # === NOI BASIS EXTRACTION ===
    
    def get_noi_basis(self, context: "DealContext") -> float:
        """
        Extract NOI basis from context based on specified kind.
        
        Args:
            context: Deal context containing NOI series
            
        Returns:
            Annual NOI based on specified basis kind
            
        Raises:
            ValueError: If NOI series missing or basis kind invalid
        """
        if context.noi_series is None or context.noi_series.empty:
            raise ValueError("NOI series required for DirectCap valuation")
            
        noi_series = context.noi_series
        
        if self.noi_basis_kind == "LTM":
            # Last 12 months (trailing) - DEFAULT
            trailing_periods = min(12, len(noi_series))
            noi_basis = noi_series.iloc[-trailing_periods:].sum()
            
            # Annualize if less than 12 months available
            if trailing_periods < 12:
                noi_basis *= (12 / trailing_periods)
                
        elif self.noi_basis_kind == "NTM":
            # Next 12 months (forward-looking)
            forward_periods = min(12, len(noi_series))  
            noi_basis = noi_series.iloc[:forward_periods].sum()
            
            # Annualize if less than 12 months available
            if forward_periods < 12:
                noi_basis *= (12 / forward_periods)
                
        elif self.noi_basis_kind == "Stabilized":
            # Normalized/stabilized NOI (use mean of all periods)
            noi_basis = noi_series.mean() * 12
            
        elif self.noi_basis_kind == "ALM":
            # Annualized last month (12× last month) - WARNING: unreliable
            noi_basis = noi_series.iloc[-1] * 12
            
        else:
            raise ValueError(f"Unknown NOI basis kind: {self.noi_basis_kind}")
            
        return noi_basis
    
    # === CALCULATION METHODS ===
    
    def calculate_gross_value(
        self, noi_basis: float, noi_by_use: Optional[Dict[str, float]] = None
    ) -> float:
        """
        Calculate gross property value before transaction costs.
        
        Args:
            noi_basis: Annual NOI for valuation
            noi_by_use: NOI breakdown by use type (for mixed-use)
            
        Returns:
            Gross property value
        """
        if self.cap_rates_by_use and noi_by_use:
            # Use asset-specific cap rates for mixed-use
            total_value = 0.0
            for use_type, noi in noi_by_use.items():
                if use_type in self.cap_rates_by_use:
                    cap_rate = self.cap_rates_by_use[use_type]
                    total_value += noi / cap_rate
                else:
                    # Fall back to blended cap rate
                    total_value += noi / self.cap_rate
            return total_value
        else:
            # Simple direct cap valuation
            return noi_basis / self.cap_rate
    
    def calculate_net_proceeds(
        self, noi_basis: float, noi_by_use: Optional[Dict[str, float]] = None
    ) -> float:
        """
        Calculate net disposition proceeds after transaction costs.
        
        Args:
            noi_basis: Annual NOI for valuation
            noi_by_use: NOI breakdown by use type (for mixed-use)
            
        Returns:
            Net disposition proceeds
        """
        gross_value = self.calculate_gross_value(noi_basis, noi_by_use)
        return gross_value * self.net_sale_proceeds_rate
    
    def calculate_value(self, context: "DealContext") -> Dict[str, float]:
        """
        Calculate property value using direct capitalization.
        
        Args:
            context: Deal context containing NOI series
            
        Returns:
            Dictionary with valuation results
        """
        noi_basis = self.get_noi_basis(context)
        gross_value = self.calculate_gross_value(noi_basis)
        net_proceeds = self.calculate_net_proceeds(noi_basis)
        
        return {
            "property_value": net_proceeds,
            "gross_value": gross_value,
            "net_proceeds": net_proceeds,
            "noi_basis": noi_basis,
            "noi_basis_kind": self.noi_basis_kind,
            "cap_rate": self.cap_rate,
            "transaction_costs": gross_value - net_proceeds,
            "transaction_costs_rate": self.transaction_costs_rate,
            "implied_yield": noi_basis / net_proceeds if net_proceeds > 0 else 0.0,
        }
    
    def calculate_metrics(
        self, 
        context: "DealContext",
        total_cost_basis: Optional[float] = None
    ) -> Dict[str, float]:
        """
        Calculate comprehensive DirectCap metrics.
        
        Args:
            context: Deal context containing NOI series
            total_cost_basis: Total cost basis for return calculations (optional)
            
        Returns:
            Dictionary of comprehensive metrics
        """
        value_results = self.calculate_value(context)
        
        # Add cost basis comparisons if provided
        if total_cost_basis is not None:
            net_proceeds = value_results["net_proceeds"]
            noi_basis = value_results["noi_basis"]
            
            value_results.update({
                "total_cost_basis": total_cost_basis,
                "total_profit": net_proceeds - total_cost_basis,
                "profit_margin": ((net_proceeds - total_cost_basis) / total_cost_basis)
                if total_cost_basis > 0 else 0.0,
                "yield_on_cost": noi_basis / total_cost_basis 
                if total_cost_basis > 0 else 0.0,
            })
            
        return value_results
    
    def compute_cf(self, context: "DealContext") -> pd.Series:
        """
        Compute disposition cash flow series for DirectCap valuation.
        
        Args:
            context: Deal context containing timeline and NOI series
            
        Returns:
            pd.Series containing disposition proceeds aligned with timeline
        """
        # Initialize cash flow series
        disposition_cf = pd.Series(0.0, index=context.timeline.period_index)
        
        try:
            # Calculate net proceeds
            value_results = self.calculate_value(context)
            net_proceeds = value_results["net_proceeds"]
            
            # Place proceeds at appropriate time
            if not context.timeline.period_index.empty:
                if self.hold_period_months is not None:
                    # Use specified hold period if provided
                    if self.hold_period_months < len(context.timeline.period_index):
                        disposition_period = context.timeline.period_index[self.hold_period_months]
                    else:
                        # If hold period exceeds timeline, use last period
                        disposition_period = context.timeline.period_index[-1]
                else:
                    # Default to last period if no hold period specified
                    disposition_period = context.timeline.period_index[-1]
                    
                disposition_cf[disposition_period] = net_proceeds
                
        except Exception as e:
            # Fail fast instead of silently returning zeros
            raise RuntimeError(f"DirectCap valuation failed: {e}") from e
            
        return disposition_cf
    
    # === FACTORY METHODS ===
    
    @classmethod
    def conservative(
        cls, 
        name: str = "Conservative Valuation",
        cap_rate: float = 0.065,
        **kwargs
    ) -> "DirectCapValuation":
        """Factory method for conservative valuation assumptions."""
        return cls(
            name=name,
            cap_rate=cap_rate,
            transaction_costs_rate=0.025,  # 2.5% transaction costs
            noi_basis_kind="LTM",  # Conservative: use actual trailing NOI
            **kwargs
        )
    
    @classmethod  
    def aggressive(
        cls,
        name: str = "Aggressive Valuation", 
        cap_rate: float = 0.055,
        **kwargs
    ) -> "DirectCapValuation":
        """Factory method for aggressive valuation assumptions."""
        return cls(
            name=name,
            cap_rate=cap_rate,
            transaction_costs_rate=0.020,  # 2.0% transaction costs
            noi_basis_kind="NTM",  # Aggressive: use forward NOI
            **kwargs
        )
        
    @classmethod
    def exit_valuation(
        cls,
        name: str = "Exit Valuation",
        cap_rate: float = 0.0625,
        hold_period_months: int = 60,
        **kwargs
    ) -> "DirectCapValuation":
        """Factory method for exit/disposition valuation."""
        return cls(
            name=name,
            cap_rate=cap_rate,
            transaction_costs_rate=0.025,
            hold_period_months=hold_period_months,
            noi_basis_kind="LTM",  # Use actual trailing NOI for exit
            **kwargs
        )