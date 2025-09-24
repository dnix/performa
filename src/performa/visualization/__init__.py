# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Performa Visualization Helpers

Chart creation utilities optimized for interactive marimo notebooks and
real estate financial modeling. Provides industry-standard visualizations
with consistent styling and professional presentation quality.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

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
}

# IRR color coding for performance visualization
IRR_COLOR_MAP = {
    "excellent": "#28A745",  # Green for >20% IRR
    "strong": "#FFC107",  # Yellow for 15-20% IRR
    "modest": "#FD7E14",  # Orange for 10-15% IRR
    "weak": "#DC3545",  # Red for <10% IRR
}


def get_irr_color(irr_value: float) -> str:
    """Get color based on IRR performance thresholds."""
    if irr_value >= 0.20:
        return IRR_COLOR_MAP["excellent"]
    elif irr_value >= 0.15:
        return IRR_COLOR_MAP["strong"]
    elif irr_value >= 0.10:
        return IRR_COLOR_MAP["modest"]
    else:
        return IRR_COLOR_MAP["weak"]


# =============================================================================
# Chart Creation Functions
# =============================================================================


def create_sources_uses_chart(
    sources_data: Dict[str, float],
    uses_data: Dict[str, float],
    title: str = "Sources & Uses of Funds",
    height: int = 500,
) -> go.Figure:
    """
    Create side-by-side Sources & Uses bar chart.

    Industry-standard visualization showing project funding (sources)
    vs project costs (uses) in paired bar format.

    Args:
        sources_data: Dict of funding sources {"Equity": 5000000, "Debt": 10000000}
        uses_data: Dict of uses {"Land": 3000000, "Construction": 12000000}
        title: Chart title
        height: Chart height in pixels

    Returns:
        Plotly Figure configured for marimo display

    Example:
        ```python
        sources = {"Equity": 5_000_000, "Construction Loan": 10_000_000}
        uses = {"Land": 3_000_000, "Hard Costs": 12_000_000}
        fig = create_sources_uses_chart(sources, uses)
        fig  # Display in marimo
        ```
    """
    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=["Sources of Funds", "Uses of Funds"],
        specs=[[{"type": "bar"}, {"type": "bar"}]],
        horizontal_spacing=0.15,
    )

    # Sources (left side)
    sources_categories = list(sources_data.keys())
    sources_values = list(sources_data.values())

    fig.add_trace(
        go.Bar(
            x=sources_categories,
            y=sources_values,
            name="Sources",
            marker_color=RE_COLORS["success"],
            text=[f"${v:,.0f}" for v in sources_values],
            textposition="outside",
            showlegend=False,
        ),
        row=1,
        col=1,
    )

    # Uses (right side)
    uses_categories = list(uses_data.keys())
    uses_values = list(uses_data.values())

    fig.add_trace(
        go.Bar(
            x=uses_categories,
            y=uses_values,
            name="Uses",
            marker_color=RE_COLORS["primary"],
            text=[f"${v:,.0f}" for v in uses_values],
            textposition="outside",
            showlegend=False,
        ),
        row=1,
        col=2,
    )

    # Styling
    fig.update_layout(
        title={"text": title, "x": 0.5, "xanchor": "center"},
        height=height,
        yaxis_title="Amount ($)",
        yaxis2_title="Amount ($)",
        template="plotly_white",
    )

    # Format y-axis as currency
    fig.update_yaxes(tickformat="$,.0s")

    return fig


