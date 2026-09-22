> **Purpose:** Understand how the Calendar Agent is designed to work before performing risk analysis or test design.
## 1. System / Runtime Architecture

### 1.1 System Overview

```text
                         ┌──────────────┐
                         │     User     │
                         └──────┬───────┘
                                │
                       Natural Language
                                │
                                ↓
                    ┌────────────────────┐
                    │  Siri / Shortcut   │
                    └─────────┬──────────┘
                              │
                        user_request
                              │
                              ↓
                    ┌────────────────────┐
                    │   Backend Agent    │
                    │                    │
                    │  Agent Decision    │
                    └─────────┬──────────┘
                              │
             ┌────────────────┼────────────────┐
             ↓                ↓                ↓
      clarification      tool_request         final
             │                │                │
             ↓                ↓                ↓
         Shortcut          Shortcut         Shortcut
             │                │                │
             ↓                ↓                ↓
           User         Tool Executor        User
             │                │
             │                ↓
             │       Calendar / Reminders
             │                │
             │           tool_result
             │                │
             │                ↓
             │             Shortcut
             │                │
             │          HTTP Request
             │                │
             │                ↓
             └──────→ Backend Agent
                         │
                         ↺
                    Agent Decision
```

### Architecture Boundary

> Backend Agent does not directly access Apple Calendar or Apple Reminders.
> All Calendar / Reminders read and write operations are executed locally by the iPhone Shortcut through structured Tool Requests.

---

### 1.2 System Components

| Component                  | Responsibility                                                                                                  |
| -------------------------- | --------------------------------------------------------------------------------------------------------------- |
| **User**                   | 提出自然语言日程请求；在需要时回答澄清问题                                                                                           |
| **Siri / iPhone Shortcut** | 获取语音转写文本和上下文；构造并校验请求；通过 HTTP 与 Agent 通信；执行 Calendar / Reminders Tool；向 Agent 返回 Tool Result；向用户反馈结果             |
| **Backend Agent**          | 理解用户请求；识别 Object 和 Intent；提取和校验参数；决定是否查询真实状态；生成 `tool_request`、`clarification` 或 `final`；处理 Tool Result 并验证最终状态 |
| **Calendar Tool**          | 执行 Calendar 查询、创建、修改或删除操作                                                                                       |
| **Reminders Tool**         | 执行 Reminders 查询、创建、修改或删除操作                                                                                      |
| **Apple Calendar**         | Calendar 的实际数据和状态                                                                                               |
| **Apple Reminders**        | Reminder 的实际数据和状态                                                                                               |
| **HTTP API**               | Shortcut 与 Backend Agent 之间的通信                                                                                  |

---

### 1.3 Runtime Flow

#### 1.3.1 Initial Request

```text
User
  ↓
Siri / iPhone Shortcut
  ↓
Speech-to-Text
  ↓
获取 Context
  ├── current_time
  ├── assistant_timezone
  ├── device_timezone
  ├── default_calendar
  ├── request_id
  └── conversation_id
  ↓
构造并校验 JSON
  ↓
HTTP Request
  ↓
Backend Agent
```

#### 1.3.2 Agent Decision

```text
Backend Agent
      ↓
校验 Input
      ↓
理解 User Request
      ↓
识别 Object + Intent
      ↓
提取 / 校验 Parameters
      ↓
判断是否需要查询真实状态
      ↓
┌─────────────────┬─────────────────┬─────────────┐
│  clarification  │  tool_request   │    final    │
└────────┬────────┴────────┴────────┴──────┬──────┘
         │                 │               │
         ↓                 ↓               ↓
       User             Shortcut          User
         │                 │
         ↓                 ↓
clarification_response  Tool Execution
                           │
                           ↓
                       tool_result
                           │
                           ↓
                         Agent
```

#### 1.3.3 Tool Execution Loop

```text
Backend Agent
      ↓
tool_request
      ↓
HTTP Response
      ↓
Siri / Shortcut
      ↓
Calendar / Reminders Tool
      ↓
Apple Calendar / Reminders
      ↓
真实执行结果
      ↓
tool_result
      ↓
HTTP Request
      ↓
Backend Agent
      ↓
验证 Tool Result
      ↓
继续决策
      ├── tool_request → 下一步 Tool
      ├── clarification → 请求用户补充
      └── final → 结束任务
```

#### 1.3.4 End-to-End Task Flow

```text
                         ┌──────────────┐
                         │     User     │
                         └──────┬───────┘
                                │
                       Natural Language
                                │
                                ↓
                    ┌────────────────────┐
                    │  Siri / Shortcut   │
                    └─────────┬──────────┘
                              │
                        user_request
                              │
                              ↓
                    ┌────────────────────┐
                    │   Backend Agent    │
                    │                    │
                    │  Agent Decision    │
                    └─────────┬──────────┘
                              │
             ┌────────────────┼────────────────┐
             ↓                ↓                ↓
      clarification      tool_request         final
             │                │                │
             ↓                ↓                ↓
         Shortcut          Shortcut         Shortcut
             │                │                │
             ↓                ↓                ↓
           User         Tool Executor        User
             │                │
             │                ↓
             │       Calendar / Reminders
             │                │
             │           tool_result
             │                │
             │                ↓
             │             Shortcut
             │                │
             │          HTTP Request
             │                │
             │                ↓
             └──────→ Backend Agent
                         │
                         ↺
                    Agent Decision
```

#### 1.3.5 Runtime Characteristics

- V1 使用单 Agent、串行执行。
- 每次最多返回一个 Tool Request。
- 查询、澄清、Tool 执行和状态验证可能形成多轮循环。
- `clarification` 是当前任务的暂停，不是新任务。
- Tool 执行结果必须返回 Agent。
- Tool `success` 不等于最终 Task `success`。
- Create / Update / Delete 在最终成功前需要验证真实状态。
- Tool 执行结果为 `unknown` 时，必须先查询真实状态，不得盲目重试。
- 多步骤任务只恢复未完成步骤，已成功步骤不得重复执行。

## 2. Spec Source & Authority

### 2.1 Canonical Specification

根据当前 V1 Protocol，`docs/protocol-v1.md` 是 Calendar Agent V1 的 **Canonical Specification**。

它定义：

- Agent 与 Shortcut 之间的正式交互协议；
- Message、ID、Task / Step / Operation 状态；
- Tool Request / Tool Result；
- 协议级业务执行边界；
- Safety / Recovery / Final Verification 等协议级规则。

因此，进行 Protocol / Contract 分析时：

```text
docs/protocol-v1.md
        ↓
Canonical Specification
        ↓
schemas/*.schema.json
        ↓
Machine-readable Contract
```

### 2.2 Spec Sources and Roles

当前项目中的不同资料承担不同职责，不能把它们简单视为同一层级：

| Source | 主要作用 | Role |
|---|---|---|
| `docs/protocol-v1.md` | V1 Protocol、消息、ID、状态、Tool、协议级业务边界与安全规则 | **Canonical Specification** |
| `schemas/*.schema.json` | 将 Protocol 中可机器验证的结构约束表达为 JSON Schema | **Machine-readable Contract** |
| `01-岗位卡.md` | Agent 角色、职责、输入、输出、成功标准、人工兜底、V1 边界 | **Product / Role Spec** |
| `02-工作流程.md` | Agent 行为流程、判断逻辑、查询、澄清、Tool、恢复、最终验证 | **Behavior Spec** |
| `02-工作流卡片.md` | 完整业务流程和关键判断点补充 | **Process Supplement** |
| `03-流程图.md` | 将流程可视化 | **Process Representation** |
| `README.md` | 项目范围和架构摘要 | **Project Overview** |
| `system-prompt.txt` | LLM 语义分析行为约束 | **LLM Behavior Constraint** |

> `docs/protocol-v1.md` 是 V1 Protocol 的 Canonical Specification，但这不意味着所有 Product / Agent Behavior 都只能从 Protocol 推导。Product / Behavior 仍需要结合岗位卡和工作流程理解。

### 2.3 Authority Rule

当不同来源出现冲突时，先判断冲突属于哪一类：

1. **Protocol / Contract 冲突**
   - 以 `docs/protocol-v1.md` 作为 V1 Protocol 的主要依据。
   - `schemas/*.schema.json` 应与 Protocol 保持一致。
   - 如果 Schema 与 Protocol 不一致，应记录为 Contract / Schema Parity Issue，而不是直接把 Schema 当成新的业务规则。

2. **Product / Agent Behavior 冲突**
   - 结合 `01-岗位卡.md` 和 `02-工作流程.md` 判断 Expected Behavior。
   - 不应因为当前代码这样实现，就反向认为这就是正确行为。

3. **Process Representation 冲突**
   - `03-流程图.md` 和工作流卡片用于表达流程。
   - 如果图示与正式文字规则冲突，需要记录并进一步确认，而不是让图示自动覆盖文字规则。

4. **LLM Behavior 冲突**
   - `system-prompt.txt` 用于约束 LLM 语义分析。
   - 状态、校验、幂等、安全门和最终成功判定不能只依赖 Prompt。

5. **Implementation 冲突**
   - `src/` 和 `tests/` 用于判断当前系统实际上实现了什么。
   - Implementation 是 Actual Behavior 的证据，不是 Spec Authority。

### 2.4 Artifact Inventory

本节记录当前 QA 已发现、并可能影响 Agent 行为的主要资料。

| Category | Artifact | Location | Role | Status |
|---|---|---|---|---|
| Canonical Protocol | Protocol V1 | `docs/protocol-v1.md` | **Canonical Specification** | Found |
| Product / Role | 岗位卡 | `01-岗位卡.md` | Product / Role Spec | Found |
| Behavior | 工作流程 | `02-工作流程.md` | Behavior Spec | Found |
| Process | 工作流卡片 | `02-工作流卡片.md` | Process Supplement | Found |
| Process | 流程图 | `03-流程图.md` | Process Representation | Found |
| Project Overview | README | `README.md` | Project Overview | Found |
| LLM Behavior | System Prompt | `system-prompt.txt` | LLM Behavior Constraint | Found |
| Contract | Common Schema | `schemas/common-v1.schema.json` | Machine-readable Contract | Found |
| Contract | Inbound Schema | `schemas/inbound-v1.schema.json` | Machine-readable Contract | Found |
| Contract | Agent Response Schema | `schemas/agent-response-v1.schema.json` | Machine-readable Contract | Found |
| Contract | Tool Request Schema | `schemas/tool-request-v1.schema.json` | Machine-readable Contract | Found |
| Contract | Tool Result Schema | `schemas/tool-result-v1.schema.json` | Machine-readable Contract | Found |
| Domain Model | Calendar Schema | `schemas/calendar-v1.schema.json` | Domain Contract | Found |
| Domain Model | Reminder Schema | `schemas/reminder-v1.schema.json` | Domain Contract | Found |
| Internal Analysis | LLM Analysis Schema | `schemas/llm-analysis-v1.schema.json` | Internal Analysis Contract | Found |
| Implementation | Protocol / Domain / Persistence | `src/calendar_agent_protocol/` | Actual Behavior Evidence | Found |
| Tests | Contract / Domain / Message Tests | `tests/` | Verification Evidence | Found |
| Evaluation | Dedicated Evaluation Dataset | Current inspected repository | Evaluation Evidence | Not confirmed |

