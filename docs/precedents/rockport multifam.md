Below is a **sample “rubric”** for a Multifamily property type, mirroring the structure of the Office/Retail rubric but tailored to the Multifamily features and inputs described in the training manual. The goal is simply to catalog and organize the **data points**, **fields**, and **settings** that might appear in a Multifamily underwriting application or data model. Feel free to adjust naming or groupings as needed.

---

# Rockport VAL Settings and Models for Multifamily Residential

Below is an outline of the major sections (similar to a sidebar navigation) and the key inputs or configurations within each section.

## 1. Dashboard

- **Key Metrics Display**  
  - Valuation (e.g. “As Is” Value, Stabilized Value)  
  - Average Rent (e.g. current actual rent/unit)  
  - Occupancy Rate (current)  
  - KPI Snapshots (e.g. Effective Gross Revenue, NOI, IRR)  

## 2. Property Details

- **Basic Information**  
  - Property Name  
  - Property Type (Multifamily)  
  - Address / Location  
  - Year Built / Renovated (optional)  
  - Number of Buildings (optional)  
  - Number of Floors (optional)  

- **Ownership & Management** (optional/metadata)  
  - Owner / Operator  
  - Management Company  

## 3. Settings

### 3.1 Model Settings

1. **Analysis Start Date**  
2. **Analysis Period** (in years, e.g. 5, 10, etc.)  
3. **Inflation Month** (which month triggers the annual inflation)  
4. **Allow Specific Dates** (bool) – whether to allow mid-month or exact day start/stop  
5. **Allow Manually Entered Property Size** (bool) – usually auto-populated from # of units, but can override  

#### Additional Model-Level Items

- **Turnover Cost Allocation** or similar setting (where to show TIs / LC equivalents in multifamily)  
- **Reimbursement/Inflation Settings** – if any reimbursements are applicable (rare in standard multifamily, but might exist for rubs/utility reimbursements).  

### 3.2 Vacancy & Collection Loss

- **Vacancy Loss**  
  - % of Potential Gross Income  
  - % of Scheduled Base Rent  
  - (Possible variants or custom basis)  

- **Collection Loss**  
  - % of Potential Gross Income  
  - % of Effective Gross Income  
  - (Likewise, custom basis)  

- **Separate or Combined Fields**  
  - “Vacancy %”  
  - “Collection Loss %”  

### 3.3 Area Settings

*(In multifamily, “Area Settings” may be simplified. Typically includes:)*

- **Property Size** (Number of units)  
- **Unit Mix** (rolled up total: e.g. total 1BR count, total 2BR count, etc.)  
- **Average Unit Size (SF)**  
- **Lot Size** (optional)  

## 4. Chart of Accounts (COA)

*(Same concept as in Office/Retail—optional or custom COA for line items.)*

## 5. Income & Expenses

### 5.1 Miscellaneous Income

Use this for any revenue that is *not* specifically part of the unit rent roll. Common examples in multifamily:

- **Parking**  
- **Laundry / Vending**  
- **Antenna / Rooftop**  
- **Storage Units**  
- **Signage**  
- **Security Deposit Forfeitures** (modeled as revenue, if applicable)

**Typical Fields** (similar to Office/Retail):

- **Type**  
- **Description**  
- **Account** (link to COA)  
- **Amount**  
- **Unit of Measure (UoM)**  
  - \$$ amount  
  - \$/unit (per physical unit)  
  - \$/area (rare in multifamily)  
  - % of EGR or % of specific line  
- **Frequency** (monthly, yearly)  
- **Growth assumptions**  
  - Growth rate reference  
- **Variable Income** (bool)  
  - % variable portion  
- **Reimbursable** (bool) – more common in commercial, but could appear for certain pass-through items  

### 5.2 Operating Expenses

**Examples**: Maintenance, Utilities, Insurance, Management Fees, Property Taxes, etc.

**Table Columns** (same format as Misc. Income):

- **Type**  
- **Description**  
- **Account**  
- **Amount**  
- **UoM**  
  - \$$ amount per year  
  - \$/unit (per apartment)  
  - \$/area (e.g. per SF)  
  - % of EGR or % of Line  
