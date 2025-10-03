# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Integration tests for capital structure validation guardrails.

Tests the comprehensive validation logic that prevents underfunded deals
and provides actionable warnings for capital structure issues.

Uses modern fixture-based approach with Pydantic model_copy() pattern
for DRY, maintainable test code.
"""

import logging
from datetime import date
from unittest.mock import Mock

import pytest

from performa.core.capital import CapitalItem, CapitalPlan
from performa.core.ledger import Ledger
from performa.core.primitives import AssetTypeEnum, Timeline
from performa.core.primitives.draw_schedule import FirstOnlyDrawSchedule
from performa.core.primitives.settings import GlobalSettings
from performa.deal import (
    AcquisitionTerms,
    Deal,
    create_simple_capital_partnership,
    create_simple_partnership,
)
from performa.deal.analysis import CashFlowEngine
from performa.deal.orchestrator import DealContext
from performa.debt import create_construction_to_permanent_plan
from performa.development import DevelopmentProject


class TestCapitalValidationGuardrails:
    """Test capital validation and funding adequacy guardrails."""

    def setup_method(self):
        """Setup common test fixtures."""
        self.timeline = Timeline.from_dates("2024-01-01", "2027-01-01")
        self.settings = GlobalSettings()

    @pytest.fixture
    def base_capital_plan(self):
        """Base capital plan that can be modified via model_copy()."""
        return CapitalPlan(
            name="Standard Project",
            capital_items=[
                CapitalItem(
                    name="Construction",
                    work_type="construction",
                    value=70_000_000,  # Default $70M construction
                    timeline=Timeline(start_date=date(2024, 1, 1), duration_months=18),
                    draw_schedule=FirstOnlyDrawSchedule(),
                )
            ],
        )

    @pytest.fixture
    def base_project(self, base_capital_plan):
        """Base development project that can be modified via model_copy()."""
        return DevelopmentProject(
            name="Standard Project",
            property_type=AssetTypeEnum.OFFICE,
            gross_area=100_000,
            net_rentable_area=90_000,
            construction_plan=base_capital_plan,
            blueprints=[],
        )

    @pytest.fixture
    def base_acquisition(self):
        """Base acquisition terms that can be modified via model_copy()."""
        return AcquisitionTerms(
            name="Land Acquisition",
            timeline=Timeline(start_date=date(2024, 1, 1), duration_months=1),
            value=10_000_000,  # Default $10M land
            acquisition_date=date(2024, 1, 1),
        )

    @pytest.fixture
    def base_financing(self):
        """Base financing structure that can be modified via model_copy()."""
        return create_construction_to_permanent_plan(
            construction_terms={
                "name": "Standard Construction",
                "ltc_ratio": 0.60,  # Default 60% LTC
                "interest_rate": 0.08,
                "loan_term_months": 24,
            },
            permanent_terms={
                "name": "Permanent Loan",
                "loan_amount": 30_000_000,
                "interest_rate": 0.06,
                "loan_term_months": 120,
                "amortization_months": 360,
            },
            project_value=80_000_000,  # Default project value
        )

    def create_test_deal(
        self,
        partnership,
        base_project,
        base_acquisition,
        financing=None,
        name="Test Deal",
        **deal_updates,
    ):
        """Helper to create test deals with smart defaults."""
        deal = Deal(
            name=name,
            asset=base_project,
            acquisition=base_acquisition,
            financing=financing,
            equity_partners=partnership,
            **deal_updates,
        )
        return deal

    def run_capital_validation_test(self, deal, total_cost, ledger=None):
        """Helper to run capital validation with standard setup."""
        if ledger is None:
            ledger = Ledger()

        context = DealContext(
            deal=deal,
            timeline=self.timeline,
            settings=self.settings,
            ledger=ledger,
        )
        engine = CashFlowEngine(context)
        return engine._calculate_equity_target(total_cost, ledger)

    # Common partnership patterns as fixtures
    @pytest.fixture
    def insufficient_partnership(self):
        """Partnership with insufficient capital ($15M) for testing shortfalls."""
        return create_simple_capital_partnership(
            gp_capital=3_000_000,  # $3M
            lp_capital=12_000_000,  # $12M = $15M total
        )

    @pytest.fixture
    def adequate_partnership(self):
        """Partnership with adequate capital ($50M) for most tests."""
        return create_simple_capital_partnership(
            gp_capital=12_500_000,  # $12.5M
            lp_capital=37_500_000,  # $37.5M = $50M total
        )

    @pytest.fixture
    def excessive_partnership(self):
        """Partnership with excessive capital ($100M) for over-commitment tests."""
        return create_simple_capital_partnership(
            gp_capital=20_000_000,  # $20M
            lp_capital=80_000_000,  # $80M = $100M total
        )

    # Common financing patterns as fixtures
    @pytest.fixture
    def low_ltc_financing(self):
        """Low LTC financing (50%) for high equity requirement tests."""
        return create_construction_to_permanent_plan(
            construction_terms={
                "name": "Low LTC Construction",
                "ltc_ratio": 0.50,  # 50% LTC = high equity requirement
                "interest_rate": 0.08,
                "loan_term_months": 24,
            },
            permanent_terms={
                "name": "Permanent Loan",
                "loan_amount": 30_000_000,
                "interest_rate": 0.06,
                "loan_term_months": 120,
                "amortization_months": 360,
            },
            project_value=80_000_000,
        )

    @pytest.fixture
    def high_ltc_financing(self):
        """High LTC financing (80%) for low equity requirement tests."""
        return create_construction_to_permanent_plan(
            construction_terms={
                "name": "High LTC Construction",
                "ltc_ratio": 0.80,  # 80% LTC = low equity requirement
                "interest_rate": 0.08,
                "loan_term_months": 24,
            },
            permanent_terms={
                "name": "Permanent Loan",
                "loan_amount": 28_000_000,
                "interest_rate": 0.06,
                "loan_term_months": 120,
                "amortization_months": 360,
            },
            project_value=35_000_000,
        )

    def test_critical_capital_shortfall_error(
        self,
        base_project,
        base_acquisition,
        insufficient_partnership,
        low_ltc_financing,
    ):
        """Test that critical capital shortfall (>10%) raises error."""
        deal = self.create_test_deal(
            partnership=insufficient_partnership,  # $15M committed
            base_project=base_project,
            base_acquisition=base_acquisition,
            financing=low_ltc_financing,  # 50% LTC = need $40M equity
            name="Critical Shortfall Test",
        )

        # Should raise capital shortfall error (>10% shortfall: $15M vs $40M needed)
        with pytest.raises(ValueError) as exc_info:
            self.run_capital_validation_test(deal, total_cost=80_000_000)

        error_msg = str(exc_info.value)
        assert "CAPITAL SHORTFALL" in error_msg
        assert "fall" in error_msg and "short" in error_msg
        assert "$15,000,000" in error_msg  # Committed amount
        assert "$40,000,000" in error_msg  # Required amount

    def test_thin_margin_warning(
        self, caplog, base_capital_plan, base_project, base_acquisition
    ):
        """Test that thin margin (5-10% shortfall) provides warning."""
        # Create partnership with insufficient capital to trigger 7% shortfall warning
        # Target: Need $50M, commit $46.5M = 7% shortfall
        partnership = create_simple_capital_partnership(
            gp_capital=11_625_000.0,  # $11.625M (25% of $46.5M)
            lp_capital=34_875_000.0,  # $34.875M (75% of $46.5M) = $46.5M total
        )

        # Use model_copy to modify only the construction value
        modified_capital_plan = base_capital_plan.model_copy(
            update={
                "name": "Tight Margin Project",
                "capital_items": [
                    base_capital_plan.capital_items[0].model_copy(
                        update={"value": 90_000_000}  # $90M construction
                    )
                ],
            }
        )

        # Use model_copy to modify project with new capital plan and size
        modified_project = base_project.model_copy(
            update={
                "name": "Tight Margin Project",
                "construction_plan": modified_capital_plan,
                "gross_area": 80_000,
                "net_rentable_area": 72_000,
            }
        )

        financing = create_construction_to_permanent_plan(
            construction_terms={
                "name": "Moderate LTC Construction",
                "ltc_ratio": 0.50,  # 50% LTC on $100M total = need $50M equity (vs $46.5M committed = 7% short)
                "interest_rate": 0.08,
                "loan_term_months": 24,
            },
            permanent_terms={
                "name": "Permanent Loan",
                "loan_amount": 25_000_000,
                "interest_rate": 0.06,
                "loan_term_months": 120,
                "amortization_months": 360,
            },
            project_value=100_000_000,  # $100M total project cost
        )

        deal = self.create_test_deal(
            partnership=partnership,
            base_project=modified_project,
            base_acquisition=base_acquisition,
            financing=financing,
            name="Thin Margin Test",
        )

        # Should provide warning but not error
        with caplog.at_level(logging.WARNING):
            equity_target = self.run_capital_validation_test(
                deal, total_cost=100_000_000
            )

        # Should get warning about thin margin
        warning_messages = [
            record.message
            for record in caplog.records
            if record.levelno == logging.WARNING
        ]
        assert any("THIN EQUITY MARGIN" in msg for msg in warning_messages)
        assert (
            equity_target == 46_500_000.0
        )  # Should return commitments ($46.5M) despite warning

    def test_excess_equity_warning(
        self,
        caplog,
        base_capital_plan,
        base_project,
        base_acquisition,
        excessive_partnership,
        high_ltc_financing,
    ):
        """Test that significant over-commitment provides warning."""
        # Create low cost project (only $30M construction vs $70M default)
        low_cost_capital_plan = base_capital_plan.model_copy(
            update={
                "name": "Low Cost Project",
                "capital_items": [
                    base_capital_plan.capital_items[0].model_copy(
                        update={"value": 30_000_000}  # Only $30M construction
                    )
                ],
            }
        )

        low_cost_project = base_project.model_copy(
            update={
                "name": "Low Cost Project",
                "construction_plan": low_cost_capital_plan,
                "gross_area": 40_000,
                "net_rentable_area": 36_000,
            }
        )

        cheap_acquisition = base_acquisition.model_copy(
            update={
                "name": "Cheap Land",
                "value": 5_000_000,  # $5M vs $10M default
            }
        )

        deal = self.create_test_deal(
            partnership=excessive_partnership,  # $100M committed vs ~$7M needed
            base_project=low_cost_project,
            base_acquisition=cheap_acquisition,
            financing=high_ltc_financing,  # 80% LTC = low equity requirement
            name="Excess Equity Test",
        )

        # Should provide warning about excess equity
        with caplog.at_level(logging.WARNING):
            equity_target = self.run_capital_validation_test(
                deal, total_cost=35_000_000
            )

        # Should get warning about excess equity
        warning_messages = [
            record.message
            for record in caplog.records
            if record.levelno == logging.WARNING
        ]
        assert any("EXCESS EQUITY" in msg for msg in warning_messages)
        assert equity_target == 100_000_000  # Should still return commitments

    def test_derived_mode_no_validation(self, base_project, base_acquisition):
        """Test that derived mode skips validation (current behavior preserved)."""
        # Create partnership without commitments (derived mode)
        derived_partnership = create_simple_partnership(
            gp_name="GP",
            gp_share=0.20,
            lp_name="LP",
            lp_share=0.80,
            # No capital commitments = derived mode
        )

        # Use standard 70% LTC financing
        standard_financing = create_construction_to_permanent_plan(
            construction_terms={
                "name": "Standard Construction",
                "ltc_ratio": 0.70,  # 70% LTC
                "interest_rate": 0.08,
                "loan_term_months": 24,
            },
            permanent_terms={
                "name": "Permanent Loan",
                "loan_amount": 35_000_000,
                "interest_rate": 0.06,
                "loan_term_months": 120,
                "amortization_months": 360,
            },
            project_value=80_000_000,
        )

        deal = self.create_test_deal(
            partnership=derived_partnership,  # No commitments = derived mode
            base_project=base_project,  # Uses default $70M construction
            base_acquisition=base_acquisition,
            financing=standard_financing,
            name="Derived Mode Test",
        )

        # Should not raise any validation errors (derived mode)
        equity_target = self.run_capital_validation_test(deal, total_cost=80_000_000)

        # Should calculate based on LTC, not commitments
        expected_equity = 80_000_000 * (1 - 0.70)  # 30% of $80M = $24M
        assert abs(equity_target - expected_equity) < 1000

    def test_required_equity_calculation_accuracy(
        self, base_capital_plan, base_project, base_acquisition, adequate_partnership
    ):
        """Test that required equity calculation handles various LTC scenarios correctly."""
        # Create test project with $80M construction (vs $70M default)
        test_capital_plan = base_capital_plan.model_copy(
            update={
                "name": "Test Project",
                "capital_items": [
                    base_capital_plan.capital_items[0].model_copy(
                        update={"value": 80_000_000}  # $80M construction
                    )
                ],
            }
        )

        test_project = base_project.model_copy(
            update={
                "name": "Test Project",
                "construction_plan": test_capital_plan,
            }
        )

        test_acquisition = base_acquisition.model_copy(update={"name": "Land"})

        # 60% LTC financing
        test_financing = create_construction_to_permanent_plan(
            construction_terms={
                "name": "Test Construction",
                "ltc_ratio": 0.60,  # 60% LTC on $90M = need $36M equity
                "interest_rate": 0.08,
                "loan_term_months": 24,
            },
            permanent_terms={
                "name": "Permanent Loan",
                "loan_amount": 30_000_000,
                "interest_rate": 0.06,
                "loan_term_months": 120,
                "amortization_months": 360,
            },
            project_value=90_000_000,
        )

        deal = self.create_test_deal(
            partnership=adequate_partnership,  # $50M committed
            base_project=test_project,
            base_acquisition=test_acquisition,
            financing=test_financing,
            name="LTC Calculation Test",
        )

        ledger = Ledger()
        context = DealContext(
            deal=deal,
            timeline=self.timeline,
            settings=self.settings,
            ledger=ledger,
        )
        engine = CashFlowEngine(context)

        # Test the required equity calculation
        total_cost = 90_000_000  # $10M land + $80M construction
        required_equity = engine._calculate_required_equity_from_ltc(total_cost)

        expected_required = total_cost * (1 - 0.60)  # 40% of $90M = $36M
        assert abs(required_equity - expected_required) < 1000

        # Committed: $50M, Required: $36M = sufficient (should pass)
        equity_target = self.run_capital_validation_test(deal, total_cost=total_cost)
        assert equity_target == 50_000_000  # Should return commitments

    def test_zero_commitment_edge_case(self):
        """Test edge case where one partner has zero commitment."""
        partnership = create_simple_capital_partnership(
            gp_capital=0,  # $0 commitment (!)
            lp_capital=50_000_000,  # $50M commitment
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
        assert gp.share == 0.0  # 0% ownership
        assert lp.share == 1.0  # 100% ownership

    def test_all_equity_deal_validation(
        self, base_capital_plan, base_project, base_acquisition
    ):
        """Test validation for all-equity deals with commitments."""
        # Create partnership for all-equity deal ($100M committed)
        all_equity_partnership = create_simple_capital_partnership(
            gp_capital=25_000_000,
            lp_capital=75_000_000,  # $100M total
        )

        # Create all-equity project ($90M construction + $10M land = $100M total)
        all_equity_capital_plan = base_capital_plan.model_copy(
            update={
                "name": "All Equity Project",
                "capital_items": [
                    base_capital_plan.capital_items[0].model_copy(
                        update={"value": 90_000_000}  # $90M construction
                    )
                ],
            }
        )

        all_equity_project = base_project.model_copy(
            update={
                "name": "All Equity Project",
                "construction_plan": all_equity_capital_plan,
                "gross_area": 120_000,
                "net_rentable_area": 108_000,
            }
        )

        # No financing = all equity deal
        deal = self.create_test_deal(
            partnership=all_equity_partnership,  # $100M committed vs $100M needed
            base_project=all_equity_project,
            base_acquisition=base_acquisition,
            financing=None,  # All-equity deal
            name="All Equity Deal",
        )

        # Should work perfectly - exact match
        equity_target = self.run_capital_validation_test(deal, total_cost=100_000_000)
        assert equity_target == 100_000_000  # Exact match

    def test_ltc_accuracy_with_validation(self):
        """Test that LTC-based required equity calculation is accurate."""
        # Create a simple test case to verify LTC math
        ltc_test_partnership = create_simple_capital_partnership(
            gp_capital=10_000_000,
            lp_capital=30_000_000,  # $40M total
        )

        # Mock deal for engine creation (lightweight test)
        mock_deal = Mock()
        mock_deal.has_equity_partners = True
        mock_deal.equity_partners = ltc_test_partnership
        mock_deal.financing = Mock()

        # Create mock facility with known LTC
        mock_facility = Mock()
        mock_facility.kind = "construction"
        mock_facility.ltc_ratio = 0.75  # 75% LTC
        mock_deal.financing.facilities = [mock_facility]

        ledger = Ledger()
        context = DealContext(
            deal=mock_deal,
            timeline=self.timeline,
            settings=self.settings,
            ledger=ledger,
        )
        engine = CashFlowEngine(context)

        # Test required equity calculation
        test_cost = 100_000_000  # $100M project
        required_equity = engine._calculate_required_equity_from_ltc(test_cost)

        expected = test_cost * (1 - 0.75)  # 25% equity = $25M
        assert abs(required_equity - expected) < 100

        # Commitments ($40M) > Required ($25M) = should warn about excess
        # (This would trigger excess equity warning in actual validation)
