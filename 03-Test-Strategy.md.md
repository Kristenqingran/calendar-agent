# 03 Test Strategy

> QA Baseline Artifact — calendar-agent V1
>
> 本文件定义如何验证 `calendar-agent` 的行为与风险。它承接 `01-spec-analysis.md` 与 `02-risk-analysis.md`，但不生成具体 Test Case，也不记录实际 Test Result。
>
> **当前 Agent 仍可能处于开发阶段。正式 QA Baseline 的执行版本需要在 Test Case Design 完成后明确 Freeze。**

## 1. Test Strategy — 我们应该怎么测？

### 1.1 Strategy Objective

本 Test Strategy 的目标是把前面的：

```text
Spec
  ↓
Behavior
  ↓
Risk
```

转换为可执行的 QA 方法：

```text
Risk
  ↓
Test Objective
  ↓
Test Method
  ↓
Test Evidence
  ↓
Test Case
  ↓
Test Result
```

本阶段重点不是追求测试数量，而是确保高风险行为能够被可重复、可观察、可判定地验证。

---

### 1.2 Strategy Scope

测试范围覆盖 V1 中：

- Natural Language Client → HTTP API → Schedule Agent → Tool Request → Tool Result → clarification / final；
- Calendar Event Query / Create / Update / Delete；
- Reminder Query / Create / Update / Delete；
- Task / Step / Operation lifecycle；
- clarification / recovery；
- Tool Result validation；
- real-state verification；
- idempotency；
- V1 boundary；
- final result communication。

测试范围不扩展到 Protocol 明确排除的：

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

---

### 1.3 Test Objectives

本轮 QA 至少验证以下目标：

| Objective | 要回答的问题 |
|---|---|
| Semantic Correctness | Agent 是否正确理解 Object / Intent / Parameters？ |
| Parameter Safety | 缺失、歧义、invalid 参数是否被正确处理？ |
| Tool Correctness | 是否选择正确 Tool，并生成正确 Tool Request？ |
| Protocol Compliance | Request / Result / Final 是否符合 Contract？ |
| State Correctness | Task / Step / Operation 是否正确流转？ |
| Safety Correctness | Write 前是否完成必要的安全检查？ |
| Real-State Correctness | Agent 是否基于真实状态做决策并验证结果？ |
| Recovery Correctness | failed / unknown / clarification 后是否正确恢复？ |
| Idempotency | retry / duplicate delivery 是否产生重复副作用？ |
| Boundary Correctness | V1 不支持的操作是否正确停止？ |
| Communication Correctness | Final 是否准确表达真实结果？ |

---

## 2. Test Approach

### 2.1 Layered Testing

测试不应只从最终用户消息观察结果，而应分层验证：

```text
Layer 1: User Intent / Semantic
        ↓
Layer 2: Agent Decision
        ↓
Layer 3: Tool Request
        ↓
Layer 4: Tool Execution / Tool Result
        ↓
Layer 5: State / Lifecycle
        ↓
Layer 6: Real Calendar / Reminder State
        ↓
Layer 7: Final Response
```

不同 Layer 的证据不能互相替代。

例如：

> Tool Request 正确 ≠ Tool Result 正确  
> Tool Result success ≠ Task succeeded  
> Task succeeded ≠ Real State 一定正确

因此测试必须根据风险选择对应的观察层级。

---

### 2.2 Black-Box + White-Box Evidence

本项目采用混合测试方法。

#### Black-Box

从用户请求出发，观察：

- Agent Response；
- clarification；
- Tool Request；
- Final Response；
- 实际 Calendar / Reminder 状态。

用于验证用户可观察行为与端到端行为。

#### White-Box / Trace Analysis

必要时检查：

- request_id；
- conversation_id；
- task_id；
- step_id；
- operation_id；
- Task State；
- Step State；
- Operation State；
- Tool Request / Tool Result；
- state transition；
- retry / recovery trace。

用于验证协议、生命周期、幂等性和恢复逻辑。

---

### 2.3 Contract Testing

