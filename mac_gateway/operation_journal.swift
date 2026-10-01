import CryptoKit
import Foundation

struct HostArguments: Codable {
    let title: String?
    let start: String?
    let end: String?
    let calendar_name: String?
    let target_id: String?
    let candidate: Candidate?
}

struct Candidate: Codable {
    let title: String?
}

struct OperationJournalRecord: Codable, Equatable {
    let argumentsDigest: String
    var state: String
    var eventID: String?
    var errorCode: String?
}

enum OperationJournalClaim {
    case execute
    case replay(OperationJournalRecord)
    case outcomeUnknown
    case conflict
}

/// Minimal durable duplicate guard for local write operations.
/// EventKit and this file do not share a transaction; `started` is intentionally
/// treated as unknown after restart so the caller resolves real state first.
final class OperationJournal {
    private let fileURL: URL

    init(fileURL: URL? = nil) {
        if let fileURL {
            self.fileURL = fileURL
        } else {
            let base = FileManager.default.urls(
                for: .applicationSupportDirectory, in: .userDomainMask
            )[0]
            self.fileURL = base
                .appendingPathComponent("com.calendaragent.mac-host", isDirectory: true)
                .appendingPathComponent("operation-journal.json", isDirectory: false)
        }
    }

    func claim(operationID: String, arguments: HostArguments) throws -> OperationJournalClaim {
        let argumentsDigest = try digest(arguments)
        var records = try load()
        if let existing = records[operationID] {
            guard existing.argumentsDigest == argumentsDigest else { return .conflict }
            switch existing.state {
            case "succeeded", "failed": return .replay(existing)
            default: return .outcomeUnknown
            }
        }
        records[operationID] = OperationJournalRecord(
            argumentsDigest: argumentsDigest, state: "started", eventID: nil, errorCode: nil
        )
        try save(records)
        return .execute
    }

    func complete(operationID: String, arguments: HostArguments,
                  eventID: String?, errorCode: String?) throws {
        var records = try load()
        guard var record = records[operationID], record.argumentsDigest == (try digest(arguments)) else {
            throw JournalError.invalidTransition
        }
        guard record.state == "started" else { throw JournalError.invalidTransition }
        record.state = eventID == nil ? "failed" : "succeeded"
        record.eventID = eventID
        record.errorCode = errorCode
        records[operationID] = record
        try save(records)
    }

    private func digest(_ arguments: HostArguments) throws -> String {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        let bytes = try encoder.encode(arguments)
        return SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
    }

    private func load() throws -> [String: OperationJournalRecord] {
        guard FileManager.default.fileExists(atPath: fileURL.path) else { return [:] }
        let bytes = try Data(contentsOf: fileURL)
        return try JSONDecoder().decode([String: OperationJournalRecord].self, from: bytes)
    }

    private func save(_ records: [String: OperationJournalRecord]) throws {
        let directory = fileURL.deletingLastPathComponent()
        try FileManager.default.createDirectory(
            at: directory, withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700]
        )
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o700], ofItemAtPath: directory.path
        )
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        try encoder.encode(records).write(to: fileURL, options: .atomic)
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o600], ofItemAtPath: fileURL.path
        )
    }

    private enum JournalError: Error {
        case invalidTransition
    }
}
