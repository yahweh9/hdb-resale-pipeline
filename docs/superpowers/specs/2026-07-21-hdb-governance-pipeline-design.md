# HDB Data Quality & Governance Pipeline — Design

Date: 2026-07-21

## Context

The existing HDB project (`C:\Users\wrigh\Desktop\HDB`) is a set of flat Python scripts implementing a bronze/silver/gold pipeline over local parquet files: `ingest_hdb.py` (data.gov.sg HDB resale), `ingest_schools.py` (currently a duplicate/broken copy of the HDB incremental fetch — does not actually ingest schools), `clean_mrt_data.py` (static local CSV, not live API), `onemap_utils.py` (OneMap geocoding via email/password login), `silver_spatial_join.py` and `silver_features.py` (feature engineering: haversine distances, elite-school proximity, mall density, lease decay), `gold_analytics.py` / `gold_postgres_analytics.py` (DuckDB/Postgres aggregation), and `dashboard.py` (Streamlit).

Key finding that motivates this project: `silver_features.py` line 45 does `df.dropna(subset=['latitude', 'longitude'])`, which **silently deletes** rows that failed geocoding (confirmed: 18 of 50,000 rows, from 23 addresses OneMap couldn't resolve) with no logging, no record of which addresses failed, and no way to audit data-quality drift over time. This is the exact anti-pattern the new pipeline replaces with quarantine + audit trail.

Live-endpoint verification (done during design, 2026-07-21):
- HDB resale (`d_8b84c4ee58e3cfc0ece0d773c8ca6abc`) and school locations (`d_688b934f82c1059ed0a6993d2a829089`) datastore_search endpoints: resolve, HTTP 200, **no API key required**. HDB resale currently has 235,938 total records (Jan 2017–present), not the ~150,000 the brief estimated.
- MRT poll-download (`d_8d886e3a83934d7447acdf5bc6959999`): works as documented, but anonymous requests are rate-limited (hit a 429 on first call, recovered after 12s) — pipeline needs retry/backoff.
- OneMap `/api/auth/post/getToken`: still live, still email/password based (confirmed via a real request that returned a genuine validation error, not a 404/deprecation notice) — existing auth pattern in `onemap_utils.py` is reusable as-is.

## Decisions made during brainstorming

1. **Data source**: live APIs (data.gov.sg + OneMap + MRT poll-download), not the existing local files — matches the brief and the resume framing.
2. **Data volume**: full history, ~236k HDB resale records, not a bounded recent window.
3. **Raw ingestion strategy**: incremental fetch (reuse the existing "only pull rows newer than what we have" pattern from `ingest_hdb.py`), each new record appended as its own timestamped row in `raw.hdb_resale_snapshot`. First run naturally pulls full history since the table starts empty.
4. **Validation granularity**: each run validates only the batch of rows newly landed in that run (not the whole staging table), with every `audit.validation_results` row and every quarantined row tagged with that run's `run_id`.
5. **Project layout**: scaffolded Dagster package (`hdb_pipeline/`), not flat scripts — required for validators to be unit-testable with no DB/Dagster running.
6. **Storage architecture**: full move from parquet-file bronze/silver/gold to Postgres-backed `raw`/`staging`/`marts`/`audit` schemas (medallion architecture, renamed + audited + SQL-queryable). The audit trail only answers governance questions if it's joinable against the data it audits, which requires everything living in the same database. Existing local parquet files are left on disk, unused by the new pipeline.
7. **Existing extras** (Streamlit dashboard, richer feature engineering — elite schools, malls, lease decay/Bala's curve): kept, layered on top. `marts.hdb_proximity_features` is built exactly to the brief's schema; the richer feature set becomes a second mart (`marts.hdb_extended_features`) built from it; `dashboard.py` gets repointed at the new Postgres schema instead of the old ad hoc `hdb_portfolio` tables.
8. **Docker/Dagster conventions**: designed fresh for this project, not copied from any other project on the machine.

## Project structure

```
HDB/
├── docker-compose.yml
├── docker/
│   └── init-db/
│       ├── 01_raw.sql
│       ├── 02_staging.sql
│       ├── 03_audit.sql
│       └── 04_marts.sql
├── hdb_pipeline/
│   ├── definitions.py
│   ├── assets/
│   │   ├── raw.py
│   │   ├── staging.py
│   │   └── marts.py
│   ├── asset_checks.py
│   ├── validators.py
│   ├── resources.py
│   ├── db.py
│   └── reference_data.py
├── legacy/                # existing dashboard.py + old scripts, kept for reference
├── tests/
│   └── test_validators.py
├── .env.example
├── requirements.txt
└── README.md
```

## Database schema

```sql
-- raw: append-only, one row per record per ingestion run
raw.hdb_resale_snapshot (id, run_id, fetched_at, raw_json JSONB)
raw.school_locations_snapshot (id, run_id, fetched_at, raw_json JSONB)
raw.mrt_stations_snapshot (id, run_id, fetched_at, raw_json JSONB)

-- staging: typed, cleaned, only rows that PASSED validation
staging.hdb_resale (
    id, source_raw_id, town, flat_type, block, street_name, storey_range,
    floor_area_sqm, flat_model, lease_commence_date, resale_price,
    month, latitude, longitude, fetched_at
)
staging.schools (id, school_name, address, latitude, longitude)
staging.mrt_stations (id, station_name, latitude, longitude)
staging.geocode_cache (address_query PK, latitude, longitude, matched_address, geocoded_at)

-- audit: the governance layer
audit.validation_results (
    id, run_id, asset_name, rule_name, rule_type, passed,
    rows_checked, rows_failed, details_json JSONB, checked_at
)
audit.quarantine (
    id, source_table, run_id, rule_name_failed, row_data_json JSONB,
    quarantined_at, resolved BOOLEAN DEFAULT FALSE
)

-- marts: analysis-ready
marts.hdb_proximity_features (
    id, town, flat_type, resale_price, floor_area_sqm,
    nearest_mrt_name, nearest_mrt_distance_km,
    nearest_school_name, nearest_school_distance_km,
    month, computed_at
)
marts.hdb_extended_features (
    -- ported from silver_features.py: dist_to_cbd_km, dist_to_elite_school_km,
    -- within_1km_elite_school, malls_within_2km, estate_maturity, floor_tier,
    -- remaining_lease_years, lease_critical_status, mrt_walk_time_mins
)
```

`source_raw_id` on `staging.hdb_resale` gives full lineage back to the exact raw row for audit purposes.

## Validation framework (`hdb_pipeline/validators.py`)

Rule engine per the brief's class shapes (`ValidationRule`, `ValidationResult`, `ValidationRunner`, and rule subclasses `SchemaDriftRule`, `NullCheckRule`, `OutlierRule`, `ReferentialIntegrityRule`, `DuplicateRule`).

Concretized choices:
- `SchemaDriftRule`: expected schema is a plain `{"col": "dtype"}` dict passed per call-site (no schema registry).
- `OutlierRule`: IQR with `k=1.5`; `group_by_cols` is required, no silent global fallback. For HDB resale: `["town", "flat_type"]`.
- `ReferentialIntegrityRule`: two modes — reference-set membership (canonical 26 HDB town names, in `reference_data.py`) or regex (postal code `^\d{6}$`).
- `DuplicateRule`: subset = `["block", "street_name", "month", "resale_price"]` (the API's `_id` is not a business key, excluded).
- Severity: `error` → row quarantined and excluded from staging; `warning` → logged but row still passes through. Schema drift and required-field nulls are always `error`. Outliers are `warning` (flags a real signal, not necessarily bad data).
- `ValidationRunner.run(df, rules, asset_name, run_id, table_name)`: runs every rule, writes one `audit.validation_results` row per rule (pass or fail), unions all `error`-severity failing row indices, splits the df into `(passing_df, quarantined_df)`, writes quarantined rows to `audit.quarantine` with `rule_name_failed` (one quarantine row per failing rule if a row fails more than one).

## Dagster orchestration

Assets (dependency order):
1. `raw_hdb_resale`, `raw_school_locations`, `raw_mrt_stations` — incremental fetch, write JSONB rows tagged with a fresh `run_id`; MRT/school fetch full snapshot each run (small datasets)
2. `validated_hdb_resale` — loads this run's new batch from `raw.hdb_resale_snapshot`, runs `ValidationRunner`, writes to `staging.hdb_resale` + `audit.*`
3. `staging_geocoded_hdb_resale` — checks `staging.geocode_cache` first, calls OneMap only for cache misses, backfills lat/long
4. `staging_schools`, `staging_mrt_stations` — same validate-then-land pattern, lighter rule sets
5. `marts_hdb_proximity_features` — haversine nearest-MRT/nearest-school join
6. `marts_hdb_extended_features` — ported richer feature set

Asset checks (`hdb_pipeline/asset_checks.py`, separate from the custom validators):
- `staging_hdb_resale_nonempty` — did this run land any rows
- `quarantine_rate_check` — WARN if this run's quarantine rate > 20% (signal of upstream schema change vs. normal messiness)

## Docker

`docker-compose.yml`: `warehouse_postgres` (port 5433, schema DDL mounted via `docker/init-db/*.sql` into `docker-entrypoint-initdb.d`), `dagster_postgres` (Dagster's own run/event storage), `dagster_webserver` (port 3000), `dagster_daemon`. Secrets via `.env` (gitignored; `.env.example` committed): `API_KEY`, `ONEMAP_EMAIL`, `ONEMAP_PASSWORD`, warehouse Postgres connection string.

## Testing

`tests/test_validators.py`, pure pytest, no DB/network:
- One test class per rule, each with a small synthetic DataFrame (3-4 clean rows, 2-3 deliberately broken: missing column, null in required field, a price far outside its group's IQR bound, an invalid town name, an exact duplicate)
- Assertions on `ValidationResult.passed`, `failing_row_indices`, `details`
- One test for `ValidationRunner.run()` (in-memory sqlite or mocked DB write) checking pass/fail split and quarantine attribution

## README

Leads with what the pipeline does, then a dedicated "why quarantine instead of delete" section naming the actual bug found in the current code (`silver_features.py`'s silent `dropna` losing 18 real rows) as the motivating example, ties it to data-integrity/audit-trail concepts and the SAF Cyber Operator connection, includes an ASCII architecture diagram, setup instructions, and a sample query against `audit.validation_results` answering "did data quality degrade last week."

## Resume framing (unchanged from brief)

"Built a governed data pipeline for Singapore HDB resale data, implementing a custom validation framework (schema drift, null, outlier, referential integrity, and duplicate checks) that quarantines failing records with a full audit trail rather than silently dropping them — orchestrated with Dagster and containerized with Docker."
