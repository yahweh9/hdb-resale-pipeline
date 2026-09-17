"""Shared fixtures for the ingest tests.

Every test here runs offline. The API is faked and the bronze layer is redirected
into a tmp_path, so nothing touches data.gov.sg or the real data/ directory.
"""

import pandas as pd
import pytest

from ingest import hdb_resale


@pytest.fixture
def bronze(tmp_path, monkeypatch):
    """Point the ingest at a throwaway bronze root and yield its path."""
    root = tmp_path / "bronze" / "hdb_resale"
    # as_posix() matters: PARTITION_GLOB is handed to DuckDB, which does not treat a
    # Windows backslash as a path separator.
    monkeypatch.setattr(hdb_resale, "BRONZE_ROOT", root.as_posix())
    monkeypatch.setattr(hdb_resale, "PARTITION_GLOB", f"{root.as_posix()}/month=*/*.parquet")
    return root


@pytest.fixture(autouse=True)
def no_sleeping(monkeypatch):
    """Retry backoff is real seconds. Tests should not spend them."""
    monkeypatch.setattr(hdb_resale.time, "sleep", lambda _seconds: None)


def records(month, ids):
    """A minimal frame shaped like what the API returns, plus _ingested_at."""
    ids = list(ids)
    return pd.DataFrame(
        {
            "_id": ids,
            "month": [month] * len(ids),
            "town": ["ANG MO KIO"] * len(ids),
            "resale_price": ["500000"] * len(ids),
            "_ingested_at": pd.Timestamp("2026-09-09", tz="UTC"),
        }
    )
