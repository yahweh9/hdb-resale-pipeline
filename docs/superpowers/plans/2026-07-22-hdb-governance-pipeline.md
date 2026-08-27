# HDB Data Quality & Governance Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the existing HDB parquet-file bronze/silver/gold pipeline as a Postgres-backed `raw → staging → marts` pipeline with an `audit` governance layer: a hand-rolled validation rule engine that quarantines failing rows (with reasons) instead of silently dropping them, orchestrated by Dagster and containerized with Docker.

**Architecture:** Dagster assets land JSONB snapshots from live data.gov.sg/OneMap APIs into `raw.*` tables, a `ValidationRunner` (custom rule engine, no external validation library) checks each new batch against schema-drift/null/outlier/referential-integrity/duplicate rules and splits it into rows that land in `staging.*` vs. rows that land in `audit.quarantine`, every rule execution is logged to `audit.validation_results` regardless of pass/fail, and downstream marts assets compute nearest-MRT/nearest-school features for analytics.

**Tech Stack:** Python 3.11, Dagster (orchestration), PostgreSQL 16 (warehouse + Dagster storage, both in Docker), SQLAlchemy 2.x + psycopg2 (DB access), pandas/numpy (data processing), requests (data.gov.sg + OneMap clients), pytest (validator unit tests), Streamlit (existing dashboard, repointed).

---

## Spec Reference

This plan implements `docs/superpowers/specs/2026-07-21-hdb-governance-pipeline-design.md`. Key decisions carried over:
- Full HDB resale history (~236k records) via live data.gov.sg, incremental fetch pattern.
- Postgres-backed `raw`/`staging`/`marts`/`audit` schemas replace the parquet bronze/silver/gold layers.
- Validation is batch-scoped (tagged by `run_id`), not whole-table.
- Existing richer feature engineering (elite schools, malls, lease decay) is kept as a second mart (`marts.hdb_extended_features`).
- OneMap auth (email/password → bearer token) confirmed still live as of 2026-07-22; data.gov.sg confirmed to need no API key but does rate-limit anonymous requests.

## File Structure

```
HDB/
├── docker-compose.yml
├── Dockerfile
├── workspace.yaml
├── dagster_home/
│   └── dagster.yaml
├── docker/
│   └── init-db/
│       ├── 01_raw.sql
│       ├── 02_staging.sql
│       ├── 03_audit.sql
│       └── 04_marts.sql
├── hdb_pipeline/
│   ├── __init__.py
│   ├── definitions.py            # Dagster Definitions object
│   ├── validators.py             # ValidationRule/ValidationResult/ValidationRunner + 5 rule classes
│   ├── reference_data.py         # town list, elite schools, expected schemas
│   ├── db.py                     # get_engine(), PostgresAuditWriter
│   ├── resources.py              # Dagster resources: WarehouseResource, OneMapResource
│   ├── onemap_client.py          # OneMap auth + geocode search, with retry
│   ├── geo.py                    # haversine_km()
│   └── assets/
│       ├── __init__.py
│       ├── raw.py                # raw_hdb_resale, raw_school_locations, raw_mrt_stations
│       ├── staging.py            # validated_hdb_resale, staging_geocoded_hdb_resale, staging_schools, staging_mrt_stations
│       ├── marts.py              # marts_hdb_proximity_features, marts_hdb_extended_features
│       └── checks.py             # asset checks
├── legacy/                       # existing scripts + dashboard.py (dashboard repointed, others kept for reference)
├── tests/
│   ├── __init__.py
│   ├── test_validators.py
│   └── test_validation_runner.py
├── .env.example
├── requirements.txt
└── README.md
```

---

## Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `hdb_pipeline/__init__.py`
- Create: `hdb_pipeline/assets/__init__.py`
- Create: `tests/__init__.py`
- Create: `.env.example`
- Create: `pytest.ini`

- [ ] **Step 1: Create `requirements.txt`**

```
dagster==1.8.13
dagster-webserver==1.8.13
dagster-postgres==0.24.13
pandas==2.2.3
numpy==1.26.4
scikit-learn==1.5.2
requests==2.32.3
python-dotenv==1.0.1
SQLAlchemy==2.0.36
psycopg2-binary==2.9.10
pytest==8.3.3
streamlit==1.39.0
```

- [ ] **Step 2: Create package `__init__.py` files (empty)**

Create `hdb_pipeline/__init__.py`, `hdb_pipeline/assets/__init__.py`, `tests/__init__.py` as empty files.

- [ ] **Step 3: Create `.env.example`**

```
API_KEY=
ONEMAP_EMAIL=
ONEMAP_PASSWORD=
WAREHOUSE_PG_PASSWORD=change_me
DAGSTER_PG_PASSWORD=change_me
WAREHOUSE_DATABASE_URL=postgresql://hdb:change_me@localhost:5433/hdb_warehouse
```

- [ ] **Step 4: Create `pytest.ini`**

```ini
[pytest]
testpaths = tests
pythonpath = .
```

- [ ] **Step 5: Install dependencies and verify**

Run: `pip install -r requirements.txt`
Expected: installs without errors.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt hdb_pipeline/__init__.py hdb_pipeline/assets/__init__.py tests/__init__.py .env.example pytest.ini
git commit -m "chore: scaffold hdb_pipeline package"
```

---

## Task 2: Validation framework base classes + NullCheckRule (TDD)

**Files:**
- Create: `hdb_pipeline/validators.py`
- Test: `tests/test_validators.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_validators.py`:

```python
import pandas as pd
from hdb_pipeline.validators import NullCheckRule, ValidationResult


def test_null_check_rule_passes_with_no_nulls():
    df = pd.DataFrame({
        "town": ["BEDOK", "TAMPINES"],
        "resale_price": [400000, 450000],
    })
    rule = NullCheckRule(required_columns=["town", "resale_price"])

    result = rule.check(df)

    assert isinstance(result, ValidationResult)
    assert result.passed is True
    assert result.failing_row_indices == []
    assert result.details["null_counts"] == {"town": 0, "resale_price": 0}


def test_null_check_rule_flags_null_rows():
    df = pd.DataFrame({
        "town": ["BEDOK", None, "TAMPINES"],
        "resale_price": [400000, 450000, None],
    })
    rule = NullCheckRule(required_columns=["town", "resale_price"])

    result = rule.check(df)

    assert result.passed is False
    assert result.failing_row_indices == [1, 2]
    assert result.details["null_counts"] == {"town": 1, "resale_price": 1}
    assert rule.name == "null_check"
    assert rule.severity == "error"
    assert rule.rule_type == "null_check"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_validators.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hdb_pipeline.validators'`

- [ ] **Step 3: Write the implementation**

Create `hdb_pipeline/validators.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class ValidationResult:
    rule_name: str
    passed: bool
    failing_row_indices: list[int]
    details: dict[str, Any]


class ValidationRule:
    """Base class. Each rule returns a ValidationResult."""

    name: str
    severity: str  # "error" (quarantine the row) or "warning" (log only)
    rule_type: str

    def check(self, df: pd.DataFrame) -> ValidationResult:
        raise NotImplementedError


class NullCheckRule(ValidationRule):
    """Fails if any of the given required columns contain nulls."""

    def __init__(self, required_columns: list[str], name: str = "null_check", severity: str = "error"):
        self.required_columns = required_columns
        self.name = name
        self.severity = severity
        self.rule_type = "null_check"

    def check(self, df: pd.DataFrame) -> ValidationResult:
        present_columns = [c for c in self.required_columns if c in df.columns]
        null_counts = {c: int(df[c].isna().sum()) for c in present_columns}

        if present_columns:
            null_mask = df[present_columns].isna().any(axis=1)
        else:
            null_mask = pd.Series(False, index=df.index)

        failing_row_indices = df.index[null_mask].tolist()
        return ValidationResult(
            rule_name=self.name,
            passed=len(failing_row_indices) == 0,
            failing_row_indices=failing_row_indices,
            details={"null_counts": null_counts, "columns_checked": present_columns},
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_validators.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add hdb_pipeline/validators.py tests/test_validators.py
git commit -m "feat: add ValidationRule base classes and NullCheckRule"
```

---

## Task 3: SchemaDriftRule (TDD)

**Files:**
- Modify: `hdb_pipeline/validators.py`
- Modify: `tests/test_validators.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_validators.py`:

```python
from hdb_pipeline.validators import SchemaDriftRule


def test_schema_drift_rule_passes_on_matching_schema():
    df = pd.DataFrame({"town": ["BEDOK"], "resale_price": [400000]})
    rule = SchemaDriftRule(expected_schema={"town": "object", "resale_price": "int64"})

    result = rule.check(df)

    assert result.passed is True
    assert result.failing_row_indices == []
    assert result.details == {"missing_columns": [], "new_columns": [], "type_mismatches": {}}


def test_schema_drift_rule_flags_missing_and_new_columns_and_quarantines_whole_batch():
    df = pd.DataFrame({"town": ["BEDOK", "TAMPINES"], "unexpected_col": [1, 2]})
    rule = SchemaDriftRule(expected_schema={"town": "object", "resale_price": "int64"})

    result = rule.check(df)

    assert result.passed is False
    assert result.details["missing_columns"] == ["resale_price"]
    assert result.details["new_columns"] == ["unexpected_col"]
    # Schema drift can't be trusted row-by-row: the whole batch is flagged.
    assert result.failing_row_indices == [0, 1]


def test_schema_drift_rule_flags_type_mismatch():
    df = pd.DataFrame({"town": ["BEDOK"], "resale_price": ["400000"]})  # string, not int
    rule = SchemaDriftRule(expected_schema={"town": "object", "resale_price": "int64"})

    result = rule.check(df)

    assert result.passed is False
    assert result.details["type_mismatches"] == {"resale_price": {"expected": "int64", "actual": "object"}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_validators.py -v -k schema_drift`
Expected: FAIL with `ImportError: cannot import name 'SchemaDriftRule'`

- [ ] **Step 3: Write the implementation**

Append to `hdb_pipeline/validators.py`:

