#!/usr/bin/env python3
# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

# %% [markdown]
"""
# Residential Development Validation & Debugging

Internal notebook for validating ResidentialDevelopmentPattern implementation
and debugging deal analysis issues.

This notebook contains comprehensive validation patterns for:
- DealResults API completeness
- Cash flow sign conventions
- Ledger transaction integrity
- Partnership waterfall mechanics
- Debt facility behavior

**Purpose**: Internal testing and debugging, not user-facing documentation.
"""

# %%
# Import libraries and setup
from datetime import date

import pandas as pd

from performa.patterns import ResidentialDevelopmentPattern
from performa.reporting import (
    analyze_ledger_semantically,
    dump_performa_object,
    validate_flow_reasonableness,
)

print("✅ Validation utilities loaded")
print("")

# %%
# Create test pattern with standard parameters
print("🔧 Creating test pattern...")

pattern = ResidentialDevelopmentPattern(
    project_name="Test Development",
    acquisition_date=date(2024, 1, 15),
    land_cost=3_500_000,
    total_units=120,
    unit_mix=[
        {"unit_type": "1BR", "count": 60, "avg_sf": 750, "target_rent": 2100},
        {"unit_type": "2BR", "count": 40, "avg_sf": 1050, "target_rent": 2800},
        {"unit_type": "Studio", "count": 20, "avg_sf": 500, "target_rent": 1600},
    ],
    construction_cost_per_unit=160_000,
    construction_duration_months=18,
    leasing_start_months=15,
    absorption_pace_units_per_month=8,
    construction_ltc_ratio=0.70,
    construction_interest_rate=0.065,
    permanent_ltv_ratio=0.65,
    permanent_interest_rate=0.065,
    permanent_loan_term_years=10,
    permanent_amortization_years=25,
    gp_share=0.10,
    preferred_return=0.08,
    promote_tier_1=0.20,
    hold_period_years=7,
    exit_cap_rate=0.055,
)

print("✅ Pattern created")
print(f"   Project: {pattern.project_name}")
print(f"   Units: {pattern.total_units}")
print("")

# %%
# Run analysis
print("⚡ Running analysis...")
results = pattern.analyze()
print("✅ Analysis complete")
print("")

# %%
# VALIDATION 1: DealResults API Completeness Check
print("=" * 80)
print("VALIDATION 1: DealResults API COMPLETENESS")
print("=" * 80)
print("")

# Test all primary metrics
metrics_to_test = [
    "levered_irr",
    "equity_multiple",
    "net_profit",
    "unlevered_irr",
    "unlevered_return_on_cost",
]

print("📊 Primary Metrics:")
for metric in metrics_to_test:
    value = getattr(results, metric, None)
    if value is not None:
        if isinstance(value, float):
            print(f"   ✅ {metric}: {value:.4f}")
        else:
            print(f"   ✅ {metric}: {value}")
    else:
        print(f"   ❌ {metric}: None")

print("")

# Test all time series
time_series_to_test = [
    "levered_cash_flow",
    "unlevered_cash_flow",
    "equity_cash_flow",
    "noi",
    "operational_cash_flow",
    "debt_service",
]

print("📈 Time Series:")
for series_name in time_series_to_test:
    series = getattr(results, series_name, None)
    if series is not None and not series.empty:
        print(f"   ✅ {series_name}: {len(series)} periods, sum=${series.sum():,.0f}")
    else:
        print(f"   ❌ {series_name}: Empty or None")

print("")

# Test debt metrics
debt_metrics = ["stabilized_dscr", "minimum_operating_dscr", "covenant_compliance_rate"]

print("🏦 Debt Metrics:")
for metric in debt_metrics:
    value = getattr(results, metric, None)
    if value is not None:
        print(f"   ✅ {metric}: {value:.4f}")
    else:
        print(f"   ⚠️  {metric}: None (may not apply to this deal)")

print("")

# Test dictionaries
dict_properties = ["partners", "deal_metrics", "financing_analysis"]

print("📋 Dictionary Properties:")
for prop_name in dict_properties:
    prop = getattr(results, prop_name, None)
    if prop is not None:
        if isinstance(prop, dict):
            print(f"   ✅ {prop_name}: {len(prop)} keys")
        else:
            print(f"   ✅ {prop_name}: {type(prop).__name__}")
    else:
        print(f"   ⚠️  {prop_name}: None")

print("\n" + "=" * 80 + "\n")

# %%
# VALIDATION 2: Cash Flow Sign Convention Check
print("=" * 80)
print("VALIDATION 2: CASH FLOW SIGN CONVENTIONS")
print("=" * 80)
print("")

# Get cash flows
ucf = results.unlevered_cash_flow
lcf = results.levered_cash_flow
ecf = results.equity_cash_flow

print("🔍 Sign Convention Check:")
print("")

