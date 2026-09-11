"""Materialise the committed CSV fixture into a bronze layer CI can build on.

CI has no way to produce a real bronze layer without calling data.gov.sg on every
pull request, which is slow, rate-limited, and turns an unrelated API outage into a
red build. This writes a 766-row sample -- stratified so every flat type and most
months are represented -- into a root of its own.

It writes through ingest_hdb.write_partitions rather than reimplementing the layout,
so the fixture cannot drift from what the real ingest produces: change the partition
scheme and this changes with it, or the tests fail.

    python seed_fixture.py
    export DUCKDB_PATH=data/fixture/warehouse.duckdb
    dbt build --vars '{bronze_glob: "data/fixture/hdb_resale/month=*/*.parquet"}'
"""

import os
import sys

import pandas as pd

import ingest_hdb

FIXTURE_CSV = "tests/fixtures/hdb_resale_sample.csv"
FIXTURE_ROOT = "data/fixture/hdb_resale"


def seed(root=FIXTURE_ROOT):
    """Write the fixture as month partitions under `root`. Returns {month: rows}."""
    if os.path.normpath(root) == os.path.normpath(ingest_hdb.BRONZE_ROOT):
        # write_partitions replaces a month wholesale. Pointed at the real bronze
        # root it would quietly swap ~240k live rows for 766 fixture ones.
        raise SystemExit(f"Refusing to seed the fixture into the real bronze root: {root}")

    df = pd.read_csv(FIXTURE_CSV, dtype=str)
    # The API hands back _id as a number and everything else as a string, and bronze
    # stores exactly that. The fixture has to match, or silver's casts go untested.
    df["_id"] = df["_id"].astype("int64")
    df["_ingested_at"] = pd.Timestamp.now(tz="UTC")

    original_root = ingest_hdb.BRONZE_ROOT
    ingest_hdb.BRONZE_ROOT = root
    try:
        written = ingest_hdb.write_partitions(df)
    finally:
        ingest_hdb.BRONZE_ROOT = original_root

    print(f"Seeded {sum(written.values()):,} fixture rows into {root}")
    return written


if __name__ == "__main__":
    seed(sys.argv[1] if len(sys.argv) > 1 else FIXTURE_ROOT)
