# Mac-first Protocol Reconciliation Proposal

> **状态：HISTORICAL PROPOSAL / SUPERSEDED。** 本提案在 V2 决策前记录候选调和方案；现已由 [`../protocol-v2.md`](../protocol-v2.md) 和 [`../architecture/adr/ADR-001-mac-first-tool-execution.md`](../architecture/adr/ADR-001-mac-first-tool-execution.md) 取代。文内“未批准 / V1 仍为 canonical”等判断只描述提案撰写时的状态，不是当前状态。

**Status:** Audit proposal; non-canonical and not approved as a Protocol change.
**Audit date:** 2026-09-30.
**Scope:** Reconcile the Frozen Protocol v1 tool-execution boundary with the current Mac-first implementation. No code, schema, protocol, role card, test, client, network, or service configuration is changed by this proposal.

## 1. Problem Statement

`docs/protocol-v1.md` is explicitly the sole canonical specification and is Frozen at version 1.0.0. It assigns real Calendar/Reminder I/O to a client-local Tool, says the Agent backend must not hold Calendar/Reminder access, and requires the client to execute Tool Requests and return Tool Results as new inbound HTTP requests.

The current server path is different: `server.build_runtime` wires `ToolDispatcher` to `MacAgentHostAdapter`; that adapter invokes the local AppKit process; `CalendarCapability` uses EventKit; and `AgentRuntime` runs verification before returning the HTTP response. This is the adopted Mac-first product direction and is supported by prior user-reported real Calendar Create plus verification. Therefore the architecture decision and running implementation are Mac-first, but the canonical Protocol still specifies the superseded client-executes-Tool boundary.

The mismatch is not merely terminology. It changes the trust boundary, public HTTP response types, who can access Calendar, what a Tool Result means, request-ID lifecycle, idempotency ownership, and which tests assert conformance. Until the canonical document is reconciled, a conforming implementation cannot simultaneously follow both models.

## 2. Historical Architecture

The Protocol v1 historical execution path is:

```text
User Client → Agent API → Agent → Tool Request → User Client Tool
            → Calendar/Reminders → Tool Result as new HTTP request
            → Agent → verification/recovery → clarification/final
```

In that model, “client” means both the user-facing interaction endpoint and the local execution agent. The client receives a Tool Request, interprets no natural language, performs native Calendar/Reminder I/O, prevents duplicate writes, and returns a Tool Result. The backend is intentionally denied Calendar access.

This remains useful historical architecture and should be retained in an ADR/evolution record. It should not remain the normative V1 behavior after a formally approved pivot.

## 3. Current Implementation Architecture

The checked-in Python path is:

```text
iPhone/Shortcut → HTTPS → Agent HTTP API → AgentRuntime
 → DemoLLM → Planner/CalendarWorkflow → ToolDispatcher
 → MacAgentHostAdapter → MacAgentHost.app
 → CapabilityRegistry → CalendarCapability → EventKit
 → ToolResult → AgentRuntime/VerificationService → Final → HTTP response
```

Evidence from code inspection:

- `server.build_runtime` constructs `DemoLLM` and, by default, maps Calendar Create and Query to `MacAgentHostAdapter`.
- `AgentRuntime.handle` dispatches a planned Tool Request synchronously when a dispatcher is present, receives the returned Tool Result in-process, and runs verification before returning a Final.
- `mac_host.py` starts the app executable with JSON-lines stdin/stdout; it does not connect to an already-running process.
- `mac_gateway/mac_agent_host.swift` creates an AppKit application lifecycle, registers `CalendarCapability`, and supports `create_calendar_event` and `query_calendar`.
- `CalendarCapability` calls EventKit through `EventKitAdapter`; Calendar Create and verification query therefore have their side effects/reads on the Mac host.
- Earlier user-reported real-device E2E says timed Calendar Create and verification succeeded. This audit did not replay that E2E and cannot establish present-day service or Shortcut state.
- There is no Shortcut export/source in the repository. Its precise actions cannot be independently inspected. The current HTTP integration and architecture documentation define it as a thin request/response client, not a Calendar executor.

