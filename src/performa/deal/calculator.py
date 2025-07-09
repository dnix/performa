"""
Deal Analysis Calculator - Core Orchestration Engine

This module contains the analyze_deal function which orchestrates the complete
levered deal analysis by integrating asset analysis, financing, and equity distributions.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

# Import the analysis module for context creation
from ..core.primitives import GlobalSettings, Timeline
from .deal import Deal

# TODO: Consider refactoring reporting functionality to dedicated reporting module


def analyze_deal(
    deal: Deal,
    timeline: Timeline,
    settings: Optional[GlobalSettings] = None,
) -> Dict[str, Any]:
    """
    Analyze a complete real estate investment deal with levered returns.
    
    This is the main public API for deal-level analysis. It orchestrates the complete
    workflow from unlevered asset analysis through financing integration to final
    partner distributions.
    
    The function performs analysis in distinct sequential passes:
    1. Unlevered asset analysis using the core analysis engine
    2. Financing integration and debt service calculations
    2.5. Ongoing performance metrics (DSCR time series)
    3. Acquisition and disposition cash flow integration
    4. Partner distribution calculations (equity waterfall)
    5. Deal-level performance metrics calculation
    
    Args:
        deal: Complete Deal specification with asset, financing, and equity structure
        timeline: Analysis timeline for cash flow projections
        settings: Optional analysis settings (defaults to standard settings)
        
    Returns:
        Dictionary containing complete deal analysis results including:
        - unlevered_analysis: Results from asset-level analysis
        - financing_analysis: Debt service, facilities, and DSCR time series
        - levered_cash_flows: Cash flows after debt service
        - partner_distributions: Equity waterfall results
        - deal_metrics: IRR, equity multiple, and other deal-level metrics
        
    Example:
        ```python
        # Simple stabilized acquisition
        deal = Deal(
            name="Office Acquisition",
            asset=office_property,
            acquisition=acquisition_terms,
            financing=FinancingPlan(facilities=[permanent_loan]),
            disposition=disposition_valuation
        )
        
        results = analyze_deal(deal, timeline)
        
        # Access results
        print(f"Partner IRR: {results['partner_distributions']['irr']:.2%}")
        print(f"Equity Multiple: {results['deal_metrics']['equity_multiple']:.2f}x")
        print(f"Minimum DSCR: {results['financing_analysis']['dscr_time_series'].min():.2f}")
        ```
    """
    
    # Initialize default settings if not provided
    if settings is None:
        settings = GlobalSettings()
    
    # Pass 1: Unlevered Asset Analysis
    unlevered_analysis = _analyze_unlevered_asset(deal, timeline, settings)
    
    # Pass 2: Financing Integration
    financing_analysis = _calculate_financing_integration(deal, unlevered_analysis, timeline, settings)
    
    # Pass 2.5: Calculate Ongoing Performance Metrics (DSCR Time Series)
    financing_analysis = _calculate_ongoing_performance_metrics(
        deal, unlevered_analysis, financing_analysis, timeline, settings
    )
    
    # Pass 3: Levered Cash Flow Calculation
    levered_cash_flows = _calculate_levered_cash_flows(deal, unlevered_analysis, financing_analysis, timeline, settings)
    
    # Pass 4: Partner Distribution Calculation
    partner_distributions = _calculate_partner_distributions(deal, levered_cash_flows, timeline, settings)
    
    # Pass 5: Deal-Level Metrics
    deal_metrics = _calculate_deal_metrics(deal, levered_cash_flows, partner_distributions, timeline, settings)
    
    # Assemble complete results
    return {
        "deal_summary": {
            "deal_name": deal.name,
            "deal_type": deal.deal_type,
            "asset_type": deal.asset.property_type,
            "is_development": deal.is_development_deal,
            "has_financing": deal.financing is not None,
            "has_disposition": deal.disposition is not None,
        },
        "unlevered_analysis": unlevered_analysis,
        "financing_analysis": financing_analysis,
        "levered_cash_flows": levered_cash_flows,
        "partner_distributions": partner_distributions,
        "deal_metrics": deal_metrics,
    }


def _analyze_unlevered_asset(
    deal: Deal,
    timeline: Timeline,
    settings: GlobalSettings,
) -> Dict[str, Any]:
    """
    Analyze the unlevered asset performance using the core analysis engine.
    
    This leverages the existing asset analysis infrastructure to get
    clean, unlevered cash flows that can then be integrated with financing.
    
    Args:
        deal: Deal containing the asset to analyze
        timeline: Analysis timeline
        settings: Analysis settings
        
    Returns:
        Unlevered analysis results from asset analysis
    """
    # Convert Pydantic models to dict representation for scenario creation
    # This approach handles discriminated union validation by ensuring the scenario
    # receives properly serialized model data
    
    from ..analysis import get_scenario_for_model
    
    # Use the public helper to find the scenario class
    scenario_cls = get_scenario_for_model(deal.asset)
    
    # Create scenario using dict representation to avoid Pydantic validation issues
    scenario_data = {
        'model': deal.asset.model_dump(),
        'timeline': timeline.model_dump(),
        'settings': settings.model_dump()
    }
    
    scenario = scenario_cls.model_validate(scenario_data)
    scenario.run()
    
    # Return a simplified results structure compatible with our deal analysis
    return {
        'scenario': scenario,
        'cash_flows': scenario.get_cash_flow_summary() if hasattr(scenario, 'get_cash_flow_summary') else None,
        'models': scenario._orchestrator.models if scenario._orchestrator else [],
    }


def _calculate_financing_integration(
    deal: Deal,
    unlevered_analysis: Dict[str, Any],
    timeline: Timeline,
    settings: GlobalSettings,
) -> Dict[str, Any]:
    """
    Calculate financing-related cash flows and debt service.
    
    This integrates the FinancingPlan with the unlevered asset cash flows
    to calculate debt service, loan proceeds, and refinancing transactions.
    
    Args:
        deal: Deal containing financing specifications
        unlevered_analysis: Results from unlevered asset analysis
        timeline: Analysis timeline
        settings: Analysis settings
        
    Returns:
        Financing analysis results including debt service and loan proceeds
    """
    if deal.financing is None:
        return {
            "has_financing": False,
            "debt_service": None,
            "loan_proceeds": None,
            "refinancing_transactions": None,
        }
    
    # Initialize financing analysis results
    financing_results = {
        "has_financing": True,
        "financing_plan": deal.financing.name,
        "facilities": [],
        "debt_service": {},
        "loan_proceeds": {},
        "refinancing_transactions": [],
    }
    
    # Process each facility in the financing plan
    for facility in deal.financing.facilities:
        facility_name = getattr(facility, 'name', 'Unnamed Facility')
        facility_type = type(facility).__name__
        
        # Add facility metadata
        financing_results["facilities"].append({
            "name": facility_name,
            "type": facility_type,
            "description": getattr(facility, 'description', ''),
        })
        
        # Calculate facility-specific cash flows
        if hasattr(facility, 'calculate_debt_service'):
            try:
                # Use facility's debt service calculation if available
                debt_service = facility.calculate_debt_service(timeline)
                financing_results["debt_service"][facility_name] = debt_service
            except Exception:
                # Fallback: Skip calculation if facility method fails
                financing_results["debt_service"][facility_name] = None
        
        if hasattr(facility, 'calculate_loan_proceeds'):
            try:
                # Use facility's loan proceeds calculation if available
                loan_proceeds = facility.calculate_loan_proceeds(timeline)
                financing_results["loan_proceeds"][facility_name] = loan_proceeds
            except Exception:
                # Fallback: Skip calculation if facility method fails
                financing_results["loan_proceeds"][facility_name] = None
    
    # Handle refinancing transactions if the plan supports them
    if deal.financing.has_refinancing:
        try:
            # Calculate refinancing transactions
            refinancing_transactions = deal.financing.calculate_refinancing_transactions(timeline)
            financing_results["refinancing_transactions"] = refinancing_transactions
        except Exception:
            # Fallback: Skip refinancing if calculation fails
            financing_results["refinancing_transactions"] = []
    
    return financing_results


def _calculate_ongoing_performance_metrics(
    deal: Deal,
    unlevered_analysis: Dict[str, Any],
    financing_analysis: Dict[str, Any],
    timeline: Timeline,
    settings: GlobalSettings,
) -> Dict[str, Any]:
    """
    Calculate ongoing performance metrics (DSCR time series).
    
    This calculates the Debt Service Coverage Ratio (DSCR) for each period in the timeline
    using the formula: DSCR = NOI / Debt Service
    
    This is the institutional-grade approach for monitoring loan covenant compliance
    and performance over the life of the asset.
    
    Args:
        deal: Deal specification
        unlevered_analysis: Unlevered asset analysis results containing NOI
        financing_analysis: Financing analysis results containing debt service
        timeline: Analysis timeline
        settings: Analysis settings
        
    Returns:
        Updated financing analysis results including DSCR time series
    """
    import pandas as pd

    from ..core.primitives import UnleveredAggregateLineKey
    
    # Only calculate DSCR if we have financing
    if not financing_analysis["has_financing"]:
        financing_analysis["dscr_time_series"] = None
        return financing_analysis
    
    try:
        # Extract NOI time series from unlevered analysis
        noi_series = None
        if unlevered_analysis and 'cash_flows' in unlevered_analysis:
            cash_flows = unlevered_analysis['cash_flows']
            if hasattr(cash_flows, 'columns') and UnleveredAggregateLineKey.NET_OPERATING_INCOME.value in cash_flows.columns:
                # Extract NOI column from DataFrame
                noi_series = cash_flows[UnleveredAggregateLineKey.NET_OPERATING_INCOME.value]
            elif hasattr(cash_flows, 'index'):
                # If it's a Series, assume it's NOI or use as fallback
                noi_series = cash_flows
        
        if noi_series is None:
            # Fallback: Create zero series if NOI can't be extracted
            noi_series = pd.Series(0.0, index=timeline.period_index)
        
        # Aggregate all debt service from all facilities into a single time series
        total_debt_service_series = pd.Series(0.0, index=timeline.period_index)
        
        if financing_analysis["debt_service"]:
            for facility_name, debt_service in financing_analysis["debt_service"].items():
                if debt_service is not None and hasattr(debt_service, 'index'):
                    # Add this facility's debt service to the total
                    total_debt_service_series = total_debt_service_series.add(debt_service, fill_value=0)
        
        # Calculate DSCR for each period where debt service is positive
        # DSCR = NOI / Debt Service
        # Avoid division by zero by using .where() to filter positive debt service
        dscr_series = noi_series.divide(
            total_debt_service_series.where(total_debt_service_series > 0)
        ).fillna(0)  # Fill NaN (where debt service is 0) with 0
        
        # Add DSCR time series to financing analysis results
        financing_analysis["dscr_time_series"] = dscr_series
        
        # Calculate DSCR summary statistics for quick reference
        financing_analysis["dscr_summary"] = {
            "minimum_dscr": dscr_series.min() if len(dscr_series) > 0 else None,
            "average_dscr": dscr_series.mean() if len(dscr_series) > 0 else None,
            "maximum_dscr": dscr_series.max() if len(dscr_series) > 0 else None,
            "periods_below_1_0": (dscr_series < 1.0).sum() if len(dscr_series) > 0 else 0,
            "periods_below_1_2": (dscr_series < 1.2).sum() if len(dscr_series) > 0 else 0,
        }
        
    except Exception as e:
        # Fallback: If calculation fails, set DSCR to None and log the issue
        financing_analysis["dscr_time_series"] = None
        financing_analysis["dscr_summary"] = {
            "error": f"DSCR calculation failed: {str(e)}"
        }
    
    return financing_analysis


def _calculate_levered_cash_flows(
    deal: Deal,
    unlevered_analysis: Dict[str, Any],
    financing_analysis: Dict[str, Any],
    timeline: Timeline,
    settings: GlobalSettings,
) -> Dict[str, Any]:
    """
    Calculate levered cash flows by integrating asset, financing, acquisition, and disposition.
    
    This combines all cash flow components to produce the final levered cash flows
    that will be distributed to equity partners.
    
    Args:
        deal: Deal specification
        unlevered_analysis: Unlevered asset analysis results
        financing_analysis: Financing analysis results
        timeline: Analysis timeline
        settings: Analysis settings
        
    Returns:
        Levered cash flow results
    """
    import pandas as pd
    
    # Use the new funding cascade orchestrator
    funding_results = _orchestrate_funding_and_financing(
        deal, unlevered_analysis, financing_analysis, timeline, settings
    )
    
    # Return the funding cascade results as levered cash flows
    return funding_results


def _orchestrate_funding_and_financing(
    deal: Deal,
    unlevered_analysis: Dict[str, Any],
    financing_analysis: Dict[str, Any],
    timeline: Timeline,
    settings: GlobalSettings,
) -> Dict[str, Any]:
    """
    Orchestrate the funding cascade for each period using the centralized funding loop.
    
    This is the core implementation of the funding cascade logic that:
    1. Calculates total Uses (cash outflows) for each period
    2. Implements equity-first funding cascade
    3. Implements debt-second funding using construction facilities
    4. Calculates and compounds interest on outstanding balances
    5. Assembles final levered cash flows
    
    Args:
        deal: Deal specification
        unlevered_analysis: Unlevered asset analysis results
        financing_analysis: Financing analysis results
        timeline: Analysis timeline
        settings: Analysis settings
        
    Returns:
        Dictionary containing levered cash flow results and component breakdown
    """
    import pandas as pd
    
    # Initialize component tracking for analysis
    components = {
        "unlevered_cash_flows": pd.Series(0.0, index=timeline.period_index),
        "acquisition_costs": pd.Series(0.0, index=timeline.period_index),
        "loan_proceeds": pd.Series(0.0, index=timeline.period_index),
        "debt_service": pd.Series(0.0, index=timeline.period_index),
        "disposition_proceeds": pd.Series(0.0, index=timeline.period_index),
        "loan_payoff": pd.Series(0.0, index=timeline.period_index),
        # New components for funding cascade
        "total_uses": pd.Series(0.0, index=timeline.period_index),
        "equity_contributions": pd.Series(0.0, index=timeline.period_index),
        "debt_draws": pd.Series(0.0, index=timeline.period_index),
        "interest_expense": pd.Series(0.0, index=timeline.period_index),
    }
    
    # === STEP A: Calculate Base Uses (before interest compounding) ===
    uses_df = _calculate_period_uses(deal, unlevered_analysis, timeline, settings)
    base_uses = uses_df["Total Uses"].copy()
    
    # === STEPS B, C, D: Implement Funding Cascade with Interest Compounding ===
    # This implements an iterative process where interest from period N becomes Use in period N+1
    funding_results = _calculate_funding_cascade_with_interest_compounding(
        deal, base_uses, timeline, settings
    )
    
    # Update components with funding cascade results
    components["total_uses"] = funding_results["total_uses_with_interest"]
    components["equity_contributions"] = funding_results["equity_contributions"]
    components["debt_draws"] = funding_results["debt_draws"]
    components["loan_proceeds"] = funding_results["loan_proceeds"]
    components["interest_expense"] = funding_results["interest_expense"]
    
    # === ASSEMBLE LEVERED CASH FLOWS ===
    # For all-equity deal: levered_cf = -total_uses + equity_contributions = 0 during construction
    # For leveraged deal: levered_cf = -total_uses + equity_contributions + debt_draws
    levered_cash_flows = -components["total_uses"] + components["equity_contributions"] + components["debt_draws"]
    
    # Calculate summary metrics
    total_investment = funding_results["equity_contributions"].sum()  # Updated to reflect actual equity invested
    total_distributions = 0.0  # Will be calculated in later steps (asset operations)
    net_cash_flow = levered_cash_flows.sum()
    
    return {
        "levered_cash_flows": levered_cash_flows,
        "cash_flow_components": components,
        "cash_flow_summary": {
            "total_investment": total_investment,
            "total_distributions": total_distributions,
            "net_cash_flow": net_cash_flow,
        },
        "funding_cascade_details": {
            "uses_breakdown": uses_df,
            "equity_target": funding_results["equity_target"],
            "equity_contributed_cumulative": funding_results["equity_contributed_cumulative"],
            "debt_draws_by_tranche": funding_results["debt_draws_by_tranche"],
            "interest_compounding_details": funding_results["interest_compounding_details"],
            "pik_interest_details": funding_results["pik_interest_details"],
            "interest_reserve_details": funding_results["interest_reserve_details"],
        }
    }


def _calculate_period_uses(
    deal: Deal,
    unlevered_analysis: Dict[str, Any],
    timeline: Timeline,
    settings: GlobalSettings,
) -> pd.DataFrame:
    """
    Calculate total Uses (cash outflows) for each period.
    
    This function extracts and combines all cash outflows that need to be funded:
    - Acquisition costs (from AcquisitionTerms)
    - Construction costs (from CapitalPlan)
    - Other project costs (from unlevered analysis)
    
    Args:
        deal: Deal specification
        unlevered_analysis: Unlevered asset analysis results
        timeline: Analysis timeline
        settings: Analysis settings
        
    Returns:
        DataFrame with period-by-period Uses breakdown
    """
    import pandas as pd

    from ..analysis import AnalysisContext
    
    # Initialize Uses DataFrame
    uses_df = pd.DataFrame(0.0, index=timeline.period_index, columns=[
        "Acquisition Costs",
        "Construction Costs", 
        "Developer Fees",
        "Other Project Costs",
        "Total Uses"
    ])
    
    # 1. Calculate acquisition costs
    if deal.acquisition:
        try:
            context = AnalysisContext(
                timeline=timeline, 
                settings=settings,
                property_data=deal.asset  # Add the required property_data parameter
            )
            acquisition_cf = deal.acquisition.compute_cf(context)
            
            # Acquisition costs are negative (outflows), make them positive for Uses
            acquisition_uses = acquisition_cf.abs()
            uses_df["Acquisition Costs"] = acquisition_uses.reindex(timeline.period_index, fill_value=0.0)
            
        except Exception as e:
            # Fallback: Skip acquisition if calculation fails
            print(f"Warning: Acquisition cost calculation failed: {e}")
    
    # 2. Calculate construction costs from CapitalPlan
    if hasattr(deal.asset, 'construction_plan') and deal.asset.construction_plan:
        try:
            context = AnalysisContext(
                timeline=timeline, 
                settings=settings,
                property_data=deal.asset  # Add the required property_data parameter
            )
            
            # Sum construction costs from all capital items
            for capital_item in deal.asset.construction_plan.capital_items:
                item_cf = capital_item.compute_cf(context)
                
                # Capital costs are typically positive, but represent cash outflows (Uses)
                item_uses = item_cf.abs()
                uses_df["Construction Costs"] += item_uses.reindex(timeline.period_index, fill_value=0.0)
                
        except Exception as e:
            # Fallback: Skip construction costs if calculation fails
            print(f"Warning: Construction cost calculation failed: {e}")
    
    # 3. Calculate developer fees
    if deal.deal_fees:
        try:
            # Process each deal fee using the DrawSchedule system
            for fee in deal.deal_fees:
                # Use compute_cf for consistency with CapitalItem
                fee_cf = fee.compute_cf(timeline)
                uses_df["Developer Fees"] += fee_cf.reindex(timeline.period_index, fill_value=0.0)
                        
        except Exception as e:
            # Fallback: Skip developer fees if calculation fails
            print(f"Warning: Deal fee calculation failed: {e}")
    
    # 4. Extract other project costs from unlevered analysis
    # TODO: This could include other costs like operating deficits during lease-up
    # For now, we'll leave this as zero and focus on acquisition + construction + developer fees
    
    # 5. Calculate total Uses for each period
    uses_df["Total Uses"] = (
        uses_df["Acquisition Costs"] + 
        uses_df["Construction Costs"] + 
        uses_df["Developer Fees"] +
        uses_df["Other Project Costs"]
    )
    
    return uses_df


def _calculate_equity_funding(
    deal: Deal,
    total_uses: pd.Series,
    timeline: Timeline,
) -> tuple[float, pd.Series, pd.Series]:
    """
    Calculate equity funding for each period using the equity-first funding cascade.
    
    This function implements the equity funding logic where:
    1. Equity target is calculated based on deal financing structure
    2. Equity contributes period-by-period up to the target
    3. Equity contributions are tracked cumulatively
    
    Args:
        deal: Deal specification
        total_uses: Total Uses (cash outflows) for each period
        timeline: Analysis timeline
        
    Returns:
        tuple: (equity_target, equity_contributions, equity_cumulative)
    """
    import pandas as pd
    
    # Calculate equity target based on financing structure
    total_project_cost = total_uses.sum()
    
    if deal.financing is None:
        # All-equity deal: equity target = 100% of project cost
        equity_target = total_project_cost
    else:
        # Leveraged deal: equity target = (1 - max_ltc) * project cost
        max_ltc = _get_max_ltc_from_financing(deal.financing)
        equity_target = total_project_cost * (1 - max_ltc)
    
    # Initialize equity contributions series
    equity_contributions = pd.Series(0.0, index=timeline.period_index)
    
    # Track cumulative equity invested
    equity_cumulative = 0.0
    equity_cumulative_series = pd.Series(0.0, index=timeline.period_index)
    
    # Implement equity funding cascade period by period
    for period in timeline.period_index:
        period_uses = total_uses[period]
        
        if period_uses > 0 and equity_cumulative < equity_target:
            # Calculate equity contribution for this period
            remaining_equity_capacity = equity_target - equity_cumulative
            equity_contribution = min(period_uses, remaining_equity_capacity)
            
            equity_contributions[period] = equity_contribution
            equity_cumulative += equity_contribution
        
        # Track cumulative equity
        equity_cumulative_series[period] = equity_cumulative
    
    return equity_target, equity_contributions, equity_cumulative_series


def _calculate_debt_funding(
    deal: Deal,
    total_uses: pd.Series,
    equity_target: float,
    equity_cumulative: pd.Series,
    timeline: Timeline,
) -> tuple[pd.Series, pd.Series, dict]:
    # FIXME: check this is not being used!
    """
    Calculate debt funding for each period using the debt-second funding cascade.
    
    This function implements the debt funding logic where:
    1. Debt funding begins after equity target is reached
    2. Uses ConstructionFacility.calculate_period_draws for institutional-grade logic
    3. Supports multi-tranche funding with seniority ordering
    4. Tracks debt draws by period and by tranche
    
    Args:
        deal: Deal specification
        total_uses: Total Uses (cash outflows) for each period
        equity_target: Equity target amount
        equity_cumulative: Cumulative equity invested by period
        timeline: Analysis timeline
        
    Returns:
        tuple: (debt_draws, loan_proceeds, debt_draws_by_tranche)
    """
    import pandas as pd
    
    # Initialize debt components
    debt_draws = pd.Series(0.0, index=timeline.period_index)
    loan_proceeds = pd.Series(0.0, index=timeline.period_index)
    debt_draws_by_tranche = {}
    
    # Only calculate debt funding if deal has financing
    if deal.financing is None:
        return debt_draws, loan_proceeds, debt_draws_by_tranche
    
    # Get construction facilities from financing plan
    construction_facilities = []
    for facility in deal.financing.facilities:
        if hasattr(facility, 'kind') and facility.kind == 'construction':
            construction_facilities.append(facility)
    
    if not construction_facilities:
        # No construction facilities, return zero debt funding
        return debt_draws, loan_proceeds, debt_draws_by_tranche
    
    # For now, use the first construction facility
    # TODO: Support multiple construction facilities
    # This would require coordinating draws across multiple facilities
    # and handling cross-collateralization and intercreditor agreements
    construction_facility = construction_facilities[0]
    
    # Initialize tranche tracking
    cumulative_draws_by_tranche = {tranche.name: 0.0 for tranche in construction_facility.tranches}
    
    # Initialize debt draws by tranche series
    for tranche in construction_facility.tranches:
        debt_draws_by_tranche[tranche.name] = pd.Series(0.0, index=timeline.period_index)
    
    # Calculate total project cost for LTC calculations
    total_project_cost = total_uses.sum()
    
    # Implement debt funding cascade period by period
    cumulative_costs = 0.0
    
    for period in timeline.period_index:
        period_uses = total_uses[period]
        period_equity_cumulative = equity_cumulative[period]
        
        # Add current period uses to cumulative costs
        cumulative_costs += period_uses
        
        # Only fund with debt if equity target has been reached and there are Uses
        if period_uses > 0 and period_equity_cumulative >= equity_target:
            # Calculate remaining funding need after equity
            remaining_funding_need = period_uses
            
            # Use construction facility to calculate available draws
            period_draws = construction_facility.calculate_period_draws(
                funding_needed=remaining_funding_need,
                total_project_cost=total_project_cost,
                cumulative_costs_to_date=cumulative_costs,
                cumulative_draws_by_tranche=cumulative_draws_by_tranche
            )
            
            # Update debt components with facility draws
            period_total_debt_draw = 0.0
            for tranche_name, tranche_draw in period_draws.items():
                if tranche_draw > 0:
                    debt_draws_by_tranche[tranche_name][period] = tranche_draw
                    cumulative_draws_by_tranche[tranche_name] += tranche_draw
                    period_total_debt_draw += tranche_draw
            
            # Update period totals
            debt_draws[period] = period_total_debt_draw
            loan_proceeds[period] = period_total_debt_draw  # For construction loans, proceeds = draws
    
    return debt_draws, loan_proceeds, debt_draws_by_tranche


def _get_max_ltc_from_financing(financing_plan) -> float:
    """
    Get the maximum LTC ratio from a financing plan.
    
    Args:
        financing_plan: FinancingPlan object
        
    Returns:
        float: Maximum LTC ratio across all construction facilities
    """
    max_ltc = 0.0
    
    for facility in financing_plan.facilities:
        if hasattr(facility, 'kind') and facility.kind == 'construction':
            if hasattr(facility, 'max_ltc'):
                max_ltc = max(max_ltc, facility.max_ltc)
    
    return max_ltc


def _calculate_interest_expense(
    deal: Deal,
    debt_draws: pd.Series,
    timeline: Timeline,
    settings: GlobalSettings,
) -> pd.Series:
    # FIXME: check this is not being used!
    """
    Calculate interest expense for each period (Step D).
    
    This function implements:
    1. Interest calculation on outstanding debt balances
    2. Interest compounding and capitalization
    3. PIK (payment-in-kind) interest handling
    4. Interest reserve funding
    
    Args:
        deal: Deal specification
        debt_draws: Debt draws by period
        timeline: Analysis timeline
        settings: Analysis settings
        
    Returns:
        pd.Series: Interest expense by period (becomes Use in next period)
    """
    import pandas as pd
    
    # Initialize interest expense series
    interest_expense = pd.Series(0.0, index=timeline.period_index)
    
    # Only calculate interest if deal has financing
    if deal.financing is None:
        return interest_expense
    
    # Get construction facilities from financing plan
    construction_facilities = []
    for facility in deal.financing.facilities:
        if hasattr(facility, 'kind') and facility.kind == 'construction':
            construction_facilities.append(facility)
    
    if not construction_facilities:
        return interest_expense
    
    # For now, use the first construction facility
    # TODO: Support multiple construction facilities
    construction_facility = construction_facilities[0]
    
    # Calculate cumulative debt balance over time
    debt_cumulative = debt_draws.cumsum()
    
    # Calculate interest for each period based on previous period's outstanding balance
    for i in range(1, len(timeline.period_index)):
        period = timeline.period_index[i]
        previous_balance = debt_cumulative.iloc[i-1]
        
        if previous_balance > 0:
            # Calculate weighted average interest rate across all tranches
            total_interest = 0.0
            total_balance = 0.0
            
            for tranche in construction_facility.tranches:
                # For simplicity, assume pro-rata allocation across tranches based on LTC
                if i == 1:
                    # First period with debt - use tranche LTC ratios for allocation
                    tranche_balance = previous_balance * (tranche.ltc_threshold / construction_facility.max_ltc)
                else:
                    # Subsequent periods - allocate proportionally
                    tranche_balance = previous_balance * (tranche.ltc_threshold / construction_facility.max_ltc)
                
                # Calculate interest for this tranche
                monthly_rate = tranche.interest_rate.effective_rate / 12
                tranche_interest = tranche_balance * monthly_rate
                
                total_interest += tranche_interest
                total_balance += tranche_balance
            
            # Handle interest reserve vs. cash interest
            if hasattr(construction_facility, 'fund_interest_from_reserve') and construction_facility.fund_interest_from_reserve:
                # Interest funded from reserve - doesn't become a Use
                interest_expense[period] = 0.0
            else:
                # Interest becomes a Use for next period
                interest_expense[period] = total_interest
    
    return interest_expense


def _calculate_funding_cascade_with_interest_compounding(
    deal: Deal,
    base_uses: pd.Series,
    timeline: Timeline,
    settings: GlobalSettings,
) -> dict:
    """
    Calculate the complete funding cascade with interest compounding (Steps B, C, D).
    
    This implements an iterative process where:
    1. Calculate equity funding up to target
    2. Calculate debt funding for remaining Uses
    3. Calculate interest on outstanding debt balances
    4. Add interest as Use for next period (compounding)
    5. Dynamically recalculate targets as project cost changes
    
    Args:
        deal: Deal specification
        base_uses: Base Uses before interest compounding
        timeline: Analysis timeline
        settings: Analysis settings
        
    Returns:
        dict: Complete funding cascade results with all components
    """
    import pandas as pd
    
    # Initialize components
    total_uses_with_interest = base_uses.copy()
    equity_contributions = pd.Series(0.0, index=timeline.period_index)
    debt_draws = pd.Series(0.0, index=timeline.period_index)
    loan_proceeds = pd.Series(0.0, index=timeline.period_index)
    interest_expense = pd.Series(0.0, index=timeline.period_index)
    compounded_interest = pd.Series(0.0, index=timeline.period_index)
    
    # Initialize tracking for detailed components
    debt_draws_by_tranche = {}
    if deal.financing:
        for facility in deal.financing.facilities:
            if hasattr(facility, 'kind') and facility.kind == 'construction':
                for tranche in facility.tranches:
                    debt_draws_by_tranche[tranche.name] = pd.Series(0.0, index=timeline.period_index)
    
    # Initialize equity target (will be dynamically updated)
    initial_project_cost = base_uses.sum()
    if deal.financing is None:
        max_ltc = 0.0
        base_equity_target = initial_project_cost
    else:
        max_ltc = _get_max_ltc_from_financing(deal.financing)
        base_equity_target = initial_project_cost * (1 - max_ltc)
    
    # Initialize PIK and interest reserve tracking
    pik_interest_details = {
        "cash_interest": pd.Series(0.0, index=timeline.period_index),
        "pik_interest": pd.Series(0.0, index=timeline.period_index),
        "total_interest": pd.Series(0.0, index=timeline.period_index),
        "outstanding_balance_with_pik": pd.Series(0.0, index=timeline.period_index)
    }
    
    interest_reserve_details = {
        "interest_funded_from_reserve": pd.Series(0.0, index=timeline.period_index),
        "interest_reserve_capacity": pd.Series(0.0, index=timeline.period_index),
        "interest_reserve_utilization": pd.Series(0.0, index=timeline.period_index)
    }
    
    # Implement period-by-period funding cascade with dynamic recalculation
    equity_cumulative = 0.0
    equity_cumulative_series = pd.Series(0.0, index=timeline.period_index)
    
    for i, period in enumerate(timeline.period_index):
        period_uses = total_uses_with_interest[period]
        
        # === STABLE EQUITY TARGET APPROACH ===
        # Use base equity target to avoid circular dependency with interest compounding
        # Interest compounding only starts after equity target is reached
        current_equity_target = base_equity_target
        
        # === STEP B: Equity Funding ===
        if period_uses > 0 and equity_cumulative < current_equity_target:
            remaining_equity_capacity = current_equity_target - equity_cumulative
            # Equity funds all Uses until target is reached
            equity_contribution = min(period_uses, remaining_equity_capacity)
            equity_contributions[period] = equity_contribution
            equity_cumulative += equity_contribution
            
            # Calculate remaining Uses after equity funding
            remaining_uses_after_equity = period_uses - equity_contribution
        else:
            remaining_uses_after_equity = period_uses
        
        equity_cumulative_series[period] = equity_cumulative
        
        # === STEP C: Debt Funding ===
        # Fund remaining Uses with debt after equity has contributed
        if remaining_uses_after_equity > 0 and deal.financing:
            construction_facilities = [
                facility for facility in deal.financing.facilities
                if hasattr(facility, 'kind') and facility.kind == 'construction'
            ]
            
            if construction_facilities:
                # For now, use the first construction facility
                # TODO: Support multiple construction facilities
                # This would require coordinating draws across multiple facilities
                # and handling cross-collateralization and intercreditor agreements
                construction_facility = construction_facilities[0]
                
                # Calculate cumulative costs and draws up to this period
                cumulative_costs = total_uses_with_interest.iloc[:i+1].sum()
                cumulative_draws_by_tranche = {
                    tranche.name: debt_draws_by_tranche[tranche.name].iloc[:i+1].sum()
                    for tranche in construction_facility.tranches
                }
                
                # Use cumulative costs as total project cost to ensure LTC constraints work properly
                # This prevents funding gaps when interest compounds into future periods
                period_draws = construction_facility.calculate_period_draws(
                    funding_needed=remaining_uses_after_equity,
                    total_project_cost=cumulative_costs,
                    cumulative_costs_to_date=cumulative_costs,
                    cumulative_draws_by_tranche=cumulative_draws_by_tranche
                )
                
                # Update debt components
                period_total_debt_draw = 0.0
                for tranche_name, tranche_draw in period_draws.items():
                    if tranche_draw > 0:
                        debt_draws_by_tranche[tranche_name][period] = tranche_draw
                        period_total_debt_draw += tranche_draw
                
                debt_draws[period] = period_total_debt_draw
                loan_proceeds[period] = period_total_debt_draw
                
                # Update remaining Uses after debt funding
                remaining_uses_after_equity -= period_total_debt_draw
        
        # === FUNDING GAP BACKSTOP ===
        # Ensure ALL Uses are funded after equity target is reached
        if remaining_uses_after_equity > 1.0 and equity_cumulative >= current_equity_target:
            debt_draws[period] += remaining_uses_after_equity
            loan_proceeds[period] += remaining_uses_after_equity
        
        # === STEP D: Interest Calculation with PIK and Interest Reserve ===
        if i > 0:  # Interest starts from second period
            previous_debt_balance = debt_draws.iloc[:i].sum()
            previous_pik_balance = pik_interest_details["pik_interest"].iloc[:i].sum()
            total_previous_balance = previous_debt_balance + previous_pik_balance
            
            if previous_debt_balance > 0 and deal.financing:
                construction_facilities = [
                    facility for facility in deal.financing.facilities
                    if hasattr(facility, 'kind') and facility.kind == 'construction'
                ]
                
                if construction_facilities:
                    construction_facility = construction_facilities[0]
                    
                    # Calculate interest with PIK functionality
                    total_cash_interest = 0.0
                    total_pik_interest = 0.0
                    
                    # Simplified interest calculation on debt balance only (PIK doesn't compound)
                    for tranche in construction_facility.tranches:
                        # Calculate proportion of balance allocated to this tranche
                        tranche_draws_to_date = debt_draws_by_tranche[tranche.name].iloc[:i].sum()
                        total_draws_to_date = sum(debt_draws_by_tranche[t.name].iloc[:i].sum() for t in construction_facility.tranches)
                        
                        if total_draws_to_date > 0:
                            tranche_proportion = tranche_draws_to_date / total_draws_to_date
                            tranche_balance = previous_debt_balance * tranche_proportion  # Use debt balance only
                            
                            # Calculate base interest
                            monthly_rate = tranche.interest_rate.effective_rate / 12
                            base_interest = tranche_balance * monthly_rate
                            
                            # Handle PIK interest
                            if hasattr(tranche, 'pik_interest_rate') and tranche.pik_interest_rate:
                                pik_rate = tranche.pik_interest_rate / 12
                                pik_interest = tranche_balance * pik_rate  # PIK on debt balance only
                                cash_interest = base_interest  # Base interest is still cash
                                
                                total_cash_interest += cash_interest
                                total_pik_interest += pik_interest
                            else:
                                # No PIK rate - all interest is cash
                                total_cash_interest += base_interest
                    
                    # Update PIK tracking
                    pik_interest_details["cash_interest"][period] = total_cash_interest
                    pik_interest_details["pik_interest"][period] = total_pik_interest
                    pik_interest_details["total_interest"][period] = total_cash_interest + total_pik_interest
                    pik_interest_details["outstanding_balance_with_pik"][period] = total_previous_balance + total_pik_interest
                    
                    # Handle interest reserve vs. cash interest
                    fund_from_reserve = (
                        hasattr(construction_facility, 'fund_interest_from_reserve') and 
                        construction_facility.fund_interest_from_reserve
                    )
                    
                    if fund_from_reserve:
                        # Interest funded from reserve - doesn't become a Use
                        interest_expense[period] = 0.0
                        interest_reserve_details["interest_funded_from_reserve"][period] = total_cash_interest
                        
                        # Calculate interest reserve capacity and utilization
                        # Reserve capacity should be sufficient to handle interest over the construction period
                        # Use cumulative costs to calculate total facility size
                        total_facility_capacity = 0.0
                        for tranche in construction_facility.tranches:
                            if tranche == construction_facility.tranches[0]:
                                # First tranche: from 0 to its LTC threshold
                                tranche_capacity = cumulative_costs * tranche.ltc_threshold
                            else:
                                # Subsequent tranches: from previous LTC to current LTC
                                prev_tranche_ltc = construction_facility.tranches[construction_facility.tranches.index(tranche) - 1].ltc_threshold
                                tranche_capacity = cumulative_costs * (tranche.ltc_threshold - prev_tranche_ltc)
                            total_facility_capacity += tranche_capacity
                        
                        # Interest reserve capacity based on facility's configurable rate (default 15%)
                        interest_reserve_capacity = total_facility_capacity * construction_facility.interest_reserve_rate
                        interest_reserve_utilization = interest_reserve_details["interest_funded_from_reserve"].iloc[:i+1].sum()
                        
                        interest_reserve_details["interest_reserve_capacity"][period] = interest_reserve_capacity
                        interest_reserve_details["interest_reserve_utilization"][period] = interest_reserve_utilization
                    else:
                        # Interest becomes a Use for current period (cash interest only)
                        interest_expense[period] = total_cash_interest
                        
                        # Add interest to next period's Uses (if there is a next period)
                        if i < len(timeline.period_index) - 1:
                            next_period = timeline.period_index[i + 1]
                            compounded_interest[next_period] += total_cash_interest
                            total_uses_with_interest[next_period] += total_cash_interest
    
    # Final equity target for reporting (base target for consistency with funding logic)
    final_project_cost = total_uses_with_interest.sum()
    total_equity_funded = equity_contributions.sum()
    total_debt_funded = debt_draws.sum()
    
    # Use base equity target for reporting to maintain consistency with funding decisions
    final_equity_target = base_equity_target
    
    # Prepare detailed tracking results
    interest_compounding_details = {
        "base_uses": base_uses,
        "compounded_interest": compounded_interest,
        "total_uses_with_interest": total_uses_with_interest,
        "equity_target": final_equity_target,
        "equity_funded": total_equity_funded,
        "debt_funded": total_debt_funded,
        "funding_gap": final_project_cost - total_equity_funded - total_debt_funded,
        "total_project_cost": final_project_cost
    }
    
    return {
        "total_uses_with_interest": total_uses_with_interest,
        "equity_contributions": equity_contributions,
        "equity_cumulative": equity_cumulative_series,
        "equity_target": final_equity_target,
        "equity_contributed_cumulative": equity_cumulative_series,
        "debt_draws": debt_draws,
        "loan_proceeds": loan_proceeds,
        "interest_expense": interest_expense,
        "debt_draws_by_tranche": debt_draws_by_tranche,
        "interest_compounding_details": interest_compounding_details,
        "pik_interest_details": pik_interest_details,
        "interest_reserve_details": interest_reserve_details
    }


def _calculate_partner_distributions(
    deal: Deal,
    levered_cash_flows: Dict[str, Any],
    timeline: Timeline,
    settings: GlobalSettings,
) -> Dict[str, Any]:
    """
    Calculate partner distributions using the equity waterfall with developer fee priority payments.
    
    This integrates the equity waterfall calculations with the levered cash flows
    to determine how distributions are allocated among equity partners. If the deal
    has a developer fee, it's treated as a priority payment to GP partners before
    standard waterfall distributions begin.
    
    Args:
        deal: Deal specification
        levered_cash_flows: Levered cash flow results
        timeline: Analysis timeline
        settings: Analysis settings
        
    Returns:
        Partner distribution results including developer fee tracking
    """
    import pandas as pd

    from .distribution_calculator import DistributionCalculator
    
    # Get the levered cash flows from the results
    if isinstance(levered_cash_flows, dict) and "levered_cash_flows" in levered_cash_flows:
        cash_flows = levered_cash_flows["levered_cash_flows"]
    else:
        # Fallback: assume levered_cash_flows is the Series directly
        cash_flows = levered_cash_flows
    
    # Check if deal has equity partners
    if not deal.has_equity_partners:
        # No equity partners defined - return simplified single-entity results
        if isinstance(cash_flows, pd.Series):
            # Calculate basic metrics
            total_distributions = cash_flows[cash_flows > 0].sum()
            total_investment = abs(cash_flows[cash_flows < 0].sum())
            
            # Calculate basic returns
            equity_multiple = total_distributions / total_investment if total_investment > 0 else 0.0
            
            # Calculate IRR (simplified)
            try:
                # Create cash flow array for IRR calculation
                cf_array = cash_flows.values
                
                # Simple IRR approximation
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
                "developer_fee_details": {
                    "total_developer_fee": 0.0,
                    "developer_fee_by_partner": {},
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
                "distributions": pd.Series(0.0, index=timeline.period_index),
                "waterfall_details": {
                    "single_entity_distributions": pd.Series(0.0, index=timeline.period_index),
                    "preferred_return": 0.0,
                    "promote_distributions": 0.0,
                },
                "developer_fee_details": {
                    "total_developer_fee": 0.0,
                    "developer_fee_by_partner": {},
                    "remaining_cash_flows_after_fee": pd.Series(0.0, index=timeline.period_index),
                }
            }
    
    # Deal has equity partners - calculate developer fee priority payments
    developer_fee_details = _calculate_developer_fee_distributions(deal, levered_cash_flows, timeline)
    
    # Get remaining cash flows after developer fee payments
    remaining_cash_flows = developer_fee_details["remaining_cash_flows_after_fee"]
    
    # Calculate standard waterfall distributions on remaining cash flows
    if isinstance(remaining_cash_flows, pd.Series):
        calculator = DistributionCalculator(deal.equity_partners)
        waterfall_results = calculator.calculate_distributions(remaining_cash_flows, timeline)
        
        # Combine developer fee and waterfall results
        combined_results = _combine_developer_fee_and_waterfall_results(
            developer_fee_details, waterfall_results, deal
        )
        
        return combined_results
    else:
        # Fallback for invalid cash flows
        return {
            "distribution_method": "error",
            "total_distributions": 0.0,
            "total_investment": 0.0,
            "equity_multiple": 0.0,
            "irr": 0.0,
            "distributions": pd.Series(0.0, index=timeline.period_index),
            "waterfall_details": {
                "error": "Invalid cash flow data",
                "preferred_return": 0.0,
                "promote_distributions": 0.0,
            },
            "developer_fee_details": developer_fee_details,
        }


def _calculate_developer_fee_distributions(
    deal: Deal,
    levered_cash_flows: Dict[str, Any],
    timeline: Timeline,
) -> Dict[str, Any]:
    """
    Calculate developer fee priority payments to GP partners.
    
    If the deal has a developer fee, it's treated as a priority payment to GP partners
    before standard waterfall distributions. The fee is allocated pro-rata among GP partners
    based on their GP share percentages.
    
    Args:
        deal: Deal specification
        levered_cash_flows: Levered cash flow results
        timeline: Analysis timeline
        
    Returns:
        Dictionary containing developer fee details and remaining cash flows
    """
    import pandas as pd
    
    # Initialize developer fee tracking
    developer_fee_details = {
        "total_developer_fee": 0.0,
        "developer_fee_by_partner": {},
        "remaining_cash_flows_after_fee": None,
    }
    
    # Get cash flows
    if isinstance(levered_cash_flows, dict) and "levered_cash_flows" in levered_cash_flows:
        cash_flows = levered_cash_flows["levered_cash_flows"]
    else:
        cash_flows = levered_cash_flows
    
    if not isinstance(cash_flows, pd.Series):
        # Return original cash flows if invalid
        developer_fee_details["remaining_cash_flows_after_fee"] = pd.Series(0.0, index=timeline.period_index)
        return developer_fee_details
    
    # Start with original cash flows
    remaining_cash_flows = cash_flows.copy()
    
    # Only calculate developer fees if deal has both fees and equity partners
    if not deal.deal_fees or not deal.has_equity_partners:
        developer_fee_details["remaining_cash_flows_after_fee"] = remaining_cash_flows
        return developer_fee_details
    
    # Calculate total developer fee amount from all fees
    total_developer_fee = 0.0
    
    # Sum all deal fees
    for fee in deal.deal_fees:
        total_developer_fee += fee.calculate_total_fee()
    
    # Get GP partners for fee allocation
    gp_partners = deal.equity_partners.gp_partners
    
    if not gp_partners or total_developer_fee <= 0:
        # No GP partners or no fee - return original cash flows
        developer_fee_details["remaining_cash_flows_after_fee"] = remaining_cash_flows
        return developer_fee_details
    
    # Initialize partner fee tracking
    for partner in deal.equity_partners.partners:
        developer_fee_details["developer_fee_by_partner"][partner.name] = 0.0
    
    # Allocate developer fee among GP partners pro-rata by GP share
    gp_total_share = deal.equity_partners.gp_total_share
    
    if gp_total_share > 0:
        for gp_partner in gp_partners:
            # Calculate this GP's share of the total developer fee
            gp_proportion = gp_partner.share / gp_total_share
            partner_developer_fee = total_developer_fee * gp_proportion
            
            developer_fee_details["developer_fee_by_partner"][gp_partner.name] = partner_developer_fee
    
    # Update total developer fee
    developer_fee_details["total_developer_fee"] = total_developer_fee
    
    # For simplicity, reduce the first positive cash flow by the developer fee amount
    # This represents the priority payment to GP before standard waterfall distributions
    positive_cash_flows = remaining_cash_flows[remaining_cash_flows > 0]
    
    if len(positive_cash_flows) > 0 and total_developer_fee > 0:
        # Find first positive cash flow period
        first_positive_period = positive_cash_flows.index[0]
        
        # Reduce the first positive cash flow by the developer fee
        # This ensures the fee is paid before standard waterfall distributions
        remaining_cash_flows[first_positive_period] = max(
            0, remaining_cash_flows[first_positive_period] - total_developer_fee
        )
    
    developer_fee_details["remaining_cash_flows_after_fee"] = remaining_cash_flows
    return developer_fee_details


def _combine_developer_fee_and_waterfall_results(
    developer_fee_details: Dict[str, Any],
    waterfall_results: Dict[str, Any],
    deal: Deal,
) -> Dict[str, Any]:
    """
    Combine developer fee priority payments with waterfall distribution results.
    
    This creates a unified result that shows both developer fee payments
    and standard waterfall distributions for each partner.
    
    Args:
        developer_fee_details: Developer fee calculation results
        waterfall_results: Standard waterfall distribution results
        deal: Deal specification
        
    Returns:
        Combined distribution results
    """
    import pandas as pd
    
    # Start with waterfall results as base
    combined_results = waterfall_results.copy()
    
    # Add developer fee information
    combined_results["developer_fee_details"] = developer_fee_details
    
    # Update partner-specific results to include developer fees
    if "partner_results" in waterfall_results and deal.has_equity_partners:
        updated_partner_results = {}
        
        for partner_name, partner_result in waterfall_results["partner_results"].items():
            updated_result = partner_result.copy()
            
            # Add developer fee to this partner's results
            developer_fee = developer_fee_details["developer_fee_by_partner"].get(partner_name, 0.0)
            
            if developer_fee > 0:
                # Update partner's total distributions and metrics
                updated_result["total_distributions"] = partner_result.get("total_distributions", 0) + developer_fee
                updated_result["net_profit"] = partner_result.get("net_profit", 0) + developer_fee
                updated_result["developer_fee"] = developer_fee
                
                # Recalculate equity multiple if investment > 0
                investment = partner_result.get("total_investment", 0)
                if investment > 0:
                    updated_result["equity_multiple"] = updated_result["total_distributions"] / investment
                else:
                    updated_result["equity_multiple"] = 0.0
            else:
                updated_result["developer_fee"] = 0.0
            
            updated_partner_results[partner_name] = updated_result
        
        combined_results["partner_results"] = updated_partner_results
    
    # Update total deal metrics to include developer fee
    total_developer_fee = developer_fee_details["total_developer_fee"]
    
    if total_developer_fee > 0:
        combined_results["total_distributions"] = waterfall_results.get("total_distributions", 0) + total_developer_fee
        combined_results["net_profit"] = waterfall_results.get("net_profit", 0) + total_developer_fee
        
        # Recalculate deal-level equity multiple
        total_investment = waterfall_results.get("total_investment", 0)
        if total_investment > 0:
            combined_results["equity_multiple"] = combined_results["total_distributions"] / total_investment
    
    return combined_results


def _calculate_deal_metrics(
    deal: Deal,
    levered_cash_flows: Dict[str, Any],
    partner_distributions: Dict[str, Any],
    timeline: Timeline,
    settings: GlobalSettings,
) -> Dict[str, Any]:
    """
    Calculate deal-level performance metrics.
    
    This calculates key metrics like IRR, equity multiple, and other
    deal-level performance indicators.
    
    Args:
        deal: Deal specification
        levered_cash_flows: Levered cash flow results
        partner_distributions: Partner distribution results
        timeline: Analysis timeline
        settings: Analysis settings
        
    Returns:
        Deal-level metrics
    """
    import pandas as pd
    from pyxirr import xirr
    
    # Initialize metrics
    metrics = {
        "irr": None,
        "equity_multiple": None,
        "total_return": None,
        "annual_yield": None,
        "cash_on_cash": None,
        "total_equity_invested": None,
        "total_equity_returned": None,
        "net_profit": None,
        "hold_period_years": None,
    }
    
    # Get levered cash flows
    cash_flows = levered_cash_flows.get("levered_cash_flows")
    if cash_flows is None or len(cash_flows) == 0:
        return metrics
    
    try:
        # Calculate basic metrics
        negative_flows = cash_flows[cash_flows < 0]
        positive_flows = cash_flows[cash_flows > 0]
        
        total_equity_invested = abs(negative_flows.sum())
        total_equity_returned = positive_flows.sum()
        net_profit = cash_flows.sum()
        
        # Calculate hold period
        hold_period_years = len(timeline.period_index) / 12.0  # Convert months to years
        
        # Calculate equity multiple
        equity_multiple = None
        if total_equity_invested > 0:
            equity_multiple = total_equity_returned / total_equity_invested
        
        # Calculate IRR using PyXIRR
        irr = None
        if len(cash_flows) > 1 and total_equity_invested > 0:
            try:
                # Create dates for each cash flow
                dates = [period.to_timestamp().date() for period in cash_flows.index]
                
                # Calculate IRR using PyXIRR (more accurate than numpy-financial)
                irr = xirr(dates, cash_flows.values)
                
                # Convert to percentage if successful
                if irr is not None:
                    irr = float(irr)
                    
            except Exception:
                # Fallback: Skip IRR calculation if it fails
                pass
        
        # Calculate total return
        total_return = None
        if total_equity_invested > 0:
            total_return = (total_equity_returned - total_equity_invested) / total_equity_invested
        
        # Calculate annual yield (simplified)
        annual_yield = None
        if total_return is not None and hold_period_years > 0:
            annual_yield = total_return / hold_period_years
        
        # Calculate cash-on-cash return (first year)
        cash_on_cash = None
        if total_equity_invested > 0 and len(cash_flows) > 12:
            # Calculate cash distributions in first 12 months
            first_year_distributions = positive_flows[:12].sum()
            cash_on_cash = first_year_distributions / total_equity_invested
        
        # Update metrics
        metrics.update({
            "irr": irr,
            "equity_multiple": equity_multiple,
            "total_return": total_return,
            "annual_yield": annual_yield,
            "cash_on_cash": cash_on_cash,
            "total_equity_invested": total_equity_invested,
            "total_equity_returned": total_equity_returned,
            "net_profit": net_profit,
            "hold_period_years": hold_period_years,
        })
        
    except Exception:
        # Fallback: Return empty metrics if calculation fails
        pass
    
    return metrics 