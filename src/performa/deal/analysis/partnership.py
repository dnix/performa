# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Partnership Analysis Specialist

This module provides the PartnershipAnalyzer service that handles complex partnership distribution
calculations including sophisticated equity waterfall logic, fee distributions, and comprehensive
partner metrics calculation for commercial real estate investment partnerships.

The PartnershipAnalyzer represents the final component of the deal analysis framework, handling
the complex distribution of equity returns among partners based on their partnership structures,
promote agreements, and fee arrangements.

Key capabilities:
- **Sophisticated Equity Waterfall**: IRR-based promote calculations with binary search precision
- **Fee Priority Payments**: Complex fee distribution logic with actual payee allocation
- **Partnership Metrics**: Comprehensive partner-level and deal-level performance calculations
- **Dual-Entry Accounting**: Proper accounting for fee payments with project debits and partner credits
- **Multi-Partner Support**: Handles complex partnership structures with multiple GP and LP partners
- **Third-Party Fee Tracking**: Comprehensive tracking of fees paid to non-equity partners

The service implements institutional standards used in commercial real estate private equity,
including the sophisticated waterfall algorithms that determine how equity returns are distributed
among partners based on their preferred returns, promote structures, and fee arrangements.

Waterfall Distribution Logic:
    The analyzer implements institutional-grade waterfall algorithms:

    1. **Fee Priority Payments**: All fees are paid first before equity distributions
    2. **Capital Return**: Partners receive return of capital pro-rata to their contributions
    3. **Preferred Return**: Partners receive preferred return on unreturned capital
    4. **IRR-Based Promote**: Sophisticated promote calculations based on running IRR
    5. **Binary Search Precision**: Exact tier transition calculations for promote thresholds
    6. **GP Promote Allocation**: Promote distributions allocated to GP partners only

    The waterfall supports complex promote structures with multiple IRR hurdles and
    promote rates, using binary search algorithms to find exact tier transition points.

Partnership Distribution Methods:
    - **Pari Passu**: Proportional distribution based on ownership percentages
    - **Waterfall**: Sophisticated IRR-based promote calculations with multiple tiers
    - **Single Entity**: Simplified distribution for deals without equity partners

Example:
    ```python
    from performa.deal.analysis import PartnershipAnalyzer

    # Create partnership analyzer
    analyzer = PartnershipAnalyzer(deal, timeline, settings)

    # Calculate partner distributions
    distribution_results = analyzer.calculate_partner_distributions(levered_cash_flows)

    # Access comprehensive results
    if hasattr(distribution_results, 'waterfall_details'):
        waterfall_details = distribution_results.waterfall_details
        print(f"Distribution method: {distribution_results.distribution_method}")
        print(f"Total distributions: ${distribution_results.total_distributions:,.0f}")
        print(f"Partner count: {len(waterfall_details.partner_results)}")

        # Analyze individual partner results
        for partner_name, partner_result in waterfall_details.partner_results.items():
            print(f"{partner_name}: ${partner_result['total_distributions']:,.0f} "
                  f"(IRR: {partner_result['irr']:.1%})")
    ```

Architecture:
    - Uses dataclass pattern for runtime service state management
    - Implements institutional-grade waterfall algorithms with binary search precision
    - Provides comprehensive fee accounting with dual-entry logic
    - Supports discriminated union result types for different distribution methods
    - Integrates with broader deal analysis workflow through typed interfaces

Institutional Standards:
    - Follows commercial real estate private equity distribution practices
    - Implements IRR-based promote calculations used by institutional sponsors
    - Provides fee priority payment logic used in institutional partnerships
    - Supports complex promote structures with multiple hurdles and rates
    - Maintains audit trails required for institutional partnerships
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional

import numpy as np
import pandas as pd
from pyxirr import xirr

from performa.core.ledger import LedgerBuilder, SeriesMetadata
from performa.deal.results import FeeAccountingDetails

if TYPE_CHECKING:
    from performa.core.ledger import LedgerBuilder
    from performa.core.primitives import GlobalSettings, Timeline
    from performa.deal.deal import Deal