- **Frequency** (monthly, yearly, a specific month)  
- **Growth Assumptions**  
  - Tied to an expense growth rate (e.g. 3% per year)  
- **Variable Expense** (bool)  
  - % variable portion  
- **Reimbursable** (bool) – typically not used in standard multifamily, but possible if there's utility recapture (RUBS).  

**Additional Features**:  

- **Payment Month** (e.g., property taxes paid in October).
- **Edit Detailed Timeline** – some items might be paid only once a year.  

### 5.3 Capital Expenses

**Examples**: Reserves (per unit), Roof Replacement, Building Improvements, Renovation CapEx.

**Table Columns** (same or very similar to Operating Expenses):

- **Type**  
- **Description**  
- **Account**  
- **Amount**  
- **UoM** (\$, \$/Unit, \$/SF, or % of EGR)  
- **Frequency** (one-time, monthly, yearly)  
- **Growth assumptions**  
- **Variable** (bool) – less common, but possible  
- **Reimbursable** (bool) – rarely used in multifamily, but keep for consistency  

**Drill-Down Timeline**:

- For large CapEx, allow a custom monthly/annual schedule of spending.  

## 6. Rent Roll

In Multifamily, the Rent Roll often has two modes:

1. **Unit Mix** – aggregated view by unit type.  
2. **Detailed Rent Roll** – each individual unit with a line.  

### 6.1 Unit Mix (Aggregate Rent Roll)

**Possible Table Fields:**

- **Unit Type** (e.g. “1BR”, “2BR”)  
- **Occupancy Status** (occupied, vacant, etc.)  
- **Number of Units**  
- **Avg SF/Unit**  
- **Start Date** (lease start if aggregated)  
- **Lease Term** (months)  
- **Rent**  
  - \$/Unit/Month  

- **Rent Control / Stabilized / Section 8** indicators (bool or category)  
- **Market vs. Affordable** subtypes  

*(When aggregated by unit type, these fields represent an average or a total for that group.)*

### 6.2 Detailed Unit-Level Rent Roll

**Possible Table Fields**:  

- **Unit #** (unique apartment ID)  
- **Unit Type**  
- **Building #** (if multiple buildings)  
- **Floor** (optional)  
- **Occupancy Status** (occupied, vacant, etc.)  
- **Area** (SF)  
- **Current Rent** (\$/Month)  
- **Lease Start / Lease End**  
- **Lease Term** (months)  

### 6.3 Import from Excel

