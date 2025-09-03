# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Tests for the LedgerQueries class.

This module tests the query layer that replaces complex aggregation logic
with simple pandas operations on the transactional ledger.
"""

from datetime import date
from uuid import uuid4

import pandas as pd
import pytest

from performa.core.ledger.queries import LedgerQueries


def create_test_ledger() -> pd.DataFrame:
    """Create a sample ledger for testing."""
    
    return pd.DataFrame([
        # Operating Revenue - Lease
        {
            'date': date(2024, 1, 1), 'amount': 10000, 'flow_purpose': 'Operating',
            'category': 'Revenue', 'subcategory': "Lease", 'item_name': 'Base Rent',
            'source_id': uuid4(), 'asset_id': uuid4(), 'pass_num': 1
        },
        {
            'date': date(2024, 2, 1), 'amount': 10000, 'flow_purpose': 'Operating',
            'category': 'Revenue', 'subcategory': "Lease", 'item_name': 'Base Rent',
            'source_id': uuid4(), 'asset_id': uuid4(), 'pass_num': 1
        },
        # Operating Revenue - Miscellaneous
        {
            'date': date(2024, 1, 1), 'amount': 500, 'flow_purpose': 'Operating',
            'category': 'Revenue', 'subcategory': "Miscellaneous", 'item_name': 'Parking Income',
            'source_id': uuid4(), 'asset_id': uuid4(), 'pass_num': 1
        },
        # Operating Expenses
        {
            'date': date(2024, 1, 1), 'amount': -2000, 'flow_purpose': 'Operating',
            'category': 'Expense', 'subcategory': "OpEx", 'item_name': 'Property Management',
            'source_id': uuid4(), 'asset_id': uuid4(), 'pass_num': 1
        },
        {
            'date': date(2024, 2, 1), 'amount': -2000, 'flow_purpose': 'Operating',
            'category': 'Expense', 'subcategory': "OpEx", 'item_name': 'Property Management',
            'source_id': uuid4(), 'asset_id': uuid4(), 'pass_num': 1
        },
        # Vacancy Loss
        {
            'date': date(2024, 1, 1), 'amount': -1000, 'flow_purpose': 'Operating',
            'category': 'Revenue', 'subcategory': "Vacancy Loss", 'item_name': 'Vacancy Loss',
            'source_id': uuid4(), 'asset_id': uuid4(), 'pass_num': 1
        },
        # Capital Use
        {
            'date': date(2024, 1, 1), 'amount': -50000, 'flow_purpose': 'Capital Use',
            'category': 'Capital', 'subcategory': 'Purchase Price', 'item_name': 'Acquisition',
            'source_id': uuid4(), 'asset_id': uuid4(), 'pass_num': 2
        },
        # Capital Source - Equity
        {
            'date': date(2024, 1, 1), 'amount': 30000, 'flow_purpose': 'Capital Source',
            'category': 'Financing', 'subcategory': 'Equity Contribution', 'item_name': 'Equity Contribution',
            'source_id': uuid4(), 'asset_id': uuid4(), 'pass_num': 2
        },
        # Capital Source - Debt
        {
            'date': date(2024, 1, 1), 'amount': 20000, 'flow_purpose': 'Capital Source',
            'category': 'Financing', 'subcategory': 'Loan Proceeds', 'item_name': 'Loan Proceeds',
            'source_id': uuid4(), 'asset_id': uuid4(), 'pass_num': 2
        },
        # Financing Service - Debt Service
        {
            'date': date(2024, 2, 1), 'amount': -800, 'flow_purpose': 'Financing Service',
            'category': 'Financing', 'subcategory': 'Debt Service', 'item_name': 'Debt Service',
            'source_id': uuid4(), 'asset_id': uuid4(), 'pass_num': 2
        },
        # Tenant Improvements (by name pattern)
        {
            'date': date(2024, 1, 1), 'amount': -5000, 'flow_purpose': 'Capital Use',
            'category': 'Capital', 'subcategory': 'Other', 'item_name': 'TI Allowance - Suite 100',
            'source_id': uuid4(), 'asset_id': uuid4(), 'pass_num': 2
        },
        # Leasing Commissions (by name pattern)
        {
            'date': date(2024, 1, 1), 'amount': -2000, 'flow_purpose': 'Capital Use',
            'category': 'Capital', 'subcategory': 'Other', 'item_name': 'LC Payment - Broker',
            'source_id': uuid4(), 'asset_id': uuid4(), 'pass_num': 2
        },
    ])


class TestLedgerQueries:  # noqa: PLR0904 (ignore too many public methods)
    """Test suite for LedgerQueries class."""
    
    def test_init_validates_schema(self):
        """Test that initialization validates required columns."""
        # Valid ledger should work
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)
        assert isinstance(queries, LedgerQueries)
        
        # Missing required columns should fail
        invalid_ledger = pd.DataFrame({'invalid_col': [1, 2, 3]})
        with pytest.raises(ValueError, match="missing required columns"):
            LedgerQueries(invalid_ledger)
    
    def test_pgr_calculation(self):
        """Test Potential Gross Revenue calculation."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)
        
        pgr = queries.pgr()
        
        # Industry standard: PGR includes all revenue at 100% occupancy
        # January: $10,000 lease + $500 misc = $10,500
        # February: $10,000 lease only = $10,000
        assert pgr.loc[date(2024, 1, 1)] == 10500
        assert pgr.loc[date(2024, 2, 1)] == 10000
    
    def test_vacancy_loss_calculation(self):
        """Test vacancy loss calculation."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)
        
        vacancy = queries.vacancy_loss()
        
        # Should be 1,000 for January (absolute value of -1000)
        assert vacancy.loc[date(2024, 1, 1)] == 1000
    
    def test_egi_calculation(self):
        """Test Effective Gross Income calculation."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)
        
        egi = queries.egi()
        
        # January: 10,000 (lease) + 500 (misc) - 1,000 (vacancy) = 9,500
        assert egi.loc[date(2024, 1, 1)] == 9500
        # February: 10,000 (lease) + 0 (misc) - 0 (vacancy) = 10,000
        assert egi.loc[date(2024, 2, 1)] == 10000
    
    def test_opex_calculation(self):
        """Test operating expenses calculation."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)
        
        opex = queries.opex()
        
        # Should be 2,000 for both January and February (absolute value)
        assert opex.loc[date(2024, 1, 1)] == 2000
        assert opex.loc[date(2024, 2, 1)] == 2000
    
    def test_noi_calculation(self):
        """Test Net Operating Income calculation."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)
        
        noi = queries.noi()
        
        # January: 10,000 + 500 - 1,000 (vacancy) revenue - 2,000 expense = 7,500
        # Note: vacancy is negative revenue, so total revenue = 10,000 + 500 - 1,000 = 9,500
        assert noi.loc[date(2024, 1, 1)] == 7500
        # February: 10,000 revenue - 2,000 expense = 8,000 (no vacancy)
        assert noi.loc[date(2024, 2, 1)] == 8000
    
    def test_noi_equals_revenue_minus_expense(self):
        """NOI should equal revenue minus expenses from operating flows."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)
        
        # Calculate manually
        operating = ledger[ledger['flow_purpose'] == 'Operating']
        revenue_txns = operating[operating['category'] == 'Revenue']
        expense_txns = operating[operating['category'] == 'Expense']
        
        manual_revenue = revenue_txns.groupby('date')['amount'].sum()
        manual_expense = expense_txns.groupby('date')['amount'].sum().abs()
        manual_noi = manual_revenue - manual_expense
        
        # Compare with query result
        query_noi = queries.noi()
        
        for date_key in manual_noi.index:
            assert abs(query_noi.loc[date_key] - manual_noi.loc[date_key]) < 0.01
    
    def test_capex_calculation(self):
        """Test capital expenditures calculation."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)
        
        capex = queries.capex()
        
        # Should include the acquisition (50,000) but exclude TI/LC (they're identified by name pattern)
        # Based on our test data: acquisition = 50,000, TI and LC are excluded
        assert capex.loc[date(2024, 1, 1)] == 50000
    
    def test_ti_calculation(self):
        """Test tenant improvements calculation (pattern matching)."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)
        
        ti = queries.ti()
        
        # Should find the "TI Allowance" item
        assert ti.loc[date(2024, 1, 1)] == 5000
    
    def test_lc_calculation(self):
        """Test leasing commissions calculation (pattern matching)."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)
        
        lc = queries.lc()
        
        # Should find the "LC Payment" item
        assert lc.loc[date(2024, 1, 1)] == 2000
    
    def test_ucf_calculation(self):
        """Test Unlevered Cash Flow calculation."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)
        
        ucf = queries.ucf()
        noi = queries.noi()
        capex = queries.capex()
        ti = queries.ti()
        lc = queries.lc()
        
        # Test that UCF calculation works and produces expected results
        # For January: NOI = 7500, CapEx = 50000, TI = 5000, LC = 2000  
        # UCF = 7500 - 50000 - 5000 - 2000 = -49500
        assert ucf.loc[date(2024, 1, 1)] == 7500 - 50000 - 5000 - 2000
        
        # For February: NOI = 8000, CapEx = 0, TI = 0, LC = 0
        # UCF = 8000 - 0 - 0 - 0 = 8000
        assert ucf.loc[date(2024, 2, 1)] == 8000
    
    def test_total_uses_calculation(self):
        """Test total uses calculation."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)
        
        uses = queries.total_uses()
        
        # January: 50,000 (acquisition) + 5,000 (TI) + 2,000 (LC) = 57,000
        assert uses.loc[date(2024, 1, 1)] == 57000
        # February: 800 (debt service) = 800
        assert uses.loc[date(2024, 2, 1)] == 800
    
    def test_total_sources_calculation(self):
        """Test total sources calculation."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)
        
        sources = queries.total_sources()
        
        # January: 30,000 (equity) + 20,000 (debt) = 50,000
        assert sources.loc[date(2024, 1, 1)] == 50000
    
    def test_debt_draws_calculation(self):
        """Test debt draws calculation."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)
        
        debt_draws = queries.debt_draws()
        
        # Should be 20,000 for January
        assert debt_draws.loc[date(2024, 1, 1)] == 20000
    
    def test_equity_contributions_calculation(self):
        """Test equity contributions calculation."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)
        
        equity = queries.equity_contributions()
        
        # Should be 30,000 for January
        assert equity.loc[date(2024, 1, 1)] == 30000
    
    def test_debt_service_calculation(self):
        """Test debt service calculation."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)
        
        debt_service = queries.debt_service()
        
        # Should be 800 for February (absolute value)
        assert debt_service.loc[date(2024, 2, 1)] == 800
    
    def test_uses_breakdown(self):
        """Test uses breakdown by subcategory."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)
        
        breakdown = queries.uses_breakdown()
        
        # Should have breakdown by subcategory
        assert breakdown.loc[date(2024, 1, 1), 'Purchase Price'] == 50000
        assert breakdown.loc[date(2024, 1, 1), 'Other'] == 7000  # TI + LC
        assert breakdown.loc[date(2024, 2, 1), 'Debt Service'] == 800
    
    def test_sources_breakdown(self):
        """Test sources breakdown by subcategory."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)
        
        breakdown = queries.sources_breakdown()
        
        # Should have breakdown by subcategory
        assert breakdown.loc[date(2024, 1, 1), 'Equity Contribution'] == 30000
        assert breakdown.loc[date(2024, 1, 1), 'Loan Proceeds'] == 20000
    
    def test_empty_ledger_handling(self):
        """Test that queries handle empty ledgers gracefully."""
        empty_ledger = pd.DataFrame(columns=[
            'date', 'amount', 'flow_purpose', 'category', 'subcategory', 'item_name'
        ])
        queries = LedgerQueries(empty_ledger)
        
        # All queries should return empty Series without errors
        assert queries.noi().empty
        assert queries.pgr().empty
        assert queries.egi().empty
        assert queries.total_uses().empty
        assert queries.total_sources().empty
    
    def test_partner_flows(self):
        """Test partner-specific flow queries."""
        ledger = create_test_ledger()
        
        # Add partner entity data
        partner_id = uuid4()
        ledger.loc[0, 'entity_id'] = partner_id
        ledger.loc[0, 'entity_type'] = 'GP'
        
        queries = LedgerQueries(ledger)
        
        partner_flows = queries.partner_flows(partner_id)
        
        # Should return the flow for that partner
        assert partner_flows.loc[date(2024, 1, 1)] == 10000
    
    def test_query_consistency_across_methods(self):
        """Test that related queries are consistent with each other."""
        ledger = create_test_ledger()
        queries = LedgerQueries(ledger)
        
        # Uses should equal sum of breakdown
        uses = queries.total_uses()
        uses_breakdown = queries.uses_breakdown()
        
        for date_key in uses.index:
            breakdown_sum = uses_breakdown.loc[date_key].sum()
            assert abs(uses.loc[date_key] - breakdown_sum) < 0.01
        
        # Sources should equal sum of breakdown
        sources = queries.total_sources()
        sources_breakdown = queries.sources_breakdown()
        
        for date_key in sources.index:
            breakdown_sum = sources_breakdown.loc[date_key].sum()
            assert abs(sources.loc[date_key] - breakdown_sum) < 0.01

    def test_rental_abatement_calculation(self):
        """Test rental abatement calculation."""
        # Create ledger with abatement data
        ledger = pd.DataFrame([
            {
                'date': date(2024, 1, 1), 'amount': -500, 'flow_purpose': 'Operating',
                'category': 'Revenue', 'subcategory': 'Abatement', 'item_name': 'Free Rent Period',
                'source_id': uuid4(), 'asset_id': uuid4(), 'pass_num': 1
            },
            {
                'date': date(2024, 2, 1), 'amount': -300, 'flow_purpose': 'Operating',
                'category': 'Revenue', 'subcategory': 'Abatement', 'item_name': 'Concession',
                'source_id': uuid4(), 'asset_id': uuid4(), 'pass_num': 1
            }
        ])
        queries = LedgerQueries(ledger)
        
        abatement = queries.rental_abatement()
        
        # Should return absolute values (positive amounts)
        assert abatement.loc[date(2024, 1, 1)] == 500
        assert abatement.loc[date(2024, 2, 1)] == 300

    def test_collection_loss_calculation(self):
        """Test collection loss calculation."""
        # Create ledger with collection loss data
        ledger = pd.DataFrame([
            {
                'date': date(2024, 1, 1), 'amount': -200, 'flow_purpose': 'Operating',
                'category': 'Revenue', 'subcategory': "Credit Loss", 'item_name': 'Bad Debt',
                'source_id': uuid4(), 'asset_id': uuid4(), 'pass_num': 1
            },
            {
                'date': date(2024, 2, 1), 'amount': -150, 'flow_purpose': 'Operating',
                'category': 'Revenue', 'subcategory': "Credit Loss", 'item_name': 'Uncollectible',
                'source_id': uuid4(), 'asset_id': uuid4(), 'pass_num': 1
            }
        ])
        queries = LedgerQueries(ledger)
        
        collection = queries.credit_loss()
        
        # Should return absolute values (positive amounts)
        assert collection.loc[date(2024, 1, 1)] == 200
        assert collection.loc[date(2024, 2, 1)] == 150

    def test_misc_income_calculation(self):
        """Test miscellaneous income calculation."""
        # Create ledger with misc income data
        ledger = pd.DataFrame([
            {
                'date': date(2024, 1, 1), 'amount': 100, 'flow_purpose': 'Operating',
                'category': 'Revenue', 'subcategory': 'Miscellaneous', 'item_name': 'Parking Fees',
                'source_id': uuid4(), 'asset_id': uuid4(), 'pass_num': 1
            },
            {
                'date': date(2024, 2, 1), 'amount': 75, 'flow_purpose': 'Operating',
                'category': 'Revenue', 'subcategory': 'Miscellaneous', 'item_name': 'Laundry Income',
                'source_id': uuid4(), 'asset_id': uuid4(), 'pass_num': 1
            }
        ])
        queries = LedgerQueries(ledger)
        
        misc = queries.misc_income()
        
        # Should return positive amounts as-is
        assert misc.loc[date(2024, 1, 1)] == 100
        assert misc.loc[date(2024, 2, 1)] == 75

    def test_expense_reimbursements_calculation(self):
        """Test expense reimbursements calculation."""
        # Create ledger with reimbursement data
        ledger = pd.DataFrame([
            {
                'date': date(2024, 1, 1), 'amount': 250, 'flow_purpose': 'Operating',
                'category': 'Revenue', 'subcategory': 'Recovery', 'item_name': 'CAM Recovery',
                'source_id': uuid4(), 'asset_id': uuid4(), 'pass_num': 1
            },
            {
                'date': date(2024, 2, 1), 'amount': 300, 'flow_purpose': 'Operating',
                'category': 'Revenue', 'subcategory': 'Recovery', 'item_name': 'Tax Recovery',
                'source_id': uuid4(), 'asset_id': uuid4(), 'pass_num': 1
            }
        ])
        queries = LedgerQueries(ledger)
        
        reimburse = queries.expense_reimbursements()
        
        # Should return positive amounts as-is
        assert reimburse.loc[date(2024, 1, 1)] == 250
        assert reimburse.loc[date(2024, 2, 1)] == 300

    def test_new_methods_with_empty_ledger(self):
        """Test that new methods handle empty ledgers gracefully."""
        empty_ledger = pd.DataFrame({
            'date': [],
            'amount': [],
            'flow_purpose': [],
            'category': [],
            'subcategory': [],
            'item_name': []
        })
        queries = LedgerQueries(empty_ledger)
        
        # All methods should return empty Series without errors
        assert queries.rental_abatement().empty
        assert queries.credit_loss().empty
        assert queries.misc_income().empty
        assert queries.expense_reimbursements().empty
