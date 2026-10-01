import EventKit
import Foundation

// JSON-lines helper. Each input line is one validated create request; each
// output line is one result. The Python gateway owns transport/auth/idempotency.
struct CreateRequest: Decodable {
    let operation_id: String
    let title: String
    let start: String
    let end: String
    let calendar_name: String?
}

struct Result: Encodable {
    let status: String
    let event_id: String?
    let error: String?
}

let store = EKEventStore()
let semaphore = DispatchSemaphore(value: 0)
var accessGranted = false

// The active Command Line Tools SDK exposes the legacy EventKit permission
// API. A newer SDK can provide stricter full-access APIs, but using the
// available API keeps this helper compatible with the installed toolchain.
store.requestAccess(to: .event) { granted, _ in
    accessGranted = granted
    semaphore.signal()
}
semaphore.wait()

func emit(_ result: Result) {
    let encoder = JSONEncoder()
    if let data = try? encoder.encode(result), let line = String(data: data, encoding: .utf8) {
        if let output = (line + "\n").data(using: .utf8) {
            FileHandle.standardOutput.write(output)
        }
    }
}

let decoder = JSONDecoder()
while let line = readLine() {
    guard let data = line.data(using: .utf8), let request = try? decoder.decode(CreateRequest.self, from: data) else {
        emit(Result(status: "failed", event_id: nil, error: "invalid_helper_request"))
        continue
    }
    guard accessGranted else {
        emit(Result(status: "failed", event_id: nil, error: "calendar_access_denied"))
        continue
    }
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    guard let start = formatter.date(from: request.start) ?? ISO8601DateFormatter().date(from: request.start),
          let end = formatter.date(from: request.end) ?? ISO8601DateFormatter().date(from: request.end) else {
        emit(Result(status: "failed", event_id: nil, error: "invalid_datetime"))
        continue
    }
    guard let calendar = (store.calendars(for: .event).first { calendar in
        request.calendar_name == nil || calendar.title == request.calendar_name!
    }) else {
        emit(Result(status: "failed", event_id: nil, error: "calendar_not_found"))
        continue
    }
    let event = EKEvent(eventStore: store)
    event.calendar = calendar
    event.title = request.title
    event.startDate = start
    event.endDate = end
    do {
        try store.save(event, span: .thisEvent, commit: true)
        emit(Result(status: "success", event_id: event.eventIdentifier, error: nil))
    } catch {
        emit(Result(status: "failed", event_id: nil, error: error.localizedDescription))
    }
}