### 2.5 Protocol / Schema / Runtime Responsibility

需要区分以下四类规则：

```text
Protocol
  ↓
定义完整交互语义和协议级业务边界

Schema
  ↓
表达机器可验证的结构约束

Runtime / State
  ↓
执行跨消息、状态、幂等、关联和运行时业务规则

External State
  ↓
验证真实 Calendar / Reminder 状态
```

例如：

- 字段是否存在、类型是否正确：Schema；
- `end > start` 这类跨字段关系：当前由 Pydantic / Domain 层承担；
- `step_id` 是否匹配当前等待步骤：Runtime / State；
- `operation_id` 是否已经成功执行：Runtime / Persistence；
- Create 后对象是否真的存在：External State / Final Verification。

因此：

> Protocol 与 Schema 不完全相同，不应自动判定 Schema 为 Defect。需要先判断该规则属于 Schema、Runtime、Business Behavior 还是 External State。

### 2.6 Implementation as Evidence

`src/` 和 `tests/` 用于回答：

> 当前系统实际上实现了什么？

它们不是 Spec Authority。

QA 分析应保持：

```text
Spec / Canonical Protocol
      ↓
Expected Behavior
      ↓
Implementation Evidence
      ↓
Actual Behavior
```

而不是：

```text
Implementation
      ↓
反向定义 Expected Behavior
```

## 3. Product / Business Behavior

### 3.1 Product Purpose

Calendar Agent V1 的目标是：

> 将用户关于 Calendar Event 和 Reminder 的自然语言请求，转换为安全、可验证、可恢复的查询或写入操作，并使最终反馈与真实系统状态一致。

Backend Agent 不直接访问 Apple Calendar 或 Apple Reminders；真实 Calendar / Reminder 数据的读取和写入由 iPhone Shortcut 本地 Tool 执行。

### 3.2 Supported Business Objects

| Object | Meaning |
|---|---|
| `calendar_event` | Calendar 中的日程事件，包含定时事件和全天事件 |
| `reminder` | Reminder / 待办事项，可包含提醒时间 |

### 3.3 Supported Intents

| Intent | Meaning |
|---|---|
| `query` | 查询已有 Calendar / Reminder 状态 |
| `create` | 创建新的 Calendar Event / Reminder |
| `update` | 修改已有 Calendar Event / Reminder |
| `delete` | 删除已有 Calendar Event / Reminder |

`clarification` 不是业务 Intent，而是 Agent 在信息不足或存在歧义时暂停当前 Task 的一种响应。

### 3.4 Calendar Event Behavior

Calendar Event 用于需要进入 Calendar 的日程安排。

#### Timed Event

需要：

```text
all_day = false
start
end
```

并满足：

```text
end > start
```

#### All-Day Event

需要：

```text
all_day = true
start_date
end_date
```

并满足：

```text
end_date >= start_date
```

Timed Event 与 All-Day Event 的字段结构不能混用。

缺少具体时间不能自动推断为 All-Day Event；只有用户明确表达全天语义，或 Spec 明确允许的等价语义，才能进入 All-Day Event 分支。

### 3.5 Reminder Behavior

Reminder 用于不需要占用 Calendar 时间段的提醒 / 待办。

当前 V1 工作流程要求 Reminder Create / Update 在执行前结合 Calendar 状态判断提醒时间是否合理。

因此业务流程需要能够形成：

```text
Reminder Create / Update
        ↓
Query Calendar
        ↓
判断时间合理性
        ↓
Write Reminder
```

### 3.6 Query Behavior

Query 用于获取真实 Calendar / Reminder 状态，并支持不同业务目的，例如：

- `answer_query`
- `check_conflict`
- `detect_duplicate`
- `find_availability`
- `resolve_target`
- `verify_state`

当后续判断依赖真实状态时，Agent 应使用 Tool Result，而不能仅根据模型推测或历史信息决定。

### 3.7 Create Behavior

Create 表示用户要求新增一个对象。

在执行写操作前，应确认：

1. 用户确实表达新增意图；
2. 必要参数完整；
3. Calendar Event 的时间结构有效；
4. 必要时完成冲突检查；
5. 必要时完成重复检查；
6. 不存在会改变执行结果的关键歧义；
7. 满足执行前安全检查。

发现相似对象并不意味着可以自动把 Create 转换为 Update。

### 3.8 Update Behavior

Update 表示修改已有对象。

必须能够唯一定位目标对象，并明确需要修改的字段。

如果存在多个合理目标，Agent 应进入 clarification，而不是自行选择一个对象。

### 3.9 Delete Behavior

Delete 表示删除已有对象。

必须使用真实、稳定、唯一的目标 ID。

V1 对高风险批量删除 / 修改存在明确边界；不能通过模糊范围、集合或多目标条件未经安全判断地一次影响多个已有对象。

### 3.10 Multi-step Behavior

V1 的任务执行采用单 Agent、串行方式：

- 每次最多一个 Tool Request；
- 多步骤任务可以形成多轮 Tool Exchange；
- 已确认成功的步骤不得重复执行；
- 失败后只恢复未完成步骤；
- Clarification 是当前 Task 的暂停，而不是自动创建新的 Task。

### 3.11 Final Success

Tool Success 不等于 Task Success。

对于 Create / Update / Delete：

```text
Tool Execution
      ↓
真实状态验证
      ↓
用户目标完成
      ↓
Task = succeeded
      ↓
Final = success
```

如果最终状态无法确认，不能仅因为 Tool 返回 success 就把整个 Task 判定为 success。

### 3.12 Current Implementation Status

| Capability | Current Evidence | Status |
|---|---|---|
| Calendar Event domain model | `types.py` / Calendar Schema | Covered |
| Reminder domain model | `types.py` / Reminder Schema | Covered |
| Query / Create / Update / Delete Tool contracts | Tool models / schemas | Covered |
| Clarification response model | `messages.py` | Covered |
| Final response model | `messages.py` | Covered |
| Complete end-to-end business orchestration | Current inspected implementation does not establish the complete runtime path | Unknown |
| Final-state verification flow | State / contract primitives exist, but complete runtime path is not established | Partial |

> 本 Section 只描述 Product / Business Behavior。具体风险、测试方法和缺陷判断留到后续 QA 阶段。
## 4. Agent Behavior (用户给 Agent 一句话以后，Agent 应该怎么理解和决定？)

### 4.1 Agent Behavior Boundary

本节描述 Backend Agent 在收到用户自然语言请求后，应该如何进行：

```text
User Request
     ↓
Understand
     ↓
Identify Object
     ↓
Identify Intent
     ↓
Extract Parameters
     ↓
Assess Missing / Ambiguous Information
     ↓
Determine Whether Real State Is Required
     ↓
Decide Next Action
     ├── clarification
     ├── query Tool
     ├── write Tool
     └── final
```

本节关注的是 **Agent 的语义理解和决策行为**。

以下内容不属于 LLM 自身职责：

- State Machine
- Schema Validation
- ID Generation
- Idempotency
- Pre-Execution Safety Gate
- Tool Result Correlation
- Final Success Judgment

这些必须由代码 / Runtime 执行。

---

### 4.2 Step 1 — Understand the User Request

Agent 首先判断用户是否真的提出了一个可执行的 Calendar / Reminders 任务。

需要区分：

- 核心任务；
- 执行参数；
- 约束条件；
- 背景信息；
- 无关内容。

只有存在明确的：

- 动作请求；
- 查询意图；
- 目标结果；
- 命令语气；

才可以认为用户提出了可执行任务。

例如：

```text
“明天下午帮我安排一个和 Alice 的会议”
```

应识别为明确任务。

而：

```text
“我明天可能要和 Alice 开会”
```

属于计划 / 可能性描述，不能自动转换为 Create。

核心原则：

> 可以唯一推导，但不可以猜测。

如果语音转写中存在少量同音字、口语省略或停顿词，但不影响关键事实判断，可以继续分析。

如果关键事实存在多个合理解释，进入 clarification。

---

### 4.3 Step 2 — Identify the Object

Agent 判断用户请求针对：

```text
calendar_event
```

还是：

```text
reminder
```

判断依据不是单纯关键词，而是用户最终希望实现的结果以及事项是否占用时间段。

#### Calendar Event

通常包括：

- 会议；
- 面试；
- 看医生；
- 上课；
- 预约；
- 需要占用某个时间段的活动；
- 查询日程；
- 查询空闲时间；
- 检查时间冲突。

#### Reminder

通常包括：

- 单点提醒；
- 待办事项；
- 不占用时间段的任务。

例如：

> “提醒我下午三点吃药”

通常属于 Reminder。

而：

> “下午三点提醒我去看医生，安排一个小时”

属于 Calendar Event，因为用户描述的是一个占用时间段的预约。

如果两个 Object 都存在合理解释，并且 Agent 无法唯一判断：

```text
→ clarification
```

不得自行选择。

---

### 4.4 Step 3 — Identify the Intent

Agent 根据用户希望达到的最终状态判断 Intent：

| User Goal | Intent |
|---|---|
| 获取已有信息 | `query` |
| 新增一个不存在的事项 | `create` |
| 改变已有事项 | `update` |
| 让已有事项不再存在 | `delete` |

#### Query

例如：

> “我明天下午有什么安排？”

→ `calendar_event + query`

#### Create

例如：

> “明天三点安排一个产品评审。”

→ `calendar_event + create`

#### Update

例如：

> “把明天三点的产品评审改到四点。”

→ `calendar_event + update`

#### Delete

例如：

> “取消明天三点的产品评审。”

→ `calendar_event + delete`

事实陈述、背景描述、计划或推测不能自动变成 Create / Update / Delete。

---

### 4.5 Step 4 — Extract Parameters

确定：

```text
Object + Intent
```

之后，Agent 提取完成该任务所需要的参数。

可能包括：

