#!/usr/bin/env python3
# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Development Deal Modeling: Composition vs Convention

This example demonstrates two approaches to modeling the same office development deal:

1. **COMPOSITION APPROACH** (Manual Assembly):
   - Manually create each component (asset, financing, partnership, etc.)
   - Full control over every detail
   - Requires deep knowledge of Performa architecture
   - ~200+ lines of configuration code
   - Current approach used in production

2. **CONVENTION APPROACH** (Pattern Interface):
   - High-level parameterized interface
   - Industry-standard defaults and validation
   - Type-safe parameter flattening
   - ~20 lines of configuration
   - Future approach for rapid deal modeling

Both approaches model the identical development project:
- Metro Office Tower: $16.7M development cost
- Office building: 45,000 SF rentable, $65/SF rent
- Construction-to-permanent financing at 65% LTC/LTV
- GP/LP partnership with 8% preferred return + 20% promote
- 5-year hold period with 6.5% exit cap rate (realistic market)

The example demonstrates the evolution from manual composition to
pattern-driven conventions while maintaining full analytical capability.

## Key Architectural Benefits of Pattern Approach

**Developer Experience**:
- Reduced configuration complexity (200+ lines → 20 lines)
- Type safety with Pydantic validation
- Industry-standard parameter names and defaults
- Built-in business rule validation

**Maintainability**:
- Centralized deal archetype logic
- Consistent parameter handling across deals
- Version-controlled deal conventions
- Easier testing and validation

**Scalability**:
- Rapid deal scenario generation
- Standardized institutional deal structures
- Template-driven deal creation
- Integration with external systems