def create_cost_breakdown_donut(
    cost_data: Dict[str, float],
    title: str = "Total Project Cost Breakdown",
    height: int = 400,
) -> go.Figure:
    """
    Create donut chart showing cost component breakdown.

    Args:
        cost_data: Dict of cost categories and amounts
        title: Chart title
        height: Chart height in pixels

    Returns:
        Plotly donut chart figure

    Example:
        ```python
        costs = {
            "Land": 3_000_000,
            "Hard Costs": 12_000_000,
            "Soft Costs": 1_500_000,
            "Developer Fee": 750_000
        }
        fig = create_cost_breakdown_donut(costs)
        ```
    """
    labels = list(cost_data.keys())
    values = list(cost_data.values())
    total_cost = sum(values)

    # Create color palette
    colors = [
        RE_COLORS["primary"],
        RE_COLORS["secondary"],
        RE_COLORS["accent"],
        RE_COLORS["neutral"],
        "#FF6B6B",
        "#4ECDC4",
        "#45B7D1",
        "#96CEB4",
    ]

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.4,  # Makes it a donut
                marker=dict(
                    colors=colors[: len(labels)], line=dict(color="#FFFFFF", width=2)
                ),
                textinfo="label+percent",
                textposition="outside",
                hovertemplate="<b>%{label}</b><br>"
                + "Amount: $%{value:,.0f}<br>"
                + "Percentage: %{percent}<br>"
                + "<extra></extra>",
            )
        ]
    )

    # Add center text with abbreviated formatting
    if total_cost >= 1_000_000:
        formatted_total = f"${total_cost / 1_000_000:.1f}M"
    elif total_cost >= 1_000:
        formatted_total = f"${total_cost / 1_000:.1f}K"
    else:
        formatted_total = f"${total_cost:,.0f}"

    fig.add_annotation(
        text=f"<b>Total<br>{formatted_total}</b>",
        x=0.5,
        y=0.5,
        font_size=16,
        showarrow=False,
    )

    fig.update_layout(
        title={"text": title, "x": 0.5, "xanchor": "center"},
        height=height,
        template="plotly_white",
        showlegend=False,
        legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5),
    )

    return fig


def create_development_timeline(
    phases: List[Dict[str, Any]],
    title: str = "Development Timeline",
    height: int = 400,
) -> go.Figure:
    """
    Create Gantt-style development timeline chart.

    Args:
        phases: List of phase dicts with keys: 'name', 'start', 'end', 'color' (optional)
        title: Chart title
        height: Chart height in pixels

    Returns:
        Plotly Gantt chart figure

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
        fig = create_development_timeline(phases)
        ```
    """
    fig = go.Figure()

    # Add each phase as a horizontal bar
    for i, phase in enumerate(phases):
        start_date = pd.to_datetime(phase["start"])
        end_date = pd.to_datetime(phase["end"])
        duration_days = (end_date - start_date).days

        # Use provided color or default color scheme
        color = phase.get(
            "color",
            RE_COLORS["primary"]
            if i == 0
            else RE_COLORS["secondary"]
            if i == 1
            else RE_COLORS["accent"],
        )

        fig.add_trace(
            go.Scatter(
                x=[start_date, end_date, end_date, start_date, start_date],
                y=[i - 0.4, i - 0.4, i + 0.4, i + 0.4, i - 0.4],
                fill="toself",
                fillcolor=color,
                line=dict(color=color, width=2),
                name=phase["name"],
                text=f"{phase['name']}<br>{duration_days} days",
                textposition="middle center",
                hovertemplate="<b>%{text}</b><br>"
                + f"Start: {start_date.strftime('%Y-%m-%d')}<br>"
                + f"End: {end_date.strftime('%Y-%m-%d')}<br>"
                + f"Duration: {duration_days} days<extra></extra>",
                showlegend=True,
            )
        )

    # Update layout
    fig.update_layout(
        title={"text": title, "x": 0.5, "xanchor": "center"},
        height=height,
        xaxis_title="Timeline",
        yaxis=dict(
            tickmode="array",
            tickvals=list(range(len(phases))),
            ticktext=[phase["name"] for phase in phases],
            showgrid=False,
        ),
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        margin=dict(l=150),  # Space for phase names
    )

    return fig


