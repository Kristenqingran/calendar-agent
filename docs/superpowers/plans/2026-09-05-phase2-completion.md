# Phase 2 Completion Implementation Plan

状态：Approved-for-execution  
日期：2026-09-05  
依据：`docs/protocol-v1.md`、冻结的 Phase 2 内部设计、现有 143 项通过测试。  
边界：只补齐 Phase 2；不修改 Frozen Protocol 或外部 Schema；不进入 HTTP、LLM、Shortcut、部署或 Phase 3。

## 文件结构映射

- `domain.py`：内部枚举、TaskEntity、纯状态机。
- `persistence.py`：SQLAlchemy 映射与数据库引擎。
- `repository.py`：数据库无关的持久化接口和异常。
- `services.py`（新增）：带上下文的 Tool Result、clarification、step/operation 守卫和原子用例。
- `migrations/versions/0001_phase2.py`：既有基线。
- `migrations/versions/0002_query_dependencies.py`（新增）：dependency_parameters。
- `tests/phase2/unit/`（新增）：A–H 红绿测试。
- `tests/phase2/integration/test_scenarios.py`（新增）：八个完整场景。
- `tests/phase2/integration/test_restart_recovery.py`（新增）：migration 后重启恢复。
- `tests/test_phase2.py`：保留既有回归，不重写。

最小拆分仅新增 `services.py`，避免继续把业务上下文守卫塞进已偏重的 `repository.py`。

## TDD 通用循环

每个 Task 严格执行：RED（新增最小测试）→ 单独运行并确认因目标行为缺失而失败 → GREEN（最小实现）→ 单测变绿 → 相关回归 → Ruff/mypy → checkpoint。Checkpoint 是本地可提交边界；本计划不擅自创建 Git commit。

## [x] Task A：dependency_parameters 持久化

- 文件：修改 `persistence.py`、`repository.py`；新增 migration 0002；新增 `test_query_dependencies.py`。
- 依赖：ToolExchangeRow、save_request、TaskSnapshot。
- 接口：`save_request(..., dependency_parameters: set[str])`；Snapshot 返回排序后的集合。
- RED：空集合、集合 round-trip、migration up/down、restart snapshot；当前因字段不存在失败。
- GREEN：JSON 列保存排序去重列表；Repository 边界转换为集合；0002 add/drop column，默认 `[]`。
- 命令：`pytest tests/phase2/unit/test_query_dependencies.py -q`；回归 `pytest tests/test_phase2.py -q`。
- Checkpoint：query dependency 可迁移、可恢复，外部 Schema 未变化。

执行证据：RED 为 `1 failed`，原因是 `0001_phase2.py` 动态引用
`Base.metadata`；GREEN 为 Task A `3 passed`；相关回归 `67 passed`；完整回归
`146 passed`，Ruff 与 mypy strict 均通过。未创建 commit（当前目录未检测到可用 Git
工作流）。

## Task B：Repository API 完整化

- 文件：修改 `repository.py`；新增 `test_repositories.py`。
- 接口：Conversation `create/get/update_timezone`；Task `create/get/update_with_version/snapshot`；TaskParameter `upsert/get/list`；Step `create/get/complete`；ToolExchange `save_request/get/save_result/invalidate`；Operation `create_or_replay/get/mark_dispatched/record_result/record_verification`；Clarification `save/get_pending/resolve`；Transition `append/list`；Receipt `accept/get`。
- 约束：Transition/Receipt 无 update/delete；Operation 仅受控迁移；not-found、duplicate、concurrency 使用明确异常。
- RED：逐 Repository 测 create/get/合法 update/duplicate/not-found/rollback/version/immutable。
- GREEN：只实现上述允许接口；Repository 不决定业务状态。
- 命令：`pytest tests/phase2/unit/test_repositories.py -q`；回归全部 phase2 unit。
- Checkpoint：九类实体接口闭合。

## Task C：Contextual Transition Guard

- 文件：新增 `services.py`、`test_contextual_guard.py`。
- 接口：`next_state_after_tool_result(exchange, result_status, requested_target) -> TaskStatus`。
- RED：六种 write success 请求 planning/succeeded/failed 均拒绝；verifying_final_state 接受。
- GREEN：使用 Phase 1 `Tool.is_write`；不修改 ALLOWED_TRANSITIONS。
- 命令：目标测试；回归 state-machine tests。
- Checkpoint：结构状态机与上下文守卫职责分离。

## Task D：Tool Result Correlation 完整化

