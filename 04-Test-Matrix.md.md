# 04 Test Matrix

> **状态：HISTORICAL V1 QA ARTIFACT / SUPERSEDED。** 当前架构边界见 [`docs/protocol-v2.md`](docs/protocol-v2.md)；本文件保留 V1 测试矩阵记录。

> QA Baseline Artifact — calendar-agent V1
>
> 本文件把 `02-risk-analysis.md` 中识别的风险，以及 `03-test-strategy.md` 中定义的测试方法，转换成结构化的 **Test Coverage Matrix**。
>
> 本文件回答的是：
>
> **“需要覆盖哪些测试维度和场景组合？”**
>
> 它还不是具体 Test Case；具体输入、步骤、Expected Result 将在 `05-test-cases.md` 中定义。
>
> **当前 Agent 仍可处于开发阶段。正式执行前，应在 Test Case Design 完成后冻结被测版本。**

---

## 1. Test Matrix Purpose

### 1.1 Matrix Objective

Test Matrix 的作用是建立：

```text
Risk
  ↓
Behavior Dimension
  ↓
Scenario Family
  ↓
Coverage
  ↓
Test Case
```

它用于防止：

- 只测试 Happy Path；
- 只测试最终 Final Message；
- 只测试 Tool Schema；
- 忽略异常状态；
- 忽略真实 Calendar / Reminder State；
- 忽略 UNKNOWN / recovery；
- 忽略 clarification；
- 忽略 V1 boundary；
- 忽略 idempotency；
- 忽略跨 Tool dependency。

---

## 2. Coverage Dimensions

本项目 Test Matrix 至少覆盖以下维度：

| Dimension | 核心问题 |
|---|---|
| Object | Calendar Event / Reminder |
| Intent | Query / Create / Update / Delete |
| Parameter State | Valid / Missing / Ambiguous / Invalid |
| Time Semantics | Concrete / Relative / Window / All-day |
| Target State | Unique / Multiple / None / Stale |
| Query Result | Non-empty / Empty / Insufficient / Stale / Failed / Unknown |
| Write State | Not executed / Success / Failed / Unknown |
| Safety | Safe / Conflict / Duplicate / Boundary violation |
| Lifecycle | Normal / Clarification / Recovery / Partial completion |
| Idempotency | First execution / Retry / Duplicate delivery |
| Tool | 8 V1 tools |
| Protocol | Request / Result / Final |
| Real State | Before / After / Verification |
| Boundary | Supported / Unsupported |
| Communication | Success / Failure / Unknown / Partial |

---

## 3. Object × Intent Matrix

| Object | Query | Create | Update | Delete |
|---|---:|---:|---:|---:|
| Calendar Event | ✓ | ✓ | ✓ | ✓ |
| Reminder | ✓ | ✓ | ✓ | ✓ |

### Coverage Notes

必须验证：

- Calendar 与 Reminder 不混淆；
- 同一 Intent 在两个 Object 上的行为符合各自 Schema / Protocol；
- 不支持的 Object × Intent 组合应正确进入 boundary handling。

---

## 4. Parameter State Matrix

| Parameter State | Query | Create | Update | Delete | Expected Coverage |
|---|---:|---:|---:|---:|---|
| Valid | ✓ | ✓ | ✓ | ✓ | 正常执行 |
| Missing required | ✓ | ✓ | ✓ | ✓ | clarification / failure |
| Ambiguous | ✓ | ✓ | ✓ | ✓ | clarification / target resolution |
| Invalid | ✓ | ✓ | ✓ | ✓ | reject / clarification / failure |
| Context-derived | ✓ | ✓ | ✓ | ✓ | 验证来源与合法性 |
| Default | ✓ | ✓ | ✓ | ✓ | 仅允许 Spec 支持的 default |

重点不是机械覆盖所有格子，而是确保每个高风险 Parameter State 都有代表性测试。

---

## 5. Time Semantics Matrix

| Time Type | Query | Event Create | Event Update | Reminder Create | Reminder Update |
|---|---:|---:|---:|---:|---:|
| Concrete time | ✓ | ✓ | ✓ | ✓ | ✓ |
| Relative date | ✓ | ✓ | ✓ | ✓ | ✓ |
| Morning | ✓ | ✓ | ✓ | — | — |
| Afternoon | ✓ | ✓ | ✓ | — | — |
| Evening | ✓ | ✓ | ✓ | — | — |
| Missing time | ✓ | ✓ | ✓ | context-dependent | context-dependent |
| Explicit all-day | ✓ | ✓ | ✓ | — | — |
| Ambiguous date/time | ✓ | ✓ | ✓ | ✓ | ✓ |
| Timezone boundary | ✓ | ✓ | ✓ | ✓ | ✓ |

