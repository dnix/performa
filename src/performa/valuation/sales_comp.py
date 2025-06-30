"""
Universal Sales Comparison Valuation - Comparable Sales Analysis

Universal sales comp valuation that works for any property type:
office, residential, development projects, existing assets, etc.
"""

from __future__ import annotations

from typing import Dict, List, Optional
from uuid import UUID, uuid4

import pandas as pd
from pydantic import Field, model_validator

from ..common.primitives import Model, PositiveFloat


class SalesComparable(Model):
    """
    Individual sales comparable data point.
    
    Represents a single comparable property sale for analysis.
    """
    
    address: str = Field(..., description="Property address or identifier")
    sale_date: str = Field(..., description="Sale date (YYYY-MM-DD format)")
    sale_price: PositiveFloat = Field(..., description="Sale price")
    property_area: PositiveFloat = Field(..., description="Property area (SF or units)")
    cap_rate: Optional[PositiveFloat] = Field(default=None, description="Cap rate at sale")
    noi: Optional[PositiveFloat] = Field(default=None, description="NOI at time of sale")
    adjustments: Optional[Dict[str, float]] = Field(
        default=None, description="Adjustment factors for differences"
    )
    
    @property
    def price_per_sf(self) -> float:
        """Price per square foot."""
        return self.sale_price / self.property_area
    
    @property
    def adjusted_price(self) -> float:
        """Adjusted sale price after applying adjustment factors."""
        if not self.adjustments:
            return self.sale_price
        
        adjustment_factor = 1.0
        for factor in self.adjustments.values():
            adjustment_factor *= factor
        
        return self.sale_price * adjustment_factor
    
    @property
    def adjusted_price_per_sf(self) -> float:
        """Adjusted price per square foot."""
        return self.adjusted_price / self.property_area


