# Sign Convention - Canonical Reference

**Generated:** October 2, 2025  
**Source:** Phase 2, Step 2.1 - Establish Sign Convention  
**Purpose:** Canonical definition of sign conventions used throughout Performa ledger system  
**Status:** VERIFIED across all posting locations in Phase 1

---

## Overview

This document establishes the **single, unambiguous sign convention** used throughout the Performa ledger system. All amounts posted to the ledger follow this convention, and all queries interpret signs according to these rules.

**Key Principle:** The ledger records transactions from the **DEAL PERSPECTIVE** (not investor perspective).

---

## Core Convention: Deal Perspective

### Deal Perspective Definition

The ledger records all transactions from the perspective of the deal entity itself, answering the question:

> **"Is cash flowing INTO the deal or OUT OF the deal?"**

### Sign Rules

| Sign | Meaning | Examples |
|------|---------|----------|
| **Positive (+)** | Cash INTO the deal (sources/inflows) | Loan proceeds, equity contributions, rental income, sale proceeds |
| **Negative (-)** | Cash OUT OF the deal (uses/outflows) | Construction costs, operating expenses, debt service, equity distributions |

---

## Transaction Type Sign Reference

### Capital Source (Always Positive)

Cash flowing INTO the deal from capital sources:

| Transaction Type | Sign | Amount Example | Interpretation |
|------------------|------|----------------|----------------|
| Loan Proceeds | + | +$10,000,000 | Debt proceeds received |
| Refinancing Proceeds | + | +$12,000,000 | New loan proceeds received |
| Equity Contribution | + | +$5,000,000 | Partner capital invested |
| Sale Proceeds | + | +$25,000,000 | Disposition proceeds received |

**Rule:** All `flow_purpose='Capital Source'` transactions are POSITIVE.

---

### Capital Use (Always Negative)

Cash flowing OUT OF the deal for capital deployment:

| Transaction Type | Sign | Amount Example | Interpretation |
|------------------|------|----------------|----------------|
| Purchase Price | - | -$8,000,000 | Property acquisition cost |
| Closing Costs | - | -$240,000 | Acquisition fees paid |
| Hard Costs | - | -$21,772,800 | Construction costs paid |
| Soft Costs | - | -$955,908 | Development fees paid |
| Transaction Costs | - | -$1,284,751 | Disposition fees paid |

**Rule:** All `flow_purpose='Capital Use'` transactions are NEGATIVE.

---

### Operating (Mixed Signs)

Operating activities can produce both inflows (revenue) and outflows (expenses):

#### Operating Revenue (Positive)

| Transaction Type | Sign | Amount Example | Interpretation |
|------------------|------|----------------|----------------|
| Lease Revenue | + | +$100,000 | Rent received |
| Miscellaneous Income | + | +$5,000 | Parking/laundry income |
| Expense Recoveries | + | +$20,000 | CAM/tax reimbursements |

#### Operating Expenses (Negative)

| Transaction Type | Sign | Amount Example | Interpretation |
|------------------|------|----------------|----------------|
| OpEx | - | -$50,000 | Operating expenses paid |
| Vacancy Loss | - | -$10,000 | Revenue reduction (contra-revenue) |
| Credit Loss | - | -$2,500 | Bad debt allowance (contra-revenue) |

**Rule:** 
- `category='Revenue'` AND `flow_purpose='Operating'` → POSITIVE (or negative for contra-revenue)
- `category='Expense'` AND `flow_purpose='Operating'` → NEGATIVE

---

### Financing Service (Always Negative)

Cash flowing OUT OF the deal for debt service and equity returns:

| Transaction Type | Sign | Amount Example | Interpretation |
|------------------|------|----------------|----------------|
| Interest Payment | - | -$96,600 | Debt interest paid |
| Principal Payment | - | -$29,591 | Debt principal paid |
| Refinancing Payoff | - | -$21,964,868 | Old loan paid off |
| Prepayment | - | -$7,470,096 | Loan paid off at exit |
| Equity Distribution | - | -$391,822 | Distributions to partners |
| Preferred Return | - | -$50,000 | Pref return paid |
| Promote | - | -$100,000 | GP promote paid |

**Rule:** All `flow_purpose='Financing Service'` transactions are NEGATIVE.

---

### Valuation (Always Positive, Non-Cash)

Non-cash mark-to-market valuations:

