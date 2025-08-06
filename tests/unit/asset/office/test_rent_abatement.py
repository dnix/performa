# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

import unittest
from datetime import date

from performa.analysis import AnalysisContext
from performa.asset.office.expense import OfficeOpExItem
from performa.asset.office.lease import OfficeLease
from performa.asset.office.lease_spec import OfficeLeaseSpec
from performa.asset.office.recovery import ExpensePool, OfficeRecoveryMethod, Recovery
from performa.asset.office.rent_abatement import OfficeRentAbatement
from performa.core.primitives import (
    FrequencyEnum,
    GlobalSettings,
    LeaseTypeEnum,
    ProgramUseEnum,
    PropertyAttributeKey,
    Timeline,
    UponExpirationEnum,
)


class TestOfficeRentAbatement(unittest.TestCase):
    """
    Comprehensive unit tests for rent abatement functionality.

    Tests cover:
    - Basic abatement scenarios (full vs partial)
    - Abatement timing (different start months, durations)
    - Recovery inclusion/exclusion logic
    - Integration with lease cash flow calculations
    - Edge cases and validation
    """

    def setUp(self):
        """Set up common test fixtures."""
        self.analysis_start_date = date(2024, 1, 1)
        self.timeline = Timeline(start_date=date(2024, 1, 1), duration_months=24)
        self.settings = GlobalSettings(analysis_start_date=self.analysis_start_date)

        # Base lease specification without abatement
        self.base_lease_spec = OfficeLeaseSpec(
            tenant_name="Test Tenant",
            suite="100",
            floor="1",
            area=10000.0,
            use_type=ProgramUseEnum.OFFICE,
            lease_type=LeaseTypeEnum.GROSS,
            start_date=date(2024, 1, 1),
            term_months=24,
            base_rent_value=30.0,  # $30/SF/year
            base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
            base_rent_frequency=FrequencyEnum.ANNUAL,
            upon_expiration=UponExpirationEnum.MARKET,
        )

        # Operating expense for recovery tests
        self.operating_expense = OfficeOpExItem(
            name="CAM",
            timeline=self.timeline,
            value=5.0,  # $5/SF/year
            reference=PropertyAttributeKey.NET_RENTABLE_AREA,
            frequency=FrequencyEnum.ANNUAL,
        )

        # Recovery method for testing abatement with recoveries
        self.recovery_method = OfficeRecoveryMethod(
            name="Net Recovery",
            gross_up=False,
            recoveries=[
                Recovery(
                    expenses=ExpensePool(
                        name="CAM Pool", expenses=[self.operating_expense]
                    ),
                    structure="net",
                )
            ],
        )

    def test_full_rent_abatement_basic(self):
        """
        Test basic full rent abatement (100% reduction).

        Scenario: 3 months of full rent abatement starting month 1
        Expected: First 3 months have $0 rent, remaining months normal rent
        """
        abatement = OfficeRentAbatement(
            months=3,
            includes_recoveries=False,
            start_month=1,
            abated_ratio=1.0,  # 100% abatement
        )

        lease_spec = self.base_lease_spec.model_copy(
            update={"rent_abatement": abatement}
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

        # Calculate expected values
        monthly_rent = (30.0 * 10000) / 12  # $25,000/month

        # First 3 months should be $0 (full abatement)
        abated_periods = self.timeline.period_index[:3]  # Jan, Feb, Mar 2024
        for period in abated_periods:
            self.assertEqual(
                cash_flows["base_rent"][period],
                0.0,
                f"Rent should be $0 during abatement period {period}",
            )

        # Remaining months should have normal rent
        normal_periods = self.timeline.period_index[3:]  # Apr 2024 onwards
        for period in normal_periods:
            self.assertAlmostEqual(
                cash_flows["base_rent"][period],
                monthly_rent,
                places=2,
                msg=f"Rent should be normal in period {period}",
            )

        # Check abatement amount tracking
        total_abatement = cash_flows["abatement"].sum()
        expected_abatement = 3 * monthly_rent  # 3 months of full rent
        self.assertAlmostEqual(total_abatement, expected_abatement, places=2)

    def test_partial_rent_abatement(self):
        """
        Test partial rent abatement (50% reduction).

        Scenario: 6 months of 50% rent abatement starting month 1
        Expected: First 6 months have 50% rent, remaining months normal rent
        """
        abatement = OfficeRentAbatement(
            months=6,
            includes_recoveries=False,
            start_month=1,
            abated_ratio=0.5,  # 50% abatement
        )

        lease_spec = self.base_lease_spec.model_copy(
            update={"rent_abatement": abatement}
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

        # Calculate expected values
        monthly_rent = (30.0 * 10000) / 12  # $25,000/month
        abated_rent = monthly_rent * 0.5  # $12,500/month during abatement

        # First 6 months should have 50% rent
        abated_periods = self.timeline.period_index[:6]
        for period in abated_periods:
            self.assertAlmostEqual(
                cash_flows["base_rent"][period],
                abated_rent,
                places=2,
                msg=f"Rent should be 50% in abated period {period}",
            )

        # Remaining months should have normal rent
        normal_periods = self.timeline.period_index[6:]
        for period in normal_periods:
            self.assertAlmostEqual(
                cash_flows["base_rent"][period],
                monthly_rent,
                places=2,
                msg=f"Rent should be normal in period {period}",
            )

        # Check abatement amount tracking
        total_abatement = cash_flows["abatement"].sum()
        expected_abatement = 6 * (monthly_rent * 0.5)  # 6 months of 50% abatement
        self.assertAlmostEqual(total_abatement, expected_abatement, places=2)

    def test_delayed_abatement_start(self):
        """
        Test abatement starting in a later month.

        Scenario: 4 months of full rent abatement starting month 7
        Expected: First 6 months normal, months 7-10 abated, remaining normal
        """
        abatement = OfficeRentAbatement(
            months=4,
            includes_recoveries=False,
            start_month=7,  # Start in July (month 7)
            abated_ratio=1.0,  # 100% abatement
        )

        lease_spec = self.base_lease_spec.model_copy(
            update={"rent_abatement": abatement}
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

        monthly_rent = (30.0 * 10000) / 12  # $25,000/month

        # First 6 months should have normal rent
        normal_periods_1 = self.timeline.period_index[:6]  # Jan-Jun 2024
        for period in normal_periods_1:
            self.assertAlmostEqual(
                cash_flows["base_rent"][period],
                monthly_rent,
                places=2,
                msg=f"Rent should be normal before abatement in {period}",
            )

        # Months 7-10 should be abated (Jul-Oct 2024)
        abated_periods = self.timeline.period_index[6:10]  # Jul-Oct 2024
        for period in abated_periods:
            self.assertEqual(
                cash_flows["base_rent"][period],
                0.0,
                f"Rent should be $0 during abatement period {period}",
            )

        # Remaining months should have normal rent
        normal_periods_2 = self.timeline.period_index[10:]  # Nov 2024 onwards
        for period in normal_periods_2:
            self.assertAlmostEqual(
                cash_flows["base_rent"][period],
                monthly_rent,
                places=2,
                msg=f"Rent should be normal after abatement in {period}",
            )

    def test_abatement_without_recoveries(self):
        """
        Test abatement that excludes recoveries.

        Scenario: Net lease with recoveries, abatement excludes recoveries
        Expected: Base rent abated, recoveries continue normally
        """
        abatement = OfficeRentAbatement(
            months=3,
            includes_recoveries=False,  # Exclude recoveries from abatement
            start_month=1,
            abated_ratio=1.0,
        )

        lease_spec = self.base_lease_spec.model_copy(
            update={
                "lease_type": LeaseTypeEnum.NET,
                "rent_abatement": abatement,
                "recovery_method": self.recovery_method,
            }
        )

        lease = OfficeLease.from_spec(
            lease_spec, self.analysis_start_date, self.timeline, self.settings
        )

        # Set up proper context with property data and recovery states
        from performa.asset.office.property import OfficeProperty
        from performa.core.base import RecoveryCalculationState

        property_data = OfficeProperty.model_construct(net_rentable_area=10000.0)
        context = AnalysisContext(
            timeline=self.timeline,
            settings=self.settings,
            property_data=property_data,
            resolved_lookups={},
            recovery_states={},
        )

        # Pre-populate expense cash flows and recovery states
        context.resolved_lookups[self.operating_expense.uid] = (
            self.operating_expense.compute_cf(context=context)
        )
        for recovery in self.recovery_method.recoveries:
            context.recovery_states[recovery.uid] = RecoveryCalculationState(
                recovery_uid=recovery.uid
            )

        cash_flows = lease.compute_cf(context)

        # Expected values
        monthly_rent = (30.0 * 10000) / 12  # $25,000/month
        monthly_recovery = (5.0 * 10000) / 12  # $4,167/month

        # During abatement: base rent = $0, recoveries = normal
        abated_periods = self.timeline.period_index[:3]
        for period in abated_periods:
            self.assertEqual(
                cash_flows["base_rent"][period],
                0.0,
                f"Base rent should be $0 during abatement in {period}",
            )
            self.assertAlmostEqual(
                cash_flows["recoveries"][period],
                monthly_recovery,
                places=2,
                msg=f"Recoveries should continue normally in {period}",
            )

        # After abatement: both base rent and recoveries normal
        normal_periods = self.timeline.period_index[3:]
        for period in normal_periods:
            self.assertAlmostEqual(
                cash_flows["base_rent"][period],
                monthly_rent,
                places=2,
                msg=f"Base rent should be normal after abatement in {period}",
            )
            self.assertAlmostEqual(
                cash_flows["recoveries"][period],
                monthly_recovery,
                places=2,
                msg=f"Recoveries should be normal after abatement in {period}",
            )

    def test_abatement_with_recoveries(self):
        """
        Test abatement that includes recoveries.

        Scenario: Net lease with recoveries, abatement includes recoveries
        Expected: Both base rent and recoveries abated
        """
        abatement = OfficeRentAbatement(
            months=3,
            includes_recoveries=True,  # Include recoveries in abatement
            start_month=1,
            abated_ratio=1.0,
        )

        lease_spec = self.base_lease_spec.model_copy(
            update={
                "lease_type": LeaseTypeEnum.NET,
                "rent_abatement": abatement,
                "recovery_method": self.recovery_method,
            }
        )

        lease = OfficeLease.from_spec(
            lease_spec, self.analysis_start_date, self.timeline, self.settings
        )

        # Set up proper context with property data and recovery states
        from performa.asset.office.property import OfficeProperty
        from performa.core.base import RecoveryCalculationState

        property_data = OfficeProperty.model_construct(net_rentable_area=10000.0)
        context = AnalysisContext(
            timeline=self.timeline,
            settings=self.settings,
            property_data=property_data,
            resolved_lookups={},
            recovery_states={},
        )

        # Pre-populate expense cash flows and recovery states
        context.resolved_lookups[self.operating_expense.uid] = (
            self.operating_expense.compute_cf(context=context)
        )
        for recovery in self.recovery_method.recoveries:
            context.recovery_states[recovery.uid] = RecoveryCalculationState(
                recovery_uid=recovery.uid
            )

        cash_flows = lease.compute_cf(context)

        # Expected values
        monthly_rent = (30.0 * 10000) / 12  # $25,000/month
        monthly_recovery = (5.0 * 10000) / 12  # $4,167/month

        # During abatement: both base rent and recoveries = $0
        abated_periods = self.timeline.period_index[:3]
        for period in abated_periods:
            self.assertEqual(
                cash_flows["base_rent"][period],
                0.0,
                f"Base rent should be $0 during abatement in {period}",
            )
            self.assertEqual(
                cash_flows["recoveries"][period],
                0.0,
                f"Recoveries should be $0 during abatement in {period}",
            )

        # After abatement: both base rent and recoveries normal
        normal_periods = self.timeline.period_index[3:]
        for period in normal_periods:
            self.assertAlmostEqual(
                cash_flows["base_rent"][period],
                monthly_rent,
                places=2,
                msg=f"Base rent should be normal after abatement in {period}",
            )
            self.assertAlmostEqual(
                cash_flows["recoveries"][period],
                monthly_recovery,
                places=2,
                msg=f"Recoveries should be normal after abatement in {period}",
            )

    def test_abatement_partial_with_recoveries(self):
        """
        Test partial abatement that includes recoveries.

        Scenario: Net lease, 50% abatement including recoveries
        Expected: Both base rent and recoveries reduced by 50%
        """
        abatement = OfficeRentAbatement(
            months=4,
            includes_recoveries=True,
            start_month=1,
            abated_ratio=0.5,  # 50% abatement
        )

        lease_spec = self.base_lease_spec.model_copy(
            update={
                "lease_type": LeaseTypeEnum.NET,
                "rent_abatement": abatement,
                "recovery_method": self.recovery_method,
            }
        )

        lease = OfficeLease.from_spec(
            lease_spec, self.analysis_start_date, self.timeline, self.settings
        )

        # Set up proper context with property data and recovery states
        from performa.asset.office.property import OfficeProperty
        from performa.core.base import RecoveryCalculationState

        property_data = OfficeProperty.model_construct(net_rentable_area=10000.0)
        context = AnalysisContext(
            timeline=self.timeline,
            settings=self.settings,
            property_data=property_data,
            resolved_lookups={},
            recovery_states={},
        )

        # Pre-populate expense cash flows and recovery states
        context.resolved_lookups[self.operating_expense.uid] = (
            self.operating_expense.compute_cf(context=context)
        )
        for recovery in self.recovery_method.recoveries:
            context.recovery_states[recovery.uid] = RecoveryCalculationState(
                recovery_uid=recovery.uid
            )

        cash_flows = lease.compute_cf(context)

        # Expected values
        monthly_rent = (30.0 * 10000) / 12  # $25,000/month
        monthly_recovery = (5.0 * 10000) / 12  # $4,167/month
        abated_rent = monthly_rent * 0.5  # $12,500/month
        abated_recovery = monthly_recovery * 0.5  # $2,084/month

        # During abatement: both reduced by 50%
        abated_periods = self.timeline.period_index[:4]
        for period in abated_periods:
            self.assertAlmostEqual(
                cash_flows["base_rent"][period],
                abated_rent,
                places=2,
                msg=f"Base rent should be 50% during abatement in {period}",
            )
            self.assertAlmostEqual(
                cash_flows["recoveries"][period],
                abated_recovery,
                places=2,
                msg=f"Recoveries should be 50% during abatement in {period}",
            )

        # After abatement: both normal
        normal_periods = self.timeline.period_index[4:]
        for period in normal_periods:
            self.assertAlmostEqual(
                cash_flows["base_rent"][period],
                monthly_rent,
                places=2,
                msg=f"Base rent should be normal after abatement in {period}",
            )
            self.assertAlmostEqual(
                cash_flows["recoveries"][period],
                monthly_recovery,
                places=2,
                msg=f"Recoveries should be normal after abatement in {period}",
            )

    def test_abatement_extends_beyond_lease_term(self):
        """
        Test abatement that would extend beyond the lease term.

        Scenario: 6-month lease with 12-month abatement starting month 1
        Expected: Abatement only applies for the actual lease duration
        """
        # Create shorter lease
        short_timeline = Timeline(start_date=date(2024, 1, 1), duration_months=6)

        abatement = OfficeRentAbatement(
            months=12,  # Longer than lease term
            includes_recoveries=False,
            start_month=1,
            abated_ratio=1.0,
        )

        lease_spec = self.base_lease_spec.model_copy(
            update={"term_months": 6, "rent_abatement": abatement}
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

        # All 6 months should be abated (no rent)
        for period in short_timeline.period_index:
            self.assertEqual(
                cash_flows["base_rent"][period],
                0.0,
                f"All rent should be abated for entire lease term in {period}",
            )

        # Should have 6 months of abatement tracked
        monthly_rent = (30.0 * 10000) / 12
        expected_total_abatement = 6 * monthly_rent
        self.assertAlmostEqual(
            cash_flows["abatement"].sum(), expected_total_abatement, places=2
        )

    def test_abatement_starts_beyond_lease_term(self):
        """
        Test abatement that starts after the lease expires.

        Scenario: 6-month lease with abatement starting month 12
        Expected: No abatement applied, normal rent for entire term
        """
        short_timeline = Timeline(start_date=date(2024, 1, 1), duration_months=6)

        abatement = OfficeRentAbatement(
            months=3,
            includes_recoveries=False,
            start_month=12,  # Starts after lease expires
            abated_ratio=1.0,
        )

        lease_spec = self.base_lease_spec.model_copy(
            update={"term_months": 6, "rent_abatement": abatement}
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

        monthly_rent = (30.0 * 10000) / 12

        # All months should have normal rent (no abatement)
        for period in short_timeline.period_index:
            self.assertAlmostEqual(
                cash_flows["base_rent"][period],
                monthly_rent,
                places=2,
                msg=f"Rent should be normal (no abatement applied) in {period}",
            )

        # No abatement should be tracked
        self.assertEqual(cash_flows["abatement"].sum(), 0.0)

    def test_zero_abatement_ratio(self):
        """
        Test abatement with 0% ratio (no actual abatement).

        Scenario: Abatement defined but with 0% ratio
        Expected: Normal rent throughout, no abatement applied
        """
        abatement = OfficeRentAbatement(
            months=6,
            includes_recoveries=False,
            start_month=1,
            abated_ratio=0.0,  # No actual abatement
        )

        lease_spec = self.base_lease_spec.model_copy(
            update={"rent_abatement": abatement}
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

        monthly_rent = (30.0 * 10000) / 12

        # All months should have normal rent
        for period in self.timeline.period_index:
            self.assertAlmostEqual(
                cash_flows["base_rent"][period],
                monthly_rent,
                places=2,
                msg=f"Rent should be normal with 0% abatement in {period}",
            )

        # No abatement should be tracked
        self.assertEqual(cash_flows["abatement"].sum(), 0.0)

    def test_revenue_calculation_with_abatement(self):
        """
        Test that revenue calculation correctly accounts for abatement.

        Scenario: Net lease with abatement including recoveries
        Expected: Revenue = (base_rent + recoveries) with both components abated
        """
        abatement = OfficeRentAbatement(
            months=2,
            includes_recoveries=True,
            start_month=1,
            abated_ratio=0.75,  # 75% abatement
        )

        lease_spec = self.base_lease_spec.model_copy(
            update={
                "lease_type": LeaseTypeEnum.NET,
                "rent_abatement": abatement,
                "recovery_method": self.recovery_method,
            }
        )

        lease = OfficeLease.from_spec(
            lease_spec, self.analysis_start_date, self.timeline, self.settings
        )

        # Set up proper context with property data and recovery states
        from performa.asset.office.property import OfficeProperty
        from performa.core.base import RecoveryCalculationState

        property_data = OfficeProperty.model_construct(net_rentable_area=10000.0)
        context = AnalysisContext(
            timeline=self.timeline,
            settings=self.settings,
            property_data=property_data,
            resolved_lookups={},
            recovery_states={},
        )

        # Pre-populate expense cash flows and recovery states
        context.resolved_lookups[self.operating_expense.uid] = (
            self.operating_expense.compute_cf(context=context)
        )
        for recovery in self.recovery_method.recoveries:
            context.recovery_states[recovery.uid] = RecoveryCalculationState(
                recovery_uid=recovery.uid
            )

        cash_flows = lease.compute_cf(context)

        # Expected values
        monthly_rent = (30.0 * 10000) / 12
        monthly_recovery = (5.0 * 10000) / 12
        normal_revenue = monthly_rent + monthly_recovery
        abated_revenue = normal_revenue * 0.25  # 25% of normal (75% abated)

        # During abatement
        abated_periods = self.timeline.period_index[:2]
        for period in abated_periods:
            self.assertAlmostEqual(
                cash_flows["revenue"][period],
                abated_revenue,
                places=2,
                msg=f"Revenue should be 25% of normal during abatement in {period}",
            )

        # After abatement
        normal_periods = self.timeline.period_index[2:]
        for period in normal_periods:
            self.assertAlmostEqual(
                cash_flows["revenue"][period],
                normal_revenue,
                places=2,
                msg=f"Revenue should be normal after abatement in {period}",
            )


if __name__ == "__main__":
    unittest.main()
