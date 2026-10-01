# Calendar Agent（Mac-first Personal Agent）

当前规范为 [`docs/protocol-v2.md`](docs/protocol-v2.md)，当前执行架构决策见 [`docs/architecture/adr/ADR-001-mac-first-tool-execution.md`](docs/architecture/adr/ADR-001-mac-first-tool-execution.md)。[`docs/protocol-v1.md`](docs/protocol-v1.md) 与 `schemas/*-v1.schema.json` 原样保留为冻结历史版本，不定义当前执行边界。

## 当前架构

```text
iPhone / Watch / Siri / Shortcut
→ HTTP /agent（鉴权与请求边界）
→ AgentRuntime → Planner / Workflow
→ ToolDispatcher → MacAgentHostAdapter
→ MacAgentHost.app → CapabilityRegistry
→ CalendarCapability → EventKit / macOS Calendar
→ 内部 ToolResult → VerificationService → Final
→ HTTP response → 用户客户端
```

客户端只传用户请求并显示/朗读 Clarification 或 Final。ToolRequest/ToolResult 是 Agent 内部执行合同，不是返回给 Shortcut 执行的公开动作协议。MacAgentHost 是本机执行 Host；当前路径不依赖 VPS、WebSocket、CalDAV 或 iCloud token。

## 当前实现范围

- 已实现：Calendar Event Create；通过 EventKit 创建后以真实 Calendar Query 验证。
- 已实现：Create 所需的 `query_calendar` / `purpose=verify_state`。
- 已实现：Clarification multi-turn resume；客户端携带原 `conversation_id`，Server 从 SQLite 恢复同一 Task，完成澄清后继续现有 Calendar Create/Verification。
- 未实现：Reminder、Calendar Update/Delete、其他 Capability。
- MacAgentHost 已实现本机持久化 operation journal；EventKit 与 journal 之间的 crash window 仍是开放可靠性问题，不提供 exactly-once 保证。
- `DemoLLM` 是确定性双语 Demo 实现，不等同真实 LLM provider。
- Mock Adapter 只用于自动化测试；Server 默认走本机 MacAgentHost。

## 本地启动

```bash
PYTHONPATH=src .venv/bin/python -m calendar_agent_protocol.server
```

默认监听 `127.0.0.1:8000`。认证与监听设置通过受保护的本机环境文件配置；不要把 API token 写入仓库或聊天。MacAgentHost 可执行路径通过 `MAC_AGENT_HOST_EXECUTABLE` 指定，Calendar 创建会触发真实系统副作用，自动化测试不运行真实 Calendar 写入。

## HTTP 请求

已有 Shortcut 的简化格式仍作为迁移兼容入口：

```json
{
  "user_request": "明天下午3点和 Bob 开一个小时的会",
  "request_id": "req_iphone_0123456789",
  "conversation_id": "conv_iphone_0123456789",
  "assistant_timezone": "Asia/Shanghai"
}
```

第二轮及后续回答继续 POST `/agent`，复用首轮响应中的 `conversation_id`；`request_id` 可省略并由 Server 为每个新 inbound 请求生成。若要安全重试同一 HTTP 请求，应显式提交同一个 `request_id` 和相同请求内容。客户端不传 task/step/operation/execution ID。API 只返回 `clarification` 或 `final`；不能把 ToolRequest 直接暴露为最终响应。没有唯一待续接澄清时 Server 返回受控错误，不会新建任务或执行写入。

## Schema

- 外部请求：[`schemas/agent-http-request-v2.schema.json`](schemas/agent-http-request-v2.schema.json)
- 外部消息：[`schemas/inbound-v2.schema.json`](schemas/inbound-v2.schema.json)
- 外部响应：[`schemas/agent-response-v2.schema.json`](schemas/agent-response-v2.schema.json)
- 内部执行：[`schemas/tool-request-v2.schema.json`](schemas/tool-request-v2.schema.json)、[`schemas/tool-result-v2.schema.json`](schemas/tool-result-v2.schema.json)
- 共用/领域/分析：`schemas/*-v2.schema.json`

## 常用入口

- 当前协议：[`docs/protocol-v2.md`](docs/protocol-v2.md)
- 架构决策：[`docs/architecture/adr/ADR-001-mac-first-tool-execution.md`](docs/architecture/adr/ADR-001-mac-first-tool-execution.md)
- QA 缺陷记录：[`docs/qa/07-defects.md`](docs/qa/07-defects.md)
- 历史 Protocol V1：[`docs/protocol-v1.md`](docs/protocol-v1.md)

## 本地运行数据

本地 Agent Server 使用相对于 Server 工作目录的 `calendar-agent.db`。当前项目目录下数据库路径通常为：

```text
/Users/wangkristen/Agents_project/calendar-agent/calendar-agent.db
```

Task 数据位于 `tasks` 表。启动目录或项目路径变化时，SQLite 相对路径也会变化。只读列出表名：

```bash
sqlite3 -readonly calendar-agent.db '.tables'
```
