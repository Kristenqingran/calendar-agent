#!/bin/zsh
set -euo pipefail

LABEL="com.calendaragent.agent-server"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
TEMPLATE="${CALENDAR_AGENT_PROJECT_DIR:-$HOME/Agents_project/calendar-agent}/mac_gateway/launchd/$LABEL.plist.template"
PROJECT_DIR="${CALENDAR_AGENT_PROJECT_DIR:-$HOME/Agents_project/calendar-agent}"
CONFIG_FILE="${CALENDAR_AGENT_CONFIG_FILE:-$HOME/.config/calendar-agent/server.env}"

case "${1:-}" in
  install)
    if [[ ! -r "$CONFIG_FILE" ]]; then
      print -u2 "Missing readable configuration: $CONFIG_FILE"
      print -u2 "Create it from tools/macos/server.env.example before installing the service."
      exit 1
    fi
    mkdir -p "$HOME/Library/LaunchAgents"
    mkdir -p "$HOME/Library/Logs/calendar-agent"
    temp_plist="$PLIST.tmp.$$"
    trap 'rm -f "$temp_plist"' EXIT
    sed -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
        -e "s|__HOME__|$HOME|g" "$TEMPLATE" > "$temp_plist"
    chmod 600 "$temp_plist"
    mv "$temp_plist" "$PLIST"
    trap - EXIT
    launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST"
    ;;
  start)
    launchctl kickstart "gui/$(id -u)/$LABEL"
    ;;
  stop)
    launchctl kill SIGTERM "gui/$(id -u)/$LABEL"
    ;;
  restart)
    launchctl kickstart -k "gui/$(id -u)/$LABEL"
    ;;
  status)
    launchctl print "gui/$(id -u)/$LABEL"
    ;;
  uninstall)
    launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    ;;
  *)
    print -u2 "Usage: $0 {install|start|stop|restart|status|uninstall}"
    exit 2
    ;;
esac
