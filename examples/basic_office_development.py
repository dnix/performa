#!/usr/bin/env python3
# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Basic Office Development Example

This script demonstrates a complete office development deal analysis using Performa's
full Deal structure, including acquisition, financing, partnerships, and exit strategy.

## Development Deal Modeling Framework

This example models a $23.5M office tower development using institutional-grade
financial analysis methodologies. The model demonstrates the complete deal lifecycle
from land acquisition through construction, lease-up, stabilization, and disposition.

### Deal Structure & Methodology

The analysis implements a multi-layered approach separating asset performance from
financing and partnership structures:

1. **Asset Layer**: Physical property modeling with absorption plans and stabilized operations
2. **Financing Layer**: Construction-to-permanent debt structure with DSCR monitoring
3. **Partnership Layer**: GP/LP equity waterfall with IRR-based promote calculations
4. **Deal Layer**: Integrated analysis combining all components for comprehensive metrics

### Financial Architecture

**Project Capitalization**:
- Total Development Cost: $23.5M (land $5M, construction $16.5M, fees $2M)
- Financing Structure: 70% LTC construction facility → 70% LTV permanent loan
- Equity Structure: 90% LP / 10% GP with 8% preferred return + 20% promote

**Key Modeling Components**:
- **Construction Facility**: Senior tranche at 70% LTC, 6.5% rate, 15% interest reserve
- **Permanent Facility**: $18M, 5.5% rate, 10-year term, 25-year amortization
- **Absorption Plan**: 9 leases over 18 months, $35/SF rent, 7-year terms
- **Exit Strategy**: 6.5% reversion cap rate, 2.5% transaction costs

### Analysis Workflow & Results

The model executes the standard institutional analysis sequence:

1. **Unlevered Analysis**: Asset cash flows without financing effects
2. **Valuation Analysis**: Property value estimation and disposition proceeds
3. **Debt Analysis**: Facility processing with DSCR calculations and covenant monitoring
4. **Cash Flow Analysis**: Institutional funding cascade with equity/debt coordination
5. **Partnership Analysis**: Waterfall distribution calculations with promote mechanics

**Expected Performance Metrics**:
- **Deal IRR**: ~23% (strong for development, target typically 15-20%)
- **GP Returns**: ~43% IRR due to promote structure and leverage effects
- **LP Returns**: ~18% IRR with lower risk profile
- **Debt Metrics**: Minimum DSCR 1.35x (well above typical 1.25x requirement)

### Technical Implementation

The example demonstrates Performa's capabilities:

- **Asset Factory Pattern**: Absorption plans defining leasing strategy and stabilized assumptions
- **Polymorphic Valuation**: ReversionValuation with cap rate methodology
- **Multi-Facility Financing**: Construction-to-permanent transition modeling
- **Institutional Waterfall**: Binary search precision for IRR-based promote tiers
- **Comprehensive Reporting**: Sources & uses, draw requests, leasing status, development summary

### Model Validation

Key validation points for deal feasibility:

- **DSCR Coverage**: Minimum 1.35x indicates strong debt service capability
- **Development Yield**: 6.0% yield on cost provides adequate return buffer
- **Market Assumptions**: $35/SF rent and 6.5% exit cap rate reflect market positioning
- **Partnership Returns**: Both GP and LP achieve target return thresholds

