#!/bin/bash
# Railway-aware entrypoint:
#   1. As root, fix volume ownership.
#   2. Drop to the nanobot user.
#   3. If config + Codex OAuth token are present, exec `nanobot gateway`.
#      Otherwise idle so the operator can SSH in and run `nanobot onboard`
#      / `nanobot provider login openai-codex` against the live volume.

set -e

if [ "$(id -u)" = "0" ]; then
    mkdir -p /home/nanobot/.nanobot/auth
    chown -R 1000:1000 /home/nanobot
    exec gosu nanobot:nanobot "$0" "$@"
fi

CONFIG="/home/nanobot/.nanobot/config.json"
TOKEN="${OAUTH_CLI_KIT_TOKEN_PATH:-/home/nanobot/.nanobot/auth/codex.json}"

if [ -f "$CONFIG" ] && [ -f "$TOKEN" ]; then
    echo "🐈 nanobot: config + Codex token present, starting gateway..."
    exec nanobot gateway
fi

echo "🐈 nanobot: waiting for first-time setup."
echo "   Missing: $([ ! -f "$CONFIG" ] && echo -n "$CONFIG ")$([ ! -f "$TOKEN" ] && echo -n "$TOKEN")"
echo "   SSH in and run: nanobot provider login openai-codex"
echo "   Then redeploy / restart this service."
exec tail -f /dev/null
