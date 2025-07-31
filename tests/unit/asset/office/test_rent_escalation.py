# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

import unittest
from datetime import date

import pandas as pd

from performa.analysis import AnalysisContext
from performa.asset.office.lease import OfficeLease
from performa.asset.office.lease_spec import OfficeLeaseSpec
from performa.asset.office.rent_escalation import OfficeRentEscalation
from performa.core.primitives import (
    FrequencyEnum,
    GlobalSettings,
    LeaseTypeEnum,
    ProgramUseEnum,
    Timeline,
    PropertyAttributeKey,
    UponExpirationEnum,
)


class TestOfficeRentEscalation(unittest.TestCase):
    """
    Comprehensive unit tests for rent escalation functionality.
    
    Tests cover:
    - Fixed escalations (recurring and non-recurring)
    - Percentage escalations (relative and absolute, recurring and non-recurring)
    - Escalation timing (different start dates, frequencies)
    - CPI escalations (NotImplementedError validation)
    - Integration with lease cash flow calculations
    - Edge cases and validation
    """

    def setUp(self):
        """Set up common test fixtures."""
        self.analysis_start_date = date(2024, 1, 1)
        self.timeline = Timeline(start_date=date(2024, 1, 1), duration_months=36)  # 3-year timeline for escalations
        self.settings = GlobalSettings(analysis_start_date=self.analysis_start_date)

        # Base lease specification without escalation
        self.base_lease_spec = OfficeLeaseSpec(
            tenant_name="Test Tenant",
            suite="100",
            floor="1",
            area=10000.0,
            use_type=ProgramUseEnum.OFFICE,
            lease_type=LeaseTypeEnum.GROSS,
            start_date=date(2024, 1, 1),
            term_months=36,
            base_rent_value=30.0,  # $30/SF/year
            base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
            base_rent_frequency=FrequencyEnum.ANNUAL,
            upon_expiration=UponExpirationEnum.MARKET,
        )

    def test_fixed_escalation_non_recurring(self):
        """
        Test fixed amount escalation applied once.
        
        Scenario: $2/SF/year increase starting Year 2
        Expected: Years 1-12: $30/SF, Years 13+: $32/SF
        """
        escalation = OfficeRentEscalation(
            type="fixed",
            rate=2.0,  # $2/SF/year increase
            reference=PropertyAttributeKey.NET_RENTABLE_AREA,
            is_relative=False,
            start_date=date(2025, 1, 1),  # Year 2
            recurring=False,
            frequency_months=None
        )

        lease_spec = self.base_lease_spec.model_copy(
            update={"rent_escalations": escalation}
        )

        lease = OfficeLease.from_spec(
            lease_spec, self.analysis_start_date, self.timeline, self.settings
        )

        context = AnalysisContext(
            timeline=self.timeline,
            settings=self.settings,
            property_data=None,
        )

        cash_flows = lease.compute_cf(context)

        # Expected values
        base_monthly_rent = (30.0 * 10000) / 12     # $25,000/month
        escalated_monthly_rent = (32.0 * 10000) / 12  # $26,667/month

        # Year 1 (2024): Base rent
        year1_periods = self.timeline.period_index[:12]  # Jan-Dec 2024
        for period in year1_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], base_monthly_rent, places=2,
                                 msg=f"Year 1 rent should be base amount in {period}")

        # Year 2+ (2025+): Escalated rent
        year2_periods = self.timeline.period_index[12:]  # Jan 2025 onwards
        for period in year2_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], escalated_monthly_rent, places=2,
                                 msg=f"Year 2+ rent should be escalated amount in {period}")

    def test_fixed_escalation_recurring_annual(self):
        """
        Test fixed amount escalation applied annually.
        
        Scenario: $1/SF/year increase every year starting Year 2
        Expected: Year 1: $30/SF, Year 2: $31/SF, Year 3: $32/SF
        """
        escalation = OfficeRentEscalation(
            type="fixed",
            rate=1.0,  # $1/SF/year increase
            reference=PropertyAttributeKey.NET_RENTABLE_AREA,
            is_relative=False,
            start_date=date(2025, 1, 1),  # Year 2
            recurring=True,
            frequency_months=12  # Annual escalation
        )

        lease_spec = self.base_lease_spec.model_copy(
            update={"rent_escalations": escalation}
        )

        lease = OfficeLease.from_spec(
            lease_spec, self.analysis_start_date, self.timeline, self.settings
        )

        context = AnalysisContext(
            timeline=self.timeline,
            settings=self.settings,
            property_data=None,
        )

        cash_flows = lease.compute_cf(context)

        # Expected values
        year1_rent = (30.0 * 10000) / 12  # $25,000/month
        year2_rent = (31.0 * 10000) / 12  # $25,833/month  
        year3_rent = (32.0 * 10000) / 12  # $26,667/month

        # Year 1: Base rent
        year1_periods = self.timeline.period_index[:12]
        for period in year1_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], year1_rent, places=2,
                                 msg=f"Year 1 rent should be $30/SF in {period}")

        # Year 2: First escalation
        year2_periods = self.timeline.period_index[12:24]
        for period in year2_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], year2_rent, places=2,
                                 msg=f"Year 2 rent should be $31/SF in {period}")

        # Year 3: Second escalation
        year3_periods = self.timeline.period_index[24:]
        for period in year3_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], year3_rent, places=2,
                                 msg=f"Year 3 rent should be $32/SF in {period}")

    def test_percentage_escalation_relative_non_recurring(self):
        """
        Test relative percentage escalation applied once.
        
        Scenario: 10% increase starting Year 2 (multiplicative)
        Expected: Year 1: $30/SF, Year 2+: $33/SF (30 * 1.10)
        """
        escalation = OfficeRentEscalation(
            type="percentage",
            rate=0.10,  # 10% increase (0.10 for 10%)
            is_relative=True,  # Multiplicative
            start_date=date(2025, 1, 1),  # Year 2
            recurring=False,
            frequency_months=None
        )

        lease_spec = self.base_lease_spec.model_copy(
            update={"rent_escalations": escalation}
        )

        lease = OfficeLease.from_spec(
            lease_spec, self.analysis_start_date, self.timeline, self.settings
        )

        context = AnalysisContext(
            timeline=self.timeline,
            settings=self.settings,
            property_data=None,
        )

        cash_flows = lease.compute_cf(context)

        # Expected values
        base_monthly_rent = (30.0 * 10000) / 12      # $25,000/month
        escalated_monthly_rent = (33.0 * 10000) / 12  # $27,500/month (30 * 1.10)

        # Year 1: Base rent
        year1_periods = self.timeline.period_index[:12]
        for period in year1_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], base_monthly_rent, places=2,
                                 msg=f"Year 1 rent should be base amount in {period}")

        # Year 2+: Escalated rent
        year2_periods = self.timeline.period_index[12:]
        for period in year2_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], escalated_monthly_rent, places=2,
                                 msg=f"Year 2+ rent should be 110% of base in {period}")

    def test_percentage_escalation_absolute_non_recurring(self):
        """
        Test absolute percentage escalation applied once.
        
        Scenario: 10% increase starting Year 2 (additive: base + 10% of base)
        Expected: Year 1: $30/SF, Year 2+: $33/SF (30 + 3)
        """
        escalation = OfficeRentEscalation(
            type="percentage",
            rate=0.10,  # 10% increase (0.10 for 10%)
            is_relative=False,  # Additive
            start_date=date(2025, 1, 1),  # Year 2
            recurring=False,
            frequency_months=None
        )

        lease_spec = self.base_lease_spec.model_copy(
            update={"rent_escalations": escalation}
        )

        lease = OfficeLease.from_spec(
            lease_spec, self.analysis_start_date, self.timeline, self.settings
        )

        context = AnalysisContext(
            timeline=self.timeline,
            settings=self.settings,
            property_data=None,
        )

        cash_flows = lease.compute_cf(context)

        # Expected values
        base_monthly_rent = (30.0 * 10000) / 12      # $25,000/month
        escalated_monthly_rent = (33.0 * 10000) / 12  # $27,500/month (30 + 3)

        # Year 1: Base rent
        year1_periods = self.timeline.period_index[:12]
        for period in year1_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], base_monthly_rent, places=2,
                                 msg=f"Year 1 rent should be base amount in {period}")

        # Year 2+: Escalated rent (base + 10%)
        year2_periods = self.timeline.period_index[12:]
        for period in year2_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], escalated_monthly_rent, places=2,
                                 msg=f"Year 2+ rent should be base + 10% in {period}")

    def test_percentage_escalation_relative_recurring(self):
        """
        Test relative percentage escalation applied annually.
        
        Scenario: 3% compound increase every year starting Year 2
        Expected: Year 1: $30/SF, Year 2: $30.90/SF, Year 3: $31.83/SF
        """
        escalation = OfficeRentEscalation(
            type="percentage",
            rate=0.03,  # 3% increase (0.03 for 3%)
            is_relative=True,  # Compound growth
            start_date=date(2025, 1, 1),  # Year 2
            recurring=True,
            frequency_months=12  # Annual escalation
        )

        lease_spec = self.base_lease_spec.model_copy(
            update={"rent_escalations": escalation}
        )

        lease = OfficeLease.from_spec(
            lease_spec, self.analysis_start_date, self.timeline, self.settings
        )

        context = AnalysisContext(
            timeline=self.timeline,
            settings=self.settings,
            property_data=None,
        )

        cash_flows = lease.compute_cf(context)

        # Expected values (compound growth)
        year1_rent = (30.0 * 10000) / 12              # $25,000/month
        year2_rent = (30.0 * 1.03 * 10000) / 12      # $25,750/month  
        year3_rent = (30.0 * 1.03 * 1.03 * 10000) / 12  # $26,523/month

        # Year 1: Base rent
        year1_periods = self.timeline.period_index[:12]
        for period in year1_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], year1_rent, places=2,
                                 msg=f"Year 1 rent should be base amount in {period}")

        # Year 2: First escalation (103% of base)
        year2_periods = self.timeline.period_index[12:24]
        for period in year2_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], year2_rent, places=2,
                                 msg=f"Year 2 rent should be 103% of base in {period}")

        # Year 3: Second escalation (103% of Year 2)
        year3_periods = self.timeline.period_index[24:]
        for period in year3_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], year3_rent, places=2,
                                 msg=f"Year 3 rent should be 103% of Year 2 in {period}")

    def test_escalation_currency_amount(self):
        """
        Test fixed currency amount escalation.
        
        Scenario: $1,000/month increase starting Year 2
        Expected: Year 1: $25,000/month, Year 2+: $26,000/month
        """
        escalation = OfficeRentEscalation(
            type="fixed",
            rate=12000.0,  # $12,000/year = $1,000/month
            is_relative=False,
            start_date=date(2025, 1, 1),  # Year 2
            recurring=False,
            frequency_months=None
        )

        lease_spec = self.base_lease_spec.model_copy(
            update={"rent_escalations": escalation}
        )

        lease = OfficeLease.from_spec(
            lease_spec, self.analysis_start_date, self.timeline, self.settings
        )

        context = AnalysisContext(
            timeline=self.timeline,
            settings=self.settings,
            property_data=None,
        )

        cash_flows = lease.compute_cf(context)

        # Expected values
        base_monthly_rent = (30.0 * 10000) / 12      # $25,000/month
        escalated_monthly_rent = base_monthly_rent + 1000  # $26,000/month

        # Year 1: Base rent
        year1_periods = self.timeline.period_index[:12]
        for period in year1_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], base_monthly_rent, places=2,
                                 msg=f"Year 1 rent should be base amount in {period}")

        # Year 2+: Escalated rent
        year2_periods = self.timeline.period_index[12:]
        for period in year2_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], escalated_monthly_rent, places=2,
                                 msg=f"Year 2+ rent should be base + $1,000 in {period}")

    def test_escalation_mid_year_start(self):
        """
        Test escalation starting mid-year.
        
        Scenario: 5% increase starting July Year 1
        Expected: Jan-Jun: $30/SF, Jul-Dec: $31.50/SF
        """
        escalation = OfficeRentEscalation(
            type="percentage",
            rate=0.05,  # 5% increase (0.05 for 5%)
            is_relative=True,
            start_date=date(2024, 7, 1),  # July Year 1
            recurring=False,
            frequency_months=None
        )

        lease_spec = self.base_lease_spec.model_copy(
            update={"rent_escalations": escalation}
        )

        lease = OfficeLease.from_spec(
            lease_spec, self.analysis_start_date, self.timeline, self.settings
        )

        context = AnalysisContext(
            timeline=self.timeline,
            settings=self.settings,
            property_data=None,
        )

        cash_flows = lease.compute_cf(context)

        # Expected values
        base_monthly_rent = (30.0 * 10000) / 12       # $25,000/month
        escalated_monthly_rent = (31.5 * 10000) / 12  # $26,250/month

        # Jan-Jun 2024: Base rent
        pre_escalation_periods = self.timeline.period_index[:6]  # Jan-Jun 2024
        for period in pre_escalation_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], base_monthly_rent, places=2,
                                 msg=f"Pre-escalation rent should be base amount in {period}")

        # Jul 2024 onwards: Escalated rent
        post_escalation_periods = self.timeline.period_index[6:]  # Jul 2024 onwards
        for period in post_escalation_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], escalated_monthly_rent, places=2,
                                 msg=f"Post-escalation rent should be 105% of base in {period}")

    def test_no_escalation_baseline(self):
        """
        Test lease without escalation for baseline comparison.
        
        Scenario: No escalation defined
        Expected: Constant rent throughout term
        """
        # No escalation added to base lease spec
        lease = OfficeLease.from_spec(
            self.base_lease_spec, self.analysis_start_date, self.timeline, self.settings
        )

        context = AnalysisContext(
            timeline=self.timeline,
            settings=self.settings,
            property_data=None,
        )

        cash_flows = lease.compute_cf(context)

        # Expected constant rent
        expected_monthly_rent = (30.0 * 10000) / 12  # $25,000/month

        # All periods should have same rent
        for period in self.timeline.period_index:
            self.assertAlmostEqual(cash_flows["base_rent"][period], expected_monthly_rent, places=2,
                                 msg=f"Rent should be constant without escalation in {period}")

    def test_escalation_frequency_quarterly(self):
        """
        Test escalation with quarterly frequency.
        
        Scenario: $0.25/SF increase every quarter starting Year 2
        Expected: Quarterly step increases
        """
        escalation = OfficeRentEscalation(
            type="fixed",
            rate=0.25,  # $0.25/SF/quarter
            reference=PropertyAttributeKey.NET_RENTABLE_AREA,
            is_relative=False,
            start_date=date(2025, 1, 1),  # Year 2
            recurring=True,
            frequency_months=3  # Quarterly
        )

        lease_spec = self.base_lease_spec.model_copy(
            update={"rent_escalations": escalation}
        )

        lease = OfficeLease.from_spec(
            lease_spec, self.analysis_start_date, self.timeline, self.settings
        )

        context = AnalysisContext(
            timeline=self.timeline,
            settings=self.settings,
            property_data=None,
        )

        cash_flows = lease.compute_cf(context)

        # Expected rents
        base_rent = (30.0 * 10000) / 12        # $25,000/month
        q1_2025_rent = (30.25 * 10000) / 12    # $25,208/month (+$0.25/SF)
        q2_2025_rent = (30.50 * 10000) / 12    # $25,417/month (+$0.50/SF)
        q3_2025_rent = (30.75 * 10000) / 12    # $25,625/month (+$0.75/SF)

        # Year 1 (2024): Base rent
        year1_periods = self.timeline.period_index[:12]
        for period in year1_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], base_rent, places=2,
                                 msg=f"Year 1 rent should be base in {period}")

        # Q1 2025 (Jan-Mar): First escalation
        q1_periods = self.timeline.period_index[12:15]  # Jan-Mar 2025
        for period in q1_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], q1_2025_rent, places=2,
                                 msg=f"Q1 2025 rent should include 1 escalation in {period}")

        # Q2 2025 (Apr-Jun): Second escalation  
        q2_periods = self.timeline.period_index[15:18]  # Apr-Jun 2025
        for period in q2_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], q2_2025_rent, places=2,
                                 msg=f"Q2 2025 rent should include 2 escalations in {period}")

        # Q3 2025 (Jul-Sep): Third escalation
        q3_periods = self.timeline.period_index[18:21]  # Jul-Sep 2025
        for period in q3_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], q3_2025_rent, places=2,
                                 msg=f"Q3 2025 rent should include 3 escalations in {period}")

    def test_growth_rate_constant_percentage_escalation(self):
        """
        Test percentage escalation using constant growth rate.
        
        Scenario: 3% growth rate applied as percentage escalation 
        Expected: 3% compound growth from Year 2 onwards
        """
        from performa.core.primitives.growth_rates import PercentageGrowthRate
        
        # Create a constant 3% growth rate
        growth_rate = PercentageGrowthRate(name="Market Growth", value=0.03)
        
        escalation = OfficeRentEscalation(
            type="percentage",
            rate=growth_rate,
            is_relative=True,  # Compound growth
            start_date=date(2025, 1, 1),  # Year 2
            recurring=True,
            frequency_months=12  # Annual escalation
        )

        lease_spec = self.base_lease_spec.model_copy(
            update={"rent_escalations": escalation}
        )

        lease = OfficeLease.from_spec(
            lease_spec, self.analysis_start_date, self.timeline, self.settings
        )

        context = AnalysisContext(
            timeline=self.timeline,
            settings=self.settings,
            property_data=None,
        )

        cash_flows = lease.compute_cf(context)

        # Expected values (compound growth)
        year1_rent = (30.0 * 10000) / 12              # $25,000/month
        year2_rent = (30.0 * 1.03 * 10000) / 12      # $25,750/month  
        year3_rent = (30.0 * 1.03 * 1.03 * 10000) / 12  # $26,523/month

        # Year 1: Base rent
        year1_periods = self.timeline.period_index[:12]
        for period in year1_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], year1_rent, places=2,
                                 msg=f"Year 1 rent should be base amount in {period}")

        # Year 2: First escalation (103% of base)
        year2_periods = self.timeline.period_index[12:24]
        for period in year2_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], year2_rent, places=2,
                                 msg=f"Year 2 rent should be 103% of base in {period}")

        # Year 3: Second escalation (103% of Year 2)
        year3_periods = self.timeline.period_index[24:]
        for period in year3_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], year3_rent, places=2,
                                 msg=f"Year 3 rent should be 103% of Year 2 in {period}")

    def test_escalation_rate_fixed_escalation(self):
        """
        Test fixed escalation using escalation rate for dollar amounts.
        
        Scenario: Escalation rate defining $1.50/SF increase annually
        Expected: Cumulative $1.50/SF increases each year
        """
        from performa.core.primitives.growth_rates import FixedGrowthRate
        
        # Create fixed escalation rate representing $1.50/SF/year increase
        escalation_rate = FixedGrowthRate(name="Fixed Growth", value=1.50)
        
        escalation = OfficeRentEscalation(
            type="fixed",
            rate=escalation_rate,
            reference=PropertyAttributeKey.NET_RENTABLE_AREA,
            is_relative=False,
            start_date=date(2025, 1, 1),  # Year 2
            recurring=True,
            frequency_months=12  # Annual escalation
        )

        lease_spec = self.base_lease_spec.model_copy(
            update={"rent_escalations": escalation}
        )

        lease = OfficeLease.from_spec(
            lease_spec, self.analysis_start_date, self.timeline, self.settings
        )

        context = AnalysisContext(
            timeline=self.timeline,
            settings=self.settings,
            property_data=None,
        )

        cash_flows = lease.compute_cf(context)

        # Expected values (cumulative fixed increases)
        year1_rent = (30.0 * 10000) / 12              # $25,000/month
        year2_rent = (31.5 * 10000) / 12              # $26,250/month (+$1.50/SF)
        year3_rent = (33.0 * 10000) / 12              # $27,500/month (+$3.00/SF total)

        # Year 1: Base rent
        year1_periods = self.timeline.period_index[:12]
        for period in year1_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], year1_rent, places=2,
                                 msg=f"Year 1 rent should be base amount in {period}")

        # Year 2: First escalation (+$1.50/SF)
        year2_periods = self.timeline.period_index[12:24]
        for period in year2_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], year2_rent, places=2,
                                 msg=f"Year 2 rent should be base + $1.50/SF in {period}")

        # Year 3: Second escalation (+$3.00/SF total)
        year3_periods = self.timeline.period_index[24:]
        for period in year3_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], year3_rent, places=2,
                                 msg=f"Year 3 rent should be base + $3.00/SF in {period}")

    def test_growth_rate_time_series(self):
        """
        Test growth rate using pandas Series with time-based rates.
        
        Scenario: Different growth rates by period (2% Year 2, 4% Year 3)
        Expected: Variable percentage increases based on period
        """
        from performa.core.primitives.growth_rates import PercentageGrowthRate
        
        # Create time-based growth rates
        growth_series = pd.Series({
            pd.Period("2025-01", freq="M"): 0.02,  # 2% for Year 2
            pd.Period("2025-02", freq="M"): 0.02,
            pd.Period("2025-03", freq="M"): 0.02,
            pd.Period("2025-04", freq="M"): 0.02,
            pd.Period("2025-05", freq="M"): 0.02,
            pd.Period("2025-06", freq="M"): 0.02,
            pd.Period("2025-07", freq="M"): 0.02,
            pd.Period("2025-08", freq="M"): 0.02,
            pd.Period("2025-09", freq="M"): 0.02,
            pd.Period("2025-10", freq="M"): 0.02,
            pd.Period("2025-11", freq="M"): 0.02,
            pd.Period("2025-12", freq="M"): 0.02,
            pd.Period("2026-01", freq="M"): 0.04,  # 4% for Year 3
            pd.Period("2026-02", freq="M"): 0.04,
            pd.Period("2026-03", freq="M"): 0.04,
            pd.Period("2026-04", freq="M"): 0.04,
            pd.Period("2026-05", freq="M"): 0.04,
            pd.Period("2026-06", freq="M"): 0.04,
            pd.Period("2026-07", freq="M"): 0.04,
            pd.Period("2026-08", freq="M"): 0.04,
            pd.Period("2026-09", freq="M"): 0.04,
            pd.Period("2026-10", freq="M"): 0.04,
            pd.Period("2026-11", freq="M"): 0.04,
            pd.Period("2026-12", freq="M"): 0.04,
        })
        
        growth_rate = PercentageGrowthRate(name="Variable Growth", value=growth_series)
        
        escalation = OfficeRentEscalation(
            type="percentage",
            rate=growth_rate,
            is_relative=True,  # Compound growth
            start_date=date(2025, 1, 1),  # Year 2
            recurring=True,
            frequency_months=12  # Annual escalation
        )

        lease_spec = self.base_lease_spec.model_copy(
            update={"rent_escalations": escalation}
        )

        lease = OfficeLease.from_spec(
            lease_spec, self.analysis_start_date, self.timeline, self.settings
        )

        context = AnalysisContext(
            timeline=self.timeline,
            settings=self.settings,
            property_data=None,
        )

        cash_flows = lease.compute_cf(context)

        # Expected values (compound growth with variable rates)
        year1_rent = (30.0 * 10000) / 12              # $25,000/month
        year2_rent = (30.0 * 1.02 * 10000) / 12      # $25,500/month (2% growth)
        year3_rent = (30.0 * 1.02 * 1.04 * 10000) / 12  # $26,520/month (2% then 4%)

        # Year 1: Base rent
        year1_periods = self.timeline.period_index[:12]
        for period in year1_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], year1_rent, places=2,
                                 msg=f"Year 1 rent should be base amount in {period}")

        # Year 2: 2% escalation
        year2_periods = self.timeline.period_index[12:24]
        for period in year2_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], year2_rent, places=2,
                                 msg=f"Year 2 rent should be 102% of base in {period}")

        # Year 3: 4% escalation on Year 2 rent
        year3_periods = self.timeline.period_index[24:]
        for period in year3_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], year3_rent, places=2,
                                 msg=f"Year 3 rent should be 104% of Year 2 in {period}")

    def test_growth_rate_dict_based(self):
        """
        Test growth rate using dictionary with date keys.
        
        Scenario: Growth rates defined for specific dates
        Expected: Rates applied based on date mapping
        """
        from datetime import date

        from performa.core.primitives.growth_rates import PercentageGrowthRate
        
        # Create date-based growth rates
        growth_dict = {
            date(2025, 1, 1): 0.025,  # 2.5% for Year 2
            date(2026, 1, 1): 0.035,  # 3.5% for Year 3
        }
        
        growth_rate = PercentageGrowthRate(name="Date-based Growth", value=growth_dict)
        
        escalation = OfficeRentEscalation(
            type="percentage",
            rate=growth_rate,
            is_relative=True,  # Compound growth
            start_date=date(2025, 1, 1),  # Year 2
            recurring=True,
            frequency_months=12  # Annual escalation
        )

        lease_spec = self.base_lease_spec.model_copy(
            update={"rent_escalations": escalation}
        )

        lease = OfficeLease.from_spec(
            lease_spec, self.analysis_start_date, self.timeline, self.settings
        )

        context = AnalysisContext(
            timeline=self.timeline,
            settings=self.settings,
            property_data=None,
        )

        cash_flows = lease.compute_cf(context)

        # Expected values (compound growth with date-based rates)
        year1_rent = (30.0 * 10000) / 12                 # $25,000/month
        year2_rent = (30.0 * 1.025 * 10000) / 12        # $25,625/month (2.5% growth)
        year3_rent = (30.0 * 1.025 * 1.035 * 10000) / 12  # $26,521/month (2.5% then 3.5%)

        # Year 1: Base rent
        year1_periods = self.timeline.period_index[:12]
        for period in year1_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], year1_rent, places=2,
                                 msg=f"Year 1 rent should be base amount in {period}")

        # Year 2: 2.5% escalation
        year2_periods = self.timeline.period_index[12:24]
        for period in year2_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], year2_rent, places=2,
                                 msg=f"Year 2 rent should be 102.5% of base in {period}")

        # Year 3: 3.5% escalation on Year 2 rent
        year3_periods = self.timeline.period_index[24:]
        for period in year3_periods:
            self.assertAlmostEqual(cash_flows["base_rent"][period], year3_rent, places=2,
                                 msg=f"Year 3 rent should be 103.5% of Year 2 in {period}")

    def test_escalation_starts_before_lease(self):
        """
        Test escalation start date before lease start.
        
        Scenario: Escalation starts before lease begins
        Expected: Escalation applied from lease start
        """
        escalation = OfficeRentEscalation(
            type="fixed",
            rate=2.0,  # $2/SF increase
            reference=PropertyAttributeKey.NET_RENTABLE_AREA,
            is_relative=False,
            start_date=date(2023, 1, 1),  # Before lease start
            recurring=False,
            frequency_months=None
        )

        lease_spec = self.base_lease_spec.model_copy(
            update={"rent_escalations": escalation}
        )

        lease = OfficeLease.from_spec(
            lease_spec, self.analysis_start_date, self.timeline, self.settings
        )

        context = AnalysisContext(
            timeline=self.timeline,
            settings=self.settings,
            property_data=None,
        )

        cash_flows = lease.compute_cf(context)

        # Expected: Escalation applied from lease start
        expected_rent = (32.0 * 10000) / 12  # $26,667/month (30 + 2)

        # All periods should have escalated rent
        for period in self.timeline.period_index:
            self.assertAlmostEqual(cash_flows["base_rent"][period], expected_rent, places=2,
                                 msg=f"Rent should be escalated from lease start in {period}")

    def test_escalation_starts_after_lease_end(self):
        """
        Test escalation start date after lease ends.
        
        Scenario: Escalation starts after lease term expires
        Expected: No escalation applied, base rent throughout
        """
        # Shorter lease for this test
        short_timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
        
        escalation = OfficeRentEscalation(
            type="fixed",
            rate=5.0,  # $5/SF increase
            reference=PropertyAttributeKey.NET_RENTABLE_AREA,
            is_relative=False,
            start_date=date(2026, 1, 1),  # After lease ends
            recurring=False,
            frequency_months=None
        )

        lease_spec = self.base_lease_spec.model_copy(
            update={"rent_escalations": escalation, "term_months": 12}
        )

        lease = OfficeLease.from_spec(
            lease_spec, self.analysis_start_date, short_timeline, self.settings
        )

        context = AnalysisContext(
            timeline=short_timeline,
            settings=self.settings,
            property_data=None,
        )

        cash_flows = lease.compute_cf(context)

        # Expected: No escalation, constant base rent
        expected_rent = (30.0 * 10000) / 12  # $25,000/month

        # All periods should have base rent (no escalation)
        for period in short_timeline.period_index:
            self.assertAlmostEqual(cash_flows["base_rent"][period], expected_rent, places=2,
                                 msg=f"Rent should remain base (no escalation) in {period}")


if __name__ == '__main__':
    unittest.main()
