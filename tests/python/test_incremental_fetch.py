"""Paging: where an incremental run stops, and what it is allowed to keep.

fetch_records makes a promise that write_partitions depends on -- every month at or
after the high-water mark comes back COMPLETE. If it did not, replacing a month
wholesale would delete rows that were never re-fetched.
"""

import pytest

import ingest_hdb


@pytest.fixture
def pages(monkeypatch):
    """Serve canned pages in place of the HTTP layer.

    CHUNK_SIZE is shrunk to the size of a page. Left at its real 5,000 the loop
    would break on `offset >= api_total` after the first page of any fixture small
    enough to read, and no test could reach a second page.
    """

    def install(*chunks, total=None):
        served = []
        page_size = max(len(c) for c in chunks)
        monkeypatch.setattr(ingest_hdb, "CHUNK_SIZE", page_size)
        api_total = sum(len(c) for c in chunks) if total is None else total

        def fake_request_chunk(offset):
            served.append(offset)
            index = offset // page_size
            page = chunks[index] if index < len(chunks) else []
            return {"records": list(page), "total": api_total}

        monkeypatch.setattr(ingest_hdb, "request_chunk", fake_request_chunk)
        return served

    return install


def rows(month, count):
    return [{"_id": f"{month}-{i}", "month": month} for i in range(count)]


def test_a_full_load_keeps_every_page(pages):
    served = pages(rows("2024-03", 2), rows("2024-02", 2), rows("2024-01", 1))

    records, total = ingest_hdb.fetch_records(latest_month=None)

    assert len(records) == 5
    assert total == 5
    assert served == [0, 2, 4]


def test_an_incremental_run_stops_once_it_crosses_the_mark(pages):
    served = pages(rows("2024-03", 2), rows("2024-02", 2), rows("2024-01", 2))

    records, _ = ingest_hdb.fetch_records(latest_month="2024-02")

    assert {r["month"] for r in records} == {"2024-03", "2024-02"}
    # Three pages are read, not four: the run stops on the first page that contains
    # a row older than the mark, and never asks for the rest of the history.
    assert served == [0, 2, 4]


def test_the_mark_month_comes_back_whole(pages):
    """The overlap month is re-fetched entirely, not topped up.

    A page that straddles the boundary keeps its 2024-02 rows and discards its
    2024-01 ones, which is what lets the 2024-02 partition be overwritten rather
    than merged into.
    """
    straddling_page = rows("2024-02", 3) + rows("2024-01", 4)
    pages(rows("2024-03", 1), straddling_page)

    records, _ = ingest_hdb.fetch_records(latest_month="2024-02")

    assert len([r for r in records if r["month"] == "2024-02"]) == 3
    assert not [r for r in records if r["month"] == "2024-01"]


def test_an_up_to_date_run_returns_nothing_rather_than_failing(pages):
    pages(rows("2024-01", 3))

    records, _ = ingest_hdb.fetch_records(latest_month="2024-09")

    assert records == []


def test_paging_stops_at_the_reported_total(pages):
    """Do not keep asking for pages the API has already said do not exist."""
    served = pages(rows("2024-03", 2), total=1)

    ingest_hdb.fetch_records(latest_month=None)

    assert served == [0]
