import marimo

__generated_with = "0.10.6"
app = marimo.App(width="medium")


@app.cell
def __():
    """Import all required modules"""
    from datetime import date

    import marimo as mo
    import pandas as pd
    import plotly.express as px

    from performa.core.primitives import (
        FirstLastDrawSchedule,
        FirstOnlyDrawSchedule,
        LastOnlyDrawSchedule,
        ManualDrawSchedule,
        SCurveDrawSchedule,
        Timeline,
        UniformDrawSchedule,
    )
    
    return (
        FirstLastDrawSchedule, FirstOnlyDrawSchedule, LastOnlyDrawSchedule, 
        ManualDrawSchedule, SCurveDrawSchedule, Timeline, 
        UniformDrawSchedule, date, mo, pd, px
    )


@app.cell  
def __(mo):
    """Display title and introduction"""
    mo.md(
        r"""
        # 🏗️ Performa Draw Schedule Demo
        
        **Capital Deployment Patterns in Real Estate Development**
        
        This demo shows how Performa models different ways to deploy capital over time 
        during development projects. Each draw schedule represents a different spending 
        pattern commonly used in real estate development.
        
        ---
        """
    )
    return


@app.cell
def __(mo):
    """Create interactive controls"""
    
    # Amount control
    total_amount = mo.ui.slider(
        start=100_000,
        stop=5_000_000,
        step=100_000,
        value=1_000_000,
        label="💰 Total Project Cost",
        show_value=True
    )
    
    # Duration control
    duration_months = mo.ui.slider(
        start=6,
        stop=48,
        step=3,
        value=18,
        label="📅 Project Duration (months)",
        show_value=True
    )
    
    # S-Curve parameter
    s_curve_sigma = mo.ui.slider(
        start=0.5,
        stop=3.0,
        step=0.1,
        value=1.0,
        label="📈 S-Curve Steepness (sigma)",
        show_value=True
    )
    
    # First/Last split
    first_percentage = mo.ui.slider(
        start=0.1,
        stop=0.9,
        step=0.05,
        value=0.3,
        label="🎯 First Period % (for First/Last)",
        show_value=True
    )
    
    # Display controls directly - don't return multiple UI elements separately
    controls_display = mo.vstack([
        mo.md("## Interactive Controls"),
        mo.md("Adjust the parameters below to see how different draw schedules work:"),
        mo.hstack([total_amount, duration_months]),
        mo.hstack([s_curve_sigma, first_percentage])
    ])
    controls_display
    
    return total_amount, duration_months, s_curve_sigma, first_percentage


@app.cell
def __(total_amount, duration_months, s_curve_sigma, first_percentage, date, Timeline, UniformDrawSchedule, SCurveDrawSchedule, FirstOnlyDrawSchedule, LastOnlyDrawSchedule, FirstLastDrawSchedule, ManualDrawSchedule, pd):
    """Calculate cash flows for all draw schedules"""
    
    # Create timeline
    timeline = Timeline(
        start_date=date(2024, 1, 1),
        duration_months=duration_months.value
    )
    
    # Create different draw schedules
    schedules = {
        "Uniform": UniformDrawSchedule(),
        "S-Curve": SCurveDrawSchedule(sigma=s_curve_sigma.value),
        "Front-Loaded": FirstOnlyDrawSchedule(),
        "Back-Loaded": LastOnlyDrawSchedule(),
        "First/Last Split": FirstLastDrawSchedule(first_percentage=first_percentage.value),
        "Custom Manual": ManualDrawSchedule(values=[1, 2, 4, 6, 4, 2, 1] + [1] * max(0, duration_months.value - 7))
    }
    
    # Calculate cash flows
    cash_flows = {}
    for name, schedule in schedules.items():
        cf = schedule.apply_to_amount(
            amount=total_amount.value,
            periods=duration_months.value
            # Don't pass index - use default integer index to avoid Period serialization issues
        )
        cash_flows[name] = cf
    
    # Create DataFrame
    cf_df = pd.DataFrame(cash_flows)
    cf_df_plot = cf_df.reset_index()
    cf_df_plot["Month"] = range(1, len(cf_df_plot) + 1)
    
    return timeline, schedules, cash_flows, cf_df, cf_df_plot


@app.cell
def __(cf_df_plot, px, total_amount):
    """Create main visualization"""
    
    # Prepare data for plotting
    cf_melted = cf_df_plot.melt(
        id_vars=["Month"],
        var_name="Draw Schedule",
        value_name="Cash Flow"
    )
    
    # Create bar chart
    fig = px.bar(
        cf_melted,
        x="Month",
        y="Cash Flow",
        color="Draw Schedule",
        title=f"Capital Deployment Patterns - ${total_amount.value:,.0f} Total Project",
        labels={
            "Cash Flow": "Monthly Cash Flow ($)",
            "Month": "Project Month"
        },
        color_discrete_sequence=px.colors.qualitative.Set3
    )
    
    # Customize layout
    fig.update_layout(
        height=500,
        hovermode='x unified',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    fig.update_yaxes(tickformat="$,.0f")

    fig
    
    return


@app.cell
def __(mo):
    """Summary section header"""
    mo.md(
        r"""
        ## 📊 Summary Statistics
        
        Here's how each draw schedule pattern affects cash flow timing:
        """
    )
    return


@app.cell
def __(cf_df, mo, total_amount):
    """Create and display summary table"""
    
    # Build summary data
    summary_data = []
    for schedule_name in cf_df.columns:
        cf_series = cf_df[schedule_name]
        peak_month = cf_series.idxmax() + 1 if len(cf_series) > 0 else "N/A"
        
        summary_data.append({
            "Draw Schedule": schedule_name,
            "Peak Amount": f"${cf_series.max():,.0f}",
            "Peak Month": f"Month {peak_month}",
            "First Month %": f"{(cf_series.iloc[0] / total_amount.value * 100):.1f}%",
            "Last Month %": f"{(cf_series.iloc[-1] / total_amount.value * 100):.1f}%"
        })
    
    mo.ui.table(data=summary_data, selection=None)
    return


@app.cell
def __(mo):
    """Educational content about draw schedules"""
    mo.md(
        r"""
        ---
        
        ## 🎯 When to Use Each Pattern
        
        **Uniform**: Most common for predictable construction. Even cash flow demands.
        
        **S-Curve**: Realistic construction pattern. Slow start (permits, site prep), 
        heavy middle phase (major construction), tapering finish (punch list, landscaping).
        
        **Front-Loaded**: Land acquisition, upfront mobilization, or immediate material purchases.
        
        **Back-Loaded**: Completion bonuses, retention releases, or milestone payments.
        
        **First/Last Split**: Common in development deals - upfront land cost plus completion payment.
        
        **Custom Manual**: When you need precise control over timing based on project specifics.
        
        ---
        
        ## 💡 Real Estate Applications
        
        - **Office Development**: Typically S-curve for construction, front-loaded for land
        - **Residential Projects**: Often first/last split for phases 
        - **Renovations**: Usually uniform or manual based on unit availability
        - **Infrastructure**: Custom patterns following engineering timelines
        
        *Adjust the sliders above to see how different parameters affect cash flow timing!*
        """
    )
    return


if __name__ == "__main__":
    app.run() 