重点验证：

- morning / afternoon / evening 不是 concrete time；
- 缺少具体时间时不能无依据执行普通 timed Event Create；
- 只有明确全天语义才能使用 `all_day=true`；
- relative date 必须可以唯一推导；
- 时间与时区必须保持一致。

---

## 6. Calendar Event Matrix

### 6.1 Calendar Query

覆盖：

| Scenario | Coverage |
|---|---|
| Existing events in range | ✓ |
| Empty result | ✓ |
| Multiple candidate events | ✓ |
| Conflict check | ✓ |
| Duplicate detection | ✓ |
| Availability query | ✓ |
| Target resolution | ✓ |
| Verify state | ✓ |
| Insufficient query range | ✓ |
| Stale result | ✓ |
| Failed query | ✓ |
| Unknown query | ✓ |

---

### 6.2 Calendar Event Create

覆盖：

| Scenario | Coverage |
|---|---|
| Valid timed event | ✓ |
| Valid all-day event | ✓ |
| Missing title | ✓ |
| Missing date | ✓ |
| Missing concrete start time | ✓ |
| Missing duration/end | ✓ |
| Ambiguous time | ✓ |
| Morning/afternoon/evening | ✓ |
| Duplicate candidate exists | ✓ |
| Conflict exists | ✓ |
| Explicit all-day | ✓ |
| No explicit all-day | ✓ |
| Invalid time range | ✓ |
| Tool success | ✓ |
| Tool failed | ✓ |
| Tool unknown | ✓ |
| Post-write verification | ✓ |

---

### 6.3 Calendar Event Update

覆盖：

| Scenario | Coverage |
|---|---|
| Unique target | ✓ |
| Multiple candidates | ✓ |
| Target not found | ✓ |
| Stable event_id | ✓ |
| Change title | ✓ |
| Change start/end | ✓ |
| Change all_day | ✓ |
| Change location | ✓ |
| Change notes | ✓ |
| Empty changes | ✓ |
| Invalid changes | ✓ |
| Conflict after update | ✓ |
| Tool failed | ✓ |
| Tool unknown | ✓ |
| Retry / idempotency | ✓ |
| Post-write verification | ✓ |

---

### 6.4 Calendar Event Delete

覆盖：

| Scenario | Coverage |
|---|---|
| Unique target | ✓ |
| Multiple candidates | ✓ |
| Target not found | ✓ |
| Stable event_id | ✓ |
| Delete success | ✓ |
| Delete failed | ✓ |
| Delete unknown | ✓ |
| Retry / idempotency | ✓ |
| Verify deletion | ✓ |
| High-risk batch delete | ✓ |
| Unsupported multi-target delete | ✓ |

---

## 7. Reminder Matrix

### 7.1 Reminder Query

覆盖：

| Scenario | Coverage |
|---|---|
| all_incomplete | ✓ |
| specific_list | ✓ |
| time_range | ✓ |
| Empty result | ✓ |
| Multiple candidates | ✓ |
| Target resolution | ✓ |
| Verify state | ✓ |
| Insufficient range | ✓ |
| Stale result | ✓ |
| Failed | ✓ |
| Unknown | ✓ |

---

### 7.2 Reminder Create

覆盖：

| Scenario | Coverage |
|---|---|
| Valid reminder | ✓ |
| Valid reminder_time | ✓ |
| Missing title | ✓ |
| Missing reminder_time | ✓ |
| Ambiguous time | ✓ |
| Invalid time | ✓ |
| Calendar pre-check performed | ✓ |
| Calendar pre-check missing | ✓ |
| Calendar result insufficient | ✓ |
| Calendar result stale | ✓ |
| Time reasonableness accepted | ✓ |
| Time reasonableness rejected / clarification | ✓ |
| Tool success | ✓ |
| Tool failed | ✓ |
| Tool unknown | ✓ |
| Post-write verification | ✓ |

---

### 7.3 Reminder Update

覆盖：

