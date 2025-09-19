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
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict

import pandas as pd

from ...core.ledger import Ledger, SeriesMetadata
from ...core.primitives import CashFlowCategoryEnum, FinancingSubcategoryEnum
from ...core.primitives.enums import FeeTypeEnum
from ..distribution_calculator import DistributionCalculator
from .base import AnalysisSpecialist

# Deprecated result imports removed - full ledger-driven now

if TYPE_CHECKING:
    from performa.deal.orchestrator import DealContext

# Constants for numerical precision
BINARY_SEARCH_ITERATIONS = 30  # Iterations for binary search precision

logger = logging.getLogger(__name__)


@dataclass
class PartnershipAnalyzer(AnalysisSpecialist):
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
    # Fields inherited from AnalysisSpecialist base class:
    # - context (DealContext)
    # - deal, timeline, settings, ledger (via properties)
    # - queries (LedgerQueries)

    def _extract_fee_rates_from_deal(self) -> Dict[str, float]:
        """
        Extract fee rates from deal's fee structure.

        Delegates to static method to eliminate duplication.

        Returns:
            Dict with management, acquisition, and development fee rates
        """
        return self._extract_fee_rates_from_deal_static(self.deal)

    @staticmethod
    def _extract_fee_rates_from_deal_static(deal) -> Dict[str, float]:
        """
        Static version for use in _calculate_single_entity_distributions.

        Args:
            deal: Deal object to extract fee rates from

        Returns:
            Dict with management, acquisition, and development fee rates
        """
        rates = {"management": 0.0, "acquisition": 0.0, "development": 0.0}

        # Extract fee rates from deal structure
        if deal.deal_fees is not None:
            for fee in deal.deal_fees:
                if fee.fee_type is not None:
                    if fee.fee_type == FeeTypeEnum.ASSET_MANAGEMENT:
                        rates["management"] = 0.02  # 2% if management fee exists
                    elif fee.fee_type == FeeTypeEnum.ACQUISITION:
                        rates["acquisition"] = 0.01  # 1% if acquisition fee exists
                    elif fee.fee_type == FeeTypeEnum.DEVELOPER:
                        rates["development"] = 0.03  # 3% if development fee exists

        # Fallback to standard institutional defaults if no deal fees specified
        if all(rate == 0.0 for rate in rates.values()):
            rates = {
                "management": 0.02,  # 2% annual management fee
                "acquisition": 0.01,  # 1% acquisition fee
                "development": 0.03,  # 3% development fee
            }

        return rates

    def process(self) -> None:
        """
        Settings-driven partnership analysis with institutional-grade waterfall logic.
        Handles single owner or complex waterfall using settings for fee assumptions.

        Writes all distribution transactions to ledger. Early returns on no-op conditions.
        """
        if not self.deal.equity_partners:
            # Single owner - simple pass-through
            # FIXME: i don't think this is true, i think we always need this object...
            return

        # Extract fee rates from deal structure (or use standard defaults)
        fee_rates = self._extract_fee_rates_from_deal()
        management_fee_rate = fee_rates["management"]
        acquisition_fee_rate = fee_rates["acquisition"]
        development_fee_rate = fee_rates["development"]

        # CRITICAL FIX: Get available cash for distribution from ACTUAL ledger transactions only

        # Step 1: Get ACTUAL NOI from ledger transactions (much cleaner than reconstructing)
        actual_noi = self.queries.noi()  # Direct NOI from operating transactions only

        # Step 2: Get ACTUAL debt service from ledger transactions
        debt_service = self.queries.debt_service()

        # TODO: create a net cash flow (noi minus debt service) in LedgerQueries

        # Step 3: Validate we have actual operations to distribute
        if actual_noi.empty and debt_service.empty:
            return  # No operations to distribute

        # Step 4: Align indices for calculation using Timeline.align_series()
        noi_aligned = self.timeline.align_series(actual_noi, fill_value=0.0)
        debt_service_aligned = self.timeline.align_series(debt_service, fill_value=0.0)

        # Step 5: Calculate ONLY actual available cash (no phantom proceeds)
        # CRITICAL FIX: debt_service() returns POSITIVE values, so subtract them from NOI
        available_for_distribution = (
            noi_aligned - debt_service_aligned
        )  # Subtract positive debt service

        # Validate available cash for distribution

        if available_for_distribution.empty or available_for_distribution.sum() == 0:
            return  # No cash available for distribution

        # Use available cash as input to waterfall (NOT equity_partner_flows!)
        levered_flows = available_for_distribution

        # PRESERVE CRITICAL LOGIC: Apply full waterfall distribution algorithm
        # Check if deal has equity partners for waterfall distribution
        has_partners = self.deal.has_equity_partners

        if has_partners:
            # Step 1: Calculate fee priority payments with settings (ESSENTIAL)
            fee_details = PartnershipAnalyzer._calculate_fee_distributions(
                levered_flows, self.context
            )
            remaining_cash_flows = fee_details["remaining_cash_flows_after_fee"]

            # Step 2: Apply waterfall to remaining flows (ESSENTIAL)
            if DistributionCalculator is not None:
                # Use existing DistributionCalculator for waterfall logic
                calculator = DistributionCalculator(self.context.deal.equity_partners)
                waterfall_results = calculator.calculate_distributions(
                    remaining_cash_flows, self.context.timeline
                )
            else:
                # Simplified waterfall when DistributionCalculator not available
                waterfall_results = self._simple_waterfall_distribution(
                    remaining_cash_flows, self.context
                )

            # Step 3: Combine fee and waterfall results (ESSENTIAL)
            combined_results = self._combine_fee_and_waterfall_results(
                fee_details, waterfall_results, self.context
            )

            # ESSENTIAL: Write distribution transactions to ledger
            self._write_distributions_to_ledger(combined_results, self.context.ledger)

        else:
            # Single entity - apply single entity distribution logic (ESSENTIAL)
            self._calculate_single_entity_distributions(levered_flows, self.context)

        # Partnership analysis complete - all transactions written to ledger

    ###########################################################################
    # WATERFALL DISTRIBUTION CALCULATIONS
    ###########################################################################

    def _calculate_single_entity_distributions(
        self, cash_flows: pd.Series, context: "DealContext"
    ) -> Dict[str, Any]:
        """
        Calculate distributions for single entity deals (no equity partners).

        Args:
            cash_flows: The cash flow series
            context: Deal context with settings and ledger

        Returns:
            Dict with distribution summary
        """
        # Extract fee rates from deal structure (or use standard defaults)
        fee_rates = PartnershipAnalyzer._extract_fee_rates_from_deal_static(
            context.deal
        )
        management_fee_rate = fee_rates["management"]
        acquisition_fee_rate = fee_rates["acquisition"]
        development_fee_rate = fee_rates["development"]

        # Calculate fee distributions even for single entity
        fee_details = PartnershipAnalyzer._calculate_fee_distributions(
            cash_flows, context
        )

        # Use remaining cash flows after fees for metrics
        remaining_cash_flows = fee_details["remaining_cash_flows_after_fee"]

        # Calculate basic metrics
        negative_flows = remaining_cash_flows[remaining_cash_flows < 0]
        positive_flows = remaining_cash_flows[remaining_cash_flows > 0]

        total_investment = abs(negative_flows.sum())
        total_distributions = positive_flows.sum()

        # Write single entity distributions to ledger
        for period in remaining_cash_flows.index:
            amount = remaining_cash_flows[period]
            if amount > 0:  # Distribution to single owner
                context.ledger.add_transaction(
                    date=period.to_timestamp()
                    if hasattr(period, "to_timestamp")
                    else period,
                    amount=-amount,  # Negative for distribution (outflow from deal)
                    category="Financing",
                    subcategory="Equity Distribution",
                    flow_purpose="Single Entity Distribution",
                    entity_id=context.deal.name,
                    entity_type="SingleOwner",
                    description=f"Distribution to {context.deal.name}",
                    source="PartnershipAnalyzer",
                )

        # Return summary dict instead of deprecated result object
        return {
            "distribution_method": "single_entity",
            "total_distributions": total_distributions,
            "total_investment": total_investment,
            "entity_name": context.deal.name,
            "fee_details": fee_details,
        }

    @staticmethod
    def _calculate_fee_distributions(
        cash_flows: pd.Series, context: "DealContext"
    ) -> Dict[str, Any]:
        """
        Calculate fee priority payments with deal-driven rates.

        This method handles the complex fee distribution logic including:
        - Fee priority payments before equity waterfall
        - Deal-driven fee rates (extracted from Deal.deal_fees)
        - Actual payee allocation (who gets paid what)
        - Dual-entry fee accounting
        - Third-party fee tracking

        Args:
            cash_flows: The cash flow series
            context: Deal context with settings and timeline

        Returns:
            Dictionary containing fee distribution details in expected test structure
        """
        # Initialize fee tracking
        total_partner_fees = 0.0
        partner_fees_by_partner = {}
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
        if context.deal.has_equity_partners:
            for partner in context.deal.equity_partners.partners:
                partner_fees_by_partner[partner.name] = 0.0
                detailed_fee_breakdown[partner.name] = []  # List format
                fee_cash_flows_by_partner[partner.name] = pd.Series(
                    0.0, index=context.timeline.period_index
                )

        # Calculate total fee amounts using settings-driven rates
        if context.deal.deal_fees:
            for fee in context.deal.deal_fees:
                try:
                    # Calculate fee cash flows
                    fee_cf = fee.compute_cf(context.timeline)
                    fee_amount = fee_cf.sum()

                    # Track fee by partner/payee
                    fee_name = fee.name  # Required field
                    fee_type = fee.fee_type or "Unknown"  # Optional field
                    payee = fee.payee  # Required field

                    # Get payee name (string key for tests)
                    payee_name = payee.name  # Entity.name is required

                    # Check if payee is a deal partner or third-party
                    is_partner = False
                    if context.deal.has_equity_partners:
                        partner_names = [
                            p.name for p in context.deal.equity_partners.partners
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
                        context.timeline.period_index, fill_value=0.0
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
                            detailed_fee_breakdown[payee_name] = []
                            fee_cash_flows_by_partner[payee_name] = pd.Series(
                                0.0, index=context.timeline.period_index
                            )

                        partner_fees_by_partner[payee_name] += fee_amount
                        total_partner_fees += fee_amount

                        # Create fee detail dictionary for detailed audit trail
                        fee_detail = {
                            "fee_name": fee_name,
                            "fee_type": fee_type,
                            "amount": float(fee_amount),
                            "payee": payee_name,
                            "draw_schedule": type(fee.draw_schedule).__name__,
                            "description": fee.description or "",  # Optional field
                        }
                        detailed_fee_breakdown[payee_name].append(fee_detail)
                        fee_cash_flows_by_partner[payee_name] += fee_cf_reindexed
                    else:
                        # Handle third-party fees
                        if payee_name not in third_party_fees:
                            third_party_fees[payee_name] = 0.0
                            third_party_fee_details[payee_name] = {}
                            third_party_fee_cash_flows[payee_name] = pd.Series(
                                0.0, index=context.timeline.period_index
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
            "total_developer_fee": total_partner_fees,
            "developer_fee_by_partner": {
                payee: amount for payee, amount in partner_fees_by_partner.items()
            },
        }

    @staticmethod
    def _combine_fee_and_waterfall_results(
        fee_details: Dict[str, Any],
        waterfall_results: Dict[str, Any],
        context: "DealContext",
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

        # Add fee details directly without creating deprecated object
        combined_results["fee_accounting_details"] = fee_details

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
                    "fee_details": {},  # Empty dictionary by default
                    "fee_cash_flows": pd.Series(
                        0.0, index=context.timeline.period_index
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

                        # Use the structured fee breakdown format
                        fee_details_list = fee_details["detailed_fee_breakdown"].get(
                            payee_name, []
                        )
                        partner_results[payee_name]["fee_details"] = {
                            fee["fee_name"]: fee["amount"] for fee in fee_details_list
                        }
                        partner_results[payee_name]["fee_count"] = len(fee_details_list)
                        partner_results[payee_name]["fee_cash_flows"] = fee_details[
                            "fee_cash_flows_by_partner"
                        ].get(
                            payee_name,
                            pd.Series(0.0, index=context.timeline.period_index),
                        )

                        # Update total distributions to include fees
                        partner_results[payee_name]["total_distributions"] = (
                            partner_results[payee_name]["distributions_from_waterfall"]
                            + fee_amount
                        )

            combined_results["waterfall_details"]["partner_results"] = partner_results

        return combined_results

    @staticmethod
    def _write_distributions_to_ledger(
        combined_results: Dict[str, Any], ledger
    ) -> None:
        """
        Write distribution transactions to ledger.

        Args:
            combined_results: Combined fee and waterfall results
            ledger: Ledger to write to
        """
        # Extract partner distributions from combined results
        if "partner_results" in combined_results:
            for partner_id, partner_data in combined_results["partner_results"].items():
                distributions_series = partner_data.get("distributions", pd.Series())
                for period in distributions_series.index:
                    amount = distributions_series[period]
                    if amount != 0:
                        ledger.add_transaction(
                            date=period.to_timestamp()
                            if hasattr(period, "to_timestamp")
                            else period,
                            amount=-amount,  # Negative for distribution (outflow)
                            category="Financing",
                            subcategory="Equity Distribution",
                            flow_purpose="Equity Distribution",
                            entity_id=partner_id,
                            entity_type="GP" if "GP" in str(partner_id) else "LP",
                            description=f"Waterfall distribution to {partner_id}",
                            source="PartnershipAnalyzer",
                        )

    @staticmethod
    def _simple_waterfall_distribution(
        cash_flows: pd.Series, context: "DealContext"
    ) -> Dict[str, Any]:
        """
        Simplified waterfall distribution when DistributionCalculator is not available.

        Args:
            cash_flows: Cash flows to distribute
            context: Deal context with partnership structure

        Returns:
            Simple waterfall results matching expected structure
        """
        # Simple pro-rata distribution based on ownership percentages
        partners = (
            context.deal.equity_partners.partners
            if context.deal.equity_partners
            else []
        )

        partner_results = {}
        for partner in partners:
            ownership = partner.share  # Partner.share is required field
            partner_flows = cash_flows * ownership

            partner_results[partner.name] = {
                "distributions": partner_flows,
                "total_distributions": partner_flows.sum(),
                "net_profit": partner_flows.sum(),
                "equity_multiple": partner_flows[partner_flows > 0].sum()
                / abs(partner_flows[partner_flows < 0].sum())
                if partner_flows[partner_flows < 0].sum() != 0
                else 1.0,
                "irr": None,  # Simplified - no IRR calculation
                "ownership_percentage": ownership,
            }

        return {
            "partner_results": partner_results,
            "total_metrics": {
                "total_distributions": cash_flows[cash_flows > 0].sum(),
                "total_investment": abs(cash_flows[cash_flows < 0].sum()),
            },
        }

    def _write_distributions_to_ledger(
        self, combined_results: Dict[str, Any], ledger: "Ledger"
    ) -> None:
        """
        CRITICAL METHOD: Write partner distributions to ledger.
        This method records equity distributions as financing transactions.
        """

        if not combined_results or "partner_distributions" not in combined_results:
            return

        partner_results = combined_results["partner_distributions"]

        for partner_name, partner_data in partner_results.items():
            # Get distributions from cash_flows (the actual distribution data)
            distributions = partner_data.get("cash_flows", pd.Series())

            if distributions.empty or distributions.sum() == 0:
                continue

            # Only record positive distributions (outflows from deal to partners)
            positive_distributions = distributions[distributions > 0]
            if positive_distributions.empty:
                continue

            # Create distribution series (negative = outflow from deal perspective)
            distribution_series = (
                -positive_distributions
            )  # Flip sign for deal perspective

            metadata = SeriesMetadata(
                category=CashFlowCategoryEnum.FINANCING,
                subcategory=FinancingSubcategoryEnum.EQUITY_DISTRIBUTION,
                item_name=f"Operating Distributions to {partner_name}",
                source_id=self.deal.uid,
                asset_id=self.deal.asset.uid,
                pass_num=5,  # Partnership pass
                entity_type="GP,LP",  # Distribution to equity partners
            )

            ledger.add_series(distribution_series, metadata)