对结构化接口进行独立 Contract Validation：

- Tool Request schema；
- Tool Result schema；
- Calendar object schema；
- Reminder object schema；
- Final response contract。

重点验证：

- required fields；
- field types；
- enum；
- additional properties；
- query / write 分支；
- operation_id；
- result / results；
- error；
- correlation fields。

Schema Validation 不能替代 Semantic / State / Real-State Testing。

---

### 2.4 Scenario-Based Testing

核心行为采用 Scenario Testing。

每个 Scenario 应至少明确：

```text
Precondition
  ↓
User Input
  ↓
Expected Agent Decision
  ↓
Expected Tool Interaction
  ↓
Expected Real State
  ↓
Expected Final Outcome
```

对于需要多个 Tool 的场景，还需要明确：

```text
Step 1
  ↓
Tool Result
  ↓
Step 2
  ↓
Tool Result
  ↓
Verification
  ↓
Final
```

---

### 2.5 Negative / Boundary Testing

由于 Risk Analysis 中大量风险来自：

- missing；
- ambiguous；
- invalid；
- insufficient；
- stale；
- failed；
- unknown；
- unsupported；

因此 Negative / Boundary Testing 是核心测试方法，而不是补充测试。

重点验证系统是否：

> **在不满足安全条件时停止，而不是为了完成用户目标而猜测或越权执行。**

---

## 3. Test Oracle Strategy

### 3.1 Expected Behavior as Oracle

每个测试必须有明确的 Expected Behavior。

Expected 不只描述最终文字，而应根据测试目的包含必要的：

- Agent response type；
- Intent；
- Object；
- parameters；
- Tool；
- purpose；
- query scope；
- operation_id；
- state transition；
- verification；
- final status；
- real state。

---

### 3.2 Multi-Level Oracle

测试 Oracle 分为：

| Oracle Level | 验证内容 |
|---|---|
| Semantic Oracle | Object / Intent / Parameter 是否正确 |
| Contract Oracle | JSON / schema / protocol 是否正确 |
| State Oracle | Task / Step / Operation 是否正确 |
| Tool Oracle | Tool / arguments / purpose 是否正确 |
| Real-State Oracle | Calendar / Reminder 最终状态是否正确 |
| Communication Oracle | Final 是否真实、清晰、符合边界 |

一个测试通过时，不要求所有 Oracle 都必须使用；但测试的风险对应的 Oracle 必须存在。

---

### 3.3 Truthfulness Oracle

对于 Write 场景，必须把：

```text
Tool success
```

与：

```text
Real State verified
```

区分开。

尤其是：

- Create；
- Update；
- Delete；
- UNKNOWN recovery；

必须验证最终结论是否有真实状态证据支持。

---

## 4. Test Environment Strategy

### 4.1 Environment Boundary

测试环境至少需要能够观察：

```text
Agent
  ↓
HTTP Request / Response
  ↓
Tool Request
  ↓
Tool Result
  ↓
Task / Step / Operation State
  ↓
Calendar / Reminder State
```

如果某一层不可观察，则必须明确记录：

> 当前测试证据无法覆盖该层。

不能用推测替代缺失证据。

---

### 4.2 Test Data Isolation

测试数据应与真实个人数据隔离。

建议使用专用：

- Calendar；
- Reminder List；
- 测试 Event；
- 测试 Reminder。

每个测试尽量：

- 使用明确的测试数据；
- 控制初始状态；
- 在测试后验证最终状态；
- 避免测试之间共享会变化的对象。

---

### 4.3 Deterministic Time

涉及：

- today；
- tomorrow；
- relative date；
- reminder_time；
- event start/end；
- timezone；

测试必须记录测试时使用的：

- current date/time；
- timezone；
- relevant Calendar state。

这样才能判断 relative-date 与 time-related 行为。

---

## 5. Test Data Strategy

### 5.1 Data Categories

Test Data 至少覆盖：

#### Calendar Events

- timed event；
- all-day event；
- single event；
- multiple similar events；
- overlapping events；
- empty query result；
- target with stable event_id。

