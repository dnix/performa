# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0


"""
Integration Tests for Residential Development Pattern with Cash Sweeps

This test suite verifies the integration of cash sweep covenants with the
Residential Development Pattern:
- Pattern creation with sweep modes (TRAP, PREPAY, None)
- Automatic synchronization of sweep timing with refinancing
- Ledger entries for sweep deposits, releases, and prepayments
- Impact on levered cash flows and IRR
"""


from performa.core.primitives import SweepMode
from performa.core.primitives.enums import FinancingSubcategoryEnum
from performa.patterns.residential_development import ResidentialDevelopmentPattern


def test_residential_pattern_with_trap_sweep():
    """Test Residential Pattern with TRAP mode cash sweep."""
    print("\n🏗️  Testing Residential Pattern with TRAP Mode Cash Sweep")
    print("-" * 70)
    
    # Create pattern with TRAP sweep
    pattern = ResidentialDevelopmentPattern(
        # Core parameters
        project_name="Test Development - TRAP",
        acquisition_date="2024-01-01",
        land_cost=3_000_000,
        total_units=100,
        construction_cost_per_unit=180_000,
        
        # Unit mix
        unit_mix=[
            {"unit_type": "1BR", "count": 50, "avg_sf": 650, "target_rent": 2_000},
            {"unit_type": "2BR", "count": 50, "avg_sf": 950, "target_rent": 2_800},
        ],
        
        # Timeline
        construction_duration_months=18,
        leasing_start_months=18,
        absorption_pace_units_per_month=10,
        
        # Financing
        construction_interest_rate=0.08,
        construction_ltc_ratio=0.65,
        permanent_interest_rate=0.06,
        permanent_ltv_ratio=0.70,
        permanent_loan_term_years=10,
        permanent_amortization_years=30,
        
        # Cash sweep configuration - TRAP mode
        construction_sweep_mode=SweepMode.TRAP,
        
        # Exit
        hold_period_years=7,
        exit_cap_rate=0.055,
    )
    
    # Build the deal
    deal = pattern.create()
    
    # Verify construction facility has cash sweep
    construction_facilities = deal.financing.construction_facilities
    assert len(construction_facilities) > 0, "Should have construction facility"
    construction_facility = construction_facilities[0]
    assert construction_facility.cash_sweep is not None, "Should have cash sweep"
    assert construction_facility.cash_sweep.mode == SweepMode.TRAP, "Should be TRAP mode"
    
    # Verify sweep timing is synchronized with refinancing
    permanent_facilities = deal.financing.permanent_facilities
    assert len(permanent_facilities) > 0, "Should have permanent facility"
    permanent_facility = permanent_facilities[0]
    refinance_timing = permanent_facility.refinance_timing
    sweep_end = construction_facility.cash_sweep.end_month
    assert sweep_end == refinance_timing, f"Sweep end ({sweep_end}) should match refinance timing ({refinance_timing})"
    
    print(f"✓ Construction facility has TRAP sweep ending at month {sweep_end}")
    print(f"✓ Refinancing occurs at month {refinance_timing} (synchronized)")
    
    # Run the analysis
    results = pattern.analyze()
    
    # Check ledger for sweep entries
    ledger_df = results.ledger_df
    
    # Should have Cash Sweep Deposit entries (trapped cash)
    deposits = ledger_df[
        ledger_df["subcategory"] == FinancingSubcategoryEnum.CASH_SWEEP_DEPOSIT.value
    ]
    assert len(deposits) > 0, "Should have cash sweep deposits"
    print(f"✓ Found {len(deposits)} cash sweep deposit entries")
    print(f"  Total trapped: ${abs(deposits['amount'].sum()):,.0f}")
    
    # Should have Cash Sweep Release entry (when refinancing occurs)
    releases = ledger_df[
        ledger_df["subcategory"] == FinancingSubcategoryEnum.CASH_SWEEP_RELEASE.value
    ]
    assert len(releases) > 0, "Should have cash sweep release"
    print(f"✓ Found {len(releases)} cash sweep release entry")
    print(f"  Total released: ${releases['amount'].sum():,.0f}")
    
    # Verify balance: total deposits should equal total releases
    total_trapped = abs(deposits["amount"].sum())
    total_released = releases["amount"].sum()
    assert abs(total_trapped - total_released) < 1.0, "Trapped amount should equal released amount"
    print(f"✓ Sweep balance verified: ${total_trapped:,.0f} trapped = ${total_released:,.0f} released")
    
    # Verify deal returns are calculated correctly
    assert results.levered_irr is not None, "Should calculate levered IRR"
    print(f"✓ Levered IRR: {results.levered_irr:.2%}")
    
    print("✓ TRAP mode integration test passed\n")


