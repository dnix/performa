# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Deal Analysis Orchestrator

This module provides the DealCalculator service that orchestrates the complete deal analysis workflow
by delegating to specialist services while maintaining a clean public API and comprehensive functionality.

The DealCalculator serves as the central orchestrator for the entire deal analysis framework, coordinating
the execution of specialist services in the proper sequence to produce comprehensive deal analysis results.
It implements the multi-pass analysis approach that ensures all components have access to the data they need.

The orchestrator follows the established analysis workflow:
1. **Unlevered Asset Analysis** - Pure asset performance without financing effects
2. **Valuation Analysis** - Property value estimation and disposition proceeds calculation
3. **Debt Analysis** - Financing structure analysis with DSCR and covenant monitoring
4. **Cash Flow Analysis** - Institutional-grade funding cascade and levered cash flows
5. **Partnership Analysis** - Equity waterfall and partner distribution calculations
6. **Deal Metrics** - Comprehensive deal-level performance metrics

Key capabilities:
- **Multi-Pass Analysis**: Systematic execution of analysis services in proper sequence
- **Typed State Management**: Maintains strongly-typed intermediate results during analysis
- **Comprehensive Results**: Returns complete DealAnalysisResult with all analysis components
- **Backward Compatibility**: Maintains legacy API support for existing tests and integrations
- **Error Handling**: Robust error handling with graceful degradation and detailed error reporting

The orchestrator implements the "orchestration pattern" where it coordinates specialist services
without duplicating their logic, ensuring clean separation of concerns and maintainability.

Example:
    ```python
    from performa.deal.orchestrator import DealCalculator

    # Create orchestrator with dependencies
    calculator = DealCalculator(deal, timeline, settings)

    # Execute complete analysis workflow
    results = calculator.run()

    # Access comprehensive results
    print(f"Deal IRR: {results.deal_metrics.irr:.2%}")
    print(f"DSCR minimum: {results.financing_analysis.dscr_summary.minimum_dscr:.2f}")
    print(f"Partner count: {len(results.partner_distributions.waterfall_details.partner_results)}")
    ```

Architecture:
    - Uses dataclass pattern for runtime service orchestration
    - Maintains typed state during multi-pass analysis execution
    - Delegates to specialist services for domain-specific logic
    - Returns strongly-typed results with comprehensive component access
    - Provides backward compatibility for existing integrations

Integration:
    - Integrates with all specialist services in the analysis module
    - Maintains compatibility with existing test suites and integrations
    - Provides comprehensive error handling and logging
    - Supports both new typed API and legacy compatibility methods
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

import pandas as pd
from pyxirr import xirr

from performa.analysis import run
from performa.core.ledger import SeriesMetadata

if TYPE_CHECKING:
    from performa.analysis.results import AssetAnalysisResult
    from performa.core.ledger import LedgerBuilder
    from performa.deal.deal import Deal
from performa.core.primitives import (
    CalculationPhase,
    CapitalSubcategoryEnum,
    CashFlowCategoryEnum,
    GlobalSettings,
    Timeline,
    TransactionPurpose,
)
from performa.deal.analysis import (
    CashFlowEngine,
    DebtAnalyzer,
    PartnershipAnalyzer,
    ValuationEngine,
)
from performa.deal.results import (
    DealAnalysisResult,
    DealMetricsResult,
    DealSummary,
    FinancingAnalysisResult,
    FundingCascadeDetails,
    InterestCompoundingDetails,
    LeveredCashFlowResult,
    PartnerDistributionResult,
    UnleveredAnalysisResult,
)

logger = logging.getLogger(__name__)


