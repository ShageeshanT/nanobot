"""Read-mostly data gatherers powering the WebUI dashboard.

Pure functions that assemble JSON-able dicts from config + the filesystem, so the
gateway's HTTP handlers stay thin. Imports are done lazily to avoid import cycles
(``websocket.py`` imports this module).
"""

from __future__ import annotations

import time
from collections import deque
from pathlib import Path
from typing import Any

from loguru import logger

# --- log ring buffer --------------------------------------------------------

_LOG_BUFFER: deque[dict[str, Any]] = deque(maxlen=2000)
_GATEWAY_STARTED_AT: float = time.time()
_LOG_SINK_ID: int | None = None


def _log_sink(message: Any) -> None:
    rec = message.record
    _LOG_BUFFER.append(
        {
            "ts": int(rec["time"].timestamp() * 1000),
            "level": rec["level"].name,
            "name": rec["name"],
            "message": rec["message"],
        }
    )


def install_log_buffer(level: str = "INFO") -> None:
    """Tee gateway logs into an in-memory ring buffer for the Logs panel.

    Idempotent and safe to call once at gateway start. Also (re)stamps the
    gateway start time used for uptime.
    """
    global _LOG_SINK_ID, _GATEWAY_STARTED_AT
    _GATEWAY_STARTED_AT = time.time()
    if _LOG_SINK_ID is not None:
        return
    try:
        _LOG_SINK_ID = logger.add(_log_sink, level=level, enqueue=False)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("dashboard: failed to install log buffer: {}", e)


def recent_logs(limit: int = 300, level: str | None = None) -> dict[str, Any]:
    items = list(_LOG_BUFFER)
    if level:
        wanted = level.strip().upper()
        items = [r for r in items if r["level"] == wanted]
    return {"logs": items[-limit:][::-1], "count": len(_LOG_BUFFER)}


# --- secret redaction -------------------------------------------------------

_SECRET_HINTS = ("key", "token", "secret", "password", "passwd", "webhook", "credential")


def _looks_secret(name: str) -> bool:
    n = name.lower()
    return any(h in n for h in _SECRET_HINTS)


def _mask(value: Any) -> Any:
    if isinstance(value, str) and value:
        return f"set ({len(value)} chars)"
    return value


def _redact(obj: Any, *, parent_key: str = "") -> Any:
    if isinstance(obj, dict):
        return {
            k: (_mask(v) if _looks_secret(str(k)) and not isinstance(v, (dict, list)) else _redact(v, parent_key=str(k)))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(v, parent_key=parent_key) for v in obj]
    return obj


# --- helpers ----------------------------------------------------------------

def _workspace() -> Path:
    from nanobot.config.loader import load_config

    return load_config().workspace_path


# Workspace files exposed (read + write) by the Memory panel.
def _memory_paths(workspace: Path) -> dict[str, Path]:
    return {
        "MEMORY.md": workspace / "memory" / "MEMORY.md",
        "HEARTBEAT.md": workspace / "HEARTBEAT.md",
        "SOUL.md": workspace / "SOUL.md",
        "AGENTS.md": workspace / "AGENTS.md",
        "USER.md": workspace / "USER.md",
        "TOOLS.md": workspace / "TOOLS.md",
    }


# --- public data gatherers --------------------------------------------------

def overview(session_manager: Any, active_connections: int) -> dict[str, Any]:
    from nanobot import __version__
    from nanobot.config.loader import load_config

    config = load_config()
    defaults = config.agents.defaults
    provider_name = config.get_provider_name(defaults.model) or defaults.provider

    sessions: list[dict[str, Any]] = []
    if session_manager is not None:
        try:
            sessions = session_manager.list_sessions()
        except Exception:
            sessions = []
    ws_sessions = [s for s in sessions if str(s.get("key", "")).startswith("websocket:")]
    recent = [
        {k: v for k, v in s.items() if k != "path"}
        for s in ws_sessions[:6]
    ]

    ch = channels_status()
    usage = usage_summary(days=30)

    providers_configured = 0
    from nanobot.providers.registry import PROVIDERS

    for spec in PROVIDERS:
        pc = getattr(config.providers, spec.name, None)
        if pc is not None and getattr(pc, "api_key", None):
            providers_configured += 1

    return {
        "version": __version__,
        "uptime_s": max(0, int(time.time() - _GATEWAY_STARTED_AT)),
        "active_connections": active_connections,
        "model": defaults.model,
        "provider": provider_name,
        "reasoning_effort": defaults.reasoning_effort,
        "counts": {
            "sessions": len(sessions),
            "webui_sessions": len(ws_sessions),
            "channels_enabled": ch["enabled_count"],
            "channels_total": len(ch["channels"]),
            "providers_configured": providers_configured,
            "cron_jobs": len(cron_jobs()["jobs"]),
        },
        "usage": usage,
        "recent_sessions": recent,
        "channels": ch["channels"],
    }