class SalesCompValuation(Model):
    """
    Universal sales comparison valuation for any property type.
    
    Provides comparable sales analysis using multiple data points
    and statistical methods to estimate market value.
    
    Attributes:
        name: Human-readable name for the valuation scenario
        comparables: List of comparable sales data
        weighting_method: Method for weighting comparables ("equal", "distance", "similarity")
        outlier_threshold: Standard deviations for outlier detection
        minimum_comparables: Minimum number of comparables required
        uid: Unique identifier
        
    Example:
        ```python
        # Create comparables
        comps = [
            SalesComparable(
                address="123 Main St",
                sale_date="2024-01-15",
                sale_price=2_500_000,
                property_area=25_000,
                cap_rate=0.065
            ),
            SalesComparable(
                address="456 Oak Ave", 
                sale_date="2024-02-20",
                sale_price=3_200_000,
                property_area=30_000,
                cap_rate=0.062
            )
        ]
        
        # Create sales comp valuation
        valuation = SalesCompValuation(
            name="Market Value Analysis",
            comparables=comps,
            weighting_method="equal"
        )
        ```
    """
    
    # === CORE IDENTITY ===
    name: str = Field(...)
    uid: UUID = Field(default_factory=uuid4)
    
    # === VALUATION PARAMETERS ===
    comparables: List[SalesComparable] = Field(
        ..., description="List of comparable sales data"
    )
    weighting_method: str = Field(
        default="equal", description="Method for weighting comparables"
    )
    outlier_threshold: PositiveFloat = Field(
        default=2.0, description="Standard deviations for outlier detection"
    )
    minimum_comparables: int = Field(
        default=3, description="Minimum number of comparables required"
    )
    
    # === VALIDATION ===
    
    @model_validator(mode="after")
    def validate_sales_comp_parameters(self) -> "SalesCompValuation":
        """Validate sales comparison parameters."""
        # Validate minimum comparables
        if len(self.comparables) < self.minimum_comparables:
            raise ValueError(
                f"Need at least {self.minimum_comparables} comparables, got {len(self.comparables)}"
            )
        
        # Validate weighting method
        valid_methods = ["equal", "distance", "similarity"]
        if self.weighting_method not in valid_methods:
            raise ValueError(
                f"Weighting method must be one of {valid_methods}, got '{self.weighting_method}'"
            )
        
        # Validate outlier threshold
        if not (0.5 <= self.outlier_threshold <= 5.0):
            raise ValueError(
                f"Outlier threshold ({self.outlier_threshold}) should be between 0.5 and 5.0"
            )
        
        return self
    
    # === COMPUTED PROPERTIES ===
    
    @property
    def comparable_count(self) -> int:
        """Number of comparables."""
        return len(self.comparables)
    
    @property
    def price_per_sf_data(self) -> List[float]:
        """Price per SF data from all comparables."""
        return [comp.price_per_sf for comp in self.comparables]
    
    @property
    def adjusted_price_per_sf_data(self) -> List[float]:
        """Adjusted price per SF data from all comparables."""
        return [comp.adjusted_price_per_sf for comp in self.comparables]
    
    # === CALCULATION METHODS ===
    
    def calculate_statistics(self, use_adjustments: bool = True) -> Dict[str, float]:
        """
        Calculate statistical measures from comparable sales.
        
        Args:
            use_adjustments: Whether to use adjusted prices
            
        Returns:
            Dictionary of statistical measures
        """
        data = self.adjusted_price_per_sf_data if use_adjustments else self.price_per_sf_data
        
        if not data:
            raise ValueError("No comparable data available")
        
        series = pd.Series(data)
        
        return {
            "mean": series.mean(),
            "median": series.median(),
            "std_dev": series.std(),
            "min": series.min(),
            "max": series.max(),
            "q1": series.quantile(0.25),
            "q3": series.quantile(0.75),
            "coefficient_of_variation": series.std() / series.mean() if series.mean() > 0 else 0.0,
            "sample_size": len(data)
        }
    
    def detect_outliers(self, use_adjustments: bool = True) -> List[int]:
        """
        Detect outliers using standard deviation method.
        
        Args:
            use_adjustments: Whether to use adjusted prices
            
        Returns:
            List of indices of outlier comparables
        """
        data = self.adjusted_price_per_sf_data if use_adjustments else self.price_per_sf_data
        series = pd.Series(data)
        
        mean = series.mean()
        std_dev = series.std()
        
        outliers = []
        for i, value in enumerate(data):
            if abs(value - mean) > (self.outlier_threshold * std_dev):
                outliers.append(i)
        
        return outliers
    
    def calculate_value(
        self,
        subject_area: float,
        exclude_outliers: bool = True,
        use_adjustments: bool = True
    ) -> Dict[str, float]:
        """
        Calculate property value using sales comparison approach.
        
        Args:
            subject_area: Area of subject property
            exclude_outliers: Whether to exclude outlier comparables
            use_adjustments: Whether to use adjusted prices
            
        Returns:
            Dictionary with valuation results
        """
        if subject_area <= 0:
            raise ValueError("Subject area must be positive")
        
        # Get price per SF data
        data = self.adjusted_price_per_sf_data if use_adjustments else self.price_per_sf_data
        
        # Exclude outliers if requested
        if exclude_outliers:
            outlier_indices = self.detect_outliers(use_adjustments)
            data = [price for i, price in enumerate(data) if i not in outlier_indices]
        
        if not data:
            raise ValueError("No valid comparables after outlier removal")
        
        # Calculate weighted average based on method
        if self.weighting_method == "equal":
            weighted_price_per_sf = sum(data) / len(data)
        else:
            # For now, default to equal weighting for other methods
            # TODO: Implement distance and similarity weighting
            weighted_price_per_sf = sum(data) / len(data)
        
        # Calculate property value
        property_value = weighted_price_per_sf * subject_area
        
        # Calculate statistics
        stats = self.calculate_statistics(use_adjustments)
        
        return {
            "property_value": property_value,
            "indicated_price_per_sf": weighted_price_per_sf,
            "subject_area": subject_area,
            "comparables_used": len(data),
            "comparables_excluded": len(self.comparables) - len(data),
            "price_per_sf_range": f"${stats['min']:.2f} - ${stats['max']:.2f}",
            "price_per_sf_median": stats["median"],
            "price_per_sf_std_dev": stats["std_dev"],
            "coefficient_of_variation": stats["coefficient_of_variation"]
        }
    
    def calculate_value_range(
        self,
        subject_area: float,
        confidence_level: float = 0.95
    ) -> Dict[str, float]:
        """
        Calculate value range using confidence intervals.
        
        Args:
            subject_area: Area of subject property
            confidence_level: Confidence level for range calculation
            
        Returns:
            Dictionary with value range results
        """
        stats = self.calculate_statistics(use_adjustments=True)
        mean_price_per_sf = stats["mean"]
        std_dev = stats["std_dev"]
        sample_size = stats["sample_size"]
        
        # Calculate confidence interval
        # Using t-distribution for small samples
        from scipy import stats as scipy_stats
        t_value = scipy_stats.t.ppf((1 + confidence_level) / 2, sample_size - 1)
        margin_of_error = t_value * (std_dev / (sample_size ** 0.5))
        
        low_price_per_sf = mean_price_per_sf - margin_of_error
        high_price_per_sf = mean_price_per_sf + margin_of_error
        
        return {
            "mean_value": mean_price_per_sf * subject_area,
            "low_value": low_price_per_sf * subject_area,
            "high_value": high_price_per_sf * subject_area,
            "confidence_level": confidence_level,
            "margin_of_error_per_sf": margin_of_error,
            "range_pct": (margin_of_error / mean_price_per_sf * 100) if mean_price_per_sf > 0 else 0.0
        }
    
    def generate_comp_analysis_report(self) -> pd.DataFrame:
        """
        Generate a comprehensive comparable analysis report.
        
        Returns:
            DataFrame with detailed comparable analysis
        """
        outliers = self.detect_outliers(use_adjustments=True)
        
        report_data = []
        for i, comp in enumerate(self.comparables):
            report_data.append({
                "Address": comp.address,
                "Sale_Date": comp.sale_date,
                "Sale_Price": comp.sale_price,
                "Area": comp.property_area,
                "Price_Per_SF": comp.price_per_sf,
                "Adjusted_Price": comp.adjusted_price,
                "Adjusted_Price_Per_SF": comp.adjusted_price_per_sf,
                "Cap_Rate": comp.cap_rate,
                "NOI": comp.noi,
                "Is_Outlier": i in outliers
            })
        
        return pd.DataFrame(report_data)
    
    # === FACTORY METHODS ===
    
    @classmethod
    def create_from_data(
        cls,
        name: str,
        sales_data: List[Dict],
        **kwargs
    ) -> "SalesCompValuation":
        """
        Factory method to create from raw sales data.
        
        Args:
            name: Name for the valuation
            sales_data: List of dictionaries with sales data
            
        Returns:
            SalesCompValuation instance
        """
        comparables = [SalesComparable(**data) for data in sales_data]
        
        return cls(
            name=name,
            comparables=comparables,
            **kwargs
        ) 