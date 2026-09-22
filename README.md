# Calendar Agent V1（日程管家）

Calendar Agent 接收客户端传入的自然语言日程请求和上下文，识别 Calendar Event 或 Reminder 的 Query、Create、Update、Delete 意图，并返回结构化 `tool_request`、`clarification`或 `final`。

V1 的唯一规范是 [`docs/protocol-v1.md`](docs/protocol-v1.md)。本 README 只提供使用摘要，不定义独立规则。

## V1 数据流

```text
iPhone Shortcut
→ HTTP API
→ Schedule Agent
→ Calendar / Reminders Tool Request
→ Shortcut 本地执行 Tool
→ Tool Result 回传 Agent
→ clarification / final
```

Agent 后端不持有 Apple Calendar / Reminders 权限。所有真实读取和写入均由 iPhone Shortcut 本地执行。

## 支持范围

- Object：`calendar_event`、`reminder`
- Intent：`query`、`create`、`update`、`delete`
- 查询 Tool：`query_calendar`、`query_reminders`
- 写 Tool：Calendar Event 与 Reminder 的 Create、Update、Delete
- 顶层响应：`tool_request`、`clarification`、`final`
- 有限、串行的多步骤任务；每次最多返回一个 Tool Request
- 明确表达的全天 Calendar Event
- Reminder 查询范围：`all_incomplete`、`specific_list`、`time_range`

V1 不使用 Hermes，不接入 Gmail、Feishu 或 Research Agent，不使用复杂多 Agent，不执行高风险批量删除或批量修改。

## 核心规则摘要

- LLM 负责自然语言理解和语义判断。
- Schema 校验、状态管理、幂等、Tool Result 校验、安全门和成功判定由代码负责。
- 可以唯一推导，但不得猜测关键日期、时间、时长或目标。
- Calendar Event 不使用默认时长。
- 未明确表达全天时，不得因缺少具体时间而自动创建全天 Event。
- Reminder Create / Update 前必须查询 Calendar 并检查时间合理性。
- 所有 Tool Result 必须回传 Agent。
- 所有 Create / Update / Delete 在成功前必须通过 `verify_state`确认真实状态。
- Tool Success、LLM 输出或 Tool Request 本身都不等于 Task Success。
- 相同逻辑写操作重试必须复用原 `operation_id`。

## 入站消息

- `user_request`
- `clarification_response`
- `tool_result`

用户请求采用 `message`、`current_time`、`assistant_timezone`、`source`等 V1 字段；旧字段 `text`、`now`、`timezone`、`calendar`不兼容。

`default_calendar`是包含 `calendar_id`和 `name`的对象。`calendar_id`允许为空；Calendar 名称不得冒充稳定 ID。

## Agent 响应

- `tool_request`：要求客户端执行一个查询或写 Tool。
- `clarification`：暂停当前任务，请求用户补充或确认。
- `final`：任务终态，状态为 `success`、`failure`或 `unknown`。

客户端必须把 Tool Result 连同任务关联 ID 回传 Agent。写操作还必须回传原 `operation_id`。

## Schema

- [`schemas/inbound-v1.schema.json`](schemas/inbound-v1.schema.json)
- [`schemas/agent-response-v1.schema.json`](schemas/agent-response-v1.schema.json)
- [`schemas/tool-request-v1.schema.json`](schemas/tool-request-v1.schema.json)
- [`schemas/tool-result-v1.schema.json`](schemas/tool-result-v1.schema.json)
- [`schemas/common-v1.schema.json`](schemas/common-v1.schema.json)
- [`schemas/calendar-v1.schema.json`](schemas/calendar-v1.schema.json)
- [`schemas/reminder-v1.schema.json`](schemas/reminder-v1.schema.json)
- [`schemas/llm-analysis-v1.schema.json`](schemas/llm-analysis-v1.schema.json)

根目录 `schema.json`已经废弃，仅保留为指向版本化 Agent Response Schema 的兼容入口。

## 设计文档

- [`01-岗位卡.md`](01-岗位卡.md)
- [`02-工作流卡片.md`](02-工作流卡片.md)
- [`02-工作流程.md`](02-工作流程.md)
- [`03-流程图.md`](03-流程图.md)
- [`docs/protocol-v1.md`](docs/protocol-v1.md)
