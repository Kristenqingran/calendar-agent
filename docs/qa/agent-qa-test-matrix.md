# Agent QA Test Matrix

> **状态：HISTORICAL V1 QA MATRIX / SUPERSEDED。** 本矩阵按 Protocol V1 的客户端执行模型编写；当前 Mac-first V2 验收边界请以 [`../protocol-v2.md`](../protocol-v2.md) 为准。历史测试风险与观察保留，不作为当前实现要求。

状态：基于当前工作区只读核查（2026-09-16）  
范围：`docs/protocol-v1.md`、`schemas/`、`docs/superpowers/`、`tests/`、`src/calendar_agent_protocol/` 及 Phase 2 completion plan。  
限制：本文件只描述测试矩阵；未修改生产代码或现有测试。

## 评级定义

- **A**：已有自动化测试覆盖，证据可定位到当前 `tests/`。
- **B**：当前实现或模型已存在，但当前没有足够自动化测试覆盖该规则/行为。
- **C**：规格要求，但当前实现尚未发现或明确超出当前 Phase 1/2 范围。
- **D**：规格、Schema、实现或测试之间存在歧义/缺口，无法安全断言行为；需先澄清或补充判定标准。
 
“覆盖”按矩阵行的主要验收点计数；一行可同时包含已有覆盖和缺口，但 `Existing Coverage` 只填最能代表该行当前状态的 A/B/C/D。

## 总览

| # | QA domain | Existing Coverage | Priorit[agent-qa-test-matrix.md](agent-qa-test-matrix.md)y | 当前判断 |
|---:|---|:---:|:---:|---|
| 1 | Input / Interface | A | P0 | 入站模型、旧字段拒绝、ID/时间/时区基础校验已有测试；HTTP 边界待验证 |
| 2 | LLM Semantic Understanding | C | P0 | LLM 语义分析与受约束输出未发现实现/测试 |
| 3 | Intent | C | P0 | Intent 枚举存在，但自然语言到 Intent 的判定器未发现 |
| 4 | Object | C | P0 | Object 枚举和数据模型存在，但语义判定/歧义澄清未发现 |
| 5 | Parameters | A | P0 | Tool 参数的结构、范围、全天/定时互斥有覆盖；动态关键参数判定未覆盖 |
| 6 | Context / Clarification | A | P0 | clarification 持久化/恢复与响应模型有部分覆盖；完整会话编排缺失 |
| 7 | Decision / Planning | C | P0 | 规划器、依赖查询和有限多步骤编排未发现 |
| 8 | Tool Selection | C | P0 | Tool 枚举/契约存在，但选择逻辑未发现 |
| 9 | Tool Arguments | A | P0 | 各类 Tool Request/Result 合同和非法组合已有覆盖 |
| 10 | Tool Execution | C | P0 | 后端不应执行真实日历访问；客户端执行闭环未发现 |
| 11 | Tool Result / Correlation | A | P0 | ID/operation/重复结果等 Phase 2 仓储行为部分有覆盖；完整关联守卫待验证 |
| 12 | State / Memory | A | P0 | 状态迁移、快照、重启相关基础测试已有；完整任务处理器未发现 |
| 13 | Idempotency | A | P0 | 入站 receipt、operation、tool result 重放/冲突已有覆盖；跨客户端持久化闭环待验证 |
| 14 | Timeout / UNKNOWN | A | P0 | UNKNOWN 枚举、锁定与终态保护有部分覆盖；超时触发机制未发现 |
| 15 | Recovery / Retry | A | P0 | clarification recovery 与 unknown operation lock 有部分覆盖；安全 retry 编排未发现 |
| 16 | Concurrency | A | P1 | 版本冲突、唯一性与事务基础有覆盖；真实并发场景仍待验证 |
| 17 | Final State Verification | C | P0 | `verify_state` 规则存在，但成功前验证编排未发现 |
| 18 | Final Response | A | P1 | response model、failure error、unsupported final 有覆盖；自然语言真实性待验证 |
| 19 | Safety / Permission | C | P0 | 安全门和后端无访问权限是规格要求，但执行层未发现 |
| 20 | End-to-End | C | P0 | 当前没有 HTTP→Agent→Tool→Result→Final 的实现或集成测试 |

