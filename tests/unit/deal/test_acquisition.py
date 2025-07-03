"""
Unit tests for AcquisitionTerms model.

Tests cover model validation, cash flow computation, and integration
with the CashFlowModel base class.
"""

from datetime import date
from unittest.mock import Mock

import pandas as pd
import pytest

from performa.analysis import AnalysisContext
from performa.common.primitives import GlobalSettings, Timeline
from performa.deal.acquisition import AcquisitionTerms


class TestAcquisitionTermsInstantiation:
    """Test model instantiation and validation."""

    def test_basic_instantiation_single_payment(self):
        """Test basic model creation with single payment."""
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
        
        acquisition = AcquisitionTerms(
            name="Test Acquisition",
            timeline=timeline,
            value=10_000_000,
            acquisition_date=date(2024, 1, 15),
            closing_costs_rate=0.025
        )
        
        assert acquisition.name == "Test Acquisition"
        assert acquisition.value == 10_000_000
        assert acquisition.acquisition_date == date(2024, 1, 15)
        assert acquisition.closing_costs_rate == 0.025
        assert acquisition.category == "Acquisition"
        assert acquisition.subcategory == "Purchase"

    def test_basic_instantiation_multi_payment(self):
        """Test basic model creation with payment schedule."""
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
        payment_schedule = {
            pd.Period('2024-01', freq='M'): 2_000_000,
            pd.Period('2024-03', freq='M'): 8_000_000
        }
        
        acquisition = AcquisitionTerms(
            name="Phased Acquisition",
            timeline=timeline,
            value=payment_schedule,
            closing_costs_rate=0.02
        )
        
        assert acquisition.name == "Phased Acquisition"
        assert isinstance(acquisition.value, dict)
        assert acquisition.acquisition_date is None  # Not needed for dict values
        assert acquisition.closing_costs_rate == 0.02

    def test_default_closing_costs_rate(self):
        """Test that default closing costs rate is applied."""
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
        
        acquisition = AcquisitionTerms(
            name="Test",
            timeline=timeline,
            value=1_000_000,
            acquisition_date=date(2024, 1, 1)
        )
        
        assert acquisition.closing_costs_rate == 0.02  # Default 2%

    def test_validation_error_missing_acquisition_date(self):
        """Test validation error when acquisition_date is missing for float value."""
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
        
        with pytest.raises(ValueError, match="'acquisition_date' is required when 'value' is a single number"):
            AcquisitionTerms(
                name="Test",
                timeline=timeline,
                value=1_000_000,
                # Missing acquisition_date
                closing_costs_rate=0.02
            )

    def test_no_validation_error_with_dict_value(self):
        """Test no validation error when using dict value without acquisition_date."""
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
        payment_schedule = {pd.Period('2024-01', freq='M'): 1_000_000}
        
        # Should not raise an error
        acquisition = AcquisitionTerms(
            name="Test",
            timeline=timeline,
            value=payment_schedule,
            # No acquisition_date needed
            closing_costs_rate=0.02
        )
        
        assert acquisition.acquisition_date is None

    def test_validation_error_acquisition_date_with_dict_value(self):
        """Test validation error when acquisition_date is provided with dict/Series value."""
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
        payment_schedule = {pd.Period('2024-01', freq='M'): 1_000_000}
        
        with pytest.raises(ValueError, match="'acquisition_date' must not be provided when 'value' is a Series or dict"):
            AcquisitionTerms(
                name="Test",
                timeline=timeline,
                value=payment_schedule,
                acquisition_date=date(2024, 1, 1),  # This should cause error
                closing_costs_rate=0.02
            )

    def test_validation_error_acquisition_date_with_series_value(self):
        """Test validation error when acquisition_date is provided with pandas Series value."""
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
        payment_series = pd.Series(
            [1_000_000, 2_000_000],
            index=pd.period_range('2024-01', periods=2, freq='M')
        )
        
        with pytest.raises(ValueError, match="'acquisition_date' must not be provided when 'value' is a Series or dict"):
            AcquisitionTerms(
                name="Test",
                timeline=timeline,
                value=payment_series,
                acquisition_date=date(2024, 1, 1),  # This should cause error
                closing_costs_rate=0.02
            )


