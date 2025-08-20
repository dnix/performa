# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Development Disposition Unit Tests

Unit tests for the DispositionCashFlow class that handles development project
exit strategies and disposition proceeds.

Test Coverage:
1. DispositionCashFlow instantiation with various value types
2. compute_cf method with different scenarios and edge cases
3. Cash flow timing and magnitude validation
4. Error handling and edge cases
5. Integration with AnalysisContext
6. Timeline compatibility and validation
"""

from datetime import date

import pandas as pd
import pytest
from pydantic import ValidationError

from performa.analysis import AnalysisContext
from performa.core.ledger import LedgerBuilder, LedgerGenerationSettings
from performa.core.primitives import (
    CashFlowModel,
    FrequencyEnum,
    GlobalSettings,
    Timeline,
    UnleveredAggregateLineKey,
)
from performa.development.disposition import DispositionCashFlow


@pytest.fixture
def sample_timeline() -> Timeline:
    """Standard timeline for testing."""
    return Timeline(start_date=date(2024, 1, 1), duration_months=12)


@pytest.fixture
def single_period_timeline() -> Timeline:
    """Single period timeline for disposition testing."""
    return Timeline(start_date=date(2024, 1, 1), duration_months=1)


@pytest.fixture
def empty_timeline() -> Timeline:
    """Empty timeline edge case."""
    return Timeline(start_date=date(2024, 1, 1), duration_months=0)


@pytest.fixture  
def sample_context(sample_timeline: Timeline) -> AnalysisContext:
    """Standard analysis context for testing."""
    ledger_builder = LedgerBuilder(settings=LedgerGenerationSettings())
    return AnalysisContext(
        timeline=sample_timeline, 
        settings=GlobalSettings(), 
        property_data=None,
        ledger_builder=ledger_builder
    )


class TestDispositionCashFlowInstantiation:
    """Test DispositionCashFlow instantiation with various parameters."""

    def test_basic_instantiation(self, sample_timeline: Timeline):
        """Test basic instantiation with required parameters."""
        disposition = DispositionCashFlow(
            name="Project Sale",
            category="Disposition",
            subcategory="Sale Proceeds",
            timeline=sample_timeline,
            value=1000000.0,
        )

        assert disposition.name == "Project Sale"
        assert disposition.category == "Disposition"
        assert disposition.subcategory == "Sale Proceeds"
        assert disposition.value == 1000000.0
        assert disposition.reference is None  # Default for currency amounts
        assert disposition.timeline == sample_timeline
        assert disposition.frequency == FrequencyEnum.MONTHLY  # Default

    def test_instantiation_with_optional_fields(self, sample_timeline: Timeline):
        """Test instantiation with all optional fields."""
        disposition = DispositionCashFlow(
            name="Luxury Tower Sale",
            category="Disposition",
            subcategory="Sale Proceeds",
            description="Sale of luxury residential tower",
            account="4100-Disposition",
            timeline=sample_timeline,
            value=25000000.0,
            frequency=FrequencyEnum.ANNUAL,
            reference=UnleveredAggregateLineKey.NET_OPERATING_INCOME,
        )

        assert disposition.description == "Sale of luxury residential tower"
        assert disposition.account == "4100-Disposition"
        assert disposition.frequency == FrequencyEnum.ANNUAL
        assert disposition.reference == UnleveredAggregateLineKey.NET_OPERATING_INCOME

    def test_inherits_from_cashflowmodel(self, sample_timeline: Timeline):
        """Test that DispositionCashFlow properly inherits from CashFlowModel."""
        disposition = DispositionCashFlow(
            name="Test Sale",
            category="Disposition",
            subcategory="Proceeds",
            timeline=sample_timeline,
            value=500000.0,
        )

        assert isinstance(disposition, CashFlowModel)
        assert hasattr(disposition, "compute_cf")
        assert hasattr(disposition, "uid")
        assert hasattr(disposition, "settings")

    def test_validation_errors(self, sample_timeline: Timeline):
        """Test validation errors for invalid parameters."""
        # Test missing required fields
        with pytest.raises(ValidationError):
            DispositionCashFlow(
                name="Test",
                # Missing category
                subcategory="Proceeds",
                timeline=sample_timeline,
                value=100000.0,
            )

        # Test negative value (should be rejected by PositiveFloat)
        with pytest.raises(ValidationError):
            DispositionCashFlow(
                name="Test Sale",
                category="Disposition",
                subcategory="Proceeds",
                timeline=sample_timeline,
                value=-100000.0,  # Negative value
            )


class TestDispositionCashFlowComputation:
    """Test the compute_cf method with various scenarios."""

    def test_compute_cf_basic_scenario(
        self, sample_timeline: Timeline, sample_context: AnalysisContext
    ):
        """Test basic cash flow computation."""
        disposition = DispositionCashFlow(
            name="Office Sale",
            category="Disposition",
            subcategory="Proceeds",
            timeline=sample_timeline,
            value=2000000.0,
        )

        cash_flow = disposition.compute_cf(sample_context)

        # Should be a pandas Series
        assert isinstance(cash_flow, pd.Series)

        # Should have same length as timeline
        assert len(cash_flow) == len(sample_timeline.period_index)

        # Should be indexed by the timeline period index
        pd.testing.assert_index_equal(cash_flow.index, sample_timeline.period_index)

        # First period should have the full value
        assert cash_flow.iloc[0] == 2000000.0

        # All other periods should be zero
        assert (cash_flow.iloc[1:] == 0.0).all()

        # Total should equal the input value
        assert cash_flow.sum() == 2000000.0

    def test_compute_cf_single_period(self, single_period_timeline: Timeline):
        """Test computation with single period timeline."""
        ledger_builder = LedgerBuilder(settings=LedgerGenerationSettings())
        context = AnalysisContext(
            timeline=single_period_timeline,
            settings=GlobalSettings(),
            property_data=None,
            ledger_builder=ledger_builder
        )

        disposition = DispositionCashFlow(
            name="Quick Sale",
            category="Disposition",
            subcategory="Proceeds",
            timeline=single_period_timeline,
            value=750000.0,
        )

        cash_flow = disposition.compute_cf(context)

        assert len(cash_flow) == 1
        assert cash_flow.iloc[0] == 750000.0

    def test_compute_cf_empty_timeline(self, empty_timeline: Timeline):
        """Test computation with empty timeline (edge case)."""
        ledger_builder = LedgerBuilder(settings=LedgerGenerationSettings())
        context = AnalysisContext(
            timeline=empty_timeline, 
            settings=GlobalSettings(), 
            property_data=None,
            ledger_builder=ledger_builder
        )

        disposition = DispositionCashFlow(
            name="No Sale",
            category="Disposition",
            subcategory="Proceeds",
            timeline=empty_timeline,
            value=1000000.0,
        )

        cash_flow = disposition.compute_cf(context)

        # Should return empty series for empty timeline
        assert isinstance(cash_flow, pd.Series)
        assert len(cash_flow) == 0
        assert cash_flow.sum() == 0.0

    def test_compute_cf_zero_value(
        self, sample_timeline: Timeline, sample_context: AnalysisContext
    ):
        """Test computation with zero disposition value."""
        disposition = DispositionCashFlow(
            name="No Sale Proceeds",
            category="Disposition",
            subcategory="Proceeds",
            timeline=sample_timeline,
            value=0.0,
        )

        cash_flow = disposition.compute_cf(sample_context)

        # All values should be zero
        assert (cash_flow == 0.0).all()
        assert cash_flow.sum() == 0.0

    def test_compute_cf_large_value(
        self, sample_timeline: Timeline, sample_context: AnalysisContext
    ):
        """Test computation with large disposition value."""
        large_value = 100_000_000.0  # $100M

        disposition = DispositionCashFlow(
            name="Mega Sale",
            category="Disposition",
            subcategory="Proceeds",
            timeline=sample_timeline,
            value=large_value,
        )

        cash_flow = disposition.compute_cf(sample_context)

        assert cash_flow.iloc[0] == large_value
        assert cash_flow.sum() == large_value

        # Verify precision is maintained
        assert abs(cash_flow.iloc[0] - large_value) < 1e-6


class TestDispositionCashFlowIntegration:
    """Test integration with the broader system."""

    def test_context_parameter_handling(self, sample_timeline: Timeline):
        """Test that compute_cf properly handles context parameter."""
        disposition = DispositionCashFlow(
            name="Context Test",
            category="Disposition",
            subcategory="Proceeds",
            timeline=sample_timeline,
            value=500000.0,
        )

        # Test with None context (should still work)
        cash_flow = disposition.compute_cf(None)
        assert isinstance(cash_flow, pd.Series)
        assert cash_flow.iloc[0] == 500000.0

        # Test with proper context
        ledger_builder = LedgerBuilder(settings=LedgerGenerationSettings())
        context = AnalysisContext(
            timeline=sample_timeline, 
            settings=GlobalSettings(), 
            property_data=None,
            ledger_builder=ledger_builder
        )
        cash_flow_with_context = disposition.compute_cf(context)

        # Results should be the same regardless of context
        pd.testing.assert_series_equal(cash_flow, cash_flow_with_context)

    def test_timeline_period_index_compatibility(
        self, sample_timeline: Timeline, sample_context: AnalysisContext
    ):
        """Test that computed cash flow index matches timeline period index."""
        disposition = DispositionCashFlow(
            name="Index Test",
            category="Disposition",
            subcategory="Proceeds",
            timeline=sample_timeline,
            value=300000.0,
        )

        cash_flow = disposition.compute_cf(sample_context)

        # Index should exactly match timeline period index
        pd.testing.assert_index_equal(cash_flow.index, sample_timeline.period_index)

        # Should be able to align with timeline-based operations
        timeline_series = pd.Series(1.0, index=sample_timeline.period_index)
        combined = cash_flow + timeline_series
        assert len(combined) == len(sample_timeline.period_index)
        assert combined.iloc[0] == 300001.0  # 300000 + 1

    def test_uid_uniqueness(self, sample_timeline: Timeline):
        """Test that each instance gets a unique uid."""
        disposition1 = DispositionCashFlow(
            name="Sale 1",
            category="Disposition",
            subcategory="Proceeds",
            timeline=sample_timeline,
            value=1000000.0,
        )

        disposition2 = DispositionCashFlow(
            name="Sale 2",
            category="Disposition",
            subcategory="Proceeds",
            timeline=sample_timeline,
            value=2000000.0,
        )

        assert disposition1.uid != disposition2.uid
        assert isinstance(disposition1.uid, type(disposition2.uid))  # Same type


class TestDispositionCashFlowEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_long_timeline(self, sample_context: AnalysisContext):
        """Test with very long timeline (edge case)."""
        long_timeline = Timeline(
            start_date=date(2024, 1, 1), duration_months=600
        )  # 50 years

        disposition = DispositionCashFlow(
            name="Long Term Sale",
            category="Disposition",
            subcategory="Proceeds",
            timeline=long_timeline,
            value=5000000.0,
        )

        cash_flow = disposition.compute_cf(sample_context)

        assert len(cash_flow) == 600
        assert cash_flow.iloc[0] == 5000000.0
        assert (cash_flow.iloc[1:] == 0.0).all()
        assert cash_flow.sum() == 5000000.0

    def test_fractional_values(
        self, sample_timeline: Timeline, sample_context: AnalysisContext
    ):
        """Test with fractional disposition values."""
        disposition = DispositionCashFlow(
            name="Fractional Sale",
            category="Disposition",
            subcategory="Proceeds",
            timeline=sample_timeline,
            value=1234567.89,  # Fractional value
        )

        cash_flow = disposition.compute_cf(sample_context)

        # Should preserve fractional precision
        assert abs(cash_flow.iloc[0] - 1234567.89) < 1e-10
        assert abs(cash_flow.sum() - 1234567.89) < 1e-10


class TestDispositionDocumentationExamples:
    """Test examples from class documentation."""

    def test_docstring_example(
        self, sample_timeline: Timeline, sample_context: AnalysisContext
    ):
        """Test the example from the class docstring."""
        # This matches the example in the DispositionCashFlow docstring
        disposition = DispositionCashFlow(
            name="Project Sale",
            timeline=sample_timeline,  # Using fixture instead of sale_timeline
            value=10000000.0,  # net_proceeds equivalent
            category="Disposition",
            subcategory="Sale Proceeds",  # Added required field
            frequency=FrequencyEnum.MONTHLY,  # Added for completeness
        )

        # Verify it works as documented
        assert disposition.name == "Project Sale"
        assert disposition.category == "Disposition"
        assert disposition.subcategory == "Sale Proceeds"

        # Test cash flow computation
        cash_flow = disposition.compute_cf(sample_context)
        assert cash_flow.iloc[0] == 10000000.0
        assert (cash_flow.iloc[1:] == 0.0).all()
