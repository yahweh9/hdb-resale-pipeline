"""Ingest HDB resale transactions from data.gov.sg into the Bronze layer.

Writes one Hive-style partition per transaction month:

    data/bronze/hdb_resale/month=2024-06/part-0.parquet

A month is replaced wholesale or not touched at all. That is what makes a rerun
idempotent: re-running March rewrites March and leaves every other month byte for
byte as it was. The previous version read the whole file into memory, concatenated,
de-duplicated and rewrote all ~190k rows on every run -- so a crash mid-write took
the entire history with it.

Runs incrementally by default. The high-water mark is read back off the partitions
themselves (max(month) over the Hive paths) rather than from a run log. There is no
second source of truth to drift, DuckDB takes the value from the directory names
rather than the column data, and a run that dies halfway self-heals on the next
attempt. At real volume a manifest is the better answer; see the README's "at scale"
section.

The newest month on disk is re-fetched rather than skipped, because a month stays
open: transactions for 2026-08 keep landing throughout August, so skipping it would
freeze a partial month on disk permanently.

Pass --full to rebuild from scratch. That matters more than it looks: an incremental
run only ever moves the high-water mark FORWARD, so if the oldest partition on disk
is 2024-06 the ~189k older transactions can never arrive on their own. The summary
printed at the end of every run flags that against the API's own record count.
"""

import argparse
import glob
import os
import re
import time
from datetime import datetime

import duckdb
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

DATASET_ID = "d_8b84c4ee58e3cfc0ece0d773c8ca6abc"
BASE_URL = "https://data.gov.sg/api/action/datastore_search"

BRONZE_ROOT = "data/bronze/hdb_resale"
# Forward slashes deliberately: this string is handed to DuckDB as a glob, and
# DuckDB does not treat a Windows backslash as a path separator.
PARTITION_GLOB = f"{BRONZE_ROOT}/month=*/*.parquet"

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

# Anchored at both ends, and a month of 00 or 13 is rejected. This value is
# interpolated into a filesystem path, so it is validated as a path component
# before it ever reaches the filesystem.
MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class IngestError(RuntimeError):
    """Raised when the API cannot be read, or answers with something unusable."""


def partition_files():
    """Every parquet file in the bronze layer, as forward-slashed paths.

    The list is expanded here and handed to DuckDB explicitly rather than passing it
    the glob and letting it walk the tree. write_partitions creates a month directory
    before it writes into it, so a crash in between leaves a REAL empty partition
    directory on disk -- and some DuckDB builds raise an internal assertion when
    expanding a glob across one. Found by CI on Linux against a newer DuckDB than the
    one this was written on; it passed locally throughout.

    Expanding in Python also removes work that was being done twice: the caller
    already globbed to decide whether any partitions existed at all.
    """
    return [f.replace(os.sep, "/") for f in glob.glob(PARTITION_GLOB)]


def months_on_disk():
    """Every month present in the bronze layer, read out of the directory names."""
    months = set()
    for path in partition_files():
        match = re.search(r"/month=([^/]+)/", path)
        if match and MONTH_PATTERN.match(match.group(1)):
            months.add(match.group(1))
    return sorted(months)


def read_high_water_mark(full_rebuild=False):
    """Return the newest month already partitioned on disk, or None.

    The month is in the path, so this is a string max over directory names. It does
    not need a query engine, and an earlier version that asked DuckDB for it was
    doing real work to answer a question Python already held the answer to: the call
    measured 26ms against 0.4ms of connection overhead, read no column data, and
    still crashed CI with an internal assertion when the file set shrank between two
    reads in the same process. Parsing the path is simpler, faster and total.

    The claim this supports is unchanged and is the point: the mark is DERIVED from
    the data rather than stored beside it, so there is no second source of truth to
    drift and a half-finished run self-heals.
    """
    if full_rebuild:
        print(f"[{datetime.now()}] --full requested. Rebuilding from scratch.")
        return None

    months = months_on_disk()
    if not months:
        print(f"[{datetime.now()}] No bronze partitions found. Running a FULL load.")
        return None

    latest = months[-1]
    print(f"[{datetime.now()}] Partitions found up to {latest}. Running an INCREMENTAL load.")
    return latest


