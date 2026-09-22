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
└────────┬────────┴────────┬────────┴──────┬──────┘
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

### 2.1 Spec Is Layered, Not a Single File

当前 Calendar Agent 的 Spec 不是由某一个文件单独定义，而是分层组成：

```text
Product / Agent Behavior
        │
        ├── 01-岗位卡
        │      → Agent 是什么、负责什么、成功标准、边界
        │
        └── 02-工作流程
               → Agent 收到请求后应该如何判断和处理

Process Representation
        │
        ├── 02-工作流卡片
        │      → 完整业务流程和判断点补充
        │
        └── 03-流程图
               → 将流程可视化，不单独定义新规则

Engineering Contract
        │
        ├── docs/protocol-v1.md
        │      → Agent 与外部系统之间的正式协议
        │
        └── schemas/*.schema.json
               → 协议的机器可读 Contract
```

因此，不能简单地说“某一个文件就是全部 Spec”。

---

### 2.2 Current Spec Sources

| Source | 主要作用 | Authority |
|---|---|---|
| `01-岗位卡` | Agent 角色、职责、输入、输出、成功标准、人工兜底、V1 边界 | **Product / Role Authority** |
| `02-工作流程` | Agent 的行为规则、判断逻辑、查询、澄清、Tool、恢复、最终验证 | **Behavior Authority** |
| `02-工作流卡片` | 端到端业务流程和关键判断点补充 | **Process Supplement** |
| `03-流程图` | 将完整决策链可视化 | **Process Representation** |
| `docs/protocol-v1.md` | Agent / Shortcut 的消息、ID、状态、协议和交互 Contract | **Protocol Authority** |
| `schemas/*.schema.json` | 将协议转换成机器可验证的 JSON Contract | **Machine-readable Contract** |

> 当前没有 `profile.md`。不要把不存在的文件作为 Spec Source。

---

### 2.3 Artifact Inventory

本节记录当前 QA 已发现、并可能影响 Agent 行为的主要资料。

| Category | Artifact | Location | Authority / Role | Status |
|---|---|---|---|---|
| Product / Business | ... | ... | ... | Found / Missing |
| Behavior | ... | ... | ... | Found / Missing |
| Protocol | ... | ... | ... | Found / Missing |
| Schema | ... | ... | ... | Found / Missing |
| Implementation | ... | ... | ... | Found / Missing |
| Tests | ... | ... | ... | Found / Missing |
| Evaluation | ... | ... | ... | Found / Missing |

### 2.4 Schema / Contract Inventory

本节基于当前 Calendar Agent 的实际项目结构，明确每一个 Schema 文件在整体架构中对应什么消息、对象或内部结构，以及它承担什么职责。

当前 `schemas/` 主要分为三层：

1. 外部消息协议
2. Tool 参数与结果协议
3. 共享数据模型和内部 LLM 语义分析协议

#### 2.4.1 Architecture ↔ Schema Mapping

```text
User
  ↓ 自然语言
Siri / Shortcut
  ↓ user_request
Backend Agent
  ├─ clarification
  ├─ tool_request
  └─ final
       ↓
Siri / Shortcut
  ↓ tool_result
Tool Executor
  ↓
Calendar / Reminders
```

| 架构环节 | 消息 / 对象类型 | 主要 Schema | 主要职责 |
|---|---|---|---|
| Siri / Shortcut → Backend Agent | `user_request` | `inbound-v1.schema.json` | 入站消息总入口 |
| Backend Agent → Siri / Shortcut | `clarification` | `agent-response-v1.schema.json` | Agent 输出消息总入口中的澄清响应 |
| Backend Agent → Siri / Shortcut | `tool_request` | `agent-response-v1.schema.json` + `tool-request-v1.schema.json` | Agent 输出消息总入口 + Tool 执行指令 |
| Backend Agent → Siri / Shortcut | `final` | `agent-response-v1.schema.json` | Agent 最终响应 |
| Tool Executor → Backend Agent | `tool_result` | `inbound-v1.schema.json` + `tool-result-v1.schema.json` | Tool Result 入站消息 + 具体结果结构 |
| Calendar / Reminders | Event / Reminder 对象 | `calendar-v1.schema.json` / `reminder-v1.schema.json` | 外部真实业务对象的数据模型 |
| Backend Agent 内部 | Semantic Analysis | `llm-analysis-v1.schema.json` | LLM 对用户请求的结构化语义分析 |
| 所有消息 / Contract | ID、时间、枚举、Error 等共享结构 | `common-v1.schema.json` | 所有其他 Schema 的公共基础定义 |