Thus the implementation is Mac-first. The iPhone does not need to execute Calendar Tools on the current code path; MacAgentHost/EventKit does. The public HTTP route is synchronous for the tested Create path: Tool execution and verification finish before the HTTP response is constructed.

## 4. Target V1 Architecture

```text
User Client (iPhone / Watch / Siri / Shortcut)
   → Agent API (authentication, transport, inbound protocol validation)
   → Agent Core (Runtime, analysis, Planner, Workflow, persistence)
   → Tool Execution Layer (Dispatcher + adapter)
   → MacAgentHost (local trusted execution boundary)
   → CapabilityRegistry → CalendarCapability → EventKit
   → internal Tool Result → Runtime / VerificationService
   → Final → Agent API → User Client
```

The public user-facing API owns conversation turns, including clarification. Tool Request/Result remain first-class contracts, but are internal execution messages in this deployment. They are not a request for the iPhone Shortcut to perform Calendar I/O. A future remote executor may use an authenticated private execution transport, but that is separate from the user-facing API and is not part of this proposal’s current V1 path.

## 5. Responsibility Matrix

| Layer | Receives | Responsible for | Must NOT do | Outputs |
|---|---|---|---|---|
| User Client / Shortcut | User input and Agent API response | Collect input; retain conversation/task references needed for clarification; submit the next user turn; display/speak clarification or Final | Interpret Tool Request; call Calendar; create IDs owned by Agent; judge operation success | User-turn HTTP message; displayed/spoken Agent response |
| Agent HTTP API | Authenticated HTTP request | Authenticate, enforce transport limits, validate external envelope, construct/validate inbound message, preserve HTTP correlation, serialize response | Natural-language planning; Calendar access; operation retry policy | Validated inbound message to Runtime; HTTP Agent response |
| AgentRuntime | Inbound user-turn message; internal Tool Result | Orchestrate task lifecycle, persistence, Planner, dispatch, verification, Final; route clarification back into the same task | Direct Calendar I/O; let LLM declare final success | Internal Tool Request to execution layer or public Clarification/Final |
| LLM / Semantic Analyzer | User text plus time/context | Extract intent, parameters, ambiguity, evidence, language | Generate IDs/state; dispatch Tools; own safety gate, idempotency, or final truth | Contract-validated semantic analysis |
| Planner / Workflow | Analysis, task context, relevant persisted state | Select supported workflow; validate required values; produce a Tool Request, Clarification, or failure | Call EventKit/HTTP/host; persist by direct DB access; invent unsupported facts | One internal execution request or user-facing response |
| Persistence | Runtime commands and state changes | Durable conversation/task/step/operation/execution/clarification records and transactional state transitions | Execute external side effects or silently infer success | Stored state and deduplication/replay decisions |
| ToolDispatcher | Validated internal Tool Request | Select adapter, enforce one-dispatch boundary, validate returned Tool Result and correlations | Parse natural language; modify arguments; decide Final.success | Adapter invocation and validated internal Tool Result |
| MacAgentHostAdapter | Internal Tool Request | Bridge Python execution contract to the local Host process; bound timeout; clean up subprocess; validate envelope | Change intended arguments; generate logical operation ID; independently declare goal success | Host result or explicit failed/unknown result |
| MacAgentHost | Authenticated/controlled local execution request | Own local native capability process and execution boundary; apply host-side duplicate guard/reconciliation | Perform semantic planning; expose a public user API; claim verified task success | Capability result with execution correlation |
| CapabilityRegistry | Capability registrations and selected tool name | Resolve a supported Tool to its Capability | Plan user intent; persist Agent task state | Selected Capability or unsupported result |
| CalendarCapability | Validated Calendar Tool Request | Map operation to Calendar capability behavior | Decide user intent; modify Tool arguments; mark whole task successful | Calendar-level execution/query outcome |
| EventKit | Native Calendar operation | Perform actual macOS Calendar read/write and return native event state/identifier | Interpret Agent protocol or user intent | Native result/state |
| VerificationService | Original write request, execution result, verification query result | Determine whether observed Calendar state satisfies requested fields; classify success/failure/unknown | Create or alter the event; relax expected fields to manufacture a match | Verification decision consumed by Runtime |

## 6. Protocol Conflicts

