# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Integration tests for capital structure validation guardrails.

Tests the comprehensive validation logic that prevents underfunded deals
and provides actionable warnings for capital structure issues.
"""

import logging
from datetime import date
from unittest.mock import Mock

import pytest

from performa.core.capital import CapitalItem, CapitalPlan
from performa.core.ledger import Ledger, LedgerGenerationSettings
from performa.core.primitives import AssetTypeEnum, Timeline
from performa.core.primitives.draw_schedule import FirstOnlyDrawSchedule
from performa.core.primitives.settings import GlobalSettings
from performa.deal import (
    AcquisitionTerms,
    Deal,
    create_simple_capital_partnership,
    create_simple_partnership,
)
from performa.deal.analysis.cash_flow import CashFlowEngine
from performa.debt import create_construction_to_permanent_plan
from performa.development import DevelopmentProject


class TestCapitalValidationGuardrails:
    """Test capital validation and funding adequacy guardrails."""
    
    def setup_method(self):
        """Setup common test fixtures."""
        self.timeline = Timeline.from_dates("2024-01-01", "2027-01-01")
        self.settings = GlobalSettings()
        
    def test_critical_capital_shortfall_error(self):
        """Test that critical capital shortfall (>10%) raises error."""
        # Create partnership with insufficient capital
        partnership = create_simple_capital_partnership(
            gp_capital=3_000_000,   # $3M
            lp_capital=12_000_000   # $12M = $15M total
        )
        
        # Create deal that needs much more equity (~$40M with 50% LTC)
        capital_plan = CapitalPlan(
            name="High Cost Project",
            capital_items=[
                CapitalItem(
                    name="Construction",
                    work_type="construction",
                    value=70_000_000,  # $70M construction
                    timeline=Timeline(start_date=date(2024, 1, 1), duration_months=18),
                    draw_schedule=FirstOnlyDrawSchedule()
                )
            ]
        )
        
        project = DevelopmentProject(
            name="Underfunded Project",
            property_type=AssetTypeEnum.OFFICE,
            gross_area=100_000,
            net_rentable_area=90_000,
            construction_plan=capital_plan,
            blueprints=[]
        )
        
        acquisition = AcquisitionTerms(
            name="Land Acquisition",
            timeline=Timeline(start_date=date(2024, 1, 1), duration_months=1),
            value=10_000_000,  # $10M land
            acquisition_date=date(2024, 1, 1)
        )
        
        # Low LTC = high equity requirement
        financing = create_construction_to_permanent_plan(
            construction_terms={
                "name": "Low LTC Construction",
                "ltc_ratio": 0.50,  # 50% LTC on $80M = need $40M equity
                "interest_rate": 0.08,
                "loan_term_months": 24
            },
            permanent_terms={
                "name": "Permanent Loan",
                "loan_amount": 30_000_000,
                "interest_rate": 0.06,
                "loan_term_months": 120,
                "amortization_months": 360
            },
            project_value=80_000_000
        )
        
        deal = Deal(
            name="Critical Shortfall Test",
            asset=project,
            acquisition=acquisition,
            financing=financing,
            equity_partners=partnership  # $15M committed vs $40M needed
        )
        
        engine = CashFlowEngine(deal, self.timeline, self.settings)
        ledger = Ledger(LedgerGenerationSettings())
        
        # Should raise capital shortfall error (>10% shortfall)
        with pytest.raises(ValueError) as exc_info:
            engine._calculate_equity_target(80_000_000, ledger)
            
        error_msg = str(exc_info.value)
        assert "CAPITAL SHORTFALL" in error_msg
        assert "fall" in error_msg and "short" in error_msg
        assert "$15,000,000" in error_msg  # Committed amount
        assert "$40,000,000" in error_msg  # Required amount
        
    def test_thin_margin_warning(self, caplog):
        """Test that thin margin (5-10% shortfall) provides warning."""
        # Create partnership with insufficient capital to trigger 7% shortfall warning
        # Target: Need $50M, commit $46.5M = 7% shortfall  
        partnership = create_simple_capital_partnership(
            gp_capital=11_625_000.0,  # $11.625M (25% of $46.5M) 
            lp_capital=34_875_000.0   # $34.875M (75% of $46.5M) = $46.5M total
        )
        
        capital_plan = CapitalPlan(
            name="Tight Margin Project",
            capital_items=[
                CapitalItem(
                    name="Construction", 
                    work_type="construction",
                    value=90_000_000,  # $90M construction
                    timeline=Timeline(start_date=date(2024, 1, 1), duration_months=18),
                    draw_schedule=FirstOnlyDrawSchedule()
                )
            ]
        )
        
        project = DevelopmentProject(
            name="Tight Margin Project",
            property_type=AssetTypeEnum.OFFICE,
            gross_area=80_000,
            net_rentable_area=72_000,
            construction_plan=capital_plan,
            blueprints=[]
        )
        
        acquisition = AcquisitionTerms(
            name="Land Acquisition",
            timeline=Timeline(start_date=date(2024, 1, 1), duration_months=1),
            value=10_000_000,  # $10M land
            acquisition_date=date(2024, 1, 1)
        )
        
        financing = create_construction_to_permanent_plan(
            construction_terms={
                "name": "Moderate LTC Construction",
                "ltc_ratio": 0.50,  # 50% LTC on $100M total = need $50M equity (vs $46.5M committed = 7% short)
                "interest_rate": 0.08,
                "loan_term_months": 24
            },
            permanent_terms={
                "name": "Permanent Loan",
                "loan_amount": 25_000_000,
                "interest_rate": 0.06,
                "loan_term_months": 120,
                "amortization_months": 360
            },
            project_value=100_000_000  # $100M total project cost
        )
        
        deal = Deal(
            name="Thin Margin Test",
            asset=project,
            acquisition=acquisition,
            financing=financing,
            equity_partners=partnership  # $40M committed vs ~$40.5M needed
        )
        
        engine = CashFlowEngine(deal, self.timeline, self.settings)
        ledger = Ledger(LedgerGenerationSettings())
        
        # Should provide warning but not error  
        with caplog.at_level(logging.WARNING):
            equity_target = engine._calculate_equity_target(100_000_000, ledger)
            
        # Should get warning about thin margin
        warning_messages = [record.message for record in caplog.records if record.levelno == logging.WARNING]
        assert any("THIN EQUITY MARGIN" in msg for msg in warning_messages)
        assert equity_target == 46_500_000.0  # Should return commitments ($46.5M) despite warning
        
    def test_excess_equity_warning(self, caplog):
        """Test that significant over-commitment provides warning."""
        # Create partnership with excessive capital
        partnership = create_simple_capital_partnership(
            gp_capital=20_000_000,  # $20M
            lp_capital=80_000_000   # $80M = $100M total (way more than needed)
        )
        
        capital_plan = CapitalPlan(
            name="Low Cost Project",
            capital_items=[
                CapitalItem(
                    name="Construction",
                    work_type="construction",
                    value=30_000_000,  # Only $30M construction
                    timeline=Timeline(start_date=date(2024, 1, 1), duration_months=18),
                    draw_schedule=FirstOnlyDrawSchedule()
                )
            ]
        )
        
        project = DevelopmentProject(
            name="Low Cost Project",
            property_type=AssetTypeEnum.OFFICE,
            gross_area=40_000,
            net_rentable_area=36_000,
            construction_plan=capital_plan,
            blueprints=[]
        )
        
        acquisition = AcquisitionTerms(
            name="Cheap Land",
            timeline=Timeline(start_date=date(2024, 1, 1), duration_months=1),
            value=5_000_000,
            acquisition_date=date(2024, 1, 1)
        )
        
        financing = create_construction_to_permanent_plan(
            construction_terms={
                "name": "High LTC Construction",
                "ltc_ratio": 0.80,  # 80% LTC on $35M = only need $7M equity
                "interest_rate": 0.08,
                "loan_term_months": 24
            },
            permanent_terms={
                "name": "Permanent Loan",
                "loan_amount": 20_000_000,
                "interest_rate": 0.06,
                "loan_term_months": 120,
                "amortization_months": 360
            },
            project_value=35_000_000
        )
        
        deal = Deal(
            name="Excess Equity Test",
            asset=project,
            acquisition=acquisition,
            financing=financing,
            equity_partners=partnership  # $100M committed vs ~$7M needed
        )
        
        engine = CashFlowEngine(deal, self.timeline, self.settings)
        ledger = Ledger(LedgerGenerationSettings())
        
        # Should provide warning about excess equity
        with caplog.at_level(logging.WARNING):
            equity_target = engine._calculate_equity_target(35_000_000, ledger)
            
        # Should get warning about excess equity
        warning_messages = [record.message for record in caplog.records if record.levelno == logging.WARNING]
        assert any("EXCESS EQUITY" in msg for msg in warning_messages)
        assert equity_target == 100_000_000  # Should still return commitments
        
    def test_derived_mode_no_validation(self):
        """Test that derived mode skips validation (current behavior preserved)."""
        # Create partnership without commitments (derived mode)        
        partnership = create_simple_partnership(
            gp_name="GP",
            gp_share=0.20,
            lp_name="LP", 
            lp_share=0.80
            # No capital commitments = derived mode
        )
        
        # Use the same high-cost project from shortfall test
        capital_plan = CapitalPlan(
            name="Derived Mode Project",
            capital_items=[
                CapitalItem(
                    name="Construction",
                    work_type="construction",
                    value=70_000_000,
                    timeline=Timeline(start_date=date(2024, 1, 1), duration_months=18),
                    draw_schedule=FirstOnlyDrawSchedule()
                )
            ]
        )
        
        project = DevelopmentProject(
            name="Derived Mode Project",
            property_type=AssetTypeEnum.OFFICE,
            gross_area=100_000,
            net_rentable_area=90_000,
            construction_plan=capital_plan,
            blueprints=[]
        )
        
        acquisition = AcquisitionTerms(
            name="Land Acquisition",
            timeline=Timeline(start_date=date(2024, 1, 1), duration_months=1),
            value=10_000_000,
            acquisition_date=date(2024, 1, 1)
        )
        
        financing = create_construction_to_permanent_plan(
            construction_terms={
                "name": "Standard Construction",
                "ltc_ratio": 0.70,
                "interest_rate": 0.08,
                "loan_term_months": 24
            },
            permanent_terms={
                "name": "Permanent Loan",
                "loan_amount": 35_000_000,
                "interest_rate": 0.06,
                "loan_term_months": 120,
                "amortization_months": 360
            },
            project_value=80_000_000
        )
        
        deal = Deal(
            name="Derived Mode Test",
            asset=project,
            acquisition=acquisition,
            financing=financing,
            equity_partners=partnership  # No commitments = derived mode
        )
        
        engine = CashFlowEngine(deal, self.timeline, self.settings)
        ledger = Ledger(LedgerGenerationSettings())
        
        # Should not raise any validation errors (derived mode)
        equity_target = engine._calculate_equity_target(80_000_000, ledger)
        
        # Should calculate based on LTC, not commitments
        expected_equity = 80_000_000 * (1 - 0.70)  # 30% of $80M
        assert abs(equity_target - expected_equity) < 1000
        
    def test_required_equity_calculation_accuracy(self):
        """Test that required equity calculation handles various LTC scenarios correctly."""
        # Test scenario 1: Simple single LTC
        partnership = create_simple_capital_partnership(
            gp_capital=15_000_000,
            lp_capital=35_000_000  # $50M total
        )
        
        # Create basic project
        capital_plan = CapitalPlan(
            name="Test Project",
            capital_items=[
                CapitalItem(
                    name="Construction",
                    work_type="construction",
                    value=80_000_000,
                    timeline=Timeline(start_date=date(2024, 1, 1), duration_months=18),
                    draw_schedule=FirstOnlyDrawSchedule()
                )
            ]
        )
        
        project = DevelopmentProject(
            name="Test Project",
            property_type=AssetTypeEnum.OFFICE,
            gross_area=100_000,
            net_rentable_area=90_000,
            construction_plan=capital_plan,
            blueprints=[]
        )
        
        acquisition = AcquisitionTerms(
            name="Land",
            timeline=Timeline(start_date=date(2024, 1, 1), duration_months=1),
            value=10_000_000,
            acquisition_date=date(2024, 1, 1)
        )
        
        financing = create_construction_to_permanent_plan(
            construction_terms={
                "name": "Test Construction",
                "ltc_ratio": 0.60,  # 60% LTC on $90M = need $36M equity
                "interest_rate": 0.08,
                "loan_term_months": 24
            },
            permanent_terms={
                "name": "Permanent Loan",
                "loan_amount": 30_000_000,
                "interest_rate": 0.06,
                "loan_term_months": 120,
                "amortization_months": 360
            },
            project_value=90_000_000
        )
        
        deal = Deal(
            name="LTC Calculation Test",
            asset=project,
            acquisition=acquisition,
            financing=financing,
            equity_partners=partnership
        )
        
        engine = CashFlowEngine(deal, self.timeline, self.settings)
        
        # Test the required equity calculation
        total_cost = 90_000_000  # $10M land + $80M construction
        required_equity = engine._calculate_required_equity_from_ltc(total_cost)
        
        expected_required = total_cost * (1 - 0.60)  # 40% of $90M = $36M
        assert abs(required_equity - expected_required) < 1000
        
        # Committed: $50M, Required: $36M = sufficient (should pass)
        ledger = Ledger(LedgerGenerationSettings())
        equity_target = engine._calculate_equity_target(total_cost, ledger)
        assert equity_target == 50_000_000  # Should return commitments
        
    def test_zero_commitment_edge_case(self):
        """Test edge case where one partner has zero commitment."""
        partnership = create_simple_capital_partnership(
            gp_capital=0,           # $0 commitment (!)
            lp_capital=50_000_000   # $50M commitment
        )
        
        # Should still work - explicit mode with zero GP contribution
        assert partnership.has_explicit_commitments
        assert partnership.total_committed_capital == 50_000_000
        
        # Capital shares should reflect zero contribution
        capital_shares = partnership.capital_shares
        assert capital_shares["GP"] == 0.0
        assert capital_shares["LP"] == 1.0
        
        # But ownership shares are proportional to capital (0% vs 100%)
        gp = partnership.get_partner_by_name("GP")
        lp = partnership.get_partner_by_name("LP") 
        assert gp.share == 0.0   # 0% ownership
        assert lp.share == 1.0   # 100% ownership
        
    def test_all_equity_deal_validation(self):
        """Test validation for all-equity deals with commitments."""
        # Create partnership for all-equity deal
        partnership = create_simple_capital_partnership(
            gp_capital=25_000_000,
            lp_capital=75_000_000   # $100M total
        )
        
        capital_plan = CapitalPlan(
            name="All Equity Project",
            capital_items=[
                CapitalItem(
                    name="Construction",
                    work_type="construction",
                    value=90_000_000,  # $90M construction
                    timeline=Timeline(start_date=date(2024, 1, 1), duration_months=18),
                    draw_schedule=FirstOnlyDrawSchedule()
                )
            ]
        )
        
        project = DevelopmentProject(
            name="All Equity Project",
            property_type=AssetTypeEnum.OFFICE,
            gross_area=120_000,
            net_rentable_area=108_000,
            construction_plan=capital_plan,
            blueprints=[]
        )
        
        acquisition = AcquisitionTerms(
            name="Land Acquisition",
            timeline=Timeline(start_date=date(2024, 1, 1), duration_months=1),
            value=10_000_000,
            acquisition_date=date(2024, 1, 1)
        )
        
        # No financing = all equity deal
        deal = Deal(
            name="All Equity Deal",
            asset=project,
            acquisition=acquisition,
            equity_partners=partnership  # $100M vs $100M needed
        )
        
        engine = CashFlowEngine(deal, self.timeline, self.settings)
        ledger = Ledger(LedgerGenerationSettings())
        
        # Should work perfectly - exact match
        equity_target = engine._calculate_equity_target(100_000_000, ledger)
        assert equity_target == 100_000_000  # Exact match
        
    def test_ltc_accuracy_with_validation(self):
        """Test that LTC-based required equity calculation is accurate."""
        # Create a simple test case to verify LTC math
        partnership = create_simple_capital_partnership(
            gp_capital=10_000_000,
            lp_capital=30_000_000   # $40M total
        )
        
        # Mock deal for engine creation
        mock_deal = Mock()
        mock_deal.has_equity_partners = True
        mock_deal.equity_partners = partnership
        mock_deal.financing = Mock()
        mock_deal.financing.facilities = []
        
        # Create mock facility with known LTC
        mock_facility = Mock()
        mock_facility.kind = "construction"
        mock_facility.ltc_ratio = 0.75  # 75% LTC
        mock_deal.financing.facilities = [mock_facility]
        
        engine = CashFlowEngine(mock_deal, self.timeline, self.settings)
        
        # Test required equity calculation
        test_cost = 100_000_000  # $100M project
        required_equity = engine._calculate_required_equity_from_ltc(test_cost)
        
        expected = test_cost * (1 - 0.75)  # 25% equity = $25M
        assert abs(required_equity - expected) < 100
        
        # Commitments ($40M) > Required ($25M) = should warn about excess
        # (This would trigger excess equity warning in actual validation)
