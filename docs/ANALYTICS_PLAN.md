# Analytics layer plan

What the analytics layer is, the decisions behind it, and the tasks for the slice
currently being built. Only the active slice is planned in detail. Later slices get
their tasks when they start, so this document cannot drift the way detailed plans do.

## Goal

Make the analysis as rigorous and tested as the pipeline: analytics engineering
(tested dbt marts, generated documentation) and econometrics (a hedonic model with
honest validation), served as a hosted dashboard that anyone can open.

## Decisions

**Model**

- Runs inside dbt as a dbt-duckdb Python model using statsmodels. The fitting logic is
  a plain Python function the dbt model calls, so pytest can test it without dbt.
- `log(price_psm) ~ town + mrt_band + lease_band + month + floor_tier + flat_type`.
  Town, MRT band and lease band are the reported effects; month, storey and flat type
  are held constant. Distance to the CBD is dropped: 96.8% of its variance is between
  towns, so it cannot be separated from the town term.
- Continuous variables enter as bands. Upper edges are inclusive, matching
  `dim_block.is_near_mrt`:
  - MRT: 0-400m, 400-800m, 800m-1.2km, over 1.2km
  - Lease: under 50, 50-60, 60-70, 70-80, 80-90, 90+ years
- Reference categories: lease 90+, MRT over 1.2km, Low (1-4), 4 ROOM. Town effects are
  reported relative to the average town, not a reference town.
- Effects are reported as percentages (`exp(b) - 1`), with standard errors clustered
  by block.
- Fitted twice: once across all years (its month terms are the price index,
  Jan 2017 = 100) and once per calendar year (effects over time, and fair value).
- **Fair value:** each sale is compared with its own year's fit, over the last 36
  months. A block gets a verdict only with 10+ sales and a 95% interval on its mean
  residual that excludes zero. Every other block shows "not enough sales to judge".
- **Validation:** hold out 20% of blocks (fixed seed), predict their sales, and report
  the typical miss next to a baseline of the town x flat type x year median. Then refit
  on all blocks for publishing.
- **Testing:** planted-answer pytest tests (synthetic sales with known effects, plus a
  year with an empty band), and a smoke test on the 766-row CI fixture, where fair
  value legitimately returns zero verdicts.

**Serving**

- **Edition:** published numbers are a committed edition in `published/`, stamped with
  the data cut. Aggregates are CSV; row-level sales for exploration are one parquet
  file. It is refreshed deliberately, not monthly.
- **Dashboard:** always reads the edition, never the warehouse, locally too.
  `publish_edition.py` is the only bridge between the warehouse and anything a person
  sees.
- **Dashboard pages:** Findings pages read pre-computed marts with no free filters. The
  Explore page keeps free filters, with its maths in a unit-tested module.
- **`FINDINGS.md`:** tables are generated from the edition between
  `<!-- table: name -->` markers. Prose and inline numbers stay hand-written. The
  edition stamp sits at the top.
- **Hosting:** Streamlit Community Cloud from the public repo.
- **README:** becomes a short landing page. Engineering detail moves to
  `docs/ENGINEERING.md`.

## Slices

One pull request each, CI green before merge.

1. **Thin slice:** MRT premium by band, end to end (detailed below).
2. The fitting function with planted-answer tests, then the dbt Python model.
3. Price index and effects over time.
4. Block holdout validation against the baseline, then fair value.
5. Remaining descriptive marts; Findings/Explore page split; Explore maths into a
   tested module.
6. README landing page and `docs/ENGINEERING.md`.
7. Forecast replay: each year predicted from the years before it, against a "same as
   last year" baseline, backing the no-forecasting limitation.

---

## Slice 1: MRT premium by band, end to end

Deliberately simple analytics carried by all the new plumbing: mart, edition export,
stamp, generated table, dashboard reading files, hosting.

### Files

| File | Responsibility |
|---|---|
| `macros/mrt_band.sql` | The one definition of the MRT bands (`mrt_band_order`, `mrt_band_label`). Slice 2 reuses it. |
| `models/marts/mart_mrt_premium_by_band.sql` | One row per band: sales, median psm, premium vs over 1.2km. |
| `models/marts/_marts_models.yml` | Column tests for the mart. |
| `tests/dbt/assert_mrt_bands_reconcile_to_fact.sql` | Every geocoded sale lands in exactly one band. |
| `publish_edition.py` | Warehouse to `published/`: mart CSVs, `sales.parquet`, `edition.json`. |
| `edition.py` | Reads the edition. Pandas only, no DuckDB. Used by the dashboard and the renderer. |
| `render_findings.py` | Fills `FINDINGS.md` markers from the edition. `--check` fails if the doc is stale. |
| `tests/python/test_publish_edition.py`, `test_render_findings.py` | Offline unit tests. |
| `dashboard.py` | Reads the edition. The MRT chart uses the mart. |
| `published/` | The committed Sep 2026 edition. |
| `.github/workflows/ci.yml` | Export smoke test on the fixture warehouse, plus the findings drift check. |

### Interfaces

- `edition.EDITION_DIR = "published"`
- `edition.read_stamp(root=EDITION_DIR) -> dict` with keys `data_through` (`"2026-09"`),
  `sales` (int), `published_on` (`"2026-09-14"`) and `tables` (list of str).
