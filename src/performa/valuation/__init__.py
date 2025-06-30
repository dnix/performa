"""
Performa Valuation Module - Universal Property Valuation

This module provides comprehensive valuation methods that work across all asset types
and development scenarios. Supports multiple valuation approaches common
in real estate analysis with pandas time series integration.

Key Components:
- DCFValuation: Discounted cash flow analysis with terminal value
- DirectCapValuation: Direct capitalization using first-year NOI
- DispositionValuation: Exit valuation via cap rates (existing)
- SalesCompValuation: Comparable sales analysis with statistical methods
- PropertyMetrics: Universal NOI, IRR, yield calculations (existing)

Usage:
    ```python
    # DCF Analysis - Most comprehensive approach
    from performa.valuation import DCFValuation
    
    dcf = DCFValuation(
        name="10-Year DCF",
        discount_rate=0.08,
        terminal_cap_rate=0.065,
        hold_period_years=10
    )
    
    results = dcf.calculate_present_value(
        cash_flows=annual_cash_flows,  # pd.Series
        terminal_noi=stabilized_noi
    )
    
    # Direct Cap - Quick valuation
    from performa.valuation import DirectCapValuation
    
    direct_cap = DirectCapValuation.market_value(cap_rate=0.065)
    value = direct_cap.calculate_value(first_year_noi=500_000)
    
    # Sales Comparison - Market-based approach
    from performa.valuation import SalesCompValuation, SalesComparable
    
    comps = [
        SalesComparable(
            address="123 Main St",
            sale_date="2024-01-15", 
            sale_price=2_500_000,
            property_area=25_000
        )
    ]
    
    sales_comp = SalesCompValuation(
        name="Market Comp Analysis",
        comparables=comps
    )
    
    # Disposition/Exit - For development projects
    from performa.valuation import DispositionValuation
    
    disposition = DispositionValuation.conservative(cap_rate=0.065)
    exit_value = disposition.calculate_net_proceeds(stabilized_noi=600_000)
    
    # Universal Metrics - Works with any approach
    from performa.valuation import PropertyMetrics
    
    metrics = PropertyMetrics.calculate_comprehensive_metrics(
        cash_flows=property_cash_flows,
        initial_investment=total_cost,
        disposition_value=exit_value
    )
    ```

Integration with Development Module:
    ```python
    from performa.development import DevelopmentProject
    from performa.valuation import DCFValuation, DispositionValuation
    
    # Development project with multiple valuation methods
    project = DevelopmentProject(
        property_name="Mixed-Use Development",
        development_program=program,
        construction_plan=construction_plan,
        space_absorption_plan=absorption_plan,
        disposition_valuation=DispositionValuation.conservative(cap_rate=0.065)
    )
    
    # Additional valuation analysis
    dcf_analysis = DCFValuation.aggressive(
        discount_rate=0.075,
        terminal_cap_rate=0.055,
        hold_period_years=7
    )
    ```
"""

from .dcf import DCFValuation
from .direct_cap import DirectCapValuation
from .disposition import DispositionValuation
from .metrics import PropertyMetrics
from .sales_comp import SalesComparable, SalesCompValuation

__all__ = [
    # Core valuation methods
    "DCFValuation",
    "DirectCapValuation", 
    "DispositionValuation",
    "SalesCompValuation",
    "SalesComparable",
    # Universal metrics
    "PropertyMetrics",
] 