import streamlit as st
import pandas as pd
import numpy as np
import pvlib
from pvlib.location import Location
from geopy.geocoders import Nominatim
import plotly.graph_objects as go
from io import BytesIO
from datetime import datetime

# --- 1. Page Configuration ---
st.set_page_config(page_title="Solar Engineering Dashboard", layout="wide")
st.title("☀️ Professional Solar Design & Analysis Dashboard")

# --- 2. Initialize Session State ---
if 'location' not in st.session_state:
    st.session_state.location = None
    st.session_state.last_address = None
    st.session_state.location_name = None

# Scenario comparison state
if 'scenarios' not in st.session_state:
    st.session_state.scenarios = {}
if 'comparison_mode' not in st.session_state:
    st.session_state.comparison_mode = False

# --- 3. Sidebar: Precise Inputs ---
with st.sidebar:
    st.header("📍 Site Selection")
    address = st.text_input("Site Address", value="Seville, Spain")
    
    # Geocoding with proper error handling and caching
    if address != st.session_state.last_address:
        geolocator = Nominatim(user_agent="solar_dash_v11")
        try:
            with st.spinner("🔍 Looking up location..."):
                location_data = geolocator.geocode(address, timeout=10)
                if location_data:
                    lat, lon = location_data.latitude, location_data.longitude
                    st.session_state.location = (lat, lon)
                    st.session_state.last_address = address
                    st.session_state.location_name = location_data.address
                    st.success(f"✓ Found: {location_data.address}")
                else:
                    st.warning("⚠️ Address not found. Using default: Seville, Spain")
                    lat, lon = 37.38, -5.98
                    st.session_state.location = (lat, lon)
                    st.session_state.last_address = address
                    st.session_state.location_name = "Seville, Spain (default)"
        except Exception as e:
            st.error(f"❌ Location lookup failed: {str(e)}")
            st.info("Using default location: Seville, Spain")
            lat, lon = 37.38, -5.98
            st.session_state.location = (lat, lon)
            st.session_state.last_address = address
            st.session_state.location_name = "Seville, Spain (default)"
    else:
        lat, lon = st.session_state.location
    
    # Display coordinates for verification
    st.caption(f"📍 Coordinates: {lat:.4f}°, {lon:.4f}°")
    if st.session_state.location_name:
        st.caption(f"📌 {st.session_state.location_name}")
    
    st.markdown("---")
    
    st.header("🔆 Array Orientation")
    tilt = st.number_input(
        "Tilt Angle (°)", 
        0, 90, 
        value=int(abs(lat)), 
        help="Optimal tilt ≈ latitude. 0° = horizontal, 90° = vertical"
    )
    azimuth = st.number_input(
        "Azimuth (°)", 
        0, 360, 
        value=180,
        help="0° = North, 90° = East, 180° = South, 270° = West"
    )
    
    st.markdown("---")
    
    st.header("🔌 System Design")
    p_mp_stc = st.number_input(
        "Module Wp (STC)", 
        value=550.0, 
        min_value=100.0, 
        max_value=800.0,
        step=10.0,
        help="Typical range: 400-700W"
    )
    n_series = st.number_input(
        "Modules per String", 
        value=18, 
        min_value=1, 
        max_value=50,
        help="Limited by inverter voltage window"
    )
    n_parallel = st.number_input(
        "Total Strings", 
        value=100, 
        min_value=1, 
        max_value=10000,
        help="Total number of parallel strings"
    )
    
    total_dc_kw = (n_series * n_parallel * p_mp_stc) / 1000
    st.info(f"**Total DC Capacity:** {total_dc_kw:,.2f} kWp")
    
    num_inv = st.number_input(
        "No. of Inverters", 
        value=4, 
        min_value=1, 
        max_value=100
    )
    inv_rating = st.number_input(
        "AC Rating per Inv (kW)", 
        value=200.0, 
        min_value=1.0, 
        max_value=5000.0,
        step=10.0
    )
    inv_efficiency = st.number_input(
        "Inverter Efficiency (%)",
        value=98.0,
        min_value=90.0,
        max_value=99.5,
        step=0.1,
        help="Typical range: 96-99%"
    ) / 100
    
    total_ac_kw = num_inv * inv_rating
    st.info(f"**Total AC Capacity:** {total_ac_kw:,.2f} kWac")
    
    dc_ac_ratio = total_dc_kw / total_ac_kw if total_ac_kw > 0 else 0
    st.metric("DC/AC Ratio", f"{dc_ac_ratio:.2f}")
    
    # DC/AC ratio validation
    if dc_ac_ratio > 2.0:
        st.warning("⚠️ DC/AC ratio > 2.0 may cause excessive clipping losses")
    elif dc_ac_ratio < 1.0:
        st.warning("⚠️ DC/AC ratio < 1.0 means undersized array relative to inverter")
    elif 1.1 <= dc_ac_ratio <= 1.4:
        st.success("✓ DC/AC ratio is in optimal range (1.1-1.4)")
    
    st.markdown("---")
    
    st.header("🏗️ Installation & Losses")
    # Logic: Open Rack vs Roof Mount
    mount_type = st.selectbox(
        "Mounting Type", 
        ["Open Rack", "Roof Mounted/Insulated"],
        help="Affects module operating temperature"
    )
    
    soiling_loss = st.number_input(
        "Soiling Loss (%)", 
        value=2.0, 
        min_value=0.0, 
        max_value=20.0,
        step=0.5,
        help="Typical: 2-5% depending on climate and cleaning frequency"
    ) / 100
    dc_loss = st.number_input(
        "DC Wiring/Mismatch Loss (%)", 
        value=3.0, 
        min_value=0.0, 
        max_value=10.0,
        step=0.5,
        help="Typical: 2-4%"
    ) / 100
    ac_loss = st.number_input(
        "AC Wiring/Transf. Loss (%)", 
        value=1.5, 
        min_value=0.0, 
        max_value=10.0,
        step=0.5,
        help="Typical: 1-3%"
    ) / 100
    avail_loss = st.number_input(
        "System Unavailability (%)", 
        value=1.0, 
        min_value=0.0, 
        max_value=10.0,
        step=0.5,
        help="Downtime due to maintenance, grid outages, etc."
    ) / 100
    
    st.markdown("---")
    
    st.header("📊 Analysis Period")
    years = st.number_input(
        "Analysis Period (Years)", 
        value=25, 
        min_value=1, 
        max_value=40,
        help="Typical PV system lifetime: 25-30 years"
    )
    deg_rate = st.number_input(
        "Annual Degradation (%)", 
        value=0.5, 
        min_value=0.0, 
        max_value=2.0,
        step=0.1,
        help="Typical: 0.4-0.8% per year"
    ) / 100
    
    st.markdown("---")
    
    # Scenario Comparison
    st.header("📊 Scenario Comparison")
    
    # Save current scenario button
    scenario_name = st.text_input("Scenario Name", value=f"Scenario {len(st.session_state.scenarios) + 1}")
    
    if st.button("💾 Save Current Scenario", use_container_width=True):
        st.session_state.scenarios[scenario_name] = {
            'location': st.session_state.location_name,
            'lat': lat,
            'lon': lon,
            'tilt': tilt,
            'azimuth': azimuth,
            'p_mp_stc': p_mp_stc,
            'n_series': n_series,
            'n_parallel': n_parallel,
            'total_dc_kw': total_dc_kw,
            'num_inv': num_inv,
            'inv_rating': inv_rating,
            'inv_efficiency': inv_efficiency,
            'total_ac_kw': total_ac_kw,
            'dc_ac_ratio': dc_ac_ratio,
            'mount_type': mount_type,
            'soiling_loss': soiling_loss,
            'dc_loss': dc_loss,
            'ac_loss': ac_loss,
            'avail_loss': avail_loss,
            'years': years,
            'deg_rate': deg_rate
        }
        st.success(f"✓ Saved '{scenario_name}'!")
    
    # Show saved scenarios
    if st.session_state.scenarios:
        st.caption(f"Saved Scenarios: {len(st.session_state.scenarios)}")
        for name in st.session_state.scenarios.keys():
            st.caption(f"• {name}")
        
        # Comparison mode toggle
        st.session_state.comparison_mode = st.checkbox(
            "🔄 Enable Comparison Mode",
            value=st.session_state.comparison_mode,
            help="Compare current scenario with saved scenarios"
        )
        
        if st.session_state.comparison_mode:
            selected_scenario = st.selectbox(
                "Compare with:",
                options=list(st.session_state.scenarios.keys())
            )
            st.session_state.selected_comparison = selected_scenario
        
        # Clear scenarios button
        if st.button("🗑️ Clear All Scenarios", use_container_width=True):
            st.session_state.scenarios = {}
            st.session_state.comparison_mode = False
            st.rerun()