| Scenario | Coverage |
|---|---|
| Unique target | ✓ |
| Multiple candidates | ✓ |
| Target not found | ✓ |
| Change title | ✓ |
| Change reminder_time | ✓ |
| Change completed | ✓ |
| Change notes | ✓ |
| Empty changes | ✓ |
| Calendar pre-check performed | ✓ |
| Calendar pre-check missing | ✓ |
| Invalid changes | ✓ |
| Tool failed | ✓ |
| Tool unknown | ✓ |
| Retry / idempotency | ✓ |
| Post-write verification | ✓ |

---

### 7.4 Reminder Delete

覆盖：

| Scenario | Coverage |
|---|---|
| Unique target | ✓ |
| Multiple candidates | ✓ |
| Target not found | ✓ |
| Stable reminder_id | ✓ |
| Delete success | ✓ |
| Delete failed | ✓ |
| Delete unknown | ✓ |
| Retry / idempotency | ✓ |
| Verify deletion | ✓ |
| High-risk batch delete | ✓ |

---

## 8. Semantic Coverage Matrix

| Semantic Risk | Positive | Negative | Boundary | Recovery |
|---|---:|---:|---:|---:|
| Object classification | ✓ | ✓ | ✓ | — |
| Intent classification | ✓ | ✓ | ✓ | — |
| Facts vs action | ✓ | ✓ | ✓ | — |
| Create vs Update | ✓ | ✓ | ✓ | ✓ |
| Duplicate interpretation | ✓ | ✓ | ✓ | ✓ |
| Missing parameter | ✓ | ✓ | ✓ | ✓ |
| Ambiguous parameter | ✓ | ✓ | ✓ | ✓ |
| Relative date | ✓ | ✓ | ✓ | — |
| All-day | ✓ | ✓ | ✓ | — |
| Time window | ✓ | ✓ | ✓ | ✓ |

---

## 9. Tool Request Matrix

### 9.1 Tool Selection

| User Goal | Expected Tool Family |
|---|---|
| Query Calendar | `query_calendar` |
| Query Reminder | `query_reminders` |
| Create Event | `create_calendar_event` |
| Update Event | `update_calendar_event` |
| Delete Event | `delete_calendar_event` |
| Create Reminder | `create_reminder` |
| Update Reminder | `update_reminder` |
| Delete Reminder | `delete_reminder` |

---

### 9.2 Tool Request Contract

每个 Tool Request 至少需要覆盖：

| Dimension | Coverage |
|---|---:|
| Correct `type` | ✓ |
| Correct `tool` | ✓ |
| Correct request_id | ✓ |
| Correct conversation_id | ✓ |
| Correct task_id | ✓ |
| Correct step_id | ✓ |
| Query has `purpose` | ✓ |
| Query has no `operation_id` | ✓ |
| Write has `operation_id` | ✓ |
| Correct arguments | ✓ |
| Required fields | ✓ |
| Optional fields | ✓ |
| Invalid extra fields | ✓ |
| Operation ID reuse on retry | ✓ |

---

## 10. Tool Result Matrix

| Tool Result State | Query | Write | Lifecycle |
|---|---:|---:|---|
| Success | ✓ | ✓ | normal |
| Empty success | ✓ | — | normal |
| Failed | ✓ | ✓ | failure |
| Unknown | ✓ | ✓ | recovery |
| Insufficient | ✓ | ✓* | validation |
| Stale | ✓ | ✓* | re-query / verify |
| Invalid correlation | ✓ | ✓ | reject / recover |
| Missing required result field | ✓ | ✓ | reject / recover |

`*` 具体适用场景取决于 Tool Result 是否能够支持当前业务决策。

重点验证：

- `executed_at`；
- query 的 `fetched_at`；
- query 的 `queried_range` / `query_scope`；
- write 的 `operation_id`；
- success 的 `result` / `results`；
- failed / unknown 的 `error`；
- correlation fields。

---

## 11. Lifecycle Matrix

### 11.1 Task State

| State Family | Coverage |
|---|---|
| received | ✓ |
| validating_input | ✓ |
| analyzing | ✓ |
| planning | ✓ |
| waiting_tool_result | ✓ |
| validating_tool_result | ✓ |
| waiting_clarification | ✓ |
| analyzing_clarification | ✓ |
| pre_execution_check | ✓ |
| verifying_final_state | ✓ |
| recovering | ✓ |
| succeeded | ✓ |
| failed | ✓ |
| unknown | ✓ |

---

