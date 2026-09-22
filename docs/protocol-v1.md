# Calendar Agent Protocol V1

状态：Frozen  
规范版本：`1.0.0`  
适用范围：calendar-agent V1

本文档是 calendar-agent V1 的唯一 Canonical Specification。README、JSON Schema、System Prompt、岗位卡、工作流和流程图都必须与本文档一致；存在冲突时，以本文档为准。

## 1. V1 范围

V1 只覆盖以下闭环：

`自然语言客户端 → HTTP API → Schedule Agent → Tool Request → Tool Result → clarification / final`

V1 使用单 Agent，支持 Calendar Event 与 Reminder 的查询、创建、修改和删除。Calendar / Reminders 的真实读取和写入由客户端本地 Tool 完成；Agent 后端不持有相关访问权限。

V1 不包含：

- Hermes。
- Gmail、Feishu、Research Agent。
- 多 Agent 编排。
- 并行 Tool 执行。
- 通用事务编排。
- 复杂自动补偿。
- 单个写步骤通过范围、条件、集合或模糊多目标选择，一次预期影响多个现有对象的高风险批量删除或批量修改。
- 旧版字段或旧版响应协议兼容。

## 2. 规范优先级

1. 本文档 `docs/protocol-v1.md`。
2. `schemas/*.schema.json` 机器可读协议。
3. `01-岗位卡.md`、`02-工作流卡片.md`、`02-工作流程.md`。
4. `03-流程图.md`。
5. `README.md`。
6. `system-prompt.txt`。

低优先级文件不得新增、放宽或覆盖高优先级规则。System Prompt 只约束 LLM 的语义分析行为；状态、校验、幂等、安全门和成功判定必须由代码执行。

## 3. RFC 2119 术语

- MUST：必须执行，没有例外。
- MUST NOT：禁止执行。
- SHOULD：通常应执行，只有明确理由时才可偏离。
- MAY：可选行为。

## 4. 协议词汇表

所有 JSON 枚举值 MUST 使用小写 `snake_case`。

### 4.1 Object

| 值 | 含义 |
|---|---|
| `calendar_event` | 有开始和结束、占用时间段的日程事件 |
| `reminder` | 单点提醒或不占用时间段的待办 |

### 4.2 Intent

| 值 | 含义 |
|---|---|
| `query` | 查询现有状态 |
| `create` | 新增对象 |
| `update` | 修改已有对象 |
| `delete` | 删除已有对象 |

`clarification`不是 Intent。

### 4.3 Tool

查询 Tool：

- `query_calendar`
- `query_reminders`

写入 Tool：

- `create_calendar_event`
- `update_calendar_event`
- `delete_calendar_event`
- `create_reminder`
- `update_reminder`
- `delete_reminder`

### 4.4 Purpose

Purpose 只用于查询 Tool Request：

| 值 | 含义 |
|---|---|
| `answer_query` | 回答用户关于当前状态的问题 |
| `check_conflict` | 检查候选时间是否冲突 |
| `detect_duplicate` | 检查是否存在相同或高度相似事项 |
| `find_availability` | 查找满足条件的空闲窗口 |
| `resolve_target` | 定位修改或删除的真实对象 |
| `verify_state` | 验证写操作后的真实状态 |

Reminder 查询范围 `query_scope`支持：

- `all_incomplete`：全部未完成 Reminder，不要求时间范围。
- `specific_list`：指定 Reminder List，不要求时间范围。
- `time_range`：指定时间范围，必须包含 `queried_range`。

### 4.5 Task Status

- `received`
- `validating_input`
- `analyzing`
- `planning`
- `waiting_tool_result`
- `validating_tool_result`
- `waiting_clarification`
- `analyzing_clarification`
- `pre_execution_check`
- `verifying_final_state`
- `recovering`
- `succeeded`
- `failed`
- `unknown`

`succeeded`、`failed`、`unknown`是终态。

### 4.6 Tool Status

- `success`：Tool 明确完成。
- `failed`：Tool 明确失败。
- `unknown`：Tool 是否完成无法确认。

### 4.7 Operation Status

- `planned`
- `dispatched`
- `success`
- `failed`
- `unknown`
- `verified_success`
- `verified_failure`

Tool 或 Operation 的 `success`不等于 Task 的 `succeeded`。只有最终真实状态满足用户目标时，Task 才能进入 `succeeded`。

### 4.8 Response Type

