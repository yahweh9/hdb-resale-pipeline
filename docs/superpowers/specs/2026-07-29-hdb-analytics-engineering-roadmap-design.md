# HDB Full-Stack Data Analytics/Engineering Project — Roadmap Design

Date: 2026-07-29

## Context

The HDB project (`C:\Users\wrigh\Desktop\HDB`) currently has two layers of existing work:

1. **`master` branch**: a flat-script bronze/silver/gold pipeline over local parquet files — `ingest_hdb.py` (data.gov.sg HDB resale, API-key based), `ingest_schools.py` (currently broken — duplicates the HDB fetch instead of pulling schools), `clean_mrt_data.py` / `onemap_utils.py` (MRT + OneMap geocoding), `silver_spatial_join.py` / `silver_features.py` (haversine distances, elite-school proximity, mall density, lease decay features), `gold_analytics.py` / `gold_postgres_analytics.py` (DuckDB/Postgres aggregation), and a partially-built `dashboard.py` (Streamlit, reads a local Postgres `hdb_portfolio` DB, already has an "Elite School Premium" section and a "Lease Decay / Bala's Curve" section). No root `requirements.txt` or `README` yet.
2. **A separate git worktree** (`worktree-hdb-governance-pipeline`), containing a full design (`docs/superpowers/specs/2026-07-21-hdb-governance-pipeline-design.md`) and a 26-task implementation plan (`docs/superpowers/plans/2026-07-22-hdb-governance-pipeline.md`) written 2026-07-21/22, rebuilding the pipeline as a governed Dagster + Postgres system (`raw`/`staging`/`audit`/`marts` schemas, custom validation rule engine with quarantine instead of silent drops). **2 of 26 tasks are complete** (package scaffolding + `NullCheckRule`).

Today's ask is broader: turn this into a "full-fledged data analytics/engineering project," not just finish the governance pipeline. This document is the roadmap that decomposes that goal into sequenced sub-projects (epics), each of which gets its own spec → plan → implementation cycle. It does not re-design the governance pipeline (already well-specified) — it places it in context and designs the rest of the picture around it.

## Decisions made during brainstorming

1. **Existing governance-pipeline design/plan is kept as-is**, not redesigned. It's already solid (TDD-based rule engine, Dagster orchestration, Docker Compose, Postgres medallion schema) and only 2/26 tasks deep, so re-planning it would waste already-good design work.
2. **Purpose**: portfolio/job-application material *and* skill-building. General data engineering + data analytics/data science focus — explicitly not leaning into a "cybersecurity" theme (access control simulation, PII masking, etc.) despite the user's cybersecurity background.
3. **Deployment target** (recommended, user approved): hybrid.
   - **Docker Compose** for the full pipeline (Dagster + Postgres + governance layer) as the "clone and run" data-engineering artifact. This is the standard pattern for orchestration-tool portfolios — nobody expects to pay to host a live Dagster instance; a recruiter reads the README/architecture diagram instead of spinning it up themselves.
   - **A free-hosted live Streamlit dashboard** (Streamlit Community Cloud) backed by a small periodically-refreshed database (free-tier hosted Postgres such as Supabase or Neon, or a scheduled-refresh DuckDB file via GitHub Actions) as the "click and see" artifact — low/no cost, high engagement.
4. **Sequencing**: Epic 1 (Governance Pipeline, already fully planned) is executed to completion as originally scoped, *then* Epic 2 (Analytics/DS layer), then Epic 3 (Dashboard expansion + live deploy), then Epic 4 (CI/CD), then Epic 5 (Documentation polish — though the README is maintained incrementally throughout, not written from scratch at the end).
5. **Scope boundary for this document**: this is a roadmap, not a full detailed design for every epic. Epic 1 already has its spec + plan. Epics 2–5 are scoped here at a level sufficient to sequence and estimate them; each needs its own brainstorming session before implementation planning.

## Target architecture

```
                    ┌─────────────────────────────────────────┐
                    │         SOURCES (live APIs)               │
                    │  data.gov.sg (HDB resale, schools)        │
                    │  data.gov.sg (MRT poll-download)          │
                    │  OneMap (geocoding)                       │
                    └───────────────────┬───────────────────────┘
                                         │
                    ┌────────────────────▼───────────────────────┐
                    │   EPIC 1: Governance Pipeline (Dagster)      │
                    │   raw → validate/quarantine → staging → marts│
                    │   Postgres: raw / staging / audit / marts    │
                    │   (already spec'd + planned, 2/26 tasks done)│
                    └───────────────────┬───────────────────────┘
                                         │  marts.hdb_proximity_features
                                         │  marts.hdb_extended_features
                    ┌────────────────────▼───────────────────────┐
                    │   EPIC 2: Analytics / Data Science layer     │
                    │   price prediction model, trend/time-series  │
                    │   analysis, feature importance, "fair value" │
                    │   estimator → writes marts.model_predictions │
                    └───────────────────┬───────────────────────┘
                                         │
              ┌──────────────────────────▼─────────────────────────┐
              │   EPIC 3: Dashboard (Streamlit)                      │
              │   existing 2 sections + prediction tool + maps       │
              │   local (reads warehouse) + live-hosted lightweight  │
              │   version (free tier DB, e.g. Supabase/Neon)          │
              └───────────────────────────────────────────────────┘

   Wrapping the whole stack:
   EPIC 4: CI/CD — pytest + lint on push (GitHub Actions),
            optionally a scheduled pipeline run
   EPIC 5: Documentation — README with architecture diagram,
            data dictionary, screenshots, the governance "why
            quarantine not delete" story
```

