# 02 Risk Analysis

> **状态：HISTORICAL V1 QA ARTIFACT / SUPERSEDED。** 当前架构边界见 [`docs/protocol-v2.md`](docs/protocol-v2.md)；本文件保留 V1 风险分析记录。

> QA Baseline Artifact — calendar-agent V1
>
> 本文件独立记录 Risk Analysis。内容来源于 `01-spec-analysis.md` 已确认的 Spec / Protocol / Tool / Lifecycle 分析。
>
> **原则：Risk ≠ Defect。**
> `Not Implemented / Partial / Unknown` 是 Implementation Coverage 状态，不自动等于 Defect。Risk 需要通过后续测试转化为实际 Failure，再根据证据判断是否形成 Defect。

## 1. Risk Analysis — 哪些地方最容易出错，为什么？

### 1.1 Risk Analysis Boundary

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

### 1.2 Risk Classification

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

### 1.3 Risk Rating Model

后续测试优先级可以从以下三个因素观察：

| Factor | 关注点 |
|---|---|
| Impact | 一旦发生，对用户真实 Calendar / Reminders 状态、任务完成度或安全性的影响 |
| Likelihood | 该错误在正常输入、边界输入、异常 Tool Result 或恢复流程中出现的可能性 |
| Detectability | 错误是否容易通过普通 UI / Final Message 发现，还是需要检查 Tool Trace / State / Real State 才能发现 |

本 Section 不对风险进行总体排名或打分；具体测试优先级在后续 Test Strategy / Test Matrix 中定义。

---

### 1.4 Semantic Interpretation Risks

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

### 1.5 Parameter Extraction Risks

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

### 1.6 Tool Selection and Tool Request Risks

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

### 1.7 Write Safety Risks

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

### 1.8 Protocol / Schema Risks

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

### 1.9 State / Lifecycle Risks

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

### 1.10 Real-State and Verification Risks

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

### 1.11 Idempotency Risks

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

### 1.12 V1 Boundary Risks

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

### 1.13 User Communication Risks

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

### 1.14 Risk Dependency Map

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

### 1.15 High-Risk Scenario Families

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

### 1.16 Risk Analysis Output for Next Sections

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

### 1.17 QA Analysis Boundary

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
