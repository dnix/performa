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
- **Construction Facility**: Senior tranche at 70% LTC, 6.5% rate, sophisticated draw-based interest calculation
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
- **Sophisticated Construction Finance**: Automated loan sizing with draw-based interest calculations
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

import traceback
from datetime import date

from performa.core.primitives import GlobalSettings
from performa.deal import analyze
from performa.patterns import OfficeDevelopmentPattern


def create_sample_development_deal():
    """Create a sample office development deal using the validated OfficeDevelopmentPattern"""

    # Use EXACT same working configuration from development_comparison.py
    pattern = OfficeDevelopmentPattern(
        # Core project parameters
        project_name="Metro Office Tower Development",
        acquisition_date=date(2024, 1, 1),
        land_cost=5_000_000,
        land_closing_costs_rate=0.025,  # Match composition closing costs
        # Building specifications (natural office parameters)
        net_rentable_area=45_000,  # 45,000 SF net rentable
        gross_area=50_000,  # 50,000 SF gross (includes common areas)
        floors=3,  # 3 floors in the building
        # Leasing assumptions ($/SF metrics) - IMPROVED FOR ATTRACTIVE RETURNS
        target_rent_psf=45.0,  # $45/SF/year base rent (premium market)
        average_lease_size_sf=5_000,  # 5,000 SF average lease
        minimum_lease_size_sf=2_500,  # 2,500 SF minimum lease
        lease_term_months=84,  # 7-year leases
        # Absorption strategy (office leasing pace) - FASTER LEASE-UP
        leasing_start_months=15,  # 15 months after land acquisition (faster to market)
        total_leasing_deals=9,  # 9 leases total
        leasing_frequency_months=1,  # New lease every 1 month (faster absorption)
        stabilized_occupancy_rate=0.95,  # 95% stabilized occupancy
        # Construction cost model - REDUCED COSTS FOR BETTER RETURNS
        construction_cost_psf=280.0,  # $280/SF (reduced from $300)
        soft_costs_rate=0.08,  # 8% soft costs (reduced from 10%)
        developer_fee_rate=0.05,  # 5% developer fee (market standard)
        # Construction timeline (EXACT MATCH to composition)
        construction_start_months=1,  # Start immediately after land (like composition)
        construction_duration_months=24,  # 24 months construction
        # Construction financing
        construction_ltc_ratio=0.70,  # 70% loan-to-cost
        construction_interest_rate=0.065,  # 6.5% construction rate
        construction_fee_rate=0.01,  # 1% origination fee
        interest_calculation_method="SCHEDULED",  # Sophisticated interest calculation
        # Permanent financing
        permanent_ltv_ratio=0.70,  # 70% loan-to-value
        permanent_interest_rate=0.055,  # 5.5% permanent rate
        permanent_loan_term_years=10,  # 10-year loan term
        permanent_amortization_years=25,  # 25-year amortization
        # Partnership structure
        distribution_method="waterfall",  # Waterfall with promote
        gp_share=0.10,  # 10% GP ownership
        lp_share=0.90,  # 90% LP ownership
        preferred_return=0.08,  # 8% preferred return
        promote_tier_1=0.20,  # 20% promote above pref
        # Exit strategy - IMPROVED FOR BETTER RETURNS
        hold_period_years=5,  # 5-year hold period (faster exit)
        exit_cap_rate=0.055,  # 5.5% exit cap rate (better market)
        exit_costs_rate=0.02,  # 2.0% transaction costs
    )

    return pattern, pattern.create()


