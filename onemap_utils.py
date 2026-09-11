"""Geocode HDB block addresses and school postal codes via OneMap into Bronze.

Runs incrementally by default: reads the coordinates already on disk and requests
only the addresses missing from it. A geocoded address never changes, so unlike the
resale ingest there is no overlap window to re-fetch -- an address either has
coordinates or it does not. Pass --full to re-request everything.

This matters at the current scale: the Bronze layer holds 9,738 unique addresses,
so a full rebuild is ~33 minutes of API calls, while topping up the missing few
hundred takes about two.

Addresses that cannot be resolved are reported by name and reason at the end of the
run rather than dropped in silence, since a missing coordinate silently removes
those transactions from the silver layer downstream.

Outputs:
    data/bronze/hdb_coordinates.parquet       address, latitude, longitude, postal_code
    data/bronze/schools_coordinates.parquet   same shape, keyed by postal code
"""

import argparse
import os
import time
from datetime import datetime

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

# .strip() because a trailing newline in .env silently breaks authentication with
# an unhelpful 400 rather than an obvious credential error.
raw_email = os.getenv("ONEMAP_EMAIL")
raw_password = os.getenv("ONEMAP_PASSWORD")
ONEMAP_EMAIL = raw_email.strip() if raw_email else None
ONEMAP_PASSWORD = raw_password.strip() if raw_password else None

HDB_SOURCE = "data/bronze/hdb_resale"  # partitioned dataset; pyarrow discovers month=*
SCHOOL_SOURCE = "data/bronze/schools_raw.parquet"
OUTPUT_PATH = "data/bronze/hdb_coordinates.parquet"
OUTPUT_PATH2 = "data/bronze/schools_coordinates.parquet"

TOKEN_URL = "https://www.onemap.gov.sg/api/auth/post/getToken"
SEARCH_URL = "https://www.onemap.gov.sg/api/common/elastic/search"

REQUEST_DELAY = 0.2  # ~5 requests/sec is comfortably within OneMap's limits
MAX_RETRIES = 4
BACKOFF_BASE = 2
PROGRESS_EVERY = 250

# Singapore's bounding box. A geocoder returning a plausible-looking point outside
# these bounds means the search matched something else entirely, which is worth
# rejecting loudly rather than carrying into distance calculations.
LAT_RANGE = (1.15, 1.48)
LON_RANGE = (103.6, 104.1)


class GeocodeError(RuntimeError):
    """Raised when OneMap cannot be reached or authenticated against."""


def get_onemap_token():
    """Authenticate with OneMap and return a JWT, or raise."""
    if not ONEMAP_EMAIL or not ONEMAP_PASSWORD:
        raise GeocodeError(
            "ONEMAP_EMAIL / ONEMAP_PASSWORD are missing from the environment."
        )

    try:
        response = requests.post(
            TOKEN_URL,
            json={"email": ONEMAP_EMAIL, "password": ONEMAP_PASSWORD},
            timeout=10,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        detail = ""
        if getattr(e, "response", None) is not None:
            detail = f" Server said: {e.response.text[:200]}"
        raise GeocodeError(f"OneMap authentication failed.{detail}") from e

    token = response.json().get("access_token")
    if not token:
        raise GeocodeError("OneMap returned no access_token.")
    return token


def load_existing(path):
    """Return coordinates already on disk, or None."""
    if not os.path.exists(path):
        return None
    return pd.read_parquet(path)


def geocode_one(address, token):
    """Resolve one address. Returns (record, failure_reason); exactly one is None."""
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "searchVal": address,
        "returnGeom": "Y",
        "getAddrDetails": "Y",
        "pageNum": "1",
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(SEARCH_URL, params=params, headers=headers, timeout=10)

            if response.status_code == 429:
                # The previous version called `continue` on the enclosing for-loop
                # here, which advanced to the NEXT address -- so a rate-limited
                # address was dropped permanently instead of retried.
                if attempt == MAX_RETRIES:
                    return None, "rate-limited after retries"
                time.sleep(BACKOFF_BASE**attempt)
                continue

            response.raise_for_status()
            data = response.json()

            if not data.get("found"):
                return None, "no match returned"

            best = data["results"][0]
            lat, lon = float(best["LATITUDE"]), float(best["LONGITUDE"])

            if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LON_RANGE[0] <= lon <= LON_RANGE[1]):
                return None, f"coordinates outside Singapore ({lat}, {lon})"

            return {
                "address": address,
                "latitude": lat,
                "longitude": lon,
                "postal_code": best.get("POSTAL"),
            }, None

        except requests.exceptions.RequestException as e:
            if attempt == MAX_RETRIES:
                return None, f"{type(e).__name__} after {MAX_RETRIES} attempts"
            time.sleep(BACKOFF_BASE**attempt)
        except (KeyError, ValueError, TypeError) as e:
            # A malformed payload is a data problem, not a transport one; retrying
            # will not help. Previously a bare `except Exception` swallowed these
            # and the address vanished without explanation.
            return None, f"unparseable response ({type(e).__name__}: {e})"

    return None, "retries exhausted"


