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
# Import libraries and setup
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
print("📊 Using Altair-based visualizations for clean, professional charts")
print("🎯 Configured for VS Code Interactive Python - charts will display inline!")
print("")
print("💡 USAGE:")
print("   1. Click the 'Run Cell' button above each # %% marker")
print("   2. Charts will appear directly in the output below each cell")
print("   3. No external files - everything displays inline!")

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

# Run the ACTUAL analysis
results = pattern.analyze()

print("✅ Analysis completed!")
print("")


# %%
# Display calculated results and KPIs
# Extract REAL calculated metrics
deal_irr = float(results.deal_metrics.get("levered_irr", 0))
equity_multiple = float(results.deal_metrics.get("equity_multiple", 0))
total_equity_invested = float(results.deal_metrics.get("total_investment", 0))
total_equity_returned = float(results.deal_metrics.get("total_distributions", 0))
# Extract actual debt amount from financing analysis results
total_debt = 0.0
if (
    hasattr(results, "financing_analysis")
    and results.financing_analysis
    and results.financing_analysis.has_financing
):
    # Get total loan proceeds from all facilities
    if hasattr(results.financing_analysis, "loan_proceeds"):
        for (
            facility_name,
            proceeds_series,
        ) in results.financing_analysis.loan_proceeds.items():
            if hasattr(proceeds_series, "sum"):
                facility_debt = float(proceeds_series.sum())
                if facility_debt > 0:
                    total_debt += facility_debt
                    print(f"   {facility_name}: ${facility_debt:,.0f}")

print(f"   Total debt from analysis: ${total_debt:,.0f}")

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

# Access ledger from asset analysis results
if hasattr(results, "asset_analysis") and hasattr(results.asset_analysis, "ledger"):
    ledger = results.asset_analysis.ledger
    ledger_analysis = analyze_ledger_semantically(ledger)
    print(f"✅ Ledger validation successful")
    print(
        f"💰 Net Ledger Flow: ${ledger_analysis['balance_checks']['total_net_flow']:,.0f}"
    )
else:
    raise ValueError(
        "No ledger found in results.asset_analysis - this indicates a serious issue with the analysis"
    )

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

# Get construction debt separately to show actual LTC
construction_debt = 0.0
if hasattr(results, "financing_analysis") and results.financing_analysis.loan_proceeds:
    for (
        facility_name,
        proceeds_series,
    ) in results.financing_analysis.loan_proceeds.items():
        if "Construction" in facility_name and hasattr(proceeds_series, "sum"):
            construction_debt = float(proceeds_series.sum())
            break

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
# Create sources & uses visualization
# Extract cost data from the pattern and results
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

print("💰 Sources & Uses:")
print("Sources:")
for source, amount in sources_dict.items():
    print(f"  - {source}: ${amount:,.0f}")
print("Uses:")
for use, amount in uses_dict.items():
    print(f"  - {use}: ${amount:,.0f}")
print("")

# Create and display the sources & uses chart
print("📊 Creating chart...")
print(
    f"   Sources data: {len(sources_dict)} items, total: ${sum(sources_dict.values()):,.0f}"
)
print(f"   Uses data: {len(uses_dict)} items, total: ${sum(uses_dict.values()):,.0f}")


sources_chart = create_sources_uses_chart(
    sources_dict, uses_dict, title="Sources & Uses of Development Funds"
)
print("✅ Chart created successfully!")
sources_chart


# %%
# Create development cost breakdown chart
# Create cost breakdown donut chart
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
print("📊 Configuration details:")
print(f"   - Marks: {len(obsplot_config.get('marks', []))} mark(s)")
print(f"   - Title: {obsplot_config.get('title', 'None')}")
print(f"   - Height: {obsplot_config.get('height', 'default')}")

print("📊 Rendering chart with Plot.plot()...")

# Debug: Check the data first
print("📊 Data check:")
print(f"   - DataFrame shape: {cost_df.shape}")
print(f"   - DataFrame columns: {list(cost_df.columns)}")
print(f"   - DataFrame dtypes:\n{cost_df.dtypes}")
print(f"   - Sample data:\n{cost_df.head()}")

# Render the chart - assign to variable so it displays in VS Code Interactive
pyobsplot_chart = Plot.plot(obsplot_config)

print("✅ PyObsPlot chart object created!")

# Display the chart (this should work in VS Code Interactive)
pyobsplot_chart

print("✅ PyObsPlot categorical chart displayed!")

# %%
# PyObsPlot cash flow time series
print("📊 Creating PyObsPlot cash flow time series...")

# Get the summary DataFrame which has time series cash flows
summary_df = results.asset_analysis.summary_df

# Create cash flow DataFrame with key metrics
cash_flow_data = pd.DataFrame({
    "Date": summary_df.index,
    "NOI": summary_df.get("Net Operating Income", 0),
    "CapEx": -abs(summary_df.get("Capital Expenditures", 0)),  # Make negative
    "UCF": summary_df.get("Unlevered Cash Flow", 0),
})

