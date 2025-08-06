import marimo

__generated_with = "0.10.6"
app = marimo.App(width="medium", css_file="../marimo.css")


@app.cell
def __():
    """Import all required modules"""
    import marimo as mo
    import pandas as pd
    import plotly.express as px
    import plotly.graph_objects as go
    from datetime import date
    
    from performa.core.primitives import (
        Timeline, 
        UniformDrawSchedule, 
        SCurveDrawSchedule, 
        ManualDrawSchedule,
        FirstOnlyDrawSchedule,
        LastOnlyDrawSchedule,
        FirstLastDrawSchedule,
        UnitOfMeasureEnum
    )
    
    return (
        FirstLastDrawSchedule, FirstOnlyDrawSchedule, LastOnlyDrawSchedule, 
        ManualDrawSchedule, SCurveDrawSchedule, Timeline, UnitOfMeasureEnum, 
        UniformDrawSchedule, date, go, mo, pd, px
    )


@app.cell  
def __(mo):
    """Display title and introduction"""
    mo.md(
        r"""
        # 💰 Draw Schedule Builder
        
        **Configure Capital Deployment for a Single Budget Item**
        
        Build and visualize how a specific budget item (like site preparation, 
        construction, or equipment) will deploy its costs over time. Choose the 
        deployment pattern and configure parameters to match your project needs.
        
        ---
        """
    )
    return


@app.cell
def __(mo):
    """Create project configuration controls"""
    
    # Budget item basics
    item_name = mo.ui.text(
        placeholder="Site Preparation",
        label="💰 Budget Item Name"
    )
    
    total_amount = mo.ui.number(
        start=100_000,
        stop=50_000_000,
        step=100_000,
        value=2_500_000,
        label="💰 Total Project Cost ($)"
    )
    
    duration_months = mo.ui.slider(
        start=6,
        stop=60,
        step=3,
        value=24,
        label="📅 Project Duration (months)",
        show_value=True
    )
    
    return item_name, total_amount, duration_months


@app.cell
def __(mo):
    """Create schedule type selection"""
    
    schedule_type = mo.ui.dropdown(
        options={
            "uniform": "📊 Uniform - Even distribution over time",
            "s_curve": "📈 S-Curve - Realistic construction pattern", 
            "front_loaded": "🚀 Front-Loaded - Major upfront costs",
            "back_loaded": "🎯 Back-Loaded - Completion-heavy costs",
            "first_last": "⚖️ First/Last Split - Start and finish emphasis",
            "manual": "✏️ Custom Manual - Define your own pattern"
        },
        value="s_curve",
        label="🎨 Draw Schedule Pattern"
    )
    
    return schedule_type


@app.cell
def __(mo):
    """Create all parameter inputs (always available)"""
    
    # S-Curve parameters - always create
    s_curve_sigma = mo.ui.slider(
        start=0.3,
        stop=3.0,
        step=0.1,
        value=2.0,
        label="📈 Curve Steepness (σ)",
        show_value=True
    )
    
    # First/Last Split parameters - always create
    first_last_percentage = mo.ui.slider(
        start=0.05,
        stop=0.95,
        step=0.05,
        value=0.25,
        label="🎯 First Period Percentage",
        show_value=True
    )
    
    # Manual schedule parameters - always create
    manual_values = mo.ui.text_area(
        placeholder="3, 1, 7, 2, 5, 8, 1, 4, 6, 2, 3",
        label="✏️ Custom Weights (comma-separated)",
        rows=3
    )
    
    return s_curve_sigma, first_last_percentage, manual_values


@app.cell
def __(mo, item_name, total_amount, duration_months, schedule_type, s_curve_sigma, first_last_percentage, manual_values):
    """Display configuration interface"""
    
    # Create two-column layout for main configuration
    left_column = mo.vstack([
        mo.md("## 💰 Budget Item Configuration"),
        item_name, 
        total_amount, 
        duration_months
    ])
    
    # Build right column with schedule selection + dynamic parameters
    right_column_elements = [
        mo.md("## 🎨 Schedule Pattern Selection"),
        schedule_type
    ]
    
    # Add parameter inputs to right column based on selection
    if "S-Curve" in schedule_type.value:
        right_column_elements.extend([
            mo.md("### 📈 S-Curve Parameters"),
            mo.md("Adjust the curve steepness to match your construction timeline:"),
            s_curve_sigma
        ])
    elif "First/Last Split" in schedule_type.value:
        right_column_elements.extend([
            mo.md("### ⚖️ First/Last Split Parameters"),
            mo.md("Set what percentage of total cost happens in the first period:"),
            first_last_percentage
        ])
    elif "Custom Manual" in schedule_type.value:
        right_column_elements.extend([
            mo.md("### ✏️ Custom Manual Pattern"),
            mo.md("Enter comma-separated weights (will be normalized to your total cost):"),
            manual_values
        ])
    
    right_column = mo.vstack(right_column_elements)
    
    # Build UI elements with horizontal layout
    ui_elements = [
        mo.hstack([left_column, right_column], justify="space-between")
    ]
    
    # Display everything stacked together
    mo.vstack(ui_elements)
    
    return


