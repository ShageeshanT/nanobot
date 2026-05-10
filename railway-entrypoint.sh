#!/bin/bash
# Railway-aware entrypoint:
#   1. As root, fix volume ownership.
#   2. Drop to the nanobot user.
#   3. If a WhatsApp session exists, start the Baileys bridge supervisor
#      in the background so the gateway can reach it on ws://127.0.0.1:3001.
#   4. If config + Codex OAuth token are present, exec `nanobot gateway`.
#      Otherwise idle so the operator can SSH in and complete onboarding.

set -e

if [ "$(id -u)" = "0" ]; then
    mkdir -p /home/nanobot/.nanobot/auth
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

if [ -f "$CONFIG" ] && [ -f "$TOKEN" ]; then
    start_whatsapp_bridge
    echo "🐈 nanobot: config + Codex token present, starting gateway..."
    exec nanobot gateway
fi

echo "🐈 nanobot: waiting for first-time setup."
echo "   Missing: $([ ! -f "$CONFIG" ] && echo -n "$CONFIG ")$([ ! -f "$TOKEN" ] && echo -n "$TOKEN")"
echo "   SSH in and run: nanobot provider login openai-codex"
echo "   Then redeploy / restart this service."
exec tail -f /dev/null
