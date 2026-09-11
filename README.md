# HDB Resale Price Pipeline

An incremental ELT pipeline over Singapore's HDB resale transaction data, built to
demonstrate data engineering practice rather than exploratory analysis.

Raw data is pulled from a live public API, landed immutably as month partitions,
modelled into a dimensional schema with dbt, tested for quality, and scheduled with
GitHub Actions.

> **Why another HDB project?** Most HDB projects are a notebook that plots median
> price by town. This one is about the pipeline: idempotent ingestion, an immutable
> raw layer, incremental modelling, and automated data quality tests that fail the
> build.

---

## Architecture

```
 data.gov.sg API        Wikidata (SPARQL)        OneMap API
       |                       |                     |
       v                       v                     v
 ingest_hdb.py          ingest_mrt_data.py    onemap_utils.py
 month partitions       fetch + archive       geocode 9,744 blocks
       |                       |                     |
       +-----------------------+---------------------+
                               v
                     +-------------------+
                     |  data/bronze/     |  Immutable. Parquet only.
                     +---------+---------+
                               v
                     +-------------------+
                     |  DuckDB           |  Reads the parquet in place.
                     +---------+---------+  No load step.
                               v
                     +-------------------+
                     |  dbt              |  silver (3) -> gold (5)
                     +---------+---------+  55 data tests
                               v
                     +-------------------+
                     |  dashboard.py     |  Streamlit, reads gold only
                     +-------------------+

Scheduled and tested by GitHub Actions.
```

---

## Data source

