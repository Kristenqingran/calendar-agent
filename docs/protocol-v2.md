# Calendar Agent Protocol V2（Mac-first）

**状态：当前规范（Canonical）**
**版本：2.0.0**
**适用架构：Mac-first Personal Agent**
**历史规范：[`protocol-v1.md`](protocol-v1.md) 保持冻结，仅供历史参考，不再定义当前执行边界。**

本文定义当前产品的外部 HTTP 会话边界、Agent 内部执行消息、标识符生命周期、Mac 原生能力执行边界、幂等和验证语义。所有与实现有关的冲突以本 V2 为准；V1 原文不追改。

## 1. 目标架构与范围

```text
iPhone / Apple Watch / Siri / Shortcut
        ↓ HTTPS（用户会话）
Agent HTTP API（认证、校验、请求去重）
        ↓
AgentRuntime（任务状态、持久化、编排）
        ↓
Semantic Analysis → Planner → Workflow
        ↓ 内部 ToolRequest
ToolDispatcher → MacAgentHostAdapter
        ↓ JSON-lines 本地 IPC
MacAgentHost.app → CapabilityRegistry → CalendarCapability → EventKit
        ↓ 内部 ToolResult
AgentRuntime → VerificationService → Final
        ↓
Agent HTTP API → 用户客户端
```

用户客户端只负责收集用户输入、发送会话请求、展示或朗读 Clarification/Final。Shortcut 不执行 Calendar Tool，不连接 EventKit，不决定执行结果。

当前已实现的真实执行范围仅为 Calendar Create 与其 `verify_state` Calendar Query。通用 Query、Reminder、Calendar Update/Delete 等协议形状可用于演进和类型校验，但未因此获得可执行能力；不得宣称这些操作可用。

V2 不要求 VPS、WebSocket、CalDAV、iCloud token、Cloudflare、VPN 或其他远程执行节点。MacAgentHost 是当前 Mac 的本地执行 Host。

## 2. 外部 HTTP 会话边界

`POST /agent` 是用户会话入口，不是 Tool endpoint。Transport 层负责鉴权、大小限制、JSON 校验、ID 校验、规范化 UserRequest、Runtime 调用和响应序列化。AgentRuntime、Planner、Workflow、Dispatcher、Host 与 Capability 不感知 HTTP、LAN、iPhone、Watch、Siri 或 Tunnel。

规范化后的 `UserRequest` 含 `request_id`、`conversation_id`、`message`、`current_time`、`assistant_timezone`、`source`，以及可选的 `device_timezone`、`default_calendar`。外部请求可提交 `user_request`、可选的 `conversation_id` 和可选的 `assistant_timezone`。Server 为每个未提供 `request_id` 的 inbound HTTP 请求生成新的 ID；需要幂等重放时，客户端可提交稳定的 `request_id`，并在同一次 HTTP 重试时复用相同 ID 与相同请求内容。继续 clarification 时，客户端复用响应中的 `conversation_id`，但不提交 task/step/operation/execution ID。

每个外部请求的成功响应类型只能是 `clarification` 或 `final`。内部 `tool_request` 不得序列化为 Agent API 响应。Runtime 若无法得到公开响应，HTTP 层必须返回明确的边界错误，而不能把内部执行命令暴露给用户客户端。

`AgentResponse` 的 V2 联合仅包含 `Clarification | Final`。外部 follow-up 仍使用 `/agent` 和 `user_request`，携带原 `conversation_id`；HTTP/Conversation 层从持久化状态中唯一解析 pending Task 与 clarification step，并在内部构造带有服务端 `task_id` / `reply_to_step_id` 的强类型 `ClarificationResponse`。若不存在唯一 pending clarification，HTTP 返回受控 404/409，绝不新建任务或执行写入。`request_id` 每个新 HTTP inbound 轮次新生成；客户端重试同一轮时可复用它。

## 3. ID 生命周期与关联

