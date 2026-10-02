"""Cooperative cancel of a live v8 delivery parent (ADR 0019).

SIGTERM only sets a flag. It raises ``DeliveryCancelled`` at most once, and
only while the parent is inside an ``interruptible()`` wait (a provider
subprocess, the MAF child pipe, the Ollama request, the targeted test), never
around ledger writes or Flow's own evidence files (a provider's streamed trace
output is the only file written inside one, and it is diagnostic only). Everywhere else the parent checks the flag at
its next authorization boundary. Sealing happens in ordinary code after the
stack has unwound.

A signal that lands after Python's last pending-signal check but before a
``select`` blocks does not interrupt it, so the handler would wait for the
deadline. The controller therefore owns a wakeup pipe (``signal.set_wakeup_fd``)
that Flow's own ``select`` waits include; a byte on it wakes the wait, which
then calls ``wake()`` to raise the pending cancel. Provider pipes use
``CancellableSelector``; a blocking call no selector can watch (the Ollama
request) goes through ``run_interruptibly``.
"""

from __future__ import annotations

import os
import select
import selectors
import signal
import threading
import time
from contextlib import contextmanager, nullcontext, suppress
from pathlib import Path
from typing import Any, Callable, ContextManager, Iterator, TypeVar

import process_identity

# The cancel CLI's request file, per attempt directory (ADR 0019).
CANCEL_REQUEST = "cancel-request.json"


class DeliveryCancelled(Exception):
    """A cancel was requested; subclasses Exception so in-flight sends are marked unknown."""


class CancelController:
    def __init__(self) -> None:
        self.requested = False
        self.raised = False
        self.armed = True
        self.depth = 0
        self.installed = False
        self._previous: Any = None
        self._previous_wakeup = -1
        self.wakeup_fd: int | None = None
        self._wakeup_write: int | None = None

    def install(self) -> bool:
        """Install the SIGTERM handler; False when this thread cannot (then cancel is unsupported)."""
        try:
            self._previous = signal.signal(signal.SIGTERM, self._handle)
        except (ValueError, OSError):
            return False
        self.installed = True
        read_fd, write_fd = os.pipe()
        os.set_blocking(read_fd, False)
        os.set_blocking(write_fd, False)
        try:
            self._previous_wakeup = signal.set_wakeup_fd(write_fd, warn_on_full_buffer=False)
        except (ValueError, OSError):
            os.close(read_fd)
            os.close(write_fd)
        else:
            self.wakeup_fd, self._wakeup_write = read_fd, write_fd
        return True

    def restore(self) -> None:
        if self.installed:
            signal.signal(signal.SIGTERM, self._previous if self._previous is not None else signal.SIG_DFL)
            self.installed = False
        if self.wakeup_fd is not None:
            signal.set_wakeup_fd(self._previous_wakeup)
            os.close(self.wakeup_fd)
            os.close(self._wakeup_write)  # type: ignore[arg-type]
            self.wakeup_fd = self._wakeup_write = None

    def _fire(self) -> None:
        self.raised = True
        raise DeliveryCancelled("delivery cancel requested")

    def _handle(self, signum: int, frame: Any) -> None:
        self.requested = True
        if self.depth > 0 and self.armed and not self.raised:
            self._fire()

    @contextmanager
    def interruptible(self) -> Iterator[None]:
        """A wait the handler may break once; a cancel already pending breaks it on entry."""
        if self.requested and self.armed and not self.raised:
            self._fire()
        self.depth += 1
        try:
            yield
        finally:
            self.depth -= 1

    def wake(self) -> None:
        """A ``select`` woke on the wakeup pipe: drain it, then break the wait if a cancel is pending."""
        if self.wakeup_fd is not None:
            try:
                while os.read(self.wakeup_fd, 512):
                    pass
            except BlockingIOError:
                pass
        if self.requested and self.depth > 0 and self.armed and not self.raised:
            self._fire()

    def check(self) -> None:
        """At an authorization boundary: a pending cancel stops any new authorization."""
        if self.requested and self.armed:
            raise DeliveryCancelled("delivery cancel requested")

    def disarm(self) -> None:
        """After the runtime outcome is recorded, a late cancel lets the normal seal finish."""
        self.armed = False


_CURRENT: CancelController | None = None


def current() -> CancelController | None:
    return _CURRENT


