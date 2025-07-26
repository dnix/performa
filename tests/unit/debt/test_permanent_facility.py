# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for PermanentFacility.

Tests the enhanced PermanentFacility functionality including the "Sizing Trifecta"
(LTV, DSCR, Debt Yield) and covenant monitoring capabilities.
"""

import numpy as np
import pandas as pd
import pytest

from performa.core.primitives import Timeline
from performa.debt.permanent import PermanentFacility
from performa.debt.rates import FixedRate, InterestRate


class TestSizingTrifecta:
    """Test the Sizing Trifecta (LTV, DSCR, Debt Yield) functionality."""
    
    def test_ltv_most_restrictive(self):
        """Test scenario where LTV is the most restrictive constraint."""
        facility = PermanentFacility(
            name='Test Loan',
            interest_rate=InterestRate(details=FixedRate(rate=0.05)),  # Lower rate
            loan_term_years=30,  # Longer term  
            amortization_years=30,
            ltv_ratio=0.60,  # 60% LTV - will be most restrictive
            dscr_hurdle=1.15,  # 1.15x DSCR (lenient)
            debt_yield_hurdle=0.06,  # 6% debt yield (lenient)
            sizing_method='auto'
        )
        
        # $10M property, $900K NOI (high NOI to make DSCR/debt yield lenient)
        property_value = 10_000_000
        noi = 900_000
        
        loan_amount = facility.calculate_refinance_amount(property_value, noi)
        
        # Should be limited by LTV: $10M * 60% = $6M
        expected_ltv_limit = property_value * 0.60
        assert abs(loan_amount - expected_ltv_limit) < 1000  # Within $1,000
    
    def test_dscr_most_restrictive(self):
        """Test scenario where DSCR is the most restrictive constraint."""
        facility = PermanentFacility(
            name='Test Loan',
            interest_rate=InterestRate(details=FixedRate(rate=0.06)),
            loan_term_years=10,
            amortization_years=25,
            ltv_ratio=0.80,  # 80% LTV - high
            dscr_hurdle=1.40,  # 1.40x DSCR - will be most restrictive
            debt_yield_hurdle=0.06,  # 6% debt yield - low
            sizing_method='auto'
        )
        
        # $10M property, $800K NOI
        property_value = 10_000_000
        noi = 800_000
        
        loan_amount = facility.calculate_refinance_amount(property_value, noi)
        
        # Should be limited by DSCR
        # Max debt service = $800K / 1.40 = $571,429
        # At 6% rate, 10-year term, 25-year amortization
        annual_debt_constant = facility._calculate_annual_debt_constant()
        expected_dscr_limit = (noi / facility.dscr_hurdle) / annual_debt_constant
        
        assert abs(loan_amount - expected_dscr_limit) < 1000  # Within $1,000
    
    def test_debt_yield_most_restrictive(self):
        """Test scenario where Debt Yield is the most restrictive constraint."""
        facility = PermanentFacility(
            name='Test Loan',
            interest_rate=InterestRate(details=FixedRate(rate=0.04)),  # Low rate
            loan_term_years=30,  # Long term
            amortization_years=30,
            ltv_ratio=0.80,  # 80% LTV - high (lenient)
            dscr_hurdle=1.10,  # 1.10x DSCR - low (lenient)
            debt_yield_hurdle=0.15,  # 15% debt yield - high, will be most restrictive
            sizing_method='auto'
        )
        
        # $10M property, $600K NOI (lower NOI makes debt yield restrictive)
        property_value = 10_000_000
        noi = 600_000
        
        loan_amount = facility.calculate_refinance_amount(property_value, noi)
        
        # Should be limited by Debt Yield: $600K / 15% = $4M
        expected_debt_yield_limit = noi / 0.15
        assert abs(loan_amount - expected_debt_yield_limit) < 1000  # Within $1,000
    
    def test_manual_sizing_override(self):
        """Test that manual sizing override works correctly."""
        facility = PermanentFacility(
            name='Test Loan',
            interest_rate=InterestRate(details=FixedRate(rate=0.06)),
            loan_term_years=10,
            ltv_ratio=0.75,
            dscr_hurdle=1.25,
            debt_yield_hurdle=0.08,
            sizing_method='manual',
            loan_amount=5_000_000  # Fixed amount
        )
        
        # Should return the manual amount regardless of property value/NOI
        property_value = 10_000_000
        noi = 800_000
        
        loan_amount = facility.calculate_refinance_amount(property_value, noi)
        
        # Should use manual override
        assert loan_amount == 5_000_000


class TestCovenantMonitoring:
    """Test covenant monitoring functionality."""
    
    def test_covenant_monitoring_setup(self):
        """Test that covenant monitoring fields are properly configured."""
        facility = PermanentFacility(
            name='Test Loan',
            interest_rate=InterestRate(details=FixedRate(rate=0.06)),
            loan_term_years=10,
            ltv_ratio=0.75,
            dscr_hurdle=1.25,
            sizing_method='manual',
            loan_amount=6_000_000,
            # Covenant monitoring fields
            ongoing_ltv_max=0.80,
            ongoing_dscr_min=1.20,
            ongoing_debt_yield_min=0.075
        )
        
        # Should have covenant monitoring fields
        assert facility.ongoing_ltv_max == 0.80
        assert facility.ongoing_dscr_min == 1.20
        assert facility.ongoing_debt_yield_min == 0.075
    
    def test_covenant_monitoring_compliant_scenario(self):
        """Test covenant monitoring with compliant scenario."""
        facility = PermanentFacility(
            name='Test Loan',
            interest_rate=InterestRate(details=FixedRate(rate=0.06)),
            loan_term_years=10,
            amortization_years=25,  # 25-year amortization for lower payments
            ltv_ratio=0.75,
            dscr_hurdle=1.25,
            sizing_method='manual',
            loan_amount=6_000_000,
            ongoing_ltv_max=0.80,
            ongoing_dscr_min=1.20,
            ongoing_debt_yield_min=0.075
        )
        
        # Create timeline
        timeline = Timeline.from_dates('2024-01-01', '2027-01-01')
        
        # Create compliant scenario
        property_values = pd.Series([8_000_000] * len(timeline.period_index), index=timeline.period_index)
        noi_values = pd.Series([600_000] * len(timeline.period_index), index=timeline.period_index)
        
        results = facility.calculate_covenant_monitoring(
            timeline=timeline,
            property_value_series=property_values,
            noi_series=noi_values,
            loan_amount=6_000_000
        )
        
        # Should have results for all periods
        assert len(results) == len(timeline.period_index)
        
        # Check covenant metrics exist
        assert 'LTV' in results.columns
        assert 'DSCR' in results.columns
        assert 'Debt_Yield' in results.columns
        assert 'Covenant_Status' in results.columns
        
        # Should be compliant
        compliant_periods = results[results['Covenant_Status'] == 'COMPLIANT']
        assert len(compliant_periods) > 0
    
    def test_covenant_monitoring_breach_scenario(self):
        """Test covenant monitoring with breach scenario."""
        facility = PermanentFacility(
            name='Test Loan',
            interest_rate=InterestRate(details=FixedRate(rate=0.06)),
            loan_term_years=10,
            ltv_ratio=0.75,
            dscr_hurdle=1.25,
            sizing_method='manual',
            loan_amount=6_000_000,
            ongoing_ltv_max=0.80,
            ongoing_dscr_min=1.20,
            ongoing_debt_yield_min=0.075
        )
        
        # Create timeline
        timeline = Timeline.from_dates('2024-01-01', '2027-01-01')
        
        # Create breach scenario - property value drops, NOI drops
        property_values = pd.Series([7_000_000] * len(timeline.period_index), index=timeline.period_index)
        noi_values = pd.Series([400_000] * len(timeline.period_index), index=timeline.period_index)
        
        results = facility.calculate_covenant_monitoring(
            timeline=timeline,
            property_value_series=property_values,
            noi_series=noi_values,
            loan_amount=6_000_000
        )
        
        # Should have breach periods
        breach_periods = results[results['Covenant_Status'] == 'BREACH']
        assert len(breach_periods) > 0
        
        # Check specific breach types
        assert 'LTV_Breach' in results.columns
        assert 'DSCR_Breach' in results.columns
        assert 'Debt_Yield_Breach' in results.columns
    
    def test_covenant_breach_summary(self):
        """Test covenant breach summary functionality."""
        facility = PermanentFacility(
            name='Test Loan',
            interest_rate=InterestRate(details=FixedRate(rate=0.06)),
            loan_term_years=10,
            ltv_ratio=0.75,
            dscr_hurdle=1.25,
            sizing_method='manual',
            loan_amount=6_000_000,
            ongoing_ltv_max=0.80,
            ongoing_dscr_min=1.20,
            ongoing_debt_yield_min=0.075
        )
        
        # Create timeline
        timeline = Timeline.from_dates('2024-01-01', '2025-01-01')
        
        # Create mixed scenario
        property_values = pd.Series([7_500_000] * len(timeline.period_index), index=timeline.period_index)
        noi_values = pd.Series([450_000] * len(timeline.period_index), index=timeline.period_index)
        
        results = facility.calculate_covenant_monitoring(
            timeline=timeline,
            property_value_series=property_values,
            noi_series=noi_values,
            loan_amount=6_000_000
        )
        
        # Get breach summary
        summary = facility.get_covenant_breach_summary(results)
        
        # Should have summary statistics
        assert 'Total_Periods' in summary
        assert 'Breach_Periods' in summary
        assert 'Breach_Rate' in summary
        assert 'Max_LTV' in summary
        assert 'Min_DSCR' in summary
        assert 'Min_Debt_Yield' in summary
        
        # Breach rate should be between 0 and 1
        assert 0 <= summary['Breach_Rate'] <= 1


class TestPermanentFacilityValidation:
    """Test validation rules for PermanentFacility."""
    
    def test_ltv_validation(self):
        """Test LTV ratio validation."""
        # Valid LTV should work
        facility = PermanentFacility(
            name='Test Loan',
            interest_rate=InterestRate(details=FixedRate(rate=0.06)),
            loan_term_years=10,
            ltv_ratio=0.75,
            dscr_hurdle=1.25,
            sizing_method='manual',
            loan_amount=5_000_000
        )
        assert facility.ltv_ratio == 0.75
        
        # Invalid LTV should fail
        with pytest.raises(ValueError):
            PermanentFacility(
                name='Test Loan',
                interest_rate=InterestRate(details=FixedRate(rate=0.06)),
                loan_term_years=10,
                ltv_ratio=0.85,  # Too high
                dscr_hurdle=1.25,
                sizing_method='manual',
                loan_amount=5_000_000
            )
    
    def test_dscr_validation(self):
        """Test DSCR hurdle validation."""
        # Valid DSCR should work
        facility = PermanentFacility(
            name='Test Loan',
            interest_rate=InterestRate(details=FixedRate(rate=0.06)),
            loan_term_years=10,
            ltv_ratio=0.75,
            dscr_hurdle=1.25,
            sizing_method='manual',
            loan_amount=5_000_000
        )
        assert facility.dscr_hurdle == 1.25
        
        # Invalid DSCR should fail
        with pytest.raises(ValueError):
            PermanentFacility(
                name='Test Loan',
                interest_rate=InterestRate(details=FixedRate(rate=0.06)),
                loan_term_years=10,
                ltv_ratio=0.75,
                dscr_hurdle=0.90,  # Too low
                sizing_method='manual',
                loan_amount=5_000_000
            )
    
    def test_interest_only_months_integration(self):
        """Test that interest-only months are properly integrated."""
        facility = PermanentFacility(
            name='Test Loan',
            interest_rate=InterestRate(details=FixedRate(rate=0.06)),
            loan_term_years=10,
            ltv_ratio=0.75,
            dscr_hurdle=1.25,
            sizing_method='manual',
            loan_amount=5_000_000,
            interest_only_months=24  # 2 years I/O
        )
        
        # Should have interest-only months field
        assert facility.interest_only_months == 24
        
        # Should generate proper amortization schedule
        timeline = Timeline.from_dates('2024-01-01', '2034-01-01')
        schedule = facility.generate_amortization(5_000_000, timeline.period_index[0])
        
        # First 24 months should be interest-only
        first_24_months = schedule.iloc[:24]
        assert (first_24_months['Principal'] == 0).all()
        assert (first_24_months['Interest'] > 0).all()
        
        # Month 25 should have principal payment
        assert schedule.iloc[24]['Principal'] > 0 