| ID | 所有者 / 范围 | V2 规则 |
|---|---|---|
| `request_id` | 外部 HTTP 用户请求 | 标识一个 inbound 轮次；未提供时由 Server 新生成。需要幂等重放时，同一轮 HTTP 重试必须复用。Clarification/Final 回显触发该响应的 request ID。 |
| `conversation_id` | 用户会话 | 跨轮次保持；响应必须与当前请求一致。 |
| `task_id` | Runtime 持久任务 | 由 Runtime 生成；澄清续接恢复同一持久 Task，客户端不管理该 ID。 |
| `step_id` | Task 中单个执行步骤 | 每个 Tool 执行步骤唯一；verification query 使用自己的 step ID。 |
| `operation_id` | 一项逻辑写入 | 对该逻辑写入稳定；未知结果后的重试不得改成新逻辑操作。Query 不得携带 operation ID。 |
| `execution_id` | 一次 Tool 执行尝试 | 每次尝试唯一，格式 `exec_<opaque-id>`；重试同一 operation 时必须生成新 execution ID。 |
| `causation_request_id` | 内部 Tool 消息的因果来源 | 等于触发该 Tool 执行的外部 HTTP `request_id`；它不是新的 HTTP 请求 ID。 |

内部 `ToolRequest → ToolResult` 必须原样保留 `execution_id`、`causation_request_id`、`conversation_id`、`task_id`、`step_id`、`tool` 和（写操作）`operation_id`。Dispatcher 与 Runtime 必须校验它们与已持久化 ToolRequest 的一致性。ToolResult 不生成、不伪造外部 `request_id`。

## 4. 内部 Tool 执行消息

`ToolRequest` 是 AgentRuntime 发给 ToolDispatcher 的内部执行命令。它不会返回给 iPhone/Watch，也不会由用户客户端执行。ToolDispatcher 只按 `tool` 选择一个 Adapter，传递原参数，校验 Adapter 的 `ToolResult` 与相关 ID；不得理解自然语言或改写参数。

`ToolResult` 是 ToolAdapter/MacAgentHost 返回给同一 Runtime 调用栈的内部执行结果，不是新的 HTTP inbound message。它必须符合 `tool-result-v2.schema.json` 和 Python contract。`success` 只代表该 Tool 的执行器报告成功，不代表用户目标已最终成功。

当前 Mac Host 支持范围：

| Tool | 当前 V2 运行状态 | 备注 |
|---|---|---|
| `create_calendar_event` | 已实现 | EventKit Create，返回真实 event identifier；仅在真实 Query 验证后允许 Final.success。 |
| `query_calendar` | 已实现为内部验证查询 | 当前主要供 Create 的 `purpose=verify_state` 使用；不代表已开放一般 Calendar 查询产品能力。 |
| `create_reminder` | 未实现 | 不可执行。 |
| Calendar Update/Delete | 未实现 | 不可执行。 |
| Reminder Query/Update/Delete | 未实现 | 不可执行。 |

## 5. 写入幂等、重复请求与未知状态

Runtime/Persistence 拥有用户请求收据与逻辑 Operation 状态。收到相同 `request_id`：

1. 请求内容 hash 一致且已有最终响应：回放保存的同一响应，不重新分析或重复执行。
2. 相同 ID 但用户意图/显式上下文不同：返回 `idempotency_conflict`，不执行 Tool。
3. 收据存在但尚无最终响应：返回 `unknown/request_in_progress`，不得再次派发写入。

`operation_id` 代表逻辑写入，`execution_id` 代表一次执行尝试。Adapter timeout、Host 消失或写入结果不能确认时必须返回 `unknown`，不能自动重试。任何后续重试必须先通过 `verify_state` 检查真实 Calendar 状态；若确认不存在，才可以在同一个 `operation_id` 下以新的 `execution_id` 发起受控重试。

MacAgentHost 围绕 `operation_id` 使用本机持久化 journal：相同参数的已完成操作重放保存结果；相同 ID 的不同参数冲突；遗留的 `started` 操作返回 unknown，要求 Runtime 先查询真实状态。Runtime 的 SQLite receipt/Operation 提供 Agent 侧持久化去重。EventKit 与两侧 journal 均无共同事务，EventKit 已写入但 Host 结果未落盘的 crash window 仍须通过查询恢复；系统不宣称 exactly-once。

