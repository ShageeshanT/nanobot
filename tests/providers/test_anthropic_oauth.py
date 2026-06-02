"""Tests for Anthropic provider Claude Pro/Max subscription (OAuth) support.

A Claude Code token (setup-token, env var, or `claude login` credentials file)
must be sent as a Bearer credential with the OAuth beta headers, the system
prompt must lead with the Claude Code identity + general-agent reframe, and
pay-as-you-go API keys / the MiniMax-Anthropic endpoint must be left untouched.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from nanobot.providers.anthropic_provider import (
    _CLAUDE_CODE_IDENTITY,
    _DEFAULT_GENERAL_AGENT_PROMPT,
    AnthropicProvider,
)

_OAT = "sk-ant-oat01-EXAMPLE"
_API = "sk-ant-api03-EXAMPLE"
_MINIMAX_BASE = "https://api.minimax.io/anthropic"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    """Isolate every test from the dev machine's real env / ~/.claude creds."""
    for var in (
        "CLAUDE_CODE_OAUTH_TOKEN",
        "ANTHROPIC_OAUTH_TOKEN",
        "NANOBOT_CLAUDE_AGENT_PROMPT",
        "CLAUDE_CONFIG_DIR",
    ):
        monkeypatch.delenv(var, raising=False)
    # Authoritative (no-fallback) creds path that does not exist.
    monkeypatch.setenv("NANOBOT_CLAUDE_CREDENTIALS_PATH", str(tmp_path / "nope.json"))


def _make(**kwargs) -> AnthropicProvider:
    with patch("anthropic.AsyncAnthropic"):
        return AnthropicProvider(**kwargs)


def _build(provider: AnthropicProvider, **overrides):
    defaults = dict(
        messages=[
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": "hello"},
        ],
        tools=None,
        model=None,
        max_tokens=4096,
        temperature=0.7,
        reasoning_effort=None,
        tool_choice=None,
        supports_caching=False,
    )
    defaults.update(overrides)
    return provider._build_kwargs(**defaults)


def _write_creds(path, access=_OAT, refresh="sk-ant-ort01-EXAMPLE", expires_ms=4_102_444_800_000):
    payload = {"claudeAiOauth": {"accessToken": access, "expiresAt": expires_ms}}
    if refresh is not None:
        payload["claudeAiOauth"]["refreshToken"] = refresh
    path.write_text(json.dumps(payload), encoding="utf-8")


# --- OAuth detection --------------------------------------------------------

def test_explicit_auth_token_enables_oauth():
    assert _make(auth_token=_OAT)._oauth is True


def test_setup_token_api_key_enables_oauth():
    assert _make(api_key=_OAT)._oauth is True


def test_normal_api_key_is_not_oauth():
    assert _make(api_key=_API)._oauth is False


def test_env_token_enables_oauth_for_anthropic_base(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _OAT)
    assert _make()._oauth is True