def channels_status() -> dict[str, Any]:
    from nanobot.config.loader import load_config

    config = load_config()
    extra = getattr(config.channels, "__pydantic_extra__", None) or {}
    channels: list[dict[str, Any]] = []
    for name, value in extra.items():
        if not isinstance(value, dict):
            continue
        enabled = bool(value.get("enabled", True))
        configured = any(
            _looks_secret(str(k)) and isinstance(v, str) and v
            for k, v in value.items()
        )
        channels.append(
            {
                "name": name,
                "enabled": enabled,
                "configured": configured,
                "type": value.get("type") or value.get("kind") or None,
            }
        )
    channels.sort(key=lambda c: (not c["enabled"], c["name"]))
    return {"channels": channels, "enabled_count": sum(1 for c in channels if c["enabled"])}


def _serialize_cron_job(job: Any) -> dict[str, Any]:
    sched = job.schedule
    state = job.state
    return {
        "id": job.id,
        "name": job.name,
        "enabled": job.enabled,
        "schedule": {
            "kind": sched.kind,
            "expr": sched.expr,
            "every_ms": sched.every_ms,
            "at_ms": sched.at_ms,
            "tz": sched.tz,
        },
        "message": job.payload.message,
        "channel": job.payload.channel,
        "deliver": job.payload.deliver,
        "next_run_at_ms": state.next_run_at_ms,
        "last_run_at_ms": state.last_run_at_ms,
        "last_status": state.last_status,
        "last_error": state.last_error,
        "created_at_ms": job.created_at_ms,
        "delete_after_run": job.delete_after_run,
    }


def _cron_service() -> Any:
    from nanobot.cron.service import CronService

    return CronService(_workspace() / "cron" / "jobs.json")


def cron_jobs() -> dict[str, Any]:
    try:
        jobs = _cron_service().list_jobs(include_disabled=True)
        return {"jobs": [_serialize_cron_job(j) for j in jobs]}
    except Exception as e:
        logger.warning("dashboard: failed to list cron jobs: {}", e)
        return {"jobs": []}


def memory_files() -> dict[str, Any]:
    workspace = _workspace()
    files = []
    for name, path in _memory_paths(workspace).items():
        content = ""
        exists = path.is_file()
        if exists:
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                content = ""
        files.append({"name": name, "exists": exists, "content": content, "path": str(path)})
    return {"files": files}


def config_redacted() -> dict[str, Any]:
    from nanobot.config.loader import get_config_path, load_config

    config = load_config()
    data = config.model_dump(mode="json", by_alias=True)
    return {"config": _redact(data), "config_path": str(get_config_path().expanduser())}


def model_presets() -> dict[str, Any]:
    from nanobot.config.loader import load_config

    config = load_config()
    presets = [
        {
            "name": name,
            "model": preset.model,
            "provider": preset.provider,
            "max_tokens": preset.max_tokens,
            "context_window_tokens": preset.context_window_tokens,
            "temperature": preset.temperature,
            "reasoning_effort": preset.reasoning_effort,
        }
        for name, preset in config.model_presets.items()
    ]
    active = config.agents.defaults.model_preset
    return {"presets": presets, "active": active}


def usage_summary(days: int = 30) -> dict[str, Any]:
    from nanobot.agent.usage import UsageStore

    try:
        return UsageStore(_workspace()).summary(days=days)
    except Exception as e:
        logger.warning("dashboard: failed to summarize usage: {}", e)
        return {"totals": {}, "by_model": [], "series": [], "recent": [], "window_days": days}