Agent 每次最多返回一个顶层响应：

- `tool_request`
- `clarification`
- `final`

入站消息类型为：

- `user_request`
- `clarification_response`
- `tool_result`

## 5. ID 规则

| ID | 生成方 | 生命周期 | 用途 |
|---|---|---|---|
| `request_id` | 入站请求发送方 | 每次 HTTP 入站请求唯一 | HTTP 幂等及响应关联 |
| `conversation_id` | 客户端 | 一段连续交互 | 聚合连续对话 |
| `task_id` | Agent | 一个用户目标 | 绑定完整任务状态 |
| `step_id` | Agent | 一次 Agent 决策或 Tool 往返 | 关联 Tool Request 与 Tool Result |
| `operation_id` | Agent | 一个逻辑写操作 | 写操作幂等 |

规则：

- 每次入站 HTTP 请求 MUST 使用新的 `request_id`。
- Agent Response MUST 回显本次入站 `request_id`。
- Tool Result 是新的入站请求，因此 MUST 使用新的 `request_id`。
- Tool Result MUST 使用原 `step_id`关联 Tool Request。
- 写 Tool Result MUST 使用原 `operation_id`。
- 同一逻辑写操作的重试 MUST 复用原 `operation_id`。
- 客户端 MUST NOT 改写 Agent 生成的 `task_id`、`step_id`或 `operation_id`。

## 6. 通用格式

- 日期时间 MUST 使用 ISO 8601，并包含 UTC Offset。
- 时区 MUST 使用 IANA 时区名。
- 时间范围统一使用 `start`和 `end`，且 `end` MUST 晚于 `start`。
- 查询时间使用 `fetched_at`。
- 执行时间使用 `executed_at`。
- 未知字段 MUST 被 Schema 拒绝，除非对应 Schema 明确允许扩展。

## 7. 入站消息

### 7.1 user_request

必需字段：

- `type = user_request`
- `request_id`
- `conversation_id`
- `message`
- `current_time`
- `assistant_timezone`
- `source`

可选字段：

- `device_timezone`
- `default_calendar`

`default_calendar`使用对象结构：

```json
{
  "calendar_id": "稳定标识或 null",
  "name": "显示名称"
}
```

`calendar_id`允许为 null。客户端能取得稳定 ID 时 MUST 优先提供；`name`只用于显示和辅助识别，MUST NOT 冒充稳定 ID。

V1 不接受旧字段 `text`、`now`、`timezone`、`calendar`。

### 7.2 clarification_response

必需字段：

- `type = clarification_response`
- `request_id`
- `conversation_id`
- `task_id`
- `reply_to_step_id`
- `message`

澄清是当前任务的暂停和恢复，不是新任务。Agent MUST 保留已确认参数、有效 Tool Result 和已完成步骤。

### 7.3 tool_result

通用必需字段：

- `type = tool_result`
- `request_id`
- `conversation_id`
- `task_id`
- `step_id`
- `tool`
- `status`
- `executed_at`

写操作结果还 MUST 包含 `operation_id`。

Calendar 查询成功时：

- MUST 包含 `queried_range`。
- MUST 包含 `fetched_at`。
- MUST 包含 `results`。

Reminder 查询成功时：

- MUST 包含 `query_scope`。
- MUST 包含 `fetched_at`。
- MUST 包含 `results`。
- 仅当 `query_scope = time_range`时，MUST 包含 `queried_range`。
- 当 `query_scope = all_incomplete`或 `specific_list`时，不要求 `queried_range`。

查询状态为 `failed`或 `unknown`时：

- MUST 包含 `error`。
- MUST NOT 因为 `results`为空而解释为“没有结果”。

以上修改是 Frozen Protocol 的一致性修正，不改变既有业务行为；规范状态保持 Frozen，版本保持 `1.0.0`。

## 8. Agent 响应

### 8.1 tool_request

通用字段：

- `type = tool_request`
- `request_id`
- `conversation_id`
- `task_id`
- `step_id`
- `tool`
- `arguments`

查询请求 MUST 包含 `purpose`，MUST NOT 包含 `operation_id`。写请求 MUST 包含 `operation_id`。

Agent 决定查询对象、目的和最小充分范围。客户端 MUST 逐字段执行请求，不得重新解释自然语言或修改范围。

### 8.2 clarification

必需字段：

