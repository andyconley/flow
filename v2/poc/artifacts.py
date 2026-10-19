"""Immutable, human-reviewable context records; never a workflow state ledger."""
from pathlib import Path
import hashlib
import json
import os
import re
import tempfile


class ArtifactError(ValueError):
    pass


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}', value):
        raise ArtifactError('Use a simple work/record identifier without path separators')
    return value


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix='.publish-')
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Artifacts:
    KINDS = {'briefs', 'contexts', 'decisions', 'assignments', 'results', 'shaping', 'closures'}

    def __init__(self, project, work_id):
        self.project = Path(project).resolve()
        self.work_id = identifier(work_id)
        self.root = self.project / '.glg' / 'work' / self.work_id
        if not self.root.resolve().is_relative_to(self.project):
            raise ArtifactError('Artifact storage escapes project through a symlink')

    def publish(self, kind, record_id, payload, supersedes=None):
        if kind not in self.KINDS:
            raise ArtifactError('Unknown artifact kind')
        identifier(record_id)
        if supersedes:
            old = self.read(supersedes)
            if old['kind'] != kind or old['id'] != record_id:
                raise ArtifactError('Supersession must identify the same kind and record')
        record = {'schema_version': 1, 'work_id': self.work_id, 'kind': kind,
                  'id': record_id, 'supersedes': supersedes, 'payload': payload}
        raw = (json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode()
        revision = hashlib.sha256(raw).hexdigest()
        path = self.root / kind / f'{record_id}-{revision}.json'
        self._contained(path)
        # Link publication is atomic and never replaces an existing revision.
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.revision-')
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != raw:
                    raise ArtifactError('Existing revision was modified')
        finally:
            os.unlink(temporary)
        return {'path': path.relative_to(self.project).as_posix(), 'revision': revision}

    def _contained(self, path):
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise ArtifactError('Artifact reference escapes this work item')

    def read(self, reference):
        if not isinstance(reference, dict) or set(reference) != {'path', 'revision'}:
            raise ArtifactError('An exact path and revision reference is required')
        path = self.project / reference['path']
        self._contained(path)
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != reference['revision']:
            raise ArtifactError('Referenced revision was modified; recovery requires inspection')
        value = json.loads(raw)
        if value.get('schema_version') != 1 or value.get('work_id') != self.work_id:
            raise ArtifactError('Unsupported or foreign artifact')
        return value

    def revisions(self, kind, record_id):
        values = []
        for path in sorted((self.root / kind).glob(f'{identifier(record_id)}-*.json')):
            ref = {'path': path.relative_to(self.project).as_posix(),
                   'revision': path.stem.rsplit('-', 1)[1]}
            values.append((ref, self.read(ref)))
        return values

    def leaf(self, kind, record_id):
        records = self.revisions(kind, record_id)
        superseded = {record['supersedes']['revision'] for _, record in records if record['supersedes']}
        leaves = [(ref, record) for ref, record in records if ref['revision'] not in superseded]
        if len(leaves) > 1:
            raise ArtifactError('Conflicting revisions; inspect and resolve rather than selecting newest')
        return leaves[0] if leaves else (None, None)


def validate_brief(value):
    if not isinstance(value, dict):
        raise ArtifactError('Brief must be a JSON object')
    for key in ('goal', 'scope', 'acceptance_criteria'):
        if not value.get(key):
            raise ArtifactError(f'Brief requires {key}')
    checks = value.get('check_command')
    if not isinstance(checks, list) or not checks or any(not isinstance(x, str) or not x for x in checks):
        raise ArtifactError('check_command must be a nonempty argv array')
    for key in ('scope', 'acceptance_criteria'):
        if not isinstance(value[key], (str, list)):
            raise ArtifactError(f'{key} must be text or an array')
    return value
