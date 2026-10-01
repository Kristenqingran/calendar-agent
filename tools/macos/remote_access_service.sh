#!/bin/zsh
set -euo pipefail

LABEL="com.calendaragent.cloudflared"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PROJECT_DIR="${CALENDAR_AGENT_PROJECT_DIR:-$HOME/Agents_project/calendar-agent}"
TEMPLATE="$PROJECT_DIR/mac_gateway/launchd/$LABEL.plist.template"

case "${1:-}" in
  install)
    [[ -r "$TEMPLATE" ]] || { print -u2 "Missing LaunchAgent template: $TEMPLATE"; exit 1; }
    mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs/calendar-agent"
    sed -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" -e "s|__HOME__|$HOME|g" \
      "$TEMPLATE" > "$PLIST"
    chmod 600 "$PLIST"
    launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST"
    ;;
  start) launchctl kickstart "gui/$(id -u)/$LABEL" ;;
  stop) launchctl kill SIGTERM "gui/$(id -u)/$LABEL" ;;
  restart) launchctl kickstart -k "gui/$(id -u)/$LABEL" ;;
  status) launchctl print "gui/$(id -u)/$LABEL" ;;
  uninstall)
    launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
    mv "$PLIST" "/tmp/$LABEL.plist.removed" 2>/dev/null || true
    ;;
  *) print -u2 "Usage: $0 {install|start|stop|restart|status|uninstall}"; exit 2 ;;
esac
