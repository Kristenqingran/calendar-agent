# Agent Observability & Traceability Baseline

本文是当前 Mac-first Calendar Agent 的可观测性现状审计与后续设计提案。它不改变 Protocol V2、业务持久化语义或运行配置。

## 1. 摘要

当前系统对“已进入 Runtime 并成功持久化”的任务已有可用业务轨迹：SQLite 保存 conversation、task、参数、clarification、状态转换、Tool exchange、operation 和 inbound receipt。主要缺口在 HTTP transport 与运行诊断边界：`AgentRequestHandler.log_message()` 丢弃访问日志；认证拒绝、请求校验拒绝、conversation resolution 失败没有统一 trace；Runtime、Planner、Dispatcher、MacAgentHost 和 EventKit 没有共享的结构化事件 taxonomy。因此真机上看到 Siri 文案或没有副作用时，通常只能从零散数据库记录反推，无法区分“客户端没发”“HTTP 拒绝”“Resume 未开始”或“执行后响应未回到客户端”。

推荐先采用**结构化 JSON 日志 + 现有 SQLite 业务记录关联**，不新增 trace/event 数据库表，不记录用户文本、澄清答案、日历标题、事件详情或任何认证凭证。`trace_id` 可作为仅用于诊断的 transport trace context；Protocol V2 的 ID 语义保持不变。

## 2. 审计范围与当前证据

审计对象：HTTP Server、Conversation/Clarification Resume、SQLite persistence、AgentRuntime、Planner/CalendarWorkflow、ToolDispatcher、MacAgentHostAdapter、Swift MacAgentHost/CalendarCapability、VerificationService 和 Final。

### 2.1 分层现状

| 层 | 当前可观察内容 | 当前缺口 |
|---|---|---|
| HTTP Server | JSON/schema 校验；认证；生成或验证 `request_id` / `conversation_id`；成功进入 Runtime 后返回 JSON response | `log_message()` 是 no-op；没有 method/path/status/duration/response type access record；401/400/404/409/500 不进入业务 receipt；无法证明请求是否到达 handler 或为何被拒绝；异常被映射为通用 HTTP error |
| Conversation Resolver | 从 SQLite 查询 conversation、唯一 waiting task、pending clarification；没有任务时返回 409；多个任务时 fail closed | 没有 resolver outcome 结构化日志；HTTP status 与 resolver 结果没有诊断关联；未携带 `conversation_id` 时 Server 会创建新 conversation，客户端续接错误不易识别 |
| Persistence | `conversations`、`tasks`、`task_parameters`、`task_steps`、`clarifications`、`state_transitions`、`inbound_receipts`、`tool_exchanges`、`operations`；request/response payload 和状态可查询 | 不持久化被 HTTP 拒绝的请求；不持久化原始 LLM 分析对象；没有 HTTP status、duration、dispatch wall time；SQLite 内含原始用户文本、clarification answer、Tool arguments/results 等敏感个人数据 |
| AgentRuntime | 创建 task/step；保存参数及 source/status/evidence；Resume 时写 inbound receipt、状态转换、clarification answer；持久化 ToolRequest/ToolResult；执行 verification 并构造 Final | 没有结构化阶段日志；LLM/merge/planner 的阶段耗时和安全摘要不可直接观察；部分异常被转换成通用失败响应，缺少诊断事件 |
| Planner / CalendarWorkflow | 将有效参数映射为 Clarification、ToolRequest 或 Final failure；ToolRequest 带 V2 execution/correlation IDs | 不记录 decision event；没有可直接查询的“为什么缺参数”诊断摘要（虽然参数状态在 SQLite 可查）；不能单凭日志看 intent/tool 选择 |
| ToolDispatcher / Adapter | Dispatcher 校验 ToolRequest、调用注入的 adapter、校验 ToolResult correlation；异常转为 failed ToolResult；Mac adapter 有 timeout / invalid response 等明确错误码 | dispatch start/end、adapter 类型、duration 和错误码未结构化记录；若 adapter exception message 直接进入错误对象，不能把该文本照搬到普通日志 |
| MacAgentHostAdapter | Popen JSON-lines；等待 stdout 一行；timeout 映射 unknown；进程 finally cleanup；ToolResult Pydantic validation | 没有稳定 execution lifecycle log；stdout 是 protocol，stderr 生命周期/诊断未与 Server log 建立关联；不能由日志快速区分启动、超时、空响应、JSON 错误和 cleanup |
| MacAgentHost / EventKit | Host 将 ToolRequest 分派到 CapabilityRegistry；CalendarCapability 支持 create 和 verify query；Host stderr 有 lifecycle 启动信息，stdout 输出 JSON-lines ToolResult；EventKit Create 检查真实 eventIdentifier/字段，query 返回 event 字段 | 无每次执行的结构化日志；无统一 request/operation/execution correlation event；EventKit 错误只作为 ToolResult error；不应将 stdout protocol 混入日志 |
| VerificationService | 持久化 verify query exchange/result；用真实 query 比较 event ID（若有）、title、start、end；Runtime 记录 operation verification status 并生成 Final | 没有 `verification.started/completed` 诊断事件、匹配/不匹配原因摘要和耗时；不得在普通日志写入完整标题/事件详情 |
| Final / HTTP Response | Clarification/Final JSON 返回客户端；成功 Runtime response 保存到 inbound receipt；Final status 更新 Task terminal state | HTTP status 未与 response type 一起记录；Final 的生成和发送缺少统一 event；客户端是否收到/朗读 Final 无服务端证据 |

