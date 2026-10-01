# MacAgentHost

本目录实现当前 Mac-first 架构中的本机 Tool Execution Boundary。当前规范见
[`../docs/protocol-v2.md`](../docs/protocol-v2.md)；V1 历史边界不适用于当前 Host。

## 当前执行链

```text
AgentRuntime → ToolDispatcher → MacAgentHostAdapter
→ MacAgentHost.app（本地 JSON-lines IPC）
→ CapabilityRegistry → CalendarCapability → EventKit
```

客户端不直接调用本 Host。Host 只执行已注册的 Capability 并返回内部 ToolResult；Final 判定与真实状态验证由 AgentRuntime/VerificationService 完成。

当前可执行范围为 `create_calendar_event` 和 Create 后的 `query_calendar` / `verify_state`。Reminder、Calendar Update/Delete、Shortcut executor 和远程执行协议均不在当前能力范围内。

## 构建

使用 Xcode 标准 macOS App Target：

```bash
xcodebuild -project mac_gateway/MacAgentHost.xcodeproj \
  -scheme MacAgentHost -configuration Debug \
  -derivedDataPath /tmp/calendar-agent-derived build
```

产物为 `Build/Products/Debug/MacAgentHost.app`。Python Server 通过 `MAC_AGENT_HOST_EXECUTABLE` 配置其 bundle executable；正常执行由 Adapter 为每次内部 ToolRequest 建立 JSON-lines 子进程并读取一条 ToolResult，不应把 Host 的内部 stdin/stdout 当作用户 API。

## 本机 operation 防重

Calendar Create 在 EventKit 写入前将 `operation_id` 与参数摘要写入用户 Application Support 下的 `com.calendaragent.mac-host/operation-journal.json`。完成后持久化真实 `event_id` 或明确失败结果；相同 ID、相同参数会重放持久结果，相同 ID、不同参数会拒绝。若进程在 `started` 状态中断，重复请求返回 `unknown`，必须先由 Runtime 查询真实 Calendar 状态，不能盲目重试。

该文件不包含 Calendar 账户凭证。EventKit 与 journal 不共享事务；写入后、结果落盘前的 crash window 仍需通过真实状态查询解决，不提供 exactly-once 保证。

旧 `CalendarAgentEventKit` CLI/helper 属于历史迁移实现，不是当前 Host 构建或执行入口。
