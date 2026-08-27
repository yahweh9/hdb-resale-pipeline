"""Ingest HDB resale transactions from data.gov.sg into the Bronze layer.

Runs incrementally by default: reads the newest month already on disk, fetches only
that month and later, then replaces the overlap month wholesale. The overlap month
is re-fetched rather than skipped because a month stays open -- transactions for
2026-08 keep landing throughout August, so skipping it would freeze a partial month
on disk permanently.

Pass --full to rebuild from scratch. That matters more than it looks: an incremental
run only ever moves the high-water mark FORWARD, so if the file on disk starts at
2024-06 the ~189k older transactions can never arrive on their own. The first build
of this file was capped at 50,000 rows, which left exactly that hole -- the summary
printed at the end of every run flags it against the API's own record count.

Outputs:
    data/bronze/hdb_resale_raw.parquet   one row per transaction, plus _ingested_at
"""

import argparse
import os
import time
from datetime import datetime

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

DATASET_ID = "d_8b84c4ee58e3cfc0ece0d773c8ca6abc"
BASE_URL = "https://data.gov.sg/api/action/datastore_search"
OUTPUT_PATH = "data/bronze/hdb_resale_raw.parquet"

# data.gov.sg serves this dataset anonymously but rate-limits harder without a key.
# Sending {"x-api-key": None} makes requests raise InvalidHeader, so drop the header
# entirely when the key is absent rather than sending a null one.
API_KEY = os.getenv("API_KEY")
HEADERS = {"x-api-key": API_KEY} if API_KEY else {}

CHUNK_SIZE = 5000
REQUEST_DELAY = 0.5
MAX_RETRIES = 5
BACKOFF_BASE = 2

# The _id tiebreaker makes paging deterministic. Ordering by month alone leaves ties
# unordered by contract -- thousands of rows share a month, and nothing promises the
# server breaks those ties identically on every request. It happens to be stable
# today; relying on that would silently duplicate rows across page boundaries and
# drop others the day it changes.
SORT = "month desc,_id asc"


class IngestError(RuntimeError):
    """Raised when the API cannot be read after exhausting retries."""


def get_existing_data(full_rebuild=False):
    """Load the current Bronze file, or None when starting from scratch."""
    if full_rebuild:
        print(f"[{datetime.now()}] --full requested. Rebuilding from scratch.")
        return None
    if not os.path.exists(OUTPUT_PATH):
        print(f"[{datetime.now()}] No existing dataset found. Running a FULL load.")
        return None
    print(f"[{datetime.now()}] Found existing dataset. Running an INCREMENTAL load.")
    return pd.read_parquet(OUTPUT_PATH)


def request_chunk(offset):
    """Fetch one page, retrying transient failures with exponential backoff.

    Retries are bounded. The previous version looped on HTTP 429 with no counter,
    so an exhausted daily quota hung the run indefinitely with no output.
    """
    params = {
        "resource_id": DATASET_ID,
        "limit": CHUNK_SIZE,
        "offset": offset,
        "sort": SORT,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        wait = BACKOFF_BASE**attempt
        try:
            response = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=30)

            if response.status_code == 429:
                if attempt == MAX_RETRIES:
                    raise IngestError(
                        f"Still rate-limited at offset {offset} after {MAX_RETRIES} attempts."
                    )
                print(f"    Rate limited. Retry {attempt}/{MAX_RETRIES} in {wait}s...")
                time.sleep(wait)
                continue

            response.raise_for_status()
            return response.json()["result"]

        except requests.exceptions.RequestException as e:
            # Retry the failed PAGE rather than aborting the whole run. A full load
            # is ~48 requests; failing on the last one used to discard every row
            # fetched up to that point.
            if attempt == MAX_RETRIES:
                raise IngestError(f"Offset {offset} failed after {MAX_RETRIES} attempts.") from e
            print(
                f"    {type(e).__name__} at offset {offset}."
                f" Retry {attempt}/{MAX_RETRIES} in {wait}s..."
            )
            time.sleep(wait)

    raise IngestError(f"Offset {offset} exhausted retries without a verdict.")


