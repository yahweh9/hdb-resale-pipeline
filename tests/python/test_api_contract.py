"""What the ingest does when data.gov.sg answers with something other than data.

The three bugs this file pins down, all of which were previously silent or slow:
  * HTTP 200 with success=false was read as data and blew up as KeyError: result
  * a 404 was retried five times with exponential backoff before being reported
  * 429 and 5xx must still be retried, so the fail-fast must not over-reach
"""

import pytest
import requests

import ingest_hdb


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}", response=self)


@pytest.fixture
def api(monkeypatch):
    """Queue up responses; returns a list that records every call made."""
    calls = []

    def install(*responses):
        queue = list(responses)

        def fake_get(url, params=None, headers=None, timeout=None):
            calls.append(params)
            return queue.pop(0) if len(queue) > 1 else queue[0]

        monkeypatch.setattr(ingest_hdb.requests, "get", fake_get)
        return calls

    return install


def ok(records, total=1):
    return FakeResponse(payload={"success": True, "result": {"records": records, "total": total}})


def test_a_good_page_comes_back_as_the_result_block(api):
    api(ok([{"_id": 1, "month": "2024-01"}], total=1))

    assert ingest_hdb.request_chunk(0)["records"] == [{"_id": 1, "month": "2024-01"}]


def test_success_false_is_an_error_not_a_payload(api):
    """data.gov.sg answers a bad resource_id with HTTP 200 and success=false."""
    calls = api(FakeResponse(payload={"success": False, "error": {"message": "Not found"}}))

    with pytest.raises(ingest_hdb.IngestError, match="success=false"):
        ingest_hdb.request_chunk(0)

    assert len(calls) == 1, "a refusal is not transient and must not be retried"


def test_a_missing_success_key_is_also_refused(api):
    api(FakeResponse(payload={"result": {"records": []}}))

    with pytest.raises(ingest_hdb.IngestError):
        ingest_hdb.request_chunk(0)


@pytest.mark.parametrize("status", [400, 403, 404, 410, 422])
def test_client_errors_fail_on_the_first_attempt(api, status):
    calls = api(FakeResponse(status_code=status, text="gone"))

    with pytest.raises(ingest_hdb.IngestError, match="not retryable"):
        ingest_hdb.request_chunk(0)

    assert len(calls) == 1, f"HTTP {status} will be just as wrong on the retry"


def test_rate_limiting_is_retried_and_recovers(api):
    calls = api(FakeResponse(status_code=429), ok([{"_id": 1}]))

    assert ingest_hdb.request_chunk(0)["records"] == [{"_id": 1}]
    assert len(calls) == 2


def test_rate_limiting_gives_up_eventually(api):
    calls = api(FakeResponse(status_code=429))

    with pytest.raises(ingest_hdb.IngestError, match="rate-limited"):
        ingest_hdb.request_chunk(0)

    assert len(calls) == ingest_hdb.MAX_RETRIES


def test_server_errors_are_still_retried(api):
    """The fail-fast covers 4xx only. A 500 is transient and must keep its retries."""
    calls = api(FakeResponse(status_code=503))

    with pytest.raises(ingest_hdb.IngestError, match="failed after"):
        ingest_hdb.request_chunk(0)

    assert len(calls) == ingest_hdb.MAX_RETRIES


def test_a_dropped_connection_is_retried_then_recovers(monkeypatch):
    attempts = []

    def flaky_get(url, params=None, headers=None, timeout=None):
        attempts.append(1)
        if len(attempts) == 1:
            raise requests.exceptions.ConnectionError("reset by peer")
        return ok([{"_id": 1}])

    monkeypatch.setattr(ingest_hdb.requests, "get", flaky_get)

    assert ingest_hdb.request_chunk(0)["records"] == [{"_id": 1}]
    assert len(attempts) == 2
