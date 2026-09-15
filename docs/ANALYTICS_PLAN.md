# Analytics plan

My working notes for the analysis side of the project: the decisions I made about the
pricing model and how the results get published, and the order I built things in. It's
written as a checklist for myself, so it uses more technical shorthand than the other
documents. [FINDINGS.md](../FINDINGS.md) explains the model in plain English.

## Goal

Make the analysis as careful and well-tested as the data pipeline: tested tables behind
every published number, a pricing model that compares flats like for like (and is
checked against a simple guess), and a dashboard anyone can open.

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
5. ~~Remaining descriptive marts; Findings/Explore page split; Explore maths into a
   tested module.~~ Done in PR #5.
6. ~~README landing page and `docs/ENGINEERING.md`.~~ Done in PR #6, then rewritten in
   plainer, first-person language with screenshots.
7. Forecast replay: each year predicted from the years before it, against a "same as
   last year" baseline, backing the no-forecasting limitation. Not started.

---

## Global constraints

- Bands are classified once, in SQL, never re-derived in Python or the dashboard.
- Medians, never means, for descriptive figures. Price per sqm for anything compared
  across flats.
- `pytest` stays offline and needs no files on disk.
- CI never writes to `published/`. Only a deliberate local publish does.
