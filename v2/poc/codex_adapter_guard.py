"""Build an isolated guard for the pinned adapter; never edit installed packages."""
import hashlib
from pathlib import Path

PINNED_VERSION = "2.2.2"
PINNED_SOURCE_SHA256 = "6b1bb4e7e9caaf4aeca1042ae4aec2dc2433b0b0e4b1614b38a4d41699902aaa"


def guarded_source(source):
    phase = 'return airOnlyMeta(airClient, AIR_MESSAGE_PHASE_KEY, phase);'
    if source.count(phase) != 1:
        raise ValueError("unsupported adapter message-phase implementation")
    source = source.replace(phase, 'return { ...airOnlyMeta(airClient, AIR_MESSAGE_PHASE_KEY, phase), "goose.native.messagePhase": phase };')
    command_end = 'output: item.aggregatedOutput ?? "",\n          exitCode: item.exitCode,'
    # Live completion and history replay use the same typed native status.
    if source.count(command_end) != 2:
        raise ValueError('unsupported adapter native command-status implementation')
    source = source.replace(command_end, command_end+'\n          nativeStatus: item.status,')
    command = 'return end.terminal ? void 0 : { exit_code: end.exitCode };'
    if source.count(command) != 1:
        raise ValueError('unsupported adapter command-result implementation')
    source = source.replace(command, r'''const output = end.output || "";
    if (end.nativeStatus === "declined") {
      return { exit_code: end.exitCode, output,
        "goose.native.boundary": { kind: "permission_required",
          code: "NATIVE_COMMAND_DECLINED", message: "Native command request was declined",
          source: "codex_command_status" } };
    }
    const denied = /(?:^|\n)PermissionError: \[Errno (1|13)\] (?:Operation not permitted|Permission denied)(?::[^\n]*)?(?:\n|$)/.exec(output);
    if (Number.isInteger(end.exitCode) && end.exitCode !== 0 && denied) {
      return { exit_code: end.exitCode, output,
        "goose.native.boundary": { kind: "permission_required",
          code: denied[1] === "1" ? "EPERM" : "EACCES",
          message: denied[0].trim(), errno: Number(denied[1]),
          source: "codex_command_python_exception" } };
    }
    return { exit_code: end.exitCode, output };''')
    completion = 'const rawOutput = this.commandEndRawOutput(end);'
    if source.count(completion) != 1:
        raise ValueError('unsupported adapter command-completion implementation')
    source = source.replace(completion, completion + r'''
        // A process exiting nonzero is a completed command, not a failed
        // transport operation. Keep its exit/output and original status as
        // evidence. Missing exit codes, non-command failures and explicit
        // permission boundaries retain their original failure semantics.
        if (Number.isInteger(end.exitCode) && facts4.status === "failed" &&
            ["failed", "completed"].includes(end.nativeStatus) &&
            rawOutput && !rawOutput["goose.native.boundary"]) {
          rendered["status"] = "completed";
          rawOutput["goose.native.commandResult"] = {
            classification: "process_exit", exit_code: end.exitCode,
            native_status: facts4.status
          };
        }''')
    return source


def build(adapter, destination):
    import json
    adapter, destination = Path(adapter), Path(destination)
    if json.loads((adapter.parent.parent / "package.json").read_text())["version"] != PINNED_VERSION:
        raise ValueError("adapter version has not been qualified offline")
    source = adapter.read_text()
    if hashlib.sha256(source.encode()).hexdigest() != PINNED_SOURCE_SHA256:
        raise ValueError("adapter bundle hash has not been qualified offline")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(guarded_source(source))
    return {"adapter_version": PINNED_VERSION, "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "guarded_sha256": hashlib.sha256(destination.read_bytes()).hexdigest()}
