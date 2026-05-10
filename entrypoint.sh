#!/bin/sh
dir="$HOME/.nanobot"

# When started as root (typical on managed platforms like Railway where
# mounted volumes are owned by UID 0), fix ownership and drop privileges
# to the nanobot user so the rest of the app runs unprivileged.
if [ "$(id -u)" = "0" ]; then
    mkdir -p "$dir"
    chown -R 1000:1000 "$HOME"
    exec gosu nanobot:nanobot nanobot "$@"
fi

if [ -d "$dir" ] && [ ! -w "$dir" ]; then
    owner_uid=$(stat -c %u "$dir" 2>/dev/null || stat -f %u "$dir" 2>/dev/null)
    cat >&2 <<EOF
Error: $dir is not writable (owned by UID $owner_uid, running as UID $(id -u)).

Fix (pick one):
  Host:   sudo chown -R 1000:1000 ~/.nanobot
  Docker: docker run --user \$(id -u):\$(id -g) ...
  Podman: podman run --userns=keep-id ...
EOF
    exit 1
fi
exec nanobot "$@"