### 2.2 当前 SQLite 业务记录

当前 ORM 定义的主要记录及其用途：

- `conversations`：conversation ID、assistant timezone、创建/更新时间。
- `tasks`：原始用户文本、对象/意图、当前状态、final status、current step、版本号。
- `task_parameters`：参数值、来源、状态、evidence。
- `task_steps`：step 类型/状态及 input/output summary。
- `clarifications`：问题、期待答案、缺失/歧义字段、用户回答和 resolve 时间。
- `state_transitions`：Task 状态前后值、reason 和时间。
- `inbound_receipts`：request/conversation/task 关联、消息类型、payload hash、保存的外部响应。
- `tool_exchanges`：ToolRequest/ToolResult payload、purpose、状态及 query metadata。
- `operations`：写操作 ID、参数 hash、operation 状态、结果及 verification 状态。

这些记录足以重建多数**已提交**的业务执行轨迹，但它们不是 HTTP access log，也不能证明一个未留下 receipt 的网络请求曾到达 Server。

## 3. 推荐 Trace Model（遵循 Protocol V2）

### 3.1 标识符职责

| 标识符 | 使用方式 | 是否属于 Protocol V2 |
|---|---|---|
| `request_id` | 一个外部 HTTP inbound 轮次；Clarification/Final 响应关联触发它的轮次；无客户端 ID 时 Server 生成 | 是 |
| `conversation_id` | 多轮用户会话稳定关联；follow-up 必须复用原值 | 是 |
| `task_id` | Runtime 持久任务；澄清后必须恢复原 Task | 是 |
| `step_id` | Task 内一个 clarification/tool/verification 步骤 | 是 |
| `operation_id` | 一个逻辑写入；create 与后续验证关联；同一写入重试保持不变 | 是 |
| `execution_id` | 单次 Tool 执行尝试；create 与 verify query 各自有 execution ID | 是 |
| `causation_request_id` | 内部 Tool 消息的外部因果来源；等于触发该执行的外部 request ID | 是 |
| `trace_id` | 建议新增为**仅日志上下文**的 opaque ID，用于覆盖尚未解析出 protocol ID 的 HTTP 请求及进程边界；不得加入/替代 V2 message contract | 否，诊断字段 |

关联关系：

```text
trace_id
└── request_id (每轮外部 HTTP 请求一个)
    └── conversation_id (多轮稳定)
        └── task_id (Resume 前后稳定)
            ├── clarification step_id(s)
            └── operation_id (逻辑写入)
                ├── create step_id + execution_id
                └── verify-query step_id + execution_id
```

一次 HTTP follow-up 使用新的 `request_id`，同一个 `conversation_id` 和 `task_id`；内部分析/Tool 的 `causation_request_id` 指向该 follow-up request。`operation_id` 不替代 `execution_id`：前者表示逻辑副作用，后者表示执行尝试。

### 3.2 可从任意 ID 追踪的最小查询路径

1. 从 JSON log 按 `request_id` 或 `trace_id` 查 `http.request.received` 到 `http.response.sent`。
2. 取日志中的 `conversation_id` / `task_id`，查 SQLite `inbound_receipts`、`tasks`、`state_transitions`、`clarifications`、`task_parameters`。
3. 从 `tool.request.created` 获取 `step_id`、`operation_id`、`execution_id`，与 `tool_exchanges` / `operations` 对照。
4. 用 `verification.*` 与 verify query exchange 确认实际字段比较结果，再看 `final.created` 和 receipt response。
5. Mac Host 本地日志仅记录同一关联 ID 和结果元数据；协议 JSON 仍只写 stdout。