The table groups conflicts by semantic requirement, not by keyword occurrence. “Current meaning” describes Frozen Protocol v1; “target meaning” is a proposal only.

| Protocol location / subject | Current Protocol Meaning | Current Implementation | Target Mac-first Meaning | Conflict? | Recommended Change |
|---|---|---|---|---|---|
| §1 V1 scope and §19 backend prohibition | Client-local Tool owns Calendar/Reminder I/O; Agent backend has no Calendar permission | Backend ToolDispatcher calls a separate local MacAgentHost process with EventKit access | MacAgentHost is the local execution authority; Agent backend coordinates but does not itself call EventKit | Yes, foundational | Replace execution-owner statements. Distinguish Agent backend orchestration from the separately permissioned local Host. |
| §4.8 / §7.3 inbound Tool Result | Tool Result is an inbound protocol/HTTP message | Result is returned synchronously from adapter to Runtime in-process; no public Tool Result endpoint | Tool Result is an internal execution-layer response in this deployment; only user turns cross the public API | Yes | Split external inbound-message contract from internal execution result contract. |
| §5 request_id lifecycle | A Tool Result is a new inbound request and gets a new HTTP request_id | Adapters/Swift generate a new `req_*` ID, but the result does not cross a new HTTP boundary | Each external HTTP turn has a request ID; Tool execution attempts have an execution ID. Internal result correlates to that execution rather than pretending to be a new client request | Yes | Reserve `request_id` for HTTP interaction messages; introduce `execution_id` (and optionally `causation_request_id`) internally. |
| §8.1 Tool Request | Agent returns Tool Request for the client to execute, field by field | Runtime keeps it internal and dispatches via ToolDispatcher/Mac host before replying | Tool Request is an internal command from Agent Core to Tool Execution Layer; it is not exposed as an action request to the Shortcut | Yes | Rename or explicitly define it as an internal `ToolExecutionRequest`; remove it from the public response union if the API never exposes it. |
| §11 query / §12 result validation | Agent requests a query from client Tool and validates returned client data | Dispatcher invokes Mac host query; Runtime validates/query-verifies internal result | Same validation rules, but the producer is the registered Capability/adapter and the result remains internal | Boundary conflict, semantic rules mostly reusable | Keep purpose/range/result sufficiency semantics; redefine producer/transport and validate host-result trust boundary. |
| §13 write safety gate | Agent code checks safety before emitting write request to client | Runtime has no distinct `pre_execution_check` stage; direct path can dispatch after planning | Runtime must complete code-owned preflight before handing a write to Mac host | Gap plus implicit boundary mismatch | Preserve requirements; make gate an explicit Runtime stage before Dispatcher. |
| §14 idempotency | Client stores recent results and prevents a repeated operation_id write; Agent generates ID | Repository records operation/hash, but Runtime does not use replay outcome to suppress dispatch; Host has no durable operation journal | Agent persistence owns logical operation state; Host provides a durable local duplicate guard/replay result; ambiguous writes are queried before another create | Yes | Move client idempotency obligation to Agent/Host, retain stable operation_id, specify duplicate and unknown recovery behavior. |
| §15 verification | Agent requires `verify_state`; execution result alone is insufficient; transport assumes client returns query | Runtime VerificationService dispatches query to Mac host and compares actual fields | Runtime/VerificationService owns decision; Capability supplies real state through internal result | Mostly aligned on semantics; boundary differs | Keep the success predicate; state that the query is internally dispatched to execution layer, not returned to User Client. |
| §16 retry/recovery/unknown | Client executes re-query/retry and returns each result; client must not repeat operation | Runtime finalizes unknown write directly without verify recovery; adapters execute synchronously | Runtime coordinates verify-before-retry; Host must deduplicate operation; never blind-repeat unknown writes | Yes and current implementation gap | Assign recovery policy to Runtime plus persistence/Host dedupe; require verify_state for unknown before any retry. |
| §17 Final | Final represents whole goal and real state | Runtime returns Final after in-process verification on successful Create | Final remains a user-facing result returned by Agent API after internal execution/verification | No semantic conflict | Keep success/failure/unknown semantics; clarify that Tool status is not Final status. |
| §18 Client duties and clarification | Client executes Tools, stores operation results, returns ToolResult, also collects clarification | Shortcut is intended as thin HTTP client; ClarificationResponse transport/resume is missing | User Client handles conversation only; Runtime handles execution; clarification still returns through API and resumes the same task | Yes, responsibilities conflated | Split client duties into User Client responsibilities and internal Tool Execution Layer responsibilities; retain clarification as conversation concern. |
| §19 backend duties | Backend MUST NOT possess Calendar/Reminder access | Separate macOS Host has EventKit permission; Python runtime directs it | Agent Core has no direct Calendar API access; explicitly permissioned local MacAgentHost is the execution authority in the same product system | Yes; define security principal carefully | Prohibit direct access by Agent Core/server process; allow the separately scoped local Host under an explicit capability boundary. |
| Errors/timeouts and Tool status (§4.6, §7.3, §12, §16) | Client reports failure/unknown in a new inbound result; Agent validates | Adapter creates ToolResult locally; timeout can become unknown; selected correlation is checked in Dispatcher | Internal execution adapter reports typed status against execution_id; Runtime owns task-level interpretation and verification | Boundary conflict | Keep success/failed/unknown categories; specify which failures are known-not-executed vs ambiguous, and never map timeout to success. |