def create_waterfall_chart(
    categories: List[str],
    values: List[float],
    title: str = "Cash Flow Waterfall",
    height: int = 500,
) -> go.Figure:
    """
    Create waterfall chart for step-by-step cash flow analysis.

    Perfect for partnership distributions, development costs, or
    any cumulative financial calculation.

    Args:
        categories: List of category names
        values: List of values (positive or negative)
        title: Chart title
        height: Chart height in pixels

    Returns:
        Plotly waterfall chart figure

    Example:
        ```python
        categories = ["Total Proceeds", "Debt Payoff", "Return of Capital", "Preferred Return", "GP Promote"]
        values = [25_000_000, -15_000_000, -5_000_000, -3_000_000, -2_000_000]
        fig = create_waterfall_chart(categories, values, "Partnership Distribution Waterfall")
        ```
    """
    # Prepare data for waterfall
    cumulative = [0]
    for value in values:
        cumulative.append(cumulative[-1] + value)

    # Create waterfall using go.Waterfall if available, otherwise custom bars
    try:
        fig = go.Figure(
            go.Waterfall(
                name="",
                orientation="v",
                measure=["relative"] * (len(categories) - 1) + ["total"],
                x=categories,
                y=values,
                text=[f"${v:,.0f}" for v in values],
                textposition="outside",
                connector={"line": {"color": "rgb(63, 63, 63)"}},
                increasing={"marker": {"color": RE_COLORS["success"]}},
                decreasing={"marker": {"color": RE_COLORS["danger"]}},
                totals={"marker": {"color": RE_COLORS["primary"]}},
            )
        )

    except AttributeError:
        # Fallback for older plotly versions - create custom bar chart
        fig = go.Figure()

        for i, (category, value) in enumerate(zip(categories, values)):
            color = RE_COLORS["success"] if value >= 0 else RE_COLORS["danger"]

            fig.add_trace(
                go.Bar(
                    x=[category],
                    y=[abs(value)],
                    base=[cumulative[i] if value >= 0 else cumulative[i] + value],
                    name=category,
                    marker_color=color,
                    text=f"${value:,.0f}",
                    textposition="outside",
                    showlegend=False,
                )
            )

    fig.update_layout(
        title={"text": title, "x": 0.5, "xanchor": "center"},
        height=height,
        yaxis_title="Amount ($)",
        yaxis_tickformat="$,.0s",
        template="plotly_white",
        showlegend=False,
    )

    return fig


