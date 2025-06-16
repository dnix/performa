import unittest
from datetime import date
from unittest.mock import MagicMock, PropertyMock

import pandas as pd

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
        self.rollover_profile = OfficeRolloverProfile(
            name="Test Profile",
            term_months=60,
            renewal_probability=0.75,
            downtime_months=3,
            market_terms=OfficeRolloverLeaseTerms(market_rent=50.0, term_months=60),
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
        self.assertEqual(lease.timeline.start_date, pd.Period('2022-01', freq='M'))
        self.assertEqual(lease.timeline.duration_months, 36)
        self.assertEqual(lease.timeline.end_date, pd.Period('2024-12', freq='M'))

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
        
        lease_timeline = Timeline(start_date=spec.start_date, duration_months=spec.term_months)
        lease = OfficeLease.from_spec(spec, self.analysis_start_date, lease_timeline, self.settings, self.lookup_fn)

        cash_flows = lease.compute_cf()

        # Annual rent is 60k, so monthly is 5k
        self.assertTrue(all(cash_flows["base_rent"] == 5000.0))
        self.assertTrue(all(cash_flows["revenue"] == 5000.0))
        self.assertTrue(all(cash_flows["net"] == 5000.0))
        self.assertEqual(len(cash_flows["base_rent"]), 12)

    def test_project_future_cash_flows_market_rollover(self):
        """
        Test the full rollover logic for a lease expiring and going to market.
        """
        # Create a rollover profile without TI/LC for this test
        rollover_profile_no_costs = OfficeRolloverProfile(
            name="Test Profile No Costs",
            term_months=60,
            renewal_probability=0.75,
            downtime_months=3,
            market_terms=OfficeRolloverLeaseTerms(market_rent=50.0, term_months=60),
            renewal_terms=OfficeRolloverLeaseTerms(market_rent=45.0, term_months=60),
        )
        self.lookup_fn.side_effect = lambda ref: {
            "rollover_1": rollover_profile_no_costs
        }.get(ref)

        spec = OfficeLeaseSpec(
            tenant_name="Expiring Tenant",
            suite="200",
            floor="2",
            area=5000.0,
            use_type=ProgramUseEnum.OFFICE,
            lease_type="net",
            start_date=date(2022, 1, 1),
            term_months=24, # Expires Dec 2023
            base_rent_value=40.0,
            base_rent_unit_of_measure=UnitOfMeasureEnum.PER_UNIT,
            base_rent_frequency=FrequencyEnum.ANNUAL,
            upon_expiration=UponExpirationEnum.MARKET,
            rollover_profile_ref="rollover_1",
        )
        
        lease_timeline = Timeline(start_date=spec.start_date, duration_months=spec.term_months)
        lease = OfficeLease.from_spec(spec, self.analysis_start_date, lease_timeline, self.settings, self.lookup_fn)

        # Use a shorter analysis timeline to prevent recursive rollover
        short_analysis_timeline = Timeline(start_date=date(2023, 1, 1), duration_months=36) # Ends Dec 2025
        future_cfs = lease.project_future_cash_flows(analysis_timeline=short_analysis_timeline, global_settings=self.settings, lookup_fn=self.lookup_fn)

        # With a short timeline, we expect only one rollover event, which creates a vacancy loss and a new lease.
        # Since the rollover terms have no TI/LC, those are not created.
        self.assertEqual(len(future_cfs), 2) 
        
        vacancy_loss = future_cfs[0]
        next_lease = future_cfs[1]
        
        # Check Vacancy Loss
        self.assertTrue("Vacancy Loss" in vacancy_loss.name)
        self.assertEqual(vacancy_loss.timeline.duration_months, rollover_profile_no_costs.downtime_months)
        # Downtime starts Jan 2024
        self.assertEqual(vacancy_loss.timeline.start_date, pd.Period("2024-01", freq="M"))
        # Rent is blended, downtime is market
        market_rent_at_expiry = rollover_profile_no_costs._calculate_rent(rollover_profile_no_costs.market_terms, date(2023, 12, 31), self.settings)
        expected_loss = market_rent_at_expiry * spec.area
        self.assertAlmostEqual(vacancy_loss.value, expected_loss, places=2)

        # Check Next Lease
        self.assertTrue("Market Lease" in next_lease.name)
        self.assertEqual(next_lease.status, LeaseStatusEnum.SPECULATIVE)
        # Next lease starts after 3 months downtime, so April 2024
        self.assertEqual(next_lease.timeline.start_date, pd.Period("2024-04", freq="M"))
        self.assertEqual(next_lease.timeline.duration_months, rollover_profile_no_costs.market_terms.term_months)
        
        # Explicitly check that no TI/LC were created for this lease
        self.assertIsNone(next_lease.ti_allowance)
        self.assertIsNone(next_lease.leasing_commission)

    def test_project_future_cash_flows_with_ti_lc(self):
        """
        Test that TI and LC are created correctly during rollover.
        """
        ti = OfficeTenantImprovement(name="Test TI", timeline=self.timeline, value=10.0, unit_of_measure=UnitOfMeasureEnum.PER_UNIT)
        lc = OfficeLeasingCommission(name="Test LC", timeline=self.timeline, value=100000, unit_of_measure=UnitOfMeasureEnum.CURRENCY, tiers=[CommissionTier(year_start=1, rate=0.03)])
        
        rollover_profile_with_costs = OfficeRolloverProfile(
            name="Test Profile With Costs",
            term_months=60,
            renewal_probability=0.75,
            downtime_months=3,
            market_terms=OfficeRolloverLeaseTerms(market_rent=50.0, term_months=60, ti_allowance=ti, leasing_commission=lc),
            renewal_terms=OfficeRolloverLeaseTerms(market_rent=45.0, term_months=60),
        )
        self.lookup_fn.side_effect = lambda ref: {
            "rollover_1": rollover_profile_with_costs
        }.get(ref)

        spec = OfficeLeaseSpec(
            tenant_name="Expiring Tenant",
            suite="200",
            floor="2",
            area=5000.0,
            use_type=ProgramUseEnum.OFFICE,
            lease_type="net",
            start_date=date(2022, 1, 1),
            term_months=24, # Expires Dec 2023
            base_rent_value=40.0,
            base_rent_unit_of_measure=UnitOfMeasureEnum.PER_UNIT,
            base_rent_frequency=FrequencyEnum.ANNUAL,
            upon_expiration=UponExpirationEnum.MARKET,
            rollover_profile_ref="rollover_1",
        )
        
        lease_timeline = Timeline(start_date=spec.start_date, duration_months=spec.term_months)
        lease = OfficeLease.from_spec(spec, self.analysis_start_date, lease_timeline, self.settings, self.lookup_fn)
    
        # Use a shorter analysis timeline to prevent recursive rollover
        short_analysis_timeline = Timeline(start_date=date(2023, 1, 1), duration_months=36) # Ends Dec 2025
        future_cfs = lease.project_future_cash_flows(analysis_timeline=short_analysis_timeline, global_settings=self.settings, lookup_fn=self.lookup_fn)
        
        self.assertEqual(len(future_cfs), 4) # Vacancy Loss, Next Lease, TI, LC
        
        # Find the items by type to make the test more robust
        vacancy_loss = next((cf for cf in future_cfs if isinstance(cf, OfficeOpExItem)), None)
        next_lease = next((cf for cf in future_cfs if isinstance(cf, OfficeLease)), None)
        ti_cf = next((cf for cf in future_cfs if isinstance(cf, OfficeTenantImprovement)), None)
        lc_cf = next((cf for cf in future_cfs if isinstance(cf, OfficeLeasingCommission)), None)

        self.assertIsNotNone(vacancy_loss)
        self.assertIsNotNone(next_lease)
        self.assertIsNotNone(ti_cf)
        self.assertIsNotNone(lc_cf)
        
        # Vacancy should start in Jan 2024, right after the lease expires
        self.assertEqual(vacancy_loss.timeline.start_date, pd.Period("2024-01", freq="M"))
        # The new lease and its costs should start in April 2024 after 3 months downtime
        self.assertEqual(next_lease.timeline.start_date, pd.Period("2024-04", freq="M"))
        self.assertEqual(ti_cf.timeline.start_date, pd.Period("2024-04", freq="M"))
        self.assertEqual(lc_cf.timeline.start_date, pd.Period("2024-04", freq="M"))


if __name__ == '__main__':
    unittest.main()
