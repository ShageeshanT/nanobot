# Railway: MiniMax + Claude Pro/Max subscription (Opus 4.8)

Two LLM options on Railway:

1. **Claude Pro/Max subscription** — log in once with `claude login` on the
   Railway shell; nanobot reads the stored credentials and runs Claude (e.g.
   `claude-opus-4-8`) on your subscription, **auto-refreshing** the token.
2. **MiniMax** — pay-as-you-go MiniMax models, via the `MINIMAX_API_KEY` variable.

The Docker image ships the **Claude Code CLI** and sets
`CLAUDE_CONFIG_DIR=/home/nanobot/.nanobot/claude` so your login persists on the
volume across redeploys. nanobot then:

- reads `…/.credentials.json` (`claudeAiOauth.{accessToken,refreshToken,expiresAt}`),
- sends the token as a **Bearer** credential with the `oauth-2025-04-20` /
  `claude-code-20250219` beta headers,
- prepends the required `"You are Claude Code…"` system block **and a friendly
  general-assistant reframe** so it behaves as a personal assistant, not a coding tool,
- refreshes the access token automatically when it nears expiry.

Implemented in `nanobot/providers/anthropic_provider.py` + `nanobot/providers/claude_code_auth.py`.

---

## 1. Configure the model

Set a Railway variable **`NANOBOT_CONFIG_JSON`** (written to the volume on first
boot, never overwriting an existing config) — Claude Opus 4.8 as default, MiniMax
as a switchable preset:

```json
{
  "agents": {
    "defaults": {
      "model": "claude-opus-4-8",
      "provider": "anthropic",
      "maxTokens": 16384,
      "contextWindowTokens": 200000
    }
  },
  "providers": { "minimax": { "apiKey": "${MINIMAX_API_KEY}" } },
  "modelPresets": {
    "minimax": { "model": "MiniMax-M2", "provider": "minimax", "maxTokens": 8192, "contextWindowTokens": 200000 }
  },
  "gateway": { "host": "0.0.0.0", "port": 18790 }
}
```

> **Important:** `provider` must be `"anthropic"` (not `"auto"`). With no Anthropic
> API key in the config, `auto` can't match Claude by name and would mis-route to
> MiniMax. The subscription credential comes from the `claude login` file, not the config.
>
> Don't want MiniMax? Drop the `providers.minimax` and `modelPresets.minimax`
> blocks (and skip `MINIMAX_API_KEY`). MiniMax-only? Set the default `model` to
> `MiniMax-M2`, `provider` to `minimax`.

Add your channel(s) under `"channels"` as usual, or use the built-in WebUI.

## 2. Set Railway variables

| Variable | Value | Needed for |
| --- | --- | --- |
| `NANOBOT_CONFIG_JSON` | the JSON above | always |
| `MINIMAX_API_KEY` | your MiniMax key | only if using MiniMax |

(No Anthropic key/token variable — that comes from `claude login` in step 4.)

## 3. Deploy

Deploy the service. With a config present the gateway starts (it no longer
requires an OpenAI Codex token). Logs: `🐈 nanobot: config present, starting gateway...`.

## 4. Log in to your Claude subscription

Open the Railway **shell/terminal** for the service and run:

```bash
claude login
```

(If `claude login` isn't recognized, run `claude` and choose **/login**.) It
prints a URL — open it in your browser, approve, paste the code back. Credentials
are saved to `/home/nanobot/.nanobot/claude/.credentials.json` (persistent).

nanobot picks them up automatically — no restart needed for the next turn (it
re-reads the file each request). If you want, restart the service to confirm.

Verify: `nanobot status` should show Anthropic configured.

---

## Customize the agent's persona (the "nice prompt")

By default, on the subscription the agent is reframed as a warm general-purpose
personal assistant (not a coding tool). To set your own, add a Railway variable:

```
NANOBOT_CLAUDE_AGENT_PROMPT = You are Ayla, a friendly, proactive personal assistant who …
```

Set it to an empty string to drop the reframe. Deeper persona still lives in the
workspace `SOUL.md` / `AGENTS.md`, which apply on top of this.

---

## Notes & caveats

- **Token refresh on headless servers / Cloudflare:** Claude `login` access
  tokens are short-lived (~1h) and refresh via
  `https://console.anthropic.com/v1/oauth/token`. Cloudflare *sometimes* blocks
  refreshes from headless hosts (HTTP 403). If Claude calls start failing after
  ~an hour, either re-run `claude login`, or switch to a long-lived
  **setup-token** (below). Overridable: `CLAUDE_OAUTH_TOKEN_URL`,
  `CLAUDE_OAUTH_CLIENT_ID`, `CLAUDE_OAUTH_USER_AGENT`.
- **Bulletproof alternative — setup-token:** run `claude setup-token` (valid ~1
  year, no refresh needed) and set it as `CLAUDE_CODE_OAUTH_TOKEN` in Railway.
  nanobot uses it the same way. This avoids the Cloudflare refresh issue entirely.
- **Temperature** is omitted automatically for `claude-opus-4-7` / `-4-8`.
- **1M context** is not available with subscription auth — keep
  `contextWindowTokens` ≤ `200000`.
- **Extended thinking** is optional: add `"reasoningEffort": "high"` (or
  `medium` / `adaptive` / `none`) under `agents.defaults`.
- Credentials file location override: `NANOBOT_CLAUDE_CREDENTIALS_PATH`.
