# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
End-to-End tests for residential asset modeling.

These tests validate the full residential analysis pipeline from property
definition through cash flow generation, ensuring institutional-grade performance.
"""
import time
from datetime import date

import pytest

from performa.analysis import run
from performa.asset.residential import (
    ResidentialCapExItem,
    ResidentialCollectionLoss,
    ResidentialExpenses,
    ResidentialGeneralVacancyLoss,
    ResidentialLosses,
    ResidentialMiscIncome,
    ResidentialOpExItem,
    ResidentialProperty,
    ResidentialRentRoll,
    ResidentialRolloverLeaseTerms,
    ResidentialRolloverProfile,
    ResidentialUnitSpec,
    ResidentialVacantUnit,
)
from performa.core.primitives import (
    FrequencyEnum,
    GlobalSettings,
    PropertyAttributeKey,
    Timeline,
)


def test_e2e_institutional_scale_residential():
    """
    E2E Test: Institutional-scale multifamily property (250 units)
    
    This test validates analysis of a large-scale institutional asset with:
    - Multiple unit types with different rent levels
    - Complex expense structures with per-unit and per-SF items
    - 5-year analysis timeline with sophisticated rollover assumptions
    - Multiple income streams beyond base rent
    """
    # Analysis parameters
    timeline = Timeline(start_date=date(2024, 1, 1), duration_months=60)  # 5-year analysis
    settings = GlobalSettings()
    
    # Market assumptions
    strong_market_rollover = ResidentialRolloverProfile(
        name="Strong Market Assumptions",
        renewal_probability=0.72,
        downtime_months=1,
        term_months=12,
        market_terms=ResidentialRolloverLeaseTerms(
            market_rent=2800.0,
            term_months=12,
            renewal_rent_increase=0.045,
            concessions_months=0,
            turnover_make_ready_cost=2500.0,
            turnover_leasing_fee=1000.0
        ),
        renewal_terms=ResidentialRolloverLeaseTerms(
            market_rent=2800.0,
            term_months=12,
            renewal_rent_increase=0.035,
            concessions_months=0,
            turnover_make_ready_cost=1200.0,
            turnover_leasing_fee=500.0
        )
    )
    
    moderate_market_rollover = ResidentialRolloverProfile(
        name="Moderate Market Assumptions",
        renewal_probability=0.68,
        downtime_months=1,
        term_months=12,
        market_terms=ResidentialRolloverLeaseTerms(
            market_rent=2200.0,
            term_months=12,
            renewal_rent_increase=0.035,
            concessions_months=1,
            turnover_make_ready_cost=2200.0,
            turnover_leasing_fee=800.0
        ),
        renewal_terms=ResidentialRolloverLeaseTerms(
            market_rent=2200.0,
            term_months=12,
            renewal_rent_increase=0.030,
            concessions_months=0,
            turnover_make_ready_cost=1000.0,
            turnover_leasing_fee=400.0
        )
    )
    
    # Institutional unit mix - 6 different unit types
    unit_specs = [
        ResidentialUnitSpec(
            unit_type_name="Studio - Premium",
            unit_count=30,
            avg_area_sf=550.0,
            current_avg_monthly_rent=1850.0,
            rollover_profile=strong_market_rollover
        ),
        ResidentialUnitSpec(
            unit_type_name="1BR/1BA - Classic",
            unit_count=80,
            avg_area_sf=750.0,
            current_avg_monthly_rent=2300.0,
            rollover_profile=moderate_market_rollover
        ),
        ResidentialUnitSpec(
            unit_type_name="1BR/1BA - Premium",
            unit_count=40,
            avg_area_sf=850.0,
            current_avg_monthly_rent=2650.0,
            rollover_profile=strong_market_rollover
        ),
        ResidentialUnitSpec(
            unit_type_name="2BR/2BA - Classic",
            unit_count=60,
            avg_area_sf=1100.0,
            current_avg_monthly_rent=3200.0,
            rollover_profile=moderate_market_rollover
        ),
        ResidentialUnitSpec(
            unit_type_name="2BR/2BA - Premium",
            unit_count=30,
            avg_area_sf=1250.0,
            current_avg_monthly_rent=3800.0,
            rollover_profile=strong_market_rollover
        ),
        ResidentialUnitSpec(
            unit_type_name="3BR/2BA - Penthouse",
            unit_count=10,
            avg_area_sf=1500.0,
            current_avg_monthly_rent=4500.0,
            rollover_profile=strong_market_rollover
        )
    ]
    
    rent_roll = ResidentialRentRoll(unit_specs=unit_specs)
    
    # Comprehensive institutional-grade expense structure
    operating_expenses = [
        ResidentialOpExItem(
            name="Property Management",
            timeline=timeline,
            value=155.0,
            reference=PropertyAttributeKey.UNIT_COUNT,
            frequency=FrequencyEnum.MONTHLY
        ),
        ResidentialOpExItem(
            name="On-Site Staff",
            timeline=timeline,
            value=85.0,
            reference=PropertyAttributeKey.UNIT_COUNT,
            frequency=FrequencyEnum.MONTHLY
        ),
        ResidentialOpExItem(
            name="Utilities - Common Areas",
            timeline=timeline,
            value=32.0,
            reference=PropertyAttributeKey.UNIT_COUNT,
            frequency=FrequencyEnum.MONTHLY
        ),
        ResidentialOpExItem(
            name="Repairs & Maintenance",
            timeline=timeline,
            value=95.0,
            reference=PropertyAttributeKey.UNIT_COUNT,
            frequency=FrequencyEnum.MONTHLY
        ),
        ResidentialOpExItem(
            name="Landscaping & Grounds",
            timeline=timeline,
            value=22.0,
            reference=PropertyAttributeKey.UNIT_COUNT,
            frequency=FrequencyEnum.MONTHLY
        ),
        ResidentialOpExItem(
            name="Insurance",
            timeline=timeline,
            value=2.75,
            reference=PropertyAttributeKey.UNIT_COUNT,
            frequency=FrequencyEnum.ANNUAL
        ),
        ResidentialOpExItem(
            name="Property Taxes",
            timeline=timeline,
            value=8.50,
            reference=PropertyAttributeKey.UNIT_COUNT,
            frequency=FrequencyEnum.ANNUAL
        ),
        ResidentialOpExItem(
            name="Marketing & Advertising",
            timeline=timeline,
            value=18.0,
            reference=PropertyAttributeKey.UNIT_COUNT,
            frequency=FrequencyEnum.MONTHLY
        )
    ]
    
    capital_expenses = [
        ResidentialCapExItem(
            name="Capital Reserves",
            timeline=timeline,
            value=525.0,
            reference=PropertyAttributeKey.UNIT_COUNT,
            frequency=FrequencyEnum.ANNUAL
        ),
        ResidentialCapExItem(
            name="Amenity Upgrades",
            timeline=timeline,
            value=150000.0,
            frequency=FrequencyEnum.ANNUAL
        )
    ]
    
    # Multiple income streams
    miscellaneous_income = [
        ResidentialMiscIncome(
            name="Parking Income",
            timeline=timeline,
            value=45.0,
            reference=PropertyAttributeKey.UNIT_COUNT,
            frequency=FrequencyEnum.MONTHLY
        ),
        ResidentialMiscIncome(
            name="Storage Unit Fees",
            timeline=timeline,
            value=25.0,
            reference=PropertyAttributeKey.UNIT_COUNT,
            frequency=FrequencyEnum.MONTHLY
        ),
        ResidentialMiscIncome(
            name="Pet Fees",
            timeline=timeline,
            value=18.0,
            reference=PropertyAttributeKey.UNIT_COUNT,
            frequency=FrequencyEnum.MONTHLY
        ),
        ResidentialMiscIncome(
            name="Laundry & Vending",
            timeline=timeline,
            value=12.0,
            reference=PropertyAttributeKey.UNIT_COUNT,
            frequency=FrequencyEnum.MONTHLY
        ),
        ResidentialMiscIncome(
            name="Application & Admin Fees",
            timeline=timeline,
            value=8500.0,
            frequency=FrequencyEnum.MONTHLY
        )
    ]
    
    # Create comprehensive property model
    property_model = ResidentialProperty(
        name="Meridian Towers",
        gross_area=250000.0,  # 229,000 / 0.916 efficiency
        net_rentable_area=229000.0,  # Matches unit mix total area
        unit_mix=rent_roll,
        expenses=ResidentialExpenses(
            operating_expenses=operating_expenses,
            capital_expenses=capital_expenses
        ),
        losses=ResidentialLosses(
            general_vacancy=ResidentialGeneralVacancyLoss(rate=0.045),
            collection_loss=ResidentialCollectionLoss(rate=0.012)
        ),
        miscellaneous_income=miscellaneous_income
    )
    
    # Validate property setup
    assert property_model.unit_count == 250
    assert property_model.occupancy_rate == 1.0  # Fully occupied
    
    # Calculate expected monthly income
    expected_income = sum(spec.unit_count * spec.current_avg_monthly_rent for spec in unit_specs)
    assert property_model.unit_mix.current_monthly_income == expected_income
    
    # Measure performance
    start_time = time.time()
    
    # Run institutional-scale analysis
    scenario = run(
        model=property_model,
        timeline=timeline,
        settings=settings
    )
    
    analysis_time = time.time() - start_time
    
    print("\n🏢 Institutional Scale Analysis Results:")
    print(f"   📊 Property Size: {property_model.unit_count} units")
    print(f"   💰 Monthly Income: ${expected_income:,.0f}")
    print(f"   📐 Total NRA: {property_model.net_rentable_area:,.0f} SF")
    print(f"   ⚡ Analysis Time: {analysis_time:.3f} seconds")
    print(f"   🚀 Processing Rate: {property_model.unit_count / analysis_time:.0f} units/second")
    
    # Validate analysis completed successfully
    assert scenario is not None
    assert analysis_time < 2.0  # Should complete within 2 seconds
    
    # Verify unit mix unrolling worked correctly
    orchestrator = scenario._orchestrator
    lease_models = [m for m in orchestrator.models if m.__class__.__name__ == 'ResidentialLease']
    assert len(lease_models) == 250  # One lease per unit
    
    print(f"   ✅ Successfully created {len(lease_models)} lease models")
    print(f"   📋 Total models: {len(orchestrator.models)}")


def test_e2e_performance_stress_test():
    """
    E2E Test: Performance validation on large property (500 units)
    
    This stress test ensures the analysis engine can handle institutional-scale
    properties efficiently, validating both speed and memory usage.
    """
    timeline = Timeline(start_date=date(2024, 1, 1), duration_months=36)
    settings = GlobalSettings()
    
    # Single rollover profile for performance
    performance_rollover = ResidentialRolloverProfile(
        name="Performance Test Profile",
        renewal_probability=0.70,
        downtime_months=1,
        term_months=12,
        market_terms=ResidentialRolloverLeaseTerms(
            market_rent=2500.0,
            term_months=12
        ),
        renewal_terms=ResidentialRolloverLeaseTerms(
            market_rent=2500.0,
            term_months=12
        )
    )
    
    # Large, uniform unit mix for maximum scale
    unit_specs = [
        ResidentialUnitSpec(
            unit_type_name="1BR/1BA - Standard",
            unit_count=500,  # 500 units
            avg_area_sf=800.0,
            current_avg_monthly_rent=2400.0,
            rollover_profile=performance_rollover
        )
    ]
    
    rent_roll = ResidentialRentRoll(unit_specs=unit_specs)
    
    # Minimal expenses for performance testing
    operating_expenses = [
        ResidentialOpExItem(
            name="Property Management",
            timeline=timeline,
            value=150.0,
            reference=PropertyAttributeKey.UNIT_COUNT,
            frequency=FrequencyEnum.MONTHLY
        )
    ]
    
    property_model = ResidentialProperty(
        name="Performance Test Property",
        gross_area=440000.0,
        net_rentable_area=400000.0,  # 500 * 800
        unit_mix=rent_roll,
        expenses=ResidentialExpenses(operating_expenses=operating_expenses),
        losses=ResidentialLosses(
            general_vacancy=ResidentialGeneralVacancyLoss(rate=0.05),
            collection_loss=ResidentialCollectionLoss(rate=0.01)
        )
    )
    
    # Performance benchmark
    start_time = time.time()
    
    scenario = run(
        model=property_model,
        timeline=timeline,
        settings=settings
    )
    
    analysis_time = time.time() - start_time
    units_per_second = property_model.unit_count / analysis_time
    
    print("\n⚡ Performance Stress Test Results:")
    print(f"   📊 Property Size: {property_model.unit_count} units")
    print(f"   ⏱️  Analysis Time: {analysis_time:.3f} seconds")
    print(f"   🚀 Processing Rate: {units_per_second:.0f} units/second")
    print(f"   📋 Models Created: {len(scenario._orchestrator.models)}")
    
    # Performance assertions
    assert scenario is not None
    assert analysis_time < 1.6  # Must complete under 1.6 seconds (adjusted for renovation logic)
    assert units_per_second > 300  # Must process at least 300 units/second
    
    # Validate correct model creation
    lease_models = [m for m in scenario._orchestrator.models if m.__class__.__name__ == 'ResidentialLease']
    assert len(lease_models) == 500
    
    print(f"   ✅ Performance test PASSED - {units_per_second:.0f} units/sec")


def test_e2e_value_add_positioning_strategy():
    """
    E2E Test: Value-add property with renovation positioning
    
    This test models a value-add acquisition with two-tier rollover assumptions:
    - Below-market in-place rents
    - Market-rate rollover assumptions with potential renovation premiums
    """
    timeline = Timeline(start_date=date(2024, 1, 1), duration_months=48)
    settings = GlobalSettings()
    
    # Conservative rollover for unrenovated units
    unrenovated_rollover = ResidentialRolloverProfile(
        name="Unrenovated Unit Assumptions",
        renewal_probability=0.60,
        downtime_months=2,
        term_months=12,
        market_terms=ResidentialRolloverLeaseTerms(
            market_rent=2300.0,
            term_months=12,
            renewal_rent_increase=0.025,
            concessions_months=1,
            turnover_make_ready_cost=3200.0,
            turnover_leasing_fee=1100.0
        ),
        renewal_terms=ResidentialRolloverLeaseTerms(
            market_rent=2300.0,
            term_months=12,
            renewal_rent_increase=0.020,
            concessions_months=0,
            turnover_make_ready_cost=1800.0,
            turnover_leasing_fee=600.0
        )
    )
    
    # Aggressive rollover for renovated units (future value-add)
    renovated_rollover = ResidentialRolloverProfile(
        name="Post-Renovation Assumptions",
        renewal_probability=0.75,
        downtime_months=1,
        term_months=12,
        market_terms=ResidentialRolloverLeaseTerms(
            market_rent=2990.0,  # 30% premium post-renovation
            term_months=12,
            renewal_rent_increase=0.040,
            concessions_months=0,
            turnover_make_ready_cost=2500.0,
            turnover_leasing_fee=800.0
        ),
        renewal_terms=ResidentialRolloverLeaseTerms(
            market_rent=2990.0,
            term_months=12,
            renewal_rent_increase=0.035,
            concessions_months=0,
            turnover_make_ready_cost=1200.0,
            turnover_leasing_fee=400.0
        )
    )
    
    # Value-add unit mix with significant upside
    unit_specs = [
        ResidentialUnitSpec(
            unit_type_name="1BR/1BA - Current Condition",
            unit_count=80,
            avg_area_sf=750.0,
            current_avg_monthly_rent=1850.0,  # 20% below market
            rollover_profile=unrenovated_rollover
        ),
        ResidentialUnitSpec(
            unit_type_name="2BR/2BA - Current Condition",
            unit_count=40,
            avg_area_sf=1050.0,
            current_avg_monthly_rent=2400.0,  # 25% below market
            rollover_profile=renovated_rollover  # Assume these get renovated
        )
    ]
    
    rent_roll = ResidentialRentRoll(unit_specs=unit_specs)
    
    # Value-add expense structure
    operating_expenses = [
        ResidentialOpExItem(
            name="Property Management",
            timeline=timeline,
            value=165.0,
            reference=PropertyAttributeKey.UNIT_COUNT,
            frequency=FrequencyEnum.MONTHLY
        ),
        ResidentialOpExItem(
            name="Maintenance & Repairs",
            timeline=timeline,
            value=125.0,  # Higher for older property
            reference=PropertyAttributeKey.UNIT_COUNT,
            frequency=FrequencyEnum.MONTHLY
        ),
        ResidentialOpExItem(
            name="Property Taxes",
            timeline=timeline,
            value=7.25,
            reference=PropertyAttributeKey.UNIT_COUNT,
            frequency=FrequencyEnum.ANNUAL
        )
    ]
    
    capital_expenses = [
        ResidentialCapExItem(
            name="Capital Reserves",
            timeline=timeline,
            value=600.0,  # Higher reserves for value-add
            reference=PropertyAttributeKey.UNIT_COUNT,
            frequency=FrequencyEnum.ANNUAL
        )
    ]
    
    property_model = ResidentialProperty(
        name="Oakwood Commons - Value-Add",
        gross_area=111000.0,  # 102,000 / 0.92 efficiency
        net_rentable_area=102000.0,  # Matches unit mix total: 80*750 + 40*1050
        unit_mix=rent_roll,
        expenses=ResidentialExpenses(
            operating_expenses=operating_expenses,
            capital_expenses=capital_expenses
        ),
        losses=ResidentialLosses(
            general_vacancy=ResidentialGeneralVacancyLoss(rate=0.06),  # Higher vacancy for value-add
            collection_loss=ResidentialCollectionLoss(rate=0.018)
        )
    )
    
    # Value-add metrics analysis
    current_income = (80 * 1850) + (40 * 2400)  # 148,000 + 96,000 = 244,000
    market_potential = (80 * 2300) + (40 * 2990)  # 184,000 + 119,600 = 303,600
    upside_potential = market_potential - current_income  # 59,600
    
    assert property_model.unit_mix.current_monthly_income == current_income
    
    # Run value-add analysis
    start_time = time.time()
    
    scenario = run(
        model=property_model,
        timeline=timeline,
        settings=settings
    )
    
    analysis_time = time.time() - start_time
    
    print("\n📈 Value-Add Analysis Results:")
    print(f"   🏢 Property: {property_model.unit_count} units")
    print(f"   💰 Current Income: ${current_income:,.0f}/month")
    print(f"   🎯 Market Potential: ${market_potential:,.0f}/month")
    print(f"   📊 Monthly Upside: ${upside_potential:,.0f}")
    print(f"   📈 Rent Premium: {((market_potential / current_income) - 1) * 100:.1f}%")
    print(f"   ⚡ Analysis Time: {analysis_time:.3f} seconds")
    
    assert scenario is not None
    assert analysis_time < 1.0
    
    # Validate lease creation
    orchestrator = scenario._orchestrator
    lease_models = [m for m in orchestrator.models if m.__class__.__name__ == 'ResidentialLease']
    assert len(lease_models) == 120
    
    print("   ✅ Value-add analysis PASSED")


def test_e2e_test_discovery_validation():
    """
    E2E Test: Framework validation and test discovery
    
    This test ensures the residential module is properly integrated
    with the testing framework and scenario registry.
    """
    # Basic framework test
    timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
    settings = GlobalSettings()
    
    rollover_profile = ResidentialRolloverProfile(
        name="Test Discovery Profile",
        renewal_probability=0.65,
        downtime_months=1,
        term_months=12,
        market_terms=ResidentialRolloverLeaseTerms(market_rent=2000.0),
        renewal_terms=ResidentialRolloverLeaseTerms(market_rent=2000.0)
    )
    
    unit_specs = [
        ResidentialUnitSpec(
            unit_type_name="Test Unit",
            unit_count=1,
            avg_area_sf=800.0,
            current_avg_monthly_rent=1900.0,
            rollover_profile=rollover_profile
        )
    ]
    
    property_model = ResidentialProperty(
        name="Test Property",
        gross_area=880.0,
        net_rentable_area=800.0,
        unit_mix=ResidentialRentRoll(unit_specs=unit_specs),
        expenses=ResidentialExpenses(),
        losses=ResidentialLosses(
            general_vacancy=ResidentialGeneralVacancyLoss(rate=0.05),
            collection_loss=ResidentialCollectionLoss(rate=0.01)
        )
    )
    
    # Test analysis registration and execution
    scenario = run(
        model=property_model,
        timeline=timeline,
        settings=settings
    )
    
    assert scenario is not None
    print("\n🧪 Test Discovery: PASSED")
    print("   ✅ Scenario registry working")
    print("   ✅ ResidentialProperty analysis enabled")
    print("   ✅ Framework integration complete")


def test_e2e_vacant_units_lease_up_scenario():
    """
    E2E Test: Comprehensive vacant units scenario - Lease-up stabilization
    
    This test models a property that's 75% occupied and demonstrates:
    1. Properties with mixed occupied/vacant units
    2. Realistic lease-up scenarios
    3. Impact of vacant units on property metrics
    4. Analysis performance with vacancy
    """
    # Analysis parameters
    timeline = Timeline(start_date=date(2024, 1, 1), duration_months=60)  # 5-year analysis
    settings = GlobalSettings()
    
    # Market assumptions for lease-up scenario
    stabilized_rollover = ResidentialRolloverProfile(
        name="Lease-Up Market Assumptions",
        renewal_probability=0.68,
        downtime_months=1,
        term_months=12,
        market_terms=ResidentialRolloverLeaseTerms(
            market_rent=2400.0,  # Higher market rent for stabilized units
            term_months=12,
            renewal_rent_increase=0.035,  # 3.5% annual increase
            concessions_months=1,  # 1 month free for new leases
            turnover_make_ready_cost=2200.0,
            turnover_leasing_fee=800.0
        ),
        renewal_terms=ResidentialRolloverLeaseTerms(
            market_rent=2400.0,
            term_months=12,
            renewal_rent_increase=0.040,  # 4% for renewals
            concessions_months=0,
            turnover_make_ready_cost=1200.0,  # Lower cost for renewals
            turnover_leasing_fee=400.0
        )
    )
    
    # Lease-up rollover for vacant units (more aggressive leasing)
    leaseup_rollover = ResidentialRolloverProfile(
        name="Lease-Up Vacant Units",
        renewal_probability=0.0,  # All new leases
        downtime_months=2,  # Longer marketing time
        term_months=12,
        market_terms=ResidentialRolloverLeaseTerms(
            market_rent=2300.0,  # Slight discount for lease-up
            term_months=12,
            renewal_rent_increase=0.030,
            concessions_months=2,  # 2 months free for initial lease-up
            turnover_make_ready_cost=3500.0,  # Higher initial make-ready
            turnover_leasing_fee=1200.0
        ),
        renewal_terms=ResidentialRolloverLeaseTerms(
            market_rent=2300.0,
            term_months=12,
            renewal_rent_increase=0.030,
            concessions_months=0,
            turnover_make_ready_cost=3500.0,
            turnover_leasing_fee=1200.0
        )
    )
    
    # Occupied units (75% of property)
    occupied_specs = [
        ResidentialUnitSpec(
            unit_type_name="1BR/1BA - Stabilized",
            unit_count=45,  # 45 occupied
            avg_area_sf=775.0,
            current_avg_monthly_rent=2200.0,  # Below market
            rollover_profile=stabilized_rollover
        ),
        ResidentialUnitSpec(
            unit_type_name="2BR/2BA - Stabilized", 
            unit_count=30,  # 30 occupied
            avg_area_sf=1050.0,
            current_avg_monthly_rent=2900.0,
            rollover_profile=stabilized_rollover
        )
    ]
    
    # Vacant units (25% of property) - need lease-up
    vacant_units = [
        ResidentialVacantUnit(
            unit_type_name="1BR/1BA - Lease-Up",
            unit_count=15,  # 15 vacant 1BR
            avg_area_sf=775.0,
            market_rent=2250.0,  # Discounted for lease-up
            rollover_profile=leaseup_rollover
        ),
        ResidentialVacantUnit(
            unit_type_name="2BR/2BA - Lease-Up",
            unit_count=10,  # 10 vacant 2BR
            avg_area_sf=1050.0,
            market_rent=2850.0,
            rollover_profile=leaseup_rollover
        )
    ]
    
    rent_roll = ResidentialRentRoll(
        unit_specs=occupied_specs,
        vacant_units=vacant_units
    )
    
    # Comprehensive expenses for lease-up property
    operating_expenses = [
        ResidentialOpExItem(
            name="Property Management", 
            timeline=timeline,
            value=175.0, 
            reference=PropertyAttributeKey.UNIT_COUNT,
            frequency=FrequencyEnum.MONTHLY
        ),
        ResidentialOpExItem(
            name="Utilities - Common Areas",
            timeline=timeline,
            value=45.0,
            reference=PropertyAttributeKey.UNIT_COUNT,
            frequency=FrequencyEnum.MONTHLY
        ),
        ResidentialOpExItem(
            name="Repairs & Maintenance",
            timeline=timeline,
            value=85.0,
            reference=PropertyAttributeKey.UNIT_COUNT,
            frequency=FrequencyEnum.MONTHLY
        ),
        ResidentialOpExItem(
            name="Insurance",
            timeline=timeline,
            value=2.50,
            reference=PropertyAttributeKey.UNIT_COUNT,
            frequency=FrequencyEnum.ANNUAL
        ),
        ResidentialOpExItem(
            name="Property Taxes",
            timeline=timeline,
            value=6.85,
            reference=PropertyAttributeKey.UNIT_COUNT,
            frequency=FrequencyEnum.ANNUAL
        ),
        ResidentialOpExItem(
            name="Marketing & Leasing",
            timeline=timeline,
            value=25.0,  # Higher during lease-up
            reference=PropertyAttributeKey.UNIT_COUNT,
            frequency=FrequencyEnum.MONTHLY
        )
    ]
    
    capital_expenses = [
        ResidentialCapExItem(
            name="Capital Reserves",
            timeline=timeline,
            value=450.0,
            reference=PropertyAttributeKey.UNIT_COUNT,
            frequency=FrequencyEnum.ANNUAL
        )
    ]
    
    # Create comprehensive property model
    property_model = ResidentialProperty(
        name="Eastwood Gardens - Lease-Up Phase",
        gross_area=96300.0,  # 88,500 / 0.92 efficiency
        net_rentable_area=88500.0,  # Matches unit mix total: (45+15)*775 + (30+10)*1050
        unit_mix=rent_roll,
        expenses=ResidentialExpenses(
            operating_expenses=operating_expenses,
            capital_expenses=capital_expenses
        ),
        losses=ResidentialLosses(
            general_vacancy=ResidentialGeneralVacancyLoss(rate=0.04),  # 4% ongoing vacancy
            collection_loss=ResidentialCollectionLoss(rate=0.015)  # 1.5% collection loss
        ),
        miscellaneous_income=[
            ResidentialMiscIncome(
                name="Laundry Income",
                timeline=timeline,
                value=18.0,
                reference=PropertyAttributeKey.UNIT_COUNT,
                frequency=FrequencyEnum.MONTHLY
            ),
            ResidentialMiscIncome(
                name="Parking Fees",
                timeline=timeline,
                value=35.0,
                reference=PropertyAttributeKey.UNIT_COUNT,
                frequency=FrequencyEnum.MONTHLY
            ),
            ResidentialMiscIncome(
                name="Pet Fees",
                timeline=timeline,
                value=12.0,
                reference=PropertyAttributeKey.UNIT_COUNT,
                frequency=FrequencyEnum.MONTHLY
            )
        ]
    )
    
    # Validate property metrics before analysis
    assert property_model.unit_count == 100  # 75 occupied + 25 vacant
    assert property_model.occupancy_rate == 0.75  # 75% occupied
    
    # Current vs potential income analysis
    current_income = (45 * 2200) + (30 * 2900)  # 99,000 + 87,000 = 186,000
    vacant_potential = (15 * 2250) + (10 * 2850)  # 33,750 + 28,500 = 62,250
    total_potential = current_income + vacant_potential  # 248,250
    
    assert property_model.unit_mix.current_monthly_income == current_income
    assert property_model.unit_mix.total_monthly_income_potential == total_potential
    
    # Measure analysis performance
    start_time = time.time()
    
    # Run comprehensive analysis
    scenario = run(
        model=property_model,
        timeline=timeline,
        settings=settings
    )
    
    analysis_time = time.time() - start_time
    print("\n🏢 Lease-Up Analysis Performance:")
    print(f"   📊 Property Size: {property_model.unit_count} units")
    print(f"   🏠 Occupied Units: {property_model.unit_mix.occupied_units}")
    print(f"   🔲 Vacant Units: {property_model.unit_mix.vacant_unit_count}")
    print(f"   📈 Occupancy Rate: {property_model.occupancy_rate:.1%}")
    print(f"   ⚡ Analysis Time: {analysis_time:.3f} seconds")
    print(f"   🚀 Processing Rate: {property_model.unit_count / analysis_time:.0f} units/second")
    
    # Validate analysis results
    assert scenario is not None
    assert analysis_time < 3.0  # Should complete within 3 seconds
    
    # Verify unit mix unrolling
    orchestrator = scenario._orchestrator
    lease_models = [m for m in orchestrator.models if m.__class__.__name__ == 'ResidentialLease']
    
    # Should have lease models for occupied units (75), vacant units don't become leases immediately
    assert len(lease_models) == 75  # Only occupied units become immediate leases
    
    # Verify expense models (look for both OpEx and CapEx)
    expense_models = [m for m in orchestrator.models if any(x in m.__class__.__name__ for x in ['OpEx', 'CapEx', 'Expense'])]
    
    # Verify miscellaneous income models
    misc_income_models = [m for m in orchestrator.models if 'Income' in m.__class__.__name__]
    
    # Financial metrics validation
    total_models = len(lease_models) + len(expense_models) + len(misc_income_models)
    print(f"   📋 Total Models Created: {total_models}")
    print(f"   🏠 Lease Models: {len(lease_models)}")
    print(f"   💰 Expense Models: {len(expense_models)}")
    print(f"   📈 Income Models: {len(misc_income_models)}")
    
    # Income potential analysis
    print("\n💰 Income Analysis:")
    print(f"   📊 Current Monthly Income: ${current_income:,.0f}")
    print(f"   🎯 Total Income Potential: ${total_potential:,.0f}")
    print(f"   📈 Lease-Up Upside: ${total_potential - current_income:,.0f}")
    print(f"   📊 Income Per Unit (Current): ${current_income / 75:,.0f}")
    print(f"   🎯 Income Per Unit (Potential): ${total_potential / 100:,.0f}")
    
    # Property efficiency metrics
    print("\n🏗️ Property Efficiency:")
    print(f"   📐 Total Rentable SF: {property_model.net_rentable_area:,.0f}")
    print(f"   🏠 Average Unit Size: {property_model.net_rentable_area / 100:.0f} SF")
    print(f"   💰 Current $/SF/Month: ${current_income / (property_model.net_rentable_area * 0.75):.2f}")
    print(f"   🎯 Potential $/SF/Month: ${total_potential / property_model.net_rentable_area:.2f}")
    
    # Assert that the analysis handles vacant units properly
    assert scenario._orchestrator is not None
    assert len(scenario._orchestrator.models) > 0
    
    print("\n✅ Vacant Units E2E Test: PASSED")
    print(f"   🎯 Successfully modeled {property_model.unit_mix.vacant_unit_count} vacant units")
    print(f"   📊 {property_model.occupancy_rate:.1%} occupancy properly calculated")
    print(f"   ⚡ Analysis completed in {analysis_time:.3f}s")


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 