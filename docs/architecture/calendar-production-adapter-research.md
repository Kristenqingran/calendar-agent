# Calendar Production Adapter Research

## Document Status

**Status: DEPRECATED / HISTORICAL RESEARCH**

本文记录旧的 VPS / Cloud Calendar 架构研究。该架构已经被当前的
Mac-first Personal Agent 架构取代。

本文仅用于保留历史技术调研、失败/阻塞证据和 architecture pivot 背景，
不得作为当前 V1 实现要求或 Codex 当前开发路径依据。

Current architecture:

`Mac-first Personal Agent → MacAgentHost → Capability → macOS native API`

当前已经真实验证的执行边界：

`MacAgentHost.app → CapabilityRegistry → CalendarCapability → EventKitAdapter → macOS Calendar → EventKit Verification → ToolResult.success`

VPS、WebSocket、Cloud Agent、ProductionCalendarAdapter 和 CalDAV 不属于当前
Calendar V1 的实现前置条件。当前系统规范应以 [`docs/protocol-v2.md`](../protocol-v2.md)
和当前代码为准；本文提到的 Protocol V1 仅为历史研究背景。

> 研究日期：2026-09-27
>
> **Historical / Deprecated architecture.** 原始范围是研究 Apple Watch → VPS → Cloud Calendar 的生产方向。本文只保留该历史调研和当前代码映射，不实现 Production Calendar Adapter，不部署 VPS，不修改 Shortcut。

## Executive Summary

当前目标不能依赖 Mac、macOS Calendar、Apple Shortcut、`osascript` 或 `MacCalendarBridge`。这些组件只能保留为 Local QA Adapter。

推荐的生产方向是：

1. 如果产品必须写入用户的 iCloud Calendar：先以独立的 `iCloud/CalDAV Production Adapter` 做小型 PoC；不要把 CalDAV 的可行性、Apple Account 授权和幂等语义当成已经验证的事实。
2. 如果可以接受生产日历迁移到云服务：Google Calendar API 或 Microsoft Graph 是更成熟的 VPS 直连方案，均有官方 HTTPS API、事件 ID、时间范围查询和版本/增量同步机制。
3. Agent Core 应只依赖 Calendar Adapter port。CalendarWorkflow、ToolDispatcher、ToolRequest/ToolResult 和 VerificationService 不应知道 iCloud、Google 或 Microsoft 的 SDK 细节。

Apple 官方资料确认第三方应用可以访问 iCloud Mail、Calendar 和 Contacts，并可使用 Apple Account 授权或 app-specific password；Apple 的设备管理文档也明确存在 CalDAV account 配置。RFC 4791 定义了 CalDAV，RFC 6578 定义了 WebDAV collection synchronization。但这不等于已经验证了本项目从 VPS 直连个人 iCloud Calendar 的全部 discovery、写入、同步和幂等流程。

## 1. Sources and Evidence

### 1.1 Apple / iCloud / EventKit

