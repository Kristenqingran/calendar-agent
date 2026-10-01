# iCloud / CalDAV Feasibility PoC

## Document Status

**Status: DEPRECATED / HISTORICAL RESEARCH**

本文记录旧的 VPS / Cloud Calendar / iCloud CalDAV 可行性研究。该架构已经被
当前的 Mac-first Personal Agent 架构取代。

本文仅用于保留历史技术调研、失败/阻塞证据和 architecture pivot 背景，
不得作为当前 V1 实现要求或 Codex 当前开发路径依据。

Current architecture:

`Mac-first Personal Agent → MacAgentHost → Capability → macOS native API`

当前已经真实验证的执行边界：

`MacAgentHost.app → CapabilityRegistry → CalendarCapability → EventKitAdapter → macOS Calendar → EventKit Verification → ToolResult.success`

VPS、WebSocket、Cloud Agent、ProductionCalendarAdapter 和 CalDAV 不属于当前
Calendar V1 的实现前置条件。本文中的 CalDAV/VPS 结论全部属于历史研究，
不代表当前系统正在采用该路径。


















#已经废弃不用的

## 1. Environment (Historical PoC Record)

**Status: FAILED for this run**

The requested test must run from the VPS, but the current execution environment is:

```text
hostname: WangdeMacBook-Air.local
OS: Darwin 25.6.0 arm64
Python: 3.12.8
```

This is the development Mac, not the Remote VPS. No Mac-independent VPS conclusion can be drawn from this run.

Observed environment checks:

```text
DNS lookup: failed with Operation not permitted
HTTPS to https://www.icloud.com/: failed because host could not be resolved
```

These failures are execution-environment restrictions, not evidence that iCloud CalDAV is unavailable.

No system network configuration, VPN, firewall, SSH, or VPS service was modified.

## 2. Authentication (Historical / Deprecated Path)

**Status: NOT TESTED**

No Apple Account credential, app-specific password, token, or environment variable was requested or provided. No secret was written to the repository or process configuration.

The feasibility run must stop before authentication when it is not running on the VPS and safe credentials are unavailable.

## 3. Principal Discovery (Historical / Deprecated Path)

**Status: NOT TESTED**

No CalDAV request was sent. Principal URL, HTTP status, authentication challenge, and response body were not observed.

## 4. Calendar Discovery (Historical / Deprecated Path)

**Status: NOT TESTED**

No `calendar-home-set`, calendar collection, display name, supported component, or writable calendar was discovered.

## 5. Create (Historical / Deprecated Path)

**Status: NOT TESTED**

No test event was created. No UID, resource URL, ETag, provider identifier, or HTTP response was obtained.

## 6. Query (Historical / Deprecated Path)

**Status: NOT TESTED**

No CalDAV `REPORT`/calendar query was sent.

## 7. Verification (Historical / Deprecated Path)

**Status: NOT TESTED**

There is no observed Create → Query → field comparison result. The current repository's VerificationService was not connected to this PoC, as required.

## 8. Delete (Historical / Deprecated Path)

**Status: NOT TESTED**

No test event existed from this run, so no delete request was sent.

## 9. Idempotency (Historical / Deprecated Path)

**Status: NOT TESTED**

No duplicate create was attempted. CalDAV/iCloud idempotency must not be assumed from RFC behavior alone; the PoC must record whether the same UID and operation key produce one resource or multiple resources.

## 10. Unknown Recovery (Historical / Deprecated Path)

**Status: NOT TESTED**

No create timeout or response-drop simulation was run. The required experiment remains:

```text
Create request
→ discard client response
→ do not retry create
→ query by stable UID / resource URL / exact fields
```

## 11. Mac Independence (Historical / Deprecated Path)

**Status: NOT VERIFIED**

This run was performed on a Mac and did not reach iCloud. It therefore cannot prove that Mac can be powered off. A valid result requires the same PoC to run from the VPS while the Mac is unavailable or powered off.

## 12. Failures

The run stopped before credentials by design:

1. The current host is `WangdeMacBook-Air.local`, not the VPS.
2. DNS calls failed with `Operation not permitted`.
3. HTTPS could not resolve `www.icloud.com`.
4. The virtual environment does not contain `caldav`, `requests`, `httpx`, `lxml`, or `icalendar`.

No dependency was installed because the requested environment was not the VPS and the user prohibited unrelated system changes. No credential was requested.

## 13. Limitations

This document records an environment-blocked feasibility attempt, not a CalDAV success or failure.

The following remain unknown:

- iCloud CalDAV endpoint and principal discovery for the target account;
- authentication method accepted by the target account;
- writable calendar selection;
- UID/resource URL/ETag behavior;
- time-range and all-day query behavior;
- duplicate UID behavior;
- response-timeout recovery;
- long-running VPS credential viability.

## 14. Production Implications (Historical / Deprecated)

No Production Calendar Adapter should be implemented or selected based on this run. The next valid run must use the VPS and must keep the Mac, macOS Calendar, EventKit, AppleScript, `osascript`, Apple Shortcut, and Mac Bridge out of the request path.

The intended future boundary remains:

```text
CalendarWorkflow
  → ToolDispatcher
  → ProductionCalendarAdapter
  → iCloud/CalDAV
  → ToolResult
  → VerificationService
```

The existing LocalCalendarAdapter/MacCalendarBridge remain local QA implementations only.

## 15. Conclusion (Historical Conclusion)

1. VPS can directly access iCloud Calendar: **NOT VERIFIED**.
2. Mac can remain completely offline: **NOT VERIFIED**.
3. Authentication can run long-term: **NOT VERIFIED**.
4. Create: **NOT TESTED**.
5. Query: **NOT TESTED**.
6. Verification: **NOT TESTED**.
7. Delete: **NOT TESTED**.
8. Same operation producing duplicates: **NOT TESTED**.
9. Create response timeout recovery: **NOT TESTED**.
10. CalDAV is ready for Production Adapter implementation: **NO — feasibility is not yet verified**.

Required next step: run an isolated PoC from the actual VPS with credentials supplied only through an interactive prompt or an untracked environment/configuration mechanism. Do not copy credentials into this repository.
