"""Cooperative cancel of a live v8 delivery parent (ADR 0019).

SIGTERM only sets a flag. It raises ``DeliveryCancelled`` at most once, and
only while the parent is inside an ``interruptible()`` wait (a provider
subprocess, the MAF child pipe, the Ollama request, the targeted test), never
around ledger writes or Flow's own evidence files (a provider's streamed trace
output is the only file written inside one, and it is diagnostic only). Everywhere else the parent checks the flag at
its next authorization boundary. Sealing happens in ordinary code after the
stack has unwound.
"""

from __future__ import annotations

import os
import signal
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Any, ContextManager, Iterator

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

    def install(self) -> bool:
        """Install the SIGTERM handler; False when this thread cannot (then cancel is unsupported)."""
        try:
            self._previous = signal.signal(signal.SIGTERM, self._handle)
        except (ValueError, OSError):
            return False
        self.installed = True
        return True

    def restore(self) -> None:
        if self.installed:
            signal.signal(signal.SIGTERM, self._previous if self._previous is not None else signal.SIG_DFL)
            self.installed = False

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
