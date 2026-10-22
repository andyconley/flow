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
        # Keep private generated state out of Git without editing project or
        # shared-worktree Git configuration. Never overwrite a user's ignore.
        ignore = self.project/'.glg/.gitignore'
        ignore.parent.mkdir(parents=True, exist_ok=True)
        try:
            with ignore.open('x') as stream:
                stream.write('*\n')
        except FileExistsError:
            pass
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


# Shared with the coordinator: definitions may describe planned verification;
# only executable briefs may cross the implementation approval boundary.
BRIEF_SCHEMA = {
    'type': 'object',
    'properties': {
        'goal': {'type': 'string', 'minLength': 1},
        'scope': {'anyOf': [{'type': 'string', 'minLength': 1}, {'type': 'array', 'minItems': 1, 'items': {'type': 'string', 'minLength': 1}}]},
        'acceptance_criteria': {'anyOf': [{'type': 'string', 'minLength': 1}, {'type': 'array', 'minItems': 1, 'items': {'type': 'string', 'minLength': 1}}]},
        'check_command': {'type': 'array', 'minItems': 1, 'items': {'type': 'string', 'minLength': 1}},
        'verification_plan': {'type': 'string', 'minLength': 1},
        'prerequisites': {'type': 'array', 'items': {'type': 'string', 'minLength': 1}},
        'coverage': {'type': 'array', 'items': {'type': 'object', 'properties': {
            'criterion': {'type': 'string', 'minLength': 1},
            'method': {'enum': ['automated', 'manual', 'uncovered']},
            'evidence': {'type': 'string', 'minLength': 1}},
            'required': ['criterion', 'method', 'evidence'], 'additionalProperties': False}},
        'check_scope': {'enum': ['smoke', 'acceptance']},
    },
    'required': ['goal', 'scope', 'acceptance_criteria', 'check_command'],
}


def _schema_errors(value, schema, path='brief'):
    errors = []
    if 'anyOf' in schema:
        if not any(not _schema_errors(value, option, path) for option in schema['anyOf']): errors.append(path+' has an invalid type or empty value')
    types = {'object': dict, 'array': list, 'string': str}
    if 'type' in schema and not isinstance(value, types[schema['type']]):
        return [path+' must be '+schema['type']]
    if 'enum' in schema and value not in schema['enum']: errors.append(path+' has an unsupported value')
    if isinstance(value, str) and (len(value.strip()) < schema.get('minLength', 0) or '\x00' in value): errors.append(path+' must be nonempty text without NUL')
    if isinstance(value, list):
        if len(value) < schema.get('minItems', 0): errors.append(path+' must be nonempty')
        for index, item in enumerate(value): errors.extend(_schema_errors(item, schema.get('items', {}), f'{path}[{index}]'))
    if isinstance(value, dict):
        for key in schema.get('required', []):
            if key not in value: errors.append(path+' requires '+key)
        for key, item in value.items():
            if key in schema.get('properties', {}): errors.extend(_schema_errors(item, schema['properties'][key], path+'.'+key))
            elif schema.get('additionalProperties') is False: errors.append(path+' has unknown field '+key)
    return errors


def brief_schema(executable=True):
    if executable: return BRIEF_SCHEMA
    return {**BRIEF_SCHEMA, 'required': ['goal', 'scope', 'acceptance_criteria'],
            'anyOf': [{'required': ['check_command']}, {'required': ['verification_plan']}]}


def validate_brief(value, executable=True):
    schema = brief_schema(executable)
    errors = _schema_errors(value, schema)
    if not executable and isinstance(value, dict) and 'check_command' not in value and not value.get('verification_plan'):
        errors.append('brief requires verification_plan when check_command is not yet defined')
    if isinstance(value, dict) and 'coverage' in value and not errors:
        criteria = value['acceptance_criteria']; criteria = [criteria] if isinstance(criteria, str) else criteria
        names = [row['criterion'] for row in value['coverage']]
        if len(set(names)) != len(names) or set(names) != set(criteria): errors.append('coverage must map every acceptance criterion exactly once')
    if errors: raise ArtifactError('; '.join(errors))
    return value