#### Reminders

- incomplete reminder；
- completed reminder；
- reminders with reminder_time；
- reminders without reminder_time；
- multiple similar reminders；
- target with stable reminder_id。

#### Query States

- result exists；
- result empty；
- result insufficient；
- result stale；
- result failed；
- result unknown。

#### Target States

- unique target；
- multiple candidates；
- no candidate；
- ambiguous target；
- already changed target；
- deleted / unavailable target。

---

### 5.2 State Preparation

测试前必须能够明确回答：

> “测试开始之前，真实状态是什么？”

例如：

```text
Before:
Event E1 exists
start = ...
end = ...
title = ...

Action:
User requests update

After:
Event E1 exists
new start = ...
```

没有明确 Precondition 的 State Test 很难判断 Failure 来源。

---

### 5.3 Data Cleanup

测试数据应支持：

- setup；
- execution；
- verification；
- cleanup。

对于 Delete 测试尤其需要注意：

> Delete 本身会改变后续测试的 Precondition。

因此 Test Case 之间不应隐式依赖执行顺序，除非依赖被明确声明。

---

## 6. Risk-Based Test Prioritization

测试资源优先用于以下风险：

### Priority Focus A — Write Safety / Real State

重点：

- Create；
- Update；
- Delete；
- Reminder Calendar pre-check；
- duplicate；
- target resolution；
- post-write verification；
- UNKNOWN recovery；
- idempotency。

原因：

这些风险可能产生真实副作用。

---

### Priority Focus B — Semantic / Parameter Safety

重点：

- object classification；
- intent classification；
- missing required parameters；
- ambiguous time；
- relative date；
- all-day；
- facts / plans / speculation；
- Create → Update auto-conversion。

---

### Priority Focus C — Lifecycle / Recovery

重点：

- clarification；
- failed；
- unknown；
- partial completion；
- retry；
- operation_id reuse；
- completed Step 不重复执行。

---

### Priority Focus D — Contract / Boundary

重点：

- schema；
- correlation；
- unsupported V1 operation；
- high-risk batch write；
- final status。

这里的优先级表示测试策略上的关注顺序，不是对风险做总体评分或排名。

---

## 7. Test Techniques

### 7.1 Equivalence Partitioning

对输入按行为类别划分，例如：

```text
Time:
- concrete time
- morning / afternoon / evening
- missing
- ambiguous
- invalid

Target:
- unique
- multiple
- none
- stale

Tool Result:
- success
- empty success
- failed
- unknown
- insufficient
```

每个等价类不需要无限重复，但必须有代表性验证。

---

### 7.2 Boundary Value Testing

重点边界包括：

- event start / end；
- end > start；
- all-day start_date / end_date；
- required_duration_minutes >= 1；
- empty query result；
- time-range boundary；
- date boundary；
- timezone boundary。

---

### 7.3 State Transition Testing

针对：

```text
Task
Step
Operation
```

验证：

```text
received
  ↓
validating_input
  ↓
analyzing
  ↓
planning
  ↓
waiting_tool_result
  ↓
validating_tool_result
  ↓
pre_execution_check
  ↓
verifying_final_state
  ↓
succeeded / failed / unknown
```

并重点验证：

- 非法跳转；
- terminal state 后继续执行；
- completed Step 重复执行；
- unknown 后错误 retry；
- clarification 后状态丢失。

---

### 7.4 Fault Injection

为了验证 Recovery / Unknown，需要构造：

- Tool failed；
- Tool unknown；
- network / response uncertainty；
- incomplete Tool Result；
- stale query result；
- insufficient query result；
- duplicate Tool Result。

Fault Injection 的目的不是测试基础设施本身，而是验证 Agent 在异常 Tool 状态下是否遵守协议和安全规则。

---

### 7.5 Metamorphic / Consistency Testing

对于语义相同但表达不同的输入，可以验证核心行为是否保持一致。

例如：

```text
“帮我查一下明天上午的日程”
“看看明天上午有没有安排”
```