### 11.2 Operation State

| Operation State | Coverage |
|---|---|
| planned | ✓ |
| dispatched | ✓ |
| success | ✓ |
| failed | ✓ |
| unknown | ✓ |
| verified_success | ✓ |
| verified_failure | ✓ |

重点验证：

```text
planned
  ↓
dispatched
  ↓
success / failed / unknown
  ↓
verification
  ↓
verified_success / verified_failure
```

---

### 11.3 Terminal State Matrix

| Terminal State | Expected Meaning |
|---|---|
| succeeded | User goal completed and real state confirmed |
| failed | User goal not completed after allowed recovery |
| unknown | Real state cannot be confirmed |

必须覆盖：

- terminal state 后无继续 Tool execution；
- terminal state 与 Final status 一致；
- success 不能只依赖 Tool success；
- unknown 不能被包装成确定 success。

---

## 12. Clarification Matrix

| Clarification Reason | Coverage |
|---|---:|
| missing_required_parameter | ✓ |
| ambiguous_parameter | ✓ |
| ambiguous_target | ✓ |
| schedule_conflict | ✓ |
| possible_duplicate | ✓ |
| tool_result_uncertain | ✓ |
| recovery_decision_required | ✓ |

每类至少验证：

- reason；
- message；
- expected_answer；
- optional missing_fields；
- optional ambiguous_fields；
- optional candidates；
- current task preserved；
- confirmed information preserved；
- completed steps preserved。

---

## 13. Recovery Matrix

| Failure Condition | Verify | Retry | Clarify | Final |
|---|---:|---:|---:|---:|
| Tool failed | possible | possible | possible | ✓ |
| Tool unknown | required | only when safe | possible | ✓ |
| Stale query | ✓ | re-query | possible | ✓ |
| Insufficient query | ✓ | re-query | possible | ✓ |
| Ambiguous target | — | — | required | ✓ |
| Duplicate risk | ✓ | — | possible | ✓ |
| Partial multi-step failure | ✓ | unfinished only | possible | ✓ |

特别验证：

> UNKNOWN 不允许未经验证直接重新执行 Write。

---

## 14. Idempotency Matrix

| Scenario | Expected Coverage |
|---|---|
| First write execution | ✓ |
| Same operation_id repeated | ✓ |
| Retry after timeout | ✓ |
| UNKNOWN after write | ✓ |
| Verify before retry | ✓ |
| New operation_id on same logical retry | Negative |
| Duplicate Tool Result | ✓ |
| Completed operation re-dispatch | Negative |
| Duplicate Create side effect | Negative |

核心 Oracle：

```text
Same logical operation
        +
same operation_id
        ↓
must not create unintended duplicate side effect
```

---

## 15. Real-State Verification Matrix

| Write Operation | Post-Write Verification |
|---|---|
| Create Calendar Event | ✓ |
| Update Calendar Event | ✓ |
| Delete Calendar Event | ✓ |
| Create Reminder | ✓ |
| Update Reminder | ✓ |
| Delete Reminder | ✓ |

Verification 需要检查：

- target；
- relevant changed fields；
- existence / absence；
- final state；
- correlation to original operation。

---

## 16. Query Freshness / Sufficiency Matrix

| Query Condition | Expected Behavior |
|---|---|
| Fresh + sufficient | Continue |
| Fresh + insufficient | Re-query / clarification |
| Stale + sufficient-looking | Revalidate |
| Stale + insufficient | Re-query |
| Empty + valid scope | Treat as valid empty result |
| Empty + insufficient scope | Do not infer absence |
| Failed | Recovery / failure |
| Unknown | Recovery / unknown |

---

## 17. Safety Matrix

| Safety Check | Query | Create | Update | Delete |
|---|---:|---:|---:|---:|
| Intent alignment | ✓ | ✓ | ✓ | ✓ |
| Target validation | — | — | ✓ | ✓ |
| Parameter validation | ✓ | ✓ | ✓ | ✓ |
| Dependency state | — | ✓* | ✓* | ✓ |
| Conflict check | possible | ✓ | ✓ | possible |
| Duplicate check | possible | ✓ | possible | — |
| V1 boundary | ✓ | ✓ | ✓ | ✓ |
| Idempotency | — | ✓ | ✓ | ✓ |
| Final verification | — | ✓ | ✓ | ✓ |

`*` Reminder Create / Update 的 Calendar pre-check 是明确的特殊依赖。

