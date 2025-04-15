Below is a structured catalog of the **data models** implied by Argus Enterprise/Valuation DCF, organized by the main **tabs** (interface sections) that drive the system's data entry and reporting. For each major tab, you will find:

- **Key subsections (where applicable)**
- **Important data inputs** (and their possible units)
- **Relationships/dependencies** (how the data ties together or drives other calculations)

Use this catalog to compare with the current package data structures and interfaces for @asset. Let's plan a strategy to methodically update the existing codebase to match the Argus Enterprise/Valuation DCF data models. For now, let's ignore Chart of Accounts, Actuals / Budget, and Attachments.

--------------------------------------------------------------------------------

# Argus Enterprise/Valuation DCF Manual

## 1\. Property Tabs

These tabs capture fundamental, per-asset information that underpins all subsequent calculations (rent rolls, cash flow modeling, valuation, etc.).

### 1.1 Description

- **Key Inputs**

  - **Property Name (text)**
  - **External ID (text)**
  - **Entity ID (text)**
  - **Property Type (dropdown)**: e.g. Office, Retail, Industrial, Multifamily, Hotel, Mixed Use
  - **Building Area (numeric)**: can also be entered as an area that changes over time
  - **Analysis Begin Date (date)**: drives the start of the projected analysis
  - **Length of Analysis (years + months)**: defines how many periods are modeled (up to 100 years)
  - **Use Actuals / Budget** flags and cutoff dates (dates)

- **Units / Potential Relationships**

  - **Building Area** is referenced anywhere calculations require area-based rates (rent, operating expenses, recoveries).
  - **Analysis Begin Date** shifts all time-based inputs (rent start dates, inflation).

### 1.2 Location

- **Key Inputs**

  - Address / City / State / Zip / Country (text fields or dropdown for country)
  - Parcel Number (text)

- **Relationships**

  - Generally informational (e.g., for advanced features that need location data).

### 1.3 Additional

- **Key Inputs**

  - Preparer Name (text)
  - Appraisal Number, Loan Number (text)
  - Year Built (numeric or year)
  - Portfolio Name (text)
  - Comments / Notes (text)

### 1.4 Attachments

- **Key Inputs**

  - Attachment Type (File vs. URL)
  - File Name or URL (string path)
  - Description / Comment (text)

- **Relationships**

  - Strictly reference or store external documents.

### 1.5 Area Measures

- **Purpose**

  - Define multiple building/occupancy areas (net rentable, office total, retail total, custom measures).

- **Key Inputs**

  - **Name (text)**: "Office NRA," "Storage Area," etc.
  - **Rentable Area** method:

    - **Enter Area** (numeric, can vary by date), or
    - **Sum of Other Rentable Areas**

  - **Occupied Area** method: All tenants, include/exclude specific tenants/groups, or by lease type

  - **Minimum / Adjusted Minimum** (optional numeric)

- **Relationships**

  - Area measures can be referenced in revenues, expenses, or recoveries (e.g., $/SF).

### 1.6 Chart of Accounts

- **Purpose**

  - Define the "parent" and "child" accounts used both for budgets (detailed G/L-level) and for summarized "cash flow" accounts.

- **Key Inputs**

  - **Account Type**: Parent or Child
  - **Parent Account** (if child)
  - **Account Number** (text or numeric)
  - **Description** (text)
  - **Class** (Revenue or Expense)
  - **Line Item Type** (e.g., Operating Expense, Capital, Non-Operating)

- **Relationships**

  - Each revenue/expense line item on other tabs references a Chart of Accounts entry.

### 1.7 Actuals / Budget

- **Purpose**

  - Store actual historical expenses (and some revenues) or prior-year budget data, typically monthly columns.

- **Key Inputs**

  - **Account Code** / **Account Name** (links to Chart of Accounts)
  - **Timing (monthly, quarterly, etc.)**
  - **Date Columns**: actual or budget amounts

- **Relationships**

  - Rolls up into expense or revenue lines for comparative or budgeting purposes.

### 1.8 Classification

- **Purpose**

  - Tag each asset with custom classification fields (e.g., "Region," "Property Grade," "Ownership Type").

- **Key Inputs**

  - **Classification** (dropdown)
  - **Value** (dropdown)

- **Relationships**

  - Often used for portfolio reports, sensitivity analyses, or filtering of grouped assets.

--------------------------------------------------------------------------------

## 2\. Market Tabs

These tabs focus on _portfolio-level market assumptions_ that drive rent growth, expense inflation, vacancy allowances, credit loss, and so on.

