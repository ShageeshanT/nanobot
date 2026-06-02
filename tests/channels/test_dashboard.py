"""Tests for the dashboard data gatherers (read-only monitoring surface)."""

from __future__ import annotations

import json

import pytest

from nanobot.channels import dashboard
from nanobot.config import loader


@pytest.fixture
def configured(tmp_path, monkeypatch):
    """Point the loader at a temp config + workspace."""
    workspace = tmp_path / "ws"
    (workspace / "memory").mkdir(parents=True)
    (workspace / "memory" / "MEMORY.md").write_text("# Memory\n\n- a fact", encoding="utf-8")
    (workspace / "HEARTBEAT.md").write_text("hb tasks", encoding="utf-8")
    config = {
        "agents": {"defaults": {"workspace": str(workspace), "model": "claude-opus-4-8", "provider": "anthropic"}},
        "providers": {"minimax": {"apiKey": "secret-mini-123"}},
        "channels": {"telegram": {"enabled": True, "botToken": "tok-abc"}, "discord": {"enabled": False}},
        "modelPresets": {"fast": {"model": "MiniMax-M2", "provider": "minimax"}},
        "tools": {
            "mcpServers": {
                "composio": {
                    "url": "https://backend.composio.dev/v3/mcp/SID?user_id=U&secret=zzz",
                    "headers": {"x-api-key": "k"},
                    "enabledTools": ["*"],
                }
            }
        },
    }
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(loader, "_current_config_path", cfg_path)
    return workspace


def test_channels_status(configured):
    out = dashboard.channels_status()
    names = {c["name"]: c for c in out["channels"]}
    assert names["telegram"]["enabled"] is True
    assert names["telegram"]["configured"] is True  # botToken present
    assert names["discord"]["enabled"] is False
    assert out["enabled_count"] == 1


def test_config_redacted_masks_secrets(configured):
    out = dashboard.config_redacted()
    blob = json.dumps(out["config"])
    assert "secret-mini-123" not in blob  # api key masked
    assert "tok-abc" not in blob  # channel token masked
    assert out["config_path"].endswith("config.json")


def test_memory_files(configured):
    files = {f["name"]: f for f in dashboard.memory_files()["files"]}
    assert files["MEMORY.md"]["exists"] is True
    assert "a fact" in files["MEMORY.md"]["content"]
    assert files["HEARTBEAT.md"]["exists"] is True
    assert files["SOUL.md"]["exists"] is False


def test_model_presets(configured):
    out = dashboard.model_presets()
    names = {p["name"] for p in out["presets"]}
    assert "fast" in names


def test_cron_jobs_empty(configured):
    assert dashboard.cron_jobs() == {"jobs": []}


def test_usage_summary_shape(configured):
    out = dashboard.usage_summary(days=7)
    assert set(out.keys()) >= {"totals", "by_model", "series", "recent", "window_days"}
    assert out["window_days"] == 7


def test_overview_shape(configured):
    out = dashboard.overview(session_manager=None, active_connections=3)
    assert out["model"] == "claude-opus-4-8"
    assert out["active_connections"] == 3
    assert out["counts"]["channels_enabled"] == 1
    assert out["counts"]["providers_configured"] >= 1  # minimax has a key
    assert "usage" in out


def test_log_buffer(configured):
    from loguru import logger

    dashboard.install_log_buffer()
    logger.info("dashboard-test-marker")
    out = dashboard.recent_logs(limit=50)
    assert any("dashboard-test-marker" in r["message"] for r in out["logs"])


def test_integrations_configured(configured):
    from nanobot.agent.tools import mcp as mcp_mod

    mcp_mod._MCP_STATUS.clear()
    out = dashboard.integrations()
    assert out["mcp_total"] == 1
    srv = out["mcp_servers"][0]
    assert srv["name"] == "composio"
    assert srv["transport"] == "streamableHttp"
    assert "user_id" not in srv["target"] and "secret" not in srv["target"]  # query dropped
    assert srv["header_count"] == 1
    assert srv["status"] == "configured"  # no live connection yet
    assert any(c["name"] == "Web tools" for c in out["capabilities"])


def test_integrations_live_overlay(configured):
    from nanobot.agent.tools import mcp as mcp_mod

    mcp_mod._MCP_STATUS.clear()
    mcp_mod._record_mcp_status(
        "composio", status="connected",
        tools=[{"name": "GMAIL_SEND", "description": "send"}], registered=1, error=None,
    )
    try:
        out = dashboard.integrations()
        srv = out["mcp_servers"][0]
        assert srv["status"] == "connected"
        assert srv["tool_count"] == 1
        assert srv["tools"][0]["name"] == "GMAIL_SEND"
        assert out["mcp_connected"] == 1
    finally:
        mcp_mod._MCP_STATUS.clear()