# --- 4. Simulation Engine with Error Handling ---
@st.cache_data(show_spinner=False)
def run_full_sim(lat, lon, dc_kw, ac_limit, losses, mount, tilt_angle, azimuth_angle, inv_eff):
    """
    Run full PV simulation with comprehensive error handling
    
    Returns:
        tuple: (weather, irrad, ac_power, temp_cell) or (None, None, None, None) on error
    """
    try:
        # Fetch TMY weather data with timeout
        weather, metadata = pvlib.iotools.get_pvgis_tmy(
            lat, 
            lon, 
            map_variables=True, 
            url='https://re.jrc.ec.europa.eu/api/v5_3/',
            timeout=30
        )
        
        # Create location object
        site = Location(lat, lon)
        
        # Calculate solar position
        solpos = site.get_solarposition(weather.index)
        
        # Calculate plane-of-array irradiance
        irrad = pvlib.irradiance.get_total_irradiance(
            tilt_angle, 
            azimuth_angle, 
            solpos['zenith'], 
            solpos['azimuth'], 
            weather['dni'], 
            weather['ghi'], 
            weather['dhi']
        )
        
        # Temperature modeling based on mounting type
        if mount == "Open Rack":
            temp_params = pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS['sapm']['open_rack_glass_glass']
        else:
            temp_params = pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS['sapm']['insulated_back_glass_polymer']
            
        temp_cell = pvlib.temperature.sapm_cell(
            irrad['poa_global'], 
            weather['temp_air'], 
            weather['wind_speed'], 
            **temp_params
        )
        
        # DC power calculation with temperature coefficient
        dc_raw = (irrad['poa_global'] / 1000) * dc_kw * (1 - 0.004 * (temp_cell - 25))
        
        # Apply losses
        dc_net = dc_raw * (1 - losses['soiling']) * (1 - losses['dc'])
        
        # Inverter conversion with efficiency and clipping
        ac_power = (dc_net * inv_eff).clip(upper=ac_limit)
        
        # Apply AC losses and availability
        ac_final = ac_power * (1 - losses['ac']) * (1 - losses['avail'])
        
        return weather, irrad, ac_final, temp_cell
        
    except Exception as e:
        # Return None values to signal error
        return None, None, None, None, str(e)

