"""Read observed Goose usage without inventing billing, attribution or occupancy."""
import sqlite3
from pathlib import Path
from .runtime_env import ROOT
from .device_context import settings

FIELDS = ('input_tokens', 'output_tokens', 'total_tokens', 'cache_read_tokens', 'cache_write_tokens')


def _observed(values):
    values = [v for v in values if type(v) in (int, float) and v >= 0]
    return sum(values) if values else None


def report(project=None, job_id=None, database=None, session_name=None):
    database = Path(database or ROOT/'runtime/goose-home/data/sessions/sessions.db')
    result = {'source': 'goose_sqlite', 'available': False, 'sessions': [], 'totals': {},
              'scope': {'project': str(Path(project).resolve()) if project else None, 'job_id': job_id, 'session_name': session_name},
              'actual_billed_cost': None, 'notes': [
                  'Provider usage can be absent or partial; null is not zero.',
                  'Model names come from session configuration and may be native aliases; ledger model names are retained separately.',
                  'Reported/estimated costs are not subscription bills.',
                  'Native transcript history can overlap Goose; do not add the two totals blindly.']}
    if not database.is_file():
        result['notes'].append('No Goose session database exists yet')
        return result
    connection = None
    try:
        connection = sqlite3.connect(database.resolve().as_uri()+'?mode=ro', uri=True, timeout=.1)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only=ON')
        connection.execute('BEGIN')
        columns = {r[1] for r in connection.execute('PRAGMA table_info(sessions)')}
        wanted = ['id', 'name', 'parent_session_id', 'working_dir', 'provider_name', 'updated_at', 'accumulated_cost',
                  *FIELDS, *('accumulated_'+field for field in FIELDS)]
        projection = ','.join('"'+name+'"' for name in wanted if name in columns)
        metadata = []
        for column, key, alias in [('recipe_json','title','recipe_title'), ('model_config_json','model_name','configured_model')]:
            metadata.append(f"CASE WHEN json_valid({column}) THEN json_extract({column}, '$.{key}') END AS {alias}" if column in columns else 'NULL AS '+alias)
        try:
            selected_rows = connection.execute('SELECT '+projection+','+','.join(metadata)+' FROM sessions').fetchall()
        except sqlite3.OperationalError:
            # Token reporting still works on a SQLite build without JSON1.
            selected_rows = connection.execute('SELECT '+projection+',NULL AS recipe_title,NULL AS configured_model FROM sessions').fetchall()
            result['notes'].append('Recipe/model metadata unavailable; token observations retained')
        rows = {r['id']: dict(r) for r in selected_rows}
        def workspace_matches(row):
            return project is None or bool(row.get('working_dir')) and Path(row['working_dir']).resolve() == Path(project).resolve()
        if session_name:
            selected = {key for key, row in rows.items() if row.get('name') == session_name
                        and workspace_matches(row)}
        elif job_id:
            selected = {key for key, row in rows.items() if (row.get('name') or '').startswith(job_id+'-')
                        and workspace_matches(row)}
        else:
            selected = {key for key, row in rows.items() if workspace_matches(row)}
        # Each physical session is included once, even when both parent and child match.
        while True:
            children = {key for key, row in rows.items() if row.get('parent_session_id') in selected}
            if children <= selected:
                break
            selected |= children
        try:
            ledger = []
            identities = sorted(selected)
            for offset in range(0, len(identities), 500):
                chunk = identities[offset:offset+500]
                query = 'SELECT * FROM usage_ledger WHERE session_id IN ('+','.join('?' for _ in chunk)+')'
                ledger.extend(dict(row) for row in connection.execute(query, chunk))
        except sqlite3.OperationalError:
            ledger = []
            result['notes'].append('This database has no per-call ledger; cumulative snapshots only')
        known_roles = {p.stem for p in (ROOT/'role-bundle/recipes').glob('*.yaml')}
        for key in sorted(selected):
            row = rows[key]
            calls = [entry for entry in ledger if entry['session_id'] == key]
            title = row.get('recipe_title')
            role = title if title in known_roles else 'implementation-coordinator' if (job_id or session_name) and not row.get('parent_session_id') else None
            usage = {}
            for field in FIELDS:
                accumulated = row.get('accumulated_'+field)
                per_call = _observed([entry.get(field) for entry in calls])
                values = [v for v in (accumulated, per_call) if type(v) is int and v >= 0]
                usage[field] = max(values) if values else None
            costs = [v for v in (row.get('accumulated_cost'), _observed([entry.get('cost') for entry in calls]))
                     if type(v) in (int, float) and v >= 0]
            result['sessions'].append({'session_id': key, 'parent_session_id': row.get('parent_session_id'),
                'name': row.get('name'), 'role': role, 'role_basis': 'recipe title' if title in known_roles else 'recorded job boundary' if role else 'unavailable',
                'updated_at': row.get('updated_at'),
                'provider': row.get('provider_name'), 'model': row.get('configured_model'),
                'model_basis': 'session configuration; may be a native alias',
                'ledger_models': sorted({entry['model'] for entry in calls if entry.get('model')}),
                'usage': usage, 'reported_cost': max(costs) if costs else None,
                'cost_sources': sorted({entry['cost_source'] for entry in calls if entry.get('cost_source')}),
                'actual_billed_cost': None, 'ledger_calls': len(calls) if calls else None,
                'goose_compactions': sum(bool(entry.get('is_compaction')) for entry in calls) if calls else None,
                'last_request_tokens': {name: row.get(name) for name in FIELDS[:3]},
                'native_context_occupancy': None})
        result['available'] = True
        result['totals'] = {field: _observed([row['usage'][field] for row in result['sessions']]) for field in FIELDS}
        result['coverage'] = {'sessions': len(selected), **{
            'missing_'+field: sum(row['usage'][field] is None for row in result['sessions']) for field in FIELDS}}
        result['reported_cost'] = _observed([row['reported_cost'] for row in result['sessions']])
        result['groups'] = []
        keys = {(row['role'], row['provider'], row['model']) for row in result['sessions']}
        for role, provider, model in sorted(keys, key=str):
            group = [row for row in result['sessions'] if (row['role'], row['provider'], row['model']) == (role, provider, model)]
            result['groups'].append({'role': role, 'provider': provider, 'model': model, 'sessions': len(group),
                'usage': {field: _observed([row['usage'][field] for row in group]) for field in FIELDS},
                'reported_cost': _observed([row['reported_cost'] for row in group]),
                'actual_billed_cost': None,
                'cost_sources': sorted({source for row in group for source in row['cost_sources']}),
                'partial': any(any(row['usage'][field] is None for field in FIELDS) for row in group)})
    except (OSError, ValueError, TypeError, KeyError, IndexError, sqlite3.Error) as error:
        result['notes'].append('Usage unavailable: '+str(error))
    finally:
        if connection:
            connection.close()
    return result


