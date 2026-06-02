"""Cross-provider tool-call ids must be sanitized for Anthropic.

The OpenAI/Codex Responses API emits tool-call ids shaped like
``call_…|fc_…``. Anthropic requires ids matching ``^[a-zA-Z0-9_-]+$`` and 400s
the whole request otherwise — a non-fallbackable error — so a session built on
Codex would break every turn after switching the default model to a Claude
model. The provider must rewrite offending ids while keeping each tool_use id
paired with its tool_result.
"""

from __future__ import annotations

import re
from unittest.mock import patch

from nanobot.providers.anthropic_provider import AnthropicProvider, _sanitize_tool_id

_ANTHROPIC_ID = re.compile(r"^[a-zA-Z0-9_-]+$")
_CODEX_ID = "call_N61JgJugQSpgWs8s8Xy1Cnrc|fc_00581380f232f005016a19245c5d5c81a0"


def _make_provider() -> AnthropicProvider:
    with patch("anthropic.AsyncAnthropic"):
        return AnthropicProvider(api_key="sk-test", default_model="claude-opus-4-8")


def test_sanitize_replaces_pipe_separator() -> None:
    out = _sanitize_tool_id(_CODEX_ID)
    assert "|" not in out
    assert _ANTHROPIC_ID.match(out)
    assert out == _CODEX_ID.replace("|", "_")


def test_sanitize_is_deterministic() -> None:
    # tool_use and tool_result are sanitized independently; they must agree.
    assert _sanitize_tool_id(_CODEX_ID) == _sanitize_tool_id(_CODEX_ID)


def test_sanitize_passes_through_valid_ids() -> None:
    assert _sanitize_tool_id("toolu_abc-123") == "toolu_abc-123"


def test_sanitize_empty_stays_empty() -> None:
    assert _sanitize_tool_id("") == ""
    assert _sanitize_tool_id(None) == ""


def _collect_ids(anthropic_messages: list[dict]) -> tuple[list[str], list[str]]:
    tool_use_ids: list[str] = []
    tool_result_ids: list[str] = []
    for msg in anthropic_messages:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                tool_use_ids.append(block["id"])
            elif block.get("type") == "tool_result":
                tool_result_ids.append(block["tool_use_id"])
    return tool_use_ids, tool_result_ids


def test_build_kwargs_sanitizes_and_preserves_pairing() -> None:
    provider = _make_provider()
    messages = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": _CODEX_ID, "function": {"name": "exec", "arguments": "{}"}}
            ],
        },
        {"role": "tool", "tool_call_id": _CODEX_ID, "content": "done"},
        {"role": "user", "content": "thanks"},
    ]
    kwargs = provider._build_kwargs(
        messages=messages,
        tools=None,
        model="claude-opus-4-8",
        max_tokens=128,
        temperature=0.7,
        reasoning_effort=None,
        tool_choice=None,
        supports_caching=False,
    )
    tool_use_ids, tool_result_ids = _collect_ids(kwargs["messages"])
    assert tool_use_ids and tool_result_ids
    for tid in tool_use_ids + tool_result_ids:
        assert _ANTHROPIC_ID.match(tid), tid
    # The rewritten tool_use id still matches its tool_result id.
    assert set(tool_use_ids) == set(tool_result_ids)
    assert "|" not in tool_use_ids[0]
