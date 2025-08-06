# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Deal Analysis Result Models

This module defines strongly-typed Pydantic models for all deal analysis results,
replacing the dictionary-based returns with type-safe, validated structures.

Key Features:
- Full pandas Series/DataFrame support for time series data
- Discriminated Union types for conditional returns
- Comprehensive field validation
- IDE autocompletion and type checking
- Performance optimized for visualization tools
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator

# Add import for the enum
from ..core.primitives import Timeline, UnleveredAggregateLineKey

# =============================================================================
# Base Result Model
# =============================================================================

class ResultModel(BaseModel):
    """Base result model for all analysis results."""
    model_config = ConfigDict(
        validate_assignment=True, 
        frozen=False, 
        arbitrary_types_allowed=True
    )


# =============================================================================
# Core Analysis Result Models
# =============================================================================

class DealSummary(ResultModel):
    """High-level deal characteristics and metadata."""
    
    deal_name: str = Field(None, description="Deal name for identification")
    deal_type: str = Field(None, description="Deal classification (development, office_acquisition, etc.)")
    asset_type: str = Field(None, description="Property type from asset enum")
    is_development: bool = Field(None, description="Whether this is a development deal")
    has_financing: bool = Field(None, description="Whether deal includes financing")
    has_disposition: bool = Field(None, description="Whether deal includes disposition")


class DealMetricsResult(ResultModel):
    """Deal-level performance metrics and returns."""
    
    # Core Return Metrics
    irr: Optional[float] = Field(None, description="Internal rate of return (annualized)")
    equity_multiple: Optional[float] = Field(None, description="Total distributions / total investment")
    total_return: Optional[float] = Field(None, description="Total return percentage")
    
    # Yield Metrics
    annual_yield: Optional[float] = Field(None, description="Annualized yield percentage")
    cash_on_cash: Optional[float] = Field(None, description="First year cash-on-cash return")
    
    # Investment Summary
    total_equity_invested: Optional[float] = Field(None, description="Total equity investment amount")
    total_equity_returned: Optional[float] = Field(None, description="Total equity distributions received")
    net_profit: Optional[float] = Field(None, description="Net profit (distributions - investment)")
    
    # Timing
    hold_period_years: Optional[float] = Field(None, description="Hold period in years")


# =============================================================================
# Unlevered Analysis Models
# =============================================================================

class UnleveredAnalysisResult(ResultModel):
    """Results from asset-level unlevered analysis."""
    
    scenario: Any = Field(None, description="Asset analysis scenario object (AnalysisScenarioBase)")
    cash_flows: Optional[pd.DataFrame] = Field(None, description="Asset cash flow summary DataFrame")
    models: List[Any] = Field(default_factory=list, description="Orchestrator models list")

    @field_validator('cash_flows')
    @classmethod
    def validate_cash_flows(cls, v):
        """Validate cash_flows is a pandas DataFrame if provided."""
        if v is not None and not isinstance(v, pd.DataFrame):
            raise ValueError('cash_flows must be a pandas DataFrame or None')
        return v

    def get_series(self, key: UnleveredAggregateLineKey, timeline: Timeline) -> pd.Series:
        """
        Safely retrieves a cash flow series using a type-safe enum key.
        
        This provides a stable interface for other modules to access results
        without knowing the internal column structure of the cash_flows DataFrame.
        Implements the "Don't Ask, Tell" principle by encapsulating data access logic.
        
        Args:
            key: UnleveredAggregateLineKey enum specifying which series to retrieve
            timeline: Timeline object providing the target period index for alignment
            
        Returns:
            pd.Series: The requested cash flow series, aligned to the timeline's period_index
                      and filled with zeros for missing periods
                      
        Example:
            >>> noi_series = result.get_series(
            ...     UnleveredAggregateLineKey.NET_OPERATING_INCOME, 
            ...     timeline
            ... )
            >>> property_value_series = result.get_series(
            ...     UnleveredAggregateLineKey.EFFECTIVE_GROSS_INCOME,
            ...     timeline
            ... )
        """
        if self.cash_flows is not None and hasattr(self.cash_flows, 'columns'):
            # Check if the exact enum value exists as a column
            if key.value in self.cash_flows.columns:
                # Return the series, aligned to the provided timeline
                return self.cash_flows[key.value].reindex(timeline.period_index, fill_value=0.0)
        
        # If the key is not found, return a zero-filled series with the correct index
        # to prevent downstream errors. This provides graceful degradation.
        return pd.Series(0.0, index=timeline.period_index, name=key.value)