@dataclass
class DealCalculator:
    """
    Service class that orchestrates the complete deal analysis workflow.

    This class encapsulates the multi-step analysis logic as internal state,
    providing a clean, maintainable structure for complex deal analysis.

    The analysis proceeds through distinct sequential steps:
    1. Unlevered asset analysis using the core analysis engine
    2. Financing integration and debt service calculations
    3. Performance metrics calculation (DSCR time series)
    4. Levered cash flow calculation with funding cascade
    5. Partner distribution calculations (equity waterfall)
    6. Deal-level performance metrics calculation

    Architecture:
    - Uses dataclass for runtime service (not a data model)
    - Maintains mutable typed state during analysis using Pydantic models
    - Returns strongly-typed result models
    - Delegates to specialist services for complex logic

    Example:
        ```python
        calculator = DealCalculator(deal, timeline, settings)
        results = calculator.run()

        # Access strongly-typed results
        print(f"Deal IRR: {results.deal_metrics.irr:.2%}")
        print(f"Partner count: {len(results.partner_distributions.partner_results)}")
        ```
    """

    # Input Parameters
    deal: Deal
    timeline: Timeline
    settings: GlobalSettings
    asset_analysis: Optional["AssetAnalysisResult"] = None  # Pre-computed asset analysis to reuse

    # Typed Result State (populated during analysis)
    deal_summary: DealSummary = field(
        init=False, repr=False, default_factory=DealSummary
    )
    unlevered_analysis: UnleveredAnalysisResult = field(
        init=False, repr=False, default_factory=UnleveredAnalysisResult
    )
    financing_analysis: FinancingAnalysisResult = field(
        init=False, repr=False, default_factory=FinancingAnalysisResult
    )
    levered_cash_flows: LeveredCashFlowResult = field(
        init=False, repr=False, default_factory=LeveredCashFlowResult
    )
    partner_distributions: PartnerDistributionResult = field(
        init=False, repr=False, default=None
    )
    deal_metrics: DealMetricsResult = field(
        init=False, repr=False, default_factory=DealMetricsResult
    )

    def run(self, ledger_builder: "LedgerBuilder") -> DealAnalysisResult:
        """
        Execute the complete deal analysis workflow by delegating to specialist services.

        Args:
            ledger_builder: The analysis ledger builder (Pass-the-Builder pattern).
                Must be the same instance used throughout the analysis.

        Returns:
            Strongly-typed DealAnalysisResult containing all analysis components

        Raises:
            ValueError: If deal structure is invalid
            RuntimeError: If analysis fails during execution
        """
        try:
            # Initialize deal summary
            self._populate_deal_summary()

            # === PASS 1: Asset Analysis (Ledger-Based) ===
            if self.asset_analysis is not None:
                # Use pre-computed asset analysis (Pass-the-Builder pattern)
                # The ledger_builder already contains asset transactions
                asset_result = self.asset_analysis
            else:
                # Run fresh asset analysis with provided ledger builder
                asset_result = run(
                    model=self.deal.asset,
                    timeline=self.timeline,
                    settings=self.settings,
                    ledger_builder=ledger_builder
                )
            
            # Continue with same builder (pass-the-builder pattern)
            # ledger_builder is the same instance used by asset analysis
            
            # Create backward compatibility wrapper using ledger data
            self.unlevered_analysis = UnleveredAnalysisResult(
                scenario=asset_result.scenario,
                cash_flows=asset_result.summary_df,  # Use actual cash flow summary
                models=asset_result.models if hasattr(asset_result, 'models') else []
            )

            # === PASS 2: Add Deal Transactions to Ledger ===
            # Add acquisition costs BEFORE funding cascade so they're included in uses
            self._add_acquisition_records(ledger_builder)
            
            # === FUNDING CASCADE ORCHESTRATION ===
            # Query ledger for actual transaction records to calculate funding needs
            self._orchestrate_funding_cascade(ledger_builder)

            # === PASS 2 (continued): Add Remaining Deal Transactions to Ledger ===
            self._add_financing_records(ledger_builder)
            self._add_partnership_records(ledger_builder)

            # === PASS 3: Valuation Analysis ===
            valuation_engine = ValuationEngine(
                deal=self.deal, timeline=self.timeline, settings=self.settings
            )
            
            property_value_series = valuation_engine.extract_property_value_series(
                self.unlevered_analysis
            )
            noi_series = valuation_engine.extract_noi_series(
                self.unlevered_analysis
            )
            disposition_proceeds = valuation_engine.calculate_disposition_proceeds(
                ledger_builder,
                self.unlevered_analysis
            )

            # === PASS 4: Debt Analysis ===
            debt_analyzer = DebtAnalyzer(
                deal=self.deal, timeline=self.timeline, settings=self.settings
            )
            self.financing_analysis = debt_analyzer.analyze_financing_structure(
                property_value_series=property_value_series,
                noi_series=noi_series,
                unlevered_analysis=self.unlevered_analysis,
            )

            # === PASS 5: Cash Flow Analysis ===
            # Preserve the funding_cascade_details created during funding cascade orchestration
            existing_funding_cascade_details = self.levered_cash_flows.funding_cascade_details if self.levered_cash_flows else None
            
            cash_flow_engine = CashFlowEngine(
                deal=self.deal, timeline=self.timeline, settings=self.settings
            )
            self.levered_cash_flows = cash_flow_engine.calculate_levered_cash_flows(
                unlevered_analysis=self.unlevered_analysis,
                financing_analysis=self.financing_analysis,
                ledger_builder=ledger_builder,  # Pass ledger builder for funding cascade
                disposition_proceeds=disposition_proceeds,
            )
            
            # Restore the funding_cascade_details (CashFlowEngine doesn't create this)
            if existing_funding_cascade_details:
                self.levered_cash_flows.funding_cascade_details = existing_funding_cascade_details

            # === PASS 5: Partnership Analysis ===
            partnership_analyzer = PartnershipAnalyzer(
                deal=self.deal, timeline=self.timeline, settings=self.settings
            )
            self.partner_distributions = (
                partnership_analyzer.calculate_partner_distributions(
                    levered_cash_flows=self.levered_cash_flows.levered_cash_flows,
                    ledger_builder=ledger_builder  # Pass ledger builder for distribution recording
                )
            )

            # === PASS 6: Deal Metrics ===
            self._calculate_deal_metrics()

            # Return the final typed result with ledger-based asset analysis
            return DealAnalysisResult(
                deal_summary=self.deal_summary,
                asset_analysis=asset_result,  # NEW: Ledger-based result
                unlevered_analysis=self.unlevered_analysis,  # DEPRECATED: Backward compatibility
                financing_analysis=self.financing_analysis
                if self.financing_analysis.has_financing
                else None,
                levered_cash_flows=self.levered_cash_flows,
                partner_distributions=self.partner_distributions,
                deal_metrics=self.deal_metrics,
            )

        except Exception as e:
            raise RuntimeError(f"Deal analysis failed: {str(e)}") from e

    # === FUNDING CASCADE ORCHESTRATION ===
    # These methods orchestrate the institutional funding cascade for development deals.

    def _orchestrate_funding_cascade(self, builder: "LedgerBuilder") -> None:
        """
        Orchestrate the complete funding cascade using ledger-based transaction records.
        
        This method queries the ledger for actual transaction records to determine:
        - Total Uses (all outflows/costs from asset analysis)
        - Funding requirements by period
        - Equity vs debt funding allocation
        """     
        # Get current ledger with all asset-level transactions
        ledger = builder.get_current_ledger()
        logger.debug(f"Funding cascade: Processing ledger with {len(ledger)} transactions")
        
        if ledger.empty:
            logger.warning("Funding cascade: Ledger is empty, creating zero funding cascade")
            self._create_zero_funding_cascade()
            return
        
        # Calculate total uses from ledger (all negative amounts = outflows/costs)
        uses_by_period = self._calculate_uses_from_ledger(ledger)
        total_uses = uses_by_period.sum()
        
        logger.debug(f"Funding cascade: Total uses calculated as ${total_uses:,.2f}")
        
        if total_uses <= 0:
            logger.warning("Funding cascade: No uses found, creating zero funding cascade")
            self._create_zero_funding_cascade()
            return
        
        # Create uses breakdown DataFrame from actual ledger transactions
        uses_breakdown = self._create_uses_breakdown_from_ledger(ledger)
        
        # Create funding cascade details
        self._create_funding_cascade_details(uses_breakdown, total_uses)
        
        logger.debug("Funding cascade orchestration completed")

    def _calculate_uses_from_ledger(self, ledger: pd.DataFrame) -> pd.Series:
        """Calculate period-by-period uses (outflows) from ledger transactions."""
        
        # Filter for capital use transactions (costs/outflows)
        # Use flow_purpose instead of amount sign for correct classification
        capital_uses = ledger[ledger['flow_purpose'] == TransactionPurpose.CAPITAL_USE.value].copy()
        
        if capital_uses.empty:
            return pd.Series(0.0, index=self.timeline.period_index)
        
        # Capital use amounts are negative (outflows), make them positive for uses calculation
        # Take absolute value first, then group by period and sum (all amounts are positive uses)
        capital_uses['amount'] = capital_uses['amount'].abs()
        uses_by_period = capital_uses.groupby('date')['amount'].sum()
        
        # Convert date index to Period index to match timeline
        if len(uses_by_period) > 0:
            if hasattr(uses_by_period.index[0], 'to_period'):
                # Timestamp index
                uses_by_period.index = uses_by_period.index.to_period('M')
            else:
                # datetime.date index - convert to Period
                uses_by_period.index = pd.PeriodIndex([pd.Period(date, 'M') for date in uses_by_period.index])
        
        # Reindex to full timeline
        uses_series = uses_by_period.reindex(self.timeline.period_index, fill_value=0.0)
        
        return uses_series

    def _create_uses_breakdown_from_ledger(self, ledger: pd.DataFrame) -> pd.DataFrame:
        """Create detailed uses breakdown from ledger transactions by category."""
        
        # Initialize breakdown DataFrame
        uses_df = pd.DataFrame(
            0.0,
            index=self.timeline.period_index,
            columns=[
                "Acquisition Costs",
                "Construction Costs", 
                "Other Project Costs",
                "Total Uses",
            ],
        )
        
        if ledger.empty:
            logger.warning("Uses breakdown: Ledger is empty")
            return uses_df
        
        logger.debug(f"Uses breakdown: Ledger has {len(ledger)} transactions")
        logger.debug(f"Flow purposes in ledger: {ledger['flow_purpose'].unique()}")
        
        # Filter for capital use transactions
        capital_uses = ledger[ledger['flow_purpose'] == TransactionPurpose.CAPITAL_USE.value].copy()
        
        if capital_uses.empty:
            logger.warning("Uses breakdown: No CAPITAL_USE transactions found")
            logger.debug(f"Available transactions by flow_purpose: {ledger['flow_purpose'].value_counts()}")
            return uses_df
        
        logger.debug(f"Uses breakdown: Found {len(capital_uses)} CAPITAL_USE transactions")
        
        # Group by date and subcategory to break down uses
        for _, transaction in capital_uses.iterrows():
            date = transaction['date']
            amount = abs(transaction['amount'])  # Ensure positive
            subcategory = transaction.get('subcategory', '')
            
            logger.debug(f"Processing transaction: date={date}, amount={amount}, subcategory='{subcategory}'")
            
            # Convert date to period for indexing
            if hasattr(date, 'to_period'):
                period = date.to_period('M')
            elif hasattr(date, 'date'):
                period = pd.Period(date.date(), freq='M')
            else:
                period = pd.Period(date, freq='M')
            
            # Skip if period not in timeline
            if period not in uses_df.index:
                logger.warning(f"Period {period} not in timeline, skipping")
                continue
                
            # Categorize by subcategory
            # Handle both enum string representation and enum value
            if (subcategory == CapitalSubcategoryEnum.PURCHASE_PRICE.value or 
                subcategory == str(CapitalSubcategoryEnum.PURCHASE_PRICE)):
                logger.debug(f"Categorizing as Acquisition Costs: {amount} in period {period}")
                old_val = uses_df.loc[period, "Acquisition Costs"]
                uses_df.loc[period, "Acquisition Costs"] += amount
                new_val = uses_df.loc[period, "Acquisition Costs"]
                logger.debug(f"Acquisition Costs updated: {old_val} -> {new_val}")
            elif (subcategory == CapitalSubcategoryEnum.CLOSING_COSTS.value or 
                  subcategory == str(CapitalSubcategoryEnum.CLOSING_COSTS)):
                logger.debug(f"Categorizing closing costs as Acquisition Costs: {amount} in period {period}")
                old_val = uses_df.loc[period, "Acquisition Costs"]
                uses_df.loc[period, "Acquisition Costs"] += amount
                new_val = uses_df.loc[period, "Acquisition Costs"]
                logger.debug(f"Acquisition Costs updated: {old_val} -> {new_val}")
            elif subcategory in [CapitalSubcategoryEnum.HARD_COSTS.value, CapitalSubcategoryEnum.SOFT_COSTS.value, CapitalSubcategoryEnum.SITE_WORK.value]:
                logger.debug(f"Categorizing as Construction Costs: {amount}")
                uses_df.loc[period, "Construction Costs"] += amount
            else:
                logger.debug(f"Categorizing as Other Project Costs: {amount} (subcategory: {subcategory})")
                uses_df.loc[period, "Other Project Costs"] += amount
            
            # Add to total uses
            uses_df.loc[period, "Total Uses"] += amount
        
        logger.debug(f"Final uses_df summary:")
        logger.debug(f"  Acquisition Costs total: {uses_df['Acquisition Costs'].sum()}")
        logger.debug(f"  Total Uses total: {uses_df['Total Uses'].sum()}")
        
        return uses_df

    def _create_funding_cascade_details(self, uses_breakdown: pd.DataFrame, total_uses: float) -> None:
        """Create funding cascade details based on calculated uses."""
        # For all-equity deals, equity funds 100% of uses
        if not self.deal.financing:
            equity_target = total_uses
            ltc_ratio = 0.0
        else:
            # Get LTC ratio from construction facilities
            ltc_ratio = 0.0
            if self.deal.financing.facilities:
                for facility in self.deal.financing.facilities:
                    if hasattr(facility, 'max_ltc'):
                        ltc_ratio = max(ltc_ratio, float(facility.max_ltc))
            
            equity_target = total_uses * (1 - ltc_ratio)
        
        # Calculate equity contributions by period (proportional to uses)
        total_uses_by_period = uses_breakdown["Total Uses"]
        if total_uses > 0:
            equity_contributions = total_uses_by_period * (equity_target / total_uses)
        else:
            equity_contributions = pd.Series(0.0, index=self.timeline.period_index)
        
        # Create interest compounding details (placeholder for now)
        # FIXME: placeholder!
        interest_details = InterestCompoundingDetails(
            base_uses=total_uses_by_period,
            compounded_interest=pd.Series(0.0, index=total_uses_by_period.index),
            total_uses_with_interest=total_uses_by_period,
            equity_target=equity_target,
            equity_funded=equity_contributions.sum(),
            debt_funded=total_uses - equity_target,
            funding_gap=0.0,
            total_project_cost=total_uses,
        )
        
        # Create funding cascade details
        self.levered_cash_flows.funding_cascade_details = FundingCascadeDetails(
            uses_breakdown=uses_breakdown,
            equity_target=equity_target,
            equity_contributed_cumulative=equity_contributions.cumsum(),
            interest_compounding_details=interest_details,
        )

    def _create_zero_funding_cascade(self) -> None:
        """Create zero funding cascade for deals with no uses."""
        zero_series = pd.Series(0.0, index=self.timeline.period_index)
        
        uses_breakdown = pd.DataFrame({
            "Acquisition Costs": zero_series,
            "Construction Costs": zero_series,
            "Other Project Costs": zero_series,
            "Total Uses": zero_series
        })
        
        interest_details = InterestCompoundingDetails(
            base_uses=zero_series,
            compounded_interest=zero_series,
            total_uses_with_interest=zero_series,
            equity_target=0.0,
            equity_funded=0.0,
            debt_funded=0.0,
            funding_gap=0.0,
            total_project_cost=0.0,
        )
        
        self.levered_cash_flows.funding_cascade_details = FundingCascadeDetails(
            uses_breakdown=uses_breakdown,
            equity_target=0.0,
            equity_contributed_cumulative=zero_series,
            interest_compounding_details=interest_details,
        )


    def _populate_deal_summary(self) -> None:
        """Initialize deal summary with basic deal characteristics."""
        self.deal_summary.deal_name = self.deal.name
        self.deal_summary.deal_type = self.deal.deal_type
        self.deal_summary.asset_type = self.deal.asset.property_type.value
        self.deal_summary.is_development = self.deal.is_development_deal
        self.deal_summary.has_financing = self.deal.financing is not None
        self.deal_summary.has_disposition = self.deal.exit_valuation is not None

    def _calculate_deal_metrics(self) -> None:
        """
        Calculate deal-level performance metrics.

        This calculates key metrics like IRR, equity multiple, and other
        deal-level performance indicators from the levered cash flows.
        """
        # Get levered cash flows
        cash_flows = self.levered_cash_flows.levered_cash_flows
        if cash_flows is None or len(cash_flows) == 0:
            return

        try:
            # Calculate basic metrics
            negative_flows = cash_flows[cash_flows < 0]
            positive_flows = cash_flows[cash_flows > 0]

            total_equity_invested = abs(negative_flows.sum())
            total_equity_returned = positive_flows.sum()
            net_profit = cash_flows.sum()

            # Calculate hold period
            hold_period_years = len(self.timeline.period_index) / 12.0

            # Calculate equity multiple
            equity_multiple = None
            if total_equity_invested > 0:
                equity_multiple = total_equity_returned / total_equity_invested

            # Calculate IRR using PyXIRR
            irr = None
            if len(cash_flows) > 1 and total_equity_invested > 0:
                try:
                    dates = [
                        period.to_timestamp().date() for period in cash_flows.index
                    ]
                    irr = xirr(dates, cash_flows.values)
                    if irr is not None:
                        irr = float(irr)
                except Exception:
                    pass

            # Calculate total return
            total_return = None
            if total_equity_invested > 0:
                total_return = (
                    total_equity_returned - total_equity_invested
                ) / total_equity_invested

            # Calculate annual yield
            annual_yield = None
            if total_return is not None and hold_period_years > 0:
                annual_yield = total_return / hold_period_years

            # Calculate cash-on-cash return (first year)
            cash_on_cash = None
            if total_equity_invested > 0 and len(cash_flows) > 12:
                first_year_distributions = positive_flows[:12].sum()
                cash_on_cash = first_year_distributions / total_equity_invested

            # Update metrics using dot notation
            self.deal_metrics.irr = irr
            self.deal_metrics.equity_multiple = equity_multiple
            self.deal_metrics.total_return = total_return
            self.deal_metrics.annual_yield = annual_yield
            self.deal_metrics.cash_on_cash = cash_on_cash
            self.deal_metrics.total_equity_invested = total_equity_invested
            self.deal_metrics.total_equity_returned = total_equity_returned
            self.deal_metrics.net_profit = net_profit
            self.deal_metrics.hold_period_years = hold_period_years

        except Exception:
            # Fallback: Return empty metrics if calculation fails
            # FIXME: Consider logging this error in production
            pass

    # === TRANSACTION INTEGRATION METHODS ===
    # These methods flow deal-level transactions through the ledger builder

    def _add_acquisition_records(self, builder: "LedgerBuilder") -> None:
        """Add acquisition and fee transactions to ledger."""
        if not self.deal.acquisition:
            logger.debug("No acquisition terms to add to ledger")
            return
            
        try:
            acquisition_date = self.deal.acquisition.acquisition_date
            purchase_price = self.deal.acquisition.value
            closing_costs_rate = self.deal.acquisition.closing_costs_rate
        except AttributeError as e:
            logger.error(f"Failed to access acquisition attributes: {e}")
            return
        
        # Purchase price (negative amount representing outflow/use)
        purchase_price_series = pd.Series(
            [-purchase_price], 
            index=[acquisition_date],
            name="Purchase Price"
        )
        
        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.CAPITAL,
            subcategory=CapitalSubcategoryEnum.PURCHASE_PRICE,
            item_name="Property Acquisition",
            source_id=str(self.deal.uid),
            asset_id=self.deal.asset.uid,
            pass_num=CalculationPhase.ACQUISITION.value  # Acquisition phase
        )
        builder.add_series(purchase_price_series, metadata)
        logger.debug(f"Added acquisition purchase price: ${purchase_price:,.0f}")
        
        # Closing costs (negative amount representing outflow/use)
        closing_costs = purchase_price * closing_costs_rate
        closing_costs_series = pd.Series(
            [-1 * closing_costs], 
            index=[acquisition_date],
            name="Closing Costs"
        )
        
        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.CAPITAL,
            subcategory=CapitalSubcategoryEnum.CLOSING_COSTS,
            item_name="Acquisition Closing Costs",
            source_id=str(self.deal.uid),
            asset_id=self.deal.asset.uid,
            pass_num=CalculationPhase.ACQUISITION.value  # Acquisition phase
        )
        builder.add_series(closing_costs_series, metadata)
        logger.debug(f"Added acquisition closing costs: ${closing_costs:,.0f}")
        
        # Add deal fees if they exist
        if hasattr(self.deal, 'deal_fees') and self.deal.deal_fees:
            logger.debug(f"Adding {len(self.deal.deal_fees)} deal fees")
            for fee in self.deal.deal_fees:
                try:
                    fee_cf = fee.compute_cf(self.timeline)
                    metadata = SeriesMetadata(
                        category="Capital",
                        subcategory="Fees",
                        item_name=f"Fee - {getattr(fee, 'name', 'Unknown')}",
                        source_id=str(getattr(fee, 'uid', fee)),
                        asset_id=self.deal.asset.uid
                    )
                    builder.add_series(fee_cf, metadata)
                    logger.debug(f"Added deal fee: {getattr(fee, 'name', 'Unknown')}")
                except Exception as e:
                    logger.warning(f"Failed to add deal fee: {e}")
        else:
            logger.debug("No deal fees to add")

    def _add_financing_records(self, builder: "LedgerBuilder") -> None:
        """Add financing transactions to ledger."""        
        if not self.deal.financing:
            logger.debug("No financing to add to ledger")
            return
            
        # Add loan proceeds (positive - cash inflow)
        try:
            # Get LTV ratio from the primary facility
            primary_facility = self.deal.financing.primary_facility
            if not hasattr(primary_facility, 'ltv_ratio'):
                logger.debug(f"Primary facility {primary_facility.name} does not have ltv_ratio attribute")
                return
                
            loan_amount = self.deal.acquisition.value * primary_facility.ltv_ratio
            acquisition_date = self.deal.acquisition.acquisition_date
        except AttributeError as e:
            logger.error(f"Failed to access financing attributes: {e}")
            return
        
        loan_proceeds_series = pd.Series(
            [loan_amount], 
            index=[acquisition_date],
            name="Loan Proceeds"
        )
        
        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.FINANCING,
            subcategory="Loan Proceeds",  # TODO: Need FinancingSubcategoryEnum 
            item_name="Construction/Acquisition Loan",
            source_id=str(self.deal.uid),
            asset_id=self.deal.asset.uid,
            pass_num=CalculationPhase.FINANCING.value  # Financing phase
        )
        builder.add_series(loan_proceeds_series, metadata)
        logger.debug(f"Added loan proceeds: ${loan_amount:,.0f} (LTV: {primary_facility.ltv_ratio:.1%})")

    def _add_partnership_records(self, builder: "LedgerBuilder") -> None:
        """Add partnership transactions to ledger."""        
        if not self.deal.equity_partners:
            logger.debug("No partnership to add to ledger")
            return
            
        # Calculate required equity (purchase price + closing costs - loan proceeds)
        try:
            total_cost = self.deal.acquisition.value * (1 + self.deal.acquisition.closing_costs_rate)
            loan_amount = self.deal.acquisition.value * self.deal.financing.ltv_ratio if self.deal.financing else 0
            required_equity = total_cost - loan_amount
            acquisition_date = self.deal.acquisition.acquisition_date
        except AttributeError as e:
            logger.error(f"Failed to access partnership attributes: {e}")
            return
        
        equity_contribution_series = pd.Series(
            [required_equity], 
            index=[acquisition_date],
            name="Partner Capital Contributions"
        )
        
        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.FINANCING,  # Partnership contributions are financing
            subcategory="Capital Contribution",  # TODO: Need FinancingSubcategoryEnum
            item_name="Initial Equity Investment",
            source_id=str(self.deal.uid),
            asset_id=self.deal.asset.uid,
            pass_num=CalculationPhase.PARTNERSHIP.value  # Partnership phase
        )
        builder.add_series(equity_contribution_series, metadata)
        logger.debug(f"Added equity contribution: ${required_equity:,.0f}")
        # TODO: Add partnership flows after they're calculated
        pass