class TestAcquisitionTermsCashFlowComputation:
    """Test cash flow computation logic."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock analysis context for testing."""
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
        
        # Create a mock property to avoid complex dependencies
        mock_property = Mock()
        mock_property.net_rentable_area = 100_000
        
        return AnalysisContext(
            timeline=timeline,
            settings=GlobalSettings(),
            property_data=mock_property,
            resolved_lookups={}
        )

    def test_single_payment_cash_flow(self, mock_context):
        """Test cash flow computation for single payment."""
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
        
        acquisition = AcquisitionTerms(
            name="Single Payment",
            timeline=timeline,
            value=10_000_000,
            acquisition_date=date(2024, 2, 1),
            closing_costs_rate=0.025
        )
        
        cash_flow = acquisition.compute_cf(mock_context)
        
        # Should be a pandas Series with 12 monthly periods
        assert isinstance(cash_flow, pd.Series)
        assert len(cash_flow) == 12
        
        # Payment should occur in February 2024
        feb_2024 = pd.Period('2024-02', freq='M')
        expected_total = 10_000_000 + (10_000_000 * 0.025)  # Purchase + closing costs
        expected_outflow = -expected_total  # Negative for outflow
        
        assert cash_flow[feb_2024] == expected_outflow
        
        # All other months should be zero
        non_feb_periods = cash_flow[cash_flow.index != feb_2024]
        assert (non_feb_periods == 0).all()

    def test_multi_payment_cash_flow(self, mock_context):
        """Test cash flow computation for multi-payment schedule."""
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
        payment_schedule = {
            pd.Period('2024-02', freq='M'): 3_000_000,
            pd.Period('2024-05', freq='M'): 7_000_000
        }
        
        acquisition = AcquisitionTerms(
            name="Multi Payment",
            timeline=timeline,
            value=payment_schedule,
            closing_costs_rate=0.02
        )
        
        cash_flow = acquisition.compute_cf(mock_context)
        
        # Check February payment
        feb_2024 = pd.Period('2024-02', freq='M')
        feb_total = 3_000_000 + (3_000_000 * 0.02)
        assert cash_flow[feb_2024] == -feb_total
        
        # Check May payment
        may_2024 = pd.Period('2024-05', freq='M')
        may_total = 7_000_000 + (7_000_000 * 0.02)
        assert cash_flow[may_2024] == -may_total
        
        # Check that only these two periods have non-zero values
        non_zero_periods = cash_flow[cash_flow != 0]
        assert len(non_zero_periods) == 2

    def test_zero_closing_costs(self, mock_context):
        """Test cash flow computation with zero closing costs."""
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=6)
        
        acquisition = AcquisitionTerms(
            name="No Closing Costs",
            timeline=timeline,
            value=5_000_000,
            acquisition_date=date(2024, 1, 1),
            closing_costs_rate=0.0  # No closing costs
        )
        
        cash_flow = acquisition.compute_cf(mock_context)
        
        jan_2024 = pd.Period('2024-01', freq='M')
        assert cash_flow[jan_2024] == -5_000_000  # Only purchase price

    def test_high_closing_costs(self, mock_context):
        """Test cash flow computation with high closing costs."""
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=6)
        
        acquisition = AcquisitionTerms(
            name="High Closing Costs",
            timeline=timeline,
            value=1_000_000,
            acquisition_date=date(2024, 1, 1),
            closing_costs_rate=0.05  # 5% closing costs
        )
        
        cash_flow = acquisition.compute_cf(mock_context)
        
        jan_2024 = pd.Period('2024-01', freq='M')
        expected_total = 1_000_000 + (1_000_000 * 0.05)
        assert cash_flow[jan_2024] == -expected_total

    def test_payment_outside_timeline(self, mock_context):
        """Test behavior when payment date is outside timeline."""
        timeline = Timeline(start_date=date(2024, 3, 1), duration_months=6)  # Mar-Aug 2024
        
        acquisition = AcquisitionTerms(
            name="Outside Timeline",
            timeline=timeline,
            value=1_000_000,
            acquisition_date=date(2024, 1, 1),  # Before timeline start
            closing_costs_rate=0.02
        )
        
        cash_flow = acquisition.compute_cf(mock_context)
        
        # All values should be zero since payment is outside timeline
        assert (cash_flow == 0).all()


