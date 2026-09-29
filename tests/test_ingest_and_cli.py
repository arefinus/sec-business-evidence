from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
import yaml

from conftest import FIXTURE_DIR
from sec_business_evidence.__main__ import main
from sec_business_evidence.errors import CacheError, ConfigurationError, NetworkError
from sec_business_evidence.ingest import client as client_mod
from sec_business_evidence.ingest.cache import JsonCache, sha256_of_json
from sec_business_evidence.ingest.client import EdgarClient, RateLimiter, companyfacts_url, submissions_url, user_agent_from_env

NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)


def test_cache_roundtrip_records_hash_and_retrieval_time(tmp_path):
    cache = JsonCache(tmp_path)
    payload = {"cik": 1, "facts": {}}
    entry = cache.put("k", "https://data.sec.gov/x", payload, retrieved_at=NOW)
    back = cache.get("k")
    assert back.payload == payload and back.sha256 == sha256_of_json(payload)
    assert back.retrieved_at == NOW and back.url == "https://data.sec.gov/x"


def test_tampered_cache_entry_is_detected(tmp_path):
    cache = JsonCache(tmp_path)
    cache.put("k", "u", {"a": 1}, retrieved_at=NOW)
    p = cache.path_for("k")
    env = json.loads(p.read_text(encoding="utf-8"))
    env["payload"]["a"] = 2
    p.write_text(json.dumps(env), encoding="utf-8")
    with pytest.raises(CacheError):
        cache.get("k")


def test_stale_cache_is_detected_by_age(tmp_path):
    cache = JsonCache(tmp_path)
    cache.put("k", "u", {"a": 1}, retrieved_at=NOW - timedelta(days=40))
    with pytest.raises(CacheError):
        cache.get_fresh("k", timedelta(days=30), now=NOW)
    assert cache.get_fresh("k", timedelta(days=60), now=NOW).payload == {"a": 1}


def test_missing_cache_entry_names_the_fix(tmp_path):
    with pytest.raises(CacheError, match="fetch"):
        JsonCache(tmp_path).get("nothing")


def test_user_agent_env_is_required_and_must_be_descriptive():
    with pytest.raises(ConfigurationError, match="SEC_USER_AGENT"):
        user_agent_from_env({})
    with pytest.raises(ConfigurationError):
        user_agent_from_env({"SEC_USER_AGENT": "bot"})
    assert user_agent_from_env({"SEC_USER_AGENT": "Demo Analyst analyst@example.invalid"}).startswith("Demo")


def test_fetch_without_user_agent_exits_2_and_prints_terms(monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)

    def blocked(url, headers):  # any network attempt is a test failure
        raise AssertionError("network call attempted")

    monkeypatch.setattr(client_mod, "http_get_json", blocked)
    code = main(["fetch", "--cik", "320193", "--cache-dir", str(tmp_path)])
    out, err = capsys.readouterr()
    assert code == 2
    assert "https://www.sec.gov/os/accessing-edgar-data" in out
    assert "SEC_USER_AGENT" in err
    assert not list(tmp_path.glob("*.json"))


def test_blocked_network_raises_network_error_and_caches_nothing(tmp_path):
    def blocked(url, headers):
        raise NetworkError("offline")

    client = EdgarClient("Demo Analyst analyst@example.invalid", JsonCache(tmp_path), getter=blocked,
                         limiter=RateLimiter(sleeper=lambda s: None))
    with pytest.raises(NetworkError):
        client.fetch_companyfacts("320193")
    assert not list(tmp_path.glob("*.json"))


def test_successful_fetch_uses_user_agent_and_caches(tmp_path):
    seen = {}

    def fake(url, headers):
        seen["url"] = url
        seen["headers"] = headers
        return {"cik": 320193, "facts": {}}

    client = EdgarClient("Demo Analyst analyst@example.invalid", JsonCache(tmp_path), getter=fake,
                         limiter=RateLimiter(sleeper=lambda s: None))
    entry = client.fetch_companyfacts(320193)
    assert seen["url"] == companyfacts_url(320193) == "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    assert seen["headers"]["User-Agent"] == "Demo Analyst analyst@example.invalid"
    assert entry.payload["cik"] == 320193 and JsonCache(tmp_path).has("CIK0000320193_companyfacts")
    assert submissions_url(320193) == "https://data.sec.gov/submissions/CIK0000320193.json"


