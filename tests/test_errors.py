"""T-api (Prep_02): error normalizer, retry policy, cache and fixture modes.
All inputs are SYNTHETIC; no network is used (httpx.MockTransport)."""
from __future__ import annotations

import asyncio
import json
import logging

import httpx
import pytest

from proofroom import crustdata as cd
from proofroom.errors import ConfigError, CrustError
from proofroom.log import RedactingFilter, redact


@pytest.fixture(autouse=True)
def fake_key(monkeypatch):
    monkeypatch.setenv("CRUSTDATA_API_KEY", "cd_SYNTHETICtestkey0000000000")


def run(coro):
    return asyncio.run(coro)


def client(handler, tmp_path, mode=cd.LIVE, **kw):
    sleeps: list[float] = []

    async def fake_sleep(s):
        sleeps.append(s)

    c = cd.Crustdata(mode, transport=httpx.MockTransport(handler), cache_dir=tmp_path / "cache",
                     fixtures_dir=tmp_path / "fixtures", sleep=fake_sleep, limiters=False, **kw)
    c.sleeps = sleeps  # type: ignore[attr-defined]
    return c


# ---- normalizer: the three documented shapes plus non-JSON (§6.3) -----------

def test_api1_nested_error_object():
    body = json.dumps({"error": {"type": "invalid_request", "message": "domains and names",
                                 "metadata": {}}})
    assert cd.normalize_error(400, body).as_dict() == {
        "status": 400, "type": "invalid_request", "message": "domains and names",
        "denied_fields": []}


def test_api2_string_error_with_description():
    e = cd.normalize_error(404, '{"error": "not_found", "description": "No data found"}')
    assert (e.type, e.message) == ("not_found", "No data found")


def test_api3_string_error_with_reason_and_denied_fields():
    e = cd.normalize_error(403, json.dumps({"error": "permission_error",
                                            "reason": "Access denied to fields: news",
                                            "denied_fields": ["news"]}))
    assert (e.type, e.message, e.denied_fields) == (
        "permission_error", "Access denied to fields: news", ["news"])


def test_api4_flat_message_is_unauthorized():
    e = cd.normalize_error(401, '{"message": "Unauthorized"}')
    assert (e.type, e.message, e.fatal) == ("unauthorized", "Unauthorized", True)


def test_api5_non_json_body():
    body = "<html>Bad gateway</html>" + "x" * 500
    e = cd.normalize_error(502, body)
    assert e.type == "http_502" and e.message == body[:200]


@pytest.mark.parametrize("body", ["", "null", "[1, 2]", '"text"', b"\xff\xfe", '{"foo": 1}'])
def test_normalizer_never_raises_on_odd_bodies(body):
    e = cd.normalize_error(500, body)
    assert e.status == 500 and e.type == "http_500"


def test_denied_fields_from_nested_metadata():
    body = json.dumps({"error": {"type": "permission_error", "message": "x",
                                 "metadata": {"denied_fields": ["news"]}}})
    assert cd.normalize_error(403, body).denied_fields == ["news"]


# ---- live request behavior -----------------------------------------------

def test_success_records_credits_and_sends_required_headers(tmp_path):
    seen = {}

    def handler(req: httpx.Request):
        seen.update(req.headers)
        return httpx.Response(200, json=[{"matches": []}], headers={"x-credits-used": "0.39"})

    c = client(handler, tmp_path)
    assert run(c.identify_domain("https://www.Example-Startup.test/about")) == [{"matches": []}]
    a = c.attempts[-1]
    assert (a.mode, a.status, a.credits_used) == ("LIVE", 200, "0.39")
    assert seen["x-api-version"] == "2025-11-01"
    assert seen["authorization"].startswith("Bearer ")
    assert seen["content-type"] == "application/json"


def test_api6_429_waits_reset_then_succeeds(tmp_path):
    calls = []

    def handler(req):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(429, json={"error": "rate_limited"},
                                  headers={"x-ratelimit-reset": "2"})
        return httpx.Response(200, json={"ok": True}, headers={"x-credits-used": "1"})

    c = client(handler, tmp_path)
    assert run(c.web_search("example")) == {"ok": True}
    assert len(calls) == 3 and len(c.sleeps) == 2 and all(2 <= s <= 3.1 for s in c.sleeps)
    assert [a.credits_used for a in c.attempts] == ["unknown", "unknown", "1"]
    assert cd.sum_credits(c.attempts) == (1.0, 2)


def test_api6_429_gives_up_after_three_tries(tmp_path):
    c = client(lambda r: httpx.Response(429, json={"error": "rate_limited"}), tmp_path)
    with pytest.raises(CrustError) as ei:
        run(c.web_search("example"))
    assert ei.value.status == 429 and len(c.attempts) == cd.MAX_429_TRIES


def test_api5_5xx_retried_once(tmp_path):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(502, text="<html>Bad gateway</html>")

    c = client(handler, tmp_path)
    with pytest.raises(CrustError) as ei:
        run(c.company_enrich(1))
    assert ei.value.type == "http_502" and len(calls) == 2


def test_5xx_not_retried_when_deadline_is_close(tmp_path):
    import time
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503, text="busy")

    c = client(handler, tmp_path, deadline=time.monotonic() + 5)
    with pytest.raises(CrustError):
        run(c.company_enrich(1))
    assert len(calls) == 1


@pytest.mark.parametrize("status", [400, 401, 402, 403])
def test_client_errors_are_not_retried(tmp_path, status):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(status, json={"error": {"type": "t", "message": "m"}})

    c = client(handler, tmp_path)
    with pytest.raises(CrustError) as ei:
        run(c.company_enrich(1))
    assert ei.value.status == status and len(calls) == 1
    assert c.attempts[-1].error["status"] == status


