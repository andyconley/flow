"""Normal read/report commands around the existing engine, never another dispatcher."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from .artifacts import ArtifactError
from .runtime_env import ROOT
from . import history, monitoring

COMPAT = {'cost', 'harvest', 'normalize', 'plugin-usage', 'gaps', 'model'}
COMMANDS = COMPAT | {'metrics', 'runs', 'run', 'archive', 'backlog', 'projects'}

BRIDGE = '''
import sys,runpy
from pathlib import Path
root,project=Path(sys.argv[1]),Path(sys.argv[2])
arguments=sys.argv[3:]
sys.path.append(str(root/'cli'))
import paths,fsutil
if not arguments or arguments[0]!='gaps':
    paths.SOURCE_DIR=root
    paths.SCAFFOLD_DIR=root/'scaffolds/default'
fsutil.repo_root=lambda: project
if arguments and arguments[0]=='cost':
    print('Native/legacy transcript history; Goose observations are available via flow metrics. Do not sum overlapping sources.',file=sys.stderr)
sys.argv=[str(root/'cli/flow.py'),*arguments]
runpy.run_path(str(root/'cli/flow.py'),run_name='__main__')
'''


def legacy_command(project, arguments):
    script = ROOT.parent/'cli/flow.py'
    if not script.is_file():
        raise ArtifactError('Legacy read/report modules require the full canonical Flow checkout')
    return subprocess.run([sys.executable, '-I', '-c', BRIDGE, str(ROOT.parent), str(project), *arguments], cwd=project).returncode


def dispatch(argv):
    """Accept the same global --project/--work prefix as workflow commands."""
    tokens = list(argv)
    project, work, index = Path.cwd(), None, 0
    while index < len(tokens):
        name = tokens[index]
        if name in {'--project', '--work'} and index+1 < len(tokens):
            if name == '--project':
                project = Path(tokens[index+1])
            else:
                work = tokens[index+1]
            index += 2
        elif name.startswith('--project='):
            project = Path(name.split('=', 1)[1]); index += 1
        elif name.startswith('--work='):
            work = name.split('=', 1)[1]; index += 1
        else:
            break
    if index >= len(tokens) or tokens[index] not in COMMANDS:
        return None
    command, arguments = tokens[index], tokens[index+1:]
    project = project.resolve()
    parser = argparse.ArgumentParser(prog='flow '+command)
    parser.add_argument('--json', action='store_true', help='Canonical JSON is already the default for these views')
    try:
        if not project.is_dir():
            raise ArtifactError('Project directory must exist')
        if command in COMPAT:
            # Reporting/harvesting and explicit gap operations only. No workflow,
            # provider execution, global setup or legacy installer is reachable.
            return legacy_command(project, [command, *arguments])
        if command == 'run':
            if not arguments or arguments[0] not in {'list', 'status', 'history'}:
                parser.error('Legacy run access is read-only: list/status/history; use create --legacy-run for a v2 handoff')
            if work and len(arguments) == 1 and arguments[0] in {'status', 'history'}:
                arguments = [*arguments, work]
            return legacy_command(project, ['run', *arguments])
        if command == 'metrics':
            parser.add_argument('view', nargs='?', choices=['summary', 'sessions', 'context'], default='summary')
            parser.add_argument('--all', action='store_true', help='Read all Goose sessions, not only this workspace')
            parser.add_argument('--model', help='Resolve a specific configured local model context')
            parser.add_argument('--limit', type=int, default=25, help='Bound session details; totals still cover the selected scope')
            args = parser.parse_args(arguments)
            if not 1 <= args.limit <= 1000:
                parser.error('--limit must be 1..1000')
            scope = None if args.all else project
            job = hashlib.sha256(str(project).encode()).hexdigest()[:16]+'-'+work if work else None
            if work:
                stored = next((row for row in history.current_runs(project) if row.get('work_id') == work), {})
                job = stored.get('job_id') or job
            observed = monitoring.report(scope, job_id=job)
            value = monitoring.context_for_usage(project, observed, args.model) if args.view == 'context' else observed
            if args.view == 'summary':
                value.pop('sessions', None)
            else:
                key = 'observations' if args.view == 'context' else 'sessions'
                value['details_truncated'] = len(value[key]) > args.limit
                value[key] = value[key][:args.limit]
        elif command == 'runs':
            parser.add_argument('--current-only', action='store_true', help='Exclude ancestor legacy overlays')
            args = parser.parse_args(arguments)
            value = {'current': history.current_runs(project), 'legacy': history.legacy_runs(project, not args.current_only),
                     'legacy_resume': 'Original runtime only, or create --legacy-run ID with a new v2 work ID and approval'}
        elif command == 'archive':
            if arguments and arguments[0] in {'legacy-search', 'legacy-inspect', 'import-preview'}:
                action = {'legacy-search': ['archive', 'search'], 'legacy-inspect': ['archive', 'inspect'],
                          'import-preview': ['archive', 'import', 'preview']}[arguments[0]]
                return legacy_command(project, [*action, *arguments[1:]])
            parser.add_argument('action', nargs='?', choices=['list', 'search'], default='list')
            parser.add_argument('query', nargs='?', default='')
            parser.add_argument('--limit', type=int, default=25)
            parser.add_argument('--max-output-bytes', type=int, default=32768, help='Bound the read view, not model usage')
            args = parser.parse_args(arguments)
            if not 1 <= args.limit <= 100:
                parser.error('--limit must be 1..100')
            if not 1024 <= args.max_output_bytes <= 1048576:
                parser.error('--max-output-bytes must be 1024..1048576')
            value = history.archives(project, args.query, args.limit)
            for row in value['records']:
                if len(json.dumps(row).encode()) > args.max_output_bytes//2:
                    row.pop('record', None)
                    row['content_omitted'] = 'Large original retained at path; inspect it directly or use qualified legacy inspection'
            while value['records'] and len(json.dumps(value, indent=2).encode()) > args.max_output_bytes:
                value['records'].pop(); value['truncated'] = True
        elif command == 'backlog':
            parser.add_argument('action', nargs='?', choices=['list'], default='list')
            parser.add_argument('--file', type=Path, help='Read an explicitly chosen existing backlog')
            parser.add_argument('--query', default='')
            args = parser.parse_args(arguments)
            value = history.backlog(project, args.file, args.query)
        else:
            parser.add_argument('--file', type=Path, help='Read an existing project registry; no automatic migration')
            args = parser.parse_args(arguments)
            if args.file:
                path = args.file if args.file.is_absolute() else project/args.file
                value = {'registry': history.document(path.resolve()), 'writes': False}
            else:
                candidates = [Path.home()/'.flow/projects.json', Path.home()/'.flow/project-registry.json',
                              project/'.flow/projects.json', project/'.glg/projects.json']
                value = {'registries': [history.document(path) for path in candidates if path.is_file()],
                         'writes': False, 'note': 'No universal legacy Flow registry contract; use --file for your existing registry. Native app projects remain app-owned.'}
        print(json.dumps(value, indent=2, default=str))
        return 0
    except (ArtifactError, OSError, ValueError, KeyError) as error:
        parser.error(str(error))
