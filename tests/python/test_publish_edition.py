"""The edition: what leaves the warehouse, and the stamp that says which data it is.

Every test builds a throwaway in-memory warehouse shaped like gold and marts, so
nothing here needs dbt, the real warehouse, or the network.
"""

import json

import duckdb
import pytest

import edition
import publish_edition


def warehouse(sales_rows=3):
    """A tiny gold star plus one mart, with `sales_rows` fact rows."""
    con = duckdb.connect(":memory:")
    con.execute("create schema gold")
    con.execute("create schema marts")
    con.execute("""
        create table gold.dim_date as
        select * from (values
            (202601, date '2026-01-01', 2026),
            (202609, date '2026-09-01', 2026)
        ) t(date_key, transaction_month, calendar_year)
    """)
    con.execute("""
        create table gold.dim_town as
        select 't1' town_key, 'ANG MO KIO' town, 'North-East' region, true is_mature_estate
    """)
    con.execute("""
        create table gold.dim_flat as
        select 'f1' flat_key, '4 ROOM' flat_type, 'Low (1-4)' floor_tier
    """)
    con.execute("""
        create table gold.dim_block as
        select 'b1' block_key, 0.35 dist_to_nearest_mrt_km, '0-400m' mrt_band, 1 mrt_band_order,
               9.1 dist_to_cbd_km, true is_near_mrt
    """)
    con.execute(f"""
        create table gold.fact_resale_txn as
        select
            'txn' || i as resale_txn_key,
            case when i % 2 = 0 then 202601 else 202609 end as date_key,
            'f1' flat_key, 't1' town_key, 'b1' block_key,
            case when i % 2 = 0 then date '2026-01-01' else date '2026-09-01' end as transaction_month,
            500000.0 + i resale_price, 5000.0 price_psm, 100.0 floor_area_sqm,
            720 remaining_lease_months, now() _ingested_at
        from range({sales_rows}) r(i)
    """)
    con.execute("""
        create table marts.mart_mrt_premium_by_band as
        select * from (values
            (1, '0-400m', 2, 5500.0, 10.0),
            (4, 'over 1.2km', 1, 5000.0, 0.0)
        ) t(band_order, mrt_band, sales, median_price_psm, premium_vs_farthest_pct)
    """)
    # Every other published mart only has to exist: these tests are about the export,
    # and the marts' own columns are tested where dbt builds them.
    for table in publish_edition.MART_TABLES:
        con.execute(f"create table if not exists marts.{table} as select 1 as placeholder")
    return con


def test_publish_writes_every_file_the_edition_promises(tmp_path):
    publish_edition.publish(warehouse(), tmp_path, "2026-09-14")

    assert (tmp_path / "mart_mrt_premium_by_band.csv").exists()
    assert (tmp_path / edition.SALES_FILE).exists()
    assert (tmp_path / edition.STAMP_FILE).exists()


def test_the_stamp_names_the_data_cut_not_the_day_it_was_written(tmp_path):
    stamp = publish_edition.publish(warehouse(sales_rows=3), tmp_path, "2026-09-14")

    assert stamp == edition.read_stamp(tmp_path)
    assert stamp["data_through"] == "2026-09"
    assert stamp["sales"] == 3
    assert stamp["published_on"] == "2026-09-14"
    assert stamp["tables"] == publish_edition.MART_TABLES


def test_a_mart_round_trips_through_the_reader_unchanged(tmp_path):
    con = warehouse()
    publish_edition.publish(con, tmp_path, "2026-09-14")

    expected = con.execute("select * from marts.mart_mrt_premium_by_band").df()
    actual = edition.read_table("mart_mrt_premium_by_band", tmp_path)

    assert list(actual.columns) == list(expected.columns)
    assert actual["sales"].tolist() == expected["sales"].tolist()


def test_sales_has_one_row_per_transaction_and_no_ingest_bookkeeping(tmp_path):
    publish_edition.publish(warehouse(sales_rows=5), tmp_path, "2026-09-14")

    sales = edition.read_sales(tmp_path)

    assert len(sales) == 5
    assert "_ingested_at" not in sales.columns
    assert {"town", "flat_type", "price_psm", "dist_to_nearest_mrt_km"} <= set(sales.columns)


def test_an_empty_warehouse_is_refused_rather_than_published(tmp_path):
    # A zero-sale edition would render every chart blank and stamp "0 sales" on
    # FINDINGS.md. That is a broken build, not a quiet month.
    with pytest.raises(publish_edition.PublishError):
        publish_edition.publish(warehouse(sales_rows=0), tmp_path, "2026-09-14")

    assert not (tmp_path / edition.STAMP_FILE).exists()


def test_the_stamp_file_is_stable_json(tmp_path):
    publish_edition.publish(warehouse(), tmp_path, "2026-09-14")

    text = (tmp_path / edition.STAMP_FILE).read_text(encoding="utf-8")

    assert json.loads(text)["sales"] == 3
    assert text.endswith("\n")