# --- 5. Run Simulation ---
losses_dict = {
    'soiling': soiling_loss, 
    'dc': dc_loss, 
    'ac': ac_loss, 
    'avail': avail_loss
}

with st.spinner("🔄 Running PV simulation..."):
    result = run_full_sim(
        lat, lon, 
        total_dc_kw, 
        total_ac_kw, 
        losses_dict, 
        mount_type,
        tilt,
        azimuth,
        inv_efficiency
    )
    
    # Check for simulation errors
    if result[0] is None:
        error_msg = result[4] if len(result) > 4 else "Unknown error"
        st.error(f"❌ Simulation Failed: {error_msg}")
        st.info("💡 Troubleshooting tips:")
        st.markdown("""
        - Check your internet connection
        - Try a different location
        - Verify coordinates are valid (latitude: -90 to 90, longitude: -180 to 180)
        - The PVGIS API may be temporarily unavailable
        """)
        st.stop()
    
    weather, irrad, ac_power, temp_cell = result

# --- Run Comparison Scenario if enabled ---
comparison_results = None
if st.session_state.comparison_mode and 'selected_comparison' in st.session_state:
    comp_scenario = st.session_state.scenarios[st.session_state.selected_comparison]
    
    with st.spinner(f"🔄 Running comparison scenario: {st.session_state.selected_comparison}..."):
        comp_losses = {
            'soiling': comp_scenario['soiling_loss'],
            'dc': comp_scenario['dc_loss'],
            'ac': comp_scenario['ac_loss'],
            'avail': comp_scenario['avail_loss']
        }
        
        comp_result = run_full_sim(
            comp_scenario['lat'], comp_scenario['lon'],
            comp_scenario['total_dc_kw'], comp_scenario['total_ac_kw'],
            comp_losses, comp_scenario['mount_type'],
            comp_scenario['tilt'], comp_scenario['azimuth'],
            comp_scenario['inv_efficiency']
        )
        
        if comp_result[0] is not None:
            comp_weather, comp_irrad, comp_ac_power, comp_temp_cell = comp_result
            
            # Calculate comparison KPIs
            comp_total_poa = comp_irrad['poa_global'].sum() / 1000
            comp_y1_yield = comp_ac_power.sum()
            comp_pr_val = (comp_y1_yield / (comp_total_poa * comp_scenario['total_dc_kw'])) * 100 if (comp_total_poa * comp_scenario['total_dc_kw']) > 0 else 0
            
            # Monthly data for comparison
            comp_df_m = pd.DataFrame({
                'GHI': comp_weather['ghi'],
                'POA': comp_irrad['poa_global'],
                'Energy': comp_ac_power
            }).resample('M').sum()
            comp_df_m['Month'] = comp_df_m.index.strftime('%b')
            comp_df_m['Energy_MWh'] = comp_df_m['Energy'] / 1000
            
            comparison_results = {
                'scenario': comp_scenario,
                'total_poa': comp_total_poa,
                'y1_yield': comp_y1_yield,
                'pr_val': comp_pr_val,
                'df_m': comp_df_m,
                'name': st.session_state.selected_comparison
            }

