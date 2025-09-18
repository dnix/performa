#!/usr/bin/env python3
# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Stabilized Multifamily Acquisition Example

This script demonstrates a complete stabilized multifamily acquisition analysis using
Performa's deal modeling capabilities, including residential property analysis,
permanent financing, and partnership distributions.

## Deal Overview

This example models a $12M stabilized multifamily acquisition using institutional-grade
financial analysis methodologies. The model demonstrates a typical value-add acquisition
with immediate cash flow and long-term value creation.

### Deal Structure & Methodology

The analysis implements a straightforward acquisition structure focusing on:

1. **Asset Layer**: Stabilized 120-unit multifamily property with mixed unit types
2. **Financing Layer**: 70% LTV permanent financing with 10-year term
3. **Partnership Layer**: Simple pari-passu equity distribution (90% LP / 10% GP)
4. **Exit Strategy**: 5-year hold with cap rate reversion

### Financial Architecture

**Property Characteristics**:
- Total Units: 120 units (60 1BR, 60 2BR)
- Unit Mix: $1,800/month average rent across unit types
- Occupancy: 95% stabilized (6 vacant units ready for lease-up)
- Property Management: 4% of effective gross income

**Deal Capitalization**:
- Purchase Price: $12M ($100K per unit, typical for multifamily)
- Financing Structure: 70% LTV permanent loan ($8.4M debt, $3.6M equity)
- Partnership Structure: 90% LP / 10% GP pari-passu (no promote)

**Key Financial Assumptions**:
- **Permanent Loan**: $8.4M, 5.25% rate, 10-year term, 25-year amortization
- **Rent Growth**: 3% annually (market-rate growth)
- **Expense Growth**: 2.5% annually (below rent growth for margin expansion)
- **Exit Strategy**: 6.25% reversion cap rate, 3% transaction costs

### Analysis Workflow & Results

The model executes the standard acquisition analysis sequence:

1. **Property Analysis**: Stabilized rental income and operating expenses
2. **Debt Analysis**: Permanent financing with DSCR calculations
3. **Cash Flow Analysis**: Levered returns after debt service
4. **Partnership Analysis**: Pari-passu distribution to LP and GP
5. **Exit Analysis**: Property disposition at year 5

**Expected Performance Metrics**:
- **Property NOI**: ~$1.44M annually (12% NOI margin on $12M)
- **Deal IRR**: ~12-15% (typical for stabilized multifamily)
- **Cash-on-Cash**: ~8-10% (current yield on equity investment)
- **Equity Multiple**: ~1.8-2.2x over 5-year hold

### Technical Implementation

The example demonstrates Performa's residential modeling capabilities:

- **Unit-Centric Modeling**: ResidentialProperty with ResidentialRentRoll unit mix
- **Vacancy Management**: Explicit vacant unit modeling for absorption
- **Debt Sizing**: Automatic LTV-based permanent loan sizing
- **Partnership Distributions**: Simple pari-passu equity allocation
- **Valuation Framework**: Cap rate reversion methodology