## 详细矩阵

| QA domain | Requirement / Rule | Risk | Expected Behavior | Test Scenario | Test Type | Existing Coverage | Coverage Gap | Priority | Real-world Incident Prevented |
|---|---|---|---|---|---|:---:|---|:---:|---|
| Input / Interface | 入站 `user_request` 必须包含 `request_id`、`conversation_id`、`message`、`current_time`、`assistant_timezone`、`source`；旧字段必须拒绝；每个 HTTP 入站请求使用新 request ID。 | 缺字段、旧协议或重复 request ID 进入任务，导致关联和幂等错误。 | Schema/Pydantic 拒绝非法 payload；HTTP 层生成/校验 request ID 并在响应回显。 | 用 valid/invalid fixture 验证字段、时区、offset、未知字段；重复 HTTP request_id 验证 receipt 行为。 | Schema + contract + API integration | A | HTTP API、request_id 生成/回显和协议级重复请求测试未发现。 | P0 | 同一请求被当成两个任务，或响应无法关联原请求。 |
| LLM Semantic Understanding | System Prompt 只产生受约束语义分析；不得把事实陈述、计划或推测自动变成操作。 | “下周可能开会”被误创建日程，或自然语言遗漏关键信息。 | 对事实/计划/推测不生成写 Tool Request；输出可被 Schema 和代码守卫验证。 | 以陈述、愿望、假设、明确命令及中英文混合输入做 golden/对抗测试。 | LLM eval + property-based | C | 未发现 LLM adapter、分析输出消费逻辑或 semantic test harness。 | P0 | 用户无意创建/删除事项。 |
| Intent | `query/create/update/delete` 必须按用户目标判定；发现相似事项不得自动把 create 改 update。 | intent 漂移导致错误写入或错误查询。 | 明确查询/新增/修改/删除分别落到正确 intent；歧义停在 clarification。 | “查一下”“新建”“把…改成”“删掉”；“有个类似的，帮我建一个”必须仍为 create。 | LLM eval + decision table | C | 仅有 Intent 枚举；未发现自然语言 intent classifier。 | P0 | 新建被覆盖，或删除了错误对象。 |
| Object | 事件占时段用 `calendar_event`；单点待办用 `reminder`；会议类即使说“提醒我”仍优先事件；无法唯一判断必须澄清。 | Reminder/Event 混淆造成时间冲突、错误 Tool 或丢失时长。 | 语义分类符合规则；两者均合理时返回 clarification，不猜。 | 覆盖会议、面试、看病、课程、一次性待办、带“提醒我”的会议及模糊输入。 | LLM eval + clarification integration | C | 仅有 ObjectType/领域模型；未发现分类器和歧义流程。 | P0 | 重要会议被建成无时段提醒。 |
| Parameters | 普通事件必须有标题、日期、具体开始时间和时长/结束时间；不得默认时长；上午/下午不可自动具体化；明确全天才用全天字段。 | 缺参被猜补，事件时间错误或跨时区错误。 | 缺关键参数就 clarification；全天与定时字段互斥且范围有效。 | “明天下午开会”“明天全天休假”“明天开会一小时”；验证缺 start、缺 end/duration、反向范围。 | Contract + parameter decision + LLM eval | A | `tools.py`/domain/fixture 覆盖结构规则；动态 required-parameter 判定和不得默认时长的运行时路径未发现。 | P0 | 日历事件被错误安排在任意时间或错误持续时长。 |
| Context / Clarification | clarification 是当前任务暂停/恢复；必须保留已确认参数、有效结果和已完成步骤。 | 用户补充信息后重置任务或重做已完成写操作。 | 保存 pending clarification；只更新受影响参数/依赖；恢复到正确分析状态。 | 缺时间后补“16:00”；目标歧义后选候选；更新 start 使旧 query 失效；故障注入验证原子回滚。 | State integration + failure injection | A | `test_phase2.py`/`test_phase2_task_b.py` 覆盖部分 resolve/persistence；计划中的完整 contextual clarification service 未发现。 | P0 | 用户回答一次却触发重复 Tool 或丢失原上下文。 |
| Decision / Planning | 依赖真实状态时必须先发最小充分 query；写前必须通过目标、参数、依赖、冲突、重复、意图、风险、幂等安全门；每次最多一个 Tool Request。 | Agent 跳过查询、范围过大或并行发写请求。 | 规划出串行、可审计、最小充分步骤；未通过门禁不生成写请求。 | 创建事件遇到冲突/重复；更新需先 resolve target；Reminder 写前先查 Calendar；多步骤一条一条推进。 | Workflow integration | C | 未发现编排器、planning service、Phase 2 计划所述 services.py 或集成场景。 | P0 | 在不知目标或冲突的情况下直接修改真实数据。 |
| Tool Selection | 查询/写入 Tool 必须与 Object+Intent+Purpose 一致；查询不能带 operation_id，写入必须带 operation_id。 | 选择了错误资源或把查询当写操作。 | 仅生成 V1 支持的八类 Tool；不支持高风险批量写直接 final failure。 | 覆盖 calendar/reminder 四种 intent、answer_query/check_conflict/resolve_target/verify_state，以及批量删除。 | Decision table + contract integration | C | 枚举和响应模型有基础测试；Tool 选择策略未发现。 | P0 | 错删多个对象或对错误数据源执行写入。 |
| Tool Arguments | 客户端必须逐字段执行 arguments；日期时间带 UTC offset；IANA timezone；范围 end > start；稳定对象 ID 用于 update/delete。 | 参数被客户端重解释、截断或用显示名称代替稳定 ID。 | 合法参数原样传递；非法/额外字段被拒绝；update/delete 缺稳定 ID 不可发出。 | valid/invalid fixture；calendar_name 不冒充 calendar_id；定时/全天互斥；reminder query 三种 scope。 | Contract + schema parity | A | `test_tool_contracts.py`、`test_response_models.py`、`test_contract_parity.py` 有较好覆盖；客户端“原样执行”未发现。 | P0 | 更新了同名但非目标日程，或查询范围错误。 |
| Tool Execution | 真实 Calendar/Reminders 读取写入由客户端 Tool 完成；Agent 后端不得直接访问；客户端按返回 type 分支并回传真实结果。 | Agent 越权访问或客户端执行与请求不一致。 | 后端只生成 request/校验 result；客户端严格执行一次并回传新 request_id、原关联 ID。 | fake client tool：成功、failed、unknown、网络超时、客户端拒绝；验证未发生后端直连。 | Contract + client integration + permission test | C | 当前未发现 HTTP、客户端 adapter、真实 Tool executor 或权限测试。 | P0 | 后端泄露日历权限，或客户端静默修改请求。 |
| Tool Result / Correlation | Tool Result 必须匹配 conversation/task/step/tool；写结果复用 operation_id；校验 status、范围、字段、新鲜度和 purpose 充分性。 | 错任务结果推进当前任务，或不完整结果被猜补。 | 错配、过期、被替代 step、非 waiting 结果不推进；相同 payload 可 replay，冲突 payload 拒绝。 | 逐项替换 conversation/task/step/tool/operation；空结果 success vs failed/unknown；旧参数版本和 late result。 | Correlation integration + contract | A | `test_phase2.py` 有重复结果/基础关联；完整 `validate_tool_result_correlation` 行为按计划未发现实现/测试。 | P0 | A 任务收到 B 任务的成功结果并错误写入。 |
| State / Memory | Task 状态只能按允许迁移；终态不可再推进；必须保存 task、step、参数、exchange、operation、clarification 和审计。 | 重启后遗失状态，或非法状态导致重复执行。 | 状态迁移拒绝非法跳转；快照可重建；审计与状态同事务。 | 全部状态表；终态保护；关闭/重开 SQLite 恢复 pending query、clarification、operation、unknown。 | State machine + persistence integration | A | `test_phase2.py`、Task B 覆盖基础迁移/快照/事务；完整 restart recovery 目录未发现。 | P0 | 服务重启后重复删除或忘记已完成步骤。 |
| Idempotency | 每个逻辑写操作唯一 operation_id；重试复用原 ID；同 ID 不同参数拒绝；已成功 operation 重发不得二次写。 | 网络重试造成重复创建、重复删除或参数漂移。 | 相同 hash replay 原结果；不同 hash `IdempotencyConflict`；unknown 先 verify_state。 | 两 session 同 operation_id 同/异参数；成功 replay；unknown replay；入站 receipt 重放。 | Persistence + concurrency integration | A | `test_phase2.py`、`test_phase2_task_b.py` 已覆盖基础 operation/receipt；真实客户端重试和跨进程验证待验证。 | P0 | 用户收到两个相同提醒或重复扣除外部副作用。 |
| Timeout / UNKNOWN | Tool `unknown` 表示完成性不可确认；Task/Operation 不得当作 success/failed；unknown operation 必须先 verify_state。 | 超时后盲目重试，产生重复副作用或错误成功提示。 | timeout 映射为 unknown；锁定 operation；先 verify_state，再决定 replay/retry/clarification。 | Tool 无响应、连接断开、结果丢失但客户端可能已完成；验证三种最终状态。 | Fault injection + integration | A | UNKNOWN 枚举、终态和 `UnknownOperationLocked` 有基础覆盖；超时检测、verify_state 编排未发现。 | P0 | 网络抖动时重复创建日历事件。 |
| Recovery / Retry | 只允许安全、确定的 retry/re-query；已成功步骤不得重做；恢复改变用户意图时必须 clarification；复杂自动补偿不在 V1。 | 恢复逻辑扩大操作范围或覆盖用户意图。 | 失败后只恢复未完成步骤；unknown 先验证；不可确定时返回 clarification/failure/unknown。 | query retryable error、write failed、unknown write、后续步骤失败的有限多步骤任务。 | Workflow integration + failure injection | A | 基础 clarification recovery/unknown lock 有测试；retry policy 和有限多步骤 orchestrator 未发现。 | P0 | 部分成功任务被全量重跑，造成重复或数据损坏。 |
| Concurrency | 状态版本更新和唯一约束必须防止并发覆盖；同 operation 同参数 replay，异参数冲突。 | 两个 worker 同时推进同一 task 或 operation。 | 一个事务成功，另一方得到明确 concurrency/idempotency error；审计不重复。 | 两 session 并发 update/transition；两个 session create_or_replay；数据库唯一约束竞争。 | Database concurrency + integration | A | 版本冲突/唯一性基础已有；计划中的真实并发 operation 测试在当前 `tests/` 未发现，需验证。 | P1 | 并发请求产生双写或丢失状态迁移。 |
| Final State Verification | 所有 Create/Update/Delete 返回 success 前必须 `verify_state`；Tool success/LLM 输出/已生成 request 都不是 Task success 依据。 | Agent 报告成功但真实状态未写入、写错对象或删除失败。 | create 存在且字段正确；update 目标字段正确；delete 对象不存在；多步骤全部满足才 success。 | 外部 Tool 返回 success 但验证缺对象/字段不符；delete 仍存在；多步骤一成功一失败。 | End-to-end + state verification | C | `Purpose.VERIFY_STATE` 和协议规则存在，但 verify_state handler/流程未发现。 | P0 | 用户依赖一个实际上未完成的日程变更。 |
| Final Response | 每次最多一个顶层响应；failure 必须 error；最终 message 简短、结果优先，不暴露 Tool/JSON/内部 ID；unknown 必须如实表达。 | 泄露内部实现或把不确定结果说成成功。 | Schema 合法；状态与真实最终状态一致；空结果只有查询成功时才能说“没有”。 | success/failure/unknown、unsupported_operation、failed/unknown 空 results、内部 ID 扫描。 | Contract + response snapshot + E2E | A | `test_response_models.py` 覆盖结构/错误；自然语言真实性、敏感字段泄露和状态一致性未覆盖。 | P1 | 用户误以为删除成功，或看到内部 ID。 |
| Safety / Permission | 写前代码安全门必须检查目标、参数、依赖、冲突、重复、意图、V1 风险边界、幂等；高风险批量写必须 final failure/unsupported_operation；后端无日历访问权限。 | 模糊多目标删除/修改造成不可逆数据损失。 | 安全门任一失败都不生成写 request；批量写不因确认而放行；后端权限边界可证明。 | 范围/条件/集合批量删改；同名多对象；缺目标 ID；冲突/重复；后端尝试访问外部数据源。 | Security + policy integration | C | Schema 能表达单对象写请求，response 有 unsupported fixture；安全门和权限执行层未发现。 | P0 | 一次误删整个日历或修改多个客户事项。 |
| End-to-End | V1 闭环是自然语言客户端→HTTP API→Agent→Tool Request→Tool Result→clarification/final；单 Agent、串行、每次一个 Tool Request。 | 单元模型都通过但真实闭环关联、状态和最终判定断裂。 | 八类典型轨迹端到端通过，包含 clarification、冲突、重复、unknown、有限多步骤和重启。 | 查询、创建、修改、删除 Calendar；查询/创建 Reminder；澄清后继续；unknown 后验证；有限串行步骤。 | E2E integration | C | 当前仅有模型/仓储测试；未发现 HTTP、Agent orchestrator 或 E2E 场景。 | P0 | 发布后首个真实请求无法完成闭环或错误写入。 |

