import pandas as pd
import os

# Paths
CSV_PATH = "data/bronze/mrt_lrt.csv" 
OUTPUT_PATH = "data/bronze/mrt_stations.parquet"

def clean_and_save_mrt():
    print(f"Loading raw MRT data from {CSV_PATH}...")
    try:
        df = pd.read_csv(CSV_PATH)
    except FileNotFoundError:
        print(f"Error: Could not find {CSV_PATH}. Make sure it's in the same folder as this script.")
        return

    # 1. Standardize column names to match our Silver Layer
    df = df.rename(columns={
        'Name': 'mrt_name',
        'Latitude': 'latitude',
        'Longitude': 'longitude'
    })

    # Keep only the columns we need (drop the weird 'Unnamed: 0', 'X', 'Y' columns)
    df = df[['mrt_name', 'latitude', 'longitude']]

    # 2. Exorcise the "Ghost Station" (Ten Mile Junction closed in 2019)
    initial_count = len(df)
    df = df[~df['mrt_name'].str.contains("TEN MILE JUNCTION", case=False, na=False)]
    print(f"Dropped {initial_count - len(df)} closed station(s).")

    # 3. Append the missing modern stations 
    new_stations = pd.DataFrame([
        {
            "mrt_name": "PUNGGOL COAST MRT STATION", 
            "latitude": 1.4158, 
            "longitude": 103.9023
        },
        {
            "mrt_name": "HUME MRT STATION", 
            "latitude": 1.3536, 
            "longitude": 103.7691
        }
    ])
    
    # Combine the cleaned data with the newly added stations
    df = pd.concat([df, new_stations], ignore_index=True)
    print("Added missing stations: Punggol Coast & Hume.")

    # 4. Save to Bronze Layer as a Lakehouse-ready Parquet file
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    df.to_parquet(OUTPUT_PATH, index=False)
    
    print(f"✅ Successfully saved {len(df)} active MRT/LRT stations to {OUTPUT_PATH}")

if __name__ == "__main__":
    clean_and_save_mrt()