#### 2.4.2 `schemas/inbound-v1.schema.json`

这是进入 Backend Agent 的消息总入口，对应：

```text
Siri / Shortcut → Backend Agent
```

支持：

```text
user_request
clarification_response
tool_result
```

其中：

- `user_request`：用户第一次发起请求；
- `clarification_response`：用户回答 Agent 的澄清问题；
- `tool_result`：Shortcut / Tool Executor 执行 Calendar 或 Reminder 操作后，将结果传回 Backend Agent。

`inbound-v1.schema.json` 负责入站消息分发，具体 `tool_result` 结构由 `tool-result-v1.schema.json` 进一步定义。

#### 2.4.3 `schemas/agent-response-v1.schema.json`

这是 Backend Agent 输出消息的总入口，对应：

```text
Backend Agent → Siri / Shortcut
```

支持：

```text
tool_request
clarification
final
```

其中：

- `clarification`：需要用户补充信息；
- `tool_request`：需要 Shortcut 调用本地 Tool；
- `final`：任务结束，返回最终结果。

`tool_request` 的具体字段由 `tool-request-v1.schema.json` 进一步定义。

#### 2.4.4 `schemas/tool-request-v1.schema.json`

这是 Backend Agent 给 Shortcut / Tool Executor 的执行指令协议：

```text
Backend Agent
  ↓ tool_request
Shortcut
  ↓
Tool Executor
```

当前覆盖：

```text
query_calendar
query_reminders

create_calendar_event
update_calendar_event
delete_calendar_event

create_reminder
update_reminder
delete_reminder
```

主要负责约束：

- Tool 名称；
- `purpose`；
- `operation_id`；
- `event_id` / `reminder_id`；
- 查询时间范围；
- 创建事件 / Reminder 的字段；
- 全天事件和定时事件的结构；
- Update 的 `changes`；
- Delete 的目标对象。

它负责定义 Tool Request 的结构，不负责判断用户自然语言是否真的应该执行该操作；后者属于 LLM 分析和 Agent 决策层。

#### 2.4.5 `schemas/tool-result-v1.schema.json`

这是 Tool Executor 返回给 Backend Agent 的执行结果协议：

```text
Tool Executor
  ↓
Calendar / Reminders
  ↓ tool_result
Shortcut
  ↓
Backend Agent
```

主要定义：

- Tool 执行 `success` / `failure` / `unknown`；
- 查询结果；
- 写入结果；
- 错误信息；
- `executed_at`；
- `fetched_at`；
- `operation_id`；
- `queried_range`；
- `query_scope`。

它负责定义“Tool Result 长什么样”，但不单独负责判断：

- `step_id` 是否匹配原请求；
- `operation_id` 是否重复；
- Result 是否过期；
- 是否应该重试；
- 是否已经完成最终状态验证。

这些属于 Backend Agent 的 Runtime / State / Business Logic。

#### 2.4.6 `schemas/calendar-v1.schema.json`

这是 Calendar Event 的领域对象 Schema，对应：

```text
Apple Calendar
```

主要用于：

- Calendar 查询结果；
- Calendar 写入后的真实对象；
- 最终状态验证；
- Tool Result 中的 Calendar 数据。

它定义定时事件和全天事件等 Calendar Event 数据结构，不是独立的 HTTP 消息协议。

#### 2.4.7 `schemas/reminder-v1.schema.json`

