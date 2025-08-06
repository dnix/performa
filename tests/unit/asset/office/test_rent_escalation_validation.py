# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

import unittest
from datetime import date

import pandas as pd
from pydantic import ValidationError

from performa.asset.office.rent_escalation import OfficeRentEscalation
from performa.core.primitives import PropertyAttributeKey
from performa.core.primitives.growth_rates import (
    FixedGrowthRate,
    PercentageGrowthRate,
)


class TestRentEscalationValidation(unittest.TestCase):
    """
    Unit tests for validation and error cases in the unified rate API.

    Tests cover:
    - Rate type consistency validation
    - Property accessor methods
    - Invalid rate combinations
    - Malformed rate objects
    - Serialization/deserialization
    - Edge cases and error conditions
    """

    def test_percentage_escalation_with_valid_float_rate(self):
        """Test that percentage escalation accepts valid float rates (0-1)."""
        # Should accept rates between 0 and 1
        valid_rates = [0.0, 0.03, 0.5, 1.0]

        for rate in valid_rates:
            escalation = OfficeRentEscalation(
                type="percentage",
                rate=rate,
                is_relative=True,
                start_date=date(2024, 1, 1),
            )
            self.assertEqual(escalation.rate, rate)
            self.assertEqual(escalation.type, "percentage")

    def test_percentage_escalation_with_invalid_float_rate(self):
        """Test that percentage escalation rejects invalid float rates."""
        invalid_rates = [-0.1, 1.1, 2.0, -1.0]

        for rate in invalid_rates:
            with self.assertRaises(ValidationError) as cm:
                OfficeRentEscalation(
                    type="percentage",
                    rate=rate,
                    is_relative=True,
                    start_date=date(2024, 1, 1),
                )
            # Check for either our custom validation message or Pydantic's built-in message
            error_text = str(cm.exception)
            self.assertTrue(
                "between 0 and 1" in error_text
                or "greater than or equal to 0" in error_text
                or "less than or equal to 1" in error_text,
                f"Unexpected error message: {error_text}",
            )

    def test_fixed_escalation_with_valid_float_rate(self):
        """Test that fixed escalation accepts valid positive float rates."""
        valid_rates = [0.01, 1.0, 10.0, 1000.0]

        for rate in valid_rates:
            escalation = OfficeRentEscalation(
                type="fixed",
                rate=rate,
                reference=PropertyAttributeKey.NET_RENTABLE_AREA,
                is_relative=False,
                start_date=date(2024, 1, 1),
            )
            self.assertEqual(escalation.rate, rate)
            self.assertEqual(escalation.type, "fixed")

    def test_fixed_escalation_with_invalid_float_rate(self):
        """Test that fixed escalation rejects negative float rates."""
        # Note: PositiveFloat allows 0.0, so we only test negative values
        invalid_rates = [-1.0, -10.0]

        for rate in invalid_rates:
            with self.assertRaises(ValidationError) as cm:
                OfficeRentEscalation(
                    type="fixed",
                    rate=rate,
                    reference=PropertyAttributeKey.NET_RENTABLE_AREA,
                    is_relative=False,
                    start_date=date(2024, 1, 1),
                )
            # Check for either our custom validation message or Pydantic's built-in message
            error_text = str(cm.exception)
            self.assertTrue(
                "must be positive" in error_text
                or "greater than or equal to 0" in error_text,
                f"Unexpected error message: {error_text}",
            )

    def test_percentage_escalation_with_wrong_rate_object_type(self):
        """Test that percentage escalation rejects FixedGrowthRate objects."""
        fixed_rate = FixedGrowthRate(name="Wrong Type", value=1.5)

        with self.assertRaises(ValidationError) as cm:
            OfficeRentEscalation(
                type="percentage",
                rate=fixed_rate,
                is_relative=True,
                start_date=date(2024, 1, 1),
            )
        self.assertIn(
            "Cannot use FixedGrowthRate with percentage escalation", str(cm.exception)
        )

    def test_fixed_escalation_with_wrong_rate_object_type(self):
        """Test that fixed escalation rejects PercentageGrowthRate objects."""
        percentage_rate = PercentageGrowthRate(name="Wrong Type", value=0.03)

        with self.assertRaises(ValidationError) as cm:
            OfficeRentEscalation(
                type="fixed",
                rate=percentage_rate,
                reference=PropertyAttributeKey.NET_RENTABLE_AREA,
                is_relative=False,
                start_date=date(2024, 1, 1),
            )
        self.assertIn(
            "Cannot use PercentageGrowthRate with fixed escalation", str(cm.exception)
        )

    def test_percentage_escalation_with_correct_rate_object_type(self):
        """Test that percentage escalation accepts PercentageGrowthRate objects."""
        percentage_rate = PercentageGrowthRate(name="Correct Type", value=0.03)

        escalation = OfficeRentEscalation(
            type="percentage",
            rate=percentage_rate,
            is_relative=True,
            start_date=date(2024, 1, 1),
        )
        self.assertEqual(escalation.rate, percentage_rate)
        self.assertEqual(escalation.type, "percentage")

    def test_fixed_escalation_with_correct_rate_object_type(self):
        """Test that fixed escalation accepts FixedGrowthRate objects."""
        fixed_rate = FixedGrowthRate(name="Correct Type", value=1.5)

        escalation = OfficeRentEscalation(
            type="fixed",
            rate=fixed_rate,
            reference=PropertyAttributeKey.NET_RENTABLE_AREA,
            is_relative=False,
            start_date=date(2024, 1, 1),
        )
        self.assertEqual(escalation.rate, fixed_rate)
        self.assertEqual(escalation.type, "fixed")

    def test_uses_rate_object_property_with_float(self):
        """Test uses_rate_object property returns False for float rates."""
        escalation = OfficeRentEscalation(
            type="percentage",
            rate=0.03,
            is_relative=True,
            start_date=date(2024, 1, 1),
        )
        self.assertFalse(escalation.uses_rate_object)

    def test_uses_rate_object_property_with_rate_object(self):
        """Test uses_rate_object property returns True for rate objects."""
        percentage_rate = PercentageGrowthRate(name="Test Rate", value=0.03)
        escalation = OfficeRentEscalation(
            type="percentage",
            rate=percentage_rate,
            is_relative=True,
            start_date=date(2024, 1, 1),
        )
        self.assertTrue(escalation.uses_rate_object)

    def test_rate_object_property_with_float(self):
        """Test rate_object property returns None for float rates."""
        escalation = OfficeRentEscalation(
            type="percentage",
            rate=0.03,
            is_relative=True,
            start_date=date(2024, 1, 1),
        )
        self.assertIsNone(escalation.rate_object)

    def test_rate_object_property_with_rate_object(self):
        """Test rate_object property returns the rate object for rate objects."""
        percentage_rate = PercentageGrowthRate(name="Test Rate", value=0.03)
        escalation = OfficeRentEscalation(
            type="percentage",
            rate=percentage_rate,
            is_relative=True,
            start_date=date(2024, 1, 1),
        )
        self.assertEqual(escalation.rate_object, percentage_rate)

    def test_rate_value_property_with_float(self):
        """Test rate_value property returns the float value for simple rates."""
        escalation = OfficeRentEscalation(
            type="percentage",
            rate=0.03,
            is_relative=True,
            start_date=date(2024, 1, 1),
        )
        self.assertEqual(escalation.rate_value, 0.03)

    def test_rate_value_property_with_rate_object_raises_error(self):
        """Test rate_value property raises error for rate objects."""
        percentage_rate = PercentageGrowthRate(name="Test Rate", value=0.03)
        escalation = OfficeRentEscalation(
            type="percentage",
            rate=percentage_rate,
            is_relative=True,
            start_date=date(2024, 1, 1),
        )

        with self.assertRaises(ValueError) as cm:
            _ = escalation.rate_value
        self.assertIn(
            "Cannot get simple rate value from rate object", str(cm.exception)
        )

    def test_fixed_rate_object_with_time_series(self):
        """Test FixedGrowthRate with pandas Series for time-varying dollar amounts."""
        # Create time-based fixed rates (different dollar amounts by period)
        rate_series = pd.Series({
            pd.Period("2025-01", freq="M"): 1.0,  # $1/SF for Year 2
            pd.Period("2025-02", freq="M"): 1.0,
            pd.Period("2025-03", freq="M"): 1.0,
            pd.Period("2025-04", freq="M"): 1.0,
            pd.Period("2025-05", freq="M"): 1.0,
            pd.Period("2025-06", freq="M"): 1.0,
            pd.Period("2025-07", freq="M"): 1.0,
            pd.Period("2025-08", freq="M"): 1.0,
            pd.Period("2025-09", freq="M"): 1.0,
            pd.Period("2025-10", freq="M"): 1.0,
            pd.Period("2025-11", freq="M"): 1.0,
            pd.Period("2025-12", freq="M"): 1.0,
            pd.Period("2026-01", freq="M"): 2.0,  # $2/SF for Year 3
            pd.Period("2026-02", freq="M"): 2.0,
            pd.Period("2026-03", freq="M"): 2.0,
            pd.Period("2026-04", freq="M"): 2.0,
            pd.Period("2026-05", freq="M"): 2.0,
            pd.Period("2026-06", freq="M"): 2.0,
            pd.Period("2026-07", freq="M"): 2.0,
            pd.Period("2026-08", freq="M"): 2.0,
            pd.Period("2026-09", freq="M"): 2.0,
            pd.Period("2026-10", freq="M"): 2.0,
            pd.Period("2026-11", freq="M"): 2.0,
            pd.Period("2026-12", freq="M"): 2.0,
        })

        fixed_rate = FixedGrowthRate(name="Variable Fixed Growth", value=rate_series)

        escalation = OfficeRentEscalation(
            type="fixed",
            rate=fixed_rate,
            reference=PropertyAttributeKey.NET_RENTABLE_AREA,
            is_relative=False,
            start_date=date(2025, 1, 1),
            recurring=True,
            frequency_months=12,
        )

        self.assertEqual(escalation.rate, fixed_rate)
        self.assertTrue(escalation.uses_rate_object)

    def test_fixed_rate_object_with_date_dict(self):
        """Test FixedGrowthRate with date dictionary for time-varying dollar amounts."""
        rate_dict = {
            date(2025, 1, 1): 1.5,  # $1.50/SF for Year 2
            date(2026, 1, 1): 2.5,  # $2.50/SF for Year 3
        }

        fixed_rate = FixedGrowthRate(name="Date-based Fixed Growth", value=rate_dict)

        escalation = OfficeRentEscalation(
            type="fixed",
            rate=fixed_rate,
            reference=PropertyAttributeKey.NET_RENTABLE_AREA,
            is_relative=False,
            start_date=date(2025, 1, 1),
            recurring=True,
            frequency_months=12,
        )

        self.assertEqual(escalation.rate, fixed_rate)
        self.assertTrue(escalation.uses_rate_object)

    def test_model_serialization_with_float_rate(self):
        """Test that escalation with float rate serializes correctly."""
        escalation = OfficeRentEscalation(
            type="percentage",
            rate=0.03,
            is_relative=True,
            start_date=date(2024, 1, 1),
            recurring=True,
            frequency_months=12,
        )

        # Serialize to dict
        data = escalation.model_dump()
        self.assertEqual(data["type"], "percentage")
        self.assertEqual(data["rate"], 0.03)

        # Deserialize from dict
        recreated = OfficeRentEscalation.model_validate(data)
        self.assertEqual(recreated.type, escalation.type)
        self.assertEqual(recreated.rate, escalation.rate)
        self.assertEqual(recreated.is_relative, escalation.is_relative)

    def test_model_serialization_with_rate_object(self):
        """Test that escalation with rate object serializes correctly."""
        percentage_rate = PercentageGrowthRate(name="Test Growth", value=0.03)
        escalation = OfficeRentEscalation(
            type="percentage",
            rate=percentage_rate,
            is_relative=True,
            start_date=date(2024, 1, 1),
            recurring=True,
            frequency_months=12,
        )

        # Serialize to dict
        data = escalation.model_dump()
        self.assertEqual(data["type"], "percentage")
        self.assertIsInstance(data["rate"], dict)
        self.assertEqual(data["rate"]["name"], "Test Growth")
        self.assertEqual(data["rate"]["value"], 0.03)

        # Deserialize from dict
        recreated = OfficeRentEscalation.model_validate(data)
        self.assertEqual(recreated.type, escalation.type)
        self.assertEqual(recreated.rate.name, percentage_rate.name)
        self.assertEqual(recreated.rate.value, percentage_rate.value)

    def test_invalid_percentage_growth_rate_values(self):
        """Test that PercentageGrowthRate rejects invalid values."""
        # Test invalid float
        with self.assertRaises(ValidationError):
            PercentageGrowthRate(name="Invalid", value=1.5)  # > 1

        with self.assertRaises(ValidationError):
            PercentageGrowthRate(name="Invalid", value=-0.1)  # < 0

        # Test invalid series
        invalid_series = pd.Series([0.5, 1.5, 0.3])  # Contains value > 1
        with self.assertRaises(ValidationError):
            PercentageGrowthRate(name="Invalid", value=invalid_series)

        # Test invalid dict
        invalid_dict = {date(2024, 1, 1): 1.5}  # Value > 1
        with self.assertRaises(ValidationError):
            PercentageGrowthRate(name="Invalid", value=invalid_dict)

    def test_invalid_fixed_growth_rate_values(self):
        """Test that FixedGrowthRate rejects invalid values."""
        # Test invalid float - only negative values are invalid (0.0 is allowed)
        with self.assertRaises(ValidationError):
            FixedGrowthRate(name="Invalid", value=-1.0)  # Negative

        # Test invalid series
        invalid_series = pd.Series([1.0, -0.1, 2.0])  # Contains negative value
        with self.assertRaises(ValidationError):
            FixedGrowthRate(name="Invalid", value=invalid_series)

        # Test invalid dict
        invalid_dict = {date(2024, 1, 1): -1.0}  # Negative value
        with self.assertRaises(ValidationError):
            FixedGrowthRate(name="Invalid", value=invalid_dict)

        # Test that 0.0 is actually valid (consistent with PositiveFloat)
        FixedGrowthRate(name="Valid", value=0.0)  # Should not raise

    def test_malformed_rate_object_keys(self):
        """Test that rate objects reject malformed dictionary keys."""
        # Integer keys should be rejected
        invalid_dict = {123: 1.5}  # Integer instead of date
        with self.assertRaises(ValidationError):
            FixedGrowthRate(name="Invalid", value=invalid_dict)

        # Test another invalid key type
        invalid_dict = {None: 0.03}  # None instead of date
        with self.assertRaises(ValidationError):
            PercentageGrowthRate(name="Invalid", value=invalid_dict)


if __name__ == "__main__":
    unittest.main()