| Transaction Type | Sign | Amount Example | Interpretation |
|------------------|------|----------------|----------------|
| Asset Valuation | + | +$29,312,596 | Property appraised value |

**Rule:** All `flow_purpose='Valuation'` transactions are POSITIVE but have **ZERO cash impact**.

---

## Investor Perspective vs Deal Perspective

### The Critical Distinction

| Perspective | Equity Contribution | Equity Distribution |
|-------------|-------------------|-------------------|
| **Deal** (Ledger) | +$5,000,000 (cash IN) | -$10,000,000 (cash OUT) |
| **Investor** (Reports) | -$5,000,000 (cash OUT of pocket) | +$10,000,000 (cash IN to pocket) |

### Sign Flip for Investor Reports

When presenting cash flows to investors, signs must be FLIPPED:

```python
# Deal perspective (ledger)
equity_contribution = +5_000_000  # Deal receives cash
equity_distribution = -10_000_000  # Deal pays out cash

# Investor perspective (reports)
investor_contribution = -equity_contribution  # = -5M (investor pays)
investor_distribution = -equity_distribution  # = +10M (investor receives)
```

**Implementation:** 
- `results.equity_cash_flow` property applies sign flip: `return -1 * equity_partner_flows()`
- User requirement: "levered_cash_flow is the project-level aggregate of each disaggregated partner's equity cash flows"

---

## Special Cases and Edge Cases

### 1. Cash-Out Refinancing

**Scenario:** New loan proceeds exceed old loan payoff

```
Refinancing Proceeds:  +$22,224,978  (cash IN to deal)
Refinancing Payoff:    -$21,964,868  (cash OUT from deal)
Net cash to deal:      +$260,110     (excess cash)
```

**Treatment:** 
- Both transactions posted separately with correct signs
- Net excess typically distributed to equity partners
- Equity distribution posted separately: -$260,110

**Net effect:** Refinancing brings excess cash into deal, which then flows out as equity distribution.

---

### 2. Capitalized Interest

**Scenario:** Construction loan interest capitalized (not paid in cash)

```
Capitalized Interest: -$100,000 (posted as Soft Costs, Capital Use)
```

**Treatment:**
- Posted as negative (capital deployment)
- Category: `Capital`
- Subcategory: `Soft Costs`
- Flow Purpose: `Capital Use`
- Increases project cost basis
- Does not impact cash flow during construction (paid at refi/disposition)

---

### 3. Contra-Revenue Accounts

**Scenario:** Vacancy loss and credit loss reduce gross revenue

```
Gross Revenue:    +$1,000,000
Vacancy Loss:     -$50,000     (contra-revenue, negative)
Credit Loss:      -$10,000     (contra-revenue, negative)
Effective Revenue: +$940,000
```

**Treatment:**
- Vacancy/credit losses posted as negative amounts
- Category: `Revenue`
- Flow Purpose: `Operating`
- Sign: Negative (revenue reduction)

---

### 4. Zero-Amount Transactions

**Scenario:** Construction loan principal payments (interest-only period)

```
Interest Payment:  -$50,000 (actual cash outflow)
Principal Payment: $0       (zero during IO period)
```

**Treatment:**
- Zero-amount series still posted to ledger
- Maintains consistent transaction structure
- Simplifies balance tracking and queries

---

## Sign Verification Rules

### At Posting Time

When posting to ledger, verify:

1. **Capital sources are positive**: Loan proceeds, equity contributions, sale proceeds
2. **Capital uses are negative**: Purchase price, construction costs, transaction costs
3. **Revenue is positive**: Rental income, misc income (except contra-revenue)
4. **Expenses are negative**: OpEx, interest, principal, distributions
5. **Financing inflows are positive**: Only if categorized as Capital Source
6. **Financing outflows are negative**: Debt service, equity distributions

### Code Pattern

```python
# Good: Explicit negation at posting
purchase_price = 8_000_000
purchase_series = pd.Series([-purchase_price], ...)  # ✅ Explicit negative

# Good: Direct negative construction
debt_service = -50_000  # ✅ Already negative

# Bad: Confusing double negation
equity_distribution = 100_000
posted_amount = -(-equity_distribution)  # ❌ Confusing, avoid
```

---

## Query Sign Handling

### General Principle

Queries should return amounts with ledger signs UNLESS:
1. Explicitly converting to investor perspective
2. Calculating absolute values for summaries
3. Applying mathematical operations that require sign flips

### Query-Specific Rules