# --- 6. Main Dashboard ---
st.success("✓ Simulation complete!")

# KPI Row
total_poa = irrad['poa_global'].sum() / 1000
y1_yield = ac_power.sum()
pr_val = (y1_yield / (total_poa * total_dc_kw)) * 100 if (total_poa * total_dc_kw) > 0 else 0

# Display KPIs based on comparison mode
if comparison_results:
    st.subheader("📊 Scenario Comparison")
    
    # Create two columns for side-by-side comparison
    col_current, col_comp = st.columns(2)
    
    with col_current:
        st.markdown(f"### 🔵 Current Scenario")
        k1, k2 = st.columns(2)
        k1.metric("1st Year Yield", f"{y1_yield/1000:,.1f} MWh")
        k2.metric("Specific Yield", f"{y1_yield/total_dc_kw:,.0f} kWh/kWp")
        k3, k4 = st.columns(2)
        k3.metric("Performance Ratio", f"{pr_val:.1f}%")
        k4.metric("Annual POA", f"{total_poa:,.1f} kWh/m²")
        
        st.caption(f"**DC Capacity:** {total_dc_kw:,.1f} kWp | **AC Capacity:** {total_ac_kw:,.1f} kWac")
        st.caption(f"**Location:** {st.session_state.location_name}")
        st.caption(f"**Tilt/Azimuth:** {tilt}° / {azimuth}°")
    
    with col_comp:
        st.markdown(f"### 🟢 {comparison_results['name']}")
        comp_scenario = comparison_results['scenario']
        comp_y1_yield = comparison_results['y1_yield']
        comp_total_poa = comparison_results['total_poa']
        comp_pr_val = comparison_results['pr_val']
        
        k1, k2 = st.columns(2)
        yield_diff = ((comp_y1_yield - y1_yield) / y1_yield) * 100
        k1.metric(
            "1st Year Yield", 
            f"{comp_y1_yield/1000:,.1f} MWh",
            delta=f"{yield_diff:+.1f}%"
        )
        spec_yield = comp_y1_yield / comp_scenario['total_dc_kw']
        spec_diff = ((spec_yield - (y1_yield/total_dc_kw)) / (y1_yield/total_dc_kw)) * 100
        k2.metric(
            "Specific Yield", 
            f"{spec_yield:,.0f} kWh/kWp",
            delta=f"{spec_diff:+.1f}%"
        )
        
        k3, k4 = st.columns(2)
        pr_diff = comp_pr_val - pr_val
        k3.metric(
            "Performance Ratio", 
            f"{comp_pr_val:.1f}%",
            delta=f"{pr_diff:+.1f}%"
        )
        poa_diff = ((comp_total_poa - total_poa) / total_poa) * 100
        k4.metric(
            "Annual POA", 
            f"{comp_total_poa:,.1f} kWh/m²",
            delta=f"{poa_diff:+.1f}%"
        )
        
        st.caption(f"**DC Capacity:** {comp_scenario['total_dc_kw']:,.1f} kWp | **AC Capacity:** {comp_scenario['total_ac_kw']:,.1f} kWac")
        st.caption(f"**Location:** {comp_scenario['location']}")
        st.caption(f"**Tilt/Azimuth:** {comp_scenario['tilt']}° / {comp_scenario['azimuth']}°")
    
    # Summary comparison
    st.markdown("---")
    st.subheader("💰 Financial Comparison")
    
    fin_col1, fin_col2, fin_col3 = st.columns(3)
    
    with fin_col1:
        st.metric("Annual Energy Difference", 
                  f"{(comp_y1_yield - y1_yield)/1000:+,.1f} MWh",
                  delta=f"{yield_diff:+.1f}%")
    
    with fin_col2:
        # Simple NPV calculation (assuming electricity price)
        electricity_price = 0.12  # $/kWh - you can make this configurable
        annual_revenue_diff = ((comp_y1_yield - y1_yield) * electricity_price)
        st.metric("Annual Revenue Difference", 
                  f"${annual_revenue_diff:+,.0f}",
                  help=f"Based on ${electricity_price}/kWh")
    
    with fin_col3:
        # 25-year NPV difference (simple calculation without degradation for now)
        npv_diff = annual_revenue_diff * years
        st.metric(f"{int(years)}-Year Revenue Difference", 
                  f"${npv_diff:+,.0f}",
                  help="Simple calculation without discounting")
    
    st.markdown("---")
    
