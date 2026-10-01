# Specification / Implementation Alignment

> **状态：HISTORICAL AUDIT / SUPERSEDED。** 本审计按 V1 precedence 撰写。V2 migration 已完成后，当前规范优先级为 `docs/protocol-v2.md` → `schemas/*-v2.schema.json` → ADR-001 → implementation/tests。本文保留迁移前的证据与发现，不再用于判断当前规范冲突。

Audit date: 2026-09-30. Normative precedence follows docs/protocol-v1.md → schemas/ → role/workflow docs → flowchart → README → system-prompt. Audit only; no source or canonical document changed.

## Product / role alignment

| Concern | Defined | Implemented | Assessment |
|---|---|---|---|
| Agent responsibility | Interpret request/context, plan response, persist state; LLM does not decide safety/final truth | Runtime owns Task/state/ToolResult; DemoLLM emits semantics | Partial: deterministic parser only; continuation and safety incomplete |
| Calendar authority | Protocol §§1,19 say Calendar I/O is a client-local Tool; backend must not hold Calendar permission | Runtime dispatches to separate local MacAgentHost process with EventKit access | Adapter/process boundary exists, but canonical/role Shortcut wording conflicts with Mac-first docs/code |
| Shortcut role | Role/workflow docs assign Tool execution and clarification continuation to Shortcut | Mac-first doc says thin Shortcut; actual Shortcut is outside repo and continuation HTTP path absent | Documentation disagrees; no client artifact for source audit |
| Final success | Requires completed goal and verified real state | Create success triggers verify_state and compares fields | Aligned for this narrow path only |

## Protocol capability coverage

Model/schema presence alone is not implementation. Wired means reachable through normal HTTP→Runtime construction with adapter execution and tests.

| Protocol tool | Model/schema | Planner/Runtime | Dispatcher/native host | Evidence | Status |
|---|---|---|---|---|---|
| create_calendar_event | Yes | Yes | Yes, EventKit | Mock loop B; real Mac execution reported A | Partial real vertical slice; no conflict/duplicate pre-write gate |
| query_calendar | Yes | Yes for supplied analysis | Yes, EventKit | Mock/runtime B | Partial: no natural-language query route via DemoLLM; Runtime returns generic completion, not query contents; host needs bounded range |
| update_calendar_event | Yes | Unsupported failure | No | Contract C only | Specified, not implemented |
| delete_calendar_event | Yes | Unsupported failure | No | Contract C only | Specified, not implemented |
| query_reminders | Yes | No route | No | Model C only | Specified, not implemented |
| create_reminder | Yes | Helper requires calendar_reasonableness_verified=True; Runtime supplies no such context | No | Gate test C | Not executable through normal Runtime |
| update_reminder | Yes | Unsupported failure | No | Contract C only | Specified, not implemented |
| delete_reminder | Yes | Unsupported failure | No | Contract C only | Specified, not implemented |

All six query purposes exist in enums/models. Normal planner emits answer_query; Create verification emits verify_state. Conflict, duplicate, availability, and target-resolution purposes are not orchestrated.

## State machine alignment

ALLOWED_TRANSITIONS is enforced by TaskRepository.transition and transition rows are persisted. Runtime only traverses states below.

| State | Specified/model | Runtime enters | Persisted | Transition enforced | Test | Gap |
|---|---|---:|---:|---:|---|---|
| received | Yes | Yes, initial | Yes | Yes | C | Basic |
| validating_input | Yes | Yes | Yes | Yes | C | No inbound receipt persistence |
| analyzing | Yes | Yes | Yes | Yes | C | Demo analyzer only |
| planning | Yes | Yes | Yes | Yes | C/B | Single task only |
| waiting_tool_result | Yes | Yes | Yes | Yes | B | Synchronous within HTTP request |
| validating_tool_result | Yes | Yes | Yes | Yes | B | Full inbound correlation/state tuple not checked |
| waiting_clarification | Yes | Yes | Yes | Yes | C | Clarification payload/step not saved |
| analyzing_clarification | Yes | No | N/A | Transition exists | No Runtime resume test | Continuation absent |
| pre_execution_check | Yes | No | N/A | Transition exists | No integrated gate test | Safety gate absent |
| verifying_final_state | Yes | Create/query | Yes | Yes | B/A | Field comparison only for successful Create |
| recovering | Yes | No | N/A | Transition exists | Repository unknown-lock tests only | Recovery absent |
| succeeded | Yes | Create verified/query success | Yes | Yes | B/A | Query response generic |
| failed | Yes | Tool failure/mismatch | Yes | Yes | B | Limited E2E cases |
| unknown | Yes | Unknown execution/failed verify | Yes | Yes | B | Unknown write finalizes without verify recovery |

