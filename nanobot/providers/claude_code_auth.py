"""Read & refresh Claude Code (``claude login``) OAuth credentials.

Lets nanobot run on a Claude Pro/Max subscription using the credentials the
Claude Code CLI stores after ``claude login`` (or ``claude setup-token``),
refreshing the short-lived access token via the OAuth refresh-token grant.

Credentials file (Linux/Windows): ``~/.claude/.credentials.json`` — or, when
``CLAUDE_CONFIG_DIR`` is set, under that directory. Shape::

    {"claudeAiOauth": {"accessToken": "...", "refreshToken": "...", "expiresAt": <ms>}}

Overridable via env:
- ``NANOBOT_CLAUDE_CREDENTIALS_PATH`` — exact creds file (authoritative; no fallback)
- ``CLAUDE_OAUTH_TOKEN_URL`` — refresh endpoint (default below)
- ``CLAUDE_OAUTH_CLIENT_ID`` — OAuth client id (default below)
- ``CLAUDE_OAUTH_USER_AGENT`` — User-Agent for the refresh request

Note: refreshing from a headless server can be blocked by Cloudflare (returns
403). If that happens on Railway, prefer ``claude setup-token`` (long-lived) via
``CLAUDE_CODE_OAUTH_TOKEN`` instead.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

DEFAULT_TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
DEFAULT_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
DEFAULT_USER_AGENT = "claude-cli/1.0 (external, cli)"

_OAUTH_KEY = "claudeAiOauth"
_REFRESH_MARGIN_MS = 5 * 60 * 1000  # refresh when <5 min remain (matches Claude Code)
_SECONDS_TS_CEILING_MS = 1_000_000_000_000  # values below this are seconds, not ms


def _candidate_paths() -> list[Path]:
    """Ordered credential-file candidates. Explicit override is authoritative."""
    explicit = os.environ.get("NANOBOT_CLAUDE_CREDENTIALS_PATH")
    if explicit:
        return [Path(explicit).expanduser()]
    paths: list[Path] = []
    cfg_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if cfg_dir:
        base = Path(cfg_dir).expanduser()
        paths.append(base / ".credentials.json")
        paths.append(base / ".claude" / ".credentials.json")
    paths.append(Path.home() / ".claude" / ".credentials.json")
    return paths


def resolve_credentials_path(*, must_exist: bool = True) -> Path | None:
    """First existing candidate path, or the preferred path when must_exist=False."""
    candidates = _candidate_paths()
    for p in candidates:
        if p.is_file():
            return p
    return None if must_exist else candidates[0]


def credentials_available() -> bool:
    """True if a parseable Claude Code OAuth credentials file is present."""
    p = resolve_credentials_path()
    if not p:
        return False
    return _parse(p) is not None


def _normalize_expiry(value: Any) -> int:
    if not isinstance(value, (int, float)):
        return 0
    exp = int(value)
    if 0 < exp < _SECONDS_TS_CEILING_MS:  # stored as seconds — normalize to ms
        exp *= 1000
    return max(0, exp)


def _parse(path: Path) -> dict[str, Any] | None:
    """Read and validate the OAuth block. Returns {access, refresh, expires_ms} or None."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("claude creds: failed to read {}: {}", path, e)
        return None
    oauth = data.get(_OAUTH_KEY) if isinstance(data, dict) else None
    if not isinstance(oauth, dict):
        return None
    access = oauth.get("accessToken")
    if not isinstance(access, str) or not access:
        return None
    refresh = oauth.get("refreshToken")
    return {
        "access": access,
        "refresh": refresh if isinstance(refresh, str) and refresh else None,
        "expires_ms": _normalize_expiry(oauth.get("expiresAt")),
    }


