# Dashboard

The WebUI ships an admin **Dashboard** — a monitoring/ops surface modeled on the
agenflow dashboard (collapsible nav rail + full-page panels with metric cards,
charts and tables), styled with nanobot's own design system.

Open it from the chat sidebar footer → **Dashboard** (next to Settings). It uses
the same gateway auth (Bearer token from `/webui/bootstrap`) as the rest of the UI.

## Panels

| Panel | Shows | Actions |
| --- | --- | --- |
| **Overview** | version, uptime, live connections, active model/provider, counts (sessions, channels, providers, cron), 30-day token chart, recent sessions, channels | — (auto-refresh 15s) |
| **Usage & cost** | token totals, per-day chart, per-model breakdown with cost — windowed 7/30/90 days | — |
| **Sessions** | all sessions with search | delete |
| **Models** | active model/provider, model presets, provider key status | switch model/provider, apply preset |
| **Channels** | configured channels, enabled/credential status | — |
| **Cron** | scheduled jobs, schedule, next run, last status | — (manage via the agent's cron tool) |
| **Memory** | workspace files (MEMORY.md, HEARTBEAT.md, SOUL.md, AGENTS.md, USER.md, TOOLS.md) | read-only viewer |
| **Logs** | live gateway log tail with level filter | live/pause, refresh |
| **Config** | redacted `config.json` (secrets masked) + path | read-only |

Control actions reuse the existing safe gateway endpoints (model/provider switch,
session delete). Cron/memory/config are read-only because the gateway's HTTP
transport is GET-only and can't carry large request bodies.

## Backend

New read endpoints on the gateway (all `GET`, Bearer-authed), in
`nanobot/channels/websocket.py` + data gatherers in `nanobot/channels/dashboard.py`:

- `/api/dashboard/overview`
- `/api/dashboard/usage?days=N`
- `/api/dashboard/channels`
- `/api/dashboard/cron`
- `/api/dashboard/memory`
- `/api/dashboard/config`
- `/api/dashboard/presets`
- `/api/dashboard/logs?limit=N&level=LEVEL`

(The dashboard also reuses `/api/sessions`, `/api/settings`, `/api/settings/update`.)

### Token-usage tracking

nanobot didn't previously persist token usage. `nanobot/agent/usage.py`
(`UsageStore`) appends one record per agent turn to
`<workspace>/usage/usage.jsonl` (hooked in `AgentLoop`), and the Usage panel
aggregates it. **Usage is therefore tracked from the moment this lands** — historic
turns aren't backfilled.

**Cost is estimated** from a small built-in price table (USD per 1M tokens);
unknown models report `$0`. Override/extend with the `NANOBOT_MODEL_PRICES` env var:

```bash
NANOBOT_MODEL_PRICES='{"my-model": [0.5, 2.0]}'   # [input_per_mtok, output_per_mtok]
```

### Logs

`install_log_buffer()` (called at gateway start) tees loguru output into an
in-memory ring buffer (last 2000 lines) that the Logs panel reads. Adjust the
captured level via the call site if needed.
