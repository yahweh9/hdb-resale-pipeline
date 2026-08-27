import pandas as pd
import numpy as np
import os
from sklearn.neighbors import BallTree 

# Paths
SILVER_SPATIAL_PATH = "data/silver/hdb_resale_spatial.parquet"
SCHOOLS_SPATIAL_PATH = "data/silver/primary_schools_spatial.parquet" 
MRT_BRONZE_PATH = "data/bronze/mrt_stations.parquet" 
MALLS_BRONZE_CSV = "data/bronze/singapore_malls.csv"

# Pipeline Output Paths
SILVER_FEATURES_STEP1 = "data/silver/hdb_resale_features_step1.parquet"
SILVER_FEATURES_STEP2 = "data/silver/hdb_resale_features_step2.parquet"
SILVER_FEATURES_FINAL = "data/silver/hdb_resale_features.parquet"

CBD_LAT, CBD_LON = 1.2839, 103.8515

# Your Data-Driven Top 20 Elite Schools
ELITE_SCHOOLS = [
    "TAO NAN SCHOOL", "AI TONG SCHOOL", "NANYANG PRIMARY SCHOOL", 
    "PEI HWA PRESBYTERIAN PRIMARY SCHOOL", "METHODIST GIRLS' SCHOOL (PRIMARY)", 
    "NAN CHIAU PRIMARY SCHOOL", "CHIJ ST. NICHOLAS GIRLS' SCHOOL", 
    "CHIJ PRIMARY (TOA PAYOH)", "RED SWASTIKA SCHOOL", "KONG HWA SCHOOL", 
    "ANGLO-CHINESE SCHOOL (JUNIOR)", "MAHA BODHI SCHOOL", 
    "HOLY INNOCENTS' PRIMARY SCHOOL", "ST. JOSEPH'S INSTITUTION JUNIOR", 
    "CHONGFU SCHOOL", "NAN HUA PRIMARY SCHOOL", "ANGLO-CHINESE SCHOOL (PRIMARY)", 
    "CATHOLIC HIGH SCHOOL", "MARIS STELLA HIGH SCHOOL", "ROSYTH SCHOOL"
]

def haversine_vectorized(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2.0)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2.0)**2
    c = 2 * np.arcsin(np.sqrt(a))
    return 6371 * c

def engineer_spatial_features():
    print("PHASE 1: Base Spatial Features...")
    df = pd.read_parquet(SILVER_SPATIAL_PATH)
    mrt_df = pd.read_parquet(MRT_BRONZE_PATH)
    schools_df = pd.read_parquet(SCHOOLS_SPATIAL_PATH)
    
    df = df.dropna(subset=['latitude', 'longitude'])

    # 1. Distance to CBD
    df['dist_to_cbd_km'] = haversine_vectorized(df['latitude'], df['longitude'], CBD_LAT, CBD_LON).round(2)

    # 2. Distance & Name of Nearest MRT
    mrt_lats, mrt_lons = mrt_df['latitude'].values, mrt_df['longitude'].values
    mrt_names = mrt_df['mrt_name'].values
    
    def get_nearest_mrt_info(row):
        distances = haversine_vectorized(row['latitude'], row['longitude'], mrt_lats, mrt_lons)
        min_idx = np.argmin(distances) 
        return distances[min_idx], mrt_names[min_idx]

    df['dist_to_nearest_mrt_km'], df['nearest_mrt_name'] = zip(*df.apply(get_nearest_mrt_info, axis=1))
    df['dist_to_nearest_mrt_km'] = df['dist_to_nearest_mrt_km'].astype(float).round(2)

    # --- THE ELITE SCHOOL UPGRADE ---
    elite_df = schools_df[schools_df['school_name'].str.upper().isin(ELITE_SCHOOLS)]
    
    if not elite_df.empty:
        elite_lats, elite_lons = elite_df['latitude'].values, elite_df['longitude'].values
        def get_nearest_elite_school(row):
            return haversine_vectorized(row['latitude'], row['longitude'], elite_lats, elite_lons).min()
        
        df['dist_to_elite_school_km'] = df.apply(get_nearest_elite_school, axis=1).round(2)
        df['within_1km_elite_school'] = (df['dist_to_elite_school_km'] <= 1.0).astype(int)

    df.to_parquet(SILVER_FEATURES_STEP1, index=False)
    print("Phase 1 complete.\n")