This is **11 conflict groups** in the matrix (some are primarily semantic/owner conflicts; §15 and §17 retain their core meaning). The most consequential five are: §1/§19 execution authority, §8.1 client-executes request, §7.3/§5 ToolResult-as-new-HTTP-request, §14 client-owned idempotency, and §18 mixed client responsibilities.

## 7. Proposed Terminology

Use names that map to existing code and distinguish the two current meanings of “client”:

- **User Client**: iPhone, Apple Watch, Siri integration, or Shortcut. Owns input and user-facing conversation only.
- **Agent API**: public/user-facing HTTP transport and authentication boundary.
- **Agent Core**: AgentRuntime, semantic analyzer, Planner/Workflow, and orchestration logic.
- **Tool Execution Layer**: ToolDispatcher plus injected ToolAdapter boundary.
- **MacAgentHost**: local AppKit process that owns access to macOS capabilities.
- **Capability**: a host-registered domain operation (currently CalendarCapability); EventKit is its native Calendar API dependency.
- **ToolExecutionRequest / ToolExecutionResult**: internal execution contract. The existing names `ToolRequest`/`ToolResult` may remain as source-level compatibility names, but their normative location must be explicitly internal.
- **HTTP Request / Agent Response**: external user-turn exchange; do not call either “Tool Request” or “Tool Result.”

Avoid “client” alone in normative text. Qualify it as User Client or Execution Host. Do not introduce a Plugin Framework or an additional workflow engine.

## 8. Tool Request / Tool Result Semantics

### Keep the contracts and their useful fields

The internal request/result pair remains valuable for adapter substitution, deterministic tests, subprocess boundaries, auditability, and future capabilities. Preserve:

- `type` (or a versioned internal envelope discriminator), `conversation_id`, `task_id`, `step_id`, `tool`, and unmodified `arguments`;
- `purpose` for queries, including `verify_state`;
- write-only `operation_id` for logical write identity;
- result `status`, `result`/`results`, `error`, timestamps, and query metadata (`queried_range`, `query_scope`, `fetched_at`);
- correlation validation, argument immutability, strict schema validation, and the rule that Tool success is not Final success.

### Change ownership and transport semantics

In Mac-first operation, Tool Request/Result are not public Agent API response/inbound messages. They are internal messages between Runtime/Dispatcher/Host. A future remote execution transport may carry them on a separately authenticated internal boundary; that does not make the iPhone the executor.

`executed_at` is useful on a completed execution result. Query success also needs `fetched_at`; write results need the operation ID and real provider result such as the event ID. A Tool Result should represent the actual adapter/Capability outcome, not the whole task outcome.

### Fields to reconsider

