#!/bin/bash
# Railway-aware entrypoint:
#   1. As root, fix volume ownership.
#   2. Drop to the nanobot user.
#   3. If a WhatsApp session exists, start the Baileys bridge supervisor
#      in the background so the gateway can reach it on ws://127.0.0.1:3001.
#   4. If config.json is present (optionally seeded from $NANOBOT_CONFIG_JSON),
#      exec `nanobot gateway`. Otherwise idle so the operator can SSH in and
#      complete onboarding.

set -e

if [ "$(id -u)" = "0" ]; then
    mkdir -p /home/nanobot/.nanobot/auth /home/nanobot/.nanobot/claude
    chown -R 1000:1000 /home/nanobot
    exec gosu nanobot:nanobot "$0" "$@"
fi

CONFIG="/home/nanobot/.nanobot/config.json"
TOKEN="${OAUTH_CLI_KIT_TOKEN_PATH:-/home/nanobot/.nanobot/auth/codex.json}"
WA_CREDS="/home/nanobot/.nanobot/whatsapp-auth/creds.json"
WA_BRIDGE_TOKEN_FILE="/home/nanobot/.nanobot/whatsapp-auth/bridge-token"
WA_BRIDGE_LOG="/home/nanobot/.nanobot/bridge.log"

start_whatsapp_bridge() {
    if [ ! -f "$WA_CREDS" ] || [ ! -f "$WA_BRIDGE_TOKEN_FILE" ]; then
        return 0
    fi
    local bt
    bt="$(cat "$WA_BRIDGE_TOKEN_FILE")"
    echo "🐈 nanobot: starting WhatsApp bridge supervisor..."
    (
        while true; do
            ( cd /app/bridge && BRIDGE_TOKEN="$bt" AUTH_DIR=/home/nanobot/.nanobot/whatsapp-auth node dist/index.js ) >> "$WA_BRIDGE_LOG" 2>&1
            echo "$(date -Iseconds) bridge exited with code $?, restarting in 5s..." >> "$WA_BRIDGE_LOG"
            sleep 5
        done
    ) &
    echo "🐈 nanobot: bridge supervisor pid=$!"
}

# First-boot convenience: materialize config.json from a NANOBOT_CONFIG_JSON
# env var (handy on Railway, where config lives in variables rather than on the
# volume). Never clobber an existing config written by onboarding.
if [ ! -f "$CONFIG" ] && [ -n "$NANOBOT_CONFIG_JSON" ]; then
    echo "🐈 nanobot: writing config.json from \$NANOBOT_CONFIG_JSON..."
    mkdir -p "$(dirname "$CONFIG")"
    printf '%s' "$NANOBOT_CONFIG_JSON" > "$CONFIG"
fi

# Start the gateway as soon as a config exists. The Codex OAuth token is only
# needed by the openai-codex provider, so it must not gate Anthropic/MiniMax or
# Claude-subscription deployments.
if [ -f "$CONFIG" ]; then
    start_whatsapp_bridge
    if [ -f "$TOKEN" ]; then
        echo "🐈 nanobot: config + Codex token present, starting gateway..."
    else
        echo "🐈 nanobot: config present, starting gateway..."
    fi
    exec nanobot gateway
fi

echo "🐈 nanobot: waiting for first-time setup (no config.json yet)."
echo "   Provide config via either:"
echo "     • a NANOBOT_CONFIG_JSON Railway variable (full config JSON), or"
echo "     • SSH in and run: nanobot onboard"
exec tail -f /dev/null