- title；
- date；
- start time；
- end time；
- duration；
- timezone；
- calendar；
- reminder time；
- notes；
- target object；
- target ID；
- other user constraints。

每个参数需要区分来源：

| Source | Meaning |
|---|---|
| `explicit` | 用户明确表达 |
| `context_derived` | 根据可信上下文唯一推导 |
| `default` | 使用允许的预配置默认值 |
| Missing | 用户没有提供 |
| Ambiguous | 存在多个合理解释 |

Agent 不应该把“不确定”转换成一个看似确定的值。

---

### 4.6 Step 5 — Determine Whether a Parameter Is Sufficient

Agent 根据：

```text
Object + Intent
```

动态判断哪些参数是关键参数。

例如：

#### Create Calendar Event

至少需要：

- title；
- date；
- concrete start time；
- duration 或 end time。

如果缺少 duration / end time：

```text
→ clarification
```

不得默认：

```text
30 minutes
1 hour
```

#### Update Calendar Event

需要：

- 唯一目标 Event；
- 明确需要修改的字段。

#### Delete Calendar Event

需要：

- 唯一目标 Event。

#### Create Reminder

需要：

- reminder 内容；
- 必要时需要进一步确定 reminder time；
- 并且执行前需要查询 Calendar。

---

### 4.7 Step 6 — Interpret Date and Time

Agent 可以对用户表达进行安全的语义解析。

例如：

```text
“明天”
→ context_derived

“后天”
→ context_derived

“下午3点”
→ 15:00
```

但：

```text
“周三”
```

如果当前上下文无法唯一判断是本周还是下周：

```text
→ ambiguous
→ clarification
```

同样：

```text
“下午”
“晚上”
“上午”
```

只是时间窗口，不是具体时间。

如果任务需要具体时间：

```text
time_window
    ↓
不能直接变成 exact_time
    ↓
查询 / clarification
```

---

### 4.8 Step 7 — Interpret All-Day Event

Agent 只有在用户明确表达：

```text
“全天”
“整天”
或同等明确语义
```

时，才能判断：

```text
all_day = true
```

以下情况不能自动转换成全天：

```text
用户没有提供具体时间
```

也就是说：

```text
缺少具体时间
      ≠
全天事件
```

如果 Calendar Event 缺少具体时间，而用户也没有表达全天语义：

```text
→ missing required parameter
→ clarification
```

---

### 4.9 Step 8 — Distinguish Create from Update

这是 Agent 判断中的关键边界。

如果用户说：

> “明天三点安排一个产品评审。”

默认表达的是：

```text
Create
```

即使 Calendar 中已经存在一个相似事件，也不能因为相似就自动改成 Update。

只有以下情况才可以进入 Update：

- 用户明确指向已有事项；
- 当前上下文已经唯一绑定已有对象；
- 用户确认某个已有事项就是目标对象。

因此：

```text
相似 ≠ 同一个对象
```

如果可能存在重复但无法确定：

```text
保持原始 Create Intent
        ↓
clarification
```

不能：

```text
Create → 自动 Update
```

---

### 4.10 Step 9 — Determine Whether Real State Is Required

Agent 判断：

> 当前决定是否依赖 Calendar / Reminders 的真实状态？

如果依赖，就必须查询。

例如：

> “我明天下午三点有空吗？”

必须查询 Calendar。

例如：

> “明天三点帮我安排会议。”

需要判断当前时间是否冲突、是否存在可能重复事项，因此需要查询。

例如：

> “取消明天的产品评审。”

需要先定位真实目标，因此需要：

```text
resolve_target
```

如果当前决定完全不依赖真实状态，则不需要为了查询而查询。

核心原则：

> 只要回答、决策或执行依赖真实 Calendar / Reminders 状态，就必须使用 Tool Result。

---

### 4.11 Step 10 — Determine Query Purpose

如果需要查询，Agent 还需要判断查询的业务目的。

当前 V1 支持：

| Purpose | Agent 要解决的问题 |
|---|---|
| `answer_query` | 用户问当前有什么安排 / 提醒 |
| `check_conflict` | 候选时间是否冲突 |
| `detect_duplicate` | 是否已经存在相同或高度相似事项 |
| `find_availability` | 找符合条件的空闲时间 |
| `resolve_target` | 找到需要修改 / 删除的真实对象 |
| `verify_state` | 验证写操作之后真实状态是否正确 |

这里要区分：

```text
check_conflict
```

和：

```text
detect_duplicate
```

前者判断时间是否被占用，后者判断是否存在同一 / 高度相似事项。

---

### 4.12 Step 11 — Decide Whether to Clarify

Agent 在以下情况下应该进入 `clarification`：

#### Missing

关键参数缺失：

```text
Missing
   ↓
无法安全执行
   ↓
clarification
```

例如：

> “帮我安排明天的会议。”

如果缺少具体开始时间和时长：

```text
→ clarification
```

#### Ambiguous

存在多个合理解释：

```text
Ambiguous
   ↓
不能安全唯一确定
   ↓
clarification
```

例如：

> “把周三的会议取消。”

如果存在多个周三会议：

```text
→ ambiguous_target
→ clarification
```

#### Recovery Decision

Tool Result 不确定，且系统无法安全决定下一步：

```text
tool_result_uncertain
        ↓
clarification
```

#### 高风险批量操作

V1 的高风险批量删除 / 修改不是：

```text
clarification → 用户确认 → 执行
```

而是：

```text
unsupported_operation
        ↓
final failure
```

---

### 4.13 Step 12 — Decide Whether to Generate a Tool Request

只有当：

```text
Intent 明确
+
关键参数完整
+
目标唯一
+
必要状态已查询
+
没有未解决的歧义
```

时，Agent 才进入 Tool Request 阶段。

决策可以抽象为：

```text
                User Request
                     ↓
              Understand Intent
                     ↓
               Object + Intent
                     ↓
             Required Parameters
                     ↓
          ┌──────────┴──────────┐
          ↓                     ↓
       Missing               Ambiguous
          ↓                     ↓
   clarification          clarification
          │                     │
          └──────────┬──────────┘
                     ↓
              Parameters Valid
                     ↓
          Need Real State?
             ┌───────┴───────┐
             ↓               ↓
            Yes              No
             ↓               ↓
        Query Tool           │
             ↓               │
       Validate Result       │
             └───────┬───────┘
                     ↓
             Precondition Met
                     ↓
              Tool Request
```

---

### 4.14 Step 13 — Interpret Tool Result

Tool Result 返回后，Agent 不能简单把：

```text
status = success
```

理解成：

```text
Task = success
```

Agent 需要判断：

- Result 是否属于当前 Task；
- Result 是否足以回答当前问题；
- 查询范围是否足够；
- 必要字段是否存在；
- 数据是否仍然有效；
- 下一步是否需要继续查询；
- 是否需要执行下一步操作；
- 是否需要 clarification。

特别是：

```text
success + results=[]
```

表示：

> 查询成功，但没有找到结果。

不能解释成查询失败。

而：

```text
failed / unknown
```

不能解释成没有数据。

---

### 4.15 Step 14 — Recovery Decision

如果 Tool 执行失败或结果未知，Agent 根据真实状态决定下一步。

#### Tool Result = failed

可以根据具体失败原因：

```text
retry
re-query
clarification
final failure
```

但只能进行安全且确定的恢复。

#### Tool Result = unknown

不得直接重试写操作。

必须：

```text
unknown
   ↓
verify_state
   ↓
┌───────────────┬────────────────┬────────────────┐
↓               ↓                ↓
已成功          未成功            仍无法确认
↓               ↓                ↓
视为实际成功    安全重试          保持 unknown
```

同一个逻辑写操作必须继续使用原来的 `operation_id`。

---

### 4.16 Step 15 — Final Decision

Agent 最终只能形成三类结果：

```text
success
failure
unknown
```

但最终 Success 不能来自：

```text
LLM 判断
Tool Request 已生成
Tool 返回 success
```

而必须来自：

```text
真实状态验证
        ↓
用户目标已经满足
        ↓
Task succeeded
        ↓
final.success
```

因此：

```text
Tool Success
    ≠
Task Success
```

---

### 4.17 Agent Decision Summary

整个 Agent 的语义决策可以总结为：

```text
User Natural Language
        ↓
1. Is this an actionable request?
        │
        ├── No → no Tool Request
        │
        └── Yes
              ↓
2. What Object?
   Calendar Event / Reminder
              ↓
3. What Intent?
   Query / Create / Update / Delete
              ↓
4. What parameters?
              ↓
5. Are required parameters complete?
        │
        ├── No → clarification
        │
        └── Yes
              ↓
6. Is there ambiguity?
        │
        ├── Yes → clarification
        │
        └── No
              ↓
7. Does the decision require real state?
        │
        ├── Yes → Query Tool
        │             ↓
        │       Validate Tool Result
        │
        └── No
              ↓
8. Is execution safe and sufficiently determined?
        │
        ├── No → clarification / final failure
        │
        └── Yes
              ↓
9. Generate Tool Request
              ↓
10. Receive Tool Result
              ↓
11. Validate / Recover / Verify
              ↓
12. Final
   success / failure / unknown
```

### 4.18 QA Analysis Boundary

本节定义的是：

> **Agent 在语义层面应该如何理解用户请求并决定下一步。**

后续章节分别负责：

- **Section 5**：Agent 与 Shortcut 如何通过 Protocol 通信；
- **Section 6**：Tool 能做什么、参数是什么；
- **Section 7**：Task / Step / Operation 如何生命周期流转；
- **Section 8**：Safety Boundary；
- **Section 9**：Spec 中尚未定义清楚的问题。

因此，本节不重复定义 Schema、State Machine 或 Runtime 实现细节。

## 5. Protocol / Contract (Agent 和外部系统之间到底怎么通信？)

### 5.1 Protocol Boundary

本节定义 Calendar Agent 与外部系统之间的 **机器可验证通信契约**。

这里的“外部系统”主要包括：

```text
Siri / Shortcut
      ↕
Backend Agent
      ↕
Tool Executor
      ↕
Calendar / Reminders
```

Protocol 负责定义：

- 一次消息是什么；
- 消息从哪里来、到哪里去；
- Agent 可以返回什么类型的消息；
- Tool Request 如何描述要执行的动作；
- Tool Result 如何返回执行结果；
- Task / Step / Operation 如何被关联；
- 成功、失败、未知状态如何表达；
- Clarification 如何进入交互；
- 最终结果如何表达。

Protocol **不等于 LLM Prompt**，也不等于 JSON Schema。

