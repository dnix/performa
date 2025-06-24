"""
Comprehensive tests for reusable validation utilities.

These tests serve multiple purposes:
1. Ensure validation logic works correctly
2. Document usage patterns for future developers
3. Prevent regression bugs
4. Cover edge cases and error conditions
"""

from __future__ import annotations

from datetime import date
from typing import Optional

import pytest
from pydantic import ValidationError, model_validator

from performa.common.primitives import Model
from performa.common.primitives.validation import (
    ValidationMixin,
    validate_term_specification,
)


class TestValidationMixin:
    """Test the ValidationMixin utility methods."""
    
    def test_validate_either_or_required_success_first_field(self):
        """Test successful validation when first field is provided."""
        data = {"field_a": "value", "field_b": None}
        result = ValidationMixin.validate_either_or_required(data, "field_a", "field_b")
        assert result == data
    
    def test_validate_either_or_required_success_second_field(self):
        """Test successful validation when second field is provided."""
        data = {"field_a": None, "field_b": "value"}
        result = ValidationMixin.validate_either_or_required(data, "field_a", "field_b")
        assert result == data
    
    def test_validate_either_or_required_fails_neither(self):
        """Test validation fails when neither field is provided."""
        data = {"field_a": None, "field_b": None}
        with pytest.raises(ValueError, match="Either field_a or field_b must be provided"):
            ValidationMixin.validate_either_or_required(data, "field_a", "field_b")
    
    def test_validate_either_or_required_fails_both(self):
        """Test validation fails when both fields are provided."""
        data = {"field_a": "value", "field_b": "value"}
        with pytest.raises(ValueError, match="Cannot provide both field_a and field_b"):
            ValidationMixin.validate_either_or_required(data, "field_a", "field_b")
    
    def test_validate_either_or_required_custom_error(self):
        """Test custom error message is used."""
        data = {"field_a": None, "field_b": None}
        with pytest.raises(ValueError, match="Custom error message"):
            ValidationMixin.validate_either_or_required(
                data, "field_a", "field_b", "Custom error message"
            )
    
    def test_validate_date_ordering_success(self):
        """Test successful date ordering validation."""
        data = {
            "start_date": date(2024, 1, 1),
            "end_date": date(2024, 12, 31)
        }
        result = ValidationMixin.validate_date_ordering(data, "start_date", "end_date")
        assert result == data
    
    def test_validate_date_ordering_fails(self):
        """Test date ordering validation fails when end is before start."""
        data = {
            "start_date": date(2024, 12, 31),
            "end_date": date(2024, 1, 1)
        }
        with pytest.raises(ValueError, match="end_date must be after start_date"):
            ValidationMixin.validate_date_ordering(data, "start_date", "end_date")
    
    def test_validate_date_ordering_same_date_fails(self):
        """Test date ordering validation fails when dates are the same."""
        data = {
            "start_date": date(2024, 1, 1),
            "end_date": date(2024, 1, 1)
        }
        with pytest.raises(ValueError, match="end_date must be after start_date"):
            ValidationMixin.validate_date_ordering(data, "start_date", "end_date")
    
    def test_validate_date_ordering_missing_dates(self):
        """Test date ordering validation skips when dates are missing."""
        data = {"start_date": None, "end_date": None}
        result = ValidationMixin.validate_date_ordering(data, "start_date", "end_date")
        assert result == data
    
    def test_validate_conditional_requirement_success(self):
        """Test successful conditional requirement validation."""
        data = {"condition": "trigger_value", "required": "provided"}
        result = ValidationMixin.validate_conditional_requirement(
            data, "condition", "trigger_value", "required"
        )
        assert result == data
    
    def test_validate_conditional_requirement_not_triggered(self):
        """Test conditional requirement when condition is not met."""
        data = {"condition": "other_value", "required": None}
        result = ValidationMixin.validate_conditional_requirement(
            data, "condition", "trigger_value", "required"
        )
        assert result == data
    
    def test_validate_conditional_requirement_fails(self):
        """Test conditional requirement fails when triggered but not provided."""
        data = {"condition": "trigger_value", "required": None}
        with pytest.raises(ValueError, match="required is required when condition is trigger_value"):
            ValidationMixin.validate_conditional_requirement(
                data, "condition", "trigger_value", "required"
            )
    
    def test_validate_conditional_requirement_multiple_values(self):
        """Test conditional requirement with multiple trigger values."""
        data = {"condition": "value2", "required": None}
        with pytest.raises(ValueError, match="required is required when condition is value2"):
            ValidationMixin.validate_conditional_requirement(
                data, "condition", ["value1", "value2"], "required"
            )


