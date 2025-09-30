# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Comprehensive tests for the ledger-driven ValuationEngine.

This test suite covers the new architecture where ValuationEngine:
1. Queries NOI directly from the ledger (not from UnleveredAnalysisResult)
2. Calculates property values using settings-driven approaches
3. Updates DealContext with computed values (void return pattern)
4. Integrates with ledger-based deal orchestration workflow

Test Philosophy:
- Test actual methods that exist in current architecture
- Use realistic deal scenarios with proper ledger setup
- Test context updates and void return patterns
- Cover edge cases and error scenarios systematically
- Maintain institutional modeling standards
"""

from datetime import date
from unittest.mock import Mock
from uuid import uuid4

import pandas as pd
import pytest

from performa.core.ledger import Ledger
from performa.core.ledger.records import SeriesMetadata
from performa.core.primitives import (
    CashFlowCategoryEnum,
    GlobalSettings,
    RevenueSubcategoryEnum,
    Timeline,
)
from performa.core.primitives.settings import ValuationSettings
from performa.deal.analysis.valuation import ValuationEngine
from performa.deal.deal import Deal
from performa.deal.orchestrator import DealContext


@pytest.fixture
def sample_timeline() -> Timeline:
    """Standard 24-month timeline for valuation testing."""
    return Timeline(start_date=date(2024, 1, 1), duration_months=24)


@pytest.fixture
def sample_settings() -> GlobalSettings:
    """Standard settings with comprehensive valuation parameters."""
    valuation_settings = ValuationSettings(
        exit_cap_rate=0.06,  # 6% exit cap rate
        costs_of_sale_percentage=0.02,  # 2% transaction costs
        discount_rate=0.08,  # 8% discount rate
    )
    return GlobalSettings(valuation=valuation_settings)


@pytest.fixture
def sample_deal() -> Mock:
    """Mock deal with basic structure for valuation testing."""
    deal = Mock(spec=Deal)
    deal.uid = uuid4()
    deal.name = "Test Valuation Deal"
    # Set up deal attributes for ValuationEngine tests
    deal.acquisition = None  # No acquisition price - use NOI-based valuation
    deal.exit_valuation = None  # No exit valuation - use default cap rate

    # Add asset mock for non-cash valuation recording
    deal.asset = Mock()
    deal.asset.uid = uuid4()

    return deal


@pytest.fixture
def sample_ledger_with_noi(sample_timeline: Timeline) -> Ledger:
    """Ledger populated with realistic NOI progression."""
    ledger = Ledger()

    # Add realistic NOI progression - $80k/month growing to $85k/month
    noi_values = [80000.0] * 12 + [85000.0] * 12  # Growth in year 2
    noi_series = pd.Series(noi_values, index=sample_timeline.period_index)

    # Create metadata for the NOI series
    noi_metadata = SeriesMetadata(
        category=CashFlowCategoryEnum.REVENUE,  # NOI is net revenue after expenses
        subcategory=RevenueSubcategoryEnum.LEASE,  # NOI comes from lease revenue
        item_name="Net Operating Income",
        source_id=uuid4(),
        asset_id=uuid4(),
        pass_num=1,
    )

    # Add the NOI series to the ledger
    ledger.add_series(noi_series, noi_metadata)

    return ledger


@pytest.fixture
def sample_context(
    sample_timeline: Timeline,
    sample_settings: GlobalSettings,
    sample_deal: Mock,
    sample_ledger_with_noi: Ledger,
) -> DealContext:
    """Standard DealContext with populated ledger for testing."""
    return DealContext(
        timeline=sample_timeline,
        settings=sample_settings,
        ledger=sample_ledger_with_noi,
        deal=sample_deal,
    )


class TestValuationEngineBasics:
    """Test basic ValuationEngine functionality and inheritance."""

    def test_valuation_engine_instantiation(self, sample_context: DealContext):
        """Test that ValuationEngine can be instantiated with DealContext."""
        engine = ValuationEngine(sample_context)

        assert engine is not None
        assert engine.context is sample_context
        assert engine.deal is sample_context.deal
        assert engine.timeline is sample_context.timeline
        assert engine.settings is sample_context.settings
        assert engine.ledger is sample_context.ledger

    def test_valuation_engine_has_required_methods(self, sample_context: DealContext):
        """Test that ValuationEngine has all required methods from new architecture."""
        engine = ValuationEngine(sample_context)

        # Main public interface (void return)
        assert hasattr(engine, "process")
        assert callable(getattr(engine, "process"))

        # Should have queries from base class for ledger access
        assert hasattr(engine, "queries")
        assert callable(getattr(engine.queries, "noi"))

    def test_valuation_engine_inherits_analysis_specialist_properly(
        self, sample_context: DealContext
    ):
        """Test inheritance from AnalysisSpecialist base class."""
        engine = ValuationEngine(sample_context)

        # Should have queries from base class for ledger access
        assert hasattr(engine, "queries")
        assert engine.queries is not None

        # Should have property access patterns from base
        assert engine.deal is sample_context.deal
        assert engine.timeline is sample_context.timeline
        assert engine.settings is sample_context.settings
        assert engine.ledger is sample_context.ledger


class TestNOIExtractionViaQueries:
    """Test NOI extraction via LedgerQueries (proper ledger-driven architecture)."""

    def test_noi_extraction_from_populated_ledger(self, sample_context: DealContext):
        """Test NOI extraction from ledger with realistic data via queries."""
        engine = ValuationEngine(sample_context)

        # Test the PUBLIC interface - queries.noi()
        noi_series = engine.queries.noi()

        assert isinstance(noi_series, pd.Series)
        # Note: LedgerQueries.noi() returns actual dates, not reindexed to timeline
        assert len(noi_series) == 24  # 24 months of data

        # First 12 months should be $80k
        assert (noi_series.iloc[:12] == 80000.0).all()

        # Second 12 months should be $85k (growth scenario)
        assert (noi_series.iloc[12:] == 85000.0).all()

    def test_noi_extraction_from_empty_ledger(
        self,
        sample_timeline: Timeline,
        sample_settings: GlobalSettings,
        sample_deal: Mock,
    ):
        """Test NOI extraction when ledger has no transactions."""
        empty_ledger = Ledger()
        context = DealContext(
            timeline=sample_timeline,
            settings=sample_settings,
            ledger=empty_ledger,
            deal=sample_deal,
        )

        engine = ValuationEngine(context)
        noi_series = engine.queries.noi()

        # Empty ledger should return empty series from queries
        assert isinstance(noi_series, pd.Series)
        assert len(noi_series) == 0  # Empty, not zeros

    def test_process_updates_context_with_noi(self, sample_context: DealContext):
        """Test that process() correctly updates context with NOI series."""
        engine = ValuationEngine(sample_context)

        # Process should query NOI and update context
        engine.process()

        assert hasattr(sample_context, "noi_series")
        assert sample_context.noi_series is not None
        assert isinstance(sample_context.noi_series, pd.Series)

        # Should match the ledger data
        assert len(sample_context.noi_series) == 24
        assert (sample_context.noi_series.iloc[:12] == 80000.0).all()
        assert (sample_context.noi_series.iloc[12:] == 85000.0).all()


class TestPropertyValueCalculation:
    """Test property value calculation methods (translates old extract_property_value_series concepts)."""

    def test_calculate_property_value_with_positive_noi(
        self, sample_context: DealContext
    ):
        """Test property value calculation using NOI and cap rates."""
        engine = ValuationEngine(sample_context)

        # Create sample NOI series
        noi_series = pd.Series(
            [80000.0] * 12 + [85000.0] * 12,  # Growing NOI
            index=sample_context.timeline.period_index,
        )

        property_values = engine._calculate_refi_property_value(noi_series)

        assert isinstance(property_values, pd.Series)
        assert len(property_values) == 24

        # Property values should be positive and time-varying (refi valuation uses LTM methodology)
        assert (property_values > 0).all()

        # Should be time-varying series (refi valuation uses trailing 12-month averages)
        assert (
            property_values.nunique() > 1
        )  # Values change over time due to LTM rolling average

        # LTM methodology: Check month 12 which has full 12-month lookback data
        # At month 12, LTM average = $80k/month for first 12 months
        # Annual NOI = $80k * 12 = $960k, Property value = $960k / 6.5% = ~$14.77M
        month_12_expected_noi = 80000.0 * 12  # First 12 months are all $80k
        month_12_expected_value = month_12_expected_noi / 0.065  # 6.5% refi cap rate
        assert (
            abs(property_values.iloc[11] - month_12_expected_value) < 100000
        )  # Month 12 (index 11)

    def test_calculate_property_value_with_zero_noi(self, sample_context: DealContext):
        """Test property value calculation when NOI is zero (edge case from old test)."""
        engine = ValuationEngine(sample_context)

        # Zero NOI series
        zero_noi_series = pd.Series(
            [0.0] * 24, index=sample_context.timeline.period_index
        )

        property_values = engine._calculate_refi_property_value(zero_noi_series)

        assert isinstance(property_values, pd.Series)
        assert len(property_values) == 24

        # Should fall back to zero values (or minimal values)
        # This tests the same edge case as the old test_extract_property_value_zero_noi
        assert (property_values >= 0).all()  # Should not be negative

    def test_calculate_property_value_with_negative_noi(
        self, sample_context: DealContext
    ):
        """Test property value calculation with negative NOI (operating losses)."""
        engine = ValuationEngine(sample_context)

        # Negative NOI series (operating losses)
        negative_noi_series = pd.Series(
            [-20000.0] * 24,  # $20k monthly losses
            index=sample_context.timeline.period_index,
        )

        property_values = engine._calculate_refi_property_value(negative_noi_series)

        assert isinstance(property_values, pd.Series)
        assert len(property_values) == 24

        # Should handle negative NOI gracefully (may fall back to cost basis or zero)
        # This tests the same concept as old test_extract_property_value_negative_noi
        assert (
            property_values >= 0
        ).all()  # Should not result in negative property values


class TestDispositionProceedsCalculation:
    """Test disposition proceeds calculation (translates old calculate_disposition_proceeds concepts)."""

    def test_calculate_disposition_proceeds_with_exit_valuation(
        self, sample_context: DealContext
    ):
        """Test disposition proceeds when deal has exit valuation."""
        # Mock deal with exit valuation
        sample_context.deal.exit_valuation = Mock()
        sample_context.deal.exit_valuation.compute_cf = Mock()
        sample_context.deal.exit_valuation.cap_rate = 0.065  # Proper numeric cap rate

        # Mock exit valuation to return $3.5M in final period
        disposition_cf = pd.Series(
            [0.0] * 23 + [3500000.0],  # $3.5M disposition in month 24
            index=sample_context.timeline.period_index,
        )
        sample_context.deal.exit_valuation.compute_cf.return_value = disposition_cf

        engine = ValuationEngine(sample_context)

        # Use realistic NOI for calculation
        noi_series = pd.Series(
            [80000.0] * 24, index=sample_context.timeline.period_index
        )

        gross_proceeds = engine._calculate_exit_gross_proceeds(noi_series)

        assert isinstance(gross_proceeds, pd.Series)
        assert len(gross_proceeds) == 24

        # Should have $3.5M in final period
        assert gross_proceeds.iloc[-1] == 3500000.0

        # Should have zero in all other periods
        assert (gross_proceeds.iloc[:-1] == 0.0).all()

    def test_calculate_disposition_proceeds_without_exit_valuation(
        self, sample_context: DealContext
    ):
        """Test disposition proceeds when deal has no exit valuation."""
        # Ensure no exit valuation
        sample_context.deal.exit_valuation = None

        engine = ValuationEngine(sample_context)

        noi_series = pd.Series(
            [80000.0] * 24, index=sample_context.timeline.period_index
        )

        gross_proceeds = engine._calculate_exit_gross_proceeds(noi_series)

        assert isinstance(gross_proceeds, pd.Series)
        assert len(gross_proceeds) == 24

        # Should be all zeros when no exit valuation
        assert (gross_proceeds == 0.0).all()

    def test_calculate_disposition_proceeds_with_error_handling(
        self, sample_context: DealContext
    ):
        """Test disposition proceeds calculation handles errors gracefully."""
        # Mock deal with exit valuation that raises exception
        sample_context.deal.exit_valuation = Mock()
        sample_context.deal.exit_valuation.compute_cf = Mock(
            side_effect=Exception("Exit valuation failed")
        )
        sample_context.deal.exit_valuation.cap_rate = (
            0.06  # Proper numeric cap rate for fallback
        )

        engine = ValuationEngine(sample_context)

        noi_series = pd.Series(
            [80000.0] * 24, index=sample_context.timeline.period_index
        )

        # Should handle exception gracefully and fall back to cap rate calculation
        gross_proceeds = engine._calculate_exit_gross_proceeds(noi_series)

        assert isinstance(gross_proceeds, pd.Series)
        assert len(gross_proceeds) == 24

        # Should fall back to cap rate calculation: $80K monthly × 12 months / 6% = $16M
        expected_value = 80000.0 * 12 / 0.06  # Monthly NOI × 12 / default 6% cap rate
        assert (
            gross_proceeds.iloc[-1] == expected_value
        )  # Final period should have disposition
        assert gross_proceeds.iloc[:-1].sum() == 0.0  # All other periods should be zero


class TestContextUpdatesAndVoidReturn:
    """Test the core new architecture: void return + context updates via process()."""

    def test_process_updates_context_with_computed_values(
        self, sample_context: DealContext
    ):
        """Test that process() correctly updates context with all computed values."""
        # Ensure context starts without valuation data
        assert (
            not hasattr(sample_context, "refi_property_value")
            or sample_context.refi_property_value is None
        )
        assert (
            not hasattr(sample_context, "noi_series")
            or sample_context.noi_series is None
        )
        assert (
            not hasattr(sample_context, "exit_gross_proceeds")
            or sample_context.exit_gross_proceeds is None
        )

        engine = ValuationEngine(sample_context)

        # Process should return None (void return pattern)
        result = engine.process()
        assert result is None

        # Context should now have all computed values
        assert (
            hasattr(sample_context, "refi_property_value")
            and sample_context.refi_property_value is not None
        )
        assert (
            hasattr(sample_context, "noi_series")
            and sample_context.noi_series is not None
        )
        assert (
            hasattr(sample_context, "exit_gross_proceeds")
            and sample_context.exit_gross_proceeds is not None
        )

        # Verify data types and shapes
        assert isinstance(sample_context.refi_property_value, pd.Series)
        assert isinstance(sample_context.noi_series, pd.Series)
        assert isinstance(sample_context.exit_gross_proceeds, pd.Series)

        assert len(sample_context.refi_property_value) == 24
        assert len(sample_context.noi_series) == 24
        assert len(sample_context.exit_gross_proceeds) == 24

    def test_process_noi_series_matches_ledger_data(self, sample_context: DealContext):
        """Test that NOI series from process() matches what's in the ledger."""
        engine = ValuationEngine(sample_context)
        engine.process()

        # Should match the fixture data: $80k for 12 months, $85k for 12 months
        assert (sample_context.noi_series.iloc[:12] == 80000.0).all()
        assert (sample_context.noi_series.iloc[12:] == 85000.0).all()

    def test_process_property_value_reflects_noi_and_settings(
        self, sample_context: DealContext
    ):
        """Test that property values reflect NOI data and cap rate settings."""
        engine = ValuationEngine(sample_context)
        engine.process()

        # Refi property values should be positive and use LTM methodology (default)
        assert (sample_context.refi_property_value > 0).all()

        # With LTM methodology, early periods will use limited history, later periods use full 12mo trailing
        # Early months (limited history): closer to current NOI
        # Later months: smooth LTM average

        # First month uses only its own NOI: $80k * 12 / 6.5% = $14.77M
        first_month_expected = (80000.0 * 12) / 0.065
        assert (
            abs(sample_context.refi_property_value.iloc[0] - first_month_expected)
            < 50000
        ), "First month should use current NOI"

        # Month 13+ should use full 12-month trailing average
        # By month 13, we have 12 months of $80k + 1 month of $85k
        month_13_ltm_noi = ((80000.0 * 11) + (85000.0 * 1)) / 12  # Weighted average
        month_13_expected = (month_13_ltm_noi * 12) / 0.065
        assert (
            abs(sample_context.refi_property_value.iloc[12] - month_13_expected) < 50000
        ), "Month 13 should use LTM"

        # Final month should use LTM of last 12 months (mix of $80k and $85k)
        final_ltm_noi = sample_context.noi_series.iloc[-12:].mean()
        final_expected = (final_ltm_noi * 12) / 0.065
        assert (
            abs(sample_context.refi_property_value.iloc[-1] - final_expected) < 50000
        ), "Final month should use full LTM"

    def test_process_can_be_called_multiple_times(self, sample_context: DealContext):
        """Test that process() can be called multiple times (idempotent)."""
        engine = ValuationEngine(sample_context)

        # First call
        engine.process()
        first_property_value = sample_context.refi_property_value.copy()
        first_noi_series = sample_context.noi_series.copy()

        # Second call should produce same results
        engine.process()

        assert sample_context.refi_property_value.equals(first_property_value)
        assert sample_context.noi_series.equals(first_noi_series)