def test_network_error_retried_once_then_normalized(tmp_path):
    calls = []

    def handler(req):
        calls.append(1)
        raise httpx.ConnectError("boom", request=req)

    c = client(handler, tmp_path)
    with pytest.raises(CrustError) as ei:
        run(c.company_enrich(1))
    assert ei.value.type == "network" and len(calls) == 2 and len(c.attempts) == 2


def test_invalid_json_on_200_is_a_failed_attempt(tmp_path):
    c = client(lambda r: httpx.Response(200, text="not json"), tmp_path)
    with pytest.raises(CrustError) as ei:
        run(c.company_enrich(1))
    assert ei.value.type == "invalid_json" and c.attempts[-1].error


def test_deadline_passed_means_no_call(tmp_path):
    import time
    c = client(lambda r: pytest.fail("must not call"), tmp_path, deadline=time.monotonic())
    with pytest.raises(CrustError) as ei:
        run(c.company_enrich(1))
    assert ei.value.type == "deadline"


# ---- cache and fixture modes ----------------------------------------------

def test_cached_mode_serves_hit_and_labels_it(tmp_path):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(200, json={"v": 1}, headers={"x-credits-used": "2"})

    run(client(handler, tmp_path, mode=cd.CACHED).company_enrich(7))
    c2 = client(handler, tmp_path, mode=cd.CACHED)
    assert run(c2.company_enrich(7)) == {"v": 1}
    assert len(calls) == 1 and c2.attempts[-1].mode == "CACHED"
    assert cd.sum_credits(c2.attempts) == (0.0, 0)


def test_corrupt_cache_file_is_a_miss(tmp_path, caplog):
    def handler(req):
        return httpx.Response(200, json={"v": 2})

    c = client(handler, tmp_path, mode=cd.CACHED)
    key = cd.cache_key("/company/enrich", {"crustdata_company_ids": [7],
                                           "fields": ["basic_info", "funding", "people", "news"]})
    path = tmp_path / "cache" / f"company_enrich-{key}.json"
    path.parent.mkdir(parents=True)
    path.write_text("{truncated")
    with caplog.at_level(logging.WARNING, logger="proofroom"):
        assert run(c.company_enrich(7)) == {"v": 2}
    assert c.attempts[-1].mode == "LIVE" and "unreadable" in caplog.text
    assert json.loads(path.read_text())["body"] == {"v": 2}  # repaired


def test_fixture_mode_needs_no_key_and_replays(tmp_path, monkeypatch):
    monkeypatch.delenv("CRUSTDATA_API_KEY")
    body = {"crustdata_company_ids": [7], "fields": ["basic_info", "funding", "people", "news"]}
    fx = tmp_path / "fixtures" / "demo" / "crustdata"
    fx.mkdir(parents=True)
    (fx / f"company_enrich-{cd.cache_key('/company/enrich', body)}.json").write_text(
        json.dumps({"status": 200, "credits_used": "2", "body": {"v": 3}}))
    c = cd.Crustdata(cd.FIXTURE, fixture="demo", fixtures_dir=tmp_path / "fixtures")
    assert run(c.company_enrich(7)) == {"v": 3} and c.attempts[-1].mode == "FIXTURE"
    with pytest.raises(CrustError) as ei:
        run(c.company_enrich(8))
    assert ei.value.type == "fixture_missing"


def test_live_without_key_is_config_error(monkeypatch):
    monkeypatch.delenv("CRUSTDATA_API_KEY")
    with pytest.raises(ConfigError):
        cd.Crustdata(cd.LIVE)


def test_bad_mode_and_bad_domain_rejected(tmp_path):
    with pytest.raises(ValueError):
        cd.Crustdata("REAL")
    with pytest.raises(ValueError):
        run(client(lambda r: httpx.Response(200, json={}), tmp_path).identify_domain("nodot"))


def test_cache_key_is_order_independent():
    assert cd.cache_key("/x", {"a": 1, "b": 2}) == cd.cache_key("/x", {"b": 2, "a": 1})
    assert cd.cache_key("/x", {"a": 1}) != cd.cache_key("/y", {"a": 1})


# ---- api-8: fetch results matched by URL ------------------------------------

def test_api8_fetch_matched_by_url_failed_listed():
    req = ["https://a.test/1", "https://b.test/2", "https://c.test/3"]
    res = [{"success": True, "url": "https://www.c.test/3/", "content": "C"},
           {"success": False, "url": None, "content": None},
           {"success": True, "url": "https://a.test/1", "content": "A"}]
    ok, failed = cd.match_fetch_results(req, res)
    assert ok["https://a.test/1"]["content"] == "A"
    assert ok["https://c.test/3"]["content"] == "C"
    assert failed == ["https://b.test/2"]
    assert cd.match_fetch_results(req, None) == ({}, req)


# ---- limiter and redaction --------------------------------------------------

def test_rate_limiter_rolling_window():
    now = [0.0]
    lim = cd.RateLimiter(2, clock=lambda: now[0])
    run(lim.acquire())
    run(lim.acquire())
    assert lim.wait_needed() > 59
    now[0] = 60.0
    assert lim.wait_needed() == 0.0


def test_secrets_redacted_from_logs(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-SYNTHETIC123456")
    assert "SYNTHETIC" not in redact("key sk-ant-SYNTHETIC123456 and Bearer abcdefghijklmnop")
    rec = logging.LogRecord("proofroom", logging.INFO, "", 0, "auth %s",
                            ("cd_SYNTHETICtestkey0000000000",), None)
    RedactingFilter().filter(rec)
    assert "SYNTHETIC" not in rec.getMessage()