- `type = clarification`
- `request_id`
- `conversation_id`
- `task_id`
- `step_id`
- `reason`
- `message`
- `expected_answer`

可选字段：

- `missing_fields`
- `ambiguous_fields`
- `candidates`

Reason 支持：

- `missing_required_parameter`
- `ambiguous_parameter`
- `ambiguous_target`
- `schedule_conflict`
- `possible_duplicate`
- `tool_result_uncertain`
- `recovery_decision_required`

V1 高风险批量写请求不得进入确认后继续执行流程，而是返回不支持该操作的 `final`。

### 8.3 final

必需字段：

- `type = final`
- `request_id`
- `conversation_id`
- `task_id`
- `status`
- `message`

可选字段：

- `result_summary`
- `error`

`status`只能为 `success`、`failure`或 `unknown`。

## 9. 语义判断规则

### 9.1 Object 判断

- 需要占用时间段、安排事件、查询日程、寻找空闲时间或检查冲突时，SHOULD 使用 `calendar_event`。
- 单点提醒或不占用时间段的待办，SHOULD 使用 `reminder`。
- 会议、面试、就医、课程、预约等事项即使包含“提醒我”，也 SHOULD 使用 `calendar_event`。
- 两种 Object 都合理且无法唯一判断时，MUST 返回 `clarification`。

### 9.2 Intent 判断

- 获得现有信息：`query`。
- 新增不存在的事项：`create`。
- 改变已有事项：`update`。
- 使已有事项不再存在：`delete`。
- 事实陈述、计划、推测或背景 MUST NOT 自动转化为操作。
- 发现相似事项 MUST NOT 自动把 Create 改为 Update。

## 10. 参数规则

参数来源：

- `explicit`
- `context_derived`
- `default`

参数状态：

- `valid`
- `missing`
- `ambiguous`
- `invalid`

Agent MUST 根据 `Object + Intent`动态确定关键参数。关键参数为 `missing`或 `ambiguous`时 MUST 澄清；非关键可选参数 MAY 为空。

- 普通 Calendar Event Create MUST 有标题、日期、具体开始时间，以及时长或结束时间。
- Calendar Event MUST NOT 使用默认时长。
- 只有用户明确表达“全天”“整天”或同等语义时，Calendar Event 才可标记为全天。
- 全天 Event 使用本地日期或日期范围，不要求具体开始时间、结束时间或时长。
- 全天 Event 使用 `start_date`和 `end_date`表示本地日期范围，两端均为包含关系；单日全天 Event 的两个日期相同。
- 用户未提供具体时间但也未明确表达全天时，MUST 按关键时间参数缺失处理，MUST NOT 自动推断为全天。
- “上午”“下午”“晚上”等只能作为时间窗口，MUST NOT 自动变为具体时间。
- 相对日期只有能够根据可信上下文唯一计算时才可使用。
- 标题 MAY 安全归纳，但 MUST NOT 增加用户未提供的关键事实。
- Reminder Create / Update MUST 先读取 Calendar 状态并检查提醒时间合理性。

## 11. 查询规则

只要回答、决策或执行依赖 Calendar / Reminders 当前真实状态，Agent MUST 返回查询 Tool Request。

- 查询范围 MUST 足够且最小。
- 可靠且覆盖当前目的的最新 Tool Result SHOULD 复用。
- 参数变化、范围不足、字段缺失或相关写操作发生后，旧结果 MUST 重新验证或重新查询。
- `success + results=[]`可以表示真实无结果。
- `failed + results=[]`和 `unknown + results=[]`不得解释为无结果。
- Reminder 查询 MUST 指定 `query_scope`。`query_scope=time_range`时 MUST 包含时间范围；`all_incomplete`或 `specific_list`不得强迫用户提供时间范围。

## 12. Tool Result 校验

Agent MUST 校验：

1. ID 与 Tool 关联。
2. Tool Status。
3. 查询或操作范围。
4. 当前 Purpose 所需字段。
5. 数据格式和内部一致性。
6. 数据新鲜度。
7. 是否足以支持当前 Purpose。

不完整或不充分的 Tool Result MUST NOT 由 LLM 猜补。

## 13. 写操作安全门

创建、修改或删除前，系统 MUST 由代码检查：

1. 目标正确性。
2. 关键参数完整性。
3. 依赖状态有效性。
4. 时间冲突。
5. 重复事项。
6. Tool 与用户原始意图一致性。
7. V1 风险边界。
8. 幂等性。

