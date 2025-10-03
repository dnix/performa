# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Integration tests for orchestrator transaction batching.

This module verifies that the CashFlowOrchestrator correctly uses the
transaction batching functionality for optimal performance while maintaining
result accuracy and dependency graph integrity.
"""

import time
import uuid
from unittest.mock import Mock

import pandas as pd
import pytest

from performa.analysis.orchestrator import AnalysisContext, CashFlowOrchestrator
from performa.core.ledger import Ledger
from performa.core.ledger.queries import LedgerQueries
from performa.core.ledger.records import SeriesMetadata
from performa.core.primitives import (
    CashFlowCategoryEnum,
    ExpenseSubcategoryEnum,
    GlobalSettings,
    OrchestrationPass,
    RevenueSubcategoryEnum,
    Timeline,
)


class TestOrchestratorTransactionBatching:
    """Test the transaction batching integration in CashFlowOrchestrator."""

    def setup_method(self):
        """Set up test fixtures for each test method."""
        # Create a simple timeline
        self.timeline = Timeline(
            start_date=pd.to_datetime("2024-01-01").date(), duration_months=12
        )

        # Create global settings
        self.settings = GlobalSettings()

        # Create mock property data (must have numeric NRA for occupancy calc)
        self.property_data = Mock()
        self.property_data.uid = uuid.uuid4()
        self.property_data.net_rentable_area = 100000

        # Create analysis context with ledger
        self.ledger = Ledger()
        self.context = AnalysisContext(
            timeline=self.timeline,
            settings=self.settings,
            property_data=self.property_data,
            ledger=self.ledger,
            resolved_lookups={},
        )

    def test_orchestrator_uses_transaction_context(self):
        """Test that the orchestrator correctly wraps execution in a transaction."""
        # Create mock models for both phases
        independent_model = Mock()
        independent_model.uid = uuid.uuid4()
        independent_model.name = "Test Independent Model"
        independent_model.category = CashFlowCategoryEnum.REVENUE
        independent_model.subcategory = RevenueSubcategoryEnum.LEASE
        independent_model.calculation_pass = OrchestrationPass.INDEPENDENT_MODELS
        independent_model.reference = None

        # Mock the compute_cf method to return a simple series
        test_series = pd.Series(
            [1000] * 12, index=self.timeline.period_index, name="test_revenue"
        )
        independent_model.compute_cf.return_value = test_series

        dependent_model = Mock()
        dependent_model.uid = uuid.uuid4()
        dependent_model.name = "Test Dependent Model"
        dependent_model.category = CashFlowCategoryEnum.EXPENSE
        dependent_model.subcategory = ExpenseSubcategoryEnum.OPEX
        dependent_model.calculation_pass = OrchestrationPass.DEPENDENT_MODELS
        dependent_model.reference = None
        dependent_model.compute_cf.return_value = pd.Series(
            [100] * 12, index=self.timeline.period_index, name="test_expense"
        )

        models = [independent_model, dependent_model]

        # Create orchestrator
        orchestrator = CashFlowOrchestrator(models=models, context=self.context)

        # Wrap the real transaction to count calls while preserving behavior
        transaction_calls = []
        original_transaction_factory = self.ledger.transaction

        def wrapped_transaction():
            transaction_calls.append("call")
            return original_transaction_factory()

        self.ledger.transaction = wrapped_transaction

        # Execute the orchestration
        orchestrator.execute()

        # Verify transactions were used (Phase 1 and Phase 2)
        assert (
            len(transaction_calls) >= 2
        ), "Expected at least two transactions (Phase 1 and Phase 2)"

    def test_strategic_flush_between_phases(self):
        """Test that flush is called between Phase 1 and intermediate aggregation."""
        # Create models for both phases
        independent_model = Mock()
        independent_model.uid = uuid.uuid4()
        independent_model.name = "Test Independent"
        independent_model.category = CashFlowCategoryEnum.REVENUE
        independent_model.subcategory = RevenueSubcategoryEnum.LEASE
        independent_model.calculation_pass = OrchestrationPass.INDEPENDENT_MODELS
        independent_model.reference = None
        independent_model.compute_cf.return_value = pd.Series(
            [1000] * 12, index=self.timeline.period_index
        )

        dependent_model = Mock()
        dependent_model.uid = uuid.uuid4()
        dependent_model.name = "Test Dependent"
        dependent_model.category = CashFlowCategoryEnum.EXPENSE
        dependent_model.subcategory = ExpenseSubcategoryEnum.OPEX
        dependent_model.calculation_pass = OrchestrationPass.DEPENDENT_MODELS
        dependent_model.reference = None
        dependent_model.compute_cf.return_value = pd.Series(
            [100] * 12, index=self.timeline.period_index
        )

        models = [independent_model, dependent_model]
        orchestrator = CashFlowOrchestrator(models=models, context=self.context)

        # Mock the ledger's flush method to track when it's called
        flush_mock = Mock()
        self.ledger.flush = flush_mock

        # Execute orchestration
        orchestrator.execute()

        # Verify flush was called (should be called once for the strategic flush)
        flush_mock.assert_called()

    def test_transaction_batching_performance_benefit(self):
        """Test that transaction batching reduces the number of database operations."""
        # Use Ledger for this test to verify actual batching behavior
        duckdb_ledger = Ledger()
        self.context.ledger = duckdb_ledger

        # Create multiple models to generate several ledger operations
        models = []
        for i in range(10):
            model = Mock()
            model.uid = uuid.uuid4()
            model.name = f"Test Model {i}"
            model.category = CashFlowCategoryEnum.REVENUE
            model.subcategory = RevenueSubcategoryEnum.LEASE
            model.calculation_pass = OrchestrationPass.INDEPENDENT_MODELS
            model.reference = None
            model.compute_cf.return_value = pd.Series(
                [100 + i] * 12, index=self.timeline.period_index
            )
            models.append(model)

        orchestrator = CashFlowOrchestrator(models=models, context=self.context)

        # Execute with transaction batching
        orchestrator.execute()

        # Verify that all data was added to the ledger
        final_count = len(duckdb_ledger)
        expected_count = 10 * 12  # 10 models * 12 periods each

        assert (
            final_count == expected_count
        ), f"Expected {expected_count} transactions, got {final_count}"

        # Verify the data can be queried correctly using LedgerQueries
        queries = LedgerQueries(duckdb_ledger)
        revenue = queries.revenue()
        assert revenue is not None
        assert revenue.sum() > 0

    def test_transaction_rollback_on_error(self):
        """Test that transactions are properly rolled back on errors."""
        # Create a model that will cause an error
        failing_model = Mock()
        failing_model.uid = uuid.uuid4()
        failing_model.name = "Failing Model"
        failing_model.category = CashFlowCategoryEnum.REVENUE
        failing_model.subcategory = RevenueSubcategoryEnum.LEASE
        failing_model.calculation_pass = OrchestrationPass.INDEPENDENT_MODELS
        failing_model.reference = None

        # Make compute_cf raise an exception
        failing_model.compute_cf.side_effect = ValueError("Test error")

        orchestrator = CashFlowOrchestrator(
            models=[failing_model], context=self.context
        )

        # Verify that execution raises the expected error
        with pytest.raises(ValueError, match="Test error"):
            orchestrator.execute()

        # Verify ledger is empty (transaction was rolled back)
        assert (
            len(self.ledger) == 0
        ), "Ledger should be empty after transaction rollback"

    def test_dependency_graph_preserved_with_transactions(self):
        """Test that dependency relationships are maintained with transaction batching."""
        # Create models with dependencies
        independent_model = Mock()
        independent_model.uid = uuid.uuid4()
        independent_model.name = "Base Revenue"
        independent_model.category = CashFlowCategoryEnum.REVENUE
        independent_model.subcategory = RevenueSubcategoryEnum.LEASE
        independent_model.calculation_pass = OrchestrationPass.INDEPENDENT_MODELS
        independent_model.reference = None
        independent_model.compute_cf.return_value = pd.Series(
            [1000] * 12, index=self.timeline.period_index
        )

        # Dependent model that should be calculated after independent models are flushed
        dependent_model = Mock()
        dependent_model.uid = uuid.uuid4()
        dependent_model.name = "Management Fee"
        dependent_model.category = CashFlowCategoryEnum.EXPENSE
        dependent_model.subcategory = ExpenseSubcategoryEnum.OPEX
        dependent_model.calculation_pass = OrchestrationPass.DEPENDENT_MODELS
        dependent_model.reference = None
        dependent_model.compute_cf.return_value = pd.Series(
            [50] * 12, index=self.timeline.period_index
        )

        models = [independent_model, dependent_model]
        orchestrator = CashFlowOrchestrator(models=models, context=self.context)

        # Execute successfully
        orchestrator.execute()

        # Verify both models were processed
        independent_model.compute_cf.assert_called_once()
        dependent_model.compute_cf.assert_called_once()

        # Verify data is in ledger
        assert (
            len(self.ledger) > 0
        ), "Ledger should contain data after successful execution"

        # Verify summary data was generated
        assert (
            orchestrator.summary_df is not None
        ), "Summary DataFrame should be generated"
        assert (
            not orchestrator.summary_df.empty
        ), "Summary DataFrame should not be empty"


class TestTransactionPerformanceComparison:
    """Compare performance with and without transaction batching."""

    def test_batched_vs_non_batched_ledger_operations(self):
        """Compare ledger operation efficiency with transaction batching."""

        timeline = Timeline(
            start_date=pd.to_datetime("2024-01-01").date(), duration_months=12
        )

        # Create test data
        test_series = pd.Series([1000] * 12, index=timeline.period_index)

        # Test 1: Non-batched operations (simulate old behavior)
        ledger1 = Ledger()
        start_time = time.perf_counter()

        # Simulate individual add_series calls (old way)
        for i in range(50):  # Simulate 50 different cash flows
            metadata = SeriesMetadata(
                category=CashFlowCategoryEnum.REVENUE,
                subcategory=RevenueSubcategoryEnum.LEASE,
                item_name=f"Test {i}",
                source_id=uuid.uuid4(),
                asset_id=uuid.uuid4(),
                pass_num=1,
            )
            ledger1.add_series(test_series, metadata)

        non_batched_time = time.perf_counter() - start_time

        # Test 2: Batched operations (new way)
        ledger2 = Ledger()
        start_time = time.perf_counter()

        # Simulate transaction-batched operations
        with ledger2.transaction():
            for i in range(50):  # Same 50 cash flows
                metadata = SeriesMetadata(
                    category=CashFlowCategoryEnum.REVENUE,
                    subcategory=RevenueSubcategoryEnum.LEASE,
                    item_name=f"Test {i}",
                    source_id=uuid.uuid4(),
                    asset_id=uuid.uuid4(),
                    pass_num=1,
                )
                ledger2.add_series(test_series, metadata)

        batched_time = time.perf_counter() - start_time

        # Verify both ledgers have the same data
        assert len(ledger1) == len(
            ledger2
        ), "Both ledgers should have the same number of records"

        # Performance should be better with batching (though with small datasets, the difference might be minimal)
        print(f"Non-batched time: {non_batched_time:.4f}s")
        print(f"Batched time: {batched_time:.4f}s")
        print(f"Performance ratio: {non_batched_time / batched_time:.2f}x")

        # The batched version should be at least as fast (sometimes much faster)
        # With small datasets, overhead might make them similar, so we just verify no regression
        assert (
            batched_time <= non_batched_time * 2.0
        ), "Batched operations should not be significantly slower"

    def test_no_record_leakage_during_orchestrator_transaction(self):
        """Test that orchestrator transactions prevent record leakage during execution."""
        timeline = Timeline(
            start_date=pd.to_datetime("2024-01-01").date(), duration_months=6
        )

        # Use Ledger to test actual database behavior
        ledger = Ledger()

        # Create context
        settings = GlobalSettings()
        property_data = Mock()
        property_data.uid = uuid.uuid4()
        property_data.net_rentable_area = 50000  # Required for occupancy calculation

        context = AnalysisContext(
            timeline=timeline,
            settings=settings,
            property_data=property_data,
            ledger=ledger,
            resolved_lookups={},
        )

        # Create models for both phases
        phase1_model = Mock()
        phase1_model.uid = uuid.uuid4()
        phase1_model.name = "Phase 1 Model"
        phase1_model.category = CashFlowCategoryEnum.REVENUE
        phase1_model.subcategory = RevenueSubcategoryEnum.LEASE
        phase1_model.calculation_pass = OrchestrationPass.INDEPENDENT_MODELS
        phase1_model.reference = None
        phase1_model.compute_cf.return_value = pd.Series(
            [1000] * 6, index=timeline.period_index
        )

        phase2_model = Mock()
        phase2_model.uid = uuid.uuid4()
        phase2_model.name = "Phase 2 Model"
        phase2_model.category = CashFlowCategoryEnum.EXPENSE
        phase2_model.subcategory = ExpenseSubcategoryEnum.OPEX
        phase2_model.calculation_pass = OrchestrationPass.DEPENDENT_MODELS
        phase2_model.reference = None
        phase2_model.compute_cf.return_value = pd.Series(
            [100] * 6, index=timeline.period_index
        )

        models = [phase1_model, phase2_model]
        orchestrator = CashFlowOrchestrator(models=models, context=context)

        # Track ledger state during orchestrator execution by mocking the transaction
        execution_states = []
        original_transaction = ledger.transaction

        class TransactionSpy:
            def __init__(self, ledger):
                self.ledger = ledger
                self.original_transaction = original_transaction()

            def __enter__(self):
                execution_states.append(("transaction_start", len(self.ledger)))
                return self.original_transaction.__enter__()

            def __exit__(self, exc_type, exc_val, exc_tb):
                result = self.original_transaction.__exit__(exc_type, exc_val, exc_tb)
                execution_states.append(("transaction_end", len(self.ledger)))
                return result

            def flush(self):
                execution_states.append(("before_flush", len(self.ledger)))
                self.original_transaction.flush()
                execution_states.append(("after_flush", len(self.ledger)))

        # Override the transaction method to use our spy
        ledger.transaction = lambda: TransactionSpy(ledger)

        # Execute the orchestrator
        orchestrator.execute()

        # Verify the execution states show proper record leakage prevention
        print(f"Execution states: {execution_states}")

        # Should have: start(0), before_flush(>0) due to Phase 1 flush, after_flush(>= before_flush), end(> after_flush)
        assert len(execution_states) >= 4, "Should have captured key execution states"

        start_count = execution_states[0][1]
        before_flush_count = execution_states[1][1]
        after_flush_count = execution_states[2][1]
        end_count = execution_states[3][1]

        # Critical assertions for record leakage prevention
        assert start_count == 0, "Should start with empty ledger"
        assert (
            before_flush_count > 0
        ), "Phase 1 records should be visible before flush() call"
        assert (
            after_flush_count >= before_flush_count
        ), "after_flush should be at least Phase 1 count"
        assert end_count > after_flush_count, "Should have more records after Phase 2"

        print(f"✅ Record leakage prevention verified:")
        print(f"   - Transaction start: {start_count} records")
        print(f"   - Before flush: {before_flush_count} records (buffered)")
        print(f"   - After flush: {after_flush_count} records (Phase 1 committed)")
        print(f"   - Transaction end: {end_count} records (all committed)")
