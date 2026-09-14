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
2. **The fitting function with planted-answer tests, then the dbt Python model**
   (detailed below).
3. Price index and effects over time.
4. Block holdout validation against the baseline, then fair value.
5. Remaining descriptive marts; Findings/Explore page split; Explore maths into a
   tested module.
6. README landing page and `docs/ENGINEERING.md`.
7. Forecast replay: each year predicted from the years before it, against a "same as
   last year" baseline, backing the no-forecasting limitation.

---

## Slice 2: the hedonic model

One fit across all years, with its coefficients as a tested warehouse table. Nothing is
published yet: slice 3 turns the coefficients into the price index and the before/after
tables.

### Files

| File | Responsibility |
|---|---|
| `hedonic.py` | `fit_hedonic(sales)`: design matrix, OLS with block-clustered errors, tidy coefficients. Pandas, numpy and statsmodels only. |
| `tests/python/test_hedonic.py` | Planted-answer tests on synthetic sales. |
| `macros/lease_band.sql` | The one definition of the lease bands. |
| `models/analysis/hedonic_sales.sql` | Model input: one row per sale with every band the model uses. |
| `models/analysis/hedonic_coefficients.py` | dbt Python model: reads `hedonic_sales`, calls `fit_hedonic`. |
| `models/analysis/_analysis_models.yml` | Column tests. |
| `tests/dbt/assert_hedonic_references.sql` | One zero-effect reference per term; town effects average to zero. |
| `profiles.yml` | `module_paths: ["."]`, so the dbt Python model can import `hedonic`. |
| `requirements.txt` | Add `statsmodels`; drop the unused `scikit-learn` and its stale comment. |

### Interfaces

- `hedonic.fit_hedonic(sales: pd.DataFrame) -> pd.DataFrame`
  - Input columns: `block_key`, `town`, `mrt_band`, `lease_band`, `floor_tier`,
    `flat_type`, `transaction_month` (`"YYYY-MM"`) and `price_psm`.
  - Output: one row per level of each term, with columns `term`, `level`,
    `is_reference`, `sales`, `estimate` (log points), `std_error`, `effect_pct`,
    `ci_low_pct` and `ci_high_pct`. The `term` values are `town`, `mrt_band`,
    `lease_band`, `floor_tier`, `flat_type` and `month`.
- `hedonic.REFERENCES = {"mrt_band": "over 1.2km", "lease_band": "90+", "floor_tier":
  "Low (1-4)", "flat_type": "4 ROOM"}`. The month reference is the earliest month.
- **A level with no sales** is absent from the output.
- **A reference level with no sales** falls back to the most common level, with
  `is_reference` marking which level was used.

### Task 1: The fitting function (TDD)

- [ ] Failing tests on a synthetic market with planted effects: MRT 0-400m +10%,
  lease under 50 -15%, towns at -8%, 0% and +8%, and a noise sd of 0.03.
  - Each planted effect is recovered within 1.5 percentage points.
  - Reference rows have estimate 0 and are flagged.
  - Town log estimates average to zero.
  - A market with no "under 50" sales fits, and that level is absent.
  - A market with no "over 1.2km" sales fits, with exactly one MRT reference.
  - Every CI contains its estimate, and every std_error is greater than 0.
- [ ] Implement `hedonic.py`. Tests pass.
- [ ] Commit: `feat: hedonic fitting function with planted-answer tests`.

### Task 2: The dbt Python model

- [ ] Add the `lease_band` macro, `hedonic_sales`, `hedonic_coefficients.py`, the yml
  tests, the singular test, `module_paths` and the requirements change.
- [ ] Fixture build and real build both green; spot-check the real coefficients
  against the naive findings.
- [ ] Commit: `feat: hedonic coefficients as a dbt Python model`.

## Global constraints

- Bands are classified once, in SQL, never re-derived in Python or the dashboard.
- Medians, never means, for descriptive figures. Price per sqm for anything compared
  across flats.
- `pytest` stays offline and needs no files on disk.
- CI never writes to `published/`. Only a deliberate local publish does.
