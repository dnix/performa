# Enum Reference - Complete Ledger Semantic Catalog

**Generated:** October 2, 2025  
**Source:** `src/performa/core/primitives/enums.py`  
**Purpose:** Canonical reference for all ledger categorization values

---

## 1. Primary Categories (CashFlowCategoryEnum)

The top-level classification of transactions:

| Enum Value | String Value | Purpose |
|------------|--------------|---------|
| `CAPITAL` | "Capital" | Capital-related transactions (acquisition, construction, disposition) |
| `EXPENSE` | "Expense" | Operating and capital expense transactions |
| `REVENUE` | "Revenue" | All revenue streams and revenue adjustments |
| `FINANCING` | "Financing" | Debt and equity financing transactions |
| `VALUATION` | "Valuation" | Non-cash valuation and appraisal records |
| `OTHER` | "Other" | Miscellaneous transactions not fitting other categories |

**Note from enum docstring:** Loan transactions are dual-nature:
- Loan draws/proceeds: `FINANCING` category + positive amount = `CAPITAL_SOURCE` flow_purpose
- Debt service payments: `FINANCING` category + negative amount = `FINANCING_SERVICE` flow_purpose

---

## 2. Subcategories by Category

### 2.1 Capital Subcategories (CapitalSubcategoryEnum)

**Category:** `Capital`  
**Flow Purpose:** Typically `Capital Use` (outflows)

| Enum Value | String Value | Typical Sign | Purpose |
|------------|--------------|--------------|---------|
| `PURCHASE_PRICE` | "Purchase Price" | Negative | Property acquisition purchase price |
| `CLOSING_COSTS` | "Closing Costs" | Negative | Acquisition closing costs and fees |
| `DUE_DILIGENCE` | "Due Diligence" | Negative | Due diligence and inspection costs |
| `TRANSACTION_COSTS` | "Transaction Costs" | Negative | Disposition broker fees, legal costs |
| `HARD_COSTS` | "Hard Costs" | Negative | Direct construction costs - materials, labor |
| `SOFT_COSTS` | "Soft Costs" | Negative | Indirect construction costs - permits, fees |
| `SITE_WORK` | "Site Work" | Negative | Site preparation and infrastructure work |
| `OTHER` | "Other" | Negative | Miscellaneous capital expenditures |

**Groupings:**
- **Acquisition:** PURCHASE_PRICE, CLOSING_COSTS, DUE_DILIGENCE
- **Construction:** HARD_COSTS, SOFT_COSTS, SITE_WORK
- **Disposition:** TRANSACTION_COSTS

---

### 2.2 Revenue Subcategories (RevenueSubcategoryEnum)

**Category:** `Revenue`  
**Flow Purpose:** `Operating` or `Capital Source` (for SALE)

| Enum Value | String Value | Typical Sign | Purpose |
|------------|--------------|--------------|---------|
| `SALE` | "Sale" | Positive | Revenue from property or unit sales |
| `LEASE` | "Lease" | Positive | Revenue from property or unit leases |
| `MISC` | "Miscellaneous" | Positive | Miscellaneous income (parking, vending, etc.) |
| `RECOVERY` | "Recovery" | Positive | Expense recoveries from tenants (CAM, etc.) |
| `SECURITY_DEPOSIT` | "Security Deposit" | Positive | Security deposits collected from tenants |
| `VACANCY_LOSS` | "Vacancy Loss" | Negative | Revenue reduction from vacant units/space |
| `CREDIT_LOSS` | "Credit Loss" | Negative | Revenue reduction from uncollectable rent |
| `ABATEMENT` | "Abatement" | Negative | Rent abatement/concessions (free rent) |

**Groupings:**
- **Gross Revenue:** LEASE, MISC, RECOVERY (positive)
- **Revenue Losses:** VACANCY_LOSS, CREDIT_LOSS, ABATEMENT (negative, contra-revenue)
- **Tenant Revenue:** LEASE, RECOVERY (tenant-sourced only)

**Special Case:** `SALE` should have flow_purpose = `Capital Source`, not `Operating`

---

### 2.3 Expense Subcategories (ExpenseSubcategoryEnum)

