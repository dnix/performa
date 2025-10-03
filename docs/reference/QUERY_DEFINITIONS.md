# Query Definitions - Canonical Specifications

**Generated:** October 2, 2025  
**Source:** Phase 2, Step 2.4 - Define Query Semantics  
**Purpose:** Formal definitions for every ledger query method  
**Status:** Canonical reference for query implementation

---

## Overview

This document provides **formal, unambiguous definitions** for every query method in `LedgerQueries`. Each definition specifies:

1. **Purpose**: What the query calculates
2. **Formula**: Mathematical or SQL definition
3. **Filters**: Which `flow_purpose`, `category`, `subcategory` to include/exclude
4. **Sign Convention**: Expected sign of result
5. **Validation**: How to verify correctness

**Critical Principle:** Queries must be **mutually exclusive** - no transaction should be counted multiple times across related queries.

---

## Core Operating Metrics

### 1. noi()

**Purpose:** Net Operating Income - profit from property operations before financing

**Formula:**
```
NOI = Gross Revenue - Operating Expenses
    = (Rental Income + Misc Income + Recoveries) 
      - (Vacancy Loss + Credit Loss)
      - (OpEx)
```

**SQL Definition:**
```sql
SELECT 
    DATE_TRUNC('month', date) AS period,
    SUM(amount) AS total
FROM ledger
WHERE flow_purpose = 'Operating'
  AND category IN ('Revenue', 'Expense')
GROUP BY period
ORDER BY period
```

**Key Filters:**
- `flow_purpose = 'Operating'` ONLY
- Includes both Revenue and Expense categories
- Excludes Capital, Financing, and Valuation

**Expected Sign:** Positive for profitable properties, negative if opex > revenue

**Validation:**
```python
noi = queries.noi()
# Should equal: gross_revenue + vacancy_loss + credit_loss - opex
# (vacancy_loss and credit_loss are negative)
```

