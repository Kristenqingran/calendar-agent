# Runtime Contract V1（Historical）

> **状态：HISTORICAL / SUPERSEDED。** 本文记录 Protocol V1 阶段的 Runtime 边界，内容中“客户端执行 Tool”“ToolResult 是外部 inbound”等规则不适用于当前 Mac-first Protocol V2。当前规范请见 [`protocol-v2.md`](protocol-v2.md) 与 [`architecture/adr/ADR-001-mac-first-tool-execution.md`](architecture/adr/ADR-001-mac-first-tool-execution.md)。本文保留用于历史追溯，不作为当前实现依据。

状态：Phase 1 boundary definition  
依据：`docs/protocol-v1.md`、现有 Pydantic models、现有 state machine、现有 Repository。

本文档只冻结未来 Agent runtime 的边界，不实现 Agent、HTTP、LLM、Planner、Tool Executor 或完整 workflow。

## 1. Agent Core

Agent Core 接收现有 `InboundMessage` union：

- `UserRequest`：创建或恢复用户目标对应的 Task，并进入语义分析/规划边界。
- `ClarificationResponse`：按 `conversation_id`、`task_id` 和 `reply_to_step_id` 恢复等待澄清的 Task。
- `ToolResult`：按 `conversation_id`、`task_id`、`step_id`、`tool` 和写操作的 `operation_id` 恢复等待 Tool Result 的 Task。

Agent Core 输出现有 `AgentResponse` union：

- `ToolRequest`：请求外部 Tool Executor 执行一个查询或写操作。
- `Clarification`：暂停当前 Task，请用户补充或确认信息。
- `Final`：Task 进入最终反馈阶段，状态为 `success`、`failure` 或 `unknown`。

Runtime interface 使用 `AgentCore.handle(InboundMessage) -> AgentResponse`。本接口不定义 HTTP transport，也不实现 workflow。

## 2. Correlation

- `request_id`：每个入站 HTTP 请求唯一，由外部发送方生成；用于入站 receipt 和响应关联。
- `conversation_id`：客户端维护的一段连续对话标识；用于恢复同一对话上下文。
- `task_id`：Agent 为一个用户目标生成；新 `user_request` 创建，后续 clarification/tool result 使用已有值。
- `step_id`：Agent 为一次决策或 Tool 往返生成；Tool Result 使用对应 Tool Request 的原值。
- `operation_id`：只用于逻辑写操作；写 Tool Request 和对应写 Tool Result 必须使用同一值，重试复用该值。

查询 Tool 不使用 `operation_id`；写 Tool 必须使用 `operation_id`。本阶段不实现 ID 生成、correlation guard 或 operation lifecycle。

## 3. External Adapter Boundary

```text
External Adapter → InboundMessage → AgentCore → AgentResponse → External Adapter
```

External Adapter 负责 transport、JSON 编解码和把外部 payload 转换为现有 Pydantic message model。当前 Protocol 未定义 authentication/authorization contract，因此本阶段不增加这些边界。

Agent Core 负责 message-level validation、Task loading/creation、状态判断和未来的 workflow decision；具体实现延后。

External Adapter 负责序列化 AgentResponse、HTTP response 和 Shortcut transport。Agent Core 不负责这些 transport 细节。

## 4. LLM Adapter

LLM Adapter 的已确认输入边界是现有 `UserRequest`，可带与当前 Task 相关的只读 context。当前仓库没有正式的 context model，因此接口使用 `Mapping[str, Any] | None`，不新增领域模型。

当前仓库存在 `system-prompt.txt` 和 `schemas/llm-analysis-v1.schema.json`，但没有 LLM consumer，且 Protocol 没有明确该 Schema 的正式 runtime 地位。因此当前只冻结 adapter boundary，不把该 Schema 宣布为已确认的正式运行时 contract。

LLM 可以负责：semantic understanding、Intent/Object understanding、parameter extraction、ambiguity identification、clarification need。

LLM 不负责：state machine、persistence、database writes、Tool execution、idempotency、safety gate、final real-state verification 或 Task success determination。

timeout、malformed output、Schema validation failure 和 retry 的具体次数/backoff 当前未由 Protocol 或代码确定，留待后续 runtime contract clarification。

## 5. Tool Adapter

```text
AgentCore → ToolRequest → External Tool Executor / Shortcut → ToolResult → AgentCore
```

Agent Core 产生现有 `ToolRequest` union。真实 Calendar/Reminders 访问由外部客户端/Shortcut Tool Executor 执行；Backend Agent 不直接访问这些资源。

Tool Adapter 使用现有 `ToolAdapter.execute(ToolRequest) -> ToolResult` 边界。本阶段不实现 executor、transport 或 Tool dispatcher。

Tool Result 的 Schema/Pydantic validation 负责消息结构；Runtime correlation 负责与历史 Task/Step/Tool/Operation 的关联。后者不放入 Schema/Pydantic model。

## 6. Validation Boundary

Pydantic 当前负责 runtime model validation：

- `InboundMessage`
- `AgentResponse`
- `ToolRequest`
- `ToolResult`
- datetime offset
- IANA timezone
- discriminator
- field-level and model-level conditions

JSON Schema 当前用于：

- machine-readable protocol artifacts
- fixture validation
- Schema meta validation
- Pydantic/Schema parity tests

当前仓库没有证据证明生产 Agent 已接入 JSON Schema validator。Runtime 应至少使用 Pydantic model validation；是否在外部 HTTP boundary 同时执行 JSON Schema，留待实际 transport contract 确认。

state correlation、idempotency、stale result、Task state 和 operation lifecycle 属于 Runtime/State/Repository，不放入 JSON Schema/Pydantic。

## 7. State Machine / Repository Dependency

Runtime 必须通过现有 State Machine 和 Repository 交互，不直接操作 SQLAlchemy persistence/database。

现有可依赖能力包括：

- Task create/get/update/snapshot
- Step create/get/complete
- ToolExchange save/get/save_result/invalidate
- Operation create_or_replay/get/mark_dispatched/record_result/record_verification
- Clarification save/get_pending/resolve
- InboundReceipt accept/get
- State transition audit

现有 `TaskStatus`、`StepStatus`、`ExchangeStatus`、`ALLOWED_TRANSITIONS` 和 `TERMINAL_STATES` 在本阶段不修改。

完整 contextual correlation、stale/replay policy、clarification atomic update、restart recovery 和 workflow orchestration 依赖未来 service/runtime implementation；本阶段只冻结依赖，不实现。
