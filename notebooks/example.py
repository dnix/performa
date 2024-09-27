# %%
# imports
import matplotlib.pyplot as plt
from pyobsplot import Obsplot, Plot, js
from pyxirr import xirr

from performa.development import (
    Budget,
    BudgetItem,
    ConstructionFinancing,
    Deal,
    Expense,
    ExpenseCostItem,
    ExpenseFactorItem,
    Partner,
    PermanentFinancing,
    Program,
    Project,
    RentalRevenueItem,
    Revenue,
    WaterfallPromote,
    WaterfallTier,
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
    draw_schedule={"kind": "uniform"},
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


my_project = Project(
    name="Le Jules Verne",
    project_start_date=project_start_date,
    debt_to_equity=0.6,
    budget=budget,
    revenue=revenue,
    expenses=expenses,
    construction_financing=ConstructionFinancing(
        interest_rate=0.095,
        fee_rate=0.00,
    ),
    permanent_financing=PermanentFinancing(
        interest_rate=0.07,
        fee_rate=0.01,
        ltv_ratio=0.5,
        amortization=30,
    ),
    # cap_rates=[
    #     CapRates(
    #         name="Residential Cap Rates",
    #         program_use="Residential",
    #         development_cap_rate=0.05,
    #         refinance_cap_rate=0.05,
    #         sale_cap_rate=0.05,
    #     ),
    # ],
    cap_rates=0.05,
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
my_project.construction_financing_cf[["Equity Draw", "Debt Draw", "Interest Reserve"]][
    0:32
].plot(kind="bar", stacked=True, title="Development Sources Cash Flow")
plt.show()  # Add this line to display the plot

# CONSTRUCTION SOURCES PIE CHART
my_project.construction_financing_cf[["Equity Draw", "Debt Draw", "Interest Reserve"]][
    0:32
].sum().plot(kind="pie", title="Development Sources")
plt.show()  # Add this line to display the plot


# my_project._revenue_table[0:32].plot(kind="bar", stacked=True, title="Revenue")

# # my_project.unlevered_cash_flow.resample("Y").sum().T
my_project.unlevered_cash_flow.resample("Y").sum().plot(
    kind="bar", stacked=True, title="Unlevered Annual Cash Flow"
)

# running xirr on unlevered cash flow
foo = my_project.unlevered_cash_flow
foo.set_index(foo.index.to_timestamp(), inplace=True)
f"IRR: {xirr(foo['Unlevered Cash Flow'])*100:.2f}%"

# my_project.levered_cash_flow.resample("Y").sum().T
my_project.levered_cash_flow.resample("Y").sum().plot(
    kind="bar", stacked=True, title="Levered Annual Cash Flow", color="purple"
)

# running xirr on levered cash flow
bar = my_project.levered_cash_flow
bar.set_index(bar.index.to_timestamp(), inplace=True)
f"IRR: {xirr(bar['Levered Cash Flow'])*100:.2f}%"

# my_project.dscr.plot(kind="bar", title="Debt Service Coverage Ratio")

# my_project.dscr
# my_project.dscr.loc[my_project.stabilization_date:my_project.stabilization_date+11]


# %%
# using pyobsplot
op = Obsplot()
# data = my_project.construction_before_financing_cf.loc[:, ("Budget", slice(None), slice(None), slice(None))].groupby(level=2, axis=1).sum()

# # long format data!
# data = my_project.budget.budget_df
# data.index.rename("Date", inplace=True)
# data.set_index(data.index.to_timestamp(), inplace=True)
# # rename column 0 to Cost
# data.rename(columns={0: "Cost"}, inplace=True)
# # op(Plot.auto(my_project._budget_table, {"x": "Date"}))
# Plot.plot({
#     "color": {"legend": True},
#     "marks": [
#         # bar chart of cumulative costs
#         Plot.barY(data, {"x": "Date", "y": "Cost", "fill": "Subcategory"}),
#         Plot.ruleY([0]),
#     ]
# })

# my_project.construction_before_financing_cf.stack(level=1).reset_index(1).rename(columns={''})


# a function to take a multi-index dataframe and return a long format dataframe
def reshape_dataframe(df):
    """Reshape a multi-index dataframe to long format for D3js/Plot"""
    # FIXME: add param for column names/mapping
    # Stack the inner-most level of the column index (level=-1 will stack the last level)
    df_long = df.stack(level=[0, 1, 2])
    # Reset the index to turn them into columns
    df_long = df_long.reset_index()
    # Rename columns to the desired names
    # TODO (in case of revenue, there is a Use column to be added)
    df_long.columns = ["Date", "Category", "Subcategory", "Name", "Amount"]
    # Set the Date column as the index and convert to datetime
    df_long.set_index(df_long["Date"], inplace=True)
    df_long.drop(columns=["Date"], inplace=True)
    df_long.set_index(df_long.index.to_timestamp(), inplace=True)
    # Return the reshaped dataframe
    return df_long


# Reshape the construction before financing cash flow
construction_before_financing_cf_long = reshape_dataframe(
    my_project.construction_before_financing_cf
)
construction_before_financing_cf_long_cumsum = reshape_dataframe(
    my_project.construction_before_financing_cf.cumsum()
)
construction_before_financing_cf_long_annual = reshape_dataframe(
    my_project.construction_before_financing_cf.resample("Y").sum()
)

# long format data!
data = construction_before_financing_cf_long_cumsum
op = Obsplot(
    debug=True,
    format="widget",
)
# set index to Date column and remove the column
# data.set_index(data['Date'], inplace=True)
# data.drop(columns=['Date'], inplace=True)
# data.set_index(data.index.to_timestamp(), inplace=True)
op(
    {
        # "grid": True,
        # "margin": 10,
        "x": {
            # "insetLeft": 12
        },
        "y": {
            "transform": js("(d) => d / 1000000"),
        },
        "color": {"legend": True},
        "marks": [
            # bar chart of cumulative costs
            Plot.axisX({"ticks": "3 months"}),
            Plot.axisY(
                {
                    "label": "Amount ($m)",
                    # "dx": 12,
                }
            ),
            Plot.barY(
                data,
                {
                    "x": "Date",
                    "y": "Amount",
                    "fill": "Subcategory",
                    "tip": True,
                },
            ),
            Plot.ruleY([0]),  # add a baseline at 0
        ],
    }
)
