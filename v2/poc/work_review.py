"""Read-only projections over immutable records and the existing checkpoint."""
from .artifacts import ArtifactError
from .review_findings import project as project_findings


def packet(artifacts, values, summary=None):
    records = []
    diagnostics = []
    superseded = set()
    for kind in sorted(artifacts.KINDS):
        for path in sorted((artifacts.root / kind).glob('*.json')):
            ref = {'path': path.relative_to(artifacts.project).as_posix(), 'revision': path.stem.rsplit('-', 1)[-1]}
            try:
                record = artifacts.read(ref)
                records.append({'reference': ref, 'record': record})
                if record.get('supersedes'):
                    superseded.add(record['supersedes']['revision'])
            except (OSError, ValueError) as error:
                diagnostics.append({'reference': ref, 'status': 'invalid', 'error': str(error)})

    def status(ref):
        try:
            artifacts.read(ref)
            return 'superseded' if ref['revision'] in superseded else 'current'
        except FileNotFoundError:
            return 'missing'
        except (OSError, ValueError):
            return 'invalid'

    links = []
    def walk(value, source, location=''):
        if isinstance(value, dict):
            if set(value) == {'path', 'revision'}:
                links.append({'source': source, 'field': location, 'target': value, 'status': status(value)})
            else:
                for key, child in value.items():
                    walk(child, source, location+'.'+key)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, source, location+f'[{index}]')
    walk(values, 'checkpoint')
    findings = []
    timeline = []
    for row in records:
        record = row['record']; ref = row['reference']; payload = record['payload']
        row['status'] = status(ref)
        walk(record, ref)
        if record['kind'] == 'results':
            result = payload.get('result') or {}
            findings.extend({'result_ref': ref, **finding} for finding in project_findings(result.get('findings', []), artifacts, status))
            runtime = result.get('runtime') or {}
            timeline.append({'operation': record['id'], 'reference': ref, 'supersedes': record.get('supersedes'),
                             'role': runtime.get('kind') or record['id'].rsplit('-', 2)[0],
                             'state': result.get('status') or result.get('outcome') or payload.get('effect'),
                             'effect': payload.get('effect'), 'blocker': result.get('reason') or runtime.get('reason'),
                             'started': runtime.get('started'), 'finished': runtime.get('finished'),
                             'attempt_evidence': runtime.get('evidence_receipt'),
                             'sessions': [{'session_id': session.get('session_id'), 'parent_session_id': session.get('parent_session_id'), 'role': session.get('role'), 'state':'observed', 'basis':'existing runtime session lineage'} for session in runtime.get('usage', {}).get('sessions', [])],
                             'next_action': 'Historical revision; inspect successor' if row['status'] == 'superseded' else (summary or {}).get('next_action', 'Inspect current checkpoint')})
    return {'schema_version': 1, 'work_id': artifacts.work_id, 'writes': False,
            'records': records, 'references': links, 'diagnostics': diagnostics, 'findings': findings,
            'timeline': sorted(timeline, key=lambda row: (row['started'] is None, row['started'] or 0, row['operation'], row['reference']['revision'])),
            'current': {key: (summary or {}).get(key) for key in ('phase', 'delivery_phase', 'outcome', 'blocker', 'next_action', 'pending', 'next_nodes')},
            'timeline_order': 'recorded start time when available; other records ordered by operation/revision, not inferred chronology',
            'authority': 'Review projection only; records and observations grant no new approval or execution authority'}