**Category:** `Expense`  
**Flow Purpose:** `Operating` (for OPEX) or varies (for CAPEX)

| Enum Value | String Value | Typical Sign | Purpose |
|------------|--------------|--------------|---------|
| `OPEX` | "OpEx" | Negative | Operational expenses |
| `CAPEX` | "CapEx" | Negative | Capital expenses |

**Note:** `CAPEX` from category `Expense` vs category `Capital` needs clarification in audit.

---

### 2.4 Financing Subcategories (FinancingSubcategoryEnum)

**Category:** `Financing`  
**Flow Purpose:** `Capital Source` (proceeds), `Financing Service` (payments), or `Capital Use` (fees)

| Enum Value | String Value | Typical Sign | Flow Purpose | Purpose |
|------------|--------------|--------------|--------------|---------|
| `LOAN_PROCEEDS` | "Loan Proceeds" | Positive | Capital Source | Initial loan funding at origination |
| `PRINCIPAL_PAYMENT` | "Principal Payment" | Negative | Financing Service | Principal portion for balance tracking |
| `INTEREST_PAYMENT` | "Interest Payment" | Negative | Financing Service | Interest portion, actual cash expense |
| `INTEREST_RESERVE` | "Interest Reserve" | Varies | TBD | Interest reserve funding or draws |
| `PREPAYMENT` | "Prepayment" | Negative | Financing Service | Loan payoff at property sale/disposition |
| `REFINANCING_PROCEEDS` | "Refinancing Proceeds" | Positive | Capital Source | New loan proceeds replacing old loan |
| `REFINANCING_PAYOFF` | "Refinancing Payoff" | Negative | Financing Service | Old loan payoff in refinancing transaction |
| `EQUITY_CONTRIBUTION` | "Equity Contribution" | Positive | Capital Source | Partner capital contributions |
| `EQUITY_DISTRIBUTION` | "Equity Distribution" | Negative | Financing Service | Distributions to equity partners |
| `PREFERRED_RETURN` | "Preferred Return" | Negative | Financing Service | Preferred return payments |
| `PROMOTE` | "Promote" | Negative | Financing Service | Carried interest/promote payments |
| `ORIGINATION_FEE` | "Origination Fee" | Negative | TBD | Loan origination fees |
| `EXIT_FEE` | "Exit Fee" | Negative | TBD | Loan exit fees |
| `PREPAYMENT_PENALTY` | "Prepayment Penalty" | Negative | TBD | Early repayment penalties |

**Debt Flow Groupings:**
- **Debt Sources:** LOAN_PROCEEDS, REFINANCING_PROCEEDS (positive)
- **Debt Service:** INTEREST_PAYMENT, PRINCIPAL_PAYMENT (negative)
- **Debt Payoffs:** PREPAYMENT, REFINANCING_PAYOFF (negative)

**Equity Flow Groupings:**
- **Equity Partner Flows:** EQUITY_CONTRIBUTION, EQUITY_DISTRIBUTION, PREFERRED_RETURN, PROMOTE

**Fee Groupings:**
- **Financing Fees:** ORIGINATION_FEE, EXIT_FEE, PREPAYMENT_PENALTY

**Critical Note:** User clarified "cash out refi is cash back in investors' pockets as proceeds!"
- REFINANCING_PROCEEDS > REFINANCING_PAYOFF = cash-out to investors
- This excess should flow through to equity distributions

---

### 2.5 Valuation Subcategories (ValuationSubcategoryEnum)

**Category:** `Valuation`  
**Flow Purpose:** `Valuation`  
**Cash Flow Impact:** ZERO (non-transactional bookkeeping)

| Enum Value | String Value | Purpose |
|------------|--------------|---------|
| `ASSET_VALUATION` | "Asset Valuation" | Direct asset appraisals and valuations |
| `COMPARABLE_SALES` | "Comparable Sales" | Market-based comparable sales analysis |
| `DCF_VALUATION` | "DCF Valuation" | Discounted cash flow valuations |
| `DIRECT_CAP_VALUATION` | "Direct Cap Valuation" | Direct capitalization method valuations |
| `COST_APPROACH` | "Cost Approach" | Cost approach valuations |
| `BROKER_OPINION` | "Broker Opinion" | Broker price opinions and estimates |

