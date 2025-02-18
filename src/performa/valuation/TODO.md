# Pending work for Valuation

Roll valuation for both asset and development modules into a single valuation module(?)

TODO: Implement multiple valuation methods:

1. Direct Capitalization
    - Add cap rate input
    - Calculate value from 1st-year NOI with occupancy adjustments
2. Property Resale
    - Support multiple calculation methods (cap rate, direct price, $/SF, GIM)
    - Add occupancy gross-up options
    - Add TI/LC deduction toggles
    - Configure hold period
    - Support misc sale adjustments
3. Present Value
    - Add discount rate input
    - Configure discount interval
    - Set PV/IRR date
    - Support separate rates for cash flow vs resale
4. Valuation Intervals
    - Add increment steps for sensitivity analysis
    - Support ranges for cap rates and sale prices