[HDB Resale Flat Prices](https://data.gov.sg) -- data.gov.sg, resource
`d_8b84c4ee58e3cfc0ece0d773c8ca6abc`, updated monthly.

- **Records:** 240,074 resale transactions
- **Date range:** 2017-01 to 2026-09, across 117 monthly partitions
- **Grain:** one row per resale transaction
- **Distinct block addresses:** 9,744, all geocoded

**Two reference sources are joined to it:**

- **MRT/LRT stations** from [Wikidata](https://query.wikidata.org) (CC0), via SPARQL.
  181 operational stations. Deliberately broader than "metro station", which would drop
  all 42 LRT stations, and filtered by transport mode rather than by station code, which
  would drop 27 coded-but-real stations including Changi Airport.
- **Block coordinates** from [OneMap](https://www.onemap.gov.sg), Singapore's national
  mapping service. All 9,744 block addresses resolved, none failed.

**Why this source:** it is genuinely public, updates on a real cadence, and arrives
with the messiness that makes ingestion non-trivial. Every column comes back as a
string. `remaining_lease` carries two different formats depending on the vintage of
the row. `flat_model` appears in 20 different mixed-case spellings. `flat_type` is
hyphenated here and unhyphenated in the pre-2017 companion dataset. And a month
stays open: transactions keep registering against 2026-09 for weeks after September
begins, so "already fetched" is not the same as "finished".

**What the data actually says** is a separate document: [FINDINGS.md](FINDINGS.md).
Six results with their sample sizes, what each one cannot tell you, and one hypothesis
that was tested and did not hold.

---

## Stack

| Layer | Tool | Why |
|---|---|---|
| Ingestion | Python (`requests`) | Full control over pagination, retries, idempotency |
| Storage | Local parquet, Hive-partitioned by month | Immutable per partition, cheap to re-read |
| Warehouse | DuckDB | Zero infrastructure, columnar, reads the parquet glob in place |
| Transformation | dbt | Dependency DAG, tests, docs, lineage |
| Orchestration | GitHub Actions | Scheduled ingest, full build and test on every PR |
| Geocoding | OneMap API | National mapping service, authoritative for SG addresses |
| Reference data | Wikidata (SPARQL) | CC0, so no attribution or share-alike obligation |
| Serving | Streamlit + Altair | One command, no server to run, reads the gold layer only |

---

## Data model

A star schema. Dimensions are deliberately denormalized -- the redundancy compresses
away columnar, and every query stays a single join from the fact table.

```
     dim_date     dim_town     dim_flat     dim_block
         |            |            |            |
         +------------+------+-----+------------+
                             |
                     fact_resale_txn
```

| Model | Grain | Rows |
|---|---|---|
| `fact_resale_txn` | one resale transaction | 240,074 |
| `dim_date` | one transaction month | 117 |
| `dim_town` | one town | 26 |
| `dim_flat` | flat type x flat model x storey range | 379 |
| `dim_block` | one physical block address, with coordinates and MRT proximity | 9,744 |
| `silver_hdb_coordinates` | one geocoded block address | 9,744 |
| `silver_mrt_stations` | one operational MRT/LRT station | 181 |

**`fact_resale_txn`** -- measures: `resale_price`, `price_psm`, `floor_area_sqm`,
`remaining_lease_months`. `source_txn_id` is carried as a degenerate dimension so any
fact row can be traced back to the bronze partition it came from.

**`dim_block` carries the spatial attributes**, not the fact. Location is a property of
the block, so `dist_to_nearest_mrt_km` on the fact would store the same value across
every sale in that block -- 240,074 rows to describe 9,744 things. The nearest station is
found by a 9,744 x 181 cross join, which DuckDB resolves in under a second; a spatial
index is the answer at a hundred times this size.

That join produces the one genuine finding in the project so far: **flats within 400m of
a station sell for a 7.2% premium** -- a median of S$5,568/sqm against S$5,194 -- across
all 240,074 transactions. 400m is the walkability threshold HDB and URA use in their own
accessibility studies.

**`dim_flat` is Type 1, deliberately.** These attributes describe the flat *as sold*
on that date. They do not change afterwards, so there is no later version of the row
for a Type 2 history to preserve -- a `valid_from`/`valid_to` pair here would carry
no information. The same reasoning covers `dim_town`: when HDB reclassifies a town's
planning region, the correct answer is that it always belonged to the new one.
Nothing in this schema has a genuine slowly-changing attribute, and adding SCD2
machinery to prove familiarity with it would be worse than not having it.

**Dimension keys are hashed, not joined.** The fact computes `town_key` with the same
`generate_surrogate_key(['town'])` that builds `dim_town`, so it never joins to a
dimension to get a foreign key. That removes any fan-out risk from a dimension that
turns out not to be unique, and the `relationships` tests still prove each dimension
holds every key the fact emits.

---

## Data quality

63 checks run on every build: 55 dbt data tests plus 8 model builds, and 36 pytest
tests on the ingest itself. The build fails if any of them fail.

| Test | Model | Catches |
|---|---|---|
| `unique`, `not_null` on `resale_txn_key` | `fact_resale_txn` | Duplicate loads, broken keys |
| `relationships` to each of the four dimensions | `fact_resale_txn` | Orphaned facts, key drift |
| `accepted_values` on `flat_type` | `dim_flat` | Upstream schema drift |
| `expression_is_true: > 0` on price and area | silver and gold | Nulls and sentinel values from the API |
| `accepted_range` on `remaining_lease_months` | `silver_hdb_resale` | A broken parse of the two lease formats |
| `not_null` on `storey_lower` | `silver_hdb_resale` | A broken parse of the '07 TO 09' format |
| `assert_every_town_has_a_region` | `dim_town` | A new town the hardcoded region map does not know |
| `assert_fact_reconciles_to_silver` | `fact_resale_txn` | An incremental run dropping or double-counting a month |

**The bug the tests did not catch, and why.** Silver originally deduplicated on `_id`,
data.gov.sg's row identifier. It is not one: it is a row offset in their datastore, and
it is reassigned when they republish. 579 `_id` values currently appear twice, and every
pair differs in block, street and floor area -- different sales sharing a row number. The
deduplication was deleting 579 real transactions, and the `unique` test on that column
passed *because* the dedup had removed its own evidence before the test ran.

It surfaced only when the parsed values were checked against the full dataset rather than
the fixture. The fix was to measure three candidate keys instead of arguing about them:

| Key | Collisions in 240,074 rows |
|---|---|
| `_id` alone | 579 |
| Full business key | 403 |
| `(month, _id)` | 0 |

The business key is worse than it sounds -- identical units in one block do sell in the
same month at the same price, so it collapses 403 genuine sales. `(month, _id)` is exact,
and the deduplication was removed entirely rather than re-keyed: with zero collisions the
`qualify` removed nothing, so it was dead code that looked like a safeguard. The
invariant is now a test. If the source ever repeats a row the build fails, instead of
quietly dropping it.

**What the tests actually caught.** All 41 passed on the first build, so rather than
claim a lucky catch, the two least obvious tests were verified by breaking the code
on purpose. Removing the `flat_type` normalisation from the silver model produced:

```
FAIL 1   accepted_values_dim_flat_flat_type__1_ROOM__2_ROOM__...__MULTI_GENERATION
FAIL 748 relationships_fact_resale_txn_flat_key__flat_key__ref_dim_flat_
```

The first was expected. The second is the more interesting one: `dim_flat` is a table
and rebuilds completely, while `fact_resale_txn` is incremental and does not, so a
change to a hashed natural key orphans every fact row built before it against a
dimension rebuilt after it. That is precisely the late-arriving-dimension failure the
`relationships` test exists for, and it is invisible to any row-level uniqueness
check. `assert_every_town_has_a_region` is a live tripwire rather than a
hypothetical: Tengah's first resale flats reach the market shortly, and the day a
27th town appears the build fails instead of quietly bucketing it as
`Unclassified`, where a regional chart would simply omit it.

---

## Idempotency and incremental loading

**The bronze layer is idempotent per month.** Each API pull writes to
`data/bronze/hdb_resale/month=YYYY-MM/part-0.parquet` and replaces exactly that
partition, via a temp file and an atomic rename. Re-running March rewrites March and
leaves every other month byte for byte as it was. The previous version of this script
read the whole file into memory, concatenated, de-duplicated and rewrote all 240k
rows on every run, so a crash mid-write took the entire history with it.

**The high-water mark is the data.** `read_high_water_mark()` asks DuckDB for
`max(month)` over the partition glob. Because `month` lives in the directory name and
not in the parquet bodies, DuckDB takes the value from the paths rather than reading
column data -- though it still opens each file. Measured at 117 partitions: 26.1ms,
against 26.7ms for `max()` of a real column. The saving is 2%, and the honest reading
is that at this scale the cost is per-file overhead, not data volume.

The alternative was a run log or a manifest. This scans instead, for two reasons.
There is no second source of truth to drift out of sync with what is actually on
disk. And it self-heals: a run that dies after writing 2024-01 but before writing
2024-02 leaves a mark of 2024-01, so the next run re-fetches from there. A stored
mark would already have been advanced, and 2024-02 would be lost silently and
permanently. A manifest is the better answer once listing partitions costs real money
-- see [at scale](#what-i-would-do-differently-at-scale). There is a test that pins
this behaviour down: delete the newest partition and the mark rolls back with it.

**The newest month is re-fetched, not skipped.** A month stays open. Transactions
keep registering against 2026-09 throughout September, so skipping it would freeze a
partial month on disk permanently. Paging is newest-first and stops at the first row
older than the mark, which means every month at or after the mark comes back
*complete* -- and that completeness is exactly what makes replacing a month wholesale
safe rather than destructive.

**The fact model's incremental unit is a month, not a row.**

```sql
materialized = 'incremental',
unique_key = 'date_key',
incremental_strategy = 'delete+insert'
```

`delete+insert` keyed on `date_key` drops every fact row for each month in the
incoming batch and re-inserts it, mirroring bronze exactly. The obvious alternative
-- keying on `resale_txn_key`, the transaction surrogate -- looks safer and is worse:
it merges rather than replaces, so any transaction data.gov.sg later withdrew from an
open month would linger in the fact forever. The fact would keep serving a
transaction the source no longer reports, and no uniqueness test would ever see it.

`--full` on the ingest and `--full-refresh` on dbt rebuild from scratch. That matters
more than it looks: an incremental run only ever moves the high-water mark *forward*,
so a gap older than the oldest partition can never close on its own. The ingest prints
a warning comparing rows on disk against the API's own reported total, so the gap is
visible at the end of every run rather than discovered months later.

---

## Running it

```bash
git clone <repo>
cd hdb-ingest
pip install -r requirements.txt

python ingest_hdb.py --full     # ~240k rows, 48 API pages, about four minutes
dbt deps && dbt build           # 6 models, 41 tests, about four seconds
streamlit run dashboard.py
```

Subsequent runs need no flags: `python ingest_hdb.py` fetches from the high-water
mark, and `dbt build` runs the fact incrementally.

To run the whole warehouse offline against the committed 766-row sample, without
calling the API at all -- this is what CI does:

```bash
python seed_fixture.py
DUCKDB_PATH=data/fixture/warehouse.duckdb dbt build --vars '{bronze_glob: "data/fixture/hdb_resale/month=*/*.parquet"}'
```

Unit tests: `pytest`. No network, no fixtures on disk, 36 tests in under a second.

An `API_KEY` in `.env` is optional -- data.gov.sg serves this dataset anonymously but
rate-limits harder without one. `ONEMAP_EMAIL` and `ONEMAP_PASSWORD` are needed only
for the geocoding scripts, which are not part of the bronze-to-gold path.

---

## Repository layout

```
ingest_hdb.py          Bronze ingest. Partitioned writes, high-water-mark read.
seed_fixture.py        Materialises the committed CSV sample into a bronze layer.
dashboard.py           Streamlit app over the gold star schema.
models/silver/         Typing, normalisation, dedup on the source row id.
models/gold/           Star schema: one fact, four dimensions.
tests/dbt/             Singular dbt tests.
tests/python/          Pytest suite for the ingest. Fully offline.
tests/fixtures/        766-row stratified sample, so CI never calls the API.
.github/workflows/     CI on every PR, scheduled ingest monthly.

onemap_utils.py        Geocoding via OneMap. Feeds dim_block.
ingest_mrt_data.py     MRT stations from Wikidata. Fetch and archive only.
```

---

## What I would do differently at scale

- **Scan-based high-water mark to a manifest.** Reading `max(month)` off the
  partition paths is the right call at 117 partitions on local disk, where it is free
  and cannot drift. On object storage with tens of thousands of partitions the LIST
  call becomes the dominant cost of every run, and a manifest -- or a table format
  like Iceberg or Delta that maintains one for you -- pays for the extra moving part.
  The self-healing property is what you give up, so the manifest write has to be
  committed in the same transaction as the data.
- **DuckDB to a warehouse.** DuckDB is single-node by design. At real volume this
  becomes Snowflake or BigQuery; the dbt models port largely unchanged, which is part
  of why the transformation layer lives in dbt rather than in the ingest script.
- **GitHub Actions to Airflow or Dagster.** Actions is fine for a cron and a test
  gate. It has no backfill semantics, no retry granularity, and no dependency graph
  across pipelines. The scheduled run here also depends on `actions/cache` to carry
  bronze between runs, which is a cache, not storage, and is allowed to evict.
- **Add data contracts.** The `accepted_values` test catches schema drift after it
  breaks something. A contract catches it at the boundary.
- **Partition the fact table** by transaction month once volume justifies the scan
  cost. Today it is a 240k-row table that DuckDB scans in milliseconds.

---

## Status

**Working end to end, verified on this machine:**

- Bronze ingest, incremental and full, 240,074 rows across 117 month partitions
- Silver: typing, normalisation, dedup on the source row id
- Gold: star schema, one fact and four dimensions
- 55 dbt data tests and 36 pytest tests, all passing
- Spatial layer: 181 MRT/LRT stations from Wikidata, 9,744 block addresses geocoded
  via OneMap, distance-to-station and distance-to-CBD on `dim_block`
- Streamlit dashboard over the gold layer

**Written but not yet exercised:** both GitHub Actions workflows. They have never
run, because this repository is not on GitHub yet. The CI workflow's steps are the
same commands verified locally against the same fixture, but a workflow that has not
gone green is not a workflow that works, and it is listed here rather than above for
that reason.

**Deleted, and worth naming.** An earlier pandas feature-engineering track
(`silver_spatial_join.py`, `silver_features.py`) was removed once the MRT and geocoding
work moved into dbt. Two ideas in it have no dbt equivalent and are genuinely missing
rather than merely relocated:

- **Distance to a top-ranked primary school**, and a within-1km flag. Primary One
  registration priority inside 1km is one of the strongest price signals in Singapore
  resale, so this is the most valuable unbuilt feature here. It needs a schools ingest
  from data.gov.sg, which does not exist yet.
- **Shopping malls within 2km.** Needs a mall dataset with no authoritative public
  source; the original used a CSV of unknown provenance, which is why it went rather
  than being ported.

Everything else those scripts computed -- distance to CBD, distance to the nearest
station, estate maturity, floor tiers -- now lives in `dim_block`, `dim_town` and
`dim_flat`, computed in SQL and covered by tests.

**Deliberately out of scope:** streaming ingestion, cloud deployment, an orchestrator
beyond CI cron, SCD Type 2 (see [Data model](#data-model) for why none of these
dimensions needs it).

---

## Screenshots

Not yet captured. Two of the three cannot be produced honestly until this is pushed
and a workflow has actually run.

- [ ] **The dbt DAG.** `dbt docs generate && dbt docs serve`, then the lineage graph.
      The catalog is already generated at `target/catalog.json`.
- [ ] **A passing GitHub Actions run.** Needs the repository pushed first.
- [ ] **The dashboard.** `streamlit run dashboard.py`. Renders correctly against the
      full 240,074-row warehouse.
