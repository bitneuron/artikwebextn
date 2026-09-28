"""artikBroker side of the Stock Analysis Agent: template, config, results, digest, purge.

Every test runs against a throwaway users DB + data dir, never the real config.
"""
from __future__ import annotations

import json

import pytest

import agent_runner
import agents_store
import app
import stock_recs

SA = agents_store.ANALYSIS_TEMPLATE


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(agents_store, "_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(agents_store, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(agents_store, "CONFIG_PATH", tmp_path / "config" / "agent_schedules.json")
    monkeypatch.setattr(agents_store, "ANALYSIS_DATA_DIR", tmp_path / "sa")
    monkeypatch.setattr(agents_store, "DATA_DIR", tmp_path / "news")
    yield


def _rows():
    return [
        {"ticker": "AAA", "verdict": "BUY", "score": 82, "origin": "discovered", "change": "new",
         "agreement": "agrees", "street": {"street_verdict": "BUY"}},
        {"ticker": "BBB", "verdict": "HOLD", "score": 60, "origin": "watchlist", "change": "BUY→HOLD",
         "agreement": "disagrees", "street": {"street_verdict": "BUY"}},
        {"ticker": "CCC", "verdict": "SELL", "score": 31, "origin": "watchlist", "change": "unchanged",
         "agreement": "no_coverage", "street": {}},
        {"ticker": "ZZZ", "verdict": "NO_SCORE", "score": None, "origin": "watchlist", "change": "new"},
    ]


def _write_latest(aid, run_id="sa-1"):
    d = stock_recs.data_dir(aid)
    d.mkdir(parents=True, exist_ok=True)
    (d / "latest_recommendations.json").write_text(json.dumps(
        {"run_id": run_id, "completed_at": "2026-09-20T13:00:00Z", "rows": _rows()}))


def test_template_is_registered_with_engine_bands():
    cfg = agents_store.get_config(SA)
    assert cfg["agent_type"] == "Equity Analysis" and cfg["template"] == SA
    assert (cfg["buy_min_score"], cfg["sell_below_score"]) == (75, 50)
    # same bands as the Broker's own BUY/HOLD/SELL
    assert app._status(75) == "BUY" and app._status(74.9) == "HOLD" and app._status(49.9) == "SELL"
    assert cfg["enabled"] is False and cfg["schedule_type"] == "daily_time"


def test_analysis_sources_are_its_own_catalog():
    cfg = agents_store.get_config(SA)
    assert set(cfg["sources"]) == {s["id"] for s in agents_store.ANALYSIS_SOURCE_CATALOG}
    assert agents_store.enabled_discovery_sources(cfg) == ["yahoo_screeners", "google_news"]
    news = agents_store.get_config(agents_store.BASE_TEMPLATE)
    assert "yahoo_screeners" not in news["sources"]


def test_create_instance_of_analysis_template():
    cfg = agents_store.create_instance(template=SA)
    assert cfg["agent_id"].startswith(SA + "__") and cfg["template"] == SA
    assert cfg["agent_name"] == "New Stock Analysis" and cfg["tickers"] == []
    clone = agents_store.create_instance(clone_from=cfg["agent_id"])
    assert clone["template"] == SA


def test_analysis_settings_persist_and_are_type_checked():
    patch = app._clean_analysis_patch({"max_candidates": "999", "buy_min_score": "70",
                                       "sell_below_score": 80, "include_etfs": 1,
                                       "sectors_exclude": "Energy, Utilities"})
    assert patch["max_candidates"] == 60
    assert patch["sell_below_score"] == 70          # clamped to the BUY band
    assert patch["sectors_exclude"] == ["Energy", "Utilities"]
    saved = agents_store.save_config(SA, patch)
    assert saved["max_candidates"] == 60 and saved["include_etfs"] is True


def test_watchlist_does_not_protect_news_articles():
    agents_store.save_config(SA, {"tickers": ["ONLYSA"]})
    assert "ONLYSA" not in agents_store.tracked_tickers()


def test_runner_config_payload_and_adhoc_disables_discovery():
    cfg = agents_store.save_config(SA, {"tickers": ["NVDA"], "max_candidates": 10})
    p = agent_runner._build_analysis_config(cfg, None)
    payload = json.loads(p.read_text())
    assert payload["tickers"] == ["NVDA"] and payload["max_candidates"] == 10
    assert payload["discovery_sources"] == ["yahoo_screeners", "google_news"]
    assert "discovery_enabled" not in payload or payload["discovery_enabled"] is True
    adhoc = json.loads(agent_runner._build_analysis_config(cfg, ["MSFT"]).read_text())
    assert adhoc["tickers"] == ["MSFT"] and adhoc["discovery_enabled"] is False


def test_results_group_by_engine_verdict():
    _write_latest(SA)
    res = stock_recs.results(SA)
    assert res["available"]
    assert [r["ticker"] for r in res["groups"]["BUY"]] == ["AAA"]
    assert [r["ticker"] for r in res["groups"]["NO_SCORE"]] == ["ZZZ"]
    assert res["changes"] == [{"ticker": "BBB", "change": "BUY→HOLD", "score": 60}]
    assert res["new_names"] == ["AAA"]


def test_latest_survives_losing_the_data_dir():
    _write_latest(SA, "sa-9")
    stock_recs.record_run(SA, {"run_id": "sa-9", "status": "completed", "buy": 1, "hold": 1, "sell": 1})
    import shutil
    shutil.rmtree(stock_recs.data_dir(SA))                 # redeploy wipes the ephemeral disk
    assert stock_recs.latest(SA)["run_id"] == "sa-9"
    assert stock_recs.latest_broker_run(SA)["buy"] == 1


def test_agent_view_shows_picks():
    _write_latest(SA)
    stock_recs.record_run(SA, {"run_id": "sa-1", "status": "completed", "buy": 1, "hold": 1,
                               "sell": 1, "no_score": 1, "analyzed": 4, "completed_at": "2026-09-20T13:00:00Z"})
    v = app._agent_view(SA)
    assert v["picks"]["buy"] == 1 and v["settings"]["buy_min_score"] == 75
    assert "1 BUY · 1 HOLD · 1 SELL" in v["last_result"]


def test_digest_lists_verdicts_and_flags_disagreement():
    _write_latest(SA)
    text = stock_recs.build_digest("Daily", stock_recs.results(SA))
    assert "*BUY* (1)" in text and "*SELL* (1)" in text
    assert "street says BUY" in text and "No engine score: ZZZ" in text
    assert "Not financial advice" in text


def test_brief_prompt_tells_model_verdicts_are_final():
    _write_latest(SA)
    prompt = stock_recs.brief_prompt(stock_recs.results(SA))
    assert "AAA BUY score 82" in prompt
    assert "never change" in stock_recs.BRIEF_SYSTEM


def test_purge_removes_data_and_history():
    _write_latest(SA)
    stock_recs.record_run(SA, {"run_id": "sa-1", "status": "completed"})
    out = stock_recs.purge(SA)
    assert out == {"data_dir_deleted": True, "history_deleted": True}
    assert stock_recs.latest(SA) is None and stock_recs.history(SA) == []