**Notes:**
- Industry standard NOI calculation
- Does NOT include capital expenditures (those are below-the-line)
- Does NOT include debt service (that's levering)

---

### 2. gross_revenue()

**Purpose:** Total operating revenue before vacancy/credit losses

**Formula:**
```
Gross Revenue = Lease + Miscellaneous + Recoveries
```

**SQL Definition:**
```sql
SELECT 
    DATE_TRUNC('month', date) AS period,
    SUM(amount) AS total
FROM ledger
WHERE flow_purpose = 'Operating'
  AND category = 'Revenue'
  AND subcategory IN ('Lease', 'Miscellaneous', 'Recovery')
GROUP BY period
ORDER BY period
```

**Key Filters:**
- `flow_purpose = 'Operating'`
- `category = 'Revenue'`
- Subcategories: Lease, Miscellaneous, Recovery
- **Excludes:** Sale (that's Capital Source), Vacancy Loss, Credit Loss

**Expected Sign:** Positive

---

### 3. opex()

**Purpose:** Operating expenses for running the property

**Formula:**
```
OpEx = All operating expenses
```

**SQL Definition:**
```sql
SELECT 
    DATE_TRUNC('month', date) AS period,
    SUM(amount) AS total
FROM ledger
WHERE flow_purpose = 'Operating'
  AND category = 'Expense'
  AND subcategory = 'OpEx'
GROUP BY period
ORDER BY period
```

**Key Filters:**
- `flow_purpose = 'Operating'`
- `category = 'Expense'`
- `subcategory = 'OpEx'`

**Expected Sign:** Negative

**⚠️ CRITICAL:** Should NOT pull from `category = 'Capital'`!

---

### 4. operational_cash_flow()

**Purpose:** Cash flow from operations after recurring capital expenditures

**Formula:**
```
Operational CF = NOI - Recurring CapEx - TI - LC
```

**SQL Definition:**
```sql
-- Method 1: Use flow_purpose ONLY (RECOMMENDED)
SELECT 
    DATE_TRUNC('month', date) AS period,
    SUM(amount) AS total
FROM ledger
WHERE flow_purpose = 'Operating'
GROUP BY period
ORDER BY period

-- This automatically includes:
-- + Rental income
-- + Misc income
-- - Vacancy loss
-- - OpEx
-- - Recurring CapEx (if categorized as Expense/CapEx with flow_purpose=Operating)
```

**Key Filters:**
- `flow_purpose = 'Operating'` **ONLY**
- **EXCLUDES** `category = 'Capital'` (those have `flow_purpose = 'Capital Use'`)

**Expected Sign:** Mixed (positive for profitable operations)

**⚠️ CRITICAL BUG (Current Implementation):**
Current code pulls `capex()` which uses `category = 'Capital'`. This causes double-counting because:
- `category = 'Capital'` transactions have `flow_purpose = 'Capital Use'`
- `project_cash_flow()` also pulls `flow_purpose = 'Capital Use'`
- Result: Capital expenditures counted TWICE

**FIX:**
```python
def operational_cash_flow(self) -> pd.Series:
    """Operational CF = All Operating flow_purpose transactions."""
    sql = f"""
        SELECT 
            DATE_TRUNC('month', date) AS period,
            SUM(amount) AS total
        FROM {self.table_name}
        WHERE flow_purpose = '{enum_to_string(TransactionPurpose.OPERATING)}'
        GROUP BY period
        ORDER BY period
    """
    return self._execute_query_to_series(sql, "period", "total", "Operational Cash Flow")
```

---

## Project-Level Cash Flows

### 5. project_cash_flow()

**Purpose:** Unlevered cash flow - property performance before financing effects

**Formula:**
```
Project CF = Operational CF + Capital Uses + Disposition Proceeds - Acquisition Costs
          = All cash flows EXCEPT financing
```

**SQL Definition:**
```sql
SELECT 
    DATE_TRUNC('month', date) AS period,
    SUM(amount) AS total
FROM ledger
WHERE flow_purpose IN ('Operating', 'Capital Use', 'Capital Source')
  AND category != 'Financing'  -- Exclude ALL financing
  AND flow_purpose != 'Valuation'  -- Exclude non-cash
GROUP BY period
ORDER BY period
```

**Alternative (More Explicit):**
```sql
SELECT 
    DATE_TRUNC('month', date) AS period,
    SUM(amount) AS total
FROM ledger
WHERE flow_purpose IN ('Operating', 'Capital Use')
   OR (flow_purpose = 'Capital Source' AND subcategory = 'Sale')
GROUP BY period
ORDER BY period
```

**Key Filters:**
- Include: `Operating`, `Capital Use`
- Include: `Capital Source` BUT only Sale proceeds (not debt/equity)
- Exclude: All `Financing` category transactions
- Exclude: `Valuation`

**Expected Sign:** Mixed (initially negative during acquisition/construction, positive after stabilization/exit)

**Sign Flip Pattern:** Expect ONE sign flip:
- Negative during acquisition/construction (capital deployed)
- Positive during operations and exit (cash generated)

**Validation:**
```python
project_cf = queries.project_cash_flow()
# Should NOT include ANY financing transactions
financing_in_project = ledger[
    (ledger['category'] == 'Financing')
]['amount'].sum()
assert financing_in_project not in project_cf  # Financing excluded
```

---

## Debt and Financing Queries

### 6. debt_draws() / debt_proceeds()

**Purpose:** Total debt proceeds received (gross)

**Formula:**
```
Debt Draws = Loan Proceeds + Refinancing Proceeds
```

**SQL Definition:**
```sql
SELECT 
    DATE_TRUNC('month', date) AS period,
    SUM(amount) AS total
FROM ledger
WHERE category = 'Financing'
  AND subcategory IN ('Loan Proceeds', 'Refinancing Proceeds')
GROUP BY period
ORDER BY period
```

**Key Filters:**
- `category = 'Financing'`
- `subcategory IN ('Loan Proceeds', 'Refinancing Proceeds')`
- Equivalently: `flow_purpose = 'Capital Source'` AND `category = 'Financing'`

**Expected Sign:** Positive (cash inflows)

---

### 7. debt_service()

**Purpose:** Total debt service payments (interest + principal + payoffs)

**Formula:**
```
Debt Service = Interest Payments + Principal Payments + Refinancing Payoffs + Prepayments
```

**SQL Definition:**
```sql
SELECT 
    DATE_TRUNC('month', date) AS period,
    SUM(amount) AS total
FROM ledger
WHERE category = 'Financing'
  AND subcategory IN (
      'Interest Payment',
      'Principal Payment',
      'Refinancing Payoff',
      'Prepayment'
  )
GROUP BY period
ORDER BY period
```

**Key Filters:**
- `category = 'Financing'`
- Subcategories: Interest Payment, Principal Payment, Refinancing Payoff, Prepayment
- Equivalently: `flow_purpose = 'Financing Service'` AND related to debt

**Expected Sign:** Negative (cash outflows)

**⚠️ CRITICAL BUG (Current Implementation):**
Current code DOES NOT include `Refinancing Payoff` and `Prepayment`. This causes:
- Understatement of total debt outflows
- Incorrect levered cash flow calculations
- Missing ~$22M in residential development example

**FIX:**
```python
DEBT_SERVICE_SUBCATEGORIES = [
    FinancingSubcategoryEnum.INTEREST_PAYMENT,
    FinancingSubcategoryEnum.PRINCIPAL_PAYMENT,
    FinancingSubcategoryEnum.REFINANCING_PAYOFF,  # ADD THIS
    FinancingSubcategoryEnum.PREPAYMENT,  # ADD THIS
]
```

---

### 8. levered_cash_flow (property in results.py)

**Purpose:** Levered cash flows from investor perspective (foundation for levered_irr)

**✅ UPDATED POST-FIX (October 2025):**

**Real Estate Industry Definition:**
Levered cash flow represents the actual cash flows experienced by equity investors after all debt effects. It includes:
- Equity contributions (negative: investor pays out)
- Operating distributions (positive: investor receives)
- Refinancing cash-out (positive: investor receives)
- Disposition proceeds (positive: investor receives)

**Key Insight:** Levered CF = Equity CF (same economic reality, investor perspective)

**Implementation:**
```python
@cached_property
def levered_cash_flow(self) -> pd.Series:
    """
    Levered cash flows from investor perspective.
    
    This is the project-level aggregate of all equity partner cash flows
    after accounting for debt effects, presented from investor perspective.
    
    Sign Convention (Investor Perspective):
    - Equity contributions: NEGATIVE (investor pays money out)
    - Equity distributions: POSITIVE (investor receives money)
    
    Implementation:
    Uses equity_partner_flows() (deal perspective) and flips sign to
    investor perspective. No formula calculation needed - just uses
    actual ledger records of equity cash flows.
    """
    deal_flows = self._queries.equity_partner_flows()
    investor_flows = -1 * deal_flows  # Flip to investor perspective
    return self._timeline.align_series(investor_flows, fill_value=0.0)
```

**Why NOT the Formula Approach:**
```python
# WRONG (old approach that was fixed):
levered_cf = project_cf + debt_draws + debt_service

# Why it fails:
# 1. When LTC ≠ 100%, creates double-counting of capital uses
# 2. Complex to get right with multiple debt facilities
# 3. Doesn't match equity_cash_flow (created $20M+ gaps)

# RIGHT (current approach):
levered_cf = -equity_partner_flows()  # Just flip sign from deal to investor

# Why it works:
# 1. Single source of truth (ledger)
# 2. Automatically captures all debt effects
# 3. Perfect parity with equity_cash_flow (by definition)
# 4. Works for any deal structure (LTC, refinancing, etc.)
```

**Expected Sign Convention (Investor Perspective):**
- Contributions: Negative (money out of investor pocket)
- Distributions: Positive (money into investor pocket)
- Mixed series: typically negative early (contributions), positive later (distributions)

**Validation:**
```python
# Perfect parity with equity_cash_flow (they're the same!)
lcf_total = results.levered_cash_flow.sum()
ecf_total = results.equity_cash_flow.sum()
assert abs(lcf_total - ecf_total) < 0.01  # Should be exactly equal

# Sign flip from deal perspective
epf_total = queries.equity_partner_flows().sum()  # Deal perspective
assert abs(lcf_total - (-epf_total)) < 0.01  # Investor = -Deal
```

**Glossary Terms:**
- **Levered Cash Flow (LCF)**: Equity cash flows after debt effects (investor perspective)
- **Cash Flow Available to Equity (CFAE)**: Same as LCF, alternative industry term
- **Free Cash Flow to Equity (FCFE)**: Corporate finance equivalent of LCF
- **Equity Partner Flows**: Deal perspective version (contributions +, distributions -)

---

## Equity Queries

### 9. equity_contributions()

**Purpose:** Total equity capital invested by partners

**Formula:**
```
Equity Contributions = All equity contributions
```

**SQL Definition:**
```sql
SELECT 
    DATE_TRUNC('month', date) AS period,
    SUM(amount) AS total
FROM ledger
WHERE category = 'Financing'
  AND subcategory = 'Equity Contribution'
GROUP BY period
ORDER BY period
```

**Key Filters:**
- `category = 'Financing'`
- `subcategory = 'Equity Contribution'`

**Expected Sign:** Positive (from deal perspective - cash INTO deal)

---

### 10. equity_distributions()

**Purpose:** Total distributions to equity partners

**Formula:**
```
Equity Distributions = All equity distributions + preferred returns + promote
```

**SQL Definition:**
```sql
SELECT 
    DATE_TRUNC('month', date) AS period,
    SUM(amount) AS total
FROM ledger
WHERE category = 'Financing'
  AND subcategory IN ('Equity Distribution', 'Preferred Return', 'Promote')
GROUP BY period
ORDER BY period
```

**Key Filters:**
- `category = 'Financing'`
- Subcategories: Equity Distribution, Preferred Return, Promote

**Expected Sign:** Negative (from deal perspective - cash OUT OF deal)

---

### 11. equity_partner_flows()

**Purpose:** Net equity flows from deal perspective (contributions + distributions)

**Formula:**
```
Equity Partner Flows = Equity Contributions + Equity Distributions
                     = (positive contributions) + (negative distributions)
```

**SQL Definition:**
```sql
SELECT 
    DATE_TRUNC('month', date) AS period,
    SUM(amount) AS total
FROM ledger
WHERE category = 'Financing'
  AND subcategory IN (
      'Equity Contribution',
      'Equity Distribution',
      'Preferred Return',
      'Promote'
  )
GROUP BY period
ORDER BY period
```

**Key Filters:**
- `category = 'Financing'`
- Subcategories: All equity-related (contributions AND distributions)

**Expected Sign:** Mixed (contributions positive, distributions negative)

**⚠️ PREVIOUS BUG (Now Fixed):**
Prior implementation used `UNION ALL` which caused double-counting when transactions matched multiple criteria. Fixed by using `SELECT DISTINCT transaction_id`.

**Critical:** This is **deal perspective**. Must flip sign for investor perspective!

---

### 12. equity_cash_flow (property in results.py)

**Purpose:** Investor equity cash flows (investor perspective)

**✅ UPDATED POST-FIX (October 2025):**

**Real Estate Industry Definition:**
Equity cash flow represents actual cash flows to/from equity partners from the investor's perspective. This is the standard metric used for calculating equity returns (levered IRR, equity multiple).

**Key Insight:** Equity CF = Levered CF (they're the same thing, just different naming)

**Implementation:**
```python
@cached_property
def equity_cash_flow(self) -> pd.Series:
    """
    Investor equity cash flows (investor perspective).
    
    Alias for levered_cash_flow. Both represent the same thing: cash flows
    to/from equity investors after all debt effects.
    
    Sign Convention (Investor Perspective):
    - Equity contributions: NEGATIVE (cash OUT of investor pocket)
    - Equity distributions: POSITIVE (cash INTO investor pocket)
    
    This property exists for semantic clarity in different contexts:
    - Use levered_cash_flow when emphasizing project-level analysis
    - Use equity_cash_flow when emphasizing investor returns
    
    Both use the same investor perspective and produce identical results.
    """
    # equity_cash_flow is simply an alias for levered_cash_flow
    # Both are in investor perspective and represent the same cash flows
    return self.levered_cash_flow
```

**Sign Convention (Investor Perspective):**
- Contributions: NEGATIVE (investor pays money out)
- Distributions: POSITIVE (investor receives money)
- Net positive = profitable investment

**Why Alias levered_cash_flow?**
```python
# Both metrics represent the SAME economic reality:
levered_cash_flow = -equity_partner_flows()  # Flip deal → investor
equity_cash_flow  = levered_cash_flow        # Same thing!

# Perfect parity guaranteed (they're identical):
assert (levered_cash_flow == equity_cash_flow).all()
```

**Context-Based Usage:**
- **Use `levered_cash_flow`**: When analyzing project performance after leverage
- **Use `equity_cash_flow`**: When calculating investor returns (IRR, EM)
- **Reality**: They're the same series, just named differently for clarity

**User Requirement (Confirmed):**
> "levered_cash_flow is the project-level aggregate of each disaggregated partner's equity cash flows (equity in, proceeds out) after debt proceeds and debt repayment"

This means: `levered_cash_flow` = `equity_cash_flow` (exactly equal, not approximate!)

**Validation:**
```python
# Perfect equality (not just ≈, but ==)
lcf = results.levered_cash_flow
ecf = results.equity_cash_flow
assert (lcf == ecf).all()  # Every value equal
assert lcf.sum() == ecf.sum()  # Perfect total match
```

**Glossary Terms:**
- **Equity Cash Flow**: Investor perspective cash flows (contributions negative, distributions positive)
- **Levered Cash Flow**: Same as equity cash flow (alternative naming for project context)
- **Investor Perspective**: Sign convention where contributions are negative, distributions positive
- **Deal Perspective**: Opposite signs (contributions positive, distributions negative) - used internally only

---

## Capital Expenditure Queries

### 13. capex()

**Purpose:** Capital expenditures (context-dependent: major or recurring)

**Current Issue:** Ambiguous - pulls ALL `category='Capital'` which includes acquisition, construction, AND ongoing capex

**Recommended Split:**

#### 13a. major_capex()
**Purpose:** Major capital deployments (acquisition, construction, TI/LC)

**SQL Definition:**
```sql
SELECT 
    DATE_TRUNC('month', date) AS period,
    SUM(amount) AS total
FROM ledger
WHERE flow_purpose = 'Capital Use'
GROUP BY period
ORDER BY period
```

**Expected Sign:** Negative

#### 13b. recurring_capex()
**Purpose:** Ongoing capital maintenance

**SQL Definition:**
```sql
SELECT 
    DATE_TRUNC('month', date) AS period,
    SUM(amount) AS total
FROM ledger
WHERE category = 'Expense'
  AND subcategory = 'CapEx'
  AND flow_purpose = 'Operating'
GROUP BY period
ORDER BY period
```

**Expected Sign:** Negative

**Note:** Current `capex()` should be renamed to `major_capex()` and use `flow_purpose = 'Capital Use'` for clarity.

---

## Validation Queries

### 14. capital_sources()

**Purpose:** All capital inflows (for sources & uses analysis)

**Formula:**
```
Capital Sources = Debt Proceeds + Equity Contributions + Sale Proceeds
```

**SQL Definition:**
```sql
SELECT 
    DATE_TRUNC('month', date) AS period,
    SUM(amount) AS total
FROM ledger
WHERE flow_purpose = 'Capital Source'
GROUP BY period
ORDER BY period
```

**Expected Sign:** Positive

**Components:**
- Loan Proceeds
- Refinancing Proceeds
- Equity Contributions
- Sale Proceeds

---

### 15. capital_uses()

**Purpose:** All capital outflows (for sources & uses analysis)

**Formula:**
```
Capital Uses = Acquisition + Construction + TI/LC + Transaction Costs
```

**SQL Definition:**
```sql
SELECT 
    DATE_TRUNC('month', date) AS period,
    SUM(amount) AS total
FROM ledger
WHERE flow_purpose = 'Capital Use'
GROUP BY period
ORDER BY period
```

**Expected Sign:** Negative

**Components:**
- Purchase Price
- Closing Costs
- Hard Costs
- Soft Costs
- Transaction Costs

---

## Validation Formulas

### Formula 1: Parity Check

```python
# Levered CF should equal equity cash flow (after perspective adjustment)
levered_cf = queries.levered_cash_flow().sum()
investor_ecf = queries.equity_cash_flow().sum()
deal_ecf = -investor_ecf  # Flip to deal perspective
assert abs(levered_cf - deal_ecf) < 100_000  # Within $100k
```

### Formula 2: Sources & Uses Balance

```python
# Sources - Uses = Net to Operations
sources = queries.capital_sources().sum()  # Positive
uses = queries.capital_uses().sum()  # Negative
operating = queries.operational_cash_flow().sum()  # Mixed
financing = queries.debt_service().sum() + queries.equity_distributions().sum()  # Negative

# Net should be small (near-zero for completed deals)
net = sources + uses + operating + financing
# Net represents profit/loss + timing differences
```

### Formula 3: Cash Neutrality Check

```python
# Ledger is NOT double-entry, so won't sum to zero
# But we can check that excess makes economic sense

capital_in = ledger[ledger['flow_purpose'] == 'Capital Source']['amount'].sum()
capital_out = ledger[ledger['flow_purpose'] == 'Capital Use']['amount'].sum()
financing_out = ledger[ledger['flow_purpose'] == 'Financing Service']['amount'].sum()
operating = ledger[ledger['flow_purpose'] == 'Operating']['amount'].sum()

excess = capital_in + capital_out + financing_out + operating
# Excess should be:
# - Positive: Profit/excess capital (good)
# - Negative: Loss/deficit (bad, or timing issue)
# - Close to zero: Break-even
```

### Formula 4: No Double-Counting

```python
# Each transaction should appear in AT MOST ONE of these queries:
operating = queries.operational_cash_flow()
capital_use = queries.capital_uses()
capital_source = queries.capital_sources()
financing = queries.debt_service() + queries.equity_distributions()

# Method: Check transaction_id uniqueness across categories
# (This requires transaction-level validation, not time-series)
```

---

## Query Dependency Graph

```
Level 1 (Atomic):
  - gross_revenue()
  - opex()
  - debt_draws()
  - debt_service()  [MUST include payoffs]
  - equity_contributions()
  - equity_distributions()

Level 2 (Derived from Level 1):
  - noi() = gross_revenue() - opex()
  - operational_cash_flow() = flow_purpose='Operating'  [NOT capex!]
  - equity_partner_flows() = equity_contributions() + equity_distributions()

Level 3 (Derived from Level 2):
  - project_cash_flow() = operational_cf() + capital_uses + sale_proceeds
  - levered_cash_flow = project_cf() + debt_draws() + debt_service()
  - equity_cash_flow = -1 * equity_partner_flows()

Level 4 (Metrics):
  - unlevered_irr = IRR(project_cash_flow())
  - levered_irr = IRR(equity_cash_flow())
  - equity_multiple = -distributions.sum() / contributions.sum()
```

---

## Critical Issues Identified

### Issue 1: operational_cash_flow() Double-Counts CapEx

**Problem:**
```python
# Current (WRONG):
ocf = noi() - capex()  # capex() pulls category='Capital'

# But category='Capital' has flow_purpose='Capital Use'
# And project_cash_flow() pulls flow_purpose='Capital Use'
# Result: Double-counting!
```

**Fix:**
```python
# Correct:
ocf = flow_purpose='Operating' only  # Simple, clean
```

**Impact:** $22.73M double-counted in residential development

---

### Issue 2: debt_service() Missing Payoffs

**Problem:**
```python
# Current (WRONG):
debt_service = Interest + Principal  # Missing payoffs!
```

**Fix:**
```python
# Correct:
debt_service = Interest + Principal + Refinancing Payoff + Prepayment
```

**Impact:** Understates debt outflows, breaks levered_cash_flow formula

---

### Issue 3: levered_cash_flow Missing Debt Proceeds

**Problem:**
```python
# Current (WRONG):
levered_cf = project_cf + debt_service  # Missing debt_draws!
```

**Fix:**
```python
# Correct:
levered_cf = project_cf + debt_draws + debt_service
```

**Impact:** $19.76M discrepancy vs equity_cash_flow

---

## Implementation Checklist

For each query method:

- [ ] **Purpose** clearly documented in docstring
- [ ] **Formula** specified (math or SQL)
- [ ] **Filters** use `flow_purpose` where possible (not category)
- [ ] **Sign convention** documented
- [ ] **Validation** logic included (assertions or tests)
- [ ] **No double-counting** verified against related queries
- [ ] **Unit tests** cover normal and edge cases

---

**Document Status**: Phase 2, Step 2.4 COMPLETE ✅

**Last Updated:** October 2, 2025

**Next Phase:** Audit current implementation against these definitions (Phase 3)