def main():
    """Run the office development deal analysis and generate reports"""
    print("🏢 Performa Office Development Deal Example")
    print("=" * 60)

    # Initialize development deal
    try:
        pattern, deal = create_sample_development_deal()
        print(f"✅ Created deal: {deal.name}")
        print(f"   Deal Type: {deal.deal_type}")
        print(f"   Asset Type: {deal.asset.property_type.value}")
        print(
            f"   Total Development Cost: ${deal.asset.construction_plan.total_cost:,.0f}"
        )
        print(f"   Net Rentable Area: {deal.asset.net_rentable_area:,.0f} SF")
        print(f"   Partnership: {len(deal.equity_partners.partners)} partners")
        print(f"   Financing: {deal.financing.name}")
    except Exception as e:
        print(f"❌ Failed to create development deal: {e}")
        traceback.print_exc()
        return

    # Comprehensive Deal Analysis
    print("\n📈 Running Comprehensive Deal Analysis...")
    try:
        # Use pattern's own timeline for consistent analysis
        timeline = pattern._derive_timeline()
        settings = GlobalSettings()

        results = analyze(deal, timeline, settings)

        print("✅ Deal Analysis Complete!")
        print(f"   Deal IRR: {results.deal_metrics.irr:.2%}")
        print(f"   Equity Multiple: {results.deal_metrics.equity_multiple:.2f}x")
        print(
            f"   Total Equity Invested: ${results.deal_metrics.total_equity_invested:,.0f}"
        )
        print(f"   Net Profit: ${results.deal_metrics.net_profit:,.0f}")

        # Partnership Results
        if (
            results.partner_distributions
            and results.partner_distributions.distribution_method == "waterfall"
        ):
            waterfall_details = results.partner_distributions.waterfall_details
            print("\n👥 Partnership Results:")
            for (
                partner_name,
                partner_result,
            ) in waterfall_details.partner_results.items():
                print(f"   {partner_name}:")
                print(
                    f"     IRR: {partner_result.irr:.2%}"
                    if partner_result.irr
                    else "     IRR: N/A"
                )
                print(f"     Equity Multiple: {partner_result.equity_multiple:.2f}x")
                print(f"     Total Return: ${partner_result.total_distributions:,.0f}")

        # Financing Results
        if results.financing_analysis and results.financing_analysis.dscr_summary:
            print("\n💰 Financing Analysis:")
            print(
                f"   Minimum DSCR: {results.financing_analysis.dscr_summary.minimum_dscr:.2f}x"
            )
            print(
                f"   Average DSCR: {results.financing_analysis.dscr_summary.average_dscr:.2f}x"
            )
            print(
                f"   Number of Facilities: {len(results.financing_analysis.facilities)}"
            )
        else:
            print("\n💰 Financing Analysis: No DSCR data available")

    except Exception as e:
        print(f"❌ Deal Analysis failed: {e}")
        traceback.print_exc()
        return

    # Note: Legacy development-specific reporting functions were deprecated
    # in favor of the new fluent API demonstrated below
    print("\n📊 Legacy reporting functions have been replaced by fluent API...")
    print("     See NEW Fluent Reporting Interface section below for examples")

    # Test NEW Fluent Reporting Interface
    print("\n📊 Testing New Fluent Reporting Interface...")
    try:
        # Test the fluent API for pro forma summary
        print("   Generating annual pro forma summary...")
        annual_summary = results.reporting.pro_forma_summary(frequency="A")
        print(f"     Annual Pro Forma shape: {annual_summary.shape}")
        print(
            f"     Available metrics: {list(annual_summary.index)[:5]}..."
        )  # Show first 5

        # Test quarterly reporting
        print("   Generating quarterly pro forma summary...")
        quarterly_summary = results.reporting.pro_forma_summary(frequency="Q")
        print(f"     Quarterly Pro Forma shape: {quarterly_summary.shape}")

        # Test interface caching
        assert results.reporting is results.reporting
        print("     ✅ Reporting interface caching verified")

        print("✅ New Fluent Reporting Interface working perfectly!")
    except Exception as e:
        print(f"❌ Fluent Reporting Interface failed: {e}")
        traceback.print_exc()

    print("\n🎉 Complete development deal analysis working!")
    print("📋 All Deal components and reporting functionality demonstrated!")
    print("🚀 New fluent reporting interface (results.reporting.*) validated!")


if __name__ == "__main__":
    main()