```text
Protocol
  ↓
定义完整交互与行为规则
  ↓
Schema
  ↓
定义可机器验证的数据结构
  ↓
Runtime / State
  ↓
负责跨消息关联、状态流转、幂等、安全门和真实状态验证
```

根据 `docs/protocol-v1.md`，V1 的 Canonical Specification 是：

```text
Calendar Agent Protocol V1
Version: 1.0.0
Status: Frozen
```

### 5.2 Protocol Authority

当前 Protocol 的权威层级为：

```text
1. docs/protocol-v1.md
2. schemas/*.schema.json
3. 01-岗位卡.md / 02-工作流卡片.md / 02-工作流程.md
4. 03-流程图.md
5. README.md
6. system-prompt.txt
```

因此 QA 分析 Protocol / Contract 时：

- `docs/protocol-v1.md` 是 Canonical Specification；
- Schema 用于表达其中可以机器验证的结构约束；
- 较低层级文档不得新增、放宽或覆盖更高层级的 Protocol 规则；
- 如果不同资料存在冲突，应以 Canonical Specification 为准，并记录冲突，而不是自行选择实现行为作为规范。

### 5.3 Protocol Scope

V1 Protocol 的交互范围为：

```text
Natural Language Client
        ↓
HTTP API
        ↓
Schedule Agent
        ↓
Tool Request
        ↓
Tool Result
        ↓
Clarification / Final
```

V1 当前支持的业务对象：

- `calendar_event`
- `reminder`

支持的 Intent：

- `query`
- `create`
- `update`
- `delete`

其中：

> `clarification` 是一种 Agent 响应类型，不是业务 Intent。

V1 的查询 / 写入 Tool：

| Object | Query | Create | Update | Delete |
|---|---|---|---|---|
| Calendar Event | `query_calendar` | `create_calendar_event` | `update_calendar_event` | `delete_calendar_event` |
| Reminder | `query_reminders` | `create_reminder` | `update_reminder` | `delete_reminder` |

V1 明确不包含：

- Hermes；
- Gmail；
- Feishu；
- Research Agent；
- Multi-Agent；
- Parallel Tool Execution；
- Generic Transaction Orchestration；
- Complex Auto-Compensation；
- High-Risk Batch Delete / Update；
- Old Fields / Old Protocol Compatibility。

### 5.4 Message Types

Protocol 的核心消息类型为：

```text
Inbound
├── user_request
├── clarification_response
└── tool_result

Agent Response
├── tool_request
├── clarification
└── final
```

可以理解为：

```text
Client
  │
  ├── user_request ───────────────→ Agent
  │
  ├── clarification_response ─────→ Agent
  │
  └── tool_result ────────────────→ Agent
  │
  ←──────────── Agent Response ────┤
              ├── tool_request
              ├── clarification
              └── final
```

### 5.5 Request Identity and Correlation

Protocol 中存在多层 ID，用于区分不同范围的请求、任务、步骤和写操作：

| ID | 作用 |
|---|---|
| `request_id` | 每一次 HTTP inbound request 的唯一标识 |
| `conversation_id` | 标识同一对话上下文 |
| `task_id` | 标识一次完整 Task |
| `step_id` | 标识 Task 中当前 / 某一步执行步骤 |
| `operation_id` | 标识一次具体写操作，用于写操作的幂等和关联 |

重要规则：

```text
每一个 HTTP inbound request
→ 都产生新的 request_id
```

因此 Tool Result 不是复用原来的 request_id，而是一次新的 inbound request。

但是 Tool Result 必须继续关联原来的执行上下文：

```text
Tool Result
├── new request_id
├── original conversation_id
├── original task_id
├── original step_id
└── write Tool Result → original operation_id
```

### 5.6 Tool Request Contract

Agent 不直接修改 Calendar / Reminders 的真实状态，而是通过 `tool_request` 请求 Tool Executor 执行。

Query Tool Request：

```text
query_calendar
query_reminders
```

Write Tool Request：

```text
create_calendar_event
update_calendar_event
delete_calendar_event
create_reminder
update_reminder
delete_reminder
```

Protocol 的关键约束是：

```text
Query Request
→ 不需要 operation_id

Write Request
→ 必须携带 operation_id
```

这一区分反映了 Query 与 Write 在幂等和状态恢复上的不同语义。

### 5.7 Tool Result Contract

Tool Executor 执行后，通过 `tool_result` 返回：

```text
success
failed
unknown
```

其中：

- `success`：Tool 已明确完成其声明的操作；
- `failed`：Tool 明确执行失败；
- `unknown`：当前无法确认操作是否真正完成。

Query 的成功结果仍然可能是空集合：

```text
success + results = []
```

表示：

> 查询成功，但没有匹配结果。

它不能被解释成 Tool Failure。

对于 `failed` / `unknown` 的 Tool Result，Protocol 要求返回相应 `error` 信息。

### 5.8 Query Contract

Calendar Query 成功时，需要能够表达：

```text
queried_range
fetched_at
results
```

Reminder Query 成功时，需要能够表达：

```text
query_scope
fetched_at
results
```

其中 `queried_range` 仅在相应的 time-range 查询语义下需要。

QA 需要区分：

```text
Query Success
    ≠
有结果
```

因此以下情况是合法的：

```text
Query Tool
    ↓
success
    ↓
results = []
    ↓
Agent 根据空结果继续决策
```

### 5.9 Write Operation Contract

所有 Calendar / Reminder 写操作均属于需要状态确认的操作：

```text
Create
Update
Delete
```

Write Request 必须带有 `operation_id`。

如果同一个逻辑写操作发生安全恢复 / 重试：

```text
Retry same logical write
        ↓
Reuse original operation_id
```

不能因为重新发送请求就生成一个全新的逻辑 `operation_id`，否则无法可靠表达同一个写操作，也会削弱幂等控制。

### 5.10 Tool Result Correlation

Tool Result 不能仅凭“字段结构正确”就被接受。

Runtime 必须进一步确认：

```text
Tool Result
   ↓
conversation_id 是否匹配？
task_id 是否匹配？
step_id 是否匹配？
tool 是否匹配当前等待的 Tool？
operation_id 是否匹配当前写操作？
是否为 stale / duplicate / unexpected result？
```

因此：

> Schema Valid ≠ Correlation Valid

Schema 可以验证字段存在和格式，但无法单独表达“这个 Tool Result 是否属于当前 Task 的当前 Step”。

### 5.11 Clarification Contract

当 Agent 无法安全地继续执行时，可以返回：

```text
clarification
```

Protocol 中定义的典型 clarification reason 包括：

- `missing_required_parameter`
- `ambiguous_parameter`
- `ambiguous_target`
- `schedule_conflict`
- `possible_duplicate`
- `tool_result_uncertain`
- `recovery_decision_required`

因此 Clarification 不是普通文本回复，而是 Protocol 中定义的一种明确交互状态。

典型流程：

```text
User Request
      ↓
Agent
      ↓
clarification
      ↓
User
      ↓
clarification_response
      ↓
Agent
      ↓
继续分析 / 执行
```

### 5.12 Task / Tool / Operation Status Contract

Protocol 分别定义 Task、Tool、Operation 的状态语义。

Task Status：

```text
received
validating_input
analyzing
planning
waiting_tool_result
validating_tool_result
waiting_clarification
analyzing_clarification
pre_execution_check
verifying_final_state
recovering
succeeded
failed
unknown
```

Tool Status：

```text
success
failed
unknown
```

Operation Status：

```text
planned
dispatched
success
failed
unknown
verified_success
verified_failure
```

这里需要明确区分三个层次：

```text
Tool Status
    ↓
说明 Tool 自己报告了什么

Operation Status
    ↓
说明一次具体操作处于什么状态

Task Status
    ↓
说明整个用户任务处于什么状态
```

因此：

```text
Tool success
    ≠
Operation verified_success
    ≠
Task succeeded
```

### 5.13 Final Response Contract

Agent 顶层响应类型为：

```text
tool_request
clarification
final
```

最终 `final` 状态包括：

```text
success
failure
unknown
```

其核心语义是：

```text
success
→ 用户目标已完成，并且真实状态已经确认

failure
→ 在允许的恢复路径后，用户目标没有完成

unknown
→ 当前无法确认真实状态
```

因此 Agent 不能因为：

- 已生成正确的 Tool Request；
- Tool 返回 `success`；
- LLM 判断“应该已经成功”；

就直接把 Task 标记为 `success`。

### 5.14 Real-State Verification Contract

Protocol 明确要求写操作在最终成功前进行真实状态验证：

```text
Write Tool
    ↓
Tool Result
    ↓
Validate Tool Result
    ↓
Verify Real Final State
    ↓
Task Success / Failure / Unknown
```

因此：

> Tool Success 是执行层信号，不是最终业务成功信号。

真实 Calendar / Reminders 状态由本地 Client Tool 读取和写入；Backend Agent 本身没有直接访问 Calendar / Reminders 的能力。

### 5.15 UNKNOWN Contract

`unknown` 表示：

> 当前系统无法确认操作到底是否完成。

特别是 Write UNKNOWN：

```text
UNKNOWN Write Result
        ↓
verify_state
        ↓
┌───────────────┬────────────────┬─────────────────┐
↓               ↓                ↓
Verified       Confirmed        Still Unknown
Success        Not Done         
↓               ↓                ↓
Success        Safe Retry       Unknown
```

核心规则：

> **UNKNOWN Write 不能被盲目重试。**

必须先通过 `verify_state` 判断真实状态，再决定是否允许安全恢复。

### 5.16 Serial Multi-Step Contract

V1 的有限多步骤任务采用单 Agent、串行执行：

```text
Step 1
  ↓
Tool Request
  ↓
Tool Result
  ↓
Validate
  ↓
Step 2
  ↓
...
```

规则包括：

- 一次只执行一个 Tool Request；
- 已成功完成的 Step 不重复执行；
- Recovery 只处理尚未完成的 Step；
- 不做 Parallel Tool Execution；
- 不做通用 Transaction Orchestration；
- 不做复杂自动 Compensation。

### 5.17 High-Risk Batch Contract

V1 对高风险批量 Delete / Update 不采用：

```text
先确认
  ↓
再执行批量写入
```

而是按照 V1 支持范围直接返回：

```text
final failure
reason = unsupported_operation
```

因此 QA 在检查这类请求时，需要确认 Agent 不会通过自然语言确认绕过 Protocol 的能力边界。

### 5.18 Domain-Specific Contract: Calendar Event

普通 Calendar Event Create 的必要信息包括：

```text
title
date
concrete start time
(duration OR end time)
```

Protocol 明确规定：

