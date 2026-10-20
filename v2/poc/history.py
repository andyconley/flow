"""Read legacy/project records without translating their state or approvals."""
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from .artifacts import ArtifactError, Artifacts, identifier
from .runtime_env import ROOT

MAX_BYTES = 1_048_576


def document(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ArtifactError('Expected a regular bounded document: '+str(path))
    raw = path.read_bytes()
    text = raw.decode('utf-8')
    return {'path': str(path), 'revision': hashlib.sha256(raw).hexdigest(), 'content': text}


def legacy_runs(project, ancestors=True):
    project = Path(project).resolve()
    rows = []
    for root in [project, *project.parents] if ancestors else [project]:
        overlay = root/'.flow'
        if overlay.resolve() == (Path.home()/'.flow').resolve() or overlay.is_symlink():
            continue
        runs = overlay/'runs'
        if not runs.is_dir() or runs.is_symlink():
            continue
        for directory in sorted(runs.iterdir()):
            if not directory.is_dir() or directory.is_symlink():
                continue
            path = directory/'run.json'
            row = {'work_id': directory.name, 'project': str(root), 'origin': 'legacy',
                   'directory': str(directory), 'native_v2_resume': False,
                   'next_action': 'Use the legacy runtime, or create --legacy-run ID with fresh v2 approval'}
            try:
                value = document(path)
                data = json.loads(value.pop('content'))
                if not isinstance(data, dict):
                    raise ArtifactError('Legacy run is not a JSON object')
                row.update(reference=value, state=data.get('state'), stage=data.get('stage'), runtime=data.get('runtime'))
            except (OSError, ValueError, ArtifactError) as error:
                row['diagnostic'] = str(error)
            rows.append(row)
    return rows


def legacy_run(project, work):
    identifier(work)
    root = Path(project).resolve()
    directory = root/'.flow/runs'/work
    if directory.is_symlink() or not directory.resolve().is_relative_to(root):
        raise ArtifactError('Legacy run escapes project')
    value = document(directory/'run.json')
    record = json.loads(value.pop('content'))
    if not isinstance(record, dict):
        raise ArtifactError('Legacy run is not a JSON object')
    return {**value, 'record': record, 'origin': 'legacy',
            'native_v2_resume': False, 'approval_imported': False,
            'next_action': 'Legacy checkpoints require their original runtime; create a referenced successor for v2'}


def current_runs(project, state_root=None):
    project = Path(project).resolve()
    key = hashlib.sha256(str(project).encode()).hexdigest()[:16]
    root = Path(state_root or ROOT/'artifacts/glg-state')/key
    rows = []
    for database in sorted(root.glob('*/workflow.sqlite')):
        try:
            with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=ro', uri=True, timeout=.1)) as connection:
                row = connection.execute("SELECT type,checkpoint FROM checkpoints WHERE thread_id=? AND checkpoint_ns='' ORDER BY checkpoint_id DESC LIMIT 1", (database.parent.name,)).fetchone()
                if row:
                    value = JsonPlusSerializer().loads_typed(row)['channel_values']
                    rows.append({'work_id': value.get('work_id'), 'origin': 'v2', 'phase': value.get('lifecycle_phase'),
                                 'outcome': value.get('outcome'), 'brief_ref': value.get('brief_ref'), 'closure_ref': value.get('closure_ref'),
                                 'job_id': value.get('job_id'), 'native_v2_resume': True})
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
            rows.append({'work_id': database.parent.name, 'origin': 'v2', 'native_v2_resume': False,
                         'diagnostic': str(error), 'next_action': 'Inspect checkpoint and preserved evidence; no read repair performed'})
    return rows


def archives(project, query='', limit=25):
    project = Path(project).resolve()
    records = []
    current = {row['work_id']: row.get('closure_ref') for row in current_runs(project)}
    paths = [(p, 'v2') for p in (project/'.glg/work').glob('*/closures/*.json')]
    paths += [(Path(row['directory'])/'abstract.json', 'legacy') for row in legacy_runs(project)]
    for path, origin in paths:
        if not path.exists():
            continue
        try:
            item = document(path)
            value = json.loads(item.pop('content'))
            if not isinstance(value, dict):
                raise ArtifactError('Archive record is not a JSON object')
            if origin == 'v2':
                value = Artifacts(project, path.parent.parent.name).read({
                    'path': path.relative_to(project).as_posix(), 'revision': path.stem.rsplit('-', 1)[-1]})
                if value.get('kind') != 'closures':
                    raise ArtifactError('Expected a v2 closure artifact')
            if query.casefold() not in json.dumps(value, ensure_ascii=False).casefold():
                continue
            work = value.get('work_id') or (path.parent.parent.name if origin == 'v2' else path.parent.name)
            reference = current.get(work)
            records.append({**item, 'work_id': work, 'origin': origin, 'record': value,
                            'current': reference.get('path') == path.relative_to(project).as_posix() if reference and origin == 'v2' else None,
                            'verification': 'content hash verified; current only when checkpoint-referenced; acceptance separate' if origin == 'v2' else 'historical document; use archive legacy-inspect for qualified validity'})
        except (OSError, ValueError, ArtifactError) as error:
            records.append({'path': str(path), 'origin': origin, 'diagnostic': str(error)})
    return {'records': records[:limit], 'matched': len(records), 'truncated': len(records) > limit,
            'search_basis': 'bounded document inspection; legacy ranked retrieval remains separate'}


def backlog(project, path=None, query=''):
    project = Path(project).resolve()
    candidates = [Path(path) if Path(path).is_absolute() else project/path] if path else [project/p for p in ['docs/backlog.md', 'BACKLOG.md', '.flow/backlog.md', '.glg/BACKLOG.md']]
    documents = [document(p) for p in candidates if p.is_file()]
    records = archives(project, query, 100)
    return {'documents': [row for row in documents if query.casefold() in row['content'].casefold()],
            'closure_followups': [{'work_id': row.get('work_id'), 'reference': row.get('path'),
                                   'current': row.get('current'), 'verification': row.get('verification'),
                                   'acceptance': row.get('record', {}).get('payload', {}).get('acceptance', 'unknown'),
                                   'followups': row.get('record', {}).get('payload', {}).get('followups', [])}
                                  for row in records['records'] if row.get('origin') == 'v2' and 'record' in row and row.get('current') is not False],
            'closure_candidates_truncated': records['truncated'],
            'framework_gap_commands': 'flow gaps list/add/promote; explicit promotion preserves the legacy backlog rules',
            'writes': False}