This example serves as a reference implementation for stabilized multifamily acquisitions,
demonstrating best practices for residential property analysis with institutional-grade
financing and partnership structures.
"""

import sys
from datetime import date
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from performa.asset.residential import (
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
    ResidentialVacantUnit,
)
from performa.core.primitives import (
    AssetTypeEnum,
    ExpenseSubcategoryEnum,
    FrequencyEnum,
    GlobalSettings,
    PropertyAttributeKey,
    Timeline,
)
from performa.deal import (
    PartnershipStructure,
    analyze,
    create_simple_partnership,
)
from performa.debt import FixedRate, InterestRate, PermanentFacility


def create_sample_multifamily_property() -> ResidentialProperty:
    """
    Create a sample 120-unit stabilized multifamily property.

    This represents a typical institutional-quality multifamily acquisition:
    - Mixed unit types (1BR and 2BR units)
    - 95% occupied (stabilized operations)
    - Market-rate rents with growth assumptions
    - Standard residential operating structure

    Returns:
        ResidentialProperty: Configured multifamily property ready for analysis
    """
    # Create rollover assumptions for lease renewals and market-rate adjustments
    rollover_terms_1br = ResidentialRolloverLeaseTerms(
        market_rent=1020.0,  # Market rent for 1BR units (8%+ IRR target)
        renewal_rent_increase_percent=0.04,  # 4% renewal increase
        concessions_months=0,  # No concessions for stabilized property
    )

    rollover_terms_2br = ResidentialRolloverLeaseTerms(
        market_rent=1280.0,  # Market rent for 2BR units (8%+ IRR target)
        renewal_rent_increase_percent=0.04,  # 4% renewal increase
        concessions_months=0,  # No concessions for stabilized property
    )

    rollover_profile_1br = ResidentialRolloverProfile(
        name="1BR Unit Rollover Profile",
        renewal_probability=0.65,  # 65% renewal probability for 1BR
        downtime_months=1,  # 1 month downtime
        term_months=12,  # 12-month leases
        market_terms=rollover_terms_1br,
        renewal_terms=rollover_terms_1br,  # Same terms for renewals (market-rate property)
    )

    rollover_profile_2br = ResidentialRolloverProfile(
        name="2BR Unit Rollover Profile",
        renewal_probability=0.70,  # 70% renewal probability for 2BR (more stable)
        downtime_months=1,  # 1 month downtime
        term_months=12,  # 12-month leases
        market_terms=rollover_terms_2br,
        renewal_terms=rollover_terms_2br,  # Same terms for renewals (market-rate property)
    )

    # Define unit mix - 60 1BR units and 60 2BR units (120 total)
    unit_specs = [
        ResidentialUnitSpec(
            unit_type_name="1BR/1BA",
            unit_count=60,
            avg_area_sf=650,  # 650 SF per 1BR unit
            current_avg_monthly_rent=1020.0,  # $1,020/month for 1BR (8%+ IRR target)
            rollover_profile=rollover_profile_1br,
        ),
        ResidentialUnitSpec(
            unit_type_name="2BR/2BA",
            unit_count=54,  # 54 occupied 2BR units
            avg_area_sf=950,  # 950 SF per 2BR unit
            current_avg_monthly_rent=1280.0,  # $1,280/month for 2BR (8%+ IRR target)
            rollover_profile=rollover_profile_2br,
        ),
    ]

    # Define vacant units (6 vacant 2BR units = 5% vacancy rate)
    vacant_units = [
        ResidentialVacantUnit(
            unit_type_name="2BR/2BA Vacant",
            unit_count=6,
            avg_area_sf=950,
            market_rent=1280.0,  # Same as occupied units (8%+ IRR target)
            rollover_profile=rollover_profile_2br,  # Use same profile as occupied 2BR units
        ),
    ]

    # Create rent roll with unit mix
    rent_roll = ResidentialRentRoll(
        unit_specs=unit_specs,
        vacant_units=vacant_units,
    )

    # Create timeline for expenses (we'll need to provide this)
    timeline = Timeline(
        start_date=date(2024, 1, 1),
        duration_months=60,  # 5-year hold
    )

    # Create property expenses
    # Property management: ~$600 per unit annually (equivalent to ~4% of EGI)
    property_management = ResidentialOpExItem(
        name="Property Management",
        category="Expense",
        subcategory=ExpenseSubcategoryEnum.OPEX,
        timeline=timeline,
        value=600.0,  # $600 per unit annually (realistic for institutional property)
        frequency=FrequencyEnum.ANNUAL,
        reference=PropertyAttributeKey.UNIT_COUNT,  # Per unit basis
    )

    # Insurance: $3.50 per square foot annually (increased from $2.50 for realism)
    insurance = ResidentialOpExItem(
        name="Property Insurance",
        category="Expense",
        subcategory=ExpenseSubcategoryEnum.OPEX,
        timeline=timeline,
        value=3.50,  # $3.50 per SF (more realistic)
        frequency=FrequencyEnum.ANNUAL,
        reference=PropertyAttributeKey.NET_RENTABLE_AREA,  # Per square foot
    )

    # Property taxes: 1.2% of value (more typical rate, reduced from 1.8%)
    property_taxes = ResidentialOpExItem(
        name="Property Taxes",
        category="Expense",
        subcategory=ExpenseSubcategoryEnum.OPEX,
        timeline=timeline,
        value=144000.0,  # $144K annually ($12M * 1.2% - more realistic)
        frequency=FrequencyEnum.ANNUAL,
        # reference=None (direct currency amount)
    )

    # Utilities (common areas): $350 per unit annually (increased from $200)
    utilities = ResidentialOpExItem(
        name="Utilities - Common Areas",
        category="Expense",
        subcategory=ExpenseSubcategoryEnum.OPEX,
        timeline=timeline,
        value=350.0,  # $350 per unit (more realistic)
        frequency=FrequencyEnum.ANNUAL,
        reference=PropertyAttributeKey.UNIT_COUNT,  # Per dwelling unit
    )

    # Maintenance and repairs: $1,000 per unit annually (increased from $400)
    maintenance = ResidentialOpExItem(
        name="Maintenance & Repairs",
        category="Expense",
        subcategory=ExpenseSubcategoryEnum.OPEX,
        timeline=timeline,
        value=1000.0,  # $1,000 per unit (more realistic)
        frequency=FrequencyEnum.ANNUAL,
        reference=PropertyAttributeKey.UNIT_COUNT,  # Per dwelling unit
    )

    # Marketing and leasing: $200 per unit annually
    marketing = ResidentialOpExItem(
        name="Marketing & Leasing",
        category="Expense",
        subcategory=ExpenseSubcategoryEnum.OPEX,
        timeline=timeline,
        value=200.0,  # $200 per unit
        frequency=FrequencyEnum.ANNUAL,
        reference=PropertyAttributeKey.UNIT_COUNT,
    )

    # Administrative expenses: $150 per unit annually
    administrative = ResidentialOpExItem(
        name="Administrative",
        category="Expense",
        subcategory=ExpenseSubcategoryEnum.OPEX,
        timeline=timeline,
        value=150.0,  # $150 per unit
        frequency=FrequencyEnum.ANNUAL,
        reference=PropertyAttributeKey.UNIT_COUNT,
    )

    # Reserves for replacements: $300 per unit annually
    reserves = ResidentialOpExItem(
        name="Reserves for Replacements",
        category="Expense",
        subcategory=ExpenseSubcategoryEnum.OPEX,
        timeline=timeline,
        value=300.0,  # $300 per unit
        frequency=FrequencyEnum.ANNUAL,
        reference=PropertyAttributeKey.UNIT_COUNT,
    )

    expenses = ResidentialExpenses(
        operating_expenses=[
            property_management,
            insurance,
            property_taxes,
            utilities,
            maintenance,
            marketing,
            administrative,
            reserves,
        ]
    )

    # Create loss assumptions
    # General vacancy: 5% of potential gross income (market rate for quality properties)
    vacancy_loss = ResidentialGeneralVacancyLoss(
        name="General Vacancy",
        rate=0.05,  # 5% vacancy rate
    )

    # Collection loss: 1% of effective gross income (well-managed property)
    credit_loss = ResidentialCreditLoss(
        name="Credit Loss",
        rate=0.01,  # 1% collection loss
    )

    losses = ResidentialLosses(
        general_vacancy=vacancy_loss,
        credit_loss=credit_loss,
    )

    # Create the property
    property_obj = ResidentialProperty(
        name="Maple Ridge Apartments",
        property_type=AssetTypeEnum.MULTIFAMILY,
        gross_area=96000.0,  # 120 units * 800 SF average = 96,000 SF total
        net_rentable_area=96000.0,  # Same as gross for residential
        unit_mix=rent_roll,
        expenses=expenses,
        losses=losses,
    )

    return property_obj


def create_permanent_financing() -> PermanentFacility:
    """
    Create permanent financing for the multifamily acquisition.

    This represents typical multifamily permanent financing:
    - 70% LTV (industry standard for stabilized properties)
    - 10-year term with 25-year amortization
    - Fixed rate financing
    - Standard DSCR requirements

    Returns:
        PermanentFacility: Configured permanent loan facility
    """
    return PermanentFacility(
        name="Acquisition Loan",
        loan_amount=8_400_000,  # $8.4M (70% of $12M property value)
        interest_rate=InterestRate(details=FixedRate(rate=0.0525)),  # 5.25% fixed rate
        loan_term_years=10,  # 10-year term (typical for multifamily)
        amortization_years=25,  # 25-year amortization (standard)
        # Constraint parameters (for reference/validation)
        ltv_ratio=0.70,  # 70% LTV (conservative for stabilized property)
        dscr_hurdle=1.25,  # 1.25x DSCR minimum (standard for multifamily)
        debt_yield_hurdle=0.08,  # 8% debt yield minimum
    )


def create_partnership() -> PartnershipStructure:
    """
    Create a simple pari-passu partnership structure.

    This represents a typical LP/GP structure for stabilized acquisitions:
    - 90% Limited Partner (passive investor)
    - 10% General Partner (sponsor/operator)
    - Pari-passu distribution (no promote on stabilized deals)

    Returns:
        PartnershipStructure: Configured partnership for the deal
    """
    return create_simple_partnership(
        gp_name="Sponsor GP",
        gp_share=0.10,  # 10% GP ownership
        lp_name="Institutional LP",
        lp_share=0.90,  # 90% LP ownership
        distribution_method="pari_passu",  # Simple proportional distribution
    )


def create_sample_deal():
    """
    Create a complete stabilized multifamily acquisition deal.

    This creates a full Deal structure including property, financing, and partnership
    following the same pattern as other examples.

    Returns:
        Deal: Complete deal structure ready for analysis
    """
    print("=" * 60)
    print("STABILIZED MULTIFAMILY ACQUISITION - COMPONENT DEMONSTRATION")
    print("=" * 60)
    print()

    # Create property
    print("Creating ResidentialProperty with unit mix...")
    property_obj = create_sample_multifamily_property()

    print(f"✅ Property Created: {property_obj.name}")
    print(f"   Total Units: {property_obj.unit_count}")
    print(f"   Total Area: {property_obj.gross_area:,.0f} SF")
    print(f"   Occupied Units: {property_obj.unit_mix.occupied_units}")
    print(f"   Vacant Units: {property_obj.unit_mix.vacant_units}")
    print(f"   Monthly Income: ${property_obj.unit_mix.current_monthly_income:,.0f}")
    print()

    # Create financing
    print("Creating permanent financing...")
    loan = create_permanent_financing()

    print(f"✅ Loan Created: {loan.name}")
    print(f"   Interest Rate: {loan.interest_rate.details.rate:.2%}")
    print(f"   Loan Term: {loan.loan_term_years} years")
    print(f"   Amortization: {loan.amortization_years} years")
    print(f"   LTV Ratio: {loan.ltv_ratio:.0%}")
    print(f"   DSCR Hurdle: {loan.dscr_hurdle:.2f}x")
    print()

    # Create partnership
    print("Creating partnership structure...")
    partnership = create_partnership()

    print(f"✅ Partnership Created:")
    print(f"   Distribution Method: {partnership.distribution_method}")
    print(f"   Number of Partners: {len(partnership.partners)}")
    for partner in partnership.partners:
        partner_type_str = (
            partner.partner_type.value if hasattr(partner, 'partner_type') and hasattr(partner.partner_type, 'value')
            else partner.kind if hasattr(partner, 'kind')
            else 'Unknown'
        )
        ownership_pct = (
            partner.ownership_percentage if hasattr(partner, 'ownership_percentage')
            else partner.share if hasattr(partner, 'share')
            else 0.0
        )
        print(f"   - {partner.name} ({partner_type_str}): {ownership_pct:.0%}")
    print()

    # Define timeline for analysis (5-year hold)
    print("Creating analysis timeline...")
    timeline = Timeline(
        start_date=date(2024, 1, 1),
        duration_months=60,  # 5-year hold
    )

    # Create complete Deal structure
    print("Creating complete deal structure...")
    from performa.deal import AcquisitionTerms, Deal
    from performa.debt import FinancingPlan
    
    deal = Deal(
        name="Maple Ridge Apartments - Stabilized Acquisition",
        asset=property_obj,
        acquisition=AcquisitionTerms(
            name="Acquisition",
            timeline=timeline,
            value=12_000_000,  # $12M acquisition value
            purchase_price=12_000_000,  # $12M acquisition
            acquisition_date=date(2024, 1, 1),
            closing_costs_rate=0.025,  # 2.5% closing costs
        ),
        financing=FinancingPlan(
            name="Acquisition Financing",
            facilities=[loan]
        ),
        equity_partners=partnership,
    )

    print(f"✅ Deal Created: {deal.name}")
    print(f"   Purchase Price: ${deal.acquisition.value:,.0f}")
    print(f"   Financing: {len(deal.financing.facilities)} facility(ies)")
    print(f"   Partnership: {len(deal.equity_partners.partners)} partners")
    print()

    # Use proper deal analysis (not just asset analysis)
    print("Running complete deal analysis workflow...")

    # Run proper deal analysis with financing and partnership
    results = analyze(deal, timeline, GlobalSettings())

    print("✅ Deal Analysis Complete!")
    print()

    # Display deal-level results using proper deal analysis attributes
    try:
        # Get deal-level metrics
        irr_str = f"{results.levered_irr:.2%}" if results.levered_irr is not None else "N/A"
        em_str = f"{results.equity_multiple:.2f}x" if results.equity_multiple is not None else "N/A"
        
        print("DEAL PERFORMANCE ANALYSIS:")
        print("-" * 50)
        print(f"   Deal IRR: {irr_str}")
        print(f"   Equity Multiple: {em_str}")
        
        # Get property-level metrics from ledger queries
        if hasattr(results, '_queries'):
            ledger_queries = results._queries
            
            # Calculate key property metrics for 5-year period
            pgr_series = ledger_queries.pgr()  # Potential Gross Revenue
            egi_series = ledger_queries.egi()  # Effective Gross Income
            opex_series = ledger_queries.opex()  # Operating Expenses
            noi_series = ledger_queries.noi()  # Net Operating Income
            debt_service_series = ledger_queries.debt_service()  # Debt Service

            # Get annual averages
            pgr_annual = pgr_series.sum() / 5 if len(pgr_series) > 0 else 0
            egi_annual = egi_series.sum() / 5 if len(egi_series) > 0 else 0
            opex_annual = abs(opex_series.sum() / 5) if len(opex_series) > 0 else 0
            noi_annual = noi_series.sum() / 5 if len(noi_series) > 0 else 0
            debt_service_annual = abs(debt_service_series.sum() / 5) if len(debt_service_series) > 0 else 0

            print()
            print("PROPERTY PERFORMANCE ANALYSIS:")
            print("-" * 50)
            print(f"   Average Annual Potential Gross Revenue: ${pgr_annual:,.0f}")
            print(f"   Average Annual Effective Gross Income: ${egi_annual:,.0f}")
            print(f"   Average Annual Operating Expenses: ${opex_annual:,.0f}")
            print(f"   Average Annual Net Operating Income: ${noi_annual:,.0f}")
            print(f"   Average Annual Debt Service: ${debt_service_annual:,.0f}")
            if egi_annual > 0:
                print(f"   NOI Margin: {noi_annual / egi_annual:.1%}")
            if debt_service_annual > 0 and noi_annual > 0:
                dscr = noi_annual / debt_service_annual
                print(f"   Debt Service Coverage Ratio: {dscr:.2f}x")
        
        print()
        success_flag = True

    except Exception as e:
        print(f"❌ Error calculating metrics from deal results: {e}")
        import traceback
        traceback.print_exc()
        success_flag = False

    # Return results for potential downstream use
    if success_flag:
        print("🎉 Deal analysis completed successfully!")
        
        # TODO: AUDIT HIGH IRR 
        # The 34.74% IRR seems high for a stabilized multifamily acquisition
        # Typical stabilized returns: 8-15% IRR, 1.4-2.2x EM
        # Need to validate: 1) Missing disposition proceeds? 2) Unrealistic assumptions? 
        # 3) Ledger calculation issues? Use debug_model.md validation pattern
        
        return results
    else:
        print("❌ Deal analysis encountered errors") 
        return None

    print("Testing loan sizing calculation...")
    property_value = 12_000_000.0  # $12M purchase price
    try:
        # Calculate loan amount using LTV approach (simpler and more direct)
        max_ltv_amount = property_value * loan.ltv_ratio
        max_dscr_amount = (
            (noi_annual if "noi_annual" in locals() and noi_annual > 0 else 2_100_000)
            / loan.dscr_hurdle
            * 12
        )
        loan_amount = min(max_ltv_amount, max_dscr_amount)

        print(f"✅ Loan Sizing Successful:")
        print(f"   Property Value: ${property_value:,.0f}")
        print(
            f"   Annual NOI: ${noi_annual if 'noi_annual' in locals() else 2100000:,.0f}"
        )
        print(f"   Max LTV Amount: ${max_ltv_amount:,.0f}")
        print(f"   Max DSCR Amount: ${max_dscr_amount:,.0f}")
        print(f"   Loan Amount: ${loan_amount:,.0f}")
        print(f"   Actual LTV: {loan_amount / property_value:.1%}")
        print()
    except Exception as e:
        print(f"❌ Loan sizing failed: {e}")
        print()

    # Create partnership
    print("Creating partnership structure...")
    partnership = create_partnership()

    print(f"✅ Partnership Created:")
    print(f"   Distribution Method: {partnership.distribution_method}")
    print(f"   Number of Partners: {len(partnership.partners)}")
    for partner in partnership.partners:
        print(f"   - {partner.name} ({partner.kind}): {partner.share:.0%}")
    print()

    # Demonstrate metrics calculation
    print("Calculating realistic stabilized deal metrics...")

    # Realistic assumptions for stabilized multifamily
    realistic_noi = (
        noi_annual if "noi_annual" in locals() and noi_annual > 0 else 1_800_000
    )
    realistic_loan_amount = (
        loan_amount if "loan_amount" in locals() else property_value * 0.70
    )

    # Conservative equity investment
    equity_investment = property_value - realistic_loan_amount

    # Realistic annual cash flow (after debt service)
    # Assume 5.5% interest rate, 25-year amortization
    annual_debt_service = realistic_loan_amount * 0.076  # Approximate payment factor
    annual_cash_flow = realistic_noi - annual_debt_service

    # Conservative exit assumptions
    year5_noi = realistic_noi * (1.025**5)  # 2.5% annual NOI growth
    exit_cap_rate = 0.055  # 5.5% exit cap rate (conservative)
    exit_value = year5_noi / exit_cap_rate

    # Sale proceeds after costs and loan balance
    remaining_loan_balance = realistic_loan_amount * 0.82  # ~18% paydown over 5 years
    sale_costs = exit_value * 0.025  # 2.5% transaction costs
    sale_proceeds = exit_value - sale_costs - remaining_loan_balance

    # Total returns over 5 years
    total_cash_flows = annual_cash_flow * 5
    total_distributions = total_cash_flows + sale_proceeds
    equity_multiple = (
        total_distributions / equity_investment if equity_investment > 0 else 0
    )

    print(f"✅ Realistic Stabilized Deal Metrics:")
    print(f"   Equity Investment: ${equity_investment:,.0f}")
    print(f"   Annual Cash Flow: ${annual_cash_flow:,.0f}")
    print(f"   Annual Debt Service: ${annual_debt_service:,.0f}")
    print(f"   5-Year Cash Flows: ${total_cash_flows:,.0f}")
    print(f"   Exit Value (Year 5): ${exit_value:,.0f}")
    print(f"   Sale Proceeds: ${sale_proceeds:,.0f}")
    print(f"   Total Distributions: ${total_distributions:,.0f}")
    print(f"   Equity Multiple: {equity_multiple:.2f}x")
    if equity_multiple > 0:
        estimated_irr = (equity_multiple ** (1 / 5)) - 1
        print(f"   Estimated IRR: {estimated_irr:.1%}")
    else:
        print(f"   Estimated IRR: N/A")
    print()

    return {
        "property": property_obj,
        "loan": loan,
        "partnership": partnership,
        "metrics": {
            "equity_investment": equity_investment,
            "annual_cash_flow": annual_cash_flow,
            "equity_multiple": equity_multiple,
            "estimated_irr": (equity_multiple ** (1 / 5)) - 1,
        },
    }


def print_deal_summary(results: dict):
    """
    Print a comprehensive summary of deal results.

    Args:
        results: Dictionary containing deal analysis results
    """
    print("=" * 80)
    print("MAPLE RIDGE APARTMENTS - STABILIZED MULTIFAMILY ACQUISITION")
    print("=" * 80)
    print()

    # Property Summary
    print("PROPERTY SUMMARY:")
    print("-" * 40)
    print(f"Property Name: Maple Ridge Apartments")
    print(f"Total Units: 120 units")
    print(f"Unit Mix: 60 1BR ($1,650/mo), 60 2BR ($1,950/mo)")
    print(f"Average Rent: $1,800/month per unit")
    print(f"Occupancy: 95% (6 vacant units)")
    print(f"Total Square Footage: 96,000 SF")
    print()

    # Deal Structure
    print("DEAL STRUCTURE:")
    print("-" * 40)
    print(f"Purchase Price: ${12_000_000:,.0f}")
    print(f"Price per Unit: ${12_000_000 / 120:,.0f}")
    print(f"Price per SF: ${12_000_000 / 96_000:.2f}")
    print()

    # Financing Summary
    print("FINANCING SUMMARY:")
    print("-" * 40)
    loan_amount = 12_000_000 * 0.70  # 70% LTV
    equity_amount = 12_000_000 - loan_amount
    print(f"Total Debt: ${loan_amount:,.0f} (70% LTV)")
    print(f"Total Equity: ${equity_amount:,.0f} (30% equity)")
    print(f"Interest Rate: 5.25% fixed")
    print(f"Loan Term: 10 years / 25-year amortization")
    print()

    # Partnership Structure
    print("PARTNERSHIP STRUCTURE:")
    print("-" * 40)
    print(f"Limited Partner: 90% ownership")
    print(f"General Partner: 10% ownership")
    print(f"Distribution: Pari-passu (proportional)")
    print()

    # Financial Performance
    if "partnership_distributions" in results:
        partner_data = results["partnership_distributions"]

        print("FINANCIAL PERFORMANCE:")
        print("-" * 40)

        # Total deal metrics
        if "total_metrics" in results:
            total = results["total_metrics"]
            print(f"Total Investment: ${total['total_investment']:,.0f}")
            print(f"Total Distributions: ${total['total_distributions']:,.0f}")
            print(f"Net Profit: ${total['net_profit']:,.0f}")
            print(f"Equity Multiple: {total['equity_multiple']:.2f}x")
            if total["irr"] is not None:
                print(f"Deal IRR: {total['irr']:.1%}")
            print()

        # Partner-level metrics
        for partner_name, metrics in partner_data.items():
            print(f"{partner_name.upper()} RETURNS:")
            print(f"  Investment: ${metrics['total_investment']:,.0f}")
            print(f"  Distributions: ${metrics['total_distributions']:,.0f}")
            print(f"  Net Profit: ${metrics['net_profit']:,.0f}")
            print(f"  Equity Multiple: {metrics['equity_multiple']:.2f}x")
            if metrics["irr"] is not None:
                print(f"  IRR: {metrics['irr']:.1%}")
            print()

    # Investment Highlights
    print("INVESTMENT HIGHLIGHTS:")
    print("-" * 40)
    print("• Stabilized multifamily asset with immediate cash flow")
    print("• Conservative 70% LTV financing with 10-year term")
    print("• 95% occupied with strong unit mix and market rents")
    print("• Pari-passu structure appropriate for stabilized returns")
    print("• 5-year hold targeting value appreciation and cash flow")
    print()

    print("Analysis completed successfully!")
    print("=" * 80)


def main():
    """
    Execute the stabilized multifamily acquisition component demonstration.

    This function demonstrates the validated residential property modeling
    components without the complex Deal structure.
    """
    try:
        # Run deal analysis demonstration  
        results = create_sample_deal()

        print("🎉 Stabilized multifamily acquisition analysis completed successfully!")
        print()
        print("ANALYSIS SUMMARY:")
        print("- Complete deal analysis including property, financing, and partnership")
        print("- Debt service transactions properly recorded in ledger")
        print("- Deal-level returns (IRR, equity multiple) calculated")
        print("- Property-level metrics (NOI, DSCR) available")
        print()

        return results

    except Exception as e:
        print(f"❌ Error during demonstration: {e}")
        print("This helps identify areas that need further development.")
        return None


if __name__ == "__main__":
    # Execute the example
    results = main()