# =============================================================================
# Financing Analysis Models
# =============================================================================

class FacilityInfo(ResultModel):
    """Metadata for individual financing facility."""
    
    name: str = Field(None, description="Facility name")
    type: str = Field(None, description="Facility class name (e.g., ConstructionFacility)")
    description: str = Field(default="", description="Facility description")


class DSCRSummary(ResultModel):
    """DSCR performance summary statistics."""
    
    minimum_dscr: Optional[float] = Field(None, description="Minimum DSCR over analysis period")
    average_dscr: Optional[float] = Field(None, description="Average DSCR over analysis period")
    maximum_dscr: Optional[float] = Field(None, description="Maximum DSCR over analysis period")
    periods_below_1_0: int = Field(0, description="Number of periods with DSCR < 1.0")
    periods_below_1_2: int = Field(0, description="Number of periods with DSCR < 1.2")


class FinancingAnalysisResult(ResultModel):
    """Results from financing integration and debt analysis."""
    
    # Core Financing Info
    has_financing: bool = Field(None, description="Whether deal includes financing")
    financing_plan: Optional[str] = Field(None, description="Financing plan name")
    facilities: List[FacilityInfo] = Field(default_factory=list, description="List of financing facilities")
    
    # Cash Flow Components (facility_name -> time series)
    debt_service: Dict[str, Optional[pd.Series]] = Field(
        default_factory=dict, 
        description="Debt service by facility name"
    )
    loan_proceeds: Dict[str, Optional[pd.Series]] = Field(
        default_factory=dict,
        description="Loan proceeds by facility name"
    )
    refinancing_transactions: List[Any] = Field(  # TODO: revisit typing here
        default_factory=list,
        description="Refinancing transaction objects"
    )
    
    # Performance Metrics
    dscr_time_series: Optional[pd.Series] = Field(None, description="DSCR time series")
    dscr_summary: Optional[DSCRSummary] = Field(None, description="DSCR summary statistics")

    @field_validator('dscr_time_series')
    @classmethod
    def validate_dscr_time_series(cls, v):
        """Validate DSCR time series is a pandas Series if provided."""
        if v is not None and not isinstance(v, pd.Series):
            raise ValueError('dscr_time_series must be a pandas Series or None')
        return v

    @field_validator('debt_service', 'loan_proceeds')
    @classmethod
    def validate_facility_series(cls, v):
        """Validate facility dictionaries contain pandas Series or None."""
        if v:
            for facility_name, series in v.items():
                if series is not None and not isinstance(series, pd.Series):
                    raise ValueError(f'Series for facility {facility_name} must be pandas Series or None')
        return v


# =============================================================================
# Cash Flow Analysis Models
# =============================================================================

class CashFlowComponents(ResultModel):
    """Individual cash flow component time series."""
    
    unlevered_cash_flows: pd.Series = Field(None, description="Unlevered cash flows")
    acquisition_costs: pd.Series = Field(None, description="Acquisition cost cash flows")
    loan_proceeds: pd.Series = Field(None, description="Loan proceeds cash flows")
    debt_service: pd.Series = Field(None, description="Debt service cash flows")
    disposition_proceeds: pd.Series = Field(None, description="Disposition proceeds")
    loan_payoff: pd.Series = Field(None, description="Loan payoff cash flows")
    total_uses: pd.Series = Field(None, description="Total uses (cash outflows)")
    equity_contributions: pd.Series = Field(None, description="Equity contributions")
    debt_draws: pd.Series = Field(None, description="Debt draws")
    interest_expense: pd.Series = Field(None, description="Interest expense")

    @field_validator('*')
    @classmethod
    def validate_series(cls, v):
        """Validate all fields are pandas Series."""
        if not isinstance(v, pd.Series):
            raise ValueError('All cash flow components must be pandas Series')
        return v