- `request_id`: currently shaped around HTTP inbound-message semantics. It should not be used as a substitute for an internal dispatch-attempt ID.
- `conversation_id`: useful for trace/audit association but not necessary to authorize or select a capability; treat as context, not execution authority.
- `task_id`/`step_id`: remain appropriate for durable orchestration and linking a result to the planned step.
- `operation_id`: remains appropriate for one logical write, stable over retries; it is not a per-attempt ID.
- `purpose`: remains appropriate on queries because answer, conflict, target resolution, and verification have distinct required scopes.
- `calendar_name` and other arguments: remain domain request data; Host must not reinterpret them or silently choose an unintended target.

## 9. ID / Correlation Semantics

### Recommended model

| Layer | Identifier | Creation / rule |
|---|---|---|
| External User HTTP turn | `request_id` | User Client creates a fresh ID per HTTP request; Agent API validates it; Agent Response echoes the ID for that turn. An HTTP retry with the same ID is deduplicated. |
| Conversation | `conversation_id` | User Client creates and retains it across user turns, including clarification. |
| Goal | `task_id` | Agent creates once per user goal and retains it through clarification, execution, verification, and recovery. |
| Planned operation step | `step_id` | Agent creates once for a logical Tool step; Tool Result refers to the same step. |
| Logical write | `operation_id` | Agent creates once and persists before dispatch; reused by every retry/recovery of that same write. |
| Internal dispatch attempt | `execution_id` | Tool Execution Layer/Runtime creates a fresh ID for each actual invocation attempt, including query and retry attempts. Request and result carry the same ID. |
| Internal causality | `causation_request_id` (optional) | Carries the relevant external HTTP turn ID for tracing; it does not mean the Tool Result is a new HTTP request. |

Under this model, **Tool Result does not receive a new external `request_id`**. It carries the `execution_id`, original task/step, and operation ID (for writes). The HTTP Agent Response correlates to the external request that caused the synchronous turn. If a later asynchronous delivery model is introduced, that transport gets its own message ID and causation metadata; do not overload the V1 user `request_id` now.

`step_id` identifies the logical workflow step; it is not sufficient to distinguish multiple attempts. `operation_id` identifies a logical write; it must remain stable when attempt IDs change. `execution_id` is therefore recommended even though the present adapter call is synchronous, because it makes timeout/recovery and future internal transport unambiguous.

The choice to add `execution_id` and redefine ToolResult request identity is a schema change and requires a protocol-version decision; it must not be retrofitted silently under Frozen 1.0.0.

## 10. Idempotency Responsibility

### Current implementation evidence

- Planner/CalendarWorkflow creates an operation ID for a write.
- Runtime persists the operation and argument hash through `OperationRepository.create_or_replay`, and marks newly created operations dispatched.
- The repository rejects same operation ID with changed arguments and blocks an operation already classified unknown.
- Runtime does not use the `created/replay` outcome to suppress a second call to `ToolDispatcher`; a persisted primitive alone does not provide end-to-end idempotency.
- `MacAgentHostAdapter` passes the Tool Request to a subprocess and enforces timeout/cleanup. It does not durably deduplicate by operation ID.
- `MacAgentHost`/CalendarCapability executes EventKit but has no durable operation journal keyed by operation ID.
- Verification can query after a known successful create. Current unknown create result becomes Final.unknown without first running recovery verification.

### Proposed ownership

1. **Agent Core / Runtime** generates one operation ID per logical write and persists the full immutable arguments/hash before any dispatch.
2. **Persistence** atomically claims a dispatch attempt and returns one of: new claim, replayable stored result, operation currently in progress, or unknown requiring verify. Replays must not dispatch again.
3. **ToolDispatcher** dispatches only a claimed execution attempt and validates execution/result correlation. It is not the durable source of truth.
4. **MacAgentHost** maintains a durable local operation journal and returns the previously recorded outcome for a repeated operation ID rather than repeating a Calendar write.
5. **VerificationService** resolves ambiguous outcomes by querying real Calendar state before any retry. A retry is allowed only after code establishes the original effect did not occur and the operation remains safe.

Exactly-once side effects cannot be promised merely by adding a database row: EventKit mutation and the local journal are not one atomic transaction. The system must fail closed as `unknown` across the crash window and reconcile by stable operation identity before retry. How that identity is discoverable on an EventKit event without altering user-visible content is an open design question (see §15).

