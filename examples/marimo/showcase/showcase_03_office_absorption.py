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
    from datetime import date, timedelta
    
    from performa.asset.office import (
        OfficeAbsorptionPlan, 
        FixedQuantityPace, 
        EqualSpreadPace,
        DirectLeaseTerms,
        SpaceFilter,
        OfficeVacantSuite
    )
    from performa.core.primitives import (
        UnitOfMeasureEnum, 
        FrequencyEnum, 
        UponExpirationEnum
    )
    
    return (
        DirectLeaseTerms, EqualSpreadPace, FixedQuantityPace, FrequencyEnum, 
        OfficeAbsorptionPlan, OfficeVacantSuite, SpaceFilter, UnitOfMeasureEnum, 
        UponExpirationEnum, date, go, mo, pd, px, timedelta
    )


@app.cell  
def __(mo):
    """Display title and introduction"""
    mo.md(
        r"""
        # 🏢 Office Absorption Modeling
        
        **Watch Vacant Space Transform Into Multiple Leases**
        
        This demo shows how Performa models the lease-up process for vacant office space. 
        Starting with raw vacant floor plates, we'll apply different leasing strategies 
        and watch as the space gets subdivided and leased to multiple tenants over time.
        
        This is where real estate development meets business strategy - transforming 
        empty buildings into cash-flowing assets.
        
        ---
        """
    )
    return


@app.cell
def __(mo):
    """Create building configuration controls"""
    
    # Building basics
    building_name = mo.ui.text(
        placeholder="Downtown Office Tower",
        value="Metro Office Plaza",
        label="❶ Building Name"
    )
    
    total_floors = mo.ui.slider(
        start=2,
        stop=20,
        step=1,
        value=8,
        label="❷ Number of Floors",
        show_value=True
    )
    
    floor_area = mo.ui.slider(
        start=5_000,
        stop=50_000,
        step=2_500,
        value=15_000,
        label="❸ Area per Floor (SF)",
        show_value=True
    )
    
    return building_name, total_floors, floor_area


@app.cell
def __(mo, floor_area):
    """Create subdivision control based on floor area"""
    
    # Subdivision control - dynamic max based on floor area
    avg_lease_size = mo.ui.slider(
        start=5_000,
        stop=floor_area.value,  # Can't be larger than floor area
        step=1_000,
        value=min(15_000, floor_area.value),  # Default to 15k or floor area, whichever is smaller
        label="❹ Average Lease Size",
        show_value=True
    )
    
    return avg_lease_size


@app.cell
def __(mo):
    """Create leasing strategy controls"""
    
    # Strategy selection
    pace_strategy = mo.ui.dropdown(
        options={
            "fixed_quantity": "🎯 Fixed Quantity - Lease X SF every Y months",
            "equal_spread": "📈 Equal Spread - Even pace over time period", 
        },
        value="fixed_quantity",
        label="❺ Leasing Strategy"
    )
    
    return pace_strategy


@app.cell
def __(mo):
    """Create lease terms controls"""
    
    base_rent = mo.ui.slider(
        start=15.0,
        stop=65.0,
        step=2.5,
        value=35.0,
        label="❻ Base Rent ($/SF/year)",
        show_value=True
    )
    
    lease_term = mo.ui.slider(
        start=24,
        stop=120,
        step=12,
        value=60,
        label="❼ Lease Term (months)",
        show_value=True
    )
    
    start_delay = mo.ui.slider(
        start=0,
        stop=18,
        step=3,
        value=6,
        label="❽ Initial Delay (months)",
        show_value=True
    )
    
    return base_rent, lease_term, start_delay