@app.cell
def __(item_name, total_amount, duration_months, schedule_type, s_curve_sigma, first_last_percentage, manual_values, date, Timeline, UniformDrawSchedule, SCurveDrawSchedule, FirstOnlyDrawSchedule, LastOnlyDrawSchedule, FirstLastDrawSchedule, ManualDrawSchedule, pd):
    """Create the draw schedule and calculate cash flows"""
    
    # Get budget item parameters  
    item_title = item_name.value or "Budget Item"
    amount = total_amount.value
    duration = duration_months.value
    
    # Create timeline
    timeline = Timeline(
        start_date=date(2024, 1, 1),
        duration_months=duration
    )
    
    # Create the appropriate schedule based on selection
    if "Uniform" in schedule_type.value:
        schedule = UniformDrawSchedule()
        schedule_name = "Uniform Distribution"
        
    elif "S-Curve" in schedule_type.value:
        sigma = s_curve_sigma.value
        schedule = SCurveDrawSchedule(sigma=sigma)
        schedule_name = f"S-Curve (σ={sigma:.1f})"
        
    elif "Front-Loaded" in schedule_type.value:
        schedule = FirstOnlyDrawSchedule()
        schedule_name = "Front-Loaded"
        
    elif "Back-Loaded" in schedule_type.value:
        schedule = LastOnlyDrawSchedule()
        schedule_name = "Back-Loaded"
        
    elif "First/Last Split" in schedule_type.value:
        first_pct = first_last_percentage.value
        schedule = FirstLastDrawSchedule(first_percentage=first_pct)
        schedule_name = f"First/Last Split ({first_pct:.0%} first)"
        
    elif "Custom Manual" in schedule_type.value:
        manual_text = manual_values.value or "3,1,7,2,5,8,1,4,6,2,3"
        try:
            # Parse manual values
            manual_weights = [float(x.strip()) for x in manual_text.split(",")]
            # Pad or trim to match duration
            if len(manual_weights) < duration:
                manual_weights.extend([1] * (duration - len(manual_weights)))
            else:
                manual_weights = manual_weights[:duration]
            schedule = ManualDrawSchedule(values=manual_weights)
            schedule_name = "Custom Manual Pattern"
        except (ValueError, AttributeError):
            # Fallback to uniform if parsing fails
            schedule = UniformDrawSchedule()
            schedule_name = "Uniform (Manual Parse Error)"
    else:
        # Default fallback 
        schedule = UniformDrawSchedule()
        schedule_name = "Uniform Distribution"
    
    # Calculate cash flows
    cash_flows = schedule.apply_to_amount(
        amount=amount,
        periods=duration
    )
    
    # Create visualization DataFrame
    cf_df = pd.DataFrame({
        'Month': range(1, len(cash_flows) + 1),
        'Cash_Flow': cash_flows.values,
        'Cumulative': cash_flows.cumsum().values
    })
    
    return item_title, amount, duration, timeline, schedule, schedule_name, cash_flows, cf_df


@app.cell
def __(cf_df, item_title, amount, schedule_name, cash_flows, px, go):
    """Create visualization"""
    
    # Create subplot with secondary y-axis
    fig = go.Figure()
    
    # Add bar chart for monthly cash flows
    fig.add_trace(go.Bar(
        x=cf_df['Month'],
        y=cf_df['Cash_Flow'],
        name='Monthly Draw',
        marker_color='#3498db',
        yaxis='y1'
    ))
    
    # Add line chart for cumulative
    fig.add_trace(go.Scatter(
        x=cf_df['Month'],
        y=cf_df['Cumulative'],
        mode='lines+markers',
        name='Cumulative',
        line=dict(color='#e74c3c', width=4),
        marker=dict(size=8, color='#e74c3c'),
        yaxis='y2'
    ))
    
    # Update layout with dual y-axes
    fig.update_layout(
        title=f"{item_title}<br><sub>{schedule_name} - ${amount:,.0f} Total</sub>",
        xaxis_title="Month",
        yaxis=dict(
            title="Monthly Cash Flow ($)",
            tickformat="$,.0f",
            side="left"
        ),
        yaxis2=dict(
            title="Cumulative Cash Flow ($)",
            tickformat="$,.0f",
            overlaying="y",
            side="right"
        ),
        height=500,
        hovermode='x unified',
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right", 
            x=1
        )
    )
    
    fig
    return