## 11. Verification Responsibility

The core Protocol semantics are already correct: §4.7, §15, and §17 say Tool/Operation success is not Task success and require a real-state query before a successful Final. Keep these invariants.

Target responsibilities:

- `MacAgentHost` / `CalendarCapability` / EventKit: perform the requested native operation and return observed execution facts.
- `AgentRuntime`: persist tool result, drive state transitions and request verification.
- `VerificationService`: compare the required user-goal fields against a fresh query result and classify verified success/failure/unknown.
- User Client: present the Final; it does not judge real state.

The current successful Calendar Create path performs a verification query and compares event identity when returned, title, start, and end. This aligns with the verification standard for the observed timed-create path. The current unknown-write path does not first run `verify_state`; it is a known implementation gap, not a reason to weaken verification.

## 12. Clarification Boundary

Clarification is a **User Client ↔ Agent API ↔ Agent Core conversation concern**. It is not a Tool execution message. A clarification response must keep the same conversation and task, identify the replied-to clarification step, merge only user-provided facts, and continue the existing task state.

Tool Request/Result are an **Agent Core ↔ Tool Execution Layer** concern. Changing this boundary does not alter `waiting_clarification`, `analyzing_clarification`, `conversation_id`, or `task_id` semantics. The current lack of resume support remains a separate P0 implementation gap and should be implemented only after the public clarification transport and canonical ownership are agreed. This proposal does not implement it.

## 13. Capability Architecture

The existing `MacAgentHost → CapabilityRegistry → CalendarCapability → EventKitAdapter` is a credible small capability boundary: the Host registers capabilities by supported Tool; a capability owns the domain API mapping; EventKit is behind a narrow adapter. It can grow by adding a focused capability and its native adapter (for example Reminder/Contacts/Files) without creating a generic plugin framework.

That is a structural foundation, not evidence those capabilities exist today. Reminder, Contacts, Files, Obsidian, Mail, Browser, and GUI/Computer are not currently registered/executable capabilities. Each new capability needs explicit permission scope, input/result contracts, safety and verification requirements, and tests. MacAgentHost should remain a controlled local execution boundary; it should not absorb Planner, user conversation state, or Final-success policy.

## 14. Schema Impact Analysis

Classification: **A** = structure can remain; **B** = semantic/documentation update; **C** = structure likely changes; **D** = legacy in the target public API.

| Schema | Class | Proposal |
|---|---|---|
| `schemas/inbound-v1.schema.json` | C | Public API needs a canonical user-turn union including `clarification_response`; remove internal ToolResult from public inbound messages. Add/clarify caller-owned request ID and client/device timezone behavior. |
| `schemas/agent-response-v1.schema.json` | C/D split | Public response should be Clarification or Final for a synchronous Mac-first API; current public `tool_request` branch becomes an internal execution request schema, not an API response. If asynchronous/pending is selected later, specify it explicitly rather than leaking an internal Tool Request. |
| `schemas/tool-request-v1.schema.json` | B/C | Keep tool names, arguments, purpose, task/step/op correlation; move from external Agent response framing to an internal execution envelope. Add `execution_id` and define causal request linkage if approved. Timed/all-day schema still needs host support parity. |
| `schemas/tool-result-v1.schema.json` | B/C | Keep status/result/error/query metadata and operation correlation; define it as an internal execution result, remove “new HTTP inbound request” semantics, add matching `execution_id`, and clarify whether request_id remains at all. |
| `schemas/common-v1.schema.json` | B/C | Keep domain/tool/status/state/error enums where unchanged; likely add an execution ID definition and revise cross-message correlation constraints. |
| `schemas/calendar-v1.schema.json` | A/B | Domain operation shapes can remain for existing operations; describe them as internal capability contracts. All-day host-boundary fields need to match actual implementation before claiming support. |
| `schemas/reminder-v1.schema.json` | A/B | Keep the future/contract shapes if protocol scope retains Reminder; mark executable support separately. Do not imply registered EventKit Reminder capability exists. |
| `schemas/llm-analysis-v1.schema.json` | A/B | Tool-execution-owner pivot does not intrinsically require analysis shape changes; independently resolve current source/status enum parity before claiming conformance. |
| Root `schema.json` | D | Already a deprecated compatibility pointer; keep out of normative reconciliation. |