两者的自然语言不同，但在相同上下文与状态下，其核心 Query intent 应保持一致。

这种测试不要求 Final 文案完全相同，而要求：

- Object；
- Intent；
- Query purpose；
- relevant scope；
- safety behavior；

保持符合 Spec。

---

## 8. End-to-End Test Strategy

### 8.1 User-to-Real-State Chain

对于关键 Write 场景，采用：

```text
User Request
     ↓
Agent Analysis
     ↓
Tool Request
     ↓
Client Tool Execution
     ↓
Tool Result
     ↓
Agent Result Validation
     ↓
Verify State
     ↓
Final
     ↓
Real Calendar / Reminder State
```

测试不能只验证其中一段。

---

### 8.2 Query Strategy

Query 测试主要验证：

- 正确 Object；
- 正确 Tool；
- purpose；
- query scope；
- freshness；
- sufficiency；
- empty result semantics；
- final interpretation。

特别注意：

> `success + results=[]` 是合法的空查询结果，不应被当作 Tool failure。

---

### 8.3 Write Strategy

Write 测试必须关注：

```text
Intent
  ↓
Target
  ↓
Parameters
  ↓
Dependency State
  ↓
Safety Check
  ↓
Idempotency
  ↓
Write
  ↓
Tool Result
  ↓
Verification
  ↓
Final
```

其中任一必要前置条件未满足，都应验证 Agent 是否正确停止、clarify、recover 或返回 failure / unknown，而不是继续执行。

---

### 8.4 Clarification Strategy

Clarification 测试验证：

- reason；
- missing_fields；
- ambiguous_fields；
- message；
- expected_answer；
- task continuity；
- confirmed parameters preservation；
- completed steps preservation；
- unfinished steps recovery。

核心原则：

> Clarification Response 应恢复当前 Task，而不是创建新 Task。

---

### 8.5 Recovery Strategy

Recovery 测试重点覆盖：

```text
failed
unknown
partial completion
stale result
insufficient result
```

验证系统是否：

- 识别已完成步骤；
- 不重复成功步骤；
- 对 unknown 先 verify；
- 必要时重新 query；
- 必要时 clarification；
- 最终正确进入 success / failure / unknown。

---

## 9. Observability and Evidence Strategy

### 9.1 Required Evidence

关键测试至少保留：

- User Request；
- Agent Response；
- Tool Request；
- Tool Result；
- relevant IDs；
- state transitions；
- pre-test real state；
- post-test real state；
- Final Response。

---

### 9.2 Evidence by Risk

| Risk | Required Evidence |
|---|---|
| Semantic | input + Agent decision |
| Parameter | extracted params + clarification / Tool Request |
| Tool | Tool Request + arguments |
| Protocol | raw structured message + schema validation |
| Lifecycle | state transition + IDs |
| Idempotency | repeated request / operation_id trace |
| Unknown | original write + unknown + verify_state |
| Real State | before / after actual object state |
| Boundary | requested unsupported operation + final response + absence of forbidden write |
| Communication | final response + verified actual outcome |

---

### 9.3 Evidence Principle

测试结论必须尽量基于：

```text
Observed Evidence
```

而不是：

```text
Agent says it succeeded
```

尤其不能仅因为 Final 是：

```text
status = success
```

就认定真实状态已经正确。

---

## 10. Test Execution Model

### 10.1 Development Testing vs QA Baseline

在 Agent 仍处于开发阶段时：

- 可以继续开发；
- 可以使用 Codex；
- 可以做 smoke / exploratory testing；
- Agent 可以发生变化。

这些测试不自动成为正式 QA Baseline。

---

### 10.2 QA Baseline Freeze Point

本项目建议在：

```text
02 Risk Analysis
        ↓
03 Test Strategy
        ↓
04 Test Matrix
        ↓
05 Test Cases
        ↓
🔒 Baseline Freeze
```

之后冻结被测 Agent 版本。

Freeze 后：

> 测试的目标是发现并记录当前版本的问题，而不是边测边修改以让测试通过。

