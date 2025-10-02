# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Deal results accessors (ledger-driven).

This module exposes a clean, flat API for deal-level results that delegates
data access to `LedgerQueries` and calculations to `FinancialCalculations`.
It contains no business logic of its own and serves as a thin orchestration
layer for ease of use and IDE discoverability.
"""

from __future__ import annotations

from functools import cached_property
from typing import Any, Dict, Optional
from uuid import UUID

import pandas as pd

from ..core.calculations import FinancialCalculations
from ..core.ledger import Ledger
from ..core.ledger.queries import LedgerQueries
from ..core.primitives import (
    CashFlowCategoryEnum,
    Timeline,
    UnleveredAggregateLineKey,
)
from ..reporting.interface import ReportingInterface
from .deal import Deal


class DealResults:  # noqa: PLR0904
    """
    Flat, ledger-driven API for deal analysis results.

    Principles:
    - Flat accessors (e.g., `levered_irr`, `equity_multiple`)
    - Delegation: data via `LedgerQueries`, math via `FinancialCalculations`
    - No calculation logic in this class
    """

    def __init__(self, deal: Deal, timeline: Timeline, ledger: Ledger):
        """
        Initialize with deal components and populated ledger.

        Args:
            deal: Deal configuration and parameters
            timeline: Analysis timeline
            ledger: POPULATED ledger with all transactions
        """
        self._deal = deal
        self._timeline = timeline
        self._ledger = ledger
        self._queries = LedgerQueries(ledger)

    # ==========================================================================
    # DIRECT DATA ACCESS
    # ==========================================================================

    @property
    def deal(self) -> "Deal":
        """Access to the original deal configuration."""
        return self._deal

    @property
    def timeline(self) -> "Timeline":
        """Analysis timeline."""
        return self._timeline

    @property
    def ledger_df(self) -> pd.DataFrame:
        """Direct access to the ledger DataFrame for reporting and analysis."""
        return self._ledger.ledger_df()

    @property
    def queries(self):
        """Direct access to ledger queries for advanced analysis."""
        return self._queries

    # ==========================================================================
    # PRIMARY METRICS
    # ==========================================================================

    @cached_property
    def levered_irr(self) -> Optional[float]:
        """THE primary return metric - levered IRR to aggregate equity."""
        return FinancialCalculations.calculate_irr(self.levered_cash_flow)

    @cached_property
    def equity_multiple(self) -> Optional[float]:
        """THE primary multiple metric - total returns / total investment."""
        # Use actual equity flows from ledger, not UCF/LCF
        # UCF assumes 100% equity, but we need actual equity invested
        contributions = self._queries.ledger[
            self._queries.ledger["subcategory"] == "Equity Contribution"
        ]["amount"].sum()

        distributions = self._queries.ledger[
            self._queries.ledger["subcategory"] == "Equity Distribution"
        ]["amount"].sum()

        if contributions <= 0:
            return None  # No equity investment to measure against

        return abs(distributions) / contributions

    @cached_property
    def net_profit(self) -> float:
        """Net profit to aggregate equity partners."""
        return self.levered_cash_flow.sum()

    # ==========================================================================
    # TIME SERIES
    # ==========================================================================

    @cached_property
    def levered_cash_flow(self) -> pd.Series:
        """
        Project-level cash flows after debt service effects (foundation for levered_irr).

        This represents the project's net cash requirements after debt service payments.
        Industry standard formula: LCF = UCF - Debt Service

        This is PROJECT-level analysis, not partner-level distributions.
        """
        # Get project cash flows and debt service
        project_cf = self._queries.project_cash_flow()
        debt_service = self._queries.debt_service()

        # Calculate levered cash flow (debt service is already negative)
        levered_cf = project_cf + debt_service

        # Align with timeline
        return self._timeline.align_series(levered_cf, fill_value=0.0)

    @cached_property
    def equity_cash_flow(self) -> pd.Series:
        """
        Partner-level equity cash flows (investor perspective).

        This represents actual cash flows to/from equity partners including:
        - Equity contributions (negative to investors)
        - Operating distributions (positive to investors)
        - Disposition distributions (positive to investors)

        This is PARTNER-level analysis for equity investor returns.
        """
        # Query equity partner flows and flip to investor perspective
        flows = self._queries.equity_partner_flows()
        # CRITICAL: Flip sign for investor perspective (contributions negative, distributions positive)
        investor_flows = -1 * flows

        # Align with timeline
        return self._timeline.align_series(investor_flows, fill_value=0.0)

    @cached_property
    def unlevered_cash_flow(self) -> pd.Series:
        """
        Project-level cash flow before debt effects (industry standard definition).

        ALWAYS includes:
        - Operational cash flows (NOI - CapEx - TI - LC)
        - Capital outflows: acquisition costs, construction costs
        - Capital inflows: disposition/sale proceeds

        This is the standard real estate definition of UCF.
        """
        flows = self._queries.project_cash_flow()
        return flows.reindex(self._timeline.period_index, fill_value=0.0)

    @cached_property
    def noi(self) -> pd.Series:
        """Net Operating Income time series."""
        flows = self._queries.noi()
        return flows.reindex(self._timeline.period_index, fill_value=0.0)

    @cached_property
    def operational_cash_flow(self) -> pd.Series:
        """Pure operational cash flows (NOI minus capex)."""
        flows = self._queries.operational_cash_flow()
        return flows.reindex(self._timeline.period_index, fill_value=0.0)

    @cached_property
    def debt_service(self) -> pd.Series:
        """Total debt service series."""
        flows = self._queries.debt_service()
        return flows.reindex(self._timeline.period_index, fill_value=0.0)

    # REMOVED: asset_value() - ambiguous "latest" concept replaced with explicit methods:
    #   - asset_value_at(date) for specific dates
    #   - disposition_valuation for exit value
    #   - refi_valuation for refinancing value
    #   - asset_valuations for complete time series

    def asset_value_at(self, date: pd.Period) -> float:
        """
        NON-CASH asset valuation as of specific date.

        These are analytical snapshots recorded for audit trail,
        not cash transactions.

        Args:
            date: Target date for valuation lookup

        Returns:
            NON-CASH asset valuation as of the specified date

        Raises:
            ValueError: If no asset valuation found on or before the date

        Example:
            # Get non-cash valuation at refinancing
            refi_date = timeline.period_index[24]  # Month 24
            refi_value = results.asset_value_at(refi_date)  # Analytical snapshot
        """
        return self._queries.asset_value_at(date)

    @cached_property
    def asset_valuations(self) -> pd.Series:
        """
        NON-CASH valuation records for analytical purposes.

        These are calculated property valuations recorded for audit trail
        and reporting - NOT cash transactions.

        Returns:
            Time series of NON-CASH asset valuations indexed by date

        Raises:
            ValueError: If no asset valuations found in ledger

        Example:
            valuations = results.asset_valuations  # Non-cash analytical records
            print(f"Valuations: {len(valuations)} entries")
            print(f"Range: {valuations.min():,.0f} to {valuations.max():,.0f}")
        """
        return self._queries.asset_valuations()

    # ==========================================================================
    # CONVENIENT ASSET VALUATION PROPERTIES (POC)
    # ==========================================================================

    @cached_property
    def acquisition_valuation(self) -> Optional[float]:
        """
        Asset valuation at acquisition (if recorded).

        Returns:
            Asset value at or near acquisition date, None if not found

        Note:
            This is a convenience property that may be too limiting for complex deals.
            Use asset_value_at() for more precise date control.
        """
        try:
            # Use acquisition date from deal
            acq_date = pd.Period(
                self._deal.acquisition.acquisition_date, freq=self._timeline.frequency
            )
            return self._queries.asset_value_at(acq_date)
        except (ValueError, AttributeError):
            return None

    @cached_property
    def refi_valuation(self) -> Optional[float]:
        """
        Asset valuation for refinancing purposes (if applicable).

        Returns:
            Conservative valuation used for refinancing, None if not found

        Note:
            This is a convenience property that may be too limiting for complex deals
            with multiple refinancings. Use asset_value_at() for more precise control.
        """
        try:
            # Look for refinancing around the middle of the timeline (typical timing)
            mid_period = len(self._timeline.period_index) // 2
            target_date = self._timeline.period_index[mid_period]
            return self._queries.asset_value_at(target_date)
        except (ValueError, IndexError):
            return None

    @cached_property
    def disposition_valuation(self) -> Optional[float]:
        """
        Asset valuation at disposition/exit (if recorded).

        Returns:
            Market valuation used for disposition, None if not found

        Note:
            This is a convenience property that may be too limiting for complex deals.
            Use asset_value_at() for more precise date control.
        """
        try:
            # Use the last few periods of the timeline (typical disposition timing)
            final_periods = self._timeline.period_index[-3:]  # Last 3 periods

            for period in reversed(final_periods):  # Check from most recent backwards
                try:
                    return self._queries.asset_value_at(period)
                except ValueError:
                    continue

            # If no valuation in final periods, return None
            return None
        except (ValueError, IndexError):
            return None

    # ==========================================================================
    # UNLEVERED METRICS (Asset-level perspective)
    # ==========================================================================

    @cached_property
    def unlevered_irr(self) -> Optional[float]:
        """IRR of the property as if purchased all-cash."""
        return FinancialCalculations.calculate_irr(self.unlevered_cash_flow)

    @cached_property
    def unlevered_return_on_cost(self) -> Optional[float]:
        """Unlevered equity multiple (return on total project cost)."""
        return FinancialCalculations.calculate_equity_multiple(self.unlevered_cash_flow)

    # ==========================================================================
    # DEBT METRICS
    # ==========================================================================

    @cached_property
    def minimum_dscr(self) -> Optional[float]:
        """Minimum Debt Service Coverage Ratio across all periods."""
        dscr_series = self._calculate_dscr_series()
        return dscr_series.min() if not dscr_series.empty else None

    @cached_property
    def average_dscr(self) -> Optional[float]:
        """Average Debt Service Coverage Ratio across periods with debt."""
        dscr_series = self._calculate_dscr_series()
        # Only average periods with actual debt service
        non_zero_dscr = dscr_series[dscr_series > 0]
        return non_zero_dscr.mean() if not non_zero_dscr.empty else None

    @cached_property
    def dscr_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive DSCR metrics including covenant monitoring.

        THIS IS CRITICAL FOR LENDER COVENANT MONITORING!

        Returns:
            Dict containing:
            - dscr_series: Full time series of DSCR values
            - minimum_dscr: Minimum DSCR value
            - average_dscr: Average DSCR value
            - covenant_analysis: Periods below various thresholds
            - trend_direction: Whether DSCR is improving/declining
        """
        # Calculate DSCR series directly from ledger (no circular dependencies)
        dscr_series = self._calculate_dscr_series()

        if dscr_series.empty or dscr_series.sum() == 0:
            return {
                "dscr_series": None,
                "minimum_dscr": None,
                "average_dscr": None,
                "median_dscr": None,
                "covenant_analysis": {},
                "trend_slope": None,
                "trend_direction": None,
            }

        # Calculate comprehensive metrics directly
        non_zero_dscr = dscr_series[dscr_series > 0]

        return {
            "dscr_series": dscr_series,
            "minimum_dscr": float(dscr_series.min()) if not dscr_series.empty else None,
            "average_dscr": float(non_zero_dscr.mean())
            if not non_zero_dscr.empty
            else None,
            "median_dscr": float(dscr_series.median())
            if not dscr_series.empty
            else None,
            "covenant_analysis": self._calculate_covenant_analysis(dscr_series),
            "trend_slope": self._calculate_dscr_trend_slope(dscr_series),
            "trend_direction": self._determine_dscr_trend_direction(dscr_series),
        }

    def _calculate_dscr_series(self) -> pd.Series:
        """Calculate DSCR for each period with comprehensive coverage."""
        noi_series = self.noi
        debt_service_series = self._queries.debt_service()

        # Align indices
        index = self._timeline.period_index
        noi_series = noi_series.reindex(index, fill_value=0.0)
        debt_service_series = debt_service_series.reindex(index, fill_value=0.0)

        # Calculate DSCR period by period
        dscr_series = pd.Series(0.0, index=index)
        for period in index:
            dscr_value = FinancialCalculations.calculate_dscr(
                noi_series[period], debt_service_series[period]
            )
            dscr_series[period] = dscr_value if dscr_value is not None else 0.0

        return dscr_series

    def _calculate_covenant_analysis(self, dscr_series: pd.Series) -> Dict[str, Any]:
        """Calculate covenant analysis for common DSCR thresholds."""
        if dscr_series.empty:
            return {}

        # Common commercial real estate covenant thresholds
        thresholds = [1.0, 1.1, 1.15, 1.2, 1.25, 1.3, 1.35, 1.4, 1.5]

        covenant_analysis = {}
        for threshold in thresholds:
            below_threshold = dscr_series < threshold
            periods_below = below_threshold.sum()
            consecutive_periods = self._find_max_consecutive_periods_below_threshold(
                dscr_series, threshold
            )

            covenant_analysis[f"below_{threshold}"] = {
                "periods_count": int(periods_below),
                "percentage": float(periods_below / len(dscr_series) * 100)
                if len(dscr_series) > 0
                else 0.0,
                "max_consecutive": int(consecutive_periods),
            }

        return covenant_analysis

    def _find_max_consecutive_periods_below_threshold(
        self, dscr_series: pd.Series, threshold: float
    ) -> int:
        """Find maximum consecutive periods below a given threshold."""
        if dscr_series.empty:
            return 0

        below_threshold = dscr_series < threshold
        max_consecutive = 0
        current_consecutive = 0

        for is_below in below_threshold:
            if is_below:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 0

        return max_consecutive

    def _calculate_dscr_trend_slope(self, dscr_series: pd.Series) -> Optional[float]:
        """Calculate the trend slope of DSCR over time."""
        if dscr_series.empty or len(dscr_series) < 2:
            return None

        # Simple linear regression slope
        non_zero_periods = dscr_series[dscr_series > 0]
        if len(non_zero_periods) < 2:
            return None

        x = range(len(non_zero_periods))
        y = non_zero_periods.values

        # Calculate slope using least squares
        n = len(x)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(x[i] * y[i] for i in range(n))
        sum_x2 = sum(x[i] ** 2 for i in range(n))

        if n * sum_x2 - sum_x * sum_x == 0:
            return None

        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
        return float(slope)

    def _determine_dscr_trend_direction(self, dscr_series: pd.Series) -> Optional[str]:
        """Determine if DSCR trend is improving, declining, or stable."""
        slope = self._calculate_dscr_trend_slope(dscr_series)

        if slope is None:
            return None
        elif slope > 0.01:  # Threshold for meaningful improvement
            return "improving"
        elif slope < -0.01:  # Threshold for meaningful decline
            return "declining"
        else:
            return "stable"

    # ==========================================================================
    # ARCHETYPE DETECTION
    # ==========================================================================

    @cached_property
    def archetype(self) -> str:
        """
        Deal archetype: Development, Value-Add, or Stabilized.

        Determined from ledger transaction patterns.
        """
        if self._queries.ledger.empty:
            return "Stabilized"

        # Check for construction transactions (Development)
        construction_mask = (
            self._queries.ledger["subcategory"]
            .astype(str)
            .str.contains("Hard Costs|Soft Costs|Construction", case=False, na=False)
        )
        if construction_mask.any():
            return "Development"

        # Check for capital improvements (Value-Add)
        capital_mask = (
            self._queries.ledger["category"] == CashFlowCategoryEnum.CAPITAL
        ) & ~construction_mask

        if capital_mask.any():
            # Has capital spending but not construction
            capital_amount = abs(self._queries.ledger[capital_mask]["amount"].sum())
            # Value-Add typically has significant capital (>5% of acquisition)
            acquisition_mask = (
                self._queries.ledger["flow_purpose"] == "Acquisition Cost"
            )
            if acquisition_mask.any():
                acquisition_amount = abs(
                    self._queries.ledger[acquisition_mask]["amount"].sum()
                )
                if capital_amount > acquisition_amount * 0.05:
                    return "Value-Add"

        # Default to Stabilized
        return "Stabilized"

    # ==========================================================================
    # PARTNERSHIP ACCESS
    # ==========================================================================

    @cached_property
    def partners(self) -> Dict[str, "PartnerMetrics"]:
        """
        Partner-level metrics for ALL partners.

        Returns dictionary keyed by partner ID.
        """
        partner_dict = {}

        # Get unique partner IDs from ledger
        partner_mask = self._queries.ledger["entity_type"].isin(["GP", "LP"])
        if partner_mask.any():
            unique_partners = self._queries.ledger[partner_mask]["entity_id"].unique()

            for partner_id in unique_partners:
                partner_dict[partner_id] = PartnerMetrics(
                    partner_id=partner_id, ledger=self._ledger, timeline=self._timeline
                )

        return partner_dict

    def partner(self, partner_id: str) -> "PartnerMetrics":
        """Get metrics for a specific partner."""
        if partner_id not in self.partners:
            raise KeyError(f"Partner '{partner_id}' not found in deal")
        return self.partners[partner_id]

    # ==========================================================================
    # LEGACY COMPATIBILITY INTERFACE
    # ==========================================================================

    def get_series(
        self, key: UnleveredAggregateLineKey, timeline: Timeline
    ) -> pd.Series:
        """
        Safely retrieves a cash flow series using a type-safe enum key.

        LEDGER-DRIVEN IMPLEMENTATION: Maps UnleveredAggregateLineKey values to
        corresponding LedgerQueries methods. This provides backward compatibility
        for existing code that used the old DataFrame-based approach.

        Args:
            key: UnleveredAggregateLineKey enum specifying which series to retrieve
            timeline: Timeline object providing the target period index for alignment

        Returns:
            pd.Series: The requested cash flow series, aligned to the timeline's period_index
                      and filled with zeros for missing periods

        Example:
            >>> noi_series = results.get_series(
            ...     UnleveredAggregateLineKey.NET_OPERATING_INCOME,
            ...     timeline
            ... )
        """
        # Map enum keys to LedgerQueries methods
        key_mapping = {
            UnleveredAggregateLineKey.NET_OPERATING_INCOME: self._queries.noi,
            UnleveredAggregateLineKey.EFFECTIVE_GROSS_INCOME: self._queries.egi,
            UnleveredAggregateLineKey.POTENTIAL_GROSS_REVENUE: self._queries.pgr,
            UnleveredAggregateLineKey.RENTAL_ABATEMENT: self._queries.rental_abatement,
            UnleveredAggregateLineKey.MISCELLANEOUS_INCOME: self._queries.misc_income,
            UnleveredAggregateLineKey.GENERAL_VACANCY_LOSS: self._queries.vacancy_loss,
            UnleveredAggregateLineKey.CREDIT_LOSS: self._queries.credit_loss,
            UnleveredAggregateLineKey.EXPENSE_REIMBURSEMENTS: self._queries.expense_reimbursements,
            UnleveredAggregateLineKey.TOTAL_OPERATING_EXPENSES: self._queries.opex,
            UnleveredAggregateLineKey.TOTAL_CAPITAL_EXPENDITURES: self._queries.capex,
        }

        # Get the query method for this key
        query_method = key_mapping.get(key)

        if query_method:
            try:
                # Call the LedgerQueries method and align to timeline
                series = query_method()
                return timeline.align_series(series, fill_value=0.0)
            except Exception:
                # Fallback to zero series if query fails
                pass

        # If key not found or query failed, return zero-filled series
        return pd.Series(0.0, index=timeline.period_index, name=key.value)

    @cached_property
    def asset_analysis(self):
        """
        Legacy compatibility adapter for reporting interface.

        Provides the asset_analysis interface expected by legacy reports.
        """

        class AssetAnalysisAdapter:
            def __init__(self, queries):
                self._queries = queries

            def get_ledger_queries(self):
                return self._queries

        return AssetAnalysisAdapter(self._queries)

    @cached_property
    def reporting(self) -> "ReportingInterface":
        """
        Provides access to standardized report formatters.

        This cached property exposes a fluent interface for generating various
        industry-standard reports from the analysis results.

        Returns:
            ReportingInterface instance for accessing reports (cached)

        Example:
            >>> results = analyze(deal, timeline)
            >>> pro_forma = results.reporting.pro_forma_summary()
            >>> sources_uses = results.reporting.sources_and_uses()
        """
        # Import here to avoid circular import
        return ReportingInterface(self)

    @cached_property
    def deal_metrics(self) -> Dict[str, Any]:
        """
        Aggregate deal-level performance metrics.

        Returns a dictionary containing all key deal metrics for backward compatibility.
        This aggregates the individual metric properties into a single object.
        """
        # Calculate total investment and distributions from equity partner flows
        equity_flows = self._queries.equity_partner_flows()
        contributions = self._queries.equity_contributions()

        # Total investment (contributions are positive from deal perspective)
        total_investment = contributions.sum() if not contributions.empty else 0.0

        # Total distributions (negative flows from equity_partner_flows)
        total_distributions = (
            equity_flows[equity_flows < 0].sum() * -1 if not equity_flows.empty else 0.0
        )

        return {
            "levered_irr": self.levered_irr,
            "unlevered_irr": self.unlevered_irr,
            "equity_multiple": self.equity_multiple,
            "unlevered_return_on_cost": self.unlevered_return_on_cost,
            "net_profit": self.net_profit,
            "minimum_dscr": self.minimum_dscr,
            "average_dscr": self.average_dscr,
            "total_investment": total_investment,
            "total_distributions": total_distributions,
        }

    @cached_property
    def deal_summary(self) -> Dict[str, Any]:
        """
        Deal metadata and summary information.

        Returns basic deal characteristics and metadata.
        """
        return {
            "deal_id": self._deal.uid,
            "deal_name": self._deal.name,
            "archetype": self.archetype,
            "asset_type": self._deal.asset.property_type.value,
            "acquisition_date": self._deal.acquisition.acquisition_date,
            "timeline_months": self._timeline.duration_months,
        }

    @cached_property
    def financing_analysis(self) -> Optional[Dict[str, Any]]:
        """
        Financing analysis summary.

        Returns None for all-equity deals, otherwise returns financing metrics.
        """
        if not self._deal.financing or not self._deal.financing.facilities:
            return None

        # If deal has financing facilities, return analysis even if debt service is zero
        # (debt service might be zero due to timing, interest-only periods, etc.)
        debt_service_series = self.debt_service

        return {
            "has_financing": True,
            "total_debt_service": debt_service_series.sum()
            if not debt_service_series.empty
            else 0.0,
            "minimum_dscr": self.minimum_dscr,
            "average_dscr": self.average_dscr,
            "facility_count": len(self._deal.financing.facilities),
            "dscr_metrics": self.dscr_metrics,
        }

    @cached_property
    def levered_cash_flows(self) -> pd.Series:
        """
        Alias for levered_cash_flow for backward compatibility.

        Many tests expect levered_cash_flows (plural) instead of levered_cash_flow (singular).
        """
        return self.levered_cash_flow

    @cached_property
    def partner_distributions(self) -> Dict[str, Any]:
        """
        Partnership distribution summary.

        Returns partnership metrics and distribution details.
        """
        if (
            not self._deal.equity_partners
            or len(self._deal.equity_partners.partners) <= 1
        ):
            return {
                "distribution_method": "single_entity",
                "partner_count": len(self._deal.equity_partners.partners)
                if self._deal.equity_partners
                else 0,
                "total_investment": self.deal_metrics.get("total_investment", 0.0),
                "total_distributions": self.deal_metrics.get(
                    "total_distributions", 0.0
                ),
                "equity_multiple": self.equity_multiple,
                "levered_irr": self.levered_irr,
            }

        # Multi-partner scenario
        partner_metrics = {}
        for partner_id, partner_info in self.partners.items():
            try:
                partner_metrics[partner_id] = {
                    "irr": partner_info.irr,
                    "equity_multiple": partner_info.equity_multiple,
                    "net_profit": partner_info.net_profit,
                }
            except (NotImplementedError, AttributeError):
                partner_metrics[partner_id] = {
                    "irr": None,
                    "equity_multiple": None,
                    "net_profit": 0.0,
                }

        return {
            "distribution_method": "partnership_waterfall",
            "partner_count": len(self._deal.equity_partners.partners),
            "partner_metrics": partner_metrics,
            "aggregate_irr": self.levered_irr,
            "aggregate_equity_multiple": self.equity_multiple,
        }

    def __repr__(self) -> str:
        """String representation showing key metrics."""
        try:
            irr_str = f"{self.levered_irr:.2%}" if self.levered_irr else "N/A"
            em_str = f"{self.equity_multiple:.2f}x" if self.equity_multiple else "N/A"
            return f"DealResults(levered_irr={irr_str}, equity_multiple={em_str})"
        except NotImplementedError:
            return "DealResults(metrics not yet implemented)"


