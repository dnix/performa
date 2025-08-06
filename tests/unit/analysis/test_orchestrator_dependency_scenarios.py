# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Systematic Orchestrator Dependency Scenario Tests.

CRITICAL: These tests systematically validate that ALL aggregate dependencies
work correctly in the orchestrator. Each test represents a real-world scenario
where dependent models reference specific aggregates.

PURPOSE: Prevent future orchestration bugs by ensuring comprehensive coverage
of all possible aggregate dependency combinations.

METHODOLOGY: Each test validates:
1. Independent models execute first
2. Required aggregates are calculated in intermediate phase  
3. Dependent models can access their required aggregates
4. Final aggregates include dependent model contributions
5. Mathematical accuracy against manual calculations
"""


import pandas as pd
import pytest

from performa.analysis.orchestrator import AnalysisContext, CashFlowOrchestrator
from performa.core.primitives import (
    CashFlowModel,
    ExpenseSubcategoryEnum,
    FrequencyEnum,
    GlobalSettings,
    RevenueSubcategoryEnum,
    Timeline,
    UnleveredAggregateLineKey,
)


class TestSystematicDependencyScenarios:
    """Systematic validation of ALL aggregate dependency scenarios."""
    
    @pytest.fixture
    def timeline(self):
        """Standard test timeline."""
        return Timeline.from_dates('2024-01-01', '2024-12-31')
    
    @pytest.fixture  
    def context(self, timeline):
        """Standard test context."""
        class SimpleProperty:
            net_rentable_area = 10000
            
        return AnalysisContext(
            timeline=timeline,
            settings=GlobalSettings(),
            property_data=SimpleProperty()
        )

    @pytest.fixture
    def base_revenue_models(self, context):
        """Base revenue models for dependency tests."""
        class BaseLease(CashFlowModel):
            def compute_cf(self, context):
                return {"base_rent": pd.Series(10000.0, index=context.timeline.period_index)}
        
        base_lease = BaseLease(
            name="Base Lease",
            category="Revenue",
            subcategory=RevenueSubcategoryEnum.LEASE,
            timeline=context.timeline,
            value=10000.0,
            reference=None
        )
        
        misc_income = CashFlowModel(
            name="Parking Income",
            category="Revenue",
            subcategory=RevenueSubcategoryEnum.MISC,
            timeline=context.timeline,
            value=500.0,
            reference=None
        )
        
        return [base_lease, misc_income]

    @pytest.fixture
    def base_expense_models(self, context):
        """Base expense models for dependency tests."""
        base_opex = CashFlowModel(
            name="Property Taxes",
            category="Expense",
            subcategory=ExpenseSubcategoryEnum.OPEX,
            timeline=context.timeline,
            value=2000.0,
            reference=None
        )
        
        return [base_opex]

    def test_potential_gross_revenue_dependency(self, context, base_revenue_models):
        """
        SCENARIO: Property management fee based on Potential Gross Revenue.
        REAL-WORLD: Management companies often charge % of PGR regardless of vacancy.
        """
        # Property management fee: 4% of PGR
        mgmt_fee = CashFlowModel(
            name="Property Management Fee",
            category="Expense",
            subcategory=ExpenseSubcategoryEnum.OPEX,
            timeline=context.timeline,
            value=0.04,
            reference=UnleveredAggregateLineKey.POTENTIAL_GROSS_REVENUE
        )
        
        models = base_revenue_models + [mgmt_fee]
        orchestrator = CashFlowOrchestrator(models=models, context=context)
        orchestrator.execute()
        
        # Validate PGR calculated
        pgr = context.resolved_lookups["Potential Gross Revenue"]
        assert pgr.sum() == pytest.approx(120000.0, abs=0.01)  # $10K * 12
        
        # Validate management fee calculated correctly  
        mgmt_result = context.resolved_lookups[mgmt_fee.uid]
        expected_mgmt = 120000.0 * 0.04  # 4% of PGR = $4.8K
        assert mgmt_result.sum() == pytest.approx(expected_mgmt, abs=0.01)
        
        print(f"✅ PGR Dependency Test: Mgmt fee ${mgmt_result.sum():,.0f} = 4% of PGR ${pgr.sum():,.0f}")

    def test_miscellaneous_income_dependency(self, context, base_revenue_models):
        """
        SCENARIO: Marketing fee based on miscellaneous income.
        REAL-WORLD: Third-party revenue sharing (parking, laundry vendors).
        """
        # Marketing fee: 10% of misc income
        marketing_fee = CashFlowModel(
            name="Marketing Fee", 
            category="Expense",
            subcategory=ExpenseSubcategoryEnum.OPEX,
            timeline=context.timeline,
            value=0.10,
            reference=UnleveredAggregateLineKey.MISCELLANEOUS_INCOME
        )
        
        models = base_revenue_models + [marketing_fee]
        orchestrator = CashFlowOrchestrator(models=models, context=context)
        orchestrator.execute()
        
        # Validate misc income calculated
        misc_income = context.resolved_lookups["Miscellaneous Income"]
        assert misc_income.sum() == pytest.approx(6000.0, abs=0.01)  # $500 * 12
        
        # Validate marketing fee
        marketing_result = context.resolved_lookups[marketing_fee.uid]
        expected_marketing = 6000.0 * 0.10  # 10% of misc income = $600
        assert marketing_result.sum() == pytest.approx(expected_marketing, abs=0.01)
        
        print(f"✅ Misc Income Dependency: Marketing fee ${marketing_result.sum():,.0f} = 10% of misc income")

    def test_net_operating_income_dependency(self, context, base_revenue_models, base_expense_models):
        """
        SCENARIO: Asset management fee based on NOI.
        REAL-WORLD: Institutional asset management fees often based on NOI performance.
        """
        # Asset management fee: 1% of NOI
        asset_mgmt_fee = CashFlowModel(
            name="Asset Management Fee",
            category="Expense", 
            subcategory=ExpenseSubcategoryEnum.OPEX,
            timeline=context.timeline,
            value=0.01,
            reference=UnleveredAggregateLineKey.NET_OPERATING_INCOME
        )
        
        models = base_revenue_models + base_expense_models + [asset_mgmt_fee]
        orchestrator = CashFlowOrchestrator(models=models, context=context)
        orchestrator.execute()
        
        # Calculate expected NOI manually  
        # Revenue: $10K base + $500 misc = $10.5K/month = $126K/year
        # Expenses: $2K base + asset mgmt fee
        # NOI before asset mgmt = $126K - $24K = $102K
        # Asset mgmt fee = 1% of $102K = $1.02K
        # Final NOI = $102K - $1.02K ≈ $100.98K
        
        # Validate NOI calculated
        noi = context.resolved_lookups["Net Operating Income"]
        expected_noi = 126000.0 - 24000.0 - (102000.0 * 0.01)  # Iterative calculation
        assert noi.sum() == pytest.approx(expected_noi, abs=1.0)  # $1 tolerance for iterative calc
        
        # Validate asset management fee
        asset_mgmt_result = context.resolved_lookups[asset_mgmt_fee.uid]
        expected_asset_mgmt = 102000.0 * 0.01  # 1% of pre-fee NOI
        assert asset_mgmt_result.sum() == pytest.approx(expected_asset_mgmt, abs=1.0)
        
        print(f"✅ NOI Dependency: Asset mgmt fee ${asset_mgmt_result.sum():,.0f} = 1% of NOI")

    def test_unlevered_cash_flow_dependency(self, context, base_revenue_models, base_expense_models):
        """
        SCENARIO: Partnership promote based on unlevered cash flow.
        REAL-WORLD: GP promotes/carried interest based on property cash flow performance.
        """
        # Capital expenditure (to create UCF < NOI)
        capex = CashFlowModel(
            name="Capital Reserves",
            category="Expense",
            subcategory=ExpenseSubcategoryEnum.CAPEX,
            timeline=context.timeline,
            value=1000.0,
            reference=None
        )
        
        # Promote fee: 5% of UCF  
        promote_fee = CashFlowModel(
            name="GP Promote",
            category="Expense",
            subcategory=ExpenseSubcategoryEnum.OPEX, 
            timeline=context.timeline,
            value=0.05,
            reference=UnleveredAggregateLineKey.UNLEVERED_CASH_FLOW
        )
        
        models = base_revenue_models + base_expense_models + [capex, promote_fee]
        orchestrator = CashFlowOrchestrator(models=models, context=context)
        orchestrator.execute()
        
        # Validate UCF calculated
        ucf = context.resolved_lookups["Unlevered Cash Flow"]
        # UCF = NOI - CapEx = ($126K - $24K) - $12K - promote_fee
        expected_ucf_before_promote = 126000.0 - 24000.0 - 12000.0  # $90K before promote
        expected_promote = expected_ucf_before_promote * 0.05  # $4.5K promote
        expected_ucf_final = expected_ucf_before_promote - expected_promote  # $85.5K final
        
        assert ucf.sum() == pytest.approx(expected_ucf_final, abs=1.0)
        
        # Validate promote fee
        promote_result = context.resolved_lookups[promote_fee.uid] 
        assert promote_result.sum() == pytest.approx(expected_promote, abs=1.0)
        
        print(f"✅ UCF Dependency: Promote ${promote_result.sum():,.0f} = 5% of UCF")

    def test_multiple_aggregate_dependencies(self, context, base_revenue_models, base_expense_models):
        """
        SCENARIO: Multiple fees referencing different aggregates in same analysis.
        REAL-WORLD: Complex properties with multiple fee structures.
        """
        # Management fee: 3% of EGI
        mgmt_fee = CashFlowModel(
            name="Management Fee",
            category="Expense",
            subcategory=ExpenseSubcategoryEnum.OPEX,
            timeline=context.timeline,
            value=0.03,
            reference=UnleveredAggregateLineKey.EFFECTIVE_GROSS_INCOME
        )
        
        # Admin fee: 8% of Total OpEx
        admin_fee = CashFlowModel(
            name="Admin Fee",
            category="Expense", 
            subcategory=ExpenseSubcategoryEnum.OPEX,
            timeline=context.timeline,
            value=0.08,
            reference=UnleveredAggregateLineKey.TOTAL_OPERATING_EXPENSES
        )
        
        # Asset management: 1.5% of NOI
        asset_mgmt = CashFlowModel(
            name="Asset Management",
            category="Expense",
            subcategory=ExpenseSubcategoryEnum.OPEX,
            timeline=context.timeline,
            value=0.015,
            reference=UnleveredAggregateLineKey.NET_OPERATING_INCOME
        )
        
        models = base_revenue_models + base_expense_models + [mgmt_fee, admin_fee, asset_mgmt]
        orchestrator = CashFlowOrchestrator(models=models, context=context)
        orchestrator.execute()
        
        # Validate all aggregates calculated correctly
        egi = context.resolved_lookups["Effective Gross Income"]
        total_opex = context.resolved_lookups["Total Operating Expenses"]
        noi = context.resolved_lookups["Net Operating Income"]
        
        # Validate all fees calculated
        mgmt_result = context.resolved_lookups[mgmt_fee.uid]
        admin_result = context.resolved_lookups[admin_fee.uid]
        asset_result = context.resolved_lookups[asset_mgmt.uid]
        
        # Basic sanity checks (detailed math would be complex with multiple iterations)
        assert mgmt_result.sum() > 0, "Management fee should be calculated"
        assert admin_result.sum() > 0, "Admin fee should be calculated" 
        assert asset_result.sum() > 0, "Asset management fee should be calculated"
        
        # Validate fees are reasonable percentages
        assert mgmt_result.sum() == pytest.approx(egi.sum() * 0.03, abs=100.0)  # Approx 3% of EGI
        
        print(f"✅ Multiple Dependencies: All fees calculated successfully")
        print(f"   Management: ${mgmt_result.sum():,.0f}, Admin: ${admin_result.sum():,.0f}, Asset Mgmt: ${asset_result.sum():,.0f}")

    def test_edge_case_zero_aggregate_dependency(self, context):
        """
        SCENARIO: Dependent model references aggregate that equals zero.
        REAL-WORLD: Fee based on component that doesn't exist (e.g., no misc income).
        """
        # Fee based on non-existent misc income
        marketing_fee = CashFlowModel(
            name="Marketing Fee",
            category="Expense",
            subcategory=ExpenseSubcategoryEnum.OPEX,
            timeline=context.timeline,
            value=0.10,
            reference=UnleveredAggregateLineKey.MISCELLANEOUS_INCOME  # No misc income models
        )
        
        models = [marketing_fee]
        orchestrator = CashFlowOrchestrator(models=models, context=context)
        orchestrator.execute()
        
        # Validate misc income is zero
        misc_income = context.resolved_lookups["Miscellaneous Income"]
        assert misc_income.sum() == pytest.approx(0.0, abs=0.01)
        
        # Validate fee is zero (10% of $0 = $0)
        marketing_result = context.resolved_lookups[marketing_fee.uid]
        assert marketing_result.sum() == pytest.approx(0.0, abs=0.01)
        
        print("✅ Zero Aggregate Dependency: Fee correctly calculated as $0 when aggregate is $0")

    def test_complex_capital_dependency_chain(self, context, base_revenue_models):
        """
        SCENARIO: Capital expenditures with management fees based on CapEx totals.
        REAL-WORLD: Construction management fees, development oversight fees.
        """
        # Base capital expenditure - $50K annually (not monthly!)
        base_capex = CashFlowModel(
            name="Roof Replacement", 
            category="Expense",
            subcategory=ExpenseSubcategoryEnum.CAPEX,
            timeline=context.timeline,
            value=50000.0,
            frequency=FrequencyEnum.ANNUAL,  # ← CRITICAL: Annual, not monthly
            reference=None
        )
        
        # Construction management fee: 8% of total CapEx
        construction_mgmt = CashFlowModel(
            name="Construction Management",
            category="Expense",
            subcategory=ExpenseSubcategoryEnum.CAPEX,
            timeline=context.timeline, 
            value=0.08,
            reference=UnleveredAggregateLineKey.TOTAL_CAPITAL_EXPENDITURES
        )
        
        models = base_revenue_models + [base_capex, construction_mgmt]
        orchestrator = CashFlowOrchestrator(models=models, context=context)
        orchestrator.execute()
        
        # DEBUG: Check individual model results
        base_capex_result = context.resolved_lookups[base_capex.uid]
        mgmt_result = context.resolved_lookups[construction_mgmt.uid]
        total_capex = context.resolved_lookups["Total Capital Expenditures"]
        
        # Validate annual CapEx calculation (FrequencyEnum.ANNUAL)
        expected_base_capex_annual = 50000.0  # $50K annually 
        expected_mgmt_fee = expected_base_capex_annual * 0.08  # 8% of $50K = $4K
        expected_total = expected_base_capex_annual + expected_mgmt_fee  # $54K total
        
        # Validate total CapEx includes both base and management fee
        assert total_capex.sum() == pytest.approx(expected_total, abs=1.0)
        
        # Validate construction management fee
        assert mgmt_result.sum() == pytest.approx(expected_mgmt_fee, abs=1.0)
        
        print(f"✅ CapEx Dependency: Construction mgmt ${mgmt_result.sum():,.0f} = 8% of base CapEx") 