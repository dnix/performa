**I have summarized the rockport val settings and models below. Following this, I have included a tutorial for creating an office model.**

--------------------------------------------------------------------------------

# Rockport VAL Settings and Models for Office/Retail

**The following are sections in the application sidebar:**

## Dashboard

## Property Details

## Settings

### Model Settings

#### General Models Settings

- **Analysis start date**
- **Analysis period**
- **Reimbursement/inflation settings**
- **Inflation Month**
- **Allow specific dates**
- **Allow manually entered property size**

#### Vacancy and Collection Loss

- **Vacancy loss calculation method**
- **Gross-up revenue by downtime** (bool)
- **Reduce vacancy by downtime** (bool)

#### Percentage Rent/Occupancy Cost

- **In use** (bool) = no
- **Occupancy cost adjustment settings**

  - **Adjust** (downward vs ???)
  - **Include recoveries** (bool) = yes
  - **Adjust during** (rollover vs ???)

#### Recoveries

- **Apply admin fee before/after contrubution deduction** (after vs before)
- **Treat contribution deduction circular references as** (error vs warning)

#### Rollover

- **Start rollover leases on the 1st of the month** (bool) = no

### Area Settings

## COA

## Income & Expenses

### Misc Income

**Using for miscellaneous revenue like parking or vending**

**Table of misc income settings, with the following columns:**

- **Type**
- **Description**
- **Account**
- **Amount**
- **Unit of measure (UoM)** ($ amount, $/area, % of EGR, % of line)
- **Frequency** (yearly, monthly)
- **Area**
- **Growth assumptions** (tied to growth rates object for misc income growth)
- **Growth rate**
- **Variable income** (bool)
- **% variable**
- **Reimbursable** (bool)

### Operating Expenses

**Table of operating expense settings, with the following columns:**

- **Type**
- **Description**
- **Account**
- **Amount**
- **UoM** (\$ amount, $/area, % of EGR, % of line)
- **Frequency** (yearly, monthly)
- **Area**
- **Growth assumptions** (tied to growth rates object for misc income growth)
- **Growth rate**
- **Variable income** (bool)
- **% variable**
- **Reimbursable** (bool)

**Items can also be grouped into a "parent item" purely as a visual aid, and to make it easier to manage a large number of items in collapsable groups**

**The interface allows for copy-paste from excel, assuming the same table structure**

### Capital Expenses

**Table of capital expense settings, with the following columns:**

- **Type**
- **Description**
- **Account**
- **Amount**
- **UoM** (\$ amount, $/area, % of EGR, % of line)
- **Frequency** (yearly, monthly)
- **Area**
- **Growth assumptions** (tied to growth rates object for misc income growth)
- **Growth rate**
- **Variable income** (bool)
- **% variable**
- **Reimbursable** (bool)

**Amount can be drilled into for a detailed timeline grid of capital expenditures**

## Rent Roll

### Rent Roll

**Model contractual or speculative leases.**

**Table of rent roll settings, with the following columns:**

- **Tenant name**
- **Suite**
- **Floor**
- **Space type**
- **Status** (examples: contract, ...)
- **Available date**
- **Start date**
- **End date**
- **Lease term**
- **Area**
- **Base rent**

  - **Amount**
  - **UoM**

- **Rent steps** ($ amount or percentage increase based on various UoM, relative or absolute)

- **Free rent** (months/years)

- **Recovery method** (uses a Method object, also built-in default NNN or BaseYear methods) (or RLA ref)

- **TIs**

  - **Amount** (or RLA ref)

- **LCs**

  - **Amount** (or RLA ref)

- **Upon expiration** (market, renew, vacate, option, reconfigured)

- **Rollover assumptions**

- ...

### Stacking Plan

**Viz of stacking plan**

## Recoveries

### Methods

**Recovery method object**

- **Name**
- **Gross up** (bool) = on

  - **Percentage**

- **Recovery pools, structure, & admin fees**

  - **Expense/pool reference** (e.g., CAM)
  - **Recovery structure** (e.g., net, base stop, fixed, BY (calc/future), BY+1, BY-1, etc.)

    - **Amount** ($ amount or $/sf)
    - **Growth rate reference**

  - **Contribution deduction**

  - **Admin fee** (%)

- **Prorata share & denominators**

  - **PRS**
  - **Denominator**

- **Year over year recovery growth**

  - **YOY min growth ref**
  - **YOY max growth ref**

- **Recovery floors & ceilings**

  - **Recover floor**
  - **Recover ceiling**

### Expense Pools

**Ability to create and manage expense pools (groups of expenses to refer to elsewhere)**

**E.g. CAM pool vs property taxes**

### Tenant Groups

### Admin Fees

## Assumptions

### Growth Rates

**Table of growth rate settings, with the following columns:**

- **Growth rate name** (examples: general growth, market rent growth, misc income growth, operating expense growth, leasing costs growth, capital expense growth)
- **Rate type** (use general vs direct entry)
- **Rate**
- **Several columns of years** ("year ending") with rate values across the analysis period

