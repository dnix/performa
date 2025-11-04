# Flow Purpose Rules - Semantic Definitions

**Generated:** October 2, 2025  
**Source:** Phase 2, Step 2.2 - Define flow_purpose Semantics  
**Purpose:** Establish clear, mutually exclusive definitions for all flow_purpose values  
**Status:** Canonical reference for transaction classification

---

## Overview

The `flow_purpose` field provides high-level, unambiguous categorization of every ledger transaction. It answers the fundamental question:

> **"What is the economic purpose of this cash flow?"**

This document establishes the **canonical definitions** and **decision rules** for assigning `flow_purpose` to transactions.

---

## Core Principles

### 1. Mutual Exclusivity

Every transaction has **EXACTLY ONE** `flow_purpose`. No transaction can have multiple purposes.

### 2. Completeness

Every cash transaction must map to one of these five purposes:
- `Operating`
- `Capital Use`
- `Capital Source`
- `Financing Service`
- `Valuation` (non-cash only)

### 3. Hierarchy

`flow_purpose` is **higher-level** than `category` and `subcategory`:
- Use `flow_purpose` for aggregate cash flow calculations
- Use `category` + `subcategory` for detailed breakdowns

---

## Flow Purpose Definitions

### 1. OPERATING

**Definition:** Day-to-day property operations that generate recurring revenue and incur ongoing expenses.

**Characteristics:**
- **Recurring**: Happens regularly (monthly, quarterly)
- **Operational**: Related to running the property
- **Revenue or Expense**: Can be positive (income) or negative (costs)
- **Not Capital**: Does not change asset basis

**Includes:**
- Rental income (lease payments)
- Operating expenses (utilities, maintenance, management)
- Property taxes and insurance
- Vacancy losses (contra-revenue)
- Credit losses (bad debt)
- Expense recoveries (CAM, tax pass-throughs)
- Miscellaneous income (parking, vending)

**Excludes:**
- Acquisition costs (those are `Capital Use`)
- Sale proceeds (those are `Capital Source`)
- Major capital improvements (those are `Capital Use`)
- Debt service (those are `Financing Service`)
- Equity distributions (those are `Financing Service`)

**Industry Alignment:**
- NOI (Net Operating Income) = SUM(Operating flows)
- Corresponds to GAAP operating activities
- Aligns with ARGUS "Operating" classification

**Sign Pattern:** Mixed (revenue positive, expenses negative)

---

### 2. CAPITAL_USE

**Definition:** One-time deployment of capital for acquiring, developing, improving, or disposing of assets.

**Characteristics:**
- **Non-Recurring**: One-time or project-based
- **Changes Asset Basis**: Increases (or decreases at exit) capital invested
- **Always Outflow**: Money leaving the deal for capital purposes
- **Not Operating**: Not part of day-to-day operations

**Includes:**
- **Acquisition:**
  - Purchase price
  - Closing costs
  - Due diligence costs
- **Development:**
  - Hard costs (construction labor, materials)
  - Soft costs (permits, professional fees, capitalized interest)
  - Site work
- **Improvements:**
  - Tenant improvements (TI)
  - Leasing commissions (LC)
  - Major capital expenditures (non-recurring)
- **Disposition:**
  - Transaction costs (broker fees, legal)
  - Transfer taxes

