# Architecture Drift and Gaps

> **状态：HISTORICAL AUDIT / SUPERSEDED。** 本审计形成于 Protocol V1 仍被视为 canonical 的阶段。Protocol V2 与 ADR-001 已采纳 Mac-first 执行边界；本文关于 V1 与实现冲突的结论仅保留为迁移前证据，不代表当前规范冲突。当前依据：[`../protocol-v2.md`](../protocol-v2.md)。

**Audit date:** 2026-09-30
**Purpose:** Identify material differences between canonical specifications, product/role documentation, implemented code, tests, and observed operation. This is an audit report only; it does not authorize or make implementation changes.

## Material architecture drift

### 1. Protocol execution owner versus Mac-first execution host — P0

`docs/protocol-v1.md` says the client (currently an iPhone Shortcut) performs real Calendar/Reminder I/O and reports a ToolResult; the Agent backend has no Calendar/Reminder permission. The implemented local path instead dispatches to `MacAgentHostAdapter`, whose separate AppKit process invokes EventKit. These models assign execution ownership to different components. The Mac-first implementation is supported by current architecture documentation and user-reported E2E, but the canonical protocol remains the higher-priority source and is not aligned.

### 2. Clarification pause/resume — P0

The protocol defines a clarification response that resumes the same task with preserved state. The current HTTP request accepts only a new natural-language UserRequest. Runtime does not implement ClarificationResponse handling; it creates a fresh task for a subsequent UserRequest. It stores neither a clarification row nor a current step pointer for resume. A real Siri/Shortcut multi-turn exchange therefore cannot be assumed to continue the original task.

### 3. Idempotency and duplicate side-effect boundary — P0

Operation persistence and argument-hash checks exist, but Runtime does not use the replay outcome to return a saved result without dispatch. A repeated request with the same operation may reach the adapter again. This conflicts with the protocol’s operation/idempotency intent and is especially significant for Calendar writes.

### 4. Inbound ToolResult correlation — P0

Dispatcher validates adapter output, but Runtime receives ToolResult via a separate path and finds the exchange by step id. It does not validate the complete tuple (request/conversation/task/step/operation/tool/status and expected state) against persisted exchange before applying the result. There is currently no public ToolResult HTTP endpoint, so the production ingress contract is also incomplete.

### 5. Canonical supported scope versus executable scope — P1

Canonical protocol/schema enumerate Calendar and Reminder create/query/update/delete. The active dispatcher and Mac host execute Calendar event create/query only. A constrained Reminder helper is present in Planner but has no matching end-to-end adapter. The distinction between “wire contract exists” and “product capability implemented” is not made consistently in the role/workflow documentation.

### 6. Production semantic analysis versus deterministic demo — P1

The server currently constructs `DemoLLM`, a deterministic rule/regex parser. It is useful for offline/demo behavior but does not provide general semantic understanding. No real LLM provider is present in the runtime wiring. Some product/QA language describes semantic analysis more broadly than the active implementation supports.

### 7. Missing explicit pre-execution gate — P1

Protocol/workflow requirements describe a pre-execution check before a side effect. The current state machine path proceeds from planning to waiting for tool result without conflict/duplicate/calendar-selection checks as a distinct gate. Verification after create does not replace pre-execution validation.

### 8. Unknown outcome handling — P1

Verification works after a successful create ToolResult. When create returns `unknown`, Runtime returns Final.unknown immediately instead of querying by operation/event identity to resolve whether the write happened. Retry suppression is desirable, but the required read-only recovery check is not implemented.

### 9. Datetime and client-zone semantics — P1

HTTP accepts `assistant_timezone`, defaults it to `Asia/Shanghai`, and has no separate client/device timezone. This does not represent a user traveling while the Mac remains at home. Earlier reported +6-hour behavior was tracked separately; the current contract still cannot express client-local zone independently from assistant zone.

### 10. Timed versus all-day capability boundary — P1

CalendarWorkflow has an all-day parameter path, but the Swift HostArguments/EventKit host boundary supports timed start/end only. This is an implementation gap and should not be represented as end-to-end all-day support.

### 11. HTTP response and client continuation protocol — P1

`POST /agent` accepts a simplified envelope with `user_request`, optional `conversation_id`, and optional `assistant_timezone`; it does not accept a canonical inbound message discriminant or a clarification-response payload. The current API therefore provides a useful entry point, but not the complete multi-message protocol transport.

### 12. Tool query result presentation — P2

Calendar Query can produce a Final response, but the current user-facing message is generic and does not summarize the returned events. Contract execution and useful client presentation are not equivalent.

## Documentation drift

- `docs/protocol-v1.md` is canonical but describes the earlier client-side tool-execution trust boundary.
- `docs/01-岗位卡.md`, `docs/02-工作流卡片.md`, `docs/02-工作流程.md`, and `docs/03-流程图.md` retain the older Shortcut-executes-Calendar model and do not consistently label it as superseded.
- The current Mac-first client-access architecture note describes the newer local EventKit host and remote tunnel boundary, but explicitly notes that clarification continuation transport remains incomplete.
- `docs/runtime-contract-v1.md` describes an earlier phase that excluded Runtime/HTTP/LLM; implementation now contains all three.
- The older QA matrix and runtime/tool-loop planning documents contain historical status statements that no longer describe the current code.
- The Cloud/CalDAV research documents have prominent historical/deprecated banners, but their internal historical recommendations remain. They should be read as research records, not current implementation direction.
- `mac_gateway/README.md` includes older app naming and future WebSocket language; it is not evidence that WebSocket is implemented or part of current V1.

## Risk ordering

| Priority | Gap | Why it matters |
|---|---|---|
| P0 | Protocol and implementation disagree on who executes tools | Security/trust boundary and client/server responsibilities are ambiguous. |
| P0 | Clarification cannot resume the same task | Common Siri interaction stops before a complete intent can execute. |
| P0 | Operation replay can dispatch again | Duplicate Calendar side effects may occur. |
| P0 | ToolResult ingress correlation is incomplete | Untrusted/stale/misrouted results may be applied to persisted task state. |
| P1 | DemoLLM is the only configured analysis adapter | Real-world language coverage is bounded and brittle. |
| P1 | Pre-execution checks and unknown recovery are absent | Conflict and ambiguous-write safeguards are incomplete. |
| P1 | Client timezone/all-day transport gaps | Correct semantics cannot be guaranteed across travel and all-day events. |
| P1 | Reminder contract is broader than execution support | Clients may request operations the current host cannot execute. |
| P2 | Query Final omits useful event summary | Client can receive a success status without actionable details. |

## Audit boundary and non-actions

This report records findings; it does not reconcile canonical protocol, alter production implementation, update role cards, change Shortcut/Cloudflare/VPN settings, access secrets, create Calendar events, or deploy anything. The known naive-datetime JSON Schema/Pydantic parity failure remains outside this audit’s corrective scope.