class TestIntegrationScenarios:
    """Test integration scenarios (translates old integration test concepts)."""

    def test_complete_valuation_workflow_with_growth(
        self,
        sample_timeline: Timeline,
        sample_settings: GlobalSettings,
        sample_deal: Mock,
    ):
        """Test complete valuation workflow with NOI growth scenario."""
        # Create ledger with aggressive growth scenario
        growth_ledger = Ledger()

        # Start at $70k, grow to $90k by month 24
        growth_per_month = (90000.0 - 70000.0) / 24

        growing_noi_values = []
        for i, period in enumerate(sample_timeline.period_index):
            noi_value = 70000.0 + (growth_per_month * i)
            growing_noi_values.append(noi_value)

        growing_noi_series = pd.Series(
            growing_noi_values, index=sample_timeline.period_index
        )

        growing_noi_metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.REVENUE,
            subcategory=RevenueSubcategoryEnum.LEASE,
            item_name="Net Operating Income",
            source_id=uuid4(),
            asset_id=uuid4(),
            pass_num=1,
        )

        growth_ledger.add_series(growing_noi_series, growing_noi_metadata)

        context = DealContext(
            timeline=sample_timeline,
            settings=sample_settings,
            ledger=growth_ledger,
            deal=sample_deal,
        )

        engine = ValuationEngine(context)
        engine.process()

        # Refi valuation should grow over time with NOI growth using LTM methodology
        assert (
            context.refi_property_value.iloc[0] < context.refi_property_value.iloc[-1]
        ), "Refi valuation should grow over time"

        # First month uses only its own NOI: 70k monthly * 12 = 840k annual / 6.5% = ~$12.92M
        first_expected = (70000.0 * 12) / 0.065
        assert (
            abs(context.refi_property_value.iloc[0] - first_expected) < 50000
        ), f"First month ${context.refi_property_value.iloc[0]:,.0f} != expected ${first_expected:,.0f}"

        # Last month uses LTM: average of last 12 months of the growing series
        last_12_avg = (
            context.noi_series.iloc[-12:].mean()
            if len(context.noi_series) >= 12
            else context.noi_series.mean()
        )
        last_expected = (last_12_avg * 12) / 0.065
        assert (
            abs(context.refi_property_value.iloc[-1] - last_expected) < 50000
        ), f"Last month ${context.refi_property_value.iloc[-1]:,.0f} != expected ${last_expected:,.0f}"

        # NOI should show growth
        assert context.noi_series.iloc[0] < context.noi_series.iloc[-1]

    def test_valuation_with_realistic_institutional_assumptions(
        self,
        sample_timeline: Timeline,
        sample_deal: Mock,
        sample_ledger_with_noi: Ledger,
    ):
        """Test valuation using realistic institutional assumptions."""
        # Create settings with institutional standards
        institutional_valuation_settings = ValuationSettings(
            exit_cap_rate=0.055,  # 5.5% - institutional acquisition
            refinancing_cap_rate=0.055,  # 5.5% - institutional refinancing (same as exit for this test)
            costs_of_sale_percentage=0.015,  # 1.5% - bulk sale
        )
        institutional_settings = GlobalSettings(
            valuation=institutional_valuation_settings
        )

        institutional_context = DealContext(
            timeline=sample_timeline,
            settings=institutional_settings,
            ledger=sample_ledger_with_noi,
            deal=sample_deal,
        )

        engine = ValuationEngine(institutional_context)
        engine.process()

        # Refi property values should reflect institutional refi cap rates (higher values than default 6.5%)
        # $80k monthly NOI * 12 = $960k annual / 5.5% refi cap rate = ~$17.45M
        expected_annual_noi = 80000.0 * 12  # $960k annual NOI
        expected_refi_value = (
            expected_annual_noi / 0.055
        )  # 5.5% institutional refi cap rate

        assert (
            abs(institutional_context.refi_property_value.iloc[0] - expected_refi_value)
            < 100000
        )  # Within $100k


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling (translates old error handling concepts)."""

    def test_process_with_empty_ledger(
        self,
        sample_timeline: Timeline,
        sample_settings: GlobalSettings,
        sample_deal: Mock,
    ):
        """Test process() behavior with completely empty ledger."""
        empty_ledger = Ledger()
        context = DealContext(
            timeline=sample_timeline,
            settings=sample_settings,
            ledger=empty_ledger,
            deal=sample_deal,
        )

        engine = ValuationEngine(context)

        # Should not raise exception
        engine.process()

        # Context should be populated with zero/fallback values
        assert hasattr(context, "noi_series")
        assert hasattr(context, "refi_property_value")
        assert hasattr(context, "exit_gross_proceeds")

        # NOI should be zeros
        assert (context.noi_series == 0.0).all()

        # Property values and proceeds should be non-negative
        assert (context.refi_property_value >= 0).all()
        assert (context.exit_gross_proceeds >= 0).all()

    def test_process_with_malformed_settings(
        self,
        sample_timeline: Timeline,
        sample_deal: Mock,
        sample_ledger_with_noi: Ledger,
    ):
        """Test process() behavior with malformed valuation settings."""
        # Create settings with problematic cap rate (as close to zero as Pydantic allows)
        malformed_valuation_settings = ValuationSettings(
            exit_cap_rate=0.001  # Very low cap rate (Pydantic won't allow 0.0 due to PositiveFloat)
        )
        malformed_settings = GlobalSettings(valuation=malformed_valuation_settings)

        malformed_context = DealContext(
            timeline=sample_timeline,
            settings=malformed_settings,
            ledger=sample_ledger_with_noi,
            deal=sample_deal,
        )

        engine = ValuationEngine(malformed_context)

        # Should handle gracefully without crashing
        engine.process()

        # Should still populate context (may use fallback values)
        assert hasattr(malformed_context, "refi_property_value")
        assert isinstance(malformed_context.refi_property_value, pd.Series)