def test_rate_limiter_sleeps_when_calls_are_too_close():
    clock = {"t": 100.0}
    slept = []
    limiter = RateLimiter(max_per_second=10, clock=lambda: clock["t"], sleeper=slept.append)
    limiter.wait()
    clock["t"] += 0.02
    limiter.wait()
    assert slept and slept[0] == pytest.approx(0.08, abs=1e-9)
    clock["t"] += 1.0
    assert limiter.wait() == 0.0


def test_smoke_writes_validated_output_and_manifest(tmp_path, capsys):
    assert main(["smoke", "--out", str(tmp_path)]) == 0
    manifest = yaml.safe_load((tmp_path / "run_manifest.yaml").read_text(encoding="utf-8"))
    for key in ("schema_version", "project_id", "run_id", "status", "mode", "evidence_status", "git_commit",
                "data", "configuration_hash", "seed", "environment", "started_at", "finished_at"):
        assert key in manifest
    assert manifest["status"] == "completed" and manifest["mode"] == "smoke" and manifest["git_commit"] is None
    assert manifest["evidence_status"] == "demo" and manifest["seed"] == 42
    assert (tmp_path / "evidence.json").exists() and (tmp_path / "flow.json").exists()
    assert "smoke ok" in capsys.readouterr().out


def test_demo_writes_three_issuers_and_portfolio_flow(tmp_path):
    assert main(["demo", "--out", str(tmp_path)]) == 0
    dirs = sorted(p.name for p in tmp_path.iterdir() if p.is_dir())
    assert dirs == ["bluewater-demo-holdings", "granite-demo-industries", "northwind-demo-corp"]
    flow = json.loads((tmp_path / "demo_flow.json").read_text(encoding="utf-8"))
    assert flow["mode"] == "synthetic-demo" and [n["id"] for n in flow["nodes"]] == ["revenue", "receivables", "cash", "liabilities"]


def test_analyze_cli_respects_as_of_and_flags_cli_reads_output(tmp_path, capsys):
    src = FIXTURE_DIR / "CIK9999999003_companyfacts.json"
    assert main(["analyze", "--companyfacts", str(src), "--as-of", "2024-06-30", "--out", str(tmp_path), "--mode", "synthetic-demo"]) == 0
    evidence = json.loads((tmp_path / "evidence.json").read_text(encoding="utf-8"))
    assert [fy["fy"] for fy in evidence["fiscal_years"]] == [2021, 2022, 2023]
    capsys.readouterr()
    assert main(["flags", "--evidence", str(tmp_path / "evidence.json")]) == 0
    out = capsys.readouterr().out
    assert "review flags" in out and "fraud" not in out.lower()


def test_missing_inputs_exit_2_with_message(tmp_path, capsys):
    assert main(["analyze", "--companyfacts", str(tmp_path / "nope.json"), "--as-of", "2024-01-01", "--out", str(tmp_path)]) == 2
    assert "not found" in capsys.readouterr().err
    assert main(["flags", "--evidence", str(tmp_path / "nope.json")]) == 2
    assert main(["figures", "--output", str(tmp_path / "empty"), "--figures", str(tmp_path / "figs")]) == 2


def test_figures_render_from_demo_output(tmp_path):
    assert main(["demo", "--out", str(tmp_path / "out")]) == 0
    assert main(["figures", "--output", str(tmp_path / "out"), "--figures", str(tmp_path / "figs")]) == 0
    svgs = sorted(p.name for p in (tmp_path / "figs").glob("*.svg"))
    assert svgs == ["dso_by_year.svg", "ocf_to_net_income.svg", "pipeline.svg", "revenue_by_year.svg"]
    assert (tmp_path / "figs" / "revenue_by_year.svg").read_text(encoding="utf-8").startswith("<svg")