else:
    # Standard single scenario display
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("1st Year Yield", f"{y1_yield/1000:,.1f} MWh")
    k2.metric("Specific Yield", f"{y1_yield/total_dc_kw:,.0f} kWh/kWp")
    k3.metric("Avg PR (%)", f"{pr_val:.1f}%")
    k4.metric("Annual POA", f"{total_poa:,.1f} kWh/m²")

st.markdown("---")

# Data Processing for Charts
df_m = pd.DataFrame({
    'GHI': weather['ghi'],
    'POA': irrad['poa_global'],
    'Energy': ac_power
}).resample('M').sum()

df_m['Month'] = df_m.index.strftime('%b') 
df_m['GHI_kWh'] = df_m['GHI'] / 1000
df_m['POA_kWh'] = df_m['POA'] / 1000
df_m['Energy_MWh'] = df_m['Energy'] / 1000
df_m['PR'] = (df_m['Energy'] / ((df_m['POA']/1000) * total_dc_kw)) * 100

# --- 7. Export Functions ---
def create_monthly_csv():
    """Create CSV export of monthly data"""
    export_df = df_m[['Month', 'GHI_kWh', 'POA_kWh', 'Energy_MWh', 'PR']].copy()
    export_df.columns = ['Month', 'GHI_kWh_m2', 'POA_kWh_m2', 'Energy_MWh', 'PR_%']
    
    # Add summary info as header comments
    header_info = f"""# Solar Analysis Export - {datetime.now().strftime("%Y-%m-%d %H:%M")}
# Location: {st.session_state.location_name or 'Unknown'}
# DC Capacity: {total_dc_kw:.2f} kWp
# AC Capacity: {total_ac_kw:.2f} kWac
# First Year Yield: {y1_yield/1000:.2f} MWh
# Performance Ratio: {pr_val:.2f}%
#
"""
    csv_string = header_info + export_df.to_csv(index=False)
    return csv_string

