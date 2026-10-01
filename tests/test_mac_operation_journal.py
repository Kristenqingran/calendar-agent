import subprocess
from pathlib import Path


def test_swift_operation_journal_persists_and_blocks_unsafe_replay(tmp_path):
    root = Path(__file__).parents[1]
    source = root / "mac_gateway" / "operation_journal.swift"
    harness = root / "mac_gateway" / "tests" / "operation_journal_test.swift"
    executable = tmp_path / "operation-journal-contract-test"

    subprocess.run(
        ["swiftc", str(source), str(harness), "-o", str(executable)],
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        [str(executable)], check=True, capture_output=True, text=True, timeout=10
    )

    assert result.stdout.strip() == "operation journal contract PASS"
