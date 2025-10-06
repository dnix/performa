# Real Estate Financial Modeling Glossary

**Purpose:** Comprehensive mapping of industry standard real estate financial terms to Performa concepts and code implementations  
**Last Updated:** October 6, 2025  
**Status:** Post-fix implementation (all bugs resolved) + Cash Sweep covenants

---

## Overview

This glossary provides:
1. **Industry Standard Definitions**: What the term means in commercial real estate
2. **Performa Implementation**: How it's calculated in the code
3. **Related Terms**: Alternative names and related concepts
4. **Code References**: Where to find it in the codebase

---

## A

### Acquisition Costs
**Industry Definition:** Total cost to purchase a property, including purchase price, closing costs, and due diligence expenses.

**Performa Implementation:**
- **Ledger Categories**: `Capital / Purchase Price`, `Capital / Closing Costs`, `Capital / Due Diligence`
- **Flow Purpose**: `Capital Use` (negative, capital outflow)
- **Query**: Included in `capital_uses()`
- **Code Reference**: `src/performa/deal/analysis/acquisition.py`

**Related Terms:** Basis, Total Project Cost (for development)

---

## B

### Basis (Cost Basis)
**Industry Definition:** Total capital invested in a property, used for calculating capital gains and depreciation.

**Performa Implementation:**
- **Calculation**: Sum of all `Capital Use` transactions
- **Query**: `capital_uses().sum()`
- **Components**: Acquisition + Development + Improvements
- **Code Reference**: `src/performa/core/ledger/queries.py` (capital_uses method)

**Related Terms:** Total Project Cost, Depreciable Basis

---

## C

### Cap Rate (Capitalization Rate)
**Industry Definition:** Ratio of Net Operating Income to property value, used for valuation.

**Performa Implementation:**
- **Formula**: NOI / Property Value
- **NOI Query**: `noi()`
- **Valuation**: `src/performa/valuation/direct_cap.py`
- **Usage**: Exit valuation, stabilized value assessment

**Related Terms:** Direct Capitalization, Going-In Cap, Exit Cap

---

### CFAE (Cash Flow Available to Equity)
**Industry Definition:** Cash available to equity investors after all debt service payments.

**Performa Implementation:**
- **Property**: `results.levered_cash_flow` (investor perspective)
- **Same As**: Levered Cash Flow, Equity Cash Flow
- **Sign Convention**: Contributions negative, distributions positive
- **Code Reference**: `src/performa/deal/results.py` (levered_cash_flow property)

**Related Terms:** Levered Cash Flow, Free Cash Flow to Equity (FCFE), Equity Cash Flow

**Key Insight:** CFAE = Levered CF = Equity CF (all the same thing in Performa)

---

### Capital Expenditures (CapEx)
**Industry Definition:** Major capital improvements and replacements required for property operations.

**Types:**
1. **Recurring CapEx**: Regular replacements (HVAC, appliances)
2. **Major CapEx**: Significant improvements (roof replacement, building systems)
3. **Development CapEx**: New construction or major renovation

**Performa Implementation:**
- **Recurring**: `Expense / CapEx` with `flow_purpose='Operating'`
- **Major/Development**: `Capital / *` with `flow_purpose='Capital Use'`
- **Query**: `capex()` for major, included in `operational_cash_flow()` for recurring
- **Code Reference**: `src/performa/core/ledger/queries.py`

**Related Terms:** Capital Improvements, FF&E (Furniture, Fixtures & Equipment)

---

### Capital Stack
**Industry Definition:** Layered structure of financing sources for a real estate investment.

**Typical Order:**
1. Senior Debt (lowest risk, lowest return)
2. Mezzanine Debt (middle risk/return)
3. Preferred Equity (higher risk/return)
4. Common Equity (highest risk, highest return)

**Performa Implementation:**
- **Debt**: `FinancingPlan` with construction/permanent facilities
- **Equity**: `Partnership` structure with GP/LP split
- **Ledger Tracking**: All flows categorized by `entity_type` and `subcategory`
- **Code Reference**: `src/performa/debt/*`, `src/performa/deal/analysis/partnership.py`

**Related Terms:** Cap Structure, Capitalization, Financing Stack

---

### Cash-on-Cash Return
**Industry Definition:** Annual cash distributed to equity divided by total equity invested.

**Performa Implementation:**
```python
# Simple version (single year):
cash_on_cash = annual_distributions / equity_invested

# Full series:
equity_contrib = queries.equity_contributions().sum()
distributions_series = -queries.equity_distributions()  # Flip to positive
coc_series = distributions_series / equity_contrib
```

**Code Reference**: Calculated from `equity_contributions()` and `equity_distributions()` queries

**Related Terms:** Cash Yield, Current Return, Dividend Yield (corporate finance)

---

### Cash-Out Refinancing
**Industry Definition:** Refinancing transaction where new loan proceeds exceed the payoff amount, providing cash to equity investors.

**Performa Implementation:**
- **Refinancing Proceeds**: `Financing / Refinancing Proceeds` (positive, Capital Source)
- **Refinancing Payoff**: `Financing / Refinancing Payoff` (negative, Financing Service)
- **Net Cash-Out**: Proceeds - Payoff = Cash to equity
- **Distribution**: Typically posted as `Equity Distribution`
- **Code Reference**: `src/performa/deal/analysis/debt.py` (_execute_refinancing method)

**Example:**
```
Old Loan Balance:     $20.0M
New Loan Proceeds:    $22.0M
Cash-Out:             $2.0M  → Distributed to equity
```

**Related Terms:** Refinancing, Recapitalization, Return of Capital

---

### Cash Sweep (Lender Cash Sweep Covenant)
**Industry Definition:** Lender covenant requiring borrower to deposit or apply excess operating cash flow to debt service or principal reduction until specific conditions are met (e.g., stabilization, DSCR threshold). Common in construction and bridge loans to mitigate risk during lease-up.