- 没有默认 duration；
- 不能因为缺少时间就自动推断为 all-day；
- `morning / afternoon / evening` 是时间窗口，不是具体时间；
- 只有用户明确表达全天语义时，才允许 `all_day=true`。

因此：

```text
“明天下午安排会议”
```

不能直接变成一个具体开始时间的 Calendar Event Create。

如果缺少必要的 concrete start time：

```text
missing required parameter
        ↓
clarification
```

### 5.19 Domain-Specific Contract: Reminder

Reminder Create / Update 有额外的状态依赖：

```text
Reminder Create / Update
        ↓
先读取 Calendar State
        ↓
检查 reminder time 的合理性
        ↓
再执行写操作
```

这个“先查询再写入”的顺序属于 Runtime / Business Rule，不能只依靠 JSON Schema 表达。

### 5.20 Protocol vs Schema vs Runtime

QA 在检查 Contract 时必须把三个层次分开：

| Layer | 负责什么 | 示例 |
|---|---|---|
| Protocol | 完整交互与行为规则 | UNKNOWN Write 必须先 verify_state |
| Schema | 数据结构和可机器验证约束 | tool、status、required fields、enum |
| Runtime / State | 跨消息状态和执行规则 | correlation、当前 waiting step、idempotency |
| External State | 真实世界最终状态 | Calendar / Reminders 是否真的完成写入 |

因此以下情况不能简单判定为 Schema Defect：

```text
Protocol 有要求
但 JSON Schema 无法表达
```

例如：

- `end > start` 等跨字段语义；
- Tool Result correlation；
- Final Success 必须经过真实状态验证；
- Idempotency；
- UNKNOWN Recovery；
- Reminder Create / Update 必须先 Query Calendar；
- 查询结果 freshness / range sufficiency。

这些需要由 Validator、Runtime、State Machine 或外部真实状态共同保证。

### 5.21 Protocol QA Checklist

后续 QA 在验证 Protocol / Contract 时，至少需要检查：

```text
□ Message Type
□ Request / Response Direction
□ request_id
□ conversation_id
□ task_id
□ step_id
□ operation_id
□ Intent
□ Object
□ Tool Name
□ Tool Arguments
□ Query vs Write distinction
□ Tool Result status
□ Error contract
□ Clarification contract
□ Task / Tool / Operation status
□ Tool Result correlation
□ Idempotency
□ UNKNOWN handling
□ Recovery / Retry
□ Serial execution
□ Final State Verification
□ Final success / failure / unknown
□ High-risk operation boundary
□ Calendar Event semantic constraints
□ Reminder pre-query requirement
```

### 5.22 QA Analysis Boundary

本节定义的是：

> **Agent、Shortcut、Tool Executor 与外部 Calendar / Reminders 系统之间，消息如何交换，以及每类消息和状态具有什么 Contract 语义。**

后续章节再分别分析：

- **Section 6**：Tool Behavior — 每个 Tool 具体能做什么、参数是什么、返回什么；
- **Section 7**：Task / Step / Operation Lifecycle — 状态如何流转；
- **Section 8**：Safety Boundary — 哪些操作必须被阻止、拒绝或进入安全门；
- **Section 9**：Open Questions — Protocol 中仍然需要澄清的地方。

本节不把 Schema 能表达的内容扩大成完整 Runtime 规则，也不把当前实现行为反向当成 Protocol 定义。
## 6. Tool Behavior — 每个 Tool 具体能做什么、参数是什么、返回什么？

### 6.1 Tool Behavior Boundary

本节把 Section 5 的 Protocol Contract 进一步落到 **具体 Tool**。

重点回答：

```text
这个 Tool 是干什么的？
↓
什么时候可以调用？
↓
调用时必须提供什么参数？
↓
哪些参数是可选的？
↓
Tool 执行什么类型的操作？
↓
Tool Result 应该返回什么？
↓
Agent 收到 Result 后应该如何理解？
```

V1 Tool 分为两类：

```text
Query Tools
├── query_calendar
└── query_reminders

Write Tools
├── create_calendar_event
├── update_calendar_event
├── delete_calendar_event
├── create_reminder
├── update_reminder
└── delete_reminder
```

Tool 本身负责：

> 执行 Agent 已经决定好的结构化操作，并返回真实执行结果。

Tool 不负责重新理解用户自然语言，也不负责重新决定 Agent 的 Intent。

---

### 6.2 Tool 总览

| Tool | Object | Intent | 类型 | 主要作用 |
|---|---|---|---|---|
| `query_calendar` | `calendar_event` | `query` | Query | 查询 Calendar Event |
| `query_reminders` | `reminder` | `query` | Query | 查询 Reminder |
| `create_calendar_event` | `calendar_event` | `create` | Write | 创建 Calendar Event |
| `update_calendar_event` | `calendar_event` | `update` | Write | 修改已有 Calendar Event |
| `delete_calendar_event` | `calendar_event` | `delete` | Write | 删除已有 Calendar Event |
| `create_reminder` | `reminder` | `create` | Write | 创建 Reminder |
| `update_reminder` | `reminder` | `update` | Write | 修改已有 Reminder |
| `delete_reminder` | `reminder` | `delete` | Write | 删除已有 Reminder |

---

### 6.3 Common Tool Request Fields

所有 Tool Request 都包含：

```text
type
request_id
conversation_id
task_id
step_id
tool
arguments
```

Write Tool 额外需要：

```text
operation_id
```

Query Tool 额外需要：

```text
purpose
```

因此：

```text
Query Request
├── Common IDs
├── tool
├── purpose
└── arguments

Write Request
├── Common IDs
├── operation_id
├── tool
└── arguments
```

QA 需要检查：

```text
□ Tool Name 正确
□ Object 与 Tool 匹配
□ Intent 与 Tool 匹配
□ Query 是否包含 purpose
□ Query 是否错误携带 operation_id
□ Write 是否缺少 operation_id
□ Arguments 是否符合对应 Tool Contract
□ 是否出现 Schema 未允许的字段
```

---

### 6.4 Tool 01 — `query_calendar`

#### Purpose

查询 Calendar Event 的真实状态。

它可以服务于：

```text
answer_query
check_conflict
detect_duplicate
find_availability
resolve_target
verify_state
```

#### Arguments

```text
start
end
required_duration_minutes
target_id
candidate
filters
```

其中：

| Parameter | 含义 |
|---|---|
| `start` | 查询开始时间 |
| `end` | 查询结束时间 |
| `required_duration_minutes` | 查询可用时间时需要的最小时长 |
| `target_id` | 用于定位已有 Calendar Event 的目标 ID |
| `candidate` | 用于冲突 / 可用性 / 重复判断的候选对象 |
| `filters` | 额外结构化查询过滤条件 |

`start` 与 `end` 如果使用，则必须成对出现。

#### Result

成功 Query Result 至少包含：

```text
queried_range
fetched_at
results
```

其中：

```text
results
→ Calendar Event 对象列表
```

空结果是合法成功结果：

```text
success
results = []
```

表示：

> 查询成功，但指定范围内没有匹配 Event。

---

### 6.5 Tool 02 — `query_reminders`

#### Purpose

查询 Reminder 的真实状态。

支持：

```text
all_incomplete
specific_list
time_range
```

#### Arguments

##### `all_incomplete`

```text
query_scope = all_incomplete
filters?
```

不要求时间范围。

##### `specific_list`

```text
query_scope = specific_list
list_id
filters?
```

用于指定 Reminder List。

##### `time_range`

```text
query_scope = time_range
start
end
filters?
```

必须提供时间范围。

#### Result

成功 Query Result 至少包含：

```text
query_scope
fetched_at
results
```

当：

```text
query_scope = time_range
```

还必须包含：

```text
queried_range
```

同样：

```text
success + results = []
```

表示成功查询但没有匹配 Reminder。

---

### 6.6 Tool 03 — `create_calendar_event`

#### Purpose

创建新的 Calendar Event。

#### Arguments

Timed Event：

```text
title
all_day = false
start
end
calendar_id?
calendar_name?
location?
notes?
```

All-Day Event：

```text
title
all_day = true
start_date
end_date
calendar_id?
calendar_name?
location?
notes?
```

两种结构不能混用。

#### Timed Event Contract

```text
title
+
concrete start
+
end
```

其中：

```text
end > start
```

属于 Protocol / Runtime 需要保证的语义约束。

#### All-Day Event Contract

```text
all_day = true
start_date
end_date
```

只有用户明确表达全天语义时才允许使用。

#### Result

Write Tool Success 返回 Tool Result，其中包含：

```text
status = success
operation_id
result
```

`result` 表示 Tool 执行后的结构化结果。

但：

```text
Tool Success
≠
Task Success
```

Create 完成后仍需要：

```text
verify_state
```

确认真实 Calendar 状态。

---

### 6.7 Tool 04 — `update_calendar_event`

#### Purpose

修改一个已经存在的 Calendar Event。

#### Arguments

```text
event_id
calendar_id?
changes
```

其中：

```text
changes
```

至少包含一个修改字段。

允许的修改字段包括：

```text
title
start
end
all_day
start_date
end_date
location
notes
```

#### Target Contract

`event_id` 必须是已经解析得到的真实对象 ID。

因此典型流程是：

```text
User Request
↓
resolve_target
↓
query_calendar
↓
得到唯一 Event
↓
event_id
↓
update_calendar_event
```

不能只因为标题或时间相似，就把一个对象直接当成唯一 Update Target。

#### Result

成功时返回：

```text
status = success
operation_id
result
```

之后必须进行：

```text
verify_state
```

确认指定 Event 的目标字段已经变成用户要求的值。

---

### 6.8 Tool 05 — `delete_calendar_event`

#### Purpose

删除一个已经存在的 Calendar Event。

#### Arguments

```text
event_id
calendar_id?
```

#### Target Contract

必须明确指定：

```text
event_id
```

对于用户只提供自然语言描述的 Delete：

```text
User
↓
resolve_target
↓
query_calendar
↓
确定唯一 Event
↓
delete_calendar_event
```

#### Result

成功表示 Tool 执行了删除请求。

但最终成功仍需要：

```text
verify_state
```

确认目标 Event 已经不存在。

---

### 6.9 Tool 06 — `create_reminder`

#### Purpose

创建新的 Reminder。

#### Arguments

```text
title
reminder_time
list_id?
notes?
```

其中：

```text
title
reminder_time
```

为必需字段。

#### Special Precondition

Protocol 对 Reminder Create 有额外要求：

```text
create_reminder
    ↑
先 query_calendar
    ↑
检查 Calendar State
    ↑
检查 reminder time 合理性
```