class TestAcquisitionTermsIntegration:
    """Test integration with CashFlowModel base class."""

    def test_inherits_from_cashflowmodel(self):
        """Test that AcquisitionTerms properly inherits from CashFlowModel."""
        from performa.common.primitives import CashFlowModel
        
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
        acquisition = AcquisitionTerms(
            name="Inheritance Test",
            timeline=timeline,
            value=1_000_000,
            acquisition_date=date(2024, 1, 1)
        )
        
        assert isinstance(acquisition, CashFlowModel)

    def test_has_required_cashflowmodel_fields(self):
        """Test that all required CashFlowModel fields are present."""
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
        acquisition = AcquisitionTerms(
            name="Required Fields Test",
            timeline=timeline,
            value=1_000_000,
            acquisition_date=date(2024, 1, 1)
        )
        
        # Check required CashFlowModel fields
        assert hasattr(acquisition, 'uid')
        assert hasattr(acquisition, 'name')
        assert hasattr(acquisition, 'category')
        assert hasattr(acquisition, 'subcategory')
        assert hasattr(acquisition, 'timeline')
        assert hasattr(acquisition, 'value')
        assert hasattr(acquisition, 'unit_of_measure')
        assert hasattr(acquisition, 'frequency')

    def test_uses_inherited_cast_to_flow_method(self):
        """Test that the model uses the inherited _cast_to_flow method."""
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=6)
        acquisition = AcquisitionTerms(
            name="Cast to Flow Test",
            timeline=timeline,
            value=1_000_000,
            acquisition_date=date(2024, 2, 1)
        )
        
        # Test _cast_to_flow method exists and works
        payment_period = pd.Period('2024-02', freq='M')
        payment_dict = {payment_period: 1_000_000}
        
        result = acquisition._cast_to_flow(payment_dict)
        
        assert isinstance(result, pd.Series)
        assert len(result) == 6  # Timeline length
        assert result[payment_period] == 1_000_000


class TestAcquisitionTermsEdgeCases:
    """Test edge cases and error conditions."""

    def test_series_value_input(self):
        """Test using pandas Series as value input."""
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)
        
        payment_series = pd.Series(
            [2_000_000, 8_000_000],
            index=pd.period_range('2024-01', periods=2, freq='M')
        )
        
        acquisition = AcquisitionTerms(
            name="Series Input",
            timeline=timeline,
            value=payment_series,
            closing_costs_rate=0.02
        )
        
        assert isinstance(acquisition.value, pd.Series)
        assert acquisition.acquisition_date is None

    def test_list_value_input(self):
        """Test using list as value input."""
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=3)
        
        # List should be spread across timeline periods
        payment_list = [1_000_000, 2_000_000, 0]
        
        acquisition = AcquisitionTerms(
            name="List Input",
            timeline=timeline,
            value=payment_list,
            closing_costs_rate=0.02
        )
        
        assert isinstance(acquisition.value, list)
        assert len(acquisition.value) == 3

    def test_compute_cf_error_handling(self):
        """Test error handling in compute_cf method."""
        from performa.analysis import AnalysisContext
        
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=6)
        
        # Create acquisition with missing acquisition_date using dict value to bypass validation
        # Then switch to float to trigger compute_cf error
        acquisition = AcquisitionTerms(
            name="Error Test",
            timeline=timeline,
            value={pd.Period('2024-01', freq='M'): 1_000_000},  # Dict to bypass validation
            closing_costs_rate=0.02
        )
        
        # Create a copy with float value but no acquisition_date (this should fail in compute_cf)
        error_acquisition = acquisition.copy(updates={
            'value': 1_000_000,  # Now it's a float
            'acquisition_date': None  # But no date provided
        })
        
        # Create mock context
        mock_property = Mock()
        mock_property.net_rentable_area = 100_000
        mock_context = AnalysisContext(
            timeline=timeline,
            settings=GlobalSettings(),
            property_data=mock_property,
            resolved_lookups={}
        )
        
        with pytest.raises(ValueError, match="'acquisition_date' is required when 'value' is a single number"):
            error_acquisition.compute_cf(mock_context) 