def wakeup_fds() -> list[int]:
    """The wakeup pipe for a ``select`` inside ``interruptible()``, or none."""
    controller = _CURRENT
    return [controller.wakeup_fd] if controller is not None and controller.wakeup_fd is not None else []


def wake() -> None:
    controller = _CURRENT
    if controller is not None:
        controller.wake()


_WAKEUP = object()
T = TypeVar("T")


class CancellableSelector:
    """A ``selectors.DefaultSelector`` that a pending cancel wakes.

    The wakeup pipe is registered but hidden from ``get_map()``, so callers'
    ``while selector.get_map()`` loops still end when their own files do.
    ``select`` never returns for the wakeup alone: it raises the pending
    cancel, or keeps waiting out the caller's timeout, so an empty result
    still means the timeout passed.
    """

    def __init__(self) -> None:
        self._selector = selectors.DefaultSelector()
        fds = wakeup_fds()
        if fds:
            self._selector.register(fds[0], selectors.EVENT_READ, _WAKEUP)

    def register(self, fileobj: Any, events: int, data: Any = None) -> selectors.SelectorKey:
        return self._selector.register(fileobj, events, data)

    def unregister(self, fileobj: Any) -> selectors.SelectorKey:
        return self._selector.unregister(fileobj)

    def get_map(self) -> dict[Any, selectors.SelectorKey]:
        return {fileobj: key for fileobj, key in self._selector.get_map().items() if key.data is not _WAKEUP}

    def select(self, timeout: float | None = None) -> list[tuple[selectors.SelectorKey, int]]:
        end = None if timeout is None else time.monotonic() + timeout
        while True:
            remaining = None if end is None else max(0.0, end - time.monotonic())
            ready = self._selector.select(remaining)
            events = [(key, mask) for key, mask in ready if key.data is not _WAKEUP]
            if len(events) != len(ready):
                wake()
            if events or not ready:
                return events

    def close(self) -> None:
        self._selector.close()


def run_interruptibly(call: Callable[[], T], *, abort: Callable[[], None] | None = None) -> T:
    """Run a blocking call no Flow select can watch, so that a cancel still breaks it.

    Without an active controller the call runs inline. Otherwise it runs on a
    helper thread while this thread waits on the wakeup pipe; a cancel calls
    ``abort`` (which should unblock the helper, e.g. by shutting its socket)
    and raises here. Call it inside ``interruptible()``.
    """
    controller = _CURRENT
    if controller is None or controller.wakeup_fd is None:
        return call()
    done_read, done_write = os.pipe()
    outcome: dict[str, Any] = {}

    def target() -> None:
        try:
            outcome["value"] = call()
        except BaseException as exc:  # handed to the waiting thread
            outcome["error"] = exc
        finally:
            # The helper owns its write end, so an abandoned wait can never
            # make it write into a reused descriptor.
            with suppress(OSError):
                os.write(done_write, b"\0")
            os.close(done_write)

    thread = threading.Thread(target=target, name="flow-interruptible-call", daemon=True)
    try:
        thread.start()
        try:
            while True:
                ready, _, _ = select.select([done_read, controller.wakeup_fd], [], [])
                if done_read in ready:
                    break
                controller.wake()
        except DeliveryCancelled:
            if abort is not None:
                with suppress(Exception):
                    abort()
            raise
    finally:
        os.close(done_read)
    thread.join()
    if "error" in outcome:
        raise outcome["error"]
    return outcome["value"]


def interruptible() -> ContextManager[None]:
    controller = _CURRENT
    return controller.interruptible() if controller is not None else nullcontext()


@contextmanager
def parent_scope(attempt_dir: Path, generation: int, *, attempt_id: str) -> Iterator[CancelController]:
    """Own one dispatching parent's cancel surface: install, record, run, close, restore.

    The handler is installed before the control record says cancel is
    supported, and restored only after the record is marked closed, so a
    cancel never signals a parent without its handler.
    """
    global _CURRENT
    # A request present before this parent recorded itself is left over from
    # a cancel CLI that died; it must never turn a later stray SIGTERM into a
    # cancel. (The CLI writes a request only after seeing this parent live.)
    stale = attempt_dir / CANCEL_REQUEST
    if os.path.lexists(stale):
        stale.unlink()
    controller = CancelController()
    supported = controller.install()
    _CURRENT = controller if supported else None
    try:
        with process_identity.control_scope(attempt_dir, generation, attempt_id=attempt_id,
                                            cancel_supported=supported):
            yield controller
    finally:
        _CURRENT = None
        controller.restore()
