"""The bronze layout: partition paths, wholesale month replacement, high-water mark."""

import glob
import os

import pandas as pd
import pytest

import ingest_hdb
from conftest import records


def test_partition_dir_builds_a_hive_path(bronze):
    assert ingest_hdb.partition_dir("2024-06").endswith("month=2024-06")


@pytest.mark.parametrize(
    "month",
    [
        "2024-6",     # unpadded: sorts BEFORE 2024-06, silently breaking the mark
        "2024-13",
        "2024-00",
        "202406",
        "2024-06-01",
        "",
        "../../etc",  # would escape the bronze root entirely
        "2024-06/x",
        None,
        202406,       # an int, not a string
    ],
)
def test_partition_dir_refuses_anything_that_is_not_a_month(month):
    with pytest.raises(ingest_hdb.IngestError):
        ingest_hdb.partition_dir(month)


def test_write_partitions_lays_out_one_directory_per_month(bronze):
    ingest_hdb.write_partitions(pd.concat([records("2024-01", [1, 2]), records("2024-02", [3])]))

    assert sorted(os.listdir(bronze)) == ["month=2024-01", "month=2024-02"]
    assert os.path.exists(bronze / "month=2024-01" / "part-0.parquet")


def test_month_is_in_the_path_and_not_in_the_file(bronze):
    """Carrying month in both places is a duplicate column the reader rejects."""
    ingest_hdb.write_partitions(records("2024-01", [1, 2]))

    body = pd.read_parquet(bronze / "month=2024-01" / "part-0.parquet")
    assert "month" not in body.columns
    assert list(body["_id"]) == [1, 2]


def test_rerunning_a_month_replaces_it_and_touches_nothing_else(bronze):
    """The whole point of partitioning: March replaces March, February is untouched."""
    ingest_hdb.write_partitions(pd.concat([records("2024-01", [1, 2, 3]), records("2024-02", [9])]))
    february = (bronze / "month=2024-02" / "part-0.parquet").read_bytes()

    ingest_hdb.write_partitions(records("2024-01", [7]))

    assert list(pd.read_parquet(bronze / "month=2024-01" / "part-0.parquet")["_id"]) == [7]
    assert (bronze / "month=2024-02" / "part-0.parquet").read_bytes() == february


def test_write_leaves_no_temp_files_behind(bronze):
    ingest_hdb.write_partitions(records("2024-01", [1]))

    assert glob.glob(f"{bronze.as_posix()}/**/.*.tmp", recursive=True) == []


def test_high_water_mark_is_none_before_the_first_run(bronze):
    assert ingest_hdb.read_high_water_mark() is None


def test_high_water_mark_is_none_when_a_full_rebuild_is_asked_for(bronze):
    ingest_hdb.write_partitions(records("2024-02", [1]))

    assert ingest_hdb.read_high_water_mark(full_rebuild=True) is None


def test_high_water_mark_is_the_newest_partition(bronze):
    ingest_hdb.write_partitions(
        pd.concat([records("2023-12", [1]), records("2024-02", [2]), records("2024-01", [3])])
    )

    assert ingest_hdb.read_high_water_mark() == "2024-02"


def test_high_water_mark_follows_the_partitions_when_one_disappears(bronze):
    """No run log to drift: delete the newest month and the mark rolls back with it.

    This is the self-healing property. A run that dies after writing 2024-01 but
    before writing 2024-02 leaves a mark of 2024-01, so the next run re-fetches from
    there. A stored mark would have been advanced already and 2024-02 would be lost.
    """
    ingest_hdb.write_partitions(pd.concat([records("2024-01", [1]), records("2024-02", [2])]))
    assert ingest_hdb.read_high_water_mark() == "2024-02"

    for f in glob.glob(f"{bronze.as_posix()}/month=2024-02/*"):
        os.remove(f)

    assert ingest_hdb.read_high_water_mark() == "2024-01"