### 2.1 Inflation

- **Key Inputs**

  - **General Inflation Rate** (annual %)
  - **Market Inflation Rate** (annual %)
  - **Expense Inflation Rate** (annual %)
  - **CPI Inflation Rate** (annual %)
  - **Custom Inflation Rates** (optional, named)
  - **Inflation Month** (month name or "Analysis Date")
  - **Recovery Timing** (Fiscal vs. Calendar)

- **Relationships**

  - Ties directly to any revenue or expense lines marked to "Use Market/General/Expense/CPI inflation."
  - Recovery timing interacts with how annual recoveries are escalated.

### 2.2 Inflation Indices

- **Key Inputs**

  - Name (may link to global category)
  - Date + Amount + Units (Index Value vs. Percent Increase)
  - **Repeat Last Percentage** toggle

- **Relationships**

  - Index-based inflation references these monthly or annual index values.

### 2.3 General Vacancy

- **Key Inputs**

  - Method:

    - **Annual Amount**
    - **% of Potential Gross Revenue**
    - **% of Total Rental Revenue**
    - **% of Total Tenant Revenue**

  - Vacancy Amount or % (inflationable)

  - **Gross Up Revenue by Absorption & Turnover**? (toggle)

  - **Override Specified Tenants**? (per-tenant override %)

- **Relationships**

  - Subtracts from projected revenue for general vacancy / occupancy assumptions.

### 2.4 Credit Loss

- **Very similar structure to General Vacancy** with the additional credit loss % or amount that is subtracted from revenue.

### 2.5 Market Leasing

- **Purpose**

  - Store _leasing assumptions_ that apply once a tenant's current lease expires.