def test_anthropic_oauth_token_env_alias(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_OAUTH_TOKEN", _OAT)
    assert _make()._oauth is True


def test_explicit_api_key_wins_over_env(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _OAT)
    assert _make(api_key=_API)._oauth is False


def test_env_token_ignored_for_minimax_base(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _OAT)
    assert _make(api_base=_MINIMAX_BASE)._oauth is False


def test_minimax_key_on_minimax_base_is_not_oauth():
    assert _make(api_key="minimax-key", api_base=_MINIMAX_BASE)._oauth is False


# --- claude login credentials file ------------------------------------------

def test_creds_file_enables_oauth(monkeypatch, tmp_path):
    creds = tmp_path / "creds.json"
    _write_creds(creds)
    monkeypatch.setenv("NANOBOT_CLAUDE_CREDENTIALS_PATH", str(creds))
    p = _make()
    assert p._oauth is True
    assert p._creds is not None
    assert p._creds.peek_access_token() == _OAT


def test_creds_file_ignored_when_api_key_present(monkeypatch, tmp_path):
    creds = tmp_path / "creds.json"
    _write_creds(creds)
    monkeypatch.setenv("NANOBOT_CLAUDE_CREDENTIALS_PATH", str(creds))
    p = _make(api_key=_API)
    assert p._oauth is False
    assert p._creds is None


def test_creds_file_ignored_for_minimax_base(monkeypatch, tmp_path):
    creds = tmp_path / "creds.json"
    _write_creds(creds)
    monkeypatch.setenv("NANOBOT_CLAUDE_CREDENTIALS_PATH", str(creds))
    p = _make(api_base=_MINIMAX_BASE)
    assert p._oauth is False
    assert p._creds is None


async def test_apply_oauth_credentials_sets_client_token(monkeypatch, tmp_path):
    creds = tmp_path / "creds.json"
    _write_creds(creds)  # far-future expiry → no refresh
    monkeypatch.setenv("NANOBOT_CLAUDE_CREDENTIALS_PATH", str(creds))
    p = _make()
    assert p._creds is not None
    p._client.auth_token = "STALE"
    await p._apply_oauth_credentials()
    assert p._client.auth_token == _OAT
    assert p._client.api_key is None


# --- Client wiring ----------------------------------------------------------

def test_oauth_uses_auth_token_not_api_key():
    with patch("anthropic.AsyncAnthropic") as mock_client:
        AnthropicProvider(api_key=_OAT)
    kwargs = mock_client.call_args.kwargs
    assert kwargs.get("auth_token") == _OAT
    assert "api_key" not in kwargs


def test_normal_key_uses_api_key_not_auth_token():
    with patch("anthropic.AsyncAnthropic") as mock_client:
        AnthropicProvider(api_key=_API)
    kwargs = mock_client.call_args.kwargs
    assert kwargs.get("api_key") == _API
    assert "auth_token" not in kwargs


def test_oauth_forces_client_api_key_none():
    """Bearer-only: the constructed client must not carry an x-api-key."""
    with patch("anthropic.AsyncAnthropic") as mock_client:
        AnthropicProvider(auth_token=_OAT)
    assert mock_client.return_value.api_key is None


# --- Beta headers -----------------------------------------------------------

def test_oauth_sets_beta_header():
    betas = _make(auth_token=_OAT).extra_headers["anthropic-beta"].split(",")
    assert "oauth-2025-04-20" in betas
    assert "claude-code-20250219" in betas


def test_beta_header_merges_without_duplicates():
    p = _make(auth_token=_OAT, extra_headers={"anthropic-beta": "custom-beta,oauth-2025-04-20"})
    betas = p.extra_headers["anthropic-beta"].split(",")
    assert betas.count("oauth-2025-04-20") == 1
    assert "custom-beta" in betas
    assert "claude-code-20250219" in betas


def test_non_oauth_has_no_beta_header():
    assert "anthropic-beta" not in _make(api_key=_API).extra_headers


# --- System prompt identity + general-agent reframe -------------------------

def test_identity_leads_then_reframe_then_system():
    kw = _build(_make(auth_token=_OAT))
    assert kw["system"][0] == {"type": "text", "text": _CLAUDE_CODE_IDENTITY}
    assert kw["system"][1]["text"] == _DEFAULT_GENERAL_AGENT_PROMPT
    assert kw["system"][-1]["text"] == "SYS"


def test_reframe_mentions_general_assistant():
    kw = _build(_make(auth_token=_OAT))
    assert "general-purpose personal assistant" in kw["system"][1]["text"]


def test_reframe_env_override(monkeypatch):
    monkeypatch.setenv("NANOBOT_CLAUDE_AGENT_PROMPT", "Be a friendly butler named Jeeves.")
    kw = _build(_make(auth_token=_OAT))
    assert kw["system"][1]["text"] == "Be a friendly butler named Jeeves."
    assert kw["system"][-1]["text"] == "SYS"


def test_reframe_disabled_when_env_empty(monkeypatch):
    monkeypatch.setenv("NANOBOT_CLAUDE_AGENT_PROMPT", "")
    kw = _build(_make(auth_token=_OAT))
    assert kw["system"][0]["text"] == _CLAUDE_CODE_IDENTITY
    assert kw["system"][1]["text"] == "SYS"
    assert len(kw["system"]) == 2


def test_identity_not_prepended_without_oauth():
    kw = _build(_make(api_key=_API))
    assert kw["system"] == "SYS"


def test_identity_present_even_without_user_system():
    kw = _build(_make(auth_token=_OAT), messages=[{"role": "user", "content": "hi"}])
    assert kw["system"][0]["text"] == _CLAUDE_CODE_IDENTITY


# --- opus-4-8 temperature ---------------------------------------------------

def test_opus_4_8_omits_temperature():
    assert "temperature" not in _build(_make(api_key=_API, default_model="claude-opus-4-8"))


def test_opus_4_8_oauth_omits_temperature():
    kw = _build(_make(auth_token=_OAT, default_model="claude-opus-4-8"))
    assert "temperature" not in kw
    assert kw["system"][0]["text"] == _CLAUDE_CODE_IDENTITY
