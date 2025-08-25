# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

import pandas as pd

from performa.analysis.results import AssetAnalysisResult
from performa.core.ledger import Ledger
from performa.core.primitives import Timeline
from performa.deal.results import (
    DealAnalysisResult,
    LeveredCashFlowResult,
    UnleveredAnalysisResult,
)


def test_fluent_pro_forma_summary():
    """Test the new fluent reporting interface for pro forma summaries."""
    # Create periods and timeline
    periods = pd.period_range("2024-01", periods=12, freq="M")
    timeline = Timeline(start_date=periods[0], duration_months=12)
    
    # Create a minimal property object
    class MockProperty:
        uid = "test-property-id"
        name = "Test Property"
        
    # Create a minimal scenario object  
    class MockScenario:
        pass
    
    # Create AssetAnalysisResult with ledger (new architecture)
    summary_df = pd.DataFrame(
        {
            "Potential Gross Revenue": pd.Series(1000.0, index=periods),
            "Rental Abatement": pd.Series(0.0, index=periods),
            "General Vacancy Loss": pd.Series(0.0, index=periods),
            "Collection Loss": pd.Series(0.0, index=periods),
            "Miscellaneous Income": pd.Series(0.0, index=periods),
            "Expense Reimbursements": pd.Series(0.0, index=periods),
            "Total Operating Expenses": pd.Series(400.0, index=periods),
            # Effective Gross Income and NOI can be computed from above
        },
        index=periods,
    )
    
    asset_analysis = AssetAnalysisResult(
        ledger=Ledger(),
        property=MockProperty(),
        timeline=timeline,
        scenario=MockScenario(),
        models=[]
    )
    
    # Create backward compatibility layer
    unlev = UnleveredAnalysisResult(cash_flows=summary_df)
    
    levered = LeveredCashFlowResult(levered_cash_flows=pd.Series(600.0, index=periods))
    results = DealAnalysisResult(
        deal_summary={},
        asset_analysis=asset_analysis,  # Use new ledger-based asset analysis
        unlevered_analysis=unlev,  # Still required for backward compatibility
        financing_analysis=None,
        levered_cash_flows=levered,
        partner_distributions={
            "distribution_method": "single_entity",
            "distributions": pd.Series(0.0, index=periods),
            "total_distributions": 0.0,
            "total_investment": 0.0,
            "equity_multiple": 0.0,
        },
        deal_metrics={},
    )

    # Test the new fluent interface
    summary = results.reporting.pro_forma_summary(frequency="A")
    assert isinstance(summary, pd.DataFrame)
    # Expect some canonical rows present
    assert "Potential Gross Revenue" in summary.index
    assert "Net Operating Income" in summary.index

    # Test that different frequencies work
    quarterly_summary = results.reporting.pro_forma_summary(frequency="Q")
    assert isinstance(quarterly_summary, pd.DataFrame)

    # Test that the reporting interface is cached
    assert results.reporting is results.reporting
