"""Flow-owned persistent local MAF sessions; child tools require parent authority.

The observer sees a model_request before its send and may deny by returning False.
Provider grants, resource policies, source scopes and review gates belong to the
calling gateway. A session never receives another assignment's transcript.
"""
from __future__ import annotations
import hashlib
import json
import os
import signal
import subprocess
import time
import threading
import uuid
from pathlib import Path
from typing import Callable
import select
from execution_contracts import LOCAL_AGENT_IPC_BYTES
try:
    from delivery_cancel import wake, wakeup_fds
except ModuleNotFoundError:
    from cli.delivery_cancel import wake, wakeup_fds


class MafTransportError(RuntimeError):
    """A retained local session failed or its send outcome is uncertain."""


def _read_message(fd, deadline, pending, check=None):
    while b'\n' not in pending:
        if check:
            check()
        if len(pending) > LOCAL_AGENT_IPC_BYTES:
            raise MafTransportError('Oversized local-agent frame')
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            raise MafTransportError('Local agent turn timed out')
        wakeup = wakeup_fds()
        ready, _, _ = select.select([fd, *wakeup], [], [], min(remaining, .25) if check else remaining)
        if wakeup and wakeup[0] in ready:
            wake()
        if fd not in ready:
            continue
        data = os.read(fd, 65536)
        if not data:
            raise MafTransportError('Local agent disconnected; consult recorded sends before recovery')
        pending.extend(data)
    line, _, rest = pending.partition(b'\n')
    if len(line) + 1 > LOCAL_AGENT_IPC_BYTES:
        raise MafTransportError('Oversized local-agent frame')
    pending[:] = rest
    value = json.loads(line)
    if not isinstance(value, dict) or value.get('protocol_version') != 1:
        raise MafTransportError('Invalid local-agent frame')
    return value


def _write_bounded(fd, value, deadline, check=None):
    payload = (json.dumps(value)+'\n').encode()
    if len(payload) > LOCAL_AGENT_IPC_BYTES:
        raise MafTransportError('Oversized local-agent frame')
    os.set_blocking(fd, False)
    position = 0
    while position < len(payload):
        if check:
            check()
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            raise MafTransportError('Local agent write timed out')
        wakeup = wakeup_fds()
        ready, writable, _ = select.select(wakeup, [fd], [], min(remaining, .25) if check else remaining)
        if ready:
            wake()
        if fd in writable:
            try:
                position += os.write(fd, payload[position:])
            except BlockingIOError:
                pass