def create_hourly_csv():
    """Create CSV export of hourly TMY data"""
    # Create hourly dataframe with all relevant data
    df_hourly = pd.DataFrame({
        'Timestamp': weather.index,
        'GHI_W_m2': weather['ghi'],
        'DNI_W_m2': weather['dni'],
        'DHI_W_m2': weather['dhi'],
        'POA_W_m2': irrad['poa_global'],
        'Temp_Air_C': weather['temp_air'],
        'Wind_Speed_m_s': weather['wind_speed'],
        'Temp_Cell_C': temp_cell,
        'AC_Power_kW': ac_power
    })
    
    # Add summary info as header comments
    header_info = f"""# Solar Analysis Hourly Export - {datetime.now().strftime("%Y-%m-%d %H:%M")}
# Location: {st.session_state.location_name or 'Unknown'}
# Coordinates: {lat:.4f}, {lon:.4f}
# DC Capacity: {total_dc_kw:.2f} kWp
# AC Capacity: {total_ac_kw:.2f} kWac
# Tilt: {tilt}°, Azimuth: {azimuth}°
# TMY (Typical Meteorological Year) - 8760 hourly values
#
"""
    csv_string = header_info + df_hourly.to_csv(index=False)
    return csv_string

# --- 8. Export Section ---
st.subheader("📥 Export Results")
col_exp1, col_exp2 = st.columns(2)

with col_exp1:
    monthly_csv = create_monthly_csv()
    st.download_button(
        label="📄 Download Monthly Data (CSV)",
        data=monthly_csv,
        file_name=f"solar_monthly_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
        use_container_width=True,
        help="Download monthly aggregated data (12 rows)"
    )

with col_exp2:
    hourly_csv = create_hourly_csv()
    st.download_button(
        label="📊 Download Hourly TMY Data (CSV)",
        data=hourly_csv,
        file_name=f"solar_hourly_tmy_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
        use_container_width=True,
        help="Download complete hourly data for the year (8760 rows)"
    )

st.markdown("---")

# --- 9. Charts ---
g_col1, g_col2 = st.columns(2)

with g_col1:
    fig_irrad = go.Figure()
    fig_irrad.add_trace(go.Bar(
        x=df_m['Month'], 
        y=df_m['GHI_kWh'], 
        name="GHI (Horizontal)",
        marker_color='lightblue'
    ))
    fig_irrad.add_trace(go.Scatter(
        x=df_m['Month'], 
        y=df_m['POA_kWh'], 
        name="POA (In-Plane)", 
        line=dict(color='orange', width=3),
        mode='lines+markers'
    ))
    fig_irrad.update_layout(
        title="Monthly Irradiation (kWh/m²)", 
        barmode='group', 
        legend=dict(orientation="h", y=1.1),
        hovermode='x unified'
    )
    st.plotly_chart(fig_irrad, use_container_width=True)

