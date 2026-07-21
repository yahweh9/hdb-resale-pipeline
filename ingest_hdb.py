import requests
import pandas as pd
import os
from datetime import datetime
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
DATASET_ID = "d_8b84c4ee58e3cfc0ece0d773c8ca6abc"
BASE_URL = "https://data.gov.sg/api/action/datastore_search"
OUTPUT_PATH = "data/bronze/hdb_resale_raw.parquet"
# Updated Configuration
API_KEY = os.getenv("API_KEY") 
HEADERS = {"x-api-key": API_KEY} # GovTech standard for 2026

def fetch_hdb_data(total_needed=50000, chunk_size=5000): # Reduced chunk for safety
    all_records = []
    offset = 0
    
    print(f"[{datetime.now()}] Starting authenticated ingestion...")

    while len(all_records) < total_needed:
        params = {
            "resource_id": DATASET_ID,
            "limit": chunk_size,
            "offset": offset,
            "sort": "month desc"
        }
        
        try:
            # Use HEADERS here
            response = requests.get(BASE_URL, params=params, timeout=30, headers=HEADERS)
            
            if response.status_code == 429:
                print("Rate limit hit even with API Key. Cooling down...")
                time.sleep(5) # API Key usually allows faster recovery
                continue
            
            response.raise_for_status()
            
            data = response.json()
            records = data['result']['records']
            
            if not records:
                break
                
            all_records.extend(records)
            print(f"Progress: {len(all_records)} / {total_needed} (Offset: {offset})")
            
            offset += chunk_size
            time.sleep(0.5) # With an API key, you can reduce this significantly!
            
        except requests.exceptions.RequestException as e:
            print(f"Error: {e}")
            break

    return pd.DataFrame(all_records)

def save_to_bronze(df):
    if df is not None and not df.empty:
        os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
        df.to_parquet(OUTPUT_PATH, index=False)
        print(f"Successfully archived {len(df)} records at: {OUTPUT_PATH}")

if __name__ == "__main__":
    hdb_df = fetch_hdb_data(total_needed=50000)
    save_to_bronze(hdb_df)


