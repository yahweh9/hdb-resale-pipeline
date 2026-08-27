import pandas as pd
import os

# Paths
HDB_RAW = "data/bronze/hdb_resale_raw.parquet"
HDB_COORDS = "data/bronze/hdb_coordinates.parquet"
SCHOOL_RAW = "data/bronze/schools_raw.parquet"
SCHOOL_COORDS = "data/bronze/schools_coordinates.parquet"

SILVER_SPATIAL_PATH = "data/silver/hdb_resale_spatial.parquet"
SILVER_SPATIAL_PATH2 = "data/silver/primary_schools_spatial.parquet" # Renamed for clarity

def create_spatial_master():
    print("Loading Bronze Datasets...")
    df_transactions = pd.read_parquet(HDB_RAW)
    df_coords = pd.read_parquet(HDB_COORDS)
    df_schools = pd.read_parquet(SCHOOL_RAW)
    df_schools_coords = pd.read_parquet(SCHOOL_COORDS)

    # --- 1. HDB TRANSACTIONS MERGE ---
    df_transactions['address'] = df_transactions['block'] + " " + df_transactions['street_name']
    df_silver = pd.merge(df_transactions, df_coords, on='address', how='left')
    
    missing_coords = df_silver['latitude'].isna().sum()
    print(f"HDB Merge complete! Missing coordinates: {missing_coords} out of {len(df_silver)}")

    # --- 2. SCHOOLS FILTER & MERGE ---
    # Filter ONLY for Primary Schools (Domain Knowledge!)
    df_schools = df_schools[df_schools['mainlevel_code'].str.contains("PRIMARY", case=False, na=False)]
    
    # Standardize the merge keys to be zero-padded strings to avoid DataType traps
    df_schools['postal_code'] = df_schools['postal_code'].astype(str).str.zfill(6)
    df_schools_coords['postal_code'] = df_schools_coords['postal_code'].astype(str).str.zfill(6)
    
    # Perform the Left Join
    df2_silver = pd.merge(df_schools, df_schools_coords, on='postal_code', how='left')
    
    missing_sch_coords = df2_silver['latitude'].isna().sum()
    print(f"Schools Merge complete! Missing coordinates: {missing_sch_coords} out of {len(df2_silver)}")

    # --- 3. SAVE TO SILVER LAYER ---
    os.makedirs(os.path.dirname(SILVER_SPATIAL_PATH), exist_ok=True)
    df_silver.to_parquet(SILVER_SPATIAL_PATH, index=False)
    df2_silver.to_parquet(SILVER_SPATIAL_PATH2, index=False)
    
    print(f"Saved HDB Spatial Master to {SILVER_SPATIAL_PATH}")
    print(f"Saved Primary Schools Spatial Master to {SILVER_SPATIAL_PATH2}")
    
    return df_silver, df2_silver # Return them so we can print them safely!

if __name__ == "__main__":
    hdb_final, schools_final = create_spatial_master()
    
    print("\n--- SNEAK PEEK: PRIMARY SCHOOLS ---")
    print(schools_final[['school_name', 'postal_code', 'latitude', 'longitude']].head())