---

## 3. Transaction Purposes (TransactionPurpose / flow_purpose)

High-level classification providing unambiguous categorization:

| Enum Value | String Value | Typical Sign | Purpose |
|------------|--------------|--------------|---------|
| `OPERATING` | "Operating" | Both | Day-to-day property operations (revenue and expenses) |
| `CAPITAL_USE` | "Capital Use" | Negative | Capital deployed for acquisition, improvements, development |
| `CAPITAL_SOURCE` | "Capital Source" | Positive | Capital raised from sales, refinancing, equity, or debt |
| `FINANCING_SERVICE` | "Financing Service" | Negative | Debt service payments and financing obligations |
| `VALUATION` | "Valuation" | Zero | Non-cash valuation and appraisal records |

### 3.1 OPERATING Details
**Includes:**
- Revenue: Rent, miscellaneous income, expense recoveries
- Expenses: Property taxes, insurance, utilities, maintenance, management
- Both positive (income) and negative (expense) amounts

**Excludes:**
- Sale proceeds (those are `Capital Source`)
- Capital expenditures (those are `Capital Use`)

---

### 3.2 CAPITAL_USE Details
**Includes:**
- Acquisition costs and fees
- Tenant improvements and leasing commissions
- Capital expenditures and major renovations
- Development costs and construction
- Typically negative amounts (cash outflows)

---

### 3.3 CAPITAL_SOURCE Details
**Includes:**
- Property sale proceeds
- Loan proceeds and refinancing proceeds (gross)
- Equity contributions from partners
- Return of capital to partners
- Debt draws during construction/development
- Typically positive amounts (cash inflows that fund capital uses)

**Critical:** User clarified this is where debt proceeds go!

---

### 3.4 FINANCING_SERVICE Details
**Includes:**
- Principal and interest payments
- Loan fees and financing costs
- Prepayment penalties
- Equity distributions to partners
- Typically negative amounts (cash outflows)

**Critical:** Includes both debt service AND equity distributions!

---

### 3.5 VALUATION Details
**Includes:**
- Property appraisals and market valuations
- DCF-based valuations
- Comparable sales valuations
- Internal mark-to-market adjustments
- Zero cash flow impact (non-transactional)

---

## 4. Sign Conventions (Proposed - To Be Validated)

### 4.1 DEAL PERSPECTIVE (Ledger Records)

```
POSITIVE (+) = Cash INTO the deal (sources)
  - Loan proceeds
  - Equity contributions
  - Revenue (rent, sale proceeds)
  - Refinancing proceeds

NEGATIVE (-) = Cash OUT OF the deal (uses)
  - Construction costs
  - Operating expenses
  - Debt service (I+P)
  - Equity distributions
  - Acquisition costs
```

### 4.2 INVESTOR PERSPECTIVE (Reports)

For investor-facing reports, signs are typically FLIPPED:
```
NEGATIVE (-) = Cash OUT of investor pocket
  - Equity contributions
  
POSITIVE (+) = Cash INTO investor pocket
  - Equity distributions
  - Sale proceeds (net)
```

---

## 5. Canonical Mappings (To Be Validated in Phase 2)

### 5.1 Debt Transaction Patterns

| Transaction | Category | Subcategory | Flow Purpose | Sign |
|-------------|----------|-------------|--------------|------|
| Construction loan draw | Financing | Loan Proceeds | Capital Source | + |
| Refi new loan | Financing | Refinancing Proceeds | Capital Source | + |
| Refi payoff old | Financing | Refinancing Payoff | Financing Service | - |
| Interest payment | Financing | Interest Payment | Financing Service | - |
| Principal payment | Financing | Principal Payment | Financing Service | - |
| Disposition payoff | Financing | Prepayment | Financing Service | - |

**Cash-Out Refi Calculation:**
```
Cash to investor = Refinancing Proceeds - Refinancing Payoff
If positive, this goes to equity as distribution
```

---

### 5.2 Equity Transaction Patterns

