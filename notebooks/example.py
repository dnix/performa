# %%
# imports
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from performa.debt import (
    ConstructionFacility as ConstructionFinancing,
)
from performa.debt import (
    DebtTranche,
    InterestRate,
)
from performa.debt import (
    PermanentFacility as PermanentFinancing,
)
from performa.development import (
    Budget,
    BudgetItem,
    CapRate,
    Deal,
    Expense,
    ExpenseCostItem,
    ExpenseFactorItem,
    Partner,
    Program,
    Project,
    RentalRevenueItem,
    Revenue,
    UniformDrawSchedule,
    WaterfallPromote,
    WaterfallTier,
)

# pandas round to 2 decimal places
pd.set_option("display.precision", 2)
pd.set_option("display.float_format", "{:.2f}".format)
np.set_printoptions(
    precision=2,  # limit to two decimal places in printing numpy
    suppress=True,  # suppress scientific notation in printing numpy
)

# %%
# create working datasets

# PROJECT
project_start_date = "2020-01"

# BUDGET
land = BudgetItem(
    name="Land",
    subcategory="Land",
    cost_total=4_000_000.0,
    periods_until_start=0,
    active_duration=1,
    draw_schedule=UniformDrawSchedule(),
)
constr_costs = BudgetItem(
    name="Construction Costs",
    subcategory="Hard Costs",
    cost_total=12_000_000.0,
    periods_until_start=6,
    active_duration=18,
    draw_schedule={
        "kind": "manual",
        "values": [1, 2, 3, 5, 7, 9, 7, 6, 10, 11, 8, 7, 5, 2, 1, 3, 1, 1],
    },
)
demo_costs = BudgetItem(
    name="Demolition",
    subcategory="Hard Costs",
    cost_total=550_000.0,
    periods_until_start=3,
    active_duration=3,
    draw_schedule={"kind": "s-curve", "sigma": 1.0},
)
soft_costs = BudgetItem.from_reference_items(
    name="Total Soft Costs",
    subcategory="Soft Costs",
    reference_budget_items=[constr_costs, demo_costs],
    reference_kind="passthrough",
    reference_percentage=0.2,
    periods_until_start=1,
    active_duration=31,
    draw_schedule={"kind": "uniform"},
)
budget = Budget(budget_items=[land, constr_costs, demo_costs, soft_costs])

# REVENUES
apt_rental = RentalRevenueItem(
    name="Residential Apartments",
    subcategory="Lease",
    periods_until_start=30,
    program=Program(
        name="Residential Apartments",
        use="Residential",
        gross_area=1500.0,
        net_area=1000.0,
        unit_count=32,
    ),
    revenue_multiplicand="Whole Unit",
    revenue_multiplier=3_500.0,
    revenue_growth_rate=0.05,
)

revenue = Revenue(
    revenue_items=[
        apt_rental,
    ]
)

# EXPENSES
management_fee = ExpenseFactorItem(
    name="Management Fee",
    subcategory="OpEx",
    program_use="Residential",
    expense_factor=0.02,
    revenue=revenue,
)
repairs_maintenance = ExpenseCostItem(
    name="Repairs and Maintenance",
    subcategory="OpEx",
    program_use="Residential",
    initial_annual_cost=5000.0,
    expense_growth_rate=0.03,
    revenue=revenue,
)
capital_improvements = ExpenseFactorItem(
    name="Capital Improvements",
    subcategory="CapEx",
    program_use="Residential",
    expense_factor=0.03,
    revenue=revenue,
)

expenses = Expense(
    expense_items=[
        management_fee,
        repairs_maintenance,
        capital_improvements,
    ]
)


# Update the construction financing setup
construction_financing = ConstructionFinancing(
    tranches=[
        DebtTranche(
            name="Senior",
            interest_rate=InterestRate(
                rate_type="fixed",
                base_rate=0.08,  # 8% base rate
            ),
            fee_rate=0.01,      # 1% upfront fee
            ltc_threshold=0.60,
        ),
        DebtTranche(
            name="Mezzanine",
            interest_rate=InterestRate(
                rate_type="fixed",
                base_rate=0.12,  # 12% fixed rate
            ),
            fee_rate=0.02,      # 2% upfront fee
            ltc_threshold=0.70,  # Up to 70% LTC (stacked on senior)
        ),
    ]
)

# Update the permanent financing setup
permanent_financing = PermanentFinancing(
    interest_rate=InterestRate(
        rate_type="fixed",
        base_rate=0.07,  # 7% fixed rate
    ),
    fee_rate=0.01,      # 1% upfront fee
    ltv_ratio=0.75,     # 75% LTV
    amortization=30,    # 30-year amortization
)

