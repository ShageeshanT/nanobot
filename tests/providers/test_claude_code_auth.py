"""Tests for Claude Code (`claude login`) OAuth credential read + refresh."""

from __future__ import annotations

import json
import time

from nanobot.providers import claude_code_auth as cca
from nanobot.providers.claude_code_auth import ClaudeCodeCredentials

_ACCESS = "sk-ant-oat01-ACCESS"
_REFRESH = "sk-ant-ort01-REFRESH"
_FAR_FUTURE_MS = 4_102_444_800_000  # year 2100


def _write(path, access=_ACCESS, refresh=_REFRESH, expires_ms=_FAR_FUTURE_MS, extra=None):
    oauth = {"accessToken": access, "expiresAt": expires_ms}
    if refresh is not None:
        oauth["refreshToken"] = refresh
    if extra:
        oauth.update(extra)
    path.write_text(json.dumps({"claudeAiOauth": oauth}), encoding="utf-8")


class _FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, resp, captured):
        self._resp = resp
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        self._captured.update(url=url, json=json, headers=headers)
        if isinstance(self._resp, Exception):
            raise self._resp
        return self._resp


def _patch_http(monkeypatch, resp):
    captured: dict = {}
    monkeypatch.setattr(cca.httpx, "AsyncClient", lambda *a, **k: _FakeClient(resp, captured))
    return captured


# --- path resolution --------------------------------------------------------

def test_explicit_path_is_authoritative(monkeypatch, tmp_path):
    real = tmp_path / "real.json"
    _write(real)
    monkeypatch.setenv("NANOBOT_CLAUDE_CREDENTIALS_PATH", str(real))
    assert cca.resolve_credentials_path() == real


def test_explicit_path_no_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("NANOBOT_CLAUDE_CREDENTIALS_PATH", str(tmp_path / "missing.json"))
    assert cca.resolve_credentials_path() is None
    assert cca.credentials_available() is False


def test_claude_config_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("NANOBOT_CLAUDE_CREDENTIALS_PATH", raising=False)
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    creds = cfg / ".credentials.json"
    _write(creds)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(cfg))
    assert cca.resolve_credentials_path() == creds


# --- parsing ----------------------------------------------------------------

def test_available_and_peek(tmp_path):
    creds = tmp_path / "c.json"
    _write(creds)
    c = ClaudeCodeCredentials(path=creds)
    assert c.peek_access_token() == _ACCESS


def test_missing_file_not_available(tmp_path):
    c = ClaudeCodeCredentials(path=tmp_path / "missing.json")
    assert c.peek_access_token() is None


def test_seconds_expiry_normalized_to_ms(tmp_path):
    creds = tmp_path / "c.json"
    _write(creds, expires_ms=1_700_000_000)  # seconds-scale value
    c = ClaudeCodeCredentials(path=creds)
    assert c._expires_ms == 1_700_000_000_000


# --- get_token / refresh ----------------------------------------------------

async def test_valid_token_no_refresh(monkeypatch, tmp_path):
    creds = tmp_path / "c.json"
    _write(creds, expires_ms=int(time.time() * 1000) + 3_600_000)  # +1h
    captured = _patch_http(monkeypatch, RuntimeError("should not refresh"))
    c = ClaudeCodeCredentials(path=creds)
    assert await c.get_token() == _ACCESS
    assert captured == {}  # no HTTP call


async def test_refresh_when_expiring(monkeypatch, tmp_path):
    creds = tmp_path / "c.json"
    _write(creds, expires_ms=int(time.time() * 1000) + 60_000)  # +1min (<5min margin)
    captured = _patch_http(
        monkeypatch,
        _FakeResp(200, {"access_token": "NEW", "refresh_token": "NEWREFRESH", "expires_in": 3600}),
    )
    c = ClaudeCodeCredentials(path=creds)
    token = await c.get_token()
    assert token == "NEW"
    # request shape
    assert captured["json"]["grant_type"] == "refresh_token"
    assert captured["json"]["refresh_token"] == _REFRESH
    assert captured["json"]["client_id"] == cca.DEFAULT_CLIENT_ID
    # persisted back to disk
    saved = json.loads(creds.read_text())["claudeAiOauth"]
    assert saved["accessToken"] == "NEW"
    assert saved["refreshToken"] == "NEWREFRESH"


async def test_force_refresh(monkeypatch, tmp_path):
    creds = tmp_path / "c.json"
    _write(creds, expires_ms=int(time.time() * 1000) + 3_600_000)  # valid
    _patch_http(monkeypatch, _FakeResp(200, {"access_token": "FORCED", "expires_in": 3600}))
    c = ClaudeCodeCredentials(path=creds)
    assert await c.get_token(force_refresh=True) == "FORCED"


async def test_refresh_failure_returns_stale_token(monkeypatch, tmp_path):
    creds = tmp_path / "c.json"
    _write(creds, expires_ms=int(time.time() * 1000) + 60_000)
    _patch_http(monkeypatch, _FakeResp(403, {"error": "blocked"}))
    c = ClaudeCodeCredentials(path=creds)
    assert await c.get_token() == _ACCESS  # falls back to current token


async def test_refresh_network_error_returns_stale_token(monkeypatch, tmp_path):
    creds = tmp_path / "c.json"
    _write(creds, expires_ms=int(time.time() * 1000) + 60_000)
    _patch_http(monkeypatch, ConnectionError("boom"))
    c = ClaudeCodeCredentials(path=creds)
    assert await c.get_token() == _ACCESS


async def test_write_preserves_other_keys(monkeypatch, tmp_path):
    creds = tmp_path / "c.json"
    _write(creds, expires_ms=int(time.time() * 1000) + 60_000, extra={"subscriptionType": "max"})
    _patch_http(monkeypatch, _FakeResp(200, {"access_token": "NEW2", "expires_in": 3600}))
    c = ClaudeCodeCredentials(path=creds)
    await c.get_token()
    saved = json.loads(creds.read_text())["claudeAiOauth"]
    assert saved["subscriptionType"] == "max"
    assert saved["refreshToken"] == _REFRESH  # unchanged when response omits it