def request_chunk(offset):
    """Fetch one page, retrying transient failures with exponential backoff.

    Retries are bounded, and only transient failures are retried. A 404 or a 400 is
    a defect in this script or a dataset that has moved; the previous version spent
    62 seconds of backoff on five identical doomed requests before reporting it.
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

            # Fail fast on the rest of the 4xx range. These are client errors: the
            # same request will be just as wrong on every retry, so backing off five
            # times only delays the report. IngestError is not a RequestException,
            # so it leaves the retry loop instead of being caught below.
            if 400 <= response.status_code < 500:
                raise IngestError(
                    f"HTTP {response.status_code} at offset {offset} -- not retryable."
                    f" Response: {response.text[:200]}"
                )

            response.raise_for_status()
            payload = response.json()

            # data.gov.sg answers a bad resource_id with HTTP 200 and success=false.
            # Reading ["result"] straight off that raised KeyError: result, which
            # points the blame at this file rather than at the API that refused.
            if not payload.get("success"):
                raise IngestError(
                    f"API returned success=false at offset {offset}:"
                    f" {payload.get('error', payload)}"
                )

            return payload["result"]

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
    """Page through the API newest-first. Returns the records and the API's total.

    Every month at or after `latest_month` comes back complete: rows are sorted
    newest-first, so paging stops only once a row OLDER than the mark appears, by
    which point that month has been read in full. That completeness is what lets
    write_partitions replace a month wholesale instead of merging into it.
    """
    records = []
    offset = 0
    api_total = None

    while True:
        result = request_chunk(offset)

        if api_total is None:
            api_total = result.get("total")
            if api_total is None:
                print("API did not report a total record count.")
            else:
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


def partition_dir(month):
    """Build the Hive partition directory for one month, refusing anything else.

    The month arrives from the API and is interpolated into a filesystem path, so it
    is validated as a path component first. A value like ../../etc or a stray empty
    string would otherwise write outside the bronze root, and a value like 2024-6
    would write a directory that month=* still matches but that sorts wrongly
    against 2024-06 -- silently corrupting the high-water mark on the next run.
    """
    if not isinstance(month, str) or not MONTH_PATTERN.match(month):
        raise IngestError(f"Refusing to write a partition for malformed month {month!r}.")
    return f"{BRONZE_ROOT}/month={month}"


def write_partitions(df):
    """Write one parquet file per month, replacing each month wholesale.

    Returns {month: rows written}.
    """
    written = {}

    for month, group in df.groupby("month", sort=True):
        directory = partition_dir(month)
        os.makedirs(directory, exist_ok=True)

        target = f"{directory}/part-0.parquet"
        tmp = f"{directory}/.part-0.parquet.tmp"

        # month is dropped from the file body because DuckDB adds it back from the
        # path under hive_partitioning, and carrying it in both places is a
        # duplicate column name that the reader rejects outright.
        try:
            group.drop(columns=["month"]).to_parquet(tmp, index=False)
            # os.replace is atomic on POSIX and overwrite-capable on Windows, so a
            # concurrent reader sees either the old month or the new one, never a
            # half-written partition.
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

        written[month] = len(group)

    print(f"Wrote {sum(written.values()):,} records across {len(written)} month partition(s).")
    if written:
        months = sorted(written)
        print(f"  Partitions touched: {months[0]} -> {months[-1]}")
    return written


def summarise(api_total):
    """Report coverage from disk, flagging any shortfall against the API total."""
    files = partition_files()
    if not files:
        print("\nNo partitions on disk.")
        return

    with duckdb.connect() as con:
        rows, first, last, partitions = con.execute(
            """
            SELECT count(*), min(month), max(month), count(DISTINCT month)
            FROM read_parquet(?, hive_partitioning = true)
            """,
            [files],
        ).fetchone()

    print(f"\nRows on disk : {rows:,} across {partitions} partitions")
    print(f"Month range  : {first} -> {last}")

    if api_total is None:
        return

    missing = api_total - rows
    if missing > 0:
        print(
            f"\nWARNING: the API holds {api_total:,} records; this layer has {rows:,}."
            f"\n         {missing:,} transactions are missing, all older than {first}."
            f"\n         Incremental runs only move forward and will never fetch them."
            f"\n         Run 'python ingest_hdb.py --full' to backfill."
        )
    else:
        print("Coverage     : complete against the API total.")


def build_bronze_hdb(full_rebuild=False):
    """Fetch from the high-water mark onward and land it as month partitions."""
    latest_month = read_high_water_mark(full_rebuild=full_rebuild)

    if latest_month is not None:
        print(f"High-water mark: {latest_month} (re-fetched to catch late transactions)")

    records, api_total = fetch_records(latest_month)

    if not records:
        # Previously this fell through to a no-op save that printed nothing at all,
        # leaving no way to tell "already current" apart from silent failure.
        print("\nNo new records returned. Already up to date.")
        summarise(api_total)
        return {}

    new_df = pd.DataFrame(records)
    new_df["_ingested_at"] = pd.Timestamp.now(tz="UTC")

    written = write_partitions(new_df)
    summarise(api_total)
    return written


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--full",
        action="store_true",
        help="Ignore what is on disk and re-fetch the entire history.",
    )
    args = parser.parse_args()
    build_bronze_hdb(full_rebuild=args.full)
