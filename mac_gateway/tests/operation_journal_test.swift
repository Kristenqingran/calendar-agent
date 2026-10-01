import Foundation

@main
struct OperationJournalContractTest {
    static func main() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("operation-journal-test-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        let file = directory.appendingPathComponent("journal.json")
        let args = HostArguments(
            title: "QA only", start: "2026-10-01T15:00:00+08:00",
            end: "2026-10-01T16:00:00+08:00", calendar_name: nil,
            target_id: nil, candidate: nil
        )
        let journal = OperationJournal(fileURL: file)
        guard case .execute = try journal.claim(operationID: "op_1", arguments: args) else {
            fatalError("new operation must be claimed for execution")
        }
        try journal.complete(operationID: "op_1", arguments: args,
                             eventID: "real-id-from-executor", errorCode: nil)
        guard case .replay(let success) = try journal.claim(operationID: "op_1", arguments: args),
              success.state == "succeeded", success.eventID == "real-id-from-executor" else {
            fatalError("completed operation must replay its persisted result")
        }
        let filePermissions = try FileManager.default.attributesOfItem(atPath: file.path)[.posixPermissions]
            as? NSNumber
        guard filePermissions?.intValue == 0o600 else {
            fatalError("journal file permissions must be restricted to the current user")
        }

        let changed = HostArguments(
            title: "Different", start: args.start, end: args.end,
            calendar_name: nil, target_id: nil, candidate: nil
        )
        guard case .conflict = try journal.claim(operationID: "op_1", arguments: changed) else {
            fatalError("operation ID reuse with different arguments must conflict")
        }

        guard case .execute = try journal.claim(operationID: "op_2", arguments: args) else {
            fatalError("new in-flight operation must be claimed")
        }
        guard case .outcomeUnknown = try OperationJournal(fileURL: file)
            .claim(operationID: "op_2", arguments: args) else {
            fatalError("a persisted started operation must resolve as unknown, not retry")
        }
        print("operation journal contract PASS")
    }
}