def fetch_records(latest_month=None):
    """Page through the API newest-first. Returns the records and the API's total."""
    records = []
    offset = 0
    api_total = None

    while True:
        result = request_chunk(offset)

        if api_total is None:
            api_total = result.get("total")
            print(f"API reports {api_total:,} total records.")

        chunk = result["records"]
        if not chunk:
            break

        if latest_month is not None:
            records.extend(r for r in chunk if r["month"] >= latest_month)
            # Sorted newest-first, so the first row older than the high-water mark
            # means everything remaining is already on disk.
            if any(r["month"] < latest_month for r in chunk):
                print(f"Reached data older than {latest_month}. Stopping.")
                break
        else:
            records.extend(chunk)

        print(f"  Fetched {len(records):,} records (offset {offset:,})")

        offset += CHUNK_SIZE
        if api_total is not None and offset >= api_total:
            break
        time.sleep(REQUEST_DELAY)

    return records, api_total


def merge_with_history(existing_df, new_df, latest_month):
    """Replace the overlap month, keep older history, drop any duplicate _id."""
    if existing_df is None or latest_month is None:
        return new_df

    historical_df = existing_df[existing_df["month"] < latest_month]
    merged = pd.concat([historical_df, new_df], ignore_index=True)
    print(f"Merged {len(historical_df):,} historical + {len(new_df):,} fetched records.")

    # Belt and braces. Dropping the overlap month above should already make
    # duplicates impossible; this makes it provable rather than merely intended.
    # keep="last" prefers the freshly fetched copy over the archived one.
    before = len(merged)
    merged = merged.drop_duplicates(subset=["_id"], keep="last")
    if before != len(merged):
        print(f"Dropped {before - len(merged):,} duplicate _id rows.")

    return merged


def summarise(df, api_total):
    """Report coverage, flagging any shortfall against what the API says exists."""
    print(f"\nRows on disk : {len(df):,}")
    print(f"Month range  : {df['month'].min()} -> {df['month'].max()}")

    if api_total is None:
        return

    missing = api_total - len(df)
    if missing > 0:
        print(
            f"\nWARNING: the API holds {api_total:,} records; this file has {len(df):,}."
            f"\n         {missing:,} transactions are missing, all older than {df['month'].min()}."
            f"\n         Incremental runs only move forward and will never fetch them."
            f"\n         Run 'python ingest_hdb.py --full' to backfill."
        )
    else:
        print("Coverage     : complete against the API total.")


def save_to_bronze(df):
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    df.to_parquet(OUTPUT_PATH, index=False)
    print(f"Saved {len(df):,} records to {OUTPUT_PATH}")


def build_bronze_hdb(full_rebuild=False):
    existing_df = get_existing_data(full_rebuild=full_rebuild)

    latest_month = None
    if existing_df is not None and not existing_df.empty:
        latest_month = existing_df["month"].max()
        print(f"High-water mark: {latest_month} (re-fetched to catch late transactions)")

    records, api_total = fetch_records(latest_month)

    if not records:
        # Previously this fell through to a no-op save that printed nothing at all,
        # leaving no way to tell "already current" apart from silent failure.
        print("\nNo new records returned. Already up to date.")
        if existing_df is not None:
            summarise(existing_df, api_total)
        return existing_df

    new_df = pd.DataFrame(records)
    new_df["_ingested_at"] = pd.Timestamp.now(tz="UTC")

    final_df = merge_with_history(existing_df, new_df, latest_month)
    save_to_bronze(final_df)
    summarise(final_df, api_total)
    return final_df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--full",
        action="store_true",
        help="Ignore the file on disk and re-fetch the entire history.",
    )
    args = parser.parse_args()
    build_bronze_hdb(full_rebuild=args.full)