def create_kpi_cards_data(
    deal_irr: float,
    equity_multiple: float,
    total_project_cost: float,
    net_profit: float,
    total_units: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Prepare data for marimo KPI cards (mo.stat).

    Args:
        deal_irr: Deal IRR as decimal (e.g., 0.185)
        equity_multiple: Equity multiple (e.g., 2.41)
        total_project_cost: Total project cost
        net_profit: Net profit amount
        total_units: Optional unit count for per-unit metrics

    Returns:
        List of dict suitable for mo.stat components

    Example:
        ```python
        kpi_data = create_kpi_cards_data(
            deal_irr=0.185,
            equity_multiple=2.41,
            total_project_cost=25_000_000,
            net_profit=8_500_000,
            total_units=120
        )

        # Use in marimo notebook:
        mo.hstack([
            mo.stat(value=kpi["value"], label=kpi["label"], icon=kpi["icon"], color=kpi["color"])
            for kpi in kpi_data
        ])
        ```
    """
    kpi_data = [
        {
            "label": "Project IRR",
            "value": f"{deal_irr:.1%}",
            "icon": "trending-up",
            "color": get_irr_color(deal_irr),
            "caption": "Internal Rate of Return",
        },
        {
            "label": "Equity Multiple",
            "value": f"{equity_multiple:.2f}x",
            "icon": "bar-chart-2",
            "color": RE_COLORS["success"]
            if equity_multiple >= 2.0
            else RE_COLORS["warning"],
            "caption": "Total Return Multiple",
        },
        {
            "label": "Total Project Cost",
            "value": _format_large_currency(total_project_cost),
            "icon": "building",
            "color": RE_COLORS["primary"],
            "caption": f"${total_project_cost / total_units:,.0f}/unit"
            if total_units
            else "Development Cost",
        },
        {
            "label": "Net Profit",
            "value": _format_large_currency(net_profit),
            "icon": "dollar-sign",
            "color": RE_COLORS["success"] if net_profit > 0 else RE_COLORS["danger"],
            "caption": f"{net_profit / total_project_cost:.1%} margin"
            if total_project_cost > 0
            else "Total Profit",
        },
    ]

    return kpi_data


def create_partnership_distribution_comparison(
    capital_contributions: Dict[str, float],
    profit_distributions: Dict[str, float],
    title: str = "Capital vs Profit Distribution",
    height: int = 400,
) -> go.Figure:
    """
    Create side-by-side pie charts comparing capital vs profit distribution.

    Visually demonstrates the "promote" concept - how profit distribution
    differs from initial capital contribution percentages.

    Args:
        capital_contributions: Dict of partner contributions {"GP": 1000000, "LP": 9000000}
        profit_distributions: Dict of partner profits {"GP": 3500000, "LP": 6500000}
        title: Chart title
        height: Chart height

    Returns:
        Plotly subplot figure with two pie charts
    """
    fig = make_subplots(
        rows=1,
        cols=2,
        specs=[[{"type": "pie"}, {"type": "pie"}]],
        subplot_titles=["Capital Contributions", "Profit Distribution"],
        horizontal_spacing=0.1,
    )

    # Capital contributions (left)
    cap_labels = list(capital_contributions.keys())
    cap_values = list(capital_contributions.values())
    cap_total = sum(cap_values)

    fig.add_trace(
        go.Pie(
            labels=cap_labels,
            values=cap_values,
            name="Capital",
            marker=dict(colors=[RE_COLORS["danger"], RE_COLORS["primary"]]),
            textinfo="label+percent",
            hovertemplate="<b>%{label}</b><br>"
            + "Amount: $%{value:,.0f}<br>"
            + "Percentage: %{percent}<br>"
            + "<extra></extra>",
            showlegend=False,
        ),
        row=1,
        col=1,
    )

    # Profit distributions (right)
    prof_labels = list(profit_distributions.keys())
    prof_values = list(profit_distributions.values())
    prof_total = sum(prof_values)

    fig.add_trace(
        go.Pie(
            labels=prof_labels,
            values=prof_values,
            name="Profit",
            marker=dict(colors=[RE_COLORS["danger"], RE_COLORS["primary"]]),
            textinfo="label+percent",
            hovertemplate="<b>%{label}</b><br>"
            + "Amount: $%{value:,.0f}<br>"
            + "Percentage: %{percent}<br>"
            + "<extra></extra>",
            showlegend=False,
        ),
        row=1,
        col=2,
    )

    fig.update_layout(
        title={"text": title, "x": 0.5, "xanchor": "center"},
        height=height,
        template="plotly_white",
    )

    return fig


def create_sensitivity_heatmap(
    x_variable: str,
    y_variable: str,
    x_values: List[float],
    y_values: List[float],
    irr_matrix: List[List[float]],
    title: str = "Two-Way Sensitivity Analysis",
    height: int = 500,
) -> go.Figure:
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
        height: Chart height

    Returns:
        Plotly heatmap figure

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

        fig = create_sensitivity_heatmap(
            "Exit Cap Rate", "Construction Cost/Unit",
            x_vals, y_vals, irr_matrix
        )
        ```
    """
    # Convert IRR matrix to percentage strings for display
    text_matrix = []
    for row in irr_matrix:
        text_row = [f"{irr:.1%}" for irr in row]
        text_matrix.append(text_row)

    # Create custom color scale based on IRR performance
    # Green for high IRR, red for low IRR
    colorscale = [
        [0.0, "#DC3545"],  # Red for low IRR
        [0.25, "#FD7E14"],  # Orange
        [0.5, "#FFC107"],  # Yellow
        [0.75, "#20C997"],  # Teal
        [1.0, "#28A745"],  # Green for high IRR
    ]

    fig = go.Figure(
        data=go.Heatmap(
            z=irr_matrix,
            x=x_values,
            y=y_values,
            text=text_matrix,
            texttemplate="%{text}",
            textfont={"size": 12},
            colorscale=colorscale,
            colorbar=dict(
                title="IRR",
                tickformat=".1%",
            ),
            hovertemplate="<b>IRR: %{text}</b><br>"
            + f"{x_variable}: %{{x}}<br>"
            + f"{y_variable}: %{{y}}<br>"
            + "<extra></extra>",
        )
    )

    fig.update_layout(
        title={"text": title, "x": 0.5, "xanchor": "center"},
        height=height,
        xaxis_title=x_variable,
        yaxis_title=y_variable,
        template="plotly_white",
    )

    # Format axes based on variable types
    if "rate" in x_variable.lower() or "cap" in x_variable.lower():
        fig.update_xaxes(tickformat=".1%")
    elif "cost" in x_variable.lower() or "price" in x_variable.lower():
        fig.update_xaxes(tickformat="$,.0f")

    if "rate" in y_variable.lower() or "cap" in y_variable.lower():
        fig.update_yaxes(tickformat=".1%")
    elif "cost" in y_variable.lower() or "price" in y_variable.lower():
        fig.update_yaxes(tickformat="$,.0f")

    return fig


def create_cash_flow_timeline(
    cash_flow_data: pd.DataFrame,
    title: str = "Annual Cash Flow Progression",
    height: int = 500,
) -> go.Figure:
    """
    Create annual cash flow timeline with cumulative overlay.

    Args:
        cash_flow_data: DataFrame with 'year' and 'cash_flow' columns
        title: Chart title
        height: Chart height

    Returns:
        Plotly figure with bars and line overlay

    Example:
        ```python
        cf_data = pd.DataFrame({
            'year': [2024, 2025, 2026, 2027, 2028],
            'cash_flow': [-10_000_000, 500_000, 800_000, 1_200_000, 15_000_000]
        })
        fig = create_cash_flow_timeline(cf_data)
        ```
    """
    # Calculate cumulative cash flows
    cash_flow_data = cash_flow_data.copy()
    cash_flow_data["cumulative"] = cash_flow_data["cash_flow"].cumsum()

    # Create subplot with secondary y-axis
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Add bar chart for annual cash flows
    colors = [
        RE_COLORS["danger"] if cf < 0 else RE_COLORS["success"]
        for cf in cash_flow_data["cash_flow"]
    ]

    fig.add_trace(
        go.Bar(
            x=cash_flow_data["year"],
            y=cash_flow_data["cash_flow"],
            name="Annual Cash Flow",
            marker_color=colors,
            text=[f"${cf:,.0f}" for cf in cash_flow_data["cash_flow"]],
            textposition="outside",
        ),
        secondary_y=False,
    )

    # Add line chart for cumulative cash flows
    fig.add_trace(
        go.Scatter(
            x=cash_flow_data["year"],
            y=cash_flow_data["cumulative"],
            mode="lines+markers",
            name="Cumulative",
            line=dict(color=RE_COLORS["accent"], width=4),
            marker=dict(size=8),
        ),
        secondary_y=True,
    )

    # Add zero line for reference
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)

    # Update layout
    fig.update_layout(
        title={"text": title, "x": 0.5, "xanchor": "center"},
        height=height,
        template="plotly_white",
        hovermode="x unified",
    )

    # Update y-axes
    fig.update_yaxes(
        title_text="Annual Cash Flow ($)", tickformat="$,.0s", secondary_y=False
    )
    fig.update_yaxes(title_text="Cumulative ($)", tickformat="$,.0s", secondary_y=True)
    fig.update_xaxes(title_text="Year")

    return fig


# =============================================================================
# Utility Functions
# =============================================================================


def _format_large_currency(value: float) -> str:
    """Format large currency values with appropriate units."""
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
    "create_sources_uses_chart",
    "create_cost_breakdown_donut",
    "create_development_timeline",
    "create_waterfall_chart",
    "create_sensitivity_heatmap",
    "create_kpi_cards_data",
    "create_partnership_distribution_comparison",
    "create_cash_flow_timeline",
    "get_irr_color",
    "get_performance_color_scheme",
    "RE_COLORS",
    "IRR_COLOR_MAP",
]