## 4. Structured Logging 架构

### 4.1 格式与通用字段

建议使用标准库 logging 的 JSON formatter，每条事件一行，UTC RFC 3339 timestamp。所有组件调用统一 logger/helper，不以自由文本作为机器关联依据。

推荐字段：

```json
{
  "timestamp": "2026-09-30T08:40:00.000Z",
  "level": "INFO",
  "event": "tool.dispatch.completed",
  "component": "tool_dispatcher",
  "trace_id": "trc_<opaque>",
  "request_id": "req_<opaque>",
  "conversation_id": "conv_<opaque>",
  "task_id": "task_<opaque>",
  "step_id": "step_<opaque>",
  "operation_id": "op_<opaque>",
  "execution_id": "exec_<opaque>",
  "status": "success",
  "duration_ms": 128,
  "error_code": null
}
```

字段按阶段可为空；禁止通过伪造 ID 填充。所有 ID 都应从已验证消息或持久化实体读取。不要将 `user_request`、clarification answer、Tool arguments、ToolResult payload、Calendar title、event ID、Authorization header 或环境变量放入公共 logger context。

### 4.2 Event taxonomy

建议稳定事件名（小写点分隔、过去/完成事件使用明确语义）：

| 阶段 | 建议 event |
|---|---|
| HTTP | `http.request.received`、`http.request.auth_rejected`、`http.request.validation_rejected`、`http.request.runtime_started`、`http.response.sent` |
| Conversation | `conversation.created`、`conversation.resume.resolved`、`conversation.resume.rejected` |
| Task / Analysis | `task.created`、`task.state.changed`、`analysis.started`、`analysis.completed`、`analysis.failed` |
| Clarification | `clarification.created`、`clarification.response.received`、`clarification.resume.claimed`、`clarification.resume.rejected` |
| Parameter / Planning | `parameters.persisted`、`parameters.merged`、`planner.decision.completed` |
| Tool | `tool.request.created`、`tool.dispatch.started`、`tool.dispatch.completed`、`tool.result.received` |
| Host | `mac_host.process.started`、`mac_host.result.received`、`mac_host.process.cleaned_up` |
| Verification | `verification.started`、`verification.query.completed`、`verification.completed` |
| Final | `final.created`、`http.response.sent` |

`planner.decision.completed` 只记录 `decision_type`（clarification/tool_request/final）、object、intent、tool、parameter status counts 或 field names；不记录值或证据文本。

## 5. HTTP Access Observability

每个到达 handler 的请求都应至少形成 ingress 与 response 两条事件。Ingress 事件在解析/认证前写入，以证明请求是否到达 Server；认证失败、错误路径、body 校验失败仍需有安全的 `http.response.sent`。在尚无 protocol `request_id` 时用内部 `trace_id` 关联；解析并验证后再附加 `request_id`、`conversation_id`。生成的 server `request_id` 必须记录为同一个实际值。

最小字段：

- method、规范化 path（不记录 query string）、content length（可选）、auth outcome（只记录 pass/fail，不记录 header）。
- request_id、conversation_id 以及 `conversation_id_present`。
- HTTP status、Agent response type（clarification/final/error）、是否进入 Runtime、总 duration_ms。
- 对拒绝请求记录稳定 `error_code`，不得记录原始 body 或异常 repr。

当前 `handle_json_body()` 对缺少 conversation ID 的请求生成新 ID；因此真机 Resume 若未携带原 ID，会被当作新 conversation，而不是延续旧 Task。HTTP 日志应明确记录 `conversation_id_present=false`，但不把它误报为 Resolver 的 `NO_WAITING_TASK`。

`http.response.sent` 表示 Server 写出响应，不证明 iPhone/Siri 已收到或朗读。客户端确认需由 Shortcut Debug Mode 或用户侧 QA 记录提供。

## 6. Clarification Resume Trace

成功续接应产生类似下列事件序列：

```text
Request 1:
http.request.received (request_id=req_1, conversation_id absent/present)
conversation.created (conversation_id=conv_1)
task.created (task_id=task_1)
analysis.completed → planner.decision.completed(decision_type=clarification)
clarification.created (step_id=step_c1)
task.state.changed(received → ... → waiting_clarification)
http.response.sent(status=200, response_type=clarification)

Request 2:
http.request.received (request_id=req_2, conversation_id=conv_1)
clarification.response.received
conversation.resume.resolved(task_id=task_1, reply_to_step_id=step_c1)
clarification.resume.claimed
task.state.changed(waiting_clarification → analyzing_clarification)
analysis.completed
parameters.merged (valid/missing/ambiguous counts; changed field names only)
planner.decision.completed
...
```