---

### 10.3 Defect Handling During Baseline

Baseline 执行中发现 Failure 时：

```text
Test Case
   ↓
Observed Failure
   ↓
Evidence
   ↓
06-test-results.md
   ↓
Defect Assessment
   ↓
07-defects.md
```

不要因为发现 Failure 就直接修改 Agent 并覆盖原测试证据。

如果之后进入 Fix：

```text
Defect
  ↓
Codex Fix
  ↓
New Version
  ↓
Regression
```

应明确区分 Baseline Result 与 Regression Result。

---

## 11. Entry / Exit Criteria

### 11.1 Strategy Entry Criteria

进入正式 Test Case Design 前，应至少具备：

- `01-spec-analysis.md` 已完成；
- `02-risk-analysis.md` 已完成；
- V1 Scope 已明确；
- Protocol Authority 已明确；
- Tool Contract 已明确；
- Task / Step / Operation Lifecycle 已明确；
- 当前 Agent 的可测试环境可用；
- 关键观察证据可获取。

---

### 11.2 Baseline Execution Entry Criteria

正式执行 Baseline 前，应具备：

- `03-test-strategy.md` 已完成；
- `04-test-matrix.md` 已完成；
- `05-test-cases.md` 已完成；
- 被测 Agent 版本明确；
- Test Data 已准备；
- Calendar / Reminder 测试状态可控制；
- Tool Result / failure / unknown 场景可构造或模拟；
- 关键 trace / state 可观察。

---

### 11.3 Baseline Exit Criteria

Baseline Execution 完成的判断不是：

> “所有 Test Case 都 PASS。”

而是：

- 计划中的测试已经执行或明确标记未执行；
- 每个 Failure 都有 evidence；
- Defect candidate 已完成判断；
- `06-test-results.md` 完整；
- `07-defects.md` 已记录确认的 Defect；
- 未执行项、环境限制、Known Limitation 已明确记录。

---

## 12. Test Coverage Philosophy

本项目不以单纯的：

```text
Test Case Count
```

衡量测试质量。

更关注：

```text
Risk Coverage
+
Behavior Coverage
+
State Coverage
+
Boundary Coverage
+
Real-State Coverage
+
Recovery Coverage
```

尤其要避免：

> 大量测试正常成功路径，却没有覆盖 failed / unknown / ambiguity / duplicate / stale / insufficient / unsupported。

---

## 13. What This Strategy Does Not Do

本文件不负责：

- 定义完整 Test Matrix；
- 编写具体 Test Case；
- 执行测试；
- 修改 Agent；
- 修复 Defect；
- 判断具体 Failure 是否已经发生；
- 生成最终 Test Result。

这些工作分别进入后续 QA artifacts。

---

## 14. Output to Next QA Artifacts

本 Test Strategy 为后续文件提供以下输入：

```text
03 Test Strategy
        │
        ├── Test Objectives
        ├── Test Approaches
        ├── Test Oracle
        ├── Test Environment
        ├── Test Data
        ├── Test Techniques
        ├── Evidence Strategy
        ├── Execution Model
        │
        ▼
04 Test Matrix
        │
        ▼
05 Test Cases
        │
        ▼
Baseline Freeze
        │
        ▼
06 Test Results
        │
        ▼
07 Defects
```

---

## 15. QA Analysis Boundary

Section 3 的核心边界是：

> **Risk 决定测试关注什么；Test Strategy 决定如何验证这些风险；Test Matrix 决定覆盖哪些组合；Test Cases 决定具体执行什么。**

因此本文件不提前定义具体 Case，也不根据当前实现状态直接修改 Agent。

正式 QA 应保持：

```text
Spec
  ↓
Risk
  ↓
Strategy
  ↓
Matrix
  ↓
Cases
  ↓
Freeze
  ↓
Execution
  ↓
Evidence
  ↓
Defect
```

这条链路的顺序，保证测试结论可以追溯到 Spec 和 Risk，而不是追溯到某一次临时的开发修改。
