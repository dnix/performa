"""
Partnership Distribution Calculator

This module implements the equity waterfall distribution logic using the partner models.
It calculates how equity returns are distributed among partners based on their ownership
structure and any promote/waterfall agreements.
"""

import math
from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
from pyxirr import xirr

from ..core.primitives import Timeline
from .partners import Partner, PartnershipStructure

# Constants for numerical precision
BINARY_SEARCH_ITERATIONS = 30  # Iterations for binary search precision

@dataclass
class DistributionCalculator:
    """
    Calculates equity distributions for partnerships based on cash flows and waterfall logic.
    
    This class implements the distribution algorithms that determine how equity returns
    are allocated among partners based on their ownership structure and any promote agreements.
    
    Attributes:
        partnership: The partnership structure defining partners and distribution method
    """
    partnership: PartnershipStructure
    
    def _calculate_partner_metrics(
        self, 
        partner_cash_flows: Dict[str, pd.Series],
        total_cash_flows: pd.Series
    ) -> Dict[str, Any]:
        """
        Calculate metrics for each partner and total deal.
        
        Args:
            partner_cash_flows: Dictionary of partner name to cash flow series
            total_cash_flows: Total deal cash flows
            
        Returns:
            Dictionary containing partner metrics and total deal metrics
        """
        # Calculate metrics for each partner
        partner_metrics = {}
        for partner in self.partnership.partners:
            partner_cf = partner_cash_flows[partner.name]
            
            # Calculate basic metrics
            total_investment = abs(partner_cf[partner_cf < 0].sum())
            total_distributions = partner_cf[partner_cf > 0].sum()
            net_profit = partner_cf.sum()
            
            # Calculate equity multiple
            equity_multiple = total_distributions / total_investment if total_investment > 0 else 0.0
            
            # Calculate IRR
            irr = None
            if len(partner_cf) > 1 and total_investment > 0:
                try:
                    # Create dates for IRR calculation
                    dates = [period.to_timestamp().date() for period in partner_cf.index]
                    irr = xirr(dates, partner_cf.values)
                    if irr is not None:
                        irr = float(irr)
                except (ValueError, ZeroDivisionError, Exception):
                    # Skip IRR calculation if it fails (e.g., only negative or positive flows)
                    pass
            
            partner_metrics[partner.name] = {
                "partner_info": partner,
                "cash_flows": partner_cf,
                "total_investment": total_investment,
                "total_distributions": total_distributions,
                "net_profit": net_profit,
                "equity_multiple": equity_multiple,
                "irr": irr,
                "ownership_percentage": partner.share
            }
        
        # Calculate total deal metrics
        total_investment = abs(total_cash_flows[total_cash_flows < 0].sum())
        total_distributions = total_cash_flows[total_cash_flows > 0].sum()
        net_profit = total_cash_flows.sum()
        
        total_equity_multiple = total_distributions / total_investment if total_investment > 0 else 0.0
        
        # Calculate total IRR
        total_irr = None
        if len(total_cash_flows) > 1 and total_investment > 0:
            try:
                dates = [period.to_timestamp().date() for period in total_cash_flows.index]
                total_irr = xirr(dates, total_cash_flows.values)
                if total_irr is not None:
                    total_irr = float(total_irr)
            except (ValueError, ZeroDivisionError, Exception):
                # Skip IRR calculation if it fails (e.g., only negative or positive flows)
                pass
        
        return {
            "partner_distributions": partner_metrics,
            "total_metrics": {
                "total_investment": total_investment,
                "total_distributions": total_distributions,
                "net_profit": net_profit,
                "equity_multiple": total_equity_multiple,
                "irr": total_irr
            }
        }
    
    def calculate_pari_passu_distribution(
        self, 
        cash_flows: pd.Series, 
        timeline: Timeline
    ) -> Dict[str, Any]:
        """
        Calculate pari passu (proportional) distribution of cash flows.
        
        In pari passu distribution:
        - All partners contribute equity proportionally to their ownership percentage
        - All partners receive distributions proportionally to their ownership percentage
        - No preferred returns or promotes are applied
        
        Args:
            cash_flows: Series of levered cash flows (negative = investment, positive = returns)
            timeline: Analysis timeline for cash flow indexing
            
        Returns:
            Dictionary containing distribution results for each partner
        """
        # Initialize partner cash flows
        partner_cash_flows = {}
        partner_names = [p.name for p in self.partnership.partners]
        
        # Create cash flow series for each partner
        for partner in self.partnership.partners:
            partner_cash_flows[partner.name] = pd.Series(0.0, index=timeline.period_index)
        
        # Distribute cash flows proportionally based on partner shares
        for period in timeline.period_index:
            period_cash_flow = cash_flows[period]
            
            # Distribute positive and negative cash flows proportionally
            for partner in self.partnership.partners:
                partner_cash_flows[partner.name][period] = period_cash_flow * partner.share
        
        # Calculate metrics for each partner
        partner_metrics = self._calculate_partner_metrics(partner_cash_flows, cash_flows)
        
        return {
            "distribution_method": "pari_passu",
            "partner_distributions": partner_metrics["partner_distributions"],
            "total_metrics": partner_metrics["total_metrics"],
            "partnership_summary": {
                "partner_count": self.partnership.partner_count,
                "gp_total_share": self.partnership.gp_total_share,
                "lp_total_share": self.partnership.lp_total_share,
                "gp_count": len(self.partnership.gp_partners),
                "lp_count": len(self.partnership.lp_partners)
            }
        }
    
    def calculate_waterfall_distribution(
        self, 
        cash_flows: pd.Series, 
        timeline: Timeline
    ) -> Dict[str, Any]:
        """
        Calculate waterfall distribution with sophisticated IRR-based promote logic.
        
        This method implements the complex waterfall algorithm that:
        1. Tracks running IRR for each partner throughout the distribution period
        2. Applies promote rates based on IRR hurdles
        3. Uses binary search to find exact tier transition points
        4. Allocates promote to GP partners only
        
        Args:
            cash_flows: Series of levered cash flows
            timeline: Analysis timeline
            
        Returns:
            Dictionary containing waterfall distribution results
        """
        if not self.partnership.has_promote:
            raise ValueError("Waterfall distribution requires a promote structure")
        
        # Get promote structure and tiers
        promote = self.partnership.promote
        tiers, final_promote_rate = promote.all_tiers
        
        # Set up partner data
        periods = cash_flows.index
        partner_names = [p.name for p in self.partnership.partners]
        n_periods = len(periods)
        n_partners = len(self.partnership.partners)
        
        # Precompute partner arrays for vectorized operations
        partner_shares = np.array([p.share for p in self.partnership.partners])
        gp_mask = np.array([p.kind == "GP" for p in self.partnership.partners])
        gp_shares_total = partner_shares[gp_mask].sum()
        
        # Validate that we have GP partners for waterfall distribution
        if gp_shares_total == 0:
            raise ValueError("Waterfall distribution requires at least one GP partner")
        
        # Initialize partner cash flows matrix
        partner_flows = np.zeros((n_periods, n_partners))
        
        # Track current tier
        current_tier_index = 0
        
        # Pre-extract dates for IRR calculation
        date_array = periods.to_timestamp().to_pydatetime()
        
        def current_irr(flows: np.ndarray, up_to_idx: int) -> Optional[float]:
            """Calculate current IRR for all partners up to a given period."""
            cf = flows[:up_to_idx+1].sum(axis=1)
            # Need both negative and positive flows for IRR to be meaningful
            if not (np.any(cf < 0) and np.any(cf > 0)):
                return None
            s = pd.Series(cf, index=date_array[:up_to_idx+1])
            try:
                return xirr(s)
            except:
                return None
        
        def allocate_cf_at_rate(cf_amount: float, promote_rate: float) -> np.ndarray:
            """
            Allocate cash flow at a given promote rate.
            
            Args:
                cf_amount: Cash flow amount to allocate
                promote_rate: Promote rate (0.0 to 1.0)
                
            Returns:
                Array of cash flows per partner
            """
            # Base distribution to all partners based on their shares
            base_dist = cf_amount * partner_shares * (1 - promote_rate)
            
            # Promote amount goes to GP partners only, pro-rata by their GP shares
            promote_amount = cf_amount * promote_rate
            base_dist[gp_mask] += promote_amount * (partner_shares[gp_mask] / gp_shares_total)
            
            return base_dist
        
        def test_allocation(flows: np.ndarray, period_idx: int, cf_amount: float, promote_rate: float) -> float:
            """
            Test what IRR would be if we allocate entire cf_amount at given promote rate.
            
            Args:
                flows: Current partner flows matrix
                period_idx: Current period index
                cf_amount: Cash flow amount to test
                promote_rate: Promote rate to test
                
            Returns:
                Resulting IRR (or -inf if can't calculate)
            """
            test_flows = flows.copy()
            dist_array = allocate_cf_at_rate(cf_amount, promote_rate)
            test_flows[period_idx, :] += dist_array
            irr = current_irr(test_flows, period_idx)
            return irr if irr is not None else float('-inf')
        
        def solve_for_x(flows: np.ndarray, period_idx: int, cf_amount: float, promote_rate: float, hurdle_rate: float) -> float:
            """
            Binary search to find exact amount to allocate to hit hurdle rate.
            
            Args:
                flows: Current partner flows matrix
                period_idx: Current period index
                cf_amount: Total cash flow amount available
                promote_rate: Promote rate for this tier
                hurdle_rate: Target hurdle rate
                
            Returns:
                Exact amount to allocate to hit hurdle rate
            """
            low, high = 0.0, cf_amount
            
            # Binary search with defined iterations for precision
            for _ in range(BINARY_SEARCH_ITERATIONS):
                mid = (low + high) / 2
                test_flows = flows.copy()
                dist_array = allocate_cf_at_rate(mid, promote_rate)
                test_flows[period_idx, :] += dist_array
                irr_val = current_irr(test_flows, period_idx)
                
                if irr_val is None or irr_val < hurdle_rate:
                    low = mid
                else:
                    high = mid
            
            return (low + high) / 2
        
        # Process each period
        for period_idx, period in enumerate(periods):
            cf_value = cash_flows.iloc[period_idx]
            
            if cf_value < 0:
                # Negative cash flow: equity contribution distributed pro-rata
                partner_flows[period_idx, :] += cf_value * partner_shares
            elif cf_value > 0:
                # Positive cash flow: apply waterfall logic
                remaining_cf = cf_value
                
                while remaining_cf > 0.01:  # Continue until all cash flow is allocated (to nearest cent)
                    # Determine current tier promote rate
                    if current_tier_index < len(tiers):
                        hurdle_rate, promote_rate = tiers[current_tier_index]
                    else:
                        # Above all tiers, use final promote rate
                        hurdle_rate = np.inf
                        promote_rate = final_promote_rate
                    
                    # Test if allocating all remaining CF would exceed hurdle
                    test_irr_val = test_allocation(partner_flows, period_idx, remaining_cf, promote_rate)
                    
                    if test_irr_val < hurdle_rate:
                        # Allocate all remaining CF at this tier
                        partner_flows[period_idx, :] += allocate_cf_at_rate(remaining_cf, promote_rate)
                        remaining_cf = 0.0
                    else:
                        # Exceeds hurdle - allocate partial amount to hit hurdle exactly
                        x = solve_for_x(partner_flows, period_idx, remaining_cf, promote_rate, hurdle_rate)
                        partner_flows[period_idx, :] += allocate_cf_at_rate(x, promote_rate)
                        remaining_cf -= x
                        # Move to next tier
                        current_tier_index += 1
        
        # Convert to DataFrame
        distribution_df = pd.DataFrame(partner_flows, index=periods, columns=partner_names)
        
        # Calculate metrics for each partner
        partner_metrics = self._calculate_partner_metrics(distribution_df, cash_flows)
        
        return {
            "distribution_method": "waterfall",
            "partner_distributions": partner_metrics["partner_distributions"],
            "total_metrics": partner_metrics["total_metrics"],
            "partnership_summary": {
                "partner_count": self.partnership.partner_count,
                "gp_total_share": self.partnership.gp_total_share,
                "lp_total_share": self.partnership.lp_total_share,
                "gp_count": len(self.partnership.gp_partners),
                "lp_count": len(self.partnership.lp_partners)
            },
            "waterfall_details": {
                "promote_structure": type(promote).__name__,
                "tiers_used": tiers,
                "final_promote_rate": final_promote_rate,
                "distribution_matrix": distribution_df
            }
        }
    
    def calculate_distributions(
        self, 
        cash_flows: pd.Series, 
        timeline: Timeline
    ) -> Dict[str, Any]:
        """
        Calculate distributions based on the partnership structure.
        
        This is the main entry point that determines which distribution method to use
        based on the partnership configuration.
        
        Args:
            cash_flows: Series of levered cash flows
            timeline: Analysis timeline
            
        Returns:
            Distribution results dictionary
        """
        if self.partnership.distribution_method == "pari_passu":
            return self.calculate_pari_passu_distribution(cash_flows, timeline)
        elif self.partnership.distribution_method == "waterfall":
            return self.calculate_waterfall_distribution(cash_flows, timeline)
        else:
            raise ValueError(f"Unknown distribution method: {self.partnership.distribution_method}")
    
    def create_partner_summary_dataframe(self, distribution_results: Dict[str, Any]) -> pd.DataFrame:
        """
        Create a summary DataFrame showing partner returns and metrics.
        
        Args:
            distribution_results: Results from calculate_distributions
            
        Returns:
            DataFrame with partner summary information
        """
        partner_data = []
        
        for partner_name, metrics in distribution_results["partner_distributions"].items():
            partner_info = metrics["partner_info"]
            
            partner_data.append({
                "Partner": partner_name,
                "Type": partner_info.kind,
                "Ownership": f"{partner_info.share:.1%}",
                "Investment": f"${metrics['total_investment']:,.0f}",
                "Distributions": f"${metrics['total_distributions']:,.0f}",
                "Net Profit": f"${metrics['net_profit']:,.0f}",
                "Equity Multiple": f"{metrics['equity_multiple']:.2f}x",
                "IRR": f"{metrics['irr']:.1%}" if metrics['irr'] is not None else "N/A"
            })
        
        # Add total row
        total_metrics = distribution_results["total_metrics"]
        partner_data.append({
            "Partner": "TOTAL",
            "Type": "ALL",
            "Ownership": "100.0%",
            "Investment": f"${total_metrics['total_investment']:,.0f}",
            "Distributions": f"${total_metrics['total_distributions']:,.0f}",
            "Net Profit": f"${total_metrics['net_profit']:,.0f}",
            "Equity Multiple": f"{total_metrics['equity_multiple']:.2f}x",
            "IRR": f"{total_metrics['irr']:.1%}" if total_metrics['irr'] is not None else "N/A"
        })
        
        return pd.DataFrame(partner_data)


