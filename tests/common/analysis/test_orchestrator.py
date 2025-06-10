from __future__ import annotations

from datetime import date
from unittest.mock import ANY, MagicMock, call
from uuid import UUID, uuid4

import pandas as pd
import pytest
from pydantic import PrivateAttr

from performa.common.analysis._orchestrator import CashFlowOrchestrator
from performa.common.base import PropertyBaseModel
from performa.common.primitives import (
    AssetTypeEnum,
    CashFlowModel,
    Timeline,
    UnitOfMeasureEnum,
)

# --- Mocks and Fixtures ---

class MockCashFlow(CashFlowModel):
    """A mock, concrete CashFlowModel for testing the orchestrator."""
    _compute_cf_mock: MagicMock = PrivateAttr(default_factory=MagicMock)

    def compute_cf(self, **kwargs) -> pd.Series:
        return self._compute_cf_mock(**kwargs)

@pytest.fixture
def sample_timeline() -> Timeline:
    return Timeline(start_date=date(2024, 1, 1), duration_months=12)

@pytest.fixture
def mock_cash_flow_factory(sample_timeline: Timeline):
    """A factory to create mock cash flow models for testing."""
    def _factory(name: str, reference: UUID | None = None) -> MockCashFlow:
        model = MockCashFlow(
            name=name,
            category="Test",
            subcategory="Test",
            timeline=sample_timeline,
            value=100.0,
            unit_of_measure=UnitOfMeasureEnum.CURRENCY,
            reference=reference,
        )
        # Set a default return value on the private mock attribute
        model._compute_cf_mock.return_value = pd.Series(1, index=sample_timeline.period_index)
        return model
    return _factory

@pytest.fixture
def sample_property_model() -> PropertyBaseModel:
    """Provides a sample PropertyBaseModel for orchestrator tests."""
    return PropertyBaseModel(
        name="Test Property",
        property_type=AssetTypeEnum.OFFICE,
        gross_area=100000,
        net_rentable_area=95000,
    )


# --- Orchestrator Tests ---

def test_orchestrator_instantiation(sample_timeline: Timeline, sample_property_model: PropertyBaseModel):
    """Test successful instantiation of the CashFlowOrchestrator."""
    orchestrator = CashFlowOrchestrator(
        subject_model=sample_property_model,
        cash_flow_models=[],
        timeline=sample_timeline,
    )
    assert orchestrator.timeline == sample_timeline
    assert orchestrator.subject_model.name == "Test Property"

def test_orchestrator_dependency_resolution_dag(mock_cash_flow_factory, sample_property_model: PropertyBaseModel):
    """Test that the orchestrator computes a valid DAG in the correct order."""
    # Create a simple DAG: C -> B -> A
    model_a = mock_cash_flow_factory("A")
    model_b = mock_cash_flow_factory("B", reference=model_a.uid)
    model_c = mock_cash_flow_factory("C", reference=model_b.uid)

    # Use a manager mock to track the order of calls to the individual mocks
    manager = MagicMock()
    manager.attach_mock(model_a._compute_cf_mock, "A_called")
    manager.attach_mock(model_b._compute_cf_mock, "B_called")
    manager.attach_mock(model_c._compute_cf_mock, "C_called")

    orchestrator = CashFlowOrchestrator(
        subject_model=sample_property_model,
        cash_flow_models=[model_c, model_a, model_b], # Pass in unsorted order
        timeline=model_a.timeline,
    )
    
    orchestrator.compute_all()
    
    # The topological sort should compute A, then B, then C
    # We use ANY for lookup_fn because we don't need to inspect it in this test
    expected_calls = [
        call.A_called(lookup_fn=ANY),
        call.B_called(lookup_fn=ANY),
        call.C_called(lookup_fn=ANY),
    ]
    assert manager.mock_calls == expected_calls