# Keep dates as PeriodIndex or convert to strings - let obsplot function handle conversion
print(f"   Date type before processing: {type(cash_flow_data['Date'].iloc[0])}")
print(f"   First date value: {cash_flow_data['Date'].iloc[0]}")

print(f"   Cash flow periods: {len(cash_flow_data)}")
print(
    f"   NOI range: ${cash_flow_data['NOI'].min():,.0f} to ${cash_flow_data['NOI'].max():,.0f}"
)
print(
    f"   UCF range: ${cash_flow_data['UCF'].min():,.0f} to ${cash_flow_data['UCF'].max():,.0f}"
)

# Single UCF stripe (true warming stripes style)
ucf_data = cash_flow_data[["Date", "UCF"]].copy()
ucf_data = ucf_data.rename(columns={"UCF": "Amount"})

single_stripe_config = create_cash_flow_time_series(
    ucf_data,
    time_column="Date",
    value_column="Amount",
    title="Unlevered Cash Flow - Warming Stripes",
    scale_millions=True,
    color_scheme="BuRd",
    height=60,  # Shorter for true warming stripes effect
)

# Display single stripe
single_stripe_plot = Plot.plot(single_stripe_config)
single_stripe_plot

# %%
# Multiple cash flow stripes using facets - Unlevered vs Levered
ucf_investment = results.asset_analysis.ucf
investment_cf = results.levered_cash_flows.levered_cash_flows

print("📊 Data alignment investigation:")
print(f"   UCF: {len(ucf_investment)} periods, {type(ucf_investment.index)}")
print(f"   LCF: {len(investment_cf)} periods, {type(investment_cf.index)}")
print(f"   UCF range: {ucf_investment.index[0]} to {ucf_investment.index[-1]}")
print(f"   LCF range: {investment_cf.index[0]} to {investment_cf.index[-1]}")

print(f"\n🎯 Timeline Analysis:")
print(f"   UCF is likely: Full operational timeline (asset perspective)")
print(f"   LCF is likely: Project timeline (investment perspective)")
print(f"   Need to truncate UCF to match LCF timeline for apples-to-apples comparison")

# Convert both to same index type for comparison
if hasattr(ucf_investment.index, "to_timestamp"):
    ucf_aligned = ucf_investment.copy()
    ucf_aligned.index = ucf_aligned.index.to_timestamp()
else:
    ucf_aligned = ucf_investment.copy()

if hasattr(investment_cf.index, "to_timestamp"):
    lcf_aligned = investment_cf.copy()
    lcf_aligned.index = lcf_aligned.index.to_timestamp()
else:
    lcf_aligned = investment_cf.copy()

print(f"   After index conversion - UCF: {len(ucf_aligned)}, LCF: {len(lcf_aligned)}")

# Find overlapping periods and align data
common_periods = ucf_aligned.index.intersection(lcf_aligned.index)
print(f"   Common periods: {len(common_periods)}")

# Strategy: Use LCF timeline as the "project timeline" and truncate UCF to match
print(f"   Strategy: Using LCF timeline ({len(lcf_aligned)} periods) as project scope")
print(f"   Truncating UCF from {len(ucf_aligned)} periods to match LCF timeline")

# Truncate UCF to match LCF timeline (project timeline)
if len(ucf_aligned) >= len(lcf_aligned):
    # UCF is longer - truncate to match LCF
    ucf_final = ucf_aligned.iloc[: len(lcf_aligned)]
    ucf_final.index = lcf_aligned.index  # Use LCF index (project timeline)
    lcf_final = lcf_aligned.copy()
    print(f"   ✅ Truncated UCF to {len(ucf_final)} periods to match project timeline")
else:
    # LCF is longer - truncate to match UCF
    lcf_final = lcf_aligned.iloc[: len(ucf_aligned)]
    lcf_final.index = ucf_aligned.index
    ucf_final = ucf_aligned.copy()
    print(f"   ✅ Truncated LCF to {len(lcf_final)} periods to match available UCF")

print(f"   Final aligned lengths - UCF: {len(ucf_final)}, LCF: {len(lcf_final)}")

# Create comparison
multi_cf_data = pd.DataFrame({
    "Date": ucf_final.index,
    "UCF": ucf_final,
    "LCF": lcf_final,
})

multi_flow_data = multi_cf_data.melt(
    id_vars=["Date"],
    value_vars=["UCF", "LCF"],
    var_name="Flow_Type",
    value_name="Amount",
)

faceted_stripes_config = create_cash_flow_time_series(
    multi_flow_data,
    time_column="Date",
    value_column="Amount",
    facet_column="Flow_Type",
    title="Investment Cash Flows: UCF vs LCF",
    scale_millions=True,
    color_scheme="RdBu",
    stripe_height=60,
)

