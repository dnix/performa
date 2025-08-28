#!/usr/bin/env python3
"""
Working example of office development using manual assembly.

This demonstrates how to create a development deal that WORKS with the current
library limitations. Uses construction-only financing to avoid the permanent
loan timing issue.
"""

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
from performa.core.ledger import Ledger
from performa.core.primitives import (
    AssetTypeEnum,
    FirstOnlyDrawSchedule,
    ProgramUseEnum,
    PropertyAttributeKey,
    Timeline,
    UponExpirationEnum,
)
from performa.deal import (
    AcquisitionTerms,
    Deal,
    Partner,
    PartnershipStructure,
    analyze,
)
from performa.debt import ConstructionFacility, FinancingPlan
from performa.development import DevelopmentProject
from performa.valuation import DirectCapValuation

# === PROJECT PARAMETERS ===
PROJECT_NAME = "Working Office Tower"
ACQUISITION_DATE = date(2024, 1, 1)
LAND_COST = 2_000_000
NRA = 30_000  # Net rentable area
FLOORS = 3
TARGET_RENT_PSF = 45.0  # Annual $/SF
CONSTRUCTION_COST_PSF = 266.67
HOLD_YEARS = 5
EXIT_CAP_RATE = 0.055

# === CALCULATED VALUES ===
GROSS_AREA = NRA * 1.11  # 11% circulation
HARD_COSTS = GROSS_AREA * CONSTRUCTION_COST_PSF
SOFT_COSTS = HARD_COSTS * 0.15  # 15% of hard costs
DEVELOPER_FEE = (HARD_COSTS + SOFT_COSTS) * 0.045  # 4.5% of costs
TOTAL_CONSTRUCTION = HARD_COSTS + SOFT_COSTS + DEVELOPER_FEE
TOTAL_PROJECT_COST = LAND_COST + TOTAL_CONSTRUCTION

print("=" * 60)
print(f"{PROJECT_NAME} - Manual Assembly Example")
print("=" * 60)
print(f"\n📊 PROJECT ECONOMICS:")
print(f"  Land: ${LAND_COST:,.0f}")
print(f"  Hard Construction: ${HARD_COSTS:,.0f}")
print(f"  Soft Costs: ${SOFT_COSTS:,.0f}")
print(f"  Developer Fee: ${DEVELOPER_FEE:,.0f}")
print(f"  Total Project: ${TOTAL_PROJECT_COST:,.0f}")

# === STEP 1: TIMELINE ===
timeline = Timeline(
    start_date=ACQUISITION_DATE,
    duration_months=HOLD_YEARS * 12 + 6,  # Add buffer for exit
)

# === STEP 2: CONSTRUCTION PLAN ===
capital_items = [
    CapitalItem(
        name="Property Acquisition",
        value=LAND_COST,
        draw_schedule=FirstOnlyDrawSchedule(),
        timeline=timeline,
    ),
    CapitalItem(
        name="Construction - Core & Shell",
        value=HARD_COSTS,
        draw_schedule=FirstOnlyDrawSchedule(),
        timeline=timeline,
    ),
    CapitalItem(
        name="Professional Fees",
        value=SOFT_COSTS,
        draw_schedule=FirstOnlyDrawSchedule(),
        timeline=timeline,
    ),
    CapitalItem(
        name="Developer Fee",
        value=DEVELOPER_FEE,
        draw_schedule=FirstOnlyDrawSchedule(),
        timeline=timeline,
    ),
]

capital_plan = CapitalPlan(
    name=f"{PROJECT_NAME} Construction Plan", capital_items=capital_items
)

# === STEP 3: OFFICE INVENTORY ===
vacant_suites = []
floor_size = NRA / FLOORS

for floor_num in range(1, FLOORS + 1):
    suite = OfficeVacantSuite(
        suite=f"Floor {floor_num}",
        floor=str(floor_num),
        use_type=ProgramUseEnum.OFFICE,
        area=floor_size,
        subdivision_minimum_lease_area=1000.0,
        subdivision_average_lease_area=floor_size / 3,
    )
    vacant_suites.append(suite)

# === STEP 4: ABSORPTION PLAN ===
# Use factory method for simplicity
absorption_plan = OfficeAbsorptionPlan.with_typical_assumptions(
    name=f"{PROJECT_NAME} Lease-Up",
    space_filter=SpaceFilter(floors=["1", "2", "3"], use_types=[ProgramUseEnum.OFFICE]),
    start_date_anchor=date(2025, 1, 1),  # Start leasing 12 months after acquisition
    pace=EqualSpreadPace(total_deals=12, frequency_months=1),  # 12 monthly deals
    leasing_assumptions=DirectLeaseTerms(
        base_rent_value=TARGET_RENT_PSF / 12,  # Convert annual to monthly
        base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
        term_months=84,  # 7-year leases
        upon_expiration=UponExpirationEnum.MARKET,
    ),
)

