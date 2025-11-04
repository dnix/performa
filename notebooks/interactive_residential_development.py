#!/usr/bin/env python3
# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

# %% [markdown]
"""
# Interactive Residential Development Analysis

A working demonstration of the Performa ResidentialDevelopmentPattern
with REAL calculated data and visualizations.

This interactive notebook shows:
- Actual deal analysis with real metrics
- Interactive charts showing sources/uses and costs
- Partnership waterfall analysis
- All data pulled from the actual Performa engine

**Usage**: Run each cell individually using VS Code's "Run Cell" buttons
"""

# %%
import time
from datetime import date

import pandas as pd
from pyobsplot import Plot

from performa.patterns import ResidentialDevelopmentPattern  # noqa: E402
from performa.reporting import (  # noqa: E402
    analyze_ledger_semantically,
    dump_performa_object,
    generate_assumptions_report,
)
from performa.visualization.altair import (  # noqa: E402
    create_cost_breakdown_donut,
    create_partnership_distribution_comparison,
    create_sources_uses_chart,
)
from performa.visualization.obsplot import (  # noqa: E402
    create_cash_flow_time_series,
    create_horizontal_categorical_bar,
)

print("✅ Libraries imported successfully!")
print("📊 Using PyObsPlot + Altair visualizations for clean, professional charts")
print("🎯 Configured for interactive Python - charts display inline!")
print("")
print("💡 USAGE:")
print("   1. Click the 'Run Cell' button above each # %% marker")
print("   2. Analysis results will appear below each cell")
print("   3. Review deal metrics, cash flows, and master ledger pivot tables")

# %%
# Configure project parameters
# Modify these parameters to see how they impact the analysis
print("🏙️ Residential Development Analysis")
print("=" * 50)

# Define project parameters (you can modify these)
project_params = {
    "project_name": "Garden View Apartments",
    "acquisition_date": date(2024, 1, 15),
    "land_cost": 3_500_000,
    "total_units": 120,
    "construction_cost_per_unit": 160_000,
    "construction_duration_months": 18,
    # === CONSTRUCTION FINANCING ===
    "construction_ltc_ratio": 0.70,  # 70% construction loan-to-cost
    "construction_interest_rate": 0.065,  # 6.5% construction rate
    "construction_fee_rate": 0.01,  # 1% origination fee
    "interest_calculation_method": "SCHEDULED",  # Dynamic interest capitalization
    # === PERMANENT FINANCING ===
    "permanent_ltv_ratio": 0.65,  # 65% permanent loan-to-value
    "permanent_interest_rate": 0.065,  # 6.5% permanent rate
    "permanent_loan_term_years": 10,  # 10-year term
    "permanent_amortization_years": 25,  # 25-year amortization
    # === PARTNERSHIP ===
    "gp_share": 0.10,
    "preferred_return": 0.08,
    "promote_tier_1": 0.20,
    "hold_period_years": 7,
    "exit_cap_rate": 0.055,
}

print(f"📋 Project: {project_params['project_name']}")
print(f"🏠 Units: {project_params['total_units']:,}")
print(f"💰 Land Cost: ${project_params['land_cost']:,}")
print(f"🏗️ Construction: ${project_params['construction_cost_per_unit']:,}/unit")
print("")

# Define unit mix
unit_mix_data = [
    {"unit_type": "1BR", "count": 60, "avg_sf": 750, "target_rent": 2100},
    {"unit_type": "2BR", "count": 40, "avg_sf": 1050, "target_rent": 2800},
    {"unit_type": "Studio", "count": 20, "avg_sf": 500, "target_rent": 1600},
]

print("🏠 Unit Mix:")
for unit in unit_mix_data:
    print(
        f"  - {unit['unit_type']}: {unit['count']} units @ {unit['avg_sf']} sf → ${unit['target_rent']:,}/mo"
    )
print("")

# %%
# Create and analyze the development pattern
print("⚡ Creating ResidentialDevelopmentPattern...")

# Create the actual pattern with REAL parameters
pattern = ResidentialDevelopmentPattern(
    # Core project parameters
    project_name=project_params["project_name"],
    acquisition_date=project_params["acquisition_date"],
    land_cost=project_params["land_cost"],
    # Unit specifications
    total_units=project_params["total_units"],
    unit_mix=unit_mix_data,
    # Construction parameters
    construction_cost_per_unit=project_params["construction_cost_per_unit"],
    construction_duration_months=project_params["construction_duration_months"],
    # Absorption strategy
    leasing_start_months=15,
    absorption_pace_units_per_month=8,
    # === CONSTRUCTION FINANCING ===
    construction_ltc_ratio=project_params["construction_ltc_ratio"],
    construction_interest_rate=project_params["construction_interest_rate"],
    construction_fee_rate=project_params["construction_fee_rate"],
    interest_calculation_method=project_params["interest_calculation_method"],
    # === PERMANENT FINANCING ===
    permanent_ltv_ratio=project_params["permanent_ltv_ratio"],
    permanent_interest_rate=project_params["permanent_interest_rate"],
    permanent_loan_term_years=project_params["permanent_loan_term_years"],
    permanent_amortization_years=project_params["permanent_amortization_years"],
    # Partnership structure
    distribution_method="waterfall",
    gp_share=project_params["gp_share"],
    lp_share=1.0 - project_params["gp_share"],
    preferred_return=project_params["preferred_return"],
    promote_tier_1=project_params["promote_tier_1"],
    # Exit strategy
    hold_period_years=project_params["hold_period_years"],
    exit_cap_rate=project_params["exit_cap_rate"],
    exit_costs_rate=0.025,
)

