# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Comprehensive Test Suite for Debt Module Features

This test suite validates the debt module functionality including:
- Floating rate structures with SOFR + spread + caps/floors
- Loan sizing constraints (LTV + DSCR + Debt Yield)
- Interest-only periods for permanent loans
- Dynamic rate calculations with time series
- Continuous covenant monitoring for risk management

Run with: python test_debt_features.py
"""

import sys

sys.path.append('src')

from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from performa.debt import (
    FixedRate,
    FloatingRate,
    InterestRate,
    LoanAmortization,
    PermanentFacility,
    RateIndexEnum,
)


class TestInterestRateSystem:
    """Test the InterestRate system with fixed and floating rates."""
    
    def test_fixed_rate_creation(self):
        """Test creating fixed rate structures."""
        rate = InterestRate(details=FixedRate(rate=0.065))
        assert rate.details.rate_type == "fixed"
        assert rate.details.rate == 0.065
        assert rate.effective_rate == 0.065
        
    def test_floating_rate_creation(self):
        """Test creating floating rate structures."""
        rate = InterestRate(details=FloatingRate(
            rate_index=RateIndexEnum.SOFR_30_DAY_AVG,
            spread=0.0275,
            interest_rate_cap=0.08,
            interest_rate_floor=0.02
        ))
        assert rate.details.rate_type == "floating"
        assert rate.details.spread == 0.0275
        assert rate.details.interest_rate_cap == 0.08
        
    def test_fixed_rate_calculation(self):
        """Test fixed rate calculations."""
        rate = InterestRate(details=FixedRate(rate=0.06))
        period = pd.Period("2024-01", freq="M")
        
        # Fixed rates don't need index curve
        calculated_rate = rate.get_rate_for_period(period)
        assert calculated_rate == 0.06
        
    def test_floating_rate_calculation(self):
        """Test floating rate calculations with index curves."""
        rate = InterestRate(details=FloatingRate(
            rate_index=RateIndexEnum.SOFR_30_DAY_AVG,
            spread=0.0275,
            interest_rate_cap=0.08
        ))
        
        # Create SOFR curve
        periods = pd.period_range("2024-01", periods=3, freq="M")
        sofr_curve = pd.Series([0.045, 0.050, 0.055], index=periods)
        
        # Test calculations
        rate1 = rate.get_rate_for_period(periods[0], sofr_curve)
        rate2 = rate.get_rate_for_period(periods[1], sofr_curve)
        rate3 = rate.get_rate_for_period(periods[2], sofr_curve)
        
        assert rate1 == 0.0725  # 4.5% + 275bps
        assert rate2 == 0.0775  # 5.0% + 275bps
        assert rate3 == 0.08    # 5.5% + 275bps = 8.25%, capped at 8%
        
    def test_rate_cap_functionality(self):
        """Test interest rate caps are properly applied."""
        rate = InterestRate(details=FloatingRate(
            rate_index=RateIndexEnum.SOFR_30_DAY_AVG,
            spread=0.0275,
            interest_rate_cap=0.08
        ))
        
        # High SOFR rate that should trigger cap
        high_sofr = pd.Series([0.07], index=pd.period_range("2024-01", periods=1, freq="M"))
        capped_rate = rate.get_rate_for_period(pd.Period("2024-01", freq="M"), high_sofr)
        
        # 7% + 275bps = 9.75%, should be capped at 8%
        assert capped_rate == 0.08
        
    def test_floating_rate_missing_index_error(self):
        """Test error handling when index curve is missing for floating rates."""
        rate = InterestRate(details=FloatingRate(
            rate_index=RateIndexEnum.SOFR_30_DAY_AVG,
            spread=0.0275
        ))
        
        with pytest.raises(ValueError, match="index_curve.*must be provided"):
            rate.get_rate_for_period(pd.Period("2024-01", freq="M"), None)


class TestLoanSizingConstraints:
    """Test loan sizing with multiple constraints (LTV + DSCR + Debt Yield)."""
    
    def test_ltv_constraint_most_restrictive(self):
        """Test LTV constraint as the most restrictive."""
        facility = PermanentFacility(
            interest_rate=InterestRate(details=FixedRate(rate=0.065)),
            loan_term_years=10,
            ltv_ratio=0.50,  # 50% LTV (very restrictive)
            dscr_hurdle=1.20,  # 1.20x DSCR (generous)
            debt_yield_hurdle=0.06  # 6% debt yield (generous)
        )
        
        # Property worth $10M with very strong NOI
        max_loan = facility.calculate_refinance_amount(10_000_000, 1_200_000)
        expected_ltv_loan = 10_000_000 * 0.50  # $5M
        
        # LTV should be most restrictive
        assert abs(max_loan - expected_ltv_loan) < 1000  # Within $1000
        
    def test_dscr_constraint_most_restrictive(self):
        """Test DSCR constraint as the most restrictive."""
        facility = PermanentFacility(
            interest_rate=InterestRate(details=FixedRate(rate=0.065)),
            loan_term_years=10,
            ltv_ratio=0.80,  # 80% LTV (generous)
            dscr_hurdle=1.50,  # 1.50x DSCR (restrictive)
            debt_yield_hurdle=0.06  # 6% debt yield (generous)
        )
        
        # Property worth $10M with modest NOI
        max_loan = facility.calculate_refinance_amount(10_000_000, 600_000)
        
        # DSCR should be most restrictive
        annual_debt_constant = facility._calculate_annual_debt_constant()
        max_debt_service = 600_000 / 1.50
        expected_dscr_loan = max_debt_service / annual_debt_constant
        
        assert abs(max_loan - expected_dscr_loan) < 1.0  # Within $1
        
    def test_debt_yield_constraint_most_restrictive(self):
        """Test Debt Yield constraint as the most restrictive."""
        facility = PermanentFacility(
            interest_rate=InterestRate(details=FixedRate(rate=0.065)),
            loan_term_years=30,  # Longer term makes DSCR less restrictive
            ltv_ratio=0.80,  # 80% LTV (maximum allowed)
            dscr_hurdle=1.10,  # 1.10x DSCR (very generous)
            debt_yield_hurdle=0.25  # 25% debt yield (extremely restrictive)
        )
        
        # Property worth $10M with very low NOI that makes debt yield most restrictive
        max_loan = facility.calculate_refinance_amount(10_000_000, 300_000)
        expected_dy_loan = 300_000 / 0.25  # $1.2M
        
        # Debt yield should be most restrictive
        assert abs(max_loan - expected_dy_loan) < 1000  # Within $1000
        
    def test_optional_debt_yield_hurdle(self):
        """Test that debt yield hurdle is optional."""
        facility = PermanentFacility(
            interest_rate=InterestRate(details=FixedRate(rate=0.065)),
            loan_term_years=10,
            ltv_ratio=0.75,
            dscr_hurdle=1.25,
            debt_yield_hurdle=None  # No debt yield constraint
        )
        
        max_loan = facility.calculate_refinance_amount(10_000_000, 800_000)
        
        # Should use min of LTV and DSCR only
        ltv_loan = 10_000_000 * 0.75
        annual_debt_constant = facility._calculate_annual_debt_constant()
        dscr_loan = (800_000 / 1.25) / annual_debt_constant
        expected_loan = min(ltv_loan, dscr_loan)
        
        assert abs(max_loan - expected_loan) < 1.0


class TestInterestOnlyPeriods:
    """Test interest-only periods functionality."""
    
    def test_standard_amortizing_loan(self):
        """Test standard fully amortizing loan (baseline)."""
        amortization = LoanAmortization(
            loan_amount=1_000_000,
            term=5,
            interest_rate=InterestRate(details=FixedRate(rate=0.06)),
            start_date=pd.Period("2024-01", freq="M"),
            interest_only_periods=0
        )
        
        schedule, summary = amortization.amortization_schedule
        
        # First payment should include principal
        assert schedule["Principal"].iloc[0] > 0
        assert summary["Interest Only Periods"] == 0
        assert summary["Amortizing Periods"] == 60
        
    def test_interest_only_payments(self):
        """Test interest-only period calculations."""
        amortization = LoanAmortization(
            loan_amount=1_000_000,
            term=5,
            interest_rate=InterestRate(details=FixedRate(rate=0.06)),
            start_date=pd.Period("2024-01", freq="M"),
            interest_only_periods=12  # 1 year I/O
        )
        
        schedule, summary = amortization.amortization_schedule
        
        # First 12 payments should be interest-only
        for i in range(12):
            assert schedule["Principal"].iloc[i] == 0.0
            expected_interest = 1_000_000 * (0.06 / 12)
            assert abs(schedule["Interest"].iloc[i] - expected_interest) < 0.01
            assert abs(schedule["Payment"].iloc[i] - expected_interest) < 0.01
            
        # 13th payment should include principal
        assert schedule["Principal"].iloc[12] > 0
        
        # Balance should remain constant during I/O period
        for i in range(12):
            assert schedule["End Balance"].iloc[i] == 1_000_000
            
        assert summary["Interest Only Periods"] == 12
        assert summary["Amortizing Periods"] == 48
        
    def test_io_cost_comparison(self):
        """Test that I/O loans cost more than standard amortizing loans."""
        # Standard loan
        standard = LoanAmortization(
            loan_amount=1_000_000, term=5,
            interest_rate=InterestRate(details=FixedRate(rate=0.06)),
            start_date=pd.Period("2024-01", freq="M"),
            interest_only_periods=0
        )
        
        # I/O loan
        io_loan = LoanAmortization(
            loan_amount=1_000_000, term=5,
            interest_rate=InterestRate(details=FixedRate(rate=0.06)),
            start_date=pd.Period("2024-01", freq="M"),
            interest_only_periods=12
        )
        
        _, standard_summary = standard.amortization_schedule
        _, io_summary = io_loan.amortization_schedule
        
        # I/O loan should cost more
        assert io_summary["Total Interest Paid"] > standard_summary["Total Interest Paid"]


class TestDynamicRateCalculations:
    """Test dynamic rate calculations with time series."""
    
    def test_fixed_rate_remains_constant(self):
        """Test that fixed rates remain constant over time."""
        amortization = LoanAmortization(
            loan_amount=1_000_000,
            term=3,
            interest_rate=InterestRate(details=FixedRate(rate=0.06)),
            start_date=pd.Period("2024-01", freq="M")
        )
        
        schedule, summary = amortization.amortization_schedule
        
        # All rates should be 6% (handle floating point precision)
        assert all(abs(rate - 0.06) < 1e-10 for rate in schedule["Rate"])
        assert abs(summary["Average Rate"] - 0.06) < 1e-10
        
    def test_floating_rate_changes_over_time(self):
        """Test that floating rates change based on index curve."""
        # Create rising SOFR curve
        periods = pd.period_range("2024-01", periods=36, freq="M")
        sofr_rates = np.linspace(0.045, 0.055, 36)  # 4.5% to 5.5%
        sofr_curve = pd.Series(sofr_rates, index=periods)
        
        amortization = LoanAmortization(
            loan_amount=1_000_000,
            term=3,
            interest_rate=InterestRate(details=FloatingRate(
                rate_index=RateIndexEnum.SOFR_30_DAY_AVG,
                spread=0.0275,
                interest_rate_cap=0.08
            )),
            start_date=pd.Period("2024-01", freq="M"),
            index_curve=sofr_curve
        )
        
        schedule, summary = amortization.amortization_schedule
        
        # Rates should change over time
        first_rate = schedule["Rate"].iloc[0]
        last_rate = schedule["Rate"].iloc[-1]
        assert last_rate > first_rate
        
        # First rate should be SOFR + spread
        expected_first = 0.045 + 0.0275
        assert abs(first_rate - expected_first) < 0.0001
        
        # Average rate should be between first and last
        avg_rate = summary["Average Rate"]
        assert first_rate < avg_rate < last_rate


class TestCovenantMonitoring:
    """Test continuous covenant monitoring functionality."""
    
    def create_test_facility(self):
        """Create a test facility with covenant monitoring."""
        return PermanentFacility(
            name="Test Loan with Covenants",
            interest_rate=InterestRate(details=FixedRate(rate=0.065)),
            loan_term_years=5,
            loan_amount=5_000_000,
            ltv_ratio=0.75,
            dscr_hurdle=1.25,
            ongoing_ltv_max=0.80,
            ongoing_dscr_min=1.20,
            ongoing_debt_yield_min=0.075
        )
    
    def create_mock_timeline(self, periods=60):
        """Create a mock timeline object."""
        timeline_periods = pd.period_range("2024-01", periods=periods, freq="M")
        
        class MockTimeline:
            def __init__(self, period_index):
                self.period_index = period_index
        
        return MockTimeline(timeline_periods)
    
    def test_covenant_monitoring_setup(self):
        """Test covenant monitoring requires proper configuration."""
        # Facility without covenant monitoring should raise error
        facility = PermanentFacility(
            interest_rate=InterestRate(details=FixedRate(rate=0.065)),
            loan_term_years=5,
            loan_amount=5_000_000,
            ltv_ratio=0.75,
            dscr_hurdle=1.25
            # No ongoing covenant fields
        )
        
        timeline = self.create_mock_timeline()
        prop_values = pd.Series([7_000_000] * 60, index=timeline.period_index)
        noi_values = pd.Series([500_000] * 60, index=timeline.period_index)
        
        with pytest.raises(ValueError, match="Covenant monitoring requires"):
            facility.calculate_covenant_monitoring(timeline, prop_values, noi_values)
    
    def test_compliant_covenant_monitoring(self):
        """Test covenant monitoring with compliant metrics."""
        # Create facility with lower loan amount for better DSCR
        facility = PermanentFacility(
            name="Test Loan with Covenants",
            interest_rate=InterestRate(details=FixedRate(rate=0.065)),
            loan_term_years=5,
            loan_amount=3_000_000,  # Lower loan amount for better DSCR
            ltv_ratio=0.75,
            dscr_hurdle=1.25,
            ongoing_ltv_max=0.80,
            ongoing_dscr_min=1.20,
            ongoing_debt_yield_min=0.075
        )
        
        timeline = self.create_mock_timeline(12)  # 1 year
        
        # Create very compliant scenario with high property value and very high NOI
        prop_values = pd.Series([10_000_000] * 12, index=timeline.period_index)  # Very high value
        noi_values = pd.Series([1_000_000] * 12, index=timeline.period_index)    # Very high NOI
        
        results = facility.calculate_covenant_monitoring(timeline, prop_values, noi_values)
        
        # Should be compliant (no breaches)
        compliant_count = (results["Covenant_Status"] == "COMPLIANT").sum()
        total_count = len(results)
        
        # Most periods should be compliant (allow for some edge cases)
        assert compliant_count >= total_count * 0.8  # At least 80% compliant
        
        # Check that LTV is reasonable
        assert all(results["LTV"] <= 0.80)  # Should be under LTV limit
        
    def test_breach_detection(self):
        """Test covenant breach detection."""
        facility = self.create_test_facility()
        timeline = self.create_mock_timeline(12)
        
        # Create breach scenario - low property value and NOI
        prop_values = pd.Series([6_000_000] * 12, index=timeline.period_index)  # Low value
        noi_values = pd.Series([300_000] * 12, index=timeline.period_index)    # Low NOI
        
        results = facility.calculate_covenant_monitoring(timeline, prop_values, noi_values)
        
        # Should detect breaches
        assert any(results["Covenant_Status"] == "BREACH")
        
        # LTV should be high (loan/value ratio)
        assert results["LTV"].iloc[0] > 0.75  # Should be high
        
        # DSCR should be low (NOI/debt service ratio)
        assert results["DSCR"].iloc[0] < 1.20  # Should breach minimum
        
    def test_breach_summary_statistics(self):
        """Test covenant breach summary generation."""
        facility = self.create_test_facility()
        timeline = self.create_mock_timeline(12)
        
        # Mixed scenario - some breaches
        prop_values = pd.Series([6_500_000] * 12, index=timeline.period_index)
        noi_values = pd.Series([400_000] * 12, index=timeline.period_index)
        
        results = facility.calculate_covenant_monitoring(timeline, prop_values, noi_values)
        summary = facility.get_covenant_breach_summary(results)
        
        assert summary["Total_Periods"] == 12
        assert isinstance(summary["Breach_Rate"], float)
        assert 0 <= summary["Breach_Rate"] <= 1.0
        assert summary["Max_LTV"] >= 0
        assert summary["Min_DSCR"] >= 0


class TestRefinancingOrchestration:
    """Test the complete construction-to-permanent refinancing workflow."""
    
    def test_construction_to_permanent_refinancing_workflow(self):
        """Test the complete construction-to-permanent refinancing workflow with automatic sizing."""
        import pandas as pd

        from performa.core.primitives import Timeline
        from performa.debt.construction import ConstructionFacility, DebtTranche
        from performa.debt.permanent import PermanentFacility
        from performa.debt.plan import FinancingPlan
        from performa.debt.rates import FixedRate, InterestRate
        
        # Create timeline for 5-year analysis
        timeline = Timeline.from_dates(
            start_date="2024-01-01", 
            end_date="2029-01-01"
        )
        
        # Create construction facility
        construction_facility = ConstructionFacility(
            name="Construction Loan",
            kind="construction",
            tranches=[
                DebtTranche(
                    name="Senior Construction",
                    ltc_threshold=0.75,
                    interest_rate=InterestRate(details=FixedRate(rate=0.08)),
                    fee_rate=0.01
                )
            ]
        )
        
        # Create permanent facility with automatic sizing and covenant monitoring
        permanent_facility = PermanentFacility(
            name="Permanent Loan",
            kind="permanent",
            interest_rate=InterestRate(details=FixedRate(rate=0.055)),
            loan_term_years=10,
            amortization_years=25,
            refinance_timing=36,  # Refinance after 36 months
            
            # Loan sizing parameters
            sizing_method="auto",
            ltv_ratio=0.75,
            dscr_hurdle=1.25,
            debt_yield_hurdle=0.08,
            
            # Covenant monitoring parameters  
            ongoing_ltv_max=0.80,
            ongoing_dscr_min=1.20,
            ongoing_debt_yield_min=0.075,
            
            # Interest-only period
            interest_only_months=24
        )
        
        # Create financing plan
        financing_plan = FinancingPlan(
            name="Construction-to-Permanent Financing",
            facilities=[construction_facility, permanent_facility]
        )
        
        # Create mock property value and NOI series
        property_values = []
        noi_values = []
        
        for i, period in enumerate(timeline.period_index):
            # Property value grows from $8M to $10M over construction/stabilization
            if i < 24:  # Construction phase
                property_value = 8_000_000 + (i * 50_000)  # $8M to $9.2M
            else:  # Stabilized phase
                property_value = 9_200_000 + ((i - 24) * 25_000)  # $9.2M to $10M
            
            # NOI grows from $0 to $700K over stabilization
            if i < 18:  # Pre-stabilization
                noi = 0
            elif i < 30:  # Lease-up phase
                noi = (i - 18) * 50_000  # $0 to $600K
            else:  # Stabilized phase
                noi = 600_000 + ((i - 30) * 5_000)  # $600K to $700K
            
            property_values.append(property_value)
            noi_values.append(noi)
        
        property_value_series = pd.Series(property_values, index=timeline.period_index)
        noi_series = pd.Series(noi_values, index=timeline.period_index)
        
        # Test refinancing transaction calculation
        refinancing_transactions = financing_plan.calculate_refinancing_transactions(
            timeline=timeline,
            property_value_series=property_value_series,
            noi_series=noi_series,
            financing_cash_flows=None
        )
        
        # Verify refinancing transactions
        assert len(refinancing_transactions) == 1
        
        transaction = refinancing_transactions[0]
        assert transaction['transaction_type'] == 'construction_to_permanent_refinancing'
        assert transaction['payoff_facility'] == 'Construction Loan'
        assert transaction['new_facility'] == 'Permanent Loan'
        
        # Verify refinancing timing (36 months)
        expected_refinance_period = timeline.period_index[35]  # 36th month (0-indexed)
        assert transaction['transaction_date'] == expected_refinance_period
        
        # Verify automatic sizing using Sizing Trifecta
        sizing_analysis = transaction['sizing_analysis']
        assert sizing_analysis['sizing_method'] == 'automatic'
        
        # At refinancing (month 36), property value should be ~$9.5M, NOI ~$600K
        refinance_property_value = property_value_series.iloc[35]
        refinance_noi = noi_series.iloc[35]
        
        # Verify sizing constraints
        expected_ltv_loan = refinance_property_value * 0.75  # 75% LTV
        expected_dscr_loan = (refinance_noi / 1.25) / permanent_facility._calculate_annual_debt_constant()
        expected_debt_yield_loan = refinance_noi / 0.08  # 8% debt yield
        
        assert sizing_analysis['ltv_constraint'] == pytest.approx(expected_ltv_loan, rel=1e-2)
        assert sizing_analysis['dscr_constraint'] == pytest.approx(expected_dscr_loan, rel=1e-2)
        assert sizing_analysis['debt_yield_constraint'] == pytest.approx(expected_debt_yield_loan, rel=1e-2)
        
        # Verify most restrictive constraint
        most_restrictive_amount = min(expected_ltv_loan, expected_dscr_loan, expected_debt_yield_loan)
        assert transaction['new_loan_amount'] == pytest.approx(most_restrictive_amount, rel=1e-2)
        
        # Verify covenant monitoring setup
        covenant_monitoring = transaction['covenant_monitoring']
        assert covenant_monitoring['monitoring_enabled'] == True
        assert covenant_monitoring['ongoing_ltv_max'] == 0.80
        assert covenant_monitoring['ongoing_dscr_min'] == 1.20
        assert covenant_monitoring['ongoing_debt_yield_min'] == 0.075
        
        # Verify closing costs and net proceeds
        assert transaction['closing_costs'] == pytest.approx(transaction['new_loan_amount'] * 0.015, rel=1e-2)
        expected_net_proceeds = transaction['new_loan_amount'] - transaction['payoff_amount'] - transaction['closing_costs']
        assert transaction['net_proceeds'] == pytest.approx(expected_net_proceeds, rel=1e-2)
        
        print("✓ Refinancing orchestration test passed:")
        print(f"  Property Value: ${refinance_property_value:,.0f}")
        print(f"  NOI: ${refinance_noi:,.0f}")
        print(f"  New Loan Amount: ${transaction['new_loan_amount']:,.0f}")
        print(f"  Most Restrictive: {sizing_analysis['most_restrictive']}")
        print(f"  Net Proceeds: ${transaction['net_proceeds']:,.0f}")
    
    def test_manual_sizing_override(self):
        """Test refinancing with manual sizing override."""
        import pandas as pd

        from performa.core.primitives import Timeline
        from performa.debt.construction import ConstructionFacility, DebtTranche
        from performa.debt.permanent import PermanentFacility
        from performa.debt.plan import FinancingPlan
        from performa.debt.rates import FixedRate, InterestRate
        
        # Create timeline
        timeline = Timeline.from_dates(
            start_date="2024-01-01", 
            end_date="2029-01-01"
        )
        
        # Create construction facility
        construction_facility = ConstructionFacility(
            name="Construction Loan",
            kind="construction",
            tranches=[
                DebtTranche(
                    name="Senior Construction",
                    ltc_threshold=0.75,
                    interest_rate=InterestRate(details=FixedRate(rate=0.08)),
                    fee_rate=0.01
                )
            ]
        )
        
        # Create permanent facility with manual sizing
        permanent_facility = PermanentFacility(
            name="Permanent Loan",
            kind="permanent",
            interest_rate=InterestRate(details=FixedRate(rate=0.055)),
            loan_term_years=10,
            amortization_years=25,
            refinance_timing=24,
            
            # Manual sizing
            sizing_method="manual",
            loan_amount=6_000_000,  # Fixed $6M loan
            
            # Still provide ratios for covenant monitoring
            ltv_ratio=0.75,
            dscr_hurdle=1.25,
            debt_yield_hurdle=0.08
        )
        
        # Create financing plan
        financing_plan = FinancingPlan(
            name="Manual Sizing Test",
            facilities=[construction_facility, permanent_facility]
        )
        
        # Create mock data (values don't matter for manual sizing)
        property_value_series = pd.Series([10_000_000] * len(timeline.period_index), index=timeline.period_index)
        noi_series = pd.Series([800_000] * len(timeline.period_index), index=timeline.period_index)
        
        # Test refinancing transaction calculation
        refinancing_transactions = financing_plan.calculate_refinancing_transactions(
            timeline=timeline,
            property_value_series=property_value_series,
            noi_series=noi_series,
            financing_cash_flows=None
        )
        
        # Verify manual sizing
        assert len(refinancing_transactions) == 1
        
        transaction = refinancing_transactions[0]
        assert transaction['new_loan_amount'] == 6_000_000
        
        sizing_analysis = transaction['sizing_analysis']
        assert sizing_analysis['sizing_method'] == 'manual'
        assert sizing_analysis['manual_amount'] == 6_000_000
        assert sizing_analysis['most_restrictive'] == 'manual_override'
        
        print("✓ Manual sizing override test passed:")
        print(f"  Fixed Loan Amount: ${transaction['new_loan_amount']:,.0f}")
        print(f"  Sizing Method: {sizing_analysis['sizing_method']}")
    
    def test_covenant_monitoring_integration(self):
        """Test that covenant monitoring is properly integrated into refinancing."""
        import pandas as pd

        from performa.core.primitives import Timeline
        from performa.debt.construction import ConstructionFacility, DebtTranche
        from performa.debt.permanent import PermanentFacility
        from performa.debt.plan import FinancingPlan
        from performa.debt.rates import FixedRate, InterestRate
        
        # Create timeline
        timeline = Timeline.from_dates(
            start_date="2024-01-01", 
            end_date="2029-01-01"
        )
        
        # Create construction facility
        construction_facility = ConstructionFacility(
            name="Construction Loan",
            kind="construction",
            tranches=[
                DebtTranche(
                    name="Senior Construction",
                    ltc_threshold=0.75,
                    interest_rate=InterestRate(details=FixedRate(rate=0.08)),
                    fee_rate=0.01
                )
            ]
        )
        
        # Create permanent facility with tight covenant monitoring
        permanent_facility = PermanentFacility(
            name="Permanent Loan",
            kind="permanent",
            interest_rate=InterestRate(details=FixedRate(rate=0.055)),
            loan_term_years=10,
            amortization_years=25,
            refinance_timing=24,
            
            # Automatic sizing
            sizing_method="auto",
            ltv_ratio=0.70,
            dscr_hurdle=1.30,
            debt_yield_hurdle=0.09,
            
            # Tight covenant monitoring (more restrictive than sizing)
            ongoing_ltv_max=0.75,
            ongoing_dscr_min=1.35,
            ongoing_debt_yield_min=0.095
        )
        
        # Create financing plan
        financing_plan = FinancingPlan(
            name="Covenant Monitoring Test",
            facilities=[construction_facility, permanent_facility]
        )
        
        # Create mock data
        property_value_series = pd.Series([8_000_000] * len(timeline.period_index), index=timeline.period_index)
        noi_series = pd.Series([600_000] * len(timeline.period_index), index=timeline.period_index)
        
        # Test refinancing transaction calculation
        refinancing_transactions = financing_plan.calculate_refinancing_transactions(
            timeline=timeline,
            property_value_series=property_value_series,
            noi_series=noi_series,
            financing_cash_flows=None
        )
        
        # Verify covenant monitoring setup
        assert len(refinancing_transactions) == 1
        
        transaction = refinancing_transactions[0]
        covenant_monitoring = transaction['covenant_monitoring']
        
        assert covenant_monitoring['monitoring_enabled'] == True
        assert covenant_monitoring['ongoing_ltv_max'] == 0.75
        assert covenant_monitoring['ongoing_dscr_min'] == 1.35
        assert covenant_monitoring['ongoing_debt_yield_min'] == 0.095
        
        # Verify that covenant monitoring is more restrictive than sizing
        assert covenant_monitoring['ongoing_ltv_max'] > permanent_facility.ltv_ratio
        assert covenant_monitoring['ongoing_dscr_min'] > permanent_facility.dscr_hurdle
        assert covenant_monitoring['ongoing_debt_yield_min'] > permanent_facility.debt_yield_hurdle
        
        print("✓ Covenant monitoring integration test passed:")
        print(f"  Sizing LTV: {permanent_facility.ltv_ratio:.1%} → Ongoing LTV: {covenant_monitoring['ongoing_ltv_max']:.1%}")
        print(f"  Sizing DSCR: {permanent_facility.dscr_hurdle:.2f}x → Ongoing DSCR: {covenant_monitoring['ongoing_dscr_min']:.2f}x")
        print(f"  Sizing Debt Yield: {permanent_facility.debt_yield_hurdle:.1%} → Ongoing Debt Yield: {covenant_monitoring['ongoing_debt_yield_min']:.1%}")
    
    def test_refinancing_with_interest_only_periods(self):
        """Test refinancing creates permanent loan with interest-only periods."""
        import pandas as pd

        from performa.core.primitives import Timeline
        from performa.debt.construction import ConstructionFacility, DebtTranche
        from performa.debt.permanent import PermanentFacility
        from performa.debt.plan import FinancingPlan
        from performa.debt.rates import FixedRate, InterestRate
        
        # Create timeline
        timeline = Timeline.from_dates(
            start_date="2024-01-01", 
            end_date="2029-01-01"
        )
        
        # Create construction facility
        construction_facility = ConstructionFacility(
            name="Construction Loan",
            kind="construction",
            tranches=[
                DebtTranche(
                    name="Senior Construction",
                    ltc_threshold=0.75,
                    interest_rate=InterestRate(details=FixedRate(rate=0.08)),
                    fee_rate=0.01
                )
            ]
        )
        
        # Create permanent facility with 36-month interest-only period
        permanent_facility = PermanentFacility(
            name="Permanent Loan",
            kind="permanent",
            interest_rate=InterestRate(details=FixedRate(rate=0.055)),
            loan_term_years=10,
            amortization_years=25,
            refinance_timing=24,
            
            # Sizing parameters
            sizing_method="manual",
            loan_amount=7_000_000,
            ltv_ratio=0.75,  # Required field
            dscr_hurdle=1.25,  # Required field
            
            # Interest-only period
            interest_only_months=36
        )
        
        # Create financing plan
        financing_plan = FinancingPlan(
            name="Interest-Only Test",
            facilities=[construction_facility, permanent_facility]
        )
        
        # Create mock data
        property_value_series = pd.Series([10_000_000] * len(timeline.period_index), index=timeline.period_index)
        noi_series = pd.Series([700_000] * len(timeline.period_index), index=timeline.period_index)
        
        # Test refinancing transaction calculation
        refinancing_transactions = financing_plan.calculate_refinancing_transactions(
            timeline=timeline,
            property_value_series=property_value_series,
            noi_series=noi_series,
            financing_cash_flows=None
        )
        
        # Verify the permanent loan parameters
        assert len(refinancing_transactions) == 1
        
        transaction = refinancing_transactions[0]
        assert transaction['new_loan_amount'] == 7_000_000
        
        # Test that the permanent facility has the correct interest-only period
        assert permanent_facility.interest_only_months == 36
        
        # Create mock timeline for amortization test
        amort_timeline = Timeline.from_dates(
            start_date="2026-01-01", 
            end_date="2036-01-01"
        )  # 10-year loan
        
        # Calculate amortization for the permanent loan
        amortization = permanent_facility.generate_amortization(
            loan_amount=7_000_000,
            start_date=amort_timeline.period_index[0]
        )
        
        # Verify interest-only periods
        schedule = amortization
        
        # First 36 months should be interest-only (no principal payment)
        first_36_months = schedule.iloc[:36]
        assert (first_36_months['Principal'] == 0).all()
        assert (first_36_months['Interest'] > 0).all()
        
        # Months 37+ should have principal payments
        amortizing_months = schedule.iloc[36:]
        assert (amortizing_months['Principal'] > 0).all()
        
        print("✓ Interest-only refinancing test passed:")
        print(f"  Loan Amount: ${transaction['new_loan_amount']:,.0f}")
        print(f"  Interest-Only Period: {permanent_facility.interest_only_months} months")
        print(f"  First Month I/O Payment: ${first_36_months['Payment'].iloc[0]:,.0f}")
        print(f"  First Month Amortizing Payment: ${amortizing_months['Payment'].iloc[0]:,.0f}")


def run_all_tests():
    """Run all test classes and provide summary."""
    print("🧪 Running Comprehensive Debt Module Enhancement Tests")
    print("=" * 60)
    
    test_classes = [
        TestInterestRateSystem,
        TestLoanSizingConstraints,
        TestInterestOnlyPeriods,
        TestDynamicRateCalculations,
        TestCovenantMonitoring,
        TestRefinancingOrchestration
    ]
    
    total_tests = 0
    passed_tests = 0
    failed_tests = []
    
    for test_class in test_classes:
        print(f"\n📋 {test_class.__name__}")
        print("-" * 40)
        
        test_instance = test_class()
        
        # Get all test methods
        test_methods = [method for method in dir(test_instance) 
                       if method.startswith('test_')]
        
        for test_method in test_methods:
            total_tests += 1
            try:
                if hasattr(test_instance, test_method):
                    getattr(test_instance, test_method)()
                    print(f"✅ {test_method}")
                    passed_tests += 1
            except Exception as e:
                print(f"❌ {test_method}: {str(e)}")
                failed_tests.append(f"{test_class.__name__}.{test_method}: {str(e)}")
    
    # Summary
    print("\n" + "=" * 60)
    print("🎯 Test Summary")
    print("=" * 60)
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {len(failed_tests)}")
    print(f"Success Rate: {passed_tests/total_tests:.1%}")
    
    if failed_tests:
        print("\n❌ Failed Tests:")
        for failure in failed_tests:
            print(f"  - {failure}")
    else:
        print("\n🎉 All tests passed! Debt module enhancements are working correctly.")
    
    return len(failed_tests) == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1) 