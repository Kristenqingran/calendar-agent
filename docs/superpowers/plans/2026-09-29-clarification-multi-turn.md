# Clarification Multi-turn Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resume a persisted Calendar Task through repeated clarification answers posted to the existing `/agent` endpoint, then continue the existing Planner → Tool → Verification → Final path.

**Architecture:** Keep the HTTP payload and Canonical Protocol unchanged. The HTTP boundary resolves a provided `conversation_id` to exactly one pending clarification and constructs a canonical `ClarificationResponse` from server-owned Task/step IDs. Runtime persists each clarification round, claims it using the Task version transition, supplies the original request plus prior answers/parameters to deterministic DemoLLM analysis, and only dispatches after Planner approves a valid ToolRequest.

**Tech Stack:** Python 3.12, SQLAlchemy, Pydantic v2, `http.server`, pytest, SQLite.

**Spec:** `docs/superpowers/specs/2026-09-29-clarification-multi-turn-design.md`

## Global Constraints

- Do not modify `docs/protocol-v1.md`, `schemas/`, or protocol models.
- Do not modify Shortcut UI/configuration, Cloudflare, Tunnel, DNS, VPN/V2rayN, firewall, listen address/port, or remote-access settings.
- Do not add a new endpoint, dependency, Calendar capability, or direct write path.
- Preserve the same `conversation_id` and `task_id` across clarification rounds; generate a fresh `request_id` for each inbound HTTP request.
- Do not dispatch any write Tool until analysis and Planner return a valid ToolRequest; retain existing operation idempotency and Verification.
- Limit each Task to five accepted clarification answers; exceeding the limit returns a localized Final failure without Tool dispatch.
- Preserve unrelated tracked and untracked workspace changes; do not commit, push, or merge.

## Review Focus

- A short answer must not lose the original meeting intent or already-valid title/date/time; test an English and a Chinese multi-round continuation.
- Replayed or concurrent answers must not create another Task or dispatch a duplicate Calendar write; test sequential replay and competing claims.
- A supplied timezone must be validated; omitted continuation timezone must come from persisted Conversation state, never the Mac timezone; test both cases.
- Unknown, completed, stale, and non-pending conversations must return controlled errors without creating a Task or invoking an adapter; test each at HTTP boundary.
- Clarification completion must still use real Planner/ToolResult/verification semantics; test a shared-database HTTP flow ending in Calendar Create + verification + Final.success.

---

### Task 1: Persist pending clarification rounds

**Files:**
- Modify: `src/calendar_agent_protocol/runtime.py`
- Modify: `src/calendar_agent_protocol/repository.py` only if a minimal existing repository method is needed
- Test: `tests/test_runtime.py`

**Interfaces:**
- Consumes: `Planner.plan(...) -> ToolRequest | Clarification | Final`; `ClarificationRow`; `TaskStepRow`; `TaskRepository.update_with_version(...)`.
- Produces: every Clarification returned by Runtime has a persisted clarification step/row, stored `current_step_id`, expected answer and field metadata, plus Task state `waiting_clarification`.

- [ ] **Step 1: Add failing Runtime tests** for persisted clarification step/row correlation, `current_step_id`, and exact `waiting_clarification` transition. Assert no Tool exchange, operation, or adapter call is created.
- [ ] **Step 2: Run the focused tests** with `.venv/bin/python -m pytest tests/test_runtime.py -k clarification -v`.
  Expected: new persistence assertions fail because current Runtime only changes Task state.
- [ ] **Step 3: Implement atomic clarification persistence** in Runtime using existing tables/repositories and current generated `step_id`; persist reason/message/expected answer/missing and ambiguous fields and transition within one `UnitOfWork`.
- [ ] **Step 4: Re-run** `.venv/bin/python -m pytest tests/test_runtime.py -k clarification -v`.
  Expected: new tests pass; existing Runtime tests remain green.

### Task 2: Resume the same Task in Runtime and retain semantic context

**Files:**
- Modify: `src/calendar_agent_protocol/runtime.py`
- Modify: `src/calendar_agent_protocol/demo.py`
- Modify: `src/calendar_agent_protocol/runtime_contract.py` only if the adapter context signature requires a typing update
- Test: `tests/test_runtime.py`
- Test: `tests/test_demo_llm.py`

**Interfaces:**
- Consumes: persisted pending Task, TaskParameters, clarification turns, and a canonical `ClarificationResponse`.
- Produces: `AgentRuntime.handle(ClarificationResponse)` claims `waiting_clarification → analyzing_clarification`, stores the answer, re-analyzes the aggregate task context, and returns another Clarification, ToolRequest, or Final on the same Task.

- [ ] **Step 1: Add failing Runtime tests** for one and multiple continuation rounds; assert stable conversation/task IDs, new clarification step IDs, prior valid parameters retained, and no Tool dispatch before sufficient information.
- [ ] **Step 2: Add failing DemoLLM tests** showing aggregate English/Chinese turns extract start and duration without inventing missing values, that an explicit correction uses the latest answer, and that response language follows the current answer/original task.
- [ ] **Step 3: Run** `.venv/bin/python -m pytest tests/test_runtime.py tests/test_demo_llm.py -k 'clarification or context' -v`.
  Expected: current Runtime rejects `ClarificationResponse`, and DemoLLM ignores context.