**Performa Implementation:**
- **Modes**:
  - **TRAP**: Excess cash held in lender-controlled escrow, released when covenant satisfied
  - **PREPAY**: Excess cash mandatorily applied to principal prepayment immediately
- **Ledger Categories**:
  - `Financing / Cash Sweep Deposit` (negative, traps cash in escrow)
  - `Financing / Cash Sweep Release` (positive, releases trapped cash)
  - `Financing / Sweep Prepayment` (negative, prepays principal)
- **Flow Purpose**: `Financing Service` (all sweep transactions)
- **Classes**: `CashSweep` (covenant object), composed into `ConstructionFacility`
- **Code Reference**: `src/performa/debt/covenants.py`, `src/performa/debt/construction.py`

**Economic Impact:**
- **TRAP Mode**: Delays cash to equity (timing drag on IRR), but full cash eventually returned
- **PREPAY Mode**: Reduces loan balance → lower interest expense → higher returns

**Example:**
```python
from performa.debt.covenants import CashSweep, SweepMode

# Create cash sweep covenant
sweep = CashSweep(
    mode=SweepMode.TRAP,  # or SweepMode.PREPAY
    end_month=42  # Release at refinancing month
)

# Attach to construction loan
construction = ConstructionFacility(
    name="Construction Loan",
    ltc_ratio=0.70,
    interest_rate=0.07,
    cash_sweep=sweep  # Compose covenant into facility
)
```

**Query Methods:**
- `sweep_deposits()` - Cash trapped in escrow (TRAP mode)
- `sweep_prepayments()` - Principal prepayments from sweep (PREPAY mode)

**Integration:**
- **PartnershipAnalyzer**: Respects sweeps when calculating distributable cash
- **DebtAnalyzer**: Processes covenants after debt service calculation
- **Auto-sync**: Helper `create_construction_to_permanent_plan()` syncs sweep end with refinancing

**Related Terms:** Cash Trap, Lockbox, Debt Service Reserve, Mandatory Prepayment, Covenant

---

### Construction-to-Permanent Loan
**Industry Definition:** Financing structure where construction loan converts to permanent loan upon stabilization.

**Performa Implementation:**
- **Construction Phase**: Interest-only, funded by draws against budget
- **Refinancing Event**: Construction loan paid off, permanent loan funded
- **Classes**: `ConstructionFacility` → `PermanentFinancing`
- **Helper**: `create_construction_to_permanent_plan()`
- **Code Reference**: `src/performa/debt/constructs.py`

**Key Ledger Transactions:**
1. Construction draws: `Loan Proceeds` (Capital Source)
2. Construction interest: `Interest Payment` (Financing Service)
3. Refinancing payoff: `Refinancing Payoff` (Financing Service)
4. Permanent proceeds: `Refinancing Proceeds` (Capital Source)

**Related Terms:** Mini-Perm, Take-Out Financing, Bridge-to-Perm

---

## D

### Deal Perspective
**Industry Definition:** (Performa-specific) Internal accounting perspective where cash flows are recorded from the deal entity's viewpoint.

**Sign Convention:**
- Cash INTO deal: Positive (debt proceeds, equity contributions, revenue)
- Cash OUT OF deal: Negative (capital deployment, debt service, distributions)

**Performa Implementation:**
- **Used**: Internally in ledger records and `equity_partner_flows()` query
- **Not Exposed**: To user-facing metrics (use investor perspective instead)
- **Code Reference**: `src/performa/core/ledger/ledger.py`

**Contrast:** Investor Perspective (used for all IRR calculations)

**Related Terms:** Entity Perspective, Project Perspective

---

### Debt Service
**Industry Definition:** Regular payments of interest and principal on debt financing.

**Components:**
1. **Interest Payment**: Cost of borrowing (expense)
2. **Principal Payment**: Loan balance reduction (not expense)
3. **Debt Payoffs**: Refinancing payoff, prepayment at sale

**Performa Implementation:**
- **Query**: `debt_service()` 
- **Includes**: Interest + Principal + Refinancing Payoff + Prepayment
- **Subcategories**: `Interest Payment`, `Principal Payment`, `Refinancing Payoff`, `Prepayment`
- **Flow Purpose**: `Financing Service` (negative outflows)
- **Code Reference**: `src/performa/core/ledger/queries.py` (debt_service method, lines 696-732)

**Critical:** Post-fix implementation includes ALL debt outflows, not just I+P

**Related Terms:** Debt Service Coverage, Debt Payments, Financing Costs

---

### Debt Service Coverage Ratio (DSCR)
**Industry Definition:** Ratio of Net Operating Income to debt service, measure of ability to cover debt payments.

**Formula:** DSCR = NOI / Debt Service

**Performa Implementation:**
```python
noi_series = queries.noi()
debt_service_series = queries.debt_service()
dscr_series = noi_series / abs(debt_service_series)  # Take abs for positive ratio
```

**Lender Requirements:**
- Typical minimum: 1.20x - 1.25x
- Higher for riskier assets/borrowers
- Covenant in loan documents

**Code Reference**: Calculated from `noi()` and `debt_service()` queries

**Related Terms:** DSC, Coverage Ratio, Cushion

---

### Development Project
**Industry Definition:** Ground-up construction or major renovation of real estate.

**Phases:**
1. **Pre-Development**: Land acquisition, entitlements, planning
2. **Construction**: Vertical construction (typically 18-36 months)
3. **Lease-Up**: Marketing and leasing to stabilization
4. **Stabilization**: Property reaches target occupancy
5. **Hold or Sale**: Either refinance and hold, or sell

**Performa Implementation:**
- **Class**: `DevelopmentProject`
- **Components**: `CapitalPlan` (hard/soft costs), `AbsorptionPlan` (lease-up)
- **Financing**: Typically construction-to-permanent structure
- **Analysis**: Tracks NOI build-up, lease-up pace, stabilization date
- **Code Reference**: `src/performa/development/*`

