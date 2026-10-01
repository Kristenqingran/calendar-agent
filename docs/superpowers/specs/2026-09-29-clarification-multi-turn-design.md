# Clarification Multi-turn Loop Design

## Status

Approved conversational design; implementation has not started. This document
defines the backend continuation path for Personal Agent V1. It does not change
Canonical Protocol v1 or any Shortcut UI configuration.

## Goal

When Calendar planning needs more information, a client can submit the answer
through the existing `/agent` endpoint and resume the same persisted Task. The
agent must retain already-confirmed parameters and only execute Calendar work
after the resumed analysis and Planner produce a valid ToolRequest.

## Non-goals and boundaries

- No changes to Cloudflare, Tunnel, DNS, VPN/V2rayN, firewall, ports, or server
  listen configuration.
- No new endpoint, transport, protocol message, or schema.
- No Calendar/Reminder capability expansion and no Shortcut UI changes.
- No direct tool execution from a clarification answer.

## Existing contracts reused

- HTTP accepts `user_request`, optional `conversation_id`, and optional
  `assistant_timezone`; the server creates a fresh inbound `request_id`.
- Canonical `ClarificationResponse` carries `request_id`, `conversation_id`,
  `task_id`, `reply_to_step_id`, and `message`.
- SQLite already persists conversations, tasks, task parameters, task steps,
  clarification rows, state transitions, and inbound receipts.
- The state machine already permits
  `waiting_clarification -> analyzing_clarification -> planning`.
- The server's supported write and verification path remains the existing
  Calendar `ToolDispatcher` and EventKit Host Adapter.

## Request routing

1. A request without `conversation_id` starts a new conversation and Task, as it
   does today.
2. A request with `conversation_id` must resolve an existing conversation and
   exactly one latest Task in `waiting_clarification`, with one unresolved
   Clarification row and a current step matching that row.
3. At the HTTP boundary, the server maps the client's answer to a canonical
   `ClarificationResponse`, using the persisted Task and step IDs. The client
   never invents backend-owned `task_id` or `step_id` values.
4. Each inbound HTTP call retains a newly generated `request_id`; continuation
   reuses `conversation_id` and the original `task_id`, and targets the pending
   `reply_to_step_id`.
5. Unknown conversations, conversations without a pending clarification,
   completed Tasks, malformed payloads, and concurrent/replayed answers return
   controlled errors. They must not create a new Task or dispatch a Tool.

## Persistence and state flow

When Planner first returns a Clarification, Runtime atomically creates a
clarification TaskStep and Clarification row, stores the current step ID on the
Task, and transitions the Task to `waiting_clarification`.

On continuation, Runtime validates the conversation/task/step correlation and
atomically claims the pending Task by transitioning it to
`analyzing_clarification` with the existing optimistic version mechanism. It
persists the user's answer on the resolved Clarification row. The same Task is
then analyzed and planned. If another clarification is needed, Runtime creates
a new clarification step/row and returns to `waiting_clarification`; otherwise
it follows the existing ToolRequest, dispatch, ToolResult, verification, and
Final path.

The maximum is five clarification answers for one Task. An answer beyond that
limit ends the Task through the existing legal failure transition and returns
a localized Final failure; it does not dispatch a Tool.

The persistent SQLite database is the source for continuation state, so the
loop can resume after Agent Server process restart. The implementation should
reuse existing tables and repositories; no schema migration is expected.

## Semantic context and parameter preservation

Each continuation analysis receives the original request, persisted valid and
ambiguous parameters, prior clarification questions and answers, the current
answer, and the effective assistant timezone. Existing valid parameters are
retained unless the user explicitly corrects them. A short answer must not
replace the original task or silently discard a confirmed date, title, or
timezone. The language of each response follows the existing bilingual
response-language policy.

For timezone selection, an explicitly supplied and valid `assistant_timezone`
on the continuation request is the effective timezone and updates the stored
conversation value; if omitted, Runtime uses the conversation's persisted
timezone. The HTTP boundary must not silently substitute the Mac timezone for a
continuation. Already-resolved date/time parameters remain preserved unless the
user explicitly corrects them.

The `DemoLLM` remains deterministic and local. It may use this context to
extract the aggregate Calendar request; it must not invent missing dates, times,
durations, or titles. The Planner remains the authority that decides whether
the information is sufficient.

## Duplicate and replay safety

The Task state transition from `waiting_clarification` to
`analyzing_clarification` is the single-consumer gate. Only one answer may claim
the pending clarification. A repeated answer after claim/resolution receives a
controlled conflict response and cannot create another Task or operation. A
write remains reachable only through the existing Planner/ToolRequest path,
which creates one operation ID and uses existing operation persistence.

Claiming the Task and recording the answer are one database transaction. If
semantic analysis or planning fails after the claim, Runtime transitions the
same Task to the already-allowed `failed` state and returns a controlled Final
failure; it does not leave a silently stranded in-progress Task or dispatch a
Tool.

## Error behavior

- Invalid JSON/body/field types: existing controlled HTTP 400 behavior.
- Unknown `conversation_id`: controlled HTTP 404 error.
- Known conversation with no pending clarification, completed Task, stale
  reply, or a replay/concurrent answer: controlled HTTP 409 error.
- Clarification answer limit reached: protocol-shaped localized Final failure
  for the original Task; no Tool dispatch.
- Unexpected storage/runtime errors must not be represented as Calendar
  success. Existing generic HTTP runtime error handling remains in place unless
  a narrowly scoped continuation error mapping is required.

## Client contract

The Shortcut remains a thin client and keeps the same HTTPS URL, headers, and
JSON fields. It must retain the returned `conversation_id`, display/speak the
Clarification message, collect the user's answer, and POST that answer as the
next `user_request` with the same `conversation_id`. It repeats while the Agent
returns Clarification and stops on Final. No Shortcut UI is changed as part of
this backend design; manual client configuration/validation remains a separate
acceptance step.

## Verification and acceptance

Automated integration tests must exercise the actual HTTP handler and
AgentRuntime against one persistent test database and a Mock Calendar adapter.
They must prove that multiple clarification rounds preserve one Task and
conversation, use a fresh request ID per inbound request, retain valid
parameters/timezone, dispatch no Tool before sufficiency, and then perform
Create -> ToolResult -> verification query -> Final success. Failure cases must
cover unknown/stale/completed conversations, malformed input, duplicate
continuation, response language, and the existing single-turn behavior.

Real iPhone/Siri regression remains pending until the unchanged Shortcut sends
each answer back to `/agent` with the returned `conversation_id` and displays
the eventual Final response.