Note: The DevelopmentPattern interface is established and the underlying
construction financing mechanics have been updated with
loan sizing and draw-based interest calculations. The example demonstrates
both working approaches with unified construction financing architecture.
"""

import traceback
from datetime import date

import pandas as pd

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
    GlobalSettings,
    ProgramUseEnum,
    PropertyAttributeKey,
    SCurveDrawSchedule,
    Timeline,
    UniformDrawSchedule,
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
from performa.debt.constructs import create_construction_to_permanent_plan
from performa.development import DevelopmentProject
from performa.patterns import OfficeDevelopmentPattern
from performa.valuation import DirectCapValuation


def create_deal_via_composition():
    """
    COMPOSITION APPROACH: Manual assembly of all deal components.

    This demonstrates the current production approach requiring
    detailed knowledge of Performa architecture and explicit
    configuration of every component.

    Advantages:
    - Full control over every parameter
    - Access to advanced features
    - No abstraction limitations

    Disadvantages:
    - High complexity and learning curve
    - Verbose configuration (200+ lines)
    - Prone to configuration errors
    - Requires deep Performa expertise
    """
    print("🔧 COMPOSITION APPROACH: Manual Component Assembly")
    print("-" * 60)

    # === STEP 1: PROJECT TIMELINE ===
    start_date = date(2024, 1, 1)
    timeline = Timeline(start_date=start_date, duration_months=60)  # 5 year timeline

    # === STEP 2: CAPITAL EXPENDITURE PLAN ===
    capital_items = [
        # REMOVED: Land Acquisition CapitalItem (double-counting with AcquisitionTerms)
        CapitalItem(
            name="Construction - Core & Shell",
            work_type="construction",
            value=10_400_000,  # Core construction costs
            draw_schedule=SCurveDrawSchedule(
                sigma=1.0
            ),  # Realistic S-curve construction draws
            timeline=timeline,
        ),
        CapitalItem(
            name="Professional Fees",
            work_type="soft_costs",
            value=624_000,  # Professional fees
            draw_schedule=SCurveDrawSchedule(
                sigma=1.2
            ),  # Slightly more gradual for soft costs
            timeline=timeline,
        ),
        CapitalItem(
            name="Developer Fee",
            work_type="developer",
            value=630_573,  # Developer fee
            draw_schedule=UniformDrawSchedule(),  # Flat monthly payments (industry standard)
            timeline=timeline,
        ),
    ]

    capital_plan = CapitalPlan(
        name="Office Development Plan", capital_items=capital_items
    )

    # === STEP 3: VACANT SPACE INVENTORY ===
    vacant_suites = [
        OfficeVacantSuite(
            suite="Floor 1",
            floor="1",
            area=15000.0,
            use_type=ProgramUseEnum.OFFICE,
            is_divisible=True,
            subdivision_average_lease_area=5000.0,
            subdivision_minimum_lease_area=2500.0,
            available_date=date(2025, 10, 1),  # Available at month 21
        ),
        OfficeVacantSuite(
            suite="Floor 2",
            floor="2",
            area=15000.0,
            use_type=ProgramUseEnum.OFFICE,
            is_divisible=True,
            subdivision_average_lease_area=5000.0,
            subdivision_minimum_lease_area=2500.0,
            available_date=date(2025, 10, 1),  # Available at month 21
        ),
        OfficeVacantSuite(
            suite="Floor 3",
            floor="3",
            area=15000.0,
            use_type=ProgramUseEnum.OFFICE,
            is_divisible=True,
            subdivision_average_lease_area=5000.0,
            subdivision_minimum_lease_area=2500.0,
            available_date=date(2025, 10, 1),  # Available at month 21
        ),
    ]

    # === STEP 4: ABSORPTION PLAN ===
    absorption_plan = OfficeAbsorptionPlan.with_typical_assumptions(
        name="Metro Tower Lease-Up Plan",
        space_filter=SpaceFilter(
            floors=["1", "2", "3"], use_types=[ProgramUseEnum.OFFICE]
        ),
        start_date_anchor=date(2025, 4, 1),  # 15 months from Jan 2024
        pace=EqualSpreadPace(
            total_deals=9,
            frequency_months=1,  # Faster leasing (every 1 month)
        ),
        leasing_assumptions=DirectLeaseTerms(
            base_rent_value=65.0
            / 12,  # Convert annual $65/SF to monthly (matches pattern logic)
            base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
            term_months=84,
            upon_expiration=UponExpirationEnum.MARKET,
        ),
    )

    # === STEP 5: DEVELOPMENT BLUEPRINT ===
    office_blueprint = OfficeDevelopmentBlueprint(
        name="Metro Office Tower",
        vacant_inventory=vacant_suites,
        absorption_plan=absorption_plan,
    )

    # === STEP 6: DEVELOPMENT PROJECT ===
    project = DevelopmentProject(
        name="Metro Office Tower Development",
        property_type=AssetTypeEnum.OFFICE,
        gross_area=50000.0,
        net_rentable_area=45000.0,
        construction_plan=capital_plan,
        blueprints=[office_blueprint],
    )

    # === STEP 7: ACQUISITION TERMS ===
    acquisition = AcquisitionTerms(
        name="Land Acquisition",
        timeline=Timeline(start_date=start_date, duration_months=1),
        value=5_000_000,
        acquisition_date=start_date,
        closing_costs_rate=0.025,
    )

    # === STEP 8: CONSTRUCTION-TO-PERMANENT FINANCING ===
    # Use the construct for proper debt timing (replaces manual facility creation)
    financing_plan = create_construction_to_permanent_plan(
        construction_terms={
            "name": "Construction Facility",
            "ltc_ratio": 0.65,  # 65% LTC (matches pattern)
            "interest_rate": 0.060,  # 6.0% construction rate
            "loan_term_months": 20,  # 20 months (match Month 21 space availability)
        },
        permanent_terms={
            "name": "Permanent Facility",
            "ltv_ratio": 0.65,  # 65% LTV - auto-sizing based on completed property value
            "sizing_method": "auto",  # Enable sophisticated auto-sizing
            "interest_rate": 0.050,  # 5.0% permanent rate
            "loan_term_years": 10,  # 10 years (use years form for construct)
            "amortization_years": 30,  # 30 years amortization (use years form)
            "dscr_hurdle": 1.25,
            "origination_fee_rate": 0.005,
        },
        project_value=16_654_573,  # Total project value including land (match pattern)
    )

    # === STEP 10: PARTNERSHIP STRUCTURE ===
    gp_partner = Partner(
        name="Development GP",
        kind="GP",
        share=0.10,
    )

    lp_partner = Partner(
        name="Institutional LP",
        kind="LP",
        share=0.90,
    )

    partnership = PartnershipStructure(
        partners=[gp_partner, lp_partner],
        distribution_method="waterfall",
        promote=CarryPromote(),
    )

    # === STEP 11: EXIT STRATEGY ===
    exit_valuation = DirectCapValuation(
        name="Stabilized Disposition",
        cap_rate=0.065,  # 6.5% exit cap rate (realistic office market - matches pattern)
        transaction_costs_rate=0.025,  # 2.5% transaction costs (realistic - matches pattern)
        hold_period_months=60,  # 5-year hold period
        noi_basis_kind="LTM",  # Use trailing 12 months (realistic)
    )

    # === STEP 12: ASSEMBLE COMPLETE DEAL ===
    deal = Deal(
        name="Metro Office Tower Development Deal",
        description="Manual composition - complete control",
        asset=project,
        acquisition=acquisition,
        financing=financing_plan,
        exit_valuation=exit_valuation,
        equity_partners=partnership,
    )

    print(f"Deal created: {deal.name}")
    print(f"   Total Development Cost: ${deal.asset.construction_plan.total_cost:,.0f}")
    print(f"   Net Rentable Area: {deal.asset.net_rentable_area:,.0f} SF")
    print(f"   Components assembled: 12 major steps, ~200 lines of code")
    print(f"   Includes: Draw-based construction financing")

    return deal


def demonstrate_pattern_interface():
    """
    CONVENTION APPROACH: High-level Pattern interface.

    This demonstrates the future vision for rapid deal modeling
    using parameterized patterns with industry-standard defaults
    and built-in validation.

    Advantages:
    - Minimal configuration (~20 lines)
    - Type safety and validation
    - Industry-standard defaults
    - Rapid deal scenario generation

    Current Status:
    - Interface complete and working
    - Parameter validation implemented
    - Timeline integration ready
    - Full create() implementation deferred
    """
    print("\n🎯 CONVENTION APPROACH: Pattern Interface")
    print("-" * 60)

    try:
        # === SINGLE STEP: OFFICE DEVELOPMENT PATTERN CONFIGURATION ===
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
            # Leasing assumptions ($/SF metrics) - OPTIMIZED FOR DEVELOPMENT RETURNS
            target_rent_psf=65.0,  # $65/SF/year base rent (premium market for development)
            average_lease_size_sf=5_000,  # 5,000 SF average lease
            minimum_lease_size_sf=2_500,  # 2,500 SF minimum lease
            lease_term_months=84,  # 7-year leases
            # Absorption strategy (office leasing pace) - FASTER LEASE-UP
            leasing_start_months=15,  # 15 months after land acquisition (faster to market)
            total_leasing_deals=9,  # 9 leases total
            leasing_frequency_months=1,  # New lease every 1 month (faster absorption)
            stabilized_occupancy_rate=0.95,  # 95% stabilized occupancy
            # Construction cost model
            construction_cost_psf=208.0,  # $208/SF (exact parity with composition)
            soft_costs_rate=0.06,  # 6% soft costs
            developer_fee_rate=0.0572,  # 5.72% developer fee
            # Construction timeline configuration
            construction_start_months=1,  # Start immediately after land acquisition
            construction_duration_months=20,  # 20 months construction (match composition Month 21)
            # Construction financing parameters
            construction_ltc_ratio=0.65,  # 65% loan-to-cost
            construction_interest_rate=0.060,  # 6.0% construction rate
            construction_fee_rate=0.01,  # 1% origination fee
            interest_calculation_method="SCHEDULED",  # Sophisticated interest calculation
            # Permanent financing parameters
            permanent_ltv_ratio=0.65,  # 65% loan-to-value
            permanent_interest_rate=0.050,  # 5.0% permanent rate
            permanent_loan_term_years=10,  # 10-year loan term
            permanent_amortization_years=30,  # 30-year amortization
            # Partnership structure
            distribution_method="waterfall",  # Waterfall with promote
            gp_share=0.10,  # 10% GP ownership
            lp_share=0.90,  # 90% LP ownership
            preferred_return=0.08,  # 8% preferred return
            promote_tier_1=0.20,  # 20% promote above pref
            # Exit strategy - REALISTIC MARKET ASSUMPTIONS
            hold_period_years=5,  # 5-year hold period (standard)
            exit_cap_rate=0.065,  # 6.5% exit cap rate (realistic office market)
            exit_costs_rate=0.025,  # 2.5% transaction costs (realistic)
        )

        print(f"✅ Pattern created: {pattern.project_name}")
        print(f"   Total Project Cost: ${pattern.total_project_cost:,.0f}")
        print(
            f"   Building Size: {pattern.net_rentable_area:,.0f} SF across {pattern.floors} floors"
        )
        print(f"   Configuration: Single step, office-specific parameters, type-safe")

        # Demonstrate timeline integration
        timeline = pattern.get_timeline()
        print(
            f"   Timeline: {timeline.start_date} for {timeline.duration_months} months"
        )

        # Demonstrate validation
        print(
            f"   Validation: GP({pattern.gp_share:.0%}) + LP({pattern.lp_share:.0%}) = 100% ✓"
        )

        # Test the new implementation
        print("\n📋 Implementation Status:")
        try:
            deal = pattern.create()
            print(f"   Interface: ✅ Complete")
            print(f"   Validation: ✅ Working")
            print(f"   Timeline: ✅ Integrated")
            print(f"   Implementation: ✅ Fully Working")
            print(f"   Deal Creation: ✅ {deal.name}")
            print(f"   Construction Finance: ✅ Includes draw-based calculations")

        except Exception as e:
            print(f"   ❌ Implementation failed: {e}")
            print(f"   Error details: {str(e)[:100]}...")
            return pattern, None

        return pattern, deal

    except Exception as e:
        print(f"❌ Pattern creation failed: {e}")
        traceback.print_exc()
        return None


def analyze_composition_deal(deal):
    """Analyze the manually composed deal to show it works."""
    print("\n📊 ANALYZING COMPOSITION DEAL")
    print("-" * 60)

    try:
        # Use same timeline as pattern for fair comparison
        timeline = Timeline(
            start_date=date(2024, 1, 1), duration_months=66
        )  # EXACT script match
        settings = GlobalSettings()

        results = analyze(deal, timeline, settings)

        print("✅ Analysis Complete!")

        irr = results.deal_metrics.get("levered_irr")
        em = results.deal_metrics.get("equity_multiple")

        if irr is not None:
            print(f"   Deal IRR: {irr:.2%}")
        else:
            print("   Deal IRR: None (negative cash flows)")

        if em is not None:
            print(f"   Equity Multiple: {em:.2f}x")
        else:
            print("   Equity Multiple: None")

        if results.deal_metrics.get("total_investment"):
            print(
                f"   Total Equity Invested: ${results.deal_metrics.get('total_investment'):,.0f}"
            )

        if results.deal_metrics.get("net_profit"):
            print(f"   Net Profit: ${results.deal_metrics.get('net_profit'):,.0f}")

        # Partnership results
        if (
            results.partner_distributions
            and results.partner_distributions.distribution_method == "waterfall"
        ):
            waterfall_details = results.partner_distributions.waterfall_details
            print("\n   Partnership Results:")
            for (
                partner_name,
                partner_result,
            ) in waterfall_details.partner_results.items():
                irr_str = (
                    f"{partner_result.get('irr'):.2%}"
                    if partner_result.get("irr")
                    else "N/A"
                )
                print(
                    f"     {partner_name}: {irr_str} IRR, {partner_result.get('equity_multiple'):.2f}x EM"
                )

        # Financing results
        if results.financing_analysis:
            print(
                f"\n   Financing: Min DSCR {results.financing_analysis.dscr_summary.minimum_dscr:.2f}x"
            )

        return results

    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        traceback.print_exc()
        return None


def main():
    """
    Demonstrate both approaches to development deal modeling.

    This example shows the evolution from manual composition to
    pattern-driven conventions, highlighting the benefits of each
    approach and the future vision for Performa deal modeling.
    """
    print("🏗️  DEVELOPMENT DEAL MODELING: COMPOSITION vs CONVENTION")
    print("=" * 80)
    print()
    print(
        "This example demonstrates two approaches to modeling the same development deal:"
    )
    print("1. Composition: Manual assembly of components (current production approach)")
    print("2. Convention: Pattern-driven interface (future rapid modeling approach)")
    print()

    # === APPROACH 1: COMPOSITION ===
    composition_deal = create_deal_via_composition()

    # === APPROACH 2: CONVENTION ===
    pattern_result = demonstrate_pattern_interface()

    # Handle the new return format (pattern, deal) or (None, None)
    if pattern_result and len(pattern_result) == 2:
        pattern, pattern_deal = pattern_result
    else:
        pattern, pattern_deal = pattern_result, None if pattern_result else None, None

    # === ANALYSIS COMPARISON ===
    if composition_deal and pattern_deal:
        # Both approaches working - compare them
        composition_results = analyze_composition_deal(composition_deal)

        # Analyze pattern deal too
        print("\n📊 ANALYZING PATTERN DEAL")
        print("-" * 60)

        try:
            # Use pattern's own timeline instead of arbitrary 120 months
            pattern_timeline = pattern._derive_timeline()
            settings = GlobalSettings()

            pattern_results = analyze(pattern_deal, pattern_timeline, settings)

            print("✅ Pattern Analysis Complete!")
            pattern_irr_str = (
                f"{pattern_results.deal_metrics.get('levered_irr'):.2%}"
                if pattern_results.deal_metrics.get("levered_irr")
                else "N/A"
            )
            print(f"   Deal IRR: {pattern_irr_str}")
            print(
                f"   Equity Multiple: {pattern_results.deal_metrics.get('equity_multiple'):.2f}x"
            )
            print(
                f"   Total Equity Invested: ${pattern_results.deal_metrics.get('total_investment'):,.0f}"
            )
            print(
                f"   Net Profit: ${pattern_results.deal_metrics.get('net_profit'):,.0f}"
            )

            # Compare results
            if composition_results:
                irr_diff = abs(
                    (composition_results.deal_metrics.get("levered_irr") or 0)
                    - (pattern_results.deal_metrics.get("levered_irr") or 0)
                )
                em_diff = abs(
                    composition_results.deal_metrics.get("equity_multiple")
                    - pattern_results.deal_metrics.get("equity_multiple")
                )
                equity_diff = abs(
                    composition_results.deal_metrics.get("total_investment")
                    - pattern_results.deal_metrics.get("total_investment")
                )

                print(f"\n   EQUIVALENCE CHECK:")
                print(
                    f"     IRR Difference: {irr_diff:.4%} ({'✅ EQUIVALENT' if irr_diff < 0.001 else '⚠️ DIFFERENT'})"
                )
                print(
                    f"     EM Difference: {em_diff:.4f}x ({'✅ EQUIVALENT' if em_diff < 0.01 else '⚠️ DIFFERENT'})"
                )
                print(
                    f"     Equity Difference: ${equity_diff:,.0f} ({'✅ EQUIVALENT' if equity_diff < 10000 else '⚠️ DIFFERENT'})"
                )

                # Add ledger comparison if not equivalent
                if irr_diff >= 0.001 or em_diff >= 0.01 or equity_diff >= 10000:
                    print(f"\n🔍 DETAILED LEDGER COMPARISON:")
                    print("=" * 60)

                    # Get ledgers
                    comp_queries = (
                        composition_results.asset_analysis.get_ledger_queries()
                    )
                    pattern_queries = (
                        pattern_results.asset_analysis.get_ledger_queries()
                    )

                    comp_ledger = comp_queries.ledger
                    pattern_ledger = pattern_queries.ledger

                    print(f"   Composition ledger: {len(comp_ledger)} records")
                    print(f"   Pattern ledger: {len(pattern_ledger)} records")

                    # Aggregate by category and subcategory
                    def aggregate_ledger(ledger_df):
                        # Convert categorical columns to string to avoid merge issues
                        df = ledger_df.copy()
                        for col in ["category", "subcategory"]:
                            if col in df.columns:
                                df[col] = df[col].astype(str)
                        return (
                            df.groupby(["category", "subcategory"], observed=False)[
                                "amount"
                            ]
                            .sum()
                            .reset_index()
                        )

                    comp_agg = aggregate_ledger(comp_ledger)
                    pattern_agg = aggregate_ledger(pattern_ledger)

                    # Merge and compare
                    comparison = pd.merge(
                        comp_agg,
                        pattern_agg,
                        on=["category", "subcategory"],
                        how="outer",
                        suffixes=("_comp", "_pattern"),
                    )

                    # Fill NaN values with 0 for numeric columns
                    comparison["amount_comp"] = comparison["amount_comp"].fillna(0)
                    comparison["amount_pattern"] = comparison["amount_pattern"].fillna(
                        0
                    )

                    comparison["difference"] = (
                        comparison["amount_pattern"] - comparison["amount_comp"]
                    )
                    comparison["abs_diff"] = comparison["difference"].abs()

                    # Show top differences
                    differences = (
                        comparison[comparison["abs_diff"] > 1000]
                        .sort_values("abs_diff", ascending=False)
                        .head(10)
                    )

                    if len(differences) > 0:
                        print(f"   TOP DIFFERENCES (> $1,000):")
                        for _, row in differences.iterrows():
                            print(f"     {row['category']} -> {row['subcategory']}:")
                            print(f"       Composition: ${row['amount_comp']:,.2f}")
                            print(f"       Pattern: ${row['amount_pattern']:,.2f}")
                            print(f"       Difference: ${row['difference']:,.2f}")
                    else:
                        print(f"   ✅ No significant ledger differences found!")

        except Exception as e:
            print(f"❌ Pattern Analysis failed: {e}")
            pattern_results = None

        if composition_results:
            print("\n🎯 APPROACH COMPARISON")
            print("-" * 60)
            print("Composition Approach:")
            print("  ✅ Full implementation working")
            print("  ✅ Complete analytical capability")
            print("  ⚠️  High complexity (200+ lines)")
            print("  ⚠️  Requires deep Performa expertise")
            print()
            print("Convention Approach:")
            print("  ✅ Interface complete and working")
            print("  ✅ Minimal configuration (office-specific parameters)")
            print("  ✅ Industry-standard defaults")
            print("  ✅ Type safety and validation")
            print("  ✅ Full implementation working")
            print()
            print("Architectural Success:")
            if pattern_results:
                print("  🎯 Both approaches produce results")
                print("  🎯 Pattern approach enables rapid office development modeling")
                print("  🎯 Construction financing works in both approaches")
                print(
                    "  🎯 Asset-specific parameters provide natural developer experience"
                )
            else:
                print("  🎯 Pattern approach interface established")
                print("  🎯 Foundation for rapid development modeling")

    elif composition_deal:
        # Only composition working
        composition_results = analyze_composition_deal(composition_deal)
        print("\n🎯 CURRENT STATUS")
        print("-" * 60)
        print("Composition Approach: ✅ Working")
        print("Pattern Approach: 🚧 Interface ready, implementation in progress")

    else:
        print("\n❌ Neither approach produced a working deal for analysis")

    # === GOLDEN VALUE ASSERTIONS ===
    # Add assertions if both approaches worked
    if (
        composition_deal
        and pattern_deal
        and "composition_results" in locals()
        and "pattern_results" in locals()
    ):
        if composition_results and pattern_results:
            # Expected values for office development comparison with realistic market assumptions
            # Both approaches produce identical results with realistic 6.5% exit cap rate and 2.5% transaction costs
            expected_irr = (
                0.16132702259868625  # 16.13% - exact parity for both approaches
            )
            expected_em = 1.89839210322396  # 1.898x - exact parity for both approaches
            expected_equity_comp = (
                6920011.156925966  # Composition equity - exact parity
            )
            expected_equity_pattern = 6920011.156925966  # Pattern equity - exact parity

            # Assert composition results (100% exact parity - no tolerances needed)
            comp_irr = composition_results.deal_metrics.get("levered_irr") or 0
            comp_em = composition_results.deal_metrics.get("equity_multiple")
            comp_equity = composition_results.deal_metrics.get("total_investment")

            # Validate composition results match expected values (100% mathematical parity within financial precision)
            assert (
                abs(comp_irr - expected_irr) < 1e-6
            ), f"Composition IRR {comp_irr} != expected {expected_irr}"
            assert (
                abs(comp_em - expected_em) < 1e-6
            ), f"Composition EM {comp_em} != expected {expected_em}"
            assert (
                abs(comp_equity - expected_equity_comp) < 1.0
            ), f"Composition Equity ${comp_equity} != expected ${expected_equity_comp}"

            # Assert pattern results match composition exactly (100% mathematical parity)
            pattern_irr = pattern_results.deal_metrics.get("levered_irr") or 0
            pattern_em = pattern_results.deal_metrics.get("equity_multiple")
            pattern_equity = pattern_results.deal_metrics.get("total_investment")

            # Pattern should match composition within financial calculation precision
            assert (
                abs(pattern_irr - comp_irr) < 1e-6
            ), f"Pattern IRR {pattern_irr} != composition {comp_irr}"
            assert (
                abs(pattern_em - comp_em) < 1e-6
            ), f"Pattern EM {pattern_em} != composition {comp_em}"
            assert (
                abs(pattern_equity - comp_equity) < 1.0
            ), f"Pattern Equity ${pattern_equity} != composition ${comp_equity}"

            print("\n✅ Expected value assertions passed - metrics remain stable")

    print("\n🎉 DEVELOPMENT PATTERN EXAMPLE COMPLETE!")
    print("📋 Interface established, ready for full implementation")
    print("🚀 Foundation for rapid institutional deal modeling")


if __name__ == "__main__":
    main()
