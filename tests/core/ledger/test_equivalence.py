# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Basic equivalence tests for the ledger system.

This module provides foundational tests to verify the ledger components
work correctly before integration with the broader analysis system.
"""

from datetime import date
from uuid import uuid4

import pandas as pd
import pytest

from performa.core.ledger import (
    FlowPurposeMapper,
    LedgerBuilder,
    LedgerGenerationSettings,
    LedgerQuery,
    SeriesBatchConverter,
    SeriesMetadata,
    TransactionRecord,
)
from performa.core.primitives import TransactionPurpose


class TestTransactionRecord:
    """Test TransactionRecord functionality."""
    
    def test_basic_creation(self):
        """Test basic TransactionRecord creation."""
        record = TransactionRecord(
            date=date(2024, 1, 15),
            amount=1000.0,
            flow_purpose=TransactionPurpose.OPERATING,
            category="Revenue",
            subcategory="Rent",
            item_name="Base Rent - Unit 101",
            source_id=uuid4(),
            asset_id=uuid4(),
            pass_num=1
        )
        
        assert record.amount == 1000.0
        assert record.flow_purpose == TransactionPurpose.OPERATING
        assert record.pass_num == 1
        assert record.transaction_id is not None  # Auto-generated
    
    def test_validation(self):
        """Test TransactionRecord validation."""
        with pytest.raises(ValueError, match="pass_num must be 1 or 2"):
            TransactionRecord(
                date=date(2024, 1, 15),
                amount=1000.0,
                flow_purpose=TransactionPurpose.OPERATING,
                category="Revenue",
                subcategory="Rent", 
                item_name="Test",
                source_id=uuid4(),
                asset_id=uuid4(),
                pass_num=3  # Invalid
            )
        
        with pytest.raises(ValueError, match="item_name cannot be empty"):
            TransactionRecord(
                date=date(2024, 1, 15),
                amount=1000.0,
                flow_purpose=TransactionPurpose.OPERATING,
                category="Revenue",
                subcategory="Rent",
                item_name="",  # Empty
                source_id=uuid4(),
                asset_id=uuid4(),
                pass_num=1
            )


class TestSeriesMetadata:
    """Test SeriesMetadata functionality."""
    
    def test_basic_creation(self):
        """Test basic SeriesMetadata creation."""
        metadata = SeriesMetadata(
            category="Revenue",
            subcategory="Rent",
            item_name="Base Rent",
            source_id=uuid4(),
            asset_id=uuid4(),
            pass_num=1
        )
        
        assert metadata.category == "Revenue"
        assert metadata.pass_num == 1
        assert metadata.deal_id is None  # Optional field
    
    def test_validation(self):
        """Test SeriesMetadata validation."""
        with pytest.raises(ValueError, match="category cannot be empty"):
            SeriesMetadata(
                category="",  # Empty
                subcategory="Rent",
                item_name="Base Rent",
                source_id=uuid4(),
                asset_id=uuid4(),
                pass_num=1
            )


class TestFlowPurposeMapper:
    """Test FlowPurposeMapper functionality."""
    
    def test_basic_mapping(self):
        """Test basic category to purpose mapping."""
        # Revenue -> Operating
        purpose = FlowPurposeMapper.determine_purpose("Revenue", 1000.0)
        assert purpose == TransactionPurpose.OPERATING
        
        # Expense -> Operating
        purpose = FlowPurposeMapper.determine_purpose("Expense", -500.0)
        assert purpose == TransactionPurpose.OPERATING
        
        # Capital outflow -> Capital Use
        purpose = FlowPurposeMapper.determine_purpose("Capital", -50000.0)
        assert purpose == TransactionPurpose.CAPITAL_USE
        
        # Capital inflow -> Capital Source
        purpose = FlowPurposeMapper.determine_purpose("Capital", 100000.0)
        assert purpose == TransactionPurpose.CAPITAL_SOURCE
        
        # Financing -> Financing Service
        purpose = FlowPurposeMapper.determine_purpose("Financing", -1500.0)
        assert purpose == TransactionPurpose.FINANCING_SERVICE
    
    def test_subcategory_mapping(self):
        """Test enhanced mapping with subcategories."""
        # TI should be Capital Use regardless of amount
        purpose = FlowPurposeMapper.determine_purpose_with_subcategory(
            "Revenue", "TI", 1000.0
        )
        assert purpose == TransactionPurpose.CAPITAL_USE
        
        # LC should be Capital Use
        purpose = FlowPurposeMapper.determine_purpose_with_subcategory(
            "Revenue", "Leasing Commission", -2000.0
        )
        assert purpose == TransactionPurpose.CAPITAL_USE


class TestLedgerBuilder:
    """Test LedgerBuilder functionality."""
    
    def test_empty_builder(self):
        """Test empty LedgerBuilder creation."""
        builder = LedgerBuilder()
        assert builder.record_count() == 0
        assert builder.series_count() == 0
        
        # Empty ledger should have proper schema
        ledger = builder.get_current_ledger()
        assert ledger.empty
        assert 'date' in ledger.columns
        assert 'amount' in ledger.columns
    
    def test_add_series(self):
        """Test adding Series to builder."""
        builder = LedgerBuilder()
        
        # Create test series
        dates = pd.date_range('2024-01-01', periods=3, freq='M')
        series = pd.Series([1000.0, 1100.0, 1200.0], index=dates)
        
        metadata = SeriesMetadata(
            category="Revenue",
            subcategory="Rent",
            item_name="Base Rent",
            source_id=uuid4(),
            asset_id=uuid4(),
            pass_num=1
        )
        
        builder.add_series(series, metadata)
        assert builder.series_count() == 1
        
        # Building ledger should convert series to records
        ledger = builder.get_current_ledger()
        assert len(ledger) == 3  # 3 months of data
        assert builder.series_count() == 0  # Series batch cleared after conversion
    
    def test_builder_ownership(self):
        """Test that builder owns the ledger."""
        builder = LedgerBuilder()
        
        # First call creates ledger
        ledger1 = builder.get_current_ledger()
        
        # Second call should return same DataFrame (cached)
        ledger2 = builder.get_current_ledger()
        assert ledger1 is ledger2
        
        # Adding data should mark as dirty
        dates = pd.date_range('2024-01-01', periods=2, freq='M')
        series = pd.Series([1000.0, 1100.0], index=dates)
        metadata = SeriesMetadata(
            category="Revenue",
            subcategory="Rent", 
            item_name="Test",
            source_id=uuid4(),
            asset_id=uuid4(),
            pass_num=1
        )
        
        builder.add_series(series, metadata)
        
        # Next call should rebuild (different DataFrame)
        ledger3 = builder.get_current_ledger()
        assert ledger3 is not ledger1
        assert len(ledger3) == 2


class TestSeriesBatchConverter:
    """Test SeriesBatchConverter functionality."""
    
    def test_convert_series(self):
        """Test converting a single Series."""
        dates = pd.date_range('2024-01-01', periods=3, freq='M')
        series = pd.Series([1000.0, 0.0, 1200.0], index=dates)
        
        metadata = SeriesMetadata(
            category="Revenue",
            subcategory="Rent",
            item_name="Base Rent",
            source_id=uuid4(),
            asset_id=uuid4(),
            pass_num=1
        )
        
        # Convert with skip_zeros=True (default)
        records = SeriesBatchConverter.convert_series(series, metadata, skip_zeros=True)
        assert len(records) == 2  # Zero value skipped
        
        # Convert with skip_zeros=False
        records = SeriesBatchConverter.convert_series(series, metadata, skip_zeros=False)
        assert len(records) == 3  # All values included
        
        # Check record content
        record = records[0]
        assert record.amount == 1000.0
        assert record.flow_purpose == TransactionPurpose.OPERATING
        assert record.category == "Revenue"


class TestLedgerQuery:
    """Test LedgerQuery functionality."""
    
    def test_empty_query(self):
        """Test LedgerQuery with empty DataFrame."""
        empty_df = pd.DataFrame(columns=[
            'date', 'amount', 'flow_purpose', 'category', 'subcategory'
        ])
        
        query = LedgerQuery(ledger=empty_df)
        
        noi = query.noi_by_period()
        assert noi.empty
    
    def test_schema_validation(self):
        """Test schema validation in LedgerQuery."""
        # Missing required column
        bad_df = pd.DataFrame({'amount': [1000.0]})
        
        with pytest.raises(ValueError, match="Ledger missing required columns"):
            LedgerQuery(ledger=bad_df)
    
    def test_basic_queries(self):
        """Test basic query operations."""
        # Create test ledger
        data = {
            'date': [date(2024, 1, 1), date(2024, 2, 1)],
            'amount': [1000.0, -500.0],
            'flow_purpose': ['Operating', 'Operating'],
            'category': ['Revenue', 'Expense'],
            'subcategory': ['Rent', 'Utilities'],
            'item_name': ['Base Rent', 'Electric'],
        }
        df = pd.DataFrame(data)
        
        query = LedgerQuery(ledger=df)
        
        # Test NOI calculation
        noi = query.noi_by_period()
        assert len(noi) == 2
        assert noi.sum() == 500.0  # 1000 - 500
        
        # Test filtering
        operating = query.operating_flows()
        assert len(operating) == 2


class TestLedgerGenerationSettings:
    """Test LedgerGenerationSettings functionality."""
    
    def test_default_settings(self):
        """Test default settings creation."""
        settings = LedgerGenerationSettings()
        
        assert settings.skip_zero_values is True
        assert settings.validate_transactions is True
        assert settings.batch_size == 1000
        assert settings.large_ledger_threshold == 10000
    
    def test_custom_settings(self):
        """Test custom settings validation."""
        settings = LedgerGenerationSettings(
            skip_zero_values=False,
            batch_size=500
        )
        
        assert settings.skip_zero_values is False
        assert settings.batch_size == 500
    
    def test_validation(self):
        """Test settings validation."""
        with pytest.raises(ValueError):
            LedgerGenerationSettings(batch_size=50)  # Below minimum
        
        with pytest.raises(ValueError):
            LedgerGenerationSettings(large_ledger_threshold=500)  # Below minimum


def test_full_integration():
    """Test full integration of ledger components."""
    # Create builder with custom settings
    settings = LedgerGenerationSettings(skip_zero_values=True)
    builder = LedgerBuilder(settings=settings)
    
    # Create test data
    dates = pd.date_range('2024-01-01', periods=12, freq='M')
    rent_series = pd.Series([10000.0] * 12, index=dates)
    expense_series = pd.Series([-2000.0] * 12, index=dates)
    
    # Create metadata
    rent_metadata = SeriesMetadata(
        category="Revenue",
        subcategory="Rent",
        item_name="Base Rent",
        source_id=uuid4(),
        asset_id=uuid4(),
        pass_num=1
    )
    
    expense_metadata = SeriesMetadata(
        category="Expense", 
        subcategory="Utilities",
        item_name="Electric",
        source_id=uuid4(),
        asset_id=uuid4(),
        pass_num=1
    )
    
    # Add to builder
    builder.add_series(rent_series, rent_metadata)
    builder.add_series(expense_series, expense_metadata)
    
    # Get ledger
    ledger = builder.get_current_ledger()
    assert len(ledger) == 24  # 12 months * 2 series
    
    # Query the ledger
    query = LedgerQuery(ledger=ledger)
    
    # Calculate NOI
    noi = query.noi_by_period()
    assert len(noi) == 12
    assert all(noi == 8000.0)  # 10000 - 2000 each month
    
    # Test summary
    summary = query.summary_by_purpose()
    assert len(summary) == 1  # Only operating flows
    assert summary.loc['Operating', 'sum'] == 96000.0  # 8000 * 12
