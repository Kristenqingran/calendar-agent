#!/bin/zsh
set -euo pipefail

PROJECT_DIR="${CALENDAR_AGENT_PROJECT_DIR:-$HOME/Agents_project/calendar-agent}"
CONFIG_FILE="${CALENDAR_AGENT_CONFIG_FILE:-$HOME/.config/calendar-agent/server.env}"

if [[ ! -d "$PROJECT_DIR" ]]; then
  print -u2 "Calendar Agent project directory does not exist."
  exit 1
fi
if [[ ! -r "$CONFIG_FILE" ]]; then
  print -u2 "Missing readable configuration: $CONFIG_FILE"
  exit 1
fi

umask 077
set -a
source "$CONFIG_FILE"
set +a

cd "$PROJECT_DIR"
exec "$PROJECT_DIR/.venv/bin/python" -m calendar_agent_protocol.server
