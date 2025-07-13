"""
Universal Direct Capitalization Valuation - Simple Cap Rate Analysis

Universal direct cap valuation that works for any property type:
office, residential, development projects, existing assets, etc.
"""

from __future__ import annotations

from typing import Dict, Literal, Optional
from uuid import UUID, uuid4

import pandas as pd
from pydantic import Field, model_validator

from ..core.primitives import Model, PositiveFloat


class DirectCapValuation(Model):
    """
    Universal direct capitalization valuation for any property type.
    
    Provides simple cap rate valuation using first-year NOI,
    the most common quick valuation method in real estate.
    
    Attributes:
        name: Human-readable name for the valuation scenario
        cap_rate: Cap rate for property valuation
        occupancy_adjustment: Occupancy rate for NOI calculation (optional)
        market_adjustments: Market-specific value adjustments (optional)
        uid: Unique identifier
        
    Example:
        ```python
        # Simple direct cap valuation
        valuation = DirectCapValuation(
            name="Market Value",
            cap_rate=0.065
        )
        
        # With occupancy and market adjustments
        valuation = DirectCapValuation(
            name="Stabilized Value",
            cap_rate=0.06,
            occupancy_adjustment=0.95,
            market_adjustments={"location": 1.10, "condition": 0.95}
        )
        ```
    """
    
    # === CORE IDENTITY ===
    name: str = Field(...)
    uid: UUID = Field(default_factory=uuid4)
    kind: Literal["direct_cap"] = Field(default="direct_cap", description="Discriminator field for polymorphic valuation")
    
    # === VALUATION PARAMETERS ===
    cap_rate: PositiveFloat = Field(
        ..., description="Cap rate for property valuation"
    )
    occupancy_adjustment: Optional[PositiveFloat] = Field(
        default=None, description="Occupancy rate for NOI calculation (optional)"
    )
    market_adjustments: Optional[Dict[str, float]] = Field(
        default=None, description="Market-specific value adjustments (optional)"
    )
    
    # === VALIDATION ===
    
    @model_validator(mode="after")
    def validate_cap_parameters(self) -> "DirectCapValuation":
        """Validate direct cap parameters are reasonable."""
        # Validate cap rate
        if not (0.01 <= self.cap_rate <= 0.20):
            raise ValueError(
                f"Cap rate ({self.cap_rate:.1%}) should be between 1% and 20%"
            )
        
        # Validate occupancy if provided
        if self.occupancy_adjustment is not None:
            if not (0.10 <= self.occupancy_adjustment <= 1.00):
                raise ValueError(
                    f"Occupancy adjustment ({self.occupancy_adjustment:.1%}) should be between 10% and 100%"
                )
        
        # Validate market adjustments if provided
        if self.market_adjustments:
            for adjustment_name, factor in self.market_adjustments.items():
                if not (0.10 <= factor <= 3.00):
                    raise ValueError(
                        f"Market adjustment '{adjustment_name}' ({factor:.2f}) should be between 0.10 and 3.00"
                    )
        
        return self
    
    # === COMPUTED PROPERTIES ===
    
    @property
    def combined_market_adjustment(self) -> float:
        """Combined market adjustment factor."""
        if not self.market_adjustments:
            return 1.0
        
        # Multiply all adjustment factors
        adjustment = 1.0
        for factor in self.market_adjustments.values():
            adjustment *= factor
        return adjustment
    
    # === CALCULATION METHODS ===
    
    def calculate_value(
        self,
        first_year_noi: float,
        potential_noi: Optional[float] = None
    ) -> Dict[str, float]:
        """
        Calculate property value using direct capitalization.
        
        Args:
            first_year_noi: First-year NOI for valuation
            potential_noi: Potential NOI at full occupancy (optional)
            
        Returns:
            Dictionary with valuation results
        """
        # Use potential NOI with occupancy adjustment if provided
        effective_noi = first_year_noi
        if potential_noi is not None and self.occupancy_adjustment is not None:
            effective_noi = potential_noi * self.occupancy_adjustment
        
        # Calculate base value using cap rate
        base_value = effective_noi / self.cap_rate
        
        # Apply market adjustments
        adjusted_value = base_value * self.combined_market_adjustment
        
        return {
            "property_value": adjusted_value,
            "base_value": base_value,
            "effective_noi": effective_noi,
            "cap_rate": self.cap_rate,
            "market_adjustment_factor": self.combined_market_adjustment,
            "occupancy_rate": self.occupancy_adjustment or 1.0,
            "implied_yield": effective_noi / adjusted_value if adjusted_value > 0 else 0.0
        }
    
    def calculate_value_per_sf(
        self,
        first_year_noi: float,
        total_area: float,
        potential_noi: Optional[float] = None
    ) -> Dict[str, float]:
        """
        Calculate property value and value per square foot.
        
        Args:
            first_year_noi: First-year NOI for valuation
            total_area: Total property area
            potential_noi: Potential NOI at full occupancy (optional)
            
        Returns:
            Dictionary with valuation results including per-SF metrics
        """
        if total_area <= 0:
            raise ValueError("Total area must be positive")
        
        value_results = self.calculate_value(first_year_noi, potential_noi)
        
        # Add per-SF calculations
        value_results.update({
            "total_area": total_area,
            "value_per_sf": value_results["property_value"] / total_area,
            "noi_per_sf": value_results["effective_noi"] / total_area
        })
        
        return value_results
    
    def calculate_sensitivity_analysis(
        self,
        first_year_noi: float,
        cap_rate_range: tuple[float, float] = (-0.005, 0.005),
        steps: int = 7
    ) -> pd.DataFrame:
        """
        Calculate sensitivity analysis varying cap rates.
        
        Args:
            first_year_noi: First-year NOI for valuation
            cap_rate_range: Range for cap rate variation (min, max)
            steps: Number of steps in the analysis
            
        Returns:
            DataFrame with sensitivity analysis results
        """
        # Generate cap rate variations
        cap_rates = [
            self.cap_rate + i * (cap_rate_range[1] - cap_rate_range[0]) / (steps - 1) 
            for i in range(steps)
        ]
        
        # Calculate values for each cap rate
        results = []
        for cap_rate in cap_rates:
            # Create temporary valuation with varied cap rate
            temp_valuation = self.model_copy(update={"cap_rate": cap_rate})
            
            value_result = temp_valuation.calculate_value(first_year_noi)
            
            results.append({
                "cap_rate": cap_rate,
                "property_value": value_result["property_value"],
                "cap_rate_delta": cap_rate - self.cap_rate,
                "value_change_pct": (value_result["property_value"] / self.calculate_value(first_year_noi)["property_value"] - 1) * 100
            })
        
        return pd.DataFrame(results)
    
    def calculate_metrics(
        self,
        first_year_noi: float,
        acquisition_cost: Optional[float] = None,
        total_area: Optional[float] = None
    ) -> Dict[str, float]:
        """
        Calculate comprehensive direct cap metrics.
        
        Args:
            first_year_noi: First-year NOI for valuation
            acquisition_cost: Acquisition cost for comparison (optional)
            total_area: Total property area for per-SF metrics (optional)
            
        Returns:
            Dictionary of valuation metrics
        """
        if total_area:
            value_results = self.calculate_value_per_sf(first_year_noi, total_area)
        else:
            value_results = self.calculate_value(first_year_noi)
        
        # Add acquisition comparison if provided
        if acquisition_cost is not None:
            value_results.update({
                "acquisition_cost": acquisition_cost,
                "value_premium": value_results["property_value"] - acquisition_cost,
                "value_premium_pct": (value_results["property_value"] / acquisition_cost - 1) * 100 if acquisition_cost > 0 else 0.0,
                "acquisition_cap_rate": first_year_noi / acquisition_cost if acquisition_cost > 0 else 0.0
            })
        
        return value_results
    
    # === FACTORY METHODS ===
    
    @classmethod
    def market_value(
        cls,
        cap_rate: float,
        name: str = "Market Value",
        **kwargs
    ) -> "DirectCapValuation":
        """Factory method for market value assessment."""
        return cls(
            name=name,
            cap_rate=cap_rate,
            **kwargs
        )
    
    @classmethod
    def stabilized_value(
        cls,
        cap_rate: float,
        occupancy_rate: float = 0.95,
        name: str = "Stabilized Value",
        **kwargs
    ) -> "DirectCapValuation":
        """Factory method for stabilized value with occupancy adjustment."""
        return cls(
            name=name,
            cap_rate=cap_rate,
            occupancy_adjustment=occupancy_rate,
            **kwargs
        )
    
    @classmethod
    def conservative(
        cls,
        cap_rate: float = 0.075,
        name: str = "Conservative Value",
        **kwargs
    ) -> "DirectCapValuation":
        """Factory method for conservative valuation assumptions."""
        return cls(
            name=name,
            cap_rate=cap_rate,
            occupancy_adjustment=0.90,  # Conservative occupancy
            **kwargs
        )
    
    @classmethod
    def aggressive(
        cls,
        cap_rate: float = 0.055,
        name: str = "Aggressive Value",
        **kwargs
    ) -> "DirectCapValuation":
        """Factory method for aggressive valuation assumptions."""
        return cls(
            name=name,
            cap_rate=cap_rate,
            occupancy_adjustment=0.98,  # Optimistic occupancy
            **kwargs
        ) 