---

## 18. V1 Boundary Matrix

### 18.1 Supported

| Capability | Expected |
|---|---|
| Calendar Query | Supported |
| Calendar Create | Supported |
| Calendar Update | Supported |
| Calendar Delete | Supported |
| Reminder Query | Supported |
| Reminder Create | Supported |
| Reminder Update | Supported |
| Reminder Delete | Supported |

---

### 18.2 Unsupported

| Capability | Expected Handling |
|---|---|
| Hermes | Unsupported |
| Gmail | Unsupported |
| Feishu | Unsupported |
| Research Agent | Unsupported |
| Multi-agent | Unsupported |
| Parallel Tool execution | Unsupported |
| Generic transaction orchestration | Unsupported |
| Complex auto-compensation | Unsupported |
| High-risk batch delete/update | Unsupported |
| Old protocol compatibility | Unsupported |

High-risk unsupported operation必须验证：

```text
User Request
   ↓
Agent identifies boundary
   ↓
Final failure
   ↓
NO forbidden Write Tool Request
```

---

## 19. Multi-Step Matrix

| Scenario | Single Step | Multi-Step | Partial Failure | Recovery |
|---|---:|---:|---:|---:|
| Query then Write | — | ✓ | ✓ | ✓ |
| Multiple serial writes | — | ✓ | ✓ | ✓ |
| Query → clarification → write | — | ✓ | ✓ | ✓ |
| Write → verify | — | ✓ | ✓ | ✓ |
| Unknown → verify | — | ✓ | ✓ | ✓ |
| Parallel Tool execution | Negative | Negative | Negative | Negative |
| Generic transaction orchestration | Negative | Negative | Negative | Negative |
| Complex compensation | Negative | Negative | Negative | Negative |

核心约束：

- serial；
- one Tool Request at a time；
- completed steps 不重复；
- unfinished steps 才能恢复；
- unknown 必须验证；
- 不执行复杂自动 compensation。

---

## 20. Final Response Matrix

| Outcome | Expected Final Status | Required Truth |
|---|---|---|
| Query completed | success | Query result correctly represented |
| Write verified | success | Real state confirmed |
| Allowed recovery exhausted | failure | Goal not completed |
| Real state cannot be confirmed | unknown | Uncertainty explicitly preserved |
| Unsupported operation | failure | V1 boundary respected |
| Partial multi-step completion | failure / appropriate non-success | Partial state honestly represented |

同时验证 Final Message：

- brief；
- natural；
- result-first；
- 不暴露内部 Tool / JSON / IDs；
- 不把 unknown 说成 success；
- 不把 partial completion 说成 complete。

---

## 21. Negative Coverage Matrix

Negative testing 至少覆盖：

| Negative Category | Coverage |
|---|---:|
| Missing parameter | ✓ |
| Ambiguous parameter | ✓ |
| Invalid parameter | ✓ |
| Invalid time range | ✓ |
| Wrong object | ✓ |
| Wrong intent | ✓ |
| Wrong tool | ✓ |
| Wrong target | ✓ |
| Multiple candidates | ✓ |
| Insufficient query | ✓ |
| Stale result | ✓ |
| Failed Tool | ✓ |
| Unknown Tool | ✓ |
| Invalid correlation | ✓ |
| Missing operation_id | ✓ |
| Wrong operation_id reuse | ✓ |
| Duplicate write | ✓ |
| Unsupported operation | ✓ |
| High-risk batch write | ✓ |
| Invalid final success | ✓ |

---

## 22. Cross-Layer Coverage Matrix

| Scenario | Semantic | Tool | Protocol | State | Real State | Final |
|---|---:|---:|---:|---:|---:|---:|
| Simple Calendar Query | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Calendar Create | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Calendar Update | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Calendar Delete | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Reminder Create | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Reminder Update | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Reminder Delete | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Clarification | ✓ | ✓ | ✓ | ✓ | — | ✓ |
| Tool Failed | — | ✓ | ✓ | ✓ | — | ✓ |
| Tool Unknown | — | ✓ | ✓ | ✓ | ✓ | ✓ |
| Duplicate Write | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Partial Multi-Step | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Unsupported Operation | ✓ | ✓ | ✓ | ✓ | — | ✓ |

---

## 23. High-Risk Coverage Matrix

以下风险族必须进入后续 Test Cases：

