"""Fetch Singapore MRT/LRT stations from Wikidata and archive the response.

This script's entire job is transport: ask Wikidata, get bytes, write them down
faithfully. It does no filtering, no parsing and no reshaping -- deciding what the
response MEANS is silver_mrt_stations.sql's job.

It did all of that once. Excluding unopened lines, collapsing interchanges and
validating coordinates happened here, before anything reached the warehouse, which
made those rules invisible to dbt, impossible to test, and re-evaluable only by
re-querying Wikidata. Worse, they expire: the Jurong Region Line opens and a rule
baked into an archive stays wrong until someone re-runs this. In dbt the same rule
re-evaluates on every build.

Replaces the Kaggle-sourced mrt_lrt.csv, which had unknown provenance, was stale, and
was patched with hardcoded coordinates ~880m off for Punggol Coast.

Wikidata is CC0 (public domain), so it carries no attribution or share-alike
obligation -- unlike Wikipedia article text (CC BY-SA) or OpenStreetMap (ODbL).

Outputs:
    data/bronze/mrt_stations_raw.parquet   the SPARQL response, as returned
"""

import os
import sys

import pandas as pd
import requests

# Wikidata line names contain en-dashes. On a Windows console defaulting to a legacy
# codepage, printing one raises UnicodeEncodeError and kills the run after the data
# has already been fetched. Force UTF-8 on our own output rather than sanitising
# every print.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# The Wikidata Query Service asks for a real contact so they can reach you if a query
# misbehaves. A placeholder address risks getting blocked.
USER_AGENT = "HDB-lakehouse/0.1 (https://github.com/yahweh9/HDB)"

ENDPOINT = "https://query.wikidata.org/sparql"
RAW_PATH = "data/bronze/mrt_stations_raw.parquet"

# Q55488  railway station -- deliberately broader than Q928830 (metro station), which
#         would silently drop all 42 LRT stations since light rail is not classed as
#         metro.
# Q334    Singapore
#
# Contamination is excluded by transport MODE (P31), not by requiring a station code.
# Requiring P296 looked tempting but dropped 27 operational stations Wikidata simply
# has not coded -- Changi Airport, Expo, Beauty World, Great World, Maxwell and the
# whole Marine Parade stretch.
#
# Filtering on P361 (part of network) does not work either: only 35 stations use it,
# all of them LRT, so it would discard the entire MRT network.
#
# These filters stay here rather than moving to dbt because they are part of the
# QUESTION being asked of Wikidata, not a judgement about the answer. Fetching every
# structure in Singapore and discarding 99% of it in SQL would be absurd.
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
    # WDQS returns 429 when rate-limited and 400 on a malformed query. Without this,
    # .json() fails further down with a confusing KeyError instead.
    response.raise_for_status()

    rows = [
        {
            "mrt_name": item.get("stationLabel", {}).get("value"),
            "station_code": item.get("stationCode", {}).get("value"),
            "line": item.get("lineLabel", {}).get("value"),
            "opening_date": item.get("openingDate", {}).get("value"),
            "coordinates": item.get("coordinates", {}).get("value"),
        }
        for item in response.json()["results"]["bindings"]
    ]

    df = pd.DataFrame(rows)
    print(f"Retrieved {len(df)} rows covering {df['mrt_name'].nunique()} stations.")
    return df


def build_bronze_mrt():
    """Fetch and archive. Everything else is silver_mrt_stations.sql."""
    df = fetch_raw()

    os.makedirs(os.path.dirname(RAW_PATH), exist_ok=True)
    df.to_parquet(RAW_PATH, index=False)
    print(f"Archived raw response to {RAW_PATH}")
    print("Run 'dbt build --select silver_mrt_stations' to narrow it to operational stations.")
    return df


if __name__ == "__main__":
    build_bronze_mrt()