## 6. Verification 与 Final

所有 Calendar 写入必须经过 Runtime 的代码控制预检和结果验证。对 Create：

```text
ToolRequest(create)
→ EventKit ToolResult
→ ToolRequest(query_calendar, purpose=verify_state)
→ EventKit 实际状态
→ VerificationService 比较 event ID（若可用）、title、start、end
→ Final
```

- `Final.success`：Create 有成功结果，且真实 Calendar Query 找到字段匹配的目标 Event。
- `Final.failure`：执行器明确报告操作失败，或成功查询确认目标状态与计划不一致/不存在。
- `Final.unknown`：执行超时、状态查询失败或证据不足，不能判定成功/失败。

不得仅凭 Create 返回 success 判定 Final.success；不得通过放宽字段匹配、伪造 event ID 或用 Host 回显的请求参数冒充真实 Query 来通过验证。当前实现应使用 EventKit query 返回实际 Calendar 事件字段。

## 7. Clarification 与工作流状态

Clarification 是 Agent API 的用户响应。客户端应展示/朗读并把回答作为下一次 `user_request` 提交，同时复用原 `conversation_id`。Server 只在该 conversation 下恰有一个当前等待澄清的 Task、且 current step 与唯一 unresolved clarification 一致时才恢复。Runtime 内部使用强类型 `ClarificationResponse` 精确关联原 `task_id` 和 `reply_to_step_id`，并持久化每轮回答。

状态路径为 `waiting_clarification → analyzing_clarification → planning`；若仍缺参数则创建新的 clarification step 并回到 `waiting_clarification`，否则走既有 pre-execution、Tool、Verification、Final 路径。有效的已保存参数、原始请求、澄清问答、response language 和 assistant timezone 会在续接时保留；新明确回答可补充或修正参数。最多接受五条澄清回答，超限结束原 Task 且不派发 Tool。已完成 Task、错误 conversation、无待澄清 Task、状态不一致和多个等待 Task 均 fail closed。HTTP inbound receipt 与 Task claim 提供重放/并发保护；重试同一 `request_id` 会重放保存的响应，不会再次创建事件。

当前可运行的 Calendar Create 不要求澄清恢复。Reminder 与 Calendar 更新/删除不在当前执行范围。

## 8. 认证与安全边界

HTTP API 在进入 Runtime 前执行认证与请求校验。当前部署可以使用 Bearer API token；Token 只从受保护的本机配置读取，不得日志记录或进入 Tool payload。Agent Core 与 MacAgentHost 之间是本地受控 IPC，不应由用户客户端直接调用 Host。

`127.0.0.1` 是当前默认监听边界。监听其他 interface 需要显式配置和认证；这不等于允许公网开放端口。V2 不要求更改 VPN、路由、防火墙或远程隧道。

## 9. Schema 与实现状态

本目录中的 `*-v2.schema.json` 是 V2 contract。V1 schema 保留且不改写，只用于历史一致性检查。V2 的外部 schemas 是 `inbound-v2` 与 `agent-response-v2`；内部 schemas 是 `tool-request-v2` 与 `tool-result-v2`；Common、Calendar、Reminder、LLM Analysis schema 均按 V2 版本引用。

本规范描述允许的合同和边界，不代表每种 Tool 已实现。实现能力以第 4 节运行状态表、CapabilityRegistry 注册项和对应自动化/真实 QA 证据为准。

## 10. 非目标与后续

本次迁移不实现 Reminder、Calendar Update/Delete、Shortcut、VPS、WebSocket、CalDAV、iCloud token 或真实 LLM provider。Clarification Resume 已通过 SQLite 持久化和 HTTP integration tests 实现；真实 iPhone/Siri multi-turn 回归仍待用户端验证。EventKit 与 Host journal 的 crash window 仍是开放可靠性问题。后续实现这些能力必须保持本协议的 ID、执行边界、幂等与 Verification 语义；不得修改冻结的 V1 文件来追溯改写历史。
