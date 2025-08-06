# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Tests for deal fee models.
"""

from datetime import date
from uuid import UUID

import pandas as pd
import pytest
from pydantic import ValidationError

from performa.core.primitives.draw_schedule import (
    FirstLastDrawSchedule,
    FirstOnlyDrawSchedule,
    LastOnlyDrawSchedule,
    ManualDrawSchedule,
    UniformDrawSchedule,
)
from performa.core.primitives.timeline import Timeline
from performa.deal.entities import Partner
from performa.deal.fees import DealFee


class TestDealFee:
    """Test DealFee model."""
    
    @pytest.fixture
    def timeline(self):
        """Create a test timeline."""
        return Timeline.from_dates(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31)
        )
    
    @pytest.fixture
    def sample_partner(self):
        """Create a sample partner for testing."""
        return Partner(
            name="Developer",
            kind="GP",
            share=0.25
        )
    
    def test_basic_fee_creation(self, timeline, sample_partner):
        """Test creating a basic deal fee."""
        fee = DealFee(
            name="Development Fee",
            value=500_000,
            payee=sample_partner,
            timeline=timeline
        )
        
        assert fee.name == "Development Fee"
        assert fee.value == 500_000
        assert fee.payee == sample_partner
        assert fee.timeline == timeline
        assert isinstance(fee.draw_schedule, UniformDrawSchedule)  # default
    
    def test_fee_defaults(self, timeline, sample_partner):
        """Test default values for deal fee."""
        fee = DealFee(
            name="Developer Fee",
            value=100_000,
            payee=sample_partner,
            timeline=timeline
        )
        
        assert fee.name == "Developer Fee"
        assert fee.value == 100_000
        assert fee.payee == sample_partner
        assert fee.timeline == timeline
        assert isinstance(fee.draw_schedule, UniformDrawSchedule)  # default
    
    def test_calculate_total_fee_fixed(self, timeline, sample_partner):
        """Test calculating total fee for fixed amount."""
        fee = DealFee(
            name="Developer Fee",
            value=500_000,
            payee=sample_partner,
            timeline=timeline
        )
        
        # Fixed amount is always the same regardless of project details
        total_fee = fee.calculate_total_fee()
        assert total_fee == 500_000
    
    def test_fee_small_values(self, timeline, sample_partner):
        """Test that small fee values are accepted."""
        fee = DealFee(
            name="Developer Fee",
            value=5_000,
            payee=sample_partner,
            timeline=timeline
        )
        assert fee.value == 5_000
    
    def test_fee_large_values(self, timeline, sample_partner):
        """Test that large fee values are accepted."""
        fee = DealFee(
            name="Developer Fee",
            value=15_000_000,
            payee=sample_partner,
            timeline=timeline
        )
        assert fee.value == 15_000_000
    
    def test_fee_various_ranges(self, timeline, sample_partner):
        """Test various fee ranges are accepted."""
        # Test small fee
        fee_small = DealFee(
            name="Developer Fee",
            value=1_000,
            payee=sample_partner,
            timeline=timeline
        )
        assert fee_small.value == 1_000
        
        # Test large fee
        fee_large = DealFee(
            name="Developer Fee",
            value=50_000_000,
            payee=sample_partner,
            timeline=timeline
        )
        assert fee_large.value == 50_000_000
        
        # Test typical range
        fee_typical = DealFee(
            name="Developer Fee",
            value=750_000,
            payee=sample_partner,
            timeline=timeline
        )
        assert fee_typical.value == 750_000
    
    def test_fee_with_description(self, timeline, sample_partner):
        """Test fee creation with description."""
        fee = DealFee(
            name="Development Fee",
            value=500_000,
            payee=sample_partner,
            timeline=timeline,
            description="Fee for development management services"
        )
        
        assert fee.description == "Fee for development management services"
    
    def test_fee_uid_generation(self, timeline, sample_partner):
        """Test that fees get unique UIDs."""
        fee1 = DealFee(name="Fee 1", value=100_000, payee=sample_partner, timeline=timeline)
        fee2 = DealFee(name="Fee 2", value=200_000, payee=sample_partner, timeline=timeline)
        
        assert fee1.uid != fee2.uid
        assert isinstance(fee1.uid, UUID)
    
    def test_series_calculation(self, timeline, sample_partner):
        """Test calculating fee as a pandas Series."""
        fee = DealFee(
            name="Development Fee",
            value=500_000,
            payee=sample_partner,
            timeline=timeline
        )
        
        # Test series with periods
        series = fee.calculate_total_fee_series(periods=3)
        assert len(series) == 3
        assert all(series == 500_000)
        
        # Test series with custom index
        custom_index = pd.Index(['Q1', 'Q2', 'Q3'])
        series_indexed = fee.calculate_total_fee_series(periods=3, index=custom_index)
        assert len(series_indexed) == 3
        assert list(series_indexed.index) == ['Q1', 'Q2', 'Q3']
        assert all(series_indexed == 500_000)
    
    def test_dict_value_creation(self, timeline, sample_partner):
        """Test creating a fee with milestone-based dict values."""
        milestone_payments = {
            date(2024, 3, 1): 100_000,
            date(2024, 9, 1): 200_000,
            date(2025, 3, 1): 200_000,
        }
        
        fee = DealFee(
            name="Development Fee",
            value=milestone_payments,
            payee=sample_partner,
            timeline=timeline
        )
        
        assert fee.name == "Development Fee"
        assert fee.value == milestone_payments
        assert fee.calculate_total_fee() == 500_000
    
    def test_dict_value_validation(self, timeline, sample_partner):
        """Test validation of dict values."""
        # Invalid key type
        with pytest.raises(ValidationError) as exc_info:
            DealFee(
                name="Fee",
                value={123: 100_000},  # Integer key instead of date
                payee=sample_partner,
                timeline=timeline
            )
        assert "date_from_datetime_inexact" in str(exc_info.value) or "must be dates" in str(exc_info.value)
        
        # Negative value
        with pytest.raises(ValidationError) as exc_info:
            DealFee(
                name="Fee",
                value={date(2024, 3, 1): -100_000},
                payee=sample_partner,
                timeline=timeline
            )
        assert "greater than or equal to 0" in str(exc_info.value) or "must be non-negative" in str(exc_info.value)
    
    def test_dict_to_series_conversion(self, timeline, sample_partner):
        """Test converting milestone dict to series."""
        milestone_payments = {
            date(2024, 3, 1): 100_000,
            date(2024, 6, 1): 200_000,
        }
        
        fee = DealFee(
            name="Development Fee",
            value=milestone_payments,
            payee=sample_partner,
            timeline=timeline
        )
        
        # Create a period index
        periods = pd.period_range('2024-01', periods=12, freq='M')
        series = fee.calculate_total_fee_series(periods=12, index=periods)
        
        assert len(series) == 12
        assert series[pd.Period('2024-03', freq='M')] == 100_000
        assert series[pd.Period('2024-06', freq='M')] == 200_000
        assert series[pd.Period('2024-01', freq='M')] == 0  # No payment this month
    
    def test_dict_value_requires_index_for_series(self, timeline, sample_partner):
        """Test that dict values require an index when converting to series."""
        fee = DealFee(
            name="Fee",
            value={date(2024, 3, 1): 100_000},
            payee=sample_partner,
            timeline=timeline
        )
        
        with pytest.raises(ValueError) as exc_info:
            fee.calculate_total_fee_series(periods=12)
        assert "Index must be provided" in str(exc_info.value)
    
    def test_custom_fee_extension(self, timeline, sample_partner):
        """Test that DealFee can be extended for custom fee types."""
        
        class AssetManagementFee(DealFee):
            """Custom asset management fee."""
            
            def __str__(self) -> str:
                return f"{self.name}: ${self.value:,.0f} (annual)"
        
        fee = AssetManagementFee(
            name="Asset Management Fee",
            value=375_000,
            payee=sample_partner,
            timeline=timeline
        )
        
        assert str(fee) == "Asset Management Fee: $375,000 (annual)"


class TestDealFeeDrawScheduleIntegration:
    """Test DealFee integration with DrawSchedule system."""
    
    @pytest.fixture
    def timeline(self):
        """Create a test timeline."""
        return Timeline.from_dates(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31)
        )
    
    @pytest.fixture
    def sample_partner(self):
        """Create a sample partner for testing."""
        return Partner(
            name="Developer",
            kind="GP",
            share=0.25
        )
    
    def test_create_upfront_fee(self, timeline, sample_partner):
        """Test creating upfront fee using factory method."""
        fee = DealFee.create_upfront_fee(
            name="Development Fee",
            value=500_000,
            payee=sample_partner,
            timeline=timeline
        )
        
        assert fee.name == "Development Fee"
        assert fee.value == 500_000
        assert fee.payee == sample_partner
        assert fee.timeline == timeline
        assert isinstance(fee.draw_schedule, FirstOnlyDrawSchedule)
    
    def test_create_completion_fee(self, timeline, sample_partner):
        """Test creating completion fee using factory method."""
        fee = DealFee.create_completion_fee(
            name="Development Fee",
            value=750_000,
            payee=sample_partner,
            timeline=timeline
        )
        
        assert fee.name == "Development Fee"
        assert fee.value == 750_000
        assert fee.payee == sample_partner
        assert fee.timeline == timeline
        assert isinstance(fee.draw_schedule, LastOnlyDrawSchedule)
    
    def test_create_split_fee_with_first_percentage(self, timeline, sample_partner):
        """Test creating split fee with first_percentage."""
        fee = DealFee.create_split_fee(
            name="Development Fee",
            value=1_000_000,
            payee=sample_partner,
            timeline=timeline,
            first_percentage=0.3
        )
        
        assert fee.name == "Development Fee"
        assert fee.value == 1_000_000
        assert fee.payee == sample_partner
        assert fee.timeline == timeline
        assert isinstance(fee.draw_schedule, FirstLastDrawSchedule)
        assert fee.draw_schedule.first_percentage == 0.3
        assert fee.draw_schedule.effective_first_percentage == 0.3
    
    def test_create_split_fee_with_last_percentage(self, timeline, sample_partner):
        """Test creating split fee with last_percentage."""
        fee = DealFee.create_split_fee(
            name="Development Fee",
            value=1_000_000,
            payee=sample_partner,
            timeline=timeline,
            last_percentage=0.7
        )
        
        assert fee.name == "Development Fee"
        assert fee.value == 1_000_000
        assert fee.payee == sample_partner
        assert fee.timeline == timeline
        assert isinstance(fee.draw_schedule, FirstLastDrawSchedule)
        assert fee.draw_schedule.last_percentage == 0.7
        assert fee.draw_schedule.effective_first_percentage == 0.3
    
    def test_create_split_fee_validation_errors(self, timeline, sample_partner):
        """Test split fee validation errors."""
        # Both percentages specified
        with pytest.raises(ValueError, match="Cannot specify both"):
            DealFee.create_split_fee(
                name="Fee",
                value=1_000_000,
                payee=sample_partner,
                timeline=timeline,
                first_percentage=0.3,
                last_percentage=0.7
            )
        
        # Neither percentage specified
        with pytest.raises(ValueError, match="Must specify either"):
            DealFee.create_split_fee(
                name="Fee",
                value=1_000_000,
                payee=sample_partner,
                timeline=timeline
            )
    
    def test_create_uniform_fee(self, timeline, sample_partner):
        """Test creating uniform fee using factory method."""
        fee = DealFee.create_uniform_fee(
            name="Management Fee",
            value=240_000,
            payee=sample_partner,
            timeline=timeline
        )
        
        assert fee.name == "Management Fee"
        assert fee.value == 240_000
        assert fee.payee == sample_partner
        assert fee.timeline == timeline
        assert isinstance(fee.draw_schedule, UniformDrawSchedule)
    
    def test_custom_draw_schedule(self, timeline, sample_partner):
        """Test using custom draw schedule."""
        fee = DealFee(
            name="Custom Fee",
            value=600_000,
            payee=sample_partner,
            timeline=timeline,
            draw_schedule=ManualDrawSchedule(values=[0.2, 0.3, 0.5])
        )
        
        assert fee.name == "Custom Fee"
        assert fee.value == 600_000
        assert fee.payee == sample_partner
        assert fee.timeline == timeline
        assert isinstance(fee.draw_schedule, ManualDrawSchedule)
    
    def test_calculate_fee_schedule_upfront(self, timeline, sample_partner):
        """Test calculating fee cash flows for upfront payment."""
        fee = DealFee.create_upfront_fee(
            name="Development Fee",
            value=500_000,
            payee=sample_partner,
            timeline=timeline
        )
        
        cash_flows = fee.compute_cf()
        
        assert isinstance(cash_flows, pd.Series)
        assert len(cash_flows) == timeline.duration_months
        assert cash_flows.sum() == 500_000
        assert cash_flows.iloc[0] == 500_000  # All in first period
        assert cash_flows.iloc[1:].sum() == 0  # Nothing in other periods
    
    def test_calculate_fee_schedule_completion(self, timeline, sample_partner):
        """Test calculating fee cash flows for completion payment."""
        fee = DealFee.create_completion_fee(
            name="Development Fee",
            value=750_000,
            payee=sample_partner,
            timeline=timeline
        )
        
        cash_flows = fee.compute_cf()
        
        assert isinstance(cash_flows, pd.Series)
        assert len(cash_flows) == timeline.duration_months
        assert cash_flows.sum() == 750_000
        assert cash_flows.iloc[-1] == 750_000  # All in last period
        assert cash_flows.iloc[:-1].sum() == 0  # Nothing in other periods
    
    def test_calculate_fee_schedule_split(self, timeline, sample_partner):
        """Test calculating fee cash flows for split payment."""
        fee = DealFee.create_split_fee(
            name="Development Fee",
            value=1_000_000,
            payee=sample_partner,
            timeline=timeline,
            first_percentage=0.3
        )
        
        cash_flows = fee.compute_cf()
        
        assert isinstance(cash_flows, pd.Series)
        assert len(cash_flows) == timeline.duration_months
        assert cash_flows.sum() == 1_000_000
        assert cash_flows.iloc[0] == 300_000  # 30% upfront
        assert cash_flows.iloc[-1] == 700_000  # 70% completion
        assert cash_flows.iloc[1:-1].sum() == 0  # Nothing in middle periods
    
    def test_calculate_fee_schedule_uniform(self, timeline, sample_partner):
        """Test calculating fee cash flows for uniform payment."""
        fee = DealFee.create_uniform_fee(
            name="Management Fee",
            value=240_000,
            payee=sample_partner,
            timeline=timeline
        )
        
        cash_flows = fee.compute_cf()
        
        assert isinstance(cash_flows, pd.Series)
        assert len(cash_flows) == timeline.duration_months
        assert cash_flows.sum() == 240_000
        
        # Should be evenly distributed
        expected_monthly = 240_000 / timeline.duration_months
        assert all(abs(val - expected_monthly) < 0.01 for val in cash_flows)
    
    def test_calculate_fee_schedule_manual(self, timeline, sample_partner):
        """Test calculating fee cash flows for manual draw schedule."""
        # Create a manual schedule with 12 values (one for each month)
        # Pattern: higher values in first few months, then small values
        values = [3, 6, 9, 1, 1, 1, 1, 1, 1, 1, 1, 1]  # All positive values
        
        fee = DealFee(
            name="Custom Fee",
            value=600_000,
            payee=sample_partner,
            timeline=timeline,
            draw_schedule=ManualDrawSchedule(values=values)
        )
        
        cash_flows = fee.compute_cf()
        
        assert isinstance(cash_flows, pd.Series)
        assert len(cash_flows) == timeline.duration_months
        assert cash_flows.sum() == 600_000
        
        # First 3 periods should follow the pattern 3:6:9 (normalized)
        # values=[3,6,9,1,1,1,1,1,1,1,1,1] sum to 27
        # So normalized: [3/27, 6/27, 9/27, 1/27, ...] = [1/9, 2/9, 3/9, 1/27, ...]
        assert abs(cash_flows.iloc[0] - (600_000 * 3 / 27)) < 0.01  # 3/27 * 600k
        assert abs(cash_flows.iloc[1] - (600_000 * 6 / 27)) < 0.01  # 6/27 * 600k
        assert abs(cash_flows.iloc[2] - (600_000 * 9 / 27)) < 0.01  # 9/27 * 600k
        assert abs(cash_flows.iloc[3] - (600_000 * 1 / 27)) < 0.01  # 1/27 * 600k
    
    def test_upfront_fee_calculation_with_draw_schedule(self, timeline, sample_partner):
        """Test upfront_amount with DrawSchedule."""
        fee = DealFee.create_split_fee(
            name="Development Fee",
            value=1_000_000,
            payee=sample_partner,
            timeline=timeline,
            first_percentage=0.3
        )
        
        upfront_fee = fee.upfront_amount()
        assert upfront_fee == 300_000  # 30% of 1M
    
    def test_completion_fee_calculation_with_draw_schedule(self, timeline, sample_partner):
        """Test completion_amount with DrawSchedule."""
        fee = DealFee.create_split_fee(
            name="Development Fee",
            value=1_000_000,
            payee=sample_partner,
            timeline=timeline,
            first_percentage=0.3
        )
        
        completion_fee = fee.completion_amount()
        assert completion_fee == 700_000  # 70% of 1M
    
    def test_string_representation_with_draw_schedule(self, timeline, sample_partner):
        """Test string representation with DrawSchedule."""
        fee = DealFee.create_upfront_fee(
            name="Development Fee",
            value=500_000,
            payee=sample_partner,
            timeline=timeline
        )
        
        string_repr = str(fee)
        assert "Development Fee: $500,000 (FirstOnlyDrawSchedule)" in string_repr


class TestDealFeeIntegration:
    """Test DealFee integration scenarios."""
    
    @pytest.fixture
    def timeline(self):
        """Create a test timeline."""
        return Timeline.from_dates(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31)
        )
    
    @pytest.fixture
    def sample_partner(self):
        """Create a sample partner for testing."""
        return Partner(
            name="Developer",
            kind="GP",
            share=0.25
        )
    
    def test_typical_development_fee_scenarios(self, timeline, sample_partner):
        """Test typical real-world developer fee scenarios."""
        # Scenario 1: Fixed amount completion fee
        dev_fee = DealFee.create_completion_fee(
            name="Development Fee",
            value=1_000_000,
            payee=sample_partner,
            timeline=timeline
        )
        
        assert dev_fee.calculate_total_fee() == 1_000_000
        assert dev_fee.upfront_amount() == 0
        assert dev_fee.completion_amount() == 1_000_000
        
        # Scenario 2: Split fee (30% upfront, 70% completion)
        split_fee = DealFee.create_split_fee(
            name="Development Fee",
            value=2_000_000,
            payee=sample_partner,
            timeline=timeline,
            first_percentage=0.3
        )
        
        assert split_fee.calculate_total_fee() == 2_000_000
        assert split_fee.upfront_amount() == 600_000
        assert split_fee.completion_amount() == 1_400_000
        
        # Scenario 3: Uniform fee spread over construction
        uniform_fee = DealFee.create_uniform_fee(
            name="Management Fee",
            value=360_000,
            payee=sample_partner,
            timeline=timeline
        )
        
        assert uniform_fee.calculate_total_fee() == 360_000
        expected_monthly = 360_000 / timeline.duration_months
        assert uniform_fee.upfront_amount() == expected_monthly
        assert uniform_fee.completion_amount() == expected_monthly 