class CashFlowSummary(ResultModel):
    """Summary metrics for cash flows."""
    
    total_investment: float = Field(None, description="Total equity investment")
    total_distributions: float = Field(None, description="Total distributions")
    net_cash_flow: float = Field(None, description="Net cash flow (distributions - investment)")


class InterestCompoundingDetails(ResultModel):
    """Interest compounding analysis results."""
    
    base_uses: pd.Series = Field(None, description="Base uses before interest compounding")
    compounded_interest: pd.Series = Field(None, description="Compounded interest by period")
    total_uses_with_interest: pd.Series = Field(None, description="Total uses including interest")
    equity_target: float = Field(None, description="Equity funding target")
    equity_funded: float = Field(None, description="Total equity funded")
    debt_funded: float = Field(None, description="Total debt funded")
    funding_gap: float = Field(None, description="Remaining funding gap")
    total_project_cost: float = Field(None, description="Total project cost with interest")

    @field_validator('base_uses', 'compounded_interest', 'total_uses_with_interest')
    @classmethod
    def validate_series(cls, v):
        """Validate series fields are pandas Series."""
        if not isinstance(v, pd.Series):
            raise ValueError('Series fields must be pandas Series')
        return v


    # NOTE: Advanced interest features not included in MVP


class InterestReserveDetails(ResultModel):
    """Interest reserve capacity and utilization."""
    
    interest_funded_from_reserve: pd.Series = Field(None, description="Interest funded from reserve")
    interest_reserve_capacity: pd.Series = Field(None, description="Interest reserve capacity")
    interest_reserve_utilization: pd.Series = Field(None, description="Interest reserve utilization")

    @field_validator('*')
    @classmethod
    def validate_series(cls, v):
        """Validate all fields are pandas Series."""
        if not isinstance(v, pd.Series):
            raise ValueError('All interest reserve fields must be pandas Series')
        return v


class FundingCascadeDetails(ResultModel):
    """Detailed funding cascade analysis results."""
    
    uses_breakdown: pd.DataFrame = Field(None, description="Period-by-period uses breakdown")
    equity_target: float = Field(None, description="Equity funding target")
    equity_contributed_cumulative: pd.Series = Field(None, description="Cumulative equity contributions")
    debt_draws_by_tranche: Dict[str, pd.Series] = Field(
        default_factory=dict,
        description="Debt draws by tranche name"
    )
    
    # Detailed Analysis Components
    interest_compounding_details: InterestCompoundingDetails = Field(
        ..., 
        description="Interest compounding analysis"
    )
    # NOTE: Advanced interest features not included in MVP
    interest_reserve_details: InterestReserveDetails = Field(None, description="Interest reserve details")

    @field_validator('uses_breakdown')
    @classmethod
    def validate_uses_breakdown(cls, v):
        """Validate uses_breakdown is a DataFrame."""
        if not isinstance(v, pd.DataFrame):
            raise ValueError('uses_breakdown must be a pandas DataFrame')
        return v

    @field_validator('equity_contributed_cumulative')
    @classmethod
    def validate_equity_cumulative(cls, v):
        """Validate equity_contributed_cumulative is a Series."""
        if not isinstance(v, pd.Series):
            raise ValueError('equity_contributed_cumulative must be a pandas Series')
        return v

    @field_validator('debt_draws_by_tranche')
    @classmethod
    def validate_debt_draws(cls, v):
        """Validate debt draws are pandas Series."""
        for tranche_name, series in v.items():
            if not isinstance(series, pd.Series):
                raise ValueError(f'Debt draws for tranche {tranche_name} must be pandas Series')
        return v