# === STEP 5: DEVELOPMENT BLUEPRINT ===
office_blueprint = OfficeDevelopmentBlueprint(
    name=f"{PROJECT_NAME} Office Component",
    vacant_inventory=vacant_suites,
    absorption_plan=absorption_plan,
)

# === STEP 6: DEVELOPMENT PROJECT ===
project = DevelopmentProject(
    name=f"{PROJECT_NAME} Development",
    property_type=AssetTypeEnum.OFFICE,
    gross_area=GROSS_AREA,
    net_rentable_area=NRA,
    construction_plan=capital_plan,
    blueprints=[office_blueprint],
)

# === STEP 7: ACQUISITION ===
acquisition = AcquisitionTerms(
    name="Land Acquisition",
    timeline=Timeline(start_date=ACQUISITION_DATE, duration_months=1),
    value=LAND_COST,
    acquisition_date=ACQUISITION_DATE,
    closing_costs_rate=0.025,  # 2.5% closing costs
)

# === STEP 8: FINANCING (CONSTRUCTION ONLY) ===
# Using explicit loan_amount to avoid project_costs issue
CONSTRUCTION_LTC = 0.65
CONSTRUCTION_LOAN_AMOUNT = TOTAL_PROJECT_COST * CONSTRUCTION_LTC

construction_loan = ConstructionFacility(
    name="Construction Loan",
    loan_amount=CONSTRUCTION_LOAN_AMOUNT,
    interest_rate=0.065,
    loan_term_months=24,
    interest_reserve_rate=0.10,
)

financing = FinancingPlan(
    name="Construction-Only Financing", facilities=[construction_loan]
)

print(f"\n💰 FINANCING:")
print(f"  Construction Loan (65% LTC): ${CONSTRUCTION_LOAN_AMOUNT:,.0f}")
print(f"  Required Equity (35%): ${TOTAL_PROJECT_COST - CONSTRUCTION_LOAN_AMOUNT:,.0f}")

# === STEP 9: PARTNERSHIP ===
gp_partner = Partner(name="Development GP", kind="GP", share=0.20)
lp_partner = Partner(name="Institutional LP", kind="LP", share=0.80)

partnership = PartnershipStructure(
    name=f"{PROJECT_NAME} Partnership",
    partners=[gp_partner, lp_partner],
)

# === STEP 10: EXIT STRATEGY ===
reversion = DirectCapValuation(
    name="Exit Sale",
    cap_rate=EXIT_CAP_RATE,
    transaction_costs_rate=0.03,  # 3% transaction costs (renamed from exit_costs_rate)
    hold_period_months=HOLD_YEARS * 12,
    noi_basis_kind="LTM",  # Use trailing 12 months
)

# === STEP 11: CREATE DEAL ===
deal = Deal(
    name=PROJECT_NAME,
    asset=project,
    acquisition=acquisition,
    financing=financing,
    equity_partners=partnership,
    exit_valuation=reversion,
)

# === STEP 12: RUN ANALYSIS ===
ledger = Ledger()
results = analyze(deal=deal, timeline=timeline, ledger=ledger)

# === STEP 13: SHOW RESULTS ===
print(f"\n📈 RESULTS:")
if results.deal_metrics:
    em = results.deal_metrics.equity_multiple
    irr = results.deal_metrics.irr

    print(f"  Equity Multiple: {em:.2f}x")
    if irr:
        print(f"  IRR: {irr:.1%}")
    print(f"  Total Invested: ${results.deal_metrics.total_equity_invested:,.0f}")
    print(f"  Total Returned: ${results.deal_metrics.total_equity_returned:,.0f}")

    # Check if reasonable
    if 1.2 <= em <= 1.8:
        print(f"\n✅ Returns are reasonable for construction-only financing")
        print("  (Would be higher with permanent loan refinancing)")
    else:
        print(f"\n⚠️ Returns: {em:.2f}x")

# Check ledger
df = ledger._to_dataframe()
exit_proceeds = df[df["item_name"] == "Exit Sale Proceeds"]["amount"].sum()
if exit_proceeds > 0:
    print(f"\n🏁 EXIT:")
    print(f"  Exit proceeds in ledger: ${exit_proceeds:,.0f}")

    # Calculate implied exit value
    implied_cap_rate = EXIT_CAP_RATE
    implied_noi = exit_proceeds * implied_cap_rate / (1 - 0.03)  # Adjust for exit costs
    print(f"  Implied NOI at exit: ${implied_noi:,.0f}/year")

print("\n" + "=" * 60)
print("✅ This example demonstrates a WORKING development deal")
print("   using manual assembly with construction-only financing.")
print("   Once refinance_month is added to PermanentFacility,")
print("   permanent loan refinancing can be included.")
print("=" * 60)