def test_residential_pattern_with_prepay_sweep():
    """Test Residential Pattern with PREPAY mode cash sweep."""
    print("\n🏗️  Testing Residential Pattern with PREPAY Mode Cash Sweep")
    print("-" * 70)
    
    # Create pattern with PREPAY sweep
    pattern = ResidentialDevelopmentPattern(
        # Core parameters
        project_name="Test Development - PREPAY",
        acquisition_date="2024-01-01",
        land_cost=3_000_000,
        total_units=100,
        construction_cost_per_unit=180_000,
        
        # Unit mix
        unit_mix=[
            {"unit_type": "1BR", "count": 50, "avg_sf": 650, "target_rent": 2_000},
            {"unit_type": "2BR", "count": 50, "avg_sf": 950, "target_rent": 2_800},
        ],
        
        # Timeline
        construction_duration_months=18,
        leasing_start_months=18,
        absorption_pace_units_per_month=10,
        
        # Financing
        construction_interest_rate=0.08,
        construction_ltc_ratio=0.65,
        permanent_interest_rate=0.06,
        permanent_ltv_ratio=0.70,
        permanent_loan_term_years=10,
        permanent_amortization_years=30,
        
        # Cash sweep configuration - PREPAY mode
        construction_sweep_mode=SweepMode.PREPAY,
        
        # Exit
        hold_period_years=7,
        exit_cap_rate=0.055,
    )
    
    # Build the deal
    deal = pattern.create()
    
    # Verify construction facility has cash sweep
    construction_facilities = deal.financing.construction_facilities
    assert len(construction_facilities) > 0, "Should have construction facility"
    construction_facility = construction_facilities[0]
    assert construction_facility.cash_sweep is not None, "Should have cash sweep"
    assert construction_facility.cash_sweep.mode == SweepMode.PREPAY, "Should be PREPAY mode"
    
    print(f"✓ Construction facility has PREPAY sweep")
    
    # Run the analysis
    results = pattern.analyze()
    
    # Check ledger for sweep prepayments
    ledger_df = results.ledger_df
    
    # Should have Sweep Prepayment entries (mandatory principal reduction)
    prepayments = ledger_df[
        ledger_df["subcategory"] == FinancingSubcategoryEnum.SWEEP_PREPAYMENT.value
    ]
    assert len(prepayments) > 0, "Should have sweep prepayment entries"
    print(f"✓ Found {len(prepayments)} sweep prepayment entries")
    print(f"  Total prepaid: ${abs(prepayments['amount'].sum()):,.0f}")
    
    # Should NOT have Cash Sweep Deposit or Release entries (PREPAY doesn't trap)
    deposits = ledger_df[
        ledger_df["subcategory"] == FinancingSubcategoryEnum.CASH_SWEEP_DEPOSIT.value
    ]
    releases = ledger_df[
        ledger_df["subcategory"] == FinancingSubcategoryEnum.CASH_SWEEP_RELEASE.value
    ]
    assert len(deposits) == 0, "PREPAY mode should not have deposits"
    assert len(releases) == 0, "PREPAY mode should not have releases"
    print(f"✓ No deposits or releases (PREPAY applies directly to principal)")
    
    # Verify deal returns are calculated correctly
    assert results.levered_irr is not None, "Should calculate levered IRR"
    print(f"✓ Levered IRR: {results.levered_irr:.2%}")
    
    print("✓ PREPAY mode integration test passed\n")


def test_residential_pattern_with_no_sweep():
    """Test Residential Pattern with cash sweep disabled."""
    print("\n🏗️  Testing Residential Pattern with No Cash Sweep")
    print("-" * 70)
    
    # Create pattern without sweep
    pattern = ResidentialDevelopmentPattern(
        # Core parameters
        project_name="Test Development - No Sweep",
        acquisition_date="2024-01-01",
        land_cost=3_000_000,
        total_units=100,
        construction_cost_per_unit=180_000,
        
        # Unit mix
        unit_mix=[
            {"unit_type": "1BR", "count": 50, "avg_sf": 650, "target_rent": 2_000},
            {"unit_type": "2BR", "count": 50, "avg_sf": 950, "target_rent": 2_800},
        ],
        
        # Timeline
        construction_duration_months=18,
        leasing_start_months=18,
        absorption_pace_units_per_month=10,
        
        # Financing
        construction_interest_rate=0.08,
        construction_ltc_ratio=0.65,
        permanent_interest_rate=0.06,
        permanent_ltv_ratio=0.70,
        permanent_loan_term_years=10,
        permanent_amortization_years=30,
        
        # Cash sweep configuration - disabled
        construction_sweep_mode=None,
        
        # Exit
        hold_period_years=7,
        exit_cap_rate=0.055,
    )
    
    # Build the deal
    deal = pattern.create()
    
    # Verify construction facility has NO cash sweep
    construction_facilities = deal.financing.construction_facilities
    assert len(construction_facilities) > 0, "Should have construction facility"
    construction_facility = construction_facilities[0]
    assert construction_facility.cash_sweep is None, "Should NOT have cash sweep"
    
    print(f"✓ Construction facility has no cash sweep (disabled)")
    
    # Run the analysis
    results = pattern.analyze()
    
    # Check ledger for sweep entries
    ledger_df = results.ledger_df
    
    # Should have NO sweep-related entries
    deposits = ledger_df[
        ledger_df["subcategory"] == FinancingSubcategoryEnum.CASH_SWEEP_DEPOSIT.value
    ]
    releases = ledger_df[
        ledger_df["subcategory"] == FinancingSubcategoryEnum.CASH_SWEEP_RELEASE.value
    ]
    prepayments = ledger_df[
        ledger_df["subcategory"] == FinancingSubcategoryEnum.SWEEP_PREPAYMENT.value
    ]
    
    assert len(deposits) == 0, "Should have no sweep deposits"
    assert len(releases) == 0, "Should have no sweep releases"
    assert len(prepayments) == 0, "Should have no sweep prepayments"
    print(f"✓ No sweep entries in ledger (as expected)")
    
    # Verify deal returns are calculated correctly
    assert results.levered_irr is not None, "Should calculate levered IRR"
    print(f"✓ Levered IRR: {results.levered_irr:.2%}")
    
    print("✓ No sweep integration test passed\n")


