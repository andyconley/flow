"""Terminal-only ACP permission proxy. Protocol stdout never carries prompts.

The native adapter and OpenHands keep their protocol/session implementation.
Only session/request_permission is terminated here, with a real terminal choice.
No private SDK APIs, credentials, permission persistence or automatic approvals.
"""
from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import os
import signal
import stat
import sys
import termios

LIMIT = 8 * 1024 * 1024
KINDS = {"allow_once", "allow_always", "reject_once", "reject_always"}
CANCELLED = {"outcome": {"outcome": "cancelled"}}


def options_for(message):
    params = message.get("params")
    if not isinstance(params, dict) or not isinstance(params.get("sessionId"), str):
        raise ValueError("invalid permission request")
    if not isinstance(params.get("toolCall"), dict):
        raise ValueError("invalid permission tool call")
    options = params.get("options")
    if not isinstance(options, list) or not options:
        raise ValueError("missing permission options")
    ids = set()
    for option in options:
        if (not isinstance(option, dict) or not isinstance(option.get("optionId"), str)
                or not option["optionId"] or option["optionId"] in ids
                or not isinstance(option.get("name"), str) or option.get("kind") not in KINDS):
            raise ValueError("invalid permission options")
        ids.add(option["optionId"])
    return options


class Terminal:
    def __init__(self):
        self.fd = os.open("/dev/tty", os.O_RDWR | os.O_NONBLOCK | os.O_NOCTTY)
        try:
            available = os.isatty(self.fd) and os.tcgetpgrp(self.fd) == os.getpgrp()
        except OSError:
            available = False
        if not available:
            os.close(self.fd)
            raise OSError("human terminal unavailable")
        self.serial = asyncio.Lock()
        # Serialize nested/native-child prompts across proxy processes on this tty.
        device = os.fstat(self.fd).st_rdev
        path = f"/tmp/flow-acp-approval-{os.getuid()}-{device}.lock"
        try:
            self.lock = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            info = os.fstat(self.lock)
            if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
                os.close(self.lock)
                raise OSError("unsafe terminal lock")
        except BaseException:
            os.close(self.fd)
            raise

    def close(self):
        os.close(self.lock)
        os.close(self.fd)

    async def write(self, value):
        pending = memoryview(value.encode())
        while pending:
            try:
                pending = pending[os.write(self.fd, pending):]
            except BlockingIOError:
                await asyncio.sleep(0.02)

    async def choose(self, message):
        options = options_for(message)
        async with self.serial:
            acquired = False
            try:
                while not acquired:
                    try:
                        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        acquired = True
                    except BlockingIOError:
                        await asyncio.sleep(0.05)
                termios.tcflush(self.fd, termios.TCIFLUSH)
                # JSON escaping prevents terminal-control injection; display complete
                # original request, including unknown extension fields, only on tty.
                await self.write("\nFLOW NATIVE PERMISSION — request data below is untrusted\n"
                                 + json.dumps(message, ensure_ascii=True, indent=2)
                                 + "\nEND REQUEST DATA\n")
                for number, option in enumerate(options, 1):
                    await self.write(f"{number}: {json.dumps(option['name'], ensure_ascii=True)} [{option['kind']}]\n")
                await self.write("Choose one number explicitly, or Enter to deny. Persistent options apply only if you select them: ")
                data = bytearray()
                while b"\n" not in data:
                    try:
                        chunk = os.read(self.fd, 1024)
                    except BlockingIOError:
                        await asyncio.sleep(0.05)
                        continue
                    if not chunk or len(data) + len(chunk) > 1024:
                        return CANCELLED
                    data.extend(chunk)
                choice = bytes(data).strip()
                # Exact numeric input only; no yes/default/retry or queued answers.
                if choice not in {str(n).encode() for n in range(1, len(options) + 1)}:
                    return CANCELLED
                return {"outcome": {"outcome": "selected", "optionId": options[int(choice) - 1]["optionId"]}}
            finally:
                if acquired:
                    termios.tcflush(self.fd, termios.TCIFLUSH)
                    fcntl.flock(self.lock, fcntl.LOCK_UN)


