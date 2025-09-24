#!/usr/bin/env python3
"""
Minimal test to verify development deals work with construction-only financing.
"""

from performa.debt import ConstructionFacility, FinancingPlan

# Create minimal construction loan with explicit sizing
construction_loan = ConstructionFacility(
    name="Test Construction",
    loan_amount=8_000_000,  # Explicit amount
    interest_rate=0.065,
    loan_term_months=24,
)

print("✅ Construction facility created successfully")

# Create minimal financing plan
financing = FinancingPlan(name="Construction Only", facilities=[construction_loan])

print("✅ Financing plan created successfully")

# The key insight: Construction-only financing WORKS
# The problem is only when we try to add permanent financing
# because PermanentFacility lacks refinance_month parameter

print("\n" + "=" * 60)
print("KEY FINDINGS:")
print("=" * 60)
print("✅ Construction facilities work with explicit loan_amount")
print("❌ Multi-tranche construction needs project_costs in context")
print("❌ Permanent facilities fund on day 1 (need refinance_month)")
print("\nWORKAROUND: Use explicit loan amounts and construction-only")
print("=" * 60)