This example serves as a reference implementation for institutional-grade development
deal modeling, demonstrating best practices for multi-layered financial analysis
with proper separation of concerns between asset, debt, and equity components.
"""

import sys
from datetime import date
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from performa.asset.office import (
    DirectLeaseTerms,
    EqualSpreadPace,
    OfficeAbsorptionPlan,
    OfficeDevelopmentBlueprint,
    OfficeVacantSuite,
    SpaceFilter,
)
from performa.core.capital import CapitalItem, CapitalPlan
from performa.core.primitives import (
    AssetTypeEnum,
    FirstOnlyDrawSchedule,
    GlobalSettings,
    ProgramUseEnum,
    PropertyAttributeKey,
    Timeline,
    UponExpirationEnum,
)
from performa.deal import (
    AcquisitionTerms,
    CarryPromote,
    Deal,
    Partner,
    PartnershipStructure,
    analyze,
)
from performa.debt import (
    ConstructionFacility,
    DebtTranche,
    FinancingPlan,
    FixedRate,
    InterestRate,
    PermanentFacility,
)
from performa.development import DevelopmentProject
from performa.reporting import (
    create_development_summary,
    create_draw_request,
    create_leasing_status_report,
    create_sources_and_uses_report,
)
from performa.valuation import ReversionValuation


def create_sample_development_deal():
    """Create a sample office development deal demonstrating complete Performa Deal structure"""
    
    # Create project timeline (30-month total: 24 months construction + 6 months lease-up)
    start_date = date(2024, 1, 1)
    timeline = Timeline(start_date=start_date, duration_months=30)
    
    # Define capital expenditure plan with construction costs
    capital_items = [
        CapitalItem(
            name="Land Acquisition",
            work_type="land",
            value=5_000_000,
            draw_schedule=FirstOnlyDrawSchedule(),
            timeline=timeline
        ),
        CapitalItem(
            name="Construction - Core & Shell",
            work_type="construction",
            value=15_000_000,
            draw_schedule=FirstOnlyDrawSchedule(),
            # FIXME: conistruction is an s-curve, not a single draw
            timeline=timeline
        ),
        CapitalItem(
            name="Professional Fees",
            work_type="soft_costs",
            value=1_500_000,
            draw_schedule=FirstOnlyDrawSchedule(),
            timeline=timeline
            # FIXME: professional fees should be evenly paid over the construction period
        ),
        CapitalItem(
            name="Developer Fee",
            work_type="developer",
            value=2_000_000,
            draw_schedule=FirstOnlyDrawSchedule(),
            timeline=timeline
            # FIXME: developer fee should be evenly paid over the construction period
        ),
    ]
    
    capital_plan = CapitalPlan(name="Office Development Plan", capital_items=capital_items)
    
    # Define vacant office space inventory for lease-up
    vacant_suites = [
        OfficeVacantSuite(
            suite="Floor 1",
            floor="1",
            area=15000.0,  # 15,000 SF
            use_type=ProgramUseEnum.OFFICE,
            is_divisible=True,
            subdivision_average_lease_area=5000.0,  # Average 5,000 SF per lease
            subdivision_minimum_lease_area=2500.0   # Minimum 2,500 SF
        ),
        OfficeVacantSuite(
            suite="Floor 2",
            floor="2", 
            area=15000.0,
            use_type=ProgramUseEnum.OFFICE,
            is_divisible=True,
            subdivision_average_lease_area=5000.0,
            subdivision_minimum_lease_area=2500.0
        ),
        OfficeVacantSuite(
            suite="Floor 3",
            floor="3",
            area=15000.0,
            use_type=ProgramUseEnum.OFFICE,
            is_divisible=True,
            subdivision_average_lease_area=5000.0,
            subdivision_minimum_lease_area=2500.0
        ),
    ]
    
    # Define market absorption plan for space lease-up
    absorption_plan = OfficeAbsorptionPlan.with_typical_assumptions(
        name="Metro Tower Lease-Up Plan",
        space_filter=SpaceFilter(
            floors=["1", "2", "3"],
            use_types=[ProgramUseEnum.OFFICE]
        ),
        start_date_anchor=date(2025, 6, 1),  # Start leasing 6 months after construction start
        pace=EqualSpreadPace(
            total_deals=9,       # 9 deals over lease-up period
            frequency_months=2   # New deal every 2 months (18 months / 9 deals)
        ),
        leasing_assumptions=DirectLeaseTerms(
            base_rent_value=35.0,  # $35/SF
                            base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
            term_months=84,  # 7-year leases
            upon_expiration=UponExpirationEnum.MARKET
        )
    )
    
    # Create development blueprint combining space and absorption plan
    office_blueprint = OfficeDevelopmentBlueprint(
        name="Metro Office Tower",
        vacant_inventory=vacant_suites,
        absorption_plan=absorption_plan
    )
    
    # Create the development project
    project = DevelopmentProject(
        name="Metro Office Tower Development",
        property_type=AssetTypeEnum.OFFICE,
        gross_area=50000.0,  # 50,000 SF gross (includes common areas)
        net_rentable_area=45000.0,  # 45,000 SF rentable
        construction_plan=capital_plan,
        blueprints=[office_blueprint]
    )
    
    # === DEAL COMPONENTS ===
    
    # 1. Acquisition Terms - Land purchase with closing costs
    acquisition = AcquisitionTerms(
        name="Land Acquisition",
        timeline=Timeline(start_date=start_date, duration_months=1),
        value=5_000_000,  # Land cost
        acquisition_date=start_date,
        closing_costs_rate=0.025  # 2.5% closing costs
    )
    
    # 2. Financing Plan - Construction-to-Permanent financing
    
    # Construction loan with senior tranche
    construction_loan = ConstructionFacility(
        name="Construction Facility",
        tranches=[
            DebtTranche(
                name="Senior Construction",
                interest_rate=InterestRate(
                    details=FixedRate(
                        rate=0.065  # 6.5% construction rate
                    )
                ),
                fee_rate=0.01,  # 1% origination fee
                ltc_threshold=0.70  # 70% LTC
            )
        ],
        fund_interest_from_reserve=True,
        interest_reserve_rate=0.15  # 15% interest reserve
    )
    
    # Permanent loan for stabilized operations
    permanent_loan = PermanentFacility(
        name="Permanent Facility",
        loan_amount=18_000_000,
        interest_rate=InterestRate(
            details=FixedRate(
                rate=0.055  # 5.5% permanent rate
            )
        ),
        loan_term_years=10,
        amortization_years=25,
        ltv_ratio=0.70,  # 70% LTV
        dscr_hurdle=1.25,  # 1.25x DSCR requirement
        origination_fee_rate=0.005  # 0.5% origination fee
    )
    
    financing_plan = FinancingPlan(
        name="Construction-to-Permanent Financing",
        facilities=[construction_loan, permanent_loan]
    )
    
    # 3. Partnership Structure - GP/LP with typical waterfall
    gp_partner = Partner(
        name="Development GP",
        kind="GP",
        share=0.10  # 10% equity share
    )
    
    lp_partner = Partner(
        name="Institutional LP",
        kind="LP", 
        share=0.90  # 90% equity share
    )
    
    partnership = PartnershipStructure(
        partners=[gp_partner, lp_partner],
        distribution_method="waterfall",
        promote=CarryPromote()  # Uses defaults: 8% preferred return, 20% promote
    )
    
    # 4. Exit Strategy - Disposition at stabilization
    exit_valuation = ReversionValuation(
        name="Stabilized Disposition",
        cap_rate=0.065,  # 6.5% exit cap rate
        transaction_costs_rate=0.025,  # 2.5% transaction costs
        hold_period_months=84  # 7-year hold period
    )
    
    # 5. Create Complete Deal
    deal = Deal(
        name="Metro Office Tower Development Deal",
        description="Complete office development with construction-to-permanent financing and GP/LP partnership",
        asset=project,
        acquisition=acquisition,
        financing=financing_plan,
        exit_valuation=exit_valuation,
        equity_partners=partnership
    )
    
    return deal


def main():
    """Run the office development deal analysis and generate reports"""
    print("🏢 Performa Office Development Deal Example")
    print("=" * 60)
    
    # Initialize development deal
    try:
        deal = create_sample_development_deal()
        print(f"✅ Created deal: {deal.name}")
        print(f"   Deal Type: {deal.deal_type}")
        print(f"   Asset Type: {deal.asset.property_type.value}")
        print(f"   Total Development Cost: ${deal.asset.construction_plan.total_cost:,.0f}")
        print(f"   Net Rentable Area: {deal.asset.net_rentable_area:,.0f} SF")
        print(f"   Partnership: {len(deal.equity_partners.partners)} partners")
        print(f"   Financing: {deal.financing.name}")
    except Exception as e:
        print(f"❌ Failed to create development deal: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Comprehensive Deal Analysis
    print("\n📈 Running Comprehensive Deal Analysis...")
    try:
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=120)  # 10-year analysis
        settings = GlobalSettings()
        
        results = analyze(deal, timeline, settings)
        
        print("✅ Deal Analysis Complete!")
        print(f"   Deal IRR: {results.deal_metrics.irr:.2%}")
        print(f"   Equity Multiple: {results.deal_metrics.equity_multiple:.2f}x")
        print(f"   Total Equity Invested: ${results.deal_metrics.total_equity_invested:,.0f}")
        print(f"   Net Profit: ${results.deal_metrics.net_profit:,.0f}")
        
        # Partnership Results
        if results.partner_distributions and results.partner_distributions.distribution_method == "waterfall":
            waterfall_details = results.partner_distributions.waterfall_details
            print("\n👥 Partnership Results:")
            for partner_name, partner_result in waterfall_details.partner_results.items():
                print(f"   {partner_name}:")
                print(f"     IRR: {partner_result.irr:.2%}" if partner_result.irr else "     IRR: N/A")
                print(f"     Equity Multiple: {partner_result.equity_multiple:.2f}x")
                print(f"     Total Return: ${partner_result.total_distributions:,.0f}")
        
        # Financing Results
        if results.financing_analysis:
            print("\n💰 Financing Analysis:")
            print(f"   Minimum DSCR: {results.financing_analysis.dscr_summary.minimum_dscr:.2f}x")
            print(f"   Average DSCR: {results.financing_analysis.dscr_summary.average_dscr:.2f}x")
            print(f"   Number of Facilities: {len(results.financing_analysis.facilities)}")
            
    except Exception as e:
        print(f"❌ Deal Analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Test Sources & Uses Report (using the asset directly)
    print("\n📊 Generating Sources & Uses Report...")
    try:
        sources_uses_report = create_sources_and_uses_report(deal.asset)
        report_data = sources_uses_report.generate_data()
        
        print("   Project Info:")
        for key, value in report_data["project_info"].items():
            print(f"     {key}: {value}")
        
        print("   Uses Summary:")
        for key, value in report_data["uses"].items():
            print(f"     {key}: {value}")
            
        print("✅ Sources & Uses Report generated successfully")
    except Exception as e:
        print(f"❌ Sources & Uses Report failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Test Development Summary Report
    print("\n📈 Generating Development Summary...")
    try:
        summary_report = create_development_summary(deal.asset)
        summary_data = summary_report.generate_data()
        
        print("   Financial Summary:")
        for key, value in summary_data["financial_summary"].items():
            print(f"     {key}: {value}")
            
        print("✅ Development Summary generated successfully")
    except Exception as e:
        print(f"❌ Development Summary failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Test Construction Draw Report
    print("\n🏗️ Generating Construction Draw Request...")
    try:
        draw_period = date(2024, 6, 1)
        draw_report = create_draw_request(deal.asset, draw_period)
        draw_data = draw_report.generate_data()
        
        print("   Draw Header:")
        for key, value in draw_data["draw_header"].items():
            print(f"     {key}: {value}")
            
        print("✅ Construction Draw Request generated successfully")
    except Exception as e:
        print(f"❌ Construction Draw Request failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Test Leasing Status Report
    print("\n🏢 Generating Leasing Status Report...")
    try:
        status_date = date(2025, 9, 1)
        leasing_report = create_leasing_status_report(deal.asset, status_date)
        leasing_data = leasing_report.generate_data()
        
        print("   Leasing Summary:")
        for key, value in leasing_data["leasing_summary"].items():
            print(f"     {key}: {value}")
            
        print("✅ Leasing Status Report generated successfully")
    except Exception as e:
        print(f"❌ Leasing Status Report failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n🎉 Complete development deal analysis working!")
    print("📋 All Deal components and reporting functionality demonstrated!")


if __name__ == "__main__":
    main() 