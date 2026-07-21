import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="HDB Analytics Portfolio", page_icon="🏢", layout="wide")
load_dotenv()

# --- 2. DATABASE CONNECTION & DATA CACHING ---
# We use @st.cache_data so the dashboard doesn't re-query the database every time you click a button
@st.cache_data
def load_data(query):
    PG_PASSWORD = os.getenv("PG_PASSWORD", "your_password_here")
    DATABASE_URI = f"postgresql://postgres:{PG_PASSWORD}@localhost:5432/hdb_portfolio"
    engine = create_engine(DATABASE_URI)
    
    with engine.connect() as conn:
        df = pd.DataFrame(conn.execute(text(query)).fetchall())
        df.columns = conn.execute(text(query)).keys()
    return df

# --- 3. HEADER & INTRO ---
st.title("🏢 Singapore HDB Pricing Engine: Beyond the Averages")
st.markdown("""
    *An end-to-end data pipeline built by Teo Shao En Wright.* This dashboard queries a local PostgreSQL Data Warehouse to analyze the impact of spatial geography, school proximity, and government lease policies on HDB resale prices.
""")
st.divider()

# --- 4. THE ELITE SCHOOL PREMIUM ---
st.header("1. The Elite Primary School Premium")
st.markdown("How much extra do buyers pay to be within the 1km priority registration zone of a Top 20 primary school?")

query_school = """
    SELECT 
        CASE WHEN within_1km_elite_school = 1 THEN 'Within 1km' ELSE 'Outside 1km' END AS zone,
        ROUND(AVG(resale_price / floor_area_sqm)) AS avg_psf
    FROM silver_hdb_features
    GROUP BY within_1km_elite_school
    ORDER BY within_1km_elite_school DESC;
"""
df_school = load_data(query_school)

col1, col2 = st.columns([1, 2])

with col1:
    premium_val = df_school.loc[df_school['zone'] == 'Within 1km', 'avg_psf'].values[0]
    standard_val = df_school.loc[df_school['zone'] == 'Outside 1km', 'avg_psf'].values[0]
    difference = premium_val - standard_val
    
    st.metric(label="Elite Zone (Per Sqm)", value=f"${premium_val:,.0f}", delta=f"+${difference:,.0f} vs Standard")
    st.metric(label="Standard Zone (Per Sqm)", value=f"${standard_val:,.0f}")

with col2:
    st.bar_chart(df_school.set_index('zone')['avg_psf'])

st.divider()

# --- 5. THE LEASE DECAY MATRIX (BALA'S CURVE) ---
st.header("2. Policy Impact: CPF Restrictions & Lease Decay")
st.markdown("When flats drop below 60 years of remaining lease, CPF usage restrictions trigger a sharp drop in valuation. Use the filters below to explore this impact across different flat sizes.")

query_lease = """
    SELECT 
        flat_type,
        estate_maturity,
        lease_critical_status,
        ROUND(AVG(resale_price / floor_area_sqm)) AS avg_psf
    FROM silver_hdb_features
    WHERE flat_type IN ('3 ROOM', '4 ROOM', '5 ROOM')
    GROUP BY flat_type, estate_maturity, lease_critical_status
    ORDER BY flat_type, estate_maturity, avg_psf DESC;
"""
df_lease = load_data(query_lease)

# --- INTERACTIVE FILTERS ---
filter_col1, filter_col2 = st.columns(2)

with filter_col1:
    selected_flat = st.selectbox("Select Flat Type:", options=['3 ROOM', '4 ROOM', '5 ROOM'])

with filter_col2:
    selected_maturity = st.radio("Select Estate Maturity:", options=['Mature', 'Non-Mature'], horizontal=True)

# Filter the dataframe based on the user's selections
filtered_lease = df_lease[
    (df_lease['flat_type'] == selected_flat) & 
    (df_lease['estate_maturity'] == selected_maturity)
]

# --- VISUALIZATION ---
# Display the metric drop clearly
safe_val = filtered_lease.loc[filtered_lease['lease_critical_status'] == 'Safe (60+ yrs)', 'avg_psf'].values
restricted_val = filtered_lease.loc[filtered_lease['lease_critical_status'] == 'Restricted (<60 yrs)', 'avg_psf'].values

if len(safe_val) > 0 and len(restricted_val) > 0:
    st.subheader(f"Price Drop for {selected_flat} in {selected_maturity} Estates")
    colA, colB = st.columns(2)
    colA.metric("Safe Lease (60+ Years)", f"${safe_val[0]:,.0f} / sqm")
    colB.metric("Restricted Lease (<60 Years)", f"${restricted_val[0]:,.0f} / sqm", delta=f"-${safe_val[0] - restricted_val[0]:,.0f} Penalty", delta_color="inverse")

# Render the Bar Chart
st.bar_chart(filtered_lease.set_index('lease_critical_status')['avg_psf'])

st.divider()
st.caption("Data Architecture: Bronze API -> OneMap Spatial Engineering -> NetworkX Graph -> PostgreSQL Gold Warehouse.")