- Apple 说明支持的第三方应用可以访问 iCloud Mail、Calendar、Contacts，并通过 Apple Account 授权；不支持该授权流程的应用可以使用 app-specific password：[Access your iCloud Mail, Calendar, and Contacts in third-party apps](https://support.apple.com/en-ca/121539)。
- Apple 说明 app-specific password 需要 Apple Account 开启双重认证，并可在 `account.apple.com` 创建或撤销：[Sign in to apps with your Apple Account using app-specific passwords](https://support.apple.com/en-gb/102654)。
- Apple 的设备管理文档定义了 CalDAV account 配置，包括 hostname、port、path 和凭据引用：[AccountCalDAV](https://developer.apple.com/documentation/devicemanagement/accountcaldav)。
- Apple EventKit 将 iCloud/CalDAV 日历表示为 `EKCalendarTypeCalDAV`：[EKCalendarTypeCalDAV](https://developer.apple.com/documentation/eventkit/ekcalendartype/caldav)。EventKit 本身是 Apple 设备/应用侧 API，不是 VPS 的云端 API。
- EventKit 文档说明 full access 才能读、创建、编辑、删除事件；macOS sandboxed app 还需要 Calendar entitlement：[Accessing the event store](https://developer.apple.com/documentation/eventkit/accessing-the-event-store)。

### 1.2 CalDAV / WebDAV

- [RFC 4791](https://www.rfc-editor.org/rfc/rfc4791) 定义 CalDAV：基于 WebDAV 的日历访问协议，可交换 iCalendar 数据。
- [RFC 6578](https://www.rfc-editor.org/rfc/rfc6578) 定义 WebDAV sync collection，用于增量同步和 sync token。
- [RFC 7809](https://www.rfc-editor.org/rfc/rfc7809) 扩展 CalDAV 以支持更现代的时区表达。

### 1.3 Google Calendar

- Google `events.insert` 是官方 HTTPS create API，需要 OAuth 授权；支持 RFC3339 date-time、IANA time zone、all-day `date`，并返回完整 Event resource：[Events: insert](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert)。
- Google create-events 指南明确事件 ID 可以由客户端生成，用于与本地实体同步并避免网络超时后的重复创建：[Create events](https://developers.google.com/workspace/calendar/api/guides/create-events)。
- Google Event resource 包含 `id`、`iCalUID`、`etag`、`updated`、start/end 等字段：[Events resource](https://developers.google.com/workspace/calendar/api/v3/reference/events)。
- Google 官方说明 ETag 可用于条件修改和条件读取，冲突通常表现为 HTTP 412：[Versioned resources](https://developers.google.com/workspace/calendar/api/guides/version-resources)。

### 1.4 Microsoft Graph

- Microsoft Graph Calendar API 支持创建、读取、更新、删除事件和时间范围视图：[Calendar overview](https://learn.microsoft.com/en-us/graph/api/resources/calendar-overview?view=graph-rest-1.0)。
- Graph Event resource 提供 `id`、`iCalUId`、`changeKey`、`transactionId`、UTC 时间、时区和 delta query；`transactionId` 专门用于避免低网络条件下重试造成重复创建：[Event resource](https://learn.microsoft.com/en-us/graph/api/resources/event?view=graph-rest-1.0)。
- Graph 官方支持 calendarView/delta 等增量读取能力：[Event delta](https://learn.microsoft.com/en-us/graph/api/event-delta?view=graph-rest-1.0)。
- Graph 更新事件使用 Bearer token 和 `Calendars.ReadWrite` 等权限：[Update event](https://learn.microsoft.com/en-us/graph/api/event-update?view=graph-rest-1.0)。

## 2. 已验证事实 vs 工程推断 vs 待 PoC 验证

### 已验证事实

- Mac 不是云端 Calendar 的必要组成部分；Apple 官方资料描述了第三方访问 iCloud Calendar 的授权路径，CalDAV 是标准协议路径。
- CalDAV 支持日历资源与 iCalendar 数据交换；RFC 6578 提供增量同步机制。
- Google Calendar 与 Microsoft Graph 都提供 VPS 可调用的官方 HTTPS API。
- Google 返回事件 ID/ETag，并允许客户端在创建时提供 event ID。
- Microsoft Graph 返回事件 ID/iCalUId/changeKey，并提供 transactionId 与 delta query。
- 当前仓库已经有 Adapter/Dispatcher 边界；`LocalCalendarAdapter` 只负责向本地 Bridge 发 ToolRequest，`MacCalendarBridge` 才负责 macOS 执行。
- 当前仓库的 `ToolRequest` 已包含 `request_id`、`conversation_id`、`task_id`、`step_id`、`operation_id`、`tool` 和 `arguments`。
- 当前仓库的 `VerificationService` 已经通过 `query_calendar` + `purpose=verify_state` 组织 Create 后的验证。

### 工程推断

- Agent Core 不需要知道 CalDAV、Google 或 Graph。Production Adapter 应实现现有 `ToolAdapter.execute(ToolRequest) -> ToolResult` 边界。
- `operation_id` 应映射到外部系统支持的幂等字段：Google 可映射为客户端生成的 event `id`（需满足 Google ID 格式限制）；Microsoft Graph 应映射为 `transactionId`，并在本地保存返回的 event `id`/`iCalUId`。
- CalDAV 的资源 URL/UID/ETag 组合可以承担外部关联，但必须在 PoC 中确认服务端是否稳定接受客户端生成 UID，以及重复 PUT/POST 的实际行为。不能仅凭 RFC 推断 iCloud 的幂等语义。
- 对于“请求已发出但响应丢失”，Adapter 必须返回 `unknown`，随后用 operation_id、外部 UID 或稳定的业务指纹查询验证，而不是立即 retry create。
- 更新应使用外部版本字段：Google 使用 ETag 条件请求；Microsoft 使用 changeKey/HTTP 条件控制；CalDAV 使用资源 ETag 和条件 HTTP 请求（具体 iCloud 行为需要 PoC）。

### 待 PoC 验证

- 当前 Apple Account 对个人 iCloud Calendar 的 VPS 直连 endpoint、principal discovery、calendar-home-set discovery 和授权组合。
- app-specific password 在实际 CalDAV 客户端中的兼容性、撤销行为和长期运行策略。
- iCloud CalDAV 的 create/update/delete、time-range REPORT、all-day 时区语义、UID、ETag 和 sync-token 行为。
- iCloud 在重复 UID/重复 operation_id、连接超时、写入成功但响应丢失时的具体响应。
- EventKit/CalDAV 创建后 event UID 的格式和是否能通过后续查询稳定定位。
- VPS 的 egress、DNS、TLS、secret storage、Apple 账户风控和长期 token 生命周期。

## 3. Capability Comparison

| 能力 | iCloud / CalDAV | Google Calendar | Microsoft Graph | 其他云日历 API |
| --- | --- | --- | --- | --- |
| VPS direct access | 协议上可行；iCloud 具体 discovery/授权待 PoC | 官方 HTTPS API | 官方 HTTPS API | 取决于供应商 |
| Mac required | 否，若 VPS 直接使用 CalDAV | 否 | 否 | 通常否 |
| Apple Watch compatible | Watch 只需连接 VPS；日历同步由 iCloud 完成 | Watch 可通过客户端/同步服务使用 | 同上 | 取决于客户端 |
| Authentication | Apple Account 授权或 app-specific password；CalDAV 细节待 PoC | OAuth 2.0 | OAuth 2.0 / delegated or application permissions | OAuth/API key 等 |
| Create | CalDAV PUT/POST 语义需 PoC | `events.insert` | POST events | 取决于 API |
| Query | CalDAV REPORT/time-range，需 PoC | list/get/timeMin/timeMax | calendarView/list/get | 取决于 API |
| Update | PUT/ETag，需 PoC | update/patch + ETag | PATCH + changeKey/conditions | 取决于 API |
| Delete | DELETE，需 PoC | delete | DELETE | 取决于 API |
| Verification | 查询同一资源/UID；行为待 PoC | get/list，强 | get/list/calendarView，强 | 取决于 API |
| Stable event ID | iCalendar UID/资源 URL；iCloud 细节待 PoC | event `id`、`iCalUID` | `id`、`iCalUId` | 取决于 API |
| Idempotency | 不能仅假设，需测试 UID/重复写 | 客户端 event ID | `transactionId` 官方支持 | 取决于 API |
| Unknown-state recovery | 通过 UID/时间范围查询，需 PoC | get/list by generated ID | get/list by transactionId/event ID | 取决于 API |
| Timezone | iCalendar VTIMEZONE/TZID；需 PoC | RFC3339 + IANA TZ | DateTimeTimeZone | 取决于 API |
| All-day event | iCalendar DATE；需 PoC | start.date/end.date | date/time-zone fields | 取决于 API |
| Deployment complexity | 协议客户端、Apple 授权、发现和兼容性风险高 | SDK/OAuth，成熟 | SDK/OAuth/tenant permissions，成熟 | 不同 |

## 4. Current Repository Mapping

### 4.1 可复用边界

当前可以保持以下结构：

```text
CalendarWorkflow
        ↓
ToolRequest
        ↓
ToolDispatcher
        ↓
ToolAdapter port
        ├── MockToolAdapter       # 自动化测试
        ├── LocalCalendarAdapter  # Mac QA
        └── ProductionCalendarAdapter  # 未来 VPS
        ↓
ToolResult
        ↓
VerificationService
        ↓
Final
```

可直接复用的当前代码：

- `CalendarWorkflow`：Create 参数组装和 Calendar ToolRequest。
- `ToolDispatcher`：单 Tool 选择、Adapter 调用、ToolResult contract/correlation 校验。
- `VerificationService`：Create 后构造 `query_calendar` verification request，并判断 success/failure/unknown。
- `AgentRuntime`：Task/Step/Operation persistence、ToolResult 回流、Final 构造。
- `OperationRepository`：operation lifecycle 与 verified status 的现有位置。
- `MockToolAdapter`：deterministic automation path。
- `LocalCalendarAdapter`/`MacCalendarBridge`：仅保留为本地 QA 实现，不应成为生产依赖。

### 4.2 当前限制和 contract 风险

- 当前 `LocalCalendarAdapter` 是 HTTP 本地桥，不是生产 Adapter；它默认连接 `127.0.0.1`，不能放入 VPS 生产路径。
- 当前 `MacCalendarBridge` 使用 macOS scripting/osascript，依赖 Mac 在线和 Automation 权限。
- 当前 `VerificationService` 的 query result 必须包含足以比对 title/start/end 的事件字段；Production Adapter 必须返回真实字段，不能仅返回 event ID。
- 当前 `ToolResult` 的 `result` 是通用字典，尚未有统一的 domain-specific Calendar result model；未来可以在不改 Protocol 语义的前提下，在 Adapter 内做严格 domain mapping，但是否收紧 Canonical Schema 需要另行决定。
- 当前 `operation_id` 是本地 operation 关联 ID；Production Adapter 需要将其映射到外部幂等字段，并把外部 event ID、UID、ETag/changeKey 保存到 result/persistence 扩展位置。不能把外部 ID 与本地 operation_id 混为一谈。
- 当前 Runtime 只支持一个任务/单 Tool 路径；不应在本 PoC 中加入并行或多步 transaction。

## 5. Operation, Unknown, Verification and Concurrency

### Create 幂等建议

```text
operation_id (local stable id)
        ├── provider idempotency field
        ├── provider event id / UID
        └── local operation record
```

生产 Adapter 的基本流程应是：

1. 在本地 OperationRepository 中以 `operation_id` 做唯一键和参数指纹。
2. 在 provider 支持时，把稳定、符合 provider 规则的 derived id 或 transaction key 发给 provider。
3. provider 返回成功时保存外部 event ID/UID/version token。
4. 超时或连接断开时返回 `ToolResult.unknown`，不自动重复 create。
5. 先以外部 ID/UID 查询；若找到且字段一致，转为 verified success；找到但字段冲突，转为 verified failure/人工处理；找不到且 provider 明确确认未写入，才允许受控 retry。

### 失败与 unknown

- `failed`：provider 明确拒绝、认证失败、参数无效、权限不足，且可以确认没有完成写入。
- `unknown`：超时、连接断开、响应解析失败、服务端状态不可判定，或 verification 查询不足以确认真实状态。
- `Final.success` 只能来自 verification；Adapter 的 HTTP 2xx 或 create response 不能单独代表最终成功。

### 并发修改

- Create：依赖 provider 幂等字段和本地 operation lock。
- Update/Delete：读取最新版本 token，使用 ETag/changeKey/条件请求；冲突时返回明确失败或 unknown，不覆盖未知的新版本。
- Query：保存 provider page token/sync token 时绑定 calendar、用户和查询范围，不能跨账户复用。







#已经废弃不用的
## 6. Apple Watch / Shortcut Role (Historical / Deprecated)

最终 Shortcut 保持薄层是合理的：

```text
Siri / Apple Watch Shortcut
        ↓
HTTPS request
        ↓
VPS Agent
        ↓
Final response
        ↓
Watch display
```

Shortcut 不应负责：

- Calendar Create/Query/Update/Delete
- 自然语言解析
- Planner
- Verification
- Retry 或 recovery

Apple Watch/Shortcut 只需要收集输入、发送 HTTPS、显示 Agent response。生产日历访问必须由 VPS Production Calendar Adapter 完成。

## 7. Minimal Production PoC (Historical / Deprecated)

不在本次实现，建议顺序如下：

1. 选择一个真实云 Calendar 账户和单一测试 Calendar。
2. 单独实现 provider client，不接入 Runtime。
3. 验证 discovery、认证、calendar selection 和 timezone。
4. 创建一个带稳定 test operation key 的事件。
5. 读取返回的 provider ID/UID/version token。
6. 通过 provider query/get 验证 title、start、end、all-day 和 timezone。
7. 重复发送相同 operation，证明不会产生第二个事件。
8. 模拟 create response timeout，随后 query 恢复为 success 或 unknown。
9. 测试 update/delete 的版本冲突；虽不纳入第一条 Vertical Slice，也要验证 adapter 的错误语义。
10. 关闭 Mac，仅保留 VPS/client path，验证全链路。
11. 最后将 provider client 包装为 `ProductionCalendarAdapter`，通过现有 Dispatcher 注入 Runtime。

### PoC 验收项

- Create event
- Query event
- Create 后真实字段 verification
- duplicate operation 不产生重复事件
- network timeout → unknown
- unknown 后 query recovery
- retry 不造成重复事件
- Mac 完全关闭仍可完成 create/query/verification

## 8. Recommended Direction (Historical Recommendation / Deprecated Architecture)

### 首选路线（Historical Recommendation / Deprecated）

如果“必须写入 iCloud Calendar”是硬约束：

```text
iCloud / CalDAV Production Adapter
```

作为独立 PoC，先验证真实账户和真实 endpoint。CalDAV 在协议层适合 VPS，但 Apple-specific authentication/discovery/UID/ETag/idempotency 不能凭文档直接视为完成。

### 工程上风险更低的替代路线（Historical Recommendation / Deprecated）

如果可以让生产 Calendar 位于 Google 或 Microsoft 云端：

- Google 更直接地提供 client-generated event ID、ETag 和 Calendar API 资源模型。
- Microsoft Graph 提供 transactionId、id/iCalUId、changeKey、calendarView 和 delta query。

这两者更容易映射到当前 `operation_id`、unknown recovery 和 verification 模型。

## 9. 下一阶段 Codex Implementation Task 草案（Historical / Deprecated）

> 仅为后续任务草案，本次不执行。

1. 选定 provider（先完成 CalDAV feasibility decision，或明确选择 Google/Microsoft）。
2. 定义内部 `CalendarProviderClient` port，不改变 Canonical Protocol v1。
3. 实现 provider-specific credential/config 与 secret handling。
4. 实现 Create + Get/Query 的离线 contract tests 和 provider integration tests。
5. 映射 operation_id 到 provider 幂等字段，保存外部 event ID/UID/version token。
6. 接入 unknown recovery 和 verification，明确 failed/unknown 边界。
7. 以 Adapter injection 接入 Agent Runtime，不修改 Agent Core 的 provider 细节。
8. 实施 VPS-only E2E：Mac 关闭，Apple Watch/HTTPS client → VPS → Cloud Calendar。

## 10. Final Conclusions（Historical Conclusions）

1. 推荐先做 iCloud/CalDAV feasibility PoC；若其 authentication/discovery/idempotency 不满足稳定运行要求，转向 Google Calendar API 或 Microsoft Graph。
2. Agent Core、CalendarWorkflow、ToolDispatcher、VerificationService 和现有 Protocol 边界可以复用。
3. 未来需要新增的是 Production Calendar Adapter/provider client、凭据管理、外部 ID/version persistence 和 provider integration tests。
4. 最大风险是 iCloud-specific CalDAV discovery/authentication 与“写入成功但响应丢失”后的幂等恢复。
5. Apple Watch Shortcut 应保持薄客户端，不承载 Calendar 逻辑。
6. Mac Bridge 继续作为 Local QA Adapter，不进入生产依赖。
