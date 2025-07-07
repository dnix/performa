"""
Tests for developer fee models.
"""

import pytest
from pydantic import ValidationError

from performa.deal.fees import DeveloperFee


class TestDeveloperFee:
    """Test DeveloperFee model."""
    
    def test_fixed_amount_fee_creation(self):
        """Test creating a fixed amount developer fee."""
        fee = DeveloperFee(
            name="Development Fee",
            amount=500_000,
            payment_timing="completion"
        )
        
        assert fee.name == "Development Fee"
        assert fee.amount == 500_000
        assert fee.is_percentage is False
        assert fee.payment_timing == "completion"
        assert fee.upfront_percentage == 0.5  # default
    
    def test_percentage_fee_creation(self):
        """Test creating a percentage-based developer fee."""
        fee = DeveloperFee(
            name="Development Fee",
            amount=0.04,  # 4%
            is_percentage=True,
            payment_timing="split"
        )
        
        assert fee.name == "Development Fee"
        assert fee.amount == 0.04
        assert fee.is_percentage is True
        assert fee.payment_timing == "split"
        assert fee.completion_percentage == 0.5  # 1.0 - 0.5
    
    def test_fee_defaults(self):
        """Test default values for developer fee."""
        fee = DeveloperFee(amount=100_000)
        
        assert fee.name == "Developer Fee"
        assert fee.is_percentage is False
        assert fee.payment_timing == "completion"
        assert fee.upfront_percentage == 0.5
        assert fee.completion_percentage == 0.5
        assert fee.description is None
    
    def test_calculate_total_fee_fixed(self):
        """Test calculating total fee for fixed amount."""
        fee = DeveloperFee(amount=500_000)
        
        # Fixed amount doesn't depend on project cost
        total_fee = fee.calculate_total_fee(10_000_000)
        assert total_fee == 500_000
        
        # Should be same regardless of project cost
        total_fee = fee.calculate_total_fee(20_000_000)
        assert total_fee == 500_000
    
    def test_calculate_total_fee_percentage(self):
        """Test calculating total fee for percentage-based amount."""
        fee = DeveloperFee(amount=0.04, is_percentage=True)  # 4%
        
        # 4% of $10M = $400K
        total_fee = fee.calculate_total_fee(10_000_000)
        assert total_fee == 400_000
        
        # 4% of $20M = $800K
        total_fee = fee.calculate_total_fee(20_000_000)
        assert total_fee == 800_000
    
    def test_upfront_payment_timing(self):
        """Test upfront payment timing calculations."""
        fee = DeveloperFee(amount=500_000, payment_timing="upfront")
        
        upfront_fee = fee.calculate_upfront_fee(10_000_000)
        completion_fee = fee.calculate_completion_fee(10_000_000)
        
        assert upfront_fee == 500_000
        assert completion_fee == 0
    
    def test_completion_payment_timing(self):
        """Test completion payment timing calculations."""
        fee = DeveloperFee(amount=500_000, payment_timing="completion")
        
        upfront_fee = fee.calculate_upfront_fee(10_000_000)
        completion_fee = fee.calculate_completion_fee(10_000_000)
        
        assert upfront_fee == 0
        assert completion_fee == 500_000
    
    def test_split_payment_timing(self):
        """Test split payment timing calculations."""
        fee = DeveloperFee(
            amount=500_000, 
            payment_timing="split",
            upfront_percentage=0.3  # 30% upfront, 70% completion
        )
        
        upfront_fee = fee.calculate_upfront_fee(10_000_000)
        completion_fee = fee.calculate_completion_fee(10_000_000)
        
        assert upfront_fee == 150_000  # 30% of 500K
        assert completion_fee == 350_000  # 70% of 500K
        assert upfront_fee + completion_fee == 500_000
    
    def test_split_payment_percentage_fee(self):
        """Test split payment with percentage-based fee."""
        fee = DeveloperFee(
            amount=0.04,  # 4%
            is_percentage=True,
            payment_timing="split",
            upfront_percentage=0.6  # 60% upfront, 40% completion
        )
        
        total_cost = 10_000_000
        upfront_fee = fee.calculate_upfront_fee(total_cost)
        completion_fee = fee.calculate_completion_fee(total_cost)
        
        expected_total = 400_000  # 4% of $10M
        assert upfront_fee == 240_000  # 60% of 400K
        assert completion_fee == 160_000  # 40% of 400K
        assert upfront_fee + completion_fee == expected_total
    
    def test_completion_percentage_property(self):
        """Test completion_percentage computed property."""
        fee = DeveloperFee(amount=100_000, upfront_percentage=0.3)
        assert fee.completion_percentage == pytest.approx(0.7)
        
        fee = DeveloperFee(amount=100_000, upfront_percentage=0.8)
        assert fee.completion_percentage == pytest.approx(0.2)
    
    def test_string_representation_fixed(self):
        """Test string representation for fixed amount fee."""
        fee = DeveloperFee(
            name="Development Fee",
            amount=500_000,
            payment_timing="completion"
        )
        
        expected = "Development Fee: $500,000 (completion)"
        assert str(fee) == expected
    
    def test_string_representation_percentage(self):
        """Test string representation for percentage fee."""
        fee = DeveloperFee(
            name="Development Fee",
            amount=0.04,
            is_percentage=True,
            payment_timing="split"
        )
        
        expected = "Development Fee: 4.0% of total cost (split)"
        assert str(fee) == expected
    
    def test_percentage_validation_too_low(self):
        """Test validation of percentage amounts that are too low."""
        with pytest.raises(ValidationError) as exc_info:
            DeveloperFee(amount=0.0005, is_percentage=True)  # 0.05%
        
        assert "must be between 0.1% and 20%" in str(exc_info.value)
    
    def test_percentage_validation_too_high(self):
        """Test validation of percentage amounts that are too high."""
        with pytest.raises(ValidationError) as exc_info:
            DeveloperFee(amount=0.25, is_percentage=True)  # 25%
        
        assert "must be between 0.1% and 20%" in str(exc_info.value)
    
    def test_percentage_validation_valid_range(self):
        """Test validation accepts valid percentage ranges."""
        # Test minimum valid
        fee = DeveloperFee(amount=0.001, is_percentage=True)  # 0.1%
        assert fee.amount == 0.001
        
        # Test maximum valid
        fee = DeveloperFee(amount=0.20, is_percentage=True)  # 20%
        assert fee.amount == 0.20
        
        # Test typical range
        fee = DeveloperFee(amount=0.04, is_percentage=True)  # 4%
        assert fee.amount == 0.04
    
    def test_fixed_amount_validation(self):
        """Test validation of fixed amounts."""
        # Fixed amounts should accept any positive value
        fee = DeveloperFee(amount=100_000)
        assert fee.amount == 100_000
        
        fee = DeveloperFee(amount=10_000_000)
        assert fee.amount == 10_000_000
        
        # Should reject negative amounts
        with pytest.raises(ValidationError):
            DeveloperFee(amount=-100_000)
    
    def test_fee_with_description(self):
        """Test fee with optional description."""
        fee = DeveloperFee(
            name="Custom Development Fee",
            amount=750_000,
            description="Fee for mixed-use development project"
        )
        
        assert fee.description == "Fee for mixed-use development project"
    
    def test_fee_uid_generation(self):
        """Test that each fee gets a unique UUID."""
        fee1 = DeveloperFee(amount=100_000)
        fee2 = DeveloperFee(amount=200_000)
        
        assert fee1.uid != fee2.uid
        assert len(str(fee1.uid)) == 36  # UUID string length