**Related Terms:** Ground-Up Development, Build-to-Core, Opportunistic Development

---

### Disposition
**Industry Definition:** Sale of property at end of investment hold period.

**Components:**
1. **Sale Proceeds**: Gross sales price (Revenue / Sale)
2. **Transaction Costs**: Broker fees, legal (Capital / Transaction Costs)
3. **Debt Payoff**: Loan prepayment (Financing / Prepayment)
4. **Net Proceeds**: Distributed to equity after debt payoff

**Performa Implementation:**
- **Analysis Class**: `DispositionAnalyzer`
- **Valuation**: `DirectCapValuation` or `DCFValuation` determines sale price
- **Net to Equity**: Sale - Transaction Costs - Debt Payoff = Equity Distribution
- **Code Reference**: `src/performa/deal/analysis/disposition.py`

**Ledger Flow:**
```
1. Sale Proceeds:       +$50M (Capital Source)
2. Transaction Costs:   -$2M  (Capital Use)
3. Loan Payoff:         -$30M (Financing Service)
4. Net to Equity:       $18M
5. Equity Distribution: -$18M (Financing Service, deal perspective)
```

**Related Terms:** Exit, Sale, Liquidation Event

---

### Distributions
**Industry Definition:** Cash payments from property/deal to equity investors.

**Types:**
1. **Operating Distributions**: From NOI after debt service
2. **Refinancing Distributions**: From cash-out refinancing
3. **Disposition Distributions**: From property sale proceeds

**Performa Implementation:**
- **Ledger**: `Financing / Equity Distribution`
- **Flow Purpose**: `Financing Service`
- **Sign Convention**: 
  - Deal Perspective: Negative (cash OUT of deal)
  - Investor Perspective: Positive (cash INTO investor pocket)
- **Query**: `equity_distributions()`
- **Code Reference**: `src/performa/deal/analysis/partnership.py`

**Key Insight:** In investor perspective (IRR calculations), distributions are POSITIVE

**Related Terms:** Dividends (corporate), Payouts, Returns

---

## E

### Equity Cash Flow
**Industry Definition:** Cash flows to/from equity investors, used to calculate levered returns.

**Components:**
- Equity contributions (negative: investor pays)
- Operating distributions (positive: investor receives)
- Refinancing cash-out (positive: investor receives)
- Disposition proceeds (positive: investor receives)

