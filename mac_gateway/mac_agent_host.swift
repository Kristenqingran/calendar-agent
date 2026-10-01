import EventKit
import Foundation
import AppKit

// Stable host-side execution boundary. Transport is intentionally JSON-lines
// for this local phase; a future WebSocket transport can feed the same host.
struct HostToolRequest: Decodable {
    let type: String
    let execution_id: String
    let causation_request_id: String
    let conversation_id: String
    let task_id: String
    let step_id: String
    let operation_id: String?
    let tool: String
    let purpose: String?
    let arguments: HostArguments
}

struct HostError: Encodable {
    let code: String
    let message: String
    let retryable: Bool
    let details: [String: String]?
}

struct HostToolResult: Encodable {
    let type: String
    let execution_id: String
    let causation_request_id: String
    let conversation_id: String
    let task_id: String
    let step_id: String
    let tool: String
    let status: String
    let executed_at: String
    let error: HostError?
    let operation_id: String?
    let result: [String: String]?
    let queried_range: [String: String]?
    let fetched_at: String?
    let results: [[String: String]]?
}

func hostError(_ code: String, message: String? = nil) -> HostError {
    HostError(code: code, message: message ?? code, retryable: false, details: nil)
}

protocol Capability {
    var name: String { get }
    var supportedTools: Set<String> { get }
    func execute(_ request: HostToolRequest) -> HostToolResult
}

final class CapabilityRegistry {
    private var capabilities: [String: Capability] = [:]

    func register(_ capability: Capability) {
        for tool in capability.supportedTools { capabilities[tool] = capability }
    }

    func capability(for tool: String) -> Capability? { capabilities[tool] }
}

final class EventKitAdapter {
    private let store = EKEventStore()

    func create(_ arguments: HostArguments) -> (String?, String?) {
        guard let title = arguments.title, let startText = arguments.start,
              let endText = arguments.end else { return (nil, "missing_calendar_arguments") }
        let semaphore = DispatchSemaphore(value: 0)
        var granted = false
        store.requestAccess(to: .event) { allowed, _ in
            granted = allowed
            semaphore.signal()
        }
        semaphore.wait()
        guard granted else { return (nil, "calendar_access_denied") }

        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let start = formatter.date(from: startText) ?? ISO8601DateFormatter().date(from: startText),
              let end = formatter.date(from: endText) ?? ISO8601DateFormatter().date(from: endText),
              end > start else {
            return (nil, "invalid_datetime_range")
        }
        let calendars = store.calendars(for: .event)
        let matching = calendars.filter { calendar in
            arguments.calendar_name == nil || calendar.title == arguments.calendar_name!
        }
        guard let calendar = matching.first(where: { $0.allowsContentModifications }) else {
            if matching.isEmpty {
                return (nil, "calendar_not_found")
            }
            return (nil, "calendar_read_only")
        }

        let event = EKEvent(eventStore: store)
        event.calendar = calendar
        event.title = title
        event.startDate = start
        event.endDate = end
        do {
            try store.save(event, span: .thisEvent, commit: true)
            guard let eventID = event.eventIdentifier,
                  let verified = store.event(withIdentifier: eventID),
                  verified.title == title,
                  verified.startDate == start,
                  verified.endDate == end else {
                return (nil, "calendar_verification_mismatch")
            }
            return (eventID, nil)
        } catch {
            return (nil, error.localizedDescription)
        }
    }

    func query(_ arguments: HostArguments) -> [[String: String]] {
        guard let startText = arguments.start, let endText = arguments.end,
              let start = ISO8601DateFormatter().date(from: startText),
              let end = ISO8601DateFormatter().date(from: endText) else { return [] }
        let events = store.events(matching: store.predicateForEvents(
            withStart: start, end: end, calendars: nil))
        return events.compactMap { event in
            if let target = arguments.target_id, event.eventIdentifier != target { return nil }
            if let title = arguments.candidate?.title, event.title != title { return nil }
            return ["event_id": event.eventIdentifier ?? "", "title": event.title ?? "",
                    "start": ISO8601DateFormatter().string(from: event.startDate),
                    "end": ISO8601DateFormatter().string(from: event.endDate)]
        }
    }
}

func failureResult(_ request: HostToolRequest, _ code: String) -> HostToolResult {
    HostToolResult(type: "tool_result", execution_id: request.execution_id,
        causation_request_id: request.causation_request_id,
        conversation_id: request.conversation_id, task_id: request.task_id,
        step_id: request.step_id, tool: request.tool, status: "failed",
        executed_at: ISO8601DateFormatter().string(from: Date()),
        error: hostError(code), operation_id: request.operation_id, result: nil,
        queried_range: nil, fetched_at: nil, results: nil)
}

final class CalendarCapability: Capability {
    let name = "calendar"
    let supportedTools: Set<String> = ["create_calendar_event", "query_calendar"]
    private let adapter: EventKitAdapter
    private let journal = OperationJournal()

    init(adapter: EventKitAdapter = EventKitAdapter()) { self.adapter = adapter }

