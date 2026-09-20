# Engineering

This is the behind-the-scenes document: how the data gets from the government's website
to the charts, and how I check it along the way. You don't need it to understand the
results. For those, start with [README.md](../README.md) and
[FINDINGS.md](../FINDINGS.md).

## The short version

1. Download. Python scripts download every HDB resale sale from data.gov.sg, the
   locations of MRT stations from Wikidata, and a map location for every block from
   OneMap. The raw files are saved exactly as they arrive and never edited.
2. Clean. SQL models, run by a tool called dbt, turn the raw files into tidy tables
   inside DuckDB, a small database that runs on a laptop. This step fixes formats,
   spellings and data types.
3. Organise. The tidy tables are arranged as one big table of sales, plus smaller
   lookup tables for dates, towns, flat types and blocks. That makes every question a
   simple lookup.
4. Model. The pricing model runs inside the same dbt build, so it always uses the
   latest cleaned data.
5. Check. More than a hundred automatic checks run on every build and fail it if
   something looks wrong, like a missing sale, a duplicate, or a model that stops
   beating a simple guess.
6. Publish. When I'm happy with the results, a script saves the final numbers into
   the `published/` folder. The dashboard and FINDINGS.md both read from there, so they
   can never show different numbers.

## Words used in this document

| Word | What it means here |
|---|---|
| Bronze / silver / gold | The raw data as downloaded / cleaned data / organised, ready-to-use data |
| Mart | A small table holding exactly the numbers behind one chart or table |
| dbt | A tool that runs SQL files in the right order and tests the results |
| Fact table / dimension | The big table of sales / the lookup tables that describe them (towns, flats, blocks, dates) |
| Partition | One file per month of sales, so a month can be replaced without touching the rest |
| Idempotent | Safe to run twice: running it again gives the same result, not duplicates |
| High-water mark | How far the download has already got, so the next run only fetches what's new |
| CI | Continuous integration: GitHub re-runs the whole build and every check on each change |
| Fixture | A small sample of the data kept in the repo, so the checks can run without downloading everything |
| Edition | The saved set of published numbers, stamped with the date of the data |

---

## Architecture

```
 data.gov.sg API          Wikidata (SPARQL)        OneMap API
       |                         |                     |
       v                         v                     v
 ingest/hdb_resale.py     ingest/mrt_stations.py   ingest/block_locations.py
 month partitions         fetch + archive          geocode 9,744 blocks
       |                         |                     |
       +-------------------------+---------------------+
                                 v
                       +--------------------+
                       |  data/bronze/      |  Immutable. Parquet only.
                       +---------+----------+
                                 v
                       +--------------------+
                       |  DuckDB + dbt      |  Reads the parquet in place. No load step.
                       |                    |
                       |  silver (3)        |  Typing, parsing, normalisation
                       |  gold (5)          |  Star schema
                       |  analysis (5)      |  Hedonic model: dbt Python models
                       |  marts (13)        |  One table per published figure
                       +---------+----------+  105 data tests
                                 v
                       +--------------------+
                       |  publish/          |  build_edition.py: deliberate,
                       |  build_edition.py  |  not scheduled
                       +---------+----------+
                                 v
                       +--------------------+
                       |  published/        |  Committed. 13 mart CSVs, one sales
                       +----+----------+----+  parquet, a stamp naming the data cut
                            |          |
                            v          v
                        app.py      publish/render_findings.py
                    Findings and    fills the tables in
                    Explore pages   FINDINGS.md and README.md

Built and tested by GitHub Actions on every pull request.
```

---

## Data source

