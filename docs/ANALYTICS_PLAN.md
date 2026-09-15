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
- Continuous variables enter as bands:
  - MRT: 0-400m, 400-800m, 800m-1.2km, over 1.2km. Classified once in `dim_block` on
    the unrounded distance, upper edges inclusive. `is_near_mrt` is band 1.
  - Lease: under 50, 50-60, 60-70, 70-80, 80-90, 90+ whole years remaining. Lower
    edges inclusive: 50-60 means at least 50 and under 60.
- Reference categories: lease 90+, MRT over 1.2km, Low (1-4), 4 ROOM, and the first
  month. Town effects are reported relative to the average town, not a reference town.
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

1. ~~Thin slice: MRT premium by band, end to end.~~ Done in PR #1.
2. ~~The fitting function with planted-answer tests, then the dbt Python model.~~ Done
   in PR #2.
3. ~~Price index, effects over time, and the before/after tables.~~ Done in PR #3.
4. ~~Block holdout validation against the baseline, then fair value.~~ Done in PR #4.
5. **Remaining descriptive marts; Findings/Explore page split; Explore maths into a
   tested module** (detailed below).
6. README landing page and `docs/ENGINEERING.md`.
7. Forecast replay: each year predicted from the years before it, against a "same as
   last year" baseline, backing the no-forecasting limitation.

---

## Slice 5: every table generated, and two dashboard pages

Finish the move off hand-typed numbers, then split the dashboard into what is published
and what is exploratory.

### Files

| File | Responsibility |
|---|---|
| `models/marts/mart_cbd_gradient.sql`, `mart_mrt_premium_by_cbd_ring.sql`, `mart_storey_premium.sql`, `mart_lease_4room.sql`, `mart_price_by_year.sql`, `mart_large_flat_share.sql`, `mart_town_ranking.sql` | The descriptive figures behind findings 1-6 and the Findings page. Each reproduces the hand-typed table it replaces exactly, except finding 4's, which moves to the model's 10-year lease bands so there is one band system. |
| `explore.py`, `tests/python/test_explore.py` | Filter-aware versions of the descriptive figures, in plain pandas, returning the same columns as the marts. |
| `check_explore_parity.py` | Explore, unfiltered, must equal the published marts. Run in CI on the fixture edition. |
| `charts.py` | Styling and chart builders, fed by marts or by `explore.py` alike. |
| `dashboard.py` | Two pages: Findings (published marts only, no filters) and Explore (filters, `explore.py`). |
| `publish_edition.py` | Sales gain `mrt_band` columns, so Explore never re-derives a band. |
| `FINDINGS.md`, `render_findings.py` | Every remaining hand table becomes a marker. |

## Global constraints

- Bands are classified once, in SQL, never re-derived in Python or the dashboard.
- Medians, never means, for descriptive figures. Price per sqm for anything compared
  across flats.
- `pytest` stays offline and needs no files on disk.
- CI never writes to `published/`. Only a deliberate local publish does.