def geocode_addresses(addresses, token):
    """Geocode a list of addresses. Returns (DataFrame, list of (address, reason))."""
    results = []
    failures = []

    print(f"[{datetime.now()}] Geocoding {len(addresses):,} addresses...")

    for i, address in enumerate(addresses, start=1):
        record, reason = geocode_one(address, token)
        if record is not None:
            results.append(record)
        else:
            failures.append((address, reason))

        if i % PROGRESS_EVERY == 0:
            print(f"  {i:,}/{len(addresses):,} done ({len(failures)} failed)")

        time.sleep(REQUEST_DELAY)

    return pd.DataFrame(results), failures


def report_failures(failures):
    """List every unresolved address so a silent gap cannot form downstream."""
    if not failures:
        return
    print(f"\n{len(failures)} address(es) could not be geocoded:")
    for address, reason in failures[:50]:
        print(f"    {address:40s} {reason}")
    if len(failures) > 50:
        print(f"    ... and {len(failures) - 50} more")


def merge_and_save(existing_df, new_df, path, label):
    """Append newly geocoded rows to whatever was already on disk."""
    if new_df.empty and existing_df is None:
        print(f"Nothing to save for {label}.")
        return None

    combined = new_df if existing_df is None else pd.concat([existing_df, new_df], ignore_index=True)

    before = len(combined)
    combined = combined.drop_duplicates(subset=["address"], keep="last")
    if before != len(combined):
        print(f"Dropped {before - len(combined):,} duplicate address rows.")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    combined.to_parquet(path, index=False)
    print(f"Saved {len(combined):,} {label} coordinates to {path}")
    return combined


def resolve_missing(wanted, existing_df, full_rebuild, label):
    """Work out which addresses still need a lookup."""
    if full_rebuild or existing_df is None:
        print(f"{label}: geocoding all {len(wanted):,} addresses.")
        return wanted, (None if full_rebuild else existing_df)

    known = set(existing_df["address"])
    missing = [a for a in wanted if a not in known]
    print(
        f"{label}: {len(wanted):,} unique addresses, {len(known):,} already geocoded,"
        f" {len(missing):,} to fetch."
    )
    return missing, existing_df


def build_bronze_geodata(full_rebuild=False):
    """Geocode every unique HDB block address in the Bronze resale file."""
    if not os.path.exists(HDB_SOURCE):
        raise GeocodeError(f"{HDB_SOURCE} not found. Run ingest_hdb.py first.")

    hdb_df = pd.read_parquet(HDB_SOURCE)
    hdb_df["address"] = hdb_df["block"] + " " + hdb_df["street_name"]
    wanted = sorted(hdb_df["address"].dropna().unique())

    existing_df = None if full_rebuild else load_existing(OUTPUT_PATH)
    missing, existing_df = resolve_missing(wanted, existing_df, full_rebuild, "HDB")

    if not missing:
        print("HDB coordinates already complete. Nothing to do.")
        return existing_df

    new_df, failures = geocode_addresses(missing, get_onemap_token())
    report_failures(failures)
    return merge_and_save(existing_df, new_df, OUTPUT_PATH, "HDB")


def build_bronze_school_data(full_rebuild=False):
    """Geocode schools by postal code, which resolves far more reliably than names."""
    if not os.path.exists(SCHOOL_SOURCE):
        raise GeocodeError(f"{SCHOOL_SOURCE} not found.")

    school_df = pd.read_parquet(SCHOOL_SOURCE)
    # Zero-pad: postal codes stored as integers lose a leading zero (e.g. 048123).
    # sorted(set(...)) because several schools share a postal code, and the old code
    # geocoded the raw list -- paying for duplicate lookups and writing duplicate rows.
    wanted = sorted(set(school_df["postal_code"].astype(str).str.zfill(6)))

    existing_df = None if full_rebuild else load_existing(OUTPUT_PATH2)
    missing, existing_df = resolve_missing(wanted, existing_df, full_rebuild, "Schools")

    if not missing:
        print("School coordinates already complete. Nothing to do.")
        return existing_df

    new_df, failures = geocode_addresses(missing, get_onemap_token())
    report_failures(failures)
    return merge_and_save(existing_df, new_df, OUTPUT_PATH2, "school")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--target",
        choices=["hdb", "schools", "both"],
        default="both",
        help="Which coordinate set to build (default: both).",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Re-geocode everything instead of only the missing addresses.",
    )
    args = parser.parse_args()

    if args.target in ("hdb", "both"):
        build_bronze_geodata(full_rebuild=args.full)
    if args.target in ("schools", "both"):
        build_bronze_school_data(full_rebuild=args.full)
