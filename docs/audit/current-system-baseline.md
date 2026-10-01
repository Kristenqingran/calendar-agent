# Current System Baseline — Calendar Agent

> **状态：HISTORICAL SNAPSHOT / SUPERSEDED。** 本文记录 2026-09-30 的 V1 对齐基线；后续 Protocol V2 migration 已将 Mac-first 架构设为当前规范。本文中的 current/baseline 仅表示审计当时，不表示今天的规范状态。当前依据：[`../protocol-v2.md`](../protocol-v2.md)。

Audit date: 2026-09-30 (Asia/Shanghai). Read-only snapshot of the inspected checkout; not a claim that every remote or real-device path passed today.

## Evidence convention

- A — real-device behavior previously reported by the user; no correlated packet/server trace is retained in the repository.
- B — multi-component integration test, generally with a deterministic adapter.
- C — isolated unit/contract/repository test.
- D — source/configuration inspection, not a runtime test.
- E — specification only; implementation/test not found.

## Actual architecture

    iPhone / Siri / Shortcut                         [client outside repo; partial evidence, A/D]
            ↓ HTTPS, Bearer token when configured
    Cloudflare Named Tunnel → 127.0.0.1:8000          [scripts/docs; user previously reported route working, A/D]
            ↓
    HTTP POST /agent                                  [implemented; custom transport envelope, D]
            ↓
    AgentRuntime                                      [new UserRequest + ToolResult; no clarification resume, D]
            ↓
    DemoLLM                                           [deterministic bilingual rule/regex parser, currently wired, D/C]
            ↓
    Planner → CalendarWorkflow                       [Calendar create/query planning, partial, D/C]
            ↓
    SQLite repositories / state transitions          [task/step/exchange/operation; partial recovery, D/C]
            ↓
    ToolDispatcher → MacAgentHostAdapter              [create_calendar_event/query_calendar, D/C]
            ↓ JSON-lines subprocess
    MacAgentHost.app → CapabilityRegistry             [AppKit host, CalendarCapability, D/A]
            ↓
    EventKit → macOS Calendar                         [real create/query previously reported verified, A]
            ↓
    VerificationService: query verify_state + compare event_id/title/start/end [create path, B/A]
            ↓
    Final.success / failure / unknown                 [supported create path; partial overall V1, B/A]

## Component status

| Layer | Status | Evidence / limit |
|---|---|---|
| Siri / Shortcut | Partial | No Shortcut export/source in repo. User reported clarification/follow-up issues and Siri treating a follow-up as timer/countdown. Actual action branches cannot be source-audited. |
| Remote access | Current / externally configured | tools/macos scripts and LaunchAgent templates route Cloudflare Tunnel to loopback. At audit time a Python process listened on 127.0.0.1:8000 (PID 1293). This audit did not re-probe Cloudflare or send a public request. |
| HTTP | Implemented, transport-specific | server.py accepts user_request and optional conversation_id / assistant_timezone, then constructs canonical UserRequest. No clarification_response or caller request_id support. |
| Runtime / state | Partial | UserRequest analysis and ToolResult paths exist. Every UserRequest creates a new Task. ClarificationResponse returns runtime_path_not_implemented. |
| Semantic analysis | Demo only | HTTP wiring instantiates DemoLLM; deterministic regex/date helpers, no production provider. Tests cover a subset of Chinese and English. |
| Planner / Workflow | Partial | Calendar create/query planning exists. Unsupported intents fail. Reminder-create helper requires context normal Runtime does not supply. |
| Persistence | Partial | Models/repos for conversation, task, parameters, steps, exchanges, operations, clarifications, transitions, receipts. Runtime does not use clarification or inbound-receipt repositories. |
| Tool execution | Partial, real local path | Dispatcher maps create/query to MacAgentHostAdapter; native host registers Calendar create/query only. |
| Verification | Implemented for successful Calendar Create only | Runtime sends query_calendar purpose=verify_state and compares event ID when present, title, start, end. Unknown writes do not first run recovery verification. |
| Historical adapters | Present, not default | LocalCalendarAdapter, AppleShortcutToolAdapter, MacShortcutBridge remain. build_runtime defaults to MacAgentHostAdapter. |
| VPS / CalDAV | Deprecated / historical | Research docs have deprecated banners; no production VPS/CalDAV adapter is wired. |

## HTTP, security, and service boundary

- Default bind 127.0.0.1:8000; configurable with AGENT_SERVER_HOST / AGENT_SERVER_PORT.
- Non-loopback bind requires AGENT_API_TOKEN. Configured tokens use Bearer auth and constant-time comparison. Loopback with no token disables auth. A tunnel terminating to loopback therefore relies on deployed environment actually setting the token; code does not infer public tunnel exposure.
- POST /agent only, JSON checks, 64 KiB request limit, generic 500 on Runtime exception.
- HTTP defaults assistant_timezone to Asia/Shanghai, generates request_id internally, and does not forward device_timezone/default_calendar.
- Server access logging is suppressed. This avoids ordinary request logging but leaves no HTTP-level trace proving a past Siri request reached Runtime.
- server.main uses relative sqlite:///calendar-agent.db and Base.metadata.create_all; LaunchAgent script changes to project directory first. Alembic files exist but startup does not run migrations.

## Persistence observed (read-only aggregate)

Tables: conversations, tasks, task_parameters, task_steps, tool_exchanges, operations, clarifications, state_transitions, inbound_receipts.

At audit time local DB had 47 tasks: 40 waiting_clarification, 6 failed, 1 succeeded; zero clarification rows; zero inbound-receipt rows; all 47 task.current_step_id values were null. This aggregate does not identify/prove any specific Siri request. No request text or credentials were queried.

Task parameters, tool request/result payloads, operations, and transitions are persisted. Task final status is persisted; there is no final-response table. Clarification model/repository exist but Runtime does not populate them.

## Real versus automated evidence

- A, user-reported: real MacAgentHost EventKit create and follow-up verification previously passed. No Calendar event was created or changed during this audit.
- A, user-reported failures: Siri/Shortcut has produced clarification, timer/countdown interpretation, and Calendar-service invalid-response message. No correlated Shortcut export/server trace is in repo.
- B: tests/test_runtime_tool_loop.py and tests/test_server.py exercise create → query verification → Final with MockToolAdapter/local test server.
- C: Mac host tests primarily mock process behavior or inspect source; they do not prove live Xcode/TCC/EventKit/iPhone behavior.
- Audit test run: 300 passed, 1 failed. Sole failure is the known inbound-naive-datetime Schema/Pydantic parity defect.

## Bottom line

The checkout has a real Mac-first Calendar Create + verification slice, deterministic bilingual DemoLLM, and configurable HTTP boundary. It is not Protocol V1 complete: clarification continuation, pre-write safety, unknown-write recovery, most Calendar/Reminder tools, canonical Mac-first documentation alignment, and production semantic analysis are incomplete.
