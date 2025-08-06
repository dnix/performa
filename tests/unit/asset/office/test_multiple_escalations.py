# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Test suite for multiple rent escalations functionality in office leases.

Tests the ability to define and apply multiple escalations with different
timing patterns, rate types, and compounding effects.
"""

from datetime import date

import pytest

from performa.analysis import AnalysisContext
from performa.asset.office.lease import OfficeLease
from performa.asset.office.lease_spec import OfficeLeaseSpec
from performa.asset.office.rent_escalation import (
    OfficeRentEscalation,
    create_escalations_from_absolute_dates,
    create_simple_annual_escalation,
    create_stepped_fixed_escalations,
    create_stepped_percentage_escalations,
)
from performa.core.primitives import (
    FrequencyEnum,
    GlobalSettings,
    LeaseTypeEnum,
    PropertyAttributeKey,
    Timeline,
    UponExpirationEnum,
)
from performa.core.primitives.growth_rates import (
    FixedGrowthRate,
    PercentageGrowthRate,
)


class TestMultipleEscalations:
    """Test multiple escalations functionality"""
    
    @pytest.fixture
    def base_spec(self) -> OfficeLeaseSpec:
        """Create a basic lease spec for testing"""
        return OfficeLeaseSpec(
            tenant_name="Test Tenant",
            start_date=date(2024, 1, 1),
            term_months=36,
            suite="100",
            floor="1",
            area=1000.0,
            lease_type=LeaseTypeEnum.NET,
            base_rent_value=30.0,
            base_rent_reference=PropertyAttributeKey.NET_RENTABLE_AREA,
            base_rent_frequency=FrequencyEnum.ANNUAL,
            upon_expiration=UponExpirationEnum.MARKET,
        )
    
    @pytest.fixture
    def timeline(self) -> Timeline:
        """Create timeline for testing"""
        return Timeline(start_date=date(2024, 1, 1), duration_months=36)
    
    @pytest.fixture  
    def context(self, timeline) -> AnalysisContext:
        """Create analysis context for testing"""
        return AnalysisContext(
            timeline=timeline,
            settings=GlobalSettings(analysis_start_date=date(2024, 1, 1)),
            property_data=None,
        )

    def test_multiple_escalations_chronological_order(self, base_spec, context):
        """Test that multiple escalations are applied in chronological order"""
        escalations = [
            OfficeRentEscalation(
                type="percentage",
                rate=0.05,  # 5% at month 13
                reference=PropertyAttributeKey.NET_RENTABLE_AREA,
                is_relative=True,
                start_month=13,
                recurring=False,
            ),
            OfficeRentEscalation(
                type="percentage", 
                rate=0.03,  # 3% at month 7 (earlier)
                reference=PropertyAttributeKey.NET_RENTABLE_AREA,
                is_relative=True,
                start_month=7,
                recurring=False,
            ),
        ]
        
        spec = base_spec.model_copy(update={"rent_escalations": escalations})
        lease = OfficeLease.from_spec(spec, date(2024, 1, 1), context.timeline)
        cash_flows = lease.compute_cf(context)
        
        base_rent = cash_flows["base_rent"]
        
        # Should be $2,500/month initially (30 * 1000 / 12)
        assert base_rent.iloc[0] == pytest.approx(2500.0, rel=1e-3)
        
        # After month 7: 3% increase
        assert base_rent.iloc[6] == pytest.approx(2575.0, rel=1e-3)  # 2500 * 1.03
        
        # After month 13: 5% increase on already increased rent (compound effect)
        assert base_rent.iloc[12] == pytest.approx(2703.75, rel=1e-3)  # 2575 * 1.05

    def test_mixed_timing_methods(self, base_spec, context):
        """Test escalations with both absolute dates and relative months"""
        escalations = [
            OfficeRentEscalation(
                type="fixed",
                rate=1.0,  # $1/SF increase
                reference=PropertyAttributeKey.NET_RENTABLE_AREA,
                is_relative=False,
                start_month=7,  # Relative timing
                recurring=False,
            ),
            OfficeRentEscalation(
                type="percentage",
                rate=0.04,  # 4% increase
                reference=PropertyAttributeKey.NET_RENTABLE_AREA,
                is_relative=True,
                start_date=date(2024, 12, 1),  # Absolute timing (month 12)
                recurring=False,
            ),
        ]
        
        spec = base_spec.model_copy(update={"rent_escalations": escalations})
        lease = OfficeLease.from_spec(spec, date(2024, 1, 1), context.timeline)
        cash_flows = lease.compute_cf(context)
        
        base_rent = cash_flows["base_rent"]
        
        # Month 1: $2,500 base
        assert base_rent.iloc[0] == pytest.approx(2500.0, rel=1e-3)
        
        # Month 7: Add $1/SF = $1000/year = $83.33/month
        assert base_rent.iloc[6] == pytest.approx(2583.33, rel=1e-2)
        
        # Month 12: 4% increase on current rent
        assert base_rent.iloc[11] == pytest.approx(2686.67, rel=1e-2)  # 2583.33 * 1.04

    def test_helper_stepped_percentage_escalations(self, base_spec, context):
        """Test helper function for stepped percentage escalations"""
        escalations = create_stepped_percentage_escalations(
            start_month=13,  # Start in year 2
            annual_rates=[0.03, 0.04, 0.05],  # 3%, 4%, 5%
        )
        
        spec = base_spec.model_copy(update={"rent_escalations": escalations})
        lease = OfficeLease.from_spec(spec, date(2024, 1, 1), context.timeline)
        cash_flows = lease.compute_cf(context)
        
        base_rent = cash_flows["base_rent"]
        
        # Month 1: $2,500 base
        assert base_rent.iloc[0] == pytest.approx(2500.0, rel=1e-3)
        
        # Month 13: 3% increase
        assert base_rent.iloc[12] == pytest.approx(2575.0, rel=1e-3)
        
        # Month 25: 4% increase on current rent
        assert base_rent.iloc[24] == pytest.approx(2678.0, rel=1e-3)

    def test_helper_stepped_fixed_escalations(self, base_spec, context):
        """Test helper function for stepped fixed escalations"""
        escalations = create_stepped_fixed_escalations(
            start_month=13,  # Start in year 2
            annual_amounts=[1.0, 1.5, 2.0],  # $1, $1.50, $2 per SF
            reference=PropertyAttributeKey.NET_RENTABLE_AREA,
        )
        
        spec = base_spec.model_copy(update={"rent_escalations": escalations})
        lease = OfficeLease.from_spec(spec, date(2024, 1, 1), context.timeline)
        cash_flows = lease.compute_cf(context)
        
        base_rent = cash_flows["base_rent"]
        
        # Month 1: $2,500 base
        assert base_rent.iloc[0] == pytest.approx(2500.0, rel=1e-3)
        
        # Month 13: Add $1/SF = $83.33/month
        assert base_rent.iloc[12] == pytest.approx(2583.33, rel=1e-2)
        
        # Month 25: Add additional $1.50/SF = $125/month
        assert base_rent.iloc[24] == pytest.approx(2708.33, rel=1e-2)

    def test_helper_simple_annual_escalation(self, base_spec, context):
        """Test helper function for simple recurring annual escalation"""
        escalation = create_simple_annual_escalation(
            rate=0.03,  # 3% annually
            start_month=1,  # Start immediately
            reference=PropertyAttributeKey.NET_RENTABLE_AREA,
        )
        
        spec = base_spec.model_copy(update={"rent_escalations": [escalation]})
        lease = OfficeLease.from_spec(spec, date(2024, 1, 1), context.timeline)
        cash_flows = lease.compute_cf(context)
        
        base_rent = cash_flows["base_rent"]
        
        # Month 1: $2,500 base (escalation applies immediately)
        assert base_rent.iloc[0] == pytest.approx(2575.0, rel=1e-3)  # 2500 * 1.03
        
        # Month 13: Second escalation (compound)
        assert base_rent.iloc[12] == pytest.approx(2652.25, rel=1e-3)  # 2575 * 1.03

    def test_helper_absolute_date_escalations(self, base_spec, context):
        """Test helper function for escalations on specific dates"""
        escalations = create_escalations_from_absolute_dates(
            escalation_schedule=[
                (date(2024, 7, 1), 0.03, "percentage"),
                (date(2024, 12, 1), 1.5, "fixed"),
            ],
            reference=PropertyAttributeKey.NET_RENTABLE_AREA,
        )
        
        spec = base_spec.model_copy(update={"rent_escalations": escalations})
        lease = OfficeLease.from_spec(spec, date(2024, 1, 1), context.timeline)
        cash_flows = lease.compute_cf(context)
        
        base_rent = cash_flows["base_rent"]
        
        # Month 1: $2,500 base
        assert base_rent.iloc[0] == pytest.approx(2500.0, rel=1e-3)
        
        # Month 7: 3% increase 
        assert base_rent.iloc[6] == pytest.approx(2575.0, rel=1e-3)
        
        # Month 12: Add $1.50/SF = $125/month
        assert base_rent.iloc[11] == pytest.approx(2700.0, rel=1e-2)

    def test_growth_rate_objects_with_multiple_escalations(self, base_spec, context):
        """Test multiple escalations using growth rate objects"""
        time_varying_rate = PercentageGrowthRate(
            name="Variable Rate",
            value={
                date(2024, 7, 1): 0.02,  # 2% in July
                date(2024, 12, 1): 0.04,  # 4% in December
            }
        )
        
        fixed_rate_obj = FixedGrowthRate(
            name="Fixed Dollar Amount",
            value=1000.0  # $1000 annually
        )
        
        escalations = [
            OfficeRentEscalation(
                type="percentage",
                rate=time_varying_rate,
                reference=PropertyAttributeKey.NET_RENTABLE_AREA,
                is_relative=True,
                start_date=date(2024, 7, 1),
                recurring=False,
            ),
            OfficeRentEscalation(
                type="fixed",
                rate=fixed_rate_obj,
                is_relative=False,
                start_date=date(2024, 12, 1),
                recurring=False,
            ),
        ]
        
        spec = base_spec.model_copy(update={"rent_escalations": escalations})
        lease = OfficeLease.from_spec(spec, date(2024, 1, 1), context.timeline)
        cash_flows = lease.compute_cf(context)
        
        base_rent = cash_flows["base_rent"]
        
        # Month 1: $2,500 base
        assert base_rent.iloc[0] == pytest.approx(2500.0, rel=1e-3)
        
        # Month 7: 2% increase (from time-varying rate for July)
        assert base_rent.iloc[6] == pytest.approx(2550.0, rel=1e-3)
        
        # Month 12: Add $1000/year = $83.33/month
        assert base_rent.iloc[11] == pytest.approx(2633.33, rel=1e-2) 