- **Key Inputs**

  - **Term (Yrs/Mos)**
  - **Renewal %**
  - **Months Vacant**
  - **New Market Rent / Renew Market Rent** (in $/SF/Year, $/SF/Month, $/Year, $/Month, or "Continue Prior")
  - **Rent Increases** (Fixed Steps, CPI timing, etc.)
  - **Free Rent** for new or renewing tenants (# months)
  - **Recoveries** default structure (Net, Base Year, Stop, None, etc.)
  - **Miscellaneous Items** (Misc. rent, incentives)
  - **Improvements** (TI $/SF or % of first-year rent)
  - **Leasing Commissions** (various methods: Fixed %, $/SF, # months base rent, etc.)
  - **Security Deposit** references
  - **Percentage Rent** (retail or mixed-use only)
  - **Intelligent Renewals** (use prior or market rent) toggles

- **Relationships**

  - Assigned to each tenant on the Rent Roll (see below).
  - Used also by "Space Absorption" for vacant blocks.

### 2.6 Free Rent Profiles

- **Purpose**

  - Let you define _which components of rent_ (base, step, CPI, percentage rent, recoveries, etc.) are abated during free rent periods.

- **Key Inputs**

  - **Name (text)**
  - **# of free months** (New vs. Renew)
  - **Abatement %** per component (Base Rent, Fixed Steps, CPI, Percentage Rent, Recoveries, Misc.)

- **Relationships**

  - Referenced on the Rent Roll or in Market Leasing profiles to specify how free rent is applied.

### 2.7 CPI Increases

- **Purpose**

  - Define custom categories for CPI-based rent escalations, including timing, min/max increases, partial indexing.

- **Key Inputs**

  - **Name (text)**
  - **Timing** (None, Each Calendar Year, Each Lease Year, At Mid-Lease, Specified Interval)
  - **Inflation Rate / Index** reference
  - **First Increase** / **Further Increases**
  - **Minimum Interval** (mo)
  - **% of CPI** plus **Min / Max**
  - **Current CPI Amount** (if needed)

### 2.8 Lease Commissions

- **Purpose**

  - Create re-usable "lease commission categories" with specific methods (Fixed %, 1st Month + %, $/SF, etc.) and specify which rent components to include.

- **Key Inputs**

  - **Commissions Unit** (None, $ Amount, $/SF, % by Year, etc.)
  - **New LC / Renew LC**
  - **Timing** (up-front, spread over lease years)
  - **Elements to Include** (Base Rent, Fixed Steps, CPI, Free Rent, Recoveries, etc.)

### 2.9 Market Rent Components

- **Purpose**

  - For advanced scenarios of "last rent" references: Standard Rent (base + steps + CPI + free) vs. total prior components vs. user-defined sets.

--------------------------------------------------------------------------------

## 3\. Revenues Tab

Enables modeling of non-lease revenues or specialized income.

**Sub-tabs**: **Miscellaneous**, **Parking**, **Storage** (plus specialized "Departmental" for Hotels).

### 3.1 Miscellaneous Revenues

- **Key Inputs**

  - **How Input**:

    - Amount 1 (a single currency amount),
    - Amount 1 × Amount 2,
    - $/Rentable Area, $/Occupied Area, or $/Vacant Area,
    - % of Effective Gross Revenue, Rental Revenue, or total tenant revenue,
    - "Sub-lines" (a hierarchical breakdown).

  - **Frequency** (Monthly vs. Annually)

  - **Fixed %** (for partial occupancy-based tie)

  - **Timing** (start/end dates)

  - **Inflation** (General, Market, Expense, or custom)

  - **Limits** (Min/Max monthly)

  - **Memo** toggle (excludes from NOI but can be used in % of other calculations)

### 3.2 Parking Revenues

- **Key Inputs**

  - **How Input**: $/Space/Month, $/Space/Year, $/Month, $/Year
  - **# of Spaces** (can vary)
  - **Fixed %** occupancy scaling
  - **Timing**, **Inflation**, **Limits** (similar to Misc. Revenues)

### 3.3 Storage Revenues

- **Key Inputs**

  - **How Input**: $/Month, $/Year, $/SF/Month, $/SF/Year
  - **Area** (optional or can vary over time)
  - **Fixed %** occupancy scaling
  - **Timing**, **Inflation**, **Limits**

### 3.4 (Hotels) Departmental Revenues

- **Key Inputs**

  - **How Input**: $/Room, $/Occup'd Room Night, $/Available Room Night, % of Room Revenue, etc.
  - **Frequency** (Annual, Monthly, Weekly, Nightly)
  - **Category** (Departmental vs. Misc.)
  - **Limits** (Min/Max)
  - **Inflation** references

### 3.5 (Hotels) Parking, Rooms

- **Hotel Parking** is similar to standard Parking, but can also tie to rooms.
- **Hotel Rooms** defines the _room mix_, average daily rate, occupancy percentages, etc.

--------------------------------------------------------------------------------

## 4\. Expenses Tab

Includes _Operating_, _Non-Operating_, _Capital_ expenses, plus _Expense Groups_ for grouping.

### 4.1 Operating Expenses

- **Key Inputs**

  - **How Input**:

    - Amount 1,
    - Amount 1 × Amount 2,
    - $/Rentable, $/Occupied, $/Vacant,
    - % of Rental Revenue, Tenant Revenue, or Effective Gross,
    - % of Another line item.

  - **Frequency** (Annual/Monthly)

  - **Fixed %** (how much is fixed vs. variable occupancy)

  - **Recoverable %** (default; can be overridden by custom recovery structure)

  - **Timing** (start/end)

  - **Inflation** (Expense vs. Market vs. CPI, etc.)

  - **Limits** (Min/Max monthly)

  - **Memo** toggle

### 4.2 Non-Operating Expenses

- **Structure** is nearly identical to Operating but often not recoverable.

### 4.3 Capital Expenses

- **Key Inputs**

  - **Project ID** (optional)
  - **How Input** / Frequency / Timing / Inflation / Limits
  - Typically 100% fixed. Optionally flagged as "Memo."

### 4.4 Expense Groups

- **Purpose**

  - Combine multiple Operating Expenses into a single group for advanced recoveries (e.g., capping or multi-step pass-through).

- **Key Inputs**

  - Group Name
  - Included vs. Excluded Expenses
  - Recoverable % adjustments

- **Relationships**

  - Linked from custom Recovery Structures to specify the method for a set of grouped expenses.

--------------------------------------------------------------------------------

## 5\. Tenants Tab

Most critical for lease-by-lease modeling. _Sub-tabs_:

1. **Rent Roll**
2. **Space Absorption**
3. **Recovery Structures**
4. **Tenant Groups**
5. **Security Deposits**

### 5.1 Rent Roll

- **Key Inputs** (per-tenant row)

  1. **Name, Suite, Lease Status, Lease Type**
  2. **Area** (with optional Variation Over Time)
  3. **Lease Start, End** (term-based or explicit date)
  4. **Base Rent** (units: $/SF/Year, etc.), plus steps, CPI, free rent
  5. **Percentage Rent** (retail)
  6. **Recoveries** (method: Net, Base Year, Stop, Fixed, or a user-defined structure)
  7. **Miscellaneous Items** (tenant-level additional rent or capital incentives)
  8. **Leasing Costs** (improvements, commissions)
  9. **Market Leasing** link + "Upon Expiration" (Market, Renew, Vacate, Option, etc.)
  10. **Override Renewal Probability, Vacant Months**
  11. **Security Deposit** record

- **Detailed Schedules**

  - **Detailed Rent Schedule** (base + steps + reviews)
  - **Detailed Percentage Rent** (sales amounts, breakpoints)
  - **Detailed Recoveries** (varies if fixed or stop amounts)
  - **Detailed Commission Timing** (if spread out)

- **Relationships**

  - Ties to the **Market Leasing** tab for next-term assumptions.
  - Ties to Chart of Accounts (expense or revenue codes).
  - Summarizes up into the property-level cash flow.

### 5.2 Space Absorption

- **Purpose**

  - Quickly subdivide large vacant blocks and lease them out speculatively (with a chosen Market Leasing profile).

- **Key Inputs**

  - **Name** (Vacant Office)
  - **Auto Generate** toggle
  - **Area to Lease** / **Average Lease Area**
  - **Date Available** / **First Lease Date**
  - **Absorption Months** or **Months Between Leases**
  - **Market Leasing** profile reference

### 5.3 Recovery Structures

- **Purpose**

  - Create user-defined pass-through/cap structures beyond the standard (Net, Base Year, etc.). E.g. partial pass-through, group caps, floor/ceiling, etc.

- **Key Inputs**

  1. **Name**
  2. **Gross-Up %** (for variable portion)
  3. **Assign Tenants** (which tenants use it)
  4. **One or more lines** each referencing:

    - **Expense or Group**
    - **Recovery Calc** (Net, Base Year, Fixed, Stop, etc.)
    - **Amount** (if fixed or stop)
    - **Allocation** (Pro-rata area, fixed percentage, custom denominated area)
    - **Limits** (min floor, max ceiling, year-over-year cap)

- **Relationships**

  - Tenants in the Rent Roll can select "User Recovery Structure" instead of standard Net/Base Year, etc.

### 5.4 Tenant Groups

- **Purpose**

  - Group specific tenants for reference in area measures or for overriding vacancy/credit loss, etc.

- **Key Inputs**

  - **Tenant Group Name**
  - **Include / Exclude** selected tenants

### 5.5 Security Deposits

- **Purpose**

  - Parameterize how refundable vs. non-refundable deposits are calculated for each tenant.

- **Key Inputs**

  - **Refundable** vs. **Non-Refundable**: (Unit: Months, $ Amount, $/Area)
  - **Amount**
  - **Interest Rate** for refundable portion
  - **% to Refund** (the remainder is retained)

--------------------------------------------------------------------------------

## Relationship Highlights

1. **Property**-level data (Building Area, Start Date, Analysis Length) flows down to _every_ revenue/expense timing calculation.
2. **Market** data (inflation, vacancy, credit loss, market leasing) merges with each tenant's lease rollover or vacant absorption.
3. **Rent Roll** references the Market Leasing profiles for expansions/rollovers, while also specifying unique overwrites (renewal prob, months vacant).
4. **Recovery** structures tie together Operating Expenses (and/or groups) with specific pass-through rules.
5. **Investment** data (purchase price, financing) is used to produce levered IRRs and debt coverage metrics.
6. **Valuation** data (direct cap, resale, present value) is the final step for "exit value," "NPV," and "IRR" calculations.

--------------------------------------------------------------------------------

## Summary

Argus Enterprise/Valuation DCF models commercial real estate with a **hierarchical** data structure:

- **Property-level** descriptive data and _model-wide_ assumptions (inflation, vacancy, etc.).
- **Revenue** lines (leases, plus miscellaneous/parking) that heavily reference area, market leasing, and timing rules.
- **Expense** lines (operating, non-operating, capital) that also reference area, occupancy, inflation, and recoveries.
- **Tenant-level** or **space-level** detail (Rent Roll, absorption, customized pass-through structures).
- **Purchase & Financing** details for _leveraged returns_.
- **Valuation** modules (direct capitalization, discounted cash flow, and resale scenarios) that rely on the above inputs.

Everything ties back into the monthly or annual cash flow engine, culminating in **NOI, net cash flows, IRR, and property valuations**. By mapping these data points to your own system, you can compare how each category of input and relationship is captured and how the resulting analysis is reported.