with g_col2:
    fig_gen = go.Figure()
    fig_gen.add_trace(go.Bar(
        x=df_m['Month'], 
        y=df_m['Energy_MWh'], 
        name="Energy (MWh)", 
        yaxis='y1',
        marker_color='green'
    ))
    fig_gen.add_trace(go.Scatter(
        x=df_m['Month'], 
        y=df_m['PR'], 
        name="PR (%)", 
        yaxis='y2', 
        line=dict(color='red', width=3),
        mode='lines+markers'
    ))
    fig_gen.update_layout(
        title="Energy Generation & PR (%)",
        yaxis=dict(title="Energy (MWh)"),
        yaxis2=dict(title="PR (%)", overlaying='y', side='right', range=[0, 100]),
        legend=dict(orientation="h", y=1.1),
        hovermode='x unified'
    )
    st.plotly_chart(fig_gen, use_container_width=True)

st.markdown("---")

# --- Comparison Charts (if in comparison mode) ---
if comparison_results:
    st.subheader("📊 Side-by-Side Energy Comparison")
    
    comp_col1, comp_col2 = st.columns(2)
    
    with comp_col1:
        st.markdown("#### 🔵 Current Scenario - Monthly Energy")
        fig_comp1 = go.Figure()
        fig_comp1.add_trace(go.Bar(
            x=df_m['Month'],
            y=df_m['Energy_MWh'],
            name="Current",
            marker_color='#4299E1'
        ))
        fig_comp1.update_layout(
            yaxis_title="Energy (MWh)",
            hovermode='x unified',
            height=300
        )
        st.plotly_chart(fig_comp1, use_container_width=True)
    
    with comp_col2:
        st.markdown(f"#### 🟢 {comparison_results['name']} - Monthly Energy")
        fig_comp2 = go.Figure()
        fig_comp2.add_trace(go.Bar(
            x=comparison_results['df_m']['Month'],
            y=comparison_results['df_m']['Energy_MWh'],
            name=comparison_results['name'],
            marker_color='#48BB78'
        ))
        fig_comp2.update_layout(
            yaxis_title="Energy (MWh)",
            hovermode='x unified',
            height=300
        )
        st.plotly_chart(fig_comp2, use_container_width=True)
    
    # Combined comparison chart
    st.markdown("#### 📊 Direct Comparison")
    fig_combined = go.Figure()
    fig_combined.add_trace(go.Bar(
        x=df_m['Month'],
        y=df_m['Energy_MWh'],
        name="Current Scenario",
        marker_color='#4299E1'
    ))
    fig_combined.add_trace(go.Bar(
        x=comparison_results['df_m']['Month'],
        y=comparison_results['df_m']['Energy_MWh'],
        name=comparison_results['name'],
        marker_color='#48BB78'
    ))
    fig_combined.update_layout(
        barmode='group',
        yaxis_title="Energy (MWh)",
        xaxis_title="Month",
        hovermode='x unified',
        legend=dict(orientation="h", y=1.1)
    )
    st.plotly_chart(fig_combined, use_container_width=True)
    
    # Difference chart
    st.markdown("#### 📈 Monthly Energy Difference")
    energy_diff = comparison_results['df_m']['Energy_MWh'].values - df_m['Energy_MWh'].values
    colors = ['green' if x > 0 else 'red' for x in energy_diff]
    
    fig_diff = go.Figure()
    fig_diff.add_trace(go.Bar(
        x=df_m['Month'],
        y=energy_diff,
        marker_color=colors,
        text=[f"{x:+.2f}" for x in energy_diff],
        textposition='outside'
    ))
    fig_diff.update_layout(
        yaxis_title="Energy Difference (MWh)",
        xaxis_title="Month",
        hovermode='x unified'
    )
    fig_diff.add_hline(y=0, line_dash="dash", line_color="gray")
    st.plotly_chart(fig_diff, use_container_width=True)
    
    st.markdown("---")

# --- Regular Waterfall and Degradation Charts ---
w_col1, w_col2 = st.columns(2)