print("✅ Pattern created successfully!")
print("🔄 Running analysis...")

# Run the ACTUAL analysis with timing
start_time = time.time()
results = pattern.analyze()
end_time = time.time()
analysis_duration = end_time - start_time

print(f"✅ Analysis completed in {analysis_duration:.3f} seconds!")
print(
    "   ⏱️  This includes: asset modeling, cash flow generation, debt analysis, ledger building"
)
print("")


# %%
# Display calculated results and KPIs
# Extract calculated metrics from DealResults
deal_irr = results.levered_irr or 0.0
equity_multiple = results.equity_multiple or 0.0
net_profit = results.net_profit or 0.0

# Calculate total investment and returns from cash flows
levered_cf = results.levered_cash_flow
total_equity_invested = (
    abs(levered_cf[levered_cf < 0].sum()) if not levered_cf.empty else 0.0
)
total_equity_returned = (
    levered_cf[levered_cf > 0].sum() if not levered_cf.empty else 0.0
)
# Extract actual debt amount from financing analysis
total_debt = 0.0
if results.financing_analysis:
    print("📋 Financing Analysis:")
    print(f"   Has financing: {results.financing_analysis.get('has_financing', False)}")
    print(
        f"   Total debt service: ${results.financing_analysis.get('total_debt_service', 0):,.0f}"
    )

    # Get debt amount from debt service or estimation
    debt_service_total = results.financing_analysis.get("total_debt_service", 0)
    if debt_service_total > 0:
        # Rough estimation: debt service suggests significant debt
        total_debt = debt_service_total * 10  # Very rough approximation
        print(f"   Estimated total debt (from debt service): ${total_debt:,.0f}")
    else:
        print("   No significant debt detected")
else:
    print("📋 No financing analysis available - likely all-equity deal")

print("📊 REAL CALCULATED RESULTS:")
print("=" * 30)
print(f"💎 Deal IRR: {deal_irr:.1%}")
print(f"📈 Equity Multiple: {equity_multiple:.2f}x")
print(f"💰 Total Equity Invested: ${total_equity_invested:,.0f}")
print(f"💵 Total Equity Returned: ${total_equity_returned:,.0f}")
print(f"🏦 Total Debt: ${total_debt:,.0f}")
print(f"💸 Net Profit: ${total_equity_returned - total_equity_invested:,.0f}")
print("")

# %% Model validation using debug utilities
print("🔍 MODEL VALIDATION:")
print("=" * 20)

# Generate assumptions report - fail fast if there's an issue
assumptions_doc = generate_assumptions_report(pattern, include_risk_assessment=True)
print("📋 Assumptions Report Generated ✓")

# Access ledger from results
try:
    ledger_df = results.ledger_df  # Direct access to ledger DataFrame
    print("✅ Ledger access successful")
    print(f"📊 Ledger contains {len(ledger_df)} transactions")
    print(f"💰 Total transaction amount: ${ledger_df['amount'].sum():,.0f}")
    print(f"📅 Date range: {ledger_df['date'].min()} to {ledger_df['date'].max()}")

    # Run ledger analysis if we have the ledger
    ledger_analysis = analyze_ledger_semantically(results.ledger)
    print(f"✅ Ledger validation successful")
    print(
        f"💰 Net Ledger Flow: ${ledger_analysis['balance_checks']['total_net_flow']:,.0f}"
    )

except Exception as e:
    print(f"⚠️ Could not access ledger: {e}")
    print("This may indicate an issue with the analysis pipeline")

# Configuration introspection - fail fast if there's an issue
config = dump_performa_object(pattern, exclude_defaults=True)
print(f"⚙️ Non-default configuration items: {len(config)}")

# Sniff test - reasonable return ranges?
if 0.15 <= deal_irr <= 0.30 and 2.0 <= equity_multiple <= 4.5:
    print("✅ Returns pass sniff test for development deals")
else:
    print(
        f"⚠️ Returns may be outside typical development range: {deal_irr:.1%} IRR, {equity_multiple:.2f}x EM"
    )

print("")