### Vacancy & Collection Loss

**Table of vacancy and collection loss settings, with the following columns:**

- **Loss type** (examples: vacancy loss, collection loss)
- **Loss basis** (examples: potential gross, effective gross, net operating income)

### Rollover

**Table of rollover settings, with the following columns:**

- **RLA name**
- **Active** (bool)
- **Renewal probability**
- **Term**
- **Downtime** (mo)
- **Market rents**

  - **New amount**
  - **New UoM** (e.g., $/SF/yr)
  - **Renew amount**
  - **Renew UoM**
  - **Growth assumptions ref**

- **In term adjustments**

  - **Increase**
  - **UoM**
  - **Start increase**
  - **Recurring**

- **Free rent**

  - **New** (months)
  - **Renew** (months)
  - **In/out** (?)

- **Tenant improvements (TI)**

  - **New**
  - **New UoM**
  - **Renew**
  - **Renew UoM**

- **Leasing commissions**

  - **New**
  - **New UoM**
  - **Renew**
  - **Renew UoM**
  - **Growth assumptions ref**

- **Recovery method ref**

- **Upon expiration** (RLA ref)

### Rent Roll Overrides

### Scenarios & Sets

## Valuation

## Debt

## Scenario Comparison

## Reports

## ---

**Below is a systematic, step‐by‐step plan--with pseudocode details--for updating the existing asset codebase into a fuller implementation that more closely aligns with the Rockport VAL/Argus functionality. This plan assumes you're willing to rework or replace parts of the current implementation.**

--------------------------------------------------------------------------------

## 1\. Requirements Analysis & Domain Modeling

**A. Review the Rockport VAL spec and tutorial:**

- **Identify key areas:**

  - **Global model settings** (analysis start date, inflation/reimbursement settings, specific date allowance, manual property size entry)
  - **Vacancy and collection loss calculations**
  - **Detailed revenue income streams** including misc. income and rent roll details
  - **Expanded operating and capital expense settings** (fields for UoM, frequency, account, grouping, etc.)
  - **Advanced lease details** (tenant name, suite, floor, status, free rent schedules, rent steps that can be defined in multiple units, rollover assumptions)
  - **Recovery methods** (with gross-up, admin fees, year-over-year caps, contribution deduction logic)
  - **Debt, financing, and cash flow** (construction, permanent financing, closing cost models)

**B. Map Existing Models to New Concepts:**

- **Property/Project:** Enrich with global settings.
- **Revenue/Lease:** Extend your existing Lease and Tenant models to include more granular fields (suite, floor, rent steps, free rent details, percentage rent, rollover assumptions).
- **Expense:** Extend ExpenseItem and CapExItem to include frequency, UoM, account numbers, and grouping (parent/child relationships).
- **Recovery:** Expand the RecoveryMethod and related structures with additional fields: contribution deductions, gross-up percentages, multiple method options (Base Stop, Net, Fixed, etc).
- **Settings Module:** Consider creating new classes (or modules) for ModelSettings, VacancySettings, and RolloverSettings. These can either be part of the Property model (as embedded settings) or stand-alone models referenced by a Property/Project.

--------------------------------------------------------------------------------

## 2\. Design New or Revised Models and Relationships

**A. Create a Settings Submodule (e.g., `src/performa/asset/_settings.py`):**

- **ModelSettings:**

  ```python
  # Pseudocode for ModelSettings structure:
  class ModelSettings(Model):
      analysis_start_date: date
      analysis_period_months: int
      inflation_month: Optional[int]
      allow_specific_dates: bool
      allow_manual_property_size: bool
      # additional fields from "General models settings"
  ```

- **VacancySettings:**

  ```python
  class VacancySettings(Model):
      vacancy_loss_method: Literal["potential_gross", "EGR", "NOI"]
      gross_up_by_downtime: bool
      reduce_vacancy_by_downtime: bool
  ```

- **RolloverSettings:**

  ```python
  class RolloverSettings(Model):
      start_on_first_of_month: bool
      renewal_probability: FloatBetween0And1
      default_term: PositiveInt
      downtime_months: PositiveInt
      # Include fields for rent, free rent adjustments, TI, LC, etc.
  ```

_Implement these as either embedded objects within the Property model or as separate entities referenced by the project._

**B. Update Revenue Models – Extend Lease and Misc Income**

- **MiscIncome Model:**

  ```python
  class MiscIncome(Model):
      type: str
      description: str
      account: str
      amount: PositiveFloat
      unit_of_measure: Literal["$", "$/Area", "% of EGR", "% of Line"]
      frequency: Literal["monthly", "yearly"]
      area: Optional[PositiveFloat]
      growth_rate: Optional[FloatBetween0And1]
      is_variable: bool
      percent_variable: Optional[FloatBetween0And1]
      reimbursable: bool
  ```

