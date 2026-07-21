import requests
import pandas as pd
import os
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Configuration (Add .strip() to clean the inputs)
raw_email = os.getenv("ONEMAP_EMAIL")
raw_password = os.getenv("ONEMAP_PASSWORD")
ONEMAP_EMAIL = raw_email.strip() if raw_email else None
ONEMAP_PASSWORD = raw_password.strip() if raw_password else None
HDB_SOURCE = "data/bronze/hdb_resale_raw.parquet"
SCHOOL_SOURCE = "data/bronze/schools_raw.parquet"
OUTPUT_PATH = "data/bronze/hdb_coordinates.parquet"
OUTPUT_PATH2 = "data/bronze/schools_coordinates.parquet"

def get_onemap_token():
    """Authenticates with OneMap and returns a JWT token."""
    
    # Failsafe: Don't hit the API if credentials are empty
    if not ONEMAP_EMAIL or not ONEMAP_PASSWORD:
        print("CRITICAL ERROR: Credentials are missing. Stopping script.")
        return None

    url = "https://www.onemap.gov.sg/api/auth/post/getToken"
    payload = {
        "email": ONEMAP_EMAIL,
        "password": ONEMAP_PASSWORD
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return response.json().get('access_token')
    except requests.exceptions.RequestException as e:
        print(f"Authentication failed: {e}")
        # Print the exact error response from the server for better debugging
        if hasattr(e, 'response') and e.response is not None:
            print(f"Server response: {e.response.text}")
        return None

# ... [Keep the rest of your functions the same below this] ...

def extract_unique_addresses(df):
    """Combines block and street to create a unique search string."""
    # Example: "215 CHOA CHU KANG CENT"
    df['address'] = df['block'] + " " + df['street_name']
    unique_addresses = df['address'].drop_duplicates().tolist()
    print(f"Found {len(unique_addresses)} unique addresses out of {len(df)} records.")
    return unique_addresses

def geocode_addresses(addresses, token):
    """Hits the OneMap Search API for each address."""
    results = []
    headers = {"Authorization": f"Bearer {token}"}
    base_url = "https://www.onemap.gov.sg/api/common/elastic/search"
    
    print(f"[{datetime.now()}] Starting Geocoding process...")
    
    for i, address in enumerate(addresses):
        params = {
            "searchVal": address,
            "returnGeom": "Y",
            "getAddrDetails": "Y",
            "pageNum": "1"
        }
        
        try:
            response = requests.get(base_url, params=params, headers=headers, timeout=10)
            
            # Simple polite rate-limiting
            if response.status_code == 429:
                print("Rate limit hit. Cooling down...")
                time.sleep(5)
                continue
                
            data = response.json()
            
            if data['found'] > 0:
                # Take the first (most relevant) result
                best_match = data['results'][0]
                results.append({
                    "address": address,
                    "latitude": float(best_match['LATITUDE']),
                    "longitude": float(best_match['LONGITUDE']),
                    "postal_code": best_match['POSTAL']
                })
            else:
                print(f"Warning: No coordinates found for {address}")
                
            # Log progress every 500 records
            if (i + 1) % 500 == 0:
                print(f"Geocoded {i + 1} / {len(addresses)} addresses...")
                
            time.sleep(0.2) # 5 requests per second is generally safe for OneMap
            
        except Exception as e:
            print(f"Error processing {address}: {e}")
            
    return pd.DataFrame(results)

def build_bronze_geodata():
    if not os.path.exists(HDB_SOURCE):
        print(f"Error: {HDB_SOURCE} not found. Run ingest_hdb.py first.")
        return

    # 1. Get Token
    token = get_onemap_token()
    if not token:
        return

    # 2. Read HDB Data & Extract Addresses
    hdb_df = pd.read_parquet(HDB_SOURCE)
    unique_addresses = extract_unique_addresses(hdb_df)
    
    # 3. Fetch Coordinates
    geo_df = geocode_addresses(unique_addresses, token)
    
    # 4. Save to Bronze
    if not geo_df.empty:
        os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
        geo_df.to_parquet(OUTPUT_PATH, index=False)
        print(f"Successfully saved {len(geo_df)} coordinates to {OUTPUT_PATH}")

def build_bronze_school_data():
    if not os.path.exists(SCHOOL_SOURCE):
        print(f"Error: {SCHOOL_SOURCE} not found. Run ingest_schools.py first.")
        return
    
    token = get_onemap_token()
    if not token:
        return
    
    # 2. Read School Data
    school_df = pd.read_parquet(SCHOOL_SOURCE)
    
    # THE TRICK: Use Postal Codes instead of text addresses for schools!
    # Convert them to strings and pad with zeros in case any started with 0 (e.g., 048123)
    postal_codes = school_df['postal_code'].astype(str).str.zfill(6).tolist()
    
    # 3. Fetch Coordinates
    geo_df = geocode_addresses(postal_codes, token)

    # 4. Save to Bronze
    if not geo_df.empty:
        os.makedirs(os.path.dirname(OUTPUT_PATH2), exist_ok=True)
        geo_df.to_parquet(OUTPUT_PATH2, index=False)
        print(f"Successfully saved {len(geo_df)} school coordinates to {OUTPUT_PATH2}")

if __name__ == "__main__":
    # build_bronze_geodata() 
    build_bronze_school_data()