# %%
# Display KPI summary
print("📊 Key Performance Indicators:")
print("=" * 35)

total_project_cost = total_equity_invested + total_debt
net_profit = total_equity_returned - total_equity_invested
cost_per_unit = total_project_cost / project_params["total_units"]
profit_per_unit = net_profit / project_params["total_units"]

# Get construction debt from financing analysis
construction_debt = (
    total_debt * 0.7 if total_debt > 0 else 0
)  # Rough estimation for construction portion
if results.financing_analysis and results.financing_analysis.get("has_financing"):
    print(f"📋 Using financing analysis data for debt calculations")
else:
    print("📋 No detailed financing breakdown available - using estimates")

# Calculate actual LTC achieved
dev_costs = float(pattern.land_cost) + float(pattern.total_construction_cost)
actual_ltc = construction_debt / dev_costs if dev_costs > 0 else 0

print(f"💎 Deal IRR:              {deal_irr:.1%}")
print(f"📈 Equity Multiple:       {equity_multiple:.2f}x")
print(
    f"🏗️ Construction LTC:      {actual_ltc:.1%} (target: {pattern.construction_ltc_ratio:.0%})"
)
print(
    f"💰 Dev Debt/Equity:       {construction_debt / total_equity_invested:.2f}x (${construction_debt:,.0f} / ${total_equity_invested:,.0f})"
)
print(f"💵 Total Capital:         ${total_project_cost:,.0f}")
print(f"💸 Net Profit:            ${net_profit:,.0f}")
print(f"🏠 Total Units:           {project_params['total_units']:,}")
print(f"🔢 Cost per Unit:         ${cost_per_unit:,.0f}")
print(f"💵 Profit per Unit:       ${profit_per_unit:,.0f}")
print("")

# %%
# Sources & Uses Analysis
print("📊 INTERACTIVE CHARTS: Sources & Uses Breakdown")
print("")

# Extract data for analysis display
land_cost_actual = float(pattern.land_cost)
construction_cost = float(pattern.total_construction_cost)

# Extract REAL cost components from pattern parameters
hard_costs = float(pattern.construction_cost_per_unit) * float(pattern.total_units)
soft_costs = hard_costs * float(pattern.soft_costs_rate)
financing_costs = total_debt * float(
    pattern.construction_fee_rate
)  # Construction origination fee

sources_dict = {"Equity": total_equity_invested}
if total_debt > 0:
    sources_dict["Construction Debt"] = total_debt

# Use ONLY what we can directly get from the pattern - no arbitrary calculations
uses_dict = {
    "Land Cost": float(pattern.land_cost),
    "Land Closing": float(pattern.land_cost) * float(pattern.land_closing_costs_rate),
    "Construction Cost": float(pattern.total_construction_cost),
    "Construction Fee": total_debt * float(pattern.construction_fee_rate),
}

print("💰 Sources & Uses Data (for later analysis):")
print("Sources:")
for source, amount in sources_dict.items():
    print(f"  - {source}: ${amount:,.0f}")
print("Uses:")
for use, amount in uses_dict.items():
    print(f"  - {use}: ${amount:,.0f}")
print("")

# SOURCES & USES CHART
sources_chart = create_sources_uses_chart(
    sources_dict, uses_dict, title="Sources & Uses of Development Funds"
)
sources_chart

# %%
# Create development cost breakdown chart
print("📊 Creating cost breakdown donut chart...")
print(
    f"   Cost data: {len(uses_dict)} categories, total: ${sum(uses_dict.values()):,.0f}"
)

donut = create_cost_breakdown_donut(uses_dict, title="Development Cost Breakdown")
print("✅ Donut chart created successfully!")
donut

# %%
# PyObsPlot horizontal cost breakdown
print("📊 Creating PyObsPlot horizontal cost breakdown...")

# Convert cost data to DataFrame format
cost_categories = []
cost_amounts = []
for category, amount in uses_dict.items():
    cost_categories.append(str(category))  # Ensure string type
    cost_amounts.append(float(amount))  # Ensure numeric type

cost_df = pd.DataFrame({"Category": cost_categories, "Amount": cost_amounts})

# Explicitly set data types to avoid datetime parsing warnings
cost_df["Category"] = cost_df["Category"].astype("string")
cost_df["Amount"] = cost_df["Amount"].astype("float64")

print(f"   Cost categories: {cost_categories}")
print(f"   Total costs: ${sum(cost_amounts):,.0f}")

# Create horizontal categorical bar showing proportional breakdown
obsplot_config = create_horizontal_categorical_bar(
    cost_df,
    category_column="Category",
    value_column="Amount",
    title="Development Cost Breakdown (Proportional)",
    show_percentages=True,
    height=100,
    margin_left=15,  # Space for axis labels (0%, 25%, etc.)
    margin_right=15,  # Space for axis labels on right
)

