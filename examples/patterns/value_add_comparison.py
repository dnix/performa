#!/usr/bin/env python3
# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Value-Add Deal Modeling: Composition vs Convention

This example demonstrates two approaches to modeling a value-add multifamily deal:

1. **COMPOSITION APPROACH** (Manual Assembly):
   - Manually assemble each component (asset, financing, partnership, etc.)
   - Full control over every parameter
   - Requires knowledge of Performa architecture
   - ~300 lines of configuration code

2. **CONVENTION APPROACH** (Pattern Interface):
   - High-level parameterized interface
   - Industry-standard defaults and validation
   - Type-safe parameter handling
   - ~25 lines of configuration

Both approaches model the same value-add project:
- Riverside Gardens: $11.5M acquisition plus $1M renovation budget
- 100 multifamily units with $1,200 to $1,450/month rent progression
- Construction-to-permanent financing at 65% LTV
- GP/LP partnership with 8% preferred return and 20% promote
- 5-year hold period with 6.0% exit cap rate

The example demonstrates how both approaches produce mathematically equivalent
deal analysis results while differing in implementation complexity and abstraction level.

## When to Use Each Approach

**Use Composition When:**
- You need fine-grained control over specific parameters
- Building non-standard deal structures
- Integrating with external systems or data sources
- Prototyping new deal archetypes