class ClaudeCodeCredentials:
    """Manages a Claude Code OAuth credential: load, expiry check, refresh, write-back."""

    def __init__(
        self,
        path: str | Path | None = None,
        token_url: str | None = None,
        client_id: str | None = None,
    ) -> None:
        self._path: Path | None = Path(path).expanduser() if path else None
        self._token_url = token_url or os.environ.get("CLAUDE_OAUTH_TOKEN_URL") or DEFAULT_TOKEN_URL
        self._client_id = client_id or os.environ.get("CLAUDE_OAUTH_CLIENT_ID") or DEFAULT_CLIENT_ID
        self._user_agent = os.environ.get("CLAUDE_OAUTH_USER_AGENT") or DEFAULT_USER_AGENT
        self._lock = asyncio.Lock()
        self._access: str | None = None
        self._refresh: str | None = None
        self._expires_ms: int = 0
        self._load()

    def _resolve(self, *, must_exist: bool = True) -> Path | None:
        if self._path is not None:
            if self._path.is_file() or not must_exist:
                return self._path
            return None
        return resolve_credentials_path(must_exist=must_exist)

    def _load(self) -> bool:
        p = self._resolve()
        if not p:
            return False
        parsed = _parse(p)
        if parsed is None:
            return False
        self._access = parsed["access"]
        self._refresh = parsed["refresh"]
        self._expires_ms = parsed["expires_ms"]
        self._path = p
        return True

    def peek_access_token(self) -> str | None:
        """Return the currently loaded access token without refreshing."""
        return self._access

    def _is_expiring(self, now_ms: int | None = None) -> bool:
        if not self._expires_ms:
            return False  # no expiry info — assume usable
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        return (self._expires_ms - now) <= _REFRESH_MARGIN_MS

    async def get_token(self, *, force_refresh: bool = False) -> str | None:
        """Return a valid access token, refreshing (and persisting) if near expiry."""
        async with self._lock:
            self._load()  # pick up external refreshes (e.g. the CLI itself)
            if not force_refresh and self._access and not self._is_expiring():
                return self._access
            if self._refresh and await self._do_refresh():
                return self._access
            return self._access  # fall back to the current (possibly stale) token

    async def _do_refresh(self) -> bool:
        body = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh,
            "client_id": self._client_id,
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": self._user_agent,
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(self._token_url, json=body, headers=headers)
        except Exception as e:
            logger.warning("claude creds: refresh request failed: {}", e)
            return False
        if resp.status_code != 200:
            detail = resp.text[:200].replace("\n", " ")
            logger.warning(
                "claude creds: refresh HTTP {} from {} — {}",
                resp.status_code, self._token_url, detail,
            )
            return False
        try:
            payload = resp.json()
        except Exception:
            logger.warning("claude creds: refresh returned non-JSON body")
            return False
        access = payload.get("access_token")
        if not isinstance(access, str) or not access:
            logger.warning("claude creds: refresh response missing access_token")
            return False
        self._access = access
        self._refresh = payload.get("refresh_token") or self._refresh
        expires_in = payload.get("expires_in")
        if isinstance(expires_in, (int, float)) and expires_in > 0:
            self._expires_ms = int(time.time() * 1000) + int(expires_in) * 1000
        self._write()
        logger.info("claude creds: refreshed access token (expires_in={}s)", expires_in)
        return True

    def _write(self) -> None:
        p = self._resolve(must_exist=False)
        if not p:
            return
        try:
            data: Any = {}
            if p.is_file():
                with suppress(Exception):
                    data = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
            existing = data.get(_OAUTH_KEY)
            existing = dict(existing) if isinstance(existing, dict) else {}
            existing.update(
                accessToken=self._access,
                refreshToken=self._refresh,
                expiresAt=self._expires_ms,
            )
            data[_OAUTH_KEY] = existing
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_name(p.name + ".tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            os.replace(tmp, p)
            with suppress(OSError):
                os.chmod(p, 0o600)
        except Exception as e:
            logger.warning("claude creds: failed to persist refreshed token to {}: {}", p, e)