def engineer_advanced_spatial_features():
    print("PHASE 2: Advanced Spatial & Gravity Models...")
    df = pd.read_parquet(SILVER_FEATURES_STEP1)
    df_mrt = pd.read_parquet(MRT_BRONZE_PATH)
    df_malls = pd.read_csv(MALLS_BRONZE_CSV)

    # 1. Walk Time to MRT
    df['mrt_walk_time_mins'] = np.ceil((df['dist_to_nearest_mrt_km'] * 1000) / 80)

    # 2. Raffles Place Index
    # UPGRADE: Rename 'mrt_name' to 'station_name' to match Phase 1
    df_mrt = df_mrt.rename(columns={'mrt_name': 'station_name'})
    
    # UPGRADE: Create the temporary mock column for travel time
    df_mrt['mins_to_raffles'] = 30 
    
    # Now the merge will work perfectly because those columns exist!
    df = df.merge(
        df_mrt[['station_name', 'mins_to_raffles']], 
        left_on='nearest_mrt_name', 
        right_on='station_name', 
        how='left'
    )
    df['total_cbd_commute_mins'] = df['mrt_walk_time_mins'] + df['mins_to_raffles']
    df = df.drop(columns=['station_name'])

    # 3. Proximity Gravity: Malls within 2km
    hdb_coords_rad = np.radians(df[['latitude', 'longitude']].values)
    # Using 'lat' and 'lon' because your singapore_malls.csv uses lowercase!
    mall_coords_rad = np.radians(df_malls[['lat', 'lon']].values)
    radius_rad = 2.0 / 6371.0 

    print(" Building BallTree for 50,000+ spatial lookups...")
    tree = BallTree(mall_coords_rad, metric='haversine')
    df['malls_within_2km'] = tree.query_radius(hdb_coords_rad, r=radius_rad, count_only=True)

    df.to_parquet(SILVER_FEATURES_STEP2, index=False)
    print(" Phase 2 Complete!\n")

def engineer_domain_features():
    print(" PHASE 3: Singapore Real Estate Domain Features...")
    df = pd.read_parquet(SILVER_FEATURES_STEP2)

    # FEATURE 1: TOWN MATURITY
    mature_towns = [
        'ANG MO KIO', 'BEDOK', 'BISHAN', 'BUKIT MERAH', 'BUKIT TIMAH', 
        'CENTRAL AREA', 'CLEMENTI', 'GEYLANG', 'KALLANG/WHAMPOA', 
        'MARINE PARADE', 'PASIR RIS', 'QUEENSTOWN', 'SERANGOON', 
        'TAMPINES', 'TOA PAYOH'
    ]
    df['estate_maturity'] = np.where(df['town'].isin(mature_towns), 'Mature', 'Non-Mature')

    # FEATURE 2: Storey premium (Floor Tiers)
    df['floor_lower_bound'] = df['storey_range'].str[:2].astype(int)
    bins = [-1, 4, 9, 19, 100]
    labels = ['Low (0-4)', 'Mid (5-9)', 'High (10-19)', 'Ultra-High (20+)']
    df['floor_tier'] = pd.cut(df['floor_lower_bound'], bins=bins, labels=labels)
    df = df.drop(columns=['floor_lower_bound'])

    # FEATURE 3: Remaining lease & Bala's Curve
    df['transaction_year'] = df['month'].str[:4].astype(int)
    
    #Convert lease_commence_date to an integer so we can do math with it!
    df['lease_commence_date'] = df['lease_commence_date'].astype(int)
    
    # Now the math will work perfectly
    df['remaining_lease_years'] = 99 - (df['transaction_year'] - df['lease_commence_date'])
    
    conditions = [
        (df['remaining_lease_years'] < 30),
        (df['remaining_lease_years'] < 60),
        (df['remaining_lease_years'] >= 60)
    ]
    choices = ['High Risk (<30 yrs)', 'Restricted (<60 yrs)', 'Safe (60+ yrs)']
    df['lease_critical_status'] = np.select(conditions, choices, default='Unknown')

    # SAVE AND VERIFY
    df.to_parquet(SILVER_FEATURES_FINAL, index=False)
    print(f"Phase 3 complete. Master dataset ready at: {SILVER_FEATURES_FINAL}\n")

if __name__ == "__main__":
    engineer_spatial_features()
    engineer_advanced_spatial_features()
    engineer_domain_features()