**Excludes:**
- Ongoing maintenance (that's `Operating`)
- Minor recurring capital expenses (gray area - see below)
- Loan proceeds (those are `Capital Source`)
- Sale proceeds (those are `Capital Source`)

**Industry Alignment:**
- Corresponds to GAAP investing activities (outflows)
- Aligns with "Total Project Cost" or "Uses" in sources & uses

**Sign Pattern:** Always NEGATIVE (outflows)

---

### 3. CAPITAL_SOURCE

**Definition:** Capital inflows from external sources that fund the deal's capital needs.

**Characteristics:**
- **Funding**: Money coming INTO the deal
- **External**: From lenders, investors, or asset sales
- **Non-Operating**: Not from property operations
- **Always Inflow**: Money entering the deal

**Includes:**
- **Debt:**
  - Loan proceeds (initial funding)
  - Refinancing proceeds (new loan)
  - Construction loan draws
- **Equity:**
  - Equity contributions (partner capital calls)
  - Initial equity investment
- **Disposition:**
  - Sale proceeds (gross)
  - Partial interest sales

**Excludes:**
- Operating revenue (that's `Operating`)
- Return of capital distributions (complex - see special cases)
- Debt service payments (those are `Financing Service`)

**Industry Alignment:**
- Corresponds to "Sources" in sources & uses
- GAAP financing activities (inflows only)

**Sign Pattern:** Always POSITIVE (inflows)

---

### 4. FINANCING_SERVICE

**Definition:** Ongoing obligations and payments to debt and equity capital providers.

**Characteristics:**
- **Obligations**: Required payments to capital providers
- **Both Debt and Equity**: Includes both lender and investor payments
- **Ongoing or Terminal**: Can be recurring (debt service) or one-time (payoffs, distributions)
- **Always Outflow**: Money leaving the deal to satisfy financing obligations

**Includes:**
- **Debt Service:**
  - Interest payments
  - Principal payments
  - Loan prepayments (payoff at exit)
  - Refinancing payoffs (old loan paid off)
  - Origination fees (maybe - see special cases)
  - Prepayment penalties
- **Equity Service:**
  - Equity distributions
  - Preferred return payments
  - GP promote/carried interest
  - Return of capital (maybe - see special cases)

**Excludes:**
- Loan proceeds (those are `Capital Source`)
- Equity contributions (those are `Capital Source`)
- Operating expenses (those are `Operating`)

**Industry Alignment:**
- Corresponds to GAAP financing activities (outflows)
- Aligns with "Debt Service" and "Distributions" in cash flow models

**Sign Pattern:** Always NEGATIVE (outflows)

---

### 5. VALUATION

**Definition:** Non-cash bookkeeping entries for asset valuation and mark-to-market adjustments.

**Characteristics:**
- **Non-Cash**: **ZERO** impact on actual cash flows
- **Bookkeeping**: For reporting and tracking only
- **Excluded from IRR**: Not included in IRR/EM calculations
- **Always Positive**: Convention for marking up asset values

**Includes:**
- Asset appraisals
- Refinancing valuations (supporting new loan)
- Exit appraisals (supporting sale price)
- Periodic mark-to-market adjustments
- DCF valuations
- Comparable sales valuations

**Excludes:**
- Actual sale proceeds (those are `Capital Source` with cash impact)
- Any transaction with real cash movement

**Industry Alignment:**
- Similar to GAAP fair value adjustments
- Corresponds to NCREIF valuation reporting

**Sign Pattern:** Always POSITIVE (by convention, but **zero cash impact**)

---

## Decision Tree

### Step-by-Step Classification

```
START: Is this a cash transaction or valuation?
│
├─> VALUATION (non-cash)
│   └─> flow_purpose = VALUATION
│
└─> CASH TRANSACTION
    │
    ├─> Is cash coming INTO or OUT OF the deal?
    │   │
    │   ├─> CASH IN (+)
    │   │   │
    │   │   ├─> From operations? (rent, recoveries, misc income)
    │   │   │   └─> flow_purpose = OPERATING
    │   │   │
    │   │   └─> From external sources? (debt, equity, sale)
    │   │       └─> flow_purpose = CAPITAL_SOURCE
    │   │
    │   └─> CASH OUT (-)
    │       │
    │       ├─> For operations? (utilities, mgmt, property taxes)
    │       │   └─> flow_purpose = OPERATING
    │       │
    │       ├─> For capital deployment? (acquisition, construction, TI/LC, exit costs)
    │       │   └─> flow_purpose = CAPITAL_USE
    │       │
    │       └─> For financing obligations? (debt service, equity distributions)
    │           └─> flow_purpose = FINANCING_SERVICE
```

---

## Special Cases and Gray Areas

### Case 1: Recurring CapEx

**Question:** Is recurring capital expenditure `Operating` or `Capital Use`?

**Answer:** Depends on magnitude and frequency:

| Type | Flow Purpose | Rationale |
|------|--------------|-----------|
| Minor recurring (HVAC replacement, roof repairs) | `Operating` | Part of ongoing property operations |
| Major non-recurring (building renovation, new parking structure) | `Capital Use` | Changes asset basis significantly |

**Rule of Thumb:**
- < 1% of property value AND annual → `Operating`
- > 1% of property value OR multi-year project → `Capital Use`

**Current Implementation:**
- `category='Capital'` → `flow_purpose='Capital Use'`
- `category='Expense'`, `subcategory='CapEx'` → `flow_purpose='Operating'` (maybe)

**Recommendation:** Use `category` to distinguish:
- Major CapEx: `category='Capital'`, `flow_purpose='Capital Use'`
- Recurring CapEx: `category='Expense'`, `subcategory='CapEx'`, `flow_purpose='Operating'`

---

### Case 2: Sale Proceeds (Special Mapping)

**Question:** Why are sale proceeds `Revenue` category but `Capital Source` flow_purpose?

**Answer:** Disposition is a capital event, not an operating activity.

**Mapping:**
```
category='Revenue'
subcategory='Sale'
flow_purpose='Capital Source'  ← NOT 'Operating'!
```

**Rationale:**
- Prevents sale proceeds from inflating NOI
- Correctly classifies disposition as capital event
- Aligns with industry standards (sale ≠ operations)

**Implementation:** Explicit override in `FlowPurposeMapper`:
```python
if subcategory == RevenueSubcategoryEnum.SALE:
    return TransactionPurpose.CAPITAL_SOURCE
else:
    return TransactionPurpose.OPERATING  # Other revenue
```

---

### Case 3: Refinancing Transactions

**Question:** How should refinancing be classified?

**Answer:** Split into two transactions:

| Transaction | Flow Purpose | Sign | Rationale |
|-------------|--------------|------|-----------|
| Refinancing Proceeds | `Capital Source` | + | New capital INTO deal |
| Refinancing Payoff | `Financing Service` | - | Obligation to old lender |

**Net Effect:**
- If Proceeds > Payoff: Cash-out refi (excess to equity)
- If Proceeds = Payoff: Rate/term refi (no cash change)
- If Proceeds < Payoff: Rare (investor must cover gap)

**Why NOT combine them?**
- Need to track both gross proceeds and gross payoff
- Debt balance tracking requires separate entries
- Cash-out amount calculated as difference

---

### Case 4: Equity Contributions vs Distributions

**Question:** Why are both `category='Financing'` but different flow_purpose?

**Answer:** Direction matters - IN vs OUT

| Transaction | Flow Purpose | Sign | Rationale |
|-------------|--------------|------|-----------|
| Equity Contribution | `Capital Source` | + | Capital coming IN from investors |
| Equity Distribution | `Financing Service` | - | Returns going OUT to investors |

**Analogy to Debt:**
- Loan Proceeds = Equity Contribution (both `Capital Source`)
- Debt Service = Equity Distribution (both `Financing Service`)

---

### Case 5: Loan Origination Fees

**Question:** Are origination fees `Capital Use` or `Financing Service`?

**Answer:** **Ambiguous** - industry varies

**Option A - Capital Use:**
- Rationale: Part of total project cost
- Increases capital deployed
- Treated like closing costs

**Option B - Financing Service:**
- Rationale: Payment to lender for service
- Similar to interest (cost of borrowing)
- Treated like prepayment penalty

**Current Implementation:** Not explicitly addressed

**Recommendation:** `Financing Service` (cost of capital)
- More consistent with interest/fees as financing costs
- Separates project costs from financing costs
- Aligns with GAAP treatment

---

### Case 6: Capitalized Interest

**Question:** Why is capitalized interest `Capital Use` not `Financing Service`?

**Answer:** Not paid in cash during construction, but it IS interest (financing cost)

**Classification:**
```
category='Financing'
subcategory='Interest Reserve'
flow_purpose='Capital Use'  ← Special case!
```

**Rationale:**
- **Semantically correct**: It IS interest on a loan → `Financing` category ✓
- **Mechanically correct**: Must have `Capital Use` flow_purpose to:
  1. Include in total project costs for LTC calculations
  2. Exclude from debt_service() queries (not a cash payment)
  3. Add to depreciable basis
- Industry standard: shown as distinct line item in sources & uses

**Implementation:**
- Special case in `FlowPurposeMapper`: `INTEREST_RESERVE` → `Capital Use`
- This is the ONLY financing subcategory that maps to `Capital Use`

**Contrast:**
- **Paid Interest**: `Financing / Interest Payment / Financing Service` (cash payment)
- **Capitalized Interest**: `Financing / Interest Reserve / Capital Use` (adds to project cost)

---

### Case 7: Tenant Improvements (TI) and Leasing Commissions (LC)

**Question:** Are TI/LC `Operating` or `Capital Use`?

**Answer:** **Capital Use** - they are capital deployments

**Rationale:**
- Required to generate lease revenue (similar to acquisition)
- One-time per lease (not recurring like maintenance)
- Increases asset value (tenant-ready space)
- Industry standard: classify as capital

**Current Implementation:**
- Should be `category='Capital'` or specific TI/LC subcategory
- `flow_purpose='Capital Use'`

**Note:** Even though they recur with lease turnover, each instance is a capital event.

---

## Flow Purpose by Category Matrix

### Expected Mappings

| Category | Subcategory | Flow Purpose | Notes |
|----------|-------------|--------------|-------|
| Capital | All | `Capital Use` | Always capital deployment |
| Revenue | Sale | `Capital Source` | **Special case** |
| Revenue | All others | `Operating` | Normal revenue |
| Expense | OpEx | `Operating` | Operating expenses |
| Expense | CapEx | `Operating` or `Capital Use` | Depends on magnitude |
| Financing | Equity Contribution | `Capital Source` | Capital IN |
| Financing | Equity Distribution | `Financing Service` | Capital OUT |
| Financing | Loan Proceeds | `Capital Source` | Debt IN |
| Financing | Refinancing Proceeds | `Capital Source` | Debt IN |
| Financing | Interest Payment | `Financing Service` | Debt obligation |
| Financing | Principal Payment | `Financing Service` | Debt obligation |
| Financing | Refinancing Payoff | `Financing Service` | Debt obligation |
| Financing | Prepayment | `Financing Service` | Debt obligation |
| Financing | Preferred Return | `Financing Service` | Equity obligation |
| Financing | Promote | `Financing Service` | Equity obligation |
| Valuation | All | `Valuation` | Non-cash |

---

## Query Implications

### Using flow_purpose for Queries

**Advantages:**
- Unambiguous categorization
- Mutually exclusive (no double-counting)
- Consistent across all transaction types
- High-level aggregation

**Query Examples:**

```python
# Operating cash flow: Use ONLY Operating flow_purpose
ocf = ledger[ledger['flow_purpose'] == 'Operating']['amount'].sum()

# Capital deployed: Use ONLY Capital Use flow_purpose
capital = ledger[ledger['flow_purpose'] == 'Capital Use']['amount'].sum()

# Capital raised: Use ONLY Capital Source flow_purpose
sources = ledger[ledger['flow_purpose'] == 'Capital Source']['amount'].sum()

# Financing costs: Use ONLY Financing Service flow_purpose
financing = ledger[ledger['flow_purpose'] == 'Financing Service']['amount'].sum()
```

**Critical:** Using `flow_purpose` eliminates double-counting issues!

---

## Validation Rules

### Completeness Check

```sql
-- Every cash transaction must have a valid flow_purpose
SELECT COUNT(*)
FROM ledger
WHERE flow_purpose IS NULL
  AND category != 'Valuation';
-- Should return 0
```

### Mutual Exclusivity Check

```sql
-- No transaction should have multiple flow_purposes
-- (This is enforced by database schema - one field)
```

### Sign Consistency Check

```sql
-- Capital Source should be positive
SELECT COUNT(*)
FROM ledger
WHERE flow_purpose = 'Capital Source'
  AND amount < 0;
-- Should return 0

-- Capital Use should be negative
SELECT COUNT(*)
FROM ledger
WHERE flow_purpose = 'Capital Use'
  AND amount > 0;
-- Should return 0

-- Financing Service should be negative
SELECT COUNT(*)
FROM ledger
WHERE flow_purpose = 'Financing Service'
  AND amount > 0;
-- Should return 0
```

---

## Best Practices

### 1. Default to flow_purpose in Queries

When aggregating cash flows, **prefer `flow_purpose`** over `category`:

```python
# Good: Use flow_purpose
noi = ledger[ledger['flow_purpose'] == 'Operating']['amount'].sum()

# Less good: Use category (may miss nuances)
noi = (
    ledger[ledger['category'] == 'Revenue']['amount'].sum()
    - ledger[ledger['category'] == 'Expense']['amount'].sum()
)
```

### 2. Use category+subcategory for Detailed Breakdowns

For detailed reporting, use `category` and `subcategory`:

```python
# Detailed CapEx breakdown
capex_by_type = ledger[
    ledger['category'] == 'Capital'
].groupby('subcategory')['amount'].sum()
```

### 3. Document Exceptions

If a transaction doesn't fit standard patterns, document why:

```python
# Unusual case: Equity distribution that's actually return of capital
metadata = SeriesMetadata(
    category=CashFlowCategoryEnum.FINANCING,
    subcategory=FinancingSubcategoryEnum.EQUITY_DISTRIBUTION,
    # flow_purpose still = FINANCING_SERVICE (return of capital is still a distribution)
    item_name="Return of Capital - Not Operating Distribution",
)
```

---

## Migration and Compatibility

### From Systems Without flow_purpose

If migrating from a system that only has `category`:

1. **Audit existing transactions** by category
2. **Apply mapping rules** from this document
3. **Handle edge cases** explicitly
4. **Validate** with test cases

### Example Migration Logic

```python
def assign_flow_purpose(category, subcategory, amount):
    """Apply flow_purpose based on category and subcategory."""
    
    if category == 'Valuation':
        return 'Valuation'
    
    if category == 'Capital':
        return 'Capital Use'
    
    if category == 'Revenue':
        if subcategory == 'Sale':
            return 'Capital Source'  # Special case!
        else:
            return 'Operating'
    
    if category == 'Expense':
        return 'Operating'  # Or 'Capital Use' for major CapEx
    
    if category == 'Financing':
        if subcategory in ['Equity Contribution', 'Loan Proceeds', 'Refinancing Proceeds']:
            return 'Capital Source'
        else:
            return 'Financing Service'
    
    raise ValueError(f"Unknown category: {category}")
```

---

## Summary: Five Purposes, Clear Boundaries

| Flow Purpose | Direction | Recurring | Cash Impact | Use For |
|--------------|-----------|-----------|-------------|---------|
| `Operating` | Mixed | Yes | Yes | Day-to-day operations |
| `Capital Use` | OUT (-) | No | Yes | Capital deployment |
| `Capital Source` | IN (+) | No | Yes | Capital raising |
| `Financing Service` | OUT (-) | Mixed | Yes | Debt/equity obligations |
| `Valuation` | N/A | No | **No** | Non-cash bookkeeping |

---

**Document Status**: Phase 2, Step 2.2 COMPLETE ✅

**Last Updated:** October 2, 2025

**Next Step:** Create canonical `SUBCATEGORY_MAPPING.csv` mapping every subcategory to its correct flow_purpose.

