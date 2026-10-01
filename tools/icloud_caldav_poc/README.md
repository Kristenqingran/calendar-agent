# iCloud CalDAV Feasibility PoC

This directory is intentionally separate from `src/calendar_agent_protocol` and is not production code.

The PoC must be run from the actual VPS. It must receive credentials interactively or through an untracked environment/configuration mechanism. It must not use the Mac, EventKit, AppleScript, `osascript`, Shortcut, or Mac Bridge.

The first run in this workspace was stopped before credentials because the current host was the development Mac and its network access was sandbox-restricted. See [`docs/architecture/icloud-caldav-poc.md`](../../docs/architecture/icloud-caldav-poc.md).
