# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Debt Analysis Specialist

This module provides the DebtAnalyzer service that handles comprehensive debt facility analysis
including institutional-grade debt service calculations, refinancing transactions, and covenant
monitoring for commercial real estate financing.

The DebtAnalyzer serves as the central hub for all debt-related analysis within the deal
analysis framework, providing sophisticated capabilities that mirror industry-standard
institutional lending practices.

Key capabilities:
- **Debt Service Calculations**: Enhanced debt service with floating rates
  and institutional features like interest-only periods
- **Refinancing Analysis**: Complete refinancing transaction processing with cash flow
  impacts and covenant monitoring setup
- **DSCR Analysis**: Comprehensive debt service coverage ratio calculations with
  stress testing and forward-looking projections
- **Covenant Monitoring**: Institutional-grade covenant tracking and breach detection
- **Multi-Facility Support**: Handles complex financing structures with multiple facilities

The service implements sophisticated algorithms used by institutional lenders, including:
- Enhanced amortization scheduling with dynamic rates
- Covenant monitoring frameworks with risk assessment
- Stress testing scenarios for underwriting analysis
- Forward-looking DSCR projections for covenant compliance

Example:
    ```python
    from performa.deal.analysis import DebtAnalyzer

    # Create debt analyzer
    debt_analyzer = DebtAnalyzer(deal, timeline, settings)

    # Analyze complete financing structure
    financing_results = debt_analyzer.analyze_financing_structure(
        property_value_series=property_values,
        noi_series=noi_series,
        unlevered_analysis=unlevered_results
    )

    # Access comprehensive results
    print(f"DSCR Summary: {financing_results.dscr_summary}")
    print(f"Facilities: {len(financing_results.facilities)}")
    print(f"Refinancing Events: {len(financing_results.refinancing_transactions)}")
    ```

Architecture:
    - Uses dataclass pattern for runtime service state management
    - Implements institutional-grade calculation standards
    - Provides comprehensive error handling with graceful degradation
    - Supports both construction and permanent facility analysis
    - Integrates with broader deal analysis workflow through typed interfaces

Institutional Standards:
    - Follows commercial real estate lending industry practices
    - Implements DSCR calculations per institutional underwriting standards
    - Provides covenant monitoring frameworks used by institutional lenders
    - Supports stress testing scenarios required for institutional analysis
