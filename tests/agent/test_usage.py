"""Tests for the dashboard token-usage store."""

from __future__ import annotations

from nanobot.agent.usage import UsageStore, estimate_cost


def test_record_and_summary(tmp_path):
    store = UsageStore(tmp_path)
    store.record("claude-opus-4-8", {"prompt_tokens": 1000, "completion_tokens": 500}, "websocket:a")
    store.record("MiniMax-M2", {"prompt_tokens": 2000, "completion_tokens": 100}, "websocket:a")
    s = store.summary(days=30)
    assert s["totals"]["input_tokens"] == 3000
    assert s["totals"]["output_tokens"] == 600
    assert s["totals"]["total_tokens"] == 3600
    assert s["totals"]["turns"] == 2
    models = {m["model"]: m for m in s["by_model"]}
    assert models["claude-opus-4-8"]["total_tokens"] == 1500
    assert models["MiniMax-M2"]["total_tokens"] == 2100
    # by_model is sorted by total_tokens desc
    assert s["by_model"][0]["model"] == "MiniMax-M2"
    assert len(s["series"]) == 1  # both same UTC day
    assert len(s["recent"]) == 2


def test_empty_store_returns_zeros(tmp_path):
    s = UsageStore(tmp_path).summary()
    assert s["totals"]["total_tokens"] == 0
    assert s["by_model"] == []
    assert s["series"] == []
    assert s["recent"] == []


def test_record_ignores_empty_usage(tmp_path):
    store = UsageStore(tmp_path)
    store.record("m", None, "k")
    store.record("m", {}, "k")
    store.record("m", {"prompt_tokens": 0, "completion_tokens": 0}, "k")
    assert store.summary()["totals"]["turns"] == 0
    assert not store.path.exists()


def test_estimate_cost_known_and_unknown():
    assert estimate_cost("claude-opus-4-8", 1_000_000, 0) == 15.0
    assert estimate_cost("claude-sonnet-4-6", 0, 1_000_000) == 15.0
    assert estimate_cost("some-unknown-model", 1_000_000, 1_000_000) == 0.0


def test_price_override(monkeypatch):
    monkeypatch.setenv("NANOBOT_MODEL_PRICES", '{"frobnicate": [1.0, 2.0]}')
    assert estimate_cost("frobnicate-v9", 1_000_000, 1_000_000) == 3.0
