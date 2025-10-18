# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Tests for PivotTableReport functionality.

Validates that the pivot table report correctly transforms ledger data
into Excel-style pivot tables with proper formatting and aggregation.
"""

from datetime import date

import pandas as pd
import pytest

from performa.patterns import ResidentialDevelopmentPattern
from performa.reporting.pivot_report import PivotTableReport


class TestPivotTableReport:
    """Test suite for PivotTableReport class."""

    @pytest.fixture(scope="class")
    def sample_analysis_results(self):
        """Create sample analysis results for testing.

        Uses class scope to avoid regenerating the same analysis for each test,
        improving test suite performance by ~1.4s.
        """
        pattern = ResidentialDevelopmentPattern(
            project_name="Test Development",
            acquisition_date=date(2024, 1, 1),
            land_cost=2_000_000,
            total_units=50,
            unit_mix=[
                {"unit_type": "1BR", "count": 30, "avg_sf": 650, "target_rent": 1500},
                {"unit_type": "2BR", "count": 20, "avg_sf": 900, "target_rent": 2000},
            ],
            construction_cost_per_unit=150_000,
            hold_period_years=5,
        )

        return pattern.analyze()

    def test_pivot_report_initialization(self, sample_analysis_results):
        """Test PivotTableReport can be initialized with analysis results."""
        report = PivotTableReport(sample_analysis_results)
        assert report._results is not None
        assert hasattr(report, "_results")

    def test_monthly_pivot_generation(self, sample_analysis_results):
        """Test monthly pivot table generation."""
        report = PivotTableReport(sample_analysis_results)
        monthly_pivot = report.generate(frequency="M")

        # Validate structure
        assert isinstance(monthly_pivot, pd.DataFrame)
        assert monthly_pivot.shape[0] > 0  # Has rows (line items)
        assert monthly_pivot.shape[1] > 0  # Has columns (periods)

        # Should have multiple months of data
        assert monthly_pivot.shape[1] >= 12  # At least 1 year of data

    def test_quarterly_pivot_generation(self, sample_analysis_results):
        """Test quarterly pivot table generation."""
        report = PivotTableReport(sample_analysis_results)
        quarterly_pivot = report.generate(frequency="Q")

        # Validate structure
        assert isinstance(quarterly_pivot, pd.DataFrame)
        assert quarterly_pivot.shape[0] > 0  # Has rows
        assert quarterly_pivot.shape[1] > 0  # Has columns

        # Should have fewer periods than monthly
        monthly_pivot = report.generate(frequency="M")
        assert quarterly_pivot.shape[1] < monthly_pivot.shape[1]

    def test_annual_pivot_generation(self, sample_analysis_results):
        """Test annual pivot table generation."""
        report = PivotTableReport(sample_analysis_results)
        annual_pivot = report.generate(frequency="A")

        # Validate structure
        assert isinstance(annual_pivot, pd.DataFrame)
        assert annual_pivot.shape[0] > 0  # Has rows
        assert annual_pivot.shape[1] > 0  # Has columns

        # Should have the fewest periods
        quarterly_pivot = report.generate(frequency="Q")
        assert annual_pivot.shape[1] <= quarterly_pivot.shape[1]

    def test_subtotals_functionality(self, sample_analysis_results):
        """Test subtotal generation."""
        report = PivotTableReport(sample_analysis_results)

        # Without subtotals
        no_subtotals = report.generate(include_subtotals=False)

        # With subtotals
        with_subtotals = report.generate(include_subtotals=True)

        # With subtotals should have more rows (subtotal rows added)
        assert with_subtotals.shape[0] >= no_subtotals.shape[0]
        assert with_subtotals.shape[1] == no_subtotals.shape[1]  # Same periods

    def test_totals_column_functionality(self, sample_analysis_results):
        """Test totals column generation."""
        report = PivotTableReport(sample_analysis_results)

        # Without totals column
        no_totals = report.generate(include_totals_column=False)

        # With totals column
        with_totals = report.generate(include_totals_column=True)

        # With totals should have one more column
        assert with_totals.shape[1] == no_totals.shape[1] + 1
        assert "Total" in with_totals.columns

    def test_category_filtering(self, sample_analysis_results):
        """Test category filtering functionality."""
        report = PivotTableReport(sample_analysis_results)

        # Get all categories
        full_pivot = report.generate()

        # Filter to revenue only
        revenue_only = report.generate(categories=["Revenue"])

        # Revenue-only should have fewer rows
        assert revenue_only.shape[0] <= full_pivot.shape[0]
        # Filtered results may have fewer columns if some periods have no revenue data
        assert revenue_only.shape[1] <= full_pivot.shape[1]

    def test_currency_formatting(self, sample_analysis_results):
        """Test currency formatting functionality."""
        report = PivotTableReport(sample_analysis_results)

        # Without formatting
        no_format = report.generate(currency_format=False)

        # With formatting
        with_format = report.generate(currency_format=True)

        # Same dimensions
        assert no_format.shape == with_format.shape

        # Different value types (formatted should be strings)
        if not no_format.empty and not with_format.empty:
            # Check that some values are formatted as strings
            formatted_sample = str(with_format.iloc[0, 0])
            assert "$" in formatted_sample or formatted_sample == "$0"

    def test_fluent_interface_integration(self, sample_analysis_results):
        """Test integration with fluent interface."""
        # This should work through the results.reporting interface
        pivot_table = sample_analysis_results.reporting.pivot_table(frequency="Q")

        assert isinstance(pivot_table, pd.DataFrame)
        assert pivot_table.shape[0] > 0
        assert pivot_table.shape[1] > 0

    def test_ledger_access_error_handling(self):
        """Test proper error handling when ledger data is unavailable."""

        # Create a mock results object without proper ledger access
        class MockResults:
            def __init__(self):
                self.asset_analysis = None

        mock_results = MockResults()

        # BaseReport now has proper type checking (improvement!)
        with pytest.raises(TypeError, match="BaseReport requires a DealResults object"):
            report = PivotTableReport(mock_results)