因此 Tool Request 本身合法，并不意味着 Agent 可以跳过这个前置状态检查。

#### Result

成功时返回：

```text
status = success
operation_id
result
```

创建完成后仍需要：

```text
verify_state
```

---

### 6.10 Tool 07 — `update_reminder`

#### Purpose

修改已有 Reminder。

#### Arguments

```text
reminder_id
list_id?
changes
```

`changes` 至少包含一个字段。

允许修改：

```text
title
reminder_time
completed
notes
```

#### Special Precondition

与 Create 类似：

```text
update_reminder
    ↑
先读取 Calendar State
    ↑
检查 reminder time 合理性
    ↑
再执行 Update
```

#### Result

成功后仍必须验证真实 Reminder 状态。

---

### 6.11 Tool 08 — `delete_reminder`

#### Purpose

删除已有 Reminder。

#### Arguments

```text
reminder_id
list_id?
```

#### Target Contract

必须使用真实 Reminder ID：

```text
reminder_id
```

如果用户只通过自然语言描述目标，则需要先通过 Query Tool 定位目标。

#### Result

成功执行删除后仍需要：

```text
verify_state
```

确认指定 Reminder 已经不存在。

---

### 6.12 Tool Result Common Contract

Tool Result 的公共字段：

```text
type
request_id
conversation_id
task_id
step_id
tool
status
executed_at
```

Write Tool Result 还需要：

```text
operation_id
```

Tool Status：

```text
success
failed
unknown
```

不同状态的含义：

| Status | 含义 | Agent 下一步 |
|---|---|---|
| `success` | Tool 明确完成 | 校验 Result，并继续 Task |
| `failed` | Tool 明确失败 | 分析失败原因并决定恢复 / 澄清 / Final Failure |
| `unknown` | 无法确认是否完成 | 对 Write 先 `verify_state`，不得盲目重试 |

---

### 6.13 Tool Result by Query / Write

#### Query

```text
Query Tool
↓
Tool Result
↓
status
├── success
│   ├── queried_range / query_scope
│   ├── fetched_at
│   └── results
├── failed
│   └── error
└── unknown
    └── error
```

#### Write

```text
Write Tool
↓
Tool Result
↓
status
├── success
│   └── result
├── failed
│   └── error
└── unknown
    └── error
```

---

### 6.14 Tool Result 与真实业务状态

Tool Result 只说明：

> Tool 对本次执行的报告。

它不直接说明：

> 整个用户目标是否已经完成。

因此：

```text
Tool Request
↓
Tool Result
↓
Result Validation
↓
Verify State
↓
Task Decision
```

尤其是：

```text
Create
Update
Delete
```

都需要最终状态验证。

---

### 6.15 Tool Boundary

Tool Executor 的职责：

```text
接收结构化 Tool Request
        ↓
执行指定 Tool
        ↓
访问本地 Calendar / Reminders
        ↓
返回真实 Tool Result
```

Tool Executor 不应该：

```text
重新解释用户自然语言
重新决定 Intent
自动修改 Agent 参数
自动把 Create 变成 Update
自动扩大查询范围
自动执行未请求的其他操作
```

如果 Agent Request 与用户目标不一致，应在 Agent / Runtime 的决策和安全门阶段阻止，而不是让 Tool Executor 自己重新推理。

---

### 6.16 Tool QA Checklist

后续测试每个 Tool 时至少检查：

```text
□ Tool Name
□ Object
□ Intent
□ Required Arguments
□ Optional Arguments
□ Argument Type
□ Argument Boundary
□ Additional Properties
□ Query Scope
□ Purpose
□ Target ID
□ operation_id
□ Tool Result Status
□ Success Result
□ Empty Result
□ Failed Result
□ UNKNOWN Result
□ Error
□ Result Freshness
□ Result Sufficiency
□ Correlation
□ Idempotency
□ Final State Verification
```

---

### 6.17 QA Analysis Boundary

本节关注：

> **单个 Tool 的能力、输入、输出和责任边界。**

Section 5 解决的是：

```text
Agent 和外部系统如何通信？
```

Section 6 进一步解决：

```text
具体调用哪个 Tool？
Tool 接收什么？
Tool 返回什么？
Tool 做到什么边界？
```

Section 7 将进一步分析：

> 一个 Task 从创建到结束时，Task / Step / Operation 如何流转。

---

## 7. Task / Step / Operation Lifecycle — 状态如何流转？

### 7.1 Lifecycle Boundary

本节分析的不是单个 Tool，而是：

```text
一个用户 Task
    ↓
多个 Agent Decision / Step
    ↓
Tool Request / Tool Result
    ↓
Operation
    ↓
Recovery
    ↓
Final State
```

核心问题：

> **一次用户任务从进入系统到最终结束，中间的 Task、Step、Operation 分别处于什么状态？**

---

### 7.2 三层状态模型

Protocol 将生命周期拆成三个层次：

```text
Task
  ↓
Step
  ↓
Operation
```

同时存在：

```text
Tool Status
```

因此 QA 不应该把所有 `success` / `failed` 看成同一个概念。

---

### 7.3 Task Lifecycle

Task Status：

```text
received
validating_input
analyzing
planning
waiting_tool_result
validating_tool_result
waiting_clarification
analyzing_clarification
pre_execution_check
verifying_final_state
recovering
succeeded
failed
unknown
```

典型主路径：

```text
received
   ↓
validating_input
   ↓
analyzing
   ↓
planning
   ↓
pre_execution_check
   ↓
waiting_tool_result
   ↓
validating_tool_result
   ↓
verifying_final_state
   ↓
succeeded
```

但并非所有 Task 都经过完全相同的路径。

例如：

```text
缺少参数
↓
analyzing
↓
waiting_clarification
↓
analyzing_clarification
↓
planning
```

---

### 7.4 Task Terminal States

Task 的终态只有：

```text
succeeded
failed
unknown
```

含义：

#### `succeeded`

```text
用户目标已完成
+
真实最终状态已经确认
```

#### `failed`

```text
允许的恢复路径已经结束
+
用户目标仍未完成
```

#### `unknown`

```text
当前无法确认真实最终状态
```

因此：

```text
Tool success
≠
Task succeeded
```

---

### 7.5 Step Lifecycle

`step_id` 用来关联一次 Agent 决策 / Tool 往返。

典型 Tool Step：

```text
Create Step
   ↓
Tool Request
   ↓
waiting_tool_result
   ↓
Tool Result
   ↓
validating_tool_result
   ↓
Step Completed
```

一个 Step 可能对应：

```text
Query
Write
Verify
Recovery
```

关键要求：

> 已经成功完成的 Step 不应该因为后续 Step 失败而重复执行。

---

### 7.6 Operation Lifecycle

Operation 只针对具体 Write 操作。

Operation Status：

```text
planned
dispatched
success
failed
unknown
verified_success
verified_failure
```

典型 Write：

```text
planned
   ↓
dispatched
   ↓
success
   ↓
verified_success
```

失败：

```text
planned
   ↓
dispatched
   ↓
failed
```

未知：

```text
planned
   ↓
dispatched
   ↓
unknown
   ↓
verify_state
   ├── verified_success
   ├── verified_failure
   └── still unknown
```

---

### 7.7 Operation 与 operation_id

每一个逻辑 Write Operation 必须有：

```text
operation_id
```

其生命周期跨越：

```text
Original Request
↓
Tool Request
↓
Tool Result
↓
Recovery / Retry
↓
Final Verification
```

如果同一个逻辑 Write 被安全重试：

```text
Retry
↓
same operation_id
```

不能生成新的 operation_id 来伪装成新的逻辑操作。

---

### 7.8 Request / Task / Step / Operation 的关系

可以理解为：

```text
HTTP Request
    │
    └── request_id
          │
          ↓
        Task
    task_id
          │
          ├── Step 1
          │    step_id
          │
          │    └── Operation 1
          │         operation_id
          │
          ├── Step 2
          │    step_id
          │
          │    └── Operation 2
          │         operation_id
          │
          └── Final
```

但：

> `request_id` 是 HTTP 入站消息级别的 ID，不等于 Task ID。

Tool Result 会创建新的 HTTP inbound request：

```text
Original User Request
request_id = R1

Tool Request
      ↓
Tool Executor
      ↓
Tool Result
request_id = R2
```

同时保持：

```text
same conversation_id
same task_id
same step_id
same operation_id   # write
```

---

### 7.9 Clarification Lifecycle

Clarification 不是新 Task。

典型流程：

```text
Task
 ↓
analyzing
 ↓
发现关键参数缺失 / 歧义
 ↓
waiting_clarification
 ↓
clarification
 ↓
User Response
 ↓
clarification_response
 ↓
analyzing_clarification
 ↓
继续原 Task
```

需要保留：

```text
已确认参数
有效 Tool Result
已完成 Step
原 task_id
```

不能把用户的 Clarification Response 当成一个全新的独立任务重新开始。

---

### 7.10 Query Lifecycle

典型 Query：

```text
received
 ↓
validating_input
 ↓
analyzing
 ↓
planning
 ↓
Tool Request
 ↓
waiting_tool_result
 ↓
Tool Result
 ↓
validating_tool_result
 ↓
succeeded
```

对于纯 Query：

```text
success + results = []
```

仍然可以形成：

```text
Task succeeded
```

前提是：

> 空结果就是用户所要求查询范围内的真实结果。

---

### 7.11 Write Lifecycle

Create / Update / Delete 的典型生命周期：

```text
received
 ↓
validating_input
 ↓
analyzing
 ↓
planning
 ↓
pre_execution_check
 ↓
Write Tool Request
 ↓
waiting_tool_result
 ↓
Tool Result
 ↓
validating_tool_result
 ↓
verifying_final_state
 ↓
verified_success
 ↓
Task succeeded
```

其中：

```text
Tool success
```

只是中间状态。

---

### 7.12 UNKNOWN Lifecycle

UNKNOWN 是生命周期中非常关键的一条路径：

```text
Write Request
     ↓
Tool Result = unknown
     ↓
Operation = unknown
     ↓
Task = recovering
     ↓
verify_state
     ↓
┌──────────────────┬───────────────────┬──────────────────┐
↓                  ↓                   ↓
真实已完成          确认未完成          仍然无法确认
↓                  ↓                   ↓
verified_success    verified_failure    unknown
↓                  ↓                   ↓
Success             Safe Retry          Task unknown
```

禁止：

```text
unknown
↓
blind retry
```

---

### 7.13 Recovery Lifecycle

Recovery 只允许处理：

```text
尚未完成的 Step
```

已经成功的 Step：

```text
MUST NOT repeat
```

