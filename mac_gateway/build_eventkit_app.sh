#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
APP="$ROOT/mac_gateway/CalendarAgentEventKit.app"
CACHE_DIR="${TMPDIR:-/tmp}/calendar-agent-modulecache"

mkdir -p "$APP/Contents/MacOS" "$CACHE_DIR"
swiftc \
  -module-cache-path "$CACHE_DIR" \
  -framework EventKit \
  "$ROOT/mac_gateway/eventkit_executor.swift" \
  -o "$APP/Contents/MacOS/eventkit_executor"

echo "Built $APP"
