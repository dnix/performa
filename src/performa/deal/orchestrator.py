"""
Deal Analysis Orchestrator

This module implements the DealCalculator service class that orchestrates
complete real estate deal analysis workflows, from unlevered asset analysis
through partner distributions and performance metrics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List

import pandas as pd
from pyxirr import xirr

if TYPE_CHECKING:
    from ..core.primitives import GlobalSettings, Timeline
    from .deal import Deal

from .results import (
    DealAnalysisResult,
    DealMetricsResult,
    DealSummary,
    ErrorDistributionResult,
    FinancingAnalysisResult,
    LeveredCashFlowResult,
    PartnerDistributionResult,
    SingleEntityDistributionResult,
    UnleveredAnalysisResult,
    WaterfallDistributionResult,
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
    - Encapsulates complex multi-step logic
    
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
    
    # Typed Result State (populated during analysis)
    deal_summary: DealSummary = field(init=False, repr=False, default_factory=DealSummary)
    unlevered_analysis: UnleveredAnalysisResult = field(init=False, repr=False, default_factory=UnleveredAnalysisResult)
    financing_analysis: FinancingAnalysisResult = field(init=False, repr=False, default_factory=FinancingAnalysisResult)
    levered_cash_flows: LeveredCashFlowResult = field(init=False, repr=False, default_factory=LeveredCashFlowResult)
    partner_distributions: PartnerDistributionResult = field(init=False, repr=False, default=None)
    deal_metrics: DealMetricsResult = field(init=False, repr=False, default_factory=DealMetricsResult)
    
    def run(self) -> DealAnalysisResult:
        """
        Execute the complete 5-pass deal analysis workflow.
        
        Returns:
            Strongly-typed DealAnalysisResult containing all analysis components
            
        Raises:
            ValueError: If deal structure is invalid
            RuntimeError: If analysis fails during execution
        """
        try:
            # Initialize deal summary
            self._populate_deal_summary()
            
            # Execute the deal analysis workflow
            self._analyze_unlevered_asset()  # pass 1: unlevered asset analysis
            self._integrate_financing()  # pass 2: financing integration
            self._calculate_dscr_metrics()  # pass 3: performance metrics (DSCR)
            self._calculate_levered_cash_flows()  # pass 4: levered cash flows
            self._calculate_partner_distributions()  # pass 5: partner distributions
            self._calculate_deal_metrics()  # pass 6: deal metrics
            
            # Return the final typed result
            return DealAnalysisResult(
                deal_summary=self.deal_summary,
                unlevered_analysis=self.unlevered_analysis,
                financing_analysis=self.financing_analysis if self.financing_analysis.has_financing else None,
                levered_cash_flows=self.levered_cash_flows,
                partner_distributions=self.partner_distributions,
                deal_metrics=self.deal_metrics,
            )
            
        except Exception as e:
            raise RuntimeError(f"Deal analysis failed: {str(e)}") from e
    
    def _populate_deal_summary(self) -> None:
        """Initialize deal summary with basic deal characteristics."""
        self.deal_summary.deal_name = self.deal.name
        self.deal_summary.deal_type = self.deal.deal_type
        self.deal_summary.asset_type = self.deal.asset.property_type.value
        self.deal_summary.is_development = self.deal.is_development_deal
        self.deal_summary.has_financing = self.deal.financing is not None
        self.deal_summary.has_disposition = self.deal.disposition is not None
    
    def _analyze_unlevered_asset(self) -> None:
        """
        Analyze the unlevered asset performance using the core analysis engine.
        
        This leverages the existing asset analysis infrastructure to get
        clean, unlevered cash flows that can then be integrated with financing.
        """
        # Import here to avoid circular imports
        from ..analysis import get_scenario_for_model
        
        # Use the public helper to find the scenario class
        scenario_cls = get_scenario_for_model(self.deal.asset)
        
        # Create scenario using dict representation to avoid Pydantic validation issues
        # PERF: review this for round trip issues
        scenario_data = {
            'model': self.deal.asset.model_dump(),
            'timeline': self.timeline.model_dump(),
            'settings': self.settings.model_dump()
        }
        
        scenario = scenario_cls.model_validate(scenario_data)
        scenario.run()
        
        # Store results in typed model
        self.unlevered_analysis.scenario = scenario
        self.unlevered_analysis.cash_flows = scenario.get_cash_flow_summary() if hasattr(scenario, 'get_cash_flow_summary') else None
        self.unlevered_analysis.models = scenario._orchestrator.models if scenario._orchestrator else []
    
    def _integrate_financing(self) -> None:
        """
        Calculate financing integration and debt service.
        
        This integrates the financing plan with the asset cash flows to
        calculate debt service, loan proceeds, and facility information.
        """
        from .results import FacilityInfo
        
        if self.deal.financing is None:
            self.financing_analysis.has_financing = False
            return
        
        # Initialize financing analysis results
        self.financing_analysis.has_financing = True
        self.financing_analysis.financing_plan = self.deal.financing.name
        
        # Process each facility in the financing plan
        for facility in self.deal.financing.facilities:
            facility_name = getattr(facility, 'name', 'Unnamed Facility')
            facility_type = type(facility).__name__
            
            # Add facility metadata
            facility_info = FacilityInfo(
                name=facility_name,
                type=facility_type,
                description=getattr(facility, 'description', ''),
            )
            self.financing_analysis.facilities.append(facility_info)
            
            # Calculate facility-specific cash flows with enhanced features
            if hasattr(facility, 'calculate_debt_service'):
                try:
                    # Enhanced debt service calculation for permanent facilities
                    if hasattr(facility, 'kind') and facility.kind == 'permanent':
                        debt_service = self._calculate_enhanced_debt_service(facility)
                    else:
                        debt_service = facility.calculate_debt_service(self.timeline)
                    self.financing_analysis.debt_service[facility_name] = debt_service
                except Exception:
                    self.financing_analysis.debt_service[facility_name] = None
            
            if hasattr(facility, 'calculate_loan_proceeds'):
                try:
                    loan_proceeds = facility.calculate_loan_proceeds(self.timeline)
                    self.financing_analysis.loan_proceeds[facility_name] = loan_proceeds
                except Exception:
                    self.financing_analysis.loan_proceeds[facility_name] = None
        
        # Handle refinancing transactions if the plan supports them
        if self.deal.financing.has_refinancing:
            try:
                # Get property value and NOI series for intelligent sizing
                property_value_series = self._extract_property_value_series()
                noi_series = self._extract_noi_series()
                
                # Calculate refinancing transactions with enhanced data
                refinancing_transactions = self.deal.financing.calculate_refinancing_transactions(
                    timeline=self.timeline,
                    property_value_series=property_value_series,
                    noi_series=noi_series,
                    financing_cash_flows=None  # Will be provided in future iterations
                )
                self.financing_analysis.refinancing_transactions = refinancing_transactions
                
                # Process refinancing cash flow impacts
                self._process_refinancing_cash_flows(refinancing_transactions)
                
            except Exception:
                # Log the error but continue with empty transactions
                self.financing_analysis.refinancing_transactions = []
    

    
    def _calculate_partner_distributions(self) -> None:
        """
        Calculate partner distributions through equity waterfall.
        
        This applies the equity waterfall logic to distribute cash flows
        among partners based on their partnership structure.
        """
        import pandas as pd

        from .distribution_calculator import DistributionCalculator
        
        # Get the levered cash flows from the results
        cash_flows = self.levered_cash_flows.levered_cash_flows
        
        # Check if deal has equity partners
        if not self.deal.has_equity_partners:
            # No equity partners - single entity results
            self.partner_distributions = self._calculate_single_entity_distributions(cash_flows)
            return
        
        # Calculate fee priority payments
        fee_details = self._calculate_fee_distributions(cash_flows)
        
        # Get remaining cash flows after fee payments
        remaining_cash_flows = fee_details["remaining_cash_flows_after_fee"]
        
        # Calculate standard waterfall distributions on remaining cash flows
        if isinstance(remaining_cash_flows, pd.Series):
            try:
                calculator = DistributionCalculator(self.deal.equity_partners)
                waterfall_results = calculator.calculate_distributions(remaining_cash_flows, self.timeline)
                
                # Combine fee and waterfall results
                try:
                    combined_results = self._combine_fee_and_waterfall_results(
                        fee_details, waterfall_results
                    )
                    self.partner_distributions = self._create_partner_distributions_result(combined_results)
                except Exception as combine_error:
                    logger.error(f"Combination failed: {combine_error}")
                    # Use waterfall results directly if combination fails
                    waterfall_results["fee_details"] = fee_details
                    self.partner_distributions = self._create_partner_distributions_result(waterfall_results)
                    
            except Exception as e:
                # Fallback for DistributionCalculator errors
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
                self.partner_distributions = self._create_partner_distributions_result(error_results)
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
            self.partner_distributions = self._create_partner_distributions_result(error_results)
    
    def _calculate_deal_metrics(self) -> None:
        """
        Calculate deal-level performance metrics.
        
        This calculates key metrics like IRR, equity multiple, and other
        deal-level performance indicators.
        """
        import pandas as pd
        
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
                    dates = [period.to_timestamp().date() for period in cash_flows.index]
                    irr = xirr(dates, cash_flows.values)
                    if irr is not None:
                        irr = float(irr)
                except Exception:
                    pass
            
            # Calculate total return
            total_return = None
            if total_equity_invested > 0:
                total_return = (total_equity_returned - total_equity_invested) / total_equity_invested
            
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
            pass
    

    
    def _create_partner_distributions_result(self, distribution_data: Dict[str, Any]) -> PartnerDistributionResult:
        """
        Create the appropriate partner distribution result based on distribution method.
        
        This handles the discriminated union logic to create the correct
        distribution result type based on the distribution method.
        
        Args:
            distribution_data: Dictionary containing distribution results
            
        Returns:
            Appropriate PartnerDistributionResult subclass
        """
        distribution_method = distribution_data.get('distribution_method', 'error')
        
        if distribution_method in ['waterfall', 'pari_passu']:
            # For pari_passu, change distribution_method to "waterfall" for Pydantic validation
            partner_distributions_data = distribution_data.copy()
            if distribution_method == 'pari_passu':
                partner_distributions_data['distribution_method'] = 'waterfall'
            return WaterfallDistributionResult(**partner_distributions_data)
        elif distribution_method == 'single_entity':
            return SingleEntityDistributionResult(**distribution_data)
        else:
            # Error case or unknown method
            return ErrorDistributionResult(
                distribution_method='error',
                total_distributions=0.0,
                total_investment=0.0,
                equity_multiple=1.0,
                irr=None,
                distributions=pd.Series(0.0, index=self.timeline.period_index),
                waterfall_details={'error': f'Unknown distribution method: {distribution_method}'},
                developer_fee_details={
                    'total_developer_fee': 0.0,
                    'developer_fee_by_partner': {},
                    'remaining_cash_flows_after_fee': pd.Series(0.0, index=self.timeline.period_index),
                },
            )
    
    def _calculate_levered_cash_flows(self) -> None:
        """
        Calculate levered cash flows through institutional-grade funding cascade.
        
        This method executes the complete funding cascade process to determine
        how project uses are funded and calculates the resulting levered cash flows.
        
        Process includes:
        1. Period-by-period Uses calculation (acquisition, construction, fees)
        2. Equity-first funding up to target LTC thresholds
        3. Debt-second funding with proper LTC constraints
        4. Interest compounding with PIK and reserve options
        5. Final levered cash flow assembly with detailed component tracking
        """
        # === Step 1: Calculate Period Uses ===
        uses_breakdown = self._calculate_period_uses()
        base_uses = uses_breakdown["Total Uses"].copy()
        
        # === Step 2: Initialize Funding Components ===
        funding_components = self._initialize_funding_components()
        
        # === Step 3: Execute Funding Cascade ===
        cascade_results = self._execute_funding_cascade(base_uses, funding_components)
        
        # === Step 4: Assemble Final Results ===
        self._assemble_levered_cash_flow_results(
            uses_breakdown, cascade_results, funding_components
        )
    
    def _calculate_period_uses(self) -> pd.DataFrame:
        """
        Calculate total Uses (cash outflows) for each period.
        
        Returns:
            DataFrame with period-by-period Uses breakdown
        """
        import pandas as pd

        from ..analysis import AnalysisContext
        
        # Initialize Uses DataFrame
        uses_df = pd.DataFrame(0.0, index=self.timeline.period_index, columns=[
            "Acquisition Costs",
            "Construction Costs", 
            "Developer Fees",
            "Other Project Costs",
            "Total Uses"
        ])
        
        # 1. Calculate acquisition costs
        if self.deal.acquisition:
            try:
                context = AnalysisContext(
                    timeline=self.timeline, 
                    settings=self.settings,
                    property_data=self.deal.asset
                )
                acquisition_cf = self.deal.acquisition.compute_cf(context)
                
                # Acquisition costs are negative (outflows), make them positive for Uses
                acquisition_uses = acquisition_cf.abs()
                uses_df["Acquisition Costs"] = acquisition_uses.reindex(self.timeline.period_index, fill_value=0.0)
                
            except Exception as e:
                # Log warning but continue analysis
                logger.warning(f"Acquisition cost calculation failed: {e}")
        
        # 2. Calculate construction costs from CapitalPlan
        if hasattr(self.deal.asset, 'construction_plan') and self.deal.asset.construction_plan:
            try:
                context = AnalysisContext(
                    timeline=self.timeline, 
                    settings=self.settings,
                    property_data=self.deal.asset
                )
                
                # Sum construction costs from all capital items
                for capital_item in self.deal.asset.construction_plan.capital_items:
                    item_cf = capital_item.compute_cf(context)
                    
                    # Capital costs are typically positive, but represent cash outflows (Uses)
                    item_uses = item_cf.abs()
                    uses_df["Construction Costs"] += item_uses.reindex(self.timeline.period_index, fill_value=0.0)
                    
            except Exception as e:
                # Log warning but continue analysis
                logger.warning(f"Construction cost calculation failed: {e}")
        
        # 3. Calculate developer fees
        if self.deal.deal_fees:
            try:
                for fee in self.deal.deal_fees:
                    fee_cf = fee.compute_cf(self.timeline)
                    uses_df["Developer Fees"] += fee_cf.reindex(self.timeline.period_index, fill_value=0.0)
                            
            except Exception as e:
                # Log warning but continue analysis
                logger.warning(f"Deal fee calculation failed: {e}")
        
        # 4. Calculate total Uses for each period
        uses_df["Total Uses"] = (
            uses_df["Acquisition Costs"] + 
            uses_df["Construction Costs"] + 
            uses_df["Developer Fees"] +
            uses_df["Other Project Costs"]
        )
        
        return uses_df
    
    def _initialize_funding_components(self) -> Dict[str, Any]:
        """
        Initialize funding component tracking structures.
        
        Returns:
            Dictionary with initialized funding component Series
        """
        import pandas as pd
        
        return {
            "total_uses": pd.Series(0.0, index=self.timeline.period_index),
            "equity_contributions": pd.Series(0.0, index=self.timeline.period_index),
            "debt_draws": pd.Series(0.0, index=self.timeline.period_index),
            "loan_proceeds": pd.Series(0.0, index=self.timeline.period_index),
            "interest_expense": pd.Series(0.0, index=self.timeline.period_index),
            "compounded_interest": pd.Series(0.0, index=self.timeline.period_index),
            "debt_draws_by_tranche": self._initialize_tranche_tracking(),
            "equity_cumulative": pd.Series(0.0, index=self.timeline.period_index),
        }
    
    def _initialize_tranche_tracking(self) -> Dict[str, pd.Series]:
        """Initialize debt tranche tracking structures."""
        import pandas as pd
        
        debt_draws_by_tranche = {}
        if self.deal.financing:
            for facility in self.deal.financing.facilities:
                if hasattr(facility, 'kind') and facility.kind == 'construction':
                    for tranche in facility.tranches:
                        debt_draws_by_tranche[tranche.name] = pd.Series(0.0, index=self.timeline.period_index)
        
        return debt_draws_by_tranche
    
    def _execute_funding_cascade(self, base_uses: pd.Series, funding_components: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute institutional-grade funding cascade with comprehensive logic.
        
        Args:
            base_uses: Base uses before interest compounding
            funding_components: Initialized funding component structures
            
        Returns:
            Dictionary with cascade results and detailed tracking
        """
        import pandas as pd
        
        # Calculate equity target based on financing structure
        total_project_cost = base_uses.sum()
        equity_target = self._calculate_equity_target(total_project_cost)
        
        # Initialize working variables
        total_uses_with_interest = base_uses.copy()
        equity_cumulative = 0.0
        
        # Execute period-by-period funding cascade
        for i, period in enumerate(self.timeline.period_index):
            period_uses = total_uses_with_interest[period]
            
            if period_uses <= 0:
                funding_components["equity_cumulative"][period] = equity_cumulative
                continue
            
            # === EQUITY-FIRST FUNDING ===
            equity_contribution = self._calculate_equity_contribution(
                period_uses, equity_cumulative, equity_target
            )
            
            if equity_contribution > 0:
                funding_components["equity_contributions"][period] = equity_contribution
                equity_cumulative += equity_contribution
                period_uses -= equity_contribution
            
            funding_components["equity_cumulative"][period] = equity_cumulative
            
            # === DEBT-SECOND FUNDING ===
            if period_uses > 0 and self.deal.financing:
                debt_contribution = self._calculate_debt_contribution(
                    period_uses, total_uses_with_interest, i, funding_components
                )
                
                if debt_contribution > 0:
                    funding_components["debt_draws"][period] = debt_contribution
                    funding_components["loan_proceeds"][period] = debt_contribution
                    period_uses -= debt_contribution
            
            # === FUNDING GAP BACKSTOP ===
            # Ensure ALL Uses are funded, regardless of equity target
            if period_uses > 1.0:  # Allow small rounding differences
                # First, try to get more debt if available
                if self.deal.financing and period_uses > 10.0:  # Only for significant gaps
                    additional_debt = self._calculate_debt_contribution(
                        period_uses, total_uses_with_interest, i, funding_components
                    )
                    
                    if additional_debt > 0:
                        funding_components["debt_draws"][period] += additional_debt
                        funding_components["loan_proceeds"][period] += additional_debt
                        period_uses -= additional_debt
                
                # Fund any remaining gap with equity (regardless of target)
                if period_uses > 1.0:  # Still have unfunded Uses
                    additional_equity = period_uses
                    funding_components["equity_contributions"][period] += additional_equity
                    equity_cumulative += additional_equity
                    funding_components["equity_cumulative"][period] = equity_cumulative
                    period_uses = 0.0
            
            # === INTEREST COMPOUNDING ===
            if i > 0:  # Interest calculation starts from second period
                interest_impact = self._calculate_interest_impact(
                    funding_components, i, total_uses_with_interest
                )
                
                funding_components["interest_expense"][period] = interest_impact.get("cash_interest", 0.0)
        
        # Update total uses with interest
        funding_components["total_uses"] = total_uses_with_interest
        
        return {
            "equity_target": equity_target,
            "total_project_cost": total_uses_with_interest.sum(),
            "equity_funded": funding_components["equity_contributions"].sum(),
            "debt_funded": funding_components["debt_draws"].sum(),
            "interest_details": self._compile_interest_details(funding_components),
        }
    
    def _calculate_equity_target(self, total_project_cost: float) -> float:
        """Calculate equity funding target based on financing structure."""
        if self.deal.financing is None:
            return total_project_cost
        
        # Calculate maximum LTC from financing facilities
        max_ltc = self._get_max_ltc_from_financing()
        return total_project_cost * (1 - max_ltc)
    
    def _get_max_ltc_from_financing(self) -> float:
        """Get maximum LTC ratio from financing facilities."""
        max_ltc = 0.0
        
        if self.deal.financing:
            for facility in self.deal.financing.facilities:
                if hasattr(facility, 'kind') and facility.kind == 'construction':
                    for tranche in facility.tranches:
                        max_ltc = max(max_ltc, tranche.ltc_threshold)
        
        return max_ltc
    
    def _calculate_equity_contribution(self, period_uses: float, equity_cumulative: float, equity_target: float) -> float:
        """Calculate equity contribution for a period using equity-first logic."""
        if equity_cumulative >= equity_target:
            return 0.0
        
        remaining_equity_capacity = equity_target - equity_cumulative
        return min(period_uses, remaining_equity_capacity)
    
    def _calculate_debt_contribution(self, period_uses: float, total_uses: pd.Series, period_idx: int, funding_components: Dict[str, Any]) -> float:
        """Calculate debt contribution for a period using debt-second logic."""
        construction_facilities = [
            facility for facility in self.deal.financing.facilities
            if hasattr(facility, 'kind') and facility.kind == 'construction'
        ]
        
        if not construction_facilities:
            return 0.0
        
        # Use first construction facility (TODO: support multiple facilities)
        construction_facility = construction_facilities[0]
        
        # Calculate cumulative state
        cumulative_costs = total_uses.iloc[:period_idx+1].sum()
        cumulative_draws_by_tranche = {
            tranche.name: funding_components["debt_draws_by_tranche"][tranche.name].iloc[:period_idx+1].sum()
            for tranche in construction_facility.tranches
        }
        
        # Calculate period draws
        period_draws = construction_facility.calculate_period_draws(
            funding_needed=period_uses,
            total_project_cost=cumulative_costs,
            cumulative_costs_to_date=cumulative_costs,
            cumulative_draws_by_tranche=cumulative_draws_by_tranche
        )
        
        # Update tranche tracking
        total_debt_draw = 0.0
        for tranche_name, tranche_draw in period_draws.items():
            if tranche_draw > 0:
                funding_components["debt_draws_by_tranche"][tranche_name].iloc[period_idx] = tranche_draw
                total_debt_draw += tranche_draw
        
        return total_debt_draw
    
    def _calculate_interest_impact(self, funding_components: Dict[str, Any], period_idx: int, total_uses: pd.Series) -> Dict[str, float]:
        """
        Calculate interest impact for a period with institutional-grade PIK and reserve options.
        
        This method implements sophisticated interest calculation including:
        - Tranche-specific interest rates
        - Payment-in-kind (PIK) interest capitalization
        - Interest reserve funding mechanisms
        - Proper interest compounding logic
        
        Args:
            funding_components: Funding component tracking
            period_idx: Current period index
            total_uses: Total uses series (modified in place for compounding)
            
        Returns:
            Dictionary with detailed interest impact breakdown
        """
        previous_debt_balance = funding_components["debt_draws"].iloc[:period_idx].sum()
        
        if previous_debt_balance <= 0:
            return {"cash_interest": 0.0, "pik_interest": 0.0, "reserve_funded": 0.0}
        
        # Get construction facilities
        construction_facilities = [
            facility for facility in self.deal.financing.facilities
            if hasattr(facility, 'kind') and facility.kind == 'construction'
        ]
        
        if not construction_facilities:
            return {"cash_interest": 0.0, "pik_interest": 0.0, "reserve_funded": 0.0}
        
        construction_facility = construction_facilities[0]
        
        # Initialize interest components
        total_cash_interest = 0.0
        total_pik_interest = 0.0
        total_reserve_funded = 0.0
        
        # Calculate tranche-specific interest
        for tranche in construction_facility.tranches:
            # Calculate this tranche's proportion of total debt balance
            tranche_draws_to_date = funding_components["debt_draws_by_tranche"][tranche.name].iloc[:period_idx].sum()
            total_draws_to_date = sum(
                funding_components["debt_draws_by_tranche"][t.name].iloc[:period_idx].sum()
                for t in construction_facility.tranches
            )
            
            if total_draws_to_date > 0:
                tranche_proportion = tranche_draws_to_date / total_draws_to_date
                tranche_balance = previous_debt_balance * tranche_proportion
                
                # Calculate base interest using enhanced rate calculation
                current_period = self.timeline.period_index[period_idx]
                try:
                    # Use enhanced rate calculation for dynamic rates
                    annual_rate = tranche.interest_rate.get_rate_for_period(
                        current_period, 
                        self._get_rate_index_curve()
                    )
                    monthly_rate = annual_rate / 12
                except Exception:
                    # Fallback to basic rate calculation
                    monthly_rate = tranche.interest_rate.effective_rate / 12
                
                base_interest = tranche_balance * monthly_rate
                
                # Handle PIK interest (if tranche has PIK rate)
                if hasattr(tranche, 'pik_interest_rate') and tranche.pik_interest_rate:
                    pik_monthly_rate = tranche.pik_interest_rate / 12
                    pik_interest = tranche_balance * pik_monthly_rate
                    
                    # PIK interest is added to outstanding balance (not cash)
                    total_pik_interest += pik_interest
                    
                    # Base interest remains as cash interest
                    total_cash_interest += base_interest
                else:
                    # No PIK - all interest is cash
                    total_cash_interest += base_interest
        
        # Handle interest reserve funding
        fund_from_reserve = getattr(construction_facility, 'fund_interest_from_reserve', False)
        
        if fund_from_reserve:
            # Calculate interest reserve capacity
            interest_reserve_capacity = self._calculate_interest_reserve_capacity(
                construction_facility, total_uses, period_idx
            )
            
            # Calculate current reserve utilization
            current_reserve_utilization = sum(
                funding_components.get("interest_reserve_utilized", pd.Series(0.0, index=self.timeline.period_index)).iloc[:period_idx]
            )
            
            # Determine how much can be funded from reserve
            available_reserve = interest_reserve_capacity - current_reserve_utilization
            reserve_funded = min(total_cash_interest, available_reserve)
            
            if reserve_funded > 0:
                # Track reserve utilization
                if "interest_reserve_utilized" not in funding_components:
                    funding_components["interest_reserve_utilized"] = pd.Series(0.0, index=self.timeline.period_index)
                funding_components["interest_reserve_utilized"].iloc[period_idx] = reserve_funded
                
                # Reduce cash interest by reserve funded amount
                total_cash_interest -= reserve_funded
                total_reserve_funded = reserve_funded
        
        # Add cash interest to next period's uses (interest compounding)
        if (total_cash_interest > 0 and period_idx < len(self.timeline.period_index) - 1):
            next_period_idx = period_idx + 1
            total_uses.iloc[next_period_idx] += total_cash_interest
            
            # Track compounded interest
            if "compounded_interest" not in funding_components:
                funding_components["compounded_interest"] = pd.Series(0.0, index=self.timeline.period_index)
            funding_components["compounded_interest"].iloc[next_period_idx] += total_cash_interest
        
        # PIK interest is added to outstanding balance for next period's interest calculation
        if total_pik_interest > 0:
            # PIK interest increases the outstanding balance but doesn't become a cash use
            if "pik_balance" not in funding_components:
                funding_components["pik_balance"] = pd.Series(0.0, index=self.timeline.period_index)
            funding_components["pik_balance"].iloc[period_idx] = total_pik_interest
        
        return {
            "cash_interest": total_cash_interest,
            "pik_interest": total_pik_interest,
            "reserve_funded": total_reserve_funded,
        }
    
    def _calculate_interest_reserve_capacity(self, construction_facility, total_uses: pd.Series, period_idx: int) -> float:
        """
        Calculate interest reserve capacity based on facility parameters.
        
        Args:
            construction_facility: Construction facility object
            total_uses: Total uses series for calculating facility capacity
            period_idx: Current period index
            
        Returns:
            Interest reserve capacity amount
        """
        # Calculate total facility capacity based on cumulative costs
        cumulative_costs = total_uses.iloc[:period_idx+1].sum()
        
        total_facility_capacity = 0.0
        for i, tranche in enumerate(construction_facility.tranches):
            if i == 0:
                # First tranche: from 0 to its LTC threshold
                tranche_capacity = cumulative_costs * tranche.ltc_threshold
            else:
                # Subsequent tranches: from previous LTC to current LTC
                prev_tranche_ltc = construction_facility.tranches[i-1].ltc_threshold
                tranche_capacity = cumulative_costs * (tranche.ltc_threshold - prev_tranche_ltc)
            total_facility_capacity += tranche_capacity
        
        # Interest reserve capacity based on facility's configurable rate
        interest_reserve_rate = getattr(construction_facility, 'interest_reserve_rate', 0.15)
        return total_facility_capacity * interest_reserve_rate
    
    def _calculate_dscr_metrics(self) -> None:
        """
        Calculate debt service coverage ratio (DSCR) metrics and time series.
        
        Calculates DSCR metrics that depend on both asset operations and financing structure,
        providing comprehensive analysis including:
        - NOI extraction from asset analysis
        - Multi-facility debt service aggregation
        - DSCR statistics and covenant monitoring
        - Forward-looking DSCR projections for underwriting
        - Stress testing and sensitivity analysis
        """
        import pandas as pd

        from ..core.primitives import UnleveredAggregateLineKey
        from .results import DSCRSummary
        
        # Only calculate DSCR if we have financing
        if not self.financing_analysis.has_financing:
            self.financing_analysis.dscr_time_series = None
            self.financing_analysis.dscr_summary = None
            return
        
        try:
            # === Extract NOI Time Series ===
            noi_series = self._extract_noi_time_series()
            
            # === Aggregate Debt Service ===
            total_debt_service_series = self._aggregate_debt_service()
            
            # === Calculate DSCR Time Series ===
            dscr_series = self._calculate_dscr_time_series(noi_series, total_debt_service_series)
            
            # === Calculate DSCR Statistics ===
            dscr_summary_data = self._calculate_dscr_summary(dscr_series)
            
            # === Add Forward-Looking Analysis ===
            forward_analysis = self._calculate_forward_dscr_analysis(noi_series, total_debt_service_series)
            
            # Update financing analysis with metrics
            self.financing_analysis.dscr_time_series = dscr_series
            self.financing_analysis.dscr_summary = DSCRSummary(**dscr_summary_data) if not dscr_summary_data.get('error') else None
            
        except Exception as e:
            # Fallback: Use basic DSCR calculation if comprehensive calculation fails
            self._calculate_basic_dscr_fallback(e)
    
    def _extract_noi_time_series(self) -> pd.Series:
        """
        Extract NOI time series from unlevered asset analysis using type-safe enum access.
        
        Uses the new get_series method for robust, enum-based data access that eliminates
        brittle string matching. This implements the "Don't Ask, Tell" principle.
        
        Returns:
            NOI time series aligned with timeline periods
        """
        from ..core.primitives import UnleveredAggregateLineKey
        
        # Use the new type-safe accessor method
        return self.unlevered_analysis.get_series(
            UnleveredAggregateLineKey.NET_OPERATING_INCOME,
            self.timeline
        )
    
    def _aggregate_debt_service(self) -> pd.Series:
        """
        Aggregate debt service from all facilities into a single time series.
        
        Returns:
            Total debt service series aligned with timeline periods
        """
        import pandas as pd
        
        total_debt_service_series = pd.Series(0.0, index=self.timeline.period_index)
        
        if self.financing_analysis.debt_service:
            for facility_name, debt_service in self.financing_analysis.debt_service.items():
                if debt_service is not None and hasattr(debt_service, 'index'):
                    # Add this facility's debt service to the total
                    aligned_debt_service = debt_service.reindex(self.timeline.period_index, fill_value=0.0)
                    total_debt_service_series = total_debt_service_series.add(aligned_debt_service, fill_value=0)
        
        return total_debt_service_series
    
    def _calculate_dscr_time_series(self, noi_series: pd.Series, debt_service_series: pd.Series) -> pd.Series:
        """
        Calculate DSCR time series with proper handling of edge cases.
        
        Args:
            noi_series: Net Operating Income time series
            debt_service_series: Total debt service time series
            
        Returns:
            DSCR time series with institutional-grade calculation
        """
        import numpy as np
        import pandas as pd
        
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
        import numpy as np
        import pandas as pd
        
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
            summary[f"periods_below_{threshold:.2f}".replace(".", "_")] = int(periods_below)
        
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
            summary["trend_direction"] = "improving" if trend_slope > 0 else "declining" if trend_slope < 0 else "stable"
        
        # Volatility analysis
        if len(meaningful_dscr) > 2:
            # Calculate coefficient of variation
            cv = summary["standard_deviation"] / summary["average_dscr"]
            summary["coefficient_of_variation"] = float(cv)
            summary["volatility_category"] = (
                "low" if cv < 0.1 else 
                "moderate" if cv < 0.25 else 
                "high"
            )
        
        return summary
    
    def _calculate_forward_dscr_analysis(self, noi_series: pd.Series, debt_service_series: pd.Series) -> Dict[str, Any]:
        """
        Calculate forward-looking DSCR analysis for underwriting and covenant monitoring.
        
        Args:
            noi_series: NOI time series
            debt_service_series: Debt service time series
            
        Returns:
            Forward-looking DSCR analysis including stress scenarios
        """
        import numpy as np
        import pandas as pd
        
        analysis = {}
        
        # Year 1 stabilized DSCR (important for underwriting)
        if len(noi_series) >= 12:
            year1_noi = noi_series.iloc[:12].mean()  # Average monthly NOI in year 1
            year1_debt_service = debt_service_series.iloc[:12].mean()  # Average monthly debt service
            
            if year1_debt_service > 0:
                analysis["year1_stabilized_dscr"] = float(year1_noi / year1_debt_service)
            else:
                analysis["year1_stabilized_dscr"] = None
        
        # Forward 12-month average DSCR (rolling analysis)
        if len(noi_series) >= 12:
            rolling_noi = noi_series.rolling(window=12).mean()
            rolling_debt_service = debt_service_series.rolling(window=12).mean()
            
            forward_dscr = rolling_noi / rolling_debt_service.where(rolling_debt_service > 0)
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
            stressed_dscr = stressed_noi / debt_service_series.where(debt_service_series > 0)
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
        import pandas as pd

        from ..core.primitives import UnleveredAggregateLineKey
        from .results import DSCRSummary
        
        # Only calculate DSCR if we have financing
        if not self.financing_analysis.has_financing:
            self.financing_analysis.dscr_time_series = None
            return
        
        try:
            # Extract NOI time series using the new type-safe accessor
            noi_series = self.unlevered_analysis.get_series(
                UnleveredAggregateLineKey.NET_OPERATING_INCOME,
                self.timeline
            )
            
            # Aggregate all debt service from all facilities
            total_debt_service_series = pd.Series(0.0, index=self.timeline.period_index)
            
            if self.financing_analysis.debt_service:
                for facility_name, debt_service in self.financing_analysis.debt_service.items():
                    if debt_service is not None and hasattr(debt_service, 'index'):
                        total_debt_service_series = total_debt_service_series.add(debt_service, fill_value=0)
            
            # Calculate DSCR for each period where debt service is positive
            dscr_series = noi_series.divide(
                total_debt_service_series.where(total_debt_service_series > 0)
            ).fillna(0)
            
            # Add DSCR time series to financing analysis results
            self.financing_analysis.dscr_time_series = dscr_series
            
            # Calculate DSCR summary statistics
            self.financing_analysis.dscr_summary = DSCRSummary(
                minimum_dscr=dscr_series.min() if len(dscr_series) > 0 else None,
                average_dscr=dscr_series.mean() if len(dscr_series) > 0 else None,
                maximum_dscr=dscr_series.max() if len(dscr_series) > 0 else None,
                periods_below_1_0=(dscr_series < 1.0).sum() if len(dscr_series) > 0 else 0,
                periods_below_1_2=(dscr_series < 1.2).sum() if len(dscr_series) > 0 else 0,
            )
            
        except Exception:
            # Ultimate fallback: Set DSCR to None
            self.financing_analysis.dscr_time_series = None
            self.financing_analysis.dscr_summary = None
    
    def _calculate_single_entity_distributions(self, cash_flows) -> Dict[str, Any]:
        """Calculate single entity distribution results when there are no equity partners."""
        import pandas as pd
        
        if isinstance(cash_flows, pd.Series):
            # Calculate basic metrics
            total_distributions = cash_flows[cash_flows > 0].sum()
            total_investment = abs(cash_flows[cash_flows < 0].sum())
            
            # Calculate basic returns
            equity_multiple = total_distributions / total_investment if total_investment > 0 else 0.0
            
            # Calculate IRR (simplified)
            try:
                if total_investment > 0:
                    irr = (equity_multiple ** (1/len(cash_flows))) - 1
                else:
                    irr = 0.0
            except:
                irr = 0.0
            
            return {
                "distribution_method": "single_entity",
                "total_distributions": total_distributions,
                "total_investment": total_investment,
                "equity_multiple": equity_multiple,
                "irr": irr,
                "distributions": cash_flows,
                "waterfall_details": {
                    "single_entity_distributions": cash_flows,
                    "preferred_return": 0.0,
                    "promote_distributions": 0.0,
                },
                "fee_accounting_details": {
                    "total_partner_fees": 0.0,
                    "partner_fees_by_partner": {},
                    "remaining_cash_flows_after_fee": cash_flows,
                }
            }
        else:
            # Fallback for invalid cash flows
            return {
                "distribution_method": "single_entity",
                "total_distributions": 0.0,
                "total_investment": 0.0,
                "equity_multiple": 0.0,
                "irr": 0.0,
                "distributions": pd.Series(0.0, index=self.timeline.period_index),
                "waterfall_details": {
                    "single_entity_distributions": pd.Series(0.0, index=self.timeline.period_index),
                    "preferred_return": 0.0,
                    "promote_distributions": 0.0,
                },
                "fee_accounting_details": {
                    "total_partner_fees": 0.0,
                    "partner_fees_by_partner": {},
                    "remaining_cash_flows_after_fee": pd.Series(0.0, index=self.timeline.period_index),
                }
            }
    
    def _calculate_fee_distributions(self, cash_flows) -> Dict[str, Any]:
        """
        Calculate fee priority payments with dual-entry accounting.
        
        Features:
        - Uses actual payee Entity from each DealFee (not pro-rata GP allocation)
        - Dual-entry logic: fees are both project debit and partner credit
        - Processes fees according to their draw schedules
        - Maintains detailed audit trail for each fee and payee
        """
        import pandas as pd
        
        # Initialize fee tracking
        fee_accounting_details = {
            "total_partner_fees": 0.0,
            "partner_fees_by_partner": {},
            "fee_details_by_partner": {},  # Track individual fees per partner
            "fee_cash_flows_by_partner": {},  # Track fee timing per partner
            "third_party_fees": {},  # Track third-party fees separately
            "third_party_fee_details": {},  # Track individual third-party fees
            "third_party_fee_cash_flows": {},  # Track third-party fee timing
            "total_third_party_fees": 0.0,
            "remaining_cash_flows_after_fee": None,
        }
        
        if not isinstance(cash_flows, pd.Series):
            fee_accounting_details["remaining_cash_flows_after_fee"] = pd.Series(0.0, index=self.timeline.period_index)
            return fee_accounting_details
        
        # Start with original cash flows (ensure float dtype for calculations)
        remaining_cash_flows = cash_flows.copy().astype(float)
        
        # Only process fees if deal has both fees and equity partners
        if not self.deal.deal_fees or not self.deal.has_equity_partners:
            fee_accounting_details["remaining_cash_flows_after_fee"] = remaining_cash_flows
            return fee_accounting_details
        
        # Initialize partner tracking for all partners
        for partner in self.deal.equity_partners.partners:
            fee_accounting_details["partner_fees_by_partner"][partner.name] = 0.0
            fee_accounting_details["fee_details_by_partner"][partner.name] = []
            fee_accounting_details["fee_cash_flows_by_partner"][partner.name] = pd.Series(0.0, index=self.timeline.period_index, dtype=float)
        
        # === FEE PROCESSING ===
        
        # Step 1: Process each fee individually with its specific payee and timing
        total_fee_by_period = pd.Series(0.0, index=self.timeline.period_index, dtype=float)
        
        for fee in self.deal.deal_fees:
            try:
                # Calculate fee cash flows using the fee's draw schedule
                fee_cash_flows = fee.compute_cf(self.timeline)
                total_fee_amount = fee.calculate_total_fee()
                
                # Check if payee is an equity participant (Partner) or third party
                if fee.payee.is_equity_participant:
                    # Validate that the payee is actually a partner in this deal
                    payee_partner = None
                    for partner in self.deal.equity_partners.partners:
                        if partner.name == fee.payee.name:
                            payee_partner = partner
                            break
                    
                    if payee_partner is None:
                        logger.warning(f"Fee payee '{fee.payee.name}' is an equity partner but not in this deal. Skipping fee '{fee.name}'.")
                        continue
                else:
                    # Third-party fee - no partner validation needed
                    payee_partner = None
                
                # DEBIT: Add fee amounts to project uses (reduces distributable cash flow)
                total_fee_by_period += fee_cash_flows.reindex(self.timeline.period_index, fill_value=0.0)
                
                if payee_partner is not None:
                    # CREDIT: Allocate fee to the specific payee partner (dual-entry)
                    fee_accounting_details["partner_fees_by_partner"][payee_partner.name] += total_fee_amount
                    fee_accounting_details["fee_cash_flows_by_partner"][payee_partner.name] += fee_cash_flows.reindex(self.timeline.period_index, fill_value=0.0)
                    
                    # Track individual fee details for audit trail
                    fee_detail = {
                        "fee_name": fee.name,
                        "fee_type": getattr(fee, 'fee_type', 'Developer'),
                        "amount": total_fee_amount,
                        "payee": payee_partner.name,
                        "draw_schedule": type(fee.draw_schedule).__name__,
                        "description": getattr(fee, 'description', ''),
                    }
                    fee_accounting_details["fee_details_by_partner"][payee_partner.name].append(fee_detail)
                    
                    # Update total partner fees
                    fee_accounting_details["total_partner_fees"] += total_fee_amount
                    
                    logger.debug(f"Processed partner fee '{fee.name}': ${total_fee_amount:,.0f} -> {payee_partner.name} ({payee_partner.kind})")
                else:
                    # Handle third-party fee (single-entry - project cost only)
                    payee_name = fee.payee.name
                    
                    # Track third-party fees separately
                    if payee_name not in fee_accounting_details["third_party_fees"]:
                        fee_accounting_details["third_party_fees"][payee_name] = 0.0
                        fee_accounting_details["third_party_fee_details"][payee_name] = []
                        fee_accounting_details["third_party_fee_cash_flows"][payee_name] = pd.Series(0.0, index=self.timeline.period_index, dtype=float)
                    
                    fee_accounting_details["third_party_fees"][payee_name] += total_fee_amount
                    fee_accounting_details["third_party_fee_cash_flows"][payee_name] += fee_cash_flows.reindex(self.timeline.period_index, fill_value=0.0)
                    
                    # Track individual third-party fee details
                    fee_detail = {
                        "fee_name": fee.name,
                        "fee_type": getattr(fee, 'fee_type', 'Third Party'),
                        "amount": total_fee_amount,
                        "payee": payee_name,
                        "draw_schedule": type(fee.draw_schedule).__name__,
                        "description": getattr(fee, 'description', ''),
                    }
                    fee_accounting_details["third_party_fee_details"][payee_name].append(fee_detail)
                    
                    # Update total third-party fees
                    fee_accounting_details["total_third_party_fees"] += total_fee_amount
                    
                    logger.debug(f"Processed third-party fee '{fee.name}': ${total_fee_amount:,.0f} -> {payee_name} (Third Party)")
                
            except Exception as e:
                logger.error(f"Failed to process fee '{fee.name}': {e}")
                continue
        
        # Step 2: Apply priority payment logic - reduce cash flows by total fee amounts
        # Fees are paid as priority distributions before equity waterfall
        
        if fee_accounting_details["total_partner_fees"] > 0:
            # Fee deduction logic: Only reduce positive cash flows (distributions)
            # This ensures fees don't affect negative cash flows (investments)
            
            remaining_fees_to_deduct = total_fee_by_period.copy()
            
            for period in self.timeline.period_index:
                period_cash_flow = remaining_cash_flows[period]
                period_fees = remaining_fees_to_deduct[period]
                
                if period_cash_flow > 0 and period_fees > 0:
                    # Reduce positive cash flow by fees, but don't go negative
                    fee_deduction = min(period_cash_flow, period_fees)
                    remaining_cash_flows[period] -= fee_deduction
                    remaining_fees_to_deduct[period] -= fee_deduction
            
            # Handle any remaining fees that couldn't be deducted due to insufficient cash flow
            total_undeducted_fees = remaining_fees_to_deduct.sum()
            if total_undeducted_fees > 0:
                logger.warning(f"Could not deduct ${total_undeducted_fees:,.0f} in fees due to insufficient positive cash flows")
            
            logger.info(f"Applied ${fee_accounting_details['total_partner_fees'] - total_undeducted_fees:,.0f} in priority fee payments across {len(self.deal.deal_fees)} fee(s)")
        
        fee_accounting_details["remaining_cash_flows_after_fee"] = remaining_cash_flows
        return fee_accounting_details
    
    def _combine_fee_and_waterfall_results(self, fee_details: Dict[str, Any], waterfall_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Combine fee priority payments with waterfall distribution results.
        
        Features:
        - Dual-entry fee accounting with actual payees
        - Properly adjusts partner cash flows to include fee payments
        - Maintains detailed audit trail of fee vs. waterfall distributions
        - Recalculates all partner metrics accurately
        """
        import pandas as pd
        
        # Map DistributionCalculator output to Pydantic model structure
        distribution_method = waterfall_results.get("distribution_method", "error")
        total_metrics = waterfall_results.get("total_metrics", {})
        partner_distributions = waterfall_results.get("partner_distributions", {})
        
        # Extract total metrics
        total_investment = total_metrics.get("total_investment", 0.0)
        total_distributions = total_metrics.get("total_distributions", 0.0)
        equity_multiple = total_metrics.get("equity_multiple", 0.0)
        irr = total_metrics.get("irr", None)
        
        # Create the overall distributions series (for the deal level)
        if partner_distributions:
            # Sum all partner cash flows to get deal-level distributions
            deal_distributions = None
            for partner_name, partner_data in partner_distributions.items():
                partner_cf = partner_data.get("cash_flows")
                if isinstance(partner_cf, pd.Series):
                    if deal_distributions is None:
                        deal_distributions = partner_cf.copy()
                    else:
                        deal_distributions += partner_cf
            
            if deal_distributions is None:
                deal_distributions = pd.Series(0.0, index=self.timeline.period_index)
        else:
            deal_distributions = pd.Series(0.0, index=self.timeline.period_index)
        
        # === PARTNER RESULTS WITH FEE ACCOUNTING ===
        
        updated_partner_results = {}
        if partner_distributions and self.deal.has_equity_partners:
            for partner_name, partner_result in partner_distributions.items():
                updated_result = partner_result.copy()
                
                # Get fee amounts for this partner (using actual payee allocation)
                partner_fee_amount = fee_details["partner_fees_by_partner"].get(partner_name, 0.0)
                fee_cash_flows = fee_details["fee_cash_flows_by_partner"].get(partner_name, pd.Series(0.0, index=self.timeline.period_index))
                fee_details_list = fee_details["fee_details_by_partner"].get(partner_name, [])
                
                # Fee tracking for this partner
                updated_result["developer_fee_amount"] = partner_fee_amount
                updated_result["developer_fee_details"] = fee_details_list
                updated_result["fee_count"] = len(fee_details_list)
                
                # Update partner's cash flows to include fee payments
                partner_waterfall_cf = partner_result.get("cash_flows", pd.Series(0.0, index=self.timeline.period_index))
                updated_partner_cf = partner_waterfall_cf + fee_cash_flows
                updated_result["cash_flows"] = updated_partner_cf
                
                # Update deal-level distributions to include fees
                deal_distributions += fee_cash_flows
                
                if partner_fee_amount > 0:
                    # Update partner's total distributions and metrics
                    waterfall_distributions = partner_result.get("total_distributions", 0.0)
                    updated_result["total_distributions"] = waterfall_distributions + partner_fee_amount
                    updated_result["distributions_from_waterfall"] = waterfall_distributions
                    updated_result["distributions_from_fees"] = partner_fee_amount
                    
                    # Fee breakdown for this partner
                    updated_result["fee_details"] = {detail["fee_name"]: detail["amount"] for detail in fee_details_list}
                    updated_result["fee_cash_flows"] = fee_cash_flows
                    
                    # Update net profit
                    updated_result["net_profit"] = partner_result.get("net_profit", 0.0) + partner_fee_amount
                    
                    # Recalculate equity multiple if investment > 0
                    investment = partner_result.get("total_investment", 0.0)
                    if investment > 0:
                        updated_result["equity_multiple"] = updated_result["total_distributions"] / investment
                    else:
                        updated_result["equity_multiple"] = 0.0
                    
                    # Recalculate IRR if possible
                    try:
                        if isinstance(updated_partner_cf, pd.Series) and len(updated_partner_cf) > 1:
                            # Use pyxirr for more accurate IRR calculation
                            from pyxirr import xirr
                            dates = [period.to_timestamp().date() for period in updated_partner_cf.index]
                            partner_irr = xirr(dates, updated_partner_cf.values)
                            if partner_irr is not None:
                                updated_result["irr"] = float(partner_irr)
                    except Exception:
                        # Fallback: use existing IRR if available
                        updated_result["irr"] = partner_result.get("irr", None)
                else:
                    # No fees for this partner - maintain waterfall-only results
                    updated_result["distributions_from_waterfall"] = partner_result.get("total_distributions", 0.0)
                    updated_result["distributions_from_fees"] = 0.0
                    updated_result["developer_fee_amount"] = 0.0
                    updated_result["fee_count"] = 0
                    updated_result["fee_details"] = {}
                    updated_result["fee_cash_flows"] = pd.Series(0.0, index=self.timeline.period_index)
                
                # Add backward compatibility field (deprecated)
                updated_result["developer_fee"] = partner_fee_amount
                
                updated_partner_results[partner_name] = updated_result
                
                logger.debug(f"Partner result for {partner_name}: "
                           f"Waterfall=${updated_result.get('distributions_from_waterfall', 0):,.0f}, "
                           f"Fees=${updated_result.get('distributions_from_fees', 0):,.0f}, "
                           f"Total=${updated_result.get('total_distributions', 0):,.0f}")
        
        # Update total deal metrics to include partner fees
        total_partner_fees = fee_details["total_partner_fees"]
        if total_partner_fees > 0:
            total_distributions += total_partner_fees
            if total_investment > 0:
                equity_multiple = total_distributions / total_investment
        
        # === FEE ACCOUNTING DETAILS WITH TRACKING ===
        
        # Calculate total fees by type for reporting
        total_fees_by_type = {}
        fee_timing_summary = {}
        
        for partner_name, fee_list in fee_details["fee_details_by_partner"].items():
            if fee_list:
                fee_timing_summary[partner_name] = {}
                for fee_detail in fee_list:
                    fee_type = fee_detail.get("fee_type", "Developer")
                    fee_amount = fee_detail.get("amount", 0.0)
                    
                    if fee_type not in total_fees_by_type:
                        total_fees_by_type[fee_type] = 0.0
                    total_fees_by_type[fee_type] += fee_amount
                    
                    # Add timing information
                    partner_cf = fee_details["fee_cash_flows_by_partner"].get(partner_name, pd.Series(0.0, index=self.timeline.period_index))
                    for period_idx, period in enumerate(self.timeline.period_index):
                        if partner_cf[period] > 0:
                            period_str = str(period)
                            if period_str not in fee_timing_summary[partner_name]:
                                fee_timing_summary[partner_name][period_str] = 0.0
                            fee_timing_summary[partner_name][period_str] += partner_cf[period]
        
        # Update fee details with tracking
        updated_fee_details = fee_details.copy()
        updated_fee_details["total_fees_by_type"] = total_fees_by_type
        updated_fee_details["fee_timing_summary"] = fee_timing_summary
        
        # Convert fee_details_by_partner from list to dict format for Pydantic validation
        converted_fee_details = {}
        for partner_name, fee_list in updated_fee_details["fee_details_by_partner"].items():
            converted_fee_details[partner_name] = {}
            for fee_detail in fee_list:
                fee_name = fee_detail.get("fee_name", "Unknown Fee")
                fee_amount = fee_detail.get("amount", 0.0)
                converted_fee_details[partner_name][fee_name] = fee_amount
        
        updated_fee_details["fee_details_by_partner"] = converted_fee_details
        
        # Create waterfall details structure
        if distribution_method == "pari_passu":
            waterfall_details = {
                "preferred_return": 0.0,  # No preferred return in pari passu
                "promote_distributions": 0.0,  # No promotes in pari passu
                "partner_results": updated_partner_results,
                "total_waterfall_distributions": total_distributions - total_partner_fees,
                "total_fee_distributions": total_partner_fees,
            }
        else:
            # For actual waterfall deals, extract from waterfall_results
            waterfall_details = waterfall_results.get("waterfall_details", {
                "preferred_return": 0.0,
                "promote_distributions": 0.0,
                "partner_results": updated_partner_results,
            })
            waterfall_details["partner_results"] = updated_partner_results
            waterfall_details["total_waterfall_distributions"] = total_distributions - total_partner_fees
            waterfall_details["total_fee_distributions"] = total_partner_fees
        
        # Create final result structure matching Pydantic models
        combined_results = {
            "distribution_method": distribution_method,
            "total_distributions": total_distributions,
            "total_investment": total_investment,
            "equity_multiple": equity_multiple,
            "irr": irr,
            "distributions": deal_distributions,
            "waterfall_details": waterfall_details,
            "fee_accounting_details": updated_fee_details,
        }
        
        logger.info(f"Combined results: Total distributions=${total_distributions:,.0f} "
                   f"(Waterfall=${total_distributions - total_partner_fees:,.0f} + "
                   f"Fees=${total_partner_fees:,.0f})")
        
        return combined_results
    
    def _extract_unlevered_cash_flows(self) -> pd.Series:
        """
        Extract unlevered cash flows from the asset analysis.
        
        Returns:
            Net unlevered cash flows series aligned with timeline
        """
        import pandas as pd
        
        if self.unlevered_analysis.cash_flows is not None:
            cash_flows = self.unlevered_analysis.cash_flows
            
            # Try to extract net cash flows from the analysis
            if hasattr(cash_flows, 'columns'):
                # If DataFrame, try to get net cash flows column
                net_cf_columns = [col for col in cash_flows.columns if 'net' in col.lower() or 'cash' in col.lower()]
                if net_cf_columns:
                    return cash_flows[net_cf_columns[0]].reindex(self.timeline.period_index, fill_value=0.0)
                else:
                    # Sum all positive columns minus all negative columns
                    positive_cols = [col for col in cash_flows.columns if (cash_flows[col] > 0).any()]
                    negative_cols = [col for col in cash_flows.columns if (cash_flows[col] < 0).any()]
                    
                    net_cf = cash_flows[positive_cols].sum(axis=1) - cash_flows[negative_cols].sum(axis=1).abs()
                    return net_cf.reindex(self.timeline.period_index, fill_value=0.0)
            elif hasattr(cash_flows, 'index'):
                # If Series, use directly
                return cash_flows.reindex(self.timeline.period_index, fill_value=0.0)
        
        # Fallback: return zeros if no cash flows found
        return pd.Series(0.0, index=self.timeline.period_index)
    
    def _calculate_debt_service_series(self) -> pd.Series:
        """
        Calculate debt service time series from financing facilities.
        
        Returns:
            Total debt service series aligned with timeline
        """
        import pandas as pd
        
        total_debt_service = pd.Series(0.0, index=self.timeline.period_index)
        
        if self.deal.financing:
            for facility in self.deal.financing.facilities:
                try:
                    facility_debt_service = facility.calculate_debt_service(self.timeline)
                    total_debt_service += facility_debt_service.reindex(self.timeline.period_index, fill_value=0.0)
                except Exception as e:
                    # Log warning but continue - some facilities may not have debt service
                    logger.warning(f"Could not calculate debt service for {facility.name}: {e}")
        
        return total_debt_service
    
    def _calculate_disposition_proceeds(self) -> pd.Series:
        """
        Calculate disposition proceeds if there's a disposition event.
        
        Returns:
            Disposition proceeds series aligned with timeline
        """
        import pandas as pd
        
        disposition_proceeds = pd.Series(0.0, index=self.timeline.period_index)
        
        if self.deal.disposition:
            try:
                # Calculate disposition proceeds from the disposition model
                from ..analysis import AnalysisContext
                
                context = AnalysisContext(
                    timeline=self.timeline,
                    settings=self.settings,
                    property_data=self.deal.asset
                )
                
                # Get disposition cash flows
                disposition_cf = self.deal.disposition.compute_cf(context)
                disposition_proceeds = disposition_cf.reindex(self.timeline.period_index, fill_value=0.0)
                
                # Disposition proceeds should be positive
                disposition_proceeds = disposition_proceeds.abs()
                
            except Exception as e:
                # Log warning but continue
                logger.warning(f"Could not calculate disposition proceeds: {e}")
        
        return disposition_proceeds
    
    def _calculate_loan_payoff_series(self) -> pd.Series:
        """
        Calculate loan payoff amounts for refinancing or disposition.
        
        Returns:
            Loan payoff series aligned with timeline
        """
        import pandas as pd
        
        loan_payoff = pd.Series(0.0, index=self.timeline.period_index)
        
        if self.deal.financing:
            for facility in self.deal.financing.facilities:
                try:
                    # Check if facility has outstanding balance calculation
                    if hasattr(facility, 'get_outstanding_balance'):
                        for period in self.timeline.period_index:
                            balance = facility.get_outstanding_balance(period)
                            if balance > 0:
                                # Check if this is a refinancing or disposition period
                                if self.deal.disposition and period == self.deal.disposition.disposition_date:
                                    loan_payoff[period] += balance
                                elif hasattr(facility, 'refinance_timing') and facility.refinance_timing:
                                    refinance_period = self.timeline.period_index[facility.refinance_timing - 1]
                                    if period == refinance_period:
                                        loan_payoff[period] += balance
                                        
                except Exception as e:
                    # Log warning but continue
                    logger.warning(f"Could not calculate loan payoff for {facility.name}: {e}")
        
        return loan_payoff
    
    def _calculate_enhanced_debt_service(self, permanent_facility) -> pd.Series:
        """
        Calculate enhanced debt service for permanent facilities with institutional features.
        
        This method leverages the enhanced permanent facility features including:
        - Interest-only periods
        - Dynamic floating rates with index curves
        - Proper amortization scheduling
        
        Args:
            permanent_facility: PermanentFacility object with enhanced features
            
        Returns:
            Enhanced debt service time series
        """
        import pandas as pd
        
        try:
            # Check if this facility has dynamic refinancing
            if hasattr(permanent_facility, 'refinance_timing') and permanent_facility.refinance_timing:
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
                        from ..core.primitives import Timeline
                        loan_timeline = Timeline(
                            start_date=refinance_start,
                            duration_months=permanent_facility.loan_term_years * 12
                        )
                        
                        # Calculate enhanced amortization
                        amortization = permanent_facility.calculate_amortization(
                            timeline=loan_timeline,
                            loan_amount=loan_amount,
                            index_curve=self._get_rate_index_curve()
                        )
                        
                        # Extract debt service from amortization
                        schedule, _ = amortization.amortization_schedule
                        debt_service_series = schedule['Total Payment']
                        
                        # Align with main timeline
                        full_debt_service = pd.Series(0.0, index=self.timeline.period_index)
                        for i, payment in enumerate(debt_service_series):
                            timeline_idx = refinance_period_idx + i
                            if timeline_idx < len(self.timeline.period_index):
                                full_debt_service.iloc[timeline_idx] = payment
                        
                        return full_debt_service
            
            # Fallback to standard debt service calculation
            return permanent_facility.calculate_debt_service(self.timeline)
            
        except Exception as e:
            # Log warning and fallback to basic calculation
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Enhanced debt service calculation failed for {permanent_facility.name}: {e}")
            return permanent_facility.calculate_debt_service(self.timeline)
    
    def _get_refinanced_loan_amount(self, permanent_facility) -> float:
        """Get the loan amount from refinancing transactions for this facility."""
        if hasattr(self.financing_analysis, 'refinancing_transactions'):
            for transaction in self.financing_analysis.refinancing_transactions:
                if transaction.get('new_facility') == permanent_facility.name:
                    return transaction.get('new_loan_amount', 0.0)
        
        # Fallback to facility's specified loan amount
        return getattr(permanent_facility, 'loan_amount', 0.0)
    
    def _get_rate_index_curve(self) -> pd.Series:
        """
        Get rate index curve for dynamic rate calculations.
        
        In a real implementation, this would come from market data or user input.
        For now, we'll create a reasonable SOFR curve.
        """
        import numpy as np
        import pandas as pd
        
        # Create a sample SOFR curve that starts at 4.5% and gradually rises to 5.5%
        periods = len(self.timeline.period_index)
        start_rate = 0.045  # 4.5%
        end_rate = 0.055    # 5.5%
        
        # Linear interpolation
        rates = np.linspace(start_rate, end_rate, periods)
        
        return pd.Series(rates, index=self.timeline.period_index)
    
    def _extract_property_value_series(self) -> pd.Series:
        """
        Extract property value time series for refinancing analysis using intelligent estimation.
        
        Property values are typically not part of cash flow statements, so this method
        uses a sophisticated estimation approach based on NOI and cap rates, or falls back
        to acquisition cost appreciation modeling.
        
        Returns:
            Time series of property values by period
        """
        import pandas as pd

        from ..core.primitives import UnleveredAggregateLineKey
        
        # First try: Check if cash flows contain any property value columns using the enum approach
        # (This would be uncommon but some analyses might include asset value calculations)
        if self.unlevered_analysis.cash_flows is not None and hasattr(self.unlevered_analysis.cash_flows, 'columns'):
            # Look for any value-related columns in the actual data
            value_columns = [col for col in self.unlevered_analysis.cash_flows.columns 
                           if any(term in col.lower() for term in ['value', 'asset_value', 'property_value'])]
            if value_columns:
                return self.unlevered_analysis.cash_flows[value_columns[0]].reindex(
                    self.timeline.period_index, method='ffill'
                )
        
        # Primary approach: Calculate property value from NOI using market cap rate
        try:
            # Use the new type-safe NOI accessor
            noi_series = self.unlevered_analysis.get_series(
                UnleveredAggregateLineKey.NET_OPERATING_INCOME,
                self.timeline
            )
            
            if not noi_series.empty and noi_series.sum() > 0:
                # Use disposition cap rate if available, otherwise assume market rate
                cap_rate = 0.065  # 6.5% default market cap rate
                
                if self.deal.disposition and hasattr(self.deal.disposition, 'cap_rate'):
                    cap_rate = self.deal.disposition.cap_rate
                
                # Calculate property value as NOI / cap rate
                estimated_values = noi_series / cap_rate
                # Forward fill to handle any zero NOI periods
                return estimated_values.reindex(self.timeline.period_index, method='ffill')
                
        except Exception:
            # Continue to fallback approaches
            pass
        
        # Fallback: Use acquisition cost escalated over time with market appreciation
        if self.deal.acquisition and hasattr(self.deal.acquisition, 'acquisition_cost'):
            base_value = self.deal.acquisition.acquisition_cost
            # Use market appreciation rate (typically 2-4% annually)
            appreciation_rate = 0.03  # 3% annual appreciation assumption
            
            values = []
            for i, period in enumerate(self.timeline.period_index):
                years_elapsed = i / 12.0
                escalated_value = base_value * (1 + appreciation_rate) ** years_elapsed
                values.append(escalated_value)
            
            return pd.Series(values, index=self.timeline.period_index)
        
        # Ultimate fallback: Return zeros (prevents errors in downstream calculations)
        return pd.Series(0.0, index=self.timeline.period_index)
    
    def _extract_noi_series(self) -> pd.Series:
        """
        Extract Net Operating Income time series for refinancing analysis using type-safe enum access.
        
        Uses the new get_series method for robust, enum-based data access that eliminates
        brittle string matching. This implements the "Don't Ask, Tell" principle.
        
        Returns:
            Time series of NOI by period
        """
        from ..core.primitives import UnleveredAggregateLineKey
        
        # Use the new type-safe accessor method
        return self.unlevered_analysis.get_series(
            UnleveredAggregateLineKey.NET_OPERATING_INCOME,
            self.timeline
        )
    
    def _process_refinancing_cash_flows(self, refinancing_transactions: List[Dict[str, Any]]) -> None:
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
        if not hasattr(self.financing_analysis, 'refinancing_cash_flows'):
            self.financing_analysis.refinancing_cash_flows = {
                'loan_payoffs': pd.Series(0.0, index=self.timeline.period_index),
                'new_loan_proceeds': pd.Series(0.0, index=self.timeline.period_index),
                'closing_costs': pd.Series(0.0, index=self.timeline.period_index),
                'net_refinancing_proceeds': pd.Series(0.0, index=self.timeline.period_index)
            }
        
        for transaction in refinancing_transactions:
            transaction_date = transaction.get('transaction_date')
            
            if transaction_date in self.timeline.period_index:
                # Record cash flow events
                payoff_amount = transaction.get('payoff_amount', 0.0)
                new_loan_amount = transaction.get('new_loan_amount', 0.0)
                closing_costs = transaction.get('closing_costs', 0.0)
                net_proceeds = transaction.get('net_proceeds', 0.0)
                
                # Update cash flow series
                self.financing_analysis.refinancing_cash_flows['loan_payoffs'][transaction_date] = -payoff_amount
                self.financing_analysis.refinancing_cash_flows['new_loan_proceeds'][transaction_date] = new_loan_amount
                self.financing_analysis.refinancing_cash_flows['closing_costs'][transaction_date] = -closing_costs
                self.financing_analysis.refinancing_cash_flows['net_refinancing_proceeds'][transaction_date] = net_proceeds
                
                # Setup covenant monitoring for new permanent loans
                covenant_monitoring = transaction.get('covenant_monitoring', {})
                if covenant_monitoring.get('monitoring_enabled', False):
                    self._setup_covenant_monitoring(transaction, transaction_date)
    
    def _setup_covenant_monitoring(self, transaction: Dict[str, Any], start_date: pd.Period) -> None:
        """
        Setup covenant monitoring for a new permanent loan from refinancing.
        
        This creates the covenant monitoring framework for ongoing risk management
        of the new permanent loan throughout its lifecycle.
        
        Args:
            transaction: Refinancing transaction dictionary
            start_date: When covenant monitoring begins
        """
        # Get the new facility information
        new_facility_name = transaction.get('new_facility', 'Unknown Facility')
        covenant_params = transaction.get('covenant_monitoring', {})
        
        # Find the actual permanent facility object
        permanent_facility = None
        if self.deal.financing:
            for facility in self.deal.financing.permanent_facilities:
                if facility.name == new_facility_name:
                    permanent_facility = facility
                    break
        
        if permanent_facility and covenant_params.get('monitoring_enabled', False):
            try:
                # Create monitoring timeline starting from refinancing date
                monitoring_periods = self.timeline.period_index[self.timeline.period_index >= start_date]
                
                if len(monitoring_periods) > 0:
                    # Create mock timeline for covenant monitoring
                    class MockMonitoringTimeline:
                        def __init__(self, period_index):
                            self.period_index = period_index
                    
                    monitoring_timeline = MockMonitoringTimeline(monitoring_periods)
                    
                    # Get property value and NOI series for monitoring
                    property_value_series = self._extract_property_value_series()
                    noi_series = self._extract_noi_series()
                    
                    # Calculate covenant monitoring results
                    covenant_results = permanent_facility.calculate_covenant_monitoring(
                        timeline=monitoring_timeline,
                        property_value_series=property_value_series,
                        noi_series=noi_series,
                        loan_amount=transaction.get('new_loan_amount', 0.0)
                    )
                    
                    # Store covenant monitoring results in financing analysis
                    if not hasattr(self.financing_analysis, 'covenant_monitoring'):
                        self.financing_analysis.covenant_monitoring = {}
                    
                    self.financing_analysis.covenant_monitoring[new_facility_name] = {
                        'covenant_results': covenant_results,
                        'breach_summary': permanent_facility.get_covenant_breach_summary(covenant_results),
                        'monitoring_start_date': start_date,
                        'facility_name': new_facility_name
                    }
                    
            except Exception:
                # Log warning but don't fail the analysis
                pass
    
    def _calculate_total_distributions(self) -> float:
        """
        Calculate total distributions from asset operations.
        
        Returns:
            Total distributions amount
        """
        # Calculate total distributions from unlevered cash flows
        unlevered_cf = self._extract_unlevered_cash_flows()
        positive_cash_flows = unlevered_cf[unlevered_cf > 0].sum()
        
        # Add disposition proceeds if applicable
        disposition_proceeds = self._calculate_disposition_proceeds()
        total_disposition = disposition_proceeds.sum()
        
        return positive_cash_flows + total_disposition
    
    def _compile_interest_details(self, funding_components: Dict[str, Any]) -> Dict[str, Any]:
        """Compile detailed interest tracking information with PIK and reserve components."""
        import pandas as pd
        
        # Get PIK balance if available
        pik_balance = funding_components.get("pik_balance", pd.Series(0.0, index=self.timeline.period_index))
        
        # Get interest reserve utilization if available
        interest_reserve_utilized = funding_components.get("interest_reserve_utilized", pd.Series(0.0, index=self.timeline.period_index))
        
        # Calculate total interest (cash + PIK)
        total_interest = funding_components["interest_expense"] + pik_balance
        
        # Calculate outstanding balance with PIK
        outstanding_balance_with_pik = funding_components["debt_draws"].cumsum() + pik_balance.cumsum()
        
        return {
            "cash_interest": funding_components["interest_expense"],
            "pik_interest": pik_balance,
            "total_interest": total_interest,
            "outstanding_balance": outstanding_balance_with_pik,
            "interest_reserve_utilized": interest_reserve_utilized,
        }
    
    def _assemble_levered_cash_flow_results(self, uses_breakdown: pd.DataFrame, cascade_results: Dict[str, Any], funding_components: Dict[str, Any]) -> None:
        """
        Assemble final levered cash flow results with all components.
        
        Args:
            uses_breakdown: Period-by-period uses breakdown
            cascade_results: Results from funding cascade execution
            funding_components: Funding component tracking
        """
        import pandas as pd
        
        # Calculate final levered cash flows including refinancing events
        base_levered_cash_flows = (
            -funding_components["total_uses"] + 
            funding_components["equity_contributions"] + 
            funding_components["debt_draws"]
        )
        
        # Add refinancing events if they exist
        levered_cash_flows = base_levered_cash_flows.copy()
        if hasattr(self.financing_analysis, 'refinancing_cash_flows'):
            refinancing_cf = self.financing_analysis.refinancing_cash_flows
            # Add net refinancing proceeds (this is the key value for equity investors)
            levered_cash_flows += refinancing_cf['net_refinancing_proceeds'].reindex(
                self.timeline.period_index, fill_value=0.0
            )
        
        # Assemble cash flow components
        from .results import (
            CashFlowComponents,
            CashFlowSummary,
            FundingCascadeDetails,
            InterestCompoundingDetails,
            InterestReserveDetails,
            PIKInterestDetails,
        )
        
        # Enhanced cash flow components including refinancing events
        enhanced_loan_proceeds = funding_components["loan_proceeds"].copy()
        enhanced_loan_payoff = self._calculate_loan_payoff_series()
        
        # Add refinancing cash flows if they exist
        if hasattr(self.financing_analysis, 'refinancing_cash_flows'):
            refinancing_cf = self.financing_analysis.refinancing_cash_flows
            enhanced_loan_proceeds += refinancing_cf['new_loan_proceeds'].reindex(
                self.timeline.period_index, fill_value=0.0
            )
            enhanced_loan_payoff += refinancing_cf['loan_payoffs'].reindex(
                self.timeline.period_index, fill_value=0.0
            )
        
        cash_flow_components = CashFlowComponents(
            unlevered_cash_flows=self._extract_unlevered_cash_flows(),
            acquisition_costs=uses_breakdown["Acquisition Costs"],
            loan_proceeds=enhanced_loan_proceeds,
            debt_service=self._calculate_debt_service_series(),
            disposition_proceeds=self._calculate_disposition_proceeds(),
            loan_payoff=enhanced_loan_payoff,
            total_uses=funding_components["total_uses"],
            equity_contributions=funding_components["equity_contributions"],
            debt_draws=funding_components["debt_draws"],
            interest_expense=funding_components["interest_expense"],
        )
        
        cash_flow_summary = CashFlowSummary(
            total_investment=cascade_results["equity_funded"],
            total_distributions=self._calculate_total_distributions(),
            net_cash_flow=levered_cash_flows.sum(),
        )
        
        # Create detailed funding cascade components
        interest_compounding_details = InterestCompoundingDetails(
            base_uses=uses_breakdown["Total Uses"],
            compounded_interest=funding_components["compounded_interest"],
            total_uses_with_interest=funding_components["total_uses"],
            equity_target=cascade_results["equity_target"],
            equity_funded=cascade_results["equity_funded"],
            debt_funded=cascade_results["debt_funded"],
            funding_gap=cascade_results["total_project_cost"] - cascade_results["equity_funded"] - cascade_results["debt_funded"],
            total_project_cost=cascade_results["total_project_cost"],
        )
        
        pik_interest_details = PIKInterestDetails(
            cash_interest=cascade_results["interest_details"]["cash_interest"],
            pik_interest=cascade_results["interest_details"]["pik_interest"],
            total_interest=cascade_results["interest_details"]["total_interest"],
            outstanding_balance_with_pik=cascade_results["interest_details"]["outstanding_balance"],
        )
        
        # Calculate interest reserve capacity properly
        total_facility_capacity = 0.0
        cumulative_costs = funding_components["total_uses"].sum()
        capacity = 0.0  # Initialize default capacity
        
        # Get construction facilities to calculate capacity
        if self.deal.financing:
            for facility in self.deal.financing.facilities:
                if hasattr(facility, 'kind') and facility.kind == 'construction':
                    for i, tranche in enumerate(facility.tranches):
                        if i == 0:
                            # First tranche: from 0 to its LTC threshold
                            tranche_capacity = cumulative_costs * tranche.ltc_threshold
                        else:
                            # Subsequent tranches: from previous LTC to current LTC
                            prev_tranche_ltc = facility.tranches[i-1].ltc_threshold
                            tranche_capacity = cumulative_costs * (tranche.ltc_threshold - prev_tranche_ltc)
                        total_facility_capacity += tranche_capacity
                    
                    # Interest reserve capacity based on facility's configurable rate
                    interest_reserve_rate = getattr(facility, 'interest_reserve_rate', 0.15)
                    capacity = total_facility_capacity * interest_reserve_rate
                    break  # Use first construction facility
        
        interest_reserve_capacity_series = pd.Series(capacity, index=self.timeline.period_index)
        
        interest_reserve_details = InterestReserveDetails(
            interest_funded_from_reserve=cascade_results["interest_details"].get("interest_reserve_utilized", pd.Series(0.0, index=self.timeline.period_index)),
            interest_reserve_capacity=interest_reserve_capacity_series,
            interest_reserve_utilization=cascade_results["interest_details"].get("interest_reserve_utilized", pd.Series(0.0, index=self.timeline.period_index)),
        )
        
        funding_cascade_details = FundingCascadeDetails(
            uses_breakdown=uses_breakdown,
            equity_target=cascade_results["equity_target"],
            equity_contributed_cumulative=funding_components["equity_cumulative"],
            debt_draws_by_tranche=funding_components["debt_draws_by_tranche"],
            interest_compounding_details=interest_compounding_details,
            pik_interest_details=pik_interest_details,
            interest_reserve_details=interest_reserve_details,
        )
        
        # Populate the levered cash flows model
        self.levered_cash_flows.levered_cash_flows = levered_cash_flows
        self.levered_cash_flows.cash_flow_components = cash_flow_components
        self.levered_cash_flows.cash_flow_summary = cash_flow_summary
        self.levered_cash_flows.funding_cascade_details = funding_cascade_details