Because these files are versioned `v1`, changing structure while keeping protocol marked Frozen 1.0.0 is not recommended. Decide whether the canonical 1.0 document is superseded and whether the boundary change requires a new protocol minor/major version before updating schemas.

## 15. Test Impact Analysis

### Retain

- Schema/Pydantic parity tests, updated only after schemas/models are jointly approved.
- Domain Tool argument and validation tests.
- MacAgentHost process lifecycle, JSON-lines, cleanup, and Host/Capability contract tests.
- Verification comparison tests proving Tool success alone never yields Final.success.
- Server authentication, listener configuration, malformed request, and HTTP status tests.
- Remote-access script/config tests as local configuration tests; do not treat them as live tunnel E2E.

### Modify

- `tests/test_tool_contracts.py`: distinguish internal execution contract from public Agent API response; retain strict per-tool arguments.
- `tests/test_runtime.py` and `tests/test_runtime_tool_loop.py`: assert internal dispatch stays within backend and Tool Result does not become a public HTTP inbound turn; add same-task clarification once that separate feature is implemented.
- `tests/test_server.py`: validate canonical external message union, HTTP request/response ID echo, public response variants, and no Tool execution payload exposed to the thin client.
- `tests/test_mac_host.py` / Host contract tests: assert execution ID, operation ID preservation, duplicate replay behavior, and correlation mismatch rejection.
- `tests/test_contract_parity.py`: update parity fixtures together with approved schema/model version; retain the known naive-datetime case as an explicit independent issue until separately resolved.
- `tests/test_remote_access.py`: keep script/security contracts; add no network/VPN mutation tests.

### Add

- End-to-end in-process HTTP → Runtime → Dispatcher → Host adapter → Tool Result → verification → Final contract test, plus Host process integration using a deterministic fake executable.
- HTTP duplicate `request_id` replay test: no second logical task and no duplicate side effect.
- operation replay tests spanning Runtime, persistence, dispatcher, and host journal, including same operation/same args, same operation/different args, in-progress, and unknown recovery.
- Tool execution timeout/late-result/duplicate-result correlation tests keyed by `execution_id`.
- Public clarification continuation contract test on the same task, kept separate from Tool Result execution tests.
- Real Mac acceptance checklist/test harness for EventKit and TCC, explicitly separated from ordinary pytest and requiring user authorization for Calendar side effects.

### Mark legacy rather than delete

- Tests whose premise is “Tool Request is returned to the Shortcut, client performs the Calendar operation, then POSTs Tool Result” should be moved to a clearly named legacy-protocol suite or retired only after protocol versioning and migration. Preserve useful client execution adapter contract tests if those adapters remain supported; do not silently make them evidence for current Mac-first behavior.

## 16. Migration Plan

The work is dependency-ordered; no implementation is performed in this proposal.

1. **Decision record:** formally record Mac-first as the sole current V1 execution architecture and list the historical client-executes-Tool model as superseded. Confirm whether Reminder is in current V1 capability scope or merely in the canonical future contract.
2. **Protocol version decision:** determine whether changing a Frozen 1.0 boundary is a new protocol version. Resolve HTTP ID ownership, execution ID, public response union, and unknown-write crash recovery before editing normative text.
3. **Canonical Protocol update:** define User Client vs Execution Host; make Tool Request/Result internal execution contracts; retain clarification as external conversation flow; place Calendar access prohibition on Agent Core/server process rather than the separately permissioned MacAgentHost.
4. **Schema/model synchronization:** update inbound/Agent response/internal execution schemas, then Python/Swift contract types in the same change set. Keep protocol parity tests required before accepting the new spec.
5. **Persistence/idempotency foundation:** implement atomic inbound request dedupe and operation claim/replay; decide how MacAgentHost durably recognizes an operation after a process restart and how unknown EventKit effects are reconciled without blind retry.
6. **Runtime correlation and verification:** bind result to execution/task/step/op and expected state; route every unknown write through `verify_state`; keep Final.success contingent on actual state.
7. **Clarification transport/resume:** accept a canonical clarification response over Agent API and continue the same persisted task. Keep it separate from the internal Tool execution envelope.
8. **Capability scope:** only after boundary/tests converge, declare Calendar Create/Query as implemented; add Reminder or other capabilities in separate vertical slices with their permission and verification contracts.
9. **Documentation and client migration:** synchronize README, role/workflow cards, flowchart, runtime contract, system prompt, Shortcut behavior and QA matrices; preserve the old client-execution design as historical/legacy evidence.
10. **Acceptance:** run contract parity and full automation, Xcode build, deterministic process integration, then separately authorized real Mac EventKit and iPhone/remote transport E2E. Do not treat unit tests as proof of real-device behavior.

