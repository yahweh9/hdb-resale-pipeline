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

# Authentication
API_KEY = os.getenv("API_KEY") 
HEADERS = {"x-api-key": API_KEY} 

def get_latest_local_month():
    """Checks the Bronze layer to find the most recent data we already have."""
    if not os.path.exists(OUTPUT_PATH):
        return None # No local data found, we need a full refresh
    
    try:
        df_existing = pd.read_parquet(OUTPUT_PATH)
        latest_month = df_existing['month'].max()
        print(f"📁 Local Database found. Latest existing month is: {latest_month}")
        return latest_month
    except Exception as e:
        print(f"Error reading local database: {e}")
        return None

def fetch_incremental_hdb(latest_month, chunk_size=5000):
    all_new_records = []
    offset = 0
    keep_fetching = True
    
    print(f"[{datetime.now()}] Starting authenticated incremental ingestion...")

    while keep_fetching:
        params = {
            "resource_id": DATASET_ID,
            "limit": chunk_size,
            "offset": offset,
            "sort": "month desc" # Pulls the absolute newest data first
        }
        
        try:
            response = requests.get(BASE_URL, params=params, timeout=30, headers=HEADERS)
            
            if response.status_code == 429:
                print("Rate limit hit even with API Key. Cooling down...")
                time.sleep(5)
                continue
            
            response.raise_for_status()
            
            data = response.json()
            records = data['result']['records']
            
            if not records:
                break # API is completely out of data
                
            for row in records:
                # The Incremental Gate: If we hit data we already have, STOP completely!
                if latest_month and row['month'] <= latest_month:
                    keep_fetching = False
                    break
                
                all_new_records.append(row)
                
            print(f"Scanned {offset + len(records)} API records... Found {len(all_new_records)} new rows so far.")
            
            if not keep_fetching:
                break # Break the while loop if the inner loop triggered the gate
            
            offset += chunk_size
            time.sleep(0.5) 
            
        except requests.exceptions.RequestException as e:
            print(f"Error: {e}")
            break

    return pd.DataFrame(all_new_records)

def update_bronze_layer():
    # 1. Figure out where we left off
    latest_month = get_latest_local_month()
    
    # 2. Go get only the new rows
    df_new = fetch_incremental_hdb(latest_month)
    
    if df_new.empty:
        print(" Database is already 100% up to date. No new records to append.")
        return

    print(f" Downloaded {len(df_new)} brand new transactions.")

    # 3. Merge the old and the new safely
    if latest_month:
        # We have existing data, so load it and append
        df_existing = pd.read_parquet(OUTPUT_PATH)
        df_combined = pd.concat([df_existing, df_new], ignore_index=True)
        
        # Deduplication Safety Net (Ensures no overlaps from API pagination)
        initial_count = len(df_combined)
        df_combined = df_combined.drop_duplicates(subset=['_id'])
        dropped = initial_count - len(df_combined)
        if dropped > 0:
            print(f" Deduplication safety net removed {dropped} overlapping records.")
    else:
        # We had no local data, so the new data becomes the master file
        df_combined = df_new

    # 4. Save the updated master file back to disk
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    df_combined.to_parquet(OUTPUT_PATH, index=False)
    print(f"✅ Successfully updated Bronze Layer. Total records now: {len(df_combined)}")

if __name__ == "__main__":
    update_bronze_layer()