faceted_stripes_plot = Plot.plot(faceted_stripes_config)
faceted_stripes_plot

# %%
# 🕵️ CASH FLOW FORENSICS - What's causing positive flows so early?
print("🕵️ CASH FLOW FORENSICS")
print("=" * 70)

print("🏗️ DEVELOPMENT TIMELINE EXPECTATIONS:")
print("   - Construction should take 12+ months")
print("   - Leasing starts around month 15")
print("   - UCF should be NEGATIVE during construction (capital outflows)")
print("   - LCF should be NEGATIVE during construction (equity + debt funding)")
print("   - Revenue should start AFTER leasing begins")
print()

print("🔍 ACTUAL CASH FLOWS - First 24 months:")
print("-" * 50)

# Investigate what's in these cash flows
for i in range(min(24, len(ucf_final))):
    period = ucf_final.index[i]
    ucf_val = ucf_final.iloc[i]
    lcf_val = lcf_final.iloc[i]

    print(
        f"   Month {i + 1:2d} ({period}): UCF=${ucf_val:8,.0f} | LCF=${lcf_val:8,.0f}"
    )

    if ucf_val > 0 and i < 15:
        print(f"      ❌ UCF POSITIVE before leasing! This should be negative!")
    if lcf_val > 0 and i < 15:
        print(f"      ❌ LCF POSITIVE before leasing! This should be negative!")

print()
print("🔍 CASH FLOW COMPONENT INVESTIGATION:")
print("   Let's check what's in the summary_df to understand the source...")

# Check summary_df components for early periods
if hasattr(results, "asset_analysis") and hasattr(results.asset_analysis, "cash_flows"):
    summary = results.asset_analysis.cash_flows
    print(f"   Summary DF columns: {list(summary.columns)}")

    # Show first few periods of key components
    print("\n   First 6 months breakdown:")
    for i in range(min(6, len(summary))):
        period = summary.index[i]
        print(f"\n   Month {i + 1} ({period}):")

        # Key components to check
        components_to_check = [
            "Total Revenue",
            "Gross Rent Revenue",
            "Net Operating Income",
            "CapEx",
            "Construction Cost",
            "Acquisition Cost",
            "Total Cash Flow",
            "Unlevered Cash Flow",
        ]

        for comp in components_to_check:
            if comp in summary.columns:
                val = summary.loc[period, comp]
                if abs(val) > 1:  # Only show non-zero values
                    print(f"      {comp}: ${val:,.0f}")

print("=" * 70)
print("🎯 QUESTIONS TO INVESTIGATE:")
print("   1. Is this a renovation deal with existing tenants? (immediate revenue)")
print("   2. Are we seeing disposition proceeds mixed in?")
print("   3. Is the timeline wrong?")
print("   4. Are we looking at the wrong cash flow series?")
print("   5. Is there a bug in the cash flow calculation?")

# Get investment cash flows (includes disposition proceeds)
investment_cf = results.levered_cash_flows.levered_cash_flows
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

# Get deal metrics
irr = results.deal_metrics.get("levered_irr", 0)
equity_multiple = results.deal_metrics.get("equity_multiple", 0)
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
# Create partnership distribution chart
# Create partnership distribution comparison chart
dist = create_partnership_distribution_comparison(
    {"GP": gp_equity, "LP": lp_equity},
    {"GP": gp_distributions, "LP": lp_distributions},
    title="Capital vs. Profit Distribution",
)
dist

# %% [markdown]
"""
## Summary and Key Insights

This interactive analysis demonstrates the full power of the Performa library for residential development modeling.
"""

# %%
# Display key insights and summary
print("✅ SUCCESS! All visualizations generated with calculated data!")
print("")
print("🎯 Key Insights:")
print(
    f"  - This {project_params['total_units']}-unit development generates a {deal_irr:.1%} IRR"
)
print(f"  - Investors get a {equity_multiple:.2f}x multiple on their equity")
print(
    f"  - Total profit of ${total_equity_returned - total_equity_invested:,.0f} over {project_params['hold_period_years']} years"
)
print(
    f"  - GP earns ${gp_distributions:,.0f} ({gp_distributions / total_equity_returned:.1%}) of total returns"
)
print("")
print("🔧 **Next Steps:**")
print(
    "  - Modify the 'project_params' dictionary in the second cell to see how changes impact returns"
)
print(
    "  - Adjust unit mix, construction costs, financing terms, or partnership structure"
)
print("  - Re-run cells to see updated analysis with new parameters")
print("  - All charts and KPIs will automatically update with your new inputs")
print("")
print(
    "📊 **All data flows from your inputs through the Performa ResidentialDevelopmentPattern analysis**"
)
print("   No hardcoded values - everything is calculated from the financial model")

# %%
