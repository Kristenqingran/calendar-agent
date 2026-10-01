# Mac-first Personal Agent: Client Access Boundary

## Status

This document describes the current Mac-first V2 client-access boundary. The
historical VPS/CalDAV research documents remain historical and are not current
implementation requirements.

The normative message and execution contracts are in [`../protocol-v2.md`](../protocol-v2.md); the V1 contract remains frozen history.

## Architecture

```text
iPhone / Apple Watch
        ↓
Siri / Shortcut
        ↓
Client Access / Security Boundary
        ↓
Agent HTTP API
        ↓
AgentRuntime → Planner → CalendarWorkflow
        ↓
ToolDispatcher → MacAgentHostAdapter → MacAgentHost.app
        ↓
Capabilities → EventKit → macOS Calendar
```

The Agent Core has no knowledge of LAN, WAN, VPN, tunnel, iPhone, Watch,
router, or public IP addresses.

## Server modes

### Local development

The safe default is loopback only:

```text
AGENT_SERVER_HOST=127.0.0.1
AGENT_SERVER_PORT=8000
```

### Controlled LAN

For a controlled home LAN, explicitly bind all interfaces and configure an API
token:

```text
AGENT_SERVER_HOST=0.0.0.0
AGENT_SERVER_PORT=8000
AGENT_API_TOKEN=<local-secret>
```

`0.0.0.0` means “listen on local interfaces”; it is not a safe public-exposure
mechanism. This project does not configure router forwarding, firewall rules,
VPN, Xray, or tunnels.

### Remote V1: Cloudflare Named Tunnel

The selected remote-access implementation is a Cloudflare Named Tunnel. The
stable public endpoint is an HTTPS hostname configured in Cloudflare DNS and
the tunnel ingress points only to `http://127.0.0.1:8000`. No router port
forwarding or public `:8000` exposure is used. The repository provides:

```text
tools/macos/run_cloudflared_tunnel.sh
tools/macos/remote_access_service.sh
mac_gateway/launchd/com.calendaragent.cloudflared.plist.template
tools/macos/cloudflared-config.example.yml
```

Cloudflare account login, named-tunnel creation, DNS hostname selection and
provider authorization remain manual steps. The tunnel does not replace
application authentication: `AGENT_API_TOKEN` remains required by the
non-loopback Agent Server.

The same client endpoint should be used regardless of whether the phone is at
home or on cellular data. A DHCP address such as `192.168.0.34` and a home
public IP must never be embedded in source or a canonical client specification.

## Authentication contract

For a configured API token, clients call:

```http
POST /agent
Content-Type: application/json
Authorization: Bearer <token>
```

with:

```json
{
  "user_request": "明天早上9点和 Bob 开一个小时的会",
  "conversation_id": "conv_http_0123456789abcdef",
  "assistant_timezone": "Asia/Shanghai"
}
```

`conversation_id` is optional. Omit it to start a new conversation; to continue
one, send the `conversation_id` returned by the previous Agent response. The
server validates it against the Protocol ID format and uses it to retain
conversation context, including response-language continuity.

The token is read from `AGENT_API_TOKEN`, never logged or returned. Missing or
invalid credentials are rejected before `AgentRuntime` is invoked. Comparison
uses a timing-safe comparison. The default loopback mode permits local
development without a token; any non-loopback listener fails fast without one.

The HTTP layer also enforces POST-only `/agent`, JSON parsing, an explicit
request-size limit, and safe error messages. Authentication here is separate
from any future tunnel/provider authentication.

## Timezone boundary

The client should send its current IANA timezone. The HTTP boundary validates
it and constructs `current_time` in that timezone. It must not infer timezone
from the Mac timezone, IP address, or network location. Existing clients that
omit it use the current local default `Asia/Shanghai`; remote iPhone/Watch
clients should make the field explicit.

## Shortcut and Watch contract

Shortcut remains a thin client:

```text
voice/text input → POST /agent → speak/display clarification or final response
```

It does not parse Calendar semantics, call EventKit, retry writes, or perform
verification. When the Agent returns a Clarification, the client sends the
answer as the next `user_request` with the same `conversation_id`; the Server
generates a fresh `request_id` unless the client supplies one for retry
idempotency. The Server resolves and validates the pending Task/step and
constructs the typed internal `ClarificationResponse`. Clients never manage
`task_id`, `step_id`, `reply_to_step_id`, `operation_id`, or `execution_id`.
No unique pending clarification yields a controlled error and no write.

## macOS service lifecycle

The repository provides, but does not install, a LaunchAgent template and
management script:

```text
tools/macos/run_agent_server.sh
tools/macos/agent_server_service.sh
mac_gateway/launchd/com.calendaragent.agent-server.plist.template
```

The wrapper reads a user-owned, untracked environment file at:

```text
~/.config/calendar-agent/server.env
```

That file must be protected with mode `600` and may contain `AGENT_API_TOKEN`.
No secret is included in the repository. LaunchAgent logs go to:

```text
~/Library/Logs/calendar-agent/server.log
~/Library/Logs/calendar-agent/server.error.log
```

The service wrapper starts only the Python Agent Server. MacAgentHost remains a
separate native AppKit/EventKit process with its existing permission model.
For real Calendar execution, `MAC_AGENT_HOST_EXECUTABLE` must point to the
executable inside the built `MacAgentHost.app` bundle. Without it, the adapter
returns a configuration failure and does not silently route to the legacy
port-8770 local bridge.
Installing or authorizing the LaunchAgent is a manual macOS step.

The Cloudflare tunnel has its own LaunchAgent and logs. It is deliberately
separate from the Agent Server so either component can be diagnosed and
restarted independently. Both services must be installed explicitly; no
credential or provider authorization is performed automatically.

## Remote acceptance criteria

- RA-01: changing the Mac DHCP address does not change the HTTPS endpoint.
- RA-02: an iPhone on home Wi-Fi reaches `/agent` with a valid token.
- RA-03: an iPhone on cellular or external Wi-Fi reaches the same HTTPS URL.
- RA-04: after Mac restart/login, both LaunchAgents recover.
- RA-05: missing or invalid Bearer credentials are rejected before AgentRuntime.
- RA-06: the stable client endpoint is HTTPS, never public HTTP on port 8000.
- RA-07: a real Calendar write still requires EventKit verification before Final.
- RA-08: Apple Watch/Siri uses the same thin Shortcut contract and receives Final.

## Troubleshooting

- `127.0.0.1` works only from the Mac itself.
- `0.0.0.0` requires `AGENT_API_TOKEN` and does not make the service public.
- A changed DHCP address affects direct LAN testing only; the stable HTTPS
  endpoint does not change.
- `401` means the Bearer token is missing or invalid.
- `413` means the request exceeds the configured size limit.
- `400` with `invalid_assistant_timezone` means the client sent an unknown IANA
  timezone.
- Calendar permissions remain controlled by macOS and MacAgentHost.app.