- `edition.read_table(name, root=EDITION_DIR) -> pd.DataFrame`, which reads
  `<root>/<name>.csv`.
- `edition.read_sales(root=EDITION_DIR) -> pd.DataFrame`, which reads `<root>/sales.parquet`.
- `publish_edition.publish(con, out_dir, published_on) -> dict` writes every mart in
  `MART_TABLES`, `sales.parquet` and `edition.json`, and returns the stamp.
- `render_findings.render(text, root) -> str` is pure. It replaces every
  `<!-- table: name -->...<!-- /table -->` and `<!-- edition -->...<!-- /edition -->`
  block, and raises `ValueError` on an unknown table or an unclosed marker.

### Task 1: The mart and its tests

- [ ] `macros/mrt_band.sql` defines two macros:
  - `mrt_band_order(d)` returns 1 for d <= 0.4, 2 for <= 0.8, 3 for <= 1.2, 4 above,
    and null when d is null.
  - `mrt_band_label(d)` returns `'0-400m'`, `'400-800m'`, `'800m-1.2km'` or
    `'over 1.2km'`.
- [ ] `mart_mrt_premium_by_band`: join the fact to `dim_block`, drop null distances, and
  group by band. Columns: `band_order`, `mrt_band`, `sales`, `median_price_psm`,
  `premium_vs_farthest_pct`, where that last column is median psm / band 4 median psm - 1,
  times 100. Add `+schema: marts` in `dbt_project.yml`.
- [ ] Yml tests: `band_order` unique and not null; `mrt_band` accepted values; `sales`
  and `median_price_psm` greater than 0.
- [ ] Singular test: `sum(sales)` equals the fact rows whose block has a non-null
  distance.
- [ ] Run the fixture build (`python seed_fixture.py`, then `dbt build` with the
  fixture vars). Expected: green.
- [ ] Commit: `feat: MRT premium by band mart`.

### Task 2: Edition export and reader (TDD)

- [ ] Failing tests in `test_publish_edition.py`. Each builds an in-memory DuckDB with
  tiny `gold.*` and `marts.*` tables:
  - `publish` writes `mart_mrt_premium_by_band.csv`, `sales.parquet` and `edition.json`.
  - The stamp has the right `data_through`, `sales` and `published_on`.
  - The CSV round-trips through `edition.read_table` with the same columns.
  - `sales.parquet` has one row per fact row and no `_ingested_at` column.
  - Publishing refuses an empty fact (a zero-sale edition is a broken edition).
- [ ] Implement `edition.py` and `publish_edition.py` (CLI:
  `python publish_edition.py [--out published] [--published-on YYYY-MM-DD]`, reading
  `DUCKDB_PATH`). Tests pass.
- [ ] Commit: `feat: publish a stamped edition from the warehouse`.

### Task 3: Generated findings table (TDD)

- [ ] Failing tests in `test_render_findings.py`:
  - A table marker is filled with a formatted markdown table.
  - Rendering is idempotent: rendering twice gives the same output as rendering once.
  - Text outside markers is untouched.
  - The edition marker renders the stamp line.
  - An unknown table name raises; an unclosed marker raises.
- [ ] Implement `render_findings.py`. Column labels and formats live in its `TABLES`
  dict. CLI: `python render_findings.py [--check]`, where `--check` exits 1 if
  `FINDINGS.md` would change. Tests pass.
- [ ] Add the edition marker at the top of `FINDINGS.md` and a
  `<!-- table: mrt_premium_by_band -->` block to finding 2. Keep the ring table
  hand-typed until slice 5.
- [ ] Commit: `feat: generate FINDINGS tables from the edition`.

### Task 4: Publish the edition, move the dashboard onto it

- [ ] `dbt build` on the real warehouse, `python publish_edition.py`,
  `python render_findings.py`.
- [ ] `dashboard.py`: `load_star()` becomes `edition.read_sales()`. `mrt_premium()`
  charts `edition.read_table("mart_mrt_premium_by_band")` and is captioned as all
  sales, unaffected by filters. The footer reads the stamp. A missing edition shows
  the publish command. Remove the `duckdb` import.
- [ ] Run `streamlit run dashboard.py` and check every chart renders.
- [ ] CI: after `dbt build`, run
  `python publish_edition.py --out data/fixture/published` (a smoke test that never
  touches the committed edition), then `python render_findings.py --check`.
- [ ] Commit the code, then the edition separately: `data: Sep 2026 edition`.

### Task 5: Hosting (by hand, by the repo owner)

- [ ] Sign in at share.streamlit.io with GitHub, create an app from
  `yahweh9/hdb-resale-pipeline` on `master` with `dashboard.py`, and deploy.
- [ ] Add the live link to the top of the README.

## Global constraints

- Bands are classified once, in `dim_block`, on the UNROUNDED distance (upper edges inclusive); `is_near_mrt` is band 1. Rounded columns are for display only.
- Medians, never means. Price per sqm for anything compared across flats.
- `pytest` stays offline and needs no files on disk.
- CI never writes to `published/`. Only a deliberate local publish does.
