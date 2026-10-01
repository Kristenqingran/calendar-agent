# Traceability Matrix

> **状态：HISTORICAL V1 TRACEABILITY / SUPERSEDED。** 本矩阵跟踪冻结的 Protocol V1 与迁移前实现。当前 V2 的实现状态以 [`../protocol-v2.md`](../protocol-v2.md)、V2 schemas 和自动化测试为准。

**Audit date:** 2026-09-30
**Scope:** Canonical Protocol v1 and current repository implementation.
**Evidence labels:** `CODE` = direct source inspection; `TEST` = automated test evidence; `DB` = read-only local SQLite aggregate; `USER E2E` = user-reported real-device observation, not independently reproduced in this audit.

## End-to-end requirements

| Requirement | Specification source | Implementation location / behavior | Evidence | Alignment |
|---|---|---|---|---|
| Correlate inbound request, conversation, task, step, and operation | `docs/protocol-v1.md`; request/tool schemas | Runtime creates IDs and persists task/step/tool exchange; dispatcher validates selected result correlation | CODE, TEST | Partial: ToolResult ingress is not exposed through HTTP, and Runtime does not validate every inbound ToolResult field against the stored exchange. |
| Distinguish UserRequest, ClarificationResponse, ToolResult and response variants | `docs/protocol-v1.md`; message schemas | Server accepts only `user_request` JSON; Runtime handles UserRequest and ToolResult; ClarificationResponse reaches unsupported-message handling | CODE, TEST | Fail for clarification continuation over current HTTP boundary. |
| Preserve a paused task and resume it on clarification | Protocol clarification and state requirements | Clarification sets the task to `waiting_clarification`, but no clarification record/current step is persisted; a later UserRequest creates a new task | CODE, DB, direct runtime probe | Fail; no implemented resume path. |
| Semantic analysis is provider-backed or explicitly identified | Protocol LLMAnalysis contract; role/system-prompt docs | `server.build_runtime` injects deterministic `DemoLLM`; no production LLM provider/SDK is configured; system-prompt document is not wired into runtime construction | CODE, TEST | Partial / documentation mismatch: current HTTP service is not using real model-based semantic analysis. |
| Clarify genuinely missing or ambiguous required values | Protocol parameter status/clarification rules | Demo parser extracts a limited bilingual subset; Planner/CalendarWorkflow return clarification for missing fields | CODE, TEST, user-reported E2E | Partial: deterministic parser coverage exists, but full language understanding is not provided. |
| Enforce a pre-execution safety/conflict/duplicate gate | Protocol task/state/operation rules and workflow docs | Runtime advances from planning to waiting-for-tool; no `pre_execution_check` state or conflict/duplicate preflight is executed | CODE, TEST | Fail / missing. |
| Build a valid Calendar Create ToolRequest | ToolRequest schema; protocol field contracts | CalendarWorkflow builds timed create requests; Mac host creates via EventKit | CODE, TEST, USER E2E | Partial: timed path is represented; all-day fields do not survive the Swift HostArguments boundary. |
| Keep client access separate from Agent Core | Product architecture docs | HTTP server owns transport/auth parsing; Runtime and Planner receive protocol messages; configured Mac host adapter dispatches locally | CODE, TEST | Mostly aligned, with protocol/deployment docs still naming an older client-executes-tool model. |
| Execute create through the declared adapter boundary | ToolRequest / ToolResult contracts | ToolDispatcher maps create/query to MacAgentHostAdapter by default; Swift Host registers CalendarCapability and uses EventKit | CODE, TEST, USER E2E | Implemented for local Calendar Create, subject to qualifications in the alignment report. |
| Return a contract-valid ToolResult with correct correlation | ToolResult schema and protocol correlation rules | Swift Host serializes tool result; Python dispatcher validates result shape/correlation | CODE, TEST | Partial: adapter and dispatcher check selected fields, but Runtime ToolResult ingress does not fully bind result to exchange. |
| Verify real Calendar state after write | Protocol `verify_state` requirements | VerificationService queries calendar and compares ID/title/start/end before Final.success | CODE, TEST, USER E2E | Implemented for observed timed create path; unknown create result currently exits as unknown without a verification lookup. |
| Do not infer success from adapter success alone | Protocol Final semantics | Create success proceeds to verification; only matching query yields success | CODE, TEST, USER E2E | Aligned on the success path. |
| Handle operation replay without duplicate side effects | Protocol operation/idempotency rules | OperationRepository records/checks operation key and argument hash; Runtime continues to dispatch after create-or-replay rather than returning a stored result | CODE, TEST | Partial / high risk: persistence primitive exists, end-to-end replay suppression is not established. |
| Persist task, step, operation, clarification, and transition state | Protocol persistence/state requirements | SQLAlchemy repositories/models exist; runtime persists task, step, exchange, operation and transitions, but does not persist clarification or current step pointer | CODE, DB, TEST | Partial. Local DB aggregate: 47 tasks, all 47 with null current_step_id; zero clarification and inbound receipt rows. |
| Protect HTTP entry point and remote exposure | Current client-access doc and server config | Host/port configurable; non-loopback requires API token; loopback permits unauthenticated access if no token configured; tunnel scripts target loopback | CODE, TEST | Partial: deployment relies on correct local secret configuration; no fail-closed requirement for a loopback origin behind a tunnel. |
| Preserve client timezone context | Protocol datetime requirements; client access doc | HTTP accepts optional `assistant_timezone`, defaults to Asia/Shanghai; no distinct device/client timezone field | CODE, TEST, user-reported E2E | Partial; client and Mac timezone distinction is not represented. |
| Support Reminder CRUD in V1 | Canonical protocol and schemas enumerate Reminder operations | Tool contracts include Reminder tools; Planner has a constrained Reminder-create helper; dispatcher/CalendarCapability do not execute Reminder | CODE, TEST | Fail / protocol-to-implementation gap. |
| Provide truthful user-facing result content | Protocol Final/result semantics | Runtime emits generic localized Final text; Calendar Query Final does not include returned event data | CODE, TEST | Partial: status is available, result summary is thin. |

## Evidence interpretation

- `USER E2E` denotes earlier user-reported tests, including timed Calendar Create followed by verification. It does not establish that every current code revision or deployment has the same result.
- The 300-pass/one-failure full pytest result is repository automation evidence only. It does not prove live Cloudflare, iPhone Shortcut, Siri, EventKit permission, or Calendar behavior.
- `DB` figures are a local aggregate snapshot taken during this audit; they contain no claim about all environments or historical retention.
- The known `inbound-naive-datetime` JSON Schema/Pydantic parity failure is independent of the above runtime gaps and remains unfixed.
