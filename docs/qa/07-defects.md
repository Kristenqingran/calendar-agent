# QA Defects

## AGENT-CONV-001 — Clarification answer started a new task instead of resuming

- **Source:** Real iPhone + Siri E2E
- **Observed:** A request requiring clarification followed by a Siri answer did
  not continue the original Calendar task. The answer could be interpreted as
  a separate request, and the client workflow did not reach the expected
  Calendar Create → verification → Final sequence.
- **Expected:** POST the answer to `/agent` with the original
  `conversation_id`; the server resolves the sole pending clarification and
  continues the same persisted task.
- **Layer:** HTTP conversation resolution / Runtime persistence and state
  transition.
- **Root cause:** HTTP treated each follow-up as an independent `UserRequest`.
  Pending clarification state was not persisted/claimed and the internal typed
  `ClarificationResponse` was not routed through Runtime.
- **Fix:** Persist pending clarification step, expected answer, parameter state,
  and Task state in existing SQLite tables. The HTTP boundary fails closed
  unless exactly one clarification is waiting, then constructs the typed
  internal response with server-owned IDs. Runtime claims the same task,
  merges saved valid parameters with the answer, preserves timezone/language
  context, and follows existing Tool/Verification paths. The Server generates
  a fresh `request_id` per inbound request; same-ID retries replay the stored
  response.
- **Regression coverage:** `tests/test_clarification_resume.py` exercises live
  loopback HTTP with a newly constructed Runtime/session per turn, bilingual
  and multi-round follow-ups, same-task/new-request IDs, timezone continuity,
  retry replay, invalid/completed/ambiguous conversations, answer limit, and
  Create → verify query → Final.
- **Status:** Automated implementation verified; real iPhone/Siri multi-turn
  regression pending.

## DEFECT-2 — HTTP timezone context caused Calendar event time shift

- **Source:** Real iPhone → LAN → Mac Agent → EventKit E2E
- **User Request:** `明天早上9点和 Bob 开一个小时的会`
- **Expected:** Start at tomorrow 09:00; end at tomorrow 10:00.
- **Actual:** Calendar event was created at 15:00 instead of 09:00.
- **Observed:** `+6 hours`.
- **Status:** Fixed in code; real-device regression revalidation pending.

### Root Cause

The HTTP boundary constructed `UserRequest.current_time` in UTC while setting
`assistant_timezone` to `Asia/Shanghai`. `DemoLLM` used
`request.current_time.tzinfo` when constructing relative local event times, so a
user-local 09:00 was serialized with the wrong timezone context. EventKit then
interpreted the serialized instant and Calendar displayed it in the Mac's local
timezone, producing the observed shift.

This was an implementation boundary defect, not a Protocol v1 defect. The
canonical protocol already requires an offset-bearing datetime and an IANA
timezone.

### Fix

The HTTP boundary now constructs `current_time` with the selected IANA timezone
instead of UTC. It accepts an optional `assistant_timezone` transport field and
defaults to `Asia/Shanghai` for the existing local HTTP client. Invalid IANA
timezones fail at the HTTP boundary.

No fixed hour correction, Mac timezone assumption, IP-based inference, or
EventKit masking was added.

### Regression Coverage

- `tests/test_demo_llm.py::test_demo_llm_preserves_morning_nine_as_local_nine`
- `tests/test_demo_llm.py::test_demo_llm_extracts_calendar_create_semantics`
- `tests/test_server.py::test_valid_request_becomes_existing_user_request`
- `tests/test_server.py::test_http_timezone_boundary_controls_current_time_offset`
- `tests/test_server.py::test_invalid_http_timezone_fails_at_boundary`
- Existing runtime verification tests continue to validate planned versus
  queried event fields.

### Follow-up

The current HTTP client contract does not automatically propagate the iPhone or
Apple Watch timezone. A future client-access change should explicitly send the
client's IANA timezone; this is a transport-boundary follow-up and must not be
inferred from the Mac timezone or network address.

## DEFECT-3 — DHCP LAN address is not a stable client endpoint

- **Source:** Real LAN client access test
- **Observed:** Mac address changed from `192.168.0.34` to `192.168.0.39`.
- **Risk:** A Shortcut hardcoded to a DHCP address stops reaching the Agent.
- **Status:** Code-side mitigation complete; external endpoint deployment pending.

The Agent does not contain a LAN address. LAN mode is explicitly configured
through `AGENT_SERVER_HOST` and `AGENT_SERVER_PORT`. A future remote deployment
must provide a stable authenticated HTTPS endpoint through a private access or
tunnel layer. Router forwarding, firewall changes, VPN changes, and provider
installation are outside this phase.

