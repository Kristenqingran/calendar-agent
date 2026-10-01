#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
APP="$ROOT/mac_gateway/MacAgentHost.app"
CACHE_DIR="${TMPDIR:-/tmp}/calendar-agent-modulecache"
mkdir -p "$APP/Contents/MacOS" "$CACHE_DIR"
swiftc -module-cache-path "$CACHE_DIR" -framework EventKit \
  "$ROOT/mac_gateway/mac_agent_host.swift" \
  -o "$APP/Contents/MacOS/mac_agent_host"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"
echo "Built and signed $APP"