这是 Reminder 的领域对象 Schema，对应：

```text
Apple Reminders
```

主要用于：

- Reminder 查询结果；
- Reminder 创建 / 更新后的真实对象；
- 最终状态验证；
- Tool Result 中的 Reminder 数据。

它是领域数据模型，而不是独立的 HTTP 消息协议。

#### 2.4.8 `schemas/common-v1.schema.json`

这是所有其他 Schema 共用的基础定义，负责：

```text
request_id
conversation_id
task_id
step_id
operation_id
date-time
IANA timezone
time range
Object
Intent
Tool
Purpose
Query Scope
Task Status
Tool Status
Operation Status
Error
```

可以理解为：

```text
所有其他 Schema 的公共基础库
```

#### 2.4.9 `schemas/llm-analysis-v1.schema.json`

这个 Schema 不属于外部 Shortcut / HTTP 消息协议，而是 Backend Agent 内部的 LLM 语义分析结果。

对应：

```text
Backend Agent
  └─ Agent Decision
      └─ LLM Semantic Analysis
```

它用于表达：

- 用户请求是否可执行；
- Object 是 Calendar Event 还是 Reminder；
- Intent 是 query / create / update / delete；
- 是否为 batch write；
- 参数来源；
- 参数状态；
- 是否需要 clarification；
- clarification reason。

它不应该直接返回给 Siri / Shortcut。正常情况下，Agent 会根据它继续生成：

```text
clarification
或
tool_request
或
final
```

#### 2.4.10 Schema 层级总结

```text
External Message Protocol
├── inbound-v1.schema.json
└── agent-response-v1.schema.json

Tool Protocol
├── tool-request-v1.schema.json
└── tool-result-v1.schema.json

Domain Data Model
├── calendar-v1.schema.json
└── reminder-v1.schema.json

Shared Contract Definitions
└── common-v1.schema.json

Internal Agent Semantic Analysis
└── llm-analysis-v1.schema.json
```

#### 2.4.11 Schema Inventory 与 Contract Analysis 的边界

本节只负责建立：

```text
Schema
  ↓
架构环节
  ↓
消息 / 对象
  ↓
主要职责
  ↓
Protocol 对应
```

Protocol 与 Schema 的一致性、职责边界以及缺失约束，在后续 Contract / Authority Analysis 中判断。

因此：

> Protocol 与 Schema 不一致，不应在 Inventory 阶段直接判定为 Schema Defect。

#### 2.4.12 Legacy / Deprecated Schema

如果项目中存在旧的 `schema.json` 入口文件，应根据 `docs/protocol-v1.md` 的当前规定识别其状态。

当前项目资料表明：

> `schema.json` 属于旧入口的废弃指针，不应作为 V1 的独立协议来源。


### 2.5 Which Source Is More Authoritative?

这里不要建立一个简单的“所有文件从高到低”的排名，而应该按**问题类型**判断权威来源。

#### 如果问：Agent 应该做什么？

优先看：

```text
01-岗位卡
    ↓
02-工作流程
```

例如：

- 是否支持 Calendar / Reminders
- 是否支持 Query / Create / Update / Delete
- 什么情况下必须 clarification
- 什么情况下不能执行
- 什么叫最终成功

这些属于 Product / Behavior，不应由 Schema 或代码反向决定。

#### 如果问：Agent 和 Shortcut 应该怎么通信？

优先看：

```text
01-岗位卡 / 02-工作流程
          ↓
   docs/protocol-v1.md
          ↓
   schemas/*.schema.json
```

其中：

- `protocol-v1.md` 定义协议语义和交互规则。
- `schemas/` 定义这些规则的机器可验证结构。
- Schema 不应该自行创造与 Protocol 冲突的业务规则。

#### 如果问：代码现在实际上怎么做？

看：

```text
src/
tests/
```

但：

> Implementation 是 Actual Behavior 的证据，不是 Product Spec 本身。

---

### 2.6 Spec vs Engineering Contract vs Implementation