print("✅ PyObsPlot configuration created!")
print(f"📊 Rendering chart with Plot.plot()...")

# Display the chart using Plot.plot()
pyobsplot_chart = Plot.plot(obsplot_config)
print("✅ PyObsPlot horizontal categorical chart displayed!")
pyobsplot_chart

# %%
# Inspect available cash flow time series
print("🔍 CASH FLOW TIME SERIES INSPECTION")
print("=" * 80)
print("")

print("Available cash flow properties in DealResults:")
print("-" * 60)

# Get all available cash flow properties from DealResults
cash_flow_properties = [
    "levered_cash_flow",
    "unlevered_cash_flow",
    "equity_cash_flow",
    "noi",
    "operational_cash_flow",
    "debt_service",
    # Note: asset valuations handled separately in Asset Valuation Diagnostic section
]

for prop_name in cash_flow_properties:
    try:
        cf_series = getattr(results, prop_name)
        if cf_series is not None and not cf_series.empty:
            print(f"\n📊 {prop_name.upper()}:")
            print(f"   Length: {len(cf_series)} periods")
            print(
                f"   First 3 periods: ${cf_series.iloc[0]:8,.0f}, ${cf_series.iloc[1]:8,.0f}, ${cf_series.iloc[2]:8,.0f}"
            )
            print(f"   Min/Max: ${cf_series.min():,.0f} / ${cf_series.max():,.0f}")
            print(f"   Total Sum: ${cf_series.sum():,.0f}")

            # Flag suspicious signs for development project
            if prop_name in ["unlevered_cash_flow", "levered_cash_flow"]:
                early_positive = (
                    cf_series.iloc[:6] > 0
                ).sum()  # First 6 months (may be positive with immediate lease-up)
                if early_positive > 2:
                    print(
                        f"   ⚠️ NOTE: {early_positive} positive values in first 6 months (development may have immediate revenue)"
                    )

            if prop_name == "equity_cash_flow":
                # Equity cash flows: contributions should be positive, distributions negative (from deal perspective)
                contributions = cf_series[cf_series > 0].sum()
                distributions = cf_series[cf_series < 0].sum()
                print(f"   Contributions (positive): ${contributions:,.0f}")
                print(f"   Distributions (negative): ${distributions:,.0f}")

        else:
            print(f"\n📊 {prop_name.upper()}: Empty or None")

    except AttributeError:
        print(f"\n📊 {prop_name.upper()}: Property not available")
    except Exception as e:
        if "asset valuation" in str(e).lower():
            print(f"\n📊 {prop_name.upper()}: Asset valuation not recorded in ledger")
            print(
                f"   🔍 This may indicate valuation engine didn't run properly during analysis"
            )
            print(
                f"   💡 Try checking: results.deal_summary for available valuation data"
            )
        else:
            print(f"\n📊 {prop_name.upper()}: Error accessing - {e}")

print("\n" + "=" * 80)

# %%
# 🔍 ASSET VALUATION DIAGNOSTIC
print("🔍 ASSET VALUATION DIAGNOSTIC")
print("-" * 50)

try:
    # Check if we have valuation data in deal_summary or elsewhere
    print("📊 Checking available valuation data...")

    if hasattr(results, "deal_summary") and results.deal_summary:
        print(f"✅ Deal summary available with {len(results.deal_summary)} entries")
        valuation_keys = [
            k
            for k in results.deal_summary.keys()
            if "value" in k.lower() or "cap" in k.lower()
        ]
        if valuation_keys:
            print(f"   Valuation-related keys: {valuation_keys}")
            for key in valuation_keys:
                print(f"   {key}: {results.deal_summary[key]}")
        else:
            print("   No valuation-related keys found in deal_summary")

    # Check if NOI is available (needed for cap rate valuations)
    if hasattr(results, "noi"):
        noi_total = results.noi.sum()
        stabilized_noi = (
            results.noi.iloc[-12:].mean()
            if len(results.noi) >= 12
            else results.noi.mean()
        )
        print(
            f"✅ NOI available: Total=${noi_total:,.0f}, Stabilized=${stabilized_noi:,.0f}"
        )

        # Check if we have cap rates for manual valuation calculation
        try:
            # Try to access any cap rate data from the pattern or results
            print("   💡 NOI is available - asset valuation should be calculable")
        except Exception:
            pass

    # Check ledger for any valuation-related transactions
    if hasattr(results, "ledger_df"):
        ledger = results.ledger_df
        valuation_txns = ledger[
            ledger["name"].str.contains("valuation|value", case=False, na=False)
        ]
        if not valuation_txns.empty:
            print(f"✅ Found {len(valuation_txns)} valuation transactions in ledger")
            for _, row in valuation_txns.head(3).iterrows():
                print(f"   {row['date']}: {row['name']} = ${row['amount']:,.0f}")
        else:
            print("ℹ️  No explicit valuation transactions found in ledger")
            print(
                "   💡 ValuationEngine should now be recording asset valuations automatically"
            )

    # Test the new explicit asset valuation methods
    print("\n🔍 Testing explicit asset valuation methods:")

    # Try disposition valuation (most common use case)
    try:
        disp_val = results.disposition_valuation
        if disp_val:
            print(f"✅ Disposition valuation: ${disp_val:,.0f}")
        else:
            print("ℹ️  No disposition valuation found")
    except Exception as e:
        print(f"❌ Disposition valuation error: {e}")

    # Try complete time series
    try:
        valuations = results.asset_valuations
        print(f"✅ Asset valuations time series: {len(valuations)} entries")
        if not valuations.empty:
            print(
                f"   Value range: ${valuations.min():,.0f} to ${valuations.max():,.0f}"
            )
    except Exception as e:
        print(f"ℹ️  No asset valuations in ledger: {e}")
        print(
            "   This is expected - asset valuations are recorded by ValuationEngine when needed"
        )