[HDB Resale Flat Prices](https://data.gov.sg) from data.gov.sg, resource
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

---

## Stack

| Layer | Tool | Why |
|---|---|---|
| Ingestion | Python (`requests`) | Full control over pagination, retries, idempotency |
| Storage | Local parquet, Hive-partitioned by month | Immutable per partition, cheap to re-read |
| Warehouse | DuckDB | Zero infrastructure, columnar, reads the parquet glob in place |
| Transformation | dbt | Dependency DAG, tests, docs, lineage |
| Modelling | statsmodels, inside dbt Python models | Coefficients with standard errors; scikit-learn reports none |
| Publishing | A committed edition (CSV + parquet) | The page and the document read the same numbers, with no live warehouse |
| Orchestration | GitHub Actions | Scheduled ingest, full build and test on every PR |
| Geocoding | OneMap API | National mapping service, authoritative for SG addresses |
| Reference data | Wikidata (SPARQL) | CC0, so no attribution or share-alike obligation |
| Serving | Streamlit + Altair | One command, no server to run, reads the edition only |

---

## Data model

A star schema. Dimensions are deliberately denormalized: the redundancy compresses away
columnar, and every query stays a single join from the fact table.

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

**`fact_resale_txn`** holds the measures `resale_price`, `price_psm`,
`floor_area_sqm` and `remaining_lease_months`. `source_txn_id` is carried as a
degenerate dimension so any fact row can be traced back to the bronze partition it
came from.

**`dim_block` carries the spatial attributes**, not the fact. Location is a property of
the block, so `dist_to_nearest_mrt_km` on the fact would store the same value across
every sale in that block, 240,074 rows to describe 9,744 things. The nearest station is
found by a 9,744 x 181 cross join, which DuckDB resolves in under a second; a spatial
index is the answer at a hundred times this size.

**Bands are classified once, here.** `dim_block` also carries `mrt_band` (0-400m,
400-800m, 800m-1.2km, over 1.2km), computed on the unrounded distance, and
`is_near_mrt` is defined as band 1. Before that, the band and the flag were computed in
two places on two differently rounded distances and disagreed on 1,096 sales; a test now
proves every located sale lands in exactly one band. Lease bands work the same way, from
one macro. Nothing in Python or the dashboard re-derives a band.

**`dim_flat` is Type 1, deliberately.** These attributes describe the flat *as sold*
on that date. They do not change afterwards, so there is no later version of the row
for a Type 2 history to preserve, and a `valid_from`/`valid_to` pair here would carry
no information. The same reasoning covers `dim_town`: when HDB reclassifies a town's
planning region, the correct answer is that it always belonged to the new one.
Nothing in this schema has a genuine slowly-changing attribute, and adding SCD2
machinery to prove familiarity with it would be worse than not having it.

**Dimension keys are hashed, not joined.** The fact computes `town_key` with the same
`generate_surrogate_key(['town'])` that builds `dim_town`, so it never joins to a
dimension to get a foreign key. That removes any fan-out risk from a dimension that
turns out not to be unique, and the `relationships` tests still prove each dimension
holds every key the fact emits.

**Above gold, two more layers.** `analysis` holds the model: `hedonic_sales` (one row
per sale, banded, in SQL) and four Python models that fit it. `marts` holds one table
per published figure, each a plain-numbers table any tool can read. How a number is
formatted for a reader is decided later, in the document or the chart, never in the mart.

---

## The analytics layer, engineered

The model is held to the same standard as the pipeline: tested before it touches real
data, built by the same `dbt build`, and gated by tests that fail the build.

**The model runs inside dbt.** `hedonic_coefficients.py` and its siblings are dbt-duckdb
Python models, but each is a few lines: it hands the `hedonic_sales` table to a plain
function in [pricing/hedonic.py](../pricing/hedonic.py) or [pricing/valuation.py](../pricing/valuation.py) and returns
the result. The statistics live in modules pytest can import without dbt, a warehouse,
or any file on disk.

**Tested against a planted answer.** [tests/python/synthetic.py](../tests/python/synthetic.py)
generates a market with known effects (town premiums, an MRT premium, lease decay, a
price trend, block premiums), and the tests assert the fit recovers them. The same market
covers the awkward cases: a band with no sales, a year too thin to identify, a holdout
that must pick the same fifth of blocks every run, and a design that cannot be solved,
which must raise rather than return arbitrary numbers.

**That last test exists because of a real bug.** Pandas hands back category codes as
`int8`, and each code is added to its term's starting column. The planted markets ran
for 24 months; the real data runs for 117, which pushes the design past 127 columns. From
March 2024, `start + code` wrapped around, 31 month columns were left as zeros, and the
fit still returned a plausible-looking table. The fix was 64-bit codes, a planted market
wide enough to have caught it, and a rank check so that a design which loses a column
fails loudly instead of fitting quietly.

**Gates that fail the build:**

| Test | Fails when |
|---|---|
| `assert_model_beats_baseline` | On held-out blocks, the model's median miss is not below the town x flat type median's, in any year with 1,000+ test sales |
| `assert_every_substantial_year_is_fitted` | A year with 5,000+ sales is missing from the per-year fit |
| `assert_hedonic_coefficients_are_well_formed` | A term lacks exactly one zero-effect reference level, town effects stop averaging to zero, or level counts stop summing to the input |
| `assert_fair_value_verdicts_follow_the_rules` | A block is called above, below or in line without 10+ sales and a 95% interval on the right side of zero |
| `assert_mrt_bands_reconcile_to_fact` | Band counts stop summing to the fact: a gap or overlap between band edges |

**The edition is the only bridge to a reader.** `publish/build_edition.py` exports the 13 marts
as CSV, every sale as one zstd parquet file in a fixed row order, and `edition.json`,
which stamps the data cut. The directory is committed. The dashboard reads it and nothing
else, locally too, so a fresh clone runs the dashboard with no API key and no warehouse,
and the hosted page and FINDINGS.md cannot show different numbers. Publishing is
deliberate: the monthly ingest keeps the warehouse current, and an edition changes only
when someone republishes, re-reads the prose against the new numbers, and commits both.

**Documents are generated where they can be, and checked where they cannot.** Every table
in FINDINGS.md sits between `<!-- table: name -->` markers and is filled from the edition
by [publish/render_findings.py](../publish/render_findings.py). The README carries the edition stamp the
same way. `publish/render_findings.py --check` runs in CI and fails if either document differs
from what the committed edition would render. Moving the hand-typed tables to markers
reproduced every hand-typed row exactly, and showed the CBD table had skipped the 18km
ring. Numbers quoted inside sentences stay hand-written, and are re-read on every
republish.

**The two dashboard pages are kept honest with each other.** Findings shows published
marts with no filters. Explore recomputes the descriptive figures in pandas under
whatever filters the reader picks ([dashboard/explore.py](../dashboard/explore.py)). `dashboard/check_parity.py`
runs Explore's maths unfiltered and fails if the result differs from the SQL marts beyond
their rounding, on both the committed edition and one CI publishes from the fixture. Two
implementations of one number either agree or the build is red.

---

## Data quality

Every build runs 131 dbt nodes (26 models and 105 data tests) and 90 pytest tests
(39 on the ingest, 51 on the model, the edition and the documents). The build fails if
any of them fail.

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
| `assert_block_geocoding_coverage` | `dim_block` | Blocks silently dropping out of every spatial answer |
| `assert_mrt_distances_are_plausible` | `dim_block` | A broken haversine, swapped coordinates, or a lost line |

The model's own gates are listed [above](#the-analytics-layer-engineered).

**The bug the tests did not catch, and why.** Silver originally deduplicated on `_id`,
data.gov.sg's row identifier. It is not one: it is a row offset in their datastore, and
it is reassigned when they republish. 579 `_id` values currently appear twice, and every
pair differs in block, street and floor area: different sales sharing a row number. The
deduplication was deleting 579 real transactions, and the `unique` test on that column
passed *because* the dedup had removed its own evidence before the test ran.

It surfaced only when the parsed values were checked against the full dataset rather than
the fixture. The fix was to measure three candidate keys instead of arguing about them:

| Key | Collisions in 240,074 rows |
|---|---|
| `_id` alone | 579 |
| Full business key | 403 |
| `(month, _id)` | 0 |

The business key is worse than it sounds. Identical units in one block do sell in the
same month at the same price, so it collapses 403 genuine sales. `(month, _id)` is exact,
and the deduplication was removed entirely rather than re-keyed: with zero collisions the
`qualify` removed nothing, so it was dead code that looked like a safeguard. The
invariant is now a test. If the source ever repeats a row the build fails, instead of
quietly dropping it.

**What the tests actually caught.** All 41 tests that existed at the time passed on the
first build, so rather than claim a lucky catch, the two least obvious were verified by
breaking the code on purpose. Removing the `flat_type` normalisation from the silver
model produced:

```
FAIL 1   accepted_values_dim_flat_flat_type__1_ROOM__2_ROOM__...__MULTI_GENERATION
FAIL 748 relationships_fact_resale_txn_flat_key__flat_key__ref_dim_flat_
```

The first was expected. The second is the more interesting one: `dim_flat` is a table
and rebuilds completely, while `fact_resale_txn` is incremental and does not, so a
change to a hashed natural key orphans every fact row built before it against a
dimension rebuilt after it. That is the late-arriving-dimension failure the
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

**The high-water mark is the data.** `read_high_water_mark()` takes the newest
`month=YYYY-MM` directory under the bronze root. Because `month` lives in the directory
name and not in the parquet bodies, this is a string max over directory names, and no
parquet is opened at all.

An earlier version asked DuckDB for it. That was measured and abandoned: at 117
partitions it took 26.1ms against 26.7ms for `max()` of a real column, so it was
saving 2% while still opening every file. The cost was per-file overhead, not data
volume, which is the same reason partition COUNT rather than data size is what bites
at scale. It also crashed CI with an internal assertion when the file set shrank
between two reads in the same process. Parsing the path takes 10ms and cannot fail
that way.

The property that matters is unchanged: the mark is **derived** from the data rather
than stored beside it.

The alternative was a run log or a manifest. This scans instead, for two reasons.
There is no second source of truth to drift out of sync with what is actually on
disk. And it self-heals: a run that dies after writing 2024-01 but before writing
2024-02 leaves a mark of 2024-01, so the next run re-fetches from there. A stored
mark would already have been advanced, and 2024-02 would be lost silently and
permanently. A manifest is the better answer once listing partitions costs real money; see
[at scale](#what-i-would-do-differently-at-scale). There is a test that pins this
behaviour down: delete the newest partition and the mark rolls back with it.

**The newest month is re-fetched, not skipped.** A month stays open. Transactions
keep registering against 2026-09 throughout September, so skipping it would freeze a
partial month on disk permanently. Paging is newest-first and stops at the first row
older than the mark, which means every month at or after the mark comes back
*complete*, and that completeness is what makes replacing a month wholesale safe
rather than destructive.

**The fact model's incremental unit is a month, not a row.**

```sql
materialized = 'incremental',
unique_key = 'date_key',
incremental_strategy = 'delete+insert'
```

`delete+insert` keyed on `date_key` drops every fact row for each month in the
incoming batch and re-inserts it, mirroring bronze exactly. The obvious alternative,
keying on `resale_txn_key`, the transaction surrogate, looks safer and is worse:
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

Every command runs from the repository root. The scripts live in folders, so they run
as modules with `python -m folder.script`.

**Just the dashboard.** It reads the committed edition, so this needs no API key, no
ingest and no warehouse:

```bash
pip install -r requirements.txt
streamlit run app.py
```

**The whole pipeline, from nothing:**

```bash
python -m ingest.hdb_resale --full    # ~240k rows, 48 API pages, about four minutes
python -m ingest.mrt_stations         # MRT/LRT stations from Wikidata
python -m ingest.block_locations      # geocode every block via OneMap, about half an hour
dbt deps && dbt build                 # 26 models, 105 tests, about 30 seconds
python -m publish.build_edition       # refresh published/
python -m publish.render_findings     # refill the tables in FINDINGS.md and README.md
```

Subsequent runs need no flags: `python -m ingest.hdb_resale` fetches from the high-water
mark, the geocoder requests only addresses it has not seen, and `dbt build` runs the
fact incrementally. Publishing is a separate, deliberate step: re-read the prose in
FINDINGS.md against the new numbers before committing an edition.

`ONEMAP_EMAIL` and `ONEMAP_PASSWORD` in `.env` are needed for the geocoding step. An
`API_KEY` is optional: data.gov.sg serves this dataset anonymously but rate-limits
harder without one.

**Offline, against the committed 766-row sample.** This is what CI does:

```bash
python -m ingest.seed_fixture
export DUCKDB_PATH=data/fixture/warehouse.duckdb
dbt build --vars '{bronze_glob: "data/fixture/hdb_resale/month=*/*.parquet"}'
python -m publish.build_edition --out data/fixture/published
python -m dashboard.check_parity --edition data/fixture/published
```

On the fixture, fair value legitimately returns no verdicts: no block has 10 sales.

**Tests:** `pytest`, with no network and no files on disk. `dbt docs generate && dbt docs
serve` opens the lineage graph and the column documentation.

---

## Repository layout

```
app.py                        The dashboard: run it with `streamlit run app.py`.

ingest/                       Getting the data in
  hdb_resale.py               Resale sales from data.gov.sg. Month partitions, high-water mark.
  mrt_stations.py             MRT and LRT stations from Wikidata. Fetch and archive only.
  block_locations.py          A map location for every block, via OneMap. Feeds dim_block.
  seed_fixture.py             Turns the committed CSV samples into a bronze layer for CI.

models/                       dbt: cleaning, organising and modelling the data
  silver/                     Typing, parsing, normalisation.
  gold/                       Star schema: one fact, four dimensions.
  analysis/                   hedonic_sales, and the dbt Python models that fit it.
  marts/                      One table per published figure.
macros/                       The MRT and lease band definitions, each in one place.

pricing/                      The pricing model, called by the dbt Python models
  hedonic.py                  The hedonic fit, across all years and per year.
  valuation.py                Block holdout validation and fair value.

publish/                      Sharing the results
  build_edition.py            Warehouse -> published/. The only bridge to a reader.
  edition.py                  Reads the edition, for everything downstream of it.
  render_findings.py          Fills the generated tables in FINDINGS.md and README.md.
published/                    The committed edition: mart CSVs, sales parquet, stamp.

dashboard/                    The dashboard's building blocks
  charts.py                   Chart builders shared by both pages, with validated colours.
  theme.py                    The page styles, headline figures, and loading, empty and error states.
  explore.py                  The Explore page's maths, in pandas.
  check_parity.py             Explore, unfiltered, must equal the published marts.

tests/dbt/                    Singular dbt tests, including the model's quality gates.
tests/python/                 Pytest: ingest, model, edition, documents. Fully offline.
tests/fixtures/               766-row stratified sample, so CI never calls the API.
.github/workflows/            CI on every PR, scheduled ingest monthly.
docs/                         This document, the analytics plan, and the screenshots.
```

---

## What I would do differently at scale

- **Scan-based high-water mark to a manifest.** Reading `max(month)` off the
  partition paths is the right call at 117 partitions on local disk, where it is free
  and cannot drift. On object storage with tens of thousands of partitions the LIST
  call becomes the dominant cost of every run, and a manifest (or a table format
  like Iceberg or Delta that maintains one for you) pays for the extra moving part.
  The self-healing property is what you give up, so the manifest write has to be
  committed in the same transaction as the data.
- **DuckDB to a warehouse.** DuckDB is single-node by design. At real volume this
  becomes Snowflake or BigQuery; the SQL models port largely unchanged, which is part
  of why the transformation layer lives in dbt rather than in the ingest script. The
  Python models are the part that would not: they would move to Snowpark, or to a
  separate training job that writes its coefficients back.
- **GitHub Actions to Airflow or Dagster.** Actions is fine for a cron and a test
  gate. It has no backfill semantics, no retry granularity, and no dependency graph
  across pipelines. The scheduled run here has nowhere durable to keep bronze between
  runs: `actions/cache` is a cache, not storage, and on a monthly schedule it has
  usually evicted by the next run, so each run rebuilds bronze from the APIs.
- **A committed edition to an object store.** Committing 13 CSVs and one parquet file is
  right at this size: the edition is versioned with the prose that describes it. At a
  few hundred megabytes it belongs in a bucket, addressed by its stamp.
- **Add data contracts.** The `accepted_values` test catches schema drift after it
  breaks something. A contract catches it at the boundary.
- **Partition the fact table** by transaction month once volume justifies the scan
  cost. Today it is a 240k-row table that DuckDB scans in milliseconds.