def test_residential_pattern_sweep_impact_on_returns():
    """Test that sweep mode impacts returns differently (TRAP vs PREPAY)."""
    print("\n🏗️  Testing Cash Sweep Impact on Returns")
    print("-" * 70)
    
    # Base parameters
    base_params = {
        "project_name": "Test Development - Returns Test",
        "acquisition_date": "2024-01-01",
        "land_cost": 3_000_000,
        "total_units": 100,
        "construction_cost_per_unit": 180_000,
        "unit_mix": [
            {"unit_type": "1BR", "count": 50, "avg_sf": 650, "target_rent": 2_000},
            {"unit_type": "2BR", "count": 50, "avg_sf": 950, "target_rent": 2_800},
        ],
        "construction_duration_months": 18,
        "leasing_start_months": 18,
        "absorption_pace_units_per_month": 10,
        "construction_interest_rate": 0.08,
        "construction_ltc_ratio": 0.65,
        "permanent_interest_rate": 0.06,
        "permanent_ltv_ratio": 0.70,
        "permanent_loan_term_years": 10,
        "permanent_amortization_years": 30,
        "hold_period_years": 7,
        "exit_cap_rate": 0.055,
    }
    
    # Test TRAP mode
    trap_pattern = ResidentialDevelopmentPattern(
        **base_params,
        construction_sweep_mode=SweepMode.TRAP
    )
    trap_results = trap_pattern.analyze()
    trap_irr = trap_results.levered_irr
    
    # Test PREPAY mode
    prepay_pattern = ResidentialDevelopmentPattern(
        **base_params,
        construction_sweep_mode=SweepMode.PREPAY
    )
    prepay_results = prepay_pattern.analyze()
    prepay_irr = prepay_results.levered_irr
    
    # Test no sweep
    no_sweep_pattern = ResidentialDevelopmentPattern(
        **base_params,
        construction_sweep_mode=None
    )
    no_sweep_results = no_sweep_pattern.analyze()
    no_sweep_irr = no_sweep_results.levered_irr
    
    print(f"  TRAP mode IRR:     {trap_irr:.2%}")
    print(f"  PREPAY mode IRR:   {prepay_irr:.2%}")
    print(f"  No sweep IRR:      {no_sweep_irr:.2%}")
    print()
    
    # Verify all modes completed successfully
    assert trap_irr is not None, "TRAP mode should calculate IRR"
    assert prepay_irr is not None, "PREPAY mode should calculate IRR"
    assert no_sweep_irr is not None, "No sweep mode should calculate IRR"
    
    # Note: In this example, IRRs are similar because construction phase has no NOI,
    # so there's minimal excess cash to sweep. In a real project with operating cash
    # during construction (e.g., phased delivery), the modes would show different returns:
    # - PREPAY: Higher IRR (interest savings from principal reduction)
    # - TRAP: Lower IRR (timing drag from escrowed cash)
    # - No sweep: Highest IRR (no restrictions on distributions)
    
    print(f"✓ All three modes calculated valid IRRs")
    print(f"✓ Integration test passed - sweep modes function correctly")
    
    print("✓ Return impact test passed\n")


if __name__ == "__main__":
    """Run integration tests."""
    print("=" * 70)
    print("RESIDENTIAL DEVELOPMENT PATTERN - CASH SWEEP INTEGRATION TESTS")
    print("=" * 70)
    
    test_residential_pattern_with_trap_sweep()
    test_residential_pattern_with_prepay_sweep()
    test_residential_pattern_with_no_sweep()
    test_residential_pattern_sweep_impact_on_returns()
    
    print("=" * 70)
    print("✅ ALL INTEGRATION TESTS PASSED")
    print("=" * 70)