@app.cell
def __(mo):
    """Create all strategy-specific UI controls upfront"""
    
    # Fixed quantity parameters - always create
    lease_quantity = mo.ui.slider(
        start=5_000,
        stop=100_000,
        step=5_000,
        value=25_000,
        label="❾ SF per Period",
        show_value=True
    )
    
    lease_frequency = mo.ui.slider(
        start=1,
        stop=12,
        step=1,
        value=3,
        label="❿ Months Between",
        show_value=True
    )
    
    # Equal spread parameters - always create
    total_deals = mo.ui.slider(
        start=2,
        stop=20,
        step=1,
        value=8,
        label="⓫ Total Number of Deals",
        show_value=True
    )
    
    deal_frequency = mo.ui.slider(
        start=1,
        stop=12,
        step=1,
        value=3,
        label="⓬ Months Between Deals",
        show_value=True
    )
    
    return lease_quantity, lease_frequency, total_deals, deal_frequency


@app.cell
def __(mo, building_name, total_floors, floor_area, avg_lease_size, pace_strategy, base_rent, lease_term, start_delay, lease_quantity, lease_frequency, total_deals, deal_frequency):
    """Display configuration interface with conditional parameter visibility"""
    
    # Building configuration section
    building_section = mo.vstack([
        mo.md("## 🏢 Building Configuration"),
        building_name,
        mo.vstack([total_floors, floor_area, avg_lease_size])
    ])
    
    # Strategy section with conditional parameters
    strategy_elements = [
        mo.md("## 🎨 Leasing Strategy"),
        pace_strategy
    ]
    
    # Conditionally display strategy-specific controls
    if "Fixed Quantity" in pace_strategy.value:
        strategy_elements.extend([
            mo.md("### Fixed Quantity Parameters"),
            mo.md("Lease a specific amount of space at regular intervals:"),
            lease_quantity,
            lease_frequency,
            mo.md(f"📝 *Note: Total SF will be subdivided into individual leases averaging ~{avg_lease_size.value:,} SF each*")
        ])
        
    elif "Equal Spread" in pace_strategy.value:
        strategy_elements.extend([
            mo.md("### Equal Spread Parameters"),
            mo.md("Divide total vacant space into a fixed number of deals:"),
            total_deals,
            deal_frequency
        ])
    
    strategy_section = mo.vstack(strategy_elements)
    
    # Lease terms section
    terms_section = mo.vstack([
        mo.md("## 💰 Market Lease Terms"),
        mo.vstack([base_rent, lease_term, start_delay]),
        
    ])
    
    # Display all sections in a single row
    display_interface = mo.hstack([
        building_section, 
        strategy_section, 
        terms_section
    ], justify="space-between", widths="equal")
    
    display_interface