`marts.*` is the contract: Epic 1 produces it, every downstream epic consumes it. This is why Epic 1 is finished before Epic 2 starts — building analytics against the current ungoverned parquet files would mean redoing that work once the schema changes underneath it.

## Epic breakdown

### Epic 1: Governance Pipeline *(already spec'd — reference only, no changes made here)*

- Spec: `docs/superpowers/specs/2026-07-21-hdb-governance-pipeline-design.md`
- Plan: `docs/superpowers/plans/2026-07-22-hdb-governance-pipeline.md`
- Status: 2/26 tasks complete, in worktree `worktree-hdb-governance-pipeline`.
- Produces: Postgres `raw`/`staging`/`audit`/`marts` schemas; `marts.hdb_proximity_features` and `marts.hdb_extended_features` are the data contract Epic 2 builds on.
- Action: no re-design needed. Resume execution via `superpowers:executing-plans` or `superpowers:subagent-driven-development` against the existing plan when implementation starts.

### Epic 2: Analytics / Data Science layer *(needs its own brainstorming session)*

- Goal: turn governed marts data into actual insights and predictions — the analytical "so what" that data engineering alone doesn't answer.
- Candidate scope, to be refined in its own design session:
  - Resale price prediction model (regression or gradient-boosted trees) trained on `marts.hdb_extended_features`.
  - Trend / time-series analysis of price movements by town and flat type over the ~236k-record history.
  - Feature importance analysis — which factors (school proximity, lease decay, MRT distance) actually move price the most.
  - Possibly a "fair value estimator": given a flat's attributes, predict expected price and flag over/under-valued listings.
- Depends on: Epic 1's `marts.*` tables existing with real, governed data.
- Output: a trained model artifact + training/evaluation script, plus a new table (e.g. `marts.model_predictions`) that Epic 3 reads from.

### Epic 3: Dashboard (Streamlit)

- Goal: expand the existing `dashboard.py` (repointed at the new governed marts schema instead of the ad hoc `hdb_portfolio` tables) with additional analyses, a prediction-tool UI backed by Epic 2's model, and map-based visualizations.
- Adds: the live-hosted lightweight deployment (Streamlit Community Cloud + free-tier hosted DB or scheduled-refresh snapshot).
- Depends on: Epic 1 for the schema repoint (can start once Epic 1's marts exist), Epic 2 for the prediction-tool section specifically.

### Epic 4: CI/CD

- Goal: GitHub Actions running `pytest` + lint on every push; optionally a scheduled trigger for the pipeline itself.
- A lightweight version (test-on-push) can start as soon as `requirements.txt` and a test suite exist — i.e., early during Epic 1 execution — rather than waiting until everything else is done. Full maturity (scheduled runs, coverage gates) comes once the codebase stabilizes.

### Epic 5: Documentation / Portfolio story

- Goal: root `README.md` with an architecture diagram, data dictionary, the governance "why quarantine instead of silently dropping rows" narrative (tied to the real bug found in `silver_features.py`'s `dropna` call), and screenshots/GIFs of the dashboard and Dagster UI.
- Maintained incrementally as a living document through every epic, but polished last, once there's a real system to describe and screenshot.

## Sequencing rationale

1. **Epic 1 first**: it defines the schema contract every downstream epic depends on, and it's already fully planned — the execution cost is low relative to the value of not having to redo analytics work later against a changed schema.
2. **Epic 2 before Epic 3 polish**: analytics is the differentiating content. A dashboard with real predictions and insights is a stronger portfolio piece than a dashboard with more chart types over the same two analyses.
3. **Epic 4 started lightly early, matured late**: a basic test-on-push CI costs little to add once tests exist and protects against regressions during Epics 2–3; full CI maturity (coverage gates, scheduled pipeline runs) isn't worth investing in before the codebase has settled.
4. **Epic 5 last for polish**, though the README exists in stub form throughout so it's never a last-minute scramble.

## Out of scope / deferred

- **No live-hosted orchestrator.** Hosting a live Dagster webserver/daemon costs money and isn't the expected portfolio pattern; the Docker Compose stack is the "run it yourself" artifact instead.
- **No cloud data warehouse migration** (Snowflake/BigQuery/etc.) — at ~236k rows, local/free-tier Postgres is sufficient; a warehouse migration wouldn't demonstrate meaningfully different skills at this scale.
- **No security-specific theming** (access-control simulation, PII masking, secrets-management showcase) — deliberately deferred per the "general DE + DS, not security-themed" decision above. Could become a future epic if priorities change.

## Testing approach across epics

- **Epic 1**: already covers TDD unit tests for every validator (pure pytest, no DB/network) per the existing plan.
- **Epic 2**: model evaluation reported with real train/test-split metrics (RMSE/MAE, or equivalent) — not just qualitative "looks right."
- **Epic 3**: manual QA in a running browser session (start the Streamlit dev server, click through both existing and new sections, check for regressions) before calling it done.
- **Epic 4**: CI enforces both of the above automatically on every push.

## Next steps

- This roadmap is committed to git.
- Epic 1 needs no further design — it can be resumed for implementation via `superpowers:executing-plans` or `superpowers:subagent-driven-development` against its existing plan whenever the user is ready to build.
- Epic 2 (Analytics / Data Science layer) is the next piece that needs its own brainstorming/design session before it can be planned or implemented.
