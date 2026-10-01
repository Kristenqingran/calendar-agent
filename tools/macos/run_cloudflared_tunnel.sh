#!/bin/zsh
set -euo pipefail

# Runs an already-authorized, named Cloudflare Tunnel. The tunnel's ingress
# must point to the local Agent API (http://127.0.0.1:8000).
if [[ -n "${CLOUDFLARED_BIN:-}" ]]; then
  cloudflared_bin="$CLOUDFLARED_BIN"
else
  cloudflared_bin=""
  for candidate in /opt/homebrew/bin/cloudflared /usr/local/bin/cloudflared /usr/bin/cloudflared; do
    if [[ -x "$candidate" ]]; then
      cloudflared_bin="$candidate"
      break
    fi
  done
fi
CLOUDFLARED_CONFIG="${CLOUDFLARED_CONFIG:-$HOME/.cloudflared/config.yml}"
CLOUDFLARED_TOKEN_FILE="${CLOUDFLARED_TOKEN_FILE:-$HOME/.config/calendar-agent/cloudflared-token}"
CLOUDFLARED_TUNNEL_NAME="${CLOUDFLARED_TUNNEL_NAME:-calendar-agent}"

if [[ -z "$cloudflared_bin" ]]; then
  print -u2 "cloudflared is not installed or CLOUDFLARED_BIN is invalid."
  exit 1
fi
if [[ -r "$CLOUDFLARED_CONFIG" ]]; then
  if [[ "$CLOUDFLARED_CONFIG" != "$HOME"/* ]]; then
    print -u2 "Cloudflare Tunnel config must be under the user's home directory."
    exit 1
  fi
  if [[ "$(stat -f '%Lp' "$CLOUDFLARED_CONFIG")" != "600" && "$(stat -f '%Lp' "$CLOUDFLARED_CONFIG")" != "640" ]]; then
    print -u2 "Cloudflare Tunnel config must have mode 600 or 640."
    exit 1
  fi
  exec "$cloudflared_bin" tunnel run --config "$CLOUDFLARED_CONFIG" "$CLOUDFLARED_TUNNEL_NAME"
fi

if [[ -r "$CLOUDFLARED_TOKEN_FILE" ]]; then
  if [[ "$CLOUDFLARED_TOKEN_FILE" != "$HOME"/* ]]; then
    print -u2 "Cloudflare Tunnel token file must be under the user's home directory."
    exit 1
  fi
  if [[ "$(stat -f '%Lp' "$CLOUDFLARED_TOKEN_FILE")" != "600" && "$(stat -f '%Lp' "$CLOUDFLARED_TOKEN_FILE")" != "640" ]]; then
    print -u2 "Cloudflare Tunnel token file must have mode 600 or 640."
    exit 1
  fi
  exec "$cloudflared_bin" tunnel run --token-file "$CLOUDFLARED_TOKEN_FILE"
fi

print -u2 "Cloudflare Tunnel config or token file is missing."
exit 1