```python
class SchemaDriftRule(ValidationRule):
    """Compares df.columns/dtypes against an expected schema dict.
    Flags new columns, missing columns, or type mismatches.
    A drifted schema can't be trusted row-by-row, so a failure flags every
    row in the batch rather than trying to guess which rows are affected.
    """

    def __init__(self, expected_schema: dict[str, str], name: str = "schema_drift", severity: str = "error"):
        self.expected_schema = expected_schema
        self.name = name
        self.severity = severity
        self.rule_type = "schema_drift"

    def check(self, df: pd.DataFrame) -> ValidationResult:
        actual_columns = set(df.columns)
        expected_columns = set(self.expected_schema.keys())
        missing_columns = sorted(expected_columns - actual_columns)
        new_columns = sorted(actual_columns - expected_columns)

        type_mismatches = {}
        for column, expected_dtype in self.expected_schema.items():
            if column in df.columns and str(df[column].dtype) != expected_dtype:
                type_mismatches[column] = {"expected": expected_dtype, "actual": str(df[column].dtype)}

        passed = not missing_columns and not new_columns and not type_mismatches
        failing_row_indices = [] if passed else df.index.tolist()

        return ValidationResult(
            rule_name=self.name,
            passed=passed,
            failing_row_indices=failing_row_indices,
            details={
                "missing_columns": missing_columns,
                "new_columns": new_columns,
                "type_mismatches": type_mismatches,
            },
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_validators.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add hdb_pipeline/validators.py tests/test_validators.py
git commit -m "feat: add SchemaDriftRule"
```

---

## Task 4: OutlierRule (TDD)

**Files:**
- Modify: `hdb_pipeline/validators.py`
- Modify: `tests/test_validators.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_validators.py`:

```python
from hdb_pipeline.validators import OutlierRule


def test_outlier_rule_flags_price_far_outside_group_iqr():
    # 5 normal 4-ROOM BEDOK prices clustered ~400k-440k, one wildly high outlier.
    df = pd.DataFrame({
        "town": ["BEDOK"] * 6,
        "flat_type": ["4 ROOM"] * 6,
        "resale_price": [400000, 410000, 420000, 430000, 440000, 5000000],
    })
    rule = OutlierRule(column="resale_price", group_by_cols=["town", "flat_type"])

    result = rule.check(df)

    assert result.passed is False
    assert result.failing_row_indices == [5]
    assert result.severity == "warning"
    assert rule.rule_type == "outlier"


def test_outlier_rule_computes_bounds_per_group_not_globally():
    # A 2-ROOM BEDOK price of 250000 is normal for its group, but would look
    # like a low outlier if compared against 4-ROOM prices globally.
    df = pd.DataFrame({
        "town": ["BEDOK"] * 5 + ["BEDOK"] * 5,
        "flat_type": ["2 ROOM"] * 5 + ["4 ROOM"] * 5,
        "resale_price": [240000, 245000, 250000, 255000, 260000] + [400000, 410000, 420000, 430000, 440000],
    })
    rule = OutlierRule(column="resale_price", group_by_cols=["town", "flat_type"])

    result = rule.check(df)

    assert result.passed is True
    assert result.failing_row_indices == []


def test_outlier_rule_skips_groups_below_minimum_size():
    df = pd.DataFrame({
        "town": ["QUEENSTOWN", "QUEENSTOWN"],
        "flat_type": ["5 ROOM", "5 ROOM"],
        "resale_price": [500000, 5000000],
    })
    rule = OutlierRule(column="resale_price", group_by_cols=["town", "flat_type"])

    result = rule.check(df)

    assert result.passed is True
    assert result.failing_row_indices == []
    assert result.details["skipped_groups"] == ["('QUEENSTOWN', '5 ROOM')"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_validators.py -v -k outlier`
Expected: FAIL with `ImportError: cannot import name 'OutlierRule'`

- [ ] **Step 3: Write the implementation**

Append to `hdb_pipeline/validators.py`:

```python
class OutlierRule(ValidationRule):
    """IQR-based outlier detection, computed per group (e.g. groupby
    town + flat_type) rather than globally.
    """

    MIN_GROUP_SIZE = 5

    def __init__(
        self,
        column: str,
        group_by_cols: list[str],
        k: float = 1.5,
        name: str = "outlier_iqr",
        severity: str = "warning",
    ):
        self.column = column
        self.group_by_cols = group_by_cols
        self.k = k
        self.name = name
        self.severity = severity
        self.rule_type = "outlier"

    def check(self, df: pd.DataFrame) -> ValidationResult:
        failing_row_indices: list[int] = []
        bounds_by_group: dict[str, dict[str, float]] = {}
        skipped_groups: list[str] = []

        for group_key, group_df in df.groupby(self.group_by_cols, dropna=False):
            if len(group_df) < self.MIN_GROUP_SIZE:
                skipped_groups.append(str(group_key))
                continue

            q1 = group_df[self.column].quantile(0.25)
            q3 = group_df[self.column].quantile(0.75)
            iqr = q3 - q1
            lower = q1 - self.k * iqr
            upper = q3 + self.k * iqr

            outliers = group_df[(group_df[self.column] < lower) | (group_df[self.column] > upper)]
            failing_row_indices.extend(outliers.index.tolist())
            bounds_by_group[str(group_key)] = {"lower": float(lower), "upper": float(upper)}

        failing_row_indices.sort()
        return ValidationResult(
            rule_name=self.name,
            passed=len(failing_row_indices) == 0,
            failing_row_indices=failing_row_indices,
            details={
                "outlier_count": len(failing_row_indices),
                "bounds_by_group": bounds_by_group,
                "skipped_groups": skipped_groups,
            },
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_validators.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add hdb_pipeline/validators.py tests/test_validators.py
git commit -m "feat: add OutlierRule with per-group IQR detection"
```

---

## Task 5: ReferentialIntegrityRule (TDD)

**Files:**
- Modify: `hdb_pipeline/validators.py`
- Modify: `tests/test_validators.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_validators.py`:

```python
from hdb_pipeline.validators import ReferentialIntegrityRule


def test_referential_integrity_rule_reference_set_mode():
    df = pd.DataFrame({"town": ["BEDOK", "ATLANTIS", "TAMPINES"]})
    rule = ReferentialIntegrityRule(column="town", reference_set={"BEDOK", "TAMPINES"}, name="valid_town")

    result = rule.check(df)

    assert result.passed is False
    assert result.failing_row_indices == [1]
    assert result.details["invalid_values"] == ["ATLANTIS"]
    assert rule.rule_type == "referential_integrity"


def test_referential_integrity_rule_regex_mode():
    df = pd.DataFrame({"postal_code": ["560123", "12", "738907"]})
    rule = ReferentialIntegrityRule(column="postal_code", pattern=r"^\d{6}$", name="postal_code_format")

    result = rule.check(df)

    assert result.passed is False
    assert result.failing_row_indices == [1]
    assert result.details["invalid_values"] == ["12"]


def test_referential_integrity_rule_passes_when_all_valid():
    df = pd.DataFrame({"town": ["BEDOK", "TAMPINES"]})
    rule = ReferentialIntegrityRule(column="town", reference_set={"BEDOK", "TAMPINES"})

    result = rule.check(df)

    assert result.passed is True
    assert result.failing_row_indices == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_validators.py -v -k referential`
Expected: FAIL with `ImportError: cannot import name 'ReferentialIntegrityRule'`

- [ ] **Step 3: Write the implementation**

Append to `hdb_pipeline/validators.py`:

```python
import re


class ReferentialIntegrityRule(ValidationRule):
    """Checks a column's values against a known reference set
    (e.g. valid HDB town names) or a regex (e.g. postal code format).
    """

    def __init__(
        self,
        column: str,
        reference_set: set[str] | None = None,
        pattern: str | None = None,
        name: str = "referential_integrity",
        severity: str = "error",
    ):
        if reference_set is None and pattern is None:
            raise ValueError("ReferentialIntegrityRule requires either reference_set or pattern")
        self.column = column
        self.reference_set = reference_set
        self.pattern = re.compile(pattern) if pattern else None
        self.name = name
        self.severity = severity
        self.rule_type = "referential_integrity"

    def check(self, df: pd.DataFrame) -> ValidationResult:
        if self.reference_set is not None:
            valid_mask = df[self.column].isin(self.reference_set)
        else:
            valid_mask = df[self.column].astype(str).str.match(self.pattern)

        failing_row_indices = df.index[~valid_mask].tolist()
        invalid_values = sorted(df.loc[failing_row_indices, self.column].astype(str).unique().tolist())

        return ValidationResult(
            rule_name=self.name,
            passed=len(failing_row_indices) == 0,
            failing_row_indices=failing_row_indices,
            details={"invalid_values": invalid_values[:50], "invalid_count": len(failing_row_indices)},
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_validators.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add hdb_pipeline/validators.py tests/test_validators.py
git commit -m "feat: add ReferentialIntegrityRule"
```

---

## Task 6: DuplicateRule (TDD)

**Files:**
- Modify: `hdb_pipeline/validators.py`
- Modify: `tests/test_validators.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_validators.py`:

```python
from hdb_pipeline.validators import DuplicateRule


def test_duplicate_rule_flags_repeats_keeps_first_occurrence():
    df = pd.DataFrame({
        "block": ["215", "215", "310"],
        "street_name": ["CCK CENT", "CCK CENT", "ANG MO KIO AVE 10"],
        "month": ["2024-01", "2024-01", "2024-01"],
        "resale_price": [450000, 450000, 380000],
    })
    rule = DuplicateRule(subset_columns=["block", "street_name", "month", "resale_price"])

    result = rule.check(df)

    assert result.passed is False
    assert result.failing_row_indices == [1]
    assert result.details["duplicate_count"] == 1
    assert rule.rule_type == "duplicate"


def test_duplicate_rule_passes_with_no_duplicates():
    df = pd.DataFrame({
        "block": ["215", "310"],
        "street_name": ["CCK CENT", "ANG MO KIO AVE 10"],
        "month": ["2024-01", "2024-01"],
        "resale_price": [450000, 380000],
    })
    rule = DuplicateRule(subset_columns=["block", "street_name", "month", "resale_price"])

    result = rule.check(df)

    assert result.passed is True
    assert result.failing_row_indices == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_validators.py -v -k duplicate`
Expected: FAIL with `ImportError: cannot import name 'DuplicateRule'`

- [ ] **Step 3: Write the implementation**

Append to `hdb_pipeline/validators.py`:

```python
class DuplicateRule(ValidationRule):
    """Flags rows that duplicate on a given subset of columns.
    The first occurrence of a duplicate group is kept; later repeats are flagged.
    """

    def __init__(self, subset_columns: list[str], name: str = "duplicate_check", severity: str = "error"):
        self.subset_columns = subset_columns
        self.name = name
        self.severity = severity
        self.rule_type = "duplicate"

    def check(self, df: pd.DataFrame) -> ValidationResult:
        duplicate_mask = df.duplicated(subset=self.subset_columns, keep="first")
        failing_row_indices = df.index[duplicate_mask].tolist()

        return ValidationResult(
            rule_name=self.name,
            passed=len(failing_row_indices) == 0,
            failing_row_indices=failing_row_indices,
            details={"duplicate_count": len(failing_row_indices), "subset_columns": self.subset_columns},
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_validators.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add hdb_pipeline/validators.py tests/test_validators.py
git commit -m "feat: add DuplicateRule"
```