- [ ] **Step 4: Implement continuation handling** in Runtime: validate Task/conversation/pending step, enforce five-answer limit, atomically claim and record the answer, use persisted timezone unless a valid explicit timezone is supplied, retain/merge previously valid parameters unless explicitly corrected, and create the next clarification step when still incomplete.
- [ ] **Step 5: Update DemoLLM context handling** to analyze the original request plus persisted clarification turns deterministically, with no defaults for missing time/duration.
- [ ] **Step 6: Ensure post-claim analysis/planning exceptions transition the same Task to the allowed `failed` state and never dispatch a Tool.**
- [ ] **Step 7: Re-run** `.venv/bin/python -m pytest tests/test_runtime.py tests/test_demo_llm.py -k 'clarification or context' -v`.
  Expected: focused continuation tests pass.

### Task 3: Route HTTP continuation safely and prove the real server path

**Files:**
- Modify: `src/calendar_agent_protocol/server.py`
- Modify: `src/calendar_agent_protocol/repository.py` only for a minimal pending-by-conversation query if required
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: existing `{user_request, conversation_id?, assistant_timezone?}` JSON and Task/Clarification persistence.
- Produces: a no-conversation request remains `UserRequest`; a known conversation with a pending clarification is mapped to `ClarificationResponse` with fresh `req_http_*` and persisted task/step IDs; invalid continuation returns controlled 404/409 and does not call Runtime/Adapter.

- [ ] **Step 1: Add failing actual HTTP server integration tests** using the existing `ThreadingHTTPServer`, one persistent SQLite test database, a newly constructed Runtime/session for each request, and Mock Calendar adapter. This simulates service/runtime restart between rounds. Cover initial clarification, same-conversation follow-ups, stable Task ID, fresh request IDs, 3 rounds, no premature adapter calls, then exactly one create and verification query ending in Final.success. Add a round-limit case proving the sixth answer is rejected without dispatch.
- [ ] **Step 2: Add HTTP error/replay tests** for malformed body, unknown conversation (404), known conversation with no pending clarification/completed Task/stale response (409), sequential replay and competing claims, proving no duplicate Task or write.
- [ ] **Step 3: Run** `.venv/bin/python -m pytest tests/test_server.py -k 'clarification or continuation' -v`.
  Expected: current handler passes every request as a new `UserRequest`, so continuation and error-routing assertions fail.
- [ ] **Step 4: Implement a small HTTP-boundary resolver** that locates exactly one latest waiting Task and its unresolved Clarification; constructs the canonical `ClarificationResponse`; maps repository correlation/concurrency errors to controlled transport responses. Do not accept Task/step IDs from the client.
- [ ] **Step 5: Re-run** `.venv/bin/python -m pytest tests/test_server.py -k 'clarification or continuation' -v`.
  Expected: integration and controlled-error tests pass, with existing single-turn HTTP behavior intact.

### Task 4: Update QA and current client/runtime documentation

**Files:**
- Modify: `docs/qa/07-defects.md`
- Modify: `docs/architecture/mac-first-client-access.md`
- Modify: `docs/runtime-contract-v1.md`
- Test: no new tests; rely on Task 1–3 coverage

**Interfaces:**
- Consumes: implemented API/status behavior and integration test evidence.
- Produces: AGENT-CONV-001 marked automated-fixed / real-device regression pending; docs describe the actual multi-turn transport without changing Canonical Protocol.

- [ ] **Step 1: Update AGENT-CONV-001** with source, observed Siri/Countdown symptom, root cause, fix, automated regression links, and real iPhone status pending.
- [ ] **Step 2: Update client/runtime documentation** so it says each answer is posted to the same `/agent` endpoint with the returned `conversation_id`; remove the stale statement that continuation transport is still unimplemented. Include the five-answer limit and controlled stale/completed behavior.
- [ ] **Step 3: Review the docs against actual handler/tests**; do not edit `docs/protocol-v1.md` or schemas.

### Task 5: Full regression and security/scope validation

**Files:**
- No additional files unless a failing relevant regression requires a focused fix

**Interfaces:**
- Consumes: all implementation and test changes from Tasks 1–4.
- Produces: verified continuation loop with an explicit report of known unrelated failures and the required manual Shortcut/iPhone check.

- [ ] **Step 1: Run targeted suites:** `.venv/bin/python -m pytest tests/test_runtime.py tests/test_demo_llm.py tests/test_server.py tests/test_runtime_tool_loop.py -v`.
- [ ] **Step 2: Run the complete suite:** `.venv/bin/python -m pytest -q`; retain and report the known unrelated `inbound-naive-datetime` Schema/Pydantic parity failure without changing it.
- [ ] **Step 3: Run `git diff --check` and inspect `git diff --stat` plus changed paths.** Confirm no Protocol/schema, Shortcut, network, VPN, Tunnel, token, listener, or unrelated files changed.
- [ ] **Step 4: Report** the implemented flow, tests, manual Shortcut requirement (reuse response `conversation_id`, POST each spoken answer, repeat on Clarification, stop at Final), and readiness for real iPhone regression. Do not claim the real-device test passed before the user runs it.