my_project = Project(
    name="Le Jules Verne",
    project_start_date=project_start_date,
    debt_to_equity=0.70,  # Total leverage matches max LTC from construction tranches
    budget=budget,
    revenue=revenue,
    expenses=expenses,
    construction_financing=construction_financing,
    permanent_financing=permanent_financing,
    cap_rates={
        "Residential": CapRate(
            development_cap_rate=0.05,
            refinance_cap_rate=0.045,
            sale_cap_rate=0.04
        ),
    },
    stabilization_year=2,
    hold_duration=7,
)
# time the next call
my_project.unlevered_cash_flow
# %timeit my_project.unlevered_cash_flow

partners = [
    Partner(name="GP", kind="GP", share=0.1),
    Partner(name="LP1", kind="LP", share=0.45),
    Partner(name="LP2", kind="LP", share=0.45),
]
tiers = [
    WaterfallTier(tier_hurdle_rate=0.1, metric="IRR", promote_rate=0.2),
    WaterfallTier(tier_hurdle_rate=0.125, metric="IRR", promote_rate=0.35),
]
promote = WaterfallPromote(
    kind="waterfall", pref_hurdle_rate=0.08, tiers=tiers, final_promote_rate=0.5
)
deal = Deal(project=my_project, partners=partners, promote=promote)
# TODO: compare to CREmodels waterfall https://online.cremodels.com/Waterfall?id=62844f33-c33b-43c5-994a-85bb798fdfc6
# TODO: but beware assumption there is only one negative value in the cash flow!

# %%
# plot a gantt chart of the project timelines (development, stabilization, hold)
phases = {
    "Hold": (my_project.hold_timeline.min(), my_project.hold_timeline.max()),
    "Stabilization": (
        my_project.stabilization_timeline.min(),
        my_project.stabilization_timeline.max(),
    ),
    "Development": (
        my_project.development_timeline.min(),
        my_project.development_timeline.max(),
    ),
}


# Convert start and end months to numerical values
def month_to_number(month):
    return (month - my_project.project_timeline.min()).n + 1


# Create list of tuples for plotting
time_blocks = []
colors = ["tab:blue", "tab:orange", "tab:green"]
for i, (phase, (start, end)) in enumerate(phases.items()):
    start_num = month_to_number(start)
    end_num = month_to_number(end)
    time_blocks.append((phase, [(start_num, end_num - start_num, colors[i])]))

# Plotting
fig, ax = plt.subplots(figsize=(10, 2))
for i, (phase, periods) in enumerate(time_blocks):
    for start, duration, color in periods:
        ax.broken_barh(
            [(start, duration)], (i - 0.3, 0.8), facecolors=(color), edgecolor="none"
        )  # Removed edgecolor
ax.set_yticks(range(len(time_blocks)))
ax.set_yticklabels([phase for phase, _ in time_blocks])
ax.set_xlabel("Months since Start of 2024")
ax.set_title("Project Gantt Chart")
plt.show()


# PLOT COSTS
my_project.construction_before_financing_cf.plot(
    kind="bar", stacked=True, title="Development Uses Cash Flow"
)

# PLOT CUMULATIVE COSTS
my_project.construction_before_financing_cf.cumsum().plot(
    kind="bar", stacked=True, title="Development Cumulative Uses Cash Flow"
)


# PLOT CONSTRUCTION FINANCING
# Get all draw columns (Equity + all debt tranches)
draw_columns = (
    ["Equity Draw"]
    + [f"{tranche.name} Draw" for tranche in construction_financing.tranches]
    + ["Interest Reserve"]
)

# Define colors dynamically
default_colors = {"Equity Draw": "lightblue", "Interest Reserve": "red"}
tranche_colors = {
    f"{tranche.name} Draw": f"C{i}"
    for i, tranche in enumerate(construction_financing.tranches)
}
colors = {**default_colors, **tranche_colors}

# Plot stacked bar chart
ax = my_project.construction_financing_cf[draw_columns][0:32].plot(
    kind="bar",
    stacked=True,
    title="Development Sources Cash Flow",
    color=[colors[col] for col in draw_columns],
)
plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
plt.tight_layout()
plt.show()

# Plot pie chart
ax = (
    my_project.construction_financing_cf[draw_columns][0:32]
    .sum()
    .plot(
        kind="pie",
        title="Development Sources",
        colors=[colors[col] for col in draw_columns],
    )
)
plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
plt.tight_layout()
plt.show()