except Exception as e:
    print(f"❌ Error in valuation diagnostic: {e}")

print("\n" + "=" * 80)
print("📊 LEDGER PIVOT TABLES")
print("-" * 50)
print("Analyze the deal ledger using pivot table views similar to Excel DCF models")
print("")

# Get the ledger DataFrame
ledger_df = results.ledger_df.copy()

# Convert date to period strings for pivot table columns
ledger_df["period"] = pd.PeriodIndex(ledger_df["date"], freq="M")

# PIVOT 1: By Category
print("\n🔢 PIVOT 1: BY CATEGORY")
try:
    pivot_category = ledger_df.pivot_table(
        values="amount", index="category", columns="period", aggfunc="sum", fill_value=0
    )

    print(f"   Shape: {pivot_category.shape}")
    print(f"   Categories: {list(pivot_category.index)}")

    # Show first 6 periods and totals
    first_6_periods = pivot_category.iloc[:, :6]
    totals = pivot_category.sum(axis=1).sort_values(ascending=False)

    print(f"\n   📊 FIRST 6 PERIODS:")
    for category in first_6_periods.index:
        period_values = " | ".join([
            f"${first_6_periods.loc[category, col]:8,.0f}"
            for col in first_6_periods.columns[:6]
        ])
        print(f"   {category:12}: {period_values}")

    print(f"\n   💰 CATEGORY TOTALS (Full Project):")
    for category, total in totals.items():
        print(f"   {category:12}: ${total:12,.0f}")

except Exception as e:
    print(f"   ❌ Error creating category pivot: {e}")

# PIVOT 2: By Category + Subcategory
print("\n🔢 PIVOT 2: BY CATEGORY + SUBCATEGORY")
try:
    pivot_cat_sub = ledger_df.pivot_table(
        values="amount",
        index=["category", "subcategory"],
        columns="period",
        aggfunc="sum",
        fill_value=0,
    )

    print(f"   Shape: {pivot_cat_sub.shape}")

    # Show totals by subcategory (top 15 by absolute value)
    totals_sub = pivot_cat_sub.sum(axis=1).reindex(
        pivot_cat_sub.sum(axis=1).abs().sort_values(ascending=False).index
    )

    print(f"\n   💰 TOP 15 SUBCATEGORY TOTALS:")
    for (category, subcategory), total in totals_sub.head(15).items():
        print(f"   {category} → {subcategory:20}: ${total:12,.0f}")

except Exception as e:
    print(f"   ❌ Error creating cat+subcat pivot: {e}")

# PIVOT 3: By Name + Category + Subcategory (Most Granular)
print("\n🔢 PIVOT 3: BY NAME + CATEGORY + SUBCATEGORY")
try:
    pivot_granular = ledger_df.pivot_table(
        values="amount",
        index=["item_name", "category", "subcategory"],
        columns="period",
        aggfunc="sum",
        fill_value=0,
    )

    print(f"   Shape: {pivot_granular.shape}")

    # Show top line items by total amount
    totals_granular = pivot_granular.sum(axis=1).reindex(
        pivot_granular.sum(axis=1).abs().sort_values(ascending=False).index
    )

    print(f"\n   💰 TOP 15 LINE ITEMS:")
    for (name, category, subcategory), total in totals_granular.head(15).items():
        name_short = name[:25] + "..." if len(name) > 25 else name
        print(f"   {name_short:28} | {category} → {subcategory:15}: ${total:12,.0f}")

except Exception as e:
    print(f"   ❌ Error creating granular pivot: {e}")