class LeveredCashFlowResult(ResultModel):
    """Results from levered cash flow analysis including funding cascade."""
    
    # Primary Cash Flows
    levered_cash_flows: pd.Series = Field(None, description="Main levered cash flow time series")
    
    # Component Breakdown
    cash_flow_components: CashFlowComponents = Field(None, description="Individual cash flow components")
    cash_flow_summary: CashFlowSummary = Field(None, description="Cash flow summary metrics")
    funding_cascade_details: FundingCascadeDetails = Field(None, description="Detailed funding cascade")

    @field_validator('levered_cash_flows')
    @classmethod
    def validate_levered_cash_flows(cls, v):
        """Validate levered_cash_flows is a pandas Series."""
        if not isinstance(v, pd.Series):
            raise ValueError('levered_cash_flows must be a pandas Series')
        return v


# =============================================================================
# Distribution Models (with discriminated unions)
# =============================================================================

class FeeAccountingDetails(ResultModel):
    """Fee allocation and tracking with dual-entry accounting."""
    
    total_partner_fees: float = Field(0.0, description="Total partner fee amount")
    partner_fees_by_partner: Dict[str, float] = Field(
        default_factory=dict,
        description="Partner fee allocation by partner name"
    )
    remaining_cash_flows_after_fee: pd.Series = Field(None, description="Cash flows after fee deduction")
    
    # Detailed fee tracking
    fee_details_by_partner: Dict[str, Dict[str, float]] = Field(
        default_factory=dict,
        description="Detailed fee breakdown by partner: {partner_name: {fee_name: amount}}"
    )
    detailed_fee_breakdown: Dict[str, List[Dict[str, Any]]] = Field(
        default_factory=dict,
        description="Comprehensive fee breakdown with full details: {partner_name: [fee_detail_dict]}"
    )
    fee_cash_flows_by_partner: Dict[str, pd.Series] = Field(
        default_factory=dict,
        description="Fee cash flows by partner: {partner_name: pd.Series}"
    )
    total_fees_by_type: Dict[str, float] = Field(
        default_factory=dict,
        description="Total fees by type: {fee_type: total_amount}"
    )
    fee_timing_summary: Dict[str, Dict[str, float]] = Field(
        default_factory=dict,
        description="Fee timing summary: {partner_name: {period: amount}}"
    )
    
    # Third-party fee tracking
    third_party_fees: Dict[str, float] = Field(
        default_factory=dict,
        description="Third-party fee amounts by entity name"
    )
    third_party_fee_details: Dict[str, Dict[str, float]] = Field(
        default_factory=dict,
        description="Detailed third-party fee breakdown: {entity_name: {fee_name: amount}}"
    )
    third_party_fee_cash_flows: Dict[str, pd.Series] = Field(
        default_factory=dict,
        description="Third-party fee cash flows: {entity_name: pd.Series}"
    )
    total_third_party_fees: float = Field(0.0, description="Total third-party fee amount")

    @field_validator('remaining_cash_flows_after_fee')
    @classmethod
    def validate_remaining_cash_flows(cls, v):
        """Validate remaining cash flows is a pandas Series."""
        if v is not None and not isinstance(v, pd.Series):
            raise ValueError('remaining_cash_flows_after_fee must be a pandas Series')
        return v
    
    @field_validator('fee_cash_flows_by_partner')
    @classmethod
    def validate_fee_cash_flows(cls, v):
        """Validate fee cash flows are pandas Series."""
        if v:
            for partner_name, series in v.items():
                if not isinstance(series, pd.Series):
                    raise ValueError(f'Fee cash flows for partner {partner_name} must be pandas Series')
        return v
    
    @field_validator('third_party_fee_cash_flows')
    @classmethod
    def validate_third_party_fee_cash_flows(cls, v):
        """Validate third-party fee cash flows are pandas Series."""
        if v:
            for entity_name, series in v.items():
                if not isinstance(series, pd.Series):
                    raise ValueError(f'Third-party fee cash flows for entity {entity_name} must be pandas Series')
        return v