需要把三层明确分开：

```text
        Spec
         │
         │ defines
         ↓
Expected Behavior
         │
         ├───────────────┐
         ↓               ↓
Protocol Contract    Business Rules
         │
         ↓
      schemas/
         │
         ↓
   Implementation
         │
         ↓
    Actual Behavior
```

因此 QA 分析时：

| Situation | Classification |
|---|---|
| Spec 要求，但代码没有实现 | **Implementation Gap / Defect** |
| Protocol 要求，但 Schema 不符合 | **Contract / Schema Defect** |
| Schema 与 Protocol 不一致 | **Contract Parity Issue** |
| Spec 本身没有定义清楚 | **Spec Ambiguity** |
| Spec 和实现都正确，但没有测试 | **Test Coverage Gap** |

---

### 2.7 Authority Rules

当不同来源出现冲突时，按照以下规则处理：

1. **Product / Behavior 冲突**
   - 优先检查 `01-岗位卡` 和 `02-工作流程`。
   - 不以当前代码行为作为正确答案。

2. **Process Representation 冲突**
   - `03-流程图` 如果与文字规则冲突，以文字 Spec 为准。
   - 然后更新流程图。

3. **Protocol 冲突**
   - `docs/protocol-v1.md` 是当前协议语义的主要依据。
   - `schemas/` 应与 Protocol 保持一致。

4. **Schema 冲突**
   - 如果 Schema 与 Protocol 不一致，先记录为 Contract Parity Issue。
   - 不应直接因为 Schema 当前存在，就认为业务规则已经改变。

5. **Implementation 冲突**
   - `src/` 反映 Actual Behavior。
   - 如果 Actual Behavior 与 Spec 不一致，应进入后续 Failure / Root Cause 分析。

---

### 2.8 Current Authority Model

当前项目可以用下面的模型理解：

```text
              PRODUCT / BEHAVIOR
                     SPEC
                       │
          ┌────────────┴────────────┐
          ↓                         ↓
    01-岗位卡                 02-工作流程
          │                         │
          └────────────┬────────────┘
                       ↓
              Expected Behavior
                       │
              ┌────────┴────────┐
              ↓                 ↓
      Process Documents    Protocol Contract
              │                 │
       ┌──────┴──────┐          ↓
       ↓             ↓    protocol-v1.md
  工作流卡片       流程图          │
                                  ↓
                              schemas/
                                  │
                                  ↓
                             Implementation
                                  │
                                  ↓
                              Actual Behavior
```

### 2.9 QA Use Rule

进行后续 Risk Analysis、Test Strategy 和 Test Case Design 时，统一按照：

```text
Spec
  ↓
Expected Behavior
  ↓
Risk
  ↓
Test Scenario / Case
  ↓
Implementation
  ↓
Actual Behavior
  ↓
Gap / Defect / Coverage
```

> **QA 不应该从代码倒推“什么是正确行为”。正确行为首先来自 Spec；Protocol / Schema 用于定义可验证的工程 Contract；代码只是需要被验证的实现。**

> 当前 `docs/protocol-v1.md` 已被现有 QA 资料作为规范主依据，`schemas/*.schema.json` 作为机器合同；因此后续还需要继续核对 Protocol 与 `01-岗位卡`、`02-工作流程` 的一致性，而不是默认它们天然完全一致。

## 3.Product / Business Behavior (这个 Agent 是干什么的？)


## 4.Agent Behavior(用户给 Agent 一句话以后，Agent应该怎么理解和决定？)
## 5.Protocol / Contract(Agent 和外部系统之间到底怎么通信？)
## 6.Tool Behavior(Agent 能要求执行哪些 Tool？什么时候能要求？参数是什么？)
## 7.State / Lifecycle(一个 Agent Task 从开始到结束，到底经历什么状态？)
## 8.Safety / Boundary(Agent 什么情况下不能继续？)
## 9.Open Questions / Ambiguities(我已经认真看了 Spec，但是 Spec 本身没有定义清楚。)