## DEFECT-4 — HTTP endpoint previously had no authentication boundary

- **Source:** Remote access threat review
- **Risk:** Any reachable caller could trigger Calendar side effects.
- **Status:** Fixed in code for the current boundary.

Non-loopback listeners now fail fast without `AGENT_API_TOKEN`. Configured
tokens use Bearer authentication and timing-safe comparison. Unauthorized
requests are rejected before `AgentRuntime`. The token is never returned or
logged. The loopback default remains available for local development.

Regression coverage is in `tests/test_server.py` for missing, invalid, and
valid credentials and configuration behavior.

## Remote Access Acceptance Criteria

- RA-01: Mac LAN DHCP changes do not change the client HTTPS endpoint.
- RA-02: iPhone home-Wi-Fi request succeeds through the stable endpoint.
- RA-03: iPhone cellular/external-Wi-Fi request succeeds through the same endpoint.
- RA-04: Mac restart/login restores Agent Server and Cloudflare Tunnel.
- RA-05: missing or invalid API credentials are rejected before AgentRuntime.
- RA-06: the stable endpoint is HTTPS and does not expose `:8000` publicly.
- RA-07: Calendar side effects require EventKit verification and Final success.
- RA-08: Apple Watch Shortcut reaches the stable endpoint and displays Final.

Repository scripts, LaunchAgent templates, server authentication and
documentation are complete. RA-02, RA-03, RA-04 and RA-08 remain
real-device/provider acceptance checks requiring Cloudflare authorization and
the user's iPhone/Watch.

## DEFECT-5 — iPhone request selected the inactive legacy Calendar bridge

- **Source:** Real iPhone Shortcut → Cloudflare Tunnel → Mac Agent E2E
- **User request:** `明天早上9点和Bob开一个小时的会`
- **Observed:** no Calendar event was created.
- **Evidence:** the persisted task reached `calendar_event/create`; a
  `create_calendar_event` ToolRequest and operation were stored. Its ToolResult
  was `failed` with `calendar_bridge_connection_error` because localhost port
  `8770` refused the connection. No MacAgentHost/EventKit write or verification
  occurred.
- **Root cause:** the LaunchAgent environment omitted
  `MAC_AGENT_HOST_EXECUTABLE`; `build_runtime()` silently chose the legacy
  `LocalCalendarAdapter` instead of the Mac-first `MacAgentHostAdapter`.
- **Response behavior:** the HTTP handler returned HTTP 200 with a
  `Final.failure` JSON body. The Shortcut HTTP action therefore completed at
  the transport level, while the Calendar side effect had failed.
- **Fix:** the Server now defaults to `MacAgentHostAdapter`, keeps alternate
  adapters available through explicit injection, and the local LaunchAgent
  config now points to the previously verified MacAgentHost executable.
- **Regression coverage:** `tests/test_server.py` checks the MacAgentHost
  default and configured executable selection.
- **Status:** fixed; one fresh iPhone replay is needed to verify the live
  Calendar Create → EventKit Verification → Final path.

## AGENT-LANG-001 — Agent response language does not follow user input language

- **Source:** Real iPhone Shortcut + Siri/Dictate E2E
- **Environment:** iPhone Shortcut → HTTPS `agent.buildcodex.net` → Cloudflare
  Named Tunnel → Mac Agent Server → AgentRuntime
- **Steps:** Run the Agent assistant Shortcut; dictate `Create a meeting tomorrow.`;
  send Dictated Text as `user_request`; let the Agent request missing date/time
  details; extract `message` and pass it to Speak Text.
- **Actual:** Agent returned Chinese (`请提供会议的具体开始时间和时长。`) for the
  English request. The English Speak voice pronounced that response incorrectly.
- **Expected:** English input receives an English user-facing response; Chinese
  input continues to receive Chinese.
- **Severity:** Medium
- **Priority:** P1 for Siri/Watch voice E2E
- **Layer:** Agent response semantics / language handling
- **Not caused by:** Dictate Text, Shortcut variable binding, Cloudflare Tunnel,
  HTTP API, Get Dictionary Value, or Speak Text. Manual isolation confirmed the
  fixed English phrase `Hello, this is a test.` is spoken correctly.
- **Root cause:** DemoLLM's missing-time clarification was a fixed Chinese string;
  Planner forwarded it unchanged, and Runtime generated success/failure/unknown
  Final messages with fixed Chinese text. No response-language selection existed.
  The latest iPhone observation was also consistent with a stale Agent Server:
  its process started at 11:02, while the language-fix source files were updated
  at 14:00. The old process therefore could still serve the pre-fix behavior.