def calculate_partner_distributions_with_structure(
    partnership: PartnershipStructure,
    cash_flows: pd.Series,
    timeline: Timeline
) -> Dict[str, Any]:
    """
    Convenience function to calculate partner distributions with a partnership structure.
    
    Args:
        partnership: Partnership structure
        cash_flows: Levered cash flows
        timeline: Analysis timeline
        
    Returns:
        Distribution results
    """
    calculator = DistributionCalculator(partnership)
    return calculator.calculate_distributions(cash_flows, timeline)


def create_simple_partnership(
    gp_name: str,
    gp_share: float,
    lp_name: str,
    lp_share: float,
    distribution_method: str = "pari_passu"
) -> PartnershipStructure:
    """
    Helper function to create a simple 2-partner structure.
    
    Args:
        gp_name: General Partner name
        gp_share: GP ownership percentage (0.0 to 1.0)
        lp_name: Limited Partner name
        lp_share: LP ownership percentage (0.0 to 1.0)
        distribution_method: Distribution method ("pari_passu" or "waterfall")
        
    Returns:
        PartnershipStructure object
    """
    gp = Partner(name=gp_name, kind="GP", share=gp_share)
    lp = Partner(name=lp_name, kind="LP", share=lp_share)
    
    return PartnershipStructure(
        partners=[gp, lp],
        distribution_method=distribution_method
    ) 