---

## Task 7: ValidationRunner (TDD)

**Files:**
- Modify: `hdb_pipeline/validators.py`
- Create: `tests/test_validation_runner.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_validation_runner.py`:

```python
import pandas as pd

from hdb_pipeline.validators import (
    DuplicateRule,
    NullCheckRule,
    OutlierRule,
    ValidationRunner,
)


class FakeAuditWriter:
    """In-memory stand-in for PostgresAuditWriter, used to test ValidationRunner
    without a database."""

    def __init__(self):
        self.validation_results = []
        self.quarantine_rows = []

    def write_validation_result(self, **kwargs):
        self.validation_results.append(kwargs)

    def write_quarantine_rows(self, rows):
        self.quarantine_rows.extend(rows)


def test_validation_runner_logs_every_rule_and_splits_passing_from_quarantined():
    df = pd.DataFrame({
        "town": ["BEDOK", "BEDOK", None],
        "flat_type": ["4 ROOM", "4 ROOM", "4 ROOM"],
        "resale_price": [400000, 410000, 420000],
    })
    rules = [
        NullCheckRule(required_columns=["town"]),  # error severity, row 2 fails
    ]
    writer = FakeAuditWriter()
    runner = ValidationRunner(audit_writer=writer)

    passing_df, quarantined_df = runner.run(
        df, rules, run_id="run-1", asset_name="validated_hdb_resale", source_table="staging.hdb_resale"
    )

    assert len(writer.validation_results) == 1
    assert writer.validation_results[0]["rule_name"] == "null_check"
    assert writer.validation_results[0]["passed"] is False
    assert writer.validation_results[0]["rows_checked"] == 3
    assert writer.validation_results[0]["rows_failed"] == 1

    assert list(passing_df.index) == [0, 1]
    assert list(quarantined_df.index) == [2]

    assert len(writer.quarantine_rows) == 1
    assert writer.quarantine_rows[0]["rule_name_failed"] == "null_check"
    assert writer.quarantine_rows[0]["run_id"] == "run-1"
    assert writer.quarantine_rows[0]["source_table"] == "staging.hdb_resale"
    assert writer.quarantine_rows[0]["row_data"]["resale_price"] == 420000


def test_validation_runner_warning_severity_rules_do_not_quarantine():
    df = pd.DataFrame({
        "town": ["BEDOK"] * 5 + ["BEDOK"],
        "flat_type": ["4 ROOM"] * 6,
        "resale_price": [400000, 410000, 420000, 430000, 440000, 5000000],
    })
    rules = [OutlierRule(column="resale_price", group_by_cols=["town", "flat_type"])]  # warning severity
    writer = FakeAuditWriter()
    runner = ValidationRunner(audit_writer=writer)

    passing_df, quarantined_df = runner.run(
        df, rules, run_id="run-2", asset_name="validated_hdb_resale", source_table="staging.hdb_resale"
    )

    assert len(passing_df) == 6  # nothing quarantined
    assert len(quarantined_df) == 0
    assert writer.quarantine_rows == []
    assert writer.validation_results[0]["passed"] is False  # but still logged as failed


def test_validation_runner_one_quarantine_row_per_failing_rule():
    df = pd.DataFrame({
        "block": ["215", "215"],
        "street_name": ["CCK CENT", "CCK CENT"],
        "month": ["2024-01", "2024-01"],
        "resale_price": [None, None],
    })
    rules = [
        NullCheckRule(required_columns=["resale_price"]),
        DuplicateRule(subset_columns=["block", "street_name", "month", "resale_price"]),
    ]
    writer = FakeAuditWriter()
    runner = ValidationRunner(audit_writer=writer)

    passing_df, quarantined_df = runner.run(
        df, rules, run_id="run-3", asset_name="validated_hdb_resale", source_table="staging.hdb_resale"
    )

    assert len(quarantined_df) == 1  # row 1 fails both rules but is quarantined once
    failed_rule_names = {row["rule_name_failed"] for row in writer.quarantine_rows}
    assert failed_rule_names == {"null_check", "duplicate_check"}
    assert len(writer.quarantine_rows) == 2  # but logged once per failing rule
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_validation_runner.py -v`
Expected: FAIL with `ImportError: cannot import name 'ValidationRunner'`

- [ ] **Step 3: Write the implementation**

Append to `hdb_pipeline/validators.py`:

```python
class ValidationRunner:
    """Runs a list of rules against a DataFrame, writes every result to
    audit.validation_results, splits the DataFrame into (passing_df,
    quarantined_df), and writes quarantined rows to audit.quarantine with
    the specific rule_name_failed attached to each row.
    """

    def __init__(self, audit_writer):
        self.audit_writer = audit_writer

    def run(
        self,
        df: pd.DataFrame,
        rules: list[ValidationRule],
        run_id: str,
        asset_name: str,
        source_table: str,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        failing_rule_by_index: dict[int, list[str]] = {}

        for rule in rules:
            result = rule.check(df)
            self.audit_writer.write_validation_result(
                run_id=run_id,
                asset_name=asset_name,
                rule_name=result.rule_name,
                rule_type=rule.rule_type,
                passed=result.passed,
                rows_checked=len(df),
                rows_failed=len(result.failing_row_indices),
                details=result.details,
            )

            if rule.severity == "error" and not result.passed:
                for idx in result.failing_row_indices:
                    failing_rule_by_index.setdefault(idx, []).append(result.rule_name)

        quarantine_indices = sorted(failing_rule_by_index.keys())
        passing_df = df.drop(index=quarantine_indices)
        quarantined_df = df.loc[quarantine_indices]

        quarantine_payload = []
        for idx, rule_names in failing_rule_by_index.items():
            row_data = df.loc[idx].to_dict()
            for rule_name in rule_names:
                quarantine_payload.append({
                    "source_table": source_table,
                    "run_id": run_id,
                    "rule_name_failed": rule_name,
                    "row_data": row_data,
                })

        if quarantine_payload:
            self.audit_writer.write_quarantine_rows(quarantine_payload)

        return passing_df, quarantined_df
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ -v`
Expected: PASS (16 tests total)

- [ ] **Step 5: Commit**

```bash
git add hdb_pipeline/validators.py tests/test_validation_runner.py
git commit -m "feat: add ValidationRunner orchestrating rules, audit log, and quarantine split"
```

This completes the validation framework. Everything from here on is infrastructure (DB, Docker) and Dagster assets that use it.

---

## Task 8: Database schema DDL

**Files:**
- Create: `docker/init-db/01_raw.sql`
- Create: `docker/init-db/02_staging.sql`
- Create: `docker/init-db/03_audit.sql`
- Create: `docker/init-db/04_marts.sql`

- [ ] **Step 1: Create `docker/init-db/01_raw.sql`**

```sql
CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE raw.hdb_resale_snapshot (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_json JSONB NOT NULL
);
CREATE INDEX idx_hdb_resale_snapshot_run_id ON raw.hdb_resale_snapshot (run_id);

CREATE TABLE raw.school_locations_snapshot (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_json JSONB NOT NULL
);
CREATE INDEX idx_school_locations_snapshot_run_id ON raw.school_locations_snapshot (run_id);

CREATE TABLE raw.mrt_stations_snapshot (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_json JSONB NOT NULL
);
CREATE INDEX idx_mrt_stations_snapshot_run_id ON raw.mrt_stations_snapshot (run_id);
```

- [ ] **Step 2: Create `docker/init-db/02_staging.sql`**