- **Fix:** Added deterministic input-script language selection (`zh` / `en`),
  conversation-context fallback for short follow-ups, and localized clarification
  and Final/error copy at the layer that creates each response. Unknown language
  falls back to Chinese. The HTTP boundary accepts an optional validated
  `conversation_id` so clients can continue language context; omitting it retains
  the existing new-conversation behavior. Canonical protocol and Shortcut
  configuration are unchanged.
- **Regression coverage:** `tests/test_response_language.py`,
  `tests/test_demo_llm.py::test_demo_llm_uses_english_for_english_clarification`,
  `tests/test_runtime.py` language/status/correlation tests, and
  `tests/test_server.py::test_http_default_runtime_clarification_matches_input_language`,
  `tests/test_server.py::test_http_short_followup_inherits_conversation_language`,
  `tests/test_server.py::test_live_http_server_returns_clarification_in_request_language`.
- **Deployment action:** Restarted only the existing Agent Server LaunchAgent;
  the new PID serves the updated language-selection code.
- **Latest verification:** Authenticated loopback HTTP returned the expected
  English and Chinese clarification messages. Public POST from the current
  execution environment returned Cloudflare `403 error code: 1010` before an
  Agent response, so it does not validate the public Agent path from this client.
- **Status:** Open — code fix and local HTTP validation pass; public route and
  real-device regression are not yet verified from this environment.
- **Real-device status:** iPhone Siri/Shortcut regression still required.

## AGENT-PARAM-001 — English Calendar Create parameters were treated as missing

- **Source:** Real iPhone Shortcut E2E
- **User request:** `Create a meeting called Test Meeting on September 30 at 3 PM for one hour.`
- **Expected:** Extract the explicit title, date, 15:00 start, and 60-minute
  duration; create and verify the matching Calendar event.
- **Actual:** HTTP returned a Clarification asking for the start time and
  duration, so Calendar Create was not planned or dispatched.
- **Layer:** Analysis / parameter extraction / validation
- **Pre-fix HTTP/runtime evidence:** The persisted task was
  `calendar_event/create` in `waiting_clarification`. Analysis stored title
  `会议` as `valid` with source `deterministic_demo`; it had no date or duration
  parameters; `start` and `end` were `null` with status `missing` and source
  `deterministic_demo`. The request timezone was `Asia/Shanghai`, supplied by
  the HTTP boundary default. No ToolRequest or Calendar write was produced.
- **Root cause:** `DemoLLM._calendar_parameters()` selected one parser for the
  entire message based on whether it contained Chinese characters. This caused
  fields expressed in the other language to be dropped in mixed-language input.
  AGENT-LANG-001 localized clarification copy; it did not cause the extraction
  limitation.
- **Fix:** Replaced exclusive language routing with per-field bilingual
  extraction. Chinese and English relative/named dates, clock times, durations,
  titles, and participants can be combined. End is derived only from an explicit
  start and duration; timezone still comes from
  `UserRequest.assistant_timezone`. Missing/invalid components continue to
  trigger clarification; no defaults are invented.
- **Regression coverage:** English, Chinese, and mixed-language complete
  requests are tested through DemoLLM parameter assertions and a live loopback
  HTTP server running AgentRuntime/Planner/CalendarWorkflow/Mock Tool
  Dispatcher/Verification. Incomplete English and Chinese requests still
  clarify rather than receiving guessed values.
- **Status:** Open — automated fix verified; real-device regression pending.
- **Real-device status:** Retest the exact English request on iPhone after
  restarting the Agent Server with the updated code.

## QA-PROTOCOL-001 — V2 inbound naive datetime 的 Schema/Pydantic parity

- **来源：** Protocol V2 全量自动化回归
- **涉及层：** `schemas/inbound-v2.schema.json` 与 Python `UserRequest`
- **实际：** `tests/test_contract_parity.py::test_invalid_fixture_is_rejected_by_schema_and_pydantic[inbound-naive-datetime]` 中，JSON Schema 接受不含 UTC offset 的 `current_time`，而 Pydantic contract 拒绝该值。
- **预期：** 两种 contract 对无 offset datetime 一致拒绝。
- **状态：** 已知历史 parity defect；本次 V2 Mac-first 迁移未修改该规则，留待独立修复。
- **回归证据：** 本轮完整 pytest 为 311 passed、1 failed；唯一失败为此 case。其余测试通过。