class PartnerMetrics:
    """
    Individual partner analysis and metrics.

    Provides partner-specific calculations using the same engine as
    deal-level results for consistency.
    """

    def __init__(self, partner_id: str, ledger: Ledger, timeline: Timeline):
        """Initialize with partner ID and shared analysis components."""
        self.partner_id = partner_id
        self._ledger = ledger
        self._timeline = timeline
        self._queries = LedgerQueries(ledger)

    @cached_property
    def irr(self) -> Optional[float]:
        """Partner-specific IRR."""
        return FinancialCalculations.calculate_irr(self.cash_flow)

    @cached_property
    def equity_multiple(self) -> Optional[float]:
        """Partner-specific equity multiple."""
        return FinancialCalculations.calculate_equity_multiple(self.cash_flow)

    @cached_property
    def net_profit(self) -> float:
        """Partner-specific net profit."""
        return self.cash_flow.sum()

    @cached_property
    def cash_flow(self) -> pd.Series:
        """Partner-specific cash flow time series."""
        try:
            partner_uuid = (
                UUID(self.partner_id)
                if isinstance(self.partner_id, str)
                else self.partner_id
            )
            flows = self._queries.partner_flows(partner_uuid)
            return flows.reindex(self._timeline.period_index, fill_value=0.0)
        except:
            # Fallback: filter ledger directly by partner_id
            partner_mask = self._queries.ledger["entity_id"] == self.partner_id
            partner_txns = self._queries.ledger[partner_mask]
            if partner_txns.empty:
                return pd.Series(0.0, index=self._timeline.period_index)

            # Group by date and sum, then flip sign for investor perspective
            flows = partner_txns.groupby("date")["amount"].sum()
            flows = -1 * flows  # Flip for investor perspective
            return flows.reindex(self._timeline.period_index, fill_value=0.0)

    def __repr__(self) -> str:
        try:
            irr_str = f"{self.irr:.2%}" if self.irr else "N/A"
            return f"PartnerMetrics({self.partner_id}, irr={irr_str})"
        except NotImplementedError:
            return f"PartnerMetrics({self.partner_id}, not yet implemented)"