- Ability to download an import template and map unit-level fields.  
- Validate & handle errors (e.g., missing unit #, invalid rent, etc.).

## 7. Leasing / Rollover Assumptions

This is often referred to as **RLA** (Rollover Lease Assumptions) or simply “Leasing Assumptions.”  

**Common Fields**:

- **RLA Name**  
- **Active** (bool)  
- **Renewal Probability** (percent)  
- **Lease Term** (mo)  
- **Downtime** (days or months)  

- **Market Rents**  
  - New \$/Unit/Month (can tie to Market Rent Growth)  
  - Renew \$/Unit/Month (can tie to Market Rent Growth or a separate factor)  
  - Growth Assumption Reference  

- **Concessions / Free Rent**  
  - New (months)  
  - Renew (months)  

- **Turnover Costs** (similar to TIs in office, but for multifamily)  
  - New \$/Unit  
  - Renew \$/Unit  

- **Leasing Commissions** (optional for multifamily, but sometimes used)  
  - New \%  
  - Renew \%  
  - If needed, tie to a Growth Assumption  

- **Upon Expiration** (Market, Renew, Vacate)  

## 8. Unit Mix & Exceptions (Advanced Multifamily Modeling)

In many multifamily models, a separate screen or workflow allows you to:

- **Roll up by** certain attributes (Unit Type, Building, etc.)  
- Apply different absorption assumptions or renovation scenarios for a subset of units.  
- **Renovation toggles**  
  - Renovation period (days/months)  
  - Renovation cost \$/Unit  
  - Renovated rent \$/Unit  

- **Absorption assumptions** for vacant or renovated units  
  - Start absorption date (day offset)  
  - Absorption period (how many months to fully lease)  
  - Which leasing assumption (RLA) to apply  

- **Unit Exceptions**  
  - Flag individual units for unique assumptions if they deviate from the standard.  

## 9. Assumptions

### 9.1 Growth Rates

- **Name** (e.g. General Growth, Market Rent Growth, Misc. Income Growth, Expense Growth, etc.)  
- **Rate Type** (constant vs. different per year)  
- **Year-by-year or monthly fields** to define the growth % across the analysis.  

### 9.2 Renovation & Absorption

*(Sometimes integrated into “Unit Mix & Exceptions.”)*

- **Reno cost** \$/Unit  
- **Reno timeline** (days/months)  
- **Reno rent** (post-renovation rent)  
- **Absorption** (lease-up period for newly vacant or newly renovated units)  

### 9.3 Vacancy & Collection Loss

(Already covered above in “Vacancy & Collection Loss” settings.)

## 10. Property Cash Flow

- High-level summary of Net Rental Income, Misc. Income, Operating Expenses, Capital Expenses, Net Operating Income, etc.  

## 11. Valuation

### 11.1 Valuation Methods

- **Discounted Cash Flow (DCF)**  
  - Cap Rate (Terminal)  
  - Discount Rate  
  - Residual Sale (which year to cap, or hold period)  
  - Cost of Sale (%)  

- **Direct Capitalization**  
  - Valuation Date (which year’s NOI to use)  
  - Cap Rate  
  - Stabilized vs. As-Is  

- **Direct Entry**  
  - Enter a fixed purchase price or value  

### 11.2 Sale Yield Matrix / Sensitivities

- Multiple increments of Cap / Discount rates to see value changes.  

## 12. Debt

*(Up to 5 or more loans, plus optional refinance loan.)*

- **Loan Name**  
- **Loan in Use** (bool)  
- **Loan Sizing** (bool)  
  - Max LTV  
  - Min DSCR  
  - Min Debt Yield  
  - Valuation Method Reference  
  - NOI reference (Forward 12 months, etc.)  

- **Loan Terms**  
  - Loan Amount  
  - Interest Rate  
  - Amortization Period  
  - Loan Term  
  - Accrual Method (30/360, Actual/365, etc.)  
  - Note Date (funding date)  

- **Refinance Loan**  
  - Payoff other loans on a specified date  

## 13. Scenarios & Sets

- **Scenario Name** (e.g. “Downside,” “Upside,” “Base Case”)  
- **Combining sets** of RLA, growth rates, vacancy/collection assumptions, etc.  
- **Scenario Comparison** (displays side-by-side results for key metrics).  

## 14. Reports

- **Property Cash Flow Report** (detailed monthly or annual)  
- **Rent Roll Mark-to-Market** (compare current contract rents vs. market)  
- **Valuation** (DCF, Direct Cap, or Direct Entry)  
- **Investment Analysis / Return Sensitivities** (unlevered & levered IRR, NPV)  
- **Amortization Schedule** (Loan-level detail)  
- **Levered IRR Summary**  
- **Report Packages** (combine multiple reports into a single output)  
- **Scenario Comparison & Cashflow Variance**  

## 15. Additional Collaboration / Interface Features

- **Share Model**: Generate a share link or invite collaborators.  
- **Versions**: Archive or label “snapshot” versions of the model.  
- **Import/Export**: Copy/paste from Excel, import rent roll, export final model or reports.  
- **User Permissions**: (Optional) read-only vs. edit.  

### Notes & Observations

1. **Renovations & Absorption** are particularly important in multifamily. A user may have specific toggles and cost fields that do not appear in an office/retail model.  
2. **Unit Type vs. Unit Subtype** (e.g., Market, LIHTC, Section 8, etc.) can further refine the rent roll logic.  
3. **Vacancy & Collection Loss** typically remain high-level percentages for the entire property in multifamily, unless more granular sub-market modeling is needed.  

## Summary

This rubric parallels the **Office/Retail** structure (Model Settings, Vacancy, Income & Expenses, Rent Roll, Rollover/Leasing, Valuation, Debt, Scenarios, etc.) but includes **multifamily-specific** features such as **Unit Mix**, **Renovation/Absorption** assumptions, and **Unit Sub Types**. Each section outlines the **typical fields**, **table columns**, and **business logic** relevant to multifamily underwriting.