def context_report(project=None, model=None, database=None, job_id=None):
    usage = report(project, job_id=job_id, database=database)
    return context_for_usage(project, usage, model)


def context_for_usage(project, usage, model=None, configuration=None):
    configuration = configuration if configuration is not None else settings(project, model)
    observed = []
    for session in usage.get('sessions', []):
        count = session['last_request_tokens']['total_tokens']
        window = configuration['context_tokens'] if session['provider'] == 'ollama' else None
        percent = 100*count/window if window and type(count) is int else None
        observed.append({'session_id': session['session_id'], 'provider': session['provider'],
                         'model': session.get('model'), 'updated_at': session.get('updated_at'),
                         'context_window': window, 'last_request_tokens': count,
                         'last_reported_request_percent': percent,
                         'basis': 'last reported request vs declared local window; not live/historical occupancy' if percent is not None else 'native/provider occupancy unavailable',
                         'warning': 'Last request approached declared window; if continuing, inspect/compact through its owning harness' if percent is not None and percent >= 80 else None})
    return {'configuration': configuration, 'observations': observed, 'informational_only': True}


def attach(record, workspace, name):
    """Metric failure must never change task outcome or authorize/refuse execution."""
    try:
        record['usage'] = report(workspace, session_name=name)
        record['goose_session_ids'] = [row['session_id'] for row in record['usage']['sessions']]
    except Exception as error:
        record['usage'] = {'available': False, 'notes': ['Observation failed: '+str(error)]}
    return record
