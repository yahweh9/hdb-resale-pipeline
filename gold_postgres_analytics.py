import pandas as pd
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()

# Paths and Config
SILVER_FEATURES_PATH = "data/silver/hdb_resale_features.parquet"
PG_PASSWORD = os.getenv("PG_PASSWORD", "your_password_here")
DB_NAME = "hdb_portfolio"

def setup_database():
    """Ensures the target database exists."""
    print("⚙️ Checking database infrastructure...")
    default_uri = f"postgresql://postgres:{PG_PASSWORD}@localhost:5432/postgres"
    engine = create_engine(default_uri, isolation_level="AUTOCOMMIT")
    
    with engine.connect() as conn:
        query = text(f"SELECT 1 FROM pg_database WHERE datname = '{DB_NAME}'")
        exists = conn.execute(query).scalar()
        if not exists:
            print(f"🛠️ Creating database '{DB_NAME}'...")
            conn.execute(text(f"CREATE DATABASE {DB_NAME}"))
            print(f"✅ Database created!")

def run_postgres_pipeline():
    setup_database()
    
    print("\n🔌 Connecting to the Gold Layer database...")
    target_uri = f"postgresql://postgres:{PG_PASSWORD}@localhost:5432/{DB_NAME}"
    engine = create_engine(target_uri)
    
    # --- PHASE 1: LOAD THE MASTER DATASET ---
    print(f"📥 Loading Master Silver data from {SILVER_FEATURES_PATH}...")
    df_silver = pd.read_parquet(SILVER_FEATURES_PATH)
    
    # CRITICAL FIX: Ensure exact math types for PostgreSQL
    df_silver['resale_price'] = pd.to_numeric(df_silver['resale_price'])
    df_silver['floor_area_sqm'] = pd.to_numeric(df_silver['floor_area_sqm'])
    
    print("⬆️ Uploading enriched dataset to PostgreSQL... (This may take a moment)")
    # We use if_exists='replace' to overwrite the old table with our new columns
    df_silver.to_sql('silver_hdb_features', engine, if_exists='replace', index=False)
    print("✅ Upload complete!")

    # --- PHASE 2: GOLD ANALYTICS (PROVING BALA'S CURVE) ---
    print("\n📊 Executing Gold Analytics directly in PostgreSQL...")
    
    # Let's test the new domain features: Maturity vs Lease Decay
    query_lease_decay = """
        SELECT 
            estate_maturity,
            lease_critical_status,
            flat_type,
            COUNT(*) AS total_sales,
            ROUND(AVG(resale_price)) AS avg_raw_price,
            ROUND(AVG(resale_price / floor_area_sqm)) AS avg_price_per_sqm
        FROM silver_hdb_features
        -- Only look at the main family flat types to keep the matrix clean
        WHERE flat_type IN ('3 ROOM', '4 ROOM', '5 ROOM') 
        GROUP BY estate_maturity, lease_critical_status, flat_type
        ORDER BY flat_type, estate_maturity, avg_price_per_sqm DESC;
    """
    
    with engine.connect() as connection:
        result = connection.execute(text(query_lease_decay))
        df_gold_insight = pd.DataFrame(result.fetchall(), columns=list(result.keys()))
        
    print("\n--- 🏆 THE MATURITY & LEASE DECAY MATRIX ---")
    print(df_gold_insight.to_string(index=False))

if __name__ == "__main__":
    run_postgres_pipeline()