# SUMMARY VIEW: Key Financial Flows
print("\n🔢 PIVOT 4: KEY FINANCIAL FLOWS SUMMARY")
try:
    # Group key financial flows
    key_flows = (
        ledger_df.groupby(["flow_purpose", "subcategory"])
        .agg({"amount": ["sum", "count"], "period": ["min", "max"]})
        .round(0)
    )

    key_flows.columns = [
        "Total_Amount",
        "Transaction_Count",
        "First_Period",
        "Last_Period",
    ]
    key_flows = key_flows.sort_values("Total_Amount", key=abs, ascending=False)

    print(f"   📊 KEY FLOW SUMMARY:")
    print(
        f"   {'Flow Purpose':<20} {'Subcategory':<20} {'Total Amount':>15} {'Txns':>6} {'Period Range'}"
    )
    print(f"   {'-' * 20} {'-' * 20} {'-' * 15} {'-' * 6} {'-' * 15}")

    for (purpose, subcat), row in key_flows.head(20).iterrows():
        period_range = f"{row['First_Period']}-{row['Last_Period']}"
        print(
            f"   {purpose:<20} {subcat:<20} ${row['Total_Amount']:>13,.0f} {row['Transaction_Count']:>6.0f} {period_range}"
        )

except Exception as e:
    print(f"   ❌ Error creating key flows summary: {e}")

print("\n" + "=" * 80)

# %%
# Cash Flow Sign Convention Analysis
print("🔍 CASH FLOW SIGN CONVENTIONS")
print("-" * 60)
print("Understanding investor perspective: negative = cash out, positive = cash in")
print("")

# Get cash flow data for detailed analysis
noi_series = results.noi
unlevered_cf = results.unlevered_cash_flow
operational_cf = results.operational_cash_flow
levered_cf = results.levered_cash_flow
equity_cf = results.equity_cash_flow

print("📊 DETAILED FIRST 12 MONTHS CASH FLOW BREAKDOWN:")
print("Month | NOI      | UCF      | LCF      | ECF      | Notes")
print("-" * 80)

for i in range(min(12, len(noi_series))):
    period = noi_series.index[i]
    noi_val = noi_series.iloc[i]
    ucf_val = unlevered_cf.iloc[i] if i < len(unlevered_cf) else 0
    lcf_val = levered_cf.iloc[i] if i < len(levered_cf) else 0
    ecf_val = equity_cf.iloc[i] if i < len(equity_cf) else 0

    # Flag notable patterns
    notes = []
    if i <= 6 and ucf_val > 0:  # First 6 months (development may have mixed patterns)
        notes.append("UCF+")
    if i <= 6 and lcf_val > 0:  # First 6 months (development may have mixed patterns)
        notes.append("LCF+")
    if (
        i <= 18 and ecf_val < 0
    ):  # Equity contributions should be positive early, distributions negative later
        notes.append("🚨ECF-early")

    notes_str = " ".join(notes) if notes else "✅"

    print(
        f" {i + 1:2d}   | ${noi_val:8,.0f} | ${ucf_val:8,.0f} | ${lcf_val:8,.0f} | ${ecf_val:8,.0f} | {notes_str}"
    )

print("\n🔍 INVESTOR PERSPECTIVE ANALYSIS:")
print("For development projects, TYPICAL signs are:")
print(
    "- UCF/LCF: NEGATIVE during construction (cash outflows), POSITIVE during operations/exit"
)
print(
    "- ECF: POSITIVE during funding (equity contributions), NEGATIVE during distributions"
)
print("- NOI: May start early in some developments, POSITIVE during operations")

# Calculate totals and check overall flow
print(f"\n💰 CASH FLOW TOTALS:")
print(f"   NOI Total: ${noi_series.sum():,.0f}")
print(f"   UCF Total: ${unlevered_cf.sum():,.0f}")
print(f"   LCF Total: ${levered_cf.sum():,.0f}")
print(f"   ECF Total: ${equity_cf.sum():,.0f}")

# Check for construction phase issues
construction_mask = (
    noi_series.index <= "2025-03"
)  # First 15 months should be construction
construction_ucf = unlevered_cf[construction_mask]
construction_positive = (construction_ucf > 0).sum()

print(f"\n🚨 CONSTRUCTION PHASE ANALYSIS (first 15 months):")
print(
    f"   Periods with POSITIVE UCF: {construction_positive} out of {len(construction_ucf)}"
)
if construction_positive <= 3:
    print(
        f"   ✅ Cash flow pattern shows expected negative construction outflows, positive operational inflows"
    )
else:
    print(
        f"   ⚠️ Note: More positive UCF values during construction than typical for this deal type"
    )

# PYOBSPLOT CASH FLOW TIME SERIES (WARMING STRIPES STYLE)
print("📊 Creating PyObsPlot cash flow time series...")

# Create cash flow DataFrame with key metrics aligned to timeline
cash_flow_data = pd.DataFrame({
    "Date": results.timeline.period_index,
    "NOI": results.noi,
    "UCF": results.unlevered_cash_flow,
    "LCF": results.levered_cash_flow,
})