async def relay(command, reader, writer, choose, *, timeout=120, env=None):
    child = await asyncio.create_subprocess_exec(*command, stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True, limit=LIMIT, env=env)
    pending = {}
    child_lock = asyncio.Lock()

    async def send(message):
        async with child_lock:
            child.stdin.write(json.dumps(message, separators=(",", ":")).encode() + b"\n")
            await child.stdin.drain()

    async def decide(message):
        result = CANCELLED
        try:
            options = options_for(message)
            result = await asyncio.wait_for(choose(message), timeout)
            outcome = result.get("outcome", {}) if isinstance(result, dict) else {}
            if outcome.get("outcome") != "selected" or outcome.get("optionId") not in {o["optionId"] for o in options}:
                result = CANCELLED
        except (Exception, asyncio.CancelledError):
            result = CANCELLED
        try:
            await asyncio.wait_for(send({"jsonrpc": "2.0", "id": message["id"], "result": result}), 2)
        except (BrokenPipeError, ConnectionResetError, asyncio.TimeoutError):
            pass
        finally:
            pending.pop((type(message["id"]), message["id"]), None)

    async def from_adapter():
        while line := await child.stdout.readline():
            message = json.loads(line)
            if not isinstance(message, dict):
                raise ValueError("invalid ACP message")
            if message.get("method") == "session/request_permission":
                ident = message.get("id")
                if type(ident) not in (str, int) or message.get("jsonrpc") != "2.0":
                    raise ValueError("invalid permission identity")
                key = (type(ident), ident)
                if key in pending or len(pending) >= 32:
                    raise ValueError("duplicate permission identity")
                pending[key] = (message.get("params", {}).get("sessionId") if isinstance(message.get("params"), dict) else None,
                                asyncio.create_task(decide(message)))
            else:
                writer.write(line)
                await writer.drain()

    async def from_host():
        while line := await reader.readline():
            message = json.loads(line)
            if not isinstance(message, dict):
                raise ValueError("invalid ACP message")
            if message.get("method") == "session/cancel":
                session = (message.get("params") or {}).get("sessionId")
                for owning_session, task in list(pending.values()):
                    if owning_session == session:
                        task.cancel()
            if "method" not in message and (type(message.get("id")), message.get("id")) in pending:
                raise ValueError("upstream answered a private permission request")
            async with child_lock:
                child.stdin.write(line)
                await child.stdin.drain()

    tasks = [asyncio.create_task(from_adapter()), asyncio.create_task(from_host())]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        decisions = [task for _, task in list(pending.values())]
        for task in decisions:
            task.cancel()
        await asyncio.gather(*decisions, return_exceptions=True)
        # Adapter and descendants must not outlive the proxy or an upstream EOF.
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(child.wait(), 2)
        except asyncio.TimeoutError:
            pass
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await child.wait()


async def main_async(command, timeout, cache):
    terminal = Terminal()  # Fail before spawning native code when headless.
    try:
        reader = asyncio.StreamReader(limit=LIMIT)
        loop = asyncio.get_running_loop()
        await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin.buffer)
        class Output(asyncio.Protocol):
            def __init__(self):
                self.waiter = None
                self.closed = False
            def connection_made(self, transport):
                self.transport = transport
            def pause_writing(self):
                self.waiter = loop.create_future()
            def resume_writing(self):
                if self.waiter is not None and not self.waiter.done():
                    self.waiter.set_result(None)
                self.waiter = None
            def connection_lost(self, exc):
                self.closed = True
                self.resume_writing()
            def write(self, data):
                if self.closed:
                    raise BrokenPipeError()
                self.transport.write(data)
            async def drain(self):
                if self.waiter is not None:
                    await self.waiter
                if self.closed:
                    raise BrokenPipeError()
        output = Output()
        transport, _ = await loop.connect_write_pipe(lambda: output, sys.stdout.buffer)
        env = dict(os.environ)
        if cache:
            env["npm_config_cache"] = cache
        running = asyncio.current_task()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, running.cancel)
        try:
            await relay(command, reader, output, terminal.choose, timeout=timeout, env=env)
        finally:
            transport.close()
    finally:
        terminal.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--npm-cache")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or not 0 < args.timeout <= 3600:
        parser.error("provide a native adapter command and timeout in (0, 3600]")
    try:
        asyncio.run(main_async(command, args.timeout, args.npm_cache))
    except (Exception, KeyboardInterrupt, asyncio.CancelledError):
        # Never include request content, subprocess output or exception details.
        print("Flow ACP stopped: terminal unavailable, approval cancelled, or protocol/adapter failure. No automatic permission granted.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