| Transaction | Category | Subcategory | Flow Purpose | Sign |
|-------------|----------|-------------|--------------|------|
| Equity in (deal view) | Financing | Equity Contribution | Capital Source | + |
| Equity out (deal view) | Financing | Equity Distribution | Financing Service | - |
| Pref return | Financing | Preferred Return | Financing Service | - |
| Promote | Financing | Promote | Financing Service | - |

---

### 5.3 Capital Transaction Patterns

| Transaction | Category | Subcategory | Flow Purpose | Sign |
|-------------|----------|-------------|--------------|------|
| Acquisition | Capital | Purchase Price | Capital Use | - |
| Closing costs | Capital | Closing Costs | Capital Use | - |
| Hard costs | Capital | Hard Costs | Capital Use | - |
| Soft costs | Capital | Soft Costs | Capital Use | - |
| Disposition costs | Capital | Transaction Costs | Capital Use | - |
| Sale proceeds | Revenue | Sale | Capital Source | + |

---

### 5.4 Operating Transaction Patterns

| Transaction | Category | Subcategory | Flow Purpose | Sign |
|-------------|----------|-------------|--------------|------|
| Rent | Revenue | Lease | Operating | + |
| Recoveries | Revenue | Recovery | Operating | + |
| Misc income | Revenue | Miscellaneous | Operating | + |
| Vacancy loss | Revenue | Vacancy Loss | Operating | - |
| OpEx | Expense | OpEx | Operating | - |

---

## 6. Issues to Investigate

### 6.1 CapEx Ambiguity
- **Question:** When is CapEx in category=`Capital` vs category=`Expense` subcategory=`CapEx`?
- **Hypothesis:** 
  - Major development/construction = category=`Capital`
  - Recurring capital improvements = category=`Expense`, subcategory=`CapEx`
- **Impact:** Critical for avoiding double-counting in `operational_cash_flow()` and `project_cash_flow()`

### 6.2 Financing Fee Flow Purpose
- **Question:** Where do `ORIGINATION_FEE`, `EXIT_FEE`, `PREPAYMENT_PENALTY` go?
- Options:
  - `Capital Use` (part of acquisition/disposition costs)?
  - `Financing Service` (part of debt costs)?
  - Depends on context?

### 6.3 Interest Reserve Treatment
- **Question:** Is `INTEREST_RESERVE` a source (positive) or use (negative)?
- **Context:** Construction loans often have interest reserves that get drawn

### 6.4 Valuation Flow Purpose
- **Question:** Should `Valuation` be a `TransactionPurpose`?
- **Alternative:** Could be a separate field or flag (`is_non_cash=True`)
- **Current usage:** Excluded from all cash flow calculations via `flow_purpose != 'Valuation'`

---

## 7. Enum Completeness Check

### 7.1 Categories vs Subcategories Matrix

| Category | Has Dedicated Subcategory Enum? | Subcategory Enum Name |
|----------|--------------------------------|----------------------|
| Capital | ✅ Yes | CapitalSubcategoryEnum |
| Revenue | ✅ Yes | RevenueSubcategoryEnum |
| Expense | ✅ Yes | ExpenseSubcategoryEnum |
| Financing | ✅ Yes | FinancingSubcategoryEnum |
| Valuation | ✅ Yes | ValuationSubcategoryEnum |
| Other | ❌ No | N/A |

### 7.2 Flow Purpose Coverage

All transactions should map to exactly ONE flow_purpose:
- [ ] Verify no transactions have `null` flow_purpose
- [ ] Verify no transactions have multiple flow_purposes
- [ ] Verify all subcategories have canonical flow_purpose mapping

---

## 8. Next Steps (Phase 1.2)

1. Run all example scripts
2. Extract `DISTINCT category, subcategory, flow_purpose` from each
3. Count transactions and sum amounts
4. Compare actual usage to this reference
5. Identify any:
   - Null values
   - Unexpected combinations
   - Contradictions with documented intent

---

## References

- Source: `src/performa/core/primitives/enums.py`
- Used by: `src/performa/core/ledger/queries.py` (query filters)
- Used by: All modules posting to ledger via `ledger.add_series()`