| Query Method | Returns | Sign Convention |
|--------------|---------|-----------------|
| `noi()` | Net operating income | Algebraic sum (pos - neg) |
| `debt_service()` | Debt payments | Negative (outflows) |
| `debt_draws()` | Debt proceeds | Positive (inflows) |
| `project_cash_flow()` | Unlevered CF | Mixed (sources pos, uses neg) |
| `levered_cash_flow` | Levered CF (deal) | Mixed (sources pos, uses neg) |
| `equity_cash_flow` | Investor equity CF | **FLIPPED** (contributions neg, dist pos) |
| `equity_partner_flows()` | Deal equity flows | NOT flipped (contributions pos, dist neg) |

### Critical Distinction

```python
# Deal perspective (no flip)
equity_partner_flows()  # Contributions +, Distributions -

# Investor perspective (flipped)
equity_cash_flow = -1 * equity_partner_flows()  # Contributions -, Distributions +
```

---

## Validation and Testing

### Unit Test Pattern

```python
def test_sign_convention():
    """Verify sign conventions for all transaction types."""
    
    # Capital sources should be positive
    assert loan_proceeds > 0
    assert equity_contribution > 0
    assert sale_proceeds > 0
    
    # Capital uses should be negative
    assert purchase_price < 0
    assert hard_costs < 0
    assert transaction_costs < 0
    
    # Financing service should be negative
    assert interest_payment < 0
    assert equity_distribution < 0
    
    # Operating revenue should be positive
    assert rental_income > 0
    
    # Operating expenses should be negative
    assert opex < 0
```

### Ledger Balance Check

```python
def check_ledger_balance(ledger_df):
    """
    Check that ledger totals make sense.
    
    Note: Ledger is NOT double-entry, so won't sum to zero.
    Excess of sources over uses = profit/excess capital.
    """
    sources = ledger_df[
        ledger_df['flow_purpose'] == 'Capital Source'
    ]['amount'].sum()
    
    uses = ledger_df[
        ledger_df['flow_purpose'].isin(['Capital Use', 'Financing Service'])
    ]['amount'].sum()
    
    operating = ledger_df[
        ledger_df['flow_purpose'] == 'Operating'
    ]['amount'].sum()
    
    # Sources should be positive
    assert sources > 0
    
    # Uses should be negative
    assert uses < 0
    
    # Net should be positive for profitable deal
    net = sources + uses + operating
    # (No assertion on net - can be pos or neg depending on deal)
```

---

## Common Mistakes and Anti-Patterns

### ❌ Mistake 1: Forgetting to Negate at Posting

```python
# Wrong: Posting capital use as positive
hard_costs = 1_000_000
ledger.add_series(pd.Series([hard_costs], ...), ...)  # ❌ Should be negative

# Correct: Negate at posting
hard_costs = 1_000_000
ledger.add_series(pd.Series([-hard_costs], ...), ...)  # ✅ Explicit negative
```

### ❌ Mistake 2: Double-Negating in Queries

```python
# Wrong: Query already returns negative debt service
debt_service = queries.debt_service()  # Returns negative values
total_outflows = -debt_service  # ❌ Makes them positive!

# Correct: Use as-is or take absolute value
debt_service = queries.debt_service()  # Returns negative values
total_outflows = abs(debt_service.sum())  # ✅ Absolute value for display
```

### ❌ Mistake 3: Mixing Perspectives

```python
# Wrong: Mixing deal and investor perspectives
levered_cf = project_cf + debt_draws + debt_service  # Deal perspective
investor_cf = equity_partner_flows()  # Also deal perspective
assert levered_cf == investor_cf  # ❌ Wrong! Need to flip investor_cf

# Correct: Consistent perspective
levered_cf = project_cf + debt_draws + debt_service  # Deal perspective
deal_equity_flows = equity_partner_flows()  # Deal perspective
assert levered_cf.sum() ≈ deal_equity_flows.sum()  # ✅ Both deal perspective
```

### ❌ Mistake 4: Assuming Ledger Balances to Zero

```python
# Wrong: Expecting double-entry balance
total = ledger_df['amount'].sum()
assert total == 0  # ❌ Ledger is NOT double-entry!

# Correct: Check for economic plausibility
sources = sum(positive amounts)
uses = sum(negative amounts)
profit = sources + uses + operating  # Can be positive (profit) or negative (loss)
```

---

## Industry Standards Alignment

### ARGUS Compatibility