# Plot interest by tranche
interest_columns = [
    f"{tranche.name} Interest" for tranche in construction_financing.tranches
]
if interest_columns:  # Only plot if there are tranches
    ax = my_project.construction_financing_cf[interest_columns][0:32].plot(
        kind="bar",
        stacked=True,
        title="Interest by Tranche",
        color=[
            tranche_colors[f"{tranche.name} Draw"]
            for tranche in construction_financing.tranches
        ],
    )
    plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
    plt.tight_layout()
    plt.show()

# After creating my_project, add these diagnostic prints:

# Print total project cost and tranche capacities
total_cost = my_project._budget_table.sum().sum()
print(f"Total Project Cost: ${total_cost:,.2f}")
print(
    f"Equity Required ({(1-my_project.debt_to_equity)*100:.0f}%): ${total_cost * (1-my_project.debt_to_equity):,.2f}"
)

print("\nDebt Capacity:")
previous_ltc = 0.0
for tranche in construction_financing.tranches:
    tranche_ltc = tranche.ltc_threshold - previous_ltc
    print(
        f"{tranche.name} ({previous_ltc*100:.0f}%-{tranche.ltc_threshold*100:.0f}%): ${total_cost * tranche_ltc:,.2f}"
    )
    previous_ltc = tranche.ltc_threshold

# Print actual draws
cf = my_project.construction_financing_cf
print("\nActual Draws:")
print("Equity: ${:,.2f}".format(cf["Equity Draw"].sum()))
for tranche in construction_financing.tranches:
    print(f"{tranche.name}: ${cf[f'{tranche.name} Draw'].sum():,.2f}")
print("Interest: ${:,.2f}".format(cf["Interest Reserve"].sum()))

# Print draw timing
print("\nDraw Timing:")
print("\nFirst non-zero draws:")
draw_columns = ["Equity Draw"] + [
    f"{t.name} Draw" for t in construction_financing.tranches
]
for col in draw_columns:
    non_zero_draws = cf[cf[col] > 0]
    if len(non_zero_draws) > 0:
        first_draw = non_zero_draws.index[0]
        print(f"{col}: {first_draw}")
    else:
        print(f"{col}: No draws")

# Print largest draws
print("\nLargest draws:")
for col in draw_columns:
    max_draw = cf[col].max()
    if max_draw > 0:
        max_draw_date = cf[cf[col] == max_draw].index[0]
        print(f"{col}: ${max_draw:,.2f} on {max_draw_date}")
    else:
        print(f"{col}: No draws")

# Print cumulative draws at key points
print("\nCumulative draws at 25%, 50%, 75% of development:")
dev_timeline = my_project.development_timeline
quarter_points = [dev_timeline[int(len(dev_timeline) * x)] for x in [0.25, 0.5, 0.75]]

for date in quarter_points:
    cumulative_costs = cf.loc[:date, "Total Costs Before Financing"].sum()
    cumulative_equity = cf.loc[:date, "Equity Draw"].sum()

    print(f"\nAt {date}:")
    print(f"Cumulative Costs: ${cumulative_costs:,.2f}")
    print(f"Cumulative Equity: ${cumulative_equity:,.2f}")

    # Track cumulative draws and percentages for each tranche
    tranche_draws = {}
    total_funding = cumulative_equity
    total_funding_with_interest = cumulative_equity

    for tranche in construction_financing.tranches:
        tranche_draw = cf.loc[:date, f"{tranche.name} Draw"].sum()
        tranche_interest = cf.loc[:date, f"{tranche.name} Interest"].sum()
        tranche_draws[tranche.name] = {
            "draw": tranche_draw,
            "interest": tranche_interest,
        }
        total_funding += tranche_draw
        total_funding_with_interest += tranche_draw + tranche_interest
        print(f"Cumulative {tranche.name}: ${tranche_draw:,.2f}")
        print(f"Cumulative {tranche.name} Interest: ${tranche_interest:,.2f}")

    # Calculate percentages excluding interest
    if total_funding > 0:
        print("\nPercentages (excluding interest):")
        print(f"Equity %: {(cumulative_equity/total_funding)*100:.1f}%")
        for tranche_name, amounts in tranche_draws.items():
            print(f"{tranche_name} %: {(amounts['draw']/total_funding)*100:.1f}%")

    # Calculate percentages including interest
    if total_funding_with_interest > 0:
        print("\nPercentages (including interest):")
        print(f"Equity %: {(cumulative_equity/total_funding_with_interest)*100:.1f}%")
        for tranche_name, amounts in tranche_draws.items():
            total_with_interest = amounts["draw"] + amounts["interest"]
            print(
                f"{tranche_name} %: {(total_with_interest/total_funding_with_interest)*100:.1f}%"
            )


# # my_project._revenue_table[0:32].plot(kind="bar", stacked=True, title="Revenue")

