# Protocol V2 Mac-first 架构迁移实施计划

> **执行说明：** 本计划按任务逐步执行，使用测试先行；本轮不提交、不推送。

**目标：** 保留并冻结 Protocol V1，建立中文的 Protocol V2 与 ADR，将外部 HTTP 会话边界和内部 Mac-first Tool Execution Contract 分离，并同步必要模型、Schema、Host 合约、测试及当前规范引用。

**架构：** User Client 只与 Agent API 处理用户会话；AgentRuntime 通过 ToolDispatcher/MacAgentHostAdapter 调用本机 MacAgentHost。外部 HTTP 使用 `request_id`，内部每次 Tool 调用使用 `execution_id`，逻辑写操作使用稳定 `operation_id`。

**技术栈：** Python 3.12、Pydantic、JSON Schema、SQLAlchemy、Swift/AppKit/EventKit、pytest、xcodebuild。

**规格：** 附件 `已粘贴的文本.txt`；架构依据 `docs/audit/mac-first-protocol-reconciliation-proposal.md`。

## 全局约束

- `docs/protocol-v1.md` 保持原样，状态为 Historical / Frozen。
- 新建 `docs/protocol-v2.md` 为 Current / Canonical；中文正文，正式 identifier 保留英文。
- Calendar Create 主链路与真实 EventKit 不得被测试改成伪成功；不操作真实 Calendar。
- 本轮不实现 Clarification Resume、Reminder、Calendar Update/Delete、Production LLM。
- 不改 Shortcut、Cloudflare、VPN/Xray、路由器、防火墙、secret/token。
- 保留工作区既有未提交改动，不提交、不推送。
- 已知 `inbound-naive-datetime` parity 失败保持记录，不顺手修复。

## 重点审查输入

1. 外部 HTTP retry：同一 `request_id` 不得重复创建 Task 或执行写操作；由 Server/Runtime 幂等测试覆盖。
2. Tool execution retry：同一 `operation_id`、新 `execution_id`；结果必须与本次执行关联，覆盖执行合约测试。
3. ToolResult 丢失/延迟/重复：不能误认成新的 HTTP inbound，也不能产生 Final.success；覆盖 Runtime/Host correlation 测试。
4. query `verify_state`：不带 `operation_id`，但带独立 `execution_id` 并与 Task/Step 关联；覆盖验证路径。
5. 实际 MacHost JSON-lines：Swift 与 Python 字段名/相关 ID 一致；运行 Host build 和契约测试，不创建真实事件。

---

### 任务 1：建立 V2 合约失败测试

**文件：**
- 修改：`tests/test_contract_parity.py`
- 修改：`tests/test_tool_contracts.py`
- 修改：`tests/test_dispatcher.py`
- 修改：`tests/test_runtime_tool_loop.py`
- 修改：`tests/test_server.py`

**接口约定：** 外部 `InboundMessage` 仅含 `UserRequest | ClarificationResponse`；内部 `ToolRequest` 与 `ToolResult` 使用 `execution_id`、`causation_request_id`，不使用内部新造的 HTTP `request_id`。写操作重试复用 `operation_id`，每次尝试更换 `execution_id`。

- [x] 增加测试：公共 Agent Response 不返回内部 Tool Request；HTTP Final/Clarification 回显本轮 `request_id`。
- [x] 增加 parity 测试：Tool Request/Result 的 `execution_id` 与 `causation_request_id` 必需，禁止旧的内部 `request_id`。
- [x] 增加 dispatcher 测试：结果必须匹配 execution/task/step/op/tool；Tool success 仍需 Verification。
- [x] 运行相关测试，确认因 V2 contract 尚未实现而失败，而非测试自身错误。

### 任务 2：创建中文 Protocol V2 与 ADR

**文件：**
- 创建：`docs/protocol-v2.md`
- 创建：`docs/architecture/adr/ADR-001-mac-first-tool-execution.md`
- 修改：`README.md`、当前架构说明及规范优先级引用文件

- [x] 从 Protocol V1 保留 Object、Intent、参数语义、Clarification、Task、Safety、Verification、Final 与工具定义。
- [x] 将 V2 明确标注为 Current / Canonical，将 V1 标注 Historical / Frozen，保留 V1 文件内容。
- [x] 写清 User Client、Agent API、Agent Core、Tool Execution Layer、MacAgentHost、Capability 的职责边界。
- [x] 写清公开 HTTP 与内部 Tool Request/Result 的分离、V2 ID 语义、幂等、Verification 与能力覆盖状态。
- [x] 检查当前规范链接和历史文档标记；新增/更新的规范正文使用中文，identifier 保留英文。

### 任务 3：同步 Schema 与 Python 合约模型

