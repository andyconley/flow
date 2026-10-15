"""Review output contracts; SDK completion is not approval or equivalence."""
from datetime import timedelta
from uuid import uuid4
import re
import verification as v

CHECK_ID = 'review-output'


def field(body, name, choices):
    values = re.findall(r'(?im)^\s*(?:#+\s*)?(?:\*\*)?' + name + r'\s*[:*_\s]+(' + '|'.join(choices) + r')\b', body)
    return values[0].upper() if len(values) == 1 else None


def current(root, run, result):
    path = v.regular(root, result['evidence']['path'], run_dir=root / '.flow/runs' / run['work_id'])
    if (v.file_sha(path) != result['evidence']['sha256'] or result['workspace'] != v.workspace(root)
            or result['approved'] != v.bindings(run)):
        raise ValueError('review output is stale or altered; independent review must be repeated')
    return path


def begin(root, run, session_id, *, continuing=False):
    history = run.setdefault('review_outputs', [])
    previous = history[-1] if history else None
    if continuing and previous and previous['session_id'] == session_id:
        if v.parse_time(v.stamp()) >= v.parse_time(previous['deadline']):
            raise ValueError('review deadline exhausted; block and escalate to the user')
        return previous, previous.get('before')
    if previous and previous['status'] == 'incomplete' and not any(
            a['check_id'] == CHECK_ID and a['after_record'] == previous['id'] for a in run.get('repair_attempts', [])):
        raise ValueError('incomplete review requires bounded repair allocation; exhausted budgets must escalate')
    now = v.stamp()
    deadline = history[0]['deadline'] if history else (v.parse_time(now) + timedelta(seconds=1800)).isoformat()
    if v.parse_time(now) >= v.parse_time(deadline):
        raise ValueError('review deadline exhausted; block and escalate to the user')
    path = root / '.flow/runs' / run['work_id'] / 'review.md'
    before = (v.file_sha(path), path.stat().st_mtime_ns) if path.is_file() and not path.is_symlink() else None
    result = {'id': uuid4().hex, 'status': 'incomplete', 'reason': 'review execution has not supplied a complete output',
              'session_id': session_id, 'started_at': now, 'deadline': deadline,
              'workspace': v.workspace(root), 'approved': v.bindings(run),
              'evidence': {'path': path.relative_to(root).as_posix(), 'sha256': None}}
    result['before'] = list(before) if before else None
    history.append(result)
    return result, before


def finish(root, run, result, before):
    try:
        path = v.regular(root, result['evidence']['path'], run_dir=root / '.flow/runs' / run['work_id'])
        body = path.read_text()
        if before is not None and tuple(before) == (v.file_sha(path), path.stat().st_mtime_ns):
            raise ValueError('review artifact was not produced by this execution')
        verdict = field(body, 'Verdict', ['ACCEPT', 'REJECT'])
        if not verdict:
            raise ValueError('review artifact needs exactly one explicit Verdict: ACCEPT or REJECT')
        rationale = re.sub(r'(?im)^\s*(?:#+\s*)?(?:\*\*)?(?:Verdict|Test equivalence)\s*:.*$', '', body).strip()
        if not rationale:
            raise ValueError('review artifact needs a rationale beyond disposition labels')
        equivalence = field(body, 'Test equivalence', ['EQUIVALENT', 'MATERIAL', 'UNCERTAIN'])
        inputs = v.registered(root, v.load_plan(root, run))
        if inputs != run['evaluation_baseline'] and not equivalence:
            raise ValueError('changed evaluation inputs require an explicit Test equivalence disposition')
        if v.parse_time(v.stamp()) >= v.parse_time(result['deadline']):
            raise ValueError('review deadline exhausted')
        result['evidence']['sha256'] = v.file_sha(path)
        current(root, run, result)
        result.update(status='complete', verdict=verdict, test_equivalence=equivalence, reason=None)
    except (ValueError, OSError) as exc:
        result['reason'] = str(exc)
    result['finished_at'] = v.stamp()
    return result


def validate_approval(root, run):
    if run.get('review_outputs'):
        result = run['review_outputs'][-1]
        if result['status'] != 'complete' or result.get('verdict') != 'ACCEPT':
            raise ValueError('review is incomplete or rejected; approval is not permitted')
        current(root, run, result)
