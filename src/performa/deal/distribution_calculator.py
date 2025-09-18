# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Partnership Distribution Calculator

This module implements the European-style equity waterfall distribution logic using the partner models.
It calculates how equity returns are distributed among partners based on their ownership
structure and any promote/waterfall agreements.
"""

from dataclasses import dataclass
from typing import Any, Dict

import numpy as np
import pandas as pd

from ..core.calculations import FinancialCalculations
from ..core.primitives import Timeline
from .partnership import PartnershipStructure


@dataclass
class DistributionCalculator:
    """
    Calculates equity distributions using European-style waterfall logic.

    This class implements the distribution algorithms that determine how equity returns
    are allocated among partners based on their ownership structure and any promote agreements.

    Attributes:
        partnership: The partnership structure defining partners and distribution method
    """

    partnership: PartnershipStructure

    def _calculate_partner_metrics(
        self, partner_cash_flows: Dict[str, pd.Series], total_cash_flows: pd.Series
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
            equity_multiple = (
                total_distributions / total_investment if total_investment > 0 else 0.0
            )

            # Calculate IRR using LedgerQueries single-source calculation
            irr = FinancialCalculations.calculate_irr(partner_cf)

            partner_metrics[partner.name] = {
                "partner_info": partner,
                "cash_flows": partner_cf,
                "total_investment": total_investment,
                "total_distributions": total_distributions,
                "net_profit": net_profit,
                "equity_multiple": equity_multiple,
                "irr": irr,
                "ownership_percentage": partner.share,
            }

        # Calculate total deal metrics
        total_investment = abs(total_cash_flows[total_cash_flows < 0].sum())
        total_distributions = total_cash_flows[total_cash_flows > 0].sum()
        net_profit = total_cash_flows.sum()

        total_equity_multiple = (
            total_distributions / total_investment if total_investment > 0 else 0.0
        )

        # Calculate total IRR using LedgerQueries single-source calculation
        total_irr = FinancialCalculations.calculate_irr(total_cash_flows)

        return {
            "partner_distributions": partner_metrics,
            "total_metrics": {
                "total_investment": total_investment,
                "total_distributions": total_distributions,
                "net_profit": net_profit,
                "equity_multiple": total_equity_multiple,
                "irr": total_irr,
            },
        }

    def calculate_pari_passu_distribution(
        self, cash_flows: pd.Series, timeline: Timeline
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
            Dictionary with same structure as waterfall distribution but simpler logic:

            {
                "distribution_method": str,  # "pari_passu"
                "partner_distributions": {
                    "<partner_name>": {
                        "partner_info": Partner,              # Partner object
                        "cash_flows": pd.Series,              # Partner's period cash flows
                        "total_investment": float,            # Partner's proportional investment
                        "total_distributions": float,         # Partner's proportional distributions
                        "net_profit": float,                  # Partner's proportional profit
                        "equity_multiple": float,             # Distributions / Investment
                        "irr": float,                         # Partner's IRR (same for all)
                        "ownership_percentage": float         # Partner's ownership share
                    }
                },
                "total_metrics": {...},     # Same as waterfall
                "partnership_summary": {...} # Same as waterfall
            }

            Note: In pari passu, all partners have the same IRR and equity multiple.

            Example access:
                results = calc.calculate_pari_passu_distribution(cash_flows, timeline)
                lp_distributions = results["partner_distributions"]["LP"]["total_distributions"]
        """
        # Initialize partner cash flows
        partner_cash_flows = {}
        partner_names = [p.name for p in self.partnership.partners]

        # Create cash flow series for each partner
        for partner in self.partnership.partners:
            partner_cash_flows[partner.name] = pd.Series(
                0.0, index=timeline.period_index
            )

        # Distribute cash flows proportionally based on partner shares
        for period in timeline.period_index:
            period_cash_flow = cash_flows[period]

            # Distribute positive and negative cash flows proportionally
            for partner in self.partnership.partners:
                partner_cash_flows[partner.name][period] = (
                    period_cash_flow * partner.share
                )

        # Calculate metrics for each partner
        partner_metrics = self._calculate_partner_metrics(
            partner_cash_flows, cash_flows
        )

        return {
            "distribution_method": "pari_passu",
            "partner_distributions": partner_metrics["partner_distributions"],
            "total_metrics": partner_metrics["total_metrics"],
            "partnership_summary": {
                "partner_count": self.partnership.partner_count,
                "gp_total_share": self.partnership.gp_total_share,
                "lp_total_share": self.partnership.lp_total_share,
                "gp_count": len(self.partnership.gp_partners),
                "lp_count": len(self.partnership.lp_partners),
            },
        }

    def calculate_waterfall_distribution(
        self, cash_flows: pd.Series, timeline: Timeline
    ) -> Dict[str, Any]:
        """
        Calculate waterfall distribution using European-style logic.

        This method implements a proper European waterfall where:
        1. All partners (including GPs) receive preferred return first (if IRR-based)
        2. Promote is applied tier-by-tier based on achieving hurdles (IRR or EM)
        3. Each tier's incremental profit is distributed with that tier's promote rate
        4. GPs receive promote on top of their pro-rata share
        
        Supports IRR, EM, and hybrid waterfall structures

        Args:
            cash_flows: Series of levered cash flows
            timeline: Analysis timeline

        Returns:
            Dictionary with detailed distribution results containing:

            {
                "distribution_method": str,  # "waterfall"
                "partner_distributions": {
                    "<partner_name>": {
                        "partner_info": Partner,              # Partner object
                        "cash_flows": pd.Series,              # Partner's period cash flows
                        "total_investment": float,            # Partner's total investment
                        "total_distributions": float,         # Partner's total distributions
                        "net_profit": float,                  # Partner's net profit
                        "equity_multiple": float,             # Distributions / Investment
                        "irr": float,                         # Partner's IRR (decimal)
                        "ownership_percentage": float,        # Partner's ownership share
                        "promote_distributions": float        # Promote received (GP only)
                    }
                },
                "total_metrics": {
                    "total_investment": float,                # All partners' investment
                    "total_distributions": float,             # All partners' distributions
                    "net_profit": float,                      # Total profit
                    "equity_multiple": float,                 # Overall equity multiple
                    "irr": float                              # Blended IRR
                },
                "partnership_summary": {
                    "partner_count": int,                     # Number of partners
                    "gp_total_share": float,                  # Total GP ownership
                    "lp_total_share": float,                  # Total LP ownership
                    "gp_count": int,                          # Number of GPs
                    "lp_count": int                           # Number of LPs
                }
            }

            Example access:
                results = calc.calculate_waterfall_distribution(cash_flows, timeline)
                lp_irr = results["partner_distributions"]["LP"]["irr"]
                total_profit = results["total_metrics"]["net_profit"]
        """
        if not self.partnership.has_promote:
            raise ValueError("Waterfall distribution requires a promote structure")

        # Get promote structure
        promote = self.partnership.promote
        
        # Import types for checking
        from ..deal.partnership import (
            CarryPromote,
            EMWaterfallPromote,
            HybridWaterfallPromote,
            IRRWaterfallPromote,
        )
        
        # Dispatch to appropriate waterfall calculation based on promote type
        # Note: WaterfallPromote is an alias for IRRWaterfallPromote, so it's handled by the first case
        if isinstance(promote, IRRWaterfallPromote):
            return self._calculate_irr_waterfall(cash_flows, timeline, promote)
        elif isinstance(promote, EMWaterfallPromote):
            return self._calculate_em_waterfall(cash_flows, timeline, promote)
        elif isinstance(promote, HybridWaterfallPromote):
            return self._calculate_hybrid_waterfall(cash_flows, timeline, promote)
        elif isinstance(promote, CarryPromote):
            # CarryPromote uses specialized traditional carry calculation
            return self._calculate_carry_promote(cash_flows, timeline, promote)
        else:
            raise ValueError(f"Unknown promote type: {type(promote).__name__}")
    
    def _calculate_irr_waterfall(
        self, cash_flows: pd.Series, timeline: Timeline, promote
    ) -> Dict[str, Any]:
        """Calculate IRR-based waterfall distribution."""
        # Get tiers from promote
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
        
        # Separate investments and distributions
        investments = cash_flows[cash_flows < 0]
        distributions = cash_flows[cash_flows > 0]
        
        # Total investment amount (as positive number)
        total_investment = abs(investments.sum())
        
        # Allocate investments pro-rata by ownership
        for period_idx, cf in enumerate(cash_flows):
            if cf < 0:
                # Investment - allocate by ownership share
                partner_flows[period_idx, :] = cf * partner_shares
        
        def calculate_distribution_for_irr_hurdle(target_irr: float) -> float:
            """
            Calculate the total distribution amount needed to achieve a target IRR.
            
            For European waterfall, we need to find what total distribution amount
            would result in the target IRR given the investment pattern.
            
            Args:
                target_irr: Target IRR hurdle (e.g., 0.08 for 8%)
                
            Returns:
                Total distribution amount needed to achieve target IRR
            """
            # For simple case of single investment at start and single distribution at end
            # Future Value = Present Value * (1 + IRR)^years
            
            # Get investment timing - use the investment-weighted average time
            investment_times = []
            investment_amounts = []
            
            for idx, cf in enumerate(cash_flows):
                if cf < 0:
                    # This is an investment
                    investment_times.append(idx)
                    investment_amounts.append(abs(cf))
            
            if not investment_amounts:
                return 0.0
                
            # Calculate time from investment to final distribution
            final_period = len(cash_flows) - 1
            
            # For each investment, calculate future value at target IRR
            total_fv = 0.0
            for inv_time, inv_amount in zip(investment_times, investment_amounts):
                # Time in years from investment to distribution
                years = (final_period - inv_time) / 12.0  # Convert months to years
                # Future value = PV * (1 + r)^t
                fv = inv_amount * (1 + target_irr) ** years
                total_fv += fv
            
            return total_fv

        # Calculate actual total distribution amount
        total_distributions = distributions.sum()
        
        # Calculate distribution amounts for each tier
        tier_amounts = []
        
        # First, return of capital (always pro-rata, no promote)
        tier_amounts.append((total_investment, 0.0, "Return of Capital"))
        
        # Then calculate amounts for each IRR tier
        for i, (hurdle_rate, promote_rate) in enumerate(tiers):
            if hurdle_rate == np.inf:
                # Final tier - takes all remaining
                tier_amounts.append((float('inf'), promote_rate, f"Final Tier"))
            else:
                # Calculate distribution needed for this hurdle
                required_dist = calculate_distribution_for_irr_hurdle(hurdle_rate)
                tier_amounts.append((required_dist, promote_rate, f"Tier {hurdle_rate:.1%}"))
        
        # Add final tier for distributions above all tiers (if final promote rate > 0)
        if final_promote_rate > 0:
            tier_amounts.append((float('inf'), final_promote_rate, "Final Tier"))
        # Now distribute each positive cash flow through the tiers
        cumulative_distributed = 0.0
        current_tier_idx = 0
        
        for period_idx, cf in enumerate(cash_flows):
            if cf <= 0:
                continue  # Skip investments, already allocated
            
            # Distribute this period's cash flow through tiers
            remaining_cf = cf
            
            while remaining_cf > 0 and current_tier_idx < len(tier_amounts):
                tier_threshold, promote_rate, tier_name = tier_amounts[current_tier_idx]
                
                # How much room left in this tier?
                if current_tier_idx == len(tier_amounts) - 1:
                    # Last tier - infinite capacity
                    tier_capacity = remaining_cf
                else:
                    tier_capacity = max(0, tier_threshold - cumulative_distributed)
                
                # Amount to distribute in this tier
                tier_amount = min(remaining_cf, tier_capacity)
                
                if tier_amount <= 0:
                    current_tier_idx += 1
                    continue
                
                # Allocate this tier's distributions
                # Base amount distributed pro-rata
                base_distribution = tier_amount * (1 - promote_rate)
                base_per_partner = base_distribution * partner_shares
                
                # Promote amount to GPs only
                promote_distribution = tier_amount * promote_rate
                promote_per_gp = np.zeros(n_partners)
                if gp_shares_total > 0:
                    promote_per_gp[gp_mask] = promote_distribution * (partner_shares[gp_mask] / gp_shares_total)
                
                # Add to partner flows for this period
                partner_flows[period_idx, :] += base_per_partner + promote_per_gp
                
                cumulative_distributed += tier_amount
                remaining_cf -= tier_amount
                
                # Move to next tier if this one is full
                if cumulative_distributed >= tier_threshold and current_tier_idx < len(tier_amounts) - 1:
                    current_tier_idx += 1


        # Convert to DataFrame
        distribution_df = pd.DataFrame(
            partner_flows, index=periods, columns=partner_names
        )

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
                "lp_count": len(self.partnership.lp_partners),
            },
            "waterfall_details": {
                "promote_structure": type(promote).__name__,
                "tiers_used": tiers,
                "final_promote_rate": final_promote_rate,
                "distribution_matrix": distribution_df,
            },
        }
    
    def _calculate_em_waterfall(
        self, cash_flows: pd.Series, timeline: Timeline, promote
    ) -> Dict[str, Any]:
        """
        Calculate Equity Multiple-based waterfall distribution.
        
        Much simpler than IRR - just threshold-based distribution.
        """
        # Get tiers from promote
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
        
        # Separate investments and distributions
        investments = cash_flows[cash_flows < 0]
        distributions = cash_flows[cash_flows > 0]
        
        # Total investment amount (as positive number)
        total_investment = abs(investments.sum())
        
        # Allocate investments pro-rata by ownership
        for period_idx, cf in enumerate(cash_flows):
            if cf < 0:
                # Investment - allocate by ownership share
                partner_flows[period_idx, :] = cf * partner_shares
        
        # Calculate tier thresholds based on equity multiples
        tier_amounts = []
        for em_hurdle, promote_rate in tiers:
            # Each EM tier is simply investment * multiple
            threshold = total_investment * em_hurdle
            tier_amounts.append((threshold, promote_rate, f"Tier {em_hurdle:.1f}x"))
        
        # Add final tier for distributions above all tiers
        tier_amounts.append((float('inf'), final_promote_rate, "Final Tier"))
        
        # Distribute each positive cash flow through the tiers
        cumulative_distributed = 0.0
        current_tier_idx = 0
        
        for period_idx, cf in enumerate(cash_flows):
            if cf <= 0:
                continue  # Skip investments, already allocated
            
            # Distribute this period's cash flow through tiers
            remaining_cf = cf
            
            while remaining_cf > 0 and current_tier_idx < len(tier_amounts):
                tier_threshold, promote_rate, tier_name = tier_amounts[current_tier_idx]
                
                # How much room left in this tier?
                if current_tier_idx == len(tier_amounts) - 1:
                    # Last tier - infinite capacity
                    tier_capacity = remaining_cf
                else:
                    tier_capacity = max(0, tier_threshold - cumulative_distributed)
                
                # Amount to distribute in this tier
                tier_amount = min(remaining_cf, tier_capacity)
                
                if tier_amount <= 0:
                    current_tier_idx += 1
                    continue
                
                # Allocate this tier's distributions
                # Base amount distributed pro-rata
                base_distribution = tier_amount * (1 - promote_rate)
                base_per_partner = base_distribution * partner_shares
                
                # Promote amount to GPs only
                promote_distribution = tier_amount * promote_rate
                promote_per_gp = np.zeros(n_partners)
                if gp_shares_total > 0:
                    promote_per_gp[gp_mask] = promote_distribution * (partner_shares[gp_mask] / gp_shares_total)
                
                # Add to partner flows for this period
                partner_flows[period_idx, :] += base_per_partner + promote_per_gp
                
                cumulative_distributed += tier_amount
                remaining_cf -= tier_amount
                
                # Move to next tier if this one is full
                if cumulative_distributed >= tier_threshold and current_tier_idx < len(tier_amounts) - 1:
                    current_tier_idx += 1
        
        # Convert to DataFrame
        distribution_df = pd.DataFrame(
            partner_flows, index=periods, columns=partner_names
        )

        # Calculate metrics for each partner
        partner_metrics = self._calculate_partner_metrics(distribution_df, cash_flows)

        return {
            "distribution_method": "em_waterfall",
            "partner_distributions": partner_metrics["partner_distributions"],
            "total_metrics": partner_metrics["total_metrics"],
            "partnership_summary": {
                "partner_count": self.partnership.partner_count,
                "gp_total_share": self.partnership.gp_total_share,
                "lp_total_share": self.partnership.lp_total_share,
                "gp_count": len(self.partnership.gp_partners),
                "lp_count": len(self.partnership.lp_partners),
            },
            "waterfall_details": {
                "promote_structure": type(promote).__name__,
                "tiers_used": tiers,
                "final_promote_rate": final_promote_rate,
                "distribution_matrix": distribution_df,
            },
        }
    
    def _calculate_hybrid_waterfall(
        self, cash_flows: pd.Series, timeline: Timeline, promote
    ) -> Dict[str, Any]:
        """
        Calculate hybrid IRR/EM waterfall distribution.
        
        Uses min or max logic to combine IRR and EM hurdles.
        """
        # For now, calculate both and combine based on logic
        # This is a simplified implementation - could be optimized
        
        # Calculate IRR-based distribution
        irr_results = self._calculate_irr_waterfall(cash_flows, timeline, promote.irr_waterfall)
        
        # Calculate EM-based distribution  
        em_results = self._calculate_em_waterfall(cash_flows, timeline, promote.em_waterfall)
        
        # Extract partner cash flows from both
        irr_flows = irr_results["waterfall_details"]["distribution_matrix"]
        em_flows = em_results["waterfall_details"]["distribution_matrix"]
        
        # Combine based on logic
        if promote.logic == "min":
            # More restrictive - LP gets better of two outcomes
            # For each partner, choose the distribution that gives LP higher return
            lp_mask = np.array([p.kind == "LP" for p in self.partnership.partners])
            
            # Calculate which gives LP more
            lp_irr_total = irr_flows.iloc[:, lp_mask].sum().sum()
            lp_em_total = em_flows.iloc[:, lp_mask].sum().sum()
            
            if lp_irr_total >= lp_em_total:
                # IRR gives LP more, use it
                final_results = irr_results
            else:
                # EM gives LP more, use it
                final_results = em_results
        else:
            # Max logic - GP gets better of two outcomes
            gp_mask = np.array([p.kind == "GP" for p in self.partnership.partners])
            
            # Calculate which gives GP more
            gp_irr_total = irr_flows.iloc[:, gp_mask].sum().sum()
            gp_em_total = em_flows.iloc[:, gp_mask].sum().sum()
            
            if gp_irr_total >= gp_em_total:
                # IRR gives GP more, use it
                final_results = irr_results
            else:
                # EM gives GP more, use it
                final_results = em_results
        
        # Update distribution method to reflect hybrid
        final_results["distribution_method"] = "hybrid_waterfall"
        final_results["waterfall_details"]["hybrid_logic"] = promote.logic
        final_results["waterfall_details"]["selected"] = (
            "IRR" if final_results == irr_results else "EM"
        )
        
        return final_results
    
    def _calculate_carry_promote(
        self, cash_flows: pd.Series, timeline: Timeline, promote
    ) -> Dict[str, Any]:
        """
        Calculate traditional private equity carry distribution.
        
        Traditional carry logic:
        1. Return of capital to all partners (pro-rata)
        2. Preferred return to LP on their capital contribution
        3. Remaining profit: GP gets carry%, rest distributed pro-rata
        """
        # Set up partner data
        periods = cash_flows.index
        partner_names = [p.name for p in self.partnership.partners]
        n_periods = len(periods)
        n_partners = len(self.partnership.partners)

        # Precompute partner arrays
        partner_shares = np.array([p.share for p in self.partnership.partners])
        gp_mask = np.array([p.kind == "GP" for p in self.partnership.partners])
        lp_mask = ~gp_mask
        
        # Validate structure
        if gp_mask.sum() == 0:
            raise ValueError("Carry promote requires at least one GP partner")
        if lp_mask.sum() == 0:
            raise ValueError("Carry promote requires at least one LP partner")

        # Initialize partner cash flows matrix
        partner_flows = np.zeros((n_periods, n_partners))
        
        # Separate investments and distributions
        investments = cash_flows[cash_flows < 0]
        distributions = cash_flows[cash_flows > 0]
        
        total_investment = abs(investments.sum())
        total_distributions = distributions.sum()
        
        if total_distributions <= total_investment:
            # No profit - just return capital pro-rata
            for period_idx, cf in enumerate(cash_flows):
                if cf < 0:
                    partner_flows[period_idx, :] = cf * partner_shares
                elif cf > 0:
                    partner_flows[period_idx, :] = cf * partner_shares
        else:
            # Allocate investments pro-rata
            for period_idx, cf in enumerate(cash_flows):
                if cf < 0:
                    partner_flows[period_idx, :] = cf * partner_shares
            
            # Traditional carry distribution calculation
            total_profit = total_distributions - total_investment
            
            # Calculate holding period in years
            # Investment at start of first period, distribution at end of last period
            # So if we have 60 monthly periods, that's a 5-year holding period
            holding_years = len(cash_flows) / 12.0
            
            # Calculate preferred return amount for LPs
            lp_investment = total_investment * partner_shares[lp_mask].sum()
            preferred_return_amount = lp_investment * (
                (1 + promote.pref_hurdle_rate) ** holding_years - 1
            )
            
            # Profit above preferred return
            profit_above_pref = max(0, total_profit - preferred_return_amount)
            
            # Carry calculation
            carry_amount = profit_above_pref * promote.promote_rate
            remaining_profit = total_profit - carry_amount
            
            # Distribute each positive cash flow
            cumulative_distributed = 0.0
            
            for period_idx, cf in enumerate(cash_flows):
                if cf <= 0:
                    continue
                
                # How much of this distribution is return of capital vs profit
                capital_portion = min(cf, max(0, total_investment - cumulative_distributed))
                profit_portion = cf - capital_portion
                
                # Distribute capital return pro-rata
                if capital_portion > 0:
                    partner_flows[period_idx, :] += capital_portion * partner_shares
                
                # Distribute profit portion
                if profit_portion > 0:
                    # Calculate what portion of total profit this represents
                    profit_ratio = profit_portion / total_profit if total_profit > 0 else 0
                    
                    # GP gets proportional carry
                    period_carry = carry_amount * profit_ratio
                    # Rest distributed pro-rata
                    period_base_profit = profit_portion - period_carry
                    
                    # Allocate to partners
                    partner_flows[period_idx, :] += period_base_profit * partner_shares
                    
                    # Add carry to GP partners only
                    if period_carry > 0:
                        gp_shares_total = partner_shares[gp_mask].sum()
                        partner_flows[period_idx, gp_mask] += period_carry * (
                            partner_shares[gp_mask] / gp_shares_total
                        )
                
                cumulative_distributed += cf
        
        # Convert to DataFrame
        distribution_df = pd.DataFrame(
            partner_flows, index=periods, columns=partner_names
        )

        # Calculate metrics
        partner_metrics = self._calculate_partner_metrics(distribution_df, cash_flows)

        return {
            "distribution_method": "carry_promote",
            "partner_distributions": partner_metrics["partner_distributions"],
            "total_metrics": partner_metrics["total_metrics"],
            "partnership_summary": {
                "partner_count": self.partnership.partner_count,
                "gp_total_share": self.partnership.gp_total_share,
                "lp_total_share": self.partnership.lp_total_share,
                "gp_count": len(self.partnership.gp_partners),
                "lp_count": len(self.partnership.lp_partners),
            },
            "waterfall_details": {
                "promote_structure": type(promote).__name__,
                "preferred_return_rate": promote.pref_hurdle_rate,
                "carry_rate": promote.promote_rate,
                "distribution_matrix": distribution_df,
                "carry_calculation": {
                    "total_investment": total_investment,
                    "total_distributions": total_distributions,
                    "total_profit": total_distributions - total_investment,
                    "preferred_return_amount": lp_investment * (
                        (1 + promote.pref_hurdle_rate) ** (len(cash_flows) / 12.0) - 1
                    ) if total_distributions > total_investment else 0,
                    "carry_amount": profit_above_pref * promote.promote_rate if total_distributions > total_investment else 0,
                }
            },
        }

    def calculate_distributions(
        self, cash_flows: pd.Series, timeline: Timeline
    ) -> Dict[str, Any]:
        """
        Calculate distributions based on the partnership structure.

        NOTE: "waterfall" method implements EUROPEAN-STYLE waterfall logic.

        This is the main entry point that determines which distribution method to use
        based on the partnership configuration.

        Args:
            cash_flows: Series of levered cash flows (negative=investment, positive=returns)
            timeline: Analysis timeline for period indexing

        Returns:
            Distribution results dictionary with partner-level metrics and cash flows
        """
        if self.partnership.distribution_method == "pari_passu":
            return self.calculate_pari_passu_distribution(cash_flows, timeline)
        elif self.partnership.distribution_method == "waterfall":
            return self.calculate_waterfall_distribution(cash_flows, timeline)
        else:
            raise ValueError(
                f"Unknown distribution method: {self.partnership.distribution_method}"
            )

    def create_partner_summary_dataframe(
        self, distribution_results: Dict[str, Any]
    ) -> pd.DataFrame:
        """
        Create a summary DataFrame showing partner returns and metrics.

        Args:
            distribution_results: Results from calculate_distributions

        Returns:
            DataFrame with partner summary information
        """
        partner_data = []

        for partner_name, metrics in distribution_results[
            "partner_distributions"
        ].items():
            partner_info = metrics["partner_info"]

            partner_data.append({
                "Partner": partner_name,
                "Type": partner_info.kind,
                "Ownership": f"{partner_info.share:.1%}",
                "Investment": f"${metrics['total_investment']:,.0f}",
                "Distributions": f"${metrics['total_distributions']:,.0f}",
                "Net Profit": f"${metrics['net_profit']:,.0f}",
                "Equity Multiple": f"{metrics['equity_multiple']:.2f}x",
                "IRR": f"{metrics['irr']:.1%}" if metrics["irr"] is not None else "N/A",
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
            "IRR": f"{total_metrics['irr']:.1%}"
            if total_metrics["irr"] is not None
            else "N/A",
        })

        return pd.DataFrame(partner_data)


def calculate_partner_distributions_with_structure(
    partnership: PartnershipStructure, cash_flows: pd.Series, timeline: Timeline
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