- **Lease Enhancements:**

  - **Add fields:** suite, floor, status, tenant details.
  - **Expand rent steps into a dedicated model** (e.g., `RentStep`) that identifies the step type (fixed, percentage, etc.) and timing details:

    ```python
    class RentStep(Model):
        step_type: Literal["fixed", "percentage", "cpi"]
        amount: PositiveFloat  # fixed amount or percentage (depending on type)
        frequency_months: int
        start_date: date  # or relative (month index)
    ```

  - **Update the existing Lease model to incorporate:**

    - A list of `RentStep` objects.
    - A structured `FreeRentSchedule` similar to rent steps.
    - Detailed fields for percentage rent and TI/LC (possibly subclasses or helper models for payment schedules).

**C. Update Expense Models**

- For **OperatingExpense**, create a subclass of ExpenseItem including additional parameters:

  ```python
  class OperatingExpense(ExpenseItem):
      account: Optional[str]
      unit_of_measure: Literal["$", "$/Area", "% of EGR", "% of Line"]
      frequency: Literal["monthly", "yearly"]
      parent_item: Optional[str]  # identifier for grouping expenses
  ```

- For **CapitalExpense**, extend CapExItem to include similar additional attributes and link to a detailed timeline if desired (for drilling down the scheduling).

**D. Update Recovery and Debt Models**

- **Recovery Methods:**<br>
  Expand the model to include:

  ```python
  class RecoveryMethod(Model):
      name: str
      gross_up: Optional[FloatBetween0And1]
      recovery_structure: Literal["net", "base_stop", "fixed", "BY", "BY+1", "BY-1"]
      base_stop_amount: Optional[PositiveFloat]
      admin_fee: Optional[FloatBetween0And1]
      contribution_deduction: Optional[str]  # logic or reference to another model
      yearly_growth_cap: Optional[FloatBetween0And1]
  ```

- **Ensure your existing Recovery configuration interacts with expense pools correctly.**

- **Closing Costs:**<br>
  In the deal module, create a more flexible structure that can accept a dollar amount, as a percentage of purchase price, total debt, or a specific loan.

  - This may involve normalizing each type within a single model so cash flow calculations can work off a single interface.

--------------------------------------------------------------------------------

## 3\. Refactor the Existing Codebase

**A. Create a Migration Plan**

- Since nothing in the asset module is sacred, plan for a refactor where existing classes are either extended (via subclassing) or replaced.
- Identify deprecated fields and plan for transitional periods across the modules (e.g., leave the old models in place but add conversion functions to the new ones).

**B. Refactor Code Modules Systematically**

1. **Project & Property:**

  - Update the `Property` model to include a nested `ModelSettings` and `VacancySettings`.
  - Add fields that allow for manual override of property sizes if needed.
  - Adjust validators to check new fields (for example, if Net Rentable Area is manually overridden, validate accordingly).

2. **Revenue Module:**

  - Adopt the new MiscIncome model and update references in the Revenue aggregation.
  - Update Lease: refactor the rent roll implementation to account for new fields (suite, floor, status), and hook in the new rent step and free rent schedule logic.

3. **Expense Module:**

  - Replace few operating and capital expense items with the new `OperatingExpense` and `CapitalExpense` versions.
  - Revise the expense grouping code (such as in `_group_by_program_use`) to optionally respect parent-child relationships for subaccounts.

4. **Recovery & Debt:**

  - Update the recovery logic within cash flow calculations to incorporate the extended model fields (gross-up, max growth caps, etc.).
  - Revise debt financing models to allow for more complex closing cost entries (multiple fee types and percentages).

**C. Test Integration & Data Flow:**

- Create unit tests for each new model to ensure that calculation methods (e.g., cash flow, escalation, recovery, etc.) work as expected.
- Validate that data import/export (copy/paste from an Excel template) works with the new fields.

--------------------------------------------------------------------------------

## 4\. Implementation Phases

**Phase 1: Domain Model Expansion**

- Create/modify new classes as outlined above.
- Update validations and model relationships.
- Write sufficient unit tests for these models.

**Phase 2: Integration and Refactoring of Asset Workflows**

- Integrate the new domain models into the existing asset modules (Project, Property, Revenue, Expense, Debt).
- Update methods that construct cash flows, ensuring the models propagate new data correctly.
- Implement utility methods for converting/importing spreadsheet data into the new models.

**Phase 3: UI/Data Import Enhancements**

- While primarily a backend concern, design APIs or import routines that reflect the bulk copy/paste functionality described in VAL.
- Ensure your new models can support cloning/group operations (e.g., clone rent roll entries, replicate expense items).

**Phase 4: End-to-End Testing & Documentation**

- Write end-to-end tests that simulate scenarios from the Rockport VAL tutorial (e.g., modeling an office lease with rent steps, free rent, recoveries, TI schedules).
- Update developer and user documentation to reflect the new model design and data import/export functionalities.

--------------------------------------------------------------------------------

## 5\. Pseudocode Summary Example

**Below is a simplified pseudocode outline illustrating how the new settings might be integrated into the Property model:**