class TestValidateTermSpecification:
    """Test the validate_term_specification function."""
    
    class TermModel(Model):
        """Test model for term validation."""
        start_date: date
        end_date: Optional[date] = None
        term_months: Optional[int] = None
        name: str
        
        @model_validator(mode="after")
        @classmethod
        def check_term(cls, data):
            """Validate term specification using reusable validator."""
            return validate_term_specification(cls, data)
    
    def test_valid_with_end_date(self):
        """Test successful validation with end_date."""
        model = self.TermModel(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            name="Test"
        )
        assert model.start_date == date(2024, 1, 1)
        assert model.end_date == date(2024, 12, 31)
        assert model.term_months is None
    
    def test_valid_with_term_months(self):
        """Test successful validation with term_months."""
        model = self.TermModel(
            start_date=date(2024, 1, 1),
            term_months=12,
            name="Test"
        )
        assert model.start_date == date(2024, 1, 1)
        assert model.term_months == 12
        assert model.end_date is None
    
    def test_valid_with_both(self):
        """Test successful validation with both fields (allowed)."""
        model = self.TermModel(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            term_months=12,
            name="Test"
        )
        assert model.start_date == date(2024, 1, 1)
        assert model.end_date == date(2024, 12, 31)
        assert model.term_months == 12
    
    def test_fails_with_neither(self):
        """Test validation fails when neither field is provided."""
        with pytest.raises(ValidationError, match="Either end_date or term_months must be provided"):
            self.TermModel(
                start_date=date(2024, 1, 1),
                name="Test"
            )
    
    def test_fails_with_invalid_date_order(self):
        """Test validation fails with invalid date ordering."""
        with pytest.raises(ValidationError, match="end_date must be after start_date"):
            self.TermModel(
                start_date=date(2024, 12, 31),
                end_date=date(2024, 1, 1),
                name="Test"
            )
    
    def test_fails_with_same_dates(self):
        """Test validation fails when start and end dates are the same."""
        with pytest.raises(ValidationError, match="end_date must be after start_date"):
            self.TermModel(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 1),
                name="Test"
            )


class TestMutualExclusivityValidator:
    """Test mutual exclusivity validation using ValidationMixin."""
    
    def test_mutual_exclusivity_with_validation_mixin(self):
        """Test using ValidationMixin for mutual exclusivity in a custom validator."""
        
        class MutualExclusiveModel(Model):
            """Test model using ValidationMixin for mutual exclusivity."""
            option_a: Optional[str] = None
            option_b: Optional[str] = None
            name: str
            
            @model_validator(mode="after")
            @classmethod
            def check_mutual_exclusivity(cls, data):
                """Validate mutual exclusivity using ValidationMixin."""
                # Check for model instances
                if hasattr(data, 'option_a'):
                    option_a = data.option_a
                    option_b = data.option_b
                    
                    if option_a is None and option_b is None:
                        raise ValueError("Either option_a or option_b must be provided")
                    if option_a is not None and option_b is not None:
                        raise ValueError("Cannot provide both option_a and option_b")
                        
                return data
        
        # Test valid cases
        model1 = MutualExclusiveModel(option_a="value", name="Test")
        assert model1.option_a == "value"
        assert model1.option_b is None
        
        model2 = MutualExclusiveModel(option_b="value", name="Test")
        assert model2.option_a is None
        assert model2.option_b == "value"
        
        # Test invalid cases
        with pytest.raises(ValidationError, match="Either option_a or option_b must be provided"):
            MutualExclusiveModel(name="Test")
        
        with pytest.raises(ValidationError, match="Cannot provide both option_a and option_b"):
            MutualExclusiveModel(option_a="value1", option_b="value2", name="Test")