# Check construction period (derive from pattern)
construction_periods = int(pattern.construction_duration_months)
ucf_construction = ucf.iloc[:construction_periods]
ucf_negative_pct = (ucf_construction < 0).sum() / len(ucf_construction)

print(f"Construction Period Analysis (first {construction_periods} months):")
print(
    f"   UCF negative periods: {(ucf_construction < 0).sum()} / {len(ucf_construction)}"
)
print(f"   Negative percentage: {ucf_negative_pct:.1%}")

if ucf_negative_pct > 0.50:
    print("   ✅ PASS: Majority of construction period shows negative UCF (expected)")
else:
    print("   ⚠️  WARN: Less than 50% negative UCF during construction (investigate)")

print("")

# Check equity cash flow signs
ecf_contributions = ecf[ecf > 0].sum()
ecf_distributions = ecf[ecf < 0].sum()

print(f"Equity Cash Flow Analysis:")
print(f"   Contributions (positive): ${ecf_contributions:,.0f}")
print(f"   Distributions (negative): ${ecf_distributions:,.0f}")
print(f"   Net: ${ecf.sum():,.0f}")

if ecf_contributions > 0 and ecf_distributions < 0:
    print("   ✅ PASS: Equity cash flows show correct signs")
else:
    print("   ❌ FAIL: Equity cash flow signs are incorrect")

print("\n" + "=" * 80 + "\n")

# %%
# VALIDATION 3: Ledger Integrity Check
print("=" * 80)
print("VALIDATION 3: LEDGER INTEGRITY")
print("=" * 80)
print("")

ledger_df = results.ledger_df

print(f"📖 Ledger Stats:")
print(f"   Total transactions: {len(ledger_df):,}")
print(f"   Date range: {ledger_df['date'].min()} to {ledger_df['date'].max()}")
print(f"   Net balance: ${ledger_df['amount'].sum():,.0f}")
print(f"   Categories: {ledger_df['category'].nunique()}")
print(f"   Subcategories: {ledger_df['subcategory'].nunique()}")
print("")

# Run semantic analysis
ledger_analysis = analyze_ledger_semantically(results.ledger)

print("🔍 Semantic Analysis:")
balance_checks = ledger_analysis["balance_checks"]
print(f"   Total inflows: ${balance_checks['total_inflows']:,.0f}")
print(f"   Total outflows: ${balance_checks['total_outflows']:,.0f}")
print(f"   Net flow: ${balance_checks['total_net_flow']:,.0f}")
print("")

# Category breakdown
print("📊 Top Categories by Absolute Amount:")
category_totals = (
    ledger_df.groupby("category")["amount"].sum().abs().sort_values(ascending=False)
)
for category, amount in category_totals.head(10).items():
    actual_amount = ledger_df[ledger_df["category"] == category]["amount"].sum()
    print(f"   {category:20}: ${actual_amount:>15,.0f}")

print("\n" + "=" * 80 + "\n")

# %%
# VALIDATION 4: Partnership Waterfall Mechanics
print("=" * 80)
print("VALIDATION 4: PARTNERSHIP WATERFALL MECHANICS")
print("=" * 80)
print("")

partners = results.partners

print("🤝 Partner Analysis:")
for partner_id, partner_metrics in partners.items():
    print(f"\n   {partner_metrics.partner_name}:")
    print(f"      Ownership: {partner_metrics.ownership_share:.1%}")
    print(f"      Entity type: {partner_metrics.entity_type}")

    # Calculate contributions and distributions
    cf = partner_metrics.cash_flow
    contributions = abs(cf[cf < 0].sum())
    distributions = cf[cf > 0].sum()

    print(f"      Contributions: ${contributions:,.0f}")
    print(f"      Distributions: ${distributions:,.0f}")
    print(f"      Net profit: ${partner_metrics.net_profit:,.0f}")

    if partner_metrics.irr is not None:
        print(f"      IRR: {partner_metrics.irr:.2%}")
    if partner_metrics.equity_multiple is not None:
        print(f"      Equity multiple: {partner_metrics.equity_multiple:.2f}x")

print("")

# Check waterfall mechanics
deal_metrics = results.deal_metrics
total_profit = deal_metrics["net_profit"]
partner_profits = sum(p.net_profit for p in partners.values())

print(f"🔍 Waterfall Integrity Check:")
print(f"   Deal total profit: ${total_profit:,.0f}")
print(f"   Partner profits sum: ${partner_profits:,.0f}")
print(f"   Difference: ${abs(total_profit - partner_profits):,.0f}")

if abs(total_profit - partner_profits) < 10:  # Allow $10 rounding error
    print("   ✅ PASS: Partnership waterfall balances correctly")
else:
    print("   ❌ FAIL: Partnership waterfall has imbalance")

print("\n" + "=" * 80 + "\n")

# %%
# VALIDATION 5: Debt Facility Behavior
print("=" * 80)
print("VALIDATION 5: DEBT FACILITY BEHAVIOR")
print("=" * 80)
print("")

