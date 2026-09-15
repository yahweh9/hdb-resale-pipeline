"""Publish an edition: the one bridge between the warehouse and anything a person sees.

Writes every published mart as CSV, every transaction as one parquet file, and a
stamp naming the data cut, into a directory that is committed to the repository.
The dashboard and FINDINGS.md read only that directory, so what the live dashboard
shows and what the document says are always the same edition.

Publishing is deliberate, not scheduled. The monthly ingest keeps the warehouse
current; an edition changes only when someone runs this, re-reads the prose in
FINDINGS.md against the new numbers, and commits both together.

    dbt build
    python publish_edition.py
    python render_findings.py
"""

import argparse
import datetime as dt
import json
import os

import duckdb

import edition

WAREHOUSE = os.getenv("DUCKDB_PATH", "data/warehouse.duckdb")

# Published marts, in the order the stamp lists them. A mart that is not named here is
# not part of the edition, however finished it looks in the warehouse.
MART_TABLES = [
    "mart_mrt_premium_by_band",
    "mart_price_index",
    "mart_model_vs_naive",
    "mart_effects_by_year",
]

# One join per dimension -- the star the dashboard used to query directly. The ingest
# timestamp is left behind: the stamp says which data this is, and a per-row load time
# is pipeline bookkeeping that means nothing to a reader.
SALES_QUERY = """
select
    d.transaction_month,
    d.calendar_year,
    t.town,
    t.region,
    t.is_mature_estate,
    f.flat_type,
    f.floor_tier,
    b.dist_to_nearest_mrt_km,
    b.dist_to_cbd_km,
    b.is_near_mrt,
    x.resale_price,
    x.price_psm,
    x.floor_area_sqm,
    x.remaining_lease_months
from gold.fact_resale_txn x
join gold.dim_date  d using (date_key)
join gold.dim_town  t using (town_key)
join gold.dim_flat  f using (flat_key)
join gold.dim_block b using (block_key)
-- Deterministic row order, so republishing unchanged data rewrites an identical file
-- and git records no change, rather than a 2MB binary diff of shuffled rows.
order by x.resale_txn_key
"""


class PublishError(Exception):
    """The warehouse is not in a state worth publishing."""


def publish(con, out_dir, published_on):
    """Write the edition into `out_dir` and return its stamp.

    Checks before writing anything, so a refused publish leaves the previous edition
    exactly as it was. A publish that fails partway can leave a mix of old and new
    files; the directory is under version control, so `git checkout published/`
    puts it back.
    """
    sales, data_through = con.execute(
        "select count(*), strftime(max(transaction_month), '%Y-%m') from gold.fact_resale_txn"
    ).fetchone()
    if sales == 0:
        raise PublishError("The fact table is empty; refusing to publish a zero-sale edition.")

    os.makedirs(out_dir, exist_ok=True)

    for table in MART_TABLES:
        con.execute(f"select * from marts.{table}").df().to_csv(
            os.path.join(out_dir, f"{table}.csv"), index=False
        )

    con.execute(SALES_QUERY).df().to_parquet(
        os.path.join(out_dir, edition.SALES_FILE), index=False, compression="zstd"
    )

    stamp = {
        "data_through": data_through,
        "sales": int(sales),
        "published_on": published_on,
        "tables": list(MART_TABLES),
    }
    with open(os.path.join(out_dir, edition.STAMP_FILE), "w", encoding="utf-8") as f:
        json.dump(stamp, f, indent=2)
        f.write("\n")
    return stamp


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=edition.EDITION_DIR,
                        help="Directory to write the edition into (default: published).")
    parser.add_argument("--published-on", default=dt.date.today().isoformat(),
                        help="Publication date for the stamp, YYYY-MM-DD (default: today).")
    args = parser.parse_args()

    with duckdb.connect(WAREHOUSE, read_only=True) as con:
        stamp = publish(con, args.out, args.published_on)
    print(f"Published {stamp['sales']:,} sales through {stamp['data_through']} to {args.out}")


if __name__ == "__main__":
    main()
