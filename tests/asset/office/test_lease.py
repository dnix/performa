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

        context = AnalysisContext(
            timeline=lease_timeline,
            settings=self.settings,
            property_data=None, # Not needed for this simple test
        )
        cash_flows = lease.compute_cf(context=context)

        # Base rent is $60k/yr -> $5k/mo
        expected_base_rent = pd.Series(5000.0, index=lease_timeline.period_index)
        self.assertTrue(all(cash_flows["base_rent"] == expected_base_rent))
        self.assertTrue(all(cash_flows["revenue"] == expected_base_rent))
        self.assertTrue(all(cash_flows["net"] == expected_base_rent))
        self.assertEqual(len(cash_flows["base_rent"]), 12)

    @unittest.skip("Rollover logic not yet fully implemented")
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
        
        context = AnalysisContext(
            timeline=short_analysis_timeline,
            settings=self.settings,
            property_data=None, # Not needed for this test
            resolved_lookups={}, # Mock resolved lookups
        )
        future_df = lease.project_future_cash_flows(context=context)

        # Basic assertion: check that the dataframe is not empty
        self.assertFalse(future_df.empty)
        # We can't easily check the name of the new lease from the aggregated DataFrame
        # but we can check if vacancy loss was calculated.
        self.assertGreater(future_df['vacancy_loss'].sum(), 0)

    @unittest.skip("Rollover logic not yet fully implemented")
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

        short_analysis_timeline = Timeline(start_date=date(2023, 1, 1), duration_months=36)
        context = AnalysisContext(
            timeline=short_analysis_timeline,
            settings=self.settings,
            property_data=None,
            resolved_lookups={},
        )
        future_df = lease.project_future_cash_flows(context=context)
        
        # Check that TI and LC were created and have non-zero values
        self.assertGreater(future_df['ti_allowance'].sum(), 0)
        self.assertGreater(future_df['leasing_commission'].sum(), 0)


if __name__ == '__main__':
    unittest.main()