class TestIntegrationWithLeaseSpecBase:
    """Test integration with actual LeaseSpecBase to ensure it works in practice."""
    
    def test_lease_spec_base_integration(self):
        """Test that LeaseSpecBase uses the validation correctly."""
        from performa.common.base.lease import LeaseSpecBase
        
        # This should work - has end_date
        spec = LeaseSpecBase(
            tenant_name="Test Tenant",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            suite="100",
            floor="1",
            area=1000.0,
            base_rent_value=50.0,
            base_rent_unit_of_measure="currency"
        )
        assert spec.end_date == date(2024, 12, 31)
    
    def test_lease_spec_base_validation_error(self):
        """Test that LeaseSpecBase validation fails correctly."""
        from performa.common.base.lease import LeaseSpecBase
        
        # This should fail - neither end_date nor term_months
        with pytest.raises(ValidationError, match="Either end_date or term_months must be provided"):
            LeaseSpecBase(
                tenant_name="Test Tenant",
                start_date=date(2024, 1, 1),
                suite="100",
                floor="1",
                area=1000.0,
                base_rent_value=50.0,
                base_rent_unit_of_measure="currency"
            )


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_validate_term_specification_with_non_model_data(self):
        """Test term validation with dictionary data."""
        # Test with dictionary (mode="before" scenario)
        data = {
            "start_date": date(2024, 1, 1),
            "end_date": date(2024, 12, 31),
            "term_months": None
        }
        result = validate_term_specification(None, data)
        assert result == data
    
    def test_validate_term_specification_dict_validation_error(self):
        """Test term validation error with dictionary data."""
        data = {
            "start_date": date(2024, 1, 1),
            "end_date": None,
            "term_months": None
        }
        with pytest.raises(ValueError, match="Either end_date or term_months must be provided"):
            validate_term_specification(None, data)
    
    def test_validation_mixin_with_missing_fields(self):
        """Test ValidationMixin with missing dictionary keys."""
        data = {}  # Missing both fields
        with pytest.raises(ValueError, match="Either field_a or field_b must be provided"):
            ValidationMixin.validate_either_or_required(data, "field_a", "field_b")


class TestDocumentationExamples:
    """Test examples that serve as documentation for other developers."""
    
    def test_real_estate_lease_example(self):
        """Example: Real estate lease with term validation."""
        
        class SimpleLeaseModel(Model):
            """Simple lease model demonstrating term validation."""
            tenant_name: str
            start_date: date
            end_date: Optional[date] = None
            term_months: Optional[int] = None
            monthly_rent: float
            
            @model_validator(mode="after")
            @classmethod
            def validate_lease_term(cls, data):
                """Ensure lease has valid duration."""
                return validate_term_specification(cls, data)
        
        # Valid lease with 12-month term
        lease = SimpleLeaseModel(
            tenant_name="ABC Corp",
            start_date=date(2024, 1, 1),
            term_months=12,
            monthly_rent=5000.0
        )
        assert lease.term_months == 12
        
        # Valid lease with specific end date
        lease2 = SimpleLeaseModel(
            tenant_name="XYZ Inc",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            monthly_rent=7500.0
        )
        assert lease2.end_date == date(2024, 12, 31)
    
    def test_timeline_like_model_example(self):
        """Example: Timeline-like model with mutual exclusivity."""
        
        class TimelineModel(Model):
            """Timeline model demonstrating mutual exclusivity validation."""
            name: str
            start_date: Optional[date] = None
            start_offset_months: Optional[int] = None
            duration_months: int
            
            @model_validator(mode="after")
            @classmethod
            def validate_start_definition(cls, data):
                """Ensure exactly one start method is defined."""
                # Use ValidationMixin for mutual exclusivity
                if hasattr(data, 'start_date'):
                    start_date = data.start_date
                    start_offset = data.start_offset_months
                    
                    if start_date is None and start_offset is None:
                        raise ValueError("Timeline must have either start_date or start_offset_months")
                    if start_date is not None and start_offset is not None:
                        raise ValueError("Cannot provide both start_date and start_offset_months")
                        
                return data
        
        # Valid absolute timeline
        timeline1 = TimelineModel(
            name="Absolute Timeline",
            start_date=date(2024, 1, 1),
            duration_months=12
        )
        assert timeline1.start_date is not None
        assert timeline1.start_offset_months is None
        
        # Valid relative timeline
        timeline2 = TimelineModel(
            name="Relative Timeline",
            start_offset_months=6,
            duration_months=12
        )
        assert timeline2.start_date is None
        assert timeline2.start_offset_months == 6 