- 文件：修改 `services.py`、`repository.py`；新增 `test_tool_correlation.py`。
- 接口：`validate_tool_result_correlation(task, step, exchange, payload, parameter_version) -> ReplayDisposition`；值为 `advance/replay/stale_late`。
- RED：conversation/task/step/tool/operation 错配、非 waiting、非 active、非 pending、stale、旧参数版本、被替代 step、terminal、同 payload replay、不同 payload conflict。
- GREEN：先识别完全相同 replay，再执行终态和新鲜度守卫；stale/late 永不推进。
- 命令：目标测试；回归 ToolExchange/状态机测试。
- Checkpoint：关联矩阵完整。

## Task E：Atomic Clarification Update

- 文件：修改 `services.py`、`repository.py`；新增 `test_clarification_update.py`。
- 接口：`apply_clarification_update(session, task_id, step_id, updates, expected_version, reason) -> TaskSnapshot`。
- RED：start_time、target、duration 选择性失效；title/notes 无依赖不失效；故障注入全回滚。
- GREEN：同事务 resolve clarification、upsert TaskParameter、集合交集失效 query、完成 step、waiting_clarification→analyzing_clarification audit；TaskParameter 为唯一事实源。
- 命令：目标测试；回归 repositories/correlation。
- Checkpoint：选择性失效与原子恢复完成。

## Task F：Completed Step 防重复

- 文件：修改 `services.py`、`repository.py`；新增 `test_completed_step_guard.py`。
- 接口：`assert_step_dispatchable(step_id)`；`dispatch_tool_exchange(...)`。
- RED：completed step 重发、重复 exchange、推进 write operation 被拒；旧结果 replay 不新增 transition。
- GREEN：step 状态与 exchange 唯一约束双重守卫；继续必须新 step_id。
- 命令：目标测试；回归 step/tool/operation。
- Checkpoint：已完成步骤不可重执行。

## Task G：Audit Atomicity Failure Injection

- 文件：修改 `repository.py`（仅需要的事务边界）；新增 `test_audit_atomicity.py`。
- 接口：沿用 `TaskRepository.transition`，测试通过数据库事件让 audit INSERT 失败。
- RED：当前调用失败后若未显式 rollback 会留下脏 Session/状态。
- GREEN：UoW 捕获异常 rollback；状态 update 与 audit insert 同事务。
- 验证：数据库重新开 Session 后 state/version/audit 均为旧值。
- 命令：目标测试；回归 transition tests。
- Checkpoint：真实数据库原子性证据。

## Task H：Concurrent Operation Idempotency

- 文件：修改 `repository.py`；新增 `test_concurrent_operations.py`。
- 接口：沿用 `create_or_replay`，捕获唯一约束后重新读取并比较 hash。
- RED：两个 Session 同 ID 同/异 hash。
- GREEN：同 hash 返回 replay；异 hash 抛 IdempotencyConflict；最终一行。
- 命令：目标测试；回归 operation tests。
- Checkpoint：SQLite 并发幂等完成。

## Task I：Restart Recovery

- 文件：修改 Snapshot 映射；新增 `test_restart_recovery.py`。
- 接口：`load_task_snapshot(task_id)`（TaskRepository.snapshot 的稳定别名）。
- RED：四种 pending 状态分别写库、关闭 engine、重开后比较 task/current step/pending exchange/operation/clarification/stale/dependencies/completed steps。
- GREEN：补齐 Snapshot 查询与确定性排序，不缓存进程内对象。
- 命令：目标测试；Alembic 空库 upgrade 后运行；回归 migration tests。
- Checkpoint：仅靠 SQLite 恢复。

## Task J：八个完整集成场景

- 文件：新增 `tests/phase2/integration/test_scenarios.py`。
- 接口：复用 A–I，不新增编排器。
- RED/GREEN：逐个编码题述八条完整轨迹；每条先失败再补最小缺口。
- 命令：`pytest tests/phase2/integration/test_scenarios.py -q`；回归 `pytest -q`。
- Checkpoint：八场景均有独立自动化证据。

## 最终验证

1. `pytest -q`
2. `ruff check --no-cache src tests migrations`
3. `mypy src --strict`
4. 空 SQLite：Alembic upgrade → downgrade → upgrade。
5. migration 后写入 pending task，关闭连接，重开并恢复 Snapshot。
6. 对照原 Phase 2 清单逐项确认“实现 + 测试”。

## 自检

- 所有剩余验收项均映射到 A–J。
- 无 TBD/TODO；接口名在各 Task 中唯一且一致。
- 仅新增 services.py 与测试目录，属于必要职责拆分。
- 不修改 Frozen Protocol、ToolRequest/ToolResult Schema。
- 不包含 FastAPI、HTTP、LLM、Shortcut、真实 Calendar/Reminders、VPS 或 Phase 3。
