import unittest
from datetime import date
from unittest.mock import MagicMock, PropertyMock

import pandas as pd

from performa.analysis import AnalysisContext
from performa.asset.office.expense import OfficeOpExItem
from performa.asset.office.lc import OfficeLeasingCommission
from performa.asset.office.lease import OfficeLease
from performa.asset.office.lease_spec import OfficeLeaseSpec
from performa.asset.office.rollover import (
    OfficeRolloverLeaseTerms,
    OfficeRolloverProfile,
)
from performa.asset.office.ti import OfficeTenantImprovement
from performa.common.base import CommissionTier
from performa.common.primitives import (
    FrequencyEnum,
    GlobalSettings,
    LeaseStatusEnum,
    ProgramUseEnum,
    Timeline,
    UnitOfMeasureEnum,
    UponExpirationEnum,
)


class TestOfficeLease(unittest.TestCase):
    def setUp(self):
        self.analysis_start_date = date(2023, 1, 1)
        self.timeline = Timeline(start_date=date(2023, 1, 1), duration_months=120)
        self.settings = GlobalSettings(analysis_start_date=self.analysis_start_date)
        # Mock lookup function
        self.ti = OfficeTenantImprovement(
            name="Market TI",
            timeline=self.timeline,
            value=10.0,
            unit_of_measure=UnitOfMeasureEnum.PER_UNIT,
        )
        self.lc = OfficeLeasingCommission(
            name="Market LC",
            timeline=self.timeline,
            value=100000,
            unit_of_measure=UnitOfMeasureEnum.CURRENCY,
            tiers=[CommissionTier(year_start=1, rate=0.03)],
        )
        self.rollover_profile = OfficeRolloverProfile(
            name="Test Profile",
            term_months=60,
            renewal_probability=0.75,
            downtime_months=3,
            market_terms=OfficeRolloverLeaseTerms(
                market_rent=50.0,
                term_months=60,
                ti_allowance=self.ti,
                leasing_commission=self.lc,
            ),
            renewal_terms=OfficeRolloverLeaseTerms(market_rent=45.0, term_months=60),
        )
        self.lookup_fn = MagicMock()
        self.lookup_fn.side_effect = lambda ref: {
            "rollover_1": self.rollover_profile
        }.get(ref)

    def test_from_spec_creation(self):
        """
        Test that an OfficeLease is created correctly from an OfficeLeaseSpec.
        """
        spec = OfficeLeaseSpec(
            tenant_name="Test Tenant",
            suite="101",
            floor="1",
            area=1000.0,
            use_type=ProgramUseEnum.OFFICE,
            lease_type="net",
            start_date=date(2022, 1, 1),
            term_months=36,
            base_rent_value=42.5,
            base_rent_unit_of_measure=UnitOfMeasureEnum.PER_UNIT,
            base_rent_frequency=FrequencyEnum.ANNUAL,
            upon_expiration=UponExpirationEnum.MARKET,
            rollover_profile_ref="rollover_1",
        )
        lease = OfficeLease.from_spec(
            spec,
            analysis_start_date=self.analysis_start_date,
            timeline=self.timeline,
            settings=self.settings,
            lookup_fn=self.lookup_fn,
        )
        self.assertEqual(lease.name, "Test Tenant")
        self.assertEqual(lease.area, 1000.0)
        self.assertEqual(lease.status, LeaseStatusEnum.CONTRACT)
        self.assertEqual(lease.value, 42.5)
        self.assertIsNotNone(lease.rollover_profile)
        self.assertEqual(lease.rollover_profile.name, "Test Profile")
        self.assertEqual(lease.upon_expiration, UponExpirationEnum.MARKET)
        # Check if timeline was created correctly on the lease
        self.assertEqual(lease.timeline.start_date, pd.Period("2022-01", freq="M"))
        self.assertEqual(lease.timeline.duration_months, 36)
        self.assertEqual(lease.timeline.end_date, pd.Period("2024-12", freq="M"))

    def test_compute_cf_basic(self):
        """
        Test the compute_cf method with base rent, without complex features.
        """
        spec = OfficeLeaseSpec(
            tenant_name="Test Tenant",
            suite="101",
            floor="1",
            area=2000.0,
            use_type=ProgramUseEnum.OFFICE,
            lease_type="net",
            start_date=date(2023, 1, 1),
            term_months=12,
            base_rent_value=60000.0,
            base_rent_unit_of_measure=UnitOfMeasureEnum.CURRENCY,
            base_rent_frequency=FrequencyEnum.ANNUAL,
            upon_expiration=UponExpirationEnum.MARKET,
        )
        lease_timeline = Timeline(
            start_date=spec.start_date, duration_months=spec.term_months
        )
        lease = OfficeLease.from_spec(
            spec, self.analysis_start_date, lease_timeline, self.settings, self.lookup_fn
        )
        context = AnalysisContext(
            timeline=lease_timeline,
            settings=self.settings,
            property_data=None,  # Not needed for this simple test
        )
        cash_flows = lease.compute_cf(context=context)
        # Base rent is $60k/yr -> $5k/mo
        expected_base_rent = pd.Series(5000.0, index=lease_timeline.period_index)
        self.assertTrue(all(cash_flows["base_rent"] == expected_base_rent))
        self.assertTrue(all(cash_flows["revenue"] == expected_base_rent))
        self.assertTrue(all(cash_flows["net"] == expected_base_rent))
        self.assertEqual(len(cash_flows["base_rent"]), 12)

    def test_project_future_cash_flows_market_rollover(self):
        """
        Test the full rollover logic for a lease expiring and going to market.
        """
        # Create a rollover profile without TI/LC for this test
        rollover_profile_no_costs = self.rollover_profile.model_copy(
            deep=True,
            update={
                "market_terms": OfficeRolloverLeaseTerms(
                    market_rent=50.0, term_months=60
                )
            },
        )
        self.lookup_fn.side_effect = lambda ref: {"rollover_1": rollover_profile_no_costs}.get(ref)

        spec = OfficeLeaseSpec(
            tenant_name="Expiring Tenant",
            suite="200",
            floor="2",
            area=5000.0,
            use_type=ProgramUseEnum.OFFICE,
            lease_type="net",
            start_date=date(2022, 1, 1),
            term_months=24,  # Expires Dec 2023
            base_rent_value=40.0,
            base_rent_unit_of_measure=UnitOfMeasureEnum.PER_UNIT,
            base_rent_frequency=FrequencyEnum.ANNUAL,
            upon_expiration=UponExpirationEnum.MARKET,
            rollover_profile_ref="rollover_1",
        )
        lease = OfficeLease.from_spec(
            spec,
            analysis_start_date=self.analysis_start_date,
            timeline=self.timeline, # Pass the main timeline
            settings=self.settings,
            lookup_fn=self.lookup_fn,
        )
        
        # Use a shorter analysis timeline to prevent infinite recursion in test
        short_analysis_timeline = Timeline(start_date=date(2023, 1, 1), duration_months=36) # Ends Dec 2025
        context = AnalysisContext(
            timeline=short_analysis_timeline,
            settings=self.settings,
            property_data=None,  # Not needed for this test
            resolved_lookups={},  # Mock resolved lookups
        )
        future_df = lease.project_future_cash_flows(context=context)

        # Assertions
        self.assertFalse(future_df.empty)
        
        # 1. Original lease runs for 12 months in 2023
        original_lease_rent = future_df.loc[pd.Period('2023-01', 'M'):pd.Period('2023-12', 'M'), 'base_rent']
        self.assertTrue((original_lease_rent > 0).all())
        self.assertAlmostEqual(original_lease_rent.sum(), 5000 * 40, places=0)
        
        # 2. Downtime vacancy loss for 3 months in 2024
        downtime_periods = pd.period_range(start='2024-01', periods=3, freq='M')
        vacancy_loss = future_df.loc[downtime_periods, 'vacancy_loss']
        expected_monthly_loss = (50.0 * 5000) / 12  # Market rent * area / 12
        self.assertTrue((vacancy_loss > 0).all())
        self.assertAlmostEqual(vacancy_loss.iloc[0], expected_monthly_loss, places=2)
        
        # 3. New lease starts in April 2024
        new_lease_start = pd.Period('2024-04', 'M')
        self.assertGreater(future_df.loc[new_lease_start, 'base_rent'], 0)
        self.assertEqual(future_df.loc[pd.Period('2024-03', 'M'), 'base_rent'], 0) # Still in downtime

    def test_project_future_cash_flows_with_ti_lc(self):
        """
        Test that TI and LC are created correctly during rollover.
        """
        spec = OfficeLeaseSpec(
            tenant_name="Expiring Tenant",
            suite="200",
            floor="2",
            area=5000.0,
            use_type=ProgramUseEnum.OFFICE,
            lease_type="net",
            start_date=date(2022, 1, 1),
            term_months=24,  # Expires Dec 2023
            base_rent_value=40.0,
            base_rent_unit_of_measure=UnitOfMeasureEnum.PER_UNIT,
            base_rent_frequency=FrequencyEnum.ANNUAL,
            upon_expiration=UponExpirationEnum.MARKET,
            rollover_profile_ref="rollover_1",
        )
        lease = OfficeLease.from_spec(
            spec,
            self.analysis_start_date,
            self.timeline,
            self.settings,
            self.lookup_fn,
        )
        short_analysis_timeline = Timeline(start_date=date(2023, 1, 1), duration_months=36)
        context = AnalysisContext(
            timeline=short_analysis_timeline,
            settings=self.settings,
            property_data=None,
            resolved_lookups={},
        )
        future_df = lease.project_future_cash_flows(context=context)

        # Check that TI and LC were created and have non-zero values
        # They should appear in April 2024, when the new lease starts
        self.assertGreater(future_df['ti_allowance'].sum(), 0)
        self.assertGreater(future_df['leasing_commission'].sum(), 0)
        
        # Check they occur at the right time
        new_lease_start = pd.Period('2024-04', 'M')
        # TI is paid at commencement, which is defined as the 2nd month of the lease
        self.assertEqual(future_df.loc[new_lease_start, 'ti_allowance'], 0)
        self.assertGreater(future_df.loc[new_lease_start + 1, 'ti_allowance'], 0)

        # LC is paid at signing (month 1)
        self.assertGreater(future_df.loc[new_lease_start, 'leasing_commission'], 0)
        
        # Check that they are zero before the new lease starts
        self.assertEqual(future_df.loc[pd.Period('2024-03', 'M'), 'ti_allowance'], 0)
        self.assertEqual(future_df.loc[pd.Period('2024-03', 'M'), 'leasing_commission'], 0)

    def test_project_future_cash_flows_renew_scenario(self):
        """
        Test the rollover logic for a lease that is set to RENEW.
        """
        spec = OfficeLeaseSpec(
            tenant_name="Renewing Tenant",
            suite="300",
            floor="3",
            area=2500.0,
            use_type=ProgramUseEnum.OFFICE,
            lease_type="net",
            start_date=date(2022, 1, 1),
            term_months=24,  # Expires Dec 2023
            base_rent_value=48.0,
            base_rent_unit_of_measure=UnitOfMeasureEnum.PER_UNIT,
            base_rent_frequency=FrequencyEnum.ANNUAL,
            upon_expiration=UponExpirationEnum.RENEW, # Explicitly set to RENEW
            rollover_profile_ref="rollover_1",
        )
        lease = OfficeLease.from_spec(
            spec, self.analysis_start_date, self.timeline, self.settings, self.lookup_fn
        )
        short_analysis_timeline = Timeline(start_date=date(2023, 1, 1), duration_months=36)

        # Create a context with NO general vacancy to isolate the test
        from performa.asset.office.expense import OfficeExpenses
        from performa.asset.office.losses import (
            OfficeCollectionLoss,
            OfficeGeneralVacancyLoss,
            OfficeLosses,
        )
        from performa.asset.office.property import OfficeProperty
        from performa.asset.office.rent_roll import OfficeRentRoll
        
        mock_property = OfficeProperty(
            name="Mock Property",
            property_type="office",
            gross_area=lease.area,
            net_rentable_area=lease.area,
            rent_roll=OfficeRentRoll(leases=[spec], vacant_suites=[]),
            losses=OfficeLosses(
                general_vacancy=OfficeGeneralVacancyLoss(rate=0.0),
                collection_loss=OfficeCollectionLoss(rate=0.0)
            ),
            expenses=OfficeExpenses()
        )

        context = AnalysisContext(
            timeline=short_analysis_timeline, 
            settings=self.settings, 
            property_data=mock_property
        )
        
        future_df = lease.project_future_cash_flows(context=context)

        # 1. No downtime for renewal, so no vacancy loss. 
        # The column might exist due to aggregation, but its sum must be 0.
        self.assertEqual(future_df['vacancy_loss'].sum(), 0)

        # 2. New lease should start immediately in Jan 2024
        renewal_start_period = pd.Period('2024-01', 'M')
        self.assertGreater(future_df.loc[renewal_start_period, 'base_rent'], 0)

        # 3. Rent should be based on renewal terms (45.0) not market (50.0)
        # Renewal rent/sf/yr = 45.0 -> monthly rent = 45.0 * 2500 / 12
        expected_renewal_rent = (45.0 * 2500) / 12
        self.assertAlmostEqual(future_df.loc[renewal_start_period, 'base_rent'], expected_renewal_rent, places=2)

    def test_project_future_cash_flows_reabsorb_scenario(self):
        """
        Test the rollover logic for a lease that is set to REABSORB.
        """
        spec = OfficeLeaseSpec(
            tenant_name="Reabsorbing Tenant",
            suite="400",
            floor="4",
            area=1000.0,
            use_type=ProgramUseEnum.OFFICE,
            lease_type="net",
            start_date=date(2022, 1, 1),
            term_months=24,  # Expires Dec 2023
            base_rent_value=50.0,
            base_rent_unit_of_measure=UnitOfMeasureEnum.PER_UNIT,
            base_rent_frequency=FrequencyEnum.ANNUAL,
            upon_expiration=UponExpirationEnum.REABSORB, # Explicitly set to REABSORB
            rollover_profile_ref="rollover_1",
        )
        lease = OfficeLease.from_spec(
            spec, self.analysis_start_date, self.timeline, self.settings, self.lookup_fn
        )
        short_analysis_timeline = Timeline(start_date=date(2023, 1, 1), duration_months=36)
        context = AnalysisContext(timeline=short_analysis_timeline, settings=self.settings, property_data=None)

        future_df = lease.project_future_cash_flows(context=context)

        # 1. Lease should produce rent until it expires
        self.assertGreater(future_df.loc[pd.Period('2023-12', 'M'), 'base_rent'], 0)
        
        # 2. No cash flows should be projected after expiration
        post_expiration_df = future_df.loc[pd.Period('2024-01', 'M'):]
        self.assertTrue((post_expiration_df == 0).all().all())

if __name__ == '__main__':
    unittest.main()