Performa's sign convention aligns with ARGUS Enterprise:
- Sources (inflows) are positive
- Uses (outflows) are negative
- Investor reports flip signs for equity flows

### REFM (Real Estate Financial Modeling) Standards

Aligns with Excel-based REFM conventions:
- Cash IN to deal is positive
- Cash OUT from deal is negative
- IRR calculations use investor-flipped signs

### Institutional Reporting

Compatible with NCREIF and GIPS standards:
- Contributions to fund: negative (investor perspective)
- Distributions from fund: positive (investor perspective)
- Requires sign flip from ledger (deal perspective) to investor reports

---

## Documentation Requirements

### Code Comments

Every posting location should include a comment indicating expected sign:

```python
# Good: Clear sign indication
purchase_series = pd.Series(
    [-purchase_price],  # Negative: capital outflow from deal
    ...
)

loan_proceeds_series = pd.Series(
    [loan_amount],  # Positive: capital inflow to deal
    ...
)
```

### Docstrings

Query methods should document sign conventions:

```python
def debt_service(self) -> pd.Series:
    """
    Monthly debt service payments (interest + principal).
    
    Returns:
        Time series of debt service amounts.
        Sign: NEGATIVE (cash outflow from deal)
    """
```

---

## Migration and Compatibility

### Legacy Code

If migrating from systems with different conventions:

1. **Identify current convention** in legacy system
2. **Document mapping** between old and new signs
3. **Apply transformation** at data import boundary
4. **Validate** with known test cases

### Example Migration

```python
# Legacy system: Contributions are negative, distributions are positive
legacy_contribution = -5_000_000
legacy_distribution = +10_000_000

# Performa: Flip for deal perspective
performa_contribution = -legacy_contribution  # +5M (deal receives)
performa_distribution = -legacy_distribution  # -10M (deal pays out)
```

---

## Summary Table: All Transaction Types

| Category | Subcategory | Flow Purpose | Sign | Example |
|----------|-------------|--------------|------|---------|
| Capital | Purchase Price | Capital Use | - | -$8,000,000 |
| Capital | Closing Costs | Capital Use | - | -$240,000 |
| Capital | Hard Costs | Capital Use | - | -$21,772,800 |
| Capital | Soft Costs | Capital Use | - | -$955,908 |
| Capital | Transaction Costs | Capital Use | - | -$1,284,751 |
| Expense | OpEx | Operating | - | -$5,302,838 |
| Financing | Equity Contribution | Capital Source | + | +$9,676,038 |
| Financing | Loan Proceeds | Capital Source | + | +$21,964,868 |
| Financing | Refinancing Proceeds | Capital Source | + | +$22,224,978 |
| Financing | Equity Distribution | Financing Service | - | -$66,217,993 |
| Financing | Interest Payment | Financing Service | - | -$8,114,376 |
| Financing | Principal Payment | Financing Service | - | -$2,485,667 |
| Financing | Refinancing Payoff | Financing Service | - | -$21,964,868 |
| Financing | Prepayment | Financing Service | - | -$7,470,096 |
| Revenue | Sale | Capital Source | + | +$42,825,042 |
| Revenue | Lease | Operating | + | +$14,077,660 |
| Revenue | Credit Loss | Operating | - | -$152,750 |
| Revenue | Vacancy Loss | Operating | - | -$763,750 |
| Valuation | Asset Valuation | Valuation | + | +$2,491,570,642 |

---

## Glossary

- **Deal Perspective**: Recording transactions from the deal entity's viewpoint (cash in vs cash out)
- **Investor Perspective**: Recording transactions from the investor's viewpoint (opposite signs)
- **Capital Source**: Money coming INTO the deal from external sources
- **Capital Use**: Money going OUT OF the deal for capital deployment
- **Financing Service**: Ongoing obligations to debt and equity holders
- **Contra-Revenue**: Negative revenue adjustments (vacancy loss, credit loss)
- **Sign Flip**: Multiplying by -1 to convert between deal and investor perspectives

---

## Validation Status

- ✅ **Phase 1 Verification**: All 19 transaction types verified for consistent signs
- ✅ **Code Audit**: All posting locations follow this convention
- ✅ **Query Audit**: All queries interpret signs correctly
- ✅ **Test Coverage**: Unit tests validate sign conventions

---

**Document Status**: Phase 2, Step 2.1 COMPLETE ✅

**Last Updated:** October 2, 2025

**Maintenance:** Update this document if new transaction types are added or sign conventions change.

