import duckdb
import os
import pandas as pd

# Paths
SILVER_FEATURES_PATH = "data/silver/hdb_resale_features.parquet"
GOLD_DIR = "data/gold/"

def build_gold_layer():
    print("Initializing DuckDB Analytics Engine...")
    
    # Ensure Gold directory exists
    os.makedirs(GOLD_DIR, exist_ok=True)
    
    # Connect to DuckDB (in-memory)
    conn = duckdb.connect()
    
    # ---------------------------------------------------------
    # INSIGHT 1: The "Elite School" Premium (Overall)
    # ---------------------------------------------------------
    print("\nCalculating the Elite Primary School Premium...")
    query_school = f"""
        SELECT 
            within_1km_elite_school,
            COUNT(*) as total_flats_sold,
            ROUND(AVG(resale_price), 0) as avg_price,
            ROUND(AVG(resale_price / floor_area_sqm), 0) as avg_psm
        FROM '{SILVER_FEATURES_PATH}'
        GROUP BY within_1km_elite_school
        ORDER BY within_1km_elite_school DESC
    """
    df_school_premium = conn.execute(query_school).df()
    
    # Save to Gold Layer
    df_school_premium.to_csv(os.path.join(GOLD_DIR, "insight_school_premium.csv"), index=False)
    print(df_school_premium)

    # ---------------------------------------------------------
    # INSIGHT 2: MRT Proximity Value Tiers
    # ---------------------------------------------------------
    print("\nCalculating MRT Distance Price Tiers...")
    query_mrt = f"""
        SELECT 
            CASE 
                WHEN dist_to_nearest_mrt_km <= 0.5 THEN '1. < 500m (Walkable)'
                WHEN dist_to_nearest_mrt_km <= 1.0 THEN '2. 500m - 1km (Feeder Bus)'
                ELSE '3. > 1km (Inaccessible)'
            END AS mrt_accessibility,
            COUNT(*) as transaction_volume,
            ROUND(AVG(resale_price), 0) as avg_price
        FROM '{SILVER_FEATURES_PATH}'
        GROUP BY mrt_accessibility
        ORDER BY mrt_accessibility
    """
    df_mrt_tiers = conn.execute(query_mrt).df()
    
    # Save to Gold Layer
    df_mrt_tiers.to_csv(os.path.join(GOLD_DIR, "insight_mrt_tiers.csv"), index=False)
    print(df_mrt_tiers)

    # ---------------------------------------------------------
    # INSIGHT 3: Most Expensive Towns by Per Square Meter
    # ---------------------------------------------------------
    print("\nRanking Top 5 Most Expensive Towns (Price Per Sqm)...")
    query_towns = f"""
        SELECT 
            town,
            ROUND(AVG(resale_price / floor_area_sqm), 0) as avg_psm
        FROM '{SILVER_FEATURES_PATH}'
        GROUP BY town
        ORDER BY avg_psm DESC
        LIMIT 5
    """
    df_top_towns = conn.execute(query_towns).df()
    df_top_towns.to_csv(os.path.join(GOLD_DIR, "insight_top_towns.csv"), index=False)
    print(df_top_towns)

    print(f"\n✅ Gold Layer built successfully. Analytics saved to {GOLD_DIR}")

if __name__ == "__main__":
    build_gold_layer()