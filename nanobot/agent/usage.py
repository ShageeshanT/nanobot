"""Lightweight token-usage / cost tracking for the dashboard.

nanobot does not otherwise persist token usage. ``UsageStore`` appends one JSON
line per agent turn to ``<workspace>/usage/usage.jsonl`` and aggregates it for
the dashboard's Usage panel. Recording is best-effort and never raises into the
agent loop.

Costs are *estimates* from a small built-in price table (USD per 1M tokens);
unknown models report 0. Override/extend via ``NANOBOT_MODEL_PRICES`` (JSON map
of ``{"model-substring": [input_per_mtok, output_per_mtok]}``).
"""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

# Approximate public prices, USD per 1M tokens: (input, output). Matched by the
# first substring found in the (lowercased) model name. Best-effort — adjust via
# the NANOBOT_MODEL_PRICES env var.
_DEFAULT_PRICES: tuple[tuple[str, float, float], ...] = (
    ("opus", 15.0, 75.0),
    ("sonnet", 3.0, 15.0),
    ("haiku", 0.80, 4.0),
    ("gpt-4o-mini", 0.15, 0.60),
    ("gpt-4o", 2.50, 10.0),
    ("gpt-4.1-mini", 0.40, 1.60),
    ("gpt-4.1", 2.0, 8.0),
    ("gpt-5", 1.25, 10.0),
    ("o3", 2.0, 8.0),
    ("minimax", 0.30, 1.20),
    ("deepseek", 0.27, 1.10),
    ("gemini-2.5-pro", 1.25, 10.0),
    ("gemini", 0.30, 2.50),
    ("qwen", 0.40, 1.20),
    ("kimi", 0.60, 2.50),
    ("glm", 0.60, 2.20),
)

_MAX_SCAN_LINES = 20_000  # safety cap when aggregating


def _load_price_overrides() -> tuple[tuple[str, float, float], ...]:
    raw = os.environ.get("NANOBOT_MODEL_PRICES")
    if not raw:
        return ()
    try:
        data = json.loads(raw)
        return tuple(
            (str(k).lower(), float(v[0]), float(v[1]))
            for k, v in data.items()
            if isinstance(v, (list, tuple)) and len(v) == 2
        )
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("usage: ignoring invalid NANOBOT_MODEL_PRICES: {}", e)
        return ()


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Best-effort USD cost estimate; 0.0 when the model price is unknown."""
    name = (model or "").lower()
    for key, pin, pout in (*_load_price_overrides(), *_DEFAULT_PRICES):
        if key in name:
            return round(input_tokens / 1e6 * pin + output_tokens / 1e6 * pout, 6)
    return 0.0


class UsageStore:
    """Append-only per-turn usage log + aggregation, scoped to a workspace."""

    def __init__(self, workspace: Path | str) -> None:
        self.path = Path(workspace).expanduser() / "usage" / "usage.jsonl"

    def record(
        self,
        model: str,
        usage: dict[str, Any] | None,
        session_key: str | None = None,
    ) -> None:
        """Append one usage record. Best-effort: never raises."""
        if not usage:
            return
        try:
            input_tokens = int(usage.get("prompt_tokens", 0) or 0)
            output_tokens = int(usage.get("completion_tokens", 0) or 0)
            if input_tokens <= 0 and output_tokens <= 0:
                return
            cached = int(usage.get("cached_tokens", 0) or 0)
            record = {
                "ts": int(time.time() * 1000),
                "session_key": session_key or "",
                "model": model or "",
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cached_tokens": cached,
                "total_tokens": input_tokens + output_tokens,
                "cost_usd": estimate_cost(model, input_tokens, output_tokens),
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("usage: failed to record turn: {}", e)

    def _iter_records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        try:
            with open(self.path, encoding="utf-8") as f:
                lines = f.readlines()[-_MAX_SCAN_LINES:]
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except Exception:
                    continue
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("usage: failed to read {}: {}", self.path, e)
        return records

    def summary(self, days: int = 30, max_recent: int = 20) -> dict[str, Any]:
        """Aggregate usage into totals, per-model, per-day, and recent rows."""
        records = self._iter_records()
        now_ms = int(time.time() * 1000)
        cutoff = now_ms - days * 86_400_000

        totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0, "turns": 0}
        by_model: dict[str, dict[str, float]] = defaultdict(
            lambda: {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0, "turns": 0}
        )
        by_day: dict[str, dict[str, float]] = {}

        windowed = [r for r in records if int(r.get("ts", 0) or 0) >= cutoff]
        for r in windowed:
            inp = int(r.get("input_tokens", 0) or 0)
            out = int(r.get("output_tokens", 0) or 0)
            cost = float(r.get("cost_usd", 0.0) or 0.0)
            model = r.get("model") or "unknown"
            totals["input_tokens"] += inp
            totals["output_tokens"] += out
            totals["total_tokens"] += inp + out
            totals["cost_usd"] += cost
            totals["turns"] += 1
            m = by_model[model]
            m["input_tokens"] += inp
            m["output_tokens"] += out
            m["total_tokens"] += inp + out
            m["cost_usd"] += cost
            m["turns"] += 1
            day = datetime.fromtimestamp(int(r.get("ts", 0) or 0) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            d = by_day.setdefault(day, {"date": day, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0, "turns": 0})
            d["input_tokens"] += inp
            d["output_tokens"] += out
            d["total_tokens"] += inp + out
            d["cost_usd"] += cost
            d["turns"] += 1

        totals["cost_usd"] = round(totals["cost_usd"], 4)
        for m in by_model.values():
            m["cost_usd"] = round(m["cost_usd"], 4)
        series = [by_day[k] for k in sorted(by_day)]
        for d in series:
            d["cost_usd"] = round(d["cost_usd"], 4)

        recent = [
            {
                "ts": r.get("ts"),
                "model": r.get("model"),
                "session_key": r.get("session_key"),
                "input_tokens": r.get("input_tokens"),
                "output_tokens": r.get("output_tokens"),
                "cost_usd": r.get("cost_usd"),
            }
            for r in records[-max_recent:][::-1]
        ]

        models = [
            {"model": name, **vals}
            for name, vals in sorted(by_model.items(), key=lambda kv: kv[1]["total_tokens"], reverse=True)
        ]
        return {
            "totals": totals,
            "by_model": models,
            "series": series,
            "recent": recent,
            "window_days": days,
        }