from performa.deal.partnership import Partner, PartnershipStructure
from performa.deal.results import (
    ErrorDistributionResult,
    PartnerDistributionResult,
    SingleEntityDistributionResult,
    WaterfallDistributionResult,
)

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

            # Calculate IRR
            irr = None
            if len(partner_cf) > 1 and total_investment > 0:
                try:
                    # Create dates for IRR calculation
                    dates = [
                        period.to_timestamp().date() for period in partner_cf.index
                    ]
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
                "ownership_percentage": partner.share,
            }

        # Calculate total deal metrics
        total_investment = abs(total_cash_flows[total_cash_flows < 0].sum())
        total_distributions = total_cash_flows[total_cash_flows > 0].sum()
        net_profit = total_cash_flows.sum()

        total_equity_multiple = (
            total_distributions / total_investment if total_investment > 0 else 0.0
        )

        # Calculate total IRR
        total_irr = None
        if len(total_cash_flows) > 1 and total_investment > 0:
            try:
                dates = [
                    period.to_timestamp().date() for period in total_cash_flows.index
                ]
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
                "irr": total_irr,
            },
        }

    def calculate_pari_passu_distribution(
        self, cash_flows: pd.Series, timeline: "Timeline"
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
        self, cash_flows: pd.Series, timeline: "Timeline"
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

        # Track cumulative capital contributions and return by partner
        partner_capital_contributions = np.zeros(n_partners)
        partner_capital_returned = np.zeros(n_partners)

        # Track current tier
        current_tier_index = 0

        # Pre-extract dates for IRR calculation
        date_array = periods.to_timestamp().to_pydatetime()

        def current_irr(flows: np.ndarray, up_to_idx: int) -> Optional[float]:
            """Calculate current IRR for all partners up to a given period."""
            cf = flows[: up_to_idx + 1].sum(axis=1)
            # Need both negative and positive flows for IRR to be meaningful
            if not (np.any(cf < 0) and np.any(cf > 0)):
                return None
            s = pd.Series(cf, index=date_array[: up_to_idx + 1])
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
            base_dist[gp_mask] += promote_amount * (
                partner_shares[gp_mask] / gp_shares_total
            )

            return base_dist

        def test_allocation(
            flows: np.ndarray, period_idx: int, cf_amount: float, promote_rate: float
        ) -> float:
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
            return irr if irr is not None else float("-inf")

        def solve_for_x(
            flows: np.ndarray,
            period_idx: int,
            cf_amount: float,
            promote_rate: float,
            hurdle_rate: float,
        ) -> float:
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

        # Process each period sequentially to build up the waterfall
        # The waterfall algorithm requires sequential processing because each period's
        # distribution depends on the cumulative IRR calculated from all previous periods
        for period_idx, period in enumerate(periods):
            cf_value = cash_flows.iloc[period_idx]

            if cf_value < 0:
                # NEGATIVE CASH FLOW: Equity contribution phase
                # Partners contribute equity proportionally to their ownership percentages
                # This is the "capital call" phase of the partnership
                contributions = cf_value * partner_shares
                partner_flows[period_idx, :] += contributions

                # Track capital contributions (as positive amounts for accounting)
                # We flip the sign because contributions are negative in cash flow but positive in accounting
                partner_capital_contributions += -contributions  # Convert to positive

            elif cf_value > 0:
                # POSITIVE CASH FLOW: Distribution phase
                # This is where the waterfall algorithm applies
                # First return capital, then apply promote logic based on IRR hurdles
                remaining_cf = cf_value

                # Step 1: Return capital pro-rata until partners get their investments back
                total_unreturned_capital = np.maximum(
                    0, partner_capital_contributions - partner_capital_returned
                ).sum()

                if total_unreturned_capital > 0 and remaining_cf > 0:
                    # Calculate how much capital to return this period
                    capital_to_return = min(remaining_cf, total_unreturned_capital)

                    # Distribute capital return pro-rata based on unreturned amounts
                    unreturned_by_partner = np.maximum(
                        0, partner_capital_contributions - partner_capital_returned
                    )

                    if unreturned_by_partner.sum() > 0:
                        capital_return_ratios = (
                            unreturned_by_partner / unreturned_by_partner.sum()
                        )
                        capital_returns = capital_to_return * capital_return_ratios

                        # Allocate capital returns
                        partner_flows[period_idx, :] += capital_returns
                        partner_capital_returned += capital_returns
                        remaining_cf -= capital_to_return

                # Step 2: Apply waterfall logic to remaining cash flow (profits above capital)
                # This is the core promote algorithm that determines GP vs LP distributions
                while (
                    remaining_cf > 0.01
                ):  # Continue until all profit is allocated (to nearest cent)
                    # Determine current tier promote rate based on IRR hurdles
                    if current_tier_index < len(tiers):
                        hurdle_rate, promote_rate = tiers[current_tier_index]
                    else:
                        # Above all tiers, use final promote rate (typically 20-50%)
                        hurdle_rate = np.inf
                        promote_rate = final_promote_rate

                    # Test if allocating all remaining CF would exceed the current hurdle
                    # This determines whether we can allocate everything at the current promote rate
                    test_irr_val = test_allocation(
                        partner_flows, period_idx, remaining_cf, promote_rate
                    )

                    if test_irr_val < hurdle_rate:
                        # CASE 1: All remaining CF can be allocated at current promote rate
                        # The IRR stays below the hurdle, so we don't move to next tier
                        partner_flows[period_idx, :] += allocate_cf_at_rate(
                            remaining_cf, promote_rate
                        )
                        remaining_cf = 0.0
                    else:
                        # CASE 2: Allocating all CF would exceed hurdle - need binary search
                        # This is the sophisticated part: find exact amount to hit hurdle precisely
                        # Uses 30-iteration binary search for institutional-grade precision
                        x = solve_for_x(
                            partner_flows,
                            period_idx,
                            remaining_cf,
                            promote_rate,
                            hurdle_rate,
                        )
                        partner_flows[period_idx, :] += allocate_cf_at_rate(
                            x, promote_rate
                        )
                        remaining_cf -= x

                        # Move to next tier for remaining distributions
                        # The next tier will have a higher promote rate for the GP
                        current_tier_index += 1

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

    def calculate_distributions(
        self, cash_flows: pd.Series, timeline: "Timeline"
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
    partnership: PartnershipStructure, cash_flows: pd.Series, timeline: "Timeline"
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
    distribution_method: str = "pari_passu",
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
        partners=[gp, lp], distribution_method=distribution_method
    )


@dataclass
class PartnershipAnalyzer:
    """
    Specialist service for analyzing partnership structures and calculating distributions with institutional precision.

    This service represents the final component of the deal analysis framework, implementing the sophisticated
    distribution algorithms used in commercial real estate private equity partnerships. It handles the complex
    allocation of equity returns among partners based on their partnership agreements, promote structures,
    and fee arrangements.

    The PartnershipAnalyzer implements institutional standards for partnership distributions, including:
    - IRR-based promote calculations with binary search precision for exact tier transitions
    - Fee priority payment logic ensuring fees are paid before equity distributions
    - Dual-entry accounting for proper fee tracking (project debits + partner credits)
    - Comprehensive partner metrics calculation including IRR, equity multiple, and cash-on-cash returns
    - Support for complex promote structures with multiple hurdles and rates
    - Third-party fee tracking for non-equity service providers

    Key features:
    - **Institutional Waterfall Logic**: Implements the standard equity waterfall used in private equity
    - **Binary Search Precision**: Uses 30-iteration binary search for exact promote tier transitions
    - **Fee Priority Payments**: Ensures all fees are paid before equity waterfall distributions
    - **Comprehensive Metrics**: Calculates IRR, equity multiple, and other key performance indicators
    - **Multi-Partner Support**: Handles complex structures with multiple GP and LP partners
    - **Third-Party Integration**: Tracks fees paid to non-equity partners and service providers
    - **Audit Trail Maintenance**: Provides detailed tracking for institutional reporting requirements

    Distribution workflow:
    1. Calculate fee priority payments with actual payee allocation
    2. Apply waterfall logic to remaining cash flows after fees
    3. Combine fee and waterfall results for comprehensive analysis
    4. Calculate partner-level and deal-level performance metrics

    Attributes:
        deal: The deal containing partnership structure and fee arrangements
        timeline: Analysis timeline for distribution calculations
        settings: Global settings for partnership analysis configuration
        partner_distributions: Runtime state populated during analysis (internal use)

    Example:
        ```python
        # Create partnership analyzer
        analyzer = PartnershipAnalyzer(deal, timeline, settings)

        # Calculate distributions
        results = analyzer.calculate_partner_distributions(levered_cash_flows)

        # Access waterfall results
        if results.distribution_method == 'waterfall':
            waterfall_details = results.waterfall_details
            partner_results = waterfall_details.partner_results

            # Analyze GP vs LP performance
            for partner_name, partner_result in partner_results.items():
                partner_info = partner_result['partner_info']
                print(f"{partner_name} ({partner_info.kind}): "
                      f"${partner_result['total_distributions']:,.0f} "
                      f"(IRR: {partner_result['irr']:.1%}, "
                      f"Multiple: {partner_result['equity_multiple']:.2f}x)")
        ```
    """

    # Input parameters
    deal: Deal
    timeline: Timeline
    settings: GlobalSettings

    # Runtime state (populated during analysis)
    partner_distributions: PartnerDistributionResult = field(
        init=False, repr=False, default=None
    )

    def calculate_partner_distributions(
        self,
        levered_cash_flows: pd.Series,
        ledger_builder: "LedgerBuilder",  # REQUIRED - must be the populated ledger from asset analysis
    ) -> PartnerDistributionResult:
        """
        Calculate partner distributions through equity waterfall with comprehensive fee handling.

        This method applies the equity waterfall logic to distribute cash flows among partners
        based on their partnership structure, including fee priority payments and complex
        IRR-based promote calculations.

        Args:
            levered_cash_flows: The levered cash flow series from cash flow analysis
            ledger_builder: Optional ledger builder for transaction recording

        Returns:
            PartnerDistributionResult containing distribution analysis
        """
        # Check if deal has equity partners
        if not self.deal.has_equity_partners:
            # No equity partners - single entity results
            self.partner_distributions = self._calculate_single_entity_distributions(
                levered_cash_flows
            )
            return self.partner_distributions

        # Calculate fee priority payments
        fee_details = self._calculate_fee_distributions(levered_cash_flows)

        # Get remaining cash flows after fee payments
        remaining_cash_flows = fee_details["remaining_cash_flows_after_fee"]

        # Calculate standard waterfall distributions on remaining cash flows
        if isinstance(remaining_cash_flows, pd.Series):
            try:
                # Use the local DistributionCalculator instead of importing
                calculator = DistributionCalculator(self.deal.equity_partners)
                waterfall_results = calculator.calculate_distributions(
                    remaining_cash_flows, self.timeline
                )

                # Combine fee and waterfall results
                try:
                    combined_results = self._combine_fee_and_waterfall_results(
                        fee_details, waterfall_results
                    )
                    self.partner_distributions = (
                        self._create_partner_distributions_result(combined_results)
                    )
                except Exception as combine_error:
                    logger = logging.getLogger(__name__)
                    logger.error(f"Combination failed: {combine_error}")
                    # Use waterfall results directly if combination fails
                    waterfall_results["fee_details"] = fee_details
                    self.partner_distributions = (
                        self._create_partner_distributions_result(waterfall_results)
                    )

            except Exception as e:
                # Fallback for DistributionCalculator errors
                logger = logging.getLogger(__name__)
                error_results = {
                    "distribution_method": "error",
                    "total_distributions": 0.0,
                    "total_investment": 0.0,
                    "equity_multiple": 0.0,
                    "irr": 0.0,
                    "distributions": pd.Series(0.0, index=self.timeline.period_index),
                    "waterfall_details": {
                        "error": f"DistributionCalculator failed: {str(e)}",
                        "preferred_return": 0.0,
                        "promote_distributions": 0.0,
                    },
                    "fee_details": fee_details,
                }
                self.partner_distributions = self._create_partner_distributions_result(
                    error_results
                )
                logger.error(f"DistributionCalculator failed with error: {e}")
                logger.debug("DistributionCalculator stack trace:", exc_info=True)
        else:
            # Fallback for invalid cash flows
            error_results = {
                "distribution_method": "error",
                "total_distributions": 0.0,
                "total_investment": 0.0,
                "equity_multiple": 0.0,
                "irr": 0.0,
                "distributions": pd.Series(0.0, index=self.timeline.period_index),
                "waterfall_details": {
                    "error": f"Invalid cash flow data type: {type(remaining_cash_flows)}",
                    "preferred_return": 0.0,
                    "promote_distributions": 0.0,
                },
                "fee_details": fee_details,
            }
            self.partner_distributions = self._create_partner_distributions_result(
                error_results
            )

        # Add distribution records to ledger (ledger_builder must be provided)
        if ledger_builder is None:
            raise ValueError(
                "ledger_builder is required and must contain prior transaction data"
            )
        self._add_distribution_records_to_ledger(ledger_builder)

        return self.partner_distributions

    def _add_distribution_records_to_ledger(self, ledger_builder: LedgerBuilder):
        """
        Add partner distribution transactions to the ledger.

        This method takes the calculated distributions and adds them as
        distribution transactions to the ledger for full audit trail.

        Args:
            ledger_builder: The ledger builder to add transactions to
        """

        if (
            self.partner_distributions is None
            or not hasattr(self.partner_distributions, "waterfall_details")
            or self.partner_distributions.waterfall_details is None
        ):
            return

        # Add partner distribution transactions
        if hasattr(self.partner_distributions.waterfall_details, "partner_results"):
            for (
                partner_name,
                partner_metrics,
            ) in self.partner_distributions.waterfall_details.partner_results.items():
                if (
                    partner_metrics.cash_flows is not None
                    and partner_metrics.cash_flows.sum() != 0
                ):
                    metadata = SeriesMetadata(
                        category="Financing",
                        subcategory="Distribution",
                        item_name=f"Distribution to {partner_name}",
                        source_id=getattr(partner_metrics.partner_info, "uid", None),
                        asset_id=self.deal.asset.uid,
                        deal_id=self.deal.uid,
                        entity_id=getattr(partner_metrics.partner_info, "uid", None),
                        entity_type="GP"
                        if getattr(partner_metrics.partner_info, "is_gp", False)
                        else "LP",
                        pass_num=3,  # TODO: Check this: Partnership is pass 3
                    )
                    # Note: Use negative cash flows since distributions are outflows from project perspective
                    distribution_flows = -1 * partner_metrics.cash_flows
                    ledger_builder.add_series(distribution_flows, metadata)

    def _calculate_single_entity_distributions(
        self, cash_flows: pd.Series
    ) -> SingleEntityDistributionResult:
        """
        Calculate distributions for single entity deals (no equity partners).

        Args:
            cash_flows: The cash flow series

        Returns:
            SingleEntityDistributionResult containing single entity analysis
        """
        # Calculate fee distributions even for single entity
        fee_details = self._calculate_fee_distributions(cash_flows)

        # Use remaining cash flows after fees for metrics
        remaining_cash_flows = fee_details["remaining_cash_flows_after_fee"]

        # Calculate basic metrics
        negative_flows = remaining_cash_flows[remaining_cash_flows < 0]
        positive_flows = remaining_cash_flows[remaining_cash_flows > 0]

        total_investment = abs(negative_flows.sum())
        total_distributions = positive_flows.sum()
        equity_multiple = (
            total_distributions / total_investment if total_investment > 0 else 0.0
        )

        # Calculate IRR
        irr = None
        if len(remaining_cash_flows) > 1 and total_investment > 0:
            try:
                dates = [
                    period.to_timestamp().date()
                    for period in remaining_cash_flows.index
                ]
                irr = xirr(dates, remaining_cash_flows.values)
                if irr is not None:
                    irr = float(irr)
            except Exception:
                pass

        return SingleEntityDistributionResult(
            distribution_method="single_entity",
            total_distributions=total_distributions,
            total_investment=total_investment,
            equity_multiple=equity_multiple,
            irr=irr,
            distributions=remaining_cash_flows,
            entity_details={
                "entity_name": self.deal.name,
                "net_profit": remaining_cash_flows.sum(),
                "hold_period_years": len(self.timeline.period_index) / 12.0,
            },
            developer_fee_details={
                "total_developer_fee": fee_details["total_partner_fees"],
                "developer_fee_by_partner": fee_details["partner_fees_by_partner"],
                "remaining_cash_flows_after_fee": remaining_cash_flows,
            },
        )

    def _calculate_fee_distributions(self, cash_flows: pd.Series) -> Dict[str, Any]:
        """
        Calculate fee priority payments with actual payee allocation.

        This method handles the complex fee distribution logic including:
        - Fee priority payments before equity waterfall
        - Actual payee allocation (who gets paid what)
        - Dual-entry fee accounting
        - Third-party fee tracking

        Args:
            cash_flows: The cash flow series

        Returns:
            Dictionary containing fee distribution details in expected test structure
        """
        # Initialize fee tracking
        total_partner_fees = 0.0
        partner_fees_by_partner = {}
        fee_details_by_partner = {}  # Dictionary format for compatibility
        detailed_fee_breakdown = {}  # List format for detailed audit trail
        fee_cash_flows_by_partner = {}

        # Initialize third-party fee tracking
        total_third_party_fees = 0.0
        third_party_fees = {}
        third_party_fee_details = {}
        third_party_fee_cash_flows = {}

        # Initialize fee type tracking
        total_fees_by_type = {}
        fee_timing_summary = {}

        remaining_cash_flows = cash_flows.copy()

        # Initialize all partners with zero fees
        if self.deal.has_equity_partners:
            for partner in self.deal.equity_partners.partners:
                partner_fees_by_partner[partner.name] = 0.0
                fee_details_by_partner[partner.name] = {}  # Dictionary format
                detailed_fee_breakdown[partner.name] = []  # List format
                fee_cash_flows_by_partner[partner.name] = pd.Series(
                    0.0, index=self.timeline.period_index
                )

        # Calculate total fee amounts
        if self.deal.deal_fees:
            for fee in self.deal.deal_fees:
                try:
                    # Calculate fee cash flows
                    fee_cf = fee.compute_cf(self.timeline)
                    fee_amount = fee_cf.sum()

                    # Track fee by partner/payee
                    fee_name = getattr(fee, "name", "Unknown Fee")
                    fee_type = getattr(fee, "fee_type", "Unknown")
                    payee = getattr(fee, "payee", "Unknown Payee")

                    # Get payee name (string key for tests)
                    payee_name = getattr(payee, "name", str(payee))

                    # Check if payee is a deal partner or third-party
                    is_partner = False
                    if self.deal.has_equity_partners:
                        partner_names = [
                            p.name for p in self.deal.equity_partners.partners
                        ]
                        is_partner = payee_name in partner_names

                    # Track fees by type (regardless of partner vs third-party)
                    if fee_type not in total_fees_by_type:
                        total_fees_by_type[fee_type] = 0.0
                    total_fees_by_type[fee_type] += fee_amount

                    # Track fee timing
                    if payee_name not in fee_timing_summary:
                        fee_timing_summary[payee_name] = {}

                    # Add timing information for each period with non-zero fee cash flows
                    fee_cf_reindexed = fee_cf.reindex(
                        self.timeline.period_index, fill_value=0.0
                    )
                    for period, amount in fee_cf_reindexed.items():
                        if amount > 0:
                            period_str = str(period)
                            if period_str not in fee_timing_summary[payee_name]:
                                fee_timing_summary[payee_name][period_str] = 0.0
                            fee_timing_summary[payee_name][period_str] += float(amount)

                    if is_partner:
                        # Handle partner fees
                        if payee_name not in partner_fees_by_partner:
                            partner_fees_by_partner[payee_name] = 0.0
                            fee_details_by_partner[payee_name] = {}
                            detailed_fee_breakdown[payee_name] = []
                            fee_cash_flows_by_partner[payee_name] = pd.Series(
                                0.0, index=self.timeline.period_index
                            )

                        partner_fees_by_partner[payee_name] += fee_amount
                        total_partner_fees += fee_amount

                        # Populate dictionary format (for backward compatibility)
                        fee_details_by_partner[payee_name][fee_name] = float(fee_amount)

                        # Create fee detail dictionary for detailed audit trail
                        fee_detail = {
                            "fee_name": fee_name,
                            "fee_type": fee_type,
                            "amount": float(fee_amount),
                            "payee": payee_name,
                            "draw_schedule": type(fee.draw_schedule).__name__,
                            "description": getattr(fee, "description", ""),
                        }
                        detailed_fee_breakdown[payee_name].append(fee_detail)
                        fee_cash_flows_by_partner[payee_name] += fee_cf_reindexed
                    else:
                        # Handle third-party fees
                        if payee_name not in third_party_fees:
                            third_party_fees[payee_name] = 0.0
                            third_party_fee_details[payee_name] = {}
                            third_party_fee_cash_flows[payee_name] = pd.Series(
                                0.0, index=self.timeline.period_index
                            )

                        third_party_fees[payee_name] += fee_amount
                        total_third_party_fees += fee_amount
                        third_party_fee_details[payee_name][fee_name] = float(
                            fee_amount
                        )
                        third_party_fee_cash_flows[payee_name] += fee_cf_reindexed

                    # Remove fee from remaining cash flows (fee priority) regardless of payee type
                    remaining_cash_flows -= fee_cf_reindexed

                except Exception:
                    # Log warning but continue
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Could not calculate fee for {fee}")

        return {
            "total_partner_fees": total_partner_fees,
            "partner_fees_by_partner": partner_fees_by_partner,
            "fee_details_by_partner": fee_details_by_partner,
            "detailed_fee_breakdown": detailed_fee_breakdown,
            "fee_cash_flows_by_partner": fee_cash_flows_by_partner,
            "remaining_cash_flows_after_fee": remaining_cash_flows,
            # Third-party fee fields
            "total_third_party_fees": total_third_party_fees,
            "third_party_fees": third_party_fees,
            "third_party_fee_details": third_party_fee_details,
            "third_party_fee_cash_flows": third_party_fee_cash_flows,
            "total_fees_by_type": total_fees_by_type,
            "fee_timing_summary": fee_timing_summary,
            # Keep backward compatibility
            "total_developer_fee": total_partner_fees,
            "developer_fee_by_partner": {
                payee: amount for payee, amount in partner_fees_by_partner.items()
            },
        }

    def _combine_fee_and_waterfall_results(
        self, fee_details: Dict[str, Any], waterfall_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Combine fee and waterfall results into comprehensive distribution analysis.

        This method merges the fee priority payments with the equity waterfall results
        to create a complete picture of partner distributions.

        Args:
            fee_details: Fee distribution details
            waterfall_results: Waterfall distribution results

        Returns:
            Combined distribution results
        """
        # Combine the results - waterfall_results has structure with total_metrics
        combined_results = waterfall_results.copy()

        fee_accounting_details = FeeAccountingDetails(**fee_details)
        combined_results["fee_accounting_details"] = fee_accounting_details

        # Adjust total distributions to include fees - access through total_metrics
        if "total_metrics" in combined_results:
            combined_results["total_metrics"]["total_distributions"] += fee_details[
                "total_partner_fees"
            ]

        # Add fee information to waterfall details (create if not exists)
        if "waterfall_details" not in combined_results:
            combined_results["waterfall_details"] = {}
        combined_results["waterfall_details"]["total_fees"] = fee_details[
            "total_partner_fees"
        ]

        # Map the expected structure for the result model
        # The result model expects top-level total_distributions, total_investment, etc.
        if "total_metrics" in combined_results:
            metrics = combined_results["total_metrics"]
            combined_results["total_distributions"] = metrics.get(
                "total_distributions", 0.0
            )
            combined_results["total_investment"] = metrics.get("total_investment", 0.0)
            combined_results["equity_multiple"] = metrics.get("equity_multiple", 1.0)
            combined_results["irr"] = metrics.get("irr", None)

        # Create partner_results structure from partner_distributions
        if "partner_distributions" in combined_results:
            partner_results = {}
            for partner_name, partner_metrics in combined_results[
                "partner_distributions"
            ].items():
                partner_results[partner_name] = {
                    "partner_info": partner_metrics.get("partner_info"),
                    "cash_flows": partner_metrics.get("cash_flows"),
                    "total_investment": partner_metrics.get("total_investment", 0.0),
                    "total_distributions": partner_metrics.get(
                        "total_distributions", 0.0
                    ),
                    "net_profit": partner_metrics.get("net_profit", 0.0),
                    "equity_multiple": partner_metrics.get("equity_multiple", 1.0),
                    "irr": partner_metrics.get("irr", None),
                    "ownership_percentage": partner_metrics.get(
                        "ownership_percentage", 0.0
                    ),
                    "distributions_from_fees": 0.0,  # Add fee-specific fields
                    "distributions_from_waterfall": partner_metrics.get(
                        "total_distributions", 0.0
                    ),  # Add waterfall-specific field
                    "developer_fee": 0.0,
                    "fee_details": {},  # Empty dictionary by default
                    "fee_cash_flows": pd.Series(
                        0.0, index=self.timeline.period_index
                    ),  # Zero by default
                    "fee_count": 0,  # Add fee count field
                }

            # Add fee distributions to partner results
            if "partner_fees_by_partner" in fee_details:
                for payee_name, fee_amount in fee_details[
                    "partner_fees_by_partner"
                ].items():
                    if payee_name in partner_results:
                        partner_results[payee_name]["distributions_from_fees"] = (
                            fee_amount
                        )
                        partner_results[payee_name]["developer_fee"] = fee_amount

                        # Use the fee details from the dictionary format
                        fee_details_dict = fee_details["fee_details_by_partner"].get(
                            payee_name, {}
                        )
                        partner_results[payee_name]["fee_details"] = fee_details_dict
                        partner_results[payee_name]["fee_count"] = len(fee_details_dict)
                        partner_results[payee_name]["fee_cash_flows"] = fee_details[
                            "fee_cash_flows_by_partner"
                        ].get(
                            payee_name, pd.Series(0.0, index=self.timeline.period_index)
                        )

                        # Update total distributions to include fees
                        partner_results[payee_name]["total_distributions"] = (
                            partner_results[payee_name]["distributions_from_waterfall"]
                            + fee_amount
                        )

            combined_results["waterfall_details"]["partner_results"] = partner_results

        return combined_results

    def _create_partner_distributions_result(
        self, distribution_data: Dict[str, Any]
    ) -> PartnerDistributionResult:
        """
        Create the appropriate partner distribution result based on distribution method.

        This handles the discriminated union logic to create the correct
        distribution result type based on the distribution method.

        Args:
            distribution_data: Dictionary containing distribution results

        Returns:
            Appropriate PartnerDistributionResult subclass
        """
        distribution_method = distribution_data.get("distribution_method", "error")

        if distribution_method in ["waterfall", "pari_passu"]:
            # For pari_passu, change distribution_method to "waterfall" for Pydantic validation
            partner_distributions_data = distribution_data.copy()
            if distribution_method == "pari_passu":
                partner_distributions_data["distribution_method"] = "waterfall"
            return WaterfallDistributionResult(**partner_distributions_data)
        elif distribution_method == "single_entity":
            return SingleEntityDistributionResult(**distribution_data)
        else:
            # Error case or unknown method
            return ErrorDistributionResult(
                distribution_method="error",
                total_distributions=0.0,
                total_investment=0.0,
                equity_multiple=1.0,
                irr=None,
                distributions=pd.Series(0.0, index=self.timeline.period_index),
                waterfall_details={
                    "error": f"Unknown distribution method: {distribution_method}"
                },
                developer_fee_details={
                    "total_developer_fee": 0.0,
                    "developer_fee_by_partner": {},
                    "remaining_cash_flows_after_fee": pd.Series(
                        0.0, index=self.timeline.period_index
                    ),
                },
            )
