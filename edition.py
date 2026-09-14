"""Read the published edition: the only data the dashboard and FINDINGS.md ever see.

An edition is a committed snapshot of the warehouse's published outputs, stamped
with the data cut it was built from. Reading it needs pandas and nothing else -- no
DuckDB, no dbt, no warehouse -- which is what lets the dashboard run on a host that
has never seen the pipeline.

publish_edition.py is the only thing that writes one.
"""

import json
import os

import pandas as pd

EDITION_DIR = "published"
STAMP_FILE = "edition.json"
SALES_FILE = "sales.parquet"


def read_stamp(root=EDITION_DIR):
    """{data_through: 'YYYY-MM', sales: int, published_on: 'YYYY-MM-DD', tables: [...]}"""
    with open(os.path.join(root, STAMP_FILE), encoding="utf-8") as f:
        return json.load(f)


def read_table(name, root=EDITION_DIR):
    """One published mart, by name."""
    return pd.read_csv(os.path.join(root, f"{name}.csv"))


def read_sales(root=EDITION_DIR):
    """Every transaction, joined to its dimensions. Backs the free-filter views."""
    return pd.read_parquet(os.path.join(root, SALES_FILE))