class LocalAgentSession:
    def __init__(self, *, assignment_id: str, instructions: str, model: str,
                 runtime_python: str, artifact_dir: Path, tools: list[str],
                 source_root: Path | None = None, num_ctx: int = 49152,
                 num_predict: int = 12288, request_timeout: float = 600,
                 turn_timeout: float = 2400, max_iterations: int | None = 40,
                 max_function_calls: int | None = 80, context_reserve: int = 2048, observer: Callable | None = None,
                 resource_monitor_factory: Callable | None = None):
        self.assignment_id = assignment_id
        self.session_id = uuid.uuid4().hex
        self.observer = observer
        self.turn_timeout = turn_timeout
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.artifact_dir / f'local-session-{self.session_id}.jsonl'
        self.events = []
        self._record_lock = threading.Lock()
        self.resource_monitor = None
        self.pending = bytearray()
        self.closed = False
        root = Path(source_root or Path(__file__).resolve().parent.parent)
        env = {key: value for key, value in os.environ.items()
               if key in ('PATH', 'SYSTEMROOT', 'TMPDIR', 'LANG', 'LC_ALL')}
        env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(root / 'runtime'))
        self.stderr = (self.artifact_dir / f'local-session-{self.session_id}.stderr').open('wb')
        self.process = subprocess.Popen([runtime_python, '-m', 'maf_runner.local_agent'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
            cwd=root, env=env, start_new_session=True)
        self.config = dict(assignment_id=assignment_id, instructions=instructions,
            model=model, tools=tools, num_ctx=num_ctx, num_predict=num_predict,
            request_timeout=request_timeout, turn_timeout=turn_timeout,
            max_iterations=max_iterations, max_function_calls=max_function_calls, context_reserve=context_reserve)
        self.config_digest = hashlib.sha256(json.dumps(self.config, sort_keys=True).encode()).hexdigest()
        try:
            if resource_monitor_factory is not None:
                self.resource_monitor = resource_monitor_factory(callback=self._resource_observation)
                self.resource_monitor.start()
            self._send(self.config, time.monotonic()+60)
            ready = self._receive(time.monotonic()+60)
            if ready.get('type') != 'ready':
                raise MafTransportError(f'Local MAF worker did not become ready: {ready}')
        except BaseException:
            self.close()
            raise

    def _check_resources(self):
        if self.resource_monitor is not None:
            self.resource_monitor.check()

    def _resource_observation(self, sample, decision):
        self._record({'type': 'resource_observation', 'sample': sample, 'decision': decision})

    def _send(self, message, deadline):
        self._check_resources()
        _write_bounded(self.process.stdin.fileno(), message, deadline, self._check_resources if self.resource_monitor else None)

    def _receive(self, deadline):
        self._check_resources()
        return _read_message(self.process.stdout.fileno(), deadline, self.pending, self._check_resources if self.resource_monitor else None)

    def _record(self, event):
        record = dict(event, session_id=self.session_id, assignment_id=self.assignment_id,
                      observed_at=time.time())
        with self._record_lock:
            self.events.append(record)
            with self.log_path.open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(record, default=str)+'\n')
        return record

    def run(self, task: str, callback: Callable[[str, dict], object], observer: Callable | None = None):
        if self.closed:
            raise MafTransportError('Local session is closed; uncertain sends cannot be automatically replayed')
        deadline = time.monotonic()+self.turn_timeout
        start = len(self.events)
        observe = observer or self.observer
        self._record({'type': 'assignment_turn', 'task': task})
        try:
            self._send({'type': 'run', 'task': task}, deadline)
            while True:
                event = self._receive(deadline)
                record = self._record(event)
                kind = event.get('type')
                if kind == 'model_request':
                    allowed = observe(record) is not False if observe else True
                    self._send({'type': 'model_authorized', 'allowed': allowed}, deadline)
                elif kind == 'tool':
                    self._check_resources()
                    if observe and observe(record) is False:
                        raise MafTransportError('Local agent tool denied by observer')
                    result = callback(event['name'], event['arguments'])
                    observation = self._record({'type': 'tool_result', 'name': event['name'],
                                                'arguments': event['arguments'], 'result': result})
                    if observe:
                        observe(observation)
                    self._send({'type': 'tool_result', 'result': result}, deadline)
                elif kind == 'result':
                    selected = self.events[start:]
                    return {'text': event['text'], 'output': event['text'],
                            'session_id': self.session_id,
                            'model_requests': [x for x in selected if x['type'] == 'model_request'],
                            'model_responses': [x for x in selected if x['type'] == 'model_response'],
                            'model_sends': [x for x in selected if x['type'] == 'model_send'],
                            'tool_observations': [x for x in selected if x['type'] == 'tool_result'],
                            'events': selected, 'history_path': str(self.log_path)}
                elif kind == 'error':
                    if self.resource_monitor is not None:
                        self.resource_monitor.record_error(event['error'])
                    raise RuntimeError(event['error'])
                elif observe:
                    observe(record)
        except BaseException as exc:
            if self.resource_monitor is not None:
                try:
                    self.resource_monitor.record_error(exc)
                except BaseException:
                    self.close()
                    raise
            # No new session/retry here: outcome may be uncertain after an actual send.
            self.close()
            raise

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
                self.process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                if self.process.poll() is None:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait(timeout=5)
        if self.resource_monitor is not None:
            self.resource_monitor.stop()
        self.process.stdin.close()
        self.process.stdout.close()
        self.stderr.close()


class LocalAgentPool:
    def __init__(self, **defaults):
        self.defaults = defaults
        self.sessions = {}

    def run(self, assignment_id: str, instructions: str, task: str, callback: Callable,
            **options):
        config = dict(self.defaults, **options, assignment_id=assignment_id, instructions=instructions)
        session = self.sessions.get(assignment_id)
        if session is None:
            session = LocalAgentSession(**config)
            self.sessions[assignment_id] = session
        else:
            for field in ('instructions', 'model', 'tools', 'num_ctx', 'num_predict'):
                if field in config and session.config[field] != config[field]:
                    raise ValueError(f'Retained assignment {field} changed; explicit new assignment required')
        return session.run(task, callback, options.get('observer'))

    def close(self):
        for session in self.sessions.values():
            session.close()