| Risk Family | Required |
|---|---:|
| Object misclassification | ✓ |
| Intent misclassification | ✓ |
| Facts → action | ✓ |
| Missing required parameter | ✓ |
| Ambiguous time | ✓ |
| Relative date | ✓ |
| All-day | ✓ |
| Duplicate candidate | ✓ |
| Target ambiguity | ✓ |
| Wrong Tool | ✓ |
| Query purpose | ✓ |
| Query range | ✓ |
| Reminder Calendar pre-check | ✓ |
| Write safety | ✓ |
| High-risk batch write | ✓ |
| Tool Result validation | ✓ |
| Task / Step / Operation correlation | ✓ |
| Clarification resume | ✓ |
| UNKNOWN recovery | ✓ |
| Idempotency | ✓ |
| Partial completion | ✓ |
| Post-write verification | ✓ |
| V1 boundary | ✓ |
| Final truthfulness | ✓ |

---

## 24. Coverage Gaps to Resolve in Test Cases

Test Matrix 本身不判断测试是否已经充分。进入 `05-test-cases.md` 前，需要检查：

1. 每个高风险族是否至少有一个具体 Test Case；
2. 高风险 Write 是否覆盖 success / failed / unknown；
3. Query 是否覆盖 empty / insufficient / stale；
4. Clarification 是否覆盖参数与 target 两类 ambiguity；
5. Idempotency 是否有真实 retry / duplicate 场景；
6. Multi-step 是否覆盖 partial completion；
7. V1 boundary 是否验证“没有发送 forbidden Write Tool Request”；
8. Final status 是否与真实状态一致；
9. 每个关键风险是否有对应 Oracle；
10. 每个需要真实状态验证的 Write 是否有 Post-Write Verification。

---

## 25. Matrix-to-Test-Case Mapping

后续 `05-test-cases.md` 应为每个 Test Case 建立至少一个 Matrix Trace：

```text
TC-XXX
  ↓
Object
  ↓
Intent
  ↓
Risk
  ↓
Matrix Dimension
  ↓
Test Strategy
  ↓
Expected Evidence
```

例如：

```text
Calendar Event Create
        ↓
Missing concrete start time
        ↓
Parameter Risk
        ↓
Negative / Boundary Testing
        ↓
Clarification expected
```

另一个例子：

```text
Calendar Event Create
        ↓
Tool Result = unknown
        ↓
Recovery + Idempotency Risk
        ↓
Fault Injection
        ↓
verify_state before retry
```

---

## 26. Test Matrix Boundary

本文件负责：

- 定义覆盖维度；
- 定义 Scenario Family；
- 定义 Risk → Coverage 的映射；
- 定义 Positive / Negative / Boundary / Recovery Coverage；
- 定义跨层 Coverage；
- 为 Test Case Design 提供输入。

本文件不负责：

- 编写完整 Test Steps；
- 定义具体 User Prompt；
- 定义每一个 Expected Result 的完整文字；
- 执行测试；
- 记录实际结果；
- 修改 Agent；
- 判断实际 Failure 是否为 Defect。

这些工作进入后续：

```text
04 Test Matrix
      ↓
05 Test Cases
      ↓
06 Test Results
      ↓
07 Defects
```

---

## 27. QA Baseline Readiness

完成本 Matrix 后，正式 QA Baseline 还需要：

```text
01 Spec Analysis       ✅
02 Risk Analysis       ✅
03 Test Strategy       ✅
04 Test Matrix         ✅
05 Test Cases          ← 下一步
        ↓
      Freeze
        ↓
06 Test Results
07 Defects
```

因此：

> **Test Matrix 完成 ≠ QA Baseline 已冻结。**

真正进入执行前，还需要完成 `05-test-cases.md`，确认具体测试数据、输入、步骤、Expected Evidence 与 Oracle，然后冻结被测 Agent 版本。

---

## 28. QA Analysis Boundary

Test Matrix 的核心职责是：

> **确保已经识别出的风险，在具体 Test Case Design 之前没有被遗漏。**

因此：

```text
Spec
  ↓
Risk
  ↓
Strategy
  ↓
Matrix
  ↓
Test Cases
```

其中 Matrix 是连接 **“为什么测”** 与 **“具体测什么”** 的桥梁。

如果某个 Risk 没有进入 Matrix，应在进入 Test Case Design 前补充，而不是等到 Test Execution 后才发现整个风险族没有覆盖。
