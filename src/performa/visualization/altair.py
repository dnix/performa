# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Performa Altair Visualization Suite

Professional real estate financial modeling charts using Altair.
"""

from __future__ import annotations

from typing import Any, Dict, List

import altair as alt
import pandas as pd

# Enable Altair to render properly
# alt.data_transformers.enable('json')

# =============================================================================
# Color Schemes and Styling
# =============================================================================

# Professional real estate color palette
RE_COLORS = {
    "primary": "#2E5984",  # Professional blue
    "secondary": "#8B4A6B",  # Muted purple
    "accent": "#D4A574",  # Warm gold
    "success": "#28A745",  # Green for positive
    "warning": "#FFC107",  # Yellow for caution
    "danger": "#DC3545",  # Red for negative
    "neutral": "#6C757D",  # Gray for neutral
    "light_gray": "#F8F9FA",  # Light background
    "dark_gray": "#343A40",  # Dark text
}

# Extended palette for multi-category charts
EXTENDED_PALETTE = [
    RE_COLORS["primary"],
    RE_COLORS["secondary"],
    RE_COLORS["accent"],
    RE_COLORS["success"],
    RE_COLORS["warning"],
    RE_COLORS["neutral"],
    "#FF6B6B",  # Light red
    "#4ECDC4",  # Teal
    "#45B7D1",  # Light blue
    "#96CEB4",  # Mint green
    "#FECA57",  # Golden yellow
    "#FF9FF3",  # Pink
]

# IRR performance color mapping
IRR_THRESHOLDS = [
    {"min": 0.20, "color": "#28A745", "label": "Excellent (>20%)"},
    {"min": 0.15, "color": "#FFC107", "label": "Strong (15-20%)"},
    {"min": 0.10, "color": "#FD7E14", "label": "Modest (10-15%)"},
    {"min": 0.00, "color": "#DC3545", "label": "Weak (<10%)"},
]


def get_irr_color(irr_value: float) -> str:
    """Get color based on IRR performance thresholds."""
    for threshold in IRR_THRESHOLDS:
        if irr_value >= threshold["min"]:
            return threshold["color"]
    return RE_COLORS["danger"]


# Base chart configuration for consistent styling
def get_base_chart() -> alt.Chart:
    """Get base chart with consistent styling."""
    return (
        alt.Chart()
        .resolve_scale(color="independent")
        .configure_axis(
            labelFontSize=11,
            titleFontSize=12,
            labelColor=RE_COLORS["dark_gray"],
            titleColor=RE_COLORS["dark_gray"],
            gridColor=RE_COLORS["light_gray"],
            domainColor=RE_COLORS["neutral"],
        )
        .configure_title(
            fontSize=14, anchor="start", color=RE_COLORS["dark_gray"], fontWeight="bold"
        )
        .configure_legend(
            labelFontSize=11,
            titleFontSize=12,
            labelColor=RE_COLORS["dark_gray"],
            titleColor=RE_COLORS["dark_gray"],
        )
        .configure_view(strokeWidth=0)
    )


# =============================================================================
# Chart Creation Functions
# =============================================================================


def create_sources_uses_chart(
    sources_data: Dict[str, float],
    uses_data: Dict[str, float],
    title: str = "Sources & Uses of Funds",
    width: int = 600,
    height: int = 400,
) -> alt.Chart:
    """
    Create side-by-side Sources & Uses bar chart.

    Industry-standard visualization showing project funding (sources)
    vs project costs (uses) in paired bar format.

    Args:
        sources_data: Dict of funding sources {"Equity": 5000000, "Debt": 10000000}
        uses_data: Dict of uses {"Land": 3000000, "Construction": 12000000}
        title: Chart title
        width: Chart width in pixels
        height: Chart height in pixels

    Returns:
        Altair Chart configured for display

    Example:
        ```python
        sources = {"Equity": 5_000_000, "Construction Loan": 10_000_000}
        uses = {"Land": 3_000_000, "Hard Costs": 12_000_000}
        chart = create_sources_uses_chart(sources, uses)
        chart.show()
        ```
    """
    # Prepare data for Altair
    sources_df = pd.DataFrame([
        {"category": category, "amount": amount, "type": "Sources"}
        for category, amount in sources_data.items()
    ])

    uses_df = pd.DataFrame([
        {"category": category, "amount": amount, "type": "Uses"}
        for category, amount in uses_data.items()
    ])

    # Combine data
    data = pd.concat([sources_df, uses_df], ignore_index=True)

    # Create chart
    chart = (
        alt.Chart(data)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X("category:N", title=None, axis=alt.Axis(labelAngle=-45)),
            y=alt.Y("amount:Q", title="Amount ($)", axis=alt.Axis(format="$.2s")),
            color=alt.Color(
                "type:N",
                scale=alt.Scale(
                    domain=["Sources", "Uses"],
                    range=[RE_COLORS["success"], RE_COLORS["primary"]],
                ),
                legend=alt.Legend(title=None, orient="top"),
            ),
            column=alt.Column(
                "type:N",
                title=None,
                header=alt.Header(labelFontSize=13, labelFontWeight="bold"),
            ),
            tooltip=[
                alt.Tooltip("category:N", title="Category"),
                alt.Tooltip("amount:Q", title="Amount", format="$,.0f"),
                alt.Tooltip("type:N", title="Type"),
            ],
        )
        .resolve_scale(x="independent")
        .properties(
            width=width // 2 - 30,
            height=height,
            title=alt.TitleParams(text=title, fontSize=14, fontWeight="bold"),
        )
    )

    return chart


def create_cost_breakdown_donut(
    cost_data: Dict[str, float],
    title: str = "Total Project Cost Breakdown",
    width: int = 400,
    height: int = 400,
) -> alt.Chart:
    """
    Create donut chart showing cost component breakdown.

    Args:
        cost_data: Dict of cost categories and amounts
        title: Chart title
        width: Chart width in pixels
        height: Chart height in pixels

    Returns:
        Altair donut chart

    Example:
        ```python
        costs = {
            "Land": 3_000_000,
            "Hard Costs": 12_000_000,
            "Soft Costs": 1_500_000,
            "Developer Fee": 750_000
        }
        chart = create_cost_breakdown_donut(costs)
        ```
    """
    # Prepare data
    data = pd.DataFrame([
        {"category": category, "amount": amount}
        for category, amount in cost_data.items()
    ])

    total_cost = data["amount"].sum()
    data["percentage"] = data["amount"] / total_cost

    # Create base chart
    base = alt.Chart(data)

    # Create donut chart using arc marks
    donut = (
        base.mark_arc(innerRadius=80, outerRadius=140, stroke="white", strokeWidth=2)
        .encode(
            theta=alt.Theta("amount:Q"),
            color=alt.Color(
                "category:N",
                scale=alt.Scale(range=EXTENDED_PALETTE),
                legend=alt.Legend(
                    orient="right", titleFontSize=12, labelFontSize=11, symbolSize=100
                ),
            ),
            tooltip=[
                alt.Tooltip("category:N", title="Category"),
                alt.Tooltip("amount:Q", title="Amount", format="$,.0f"),
                alt.Tooltip("percentage:Q", title="Percentage", format=".1%"),
            ],
        )
        .properties(
            width=width,
            height=height,
            title=alt.TitleParams(text=title, fontSize=14, fontWeight="bold"),
        )
    )

    # Add center text with total
    if total_cost >= 1_000_000:
        formatted_total = f"${total_cost / 1_000_000:.1f}M"
    elif total_cost >= 1_000:
        formatted_total = f"${total_cost / 1_000:.1f}K"
    else:
        formatted_total = f"${total_cost:,.0f}"

    center_text = (
        alt.Chart(
            pd.DataFrame([
                {"x": width // 2, "y": height // 2, "text": f"Total\n{formatted_total}"}
            ])
        )
        .mark_text(
            align="center",
            baseline="middle",
            fontSize=16,
            fontWeight="bold",
            color=RE_COLORS["dark_gray"],
        )
        .encode(
            x=alt.X("x:Q", scale=alt.Scale(domain=[0, width]), axis=None),
            y=alt.Y("y:Q", scale=alt.Scale(domain=[0, height]), axis=None),
            text="text:N",
        )
        .resolve_scale(x="independent", y="independent")
    )

    # Return just the donut to avoid LayerChart issues completely
    return donut


def create_development_timeline(
    phases: List[Dict[str, Any]],
    title: str = "Development Timeline",
    width: int = 600,
    height: int = 400,
) -> alt.Chart:
    """
    Create Gantt-style development timeline chart.

    Args:
        phases: List of phase dicts with keys: 'name', 'start', 'end', 'color' (optional)
        title: Chart title
        width: Chart width in pixels
        height: Chart height in pixels

    Returns:
        Altair Gantt chart

    Example:
        ```python
        phases = [
            {
                "name": "Construction",
                "start": "2024-01-01",
                "end": "2025-06-30",
                "color": "#2E5984"
            },
            {
                "name": "Lease-Up",
                "start": "2025-04-01",
                "end": "2026-12-31",
                "color": "#8B4A6B"
            }
        ]
        chart = create_development_timeline(phases)
        ```
    """
    # Prepare data with calculated duration
    data = []
    for i, phase in enumerate(phases):
        start_date = pd.to_datetime(phase["start"])
        end_date = pd.to_datetime(phase["end"])
        duration_days = (end_date - start_date).days

        data.append({
            "name": phase["name"],
            "start": start_date,
            "end": end_date,
            "duration_days": duration_days,
            "color": phase.get("color", EXTENDED_PALETTE[i % len(EXTENDED_PALETTE)]),
            "y_position": i,
        })

    df = pd.DataFrame(data)

    # Create base chart
    base = alt.Chart(df)

    # Create Gantt bars
    gantt = (
        base.mark_bar(height=30, cornerRadius=5)
        .encode(
            x=alt.X("start:T", title="Timeline", axis=alt.Axis(format="%Y-%m")),
            x2=alt.X2("end:T"),
            y=alt.Y(
                "name:N",
                title=None,
                sort=alt.EncodingSortField(field="y_position", order="descending"),
                axis=alt.Axis(labelFontSize=12),
            ),
            color=alt.Color(
                "name:N",
                scale=alt.Scale(range=[p["color"] for p in phases]),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("name:N", title="Phase"),
                alt.Tooltip("start:T", title="Start Date", format="%Y-%m-%d"),
                alt.Tooltip("end:T", title="End Date", format="%Y-%m-%d"),
                alt.Tooltip("duration_days:Q", title="Duration (days)"),
            ],
        )
        .properties(
            width=width,
            height=height,
            title=alt.TitleParams(text=title, fontSize=14, fontWeight="bold"),
        )
    )

    # Add text labels on bars
    text = (
        base.mark_text(
            align="center",
            baseline="middle",
            fontSize=11,
            fontWeight="bold",
            color="white",
        )
        .encode(
            x=alt.X("start:T"),
            x2=alt.X2("end:T"),
            y=alt.Y(
                "name:N",
                sort=alt.EncodingSortField(field="y_position", order="descending"),
            ),
            text=alt.Text("duration_days:Q", format=".0f"),
        )
        .transform_calculate(text_label='datum.duration_days + " days"')
    )

    return gantt + text


def create_waterfall_chart(
    categories: List[str],
    values: List[float],
    title: str = "Cash Flow Waterfall",
    width: int = 600,
    height: int = 500,
) -> alt.Chart:
    """
    Create waterfall chart for step-by-step cash flow analysis.

    Perfect for partnership distributions, development costs, or
    any cumulative financial calculation.

    Args:
        categories: List of category names
        values: List of values (positive or negative)
        title: Chart title
        width: Chart width in pixels
        height: Chart height in pixels

    Returns:
        Altair waterfall chart

    Example:
        ```python
        categories = ["Total Proceeds", "Debt Payoff", "Return of Capital", "Preferred Return", "GP Promote"]
        values = [25_000_000, -15_000_000, -5_000_000, -3_000_000, -2_000_000]
        chart = create_waterfall_chart(categories, values, "Partnership Distribution Waterfall")
        ```
    """
    # Calculate cumulative positions for waterfall effect
    data = []
    running_total = 0

    for i, (category, value) in enumerate(zip(categories, values)):
        # For positive values, bar starts at running total
        # For negative values, bar starts at running total + value
        if value >= 0:
            start_position = running_total
            end_position = running_total + value
        else:
            start_position = running_total + value
            end_position = running_total

        data.append({
            "category": category,
            "value": value,
            "start": start_position,
            "end": end_position,
            "abs_value": abs(value),
            "type": "positive" if value >= 0 else "negative",
            "order": i,
        })

        running_total += value

    df = pd.DataFrame(data)

    # Create base chart
    base = alt.Chart(df)

    # Create bars with custom positioning
    bars = (
        base.mark_bar(
            cornerRadiusTopLeft=3, cornerRadiusTopRight=3, stroke="white", strokeWidth=1
        )
        .encode(
            x=alt.X(
                "category:N",
                title=None,
                sort=alt.SortField("order"),
                axis=alt.Axis(labelAngle=-45, labelFontSize=10),
            ),
            y=alt.Y("start:Q", title="Amount ($)", axis=alt.Axis(format="$.2s")),
            y2=alt.Y2("end:Q"),
            color=alt.Color(
                "type:N",
                scale=alt.Scale(
                    domain=["positive", "negative"],
                    range=[RE_COLORS["success"], RE_COLORS["danger"]],
                ),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("category:N", title="Category"),
                alt.Tooltip("value:Q", title="Value", format="$,.0f"),
                alt.Tooltip("end:Q", title="Running Total", format="$,.0f"),
            ],
        )
        .properties(
            width=width,
            height=height,
            title=alt.TitleParams(text=title, fontSize=14, fontWeight="bold"),
        )
    )

    # Add value labels on bars
    labels = base.mark_text(
        align="center",
        baseline="bottom",
        dy=-5,
        fontSize=10,
        fontWeight="bold",
        color=RE_COLORS["dark_gray"],
    ).encode(
        x=alt.X("category:N", sort=alt.SortField("order")),
        y=alt.Y("end:Q"),
        text=alt.Text("value:Q", format="$.1s"),
    )

    # Add connecting lines between bars
    # Create line data
    line_data = []
    for i in range(len(data) - 1):
        line_data.append({
            "x": i + 0.4,  # End of current bar
            "y": data[i]["end"],
            "x2": i + 1 - 0.4,  # Start of next bar
            "y2": data[i]["end"],
        })

    if line_data:
        line_df = pd.DataFrame(line_data)

        lines = (
            alt.Chart(line_df)
            .mark_rule(strokeDash=[3, 3], stroke=RE_COLORS["neutral"], strokeWidth=1)
            .encode(
                x=alt.X("x:Q", scale=alt.Scale(domain=[-0.5, len(categories) - 0.5])),
                y=alt.Y("y:Q"),
                x2=alt.X2("x2:Q"),
                y2=alt.Y2("y2:Q"),
            )
            .resolve_scale(x="independent")
        )

        return bars + labels + lines

    return bars + labels


def create_partnership_distribution_comparison(
    capital_contributions: Dict[str, float],
    profit_distributions: Dict[str, float],
    title: str = "Capital vs Profit Distribution",
    width: int = 700,
    height: int = 400,
) -> alt.Chart:
    """
    Create side-by-side pie charts comparing capital vs profit distribution.

    Visually demonstrates the "promote" concept - how profit distribution
    differs from initial capital contribution percentages.

    Args:
        capital_contributions: Dict of partner contributions {"GP": 1000000, "LP": 9000000}
        profit_distributions: Dict of partner profits {"GP": 3500000, "LP": 6500000}
        title: Chart title
        width: Chart width in pixels
        height: Chart height in pixels

    Returns:
        Altair subplot with two pie charts
    """
    # Prepare capital contributions data
    cap_data = pd.DataFrame([
        {"partner": partner, "amount": amount, "type": "Capital Contributions"}
        for partner, amount in capital_contributions.items()
    ])
    cap_total = cap_data["amount"].sum()
    cap_data["percentage"] = cap_data["amount"] / cap_total

    # Prepare profit distributions data
    prof_data = pd.DataFrame([
        {"partner": partner, "amount": amount, "type": "Profit Distribution"}
        for partner, amount in profit_distributions.items()
    ])
    prof_total = prof_data["amount"].sum()
    prof_data["percentage"] = prof_data["amount"] / prof_total

    # Combine data
    data = pd.concat([cap_data, prof_data], ignore_index=True)

    # Create base chart
    base = alt.Chart(data)

    # Create pie charts side by side using faceting
    charts = (
        base.mark_arc(innerRadius=20, outerRadius=120, stroke="white", strokeWidth=2)
        .encode(
            theta=alt.Theta("amount:Q"),
            color=alt.Color(
                "partner:N",
                scale=alt.Scale(
                    domain=list(capital_contributions.keys()),
                    range=[RE_COLORS["danger"], RE_COLORS["primary"]],
                ),
                legend=alt.Legend(
                    orient="bottom", titleFontSize=12, labelFontSize=11, symbolSize=100
                ),
            ),
            column=alt.Column(
                "type:N",
                title=None,
                header=alt.Header(labelFontSize=13, labelFontWeight="bold"),
            ),
            tooltip=[
                alt.Tooltip("partner:N", title="Partner"),
                alt.Tooltip("amount:Q", title="Amount", format="$,.0f"),
                alt.Tooltip("percentage:Q", title="Percentage", format=".1%"),
                alt.Tooltip("type:N", title="Type"),
            ],
        )
        .resolve_scale(color="shared")
        .properties(
            width=width // 2 - 50,
            height=height,
            title=alt.TitleParams(text=title, fontSize=14, fontWeight="bold"),
        )
    )

    return charts


def create_sensitivity_heatmap(
    x_variable: str,
    y_variable: str,
    x_values: List[float],
    y_values: List[float],
    irr_matrix: List[List[float]],
    title: str = "Two-Way Sensitivity Analysis",
    width: int = 500,
    height: int = 400,
) -> alt.Chart:
    """
    Create sensitivity heatmap showing IRR sensitivity to two variables.

    Note: This function only creates the visualization. The sensitivity
    computation should be done separately with manual trigger to avoid
    performance issues in reactive notebooks.

    Args:
        x_variable: Name of x-axis variable (e.g., "Exit Cap Rate")
        y_variable: Name of y-axis variable (e.g., "Construction Cost/Unit")
        x_values: List of x-axis values
        y_values: List of y-axis values
        irr_matrix: 2D matrix of IRR values [y_len][x_len]
        title: Chart title
        width: Chart width in pixels
        height: Chart height in pixels

    Returns:
        Altair heatmap

    Example:
        ```python
        # Pre-computed sensitivity matrix (expensive computation done separately)
        x_vals = [0.050, 0.055, 0.060, 0.065, 0.070]  # Cap rates
        y_vals = [140_000, 160_000, 180_000, 200_000]  # Cost per unit
        irr_matrix = [
            [0.28, 0.25, 0.22, 0.19, 0.16],  # $140K/unit
            [0.25, 0.22, 0.19, 0.16, 0.13],  # $160K/unit
            [0.22, 0.19, 0.16, 0.13, 0.10],  # $180K/unit
            [0.19, 0.16, 0.13, 0.10, 0.07],  # $200K/unit
        ]

        chart = create_sensitivity_heatmap(
            "Exit Cap Rate", "Construction Cost/Unit",
            x_vals, y_vals, irr_matrix
        )
        ```
    """
    # Prepare data in long format for Altair
    data = []
    for i, y_val in enumerate(y_values):
        for j, x_val in enumerate(x_values):
            irr_val = irr_matrix[i][j]
            data.append({
                "x_var": x_val,
                "y_var": y_val,
                "irr": irr_val,
                "irr_text": f"{irr_val:.1%}",
                "x_var_name": x_variable,
                "y_var_name": y_variable,
            })

    df = pd.DataFrame(data)

    # Create base chart
    base = alt.Chart(df)

    # Create heatmap
    heatmap = (
        base.mark_rect(stroke="white", strokeWidth=1)
        .encode(
            x=alt.X(
                "x_var:O",
                title=x_variable,
                axis=alt.Axis(
                    format=".1%"
                    if "rate" in x_variable.lower() or "cap" in x_variable.lower()
                    else "$,.0f"
                    if "cost" in x_variable.lower() or "price" in x_variable.lower()
                    else ".2f"
                ),
            ),
            y=alt.Y(
                "y_var:O",
                title=y_variable,
                axis=alt.Axis(
                    format=".1%"
                    if "rate" in y_variable.lower() or "cap" in y_variable.lower()
                    else "$,.0f"
                    if "cost" in y_variable.lower() or "price" in y_variable.lower()
                    else ".2f"
                ),
            ),
            color=alt.Color(
                "irr:Q",
                scale=alt.Scale(
                    range=["#DC3545", "#FD7E14", "#FFC107", "#20C997", "#28A745"],
                    type="linear",
                ),
                legend=alt.Legend(title="IRR", format=".1%", gradientLength=200),
            ),
            tooltip=[
                alt.Tooltip("x_var_name:N", title="Variable"),
                alt.Tooltip(
                    "x_var:Q",
                    title="X Value",
                    format=".1%"
                    if "rate" in x_variable.lower() or "cap" in x_variable.lower()
                    else "$,.0f"
                    if "cost" in x_variable.lower() or "price" in x_variable.lower()
                    else ".2f",
                ),
                alt.Tooltip("y_var_name:N", title="Variable"),
                alt.Tooltip(
                    "y_var:Q",
                    title="Y Value",
                    format=".1%"
                    if "rate" in y_variable.lower() or "cap" in y_variable.lower()
                    else "$,.0f"
                    if "cost" in y_variable.lower() or "price" in y_variable.lower()
                    else ".2f",
                ),
                alt.Tooltip("irr:Q", title="IRR", format=".1%"),
            ],
        )
        .properties(
            width=width,
            height=height,
            title=alt.TitleParams(text=title, fontSize=14, fontWeight="bold"),
        )
    )

    # Add text labels
    text = base.mark_text(
        align="center", baseline="middle", fontSize=10, fontWeight="bold", color="white"
    ).encode(
        x=alt.X("x_var:O"),
        y=alt.Y("y_var:O"),
        text=alt.Text("irr_text:N"),
        opacity=alt.condition(alt.datum.irr > 0.15, alt.value(1.0), alt.value(0.8)),
    )

    return heatmap + text


def create_cash_flow_timeline(
    cash_flow_data: pd.DataFrame,
    title: str = "Annual Cash Flow Progression",
    width: int = 600,
    height: int = 500,
) -> alt.Chart:
    """
    Create annual cash flow timeline with cumulative overlay.

    Args:
        cash_flow_data: DataFrame with 'year' and 'cash_flow' columns
        title: Chart title
        width: Chart width in pixels
        height: Chart height in pixels

    Returns:
        Altair chart with bars and line overlay

    Example:
        ```python
        cf_data = pd.DataFrame({
            'year': [2024, 2025, 2026, 2027, 2028],
            'cash_flow': [-10_000_000, 500_000, 800_000, 1_200_000, 15_000_000]
        })
        chart = create_cash_flow_timeline(cf_data)
        ```
    """
    # Prepare data with cumulative calculation
    data = cash_flow_data.copy()
    data["cumulative"] = data["cash_flow"].cumsum()
    data["is_positive"] = data["cash_flow"] >= 0

    # Normalize cumulative for dual-axis effect (scale to match cash flow range)
    cf_range = data["cash_flow"].max() - data["cash_flow"].min()
    cum_range = data["cumulative"].max() - data["cumulative"].min()
    if cum_range > 0:
        scale_factor = cf_range / cum_range * 0.8  # Scale to 80% of cash flow range
        data["cumulative_scaled"] = data["cumulative"] * scale_factor
    else:
        data["cumulative_scaled"] = data["cumulative"]

    # Create base chart
    base = alt.Chart(data)

    # Create annual cash flow bars
    bars = base.mark_bar(
        cornerRadiusTopLeft=3,
        cornerRadiusTopRight=3,
        opacity=0.8,
        stroke="white",
        strokeWidth=1,
    ).encode(
        x=alt.X("year:O", title="Year", axis=alt.Axis(labelFontSize=11)),
        y=alt.Y(
            "cash_flow:Q",
            title="Annual Cash Flow ($)",
            axis=alt.Axis(format="$.2s", labelFontSize=11),
        ),
        color=alt.Color(
            "is_positive:N",
            scale=alt.Scale(
                domain=[True, False], range=[RE_COLORS["success"], RE_COLORS["danger"]]
            ),
            legend=None,
        ),
        tooltip=[
            alt.Tooltip("year:O", title="Year"),
            alt.Tooltip("cash_flow:Q", title="Annual Cash Flow", format="$,.0f"),
            alt.Tooltip("cumulative:Q", title="Cumulative Cash Flow", format="$,.0f"),
        ],
    )

    # Create cumulative line
    line = base.mark_line(point=True, strokeWidth=3, opacity=0.9).encode(
        x=alt.X("year:O"),
        y=alt.Y("cumulative_scaled:Q", scale=alt.Scale(zero=False)),
        color=alt.value(RE_COLORS["accent"]),
        tooltip=[
            alt.Tooltip("year:O", title="Year"),
            alt.Tooltip("cumulative:Q", title="Cumulative Cash Flow", format="$,.0f"),
        ],
    )

    # Add point markers on the line
    points = base.mark_circle(size=100, stroke="white", strokeWidth=2).encode(
        x=alt.X("year:O"),
        y=alt.Y("cumulative_scaled:Q"),
        color=alt.value(RE_COLORS["accent"]),
        tooltip=[
            alt.Tooltip("year:O", title="Year"),
            alt.Tooltip("cumulative:Q", title="Cumulative Cash Flow", format="$,.0f"),
        ],
    )

    # Add zero reference line
    zero_line = (
        alt.Chart(pd.DataFrame([{"zero": 0}]))
        .mark_rule(
            strokeDash=[3, 3], stroke=RE_COLORS["neutral"], strokeWidth=1, opacity=0.7
        )
        .encode(y=alt.Y("zero:Q"))
    )

    # Add value labels on bars
    labels = base.mark_text(
        align="center",
        baseline="bottom" if data["cash_flow"].min() >= 0 else "middle",
        dy=-5,
        fontSize=9,
        fontWeight="bold",
        color=RE_COLORS["dark_gray"],
    ).encode(
        x=alt.X("year:O"),
        y=alt.Y("cash_flow:Q", scale=alt.Scale(zero=True)),
        text=alt.Text("cash_flow:Q", format="$.1s"),
        opacity=alt.condition(alt.datum.cash_flow != 0, alt.value(1.0), alt.value(0.0)),
    )

    # Create legend manually since we have custom elements
    legend_data = pd.DataFrame([
        {
            "legend_x": width * 0.02,
            "legend_y": height * 0.95,
            "text": "Annual Cash Flow",
            "color": RE_COLORS["neutral"],
        },
        {
            "legend_x": width * 0.02,
            "legend_y": height * 0.90,
            "text": "Cumulative (scaled)",
            "color": RE_COLORS["accent"],
        },
    ])

    legend_text = (
        alt.Chart(legend_data)
        .mark_text(align="left", fontSize=11, fontWeight="normal")
        .encode(
            x=alt.X("legend_x:Q", scale=alt.Scale(domain=[0, width])),
            y=alt.Y("legend_y:Q", scale=alt.Scale(domain=[0, height])),
            text="text:N",
            color=alt.Color("color:N", scale=None),
        )
        .resolve_scale(x="independent", y="independent")
    )

    # Combine all elements
    combined = (
        (zero_line + bars + line + points + labels + legend_text)
        .resolve_scale(y="shared")
        .properties(
            width=width,
            height=height,
            title=alt.TitleParams(text=title, fontSize=14, fontWeight="bold"),
        )
    )

    return combined


# =============================================================================
# Utility Functions
# =============================================================================


def format_currency_altair(value: float) -> str:
    """Format currency values for Altair chart labels."""
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    elif abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    elif abs(value) >= 1_000:
        return f"${value / 1_000:.0f}K"
    else:
        return f"${value:.0f}"


def get_performance_color_scheme(irr: float) -> Dict[str, str]:
    """Get color scheme based on IRR performance."""
    base_color = get_irr_color(irr)

    return {
        "primary": base_color,
        "secondary": f"{base_color}80",  # Add transparency
        "text": "#FFFFFF" if irr >= 0.15 else "#000000",
        "border": base_color,
    }


# Export main functions
__all__ = [
    # Chart creation functions
    "create_sources_uses_chart",
    "create_cost_breakdown_donut",
    "create_development_timeline",
    "create_waterfall_chart",
    "create_partnership_distribution_comparison",
    "create_sensitivity_heatmap",
    "create_cash_flow_timeline",
    # Utility functions
    "get_irr_color",
    "get_performance_color_scheme",
    "get_base_chart",
    "format_currency_altair",
    # Constants
    "RE_COLORS",
    "EXTENDED_PALETTE",
    "IRR_THRESHOLDS",
]