拒绝原因应可从事件和 `error_code` 明确区分：

| 情况 | 诊断分类建议 | V2/当前行为边界 |
|---|---|---|
| 客户端没有发送第二轮 | `CLIENT_NOT_SENT` | Server 无法自行观察；需 Shortcut/client debug evidence |
| HTTP auth/body/path 拒绝 | `HTTP_REJECTED` | 记录 status + 安全 error code，不进入 Runtime |
| Conversation 不存在 | `CONVERSATION_NOT_FOUND` | 当前 controlled 404 |
| 没有 waiting Task | `NO_WAITING_TASK` | 当前 controlled 409 |
| 多个 waiting Task | `AMBIGUOUS_WAITING_TASK` | 当前 controlled 409，fail closed |
| current step / pending clarification 不匹配 | `INVALID_REPLY_STEP` | 当前 stale clarification 409 |
| Resume claim/analysis 失败 | `RESUME_FAILED` | 记录稳定错误类别；不可记录答案原文 |
| 参数合并失败 | `PARAMETER_MERGE_FAILED` | 记录字段名/状态摘要；不可记录值/evidence |

这些是诊断分类建议，不要求成为新的 HTTP error code，也不改变 Canonical Protocol。Client 未发送的结论只能由客户端侧日志/测试确认，不能由 Server 的“没有 receipt”推断。

## 7. Tool / Verification Trace

每次执行从持久化 ToolRequest 关联 `task_id`、`step_id`、`operation_id`（仅 write）、`execution_id`、`causation_request_id`、tool/purpose。建议事件：

```text
tool.request.created
tool.dispatch.started
mac_host.process.started
mac_host.result.received
mac_host.process.cleaned_up
tool.dispatch.completed
tool.result.received
verification.started
verification.query.completed
verification.completed
final.created
http.response.sent
```

只记录 tool 名、purpose、status、duration、错误码、结果数量、验证匹配状态；不记录 Calendar event title/details/event ID 到普通日志。SQLite 中的 Tool payload 仍按受限业务记录管理。

必须保留语义：Tool `success` 只是执行器报告成功；`Final.success` 必须有真实 verify query 的匹配证据。Verification 事件应明确记录 `decision=success|failure|unknown`、被比较字段集合（例如 `title,start,end,event_id`）和 mismatch 字段名，不记录字段值。

MacAgentHost 的 stdout 是 JSON-lines protocol，绝不能附加 log。Swift 诊断只写 stderr 或独立 logger，并携带同一关联 ID；不要把 stderr 原文无筛选地回传给客户端/普通日志。

## 8. SQLite 与运行日志职责

### SQLite：业务事实、恢复和审计

继续保存 task/step/parameter/clarification/receipt/tool exchange/operation 状态及必要的恢复 payload。数据应遵循最小权限、文件权限、备份与保留周期策略。SQLite 中现有 `original_message`、`clarifications.user_response`、Tool arguments/results 可能包含个人或日历信息，不能将其视作无敏感性的通用日志。

### Structured log：短期诊断和跨层时间线

保存低敏元数据事件、HTTP status、duration、状态转换摘要和 error code；使用本机受限文件、轮转和有限保留周期。不要把完整 LLM analysis、用户话语、澄清答案、Calendar 内容、secret 或完整 exception message 写入普通日志。

### 是否新增 trace/event table

当前不建议新增独立 event table。已有 SQLite 业务表能够作为已提交任务的状态事实；再建一份 trace event 表会复制状态、增加事务一致性与保留/隐私负担。HTTP 被拒绝的诊断由日志承担，不应为了日志把失败 ingress 塞入业务数据库。只有未来需要跨重启、跨主机的强审计查询且日志系统不能满足时，再单独评估 append-only audit store；这不是当前最小范围。

## 9. Shortcut 真机 QA Debug Mode

保持 Shortcut 为 Thin Client。开发/QA 模式可将 API response 的少量诊断字段显示在屏幕上：

- 当前是第几轮（客户端本地轮次计数，仅 UI 提示，不是 Agent ID）。
- 本轮发送前是否有 `conversation_id`；follow-up 应复用第一次 Clarification response 的 ID。
- HTTP status、response `type`（clarification/final/error）。
- 可选显示 `request_id` 与 `task_id` 供 QA 抄录；正常模式隐藏，不负责生成或管理它们。

