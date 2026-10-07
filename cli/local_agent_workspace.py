"""Parent-owned scoped tools and current-source-bound local-agent evidence."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Callable
from delivery_cancel import DeliveryCancelled


class LocalAgentWorkspace:
    def __init__(self, worktree: Path, read_paths: list[str], write_paths: list[str],
                 artifact_dir: Path, test_callback: Callable | None = None,
                 authority_callback: Callable | None = None,
                 assignment_scopes: dict | None = None, test_argv: list[str] | None = None,
                 test_timeout: float = 600):
        self.worktree = Path(worktree).resolve()
        self.read_paths = list(dict.fromkeys(read_paths + write_paths))
        self.write_paths = write_paths
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.test_callback = test_callback
        self.authority_callback = authority_callback
        self.assignment_scopes = assignment_scopes or {}
        self.test_argv = test_argv
        self.test_timeout = test_timeout
        self.reads = {}
        self.tests = {}
        self.reviews = {}
        self.handoffs = {}
        self.writes = {}
        self.handoff_reads = {}
        self.observations = []
        for scope in self.read_paths:
            self._path(scope, self.read_paths)
        self._restore_handoffs()

    def _restore_handoffs(self):
        """Recover observed handoffs, never invent current-session reads or tests."""
        log = self.artifact_dir / 'local-tools.jsonl'
        if not log.exists():
            if list(self.artifact_dir.glob('handoff-*.json')):
                raise ValueError('Handoff lacks durable parent tool observation')
            return
        if log.is_symlink():
            raise ValueError('Tool observation log is a symlink')
        records = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
        stale = []
        handoff_positions = {}
        for path in sorted(self.artifact_dir.glob('handoff-*.json')):
            if path.is_symlink():
                raise ValueError('Handoff artifact is a symlink')
            raw = path.read_bytes()
            artifact = json.loads(raw)
            producer = artifact['producer']
            digest = hashlib.sha256(raw).hexdigest()
            observed = next((record for record in reversed(records)
                if record.get('assignment_id') == producer and record.get('tool') == 'submit_handoff'
                and record.get('result', {}).get('status') == 'handoff_recorded'
                and record['result'].get('artifact_sha256') == digest), None)
            if observed is None:
                raise ValueError('Handoff differs from durable parent observation')
            position = next(index for index in reversed(range(len(records))) if records[index] is observed)
            handoff_positions[producer] = position
            writes = set()
            for name, expected in artifact['files'].items():
                self._path(name, self.write_paths)
                target = self._path(name, self._scopes(producer).get('write_paths', []))
                current = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None
                if current != expected:
                    stale.append((producer, name, current, position))
                if any(record.get('assignment_id') == producer and record.get('tool') == 'write_file'
                       and record.get('result', {}).get('status') == 'written'
                       and record['result'].get('path') == name
                       and record['result'].get('sha256') == expected for record in records):
                    writes.add(name)
            if not writes:
                raise ValueError('Handoff lacks observed current producer writes')
            self.handoffs[producer] = dict(artifact, artifact_sha256=digest, artifact_path=str(path))
            self.writes[producer] = writes
        for producer, name, current, position in stale:
            latest = next(((index, record) for index, record in reversed(list(enumerate(records)))
                if record.get('tool') == 'write_file'
                and record.get('result', {}).get('status') == 'written'
                and record['result'].get('path') == name), None)
            successor = latest[1].get('assignment_id') if latest else None
            artifact = self.handoffs.get(successor, {})
            if (latest is None or latest[0] <= position or successor == producer
                    or latest[1]['result'].get('sha256') != current
                    or artifact.get('files', {}).get(name) != current
                    or handoff_positions.get(successor, -1) <= latest[0]):
                raise ValueError('Persisted handoff source changed; reconcile producer evidence')

    def _authority(self):
        if self.authority_callback and self.authority_callback() is False:
            raise PermissionError('Current Flow authority denied this tool')

    def _scopes(self, assignment_id):
        return self.assignment_scopes.get(assignment_id, {
            'read_paths': self.read_paths, 'write_paths': self.write_paths})

    def _path(self, name, scopes):
        path = Path(name)
        if not isinstance(name, str) or not name or path.is_absolute() or any(
                part in ('..', '.git') for part in path.parts):
            raise PermissionError('Path must be an authorized relative path')
        if not any(path == Path(scope) or path.is_relative_to(Path(scope)) for scope in scopes):
            raise PermissionError('Path lies outside assignment scope')
        target = self.worktree / path
        cursor = target
        while cursor != self.worktree:
            if cursor.is_symlink():
                raise PermissionError('Symlink access is not authorized')
            cursor = cursor.parent
        if not target.resolve().is_relative_to(self.worktree):
            raise PermissionError('Path escapes worktree')
        return target

    def _snapshot(self):
        files = {}
        for name in self.write_paths:
            target = self._path(name, self.write_paths)
            if target.is_dir():
                targets = sorted(target.rglob('*'))
            else:
                targets = [target]
            for path in targets:
                relative = str(path.relative_to(self.worktree))
                safe = self._path(relative, self.write_paths)
                if safe.is_file():
                    files[relative] = hashlib.sha256(safe.read_bytes()).hexdigest()
                elif not safe.exists():
                    files[relative] = None
        return files

    @property
    def current_source_digest(self):
        return hashlib.sha256(json.dumps(self._snapshot(), sort_keys=True).encode()).hexdigest()

    def _record(self, assignment_id, name, result):
        event = {'assignment_id': assignment_id, 'tool': name, 'result': result,
                 'observed_at': time.time()}
        self.observations.append(event)
        with (self.artifact_dir / 'local-tools.jsonl').open('a') as handle:
            handle.write(json.dumps(event, default=str)+'\n')
        return result

    def callback(self, assignment_id, name, arguments):
        self._authority()
        try:
            handler = getattr(self, '_' + name)
            if name not in ('read_files', 'write_file', 'run_tests', 'submit_review',
                            'submit_handoff', 'read_handoff'):
                raise PermissionError('Unknown local-agent tool')
            result = handler(assignment_id, **arguments)
        except (PermissionError, FileNotFoundError, ValueError, TypeError) as exc:
            result = {'status': 'denied', 'reason': str(exc)}
        return self._record(assignment_id, name, result)

    def _read_files(self, assignment_id, paths):
        allowed = self._scopes(assignment_id).get('read_paths', self.read_paths)
        observed = self.reads.setdefault(assignment_id, {})
        result = []
        for name in paths:
            self._path(name, self.read_paths)
            target = self._path(name, allowed)
            if target.is_dir():
                raise ValueError('Read individual files; directory contents are not source evidence')
            raw = target.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            observed[name] = digest
            result.append({'path': name, 'sha256': digest, 'content': raw.decode('utf-8')})
        return {'status': 'read', 'files': result}

    def _write_file(self, assignment_id, path, content, expected_sha256=''):
        self._path(path, self.write_paths)
        target = self._path(path, self._scopes(assignment_id).get('write_paths', []))
        before = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None
        if expected_sha256 and before != expected_sha256:
            raise ValueError('Write source digest is stale')
        if before and self.reads.get(assignment_id, {}).get(path) != before:
            raise ValueError('Read the actual current file before replacing it')
        self._authority()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(content.encode('utf-8'))
            self._path(path, self._scopes(assignment_id).get('write_paths', []))
            self._authority()
            os.replace(temporary, target)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
        # Invalidated immediately, including another specialist's approval.
        self.writes.setdefault(assignment_id, set()).add(path)
        for reader, records in list(self.handoff_reads.items()):
            if any(path in record['files'] for record in records):
                self.handoff_reads.pop(reader, None)
        self.tests.clear()
        self.reviews.clear()
        return {'status': 'written', 'path': path,
                'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                'source_digest': self.current_source_digest}

    def _run_tests(self, assignment_id):
        before = self.current_source_digest
        if self.test_callback:
            try:
                result = self.test_callback()
            except DeliveryCancelled:
                raise
            except Exception as exc:
                result = {'status': 'failed', 'output_excerpt': str(exc)}
        elif self.test_argv:
            completed = subprocess.run(self.test_argv, cwd=self.worktree,
                capture_output=True, text=True, timeout=self.test_timeout,
                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
            output = completed.stdout + completed.stderr
            result = {'status': 'passed' if completed.returncode == 0 else 'failed',
                      'exit_code': completed.returncode, 'command': self.test_argv,
                      'output_excerpt': output[-8192:],
                      'output_sha256': hashlib.sha256(output.encode()).hexdigest()}
        else:
            raise ValueError('No Flow-authorized test command is configured')
        self._authority()
        after = self.current_source_digest
        evidence = dict(result, source_digest=before, current_source_digest=after)
        if before != after:
            evidence['status'] = 'stale'
        self.tests[assignment_id] = evidence
        return evidence

    def _submit_review(self, assignment_id, approved, findings):
        if self._scopes(assignment_id).get('write_paths'):
            raise PermissionError('Independent reviewer must have read-only assignment')
        snapshot = self._snapshot()
        observed = self.reads.get(assignment_id, {})
        if any(digest is not None and observed.get(path) != digest for path, digest in snapshot.items()):
            raise ValueError('Review requires actual reads of every current source file')
        test = self.tests.get(assignment_id, {})
        if test.get('source_digest') != self.current_source_digest:
            raise ValueError('Review requires a test observation on the current source')
        if approved and test.get('status') != 'passed':
            raise ValueError('Passing review requires actual passing current-source tests')
        if not isinstance(findings, str) or not findings.strip():
            raise ValueError('Review findings must describe actual evidence')
        evidence = 'Source SHA-256: '+self.current_source_digest+'; observed tests: '+str(test.get('status'))
        bounded_findings = findings.encode('utf-8')[:1024].decode('utf-8', errors='ignore')
        candidate = {'schema_version': 1, 'decision': 'pass' if approved else 'fail',
                     'summary': bounded_findings, 'findings': [] if approved else [
                         {'severity': 'blocking', 'summary': bounded_findings, 'evidence': evidence}]}
        self.reviews[assignment_id] = {'candidate': candidate,
            'source_digest': self.current_source_digest, 'test_evidence': test, 'raw_findings': findings}
        return {'status': 'review_recorded', **self.reviews[assignment_id]}

    def _submit_handoff(self, assignment_id, summary):
        paths = self._scopes(assignment_id).get('write_paths', [])
        files = {path: digest for path, digest in self._snapshot().items()
                 if any(Path(path) == Path(scope) or Path(path).is_relative_to(Path(scope)) for scope in paths)}
        if not self.writes.get(assignment_id) or not files or not isinstance(summary, str) or not summary.strip():
            raise ValueError('Handoff requires assigned source and concrete integration guidance')
        artifact = {'producer': assignment_id, 'files': files, 'summary': summary,
                    'source_digest': self.current_source_digest}
        identity = hashlib.sha256(assignment_id.encode()).hexdigest()[:16]
        path = self.artifact_dir / ('handoff-'+identity+'.json')
        path.write_text(json.dumps(artifact, sort_keys=True)+'\n')
        artifact['artifact_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        artifact['artifact_path'] = str(path)
        self.handoffs[assignment_id] = artifact
        return {'status': 'handoff_recorded', **artifact}

    def _read_handoff(self, assignment_id):
        records = []
        dependencies = self._scopes(assignment_id).get('handoff_dependencies')
        if dependencies is not None and any(producer not in self.handoffs for producer in dependencies):
            raise ValueError('Required specialist handoff is missing')
        for producer, artifact in self.handoffs.items():
            if producer == assignment_id or (dependencies is not None and producer not in dependencies):
                continue
            path = Path(artifact['artifact_path'])
            if hashlib.sha256(path.read_bytes()).hexdigest() != artifact['artifact_sha256']:
                raise ValueError('Handoff artifact changed')
            for name, digest in artifact['files'].items():
                target = self._path(name, self._scopes(assignment_id).get('read_paths', self.read_paths))
                actual = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None
                if actual != digest:
                    raise ValueError('Handoff source changed; producer must refresh it')
            records.append(artifact)
        if not records:
            raise ValueError('No preceding specialist handoff exists')
        self.handoff_reads[assignment_id] = records
        return {'status': 'handoff_read', 'handoffs': records}