financing = results.financing_analysis

if financing and financing.get("has_financing"):
    print("🏦 Financing Analysis:")
    print(f"   Has financing: True")
    print(f"   Total debt service: ${financing.get('total_debt_service', 0):,.0f}")
    print("")

    # Check debt service series
    debt_service = results.debt_service
    if not debt_service.empty:
        print(f"📊 Debt Service Pattern:")
        print(f"   Total periods: {len(debt_service)}")
        print(f"   Total debt service: ${debt_service.sum():,.0f}")
        print(f"   Average per period: ${debt_service.mean():,.0f}")
        print(f"   Max period: ${debt_service.max():,.0f}")
        print(f"   Min period: ${debt_service.min():,.0f}")
        print("")

        # Check for construction vs permanent debt patterns
        construction_mask = debt_service.index < pd.Period("2025-07", freq="M")
        construction_ds = debt_service[construction_mask]
        permanent_ds = debt_service[~construction_mask]

        if not construction_ds.empty:
            print(f"   Construction phase debt service:")
            print(f"      Periods: {len(construction_ds)}")
            print(f"      Total: ${construction_ds.sum():,.0f}")
            print(f"      Average: ${construction_ds.mean():,.0f}")

        if not permanent_ds.empty:
            print(f"   Permanent phase debt service:")
            print(f"      Periods: {len(permanent_ds)}")
            print(f"      Total: ${permanent_ds.sum():,.0f}")
            print(f"      Average: ${permanent_ds.mean():,.0f}")

    print("")

    # DSCR analysis
    if results.stabilized_dscr:
        print(f"📈 DSCR Metrics:")
        print(f"   Stabilized DSCR: {results.stabilized_dscr:.2f}x")
        print(f"   Minimum operating DSCR: {results.minimum_operating_dscr:.2f}x")
        print(f"   Covenant compliance: {results.covenant_compliance_rate:.1%}")

        if results.stabilized_dscr >= 1.25:
            print("   ✅ PASS: Stabilized DSCR meets typical lender requirements")
        else:
            print("   ⚠️  WARN: Stabilized DSCR below typical 1.25x threshold")
else:
    print("ℹ️  No financing in this deal")

print("\n" + "=" * 80 + "\n")

# %%
# VALIDATION 6: Configuration Introspection
print("=" * 80)
print("VALIDATION 6: CONFIGURATION INTROSPECTION")
print("=" * 80)
print("")

# Dump non-default configuration
config = dump_performa_object(pattern, exclude_defaults=True)

print(f"⚙️  Non-default Configuration:")
print(f"   Total non-default parameters: {len(config)}")
print("")

# Group by category
config_by_prefix = {}
for key in config.keys():
    prefix = key.split("_")[0] if "_" in key else "other"
    if prefix not in config_by_prefix:
        config_by_prefix[prefix] = []
    config_by_prefix[prefix].append(key)

for prefix, keys in sorted(config_by_prefix.items()):
    print(f"   {prefix}: {len(keys)} parameters")

print("\n" + "=" * 80 + "\n")

# %%
# VALIDATION 7: Flow Reasonableness Check
print("=" * 80)
print("VALIDATION 7: FLOW REASONABLENESS")
print("=" * 80)
print("")

# Use validation utility to check flow reasonableness
try:
    reasonableness = validate_flow_reasonableness(results)

    print("🔍 Reasonableness Checks:")

    for check_name, check_result in reasonableness.items():
        status = "✅" if check_result.get("passed", False) else "⚠️"
        print(f"   {status} {check_name}: {check_result.get('message', 'No message')}")

    print("")

    # Overall verdict
    all_passed = all(r.get("passed", False) for r in reasonableness.values())
    if all_passed:
        print("✅ OVERALL: All reasonableness checks passed")
    else:
        failed_count = sum(
            1 for r in reasonableness.values() if not r.get("passed", False)
        )
        print(f"⚠️  OVERALL: {failed_count} check(s) require attention")

except Exception as e:
    print(f"❌ Could not run reasonableness checks: {e}")

print("\n" + "=" * 80 + "\n")

# %%
# Final Summary
print("=" * 80)
print("VALIDATION SUMMARY")
print("=" * 80)
print("")

print("📋 Validation Steps Completed:")
print("   1. ✅ DealResults API completeness")
print("   2. ✅ Cash flow sign conventions")
print("   3. ✅ Ledger integrity")
print("   4. ✅ Partnership waterfall mechanics")
print("   5. ✅ Debt facility behavior")
print("   6. ✅ Configuration introspection")
print("   7. ✅ Flow reasonableness")
print("")

print("💡 Next Steps:")
print("   • Review any warnings flagged above")
print("   • Compare metrics against industry benchmarks")
print("   • Test edge cases (high leverage, long hold, etc.)")
print("   • Validate against external models (Argus, Excel)")
print("")

# %%