**文件：**
- 创建 V2 版本：`schemas/inbound-v2.schema.json`、`schemas/agent-response-v2.schema.json`、`schemas/tool-request-v2.schema.json`、`schemas/tool-result-v2.schema.json`、`schemas/common-v2.schema.json`；V1 schemas 保持冻结
- 必要时修改：`src/calendar_agent_protocol/messages.py`、`tools.py`、`runtime_contract.py`

- [x] 更新测试夹具/测试断言为 V2 字段并验证预期红灯。
- [x] 外部 inbound schema 只承载 UserRequest 与 ClarificationResponse；ToolResult 改为内部执行结果合约。
- [x] 公共 Agent Response 只包含 Clarification/Final；内部 Runtime decision 仍可包含 ToolRequest。
- [x] 内部 Tool Request/Result 加入 `execution_id` 和 `causation_request_id`；移除其 HTTP `request_id` 字段语义。
- [x] 增加严格 parity，除既有 naive-datetime fixture 外保持 Schema/Pydantic 一致。

### 任务 4：同步 Runtime、Dispatcher 与 MacAgentHost 执行相关 ID

**文件：**
- 修改：`src/calendar_agent_protocol/runtime.py`、`dispatcher.py`、`calendar_workflow.py`、`planning.py`、`verification.py`、`mac_host.py`
- 修改：`mac_gateway/mac_agent_host.swift`
- 修改：对应 Runtime、Dispatcher、Mac Host、Verification 测试

- [x] Runtime 在每次执行尝试前创建并持久化新的 `execution_id`，保留当前外部 `causation_request_id`。
- [x] Tool Request 与 Tool Result 使用同一 execution/task/step/causation；写结果保留原 `operation_id`；query 不含 operation ID。
- [x] Final/Clarification HTTP response 使用触发当前响应的 HTTP `request_id`。
- [x] Swift Host 解码并回传新的内部 execution correlation；Host 仅报告执行结果，不负责 Final 判定。
- [x] 增加 Python/Swift JSON-lines 字段契约测试与必要 xcodebuild。

### 任务 5：让当前 Server 边界明确为 V2 public API

**文件：**
- 修改：`src/calendar_agent_protocol/server.py`
- 修改：`tests/test_server.py`

- [x] Server 接受 V2 用户消息 envelope，生成或验证每次外部 HTTP 的 `request_id`，响应严格回显。
- [x] 公开响应不得泄漏内部 Tool Request/Tool Result；正常带 Dispatcher 的 Calendar Create 仍返回验证后的 Final。
- [x] ClarificationResponse schema 可验证，但本轮 Runtime resume 明确保持未实现；HTTP 边界拒绝不支持的消息形状，不新建 Task 假装恢复。
- [x] 不更改网络监听、认证方式或服务生命周期。

### 任务 6：幂等语义最小同步与安全测试

**文件：**
- 必要时修改：`src/calendar_agent_protocol/runtime.py`、`repository.py`
- 修改：`tests/test_runtime_tool_loop.py`、`tests/test_repository.py`（若存在）

- [x] 对同一逻辑 operation 重放时，Runtime 不再次 dispatch；相同 ID 不同参数继续拒绝。
- [x] operation 状态 unknown 时不得直接重试；Host journal 的 started 状态返回 unknown，Agent operation unknown 保持锁定。
- [x] `operation_id` 稳定而 `execution_id` 每次 attempt 唯一；增加确定性契约与 Swift journal 测试。
- [x] EventKit 与本地幂等记录 crash window 明确记录为开放可靠性问题；未引入跨系统事务或 Calendar 标记。

### 任务 7：更新当前规范引用与覆盖状态说明

**文件：**
- 修改：`01-岗位卡.md`、`02-工作流卡片.md`、`02-工作流程.md`、`03-流程图.md`、`README.md`、`system-prompt.txt`、`docs/runtime-contract-v1.md`（必要时注明历史状态）
- 修改：引用 Protocol V1 的当前性文档

- [x] 将当前引用指向 `docs/protocol-v2.md`；V1 引用明确标为历史规范。
- [x] 明确 Schema-defined 与当前可执行 capability 的区别；不宣称 Reminder、Update/Delete 已实现。
- [x] 将旧客户端执行架构保留为历史/演进资料，不删除其证据。
- [x] 不改 V1 正文、历史 Cloud/CalDAV 研究与 Shortcut 本体。

### 任务 8：最终验证

**文件：** 无额外范围

- [x] 运行 Schema/Domain parity、Tool contracts、Runtime、Server、MacHost、Verification、remote-access 相关测试。
- [x] 运行完整 `.venv/bin/python -m pytest -q` 并记录唯一已知 `inbound-naive-datetime` parity failure。
- [x] 运行 `git diff --check`。
- [x] 使用当前 Xcode 构建 MacAgentHost；未启动 Host 或执行真实 Calendar 操作。
- [x] 保留工作区既有更改；未提交、未推送。
