# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Integration Tests for Partnership Foundation

This module tests the complete partnership functionality integrated with real deals,
demonstrating the full partnership foundation in action.
"""

from datetime import datetime

import pandas as pd
import pytest
from pydantic import ValidationError

from performa.core.capital import CapitalItem, CapitalPlan
from performa.core.primitives import AssetTypeEnum, Timeline
from performa.deal import (
    Deal,
    DistributionCalculator,
    Partner,
    PartnershipStructure,
    analyze,
    create_simple_partnership,
)
from performa.deal.acquisition import AcquisitionTerms
from performa.development.project import DevelopmentProject


class TestPartnershipIntegrationWithRealDeals:
    """Test partnership functionality with complete real estate deals."""

    @pytest.fixture
    def development_project(self):
        """Create a sample development project."""
        return DevelopmentProject(
            name="Urban Mixed-Use Development",
            property_type=AssetTypeEnum.MIXED_USE,
            gross_area=250_000.0,
            net_rentable_area=225_000.0,
            construction_plan=CapitalPlan(
                name="Mixed-Use Construction", 
                capital_items=[
                    CapitalItem(
                        name="Mixed-Use Construction",
                        value=50_000_000,  # $50M construction 
                        timeline=Timeline.from_dates(datetime(2024, 1, 1), datetime(2025, 12, 31)),
                    )
                ]
            ),
            blueprints=[],
        )

    @pytest.fixture
    def acquisition_terms(self):
        """Create sample acquisition terms."""
        timeline = Timeline(start_date=datetime(2024, 1, 1), duration_months=1)
        return AcquisitionTerms(
            name="Land Acquisition",
            timeline=timeline,
            value=25_000_000.0,  # $25M land cost
            acquisition_date=datetime(2024, 1, 1).date(),
            closing_costs_rate=0.03,
        )

    @pytest.fixture
    def analysis_timeline(self):
        """Create analysis timeline."""
        return Timeline(
            start_date=datetime(2024, 1, 1),
            duration_months=36,  # 3-year analysis
        )

    def test_development_deal_with_institutional_partnership(
        self, development_project, acquisition_terms, analysis_timeline
    ):
        """
        Test a complete development deal with institutional partnership.

        Scenario: Development sponsor (GP) partners with institutional capital (LP)
        - GP: 20% ownership, development sponsor
        - LP: 80% ownership, institutional capital provider
        - All-equity development deal (no debt for simplicity)
        """
        # Create institutional partnership structure
        gp = Partner(
            name="Development Sponsor LLC",
            kind="GP",
            share=0.20,
            description="Development and asset management sponsor",
        )

        lp = Partner(
            name="Institutional Capital Fund",
            kind="LP",
            share=0.80,
            description="Institutional equity capital provider",
        )

        partnership = PartnershipStructure(
            partners=[gp, lp], distribution_method="pari_passu"
        )

        # Create development deal with partnership
        deal = Deal(
            name="Urban Mixed-Use Development Partnership",
            asset=development_project,
            acquisition=acquisition_terms,
            financing=None,  # All-equity for simplicity
            equity_partners=partnership,
        )

        # Analyze the deal
        results = analyze(deal, analysis_timeline)

        # Test deal summary reflects partnership
        deal_summary = results.deal_summary
        assert deal_summary.deal_name == "Urban Mixed-Use Development Partnership"
        assert deal_summary.has_financing is False

        # Test partner distributions are calculated
        partner_distributions = results.partner_distributions
        assert (
            partner_distributions.distribution_method == "waterfall"
        )  # pari_passu maps to waterfall (no promotes)
        assert hasattr(partner_distributions, "waterfall_details")

        # Test individual partner results
        partner_results = partner_distributions.waterfall_details.partner_results
        assert "Development Sponsor LLC" in partner_results
        assert "Institutional Capital Fund" in partner_results

        gp_results = partner_results["Development Sponsor LLC"]
        lp_results = partner_results["Institutional Capital Fund"]

        # Validate GP (20% ownership)
        assert gp_results.ownership_percentage == 0.20
        assert gp_results.partner_info.kind == "GP"
        assert gp_results.partner_info.name == "Development Sponsor LLC"

        # Validate LP (80% ownership)
        assert lp_results.ownership_percentage == 0.80
        assert lp_results.partner_info.kind == "LP"
        assert lp_results.partner_info.name == "Institutional Capital Fund"

        # Test proportional allocation
        if gp_results.total_investment > 0 and lp_results.total_investment > 0:
            # GP should invest 20%, LP should invest 80%
            total_investment = gp_results.total_investment + lp_results.total_investment
            gp_percentage = gp_results.total_investment / total_investment
            lp_percentage = lp_results.total_investment / total_investment

            assert abs(gp_percentage - 0.20) < 0.01  # Within 1%
            assert abs(lp_percentage - 0.80) < 0.01  # Within 1%

    def test_development_deal_with_multiple_partners(
        self, development_project, acquisition_terms, analysis_timeline
    ):
        """
        Test a development deal with multiple partners across GP/LP categories.

        Scenario: Joint venture with multiple sponsors and capital sources
        - Lead GP: 15% ownership
        - Co-GP: 10% ownership
        - Institutional LP: 60% ownership
        - Family Office LP: 15% ownership
        """
        # Create multi-partner structure
        lead_gp = Partner(name="Lead Development GP", kind="GP", share=0.15)
        co_gp = Partner(name="Co-Development GP", kind="GP", share=0.10)
        institutional_lp = Partner(name="Pension Fund LP", kind="LP", share=0.60)
        family_office_lp = Partner(name="Family Office LP", kind="LP", share=0.15)

        partnership = PartnershipStructure(
            partners=[lead_gp, co_gp, institutional_lp, family_office_lp],
            distribution_method="pari_passu",
        )

        # Create deal
        deal = Deal(
            name="Multi-Partner Joint Venture",
            asset=development_project,
            acquisition=acquisition_terms,
            equity_partners=partnership,
        )

        # Analyze deal
        results = analyze(deal, analysis_timeline)

        # Test partnership summary
        partner_distributions = results.partner_distributions
        # Note: partnership_summary is not included in the waterfall result structure
        # partnership_summary = partner_distributions["partnership_summary"]

        # Test basic structure instead
        assert (
            partner_distributions.distribution_method == "waterfall"
        )  # pari_passu maps to waterfall
        assert hasattr(partner_distributions, "waterfall_details")

        # Test all partners are included
        partner_results = partner_distributions.waterfall_details.partner_results
        expected_partners = [
            "Lead Development GP",
            "Co-Development GP",
            "Pension Fund LP",
            "Family Office LP",
        ]
        for partner_name in expected_partners:
            assert partner_name in partner_results

        # Test ownership percentages
        assert partner_results["Lead Development GP"].ownership_percentage == 0.15
        assert partner_results["Co-Development GP"].ownership_percentage == 0.10
        assert partner_results["Pension Fund LP"].ownership_percentage == 0.60
        assert partner_results["Family Office LP"].ownership_percentage == 0.15

    def test_partnership_distribution_calculator_standalone(self, analysis_timeline):
        """
        Test the DistributionCalculator directly with realistic cash flows.

        This tests the distribution calculator independent of deal analysis
        to validate the core partnership distribution logic.
        """
        # Create simple partnership
        partnership = create_simple_partnership(
            gp_name="Development GP", gp_share=0.25, lp_name="Capital LP", lp_share=0.75
        )

        # Create realistic development cash flows
        # Scenario: $20M investment over 18 months, $30M sale proceeds
        cash_flows = pd.Series(
            [
                -5_000_000,  # Month 1: Land acquisition
                -2_000_000,  # Month 2: Construction start
                -3_000_000,  # Month 3: Construction ramp-up
                -2_000_000,  # Month 4: Construction
                -2_000_000,  # Month 5: Construction
                -3_000_000,  # Month 6: Construction
                -2_000_000,  # Month 7: Construction
                -1_000_000,  # Month 8: Construction wind-down
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,  # Months 9-18: Lease-up period
                30_000_000,  # Month 19: Sale
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,  # Months 20-36: Post-sale
            ],
            index=analysis_timeline.period_index,
        )

        # Calculate distributions
        calculator = DistributionCalculator(partnership)
        results = calculator.calculate_distributions(cash_flows, analysis_timeline)

        # Validate basic structure
        assert results["distribution_method"] == "pari_passu"
        assert "partner_distributions" in results
        assert "total_metrics" in results

        # Test total metrics
        total_metrics = results["total_metrics"]
        assert total_metrics["total_investment"] == 20_000_000  # Total investment
        assert total_metrics["total_distributions"] == 30_000_000  # Total returns
        assert total_metrics["net_profit"] == 10_000_000  # $10M profit
        assert total_metrics["equity_multiple"] == 1.5  # 1.5x return

        # Test partner allocations
        gp_results = results["partner_distributions"]["Development GP"]
        lp_results = results["partner_distributions"]["Capital LP"]

        # GP (25% ownership)
        assert gp_results["total_investment"] == 5_000_000  # 25% of $20M
        assert gp_results["total_distributions"] == 7_500_000  # 25% of $30M
        assert gp_results["net_profit"] == 2_500_000  # $2.5M profit
        assert gp_results["equity_multiple"] == 1.5  # Same return multiple

        # LP (75% ownership)
        assert lp_results["total_investment"] == 15_000_000  # 75% of $20M
        assert lp_results["total_distributions"] == 22_500_000  # 75% of $30M
        assert lp_results["net_profit"] == 7_500_000  # $7.5M profit
        assert lp_results["equity_multiple"] == 1.5  # Same return multiple

        # Test cash flow period-by-period allocation
        gp_cash_flows = gp_results["cash_flows"]
        lp_cash_flows = lp_results["cash_flows"]

        # Month 1: -$5M investment should be allocated 25%/75%
        assert gp_cash_flows.iloc[0] == -1_250_000  # 25% of -$5M
        assert lp_cash_flows.iloc[0] == -3_750_000  # 75% of -$5M

        # Month 19: $30M sale should be allocated 25%/75%
        assert gp_cash_flows.iloc[18] == 7_500_000  # 25% of $30M
        assert lp_cash_flows.iloc[18] == 22_500_000  # 75% of $30M

    def test_partner_summary_dataframe_formatting(self):
        """
        Test the formatted partner summary DataFrame for reporting.

        This validates the reporting functionality for partnership results.
        """
        # Create partnership
        partnership = create_simple_partnership(
            gp_name="Sponsor GP", gp_share=0.30, lp_name="Investor LP", lp_share=0.70
        )

        # Create simple timeline and cash flows
        timeline = Timeline(start_date=datetime(2024, 1, 1), duration_months=12)
        cash_flows = pd.Series(
            [
                -10_000_000,  # Investment
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,  # Hold periods
                14_000_000,  # Sale (40% return)
            ],
            index=timeline.period_index,
        )

        # Calculate distributions
        calculator = DistributionCalculator(partnership)
        results = calculator.calculate_distributions(cash_flows, timeline)

        # Create summary DataFrame
        summary_df = calculator.create_partner_summary_dataframe(results)

        # Test DataFrame structure
        assert len(summary_df) == 3  # 2 partners + total row
        expected_columns = [
            "Partner",
            "Type",
            "Ownership",
            "Investment",
            "Distributions",
            "Net Profit",
            "Equity Multiple",
            "IRR",
        ]
        assert list(summary_df.columns) == expected_columns

        # Test data formatting (all values should be properly formatted strings)
        sponsor_row = summary_df.iloc[0]
        assert sponsor_row["Partner"] == "Sponsor GP"
        assert sponsor_row["Type"] == "GP"
        assert sponsor_row["Ownership"] == "30.0%"
        assert sponsor_row["Investment"] == "$3,000,000"  # 30% of $10M
        assert sponsor_row["Distributions"] == "$4,200,000"  # 30% of $14M
        assert sponsor_row["Net Profit"] == "$1,200,000"  # $1.2M profit
        assert sponsor_row["Equity Multiple"] == "1.40x"  # 1.4x return

        investor_row = summary_df.iloc[1]
        assert investor_row["Partner"] == "Investor LP"
        assert investor_row["Type"] == "LP"
        assert investor_row["Ownership"] == "70.0%"
        assert investor_row["Investment"] == "$7,000,000"  # 70% of $10M
        assert investor_row["Distributions"] == "$9,800,000"  # 70% of $14M
        assert investor_row["Net Profit"] == "$2,800,000"  # $2.8M profit
        assert investor_row["Equity Multiple"] == "1.40x"  # 1.4x return

        total_row = summary_df.iloc[2]
        assert total_row["Partner"] == "TOTAL"
        assert total_row["Type"] == "ALL"
        assert total_row["Ownership"] == "100.0%"
        assert total_row["Investment"] == "$10,000,000"
        assert total_row["Distributions"] == "$14,000,000"
        assert total_row["Net Profit"] == "$4,000,000"
        assert total_row["Equity Multiple"] == "1.40x"


class TestPartnershipFoundationEdgeCases:
    """Test edge cases and validation for the partnership foundation."""

    def test_single_entity_vs_partnership_behavior(self):
        """
        Test that deals behave correctly both with and without partnerships.

        This ensures backward compatibility and proper handling of single-entity deals.
        """
        # Create basic deal components
        timeline = Timeline(start_date=datetime(2024, 1, 1), duration_months=12)
        acquisition_timeline = Timeline(
            start_date=datetime(2024, 1, 1), duration_months=1
        )

        acquisition = AcquisitionTerms(
            name="Test Acquisition",
            timeline=acquisition_timeline,
            value=5_000_000.0,
            acquisition_date=datetime(2024, 1, 1).date(),
        )

        project = DevelopmentProject(
            name="Test Development",
            property_type=AssetTypeEnum.OFFICE,
            gross_area=50_000.0,
            net_rentable_area=45_000.0,
            construction_plan=CapitalPlan(name="Test Construction", capital_items=[]),
            blueprints=[],
        )

        # Test 1: Single entity deal (no partners)
        single_entity_deal = Deal(
            name="Single Entity Deal",
            asset=project,
            acquisition=acquisition,
            equity_partners=None,
        )

        single_results = analyze(single_entity_deal, timeline)
        single_distributions = single_results.partner_distributions

        assert single_distributions.distribution_method == "single_entity"
        assert hasattr(single_distributions, "total_distributions")
        assert hasattr(single_distributions, "total_investment")

        # Test 2: Partnership deal
        partnership = create_simple_partnership("GP", 0.25, "LP", 0.75)

        partnership_deal = Deal(
            name="Partnership Deal",
            asset=project,
            acquisition=acquisition,
            equity_partners=partnership,
        )

        partnership_results = analyze(partnership_deal, timeline)
        partnership_distributions = partnership_results.partner_distributions

        assert (
            partnership_distributions.distribution_method == "waterfall"
        )  # pari_passu maps to waterfall
        assert hasattr(partnership_distributions, "waterfall_details")
        # assert "partnership_summary" in partnership_distributions  # Not available in waterfall result

        # Both should have valid metrics
        assert isinstance(single_distributions.equity_multiple, (int, float))
        assert isinstance(partnership_distributions.equity_multiple, (int, float))

    def test_partnership_validation_integration(self):
        """
        Test that partnership validation works properly in the context of deals.

        This ensures that invalid partnerships are caught during deal creation.
        """
        # Create basic deal components
        timeline = Timeline(start_date=datetime(2024, 1, 1), duration_months=1)

        acquisition = AcquisitionTerms(
            name="Test Acquisition",
            timeline=timeline,
            value=1_000_000.0,
            acquisition_date=datetime(2024, 1, 1).date(),
        )

        project = DevelopmentProject(
            name="Test Development",
            property_type=AssetTypeEnum.OFFICE,
            gross_area=10_000.0,
            net_rentable_area=9_000.0,
            construction_plan=CapitalPlan(name="Test Construction", capital_items=[]),
            blueprints=[],
        )

        # Test 1: Invalid partnership shares (don't sum to 100%)
        gp_invalid = Partner(name="GP", kind="GP", share=0.30)
        lp_invalid = Partner(name="LP", kind="LP", share=0.60)  # Only 90% total

        with pytest.raises(ValidationError):
            PartnershipStructure(partners=[gp_invalid, lp_invalid])

        # Test 2: Duplicate partner names
        gp1 = Partner(name="Same Name", kind="GP", share=0.20)
        gp2 = Partner(name="Same Name", kind="GP", share=0.30)
        lp = Partner(name="Different Name", kind="LP", share=0.50)

        with pytest.raises(ValidationError):
            PartnershipStructure(partners=[gp1, gp2, lp])

        # Test 3: Valid partnership works in deal
        valid_partnership = create_simple_partnership(
            "Valid GP", 0.40, "Valid LP", 0.60
        )

        valid_deal = Deal(
            name="Valid Partnership Deal",
            asset=project,
            acquisition=acquisition,
            equity_partners=valid_partnership,
        )

        # Should not raise an exception
        assert valid_deal.has_equity_partners is True
        assert valid_deal.equity_partners.partner_count == 2