with w_col1:
    # Waterfall with explicit DC and AC losses
    theo_mwh = (total_poa * total_dc_kw) / 1000
    loss_temp = theo_mwh * 0.08  # Approximate temperature loss
    loss_soil = (theo_mwh - loss_temp) * soiling_loss
    loss_dc = (theo_mwh - loss_temp - loss_soil) * dc_loss
    loss_inv = (theo_mwh - loss_temp - loss_soil - loss_dc) * (1 - inv_efficiency)
    loss_ac = (y1_yield / 1000) / (1 - ac_loss) * ac_loss
    loss_avail = (y1_yield / 1000) / (1 - avail_loss) * avail_loss
    
    fig_water = go.Figure(go.Waterfall(
        measure = ["absolute", "relative", "relative", "relative", "relative", "relative", "relative", "total"],
        x = ["Theoretical", "Temp Loss", "Soiling", "DC Loss", "Inverter", "AC Loss", "Unavailability", "Net Yield"],
        y = [theo_mwh, -loss_temp, -loss_soil, -loss_dc, -loss_inv, -loss_ac, -loss_avail, 0],
        totals = {"marker": {"color": "green"}},
        decreasing = {"marker": {"color": "salmon"}},
        text = [f"{v:.1f}" for v in [theo_mwh, -loss_temp, -loss_soil, -loss_dc, -loss_inv, -loss_ac, -loss_avail, y1_yield/1000]],
        textposition = "outside"
    ))
    fig_water.update_layout(
        title="Annual Loss Breakdown (MWh)",
        showlegend=False
    )
    st.plotly_chart(fig_water, use_container_width=True)

with w_col2:
    y_list = list(range(1, int(years) + 1))
    deg_data = [(y1_yield/1000) * (1 - deg_rate)**y for y in range(len(y_list))]
    
    fig_deg = go.Figure()
    fig_deg.add_trace(go.Scatter(
        x=y_list, 
        y=deg_data, 
        fill='tozeroy', 
        name="Annual Energy",
        line=dict(color='royalblue'),
        mode='lines'
    ))
    fig_deg.update_layout(
        title=f"{years}-Year Degradation Forecast", 
        xaxis_title="Year", 
        yaxis_title="Annual Energy (MWh)",
        hovermode='x'
    )
    
    # Add cumulative total as annotation
    cumulative_mwh = sum(deg_data)
    fig_deg.add_annotation(
        text=f"Cumulative: {cumulative_mwh:,.0f} MWh",
        xref="paper", yref="paper",
        x=0.95, y=0.95,
        showarrow=False,
        bordercolor="black",
        borderwidth=1
    )
    
    st.plotly_chart(fig_deg, use_container_width=True)

# --- 10. Additional System Info ---
with st.expander("📋 Detailed System Information"):
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.subheader("Array Configuration")
        st.write(f"**Total Modules:** {n_series * n_parallel:,}")
        st.write(f"**String Configuration:** {n_series}S × {n_parallel}P")
        st.write(f"**Module Power:** {p_mp_stc:.0f} Wp")
        st.write(f"**Array Tilt:** {tilt}°")
        st.write(f"**Array Azimuth:** {azimuth}°")
    
    with col2:
        st.subheader("Inverter Configuration")
        st.write(f"**Number of Inverters:** {num_inv}")
        st.write(f"**Inverter Rating:** {inv_rating:.0f} kW")
        st.write(f"**Inverter Efficiency:** {inv_efficiency*100:.1f}%")
        st.write(f"**DC/AC Ratio:** {dc_ac_ratio:.2f}")
        st.write(f"**Total AC Power:** {total_ac_kw:,.0f} kWac")
    
    with col3:
        st.subheader("Environmental")
        st.write(f"**Location:** {st.session_state.location_name or 'Unknown'}")
        st.write(f"**Coordinates:** {lat:.4f}°, {lon:.4f}°")
        st.write(f"**Mounting:** {mount_type}")
        avg_temp = weather['temp_air'].mean()
        max_temp = weather['temp_air'].max()
        st.write(f"**Avg Temp:** {avg_temp:.1f}°C")
        st.write(f"**Max Temp:** {max_temp:.1f}°C")

# --- 11. Footer ---
st.markdown("---")
st.caption(f"⚡ Solar Engineering Dashboard | Powered by pvlib & PVGIS | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")