class TestDeveloperFeeIntegration:
    """Test DeveloperFee integration scenarios."""
    
    def test_typical_development_fee_scenarios(self):
        """Test typical real-world developer fee scenarios."""
        # Scenario 1: Fixed amount completion fee
        dev_fee = DeveloperFee(
            name="Development Fee",
            amount=1_000_000,
            payment_timing="completion"
        )
        
        project_cost = 25_000_000
        assert dev_fee.calculate_total_fee(project_cost) == 1_000_000
        assert dev_fee.calculate_upfront_fee(project_cost) == 0
        assert dev_fee.calculate_completion_fee(project_cost) == 1_000_000
        
        # Scenario 2: Percentage-based split fee (industry standard)
        dev_fee = DeveloperFee(
            name="Development Fee",
            amount=0.04,  # 4%
            is_percentage=True,
            payment_timing="split",
            upfront_percentage=0.5  # 50/50 split
        )
        
        project_cost = 25_000_000
        expected_total = 1_000_000  # 4% of $25M
        assert dev_fee.calculate_total_fee(project_cost) == expected_total
        assert dev_fee.calculate_upfront_fee(project_cost) == 500_000
        assert dev_fee.calculate_completion_fee(project_cost) == 500_000
        
        # Scenario 3: Small acquisition fee
        acq_fee = DeveloperFee(
            name="Acquisition Fee",
            amount=0.015,  # 1.5%
            is_percentage=True,
            payment_timing="upfront"
        )
        
        acquisition_cost = 50_000_000
        expected_total = 750_000  # 1.5% of $50M
        assert acq_fee.calculate_total_fee(acquisition_cost) == expected_total
        assert acq_fee.calculate_upfront_fee(acquisition_cost) == expected_total
        assert acq_fee.calculate_completion_fee(acquisition_cost) == 0 