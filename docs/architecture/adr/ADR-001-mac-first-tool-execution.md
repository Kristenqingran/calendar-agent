# ADR-001：Mac-first Tool Execution 与 Protocol V2

- **状态：已采纳**
- **日期：2026-09-30**
- **决策范围：** Personal Agent V1 的外部 HTTP 与本机 Tool 执行边界
- **规范：** [`../../protocol-v2.md`](../../protocol-v2.md)
- **历史规范：** [`../../protocol-v1.md`](../../protocol-v1.md)，冻结保留

## 背景

Protocol V1 将 Calendar/Reminder Tool 执行、ToolResult HTTP 回传和写入幂等职责放在用户客户端；当前产品与已验证实现已转为 Mac-first：AgentRuntime 在 Mac 上编排，MacAgentHost 通过 EventKit 执行本机能力，并在同一 Runtime 流程内完成 Verification。V1 的规范性边界与当前架构不能同时成立。

## 决策

1. 当前产品采用 Mac-first Personal Agent。Agent HTTP API 接收用户会话请求并仅返回 Clarification 或 Final。
2. ToolRequest/ToolResult 保留为内部 ToolDispatcher ↔ Adapter ↔ MacAgentHost 执行合同，不是公开 Agent API response/inbound。
3. 外部 `request_id` 标识用户 HTTP 轮次；内部每次执行使用新的 `execution_id`，并携带 `causation_request_id`；逻辑写入 `operation_id` 在重试之间保持稳定。
4. Agent Runtime/Persistence 管理请求收据、Operation 状态与 replay/no-repeat 决策；MacAgentHost 通过本机持久化 journal 提供重复写防护和已完成结果重放。EventKit 与 journal 不共享事务，系统不宣称 exactly-once；unknown 先查真实状态，禁止盲目重复 Create。
5. Final.success 必须建立在真实 EventKit Query 验证目标事件字段匹配之上。ToolResult.success 单独不足以构成最终成功。
6. 当前真实能力范围包括 Calendar Create、其内部 verify_state Query，以及基于持久化 Task 的 Clarification Resume。Reminder 与 Calendar Update/Delete 不在当前可执行范围，虽可在 V2 合同中表达未来边界。
7. Protocol V1 文档/schema 原样保留为历史版本；Protocol V2 成为当前 canonical reference。文档不得把历史 VPS/客户端执行模型描述成当前路径。

## 考虑过的方案

### 保持 V1 并改回客户端执行

拒绝。它要求把 Calendar 执行搬回 Shortcut/iPhone，并与 MacAgentHost/EventKit 已选定的执行边界冲突。

### 静默改写 V1

拒绝。会破坏版本审计性，也会让既有 V1 fixture、文档和外部依赖失去可追溯语义。

### 新建 V2 并显式冻结 V1

采纳。保留历史内容，同时让当前代码、测试、schema 与开发入口引用一份明确的 V2 规范。

## 后果与风险

- 外部 HTTP 响应类型缩窄；内部 Tool command 不得泄漏给用户客户端。
- 测试与调用方必须分别使用 public `AgentResponse` 和 internal `ToolRequest`。
- 同 request ID replay 可以避免已完成写入重复执行；不带客户端 request ID 的旧简化 Shortcut 请求只能使用兼容生成 ID，无法提供跨网络重试的严格去重保证。
- Runtime/Persistence 的请求收据可防止相同 HTTP 请求重复派发；Mac Host journal 可拦截相同 operation 的重复执行。EventKit 写入与 journal 之间的崩溃窗口仍需要通过真实状态查询恢复。
- Clarification multi-turn resume 通过 `/agent` + `conversation_id` 实现；真实 iPhone/Siri 多轮回归仍需客户端验收。V2 schema 本身不构成该行为的测试证据。
- 当前只有 Calendar Create 与验证查询可执行。协议中保留其他 Tool 形状不代表它们已上线。
- 远程访问、VPN、Tunnel 与 Shortcut 配置不属于本 ADR 的迁移工作。

## 验证要求

- V2 外部 `InboundMessage` 不接受 ToolResult；`AgentResponse` 不接受 ToolRequest。
- 内部 ToolRequest/ToolResult 以执行尝试 ID、因果 request ID 和 Operation ID 校验相关性。
- 相同 HTTP request ID 的相同 payload 返回缓存 Final；同 ID 不同 payload 被拒绝；pending replay 不再分派 Tool。
- Calendar Create 的 Final.success 必须经过真实状态 Verification；自动化测试不得声称完成真实 macOS EventKit E2E。
- 保留 V1 schemas 与文档原文；V2 parity tests 只针对 V2 schemas/models。