    func execute(_ request: HostToolRequest) -> HostToolResult {
        let now = ISO8601DateFormatter().string(from: Date())
        if request.tool == "create_calendar_event" {
            guard let operationID = request.operation_id, !operationID.isEmpty else {
                return failureResult(request, "operation_id_required")
            }
            do {
                switch try journal.claim(operationID: operationID, arguments: request.arguments) {
                case .replay(let record):
                    return HostToolResult(
                        type: "tool_result", execution_id: request.execution_id,
                        causation_request_id: request.causation_request_id,
                        conversation_id: request.conversation_id, task_id: request.task_id,
                        step_id: request.step_id, tool: request.tool,
                        status: record.state == "succeeded" ? "success" : "failed",
                        executed_at: now,
                        error: record.errorCode.map { hostError($0) },
                        operation_id: operationID,
                        result: record.eventID.map { ["event_id": $0] },
                        queried_range: nil, fetched_at: nil, results: nil
                    )
                case .outcomeUnknown:
                    return HostToolResult(
                        type: "tool_result", execution_id: request.execution_id,
                        causation_request_id: request.causation_request_id,
                        conversation_id: request.conversation_id, task_id: request.task_id,
                        step_id: request.step_id, tool: request.tool, status: "unknown",
                        executed_at: now, error: hostError("operation_outcome_unknown"),
                        operation_id: operationID, result: nil,
                        queried_range: nil, fetched_at: nil, results: nil
                    )
                case .conflict:
                    return failureResult(request, "operation_id_conflict")
                case .execute:
                    break
                }
            } catch {
                return failureResult(request, "operation_journal_unavailable")
            }
            let (eventID, error) = adapter.create(request.arguments)
            let effectiveError = error ?? (eventID == nil ? "calendar_create_failed" : nil)
            do {
                try journal.complete(
                    operationID: operationID, arguments: request.arguments,
                    eventID: eventID, errorCode: effectiveError
                )
            } catch {
                return HostToolResult(
                    type: "tool_result", execution_id: request.execution_id,
                    causation_request_id: request.causation_request_id,
                    conversation_id: request.conversation_id, task_id: request.task_id,
                    step_id: request.step_id, tool: request.tool, status: "unknown",
                    executed_at: now, error: hostError("operation_result_not_persisted"),
                    operation_id: operationID, result: nil,
                    queried_range: nil, fetched_at: nil, results: nil
                )
            }
            return HostToolResult(type: "tool_result", execution_id: request.execution_id,
                causation_request_id: request.causation_request_id,
                conversation_id: request.conversation_id, task_id: request.task_id,
                step_id: request.step_id, tool: request.tool,
                status: effectiveError == nil ? "success" : "failed", executed_at: now,
                error: effectiveError.map { hostError($0) }, operation_id: request.operation_id,
                result: eventID.map { ["event_id": $0] }, queried_range: nil,
                fetched_at: nil, results: nil)
        }
        if request.tool == "query_calendar" {
            let found = adapter.query(request.arguments)
            return HostToolResult(type: "tool_result", execution_id: request.execution_id,
                causation_request_id: request.causation_request_id,
                conversation_id: request.conversation_id, task_id: request.task_id,
                step_id: request.step_id, tool: request.tool, status: "success", executed_at: now,
                error: nil, operation_id: nil, result: nil,
                queried_range: ["start": request.arguments.start ?? "", "end": request.arguments.end ?? ""],
                fetched_at: now, results: found)
        }
        return HostToolResult(type: "tool_result", execution_id: request.execution_id,
            causation_request_id: request.causation_request_id,
            conversation_id: request.conversation_id, task_id: request.task_id,
            step_id: request.step_id, tool: request.tool, status: "failed", executed_at: now,
            error: hostError("unsupported_operation"), operation_id: request.operation_id,
            result: nil, queried_range: nil, fetched_at: nil, results: nil)
    }
}

func emit(_ result: HostToolResult) {
    guard let data = try? JSONEncoder().encode(result) else { return }
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data([0x0a]))
}

final class MacAgentHostDelegate: NSObject, NSApplicationDelegate {
    private let registry = CapabilityRegistry()
    private let decoder = JSONDecoder()

    func applicationDidFinishLaunching(_ notification: Notification) {
        registry.register(CalendarCapability())
        fputs("[MacAgentHost] applicationDidFinishLaunching\n", stderr)
        fputs("[MacAgentHost] CapabilityRegistry initialized\n", stderr)

        // Keep stdin/stdout as the local development IPC boundary while the
        // AppKit run loop remains alive for TCC and future host services.
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self else { return }
            while let line = readLine() {
                self.handle(line)
            }
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        fputs("[MacAgentHost] applicationWillTerminate\n", stderr)
    }

    private func handle(_ line: String) {
        guard let data = line.data(using: .utf8),
              let request = try? decoder.decode(HostToolRequest.self, from: data) else {
            emit(HostToolResult(type: "tool_result", execution_id: "exec_invalid_input",
                causation_request_id: "req_host_invalid_input",
                conversation_id: "unknown", task_id: "unknown", step_id: "unknown",
                tool: "unknown", status: "failed", executed_at: ISO8601DateFormatter().string(from: Date()),
                error: hostError("invalid_tool_request"), operation_id: nil, result: nil,
                queried_range: nil, fetched_at: nil, results: nil))
            return
        }
        guard let capability = registry.capability(for: request.tool) else {
            emit(failureResult(request, "unsupported_operation"))
            return
        }
        emit(capability.execute(request))
    }
}

// Use a standard Swift application entry point and let AppKit own the run
// loop. This is a real AppKit lifecycle even though the host has no UI.
@main
struct MacAgentHostMain {
    static func main() {
        let application = NSApplication.shared
        application.setActivationPolicy(.accessory)
        let delegate = MacAgentHostDelegate()
        application.delegate = delegate
        application.run()
    }
}