不要把 Authorization header、token、原始完整 payload 或 Calendar event 内容显示/朗读到共享日志。Shortcut 应只解析并展示 Agent 的正式 response，不应自行执行 `Find Calendar Events` 来推断 Agent 是否写入。

当前 API 的 Clarification 包含 `conversation_id`、`task_id`、`step_id`；客户端续接只需回传 `user_request`、原 `conversation_id` 及所需 timezone。Task/step/reply/operation/execution ID 由服务端负责。

## 10. Privacy / Security 基线

**绝不记录：**Authorization/Bearer header、`AGENT_API_TOKEN`、Cloudflare token、密码、cookie、Keychain secret、其他 credential；也不记录完整 request/response body。

普通日志默认不记录：

- `user_request` 与 clarification answer。
- 日历标题、description、参加人、地点、事件时间、event identifier。
- Tool arguments/results、LLM analysis 原文和 parameter evidence。
- 完整异常文本（它可能包含输入数据、路径或响应内容）。

可以记录：经过验证的 opaque correlation IDs、HTTP method/固定 route、status、response type、tool/purpose、参数字段名与状态计数、duration、错误码、匹配与否。生产日志默认 INFO 仅元数据；本机 QA 可临时启用更详细的字段级状态，但仍不得记录 secret 或个人内容。若要采集用户文本用于诊断，应另设显式 opt-in、短保留期和严格访问控制；当前建议不做。

## 11. Agent QA Trace 使用方式

每个缺陷记录应附：

```text
QA Case ID
→ 每轮 request_id / trace_id
→ conversation_id
→ task_id
→ 相关 step_id / operation_id / execution_id
→ SQLite 业务记录与结构化日志时间线
→ 外部真实状态证据（如 Calendar 中的事件，仅 QA 受控采集）
→ 实际 Clarification / Final 状态与 HTTP status
→ 首个失败事件 / failure layer / root cause
```

报告里不要附 Authorization、用户原话、日历标题或完整事件 payload。若需可复现输入，使用 synthetic fixture、QA-safe 标题与脱敏值；真实事件证据与日志分开管理。`request_id` 未出现于 ingress log，才能说明 Server 没有观察到对应请求；要证明 CLIENT_NOT_SENT 仍需 Shortcut 侧记录。

## 12. 建议的最小实施范围（本文件仅提案，不实施）

建议后续分阶段实施：

1. **HTTP boundary**：建立 JSON logger；在认证前生成诊断 `trace_id`；记录 ingress、拒绝原因、Runtime start/end、HTTP status、response type、duration；加入 secret/body 字段排除测试。
2. **Conversation/Runtime**：围绕现有 UnitOfWork/transition 增加事件；记录 resolver 结果、task state、clarification step、Resume claim 与 merge 状态摘要。
3. **Tool/Verification**：传播已存在的 V2 IDs；记录 dispatch/host/cleanup/tool result/verification/final 阶段事件和 duration；stdout protocol 与日志严格分离。
4. **QA client display**：在既有 Shortcut 上加可选 debug 显示（不改业务语义）；至少显示 HTTP status、response type、是否携带 conversation ID，必要时显示 request/task ID。
5. **回归**：用 HTTP integration tests 断言一轮与多轮 trace 关联、失败分类以及敏感字段不出现在 logs；增加 Host contract test 保证 stdout 只含 ToolResult JSON-lines。

首阶段不调整 Protocol、SQLite schema、Calendar 行为、Cloudflare/Tunnel 或认证方案；日志配置及文件权限需沿用项目本机 service lifecycle。

## 13. 是否引入 OpenTelemetry

**当前不建议立即引入 OpenTelemetry。** 当前是单机 Mac-first 服务，SQLite 已记录业务执行事实；JSON structured logs 加 V2 ID 关联足以定位主要真机 Resume 盲区，引入 Collector/SDK/context propagation 会增加部署与隐私面。

当系统需要多个进程/主机统一 trace、远程 gateway、外部 telemetry backend 或标准化 metrics/traces 时，可再评估 OpenTelemetry。届时将 `trace_id` 映射到 W3C Trace Context，并保持 V2 `request_id` / `conversation_id` / `task_id` 等业务标识独立；不得以 OTel trace ID 替换协议相关 ID，也不得默认导出用户内容。

## 14. 本轮边界

本轮只审计和提出设计；未修改 Runtime、Server、数据库、Protocol、Schema、Shortcut、Cloudflare、Calendar 或 tests。本文中的 event taxonomy、日志字段和实施步骤均为 proposal，不表示当前已经实现。