**Performa Implementation:**
- **Property**: `results.equity_cash_flow`
- **Calculation**: Alias for `levered_cash_flow` (they're identical)
- **Source**: `=-equity_partner_flows()` with sign flip
- **Sign Convention**: Investor perspective (contributions -, distributions +)
- **Code Reference**: `src/performa/deal/results.py` (lines 167-197)

**Formula (conceptual):**
```
Equity CF = -Equity Contributions + Distributions
          = What investors actually experience
```

**Key Insight:** Equity CF = Levered CF = CFAE (all same thing, different names)

**Related Terms:** Levered Cash Flow, CFAE, Free Cash Flow to Equity

---

### Equity Multiple (EM)
**Industry Definition:** Total distributions divided by total contributions, measure of total return.

**Formula:** EM = Total Distributions / Total Contributions

**Performa Implementation:**
```python
# From results properties:
equity_multiple = results.equity_multiple

# Calculation:
contributions = abs(queries.equity_contributions().sum())  # Make positive
distributions = abs(queries.equity_distributions().sum())  # Make positive
em = distributions / contributions
```

**Interpretation:**
- EM = 2.0x means investors got back 2x their investment
- EM > 1.0 means profitable (got back more than invested)
- EM < 1.0 means loss (got back less than invested)

**Relationship to IRR:**
```
For a given holding period:
EM = (1 + IRR) ^ years

Example: 20% IRR over 5 years:
EM = (1.20) ^ 5 = 2.49x
```

**Code Reference**: `src/performa/deal/results.py` (equity_multiple property)

**Related Terms:** MOIC (Multiple on Invested Capital), Cash-on-Cash Multiple

---

### Equity Partner Flows
**Industry Definition:** (Performa-specific) Aggregate of all equity transactions across all partners.

**Performa Implementation:**
- **Query**: `equity_partner_flows()`
- **Includes**: Equity Contribution + Equity Distribution + Preferred Return + Promote
- **Perspective**: Deal perspective (contributions +, distributions -)
- **Aggregation**: Sums across all partners (GP, LP) per period
- **Code Reference**: `src/performa/core/ledger/queries.py` (lines 1263-1322)

**Sign Convention (Deal Perspective):**
```
Contributions:  Positive (cash INTO deal)
Distributions:  Negative (cash OUT OF deal)
Net:            Typically negative (more out than in for profitable deals)
```

**Relationship to Other Metrics:**
```
levered_cash_flow = -equity_partner_flows()  # Flip to investor perspective
equity_cash_flow  = -equity_partner_flows()  # Same thing
```

**Related Terms:** Partner Cash Flows, Equity Flows

---

## F

### Flow Purpose
**Industry Definition:** (Performa-specific) High-level categorization of transactions by economic purpose.

**Values:**
1. **Operating**: Day-to-day property operations (revenue & expenses)
2. **Capital Use**: Capital deployment (acquisition, construction, improvements)
3. **Capital Source**: Capital inflows (debt, equity, sale proceeds)
4. **Financing Service**: Debt service and equity distributions
5. **Valuation**: Non-cash bookkeeping (appraisals, mark-to-market)

**Purpose:**
- Provides unambiguous, mutually exclusive categorization
- Prevents double-counting in queries
- Enables accurate cash flow aggregation

**Performa Implementation:**
- **Field**: `TransactionPurpose` enum
- **Mapper**: `FlowPurposeMapper.determine()` assigns based on category + subcategory
- **Usage**: Primary filter for all cash flow queries
- **Code Reference**: `src/performa/core/primitives/enums.py`, `src/performa/core/ledger/mapper.py`

**Documentation**: See `FLOW_PURPOSE_RULES.md` for complete semantics

**Related Terms:** Transaction Purpose, Cash Flow Category

---

### Free Cash Flow to Equity (FCFE)
**Industry Definition:** (Corporate finance term) Cash available to equity after all expenses, reinvestment, and debt service.

**Real Estate Equivalent:** Levered Cash Flow / CFAE / Equity Cash Flow

**Performa Implementation:**
- **Property**: `results.levered_cash_flow`
- **Same As**: Equity Cash Flow, CFAE
- **Sign Convention**: Investor perspective
- **Code Reference**: `src/performa/deal/results.py`

**Related Terms**: Levered Cash Flow, CFAE, Equity Cash Flow

---

## G

### GP (General Partner)
**Industry Definition:** Managing partner in a real estate partnership, typically receives promote/carried interest.

**Responsibilities:**
- Asset management
- Deal sourcing and execution
- Day-to-day operations
- Investor relations

**Compensation:**
1. **GP Contribution**: Small equity investment (1-5%)
2. **Asset Management Fee**: Annual fee (1-2% of asset value)
3. **Promote/Carry**: Disproportionate share of profits after LP preferred return

**Performa Implementation:**
- **Partnership Structure**: Defined in `Partnership` class
- **Entity Type**: `entity_type='GP'`
- **Waterfall**: `PartnershipWaterfall` calculates GP vs LP allocations
- **Code Reference**: `src/performa/deal/analysis/partnership.py`

**Related Terms:** Sponsor, Managing Member, Operator

---

### Gross Revenue
**Industry Definition:** Total revenue before deductions for vacancy, credit losses, or expenses.

**Components:**
- Lease revenue (rental income)
- Miscellaneous income (parking, storage, amenities)
- Expense recoveries (CAM, taxes, insurance reimbursements)

**Performa Implementation:**
```python
# Query:
gross_revenue = queries.gross_revenue()

# Includes subcategories:
# - Lease
# - Miscellaneous
# - Recovery

# Excludes:
# - Vacancy Loss (contra-revenue)
# - Credit Loss (contra-revenue)
# - Sale (that's Capital Source, not operating)
```

**Formula:**
```
Effective Gross Revenue (EGR) = Gross Revenue - Vacancy - Credit Loss
```

**Code Reference**: `src/performa/core/ledger/queries.py` (gross_revenue method)

**Related Terms:** Potential Gross Income (PGI), Scheduled Rent

---

## H

### Hard Costs
**Industry Definition:** Direct construction costs for materials and labor.

**Examples:**
- Foundation and framing
- Mechanical, electrical, plumbing (MEP)
- Interior finishes
- Exterior work (facades, landscaping)

**Performa Implementation:**
- **Ledger**: `Capital / Hard Costs`
- **Flow Purpose**: `Capital Use`
- **Sign**: Negative (capital outflow)
- **Timing**: Posted during construction phase based on draw schedule
- **Code Reference**: Asset-specific capital plans

**Typical Percentage:** 70-80% of total development cost

**Related Terms:** Direct Costs, Construction Costs, Sticks and Bricks

---

### Holding Period
**Industry Definition:** Duration from acquisition to disposition.

**Typical Periods:**
- **Core**: 7-10+ years
- **Core Plus**: 5-7 years
- **Value-Add**: 3-5 years
- **Opportunistic/Development**: 3-7 years

**Performa Implementation:**
- **Timeline**: `Timeline` class defines analysis period
- **Acquisition**: First period (typically month 1)
- **Disposition**: Final period (e.g., month 60 for 5-year hold)
- **Code Reference**: `src/performa/core/primitives/timeline.py`

**Impact on Returns:**
```
Same equity multiple but different periods:
- EM 2.0x over 3 years = 26% IRR
- EM 2.0x over 5 years = 15% IRR
- EM 2.0x over 7 years = 10% IRR
```

**Related Terms:** Investment Horizon, Hold Period, Duration

---

## I

### Internal Rate of Return (IRR)
**Industry Definition:** Discount rate that makes NPV of cash flows equal to zero, annualized return metric.

**Types in Real Estate:**
1. **Levered IRR**: Return on equity after debt effects
2. **Unlevered IRR**: Return on project before debt effects
3. **Equity IRR**: Same as levered IRR (investor perspective)

**Performa Implementation:**
```python
# Levered (equity) IRR:
levered_irr = results.levered_irr
# Calculated from: levered_cash_flow series

# Unlevered (project) IRR:
unlevered_irr = results.unlevered_irr
# Calculated from: project_cash_flow series
```

**Calculation:**
```python
from numpy_financial import irr
levered_irr = irr(results.levered_cash_flow.values)
```

**Sign Convention Critical:**
- Cash flows must use investor perspective (contributions -, distributions +)
- First cash flow typically negative (initial contribution)
- Subsequent positive for profitable investments

**Code Reference**: `src/performa/core/calculations.py` (calculate_irr function)

**Related Terms:** Internal Rate of Return, Time-Weighted Return, XIRR (for irregular intervals)

---

### Investor Perspective
**Industry Definition:** (Performa-specific) Sign convention where cash flows are viewed from investor's pocket.

**Sign Convention:**
- Contributions: Negative (money OUT of pocket)
- Distributions: Positive (money INTO pocket)
- Net positive = profitable investment

**Usage:**
- **All IRR calculations**: Levered IRR, Unlevered IRR
- **All return metrics**: Equity Multiple, Cash-on-Cash
- **User-facing results**: `levered_cash_flow`, `equity_cash_flow`

**Performa Implementation:**
```python
# Internal (deal perspective):
deal_flows = equity_partner_flows()  # Contributions +, Distributions -

# User-facing (investor perspective):
investor_flows = -deal_flows  # Flip signs
levered_cash_flow = investor_flows  # Contributions -, Distributions +
```

**Why This Matters:**
- Industry standard for IRR calculations
- Intuitive: "I received money" = positive ✓
- Consistent with NCREIF, GIPS reporting standards

**Code Reference**: `src/performa/deal/results.py`

**Contrast**: Deal Perspective (internal ledger accounting only)

**Related Terms**: LP Perspective, Equity Holder View

---

## L

### Lease Commissions (LC)
**Industry Definition:** Fees paid to brokers for securing tenant leases.

**Typical Rates:**
- **New Leases**: 4-6% of total lease value
- **Renewals**: 2-3% of total lease value
- **Paid**: Upfront at lease execution

**Performa Implementation:**
- **Ledger**: `Capital / Leasing Commissions` (if coded)
- **Flow Purpose**: `Capital Use`
- **Timing**: Posted when lease is executed
- **Include In**: Capital expenditures, not operating expenses

**Formula:**
```
LC = Lease Term (years) × Annual Rent × Commission Rate
Example: 5 years × $50k/yr × 5% = $12,500
```

**Code Reference**: Lease structures, TI/LC calculations

**Related Terms**: Brokerage Fees, Leasing Costs

---

### Ledger
**Industry Definition:** (Performa-specific) Single source of truth for all financial transactions.

**Implementation:**
- **Technology**: DuckDB in-memory analytical database
- **Schema**: date, amount, category, subcategory, flow_purpose, entity, item
- **Purpose**: All financial calculations derive from ledger queries
- **Benefit**: Eliminates formula errors, ensures consistency

**Key Principle:**
```
Don't calculate with formulas.
Query the ledger for truth.
```

**Performa Implementation:**
- **Class**: `Ledger`
- **Queries**: `LedgerQueries` provides all query methods
- **Posting**: All transactions posted via `ledger.add_series()`
- **Code Reference**: `src/performa/core/ledger/ledger.py`, `src/performa/core/ledger/queries.py`

**Critical Insight:** The $20M gap was resolved by abandoning formulas and using ledger directly

**Related Terms**: Transaction Log, Financial Records, Books

---

### Levered Cash Flow (LCF)
**Industry Definition:** Cash flows to equity after all debt effects, used to calculate levered returns.

**Performa Implementation:**
- **Property**: `results.levered_cash_flow`
- **Calculation**: `=-equity_partner_flows()` with sign flip to investor perspective
- **Same As**: Equity Cash Flow, CFAE
- **Sign Convention**: Investor perspective (contributions -, distributions +)
- **Code Reference**: `src/performa/deal/results.py` (lines 117-165)

**What It Represents:**
```
Levered CF = Equity Contributions + Distributions
           = What investors actually experience
           = Foundation for levered IRR
```

**NOT a formula:**
```
# WRONG (old approach):
levered_cf = project_cf + debt_draws + debt_service

# RIGHT (current approach):
levered_cf = -equity_partner_flows()  # Just flip sign
```

**Key Insight:** Levered CF = Equity CF (they're the same thing!)

**Code Reference**: `src/performa/deal/results.py` (levered_cash_flow property)

**Related Terms**: CFAE, Equity Cash Flow, Free Cash Flow to Equity

---

### Levered Returns
**Industry Definition:** Returns on equity investment after accounting for debt financing effects.

**Metrics:**
1. **Levered IRR**: Internal rate of return on equity cash flows
2. **Equity Multiple**: Total return multiple on equity investment
3. **Cash-on-Cash**: Annual yield on equity investment

**Performa Implementation:**
```python
# Levered IRR:
levered_irr = results.levered_irr
# Calculated from levered_cash_flow series

# Equity Multiple:
equity_multiple = results.equity_multiple
# distributions / contributions

# Both use investor perspective
```

**Leverage Effect:**
```
Unlevered IRR:  15% (property performance)
Levered IRR:   25% (equity returns)
Leverage Boost: +10% (benefit of debt)
```

**Code Reference**: `src/performa/deal/results.py`

**Related Terms**: Equity Returns, After-Debt Returns, Geared Returns

---

### Loan-to-Cost (LTC)
**Industry Definition:** Ratio of debt financing to total development or acquisition cost.

**Formula:** LTC = Debt Amount / Total Cost

**Typical Ranges:**
- **Stabilized Acquisition**: 60-75%
- **Value-Add**: 65-75%
- **Development**: 55-65%

**Performa Implementation:**
```python
total_debt = queries.debt_draws().sum()
total_cost = abs(queries.capital_uses().sum())
ltc = total_debt / total_cost
```

**Impact:**
- **LTC > 100%**: Debt over-funds project (excess to operations/equity)
- **LTC = 100%**: Debt fully funds project
- **LTC < 100%**: Equity fills gap

**Critical Insight:** LTC ≠ 100% is why formula approach failed for levered_cash_flow

**Code Reference**: Calculated from `debt_draws()` and `capital_uses()` queries

**Related Terms**: LTV (Loan-to-Value), Leverage Ratio, Debt-to-Cost

---

### Loan-to-Value (LTV)
**Industry Definition:** Ratio of debt financing to property value.

**Formula:** LTV = Debt Amount / Property Value

**Typical Ranges:**
- **Core**: 50-60%
- **Core Plus**: 60-70%
- **Value-Add**: 65-75%
- **Development**: Based on stabilized value

**Performa Implementation:**
```python
total_debt = queries.debt_draws().sum()
property_value = valuation.value  # From appraisal or cap rate
ltv = total_debt / property_value
```

**Difference from LTC:**
- **LTC**: Debt / Cost (what you paid/spent)
- **LTV**: Debt / Value (what it's worth)

**Lender Focus:** LTV is key covenant, protects lender if forced to foreclose

**Code Reference**: Valuation classes determine property value

**Related Terms**: LTC (Loan-to-Cost), Leverage, Mortgage Constant

---

### LP (Limited Partner)
**Industry Definition:** Passive investor in real estate partnership, typically receives preferred return.

**Characteristics:**
- Provides majority of equity capital (90-95%)
- Limited liability (capped at investment amount)
- Passive role (no day-to-day management)
- Preferred return (6-10% annually)

**Returns:**
1. **Preferred Return**: Annual priority return (e.g., 8%)
2. **Return of Capital**: Get initial investment back
3. **Profits Above Preferred**: Split with GP per waterfall

**Performa Implementation:**
- **Partnership Structure**: Defined in `Partnership` class
- **Entity Type**: `entity_type='LP'`
- **Waterfall**: `PartnershipWaterfall` calculates LP priority
- **Code Reference**: `src/performa/deal/analysis/partnership.py`

**Related Terms**: Limited Member, Investor, Passive Partner

---

## M

### Mezzanine Financing
**Industry Definition:** Subordinated debt between senior debt and equity in capital stack.

**Characteristics:**
- **Position**: Junior to senior debt, senior to equity
- **Interest Rate**: 10-15% (higher than senior)
- **Security**: Second lien or equity pledge
- **Use**: Fills gap between senior debt and equity

**Performa Status:** Not yet fully implemented (Phase 2 feature)

**Related Terms**: Mezz Debt, Subordinated Debt, Junior Debt

---

## N

### Net Operating Income (NOI)
**Industry Definition:** Property revenue minus operating expenses, before debt service and capital expenditures.

**Formula:**
```
NOI = Gross Revenue - Vacancy - Credit Loss - Operating Expenses
    = Effective Gross Revenue - OpEx
```

**Performa Implementation:**
```python
# Query:
noi = queries.noi()

# Calculation:
noi = (gross_revenue + vacancy_loss + credit_loss) - opex
# Note: vacancy/credit losses are negative, so + is correct

# Alternative: Use flow_purpose
noi = SUM(flow_purpose='Operating' AND category IN ('Revenue', 'Expense'))
```

**What NOI Includes:**
- Rental income ✓
- Operating expenses ✓
- Property taxes and insurance ✓

**What NOI Excludes:**
- Debt service ✗
- Capital expenditures ✗
- Depreciation ✗
- Acquisition costs ✗

**Importance:**
- Primary driver of property value (Price = NOI / Cap Rate)
- Key metric for lenders (DSCR = NOI / Debt Service)
- Pure property performance (before financing and ownership effects)

**Code Reference**: `src/performa/core/ledger/queries.py` (noi method)

**Related Terms**: Net Income from Operations, Operating Income

---

## O

### Operational Cash Flow (OCF)
**Industry Definition:** Cash generated from property operations after all operating expenses and recurring capital expenditures.

**Formula:**
```
OCF = NOI - Recurring CapEx - TI - LC
```

**Performa Implementation (POST-FIX):**
```python
# Current (correct):
ocf = queries.operational_cash_flow()
# Single SQL query: flow_purpose='Operating' ONLY

# OLD (wrong):
# ocf = noi - capex - ti - lc
# (This caused double-counting)
```

**What It Includes:**
- All operating revenue (rent, recoveries)
- All operating expenses (utilities, maintenance, taxes)
- Recurring capital needs (if categorized as Expense/CapEx)

**What It Excludes:**
- Major capital deployments (acquisition, construction)
- Debt service
- Equity distributions

**Critical Fix (October 2025):** Now uses ONLY `flow_purpose='Operating'` to eliminate double-counting

**Code Reference**: `src/performa/core/ledger/queries.py` (operational_cash_flow method, lines 1072-1140)

**Related Terms**: Operating Cash, Property Cash Flow, NOPAT (corporate finance)

---

## P

### Pari Passu
**Industry Definition:** Latin for "equal footing" - investors receiving distributions proportionally to their ownership.

**Example:**
```
LP owns 90%, GP owns 10%
Distribution: $100k
Pari Passu split: LP gets $90k, GP gets $10k
```

**Performa Implementation:**
- Used in simple partnership structures without promote
- Contrasted with waterfall structures with preferred returns
- **Code Reference**: `src/performa/deal/analysis/partnership.py`

**Related Terms**: Pro Rata, Proportional, Equal Footing

---

### Partnership Waterfall
**Industry Definition:** Sequential allocation of cash flows to partners based on priority rules.

**Typical Structure:**
1. **Return of Capital**: LP gets capital back first
2. **Preferred Return**: LP gets preferred return (8%)
3. **GP Catch-Up**: GP catches up to LP return
4. **Remaining Profits**: Split per profit share (80/20, 70/30, etc.)

**Performa Implementation:**
- **Class**: `PartnershipWaterfall`
- **Tiers**: Defined sequentially with hurdles and splits
- **Lookback**: Can be lookback or straight
- **Code Reference**: `src/performa/deal/analysis/partnership.py`

**Example:**
```python
# 8% pref, 80/20 split after pref
waterfall = PartnershipWaterfall(
    tiers=[
        Tier(hurdle=0.08, lp_share=1.0),  # 8% pref to LP
        Tier(hurdle=None, lp_share=0.8),  # 80/20 split thereafter
    ]
)
```

**Related Terms**: Promote Structure, Distribution Waterfall, Carried Interest

---

### Preferred Return (Pref)
**Industry Definition:** Priority return paid to LP before GP receives promote/carried interest.

**Typical Rates:** 6-10% annualized

**Types:**
1. **Current Pay**: Paid annually/quarterly (rare in real estate)
2. **Cumulative**: Accrues, paid when cash available
3. **Lookback**: True-up at exit to ensure full pref achieved

**Performa Implementation:**
- **Ledger**: `Financing / Preferred Return`
- **Flow Purpose**: `Financing Service`
- **Calculation**: Part of partnership waterfall analysis
- **Code Reference**: `src/performa/deal/analysis/partnership.py`

**Example:**
```
LP Investment: $10M
Preferred Return: 8%
Annual Pref: $800k (paid before GP gets promote)
```

**Related Terms**: Hurdle Rate, Pref, Priority Return

---

### Project Cash Flow
**Industry Definition:** (Performa-specific) Unlevered cash flows before financing effects, represents pure property performance.

**Components:**
- Operating cash flows
- Capital expenditures
- Disposition proceeds
- Excludes: All debt and equity financing transactions

**Performa Implementation:**
```python
# Query:
project_cf = queries.project_cash_flow()

# Includes flow_purpose:
# - Operating (revenue & expenses)
# - Capital Use (acquisition, construction, disposition costs)
# - Capital Source (only Sale proceeds, NOT debt/equity)

# Excludes:
# - All Financing category transactions
```

**Usage:**
- Calculate unlevered IRR (property performance)
- Compare properties before financing decisions
- Evaluate asset quality independent of capital structure

**Code Reference**: `src/performa/core/ledger/queries.py` (project_cash_flow method, lines 1144-1204)

**Related Terms**: Unlevered Cash Flow, Property Cash Flow, Asset-Level Cash Flow

---

### Promote (Carried Interest)
**Industry Definition:** Disproportionate share of profits awarded to GP after LP receives preferred return.

**Typical Structure:**
- LP: 70-80% of profits above pref
- GP: 20-30% of profits above pref (promote)

**Performa Implementation:**
- **Ledger**: `Financing / Promote`
- **Flow Purpose**: `Financing Service`
- **Calculation**: Part of partnership waterfall
- **Code Reference**: `src/performa/deal/analysis/partnership.py`

**Example:**
```
Profits above 8% pref: $5M
Split: 80% LP / 20% GP
LP gets: $4M
GP gets: $1M (this is the promote)
```

**Alignment of Interest:**
- GP earns promote only if LP gets preferred return
- Motivates GP to maximize returns

**Related Terms**: Carried Interest, Carry, Performance Fee, Incentive Allocation

---

## R

### Refinancing
**Industry Definition:** Replacing existing debt with new debt, typically at maturity or to extract equity.

**Types:**
1. **Rate/Term Refi**: Better terms, same balance
2. **Cash-Out Refi**: New loan > old balance, excess to equity
3. **Construction-to-Perm**: Permanent loan replaces construction loan

**Performa Implementation:**
- **Analysis**: `DebtAnalyzer._execute_refinancing()`
- **Transactions**:
  1. Refinancing Proceeds (Capital Source, positive)
  2. Refinancing Payoff (Financing Service, negative)
- **Net Cash**: If proceeds > payoff, excess distributed to equity
- **Code Reference**: `src/performa/deal/analysis/debt.py` (lines 373-407)

**Ledger Example:**
```
Old Construction Loan: $22.0M
New Permanent Loan:    $22.2M
Cash-Out:              $0.2M → Equity Distribution
```

**Related Terms**: Refi, Recapitalization, Take-Out Financing

---

## S

### Sign Convention
**Industry Definition:** (Performa-specific) Rules for whether cash flows are positive or negative.

**Two Perspectives:**

1. **Deal Perspective** (Internal):
   - Cash INTO deal: Positive
   - Cash OUT OF deal: Negative
   - Used: Ledger records, `equity_partner_flows()` query

2. **Investor Perspective** (User-Facing):
   - Contributions: Negative (money out of pocket)
   - Distributions: Positive (money received)
   - Used: `levered_cash_flow`, `equity_cash_flow`, all IRR calculations

**Conversion:**
```python
deal_flows = equity_partner_flows()      # Contributions +, Dist -
investor_flows = -deal_flows             # Flip signs
levered_cf = investor_flows              # Now contributions -, Dist +
```

**Why It Matters:**
- IRR calculations require investor perspective
- Industry standard for return metrics
- Intuitive: "I received money" = positive ✓

**Documentation**: See `SIGN_CONVENTION.md` for complete reference

**Related Terms**: Perspective, Cash Flow Sign, Direction Convention

---

### Soft Costs
**Industry Definition:** Indirect development costs not directly related to construction.

**Examples:**
- Architecture and engineering fees
- Legal and accounting
- Permits and entitlements
- Financing fees
- Capitalized interest
- Developer fees

**Performa Implementation:**
- **Ledger**: `Capital / Soft Costs`
- **Flow Purpose**: `Capital Use`
- **Sign**: Negative (capital outflow)
- **Special**: Capitalized interest posted as soft costs by `ConstructionFacility`
- **Code Reference**: `src/performa/debt/construction.py` (capitalized interest), asset capital plans

**Typical Percentage:** 20-30% of total development cost

**Related Terms**: Indirect Costs, Development Fees, Project Costs

---

### Stabilization
**Industry Definition:** Point at which property reaches target occupancy and stable operations.

**Typical Criteria:**
- 90-95% physical occupancy
- 85-90% economic occupancy (accounting for abatements)
- 12 months of stable operations
- Meets proforma NOI

**Performa Implementation:**
- **Development**: End of lease-up period
- **Value-Add**: End of renovation and re-leasing
- **Refinancing Trigger**: Often refinance construction loan at stabilization
- **Code Reference**: Absorption plans, lease-up schedules

**Importance:**
- Triggers permanent loan funding
- Begins operating distributions
- Marks transition from development risk to operating asset
- Used for exit valuation

**Related Terms**: Lease-Up Complete, Fully Occupied, Steady State

---

## T

### Tenant Improvements (TI)
**Industry Definition:** Capital spent to customize space for tenant requirements.

**Typical Amounts:**
- **Office**: $40-80/SF
- **Retail**: $25-50/SF
- **Industrial**: $10-30/SF

**Performa Implementation:**
- **Ledger**: `Capital / Tenant Improvements` (if coded)
- **Flow Purpose**: `Capital Use`
- **Timing**: Posted at lease execution
- **Include In**: Capital expenditures, not operating expenses

**Formula:**
```
TI = Square Footage × TI Rate
Example: 5,000 SF × $60/SF = $300,000
```

**Code Reference**: Lease structures, TI/LC calculations

**Related Terms**: Leasehold Improvements, Build-Out Costs, Workletter

---

### Total Project Cost (TPC)
**Industry Definition:** Sum of all capital deployed for development project.

**Components:**
- Land acquisition
- Hard costs
- Soft costs
- Financing costs
- Contingency

**Performa Implementation:**
```python
# Query:
tpc = abs(queries.capital_uses().sum())

# Includes all:
# - Capital / Purchase Price
# - Capital / Closing Costs
# - Capital / Hard Costs
# - Capital / Soft Costs
# All with flow_purpose='Capital Use'
```

**Used For:**
- Loan-to-Cost (LTC) calculation
- Equity requirement determination
- Project feasibility analysis

**Code Reference**: `capital_uses()` query

**Related Terms**: Total Development Cost, All-In Cost, Project Budget

---

### Transaction Purpose
**Industry Definition:** See **Flow Purpose** (same concept)

---

## U

### Unlevered Cash Flow
**Industry Definition:** Cash flows before financing effects, represents pure property performance.

**Performa Implementation:**
- **Property**: `results.unlevered_cash_flow`
- **Same As**: `project_cash_flow`
- **Components**: Operating + Capital + Disposition (no financing)
- **Usage**: Calculate unlevered IRR
- **Code Reference**: `src/performa/deal/results.py` (unlevered_cash_flow property)

**Formula:**
```
Unlevered CF = Operating Cash Flow
             + Capital Uses
             + Disposition Proceeds (net of transaction costs)
```

**Excludes:**
- Debt service
- Debt proceeds
- Equity contributions
- Equity distributions

**Purpose:**
- Evaluate property performance independent of financing
- Compare properties with different capital structures
- Analyze asset quality

**Related Terms**: Project Cash Flow, Property-Level Cash Flow, Before-Debt Cash Flow

---

### Unlevered Returns
**Industry Definition:** Returns on total capital (debt + equity) before financing effects.

**Metrics:**
1. **Unlevered IRR**: IRR on project cash flows
2. **Asset-Level Return**: Property performance metric

**Performa Implementation:**
```python
# Unlevered IRR:
unlevered_irr = results.unlevered_irr
# Calculated from project_cash_flow series
```

**Comparison to Levered:**
```
Unlevered IRR:  15% (property performance)
Levered IRR:    25% (equity returns with debt)
Leverage Effect: +10% (benefit of debt)
```

**Usage:**
- Evaluate property quality
- Compare across different leverage levels
- Assess operating performance

**Code Reference**: `src/performa/deal/results.py`

**Related Terms**: Project Returns, Asset Returns, Before-Debt Returns

---

## V

### Value-Add
**Industry Definition:** Investment strategy involving property improvements to increase value.

**Typical Actions:**
- Physical renovations (units, lobbies, amenities)
- Operational improvements (management, marketing)
- Re-leasing to market rents
- Occupancy improvements

**Timeline:**
- Year 1-2: Renovations and repositioning
- Year 2-3: Lease-up to stabilization
- Year 3-5: Stabilized operations and exit

**Target Returns:** 15-20% levered IRR

**Performa Implementation:**
- **Asset Class**: Property with planned improvements
- **Capital Plan**: Renovation budget over 12-24 months
- **Revenue Growth**: Rent increases as units/spaces renovated
- **Example Scripts**: `examples/patterns/value_add_comparison.py`

**Code Reference**: Value-add example implementations

**Related Terms**: Opportunistic, Repositioning, Heavy Value-Add (20%+ renovation cost)

---

### Vacancy Loss
**Industry Definition:** Revenue reduction from vacant units or space.

**Calculation:**
```
Vacancy Loss = Potential Rent × Vacancy Rate
Example: $1M potential × 10% vacancy = $100k loss
```

**Performa Implementation:**
- **Ledger**: `Revenue / Vacancy Loss`
- **Flow Purpose**: `Operating`
- **Sign**: Negative (revenue reduction, contra-revenue)
- **Usage**: Reduces gross revenue to get effective revenue

**Formula:**
```
Effective Revenue = Gross Revenue + Vacancy Loss
(Vacancy Loss is negative, so + is correct)
```

**Code Reference**: Asset revenue models, NOI calculation

**Related Terms**: Vacancy Allowance, Unoccupied Space, Vacancy Factor

---

## W

### Waterfall
**Industry Definition:** See **Partnership Waterfall**

---

## Implementation Notes

### Document Maintenance
This glossary should be updated when:
1. New features are added (e.g., mezzanine financing)
2. Industry terms evolve
3. Performa implementations change
4. User feedback identifies missing or unclear terms

### Cross-References
- **Code Documentation**: See inline docstrings for implementation details
- **Audit Documents**: See `QUERY_DEFINITIONS.md`, `FLOW_PURPOSE_RULES.md`, `SIGN_CONVENTION.md`
- **Examples**: See `examples/patterns/*` for working implementations

### Glossary Usage
- **For Developers**: Understand industry context behind code
- **For Real Estate Pros**: Map familiar concepts to Performa implementation
- **For Users**: Learn both real estate and software terminology

---

**Document Version:** 1.0 (Post-Fix Implementation)  
**Last Updated:** October 2, 2025  
**Status:** ✅ Complete and Current  
**Related Documents:** 
- `QUERY_DEFINITIONS.md` - Detailed query specifications
- `FLOW_PURPOSE_RULES.md` - Transaction categorization rules
- `SIGN_CONVENTION.md` - Sign convention reference
- `GAP_RESOLUTION.md` - Fix implementation details


