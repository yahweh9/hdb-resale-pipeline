"""Ingest Singapore MRT/LRT stations from Wikidata into the Bronze layer.

Replaces the Kaggle-sourced mrt_lrt.csv, which had unknown provenance, was stale,
and was patched with hardcoded coordinates that were ~880m off for Punggol Coast.

Wikidata is CC0 (public domain), so it carries no attribution or share-alike
obligation -- unlike Wikipedia article text (CC BY-SA) or OpenStreetMap (ODbL).

Outputs:
    data/bronze/mrt_stations_raw.parquet  as returned, one row per station/line/code
    data/bronze/mrt_stations.parquet      one row per operational station
"""

import os

import pandas as pd
import requests

# The Wikidata Query Service asks for a real contact so they can reach you if a
# query misbehaves. A placeholder address risks getting blocked.
USER_AGENT = "HDB-lakehouse/0.1 (https://github.com/yahweh9/HDB)"

ENDPOINT = "https://query.wikidata.org/sparql"
RAW_PATH = "data/bronze/mrt_stations_raw.parquet"
OUTPUT_PATH = "data/bronze/mrt_stations.parquet"

# Q55488  railway station -- deliberately broader than Q928830 (metro station),
#         which would silently drop all 42 LRT stations since light rail is not
#         classed as metro.
# Q334    Singapore
#
# Contamination is excluded by transport MODE (P31), not by requiring a station
# code. Requiring P296 looked tempting but dropped 27 operational stations that
# Wikidata simply has not coded -- Changi Airport, Expo, Beauty World, Great
# World, Maxwell and the whole Marine Parade stretch.
#
# Filtering on P361 (part of network) does not work either: only 35 stations use
# it, all of them LRT, so it would discard the entire MRT network.
#
# P81     connecting line
# P1619   date of official opening
# P625    coordinate location, returned as WKT "Point(longitude latitude)"
QUERY = """
SELECT DISTINCT ?stationLabel ?stationCode ?lineLabel ?openingDate ?coordinates WHERE {
  ?station wdt:P31/wdt:P279* wd:Q55488.
  ?station wdt:P17 wd:Q334.

  FILTER NOT EXISTS { ?station wdt:P31 wd:Q63125083. }   # monorail station (Sentosa)
  FILTER NOT EXISTS { ?station wdt:P31 wd:Q63979268. }   # people mover station
  FILTER NOT EXISTS { ?station wdt:P31 wd:Q4663385.  }   # former railway station (KTM)
  FILTER NOT EXISTS { ?station wdt:P31 wd:Q2175765.  }   # tram stop

  OPTIONAL { ?station wdt:P296  ?stationCode. }
  OPTIONAL { ?station wdt:P81   ?line. }
  OPTIONAL { ?station wdt:P1619 ?openingDate. }
  OPTIONAL { ?station wdt:P625  ?coordinates. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
ORDER BY ?stationCode
"""


def fetch_raw():
    """Query Wikidata and return the response as a flat DataFrame."""
    print("Querying Wikidata Query Service...")
    response = requests.get(
        ENDPOINT,
        params={"format": "json", "query": QUERY},
        headers={"User-Agent": USER_AGENT},
        timeout=90,
    )
    # WDQS returns 429 when rate-limited and 400 on a malformed query. Without
    # this, .json() fails further down with a confusing KeyError instead.
    response.raise_for_status()

    rows = []
    for item in response.json()["results"]["bindings"]:
        rows.append(
            {
                "mrt_name": item.get("stationLabel", {}).get("value"),
                "station_code": item.get("stationCode", {}).get("value"),
                "line": item.get("lineLabel", {}).get("value"),
                "opening_date": item.get("openingDate", {}).get("value"),
                "coordinates": item.get("coordinates", {}).get("value"),
            }
        )

    df = pd.DataFrame(rows)
    print(f"Retrieved {len(df)} rows covering {df['mrt_name'].nunique()} stations.")
    return df


def parse_coordinates(df):
    """Split WKT 'Point(lon lat)' into columns. Longitude comes FIRST."""
    extracted = df["coordinates"].str.extract(r"Point\(([-\d.]+)\s+([-\d.]+)\)")
    df["longitude"] = pd.to_numeric(extracted[0], errors="coerce")
    df["latitude"] = pd.to_numeric(extracted[1], errors="coerce")
    return df


def collapse_to_stations(df):
    """One row per station. Interchanges fan out across both lines and codes."""
    return df.groupby("mrt_name", as_index=False).agg(
        station_codes=("station_code", lambda s: "|".join(sorted(set(s.dropna())))),
        lines=("line", lambda s: "|".join(sorted(set(s.dropna())))),
        opening_date=("opening_date", "min"),
        latitude=("latitude", "first"),
        longitude=("longitude", "first"),
    )


def build_bronze_mrt():
    df_raw = fetch_raw()

    os.makedirs(os.path.dirname(RAW_PATH), exist_ok=True)
    df_raw.to_parquet(RAW_PATH, index=False)
    print(f"Archived raw response to {RAW_PATH}")

    df = collapse_to_stations(parse_coordinates(df_raw.copy()))
    print(f"\nCollapsed to {len(df)} unique stations.")

    df["opening_date"] = pd.to_datetime(df["opening_date"], errors="coerce", utc=True)

    # Exclude stations that have not opened yet. Wikidata carries the Jurong
    # Region and Cross Island lines in full, but they are not operational --
    # including them computes distances to stations that do not exist.
    now = pd.Timestamp.now(tz="UTC")
    unopened = df[df["opening_date"] > now]
    if not unopened.empty:
        print(f"\nExcluded {len(unopened)} stations with a future opening date:")
        for _, row in unopened.sort_values("opening_date").iterrows():
            print(f"    {row['mrt_name']:38s} opens {row['opening_date'].date()}")
        df = df[~(df["opening_date"] > now)]

    # A missing opening date reliably means "not open yet" here: every such
    # station is Jurong Region Line, Sungei Bedok, or Teck Lee (built but never
    # opened). Dropping them is listed explicitly so the assumption stays
    # falsifiable -- if a station you expect appears below, revisit this rule.
    undated = df[df["opening_date"].isna()]
    if not undated.empty:
        print(f"\nExcluded {len(undated)} stations with no opening date (treated as unopened):")
        for _, row in undated.iterrows():
            print(f"    {row['mrt_name']:38s} {row['lines']}")
        df = df.dropna(subset=["opening_date"])

    missing_coords = df[df["latitude"].isna() | df["longitude"].isna()]
    if not missing_coords.empty:
        print(f"\nDropped {len(missing_coords)} stations with no coordinates:")
        for name in missing_coords["mrt_name"]:
            print(f"    {name}")
        df = df.dropna(subset=["latitude", "longitude"])

    # Every station must land inside Singapore. This catches a lat/lon swap,
    # which is the easiest mistake to make with WKT's longitude-first ordering.
    outside = df[
        ~df["latitude"].between(1.15, 1.48) | ~df["longitude"].between(103.6, 104.1)
    ]
    if not outside.empty:
        raise ValueError(f"{len(outside)} stations fall outside Singapore:\n{outside}")

    df["opening_date"] = df["opening_date"].dt.date
    df = df.sort_values("mrt_name").reset_index(drop=True)

    df.to_parquet(OUTPUT_PATH, index=False)
    print(f"\nSaved {len(df)} operational stations to {OUTPUT_PATH}")
    return df


if __name__ == "__main__":
    stations = build_bronze_mrt()
    print("\n--- SAMPLE ---")
    print(stations.head(8).to_string(index=False))
