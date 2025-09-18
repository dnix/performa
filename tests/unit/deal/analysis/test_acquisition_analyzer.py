# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Comprehensive tests for the AcquisitionAnalyzer specialist service.

This test suite covers the new AcquisitionAnalyzer which handles:
1. Initial project cost calculations from deal structure
2. Acquisition purchase price and closing costs recording to ledger  
3. Deal fee processing and recording
4. Context updates with project_costs for downstream financing

Test Philosophy:
- Test actual methods that exist in current architecture
- Use realistic deal scenarios with proper acquisition setups
- Test context updates and void return patterns
- Cover edge cases (no acquisition, missing fees, etc.)
- Validate ledger entries for all acquisition transactions
"""

from datetime import date
from unittest.mock import Mock
from uuid import uuid4

import pandas as pd
import pytest

from performa.core.ledger import Ledger
from performa.core.primitives import (
    CapitalSubcategoryEnum,
    CashFlowCategoryEnum,
    GlobalSettings,
    Timeline,
)
from performa.core.primitives.enums import FeeTypeEnum
from performa.deal.analysis.acquisition import AcquisitionAnalyzer
from performa.deal.deal import Deal
from performa.deal.orchestrator import DealContext


@pytest.fixture
def sample_timeline() -> Timeline:
    """Standard timeline for acquisition testing."""
    return Timeline(start_date=date(2024, 1, 1), duration_months=24)


@pytest.fixture
def sample_settings() -> GlobalSettings:
    """Standard settings for acquisition analysis."""
    return GlobalSettings()


@pytest.fixture
def sample_ledger() -> Ledger:
    """Empty ledger for acquisition testing."""
    return Ledger()


@pytest.fixture
def sample_deal() -> Mock:
    """Mock deal with basic acquisition structure."""
    deal = Mock(spec=Deal)
    deal.uid = uuid4()  # Required for ledger metadata
    
    # Standard acquisition terms
    deal.acquisition = Mock()
    deal.acquisition.value = 5000000.0  # $5M purchase price
    deal.acquisition.closing_costs_rate = 0.02  # 2% closing costs
    deal.acquisition.acquisition_date = date(2024, 1, 15)  # Required for ledger timing
    
    # Basic asset info
    deal.asset = Mock()
    deal.asset.uid = uuid4()  # Required for ledger metadata
    deal.asset.renovation_budget = 1000000.0  # $1M renovation
    
    # Deal fees
    deal.deal_fees = []
    
    return deal


@pytest.fixture
def sample_deal_no_acquisition() -> Mock:
    """Mock deal without acquisition (development only)."""
    deal = Mock(spec=Deal)
    deal.uid = uuid4()  # Required for ledger metadata
    deal.acquisition = None
    deal.asset = Mock()
    deal.asset.uid = uuid4()  # Required for ledger metadata
    deal.asset.renovation_budget = 2000000.0  # Development only
    deal.deal_fees = []
    return deal


@pytest.fixture
def sample_deal_with_fees() -> Mock:
    """Mock deal with various fee structures."""
    deal = Mock(spec=Deal)
    deal.uid = uuid4()  # Required for ledger metadata
    
    # Acquisition terms
    deal.acquisition = Mock()
    deal.acquisition.value = 8000000.0
    deal.acquisition.closing_costs_rate = 0.025  # 2.5% closing costs
    deal.acquisition.acquisition_date = date(2024, 1, 15)  # Required for ledger timing
    
    # Asset info  
    deal.asset = Mock()
    deal.asset.uid = uuid4()  # Required for ledger metadata
    deal.asset.renovation_budget = 1500000.0
    
    # Multiple deal fees
    deal.deal_fees = []
    
    # Acquisition fee
    acq_fee = Mock()
    acq_fee.fee_type = FeeTypeEnum.ACQUISITION
    acq_fee.amount = 80000.0  # $80k acquisition fee
    acq_fee.name = "Acquisition Fee"
    acq_fee.uid = uuid4()
    acq_fee.compute_cf = lambda timeline: pd.Series(
        [-80000.0, 0.0] + [0.0] * (len(timeline.period_index) - 2),
        index=timeline.period_index,
        name="Acquisition Fee"
    )
    deal.deal_fees.append(acq_fee)
    
    # Development fee
    dev_fee = Mock()
    dev_fee.fee_type = FeeTypeEnum.DEVELOPER
    dev_fee.amount = 150000.0  # $150k developer fee
    dev_fee.name = "Developer Fee"
    dev_fee.uid = uuid4()
    dev_fee.compute_cf = lambda timeline: pd.Series(
        [-150000.0, 0.0] + [0.0] * (len(timeline.period_index) - 2),
        index=timeline.period_index,
        name="Developer Fee"
    )
    deal.deal_fees.append(dev_fee)
    
    # Asset management fee (ongoing - annual)
    mgmt_fee = Mock()
    mgmt_fee.fee_type = FeeTypeEnum.ASSET_MANAGEMENT
    mgmt_fee.amount = 50000.0  # $50k annual management fee
    mgmt_fee.name = "Asset Management Fee"
    mgmt_fee.uid = uuid4()
    mgmt_fee.compute_cf = lambda timeline: pd.Series(
        [-50000.0 / 12] * len(timeline.period_index),  # Monthly fee
        index=timeline.period_index,
        name="Asset Management Fee"
    )
    deal.deal_fees.append(mgmt_fee)
    
    return deal


def create_sample_context(
    timeline: Timeline,
    settings: GlobalSettings,
    ledger: Ledger,
    deal: Mock
) -> DealContext:
    """Helper to create DealContext for testing."""
    return DealContext(
        timeline=timeline,
        settings=settings,
        ledger=ledger,
        deal=deal
    )


class TestAcquisitionAnalyzerBasics:
    """Test basic AcquisitionAnalyzer functionality and inheritance."""
    
    def test_acquisition_analyzer_instantiation(
        self,
        sample_timeline: Timeline,
        sample_settings: GlobalSettings,
        sample_ledger: Ledger,
        sample_deal: Mock
    ):
        """Test that AcquisitionAnalyzer can be instantiated with DealContext."""
        context = create_sample_context(sample_timeline, sample_settings, sample_ledger, sample_deal)
        analyzer = AcquisitionAnalyzer(context)

        assert analyzer is not None
        assert analyzer.context is context
        assert analyzer.deal is sample_deal
        assert analyzer.timeline is sample_timeline
        assert analyzer.settings is sample_settings
        assert analyzer.ledger is sample_ledger
    
    def test_acquisition_analyzer_has_required_methods(
        self,
        sample_timeline: Timeline,
        sample_settings: GlobalSettings,
        sample_ledger: Ledger,
        sample_deal: Mock
    ):
        """Test that AcquisitionAnalyzer has all required methods."""
        context = create_sample_context(sample_timeline, sample_settings, sample_ledger, sample_deal)
        analyzer = AcquisitionAnalyzer(context)
        
        # Main public interface (void return)
        assert hasattr(analyzer, 'process')
        assert callable(getattr(analyzer, 'process'))
        
        # Should have queries from base class for ledger access
        assert hasattr(analyzer, 'queries')
        
        # Should have inherited properties from AnalysisSpecialist
        assert hasattr(analyzer, 'deal')
        assert hasattr(analyzer, 'timeline')
        assert hasattr(analyzer, 'settings')
        assert hasattr(analyzer, 'ledger')
    
    def test_acquisition_analyzer_inherits_analysis_specialist_properly(
        self,
        sample_timeline: Timeline,
        sample_settings: GlobalSettings,
        sample_ledger: Ledger,
        sample_deal: Mock
    ):
        """Test inheritance from AnalysisSpecialist base class."""
        context = create_sample_context(sample_timeline, sample_settings, sample_ledger, sample_deal)
        analyzer = AcquisitionAnalyzer(context)
        
        # Should inherit from AnalysisSpecialist
        from performa.deal.analysis.base import AnalysisSpecialist
        assert isinstance(analyzer, AnalysisSpecialist)
        
        # Should have queries initialized properly
        assert analyzer.queries is not None


class TestProjectCostCalculation:
    """Test initial project cost calculation logic."""
    
    def test_calculate_project_costs_with_acquisition(
        self,
        sample_timeline: Timeline,
        sample_settings: GlobalSettings,
        sample_ledger: Ledger,
        sample_deal: Mock
    ):
        """Test project cost calculation with standard acquisition."""
        context = create_sample_context(sample_timeline, sample_settings, sample_ledger, sample_deal)
        analyzer = AcquisitionAnalyzer(context)
        
        # Calculate project costs
        project_costs = analyzer._calculate_initial_project_costs()
        
        # Expected: $5M acquisition + $100k closing costs (2%) + $1M renovation = $6.1M
        expected_costs = 5000000.0 + (5000000.0 * 0.02) + 1000000.0
        assert project_costs == expected_costs
        assert project_costs == 6100000.0
    
    def test_calculate_project_costs_no_acquisition(
        self,
        sample_timeline: Timeline,
        sample_settings: GlobalSettings,
        sample_ledger: Ledger,
        sample_deal_no_acquisition: Mock
    ):
        """Test project cost calculation for development-only deal."""
        context = create_sample_context(
            sample_timeline, sample_settings, sample_ledger, sample_deal_no_acquisition
        )
        analyzer = AcquisitionAnalyzer(context)
        
        # Calculate project costs (development only)
        project_costs = analyzer._calculate_initial_project_costs()
        
        # Expected: Only $2M renovation (no acquisition)
        assert project_costs == 2000000.0
    
    def test_calculate_project_costs_series_acquisition_value(
        self,
        sample_timeline: Timeline,
        sample_settings: GlobalSettings,
        sample_ledger: Ledger,
        sample_deal: Mock
    ):
        """Test project cost calculation when acquisition value is a pandas Series."""
        # Modify deal to have Series acquisition value
        acquisition_series = pd.Series([2000000.0, 3000000.0], index=[0, 1])
        sample_deal.acquisition.value = acquisition_series
        
        context = create_sample_context(sample_timeline, sample_settings, sample_ledger, sample_deal)
        analyzer = AcquisitionAnalyzer(context)
        
        # Calculate project costs
        project_costs = analyzer._calculate_initial_project_costs()
        
        # Expected: $5M total acquisition + $100k closing costs (2% of $5M) + $1M renovation = $6.1M
        expected_costs = 5000000.0 + (5000000.0 * 0.02) + 1000000.0
        assert project_costs == expected_costs


class TestAcquisitionRecords:
    """Test acquisition transaction recording to ledger."""
    
    def test_add_acquisition_records_standard(
        self,
        sample_timeline: Timeline,
        sample_settings: GlobalSettings,
        sample_ledger: Ledger,
        sample_deal: Mock
    ):
        """Test standard acquisition record creation."""
        context = create_sample_context(sample_timeline, sample_settings, sample_ledger, sample_deal)
        analyzer = AcquisitionAnalyzer(context)
        
        # Add acquisition records to ledger
        analyzer._add_acquisition_records()
        
        # Verify ledger entries
        ledger_df = sample_ledger.ledger_df()
        
        # Should have acquisition entries
        acquisition_records = ledger_df[
            ledger_df['category'] == CashFlowCategoryEnum.CAPITAL
        ]
        
        assert not acquisition_records.empty
        
        # Should have purchase price entry (negative outflow)
        purchase_records = ledger_df[
            (ledger_df['category'] == CashFlowCategoryEnum.CAPITAL) &
            (ledger_df['subcategory'] == CapitalSubcategoryEnum.PURCHASE_PRICE) &
            (ledger_df['item_name'].str.contains('Acquisition', na=False))
        ]
        assert not purchase_records.empty
        
        # Should have closing costs entry
        closing_cost_records = ledger_df[
            (ledger_df['category'] == CashFlowCategoryEnum.CAPITAL) &
            (ledger_df['subcategory'] == CapitalSubcategoryEnum.CLOSING_COSTS) &
            (ledger_df['item_name'].str.contains('Closing Costs', na=False))
        ]
        assert not closing_cost_records.empty
    
    def test_add_acquisition_records_no_acquisition(
        self,
        sample_timeline: Timeline,
        sample_settings: GlobalSettings,
        sample_ledger: Ledger,
        sample_deal_no_acquisition: Mock
    ):
        """Test acquisition record handling when no acquisition exists."""
        context = create_sample_context(
            sample_timeline, sample_settings, sample_ledger, sample_deal_no_acquisition
        )
        analyzer = AcquisitionAnalyzer(context)
        
        # Add acquisition records (should handle gracefully)
        analyzer._add_acquisition_records()
        
        # Verify no acquisition records added
        ledger_df = sample_ledger.ledger_df()
        acquisition_records = ledger_df[
            ledger_df['category'] == CashFlowCategoryEnum.CAPITAL
        ]
        
        # Should be empty since no acquisition
        assert acquisition_records.empty


class TestDealFeeProcessing:
    """Test deal fee processing and recording."""
    
    def test_add_deal_fees_multiple_types(
        self,
        sample_timeline: Timeline,
        sample_settings: GlobalSettings,
        sample_ledger: Ledger,
        sample_deal_with_fees: Mock
    ):
        """Test processing multiple deal fee types."""
        context = create_sample_context(
            sample_timeline, sample_settings, sample_ledger, sample_deal_with_fees
        )
        analyzer = AcquisitionAnalyzer(context)
        
        # Add deal fees to ledger
        analyzer._add_deal_fees()
        
        # Verify ledger entries
        ledger_df = sample_ledger.ledger_df()
        
        # Should have capital outflow entries for fees
        fee_records = ledger_df[
            ledger_df['category'] == CashFlowCategoryEnum.CAPITAL
        ]
        
        assert not fee_records.empty
        
        # Should have specific fee entries
        acquisition_fee_records = ledger_df[
            ledger_df['item_name'].str.contains('Acquisition Fee', na=False)
        ]
        assert not acquisition_fee_records.empty
        
        developer_fee_records = ledger_df[
            ledger_df['item_name'].str.contains('Developer Fee', na=False)
        ]
        assert not developer_fee_records.empty
        
        management_fee_records = ledger_df[
            ledger_df['item_name'].str.contains('Asset Management Fee', na=False)
        ]
        assert not management_fee_records.empty
    
    def test_add_deal_fees_no_fees(
        self,
        sample_timeline: Timeline,
        sample_settings: GlobalSettings,
        sample_ledger: Ledger,
        sample_deal: Mock
    ):
        """Test deal fee processing when no fees exist."""
        # Ensure deal has no fees
        sample_deal.deal_fees = []
        
        context = create_sample_context(sample_timeline, sample_settings, sample_ledger, sample_deal)
        analyzer = AcquisitionAnalyzer(context)
        
        # Add deal fees (should handle gracefully)
        analyzer._add_deal_fees()
        
        # Verify ledger state
        ledger_df = sample_ledger.ledger_df()
        
        # Should be empty since no fees
        assert ledger_df.empty


class TestProcessMethodIntegration:
    """Test the main process() method integration."""
    
    def test_process_updates_context(
        self,
        sample_timeline: Timeline,
        sample_settings: GlobalSettings,
        sample_ledger: Ledger,
        sample_deal: Mock
    ):
        """Test that process() updates context with project_costs."""
        context = create_sample_context(sample_timeline, sample_settings, sample_ledger, sample_deal)
        
        # Initially no project costs
        assert context.project_costs is None
        
        # Process acquisition
        analyzer = AcquisitionAnalyzer(context)
        analyzer.process()
        
        # Should have updated context
        assert context.project_costs is not None
        assert context.project_costs == 6100000.0  # Expected total from calculation
    
    def test_process_void_return(
        self,
        sample_timeline: Timeline,
        sample_settings: GlobalSettings,
        sample_ledger: Ledger,
        sample_deal: Mock
    ):
        """Test that process() follows void return pattern."""
        context = create_sample_context(sample_timeline, sample_settings, sample_ledger, sample_deal)
        analyzer = AcquisitionAnalyzer(context)
        
        # Should return None (void pattern)
        result = analyzer.process()
        assert result is None
    
    def test_process_creates_ledger_entries(
        self,
        sample_timeline: Timeline,
        sample_settings: GlobalSettings,
        sample_ledger: Ledger,
        sample_deal_with_fees: Mock
    ):
        """Test that process() creates expected ledger entries."""
        context = create_sample_context(
            sample_timeline, sample_settings, sample_ledger, sample_deal_with_fees
        )
        
        # Initially empty ledger
        assert sample_ledger.ledger_df().empty
        
        # Process acquisition
        analyzer = AcquisitionAnalyzer(context)
        analyzer.process()
        
        # Should have ledger entries
        ledger_df = sample_ledger.ledger_df()
        assert not ledger_df.empty
        
        # Should have capital entries (acquisition + fees)
        capital_records = ledger_df[
            ledger_df['category'] == CashFlowCategoryEnum.CAPITAL
        ]
        assert not capital_records.empty
        assert len(capital_records) >= 5  # Purchase price, closing costs, 3 fees


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling scenarios."""
    
    def test_process_no_acquisition_no_renovation(
        self,
        sample_timeline: Timeline,
        sample_settings: GlobalSettings,
        sample_ledger: Ledger
    ):
        """Test processing deal with no acquisition and no renovation."""
        # Create minimal deal
        deal = Mock(spec=Deal)
        deal.uid = uuid4()  # Required for ledger metadata
        deal.acquisition = None
        deal.asset = Mock()
        deal.asset.uid = uuid4()  # Required for ledger metadata
        # Explicitly set renovation_budget to None (not a Mock)
        deal.asset.renovation_budget = None
        deal.deal_fees = []
        
        context = create_sample_context(sample_timeline, sample_settings, sample_ledger, deal)
        analyzer = AcquisitionAnalyzer(context)
        
        # Should handle gracefully
        analyzer.process()
        
        # Should have zero project costs
        assert context.project_costs == 0.0
        
        # Should have empty ledger
        assert sample_ledger.ledger_df().empty
    
    def test_process_acquisition_zero_value(
        self,
        sample_timeline: Timeline,
        sample_settings: GlobalSettings,
        sample_ledger: Ledger,
        sample_deal: Mock
    ):
        """Test processing with zero acquisition value."""
        # Set acquisition value to zero
        sample_deal.acquisition.value = 0.0
        
        context = create_sample_context(sample_timeline, sample_settings, sample_ledger, sample_deal)
        analyzer = AcquisitionAnalyzer(context)
        
        # Process should handle gracefully
        analyzer.process()
        
        # Should have only renovation costs
        assert context.project_costs == 1000000.0  # Only renovation
    
    def test_process_missing_closing_costs_rate(
        self,
        sample_timeline: Timeline,
        sample_settings: GlobalSettings,
        sample_ledger: Ledger,
        sample_deal: Mock
    ):
        """Test processing when closing costs rate is missing."""
        # Remove closing costs rate
        sample_deal.acquisition.closing_costs_rate = None
        
        context = create_sample_context(sample_timeline, sample_settings, sample_ledger, sample_deal)
        analyzer = AcquisitionAnalyzer(context)
        
        # Should handle gracefully
        analyzer.process()
        
        # Should have acquisition + renovation costs (no closing costs)
        assert context.project_costs == 6000000.0  # $5M + $1M (no closing costs)
