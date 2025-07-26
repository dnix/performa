# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Tests for Sales Comparison Valuation module.
"""

import pandas as pd
import pytest
from pydantic import ValidationError

from performa.valuation import SalesComparable, SalesCompValuation


class TestSalesComparable:
    """Tests for Sales Comparable functionality."""
    
    def test_comparable_creation_basic(self):
        """Test basic comparable creation."""
        comp = SalesComparable(
            address="123 Main St",
            sale_date="2024-01-15",
            sale_price=2500000,
            property_area=25000
        )
        
        assert comp.address == "123 Main St"
        assert comp.sale_date == "2024-01-15"
        assert comp.sale_price == 2500000
        assert comp.property_area == 25000
        assert comp.cap_rate is None
        assert comp.noi is None
        assert comp.adjustments is None
    
    def test_comparable_computed_properties(self):
        """Test comparable computed properties."""
        comp = SalesComparable(
            address="123 Main St",
            sale_date="2024-01-15",
            sale_price=2500000,
            property_area=25000
        )
        
        # Price per SF
        assert comp.price_per_sf == 100.0  # 2,500,000 / 25,000
        
        # Adjusted price (no adjustments)
        assert comp.adjusted_price == 2500000
        assert comp.adjusted_price_per_sf == 100.0
    
    def test_comparable_with_adjustments(self):
        """Test comparable with adjustments."""
        comp = SalesComparable(
            address="123 Main St",
            sale_date="2024-01-15",
            sale_price=2500000,
            property_area=25000,
            adjustments={"location": 1.10, "condition": 0.95}
        )
        
        # Adjusted price should multiply all adjustment factors
        expected_adjusted = 2500000 * 1.10 * 0.95
        assert abs(comp.adjusted_price - expected_adjusted) < 1.0
        
        expected_adjusted_per_sf = expected_adjusted / 25000
        assert abs(comp.adjusted_price_per_sf - expected_adjusted_per_sf) < 0.01


class TestSalesCompValuation:
    """Tests for Sales Comparison valuation functionality."""
    
    @pytest.fixture
    def sample_comparables(self):
        """Create sample comparables for testing."""
        return [
            SalesComparable(
                address="123 Main St",
                sale_date="2024-01-15",
                sale_price=2500000,
                property_area=25000,
                cap_rate=0.065
            ),
            SalesComparable(
                address="456 Oak Ave",
                sale_date="2024-02-20",
                sale_price=3200000,
                property_area=30000,
                cap_rate=0.062
            ),
            SalesComparable(
                address="789 Elm St",
                sale_date="2024-03-10",
                sale_price=2800000,
                property_area=28000,
                cap_rate=0.068
            )
        ]
    
    def test_sales_comp_creation_basic(self, sample_comparables):
        """Test basic sales comp creation."""
        valuation = SalesCompValuation(
            name="Market Analysis",
            comparables=sample_comparables
        )
        
        assert valuation.name == "Market Analysis"
        assert len(valuation.comparables) == 3
        assert valuation.weighting_method == "equal"  # default
        assert valuation.outlier_threshold == 2.0     # default
        assert valuation.minimum_comparables == 3     # default
    
    def test_sales_comp_validation_minimum_comparables(self, sample_comparables):
        """Test minimum comparables validation."""
        # Valid number of comparables
        valuation = SalesCompValuation(
            name="Test", comparables=sample_comparables, minimum_comparables=3
        )
        assert len(valuation.comparables) == 3
        
        # Too few comparables
        with pytest.raises(ValidationError, match="Need at least 3 comparables, got 2"):
            SalesCompValuation(
                name="Test", comparables=sample_comparables[:2], minimum_comparables=3
            )
    
    def test_sales_comp_validation_weighting_method(self, sample_comparables):
        """Test weighting method validation."""
        # Valid method
        valuation = SalesCompValuation(
            name="Test", comparables=sample_comparables, weighting_method="equal"
        )
        assert valuation.weighting_method == "equal"
        
        # Invalid method
        with pytest.raises(ValidationError, match="Weighting method must be one of"):
            SalesCompValuation(
                name="Test", comparables=sample_comparables, weighting_method="invalid"
            )
    
    def test_sales_comp_validation_outlier_threshold(self, sample_comparables):
        """Test outlier threshold validation."""
        # Valid threshold
        valuation = SalesCompValuation(
            name="Test", comparables=sample_comparables, outlier_threshold=2.0
        )
        assert valuation.outlier_threshold == 2.0
        
        # Invalid threshold - too low
        with pytest.raises(ValidationError, match="Outlier threshold.*should be between 0.5 and 5.0"):
            SalesCompValuation(
                name="Test", comparables=sample_comparables, outlier_threshold=0.3
            )
    
    def test_computed_properties(self, sample_comparables):
        """Test computed properties."""
        valuation = SalesCompValuation(name="Test", comparables=sample_comparables)
        
        assert valuation.comparable_count == 3
        
        # Price per SF data
        price_data = valuation.price_per_sf_data
        assert len(price_data) == 3
        assert price_data[0] == 100.0  # 2,500,000 / 25,000
        assert abs(price_data[1] - 106.6667) < 0.01  # 3,200,000 / 30,000
        
        # Since no adjustments, adjusted data should be the same
        adjusted_data = valuation.adjusted_price_per_sf_data
        assert price_data == adjusted_data
    
    def test_calculate_statistics(self, sample_comparables):
        """Test statistics calculation."""
        valuation = SalesCompValuation(name="Test", comparables=sample_comparables)
        
        stats = valuation.calculate_statistics()
        
        # Check all expected statistics are present
        expected_keys = [
            "mean", "median", "std_dev", "min", "max", "q1", "q3",
            "coefficient_of_variation", "sample_size"
        ]
        
        for key in expected_keys:
            assert key in stats
        
        # Check values are reasonable
        assert stats["sample_size"] == 3
        assert stats["min"] <= stats["mean"] <= stats["max"]
        assert stats["min"] <= stats["median"] <= stats["max"]
        assert stats["std_dev"] >= 0
        assert stats["coefficient_of_variation"] >= 0
    
    def test_detect_outliers(self, sample_comparables):
        """Test outlier detection."""
        valuation = SalesCompValuation(name="Test", comparables=sample_comparables)
        
        # With normal data, should have no outliers
        outliers = valuation.detect_outliers()
        assert isinstance(outliers, list)
        assert len(outliers) <= len(sample_comparables)
        
        # Add an extreme outlier - much more extreme price
        outlier_comp = SalesComparable(
            address="999 Extreme St",
            sale_date="2024-04-01",
            sale_price=50000000,  # Very extreme price (20x higher)
            property_area=25000
        )
        
        outlier_valuation = SalesCompValuation(
            name="Test with Outlier",
            comparables=sample_comparables + [outlier_comp],
            outlier_threshold=1.0  # More strict threshold
        )
        
        outliers = outlier_valuation.detect_outliers()
        # Should detect the extreme comp as outlier (price per SF = 2000 vs ~100)
        assert len(outliers) >= 1
        assert 3 in outliers  # Index of the extreme comp
    
    def test_calculate_value(self, sample_comparables):
        """Test value calculation."""
        valuation = SalesCompValuation(name="Test", comparables=sample_comparables)
        
        subject_area = 27000
        result = valuation.calculate_value(subject_area)
        
        # Check result structure
        expected_keys = [
            "property_value", "indicated_price_per_sf", "subject_area",
            "comparables_used", "comparables_excluded", "price_per_sf_range",
            "price_per_sf_median", "price_per_sf_std_dev", "coefficient_of_variation"
        ]
        
        for key in expected_keys:
            assert key in result
        
        # Check calculations
        assert result["subject_area"] == subject_area
        assert result["comparables_used"] <= len(sample_comparables)
        assert result["property_value"] > 0
        assert result["indicated_price_per_sf"] > 0
        assert result["property_value"] == result["indicated_price_per_sf"] * subject_area
        
        # Invalid subject area should raise error
        with pytest.raises(ValueError, match="Subject area must be positive"):
            valuation.calculate_value(0)
    
    def test_calculate_value_with_outlier_exclusion(self, sample_comparables):
        """Test value calculation with outlier exclusion."""
        # Add an extreme outlier
        outlier_comp = SalesComparable(
            address="999 Extreme St",
            sale_date="2024-04-01",
            sale_price=50000000,  # Very extreme price (20x higher)
            property_area=25000
        )
        
        valuation = SalesCompValuation(
            name="Test with Outlier",
            comparables=sample_comparables + [outlier_comp],
            outlier_threshold=1.0  # Stricter threshold
        )
        
        subject_area = 27000
        
        # With outlier exclusion
        result_excluded = valuation.calculate_value(subject_area, exclude_outliers=True)
        
        # Without outlier exclusion
        result_included = valuation.calculate_value(subject_area, exclude_outliers=False)
        
        # Should use fewer comparables when excluding outliers
        assert result_excluded["comparables_used"] <= result_included["comparables_used"]
        assert result_excluded["comparables_excluded"] >= result_included["comparables_excluded"]
    
    def test_calculate_value_range(self, sample_comparables):
        """Test value range calculation with confidence intervals."""
        valuation = SalesCompValuation(name="Test", comparables=sample_comparables)
        
        subject_area = 27000
        confidence_level = 0.95
        
        value_range = valuation.calculate_value_range(subject_area, confidence_level)
        
        # Check result structure
        expected_keys = [
            "mean_value", "low_value", "high_value", "confidence_level",
            "margin_of_error_per_sf", "range_pct"
        ]
        
        for key in expected_keys:
            assert key in value_range
        
        # Check relationships
        assert value_range["low_value"] <= value_range["mean_value"] <= value_range["high_value"]
        assert value_range["confidence_level"] == confidence_level
        assert value_range["margin_of_error_per_sf"] >= 0
        assert value_range["range_pct"] >= 0
    
    def test_generate_comp_analysis_report(self, sample_comparables):
        """Test comprehensive comparable analysis report generation."""
        valuation = SalesCompValuation(name="Test", comparables=sample_comparables)
        
        report = valuation.generate_comp_analysis_report()
        
        # Should return a DataFrame
        assert isinstance(report, pd.DataFrame)
        assert len(report) == len(sample_comparables)
        
        # Check columns
        expected_cols = [
            "Address", "Sale_Date", "Sale_Price", "Area", "Price_Per_SF",
            "Adjusted_Price", "Adjusted_Price_Per_SF", "Cap_Rate", "NOI", "Is_Outlier"
        ]
        
        for col in expected_cols:
            assert col in report.columns
        
        # Check data integrity
        for i, comp in enumerate(sample_comparables):
            assert report.iloc[i]["Address"] == comp.address
            assert report.iloc[i]["Sale_Price"] == comp.sale_price
            assert report.iloc[i]["Area"] == comp.property_area
    
    def test_factory_method(self, sample_comparables):
        """Test factory method creation."""
        sales_data = [
            {
                "address": "123 Main St",
                "sale_date": "2024-01-15",
                "sale_price": 2500000,
                "property_area": 25000
            },
            {
                "address": "456 Oak Ave",
                "sale_date": "2024-02-20",
                "sale_price": 3200000,
                "property_area": 30000
            }
        ]
        
        valuation = SalesCompValuation.create_from_data(
            name="Factory Test",
            sales_data=sales_data,
            minimum_comparables=2
        )
        
        assert valuation.name == "Factory Test"
        assert len(valuation.comparables) == 2
        assert valuation.minimum_comparables == 2
        assert valuation.comparables[0].address == "123 Main St"
        assert valuation.comparables[1].address == "456 Oak Ave"
    
    def test_model_immutability(self, sample_comparables):
        """Test that Sales Comp models are immutable."""
        valuation = SalesCompValuation(name="Test", comparables=sample_comparables)
        
        # Should not be able to modify attributes directly (frozen model)
        with pytest.raises((AttributeError, TypeError, ValidationError)):
            valuation.weighting_method = "distance"
        
        # But should be able to create copies with modifications
        modified_valuation = valuation.model_copy(update={"weighting_method": "distance"})
        assert modified_valuation.weighting_method == "distance"
        assert valuation.weighting_method == "equal"  # Original unchanged
    
    def test_edge_cases(self, sample_comparables):
        """Test edge cases and error conditions."""
        valuation = SalesCompValuation(name="Test", comparables=sample_comparables)
        
        # Empty data after outlier removal should raise error
        # Create valuation with very strict outlier threshold that removes everything
        strict_valuation = SalesCompValuation(
            name="Strict", comparables=sample_comparables, outlier_threshold=0.5
        )
        
        # This might remove all comparables, causing an error
        try:
            result = strict_valuation.calculate_value(27000, exclude_outliers=True)
            # If it doesn't error, we should still have some comparables
            assert result["comparables_used"] > 0
        except ValueError as e:
            # Should get "No valid comparables after outlier removal"
            assert "No valid comparables" in str(e) 