@app.cell
def __(mo):
    """Summary section header"""
    mo.md(
        r"""
        ## 📊 Cash Flow Analysis
        
        Detailed breakdown of your configured draw schedule:
        """
    )
    return


@app.cell
def __(cf_df, amount, cash_flows, mo):
    """Create detailed cash flow table"""
    
    # Create detailed table data
    table_data = []
    for idx, row in cf_df.iterrows():
        table_data.append({
            "Month": f"Month {int(row['Month'])}",
            "Monthly Draw": f"${row['Cash_Flow']:,.0f}",
            "% of Total": f"{(row['Cash_Flow'] / amount * 100):.1f}%",
            "Cumulative": f"${row['Cumulative']:,.0f}",
            "% Complete": f"{(row['Cumulative'] / amount * 100):.1f}%"
        })
    
    mo.ui.table(
        data=table_data,
        selection=None,
        pagination=True,
        page_size=12
    )
    return


@app.cell
def __(cf_df, amount, cash_flows, mo):
    """Create summary statistics"""
    
    peak_month = cf_df.loc[cf_df['Cash_Flow'].idxmax(), 'Month']
    peak_amount = cf_df['Cash_Flow'].max()
    avg_monthly = cf_df['Cash_Flow'].mean()
    
    mo.md(f"""
    ### 📈 Schedule Statistics
    
    - **Peak Draw**: ${peak_amount:,.0f} in Month {peak_month:.0f}
    - **Average Monthly**: ${avg_monthly:,.0f}
    - **First Month**: ${cf_df.iloc[0]['Cash_Flow']:,.0f} ({cf_df.iloc[0]['Cash_Flow'] / amount * 100:.1f}%)
    - **Last Month**: ${cf_df.iloc[-1]['Cash_Flow']:,.0f} ({cf_df.iloc[-1]['Cash_Flow'] / amount * 100:.1f}%)
    - **Total Verified**: ${cf_df['Cash_Flow'].sum():,.0f} ✓
    """)
    return


@app.cell
def __(mo, schedule_type):
    """Educational content about the selected pattern"""
    
    # Show educational content based on selection
    if "Uniform" in schedule_type.value:
        mo.md("""
        ### 📊 Uniform Distribution
        **Perfect for**: Predictable construction with steady resource needs
        - Equal monthly cash flows throughout the project
        - Simplest to budget and manage
        - Good baseline for comparison with other patterns
        """)
    elif "S-Curve" in schedule_type.value:
        mo.md("""
        ### 📈 S-Curve Distribution  
        **Perfect for**: Realistic construction modeling
        - Slow start (permits, site preparation, mobilization)
        - Heavy middle phase (major construction activities)
        - Tapering finish (punch list, landscaping, final inspections)
        - Matches most real-world construction spending patterns
        """)
    elif "Front-Loaded" in schedule_type.value:
        mo.md("""
        ### 🚀 Front-Loaded Distribution
        **Perfect for**: Projects with major upfront costs
        - Land acquisition deals
        - Equipment purchases before construction
        - Permit and soft cost heavy projects
        - Immediate material procurement strategies
        """)
    elif "Back-Loaded" in schedule_type.value:
        mo.md("""
        ### 🎯 Back-Loaded Distribution
        **Perfect for**: Completion-dependent expenditures
        - Retention release schedules
        - Performance milestone payments
        - Final equipment installations
        - Completion bonuses and final inspections
        """)
    elif "First/Last Split" in schedule_type.value:
        mo.md("""
        ### ⚖️ First/Last Split Distribution
        **Perfect for**: Projects with distinct phases
        - Land cost upfront + construction completion costs
        - Design/permitting phase + construction phase
        - Phase 1 infrastructure + Phase 2 vertical construction
        - Common in development deals with milestone payments
        """)
    elif "Custom Manual" in schedule_type.value:
        mo.md("""
        ### ✏️ Custom Manual Distribution
        **Perfect for**: Unique project requirements
        - Following detailed construction schedules
        - Matching contractor payment schedules
        - Modeling complex phased developments
        - Testing custom cash flow scenarios
        """)
    
    return


@app.cell
def __(mo):
    """Usage tips and next steps"""
    mo.md(
        r"""
        ---
        
        ### Tips for Using This Builder
        
        **Experiment with Parameters**: Try different steepness values for S-curves or split percentages for First/Last patterns.
        
        **Real-World Validation**: Compare your pattern against actual project cash flows to refine parameters.
        
        **Documentation**: Use the budget item name to track different cost categories you're modeling.
        
        **Next Steps**: Once you've configured this budget item, you can combine multiple items into a complete capital plan.
        
        ---
        
        *This builder helps you configure individual budget items before combining them into complete capital plans.*
        """
    )
    return


if __name__ == "__main__":
    app.run()