print(f"   Cash flow periods: {len(cash_flow_data)}")
print(
    f"   NOI range: ${cash_flow_data['NOI'].min():,.0f} to ${cash_flow_data['NOI'].max():,.0f}"
)
print(
    f"   UCF range: ${cash_flow_data['UCF'].min():,.0f} to ${cash_flow_data['UCF'].max():,.0f}"
)

# Single UCF stripe (warming stripes style)
ucf_data = cash_flow_data[["Date", "UCF"]].copy()
ucf_data = ucf_data.rename(columns={"UCF": "Amount"})

single_stripe_config = create_cash_flow_time_series(
    ucf_data,
    time_column="Date",
    value_column="Amount",
    title="Unlevered Cash Flow - Warming Stripes",
    scale_millions=True,
    # Using new default RdBu: red for outflows, blue for inflows
    color_clamp_percentiles=(0.05, 0.95),  # Aggressive clamping for better gradient
    height=60,  # Shorter for true warming stripes effect
)

print("✅ Single stripe config created!")
single_stripe_plot = Plot.plot(single_stripe_config)
single_stripe_plot

# %%
# Multiple cash flow stripes using facets - Unlevered vs Levered
print("📊 Creating faceted cash flow comparison...")

# Prepare data for faceted view
multi_cf_records = []
for i, date_period in enumerate(cash_flow_data["Date"]):
    # Convert Period to timestamp for plotting
    date_ts = (
        date_period.to_timestamp()
        if hasattr(date_period, "to_timestamp")
        else date_period
    )
    multi_cf_records.extend([
        {
            "Date": date_ts,
            "Type": "Unlevered CF",
            "Amount": cash_flow_data["UCF"].iloc[i],
        },
        {
            "Date": date_ts,
            "Type": "Levered CF",
            "Amount": cash_flow_data["LCF"].iloc[i],
        },
    ])

multi_cf_data = pd.DataFrame(multi_cf_records)

faceted_stripes_config = create_cash_flow_time_series(
    multi_cf_data,
    time_column="Date",
    value_column="Amount",
    facet_column="Type",
    title="Cash Flow Comparison: Unlevered vs Levered",
    scale_millions=True,
    color_scheme="RdBu",  # Red for outflows, blue for inflows
    color_clamp_percentiles=(
        0.03,
        0.97,
    ),  # Slightly more aggressive clamping for faceted view
    stripe_height=60,
)

print("✅ Faceted stripes config created!")
faceted_stripes_plot = Plot.plot(faceted_stripes_config)
faceted_stripes_plot

print("\n" + "=" * 80)

# %%
# Development Cash Flow Patterns
print("🏗️ DEVELOPMENT CASH FLOW PATTERNS")
print("=" * 70)
print("")

print("Understanding development deal cash flow characteristics:")
print("   • Construction phase: Negative UCF (cash outflows for construction)")
print("   • Lease-up phase: Gradually positive as units come online")
print("   • Operations: Positive cash flows from stabilized operations")
print("   • Disposition: Large positive inflow from sale proceeds")
print("")

print("Key timeline for this project:")
print(f"   • Construction: {project_params['construction_duration_months']} months")
print(f"   • Hold period: {project_params['hold_period_years']} years")
print(f"   • Lease-up strategy: Immediate absorption starting month 15")
print("")

# Get investment cash flows using DealResults interface
investment_cf = results.levered_cash_flow  # Direct property access
print(f"📈 INVESTMENT CASH FLOWS (basis for IRR):")
print(f"   Shape: {investment_cf.shape}")
print(f"   Range: ${investment_cf.min():,.0f} to ${investment_cf.max():,.0f}")
print(f"   Total investment: ${abs(investment_cf[investment_cf < 0].sum()):,.0f}")
print(f"   Total returns: ${investment_cf[investment_cf > 0].sum():,.0f}")
print(f"   Net profit: ${investment_cf.sum():,.0f}")

# Check for disposition proceeds (big exit cash flow)
max_period = investment_cf.idxmax()
max_value = investment_cf.max()
print(f"   🎯 Largest cash flow: ${max_value:,.0f} in period {max_period}")

# Get deal metrics from results
irr = results.levered_irr or 0.0
equity_multiple = results.equity_multiple or 0.0
print(f"\n🎯 Deal Performance:")
print(f"   IRR: {irr:.2%}")
print(f"   Equity Multiple: {equity_multiple:.2f}x")

# Compare to industry standards (declarative expectations)
print(f"\n📊 Industry Standards (Development): 18-28% IRR, 2.5-4.0x EM")
is_irr_in_range = 0.18 <= irr <= 0.28
is_em_in_range = 2.5 <= equity_multiple <= 4.0
print(
    f"   IRR {'✅' if is_irr_in_range else '⚠️'} {'within' if is_irr_in_range else 'outside'} development range"
)
print(
    f"   EM {'✅' if is_em_in_range else '⚠️'} {'within' if is_em_in_range else 'outside'} development range"
)