任何检查未通过时 MUST NOT 生成写 Tool Request。

Update / Delete MUST 优先使用真实 Tool Result 返回的稳定对象 ID。

高风险批量写操作定义为：单个写步骤通过范围、条件、集合或模糊多目标选择，一次预期影响多个现有对象。此类删除或修改 MUST 返回 `final.status=failure`和 `error.code=unsupported_operation`，不得生成写 Tool Request，也不得通过用户确认后继续执行。

一个 Task 中包含多个彼此独立、每一步都唯一定位单一对象的串行写步骤，不属于批量操作。此类任务 MAY 按有限串行多步骤规则执行。

## 14. 幂等规则

- 每个逻辑写操作 MUST 使用唯一 `operation_id`。
- 重试同一写操作 MUST 复用原 ID。
- 相同 `operation_id`与不同参数组合 MUST 被拒绝。
- 客户端 SHOULD 保存近期执行结果。
- 再次收到已成功执行的 `operation_id`时，客户端 MUST NOT 再次写入，必须返回原结果。
- Operation 为 `unknown`时 MUST 先执行 `verify_state`，不得盲目重试。

## 15. 最终状态验证

所有 Create、Update、Delete 在返回成功前 MUST 执行 `verify_state`查询。

- Create：对象真实存在且关键字段正确。
- Update：正确对象的目标字段已变为用户要求的值。
- Delete：指定对象已不存在。
- 有限多步骤任务：所有步骤的整体最终状态符合原始目标。

Tool Success、LLM 输出或已生成 Tool Request 都不能作为 Task Success 的依据。

## 16. 有限多步骤任务

V1 MAY 支持相互关联的串行多步骤任务，但必须满足：

- 单 Agent。
- 串行执行。
- 每次最多返回一个 Tool Request。
- 每一步独立记录真实状态。
- 已成功步骤不得因后续失败而重复执行。
- 失败后只恢复尚未完成的步骤。
- UNKNOWN 必须先 `verify_state`。
- 只允许安全、确定的 retry 或 re-query。
- 不并行执行。
- 不进行通用事务编排。
- 不进行复杂自动补偿。
- 恢复决策可能改变用户原始意图时 MUST 返回 `clarification`。

## 17. 最终结果

- 整个目标完成且真实状态符合要求：`final.status=success`。
- 允许的恢复结束后仍未完成：`final.status=failure`。
- 执行结果与最终状态均无法确认：`final.status=unknown`。
- V1 不支持的确定性操作：`final.status=failure`，并使用 `error.code=unsupported_operation`。
- 多步骤任务未全部完成时整体为 `failure`，但 message MUST 如实说明已经发生的真实变化。
- 纯查询只有在查询成功时，才能把空结果表述为“没有安排”或“没有提醒”。
- 最终 message MUST 简短、自然、结果优先，不得暴露内部 Tool、JSON 或 ID。

## 18. 客户端职责

客户端 MUST：

- 生成每次入站请求的 `request_id`。
- 生成并保持 `conversation_id`。
- 按返回 `type`执行分支。
- 严格执行指定 Tool 和 Arguments。
- 不重新理解自然语言，不修改 Tool Request。
- 回传所有关联 ID 和真实 Tool Result。
- 本地防止相同 `operation_id`重复写入。
- 对 Clarification 获取用户回答并回传。
- 仅在收到 Final 后结束正常任务反馈闭环。

## 19. Agent 后端职责与禁止项

Agent 后端 MUST：

- 生成 `task_id`、`step_id`和 `operation_id`。
- 保存任务、步骤、参数、Tool Exchange 和状态迁移。
- 通过代码实施 Schema 校验、状态机、幂等、结果校验、安全门和成功判定。

Agent 后端 MUST NOT：

- 持有 Calendar / Reminders 访问权限。
- 直接读取或写入用户 Calendar / Reminders。
- 依赖 LLM 决定幂等、真实状态或最终成功。
- 执行 V1 范围之外的集成或复杂 Agent 编排。

## 20. Phase 0 一致性要求

- `README.md`只能摘要本文档，不得新增规则。
- `schemas/`必须实现本文档中的消息和枚举约束。
- `system-prompt.txt`必须删除默认时长和旧版协议，只输出受约束的语义分析结果。
- `schema.json`只作为旧入口的废弃指针，不再定义独立协议。