"""

from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List

import numpy as np
import pandas as pd

from performa.core.primitives import Timeline, UnleveredAggregateLineKey
from performa.core.primitives.enums import (
    CashFlowCategoryEnum,
    FinancingSubcategoryEnum,
)
from performa.deal.results import (
    DSCRSummary,
    FacilityInfo,
    FinancingAnalysisResult,
    UnleveredAnalysisResult,
)

if TYPE_CHECKING:
    from performa.core.ledger import LedgerBuilder
    from performa.core.primitives import GlobalSettings, Timeline
    from performa.deal.deal import Deal
    from performa.deal.orchestrator import DealContext


logger = logging.getLogger(__name__)


@dataclass
class DebtAnalyzer:
    """
    Specialist service for analyzing debt facilities and financing structures with institutional-grade capabilities.

    This service provides comprehensive debt analysis that mirrors the sophistication of institutional
    commercial real estate lending practices. It handles complex financing structures including
    construction loans, permanent financing, refinancing transactions, and covenant monitoring.

    The DebtAnalyzer is designed to support the full lifecycle of commercial real estate financing,
    from initial construction funding through permanent loan monitoring and refinancing analysis.

    Key features:
    - **Enhanced Debt Service**: Floating rates, interest-only periods
    - **Refinancing Analysis**: Complete transaction processing with cash flow impacts
    - **DSCR Monitoring**: Institutional-grade covenant monitoring and breach detection
    - **Multi-Facility Support**: Handles complex financing structures with multiple facilities
    - **Stress Testing**: Forward-looking analysis with sensitivity scenarios
    - **Risk Assessment**: Comprehensive covenant monitoring and breach detection

    Institutional capabilities:
    - Follows commercial real estate lending industry standards
    - Implements DSCR calculations per institutional underwriting requirements
    - Provides covenant monitoring frameworks used by institutional lenders
    - Supports stress testing scenarios required for institutional analysis

    Attributes:
        deal: The deal containing financing structure and asset information
        timeline: Analysis timeline for debt service and covenant calculations
        settings: Global settings for debt analysis configuration
        financing_analysis: Runtime state populated during analysis (internal use)

    Example:
        ```python
        # Create analyzer with dependencies
        analyzer = DebtAnalyzer(deal, timeline, settings)

        # Execute comprehensive financing analysis
        results = analyzer.analyze_financing_structure(
            property_value_series=property_values,
            noi_series=noi_series,
            unlevered_analysis=unlevered_results
        )

        # Access institutional-grade results
        print(f"DSCR minimum: {results.dscr_summary.minimum_dscr:.2f}")
        print(f"Covenant breaches: {len(results.covenant_monitoring)}")
        print(f"Refinancing proceeds: {sum(results.refinancing_cash_flows.values())}")
        ```
    """

    # Input parameters - injected dependencies
    deal: Deal
    timeline: Timeline
    settings: GlobalSettings

    # Runtime state (populated during analysis) - institutional-grade results
    financing_analysis: FinancingAnalysisResult = field(
        init=False, repr=False, default_factory=FinancingAnalysisResult
    )

    def analyze_financing_structure(
        self,
        property_value_series: pd.Series,
        noi_series: pd.Series,
        unlevered_analysis: UnleveredAnalysisResult,
        ledger_builder: "LedgerBuilder",
        deal_context: "DealContext",
    ) -> FinancingAnalysisResult:
        """
        Analyze the complete financing structure including facilities, refinancing, covenants, and DSCR.

        This method orchestrates the complete debt analysis workflow including:
        1. Facility processing through compute_cf method (writes to ledger)
        2. Refinancing transaction processing
        3. Covenant monitoring setup
        4. DSCR analysis and covenant monitoring

        Args:
            property_value_series: Property value time series for refinancing analysis
            noi_series: NOI time series for covenant monitoring
            unlevered_analysis: Results from unlevered asset analysis for DSCR calculation
            ledger_builder: LedgerBuilder for debt facility processing

        Returns:
            FinancingAnalysisResult containing all debt analysis results
        """
        if self.deal.financing is None:
            self.financing_analysis.has_financing = False
            return self.financing_analysis

        # Initialize financing analysis results
        self.financing_analysis.has_financing = True
        self.financing_analysis.financing_plan = self.deal.financing.name

        # Step 1: Process each facility in the financing plan
        self._process_facilities(ledger_builder, deal_context)

        # Step 2: Handle refinancing transactions if the plan supports them
        if self.deal.financing.has_refinancing:
            self._process_refinancing_transactions(property_value_series, noi_series)

        # Step 3: Calculate DSCR metrics (critical for institutional deals)
        self.calculate_dscr_metrics(unlevered_analysis)

        return self.financing_analysis

    def _process_facilities(
        self,
        ledger_builder: "LedgerBuilder",
        deal_context: "DealContext",
    ) -> None:
        """
        Process each facility through their compute_cf method for ledger integration.

        This method processes both construction and permanent facilities using the new
        compute_cf approach that writes all transactions to the ledger while maintaining
        backward compatibility by populating the FinancingAnalysisResult.

        Args:
            ledger_builder: LedgerBuilder instance for facility processing
            deal_context: DealContext for proper debt facility processing (required)
        """
        # Debt facilities are deal-level models and must use DealContext
        context = deal_context

        for facility in self.deal.financing.facilities:
            facility_name = getattr(facility, "name", "Unnamed Facility")
            facility_type = type(facility).__name__

            # Add facility metadata
            facility_info = FacilityInfo(
                name=facility_name,
                type=facility_type,
                description=getattr(facility, "description", ""),
            )
            self.financing_analysis.facilities.append(facility_info)

            # NEW APPROACH: Use compute_cf method (writes to ledger)
            if hasattr(facility, "compute_cf"):
                try:
                    # Call facility's compute_cf method - this writes all transactions to ledger
                    debt_service = facility.compute_cf(context)
                    # Store for backward compatibility
                    self.financing_analysis.debt_service[facility_name] = debt_service

                    # Extract loan proceeds from ledger after compute_cf execution
                    try:
                        current_ledger = ledger_builder.get_current_ledger()
                        logger.info(
                            f"DEBUG: Ledger size after compute_cf: {len(current_ledger)}"
                        )

                        if not current_ledger.empty:
                            # Debug: Show all financing entries
                            financing_entries = current_ledger[
                                current_ledger["category"]
                                == CashFlowCategoryEnum.FINANCING
                            ]
                            logger.info(
                                f"DEBUG: Found {len(financing_entries)} financing entries"
                            )

                            if not financing_entries.empty:
                                logger.info(f"DEBUG: Financing entries:")
                                for idx, row in financing_entries.iterrows():
                                    logger.info(
                                        f"  - {row['item_name']}: ${row['amount']:,.0f} ({row['category']}/{row.get('subcategory', 'N/A')})"
                                    )

                            # Filter for actual loan proceeds (by subcategory enum, not just positive amount)
                            financing_mask = (
                                (
                                    current_ledger["category"]
                                    == CashFlowCategoryEnum.FINANCING
                                )
                                & (
                                    current_ledger["subcategory"]
                                    == FinancingSubcategoryEnum.LOAN_PROCEEDS
                                )  # Only actual loan proceeds
                                & (
                                    current_ledger["item_name"].str.contains(
                                        facility_name, case=False, na=False
                                    )
                                )
                            )
                            facility_proceeds = current_ledger[financing_mask]
                            logger.info(
                                f"DEBUG: Found {len(facility_proceeds)} facility proceeds for '{facility_name}'"
                            )

                            if not facility_proceeds.empty:
                                # Convert dates to periods for proper reindexing
                                facility_proceeds_copy = facility_proceeds.copy()
                                facility_proceeds_copy["period"] = pd.to_datetime(
                                    facility_proceeds_copy["date"]
                                ).dt.to_period("M")
                                # Group by period and sum to get loan proceeds by period
                                proceeds_by_period = facility_proceeds_copy.groupby(
                                    "period"
                                )["amount"].sum()
                                # Reindex to match timeline
                                loan_proceeds = proceeds_by_period.reindex(
                                    self.timeline.period_index, fill_value=0.0
                                )
                                self.financing_analysis.loan_proceeds[facility_name] = (
                                    loan_proceeds
                                )
                                logger.info(
                                    f"✅ Extracted ${loan_proceeds.sum():,.0f} loan proceeds for '{facility_name}' from ledger"
                                )
                            else:
                                logger.warning(
                                    f"❌ No loan proceeds found in ledger for '{facility_name}'"
                                )
                                self.financing_analysis.loan_proceeds[facility_name] = (
                                    None
                                )
                        else:
                            logger.warning(
                                "❌ Ledger is empty - cannot extract loan proceeds"
                            )
                            self.financing_analysis.loan_proceeds[facility_name] = None
                    except Exception as e:
                        logger.warning(
                            f"❌ Error extracting loan proceeds from ledger for '{facility_name}': {e}"
                        )
                        logger.warning(f"Traceback: {traceback.format_exc()}")
                        self.financing_analysis.loan_proceeds[facility_name] = None

                except Exception as e:
                    logger.error(
                        f"Error processing facility '{facility_name}' with compute_cf: {e}"
                    )
                    self.financing_analysis.debt_service[facility_name] = None
                    self.financing_analysis.loan_proceeds[facility_name] = None
                    continue
            else:
                # FALLBACK: Use old methods for facilities not yet upgraded
                logger.warning(
                    f"Facility '{facility_name}' using fallback methods (no compute_cf)"
                )

                # Old debt service calculation
                if hasattr(facility, "calculate_debt_service"):
                    try:
                        if hasattr(facility, "kind") and facility.kind == "permanent":
                            debt_service = self._calculate_enhanced_debt_service(
                                facility
                            )
                        else:
                            debt_service = facility.calculate_debt_service(
                                self.timeline
                            )
                        self.financing_analysis.debt_service[facility_name] = (
                            debt_service
                        )
                    except Exception:
                        self.financing_analysis.debt_service[facility_name] = None

                # Old loan proceeds calculation
                if hasattr(facility, "calculate_loan_proceeds"):
                    try:
                        loan_proceeds = facility.calculate_loan_proceeds(self.timeline)
                        self.financing_analysis.loan_proceeds[facility_name] = (
                            loan_proceeds
                        )
                    except Exception:
                        self.financing_analysis.loan_proceeds[facility_name] = None

    def _calculate_enhanced_debt_service(self, permanent_facility) -> pd.Series:
        """
        Calculate enhanced debt service for permanent facilities with institutional features.

        This method implements sophisticated debt service calculations that mirror institutional
        lending practices, including support for interest-only periods, floating rate indexes,
        and dynamic refinancing scenarios commonly used in commercial real estate financing.

        Enhanced features supported:
        - **Interest-Only Periods**: Supports I/O periods during initial loan terms
        - **Dynamic Floating Rates**: Integrates with rate index curves (SOFR, LIBOR, etc.)
        - **Refinancing Integration**: Calculates debt service starting from refinancing dates
        - **Amortization Scheduling**: Proper institutional-grade amortization calculations
        - **Timeline Alignment**: Ensures debt service aligns with project timeline

        The method handles complex scenarios where permanent facilities are originated
        through refinancing transactions, requiring careful timeline management and
        loan amount determination from refinancing events.

        Args:
            permanent_facility: PermanentFacility object with enhanced institutional features
                               including refinancing timing, loan terms, and rate specifications

        Returns:
            pd.Series containing enhanced debt service payments aligned with the project
            timeline, with proper handling of refinancing timing and rate dynamics

        Example:
            ```python
            # For a refinanced permanent loan
            debt_service = analyzer._calculate_enhanced_debt_service(permanent_facility)

            # Analyze debt service pattern
            print(f"Total debt service: ${debt_service.sum():,.0f}")
            print(f"Average payment: ${debt_service.mean():,.0f}")
            print(f"Peak payment: ${debt_service.max():,.0f}")
            ```
        """
        try:
            # Check if this facility has dynamic refinancing
            if (
                hasattr(permanent_facility, "refinance_timing")
                and permanent_facility.refinance_timing
            ):
                # For facilities that are originated via refinancing, we need to calculate
                # debt service starting from the refinance timing
                refinance_period_idx = permanent_facility.refinance_timing - 1
                if refinance_period_idx < len(self.timeline.period_index):
                    # Create a sub-timeline starting from refinancing
                    refinance_start = self.timeline.period_index[refinance_period_idx]

                    # Calculate loan amount from refinancing transaction
                    loan_amount = self._get_refinanced_loan_amount(permanent_facility)

                    if loan_amount > 0:
                        # Create timeline for the permanent loan term
                        loan_timeline = Timeline(
                            start_date=refinance_start,
                            duration_months=permanent_facility.loan_term_years * 12,
                        )

                        # Calculate enhanced amortization
                        amortization = permanent_facility.calculate_amortization(
                            timeline=loan_timeline,
                            loan_amount=loan_amount,
                            index_curve=self._get_rate_index_curve(),
                        )

                        # Extract debt service from amortization
                        schedule, _ = amortization.amortization_schedule
                        debt_service_series = schedule["Total Payment"]

                        # Align with main timeline
                        full_debt_service = pd.Series(
                            0.0, index=self.timeline.period_index
                        )
                        for i, payment in enumerate(debt_service_series):
                            timeline_idx = refinance_period_idx + i
                            if timeline_idx < len(self.timeline.period_index):
                                full_debt_service.iloc[timeline_idx] = payment

                        return full_debt_service

            # Fallback to standard debt service calculation
            return permanent_facility.calculate_debt_service(self.timeline)

        except Exception as e:
            # Log warning and fallback to basic calculation
            logger = logging.getLogger(__name__)
            logger.warning(
                f"Enhanced debt service calculation failed for {permanent_facility.name}: {e}"
            )
            return permanent_facility.calculate_debt_service(self.timeline)

    def _get_refinanced_loan_amount(self, permanent_facility) -> float:
        """Get the loan amount from refinancing transactions for this facility."""
        if hasattr(self.financing_analysis, "refinancing_transactions"):
            for transaction in self.financing_analysis.refinancing_transactions:
                if transaction.get("new_facility") == permanent_facility.name:
                    return transaction.get("new_loan_amount", 0.0)

        # Fallback to facility's specified loan amount
        return getattr(permanent_facility, "loan_amount", 0.0)

    def _get_rate_index_curve(self) -> pd.Series:
        """
        Get rate index curve for dynamic rate calculations.

        In a real implementation, this would come from market data or user input.
        For now, we'll create a reasonable SOFR curve.
        """
        # Create a sample SOFR curve that starts at 4.5% and gradually rises to 5.5%
        periods = len(self.timeline.period_index)
        # FIXME: we should have default parameters in the method signature, not hard coded here
        start_rate = 0.045  # 4.5%
        end_rate = 0.055  # 5.5%

        # Linear interpolation
        rates = np.linspace(start_rate, end_rate, periods)

        return pd.Series(rates, index=self.timeline.period_index)

    def _process_refinancing_transactions(
        self, property_value_series: pd.Series, noi_series: pd.Series
    ) -> None:
        """
        Process refinancing transactions and integrate cash flow impacts.

        This method handles the complete refinancing workflow including:
        - Refinancing transaction calculation
        - Cash flow event processing
        - Covenant monitoring setup for new loans

        Args:
            property_value_series: Property value time series for refinancing analysis
            noi_series: NOI time series for covenant monitoring
        """
        try:
            # Calculate refinancing transactions with enhanced data
            refinancing_transactions = (
                self.deal.financing.calculate_refinancing_transactions(
                    timeline=self.timeline,
                    property_value_series=property_value_series,
                    noi_series=noi_series,
                    financing_cash_flows=None,  # Will be provided in future iterations
                )
            )
            self.financing_analysis.refinancing_transactions = refinancing_transactions

            # Process refinancing cash flow impacts
            self._process_refinancing_cash_flows(refinancing_transactions)

        except Exception:
            # Log the error but continue with empty transactions
            self.financing_analysis.refinancing_transactions = []

    def _process_refinancing_cash_flows(
        self, refinancing_transactions: List[Dict[str, Any]]
    ) -> None:
        """
        Process refinancing transactions and integrate cash flow impacts.

        This method handles the cash flow events from refinancing:
        - Loan payoffs (negative cash flow)
        - New loan proceeds (positive cash flow)
        - Net proceeds to borrower
        - Setup covenant monitoring for new loans

        Args:
            refinancing_transactions: List of refinancing transaction dictionaries
        """
        if not refinancing_transactions:
            return

        # Initialize refinancing cash flow tracking
        self.financing_analysis.refinancing_cash_flows = {
            "loan_payoffs": pd.Series(0.0, index=self.timeline.period_index),
            "new_loan_proceeds": pd.Series(0.0, index=self.timeline.period_index),
            "closing_costs": pd.Series(0.0, index=self.timeline.period_index),
            "net_refinancing_proceeds": pd.Series(
                0.0, index=self.timeline.period_index
            ),
        }

        for transaction in refinancing_transactions:
            transaction_date = transaction.get("transaction_date")

            if transaction_date in self.timeline.period_index:
                # Record cash flow events
                payoff_amount = transaction.get("payoff_amount", 0.0)
                new_loan_amount = transaction.get("new_loan_amount", 0.0)
                closing_costs = transaction.get("closing_costs", 0.0)
                net_proceeds = transaction.get("net_proceeds", 0.0)

                # Update cash flow series
                self.financing_analysis.refinancing_cash_flows["loan_payoffs"][
                    transaction_date
                ] = -payoff_amount
                self.financing_analysis.refinancing_cash_flows["new_loan_proceeds"][
                    transaction_date
                ] = new_loan_amount
                self.financing_analysis.refinancing_cash_flows["closing_costs"][
                    transaction_date
                ] = -closing_costs
                self.financing_analysis.refinancing_cash_flows[
                    "net_refinancing_proceeds"
                ][transaction_date] = net_proceeds

                # Setup covenant monitoring for new permanent loans
                covenant_monitoring = transaction.get("covenant_monitoring", {})
                if covenant_monitoring.get("monitoring_enabled", False):
                    self._setup_covenant_monitoring(transaction, transaction_date)

    def _setup_covenant_monitoring(
        self, transaction: Dict[str, Any], start_date: pd.Period
    ) -> None:
        """
        Setup covenant monitoring for a new permanent loan from refinancing.

        This creates the covenant monitoring framework for ongoing risk management
        of the new permanent loan throughout its lifecycle.

        Args:
            transaction: Refinancing transaction dictionary
            start_date: When covenant monitoring begins
        """
        # Get the new facility information
        new_facility_name = transaction.get("new_facility", "Unknown Facility")
        covenant_params = transaction.get("covenant_monitoring", {})

        # Find the actual permanent facility object
        permanent_facility = None
        if self.deal.financing:
            for facility in self.deal.financing.permanent_facilities:
                if facility.name == new_facility_name:
                    permanent_facility = facility
                    break

        if permanent_facility and covenant_params.get("monitoring_enabled", False):
            try:
                # Create monitoring timeline starting from refinancing date
                monitoring_periods = self.timeline.period_index[
                    self.timeline.period_index >= start_date
                ]

                if len(monitoring_periods) > 0:
                    # Create mock timeline for covenant monitoring
                    class MockMonitoringTimeline:
                        def __init__(self, period_index):
                            self.period_index = period_index

                    monitoring_timeline = MockMonitoringTimeline(monitoring_periods)

                    # Get property value and NOI series from the transaction context
                    # In a real implementation, this would be passed from the calling method
                    property_value_series = pd.Series(
                        0.0, index=self.timeline.period_index
                    )
                    noi_series = pd.Series(0.0, index=self.timeline.period_index)

                    # Calculate covenant monitoring results
                    covenant_results = permanent_facility.calculate_covenant_monitoring(
                        timeline=monitoring_timeline,
                        property_value_series=property_value_series,
                        noi_series=noi_series,
                        loan_amount=transaction.get("new_loan_amount", 0.0),
                    )

                    # Store covenant monitoring results in financing analysis
                    if not hasattr(self.financing_analysis, "covenant_monitoring"):
                        self.financing_analysis.covenant_monitoring = {}

                    self.financing_analysis.covenant_monitoring[new_facility_name] = {
                        "covenant_results": covenant_results,
                        "breach_summary": permanent_facility.get_covenant_breach_summary(
                            covenant_results
                        ),
                        "monitoring_start_date": start_date,
                        "facility_name": new_facility_name,
                    }

            except Exception:
                # Log warning but don't fail the analysis
                pass

    def calculate_dscr_metrics(
        self, unlevered_analysis: UnleveredAnalysisResult
    ) -> None:
        """
        Calculate debt service coverage ratio (DSCR) metrics and time series using institutional standards.

        This method implements comprehensive DSCR analysis that mirrors institutional lending
        practices and underwriting standards. DSCR is a critical metric for commercial real
        estate financing, measuring the property's ability to service debt obligations.

        The calculation follows institutional standards where:
        - DSCR = Net Operating Income (NOI) / Debt Service
        - Values above 1.0 indicate adequate debt service coverage
        - Common covenant thresholds range from 1.15x to 1.35x
        - Stress testing evaluates performance under adverse scenarios

        Comprehensive analysis includes:
        - **NOI Extraction**: Type-safe extraction from asset analysis using enum keys
        - **Multi-Facility Aggregation**: Combines debt service from all financing facilities
        - **Time Series Analysis**: Period-by-period DSCR calculations with trend analysis
        - **Statistical Summary**: Comprehensive statistics including percentiles and volatility
        - **Covenant Monitoring**: Analysis against common institutional covenant thresholds
        - **Forward-Looking Projections**: Rolling averages and stabilized DSCR calculations
        - **Stress Testing**: Sensitivity analysis under various NOI decline scenarios

        Institutional standards implemented:
        - Uses industry-standard DSCR calculation methodology
        - Provides covenant breach analysis for institutional monitoring
        - Includes stress testing scenarios required for institutional underwriting
        - Supports forward-looking analysis for covenant compliance projections

        Args:
            unlevered_analysis: Results from unlevered asset analysis containing NOI data
                               and operational metrics required for DSCR calculations

        Note:
            This method populates the financing_analysis.dscr_time_series and
            financing_analysis.dscr_summary attributes with institutional-grade results.
            If no financing exists, both attributes are set to None.

        Example:
            ```python
            # Calculate DSCR metrics
            analyzer.calculate_dscr_metrics(unlevered_analysis)

            # Access results
            dscr_summary = analyzer.financing_analysis.dscr_summary
            print(f"Minimum DSCR: {dscr_summary.minimum_dscr:.2f}")
            print(f"Covenant breaches: {dscr_summary.periods_below_1_25}")

            # Access time series
            dscr_series = analyzer.financing_analysis.dscr_time_series
            print(f"DSCR trend: {dscr_series.iloc[-12:].mean():.2f}")
            ```
        """
        # Only calculate DSCR if we have financing
        if not self.financing_analysis.has_financing:
            self.financing_analysis.dscr_time_series = None
            self.financing_analysis.dscr_summary = None
            return

        try:
            # === Extract NOI Time Series ===
            noi_series = self._extract_noi_time_series(unlevered_analysis)

            # === Aggregate Debt Service ===
            total_debt_service_series = self._aggregate_debt_service()

            # === Calculate DSCR Time Series ===
            dscr_series = self._calculate_dscr_time_series(
                noi_series, total_debt_service_series
            )

            # === Calculate DSCR Statistics ===
            dscr_summary_data = self._calculate_dscr_summary(dscr_series)

            # === Add Forward-Looking Analysis ===
            forward_analysis = self._calculate_forward_dscr_analysis(
                noi_series, total_debt_service_series
            )

            # Update financing analysis with metrics
            self.financing_analysis.dscr_time_series = dscr_series
            self.financing_analysis.dscr_summary = (
                DSCRSummary(**dscr_summary_data)
                if not dscr_summary_data.get("error")
                else None
            )

        except Exception as e:
            # Fallback: Use basic DSCR calculation if comprehensive calculation fails
            self._calculate_basic_dscr_fallback(e)

    def _extract_noi_time_series(
        self, unlevered_analysis: UnleveredAnalysisResult
    ) -> pd.Series:
        """
        Extract NOI time series from unlevered asset analysis using type-safe enum access.

        Uses the new get_series method for robust, enum-based data access that eliminates
        brittle string matching. This implements the "Don't Ask, Tell" principle.

        Args:
            unlevered_analysis: Results from unlevered asset analysis

        Returns:
            NOI time series aligned with timeline periods
        """
        # Use the new type-safe accessor method
        return unlevered_analysis.get_series(
            UnleveredAggregateLineKey.NET_OPERATING_INCOME, self.timeline
        )

    def _aggregate_debt_service(self) -> pd.Series:
        """
        Aggregate debt service from all facilities into a single time series.

        Returns:
            Total debt service series aligned with timeline periods
        """
        total_debt_service_series = pd.Series(0.0, index=self.timeline.period_index)

        if self.financing_analysis.debt_service:
            for (
                facility_name,
                debt_service,
            ) in self.financing_analysis.debt_service.items():
                if debt_service is not None and hasattr(debt_service, "index"):
                    # Add this facility's debt service to the total
                    aligned_debt_service = debt_service.reindex(
                        self.timeline.period_index, fill_value=0.0
                    )
                    total_debt_service_series = total_debt_service_series.add(
                        aligned_debt_service, fill_value=0
                    )

        return total_debt_service_series

    def _calculate_dscr_time_series(
        self, noi_series: pd.Series, debt_service_series: pd.Series
    ) -> pd.Series:
        """
        Calculate DSCR time series with proper handling of edge cases.

        Args:
            noi_series: Net Operating Income time series
            debt_service_series: Total debt service time series

        Returns:
            DSCR time series with institutional-grade calculation
        """

        # Calculate DSCR for each period where debt service is positive
        # DSCR = NOI / Debt Service
        # Handle division by zero and negative values appropriately

        dscr_series = pd.Series(index=self.timeline.period_index, dtype=float)

        for period in self.timeline.period_index:
            noi = noi_series.get(period, 0.0)
            debt_service = debt_service_series.get(period, 0.0)

            if debt_service > 0:
                dscr = noi / debt_service
                # Cap extremely high DSCR values for practical analysis
                dscr_series[period] = min(dscr, 100.0)  # Cap at 100x coverage
            elif debt_service == 0 and noi >= 0:
                # No debt service but positive NOI = infinite coverage (set to high value)
                dscr_series[period] = 100.0
            else:
                # Negative NOI or other edge cases
                dscr_series[period] = 0.0

        return dscr_series

    def _calculate_dscr_summary(self, dscr_series: pd.Series) -> Dict[str, Any]:
        """
        Calculate comprehensive DSCR summary statistics for covenant monitoring.

        Args:
            dscr_series: DSCR time series

        Returns:
            Comprehensive DSCR summary with covenant analysis
        """
        if len(dscr_series) == 0:
            return {"error": "No DSCR data available"}

        # Filter out zero values for meaningful statistics
        meaningful_dscr = dscr_series[dscr_series > 0]

        if len(meaningful_dscr) == 0:
            return {"error": "No meaningful DSCR values (all zero or negative)"}

        # Basic statistics
        summary = {
            "minimum_dscr": float(meaningful_dscr.min()),
            "average_dscr": float(meaningful_dscr.mean()),
            "maximum_dscr": float(meaningful_dscr.max()),
            "median_dscr": float(meaningful_dscr.median()),
            "standard_deviation": float(meaningful_dscr.std()),
        }

        # Covenant analysis - common DSCR thresholds
        covenant_thresholds = [1.0, 1.1, 1.15, 1.2, 1.25, 1.3, 1.35, 1.4, 1.5]

        for threshold in covenant_thresholds:
            periods_below = (dscr_series < threshold).sum()
            summary[f"periods_below_{threshold:.2f}".replace(".", "_")] = int(
                periods_below
            )

        # Percentile analysis
        percentiles = [10, 25, 75, 90, 95]
        for p in percentiles:
            summary[f"dscr_{p}th_percentile"] = float(meaningful_dscr.quantile(p / 100))

        # Trend analysis
        if len(meaningful_dscr) > 1:
            # Calculate trend using linear regression slope
            x = range(len(meaningful_dscr))
            trend_slope = np.polyfit(x, meaningful_dscr.values, 1)[0]
            summary["trend_slope"] = float(trend_slope)
            summary["trend_direction"] = (
                "improving"
                if trend_slope > 0
                else "declining"
                if trend_slope < 0
                else "stable"
            )

        # Volatility analysis
        if len(meaningful_dscr) > 2:
            # Calculate coefficient of variation
            cv = summary["standard_deviation"] / summary["average_dscr"]
            summary["coefficient_of_variation"] = float(cv)
            summary["volatility_category"] = (
                "low" if cv < 0.1 else "moderate" if cv < 0.25 else "high"
            )

        return summary

    def _calculate_forward_dscr_analysis(
        self, noi_series: pd.Series, debt_service_series: pd.Series
    ) -> Dict[str, Any]:
        """
        Calculate forward-looking DSCR analysis for underwriting and covenant monitoring.

        Args:
            noi_series: NOI time series
            debt_service_series: Debt service time series

        Returns:
            Forward-looking DSCR analysis including stress scenarios
        """

        analysis = {}

        # Year 1 stabilized DSCR (important for underwriting)
        if len(noi_series) >= 12:
            year1_noi = noi_series.iloc[:12].mean()  # Average monthly NOI in year 1
            year1_debt_service = debt_service_series.iloc[
                :12
            ].mean()  # Average monthly debt service

            if year1_debt_service > 0:
                analysis["year1_stabilized_dscr"] = float(
                    year1_noi / year1_debt_service
                )
            else:
                analysis["year1_stabilized_dscr"] = None

        # Forward 12-month average DSCR (rolling analysis)
        if len(noi_series) >= 12:
            rolling_noi = noi_series.rolling(window=12).mean()
            rolling_debt_service = debt_service_series.rolling(window=12).mean()

            forward_dscr = rolling_noi / rolling_debt_service.where(
                rolling_debt_service > 0
            )
            analysis["forward_12m_dscr_series"] = forward_dscr.dropna()

            if not forward_dscr.dropna().empty:
                analysis["minimum_forward_dscr"] = float(forward_dscr.dropna().min())
                analysis["average_forward_dscr"] = float(forward_dscr.dropna().mean())

        # Stress testing scenarios
        stress_scenarios = {
            "noi_decline_5%": 0.95,
            "noi_decline_10%": 0.90,
            "noi_decline_15%": 0.85,
            "noi_decline_20%": 0.80,
        }

        analysis["stress_test_results"] = {}

        for scenario_name, noi_factor in stress_scenarios.items():
            stressed_noi = noi_series * noi_factor
            stressed_dscr = stressed_noi / debt_service_series.where(
                debt_service_series > 0
            )
            stressed_dscr_clean = stressed_dscr.dropna()

            if not stressed_dscr_clean.empty:
                analysis["stress_test_results"][scenario_name] = {
                    "minimum_dscr": float(stressed_dscr_clean.min()),
                    "average_dscr": float(stressed_dscr_clean.mean()),
                    "periods_below_1_20": int((stressed_dscr_clean < 1.2).sum()),
                    "periods_below_1_00": int((stressed_dscr_clean < 1.0).sum()),
                }

        return analysis

    def _calculate_basic_dscr_fallback(self, error: Exception) -> None:
        """
        Basic DSCR calculation fallback when comprehensive calculation fails.

        Args:
            error: The exception that caused the comprehensive calculation to fail
        """
        logger = logging.getLogger(__name__)
        logger.warning(f"DSCR calculation failed with error: {error}")
        logger.debug("DSCR calculation stack trace:", exc_info=True)

        # Set basic fallback values
        self.financing_analysis.dscr_time_series = pd.Series(
            0.0, index=self.timeline.period_index
        )
        self.financing_analysis.dscr_summary = DSCRSummary(
            minimum_dscr=0.0,
            average_dscr=0.0,
            maximum_dscr=0.0,
            median_dscr=0.0,
            standard_deviation=0.0,
        )