class PartnerMetrics(ResultModel):
    """Individual partner performance metrics."""
    
    partner_info: Any = Field(None, description="Partner object (Partner)")  # TODO: Type as Partner when imported
    cash_flows: pd.Series = Field(None, description="Partner's cash flows")
    total_investment: float = Field(None, description="Partner's total investment")
    total_distributions: float = Field(None, description="Partner's total distributions")
    net_profit: float = Field(None, description="Partner's net profit")
    equity_multiple: float = Field(None, description="Partner's equity multiple")
    irr: Optional[float] = Field(None, description="Partner's IRR")
    ownership_percentage: float = Field(None, description="Partner's ownership percentage")
    
    # Distribution source tracking
    distributions_from_waterfall: float = Field(0.0, description="Distributions from equity waterfall")
    distributions_from_fees: float = Field(0.0, description="Distributions from deal fees")
    
    # Backward compatibility (deprecated - use distributions_from_fees)
    developer_fee: float = Field(0.0, description="Developer fee received by partner (deprecated)")
    
    # Detailed fee breakdown for this partner
    fee_details: Dict[str, float] = Field(
        default_factory=dict,
        description="Detailed fee breakdown: {fee_name: amount}"
    )
    fee_cash_flows: Optional[pd.Series] = Field(None, description="Fee cash flows for this partner")

    @field_validator('cash_flows')
    @classmethod
    def validate_cash_flows(cls, v):
        """Validate cash_flows is a pandas Series."""
        if v is not None and not isinstance(v, pd.Series):
            raise ValueError('cash_flows must be a pandas Series')
        return v
    
    @field_validator('fee_cash_flows')
    @classmethod
    def validate_fee_cash_flows(cls, v):
        """Validate fee_cash_flows is a pandas Series."""
        if v is not None and not isinstance(v, pd.Series):
            raise ValueError('fee_cash_flows must be a pandas Series')
        return v


# Base class for all distribution results
class BaseDistributionResult(ResultModel):
    """Base class for all distribution results."""
    
    distribution_method: str = Field(None, description="Distribution method identifier")
    total_distributions: float = Field(None, description="Total distributions")
    total_investment: float = Field(None, description="Total investment")
    equity_multiple: float = Field(None, description="Equity multiple")
    irr: Optional[float] = Field(None, description="Deal IRR")
    distributions: pd.Series = Field(None, description="Distribution cash flows")

    @field_validator('distributions')
    @classmethod
    def validate_distributions(cls, v):
        """Validate distributions is a pandas Series."""
        if not isinstance(v, pd.Series):
            raise ValueError('distributions must be a pandas Series')
        return v


# Waterfall-specific details
class WaterfallDetails(ResultModel):
    """Detailed waterfall distribution results."""
    
    preferred_return: float = Field(None, description="Preferred return amount")
    promote_distributions: float = Field(None, description="Promote distributions amount")
    partner_results: Dict[str, PartnerMetrics] = Field(
        default_factory=dict,
        description="Partner-specific metrics by partner name"
    )


# Specific distribution result types (discriminated union)
class WaterfallDistributionResult(BaseDistributionResult):
    """Results for deals with equity waterfall partners."""
    
    distribution_method: Literal["waterfall"] = "waterfall"
    
    # Waterfall Details
    waterfall_details: WaterfallDetails = Field(None, description="Detailed waterfall results")
    fee_accounting_details: FeeAccountingDetails = Field(None, description="Fee accounting details")