## ID and correlation

| ID | Protocol rule | Current behavior | Alignment |
|---|---|---|---|
| request_id | Sender creates new ID per inbound request; response echoes it | HTTP ignores caller ID and generates req_http_*; Tool adapter creates new req_* result ID | Unique/echo works internally, but sender rule is not implemented at HTTP boundary; new ToolResult ID is correct |
| conversation_id | Client-owned across continuous conversation | Optional; generated if absent; caller retains response value | Language context only, not task continuation |
| task_id | One per goal; clarification/tool result reuse it | Every UserRequest creates new Task; clarification not resumed | Mismatch |
| step_id | Agent creates; ToolResult reuses request step | Exchange keyed by step; Dispatcher checks adapter output | Runtime does not validate full inbound tuple/state |
| operation_id | Stable per logical write; replay cannot repeat side effect | Created/persisted; Runtime dispatches even if create_or_replay says existing | Idempotency execution gap |

## Parameter / datetime alignment

Protocol source values: explicit/context_derived/default. Status values: valid/missing/ambiguous/invalid. Calendar Create requires title/date/concrete start and duration or end; no guessed duration/all-day; time windows are not exact times.

LLMParameter.source/status are unrestricted strings. llm-analysis schema constrains them, but Runtime validates its looser Pydantic model and does not run that JSON Schema. DemoLLM emits noncanonical provenance values such as explicit_request, inferred_from_request, inferred_timed_event, and user_request.assistant_timezone. This is a schema/implementation mismatch.

HTTP defaults assistant_timezone to Asia/Shanghai and uses it for current_time; it does not accept device_timezone. DemoLLM resolves relative dates in assistant timezone. Offset-bearing start/end reach ToolRequest, but named IANA timezone is not carried in Calendar Create arguments into EventKit. Offset/instant preservation exists; full named-zone/DST continuity is unproven.

## Persistence alignment

| Data | Model/repository | Runtime writes | Finding |
|---|---:|---:|---|
| Conversation/timezone | Yes | Yes | Stored |
| Task/final status | Yes | Yes | Stored; every UserRequest creates new Task |
| Parameters/source/status/evidence | Yes | Yes | Stored; source enum not constrained |
| Step/current-step pointer | Yes | Step yes; pointer no | All 47 observed task pointers null |
| Tool request/result exchange | Yes | Yes | Stored by step; hash rejects conflicting result |
| Operation | Yes | Yes | Stored; replay flag does not stop dispatch |
| Clarification context | Yes | No | Repository unused; zero observed rows |
| Inbound receipt/dedupe | Yes | No | Repository unused; zero observed rows |
| State transition audit | Yes | Yes | Stored |
| Final response body | No table | No | Only task status and Tool exchange remain |

server.main calls Base.metadata.create_all and does not run Alembic upgrades. Migration files exist; existing DB evolution is not guaranteed by service startup.

## Verification alignment

- Successful Create builds query_calendar purpose=verify_state for requested range and optional returned event ID/title; compares event ID when present plus title/start/end. Final.success follows this result only.
- Failed/unknown verification returns Final.unknown.
- Unknown write result immediately returns Final.unknown; Protocol requires verify_state before deciding/retrying.
- No pre_execution_check transition, conflict/duplicate query, or safety gate was found.
- Successful query returns generic “Calendar query completed”; result data is not summarized to user.
