# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Integration tests for debt orchestration.

These tests verify that all enhanced debt features work together correctly,
including refinancing orchestration, covenant monitoring, and deal integration.
"""

import numpy as np
import pandas as pd

from performa.core.primitives import Timeline
from performa.debt.construction import ConstructionFacility, DebtTranche
from performa.debt.permanent import PermanentFacility
from performa.debt.plan import FinancingPlan
from performa.debt.rates import FixedRate, FloatingRate, InterestRate, RateIndexEnum


class TestEnhancedDebtServiceIntegration:
    """Test enhanced debt service calculations with institutional features."""
    
    def test_interest_only_debt_service_integration(self):
        """Test that interest-only periods are properly integrated into debt service."""
        # Create permanent facility with interest-only periods
        facility = PermanentFacility(
            name='Permanent Loan',
            kind='permanent',
            interest_rate=InterestRate(details=FixedRate(rate=0.055)),
            loan_term_years=10,
            amortization_years=25,
            interest_only_months=24,  # 2 years I/O
            sizing_method='manual',
            loan_amount=5_000_000,
            ltv_ratio=0.75,
            dscr_hurdle=1.25
        )
        
        # Create timeline
        timeline = Timeline.from_dates('2024-01-01', '2034-01-01')
        
        # Calculate debt service
        debt_service = facility.calculate_debt_service(timeline)
        
        # Verify debt service series is created
        assert len(debt_service) > 0
        assert debt_service.sum() > 0
        
        # Generate amortization to verify I/O integration
        schedule = facility.generate_amortization(5_000_000, timeline.period_index[0])
        
        # First 24 months should be interest-only
        first_24_months = schedule.iloc[:24]
        assert (first_24_months['Principal'] == 0).all()
        assert (first_24_months['Interest'] > 0).all()
        
        # I/O payments should be lower than amortizing payments
        io_payment = first_24_months['Payment'].iloc[0]
        amortizing_payment = schedule.iloc[24]['Payment']
        assert io_payment < amortizing_payment
        
        print(f"✓ I/O payment: ${io_payment:,.0f}")
        print(f"✓ Amortizing payment: ${amortizing_payment:,.0f}")
        print(f"✓ Payment difference: ${amortizing_payment - io_payment:,.0f}")
    
    def test_floating_rate_debt_service_integration(self):
        """Test dynamic floating rate calculations in debt service."""
        # Create floating rate facility
        facility = PermanentFacility(
            name='Floating Rate Loan',
            kind='permanent',
            interest_rate=InterestRate(details=FloatingRate(
                rate_index=RateIndexEnum.SOFR_30_DAY_AVG,
                spread=0.0275,  # 275 bps
                interest_rate_cap=0.08  # 8% cap
            )),
            loan_term_years=5,
            amortization_years=25,
            sizing_method='manual',
            loan_amount=3_000_000,
            ltv_ratio=0.75,
            dscr_hurdle=1.25
        )
        
        # Create timeline and rate curve
        timeline = Timeline.from_dates('2024-01-01', '2029-01-01')
        
        # Create rising SOFR curve
        sofr_values = np.linspace(0.045, 0.065, len(timeline.period_index))
        sofr_curve = pd.Series(sofr_values, index=timeline.period_index)
        
        # Create LoanAmortization with floating rate
        from performa.debt.amortization import LoanAmortization
        amortization = LoanAmortization(
            loan_amount=3_000_000,
            term=5,
            interest_rate=facility.interest_rate,
            start_date=timeline.period_index[0],
            index_curve=sofr_curve
        )
        
        schedule, summary = amortization.amortization_schedule
        
        # Verify rates are changing over time
        rates = schedule['Rate'].values
        assert len(set(rates)) > 1  # Should have varying rates
        
        # Verify cap is enforced
        max_rate = rates.max()
        assert max_rate <= 0.08  # Should respect cap
        
        print(f"✓ Rate range: {rates.min():.3%} to {rates.max():.3%}")
        print(f"✓ Average rate: {summary['Average Rate']:.3%}")
        print(f"✓ Rate cap enforced: {max_rate <= 0.08}")


class TestRefinancingOrchestrationIntegration:
    """Test complete refinancing orchestration with automatic sizing."""
    
    def test_construction_to_permanent_refinancing(self):
        """Test complete refinancing workflow with sizing trifecta."""
        # Create construction facility
        construction_facility = ConstructionFacility(
            name='Construction Loan',
            kind='construction',
            tranches=[
                DebtTranche(
                    name='Senior Construction',
                    ltc_threshold=0.75,
                    interest_rate=InterestRate(details=FixedRate(rate=0.08)),
                    fee_rate=0.01
                )
            ]
        )
        
        # Create permanent facility with auto sizing
        permanent_facility = PermanentFacility(
            name='Permanent Loan',
            kind='permanent',
            interest_rate=InterestRate(details=FixedRate(rate=0.055)),
            loan_term_years=10,
            amortization_years=25,
            refinance_timing=24,  # 24 months
            
            # Sizing Trifecta
            sizing_method='auto',
            ltv_ratio=0.75,
            dscr_hurdle=1.25,
            debt_yield_hurdle=0.08,
            
            # Covenant monitoring
            ongoing_ltv_max=0.80,
            ongoing_dscr_min=1.20,
            ongoing_debt_yield_min=0.075
        )
        
        # Create financing plan
        financing_plan = FinancingPlan(
            name='Construction-to-Permanent Financing',
            facilities=[construction_facility, permanent_facility]
        )
        
        # Create timeline and mock data
        timeline = Timeline.from_dates('2024-01-01', '2029-01-01')
        property_value_series = pd.Series([9_000_000] * len(timeline.period_index), index=timeline.period_index)
        noi_series = pd.Series([600_000] * len(timeline.period_index), index=timeline.period_index)
        
        # Test refinancing calculation
        refinancing_transactions = financing_plan.calculate_refinancing_transactions(
            timeline=timeline,
            property_value_series=property_value_series,
            noi_series=noi_series,
            financing_cash_flows=None
        )
        
        # Verify refinancing transaction created
        assert len(refinancing_transactions) == 1
        
        transaction = refinancing_transactions[0]
        assert transaction['transaction_type'] == 'construction_to_permanent_refinancing'
        assert transaction['new_loan_amount'] > 0
        assert transaction['sizing_analysis']['sizing_method'] == 'automatic'
        assert transaction['covenant_monitoring']['monitoring_enabled'] == True
        
        # Verify sizing analysis
        sizing_analysis = transaction['sizing_analysis']
        assert 'ltv_constraint' in sizing_analysis
        assert 'dscr_constraint' in sizing_analysis
        assert 'debt_yield_constraint' in sizing_analysis
        assert 'most_restrictive' in sizing_analysis
        
        print(f"✓ New loan amount: ${transaction['new_loan_amount']:,.0f}")
        print(f"✓ Most restrictive constraint: {sizing_analysis['most_restrictive']}")
        print(f"✓ Covenant monitoring enabled: {transaction['covenant_monitoring']['monitoring_enabled']}")
    
    def test_refinancing_with_covenant_monitoring_setup(self):
        """Test that refinancing properly sets up covenant monitoring."""
        # Create permanent facility
        permanent_facility = PermanentFacility(
            name='Permanent Loan',
            kind='permanent',
            interest_rate=InterestRate(details=FixedRate(rate=0.055)),
            loan_term_years=10,
            amortization_years=25,
            sizing_method='auto',
            ltv_ratio=0.75,
            dscr_hurdle=1.25,
            debt_yield_hurdle=0.08,
            
            # Covenant monitoring configuration
            ongoing_ltv_max=0.80,
            ongoing_dscr_min=1.20,
            ongoing_debt_yield_min=0.075
        )
        
        # Test covenant monitoring directly
        timeline = Timeline.from_dates('2024-01-01', '2029-01-01')
        
        # Create compliant scenario
        property_values = pd.Series([8_000_000] * len(timeline.period_index), index=timeline.period_index)
        noi_values = pd.Series([600_000] * len(timeline.period_index), index=timeline.period_index)
        
        # Calculate covenant monitoring
        covenant_results = permanent_facility.calculate_covenant_monitoring(
            timeline=timeline,
            property_value_series=property_values,
            noi_series=noi_values,
            loan_amount=6_000_000
        )
        
        # Verify covenant monitoring structure
        assert len(covenant_results) == len(timeline.period_index)
        assert 'LTV' in covenant_results.columns
        assert 'DSCR' in covenant_results.columns
        assert 'Debt_Yield' in covenant_results.columns
        assert 'Covenant_Status' in covenant_results.columns
        
        # Get breach summary
        breach_summary = permanent_facility.get_covenant_breach_summary(covenant_results)
        
        assert 'Breach_Rate' in breach_summary
        assert 'Total_Periods' in breach_summary
        
        print(f"✓ Covenant monitoring periods: {len(covenant_results)}")
        print(f"✓ Breach rate: {breach_summary['Breach_Rate']:.1%}")
        print(f"✓ Covenant status range: {covenant_results['Covenant_Status'].unique()}")


class TestCovenantMonitoringIntegration:
    """Test covenant monitoring integration with realistic scenarios."""
    
    def test_covenant_monitoring_compliant_vs_breach(self):
        """Test covenant monitoring with both compliant and breach scenarios."""
        facility = PermanentFacility(
            name='Permanent Loan',
            kind='permanent',
            interest_rate=InterestRate(details=FixedRate(rate=0.055)),
            loan_term_years=10,
            amortization_years=25,
            sizing_method='manual',
            loan_amount=6_000_000,
            ltv_ratio=0.75,
            dscr_hurdle=1.25,
            ongoing_ltv_max=0.80,
            ongoing_dscr_min=1.20,
            ongoing_debt_yield_min=0.075
        )
        
        timeline = Timeline.from_dates('2024-01-01', '2029-01-01')
        
        # Scenario 1: Compliant
        property_values_good = pd.Series([8_000_000] * len(timeline.period_index), index=timeline.period_index)
        noi_good = pd.Series([600_000] * len(timeline.period_index), index=timeline.period_index)
        
        results_good = facility.calculate_covenant_monitoring(
            timeline=timeline,
            property_value_series=property_values_good,
            noi_series=noi_good,
            loan_amount=6_000_000
        )
        
        breach_summary_good = facility.get_covenant_breach_summary(results_good)
        
        # Scenario 2: Breach scenario
        property_values_bad = pd.Series([7_000_000] * len(timeline.period_index), index=timeline.period_index)
        noi_bad = pd.Series([400_000] * len(timeline.period_index), index=timeline.period_index)
        
        results_bad = facility.calculate_covenant_monitoring(
            timeline=timeline,
            property_value_series=property_values_bad,
            noi_series=noi_bad,
            loan_amount=6_000_000
        )
        
        breach_summary_bad = facility.get_covenant_breach_summary(results_bad)
        
        # Verify breach detection works
        assert breach_summary_good['Breach_Rate'] < breach_summary_bad['Breach_Rate']
        assert breach_summary_bad['Breach_Rate'] > 0  # Should have breaches
        
        # Verify specific breach types
        assert 'DSCR_Breach_Count' in breach_summary_bad
        assert 'LTV_Breach_Count' in breach_summary_bad
        assert 'Debt_Yield_Breach_Count' in breach_summary_bad
        
        print(f"✓ Compliant scenario breach rate: {breach_summary_good['Breach_Rate']:.1%}")
        print(f"✓ Stress scenario breach rate: {breach_summary_bad['Breach_Rate']:.1%}")
        print(f"✓ DSCR breaches (stress): {breach_summary_bad['DSCR_Breach_Count']}")
        print("✓ Covenant monitoring differentiation working")


class TestRateCapEnforcementIntegration:
    """Test rate cap enforcement in integrated scenarios."""
    
    def test_rate_cap_enforcement_in_amortization(self):
        """Test that rate caps are enforced throughout amortization."""
        # Create floating rate with aggressive cap
        floating_rate = InterestRate(details=FloatingRate(
            rate_index=RateIndexEnum.SOFR_30_DAY_AVG,
            spread=0.03,  # 300 bps
            interest_rate_cap=0.06  # 6% cap
        ))
        
        timeline = Timeline.from_dates('2024-01-01', '2025-01-01')
        
        # Create high SOFR curve that would exceed cap
        high_sofr = pd.Series([0.055] * len(timeline.period_index), index=timeline.period_index)
        
        # Create amortization with rate cap
        from performa.debt.amortization import LoanAmortization
        amortization = LoanAmortization(
            loan_amount=1_000_000,
            term=5,
            interest_rate=floating_rate,
            start_date=timeline.period_index[0],
            index_curve=high_sofr
        )
        
        schedule, summary = amortization.amortization_schedule
        
        # Verify all rates are capped
        rates = schedule['Rate'].values
        assert (rates <= 0.06).all()  # All rates should be at or below cap
        
        # Test specific rate calculation
        capped_rate = floating_rate.get_rate_for_period(timeline.period_index[0], high_sofr)
        expected_uncapped = 0.055 + 0.03  # 8.5%
        assert capped_rate == 0.06  # Should be capped at 6%
        assert expected_uncapped > 0.06  # Verify cap was needed
        
        print("✓ SOFR: 5.50%")
        print("✓ Spread: 3.00%")
        print(f"✓ Uncapped rate: {expected_uncapped:.2%}")
        print(f"✓ Capped rate: {capped_rate:.2%}")
        print(f"✓ All amortization rates capped: {(rates <= 0.06).all()}")


class TestFullDebtModuleIntegration:
    """Test complete debt module integration with all features."""
    
    def test_institutional_loan_workflow(self):
        """Test complete institutional loan workflow with all enhanced features."""
        # Create sophisticated permanent facility
        facility = PermanentFacility(
            name='Institutional Permanent Loan',
            kind='permanent',
            interest_rate=InterestRate(details=FloatingRate(
                rate_index=RateIndexEnum.SOFR_30_DAY_AVG,
                spread=0.0275,  # 275 bps
                interest_rate_cap=0.08,  # 8% cap
                interest_rate_floor=0.04  # 4% floor
            )),
            loan_term_years=10,
            amortization_years=25,
            
            # Interest-only periods
            interest_only_months=36,  # 3 years I/O
            
            # Sizing Trifecta
            sizing_method='auto',
            ltv_ratio=0.75,
            dscr_hurdle=1.25,
            debt_yield_hurdle=0.08,
            
            # Covenant monitoring
            ongoing_ltv_max=0.80,
            ongoing_dscr_min=1.20,
            ongoing_debt_yield_min=0.075
        )
        
        # Test automatic sizing
        property_value = 12_000_000
        noi = 900_000
        
        loan_amount = facility.calculate_refinance_amount(property_value, noi)
        
        # Verify sizing worked
        assert loan_amount > 0
        assert loan_amount <= property_value * 0.75  # LTV constraint
        
        # Test amortization with all features
        timeline = Timeline.from_dates('2024-01-01', '2034-01-01')
        
        # Create rate curve
        sofr_curve = pd.Series(
            np.linspace(0.045, 0.055, len(timeline.period_index)),
            index=timeline.period_index
        )
        
        # Create amortization with floating rate and I/O periods
        from performa.debt.amortization import LoanAmortization
        amortization = LoanAmortization(
            loan_amount=loan_amount,
            term=10,
            interest_rate=facility.interest_rate,
            start_date=timeline.period_index[0],
            interest_only_periods=36,
            index_curve=sofr_curve
        )
        
        schedule, summary = amortization.amortization_schedule
        
        # Verify I/O periods
        first_36_months = schedule.iloc[:36]
        assert (first_36_months['Principal'] == 0).all()
        
        # Verify floating rates
        rates = schedule['Rate'].values
        assert len(set(rates)) > 1  # Should vary
        
        # Test covenant monitoring
        property_values = pd.Series([property_value] * len(timeline.period_index), index=timeline.period_index)
        noi_values = pd.Series([noi] * len(timeline.period_index), index=timeline.period_index)
        
        covenant_results = facility.calculate_covenant_monitoring(
            timeline=timeline,
            property_value_series=property_values,
            noi_series=noi_values,
            loan_amount=loan_amount,
            index_curve=sofr_curve
        )
        
        breach_summary = facility.get_covenant_breach_summary(covenant_results)
        
        # Verify all components working
        assert len(schedule) > 0
        assert len(covenant_results) > 0
        assert 'Breach_Rate' in breach_summary
        
        print(f"✓ Loan amount (auto-sized): ${loan_amount:,.0f}")
        print("✓ I/O periods: 36 months")
        print(f"✓ Floating rates: {rates.min():.3%} to {rates.max():.3%}")
        print(f"✓ Covenant breach rate: {breach_summary['Breach_Rate']:.1%}")
        print("✓ Complete institutional workflow validated") 