安全 Recovery 可以包括：

```text
re-query
verify_state
safe retry
clarification
final failure
final unknown
```

如果 Recovery 会改变用户原始意图：

```text
Recovery Decision
↓
clarification
```

而不是 Agent 自己替用户选择。

---

### 7.14 Finite Multi-Step Lifecycle

V1 可以支持有限的串行多步骤任务：

```text
Task
 ↓
Step 1
 ↓
Tool Request
 ↓
Tool Result
 ↓
Verify
 ↓
Step 1 Completed
 ↓
Step 2
 ↓
Tool Request
 ↓
Tool Result
 ↓
Verify
 ↓
Step 2 Completed
 ↓
Final
```

约束：

```text
□ Single Agent
□ Serial
□ One Tool Request at a time
□ Each Step independently tracked
□ Completed Step not repeated
□ Recovery only unfinished Step
□ UNKNOWN requires verify_state
□ No parallel Tool execution
□ No generic transaction orchestration
□ No complex auto-compensation
```

---

### 7.15 Final State Transition

最终 Task 只能进入：

```text
succeeded
failed
unknown
```

判断依据：

```text
User Goal
    ↓
Required Operations
    ↓
Tool Results
    ↓
Real State Verification
    ↓
Overall Task State
```

例如多步骤任务：

```text
Step 1 = success
Step 2 = failed
```

不能直接：

```text
Task = success
```

而应根据 Protocol：

```text
Task = failure
```

同时 Final Message 必须如实说明：

> 已经发生了什么，以及还有什么没有完成。

---

### 7.16 Lifecycle Invariants

QA 后续需要验证以下生命周期不变量：

```text
□ Task terminal state 不再继续执行普通流程
□ Task succeeded 必须有真实状态依据
□ Tool success 不直接等于 Task succeeded
□ Write Operation 必须有 operation_id
□ Retry 同一逻辑 Write 必须复用 operation_id
□ UNKNOWN Write 必须先 verify_state
□ 已完成 Step 不重复执行
□ Clarification 不创建新 Task
□ Tool Result 使用新的 request_id
□ Tool Result 保留原 task_id / step_id
□ Write Tool Result 保留原 operation_id
□ 一个时刻最多一个 Tool Request
□ Final 状态与真实状态一致
```

---

### 7.17 QA Analysis Boundary

本节定义：

> **Task、Step、Operation、Tool Result 和 Final State 之间的生命周期关系。**

到这里，Section 1–7 已经形成：

```text
Section 1
System / Runtime Architecture
        ↓
Section 2
Spec Source & Authority
        ↓
Section 3
Product / Business Behavior
        ↓
Section 4
Agent Behavior
        ↓
Section 5
Protocol / Contract
        ↓
Section 6
Tool Behavior
        ↓
Section 7
Task / Step / Operation Lifecycle
```

后续 Section 8 再进入：

```text
Safety Boundary
```

即：

> 哪些操作在什么条件下必须被阻止、拒绝或进入安全门。

## 8. Risk Analysis — 哪些地方最容易出错，为什么？

### 8.1 Risk Analysis Boundary

本 Section 的目标不是判断“代码写得好不好”，也不是根据当前实现状态直接下 Defect 结论，而是基于前面的 Spec / Protocol / Tool / Lifecycle Analysis，识别：

- 哪些行为最容易发生错误；
- 哪些错误一旦发生影响较大；
- 哪些场景最难通过普通成功路径发现；
- 哪些状态、工具、参数或真实世界状态之间存在高风险耦合；
- 哪些风险需要在后续 Test Strategy / Test Matrix / Test Cases 中被明确覆盖。

因此，本 Section 输出的是 **Risk**，不是 **Defect**。

> `Not Implemented / Partial / Unknown` 是 Implementation Coverage 状态，不自动等于 Defect。  
> Risk 需要通过后续测试转化为实际 Failure，Failure 再根据证据判断是否形成 Defect。

---

### 8.2 Risk Classification

本项目 QA 风险至少从以下几个维度分析：

| Risk Dimension | 说明 |
|---|---|
| Semantic Risk | 用户自然语言被错误理解、分类或解释 |
| Parameter Risk | 参数缺失、错误、歧义、默认值或推导错误 |
| Protocol Risk | Tool Request / Tool Result / Final 不符合协议 |
| State Risk | Task / Step / Operation 状态流转错误 |
| Tool Risk | Tool 选择、参数、执行或结果解释错误 |
| Real-State Risk | Agent 对真实 Calendar / Reminders 状态判断错误 |
| Safety Risk | 未满足安全条件就执行 Create / Update / Delete |
| Idempotency Risk | 重试导致重复写入或重复副作用 |
| Recovery Risk | failed / unknown / clarification 后恢复错误 |
| Multi-Step Risk | 多步骤任务部分完成后状态或恢复错误 |
| Boundary Risk | 超出 V1 能力边界却继续执行 |
| Freshness / Sufficiency Risk | 查询结果过期、范围不足或无法支持当前决策 |
| Correlation Risk | request / task / step / operation 关联错误 |
| User-Communication Risk | 最终结果与真实状态不一致或表达误导 |

---

### 8.3 Risk Rating Model

后续测试优先级可以从以下三个因素观察：

| Factor | 关注点 |
|---|---|
| Impact | 一旦发生，对用户真实 Calendar / Reminders 状态、任务完成度或安全性的影响 |
| Likelihood | 该错误在正常输入、边界输入、异常 Tool Result 或恢复流程中出现的可能性 |
| Detectability | 错误是否容易通过普通 UI / Final Message 发现，还是需要检查 Tool Trace / State / Real State 才能发现 |

本 Section 不对风险进行总体排名或打分；具体测试优先级在后续 Test Strategy / Test Matrix 中定义。

---

### 8.4 Semantic Interpretation Risks

#### 8.4.1 Object Classification Risk

用户表达可能同时包含：

- 时间安排；
- 待办事项；
- 提醒；
- 事实描述；
- 计划描述；
- 已存在对象的修改意图。

核心风险：

> Agent 将 Calendar Event 与 Reminder 错误分类。

重点风险场景：

- “提醒我明天 10 点开会”
- “明天 10 点有个会”
- “记得下午买牛奶”
- “把明天的会议改到 3 点”
- “这个事项已经存在，帮我处理一下”

QA 需要验证 Agent 是否按照 Protocol 的对象语义，而不是仅根据关键词决定对象类型。

---

#### 8.4.2 Intent Classification Risk

核心 Intent 为：

- query
- create
- update
- delete

风险包括：

- query 被识别成 create；
- create 被错误识别成 update；
- update 被错误识别成 create；
- delete 被错误识别成 query；
- 用户只是陈述事实，Agent 却产生写操作。

尤其需要验证：

> Facts / Plans / Speculation 不应自动转换为 Action。

---

#### 8.4.3 Create → Update Auto-Conversion Risk

当用户请求 Create，而系统发现类似已有对象时：

> 相似对象不能自动将 Create 转换成 Update。

风险包括：

- 标题相似；
- 时间相同；
- 地点相同；
- Reminder 与 Event 信息相似；
- 只有部分字段匹配。

需要验证：

1. Agent 是否先识别用户原始 Intent；
2. 是否通过 `detect_duplicate` 判断重复风险；
3. 是否在需要时进入 clarification；
4. 是否避免未经用户授权修改已有对象。

---

### 8.5 Parameter Extraction Risks

#### 8.5.1 Missing Required Parameter

普通 Calendar Event Create 至少需要：

- title
- date
- concrete start time
- duration 或 end time

风险：

- 缺少具体时间却直接 Create；
- 缺少结束时间又错误推导默认 duration；
- 使用系统默认时长替代用户未提供的信息。

---

#### 8.5.2 Ambiguous Time Risk

以下表达不是具体时间：

- morning
- afternoon
- evening

它们表示时间窗口，而不是精确开始时间。

风险：

- Agent 擅自选择窗口中的某个时间；
- 根据历史习惯猜测具体时间；
- 直接执行 Create。

正确行为应是根据具体场景进入 clarification / availability 等后续流程，而不是无依据地生成精确时间。

---

#### 8.5.3 Relative Date Interpretation Risk

相对日期只有在可以唯一推导时才能直接使用。

风险：

- “明天”基准时间错误；
- 时区错误；
- 跨日期边界时计算错误；
- 当前上下文不足却强行推导；
- 将不唯一的相对日期当成确定日期。

---

#### 8.5.4 All-Day Interpretation Risk

只有明确表达全天 / 整天语义时，才允许使用 `all_day=true`。

风险：

- 缺少时间却自动转为全天事件；
- “下午”“晚上”等窗口被误判成全天；
- 普通日期事件被错误使用 all-day 分支。

---

#### 8.5.5 Parameter Source Risk

参数来源需要区分：

- explicit
- context_derived
- default

参数状态需要区分：

- valid
- missing
- ambiguous
- invalid

风险包括：

- 把 context_derived 当成 explicit；
- 使用不允许的 default；
- ambiguous 参数被当作 valid；
- invalid 参数没有被拦截；
- 上一轮 clarification 已确认的信息在后续步骤中丢失。

---

### 8.6 Tool Selection and Tool Request Risks

#### 8.6.1 Wrong Tool Risk

八个 V1 Tool 分别承担明确职责：

- `query_calendar`
- `query_reminders`
- `create_calendar_event`
- `update_calendar_event`
- `delete_calendar_event`
- `create_reminder`
- `update_reminder`
- `delete_reminder`

风险：

- Calendar / Reminder tool 混用；
- query / write tool 混用；
- update / delete 混用；
- 对当前 Intent 使用不匹配的 Tool。

---

#### 8.6.2 Query Purpose Risk

Query Tool 必须带有明确 `purpose`。

允许的 purpose 包括：

- `answer_query`
- `check_conflict`
- `detect_duplicate`
- `find_availability`
- `resolve_target`
- `verify_state`

风险：

- Query 缺少 purpose；
- purpose 与实际查询目的不一致；
- 为了“先查一下”而发起没有明确业务目的的查询；
- Query 范围与 purpose 不匹配。

---

#### 8.6.3 Query Range Risk

查询范围必须满足：

- 足够支持当前决策；
- 尽量最小；
- 与任务目的匹配。

风险：

- 范围过小，漏掉相关对象；
- 范围过大，引入无关对象；
- query_calendar 的 start / end 不成对；
- 使用 stale result；
- 使用不足以支持决策的查询结果继续执行。

---

#### 8.6.4 Target Resolution Risk

Update / Delete 应使用稳定的对象 ID。

风险：