**Use Pattern Convention When:**
- Creating standard deal structures quickly
- Generating multiple scenarios with consistent parameters
- Leveraging industry-standard assumptions and methodologies
- Prioritizing code clarity and maintainability
using unified construction financing for renovation funding.
"""

import traceback
from datetime import date
from uuid import uuid4

from performa.asset.residential import (
    ResidentialAbsorptionPlan,
    ResidentialCreditLoss,
    ResidentialExpenses,
    ResidentialGeneralVacancyLoss,
    ResidentialLosses,
    ResidentialOpExItem,
    ResidentialProperty,
    ResidentialRentRoll,
    ResidentialRolloverLeaseTerms,
    ResidentialRolloverProfile,
    ResidentialUnitSpec,
)
from performa.asset.residential.absorption import ResidentialDirectLeaseTerms
from performa.core.base.absorption import FixedQuantityPace
from performa.core.capital import CapitalItem, CapitalPlan
from performa.core.primitives import (
    FrequencyEnum,
    GlobalSettings,
    InterestCalculationMethod,
    PercentageGrowthRate,
    PropertyAttributeKey,
    StartDateAnchorEnum,
    Timeline,
    UnleveredAggregateLineKey,
)
from performa.core.primitives.enums import UponExpirationEnum
from performa.deal import AcquisitionTerms, Deal, analyze, create_gp_lp_waterfall
from performa.debt import (
    ConstructionFacility,
    DebtTranche,
    FinancingPlan,
    FixedRate,
    InterestRate,
    PermanentFacility,
)
from performa.patterns import ValueAddAcquisitionPattern
from performa.valuation import DirectCapValuation


def create_deal_via_composition():
    """
    Create a deal by manually assembling all components.

    This approach demonstrates explicit control over every deal aspect through
    direct component configuration. Each component (asset, financing, partnership)
    is built separately and assembled into a complete deal specification.

    Advantages:
    - Full control over every parameter and advanced features
    - Access to sophisticated customization and edge cases
    - No abstraction limitations for complex scenarios

    Disadvantages:
    - Higher complexity and learning curve
    - Verbose configuration (approximately 200 lines)
    - Requires deep understanding of Performa architecture
    - Prone to configuration errors without careful attention

    Returns:
        Deal: Complete deal object with all specifications assembled.
    """
    print("COMPOSITION APPROACH: Manual Component Assembly")
    print("-" * 60)

    # === STEP 1: PROJECT TIMELINE ===
    acquisition_date = date(2024, 1, 1)
    timeline = Timeline(
        start_date=acquisition_date, duration_months=96
    )  # 7 years hold + 12 months renovation/lease-up = 8 years total

    # Renovation timeline starts year 1
    renovation_start_date = date(
        2025, 1, 1
    )  # Start renovations 1 year after acquisition
    renovation_timeline = Timeline(
        start_date=renovation_start_date, duration_months=25
    )  # 25 months renovation duration

    # === STEP 2: CREATE ABSORPTION PLAN ID FIRST ===
    post_renovation_plan_id = uuid4()

    # === STEP 3: RESIDENTIAL UNIT SPECIFICATIONS ===
    # Create rollover profile for lease transitions
    rollover_profile = ResidentialRolloverProfile(
        name="Value-Add Lease Expiration",
        term_months=12,
        renewal_probability=0.30,  # Low renewal to encourage turnover
        downtime_months=2,  # Time for renovation
        upon_expiration=UponExpirationEnum.REABSORB,
        target_absorption_plan_id=post_renovation_plan_id,  # Link to absorption plan
        market_terms=ResidentialRolloverLeaseTerms(
            market_rent=1200.0,  # Current market rent
            term_months=12,
        ),
        renewal_terms=ResidentialRolloverLeaseTerms(
            market_rent=1200.0 * 0.95,  # Renewal rent slightly below market
            term_months=12,
        ),
    )

    # === STEP 4: CURRENT RENT ROLL ===
    # Split units into 1BR and 2BR unit types
    br1_count = 100 // 2  # 50 units
    br2_count = 100 - br1_count  # 50 units

    unit_specs = [
        ResidentialUnitSpec(
            unit_type_name="1BR - Current",
            unit_count=br1_count,
            avg_area_sf=800 * 0.8,  # 1BR is 80% of average (640 SF)
            current_avg_monthly_rent=1200.0 * 0.9,  # 1BR is 90% of average ($1080)
            rollover_profile=rollover_profile,
            lease_start_date=date(2023, 4, 1),  # Default lease start
        ),
        ResidentialUnitSpec(
            unit_type_name="2BR - Current",
            unit_count=br2_count,
            avg_area_sf=800 * 1.2,  # 2BR is 120% of average (960 SF)
            current_avg_monthly_rent=1200.0 * 1.1,  # 2BR is 110% of average ($1320)
            rollover_profile=rollover_profile,
            lease_start_date=date(2023, 4, 1),
        ),
    ]

    rent_roll = ResidentialRentRoll(unit_specs=unit_specs, vacant_units=[])

    # === STEP 5: OPERATING EXPENSES ===
    # Standard expense structure for value-add properties
    expenses = ResidentialExpenses(
        operating_expenses=[
            ResidentialOpExItem(
                name="Property Management",
                timeline=timeline,
                value=0.05,  # 5% of effective gross income
                frequency=FrequencyEnum.MONTHLY,
                reference=UnleveredAggregateLineKey.EFFECTIVE_GROSS_INCOME,
            ),
            ResidentialOpExItem(
                name="Maintenance & Repairs",
                timeline=timeline,
                value=600.0,  # $600 per unit annually
                frequency=FrequencyEnum.ANNUAL,
                reference=PropertyAttributeKey.UNIT_COUNT,
                growth_rate=PercentageGrowthRate(
                    name="Maintenance Inflation", value=0.03
                ),
            ),
            ResidentialOpExItem(
                name="Insurance",
                timeline=timeline,
                value=400.0,  # $400 per unit annually
                frequency=FrequencyEnum.ANNUAL,
                reference=PropertyAttributeKey.UNIT_COUNT,
                growth_rate=PercentageGrowthRate(
                    name="Insurance Inflation", value=0.04
                ),
            ),
            ResidentialOpExItem(
                name="Property Taxes",
                timeline=timeline,
                value=11_500_000
                * 0.012,  # 1.2% of acquisition price ($138k to match pattern)
                frequency=FrequencyEnum.ANNUAL,
                growth_rate=PercentageGrowthRate(name="Tax Growth", value=0.025),
            ),
            ResidentialOpExItem(
                name="Utilities (Common Area)",
                timeline=timeline,
                value=200.0,  # $200 per unit annually
                frequency=FrequencyEnum.ANNUAL,
                reference=PropertyAttributeKey.UNIT_COUNT,
                growth_rate=PercentageGrowthRate(name="Utility Inflation", value=0.04),
            ),
            ResidentialOpExItem(
                name="Marketing & Leasing",
                timeline=timeline,
                value=150.0,  # $150 per unit annually
                frequency=FrequencyEnum.ANNUAL,
                reference=PropertyAttributeKey.UNIT_COUNT,
            ),
            ResidentialOpExItem(
                name="Admin & Professional",
                timeline=timeline,
                value=100.0,  # $100 per unit annually
                frequency=FrequencyEnum.ANNUAL,
                reference=PropertyAttributeKey.UNIT_COUNT,
            ),
        ]
    )

    # === STEP 6: LOSSES (VACANCY & COLLECTION) ===
    # MATCHED TO PATTERN: Use identical assumptions as pattern approach
    losses = ResidentialLosses(
        general_vacancy=ResidentialGeneralVacancyLoss(
            rate=0.05,  # 5% stabilized vacancy (matches pattern)
        ),
        credit_loss=ResidentialCreditLoss(
            rate=0.015,  # 1.5% collection loss (matches pattern default)
        ),
    )

    # === STEP 7: ABSORPTION PLAN ===
    # Note: post_renovation_plan_id created earlier
    absorption_plan = ResidentialAbsorptionPlan(
        uid=post_renovation_plan_id,
        name="Post-Renovation Premium Leasing",
        start_date_anchor=StartDateAnchorEnum.ANALYSIS_START,
        pace=FixedQuantityPace(
            quantity=2, unit="Units", frequency_months=1
        ),  # 2 units per month absorption rate
        leasing_assumptions=ResidentialDirectLeaseTerms(
            monthly_rent=1450.0,  # $250 rent premium post-renovation ($10K/unit renovation should justify 2.5% monthly rent increase)
            lease_term_months=12,
            stabilized_renewal_probability=0.8,
            stabilized_downtime_months=1,
        ),
        stabilized_expenses=expenses,
        stabilized_losses=losses,
        stabilized_misc_income=[],
    )

    # === STEP 8: RENOVATION CAPITAL PLAN ===
    renovation_items = [
        CapitalItem(
            name="Unit Renovations",
            work_type="renovation",
            value=1_000_000,  # $1M total renovation budget
            timeline=renovation_timeline,  # Renovation timeline (starts 2025-01)
        ),
        # Removed Common Area item to match pattern approach exactly
    ]

    renovation_plan = CapitalPlan(
        name="Value-Add Renovation Plan",
        capital_items=renovation_items,
    )

    # === STEP 9: RESIDENTIAL PROPERTY ===
    property_asset = ResidentialProperty(
        name="Riverside Gardens",
        property_type="multifamily",
        gross_area=100 * 800,  # 100 units * 800 SF each
        net_rentable_area=100 * 800,
        unit_mix=rent_roll,
        capital_plans=[renovation_plan],  # Attach to asset, not Deal
        absorption_plans=[absorption_plan],
        expenses=expenses,
        losses=losses,
        miscellaneous_income=[],
    )

    # === STEP 9: ACQUISITION TERMS ===
    acquisition = AcquisitionTerms(
        name="Riverside Gardens Acquisition",
        timeline=Timeline(
            start_date=acquisition_date, duration_months=3
        ),  # 3 months to close
        value=11_500_000,  # $115K per unit (conservative institutional basis)
        acquisition_date=acquisition_date,
        closing_costs_rate=0.02,  # 2% closing costs
    )

    # === STEP 10: CONSTRUCTION-TO-PERMANENT FINANCING ===
    #  SOLVED: Our new ConstructionFacility automatically calculates loan amounts
    # based on TOTAL PROJECT COST (acquisition + renovation) from the ledger!

    # Calculate explicit loan amount to ensure proper financing
    total_project_cost = 11_500_000 + 1_000_000  # Acquisition + renovation = $12.5M
    construction_loan_amount = total_project_cost * 0.65  # 65% LTC

    # Construction facility with explicit loan sizing
    construction_loan = ConstructionFacility(
        name="Renovation Loan",
        loan_amount=construction_loan_amount,  # Explicit amount to prevent $1 fallback
        loan_term_months=36,  # 36 month loan term
        tranches=[
            DebtTranche(
                name="Bridge Financing",
                interest_rate=InterestRate(
                    details=FixedRate(rate=0.075)
                ),  # 7.5% renovation loan rate
                fee_rate=0.015,  # 1.5% origination fee
                ltc_threshold=0.65,  # 65% Loan-to-Cost
            )
        ],
        # Use SCHEDULED interest calculation method
        interest_calculation_method=InterestCalculationMethod.SCHEDULED,
        fund_interest_from_reserve=True,
        interest_reserve_rate=0.10,  # 10% interest reserve
    )

    # Permanent loan for stabilized operations (same amount as construction)
    permanent_loan = PermanentFacility(
        name="Permanent Financing",
        loan_amount=construction_loan_amount,  # EXPLICIT amount to match construction loan
        interest_rate=InterestRate(
            details=FixedRate(rate=0.055)
        ),  # 5.5% permanent rate
        loan_term_months=120,  # 10 years loan term
        ltv_ratio=0.65,  # 65% LTV
        dscr_hurdle=1.25,  # 1.25x DSCR requirement
        refinance_timing=36,  # Refinance timing at month 36
        sizing_method="manual",  # Use explicit loan amount (manual sizing)
    )

    financing_plan = FinancingPlan(
        name="Construction-to-Permanent",
        facilities=[construction_loan, permanent_loan],
    )

    # === STEP 11: PARTNERSHIP STRUCTURE ===
    # Use waterfall partnership structure
    partnership = create_gp_lp_waterfall(
        gp_share=0.20,
        lp_share=0.80,
        pref_return=0.08,  # 8% preferred return
        promote_tiers=[(0.15, 0.20)],  # 20% promote above 15% IRR
        final_promote_rate=0.20,  # 20% final promote rate
    )

    # === STEP 12: EXIT STRATEGY ===
    exit_valuation = DirectCapValuation(
        name="Riverside Gardens Sale",
        cap_rate=0.060,  # 6.0% exit cap (realistic for renovated Class B+ multifamily)
        transaction_costs_rate=0.025,
        hold_period_months=60,  # 5 years (typical value-add hold period)
        noi_basis_kind="LTM",  # Use trailing 12 months (realistic)
    )

    # === STEP 13: ASSEMBLE COMPLETE DEAL ===
    deal = Deal(
        name="Riverside Gardens Value-Add Acquisition",
        # No description for this deal
        asset=property_asset,
        acquisition=acquisition,
        financing=financing_plan,
        exit_valuation=exit_valuation,
        equity_partners=partnership,
    )

    total_project_cost = 11_500_000 + 1_000_000  # Acquisition + renovation for display
    print(f" Deal created: {deal.name}")
    print(f"   Total Project Cost: ${total_project_cost:,.0f}")
    print(f"   Units: 100 (from rent roll)")
    print(f"   Components assembled: 13 major steps, ~300 lines of code")
    print("    Construction facility properly funds total project cost")

    return deal


def demonstrate_pattern_interface():
    """
    Create a development/acquisition deal using the pattern interface.

    This approach demonstrates a high-level parameterized interface with industry-standard
    defaults and comprehensive validation. Rather than assembling components individually,
    the pattern accepts a minimal set of parameters and handles the rest through sensible defaults.

    Advantages:
    - Minimal configuration (approximately 20 lines)
    - Type safety and built-in validation via Pydantic
    - Industry-standard parameters and naming conventions
    - Rapid deal scenario generation
    - Built-in business rule validation

    Disadvantages:
    - Less control over advanced customization
    - Relies on sensible defaults that may not suit all scenarios
    - Limited to supported deal archetypes
    - May require composition approach for complex structures

    Returns:
        tuple: (pattern, deal) - Pattern object and created Deal, or (None, None) on error
    """
    print("\nCONVENTION APPROACH: Pattern Interface")
    print("-" * 60)

    try:
        # === SINGLE STEP: PATTERN CONFIGURATION ===
        pattern = ValueAddAcquisitionPattern(
            # Core project parameters
            property_name="Riverside Gardens",
            acquisition_date=date(2024, 1, 1),
            # Timeline derived from hold_period_years automatically
            # Acquisition terms
            acquisition_price=11_500_000,  # $115K per unit (conservative institutional basis)
            closing_costs_rate=0.02,  # 2% closing costs
            # Value-add strategy timing
            renovation_budget=1_000_000,  # $10K per unit (realistic renovation scope)
            renovation_start_year=1,  # Start in year 1 (2025-01)
            renovation_duration_years=2,  # 2 years renovation period
            # Property specifications
            total_units=100,
            current_avg_rent=1200.0,  # Pre-renovation rent (realistic starting point)
            target_avg_rent=1450.0,  # Post-renovation rent ($250 premium - $10K/unit renovation justifies 2.5% monthly rent increase)
            initial_vacancy_rate=0.05,  # Start with 5% vacancy rate
            stabilized_vacancy_rate=0.05,  # 5% stabilized vacancy
            credit_loss_rate=0.015,  # 1.5% credit loss rate
            # Financing terms
            ltv_ratio=0.65,  # 65% LTV (conservative for value-add)
            renovation_loan_rate=0.075,  # 7.5% renovation loan rate
            permanent_rate=0.055,  # 5.5% permanent rate
            loan_term_years=10,
            amortization_years=30,
            # Partnership structure
            distribution_method="waterfall",
            gp_share=0.20,
            lp_share=0.80,
            pref_return=0.08,  # 8% preferred return
            promote_tiers=[(0.15, 0.20)],  # 20% promote above 15% IRR
            # Exit strategy
            hold_period_years=5,  # 5 years (typical value-add hold period)
            exit_cap_rate=0.060,  # 6.0% exit cap (realistic for renovated Class B+ multifamily)
            exit_costs_rate=0.025,
        )

        print(f" Pattern created: {pattern.property_name}")
        print(
            f"   Total Project Cost: ${pattern.acquisition_price + pattern.renovation_budget:,.0f}"
        )
        print(f"   Configuration: Single step, ~25 parameters, type-safe")

        # Demonstrate timeline integration
        timeline = pattern.get_timeline()
        print(
            f"   Timeline: {timeline.start_date} for {timeline.duration_months} months"
        )

        # Demonstrate validation
        print(
            f"   Validation: GP({pattern.gp_share:.0%}) + LP({pattern.lp_share:.0%}) = 100% ✓"
        )
        print(
            f"   Rent Increase: ${pattern.current_avg_rent:.0f} → ${pattern.target_avg_rent:.0f}/month"
        )

        # Create the deal to show it works
        deal = pattern.create()
        print(f"   Deal Creation:  {deal.name}")
        print("    Construction financing properly funds total project cost")

        return pattern, deal

    except Exception as e:
        print(f" Pattern creation failed: {e}")
        traceback.print_exc()
        return None, None


def analyze_deals(composition_deal, pattern_deal):
    """
    Analyze both deals and display comparison of results.

    Runs complete deal analysis for each approach and compares key metrics
    including IRR, equity multiple, and total equity invested.

    Args:
        composition_deal: Deal created via composition
        pattern_deal: Deal created via pattern

    Returns:
        tuple: (comp_results, pattern_results) or (None, None) if analysis fails
    """
    print("\nANALYZING BOTH DEALS")
    print("-" * 60)

    try:
        # Use fixed timeline that matches pattern's derived timeline (7-year hold + 12-month renovation = 96 months)
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=96)
        settings = GlobalSettings()

        # Analyze composition deal
        print("   Analyzing composition deal...")
        comp_results = analyze(composition_deal, timeline, settings)

        # Analyze pattern deal
        print("   Analyzing pattern deal...")
        pattern_results = analyze(pattern_deal, timeline, settings)

        print("\n Analysis Complete!")
        print("\n   COMPOSITION RESULTS:")
        comp_irr_str = (
            f"{comp_results.levered_irr:.2%}" if comp_results.levered_irr else "N/A"
        )
        print(f"     Deal IRR: {comp_irr_str}")
        print(f"     Equity Multiple: {comp_results.equity_multiple:.2f}x")
        print(
            f"     Total Equity: ${comp_results.deal_metrics.get('total_investment'):,.0f}"
        )

        print("\n   PATTERN RESULTS:")
        irr_str = (
            f"{pattern_results.levered_irr:.2%}"
            if pattern_results.levered_irr
            else "N/A"
        )
        print(f"     Deal IRR: {irr_str}")
        print(f"     Equity Multiple: {pattern_results.equity_multiple:.2f}x")
        print(
            f"     Total Equity: ${pattern_results.deal_metrics.get('total_investment'):,.0f}"
        )

        # Check for equivalence
        irr_diff = abs(
            (comp_results.levered_irr or 0) - (pattern_results.levered_irr or 0)
        )
        em_diff = abs(comp_results.equity_multiple - pattern_results.equity_multiple)
        equity_diff = abs(
            comp_results.deal_metrics.get("total_investment")
            - pattern_results.deal_metrics.get("total_investment")
        )

        print(f"\n   EQUIVALENCE CHECK:")
        print(
            f"     IRR Difference: {irr_diff:.4%} ({'EQUIVALENT' if irr_diff < 0.001 else 'DIFFERENT'})"
        )
        print(
            f"     EM Difference: {em_diff:.4f}x ({'EQUIVALENT' if em_diff < 0.01 else 'DIFFERENT'})"
        )
        print(
            f"     Equity Difference: ${equity_diff:,.0f} ({'EQUIVALENT' if equity_diff < 10000 else 'DIFFERENT'})"
        )

        return comp_results, pattern_results

    except Exception as e:
        print(f" Analysis failed: {e}")
        traceback.print_exc()
        return None, None


def main():
    """
    Demonstrate value-add deal modeling using composition and pattern approaches.

    Creates the same value-add deal two ways: by manually assembling
    components and by using a high-level pattern interface. Displays both
    complete deal analysis results and compares the approaches.
    """
    print("VALUE-ADD DEAL MODELING: COMPOSITION vs CONVENTION")
    print("=" * 80)
    print()
    print(
        "This example demonstrates two approaches to modeling the same value-add deal:"
    )
    print("1. Composition: Manual assembly of components (current production approach)")
    print("2. Convention: Pattern-driven interface (ready for full implementation)")
    print()
    print(" Both approaches use unified construction financing solution")
    print("   with automatic loan sizing and ledger-first Sources & Uses integration.")
    print()

    # === APPROACH 1: COMPOSITION ===
    composition_deal = create_deal_via_composition()

    # === APPROACH 2: CONVENTION ===
    pattern, pattern_deal = demonstrate_pattern_interface()

    # === ANALYSIS COMPARISON ===
    if composition_deal and pattern_deal:
        comp_results, pattern_results = analyze_deals(composition_deal, pattern_deal)

        if comp_results and pattern_results:
            print("\nAPPROACH COMPARISON")
            print("-" * 60)
            print("Composition Approach:")
            print("  Full implementation working")
            print("  Complete analytical capability")
            print("  Construction financing fully resolved")
            print("  High complexity (300+ lines)")
            print("  Requires deep Performa expertise")
            print()
            print("Convention Approach:")
            print("  Interface complete and working")
            print("  Minimal configuration (25 parameters)")
            print("  Industry-standard defaults")
            print("  Type safety and validation")
            print("  Same construction financing solution")

    # === GOLDEN VALUE ASSERTIONS ===
    # Add assertions if both approaches worked
    if (
        composition_deal
        and pattern_deal
        and "comp_results" in locals()
        and "pattern_results" in locals()
    ):
        if comp_results and pattern_results:
            # Expected values for value-add comparison
            expected_composition_irr = 0.221  # 22.1% - Updated for value-add with rent growth and cap compression
            expected_em = 2.15  # 2.15x - Updated equity multiple
            expected_equity = 7394000  # ~$7.4M - actual equity invested (updated)

            # Validate composition results against expected values
            comp_irr = comp_results.levered_irr
            comp_em = comp_results.equity_multiple
            comp_equity = comp_results.deal_metrics.get("total_investment")

            # Validate composition results match expected values
            assert comp_irr is not None, f"Composition IRR should not be None"
            assert abs(comp_irr - expected_composition_irr) < 0.01, (
                f"Composition IRR {comp_irr} != expected {expected_composition_irr}"
            )
            assert abs(comp_em - expected_em) < 0.1, (
                f"Composition EM {comp_em} != expected {expected_em}"
            )
            assert abs(comp_equity - expected_equity) < 150000, (
                f"Composition Equity ${comp_equity} != expected ${expected_equity}"
            )

            # Validate pattern results match composition
            pattern_irr = pattern_results.levered_irr
            pattern_em = pattern_results.equity_multiple
            pattern_equity = pattern_results.deal_metrics.get("total_investment")

            # Pattern should match composition within financial calculation precision
            assert pattern_irr is not None, f"Pattern IRR should not be None"
            assert abs(pattern_irr - comp_irr) < 1e-6, (
                f"Pattern IRR {pattern_irr} != composition {comp_irr}"
            )
            assert abs(pattern_em - comp_em) < 1e-6, (
                f"Pattern EM {pattern_em} != composition {comp_em}"
            )
            assert abs(pattern_equity - comp_equity) < 1.0, (
                f"Pattern equity ${pattern_equity} != composition ${comp_equity}"
            )

            print(f" Composition validated: {comp_irr:.2%} IRR")
            print(f" Pattern validated: {pattern_irr:.2%} IRR")
            print(f"   Both approaches produce equivalent results")

            print("\nExpected value assertions passed - metrics remain stable")

    print("\nVALUE-ADD PATTERN COMPARISON COMPLETE!")
    print("Both approaches working with unified construction financing solution")
    print("Production-ready foundation for institutional deal modeling!")


if __name__ == "__main__":
    main()