# # # my_project.unlevered_cash_flow.resample("Y").sum().T
# my_project.unlevered_cash_flow.resample("Y").sum().plot(
#     kind="bar", stacked=True, title="Unlevered Annual Cash Flow"
# )

# # running xirr on unlevered cash flow
# foo = my_project.unlevered_cash_flow
# foo.set_index(foo.index.to_timestamp(), inplace=True)
# f"IRR: {xirr(foo['Unlevered Cash Flow'])*100:.2f}%"

# # my_project.levered_cash_flow.resample("Y").sum().T
# my_project.levered_cash_flow.resample("Y").sum().plot(
#     kind="bar", stacked=True, title="Levered Annual Cash Flow", color="purple"
# )

# # running xirr on levered cash flow
# bar = my_project.levered_cash_flow
# bar.set_index(bar.index.to_timestamp(), inplace=True)
# f"IRR: {xirr(bar['Levered Cash Flow'])*100:.2f}%"

# # my_project.dscr.plot(kind="bar", title="Debt Service Coverage Ratio")

# # my_project.dscr
# # my_project.dscr.loc[my_project.stabilization_date:my_project.stabilization_date+11]


# # %%
# # using pyobsplot
# op = Obsplot()
# # data = my_project.construction_before_financing_cf.loc[:, ("Budget", slice(None), slice(None), slice(None))].groupby(level=2, axis=1).sum()

# # # long format data!
# # data = my_project.budget.budget_df
# # data.index.rename("Date", inplace=True)
# # data.set_index(data.index.to_timestamp(), inplace=True)
# # # rename column 0 to Cost
# # data.rename(columns={0: "Cost"}, inplace=True)
# # # op(Plot.auto(my_project._budget_table, {"x": "Date"}))
# # Plot.plot({
# #     "color": {"legend": True},
# #     "marks": [
# #         # bar chart of cumulative costs
# #         Plot.barY(data, {"x": "Date", "y": "Cost", "fill": "Subcategory"}),
# #         Plot.ruleY([0]),
# #     ]
# # })

# # my_project.construction_before_financing_cf.stack(level=1).reset_index(1).rename(columns={''})


# # a function to take a multi-index dataframe and return a long format dataframe
# def reshape_dataframe(df):
#     """Reshape a multi-index dataframe to long format for D3js/Plot"""
#     # FIXME: add param for column names/mapping
#     # Stack the inner-most level of the column index (level=-1 will stack the last level)
#     df_long = df.stack(level=[0, 1, 2])
#     # Reset the index to turn them into columns
#     df_long = df_long.reset_index()
#     # Rename columns to the desired names
#     # TODO (in case of revenue, there is a Use column to be added)
#     df_long.columns = ["Date", "Category", "Subcategory", "Name", "Amount"]
#     # Set the Date column as the index and convert to datetime
#     df_long.set_index(df_long["Date"], inplace=True)
#     df_long.drop(columns=["Date"], inplace=True)
#     df_long.set_index(df_long.index.to_timestamp(), inplace=True)
#     # Return the reshaped dataframe
#     return df_long


# # Reshape the construction before financing cash flow
# construction_before_financing_cf_long = reshape_dataframe(
#     my_project.construction_before_financing_cf
# )
# construction_before_financing_cf_long_cumsum = reshape_dataframe(
#     my_project.construction_before_financing_cf.cumsum()
# )
# construction_before_financing_cf_long_annual = reshape_dataframe(
#     my_project.construction_before_financing_cf.resample("Y").sum()
# )

# # long format data!
# data = construction_before_financing_cf_long_cumsum
# op = Obsplot(
#     debug=True,
#     format="widget",
# )
# # set index to Date column and remove the column
# # data.set_index(data['Date'], inplace=True)
# # data.drop(columns=['Date'], inplace=True)
# # data.set_index(data.index.to_timestamp(), inplace=True)
# op(
#     {
#         # "grid": True,
#         # "margin": 10,
#         "x": {
#             # "insetLeft": 12
#         },
#         "y": {
#             "transform": js("(d) => d / 1000000"),
#         },
#         "color": {"legend": True},
#         "marks": [
#             # bar chart of cumulative costs
#             Plot.axisX({"ticks": "3 months"}),
#             Plot.axisY(
#                 {
#                     "label": "Amount ($m)",
#                     # "dx": 12,
#                 }
#             ),
#             Plot.barY(
#                 data,
#                 {
#                     "x": "Date",
#                     "y": "Amount",
#                     "fill": "Subcategory",
#                     "tip": True,
#                 },
#             ),
#             Plot.ruleY([0]),  # add a baseline at 0
#         ],
#     }
# )

# # PLOT INTEREST BY TRANCHE
