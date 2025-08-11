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
- Metro Office Tower: $23.5M development cost
- Office building: 45,000 SF rentable, $35/SF rent
- Construction-to-permanent financing at 70% LTC/LTV
- GP/LP partnership with 8% preferred return + 20% promote
- 7-year hold period with 6.5% exit cap rate

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

Note: The DevelopmentPattern interface is currently established but
the full implementation is deferred pending resolution of construction
loan draw mechanics and sources & uses modeling. The example shows
both the current state and the future vision.
"""

import traceback
from datetime import date

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
from performa.patterns import DevelopmentPattern
from performa.valuation import ReversionValuation


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
    timeline = Timeline(start_date=start_date, duration_months=30)

    # === STEP 2: CAPITAL EXPENDITURE PLAN ===
    capital_items = [
        CapitalItem(
            name="Land Acquisition",
            work_type="land",
            value=5_000_000,
            draw_schedule=FirstOnlyDrawSchedule(),
            timeline=timeline,
        ),
        CapitalItem(
            name="Construction - Core & Shell",
            work_type="construction",
            value=15_000_000,
            draw_schedule=FirstOnlyDrawSchedule(),
            timeline=timeline,
        ),
        CapitalItem(
            name="Professional Fees",
            work_type="soft_costs",
            value=1_500_000,
            draw_schedule=FirstOnlyDrawSchedule(),
            timeline=timeline,
        ),
        CapitalItem(
            name="Developer Fee",
            work_type="developer",
            value=2_000_000,
            draw_schedule=FirstOnlyDrawSchedule(),
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
        ),
        OfficeVacantSuite(
            suite="Floor 2",
            floor="2",
            area=15000.0,
            use_type=ProgramUseEnum.OFFICE,
            is_divisible=True,
            subdivision_average_lease_area=5000.0,
            subdivision_minimum_lease_area=2500.0,
        ),
        OfficeVacantSuite(
            suite="Floor 3",
            floor="3",
            area=15000.0,
            use_type=ProgramUseEnum.OFFICE,
            is_divisible=True,
            subdivision_average_lease_area=5000.0,
            subdivision_minimum_lease_area=2500.0,
        ),
    ]

    # === STEP 4: ABSORPTION PLAN ===
    absorption_plan = OfficeAbsorptionPlan.with_typical_assumptions(
        name="Metro Tower Lease-Up Plan",
        space_filter=SpaceFilter(
            floors=["1", "2", "3"], use_types=[ProgramUseEnum.OFFICE]
        ),
        start_date_anchor=date(2025, 6, 1),
        pace=EqualSpreadPace(
            total_deals=9,
            frequency_months=2,
        ),
        leasing_assumptions=DirectLeaseTerms(
            base_rent_value=35.0,
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

    # === STEP 8: CONSTRUCTION FINANCING ===
    construction_loan = ConstructionFacility(
        name="Construction Facility",
        tranches=[
            DebtTranche(
                name="Senior Construction",
                interest_rate=InterestRate(details=FixedRate(rate=0.065)),
                fee_rate=0.01,
                ltc_threshold=0.70,
            )
        ],
        fund_interest_from_reserve=True,
        interest_reserve_rate=0.15,
    )

    # === STEP 9: PERMANENT FINANCING ===
    permanent_loan = PermanentFacility(
        name="Permanent Facility",
        loan_amount=18_000_000,
        interest_rate=InterestRate(details=FixedRate(rate=0.055)),
        loan_term_years=10,
        amortization_years=25,
        ltv_ratio=0.70,
        dscr_hurdle=1.25,
        origination_fee_rate=0.005,
    )

    financing_plan = FinancingPlan(
        name="Construction-to-Permanent Financing",
        facilities=[construction_loan, permanent_loan],
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
    exit_valuation = ReversionValuation(
        name="Stabilized Disposition",
        cap_rate=0.065,
        transaction_costs_rate=0.025,
        hold_period_months=84,
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

    print(f"✅ Deal created: {deal.name}")
    print(f"   Total Development Cost: ${deal.asset.construction_plan.total_cost:,.0f}")
    print(f"   Net Rentable Area: {deal.asset.net_rentable_area:,.0f} SF")
    print(f"   Components assembled: 12 major steps, ~200 lines of code")

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
        # === SINGLE STEP: PATTERN CONFIGURATION ===
        pattern = DevelopmentPattern(
            # Core project parameters
            project_name="Metro Office Tower Development",
            acquisition_date=date(2024, 1, 1),
            land_cost=5_000_000,
            land_closing_costs_rate=0.025,
            # Construction parameters
            construction_budget=18_500_000,  # Construction + fees
            construction_start_months=6,
            construction_duration_months=24,
            # Building specifications (simplified for office)
            total_units=45,  # Representing 45K SF as "units" for pattern compatibility
            avg_unit_sf=1000,  # 1K SF average lease size
            target_rent=35.0,  # $35/SF annual rent
            # Lease-up assumptions
            leasing_start_months=18,
            absorption_pace_units_per_month=5.0,  # 5K SF per month absorption
            stabilized_occupancy_rate=0.95,
            # Construction financing
            construction_ltc_ratio=0.70,
            construction_interest_rate=0.065,
            construction_fee_rate=0.01,
            # Permanent financing
            permanent_ltv_ratio=0.70,
            permanent_interest_rate=0.055,
            permanent_loan_term_years=10,
            permanent_amortization_years=25,
            # Partnership structure
            distribution_method="waterfall",
            gp_share=0.10,
            lp_share=0.90,
            preferred_return=0.08,
            # Exit strategy
            hold_period_years=7,
            exit_cap_rate=0.065,
            exit_costs_rate=0.025,
        )

        print(f"✅ Pattern created: {pattern.project_name}")
        print(
            f"   Total Project Cost: ${pattern.land_cost + pattern.construction_budget:,.0f}"
        )
        print(f"   Configuration: Single step, ~20 parameters, type-safe")

        # Demonstrate timeline integration
        timeline = pattern.get_timeline()
        print(
            f"   Timeline: {timeline.start_date} for {timeline.duration_months} months"
        )

        # Demonstrate validation
        print(
            f"   Validation: GP({pattern.gp_share:.0%}) + LP({pattern.lp_share:.0%}) = 100% ✓"
        )

        # Show current limitation
        print("\n📋 Current Implementation Status:")
        try:
            pattern.create()
        except NotImplementedError as e:
            print(f"   Interface: ✅ Complete")
            print(f"   Validation: ✅ Working")
            print(f"   Timeline: ✅ Integrated")
            print(f"   Implementation: 🚧 Deferred (complex construction modeling)")
            print(f"   Guidance: {str(e)[:80]}...")

        return pattern

    except Exception as e:
        print(f"❌ Pattern creation failed: {e}")
        traceback.print_exc()
        return None


def analyze_composition_deal(deal):
    """Analyze the manually composed deal to show it works."""
    print("\n📊 ANALYZING COMPOSITION DEAL")
    print("-" * 60)

    try:
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=120)
        settings = GlobalSettings()

        results = analyze(deal, timeline, settings)

        print("✅ Analysis Complete!")
        print(f"   Deal IRR: {results.deal_metrics.irr:.2%}")
        print(f"   Equity Multiple: {results.deal_metrics.equity_multiple:.2f}x")
        print(
            f"   Total Equity Invested: ${results.deal_metrics.total_equity_invested:,.0f}"
        )
        print(f"   Net Profit: ${results.deal_metrics.net_profit:,.0f}")

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
                irr_str = f"{partner_result.irr:.2%}" if partner_result.irr else "N/A"
                print(
                    f"     {partner_name}: {irr_str} IRR, {partner_result.equity_multiple:.2f}x EM"
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
    pattern = demonstrate_pattern_interface()

    # === ANALYSIS COMPARISON ===
    if composition_deal:
        composition_results = analyze_composition_deal(composition_deal)

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
            print("  ✅ Interface complete and type-safe")
            print("  ✅ Minimal configuration (20 parameters)")
            print("  ✅ Industry-standard defaults")
            print("  🚧 Implementation deferred (construction modeling complexity)")
            print()
            print("Future Vision:")
            print("  🎯 Both approaches will produce identical results")
            print("  🎯 Pattern approach will enable rapid deal scenario generation")
            print("  🎯 Composition approach will remain for advanced customization")

    print("\n🎉 DEVELOPMENT PATTERN EXAMPLE COMPLETE!")
    print("📋 Interface established, ready for full implementation")
    print("🚀 Foundation for rapid institutional deal modeling")


if __name__ == "__main__":
    main()