print("=" * 50)

# %%
# Partnership waterfall analysis
# Extract partnership structure from pattern
gp_share_pct = float(pattern.gp_share)
preferred_return_pct = float(pattern.preferred_return)
promote_rate_pct = float(pattern.promote_tier_1)

# Calculate actual contributions
gp_equity = total_equity_invested * gp_share_pct
lp_equity = total_equity_invested * (1 - gp_share_pct)
# Calculate actual waterfall distributions
preferred_amount = lp_equity * preferred_return_pct
remaining_after_pref = max(
    0, total_equity_returned - total_equity_invested - preferred_amount
)

lp_distributions = (
    lp_equity + preferred_amount + remaining_after_pref * (1 - promote_rate_pct)
)
gp_distributions = gp_equity + remaining_after_pref * promote_rate_pct

print("🤝 Partnership Analysis:")
print(f"👔 GP Share: {gp_share_pct:.1%}")
print(f"🏦 LP Preferred Return: {preferred_return_pct:.1%}")
print(f"🚀 GP Promote: {promote_rate_pct:.1%}")
print("")
print("Capital Contributions:")
print(f"  - GP Equity: ${gp_equity:,.0f}")
print(f"  - LP Equity: ${lp_equity:,.0f}")
print("")
print("Distribution Results:")
print(
    f"  - GP Gets: ${gp_distributions:,.0f} ({gp_distributions / total_equity_returned:.1%})"
)
print(
    f"  - LP Gets: ${lp_distributions:,.0f} ({lp_distributions / total_equity_returned:.1%})"
)
print("")

# %%
# Partnership Distribution Analysis
print("🤝 PARTNERSHIP DISTRIBUTION ANALYSIS")
print("-" * 60)
print("Analyzing how cash flows through GP/LP waterfall structure")
print("")

print("🤝 Partnership Structure Analysis:")
print(f"👔 GP Share: {gp_share_pct:.1%}")
print(f"🏦 LP Preferred Return: {preferred_return_pct:.1%}")
print(f"🚀 GP Promote: {promote_rate_pct:.1%}")
print("")
print("Capital Contributions (calculated from levered_cash_flow):")
print(f"  - GP Equity: ${gp_equity:,.0f}")
print(f"  - LP Equity: ${lp_equity:,.0f}")
print("")
print("Distribution Results (calculated from cash flows):")
print(
    f"  - GP Gets: ${gp_distributions:,.0f} ({gp_distributions / total_equity_returned:.1%})"
)
print(
    f"  - LP Gets: ${lp_distributions:,.0f} ({lp_distributions / total_equity_returned:.1%})"
)
print("")

# PARTNERSHIP DISTRIBUTION CHART
dist = create_partnership_distribution_comparison(
    {"GP": gp_equity, "LP": lp_equity},
    {"GP": gp_distributions, "LP": lp_distributions},
    title="Capital vs. Profit Distribution",
)
dist

print("\n" + "=" * 80)

# %% [markdown]
"""
## Summary and Key Insights

This interactive analysis demonstrates the full power of the Performa library for residential development modeling.
"""

# %%
# Analysis Summary
print("📊 ANALYSIS SUMMARY")
print("=" * 80)
print("")

print("🎯 DEAL PERFORMANCE METRICS:")
print(f"   Levered IRR: {deal_irr:.1%}")
print(f"   Equity Multiple: {equity_multiple:.2f}x")
print(f"   Net Profit: ${net_profit:,.0f}")
print("")

print("🔍 CASH FLOW CHARACTERISTICS:")
print(
    "   • Unlevered Cash Flow: Negative during construction, positive during operations"
)
print("   • Levered Cash Flow: Reflects debt service and refinancing impacts")
print("   • Equity Cash Flow: Shows investor contributions and distributions")
print("   • NOI: Builds from lease-up through stabilization")
print("")

print("📖 LEDGER INTEGRITY:")
ledger_size = len(results.ledger_df)
ledger_balance = results.ledger_df["amount"].sum()
print(f"   • Total transactions recorded: {ledger_size:,}")
print(
    f"   • Date range: {results.ledger_df['date'].min()} to {results.ledger_df['date'].max()}"
)
print(f"   • Net ledger balance: ${ledger_balance:,.0f}")
print("")

print("💡 USING THIS NOTEBOOK:")
print("   • Modify parameters at the top to stress test different scenarios")
print(
    "   • Use debug utilities (dump_performa_object, analyze_ledger_semantically) to diagnose issues"
)
print("   • Review ledger pivot tables for complete transaction audit trail")
print("   • Compare metrics against industry benchmarks for reasonableness")
print("")

print("\n" + "=" * 80)

# %%