```sql
CREATE SCHEMA IF NOT EXISTS staging;

CREATE TABLE staging.hdb_resale (
    id BIGSERIAL PRIMARY KEY,
    source_raw_id BIGINT,
    town TEXT NOT NULL,
    flat_type TEXT NOT NULL,
    block TEXT NOT NULL,
    street_name TEXT NOT NULL,
    storey_range TEXT,
    floor_area_sqm NUMERIC,
    flat_model TEXT,
    lease_commence_date INTEGER,
    resale_price NUMERIC NOT NULL,
    month TEXT NOT NULL,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    fetched_at TIMESTAMPTZ
);
CREATE INDEX idx_staging_hdb_resale_town_flat_type ON staging.hdb_resale (town, flat_type);
CREATE INDEX idx_staging_hdb_resale_month ON staging.hdb_resale (month);

CREATE TABLE staging.schools (
    id BIGSERIAL PRIMARY KEY,
    school_name TEXT NOT NULL,
    address TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION
);

CREATE TABLE staging.mrt_stations (
    id BIGSERIAL PRIMARY KEY,
    station_name TEXT NOT NULL,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION
);

CREATE TABLE staging.geocode_cache (
    address_query TEXT PRIMARY KEY,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    matched_address TEXT,
    geocoded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- [ ] **Step 3: Create `docker/init-db/03_audit.sql`**

```sql
CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE audit.validation_results (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL,
    asset_name TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    rule_type TEXT NOT NULL,
    passed BOOLEAN NOT NULL,
    rows_checked INTEGER NOT NULL,
    rows_failed INTEGER NOT NULL,
    details_json JSONB,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_validation_results_run_id ON audit.validation_results (run_id);
CREATE INDEX idx_validation_results_asset_name ON audit.validation_results (asset_name);

CREATE TABLE audit.quarantine (
    id BIGSERIAL PRIMARY KEY,
    source_table TEXT NOT NULL,
    run_id UUID NOT NULL,
    rule_name_failed TEXT NOT NULL,
    row_data_json JSONB NOT NULL,
    quarantined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX idx_quarantine_run_id ON audit.quarantine (run_id);
CREATE INDEX idx_quarantine_source_table ON audit.quarantine (source_table);
```

- [ ] **Step 4: Create `docker/init-db/04_marts.sql`**

```sql
CREATE SCHEMA IF NOT EXISTS marts;

CREATE TABLE marts.hdb_proximity_features (
    id BIGSERIAL PRIMARY KEY,
    town TEXT NOT NULL,
    flat_type TEXT NOT NULL,
    resale_price NUMERIC NOT NULL,
    floor_area_sqm NUMERIC,
    nearest_mrt_name TEXT,
    nearest_mrt_distance_km DOUBLE PRECISION,
    nearest_school_name TEXT,
    nearest_school_distance_km DOUBLE PRECISION,
    month TEXT NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE marts.hdb_extended_features (
    id BIGSERIAL PRIMARY KEY,
    town TEXT NOT NULL,
    flat_type TEXT NOT NULL,
    resale_price NUMERIC NOT NULL,
    floor_area_sqm NUMERIC,
    dist_to_cbd_km DOUBLE PRECISION,
    dist_to_elite_school_km DOUBLE PRECISION,
    within_1km_elite_school BOOLEAN,
    malls_within_2km INTEGER,
    estate_maturity TEXT,
    floor_tier TEXT,
    remaining_lease_years INTEGER,
    lease_critical_status TEXT,
    mrt_walk_time_mins DOUBLE PRECISION,
    month TEXT NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- [ ] **Step 5: Commit**

```bash
git add docker/init-db/
git commit -m "feat: add raw/staging/audit/marts schema DDL"
```

---

## Task 9: Docker Compose + Dagster infra files

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `workspace.yaml`
- Create: `dagster_home/dagster.yaml`

- [ ] **Step 1: Create `Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /opt/dagster/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY hdb_pipeline/ ./hdb_pipeline/
COPY workspace.yaml .

ENV DAGSTER_HOME=/opt/dagster/dagster_home
RUN mkdir -p $DAGSTER_HOME
COPY dagster_home/dagster.yaml $DAGSTER_HOME/dagster.yaml
```

- [ ] **Step 2: Create `dagster_home/dagster.yaml`**

```yaml
storage:
  postgres:
    postgres_db:
      username: dagster
      password:
        env: DAGSTER_PG_PASSWORD
      hostname: dagster_postgres
      db_name: dagster
      port: 5432
```

- [ ] **Step 3: Create `workspace.yaml`**

```yaml
load_from:
  - python_module: hdb_pipeline.definitions
```

- [ ] **Step 4: Create `docker-compose.yml`**

```yaml
services:
  warehouse_postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: hdb
      POSTGRES_PASSWORD: ${WAREHOUSE_PG_PASSWORD}
      POSTGRES_DB: hdb_warehouse
    volumes:
      - ./docker/init-db:/docker-entrypoint-initdb.d
      - warehouse_data:/var/lib/postgresql/data
    ports:
      - "5433:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U hdb"]
      interval: 5s
      timeout: 5s
      retries: 10

  dagster_postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: dagster
      POSTGRES_PASSWORD: ${DAGSTER_PG_PASSWORD}
      POSTGRES_DB: dagster
    volumes:
      - dagster_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U dagster"]
      interval: 5s
      timeout: 5s
      retries: 10

  dagster_webserver:
    build: .
    command: ["dagster-webserver", "-h", "0.0.0.0", "-p", "3000", "-w", "workspace.yaml"]
    environment:
      WAREHOUSE_DATABASE_URL: postgresql://hdb:${WAREHOUSE_PG_PASSWORD}@warehouse_postgres:5432/hdb_warehouse
      DAGSTER_PG_PASSWORD: ${DAGSTER_PG_PASSWORD}
      API_KEY: ${API_KEY}
      ONEMAP_EMAIL: ${ONEMAP_EMAIL}
      ONEMAP_PASSWORD: ${ONEMAP_PASSWORD}
    ports:
      - "3000:3000"
    depends_on:
      warehouse_postgres:
        condition: service_healthy
      dagster_postgres:
        condition: service_healthy

  dagster_daemon:
    build: .
    command: ["dagster-daemon", "run"]
    environment:
      WAREHOUSE_DATABASE_URL: postgresql://hdb:${WAREHOUSE_PG_PASSWORD}@warehouse_postgres:5432/hdb_warehouse
      DAGSTER_PG_PASSWORD: ${DAGSTER_PG_PASSWORD}
      API_KEY: ${API_KEY}
      ONEMAP_EMAIL: ${ONEMAP_EMAIL}
      ONEMAP_PASSWORD: ${ONEMAP_PASSWORD}
    depends_on:
      warehouse_postgres:
        condition: service_healthy
      dagster_postgres:
        condition: service_healthy

volumes:
  warehouse_data:
  dagster_data:
```

- [ ] **Step 5: Create local `.env` from `.env.example` and fill in real credentials**

Copy `.env.example` to `.env` and fill in `API_KEY` (if you have one — the datastore_search endpoints work without it), `ONEMAP_EMAIL`, `ONEMAP_PASSWORD` (the same ones already used in the legacy `onemap_utils.py`), and set real values for `WAREHOUSE_PG_PASSWORD` / `DAGSTER_PG_PASSWORD`. `.env` is gitignored — do not commit it.

- [ ] **Step 6: Bring up just the warehouse and verify schema creation**

Run: `docker compose up -d warehouse_postgres` then wait for healthy, then:
`docker compose exec warehouse_postgres psql -U hdb -d hdb_warehouse -c "\dn"`
Expected: lists `raw`, `staging`, `audit`, `marts`, `public` schemas.

Run: `docker compose exec warehouse_postgres psql -U hdb -d hdb_warehouse -c "\dt raw.*"`
Expected: lists the three `raw.*` tables.

- [ ] **Step 7: Commit**

```bash
git add Dockerfile docker-compose.yml workspace.yaml dagster_home/dagster.yaml
git commit -m "feat: add Docker Compose stack (warehouse + dagster postgres, webserver, daemon)"
```

---

## Task 10: `db.py` — engine + PostgresAuditWriter

**Files:**
- Create: `hdb_pipeline/db.py`

No TDD here — this is a thin DB-adapter module that implements the same interface `FakeAuditWriter` already exercises in `tests/test_validation_runner.py`; it's verified end-to-end in Task 26, not in isolation.

- [ ] **Step 1: Create `hdb_pipeline/db.py`**

```python
from __future__ import annotations

import json
import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def get_engine() -> Engine:
    database_url = os.environ["WAREHOUSE_DATABASE_URL"]
    return create_engine(database_url)


class PostgresAuditWriter:
    """Implements the audit_writer interface ValidationRunner expects:
    write_validation_result(**kwargs) and write_quarantine_rows(list[dict]).
    """

    def __init__(self, engine: Engine):
        self.engine = engine

    def write_validation_result(
        self,
        run_id: str,
        asset_name: str,
        rule_name: str,
        rule_type: str,
        passed: bool,
        rows_checked: int,
        rows_failed: int,
        details: dict,
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO audit.validation_results
                        (run_id, asset_name, rule_name, rule_type, passed, rows_checked, rows_failed, details_json)
                    VALUES
                        (:run_id, :asset_name, :rule_name, :rule_type, :passed, :rows_checked, :rows_failed, CAST(:details_json AS JSONB))
                    """
                ),
                {
                    "run_id": run_id,
                    "asset_name": asset_name,
                    "rule_name": rule_name,
                    "rule_type": rule_type,
                    "passed": passed,
                    "rows_checked": rows_checked,
                    "rows_failed": rows_failed,
                    "details_json": json.dumps(details, default=str),
                },
            )

    def write_quarantine_rows(self, quarantine_payload: list[dict]) -> None:
        if not quarantine_payload:
            return
        with self.engine.begin() as conn:
            for row in quarantine_payload:
                conn.execute(
                    text(
                        """
                        INSERT INTO audit.quarantine
                            (source_table, run_id, rule_name_failed, row_data_json)
                        VALUES
                            (:source_table, :run_id, :rule_name_failed, CAST(:row_data_json AS JSONB))
                        """
                    ),
                    {
                        "source_table": row["source_table"],
                        "run_id": row["run_id"],
                        "rule_name_failed": row["rule_name_failed"],
                        "row_data_json": json.dumps(row["row_data"], default=str),
                    },
                )
```

- [ ] **Step 2: Commit**

```bash
git add hdb_pipeline/db.py
git commit -m "feat: add PostgresAuditWriter implementing the ValidationRunner audit interface"
```

---

## Task 11: Reference data

**Files:**
- Create: `hdb_pipeline/reference_data.py`

- [ ] **Step 1: Create `hdb_pipeline/reference_data.py`**

```python
VALID_HDB_TOWNS = {
    "ANG MO KIO", "BEDOK", "BISHAN", "BUKIT BATOK", "BUKIT MERAH",
    "BUKIT PANJANG", "BUKIT TIMAH", "CENTRAL AREA", "CHOA CHU KANG",
    "CLEMENTI", "GEYLANG", "HOUGANG", "JURONG EAST", "JURONG WEST",
    "KALLANG/WHAMPOA", "MARINE PARADE", "PASIR RIS", "PUNGGOL",
    "QUEENSTOWN", "SEMBAWANG", "SENGKANG", "SERANGOON", "TAMPINES",
    "TOA PAYOH", "WOODLANDS", "YISHUN",
}

# Expected shape of a raw HDB resale record as returned by the data.gov.sg
# datastore_search API. All text fields except _id come back as JSON strings
# (even resale_price and floor_area_sqm), so schema drift here means the API
# actually changed its response shape, not just "needs type casting."
EXPECTED_HDB_RESALE_SCHEMA = {
    "month": "object",
    "town": "object",
    "flat_type": "object",
    "block": "object",
    "street_name": "object",
    "storey_range": "object",
    "floor_area_sqm": "object",
    "flat_model": "object",
    "lease_commence_date": "object",
    "remaining_lease": "object",
    "resale_price": "object",
    "_id": "int64",
}

MATURE_TOWNS = {
    "ANG MO KIO", "BEDOK", "BISHAN", "BUKIT MERAH", "BUKIT TIMAH",
    "CENTRAL AREA", "CLEMENTI", "GEYLANG", "KALLANG/WHAMPOA",
    "MARINE PARADE", "PASIR RIS", "QUEENSTOWN", "SERANGOON",
    "TAMPINES", "TOA PAYOH",
}

ELITE_SCHOOLS = {
    "TAO NAN SCHOOL", "AI TONG SCHOOL", "NANYANG PRIMARY SCHOOL",
    "PEI HWA PRESBYTERIAN PRIMARY SCHOOL", "METHODIST GIRLS' SCHOOL (PRIMARY)",
    "NAN CHIAU PRIMARY SCHOOL", "CHIJ ST. NICHOLAS GIRLS' SCHOOL",
    "CHIJ PRIMARY (TOA PAYOH)", "RED SWASTIKA SCHOOL", "KONG HWA SCHOOL",
    "ANGLO-CHINESE SCHOOL (JUNIOR)", "MAHA BODHI SCHOOL",
    "HOLY INNOCENTS' PRIMARY SCHOOL", "ST. JOSEPH'S INSTITUTION JUNIOR",
    "CHONGFU SCHOOL", "NAN HUA PRIMARY SCHOOL", "ANGLO-CHINESE SCHOOL (PRIMARY)",
    "CATHOLIC HIGH SCHOOL", "MARIS STELLA HIGH SCHOOL", "ROSYTH SCHOOL",
}

CBD_LAT, CBD_LON = 1.2839, 103.8515
```

- [ ] **Step 2: Commit**

```bash
git add hdb_pipeline/reference_data.py
git commit -m "feat: add reference data (town list, expected schema, elite schools)"
```

---

## Task 12: `geo.py` — haversine helper (TDD)

**Files:**
- Create: `hdb_pipeline/geo.py`
- Create: `tests/test_geo.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_geo.py`:

```python
from hdb_pipeline.geo import haversine_km


def test_haversine_km_zero_distance_for_same_point():
    assert haversine_km(1.35, 103.82, 1.35, 103.82) == 0.0


def test_haversine_km_known_distance():
    # Raffles Place (1.2839, 103.8515) to Ang Mo Kio MRT (~1.3700, 103.8495)
    # is roughly 9.6 km as the crow flies.
    distance = haversine_km(1.2839, 103.8515, 1.3700, 103.8495)
    assert 9.0 < distance < 10.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_geo.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hdb_pipeline.geo'`

- [ ] **Step 3: Write the implementation**

Create `hdb_pipeline/geo.py`:

```python
import numpy as np


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    c = 2 * np.arcsin(np.sqrt(a))
    return 6371.0 * c
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_geo.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add hdb_pipeline/geo.py tests/test_geo.py
git commit -m "feat: add haversine distance helper"
```

---

## Task 13: `onemap_client.py` — OneMap auth + geocode (with retry)

**Files:**
- Create: `hdb_pipeline/onemap_client.py`

No TDD (network I/O) — exercised end-to-end in Task 26.

- [ ] **Step 1: Create `hdb_pipeline/onemap_client.py`**

```python
from __future__ import annotations

import time

import requests

ONEMAP_TOKEN_URL = "https://www.onemap.gov.sg/api/auth/post/getToken"
ONEMAP_SEARCH_URL = "https://www.onemap.gov.sg/api/common/elastic/search"


class OneMapClient:
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self._token: str | None = None

    def _get_token(self) -> str:
        if self._token:
            return self._token
        response = requests.post(
            ONEMAP_TOKEN_URL, json={"email": self.email, "password": self.password}, timeout=10
        )
        response.raise_for_status()
        self._token = response.json()["access_token"]
        return self._token

    def geocode(self, search_val: str) -> dict | None:
        """Returns {"latitude": float, "longitude": float, "matched_address": str}
        or None if OneMap found no match."""
        for attempt in range(3):
            token = self._get_token()
            response = requests.get(
                ONEMAP_SEARCH_URL,
                params={"searchVal": search_val, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": "1"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            if response.status_code == 401:
                self._token = None  # token expired/rejected, force re-auth next loop
                continue
            if response.status_code == 429:
                time.sleep(5)
                continue
            response.raise_for_status()
            data = response.json()
            if data.get("found", 0) > 0:
                best = data["results"][0]
                return {
                    "latitude": float(best["LATITUDE"]),
                    "longitude": float(best["LONGITUDE"]),
                    "matched_address": best.get("ADDRESS", ""),
                }
            return None
        return None
```

- [ ] **Step 2: Commit**

```bash
git add hdb_pipeline/onemap_client.py
git commit -m "feat: add OneMap geocoding client with token retry on 401/429"
```

---

## Task 14: Dagster resources

**Files:**
- Create: `hdb_pipeline/resources.py`

- [ ] **Step 1: Create `hdb_pipeline/resources.py`**

```python
import os

import dagster as dg
from sqlalchemy.engine import Engine

from hdb_pipeline.db import get_engine


class WarehouseResource(dg.ConfigurableResource):
    def get_engine(self) -> Engine:
        return get_engine()


class OneMapResource(dg.ConfigurableResource):
    email: str = os.environ.get("ONEMAP_EMAIL", "")
    password: str = os.environ.get("ONEMAP_PASSWORD", "")
```

- [ ] **Step 2: Commit**

```bash
git add hdb_pipeline/resources.py
git commit -m "feat: add Dagster WarehouseResource and OneMapResource"
```

---

## Task 15: Raw ingestion assets

**Files:**
- Create: `hdb_pipeline/assets/raw.py`

No TDD (network + DB I/O) — exercised end-to-end in Task 26.

- [ ] **Step 1: Create `hdb_pipeline/assets/raw.py`**

```python
from __future__ import annotations

import json
import os
import time
import uuid

import dagster as dg
import requests
from sqlalchemy import text

from hdb_pipeline.resources import WarehouseResource

HDB_DATASET_ID = "d_8b84c4ee58e3cfc0ece0d773c8ca6abc"
SCHOOL_DATASET_ID = "d_688b934f82c1059ed0a6993d2a829089"
MRT_DATASET_ID = "d_8d886e3a83934d7447acdf5bc6959999"
DATASTORE_SEARCH_URL = "https://data.gov.sg/api/action/datastore_search"
POLL_DOWNLOAD_URL_TEMPLATE = "https://api-open.data.gov.sg/v1/public/api/datasets/{dataset_id}/poll-download"


def _fetch_datastore_page(dataset_id: str, offset: int, limit: int) -> list[dict]:
    headers = {}
    api_key = os.environ.get("API_KEY")
    if api_key:
        headers["x-api-key"] = api_key

    for attempt in range(5):
        response = requests.get(
            DATASTORE_SEARCH_URL,
            params={"resource_id": dataset_id, "limit": limit, "offset": offset, "sort": "month desc"},
            headers=headers,
            timeout=30,
        )
        if response.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        response.raise_for_status()
        return response.json()["result"]["records"]

    raise RuntimeError(f"Rate limited fetching dataset {dataset_id} after 5 retries")


def _insert_raw_rows(engine, table: str, run_id: str, rows: list[dict]) -> None:
    if not rows:
        return
    with engine.begin() as conn:
        for row in rows:
            conn.execute(
                text(f"INSERT INTO raw.{table} (run_id, raw_json) VALUES (:run_id, CAST(:raw_json AS JSONB))"),
                {"run_id": run_id, "raw_json": json.dumps(row)},
            )


@dg.asset(group_name="raw")
def raw_hdb_resale(context: dg.AssetExecutionContext, warehouse: WarehouseResource) -> str:
    """Incrementally fetches HDB resale records newer than what's already in
    raw.hdb_resale_snapshot. First run pulls full history."""
    engine = warehouse.get_engine()
    run_id = str(uuid.uuid4())

    with engine.connect() as conn:
        latest_month = conn.execute(
            text("SELECT MAX(raw_json->>'month') FROM raw.hdb_resale_snapshot")
        ).scalar()

    offset = 0
    new_row_count = 0
    keep_fetching = True

    while keep_fetching:
        records = _fetch_datastore_page(HDB_DATASET_ID, offset, 5000)
        if not records:
            break

        batch = []
        for row in records:
            if latest_month and row["month"] <= latest_month:
                keep_fetching = False
                break
            batch.append(row)

        _insert_raw_rows(engine, "hdb_resale_snapshot", run_id, batch)
        new_row_count += len(batch)
        context.log.info(f"Fetched offset={offset}, new_rows_so_far={new_row_count}")

        if not keep_fetching:
            break
        offset += 5000
        time.sleep(0.5)

    context.add_output_metadata({"run_id": run_id, "new_rows": new_row_count})
    return run_id


@dg.asset(group_name="raw")
def raw_school_locations(context: dg.AssetExecutionContext, warehouse: WarehouseResource) -> str:
    engine = warehouse.get_engine()
    run_id = str(uuid.uuid4())

    offset = 0
    total = 0
    while True:
        records = _fetch_datastore_page(SCHOOL_DATASET_ID, offset, 1000)
        if not records:
            break
        _insert_raw_rows(engine, "school_locations_snapshot", run_id, records)
        total += len(records)
        offset += 1000
        time.sleep(0.5)

    context.add_output_metadata({"run_id": run_id, "rows": total})
    return run_id


@dg.asset(group_name="raw")
def raw_mrt_stations(context: dg.AssetExecutionContext, warehouse: WarehouseResource) -> str:
    engine = warehouse.get_engine()
    run_id = str(uuid.uuid4())

    poll_url = POLL_DOWNLOAD_URL_TEMPLATE.format(dataset_id=MRT_DATASET_ID)
    for attempt in range(5):
        response = requests.get(poll_url, timeout=30)
        if response.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        response.raise_for_status()
        break
    else:
        raise RuntimeError("Rate limited polling MRT dataset download after 5 retries")

    signed_url = response.json()["data"]["url"]
    geojson_response = requests.get(signed_url, timeout=60)
    geojson_response.raise_for_status()
    features = geojson_response.json()["features"]

    _insert_raw_rows(engine, "mrt_stations_snapshot", run_id, features)
    context.add_output_metadata({"run_id": run_id, "rows": len(features)})
    return run_id
```

- [ ] **Step 2: Commit**

```bash
git add hdb_pipeline/assets/raw.py
git commit -m "feat: add raw ingestion assets (hdb resale, schools, mrt stations)"
```

---

## Task 16: `validated_hdb_resale` asset

**Files:**
- Create: `hdb_pipeline/assets/staging.py`

- [ ] **Step 1: Create `hdb_pipeline/assets/staging.py` with the validation asset**

```python
from __future__ import annotations

import time

import dagster as dg
import pandas as pd
from sqlalchemy import text

from hdb_pipeline.db import PostgresAuditWriter
from hdb_pipeline.onemap_client import OneMapClient
from hdb_pipeline.reference_data import EXPECTED_HDB_RESALE_SCHEMA, VALID_HDB_TOWNS
from hdb_pipeline.resources import OneMapResource, WarehouseResource
from hdb_pipeline.validators import (
    DuplicateRule,
    NullCheckRule,
    OutlierRule,
    ReferentialIntegrityRule,
    SchemaDriftRule,
    ValidationRunner,
)

STAGING_HDB_COLUMNS = [
    "source_raw_id", "town", "flat_type", "block", "street_name", "storey_range",
    "floor_area_sqm", "flat_model", "lease_commence_date", "resale_price", "month",
]


@dg.asset(group_name="staging")
def validated_hdb_resale(
    context: dg.AssetExecutionContext, warehouse: WarehouseResource, raw_hdb_resale: str
) -> int:
    run_id = raw_hdb_resale
    engine = warehouse.get_engine()

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, raw_json FROM raw.hdb_resale_snapshot WHERE run_id = :run_id"),
            {"run_id": run_id},
        ).fetchall()

    if not rows:
        context.add_output_metadata({"rows_landed": 0, "rows_quarantined": 0})
        return 0

    df = pd.DataFrame([r.raw_json for r in rows])
    df["source_raw_id"] = [r.id for r in rows]

    rules = [
        SchemaDriftRule(expected_schema=EXPECTED_HDB_RESALE_SCHEMA),
    ]
    runner = ValidationRunner(audit_writer=PostgresAuditWriter(engine))
    schema_checked_df, schema_failed_df = runner.run(
        df, rules, run_id=run_id, asset_name="validated_hdb_resale", source_table="staging.hdb_resale"
    )

    # If schema drifted, every row in the batch was quarantined above and
    # there is nothing safely typeable left to run the remaining rules on.
    if schema_checked_df.empty:
        context.add_output_metadata({"rows_landed": 0, "rows_quarantined": len(schema_failed_df)})
        return 0

    typed_df = schema_checked_df.copy()
    typed_df["floor_area_sqm"] = pd.to_numeric(typed_df["floor_area_sqm"], errors="coerce")
    typed_df["resale_price"] = pd.to_numeric(typed_df["resale_price"], errors="coerce")
    typed_df["lease_commence_date"] = pd.to_numeric(typed_df["lease_commence_date"], errors="coerce")

    remaining_rules = [
        NullCheckRule(required_columns=["town", "flat_type", "block", "street_name", "resale_price", "month"]),
        ReferentialIntegrityRule(column="town", reference_set=VALID_HDB_TOWNS, name="valid_town"),
        DuplicateRule(subset_columns=["block", "street_name", "month", "resale_price"]),
        OutlierRule(column="resale_price", group_by_cols=["town", "flat_type"]),
    ]
    passing_df, quarantined_df = runner.run(
        typed_df, remaining_rules, run_id=run_id, asset_name="validated_hdb_resale", source_table="staging.hdb_resale"
    )

    if not passing_df.empty:
        insert_df = passing_df[STAGING_HDB_COLUMNS].copy()
        insert_df["fetched_at"] = pd.Timestamp.utcnow()
        insert_df.to_sql("hdb_resale", engine, schema="staging", if_exists="append", index=False)

    total_quarantined = len(schema_failed_df) + len(quarantined_df)
    context.add_output_metadata({
        "rows_landed": len(passing_df),
        "rows_quarantined": total_quarantined,
        "quarantine_rate": round(total_quarantined / len(df), 4) if len(df) else 0,
    })
    return len(passing_df)
```

- [ ] **Step 2: Commit**

```bash
git add hdb_pipeline/assets/staging.py
git commit -m "feat: add validated_hdb_resale asset (schema drift, null, referential, duplicate, outlier rules)"
```

---

## Task 17: `staging_geocoded_hdb_resale` asset

**Files:**
- Modify: `hdb_pipeline/assets/staging.py`

- [ ] **Step 1: Add `import uuid` to the top of `hdb_pipeline/assets/staging.py`**

Add `import uuid` alongside the existing `import time` line at the top of the file.

- [ ] **Step 2: Append the geocoding asset to `hdb_pipeline/assets/staging.py`**

```python
@dg.asset(group_name="staging")
def staging_geocoded_hdb_resale(
    context: dg.AssetExecutionContext,
    warehouse: WarehouseResource,
    onemap: OneMapResource,
    validated_hdb_resale: int,
) -> int:
    """Backfills lat/long on staging.hdb_resale rows missing coordinates,
    using staging.geocode_cache first. Unlike the original pipeline's
    df.dropna(subset=['latitude','longitude']), rows that fail geocoding are
    NOT deleted — the transaction data is still valid even without
    coordinates. Instead, the coverage gap is logged to
    audit.validation_results as a warning, with the specific unresolved
    addresses in details_json, so the gap is auditable instead of invisible.
    """
    engine = warehouse.get_engine()
    client = OneMapClient(onemap.email, onemap.password)

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, block, street_name FROM staging.hdb_resale WHERE latitude IS NULL")
        ).fetchall()

    if not rows:
        context.add_output_metadata({"rows_geocoded": 0, "rows_unresolved": 0})
        return 0

    addresses = sorted({f"{r.block} {r.street_name}" for r in rows})

    with engine.connect() as conn:
        cached = conn.execute(
            text("SELECT address_query, latitude, longitude FROM staging.geocode_cache WHERE address_query = ANY(:addresses)"),
            {"addresses": addresses},
        ).fetchall()
    cache_map = {r.address_query: (r.latitude, r.longitude) for r in cached}

    unresolved: list[str] = []
    for address in [a for a in addresses if a not in cache_map]:
        result = client.geocode(address)
        if result:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """INSERT INTO staging.geocode_cache (address_query, latitude, longitude, matched_address)
                           VALUES (:address_query, :latitude, :longitude, :matched_address)
                           ON CONFLICT (address_query) DO NOTHING"""
                    ),
                    {"address_query": address, **result},
                )
            cache_map[address] = (result["latitude"], result["longitude"])
        else:
            unresolved.append(address)
        time.sleep(0.2)

    geocoded_count = 0
    with engine.begin() as conn:
        for r in rows:
            address = f"{r.block} {r.street_name}"
            if address in cache_map:
                lat, lon = cache_map[address]
                conn.execute(
                    text("UPDATE staging.hdb_resale SET latitude = :lat, longitude = :lon WHERE id = :id"),
                    {"lat": lat, "lon": lon, "id": r.id},
                )
                geocoded_count += 1

    unresolved_row_count = sum(1 for r in rows if f"{r.block} {r.street_name}" in unresolved)

    PostgresAuditWriter(engine).write_validation_result(
        run_id=str(uuid.uuid4()),
        asset_name="staging_geocoded_hdb_resale",
        rule_name="geocode_coverage",
        rule_type="null_check",
        passed=(unresolved_row_count == 0),
        rows_checked=len(rows),
        rows_failed=unresolved_row_count,
        details={"unresolved_addresses": unresolved, "unresolved_row_count": unresolved_row_count},
    )

    context.add_output_metadata({
        "rows_geocoded": geocoded_count,
        "rows_unresolved": unresolved_row_count,
        "unresolved_addresses_sample": unresolved[:20],
    })
    return geocoded_count
```

The `validated_hdb_resale` parameter is the upstream asset's returned row-count (an `int`), used only
to declare the Dagster dependency (so this asset runs after validation lands new rows) — it is not
used as a run_id. Geocoding operates on the accumulated backlog of ungeocoded rows across all runs, so
this asset mints its own fresh `run_id` via `uuid.uuid4()` for its audit log entry.

- [ ] **Step 3: Commit**

```bash
git add hdb_pipeline/assets/staging.py
git commit -m "feat: add staging_geocoded_hdb_resale asset with audited geocode coverage (no silent drop)"
```

---

## Task 18: `staging_schools` and `staging_mrt_stations` assets

**Files:**
- Modify: `hdb_pipeline/assets/staging.py`

- [ ] **Step 1: Append both assets to `hdb_pipeline/assets/staging.py`**

```python
@dg.asset(group_name="staging")
def staging_schools(context: dg.AssetExecutionContext, warehouse: WarehouseResource, raw_school_locations: str) -> int:
    run_id = raw_school_locations
    engine = warehouse.get_engine()

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT raw_json FROM raw.school_locations_snapshot WHERE run_id = :run_id"),
            {"run_id": run_id},
        ).fetchall()

    if not rows:
        context.add_output_metadata({"rows_landed": 0})
        return 0

    df = pd.DataFrame([r.raw_json for r in rows])
    df = df[df["mainlevel_code"].str.contains("PRIMARY", case=False, na=False)]

    rules = [
        NullCheckRule(required_columns=["school_name", "postal_code"]),
        DuplicateRule(subset_columns=["school_name", "postal_code"]),
    ]
    runner = ValidationRunner(audit_writer=PostgresAuditWriter(engine))
    passing_df, quarantined_df = runner.run(
        df, rules, run_id=run_id, asset_name="staging_schools", source_table="staging.schools"
    )

    if not passing_df.empty:
        insert_df = passing_df[["school_name", "address"]].copy()
        insert_df["latitude"] = None
        insert_df["longitude"] = None
        insert_df.to_sql("schools", engine, schema="staging", if_exists="append", index=False)

    context.add_output_metadata({"rows_landed": len(passing_df), "rows_quarantined": len(quarantined_df)})
    return len(passing_df)


@dg.asset(group_name="staging")
def staging_mrt_stations(context: dg.AssetExecutionContext, warehouse: WarehouseResource, raw_mrt_stations: str) -> int:
    run_id = raw_mrt_stations
    engine = warehouse.get_engine()

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT raw_json FROM raw.mrt_stations_snapshot WHERE run_id = :run_id"),
            {"run_id": run_id},
        ).fetchall()

    if not rows:
        context.add_output_metadata({"rows_landed": 0})
        return 0

    records = []
    for r in rows:
        properties = r.raw_json.get("properties", {})
        geometry = r.raw_json.get("geometry", {})
        name = properties.get("Name") or properties.get("STN_NAME") or properties.get("name")
        coords = geometry.get("coordinates")
        if not name or not coords:
            continue
        centroid_lon, centroid_lat = _polygon_centroid(coords, geometry.get("type"))
        records.append({"station_name": name, "latitude": centroid_lat, "longitude": centroid_lon})

    df = pd.DataFrame(records)
    rules = [
        NullCheckRule(required_columns=["station_name", "latitude", "longitude"]),
        DuplicateRule(subset_columns=["station_name"]),
    ]
    runner = ValidationRunner(audit_writer=PostgresAuditWriter(engine))
    passing_df, quarantined_df = runner.run(
        df, rules, run_id=run_id, asset_name="staging_mrt_stations", source_table="staging.mrt_stations"
    )

    if not passing_df.empty:
        passing_df.to_sql("mrt_stations", engine, schema="staging", if_exists="append", index=False)

    context.add_output_metadata({"rows_landed": len(passing_df), "rows_quarantined": len(quarantined_df)})
    return len(passing_df)


def _polygon_centroid(coordinates, geometry_type: str) -> tuple[float, float]:
    """Returns (longitude, latitude) centroid of a Polygon or MultiPolygon ring."""
    if geometry_type == "MultiPolygon":
        ring = coordinates[0][0]
    else:
        ring = coordinates[0]
    lons = [pt[0] for pt in ring]
    lats = [pt[1] for pt in ring]
    return sum(lons) / len(lons), sum(lats) / len(lats)
```

- [ ] **Step 2: Commit**

```bash
git add hdb_pipeline/assets/staging.py
git commit -m "feat: add staging_schools and staging_mrt_stations assets"
```

---

## Task 19: `marts_hdb_proximity_features` asset

**Files:**
- Create: `hdb_pipeline/assets/marts.py`

- [ ] **Step 1: Create `hdb_pipeline/assets/marts.py`**

```python
from __future__ import annotations

import dagster as dg
import numpy as np
import pandas as pd

from hdb_pipeline.geo import haversine_km
from hdb_pipeline.resources import WarehouseResource


@dg.asset(group_name="marts")
def marts_hdb_proximity_features(
    context: dg.AssetExecutionContext,
    warehouse: WarehouseResource,
    staging_geocoded_hdb_resale: int,
    staging_schools: int,
    staging_mrt_stations: int,
) -> int:
    engine = warehouse.get_engine()
    resale_df = pd.read_sql("SELECT * FROM staging.hdb_resale WHERE latitude IS NOT NULL", engine)
    mrt_df = pd.read_sql("SELECT * FROM staging.mrt_stations", engine)
    school_df = pd.read_sql("SELECT * FROM staging.schools WHERE latitude IS NOT NULL", engine)

    if resale_df.empty or mrt_df.empty or school_df.empty:
        context.add_output_metadata({"rows_written": 0, "reason": "one or more inputs empty"})
        return 0

    mrt_lats, mrt_lons, mrt_names = mrt_df["latitude"].values, mrt_df["longitude"].values, mrt_df["station_name"].values
    school_lats = school_df["latitude"].values
    school_lons = school_df["longitude"].values
    school_names = school_df["school_name"].values

    nearest_mrt_names, nearest_mrt_dists = [], []
    nearest_school_names, nearest_school_dists = [], []
    for lat, lon in zip(resale_df["latitude"], resale_df["longitude"]):
        mrt_distances = haversine_km(lat, lon, mrt_lats, mrt_lons)
        school_distances = haversine_km(lat, lon, school_lats, school_lons)
        mrt_idx = int(np.argmin(mrt_distances))
        school_idx = int(np.argmin(school_distances))
        nearest_mrt_names.append(mrt_names[mrt_idx])
        nearest_mrt_dists.append(round(float(mrt_distances[mrt_idx]), 2))
        nearest_school_names.append(school_names[school_idx])
        nearest_school_dists.append(round(float(school_distances[school_idx]), 2))

    output_df = pd.DataFrame({
        "town": resale_df["town"],
        "flat_type": resale_df["flat_type"],
        "resale_price": resale_df["resale_price"],
        "floor_area_sqm": resale_df["floor_area_sqm"],
        "nearest_mrt_name": nearest_mrt_names,
        "nearest_mrt_distance_km": nearest_mrt_dists,
        "nearest_school_name": nearest_school_names,
        "nearest_school_distance_km": nearest_school_dists,
        "month": resale_df["month"],
    })

    output_df.to_sql("hdb_proximity_features", engine, schema="marts", if_exists="replace", index=False)

    context.add_output_metadata({"rows_written": len(output_df)})
    return len(output_df)
```

- [ ] **Step 2: Commit**

```bash
git add hdb_pipeline/assets/marts.py
git commit -m "feat: add marts_hdb_proximity_features asset"
```

---

## Task 20: `marts_hdb_extended_features` asset

**Files:**
- Modify: `hdb_pipeline/assets/marts.py`
- Create: `hdb_pipeline/reference_data_files/singapore_malls.csv` (copied from legacy)

- [ ] **Step 1: Copy the existing malls reference file**

Run: `mkdir -p hdb_pipeline/reference_data_files && cp data/bronze/singapore_malls.csv hdb_pipeline/reference_data_files/singapore_malls.csv`

This is a static reference list (mall name + lat/lon), not something data.gov.sg publishes a dataset_id for, so it's bundled as a reference file rather than ingested through `raw.*` like the other three sources.

- [ ] **Step 2: Append the extended features asset to `hdb_pipeline/assets/marts.py`**

```python
from pathlib import Path

from sklearn.neighbors import BallTree

from hdb_pipeline.reference_data import CBD_LAT, CBD_LON, ELITE_SCHOOLS, MATURE_TOWNS

MALLS_CSV_PATH = Path(__file__).resolve().parent.parent / "reference_data_files" / "singapore_malls.csv"


@dg.asset(group_name="marts")
def marts_hdb_extended_features(
    context: dg.AssetExecutionContext, warehouse: WarehouseResource, marts_hdb_proximity_features: int
) -> int:
    engine = warehouse.get_engine()
    resale_df = pd.read_sql(
        "SELECT * FROM staging.hdb_resale WHERE latitude IS NOT NULL AND longitude IS NOT NULL", engine
    )
    school_df = pd.read_sql("SELECT * FROM staging.schools WHERE latitude IS NOT NULL", engine)
    malls_df = pd.read_csv(MALLS_CSV_PATH)

    if resale_df.empty:
        context.add_output_metadata({"rows_written": 0})
        return 0

    df = resale_df.copy()
    df["dist_to_cbd_km"] = haversine_km(df["latitude"], df["longitude"], CBD_LAT, CBD_LON).round(2)

    elite_df = school_df[school_df["school_name"].str.upper().isin(ELITE_SCHOOLS)]
    if not elite_df.empty:
        elite_lats, elite_lons = elite_df["latitude"].values, elite_df["longitude"].values

        def nearest_elite_school(row):
            return haversine_km(row["latitude"], row["longitude"], elite_lats, elite_lons).min()

        df["dist_to_elite_school_km"] = df.apply(nearest_elite_school, axis=1).round(2)
        df["within_1km_elite_school"] = df["dist_to_elite_school_km"] <= 1.0
    else:
        df["dist_to_elite_school_km"] = None
        df["within_1km_elite_school"] = False

    hdb_coords_rad = np.radians(df[["latitude", "longitude"]].values)
    mall_coords_rad = np.radians(malls_df[["lat", "lon"]].values)
    tree = BallTree(mall_coords_rad, metric="haversine")
    df["malls_within_2km"] = tree.query_radius(hdb_coords_rad, r=2.0 / 6371.0, count_only=True)

    df["estate_maturity"] = np.where(df["town"].isin(MATURE_TOWNS), "Mature", "Non-Mature")

    df["floor_lower_bound"] = df["storey_range"].str[:2].astype(int)
    bins = [-1, 4, 9, 19, 100]
    labels = ["Low (0-4)", "Mid (5-9)", "High (10-19)", "Ultra-High (20+)"]
    df["floor_tier"] = pd.cut(df["floor_lower_bound"], bins=bins, labels=labels)

    transaction_year = df["month"].str[:4].astype(int)
    df["remaining_lease_years"] = 99 - (transaction_year - df["lease_commence_date"].astype(int))
    conditions = [
        df["remaining_lease_years"] < 30,
        df["remaining_lease_years"] < 60,
        df["remaining_lease_years"] >= 60,
    ]
    choices = ["High Risk (<30 yrs)", "Restricted (<60 yrs)", "Safe (60+ yrs)"]
    df["lease_critical_status"] = np.select(conditions, choices, default="Unknown")

    mrt_df = pd.read_sql("SELECT * FROM staging.mrt_stations", engine)
    mrt_lats, mrt_lons = mrt_df["latitude"].values, mrt_df["longitude"].values

    def nearest_mrt_km(row):
        return haversine_km(row["latitude"], row["longitude"], mrt_lats, mrt_lons).min()

    dist_to_mrt = df.apply(nearest_mrt_km, axis=1)
    df["mrt_walk_time_mins"] = np.ceil((dist_to_mrt * 1000) / 80)

    output_df = df[[
        "town", "flat_type", "resale_price", "floor_area_sqm", "dist_to_cbd_km",
        "dist_to_elite_school_km", "within_1km_elite_school", "malls_within_2km",
        "estate_maturity", "floor_tier", "remaining_lease_years", "lease_critical_status",
        "mrt_walk_time_mins", "month",
    ]]
    output_df.to_sql("hdb_extended_features", engine, schema="marts", if_exists="replace", index=False)

    context.add_output_metadata({"rows_written": len(output_df)})
    return len(output_df)
```

- [ ] **Step 3: Commit**

```bash
git add hdb_pipeline/assets/marts.py hdb_pipeline/reference_data_files/singapore_malls.csv
git commit -m "feat: add marts_hdb_extended_features asset (elite schools, malls, lease decay)"
```

---

## Task 21: Asset checks

**Files:**
- Create: `hdb_pipeline/assets/checks.py`

- [ ] **Step 1: Create `hdb_pipeline/assets/checks.py`**

```python
from __future__ import annotations

import dagster as dg
from sqlalchemy import text

from hdb_pipeline.resources import WarehouseResource


@dg.asset_check(asset="validated_hdb_resale")
def staging_hdb_resale_nonempty(context: dg.AssetCheckExecutionContext, warehouse: WarehouseResource) -> dg.AssetCheckResult:
    """Did staging receive any rows at all this run? An empty staging table
    after a run usually means the upstream API returned nothing or every
    row was quarantined — either way, worth a human looking."""
    engine = warehouse.get_engine()
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM staging.hdb_resale")).scalar()

    return dg.AssetCheckResult(passed=count > 0, metadata={"staging_row_count": count})


@dg.asset_check(asset="validated_hdb_resale")
def quarantine_rate_check(context: dg.AssetCheckExecutionContext, warehouse: WarehouseResource) -> dg.AssetCheckResult:
    """Flags when a single run's quarantine rate exceeds 20% — that level of
    failure is more consistent with an upstream schema change than with
    normal, day-to-day messy data."""
    engine = warehouse.get_engine()
    with engine.connect() as conn:
        latest_run = conn.execute(
            text(
                """SELECT run_id FROM audit.validation_results
                   WHERE asset_name = 'validated_hdb_resale'
                   ORDER BY checked_at DESC LIMIT 1"""
            )
        ).scalar()

        if latest_run is None:
            return dg.AssetCheckResult(passed=True, metadata={"reason": "no runs yet"})

        batch_size = conn.execute(
            text("SELECT MAX(rows_checked) FROM audit.validation_results WHERE run_id = :run_id"),
            {"run_id": latest_run},
        ).scalar() or 0

        quarantined = conn.execute(
            text(
                """SELECT COUNT(DISTINCT row_data_json->>'source_raw_id')
                   FROM audit.quarantine WHERE run_id = :run_id"""
            ),
            {"run_id": latest_run},
        ).scalar() or 0

    rate = quarantined / batch_size if batch_size else 0
    passed = rate <= 0.20

    return dg.AssetCheckResult(
        passed=passed,
        metadata={
            "run_id": str(latest_run),
            "batch_size": batch_size,
            "quarantined_rows": quarantined,
            "quarantine_rate": round(rate, 4),
        },
        description=f"Quarantine rate {rate:.1%} {'exceeds' if not passed else 'is within'} the 20% threshold.",
    )
```

- [ ] **Step 2: Commit**

```bash
git add hdb_pipeline/assets/checks.py
git commit -m "feat: add asset checks (staging nonempty, quarantine rate)"
```

---

## Task 22: Dagster Definitions

**Files:**
- Create: `hdb_pipeline/definitions.py`

- [ ] **Step 1: Create `hdb_pipeline/definitions.py`**

```python
import dagster as dg

from hdb_pipeline.assets import checks, marts, raw, staging
from hdb_pipeline.resources import OneMapResource, WarehouseResource

all_assets = dg.load_assets_from_modules([raw, staging, marts])
all_asset_checks = dg.load_asset_checks_from_modules([checks])

defs = dg.Definitions(
    assets=all_assets,
    asset_checks=all_asset_checks,
    resources={
        "warehouse": WarehouseResource(),
        "onemap": OneMapResource(),
    },
)
```

- [ ] **Step 2: Verify Dagster can load the definitions**

Run: `python -c "from hdb_pipeline.definitions import defs; print(len(defs.get_asset_graph().get_all_asset_keys()))"`
Expected: prints `9` (raw_hdb_resale, raw_school_locations, raw_mrt_stations, validated_hdb_resale, staging_geocoded_hdb_resale, staging_schools, staging_mrt_stations, marts_hdb_proximity_features, marts_hdb_extended_features)

Note: this requires `WAREHOUSE_DATABASE_URL` etc. to be at least set in the environment (values don't need to be reachable yet, just present, since `WarehouseResource`/`OneMapResource` read env vars at construction). Run with `.env` loaded, e.g. via `python -m dotenv run -- python -c "..."` or export the vars manually first.

- [ ] **Step 3: Commit**

```bash
git add hdb_pipeline/definitions.py
git commit -m "feat: wire up Dagster Definitions"
```

---

## Task 23: Repoint the Streamlit dashboard

**Files:**
- Modify: `dashboard.py` (move to `legacy/dashboard.py` first)

- [ ] **Step 1: Move existing scripts into `legacy/`**

Run:
```bash
mkdir -p legacy
git mv clean_mrt_data.py dashboard.py gold_analytics.py gold_postgres_analytics.py ingest_hdb.py ingest_schools.py onemap_utils.py silver_features.py silver_spatial_join.py legacy/
```

- [ ] **Step 2: Update `legacy/dashboard.py`'s data source to the new schema**

In `legacy/dashboard.py`, replace the `load_data` function's connection setup and the two queries to read from `marts.hdb_extended_features` (which has `within_1km_elite_school`, `estate_maturity`, `lease_critical_status`, `flat_type`) instead of the old `silver_hdb_features` table:

Find:
```python
@st.cache_data
def load_data(query):
    PG_PASSWORD = os.getenv("PG_PASSWORD", "your_password_here")
    DATABASE_URI = f"postgresql://postgres:{PG_PASSWORD}@localhost:5432/hdb_portfolio"
    engine = create_engine(DATABASE_URI)
```

Replace with:
```python
@st.cache_data
def load_data(query):
    DATABASE_URI = os.getenv("WAREHOUSE_DATABASE_URL", "postgresql://hdb:change_me@localhost:5433/hdb_warehouse")
    engine = create_engine(DATABASE_URI)
```

Find both occurrences of `FROM silver_hdb_features` and replace with `FROM marts.hdb_extended_features`.

- [ ] **Step 3: Verify the dashboard starts (requires the stack running, covered in Task 26)**

Skip execution here — this is verified together with the rest of the stack in Task 26, Step 6.

- [ ] **Step 4: Commit**

```bash
git add legacy/ dashboard.py
git commit -m "refactor: move legacy scripts to legacy/, repoint dashboard at marts.hdb_extended_features"
```

---

## Task 24: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create `README.md`**

```markdown
# HDB Data Quality & Governance Pipeline

A governed data pipeline for Singapore HDB resale transactions: live data.gov.sg + OneMap ingestion,
a hand-rolled validation rule engine, a full audit trail, and a quarantine pattern for bad data —
built to be as explainable in an interview as it is functional.

## Why quarantine instead of delete

The project this was rebuilt from had one line doing real damage:

```python
df = df.dropna(subset=['latitude', 'longitude'])
```

That line silently deleted 18 of 50,000 HDB resale records — rows where OneMap couldn't geocode the
address — with no log, no record of which addresses failed, and no way to answer "how much data did
we lose, and why?" after the fact. That's a data-integrity problem: data disappeared without anyone
having decided it should.

This pipeline replaces every silent-drop with an explicit decision, logged before it happens:

- **Every validation rule run, every batch** is written to `audit.validation_results` — pass or fail,
  not just failures. You can answer "did data quality degrade last week?" with one query against this
  table alone.
- **Rows that fail a hard rule** (schema drift, missing required fields, an invalid town name, an exact
  duplicate) are moved to `audit.quarantine` with the specific rule that failed and the full row
  attached as JSON — never deleted.
- **Rows that fail a soft rule** (a resale price statistically unusual for its town + flat type) are
  logged as a warning but still land in `staging` — an outlier is often a real, interesting data point,
  not necessarily bad data.
- **Geocoding gaps are logged, not dropped.** Rows that can't be geocoded stay in `staging.hdb_resale`
  (the transaction is still valid data) but the coverage gap is written to `audit.validation_results` as
  a warning, naming every address OneMap couldn't resolve.

This mirrors a security-monitoring mindset more than a typical ETL script: integrity checks, an audit
log that can't be bypassed by the happy path, and a "contain, don't discard" response to anomalies.

## Architecture

```
data.gov.sg (HDB resale, schools) + OneMap (geocoding) + MRT/LRT GeoJSON
        │
        ▼
raw.*_snapshot          append-only, timestamped JSONB, one row per run_id
        │
        ▼
ValidationRunner        schema drift / null / outlier / referential integrity / duplicate rules
        │
   ┌────┴────┐
   ▼         ▼
staging.*   audit.quarantine     +  audit.validation_results (every rule, every run)
   │
   ▼
marts.hdb_proximity_features, marts.hdb_extended_features
   │
   ▼
Streamlit dashboard (legacy/dashboard.py)
```

## Answering "did data quality degrade last week?"

```sql
SELECT
    date_trunc('day', checked_at) AS day,
    rule_name,
    SUM(rows_failed)::float / NULLIF(SUM(rows_checked), 0) AS fail_rate
FROM audit.validation_results
WHERE asset_name = 'validated_hdb_resale'
  AND checked_at > now() - interval '7 days'
GROUP BY 1, 2
ORDER BY 1, 2;
```

## Running it

1. Copy `.env.example` to `.env` and fill in `ONEMAP_EMAIL` / `ONEMAP_PASSWORD` (a free OneMap account)
   and Postgres passwords. `API_KEY` for data.gov.sg is optional — the endpoints work without one.
2. `docker compose up -d --build`
3. Open the Dagster UI at `http://localhost:3000`, materialize assets in order (raw → staging → marts),
   or select all and materialize — Dagster resolves the dependency order automatically.
4. `pip install -r requirements.txt && streamlit run legacy/dashboard.py` to view the dashboard
   (reads from `marts.hdb_extended_features` in the warehouse Postgres on `localhost:5433`).

## Tests

```bash
pytest tests/ -v
```

Validator unit tests run against small synthetic DataFrames — no database or network required.

## Resume framing

Built a governed data pipeline for Singapore HDB resale data, implementing a custom validation
framework (schema drift, null, outlier, referential integrity, and duplicate checks) that quarantines
failing records with a full audit trail rather than silently dropping them — orchestrated with Dagster
and containerized with Docker.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with governance/audit trail explanation"
```

---

## Task 25: End-to-end run and verification

**Files:** None created — this task runs the full stack and confirms real behavior.

- [ ] **Step 1: Run the full unit test suite**

Run: `pytest tests/ -v`
Expected: all validator/runner/geo tests PASS (18 tests).

- [ ] **Step 2: Bring up the full Docker stack**

Run: `docker compose up -d --build`
Expected: all four services running; `docker compose ps` shows `warehouse_postgres` and `dagster_postgres` healthy, `dagster_webserver` and `dagster_daemon` running.

- [ ] **Step 3: Materialize all assets via the Dagster UI or CLI**

Open `http://localhost:3000`, go to Assets, select all, click Materialize. This will take a while on
first run (~236k HDB records to ingest, thousands of unique addresses to geocode through OneMap at
~5 req/s — expect 30-60 minutes for the first full run; subsequent runs are incremental and much
faster).

Alternatively via CLI: `docker compose exec dagster_webserver dagster asset materialize --select "*" -m hdb_pipeline.definitions`

- [ ] **Step 4: Verify the audit trail is populated**

Run: `docker compose exec warehouse_postgres psql -U hdb -d hdb_warehouse -c "SELECT asset_name, rule_name, passed, rows_checked, rows_failed FROM audit.validation_results ORDER BY checked_at DESC LIMIT 20;"`
Expected: rows for every rule that ran, mix of `passed = true` and `passed = false`.

Run: `docker compose exec warehouse_postgres psql -U hdb -d hdb_warehouse -c "SELECT rule_name_failed, COUNT(*) FROM audit.quarantine GROUP BY rule_name_failed;"`
Expected: at least one row — real HDB data should trip at least the duplicate or referential integrity
rules given ~236k records.

- [ ] **Step 5: Verify the marts landed**

Run: `docker compose exec warehouse_postgres psql -U hdb -d hdb_warehouse -c "SELECT COUNT(*) FROM marts.hdb_proximity_features;"`
Expected: non-zero count roughly matching the number of successfully-geocoded staging rows.

- [ ] **Step 6: Verify the dashboard runs against the new schema**

Run: `streamlit run legacy/dashboard.py` (with `.env` loaded so `WAREHOUSE_DATABASE_URL` resolves, and
`localhost:5433` reachable since `warehouse_postgres` publishes that port)
Expected: dashboard loads in browser without connection errors, shows the elite-school-premium and
lease-decay charts populated from `marts.hdb_extended_features`.

- [ ] **Step 7: Final commit**

```bash
git add -A
git commit -m "chore: verify end-to-end pipeline run against live data"
```

(Only if verification produced file changes worth committing — e.g. if any fixes were needed during this step. If nothing changed, skip this commit.)