## 17. Open Questions

These questions should be answered before changing the canonical protocol:

1. **Versioning:** Is the Mac-first boundary an approved successor to Frozen Protocol 1.0.0, and should it be Protocol 1.1/2.0 rather than silently rewriting Frozen 1.0?
2. **Reminder scope:** Does current V1 promise Reminder CRUD, or is only Calendar Create/Query in executable V1 while Reminder schemas remain planned contracts?
3. **Execution-ID generation:** Should `execution_id` be generated and persisted by Runtime before dispatch, or by a dedicated execution coordinator? Recommendation: Runtime/coordinator generates and persists before dispatch.
4. **EventKit duplicate recovery:** What durable, privacy-preserving link between operation ID and event can be searched after a crash between EventKit save and local journal commit? Can supported EventKit metadata hold an opaque correlation marker, or is conservative `unknown` plus user clarification acceptable?
5. **User HTTP replay:** How long are inbound request IDs retained, and should a duplicate HTTP request return the exact previous response, a task status, or a conflict when the prior request is still running?
6. **Permission principal:** Is the Python Agent Server always forbidden from Calendar access while MacAgentHost alone owns TCC permission? The proposal assumes yes.
7. **Public response timing:** Is Agent API required to wait synchronously for Tool execution/verification, as current code does, or will an explicit pending/status mechanism be needed later?
8. **Tool Request visibility:** Should internal Tool Request/Result schemas remain public files under `schemas/` for adapter contract reuse, or move to an explicitly internal schema namespace while preserving generated clients?

Questions 1, 2, 4, and 6 are the highest-priority decisions.

## 18. Recommended Protocol Changes

After the version/ownership decisions above, the canonical document should:

1. Replace §1 and §19 client-local execution/backend prohibition with the Agent Core versus MacAgentHost permission boundary.
2. Define User Client, Agent API, Agent Core, Tool Execution Layer, MacAgentHost, and Capability; prohibit unqualified normative “client” where ownership matters.
3. State that public HTTP user turns are distinct from internal ToolExecutionRequest/ToolExecutionResult. The User Client receives Clarification/Final and never receives or executes a Calendar Tool Request in Mac-first V1.
4. Revise §5 ID table: HTTP `request_id` per client turn; `task_id` per goal; `step_id` per logical step; `operation_id` per logical write; add per-attempt `execution_id`; optionally link execution to an external turn with `causation_request_id`.
5. Replace “Tool Result is a new inbound request” with “internal result of a particular execution attempt”; do not allocate an HTTP request ID to it. Define exact result correlation and stale/duplicate result rejection.
6. Move §18 client-side idempotency duties into Agent persistence/Runtime and MacAgentHost. Keep operation ID stable and require durable duplicate suppression/replay or verify-before-retry under ambiguous outcomes.
7. Keep §12–17 validation, safety, verification, unknown, and Final success rules; clarify that the Agent Core requests internal query execution and compares returned real state.
8. Keep clarification as a user conversation concern and specify that a clarification response resumes the same task; define public HTTP message handling separately from internal execution messages.
9. Specify that Calendar/Reminder operation availability depends on registered Capabilities, and distinguish schema-defined operations from currently supported product capabilities.
10. Update error/timeout rules so host/process timeout is `unknown` unless the implementation can prove the operation did not execute; require a `verify_state` query before retry.

This proposal does not change the canonical specification. Until the change is approved and versioned, `docs/protocol-v1.md` remains normative even where implementation has deliberately pivoted.