@app.cell
def __(building_name, total_floors, floor_area, avg_lease_size, OfficeVacantSuite):
    """Create vacant building inventory"""
    
    # Build vacant suite inventory
    vacant_suites = []
    building_title = building_name.value or "Office Building"
    
    for floor_num in range(1, total_floors.value + 1):
        suite = OfficeVacantSuite(
            suite=f"Floor-{floor_num:02d}",
            floor=str(floor_num),
            area=floor_area.value,
            use_type="office",
            is_divisible=True,  # Allow subdivision of floor plates
            subdivision_average_lease_area=min(avg_lease_size.value, floor_area.value),  # Average lease size when subdivided
            subdivision_minimum_lease_area=max(3_000, min(avg_lease_size.value, floor_area.value) // 3),  # Minimum viable lease size
            subdivision_naming_pattern="{master_suite_id}-Suite{count:02d}"
        )
        vacant_suites.append(suite)
    
    total_vacant_sf = sum(suite.area for suite in vacant_suites)
    
    # Display building summary
    building_summary = f"""
    ### 🏢 {building_title} - Vacant Inventory
    
    - **Total Floors**: {total_floors.value}
    - **Area per Floor**: {floor_area.value:,} SF  
    - **Total Vacant Space**: {total_vacant_sf:,} SF
    - **Floors Available for Subdivision**: All floors
    """
    
    return vacant_suites, total_vacant_sf, building_summary, building_title


# @app.cell
# def __(mo, building_summary):
#     """Display building summary"""
#     mo.md(building_summary)
#     return


@app.cell
def __(pace_strategy, lease_quantity, lease_frequency, total_deals, deal_frequency, base_rent, lease_term, start_delay, date, timedelta, FixedQuantityPace, EqualSpreadPace, DirectLeaseTerms, SpaceFilter, OfficeAbsorptionPlan, UnitOfMeasureEnum, FrequencyEnum, UponExpirationEnum):
    """Create absorption plan and pace model"""
    
    # Create pace model based on strategy
    if "Fixed Quantity" in pace_strategy.value:
        # Use Fixed Quantity parameters
        pace_model = FixedQuantityPace(
            type="FixedQuantity",
            quantity=lease_quantity.value,
            unit="SF",
            frequency_months=lease_frequency.value
        )
        pace_description = f"Lease {lease_quantity.value:,} SF every {lease_frequency.value} months"
    else:  # equal_spread
        # Use Equal Spread parameters
        pace_model = EqualSpreadPace(
            type="EqualSpread", 
            total_deals=total_deals.value,
            frequency_months=deal_frequency.value
        )
        pace_description = f"Spread into {total_deals.value} deals every {deal_frequency.value} months"
    
    # Create lease terms
    lease_terms = DirectLeaseTerms(
        base_rent_value=base_rent.value,
        base_rent_unit_of_measure=UnitOfMeasureEnum.PER_UNIT,
        base_rent_frequency=FrequencyEnum.ANNUAL,
        term_months=lease_term.value,
        upon_expiration=UponExpirationEnum.MARKET
    )
    
    # Calculate start date
    leasing_start_date = date.today() + timedelta(days=start_delay.value * 30)
    
    # Create absorption plan
    absorption_plan = OfficeAbsorptionPlan.with_typical_assumptions(
        name="Building Lease-Up",
        space_filter=SpaceFilter(use_types=["office"]),
        start_date_anchor=leasing_start_date,
        pace=pace_model,
        leasing_assumptions=lease_terms
    )
    
    return pace_model, pace_description, lease_terms, leasing_start_date, absorption_plan


@app.cell
def __(vacant_suites, absorption_plan, leasing_start_date, date, timedelta, total_vacant_sf, pace_model, pace_description):
    """Execute absorption plan and generate lease specs"""
    
    # Set analysis period starting from when leasing begins (to ensure leases are generated)
    analysis_start = min(date.today(), leasing_start_date)
    
    # Calculate dynamic analysis period to ensure full absorption is possible
    if hasattr(pace_model, 'quantity'):  # FixedQuantityPace
        # Fixed Quantity: estimate time needed based on total space and pace
        periods_needed = max(1, int(total_vacant_sf / pace_model.quantity))
        months_needed = periods_needed * pace_model.frequency_months
    else:  # EqualSpreadPace
        # Equal Spread: use total deals and frequency
        months_needed = pace_model.total_deals * pace_model.frequency_months
    
    # Add 50% buffer and minimum 5 years to ensure completion
    analysis_years = max(5, int(months_needed * 1.5 / 12))
    analysis_end = leasing_start_date + timedelta(days=analysis_years * 365)
    
    # Debug info
    analysis_info = f"Analysis period: {analysis_years} years (estimated {months_needed} months needed)"
    
    # Execute the absorption plan
    generated_lease_specs = absorption_plan.generate_lease_specs(
        available_vacant_suites=vacant_suites,
        analysis_start_date=analysis_start,
        analysis_end_date=analysis_end,
        lookup_fn=None,
        global_settings=None
    )
    
    # Calculate leasing summary
    total_leased_sf = sum(spec.area for spec in generated_lease_specs)
    leasing_percentage = (total_leased_sf / total_vacant_sf * 100) if total_vacant_sf > 0 else 0
    
    return generated_lease_specs, analysis_start, analysis_end, total_leased_sf, leasing_percentage, analysis_info


# @app.cell
# def __(mo, generated_lease_specs, total_leased_sf, total_vacant_sf, leasing_percentage, pace_description, leasing_start_date):
#     """Display absorption results summary"""
    
#     mo.md(f"""
#     ## 📊 Absorption Results
    
#     **Strategy**: {pace_description}
    
#     - **Leases Generated**: {len(generated_lease_specs)}
#     - **Total SF Leased**: {total_leased_sf:,.0f} SF
#     - **Vacant SF Remaining**: {total_vacant_sf - total_leased_sf:,.0f} SF  
#     - **Building Occupancy**: {leasing_percentage:.1f}%
    
#     {f"**Note**: Leasing starts {leasing_start_date}" if len(generated_lease_specs) > 0 else "**Try reducing 'Months Until Leasing Starts' to 0 to see immediate results.**"}
    
#     ---
#     """)
#     return


@app.cell
def __(mo, building_summary, analysis_info):
    """Display building summary and analysis period"""
    mo.md(f"""
    ---
    
    📊 **{analysis_info}**
    """)
    return



@app.cell
def __(generated_lease_specs, pd):
    """Create lease timeline visualization data"""
    
    if not generated_lease_specs:
        timeline_df = pd.DataFrame()
    else:
        # Create timeline data
        timeline_data = []
        cumulative_sf = 0
        
        for spec in generated_lease_specs:
            cumulative_sf += spec.area
            timeline_data.append({
                'Lease_Date': spec.start_date,
                'Tenant': spec.tenant_name,
                'Suite': spec.suite,
                'Area_SF': spec.area,
                'Cumulative_SF': cumulative_sf,
                'Monthly_Rent': spec.area * spec.base_rent_value / 12,
                'Annual_Rent': spec.area * spec.base_rent_value
            })
        
        timeline_df = pd.DataFrame(timeline_data)
        timeline_df['Lease_Date'] = pd.to_datetime(timeline_df['Lease_Date'])
        timeline_df = timeline_df.sort_values('Lease_Date')
    
    return timeline_df


@app.cell  
def __(mo):
    """Section header for absorption timeline"""
    mo.md(
        r"""
        ## 📊 Absorption Timeline & Progress
        
        Track leasing velocity and cumulative progress over time:
        """
    )
    return


@app.cell
def __(timeline_df, go, building_title, mo):
    """Create absorption timeline visualization"""
    
    if timeline_df.empty:
        display_output = mo.md("No leases generated with current parameters.")
    else:
        # Create dual-axis chart
        fig = go.Figure()
        
        # Add bar chart for individual lease areas
        fig.add_trace(go.Bar(
            x=timeline_df['Lease_Date'],
            y=timeline_df['Area_SF'],
            name='Lease Area (SF)',
            marker_color='#3498db',
            yaxis='y1',
            hovertemplate='<b>%{x}</b><br>Lease: %{y:,.0f} SF<br>Tenant: %{customdata}<extra></extra>',
            customdata=timeline_df['Tenant']
        ))
        
        # Add stepped line chart for cumulative leased area
        fig.add_trace(go.Scatter(
            x=timeline_df['Lease_Date'],
            y=timeline_df['Cumulative_SF'],
            mode='lines+markers',
            name='Cumulative Leased',
            line=dict(color='#e74c3c', width=4, shape='hv'),  # 'hv' creates stepped line
            marker=dict(size=8, color='#e74c3c'),
            yaxis='y2',
            hovertemplate='<b>%{x}</b><br>Total Leased: %{y:,.0f} SF<extra></extra>'
        ))
        
        # Update layout with dual y-axes
        fig.update_layout(
            title=f"{building_title}<br><sub>Lease Absorption Timeline</sub>",
            xaxis_title="Date",
            yaxis=dict(
                title="Individual Lease Area (SF)",
                tickformat=",.0f",
                side="left"
            ),
            yaxis2=dict(
                title="Cumulative Leased Area (SF)",
                tickformat=",.0f",
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
        
        display_output = fig
    
    display_output


@app.cell
def __(mo):
    """Section header for Gantt chart"""
    mo.md(
        r"""
        ## 📅 Lease Terms Timeline
        
        Gantt chart showing the full duration of each lease from start to expiration.
        **Bar height represents lease square footage** - larger leases appear taller:
        """
    )
    return


@app.cell
def __(timeline_df, go, building_title, mo, pd, lease_term):
    """Create Gantt chart showing lease terms and durations"""
    
    if timeline_df.empty:
        gantt_output = mo.md("*No lease timeline to display*")
    else:
        # Create Gantt chart using a simpler approach
        gantt_fig = go.Figure()
        
        # Use actual lease term from controls
        lease_term_months = lease_term.value
        
        # Sort leases by start date for chronological display (first lease at top)
        gantt_sorted_leases = timeline_df.sort_values('Lease_Date').reset_index(drop=True)
        
        # Calculate bar heights based on lease areas (normalized to avoid jittiness)
        min_area = gantt_sorted_leases['Area_SF'].min()
        max_area = gantt_sorted_leases['Area_SF'].max()
        num_leases = len(gantt_sorted_leases)
        
        # Calculate base height to utilize chart space efficiently
        available_height = num_leases * 1.2  # Total domain height
        gap_height = 0.1  # Small gap between bars
        usable_height = available_height - (num_leases - 1) * gap_height
        
        # Normalize heights to use available space proportionally
        min_height = 0.4  # Minimum readable height
        max_height = usable_height / num_leases * 2.0  # Allow larger bars to be up to 2x average
        
        def get_bar_height(area_sf):
            if max_area == min_area:  # All leases same size
                return usable_height / num_leases  # Equal distribution
            # Linear scaling based on area
            normalized = (area_sf - min_area) / (max_area - min_area)
            return min_height + normalized * (max_height - min_height)
        
        # Calculate y-positions from top to bottom (chronological order)
        y_positions = []
        current_y = available_height  # Start from top
        
        for gantt_idx, lease_row in gantt_sorted_leases.iterrows():
            bar_height = get_bar_height(lease_row['Area_SF'])
            current_y -= bar_height  # Move down by bar height
            y_positions.append((current_y, bar_height))
            current_y -= gap_height  # Add gap for next bar
        
        # Prepare data for Gantt chart
        for gantt_idx, lease_row in gantt_sorted_leases.iterrows():
            lease_start = lease_row['Lease_Date']
            lease_end = lease_start + pd.DateOffset(months=lease_term_months)
            
            # Get y-position and height for this lease (chronological order, first at top)
            y_bottom, bar_height = y_positions[gantt_idx]
            y_top = y_bottom + bar_height
            
            # Create a horizontal bar using Scatter with fill
            gantt_fig.add_trace(go.Scatter(
                x=[lease_start, lease_end, lease_end, lease_start, lease_start],
                y=[y_bottom, y_bottom, y_top, y_top, y_bottom],
                fill='toself',
                fillcolor=f"hsla({(gantt_idx * 40) % 360}, 70%, 60%, 0.7)",
                line=dict(color=f"hsl({(gantt_idx * 40) % 360}, 70%, 50%)", width=2),
                name=lease_row['Tenant'],
                text=f"{lease_row['Area_SF']:,.0f} SF",
                textposition='middle center',
                hovertemplate=f"<b>{lease_row['Tenant']}</b><br>" +
                             f"Start: {lease_start.strftime('%Y-%m-%d')}<br>" +
                             f"End: {lease_end.strftime('%Y-%m-%d')}<br>" +
                             f"Area: {lease_row['Area_SF']:,.0f} SF<br>" +
                             f"Annual Rent: ${lease_row['Annual_Rent']:,.0f}<extra></extra>",
                showlegend=False
            ))
        
        # Use reasonable chart height
        chart_height = max(400, min(700, num_leases * 50 + 150))
        
        # Create y-axis tick positions at the center of each bar
        tick_positions = []
        tick_labels = []
        for i, (y_bottom, bar_height) in enumerate(y_positions):
            tick_positions.append(y_bottom + bar_height / 2)
            tick_labels.append(f"Lease {i + 1}")  # Chronological order (1st, 2nd, 3rd...)
        
        # Update layout for Gantt chart
        gantt_fig.update_layout(
            title=f"{building_title}<br><sub>Lease Terms & Duration Timeline (Bar Height = Square Footage)</sub>",
            xaxis_title="Timeline",
            yaxis_title="Leases (Chronological Order)",
            height=chart_height,
            yaxis=dict(
                tickmode='array',
                tickvals=tick_positions,
                ticktext=tick_labels,
                range=[-available_height * 0.05, available_height * 1.05],  # Add 5% padding top and bottom
                showgrid=False  # Remove grid lines for cleaner look with variable heights
            ),
            xaxis=dict(
                type='date'
            ),
            margin=dict(l=100),  # Less margin needed without long tenant names
        )
        
        gantt_output = gantt_fig
    
    gantt_output


@app.cell
def __(mo):
    """Section header for occupancy analysis"""
    mo.md(
        r"""
        ## 📈 Building Occupancy Progression
        
        Track how the building fills up over time:
        """
    )
    return


@app.cell
def __(timeline_df, total_vacant_sf, go, building_title, mo, pd, lease_term):
    """Create occupancy time series chart"""
    
    if timeline_df.empty:
        occupancy_output = mo.md("*No occupancy data to display*")
    else:
        # Create occupancy progression data
        occupancy_data = []
        chart_cumulative_occupied = 0
        
        # Calculate time domain to match Gantt chart (from first lease to last lease expiration)
        chart_first_lease_date = timeline_df['Lease_Date'].min()
        chart_last_lease_date = timeline_df['Lease_Date'].max()
        chart_last_lease_expiration = chart_last_lease_date + pd.DateOffset(months=lease_term.value)
        
        # Add starting point (0% occupancy) - a bit before first lease
        chart_start_date = chart_first_lease_date - pd.DateOffset(days=30)
        occupancy_data.append({
            'Date': chart_start_date,
            'Cumulative_SF': 0,
            'Occupancy_Pct': 0
        })
        
        # Add each lease signing
        for _, chart_row in timeline_df.sort_values('Lease_Date').iterrows():
            chart_cumulative_occupied += chart_row['Area_SF']
            chart_occupancy_pct = (chart_cumulative_occupied / total_vacant_sf) * 100
            
            occupancy_data.append({
                'Date': chart_row['Lease_Date'],
                'Cumulative_SF': chart_cumulative_occupied,
                'Occupancy_Pct': chart_occupancy_pct
            })
        
        # Add end point to extend chart to match Gantt timeline
        occupancy_data.append({
            'Date': chart_last_lease_expiration,
            'Cumulative_SF': chart_cumulative_occupied,
            'Occupancy_Pct': chart_occupancy_pct
        })
        
        occupancy_df = pd.DataFrame(occupancy_data)
        
        # Create occupancy chart
        occupancy_fig = go.Figure()
        
        occupancy_fig.add_trace(go.Scatter(
            x=occupancy_df['Date'],
            y=occupancy_df['Occupancy_Pct'],
            mode='lines+markers',
            name='Building Occupancy',
            line=dict(color='#2ecc71', width=4, shape='hv'),  # Green stepped line
            marker=dict(size=10, color='#2ecc71'),
            fill='tonexty',
            fillcolor='rgba(46, 204, 113, 0.1)',
            hovertemplate='<b>%{x}</b><br>Occupancy: %{y:.1f}%<br><extra></extra>'
        ))
        
        # Add milestone lines
        for milestone in [25, 50, 75, 100]:
            occupancy_fig.add_hline(
                y=milestone, 
                line_dash="dash", 
                line_color="gray", 
                annotation_text=f"{milestone}%",
                annotation_position="right"
            )
        
        occupancy_fig.update_layout(
            title=f"{building_title}<br><sub>Occupancy Progression Over Time</sub>",
            xaxis_title="Date",
            yaxis_title="Building Occupancy (%)",
            height=400,
            yaxis=dict(range=[0, 105], ticksuffix="%"),
            xaxis=dict(
                type='date',
                range=[chart_start_date, chart_last_lease_expiration]  # Match Gantt chart time domain
            ),
            showlegend=False
        )
        
        occupancy_output = occupancy_fig
    
    occupancy_output


@app.cell  
def __(mo):
    """Section header for occupancy milestones"""
    mo.md(
        r"""
        ## 🎯 Occupancy Milestones
        
        Key dates when building reaches major occupancy thresholds:
        """
    )
    return


@app.cell
def __(timeline_df, total_vacant_sf, mo, pd):
    """Create occupancy milestones table"""
    
    if timeline_df.empty:
        milestones_output = mo.md("*No milestone data to display*")
    else:
        # Calculate occupancy milestones
        milestones = []
        milestone_cumulative_occupied = 0
        
        milestone_sorted_leases = timeline_df.sort_values('Lease_Date')
        
        milestone_targets = [25, 50, 75, 100]
        milestone_idx = 0
        
        for _, milestone_row in milestone_sorted_leases.iterrows():
            milestone_cumulative_occupied += milestone_row['Area_SF']
            milestone_occupancy_pct = (milestone_cumulative_occupied / total_vacant_sf) * 100
            
            # Check if we've hit any milestones
            while milestone_idx < len(milestone_targets) and milestone_occupancy_pct >= milestone_targets[milestone_idx]:
                milestones.append({
                    'Milestone': f"{milestone_targets[milestone_idx]}% Occupied",
                    'Date': milestone_row['Lease_Date'].strftime('%Y-%m-%d'),
                    'Lease': milestone_row['Tenant'],
                    'Occupied_SF': f"{milestone_cumulative_occupied:,.0f}",
                    'Remaining_SF': f"{total_vacant_sf - milestone_cumulative_occupied:,.0f}"
                })
                milestone_idx += 1
        
        if milestones:
            milestones_output = mo.ui.table(
                data=milestones,
                selection=None,
                pagination=False
            )
        else:
            milestones_output = mo.md("*No occupancy milestones reached yet*")
    
    milestones_output


@app.cell
def __(mo):
    """Section header for detailed lease table"""
    mo.md(
        r"""
        ## 📋 Generated Lease Details
        
        Complete breakdown of each lease generated by the absorption plan:
        """
    )
    return


@app.cell
def __(timeline_df, mo):
    """Create detailed lease table"""
    
    if timeline_df.empty:
        table_output = mo.md("*No leases to display*")
    else:
        # Prepare table data
        table_data = []
        for table_idx, table_row in timeline_df.iterrows():
            table_data.append({
                "Lease Date": table_row['Lease_Date'].strftime('%Y-%m-%d'),
                "Tenant": table_row['Tenant'],
                "Suite": table_row['Suite'],
                "Area (SF)": f"{table_row['Area_SF']:,.0f}",
                "Annual Rent": f"${table_row['Annual_Rent']:,.0f}",
                "$/SF/Year": f"${table_row['Annual_Rent']/table_row['Area_SF']:.2f}",
                "Cumulative SF": f"{table_row['Cumulative_SF']:,.0f}"
            })
        
        table_output = mo.ui.table(
            data=table_data,
            selection=None,
            pagination=True,
            page_size=100
        )
    
    table_output


@app.cell  
def __(mo):
    """Section header for revenue analysis"""
    mo.md(
        r"""
        ## 💰 Revenue Analysis & Performance
        
        Financial summary of the absorption results:
        """
    )
    return


@app.cell
def __(timeline_df, mo, total_vacant_sf):
    """Create revenue analysis"""
    
    if timeline_df.empty:
        revenue_analysis = "No revenue to analyze"
    else:
        revenue_total_annual_rent = timeline_df['Annual_Rent'].sum()
        revenue_avg_rent_psf = revenue_total_annual_rent / timeline_df['Area_SF'].sum() if not timeline_df.empty else 0
        revenue_first_lease_date = timeline_df['Lease_Date'].min().strftime('%Y-%m-%d')
        revenue_last_lease_date = timeline_df['Lease_Date'].max().strftime('%Y-%m-%d')
        
        revenue_analysis = f"""
        ### 💰 Revenue Analysis
        
        - **Total Annual Rent**: ${revenue_total_annual_rent:,.0f}
        - **Average Rent**: ${revenue_avg_rent_psf:.2f}/SF/year
        - **First Lease**: {revenue_first_lease_date}
        - **Last Lease**: {revenue_last_lease_date}
        - **Leasing Period**: {(timeline_df['Lease_Date'].max() - timeline_df['Lease_Date'].min()).days} days
        - **Revenue per Occupied SF**: ${revenue_total_annual_rent/timeline_df['Area_SF'].sum():.0f}/SF/year
        """
    
    mo.md(revenue_analysis)
    return


@app.cell
def __(mo, pace_strategy):
    """Educational content about absorption strategies"""
    
    if "Fixed Quantity" in pace_strategy.value:
        mo.md("""
        ### 🎯 Fixed Quantity Strategy
        **Perfect for**: Controlled, predictable lease-up
        - Maintains consistent leasing velocity
        - Predictable cash flow ramp-up  
        - Good for buildings with steady market demand
        - Allows subdivision of large floor plates into right-sized tenants
        - Real estate teams can plan marketing efforts around fixed targets
        """)
    else:
        mo.md("""
        ### 📈 Equal Spread Strategy  
        **Perfect for**: Time-constrained lease-up
        - Spreads leasing evenly over specified period
        - Front-loads effort for faster stabilization
        - Good for competitive markets or financing requirements
        - Creates urgency in leasing teams
        - Useful when construction completion drives lease-up timing
        """)
    
    return


@app.cell
def __(mo):
    """Technical details and next steps"""
    mo.md(
        r"""
        ---
        
        ## 🔧 How This Works Behind the Scenes
        
        **Subdivision Logic**: Large floor plates automatically subdivide into right-sized leases based on:
        - Average lease size preferences (adjustable via slider)
        - Minimum viable lease size (calculated as 1/3 of average)
        - Remaining available space in each period
        
        **Realistic Tenant Names**: Generated leases get unique tenant identifiers following the pattern:
        `{Plan Name}-Deal{Number}-{Suite}` for traceability.
        
        **Visual Encoding**: The Gantt chart uses multiple dimensions to show lease information:
        - Horizontal position: Lease start and end dates
        - Bar height: Square footage (larger leases = taller bars)
        - Color: Unique identifier for each lease
        
        **Market Assumptions**: Each generated lease uses the market terms you specified, but Performa can also model:
        - Varying rent rates by floor, size, or timing
        - Different lease terms and escalations
        - Tenant improvement allowances and leasing commissions
        
        ---
        
        ## 🚀 Next Steps
        
        This absorption output feeds directly into Performa's cash flow analysis engine. The generated lease specs become the foundation for:
        
        - **Monthly cash flow projections**
        - **Development project analysis** 
        - **Investment underwriting**
        - **Sensitivity analysis** on leasing assumptions
        
        *Try adjusting the parameters above to see how different strategies affect your building's lease-up!*
        """
    )
    return


if __name__ == "__main__":
    app.run() 