- 根据 title 模糊匹配直接写入；
- 根据自然语言中的名称直接删除；
- query 返回多个候选后未进行消歧；
- clarification 已指出目标对象，但后续 Tool Request 使用了错误 ID。

---

### 8.7 Write Safety Risks

#### 8.7.1 Missing Pre-Execution Safety Check

Create / Update / Delete 执行前需要进行安全检查，包括：

- target；
- parameters；
- dependency state；
- conflicts；
- duplicates；
- intent alignment；
- V1 boundary；
- idempotency。

风险：

> Agent 在缺少关键安全证据时直接发出 Write Tool Request。

---

#### 8.7.2 Reminder Time Reasonableness Risk

Reminder Create / Update 有特殊前置条件：

> 必须先查询 Calendar，并检查 reminder time 是否合理。

风险：

- 未查询 Calendar 就创建 Reminder；
- 查询了 Calendar 但结果不足；
- 查询结果过期；
- 未基于查询结果判断时间合理性；
- 判断完成后仍使用错误的 reminder_time。

这是一个典型的 **跨 Tool Dependency Risk**。

---

#### 8.7.3 High-Risk Batch Write Risk

如果单个 Write Step 会通过：

- range；
- condition；
- collection；
- fuzzy multi-target；

影响多个已有对象，则属于高风险批量 Update / Delete。

V1 对此要求：

- final failure；
- 不发送 Write Tool Request；
- 不允许通过确认后继续执行来绕过 V1 边界。

风险：

- Agent 把批量操作拆成普通单对象操作；
- Agent 先请求确认再执行 unsupported operation；
- Agent 发出没有明确单对象 target ID 的 Write Tool Request；
- Client 执行了超出 V1 的操作。

---

### 8.8 Protocol / Schema Risks

#### 8.8.1 Tool Request Contract Risk

风险包括：

- 缺少必填字段；
- 多出 schema 不允许字段；
- query 错误携带 operation_id；
- write 缺少 operation_id；
- write 的 operation_id 在 retry 时改变；
- Tool 参数结构错误；
- Tool 名称与 arguments 不匹配。

---

#### 8.8.2 Tool Result Contract Risk

风险包括：

- request_id 关联错误；
- conversation_id / task_id / step_id 不一致；
- write result 缺少 operation_id；
- query success 缺少 fetched_at；
- query success 缺少 results；
- time_range reminder query 缺少 queried_range；
- failed / unknown 缺少 error；
- write success 缺少 result；
- 返回 unknown 字段。

---

#### 8.8.3 Final Response Contract Risk

Final 的 `status` 只有：

- success
- failure
- unknown

风险：

- Tool success 直接等同于 Final success；
- 未验证真实状态就返回 success；
- 无法确认真实状态却返回 failure 或 success；
- unsupported operation 没有返回 failure；
- Final message 描述与实际状态不一致。

---

### 8.9 State / Lifecycle Risks

#### 8.9.1 Task / Step / Operation Confusion

三个层级必须保持区别：

- Task：用户目标；
- Step：当前一次 Agent 决策 / Tool round；
- Operation：逻辑写操作。

风险：

- 把 request_id 当成 task_id；
- Tool Result 创建新 Task；
- Step 完成后重复执行；
- Operation retry 时生成新 operation_id；
- 多个不同逻辑 Write 共用 operation_id。

---

#### 8.9.2 Clarification Resume Risk

Clarification 是当前 Task 的暂停 / 恢复，而不是新 Task。

风险：

- clarification response 创建新 task_id；
- 已确认参数丢失；
- 已完成 Step 重复执行；
- 已成功写入的 Operation 再次执行；
- 只恢复未完成步骤却错误重跑整个任务。

---

#### 8.9.3 UNKNOWN Handling Risk

UNKNOWN 表示真实执行状态无法确认。

风险：

- unknown 后盲目 retry；
- retry 使用新的 operation_id；
- unknown 后不进行 verify_state；
- verify_state 不足以确认真实状态却返回 success；
- 已经成功的 write 因重复 retry 产生 duplicate。

---

#### 8.9.4 Partial Completion Risk

有限多步骤任务可能出现：

- Step 1 success；
- Step 2 success；
- Step 3 failed / unknown。

风险：

- 重新执行 Step 1 / Step 2；
- 把部分完成说成全部完成；
- 错误执行复杂 compensation；
- 未完成步骤未被明确识别；
- Task 最终状态与实际已完成步骤不一致。

---

### 8.10 Real-State and Verification Risks

#### 8.10.1 Query Result Freshness Risk

当当前真实状态影响决策时，必须查询真实状态。

风险：

- 使用旧查询结果；
- 在状态可能变化后继续写入；
- Tool Result 的 `fetched_at` 未被检查；
- 当前查询范围已不再覆盖目标状态。

---

#### 8.10.2 Result Sufficiency Risk

Query 成功并不代表结果足以支持当前决策。

风险：

- query 范围不足；
- filter 过窄；
- 结果为空但实际上只是漏查；
- 返回结果结构不完整；
- Agent 将“没有查到”误认为“现实中不存在”。

---

#### 8.10.3 Post-Write Verification Risk

Write Tool success 只说明 Tool 层成功，不等于用户真实目标已经完成。

风险：

- Create Tool success 后不 verify；
- Update Tool success 后不 verify；
- Delete Tool success 后不 verify；
- verify_state 查询错误对象；
- verify_state 范围不足；
- verify_state 结果过期；
- verify_state 与原 Operation 无法关联。

---

### 8.11 Idempotency Risks

写操作必须围绕 `operation_id` 保持幂等语义。

风险：

- 同一逻辑写操作 retry 时生成新的 operation_id；
- Client 重复执行相同 operation_id；
- Backend 没有阻止 duplicate dispatch；
- Tool Result 重复到达导致重复处理；
- UNKNOWN 恢复路径重新创建同一对象。

典型高风险场景：

```text
Agent
  ↓
Create operation_id = O1
  ↓
Client executes
  ↓
network timeout
  ↓
Agent receives UNKNOWN
  ↓
incorrect retry with operation_id = O2
  ↓
duplicate write
```

因此后续测试必须区分：

- Tool execution retry；
- HTTP retry；
- Agent reasoning retry；
- UNKNOWN recovery；
- duplicate Tool Result。

---

### 8.12 V1 Boundary Risks

V1 明确排除：

- Hermes；
- Gmail；
- Feishu；
- Research Agent；
- multi-agent；
- parallel Tool execution；
- generic transaction orchestration；
- complex auto-compensation；
- high-risk batch delete/update；
- old fields / protocol compatibility。

风险：

- 用户输入触发 V1 外能力；
- Agent 为了“完成用户目标”越过边界；
- Client 执行 unsupported Tool；
- 多 Agent / parallel execution 被错误引入；
- 老协议字段被错误兼容。

Boundary failure 的核心 QA 问题不是：

> “Agent 能不能把它做出来？”

而是：

> “当它不属于 V1 时，系统是否正确停止并给出符合协议的 failure？”

---

### 8.13 User Communication Risks

最终消息需要：

- brief；
- natural；
- result-first；
- 不暴露内部 Tool / JSON / ID。

风险：

- 成功但实际没有完成；
- 失败却说“已完成”；
- unknown 却给确定性表述；
- partial completion 却描述为 complete；
- 暴露内部 operation_id；
- 暴露 Tool / JSON 实现细节；
- 用户无法理解实际发生了什么。

因此 Final Message 也是 QA 验证对象，而不是纯 UI 文案。

---

### 8.14 Risk Dependency Map

以下风险不是彼此独立，而是存在明显的依赖关系：

```text
User Language
      │
      ▼
Semantic Interpretation
      │
      ├── Object
      ├── Intent
      └── Parameters
              │
              ▼
        Tool Selection
              │
              ▼
        Query / Write
              │
              ├──────────────┐
              ▼              ▼
        Real State       Safety Gate
              │              │
              └──────┬───────┘
                     ▼
                Execution
                     │
                     ▼
              Tool Result
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
     Success       Failed       Unknown
        │            │            │
        │            │            ▼
        │            │        Recovery
        │            │            │
        └──────┬─────┴────────────┘
               ▼
          Verification
               │
               ▼
          Final Decision
               │
               ▼
        User Communication
```

这个依赖关系意味着：

> 前置语义错误可以在后续多个层级被放大；后置验证错误则可能让整个错误状态最终被包装成“成功”。

因此后续 Test Strategy 不能只测试单个 Tool，而需要覆盖跨层链路。

---

### 8.15 High-Risk Scenario Families

后续 Test Matrix 至少应覆盖以下风险族：

| Scenario Family | 主要验证风险 |
|---|---|
| Missing information | missing / clarification |
| Ambiguous time | semantic / parameter |
| Relative date | date / timezone |
| All-day | semantic / schema branch |
| Create with duplicate candidate | duplicate / intent |
| Update with multiple candidates | target resolution |
| Delete target ambiguity | target / safety |
| Reminder time check | cross-tool dependency |
| Query empty result | empty-result semantics |
| Query insufficient range | sufficiency |
| Stale Tool Result | freshness |
| Tool failed | failure handling |
| Tool unknown | recovery / idempotency |
| Duplicate operation | idempotency |
| Clarification resume | task continuity |
| Multi-step partial failure | recovery / state |
| Unsupported operation | V1 boundary |
| High-risk batch write | safety / boundary |
| Post-write verification | real-state confirmation |
| Final response mismatch | communication / truthfulness |

---

### 8.16 Risk Analysis Output for Next Sections

本 Section 的结果应作为后续章节的输入：

```text
Section 8 Risk Analysis
        │
        ├── Risk Families
        │
        ├── Cross-Layer Dependencies
        │
        ├── High-Risk Scenarios
        │
        ▼
Section 9 Test Strategy
        │
        ▼
Section 10 Test Matrix
        │
        ▼
Section 11 Coverage Review
        │
        ▼
Section 12 Test Cases / Evaluation Dataset
```

后续 Test Strategy 不应重新发明 Risk，而应回答：

> 针对这些已识别风险，采用什么测试方法、什么环境、什么证据、什么优先级来验证？

---

### 8.17 QA Analysis Boundary

Section 8 只负责：

- 识别风险；
- 分类风险；
- 解释风险来源；
- 建立风险之间的依赖；
- 明确后续测试需要覆盖的风险族。

Section 8 不负责：

- 编写完整 Test Case；
- 执行测试；
- 判断具体实现是否已经产生 Defect；
- 修改 Agent；
- 修改 Protocol；
- 修改 Schema；
- 生成最终 Test Result。

后续章节分别承担这些工作。