## 当前最高优先级的 10 个测试风险

按“可能造成不可逆真实数据影响 + 当前缺少实现/覆盖”排序：

1. 写前安全门未发现：模糊多目标删除/修改可能生成写请求。
2. Final State Verification 未实现/未验证：Tool success 可能被错误当成任务成功。
3. UNKNOWN/超时恢复未闭环：写操作超时后可能盲目重试。
4. LLM 未覆盖事实陈述、默认时长、对象/Intent 歧义等高风险语义。
5. Tool Result correlation 的完整 stale/late/conflict 守卫未发现。
6. HTTP request_id 生成、回显和重复入站行为未验证。
7. 客户端 Tool 严格执行 arguments、回传真实结果和关联 ID 未验证。
8. 多步骤任务的串行推进、部分成功和只恢复未完成步骤未验证。
9. 真实并发 operation 的同/异参数竞争结果未在当前测试目录确认。
10. End-to-End 闭环未实现/未覆盖，无法证明单元合同之间的集成一致性。

## 建议下一步实际执行的测试组

优先执行 **P0 安全写闭环组**，顺序如下：

1. 先确认当前分支真实文件状态：是否存在计划所述 `services.py`、Phase 2 unit/integration 目录及 HTTP/Agent 入口。
2. 用 fake client Tool 构造 create/update/delete 的成功、failed、unknown 结果，验证 operation_id、correlation、UNKNOWN 锁定和 replay。
3. 加入写前安全门与 `verify_state` 的集成场景：冲突、重复、错误目标、批量写、验证失败均不得返回 success 或发出不安全写请求。
4. 再执行同一组的 clarification、重启恢复和双 session 并发变体。
5. 最后才扩展 LLM 语义 golden 集，避免在状态/安全闭环未成立时把语义问题误判为 Tool 或持久化问题。

## 证据索引

- 规范主依据：`docs/protocol-v1.md`
- 机器合同：`schemas/*.schema.json`
- 当前协议实现：`src/calendar_agent_protocol/messages.py`、`tools.py`、`types.py`、`enums.py`
- 当前状态/持久化实现：`src/calendar_agent_protocol/domain.py`、`persistence.py`、`repository.py`
- 已发现测试：`tests/test_inbound_models.py`、`test_tool_contracts.py`、`test_response_models.py`、`test_contract_parity.py`、`test_phase2.py`、`test_phase2_task_a.py`、`test_phase2_task_b.py`、`test_domain_models.py`、`test_common_types.py`、`test_schema_meta.py`
- Phase 2 计划：`docs/superpowers/plans/2026-09-05-phase2-completion.md`