class SingleEntityWaterfallDetails(ResultModel):
    """Simplified waterfall for single entity."""
    
    single_entity_distributions: pd.Series = Field(None, description="Single entity distributions")
    preferred_return: float = Field(0.0, description="Preferred return (always 0)")
    promote_distributions: float = Field(0.0, description="Promote distributions (always 0)")

    @field_validator('single_entity_distributions')
    @classmethod
    def validate_distributions(cls, v):
        """Validate distributions is a pandas Series."""
        if not isinstance(v, pd.Series):
            raise ValueError('single_entity_distributions must be a pandas Series')
        return v


class EmptyFeeAccountingDetails(FeeAccountingDetails):
    """Empty fee accounting details for single entity deals."""
    
    total_partner_fees: float = 0.0
    partner_fees_by_partner: Dict[str, float] = Field(default_factory=dict)


class SingleEntityDistributionResult(BaseDistributionResult):
    """Results for single entity deals (no partners)."""
    
    distribution_method: Literal["single_entity"] = "single_entity"
    
    # Simplified Details
    waterfall_details: SingleEntityWaterfallDetails = Field(None, description="Single entity waterfall")
    fee_accounting_details: EmptyFeeAccountingDetails = Field(None, description="Empty fee accounting")


class ErrorWaterfallDetails(ResultModel):
    """Error case waterfall details."""
    
    error: str = Field(None, description="Error message")
    preferred_return: float = Field(0.0, description="Preferred return (always 0)")
    promote_distributions: float = Field(0.0, description="Promote distributions (always 0)")


class ErrorDistributionResult(BaseDistributionResult):
    """Fallback for error cases."""
    
    distribution_method: Literal["error"] = "error"
    
    # Error Details
    waterfall_details: ErrorWaterfallDetails = Field(None, description="Error waterfall details")
    fee_accounting_details: FeeAccountingDetails = Field(None, description="Fee accounting details")


# Union type for all distribution results (discriminated by distribution_method)
PartnerDistributionResult = Union[
    WaterfallDistributionResult,
    SingleEntityDistributionResult,
    ErrorDistributionResult
]


# =============================================================================
# Main Deal Analysis Result
# =============================================================================

class DealAnalysisResult(ResultModel):
    """Complete deal analysis results containing all analysis components."""
    
    # Core Summary
    deal_summary: DealSummary = Field(None, description="Deal metadata and characteristics")
    
    # Analysis Components
    unlevered_analysis: UnleveredAnalysisResult = Field(None, description="Unlevered asset analysis")
    financing_analysis: Optional[FinancingAnalysisResult] = Field(
        None,
        description="Financing analysis (None for all-equity deals)"
    )
    levered_cash_flows: LeveredCashFlowResult = Field(None, description="Levered cash flow analysis")
    partner_distributions: PartnerDistributionResult = Field(
        ...,
        description="Partner distribution results"
    )
    deal_metrics: DealMetricsResult = Field(None, description="Deal-level performance metrics")


# =============================================================================
# Export all models
# =============================================================================

__all__ = [
    # Main result
    "DealAnalysisResult",
    
    # Core models
    "DealSummary",
    "DealMetricsResult",
    
    # Unlevered analysis
    "UnleveredAnalysisResult",
    
    # Financing analysis
    "FinancingAnalysisResult",
    "FacilityInfo",
    "DSCRSummary",
    
    # Cash flow analysis
    "LeveredCashFlowResult",
    "CashFlowComponents",
    "CashFlowSummary",
    "FundingCascadeDetails",
    "InterestCompoundingDetails",
    # Note: Advanced interest features not included in MVP
    "InterestReserveDetails",
    
    # Distribution analysis
    "PartnerDistributionResult",
    "WaterfallDistributionResult",
    "SingleEntityDistributionResult",
    "ErrorDistributionResult",
    "BaseDistributionResult",
    "WaterfallDetails",
    "SingleEntityWaterfallDetails",
    "ErrorWaterfallDetails",
    "FeeAccountingDetails",
    "EmptyFeeAccountingDetails",
    "PartnerMetrics",
] 