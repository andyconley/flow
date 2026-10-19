"""Flow v2.0 native-host entry, powered by Goose/LangGraph."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from .artifacts import ArtifactError, Artifacts, identifier, validate_brief
from .contracts import digest_tree
from .project_context import resolve
from .runtime_env import ROOT
from .work_lifecycle import build, publish_index

STAGES = {'define': 'business-analyst', 'solution': 'solution-architect', 'plan': 'lead-developer'}


class BriefChecker:
    def __init__(self, artifacts):
        self.artifacts = artifacts

    def run_state(self, state):
        command = validate_brief(self.artifacts.read(state['brief_ref'])['payload'])['check_command']
        remaining = state['deadline'] - time.time()
        if remaining <= 0:
            return {'passed': False, 'outcome': 'blocked', 'reason': 'Workflow time budget exhausted'}
        try:
            result = subprocess.run(command, cwd=state['workspace'], capture_output=True,
                                    text=True, timeout=min(60, remaining))
        except subprocess.TimeoutExpired:
            return {'passed': False, 'outcome': 'blocked', 'reason': 'Check time budget exhausted; inspect any subprocess effects before retry'}
        except OSError as error:
            if isinstance(error, PermissionError):
                raise
            return {'passed': False, 'outcome': 'scope_required',
                    'reason': f'Check configuration needs attention: {error}'}
        return {'passed': result.returncode == 0, 'exit': result.returncode,
                'stdout': result.stdout, 'stderr': result.stderr, 'command': command}


class NativeHarness:
    def __init__(self, options):
        self.options = options
        self.job = None

    def _job(self):
        if self.job is None:
            from .runtime_env import setup
            from .goose_job import GooseJob
            setup()
            self.job = GooseJob(provider=self.options['provider'], model=self.options['model'],
                                timeout=self.options['budget_seconds'], role_bundle=ROOT / 'role-bundle')
        return self.job

    def implement(self, state):
        return self._job().implement(state)

    def review(self, state):
        return self._job().review(state)

    def reconcile(self, state):
        return self._job().reconcile(state)


def storage(project, work):
    project_key = hashlib.sha256(str(project).encode()).hexdigest()[:16]
    return ROOT / 'artifacts' / 'glg-state' / project_key / identifier(work)


@contextmanager
def locked(path):
    path.mkdir(parents=True, exist_ok=True)
    with (path / 'operator.lock').open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ArtifactError('Another operator is updating this work item; inspect status and retry later')
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def read_json(path):
    return json.loads(Path(path).read_text())


def summarize(snapshot, artifacts):
    values = snapshot.values
    references = {key: values[key] for key in ('brief_ref', 'context_ref', 'approval_ref', 'closure_ref') if values.get(key)}
    problems = []
    def verify(value):
        if isinstance(value, dict) and set(value) == {'path', 'revision'}:
            try:
                artifacts.read(value)
            except (ArtifactError, OSError, ValueError) as error:
                problems.append({'reference': value, 'error': str(error)})
        elif isinstance(value, dict):
            for nested in value.values():
                verify(nested)
        elif isinstance(value, list):
            for nested in value:
                verify(nested)
    verify(values)
    def pauses(current):
        result = []
        for task in current.tasks:
            result.extend({'id': item.id, 'value': item.value} for item in task.interrupts)
            if hasattr(task.state, 'tasks'):
                result.extend(pauses(task.state))
        return result
    pending = pauses(snapshot)
    return {'work_id': values.get('work_id'), 'phase': values.get('lifecycle_phase'),
            'delivery_phase': values.get('phase'), 'outcome': values.get('outcome'),
            'references': references, 'pending': pending, 'next_nodes': list(snapshot.next),
            'recovery_problems': problems,
            'next_action': 'Inspect referenced revision problems' if problems else 'Respond to pending decision' if pending else 'Inspect blocker/closure' if not snapshot.next else 'Resume the checkpoint'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version', version='Flow 2.0.0-preview (Goose/LangGraph)')
    parser.add_argument('--project', required=True, type=Path)
    parser.add_argument('--work')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('context', help='Read project orientation and recorded work; no inference or writes')
    create = sub.add_parser('create')
    create.add_argument('--request', default='')
    create.add_argument('--brief-file', type=Path)
    create.add_argument('--provider', default='chatgpt_codex')
    create.add_argument('--model', default='gpt-5.6-sol')
    create.add_argument('--budget-seconds', type=int, default=600)
    brief = sub.add_parser('brief'); brief.add_argument('--file', required=True, type=Path)
    assign = sub.add_parser('assign'); assign.add_argument('--stage', required=True, choices=STAGES)
    assign.add_argument('--question', required=True)
    stage = sub.add_parser('stage'); stage.add_argument('--stage', required=True, choices=STAGES)
    stage.add_argument('--file', required=True, type=Path, help='Research/definition/solution/planning narrative')
    approve = sub.add_parser('approve'); approve.add_argument('--actor', required=True)
    approve.add_argument('--revision', required=True, help='Exact brief revision shown by status')
    decision = sub.add_parser('approve-stage'); decision.add_argument('--stage', required=True, choices=STAGES)
    decision.add_argument('--actor', required=True); decision.add_argument('--reason', default='')
    stop = sub.add_parser('stop'); stop.add_argument('--actor', required=True); stop.add_argument('--reason', default='')
    accept = sub.add_parser('accept'); accept.add_argument('--actor', required=True)
    accept.add_argument('--revision', required=True, help='Exact closure revision shown by status')
    resume = sub.add_parser('resume'); resume.add_argument('--decision-file', type=Path)
    sub.add_parser('status')
    sub.add_parser('index')
    args = parser.parse_args(argv)
    project = args.project.resolve()
    if not project.is_dir():
        parser.error('Project workspace must already exist')
    if args.command == 'context':
        items = []
        for directory in sorted(storage(project, 'orientation').parent.glob('*')):
            database = directory / 'workflow.sqlite'
            if not database.is_file():
                continue
            # Read-only SQLite connection avoids creating a missing workflow.
            import sqlite3
            with sqlite3.connect(database.as_uri()+'?mode=ro', uri=True) as connection:
                saver = SqliteSaver(connection)
                checkpoint = saver.get({'configurable': {'thread_id': directory.name}})
                if checkpoint:
                    values = checkpoint['channel_values']
                    items.append({'work_id': directory.name, 'phase': values.get('lifecycle_phase'),
                                  'outcome': values.get('outcome'), 'brief_ref': values.get('brief_ref'),
                                  'closure_ref': values.get('closure_ref')})
        print(json.dumps({'product': 'Flow v2.0', 'context': resolve(project), 'work': items}, indent=2))
        return
    if not args.work:
        parser.error('--work is required for work-item commands')
    try:
        artifacts = Artifacts(project, args.work)
        state_dir = storage(project, args.work)
        if args.command == 'index':
            records = []
            for path in (project / '.glg' / 'work').glob('*'):
                if path.is_dir():
                    record_store = Artifacts(project, path.name)
                    ref, record = record_store.leaf('closures', 'closure')
                    if record:
                        records.append((path.name, ref, record))
            publish_index(project, records)
            print(json.dumps({'index': str(project / '.glg' / 'INDEX.md'), 'closed_records': len(records)}))
            return
        if args.command != 'create' and not (state_dir / 'workflow.sqlite').exists():
            parser.error('No checkpoint exists for this project/work item')
        with locked(state_dir), SqliteSaver.from_conn_string(str(state_dir / 'workflow.sqlite')) as saver:
            config = {'configurable': {'thread_id': args.work}, 'recursion_limit': 100}
            checkpoint = saver.get(config)
            old = checkpoint['channel_values'] if checkpoint else {}
            if args.command == 'create':
                if old:
                    parser.error('Work item already exists; inspect status or resume it')
                if args.budget_seconds <= 0 or not (args.request or args.brief_file):
                    parser.error('Provide a request/brief and a positive budget')
                options = {'provider': args.provider, 'model': args.model, 'budget_seconds': args.budget_seconds}
            else:
                options = old['runtime_options']
            graph = build(artifacts, NativeHarness(options), BriefChecker(artifacts)).compile(checkpointer=saver)
            saved = graph.get_state(config, subgraphs=True)
            if args.command == 'status':
                print(json.dumps(summarize(saved, artifacts), indent=2, default=str))
                return
            if args.command == 'create':
                context_ref = artifacts.publish('contexts', 'project', resolve(project))
                initial = {'work_id': args.work, 'workspace': str(project), 'request': args.request,
                           'job_id': hashlib.sha256(str(project).encode()).hexdigest()[:16] + '-' + args.work,
                           'context_ref': context_ref, 'runtime_options': options,
                           'budget_seconds': args.budget_seconds, 'lifecycle_phase': 'shaping'}
                if args.brief_file:
                    initial['brief_ref'] = artifacts.publish('briefs', 'brief', validate_brief(read_json(args.brief_file)))
                graph.invoke(initial, config)
            elif args.command == 'resume':
                decision = read_json(args.decision_file) if args.decision_file else None
                if isinstance(decision, dict) and decision.get('action') == 'retry-review':
                    if old.get('lifecycle_phase') != 'closed' or old.get('phase') != 'blocked' or not old.get('review'):
                        parser.error('retry-review requires a closed blocked review')
                    if not decision.get('actor') or not decision.get('reason'):
                        parser.error('retry-review requires actor and reason')
                    if old.get('candidate') != digest_tree(project):
                        parser.error('Candidate changed; use a separately approved successor work item')
                    if old['deadline'] <= time.time():
                        parser.error('Original delivery budget exhausted; no retry started')
                    decisions = old.get('decision_refs', [])
                    ref = artifacts.publish('decisions', f'decision-{len(decisions)+1:04d}',
                                            {**decision, 'target_ref': old['closure_ref'],
                                             'brief_ref': old['brief_ref'], 'authority': 'Recheck unchanged candidate; no implementation'})
                    # LangGraph re-enters the existing delivery subgraph. Its
                    # authorize node routes candidate_reused directly to checks.
                    graph.update_state(config, {'candidate_reused': True, 'lifecycle_phase': 'delivery',
                                                'decision_refs': [*decisions, ref],
                                                'resume_epoch': old.get('resume_epoch', 0)+1}, as_node='prepare')
                    graph.invoke(None, config)
                else:
                    graph.invoke(Command(resume=decision) if args.decision_file else None, config)
            elif args.command == 'accept':
                if old.get('lifecycle_phase') != 'closed' or old.get('phase') != 'reviewed-and-ready' or old.get('acceptance') == 'accepted':
                    parser.error('Acceptance applies once to closed, reviewed-and-ready work')
                if args.revision != old['closure_ref']['revision']:
                    parser.error('Acceptance must reference the exact current closure revision')
                decisions = old.get('decision_refs', [])
                ref = artifacts.publish('decisions', f'decision-{len(decisions)+1:04d}',
                                        {'action': 'accept', 'actor': args.actor, 'target_ref': old['closure_ref']})
                graph.update_state(config, {'acceptance': 'accepted', 'decision_refs': [*decisions, ref]}, as_node='delivery')
                graph.invoke(None, config)
            else:
                if saved.values.get('lifecycle_phase') not in {'shaping', 'awaiting-approval'} or not saved.next:
                    parser.error('Shaping commands apply only before implementation approval; start a successor work item for changed scope')
                if args.command == 'brief':
                    ref = artifacts.publish('briefs', 'brief', validate_brief(read_json(args.file)), supersedes=old.get('brief_ref'))
                    response = {'action': 'brief', 'brief_ref': ref}
                elif args.command == 'assign':
                    payload = {'stage': args.stage, 'question': args.question, 'context_ref': old['context_ref'],
                               'brief_ref': old.get('brief_ref'), 'role': STAGES[args.stage],
                               'recipe': str(ROOT / 'workflow-recipes' / f'{args.stage}.yaml'),
                               'role_recipe': str(ROOT / 'role-bundle' / 'recipes' / f'{STAGES[args.stage]}.yaml'),
                               'authority': 'Research/shaping only; preserve existing external-action permissions. No implementation authority.'}
                    ref = artifacts.publish('assignments', args.stage, payload, supersedes=old.get('shaping_assignment_refs', {}).get(args.stage))
                    response = {'action': 'assign', 'assignment_ref': ref}
                elif args.command == 'stage':
                    ref = artifacts.publish('shaping', args.stage, {'stage': args.stage, 'content': args.file.read_text(),
                                            'assignment_ref': old.get('shaping_assignment_refs', {}).get(args.stage),
                                            'context_ref': old['context_ref'], 'brief_ref': old.get('brief_ref')},
                                            supersedes=old.get('shaping_refs', {}).get(args.stage))
                    response = {'action': 'stage', 'shaping_ref': ref}
                elif args.command == 'approve':
                    if not old.get('brief_ref') or args.revision != old['brief_ref']['revision']:
                        parser.error('Approval revision must match the exact currently proposed brief')
                    response = {'action': 'approve', 'actor': args.actor, 'brief_ref': old['brief_ref']}
                else:
                    response = {'action': args.command, 'actor': args.actor, 'reason': args.reason}
                    if args.command == 'approve-stage':
                        response['stage'] = args.stage
                graph.invoke(Command(resume=response), config)
            print(json.dumps(summarize(graph.get_state(config, subgraphs=True), artifacts), indent=2, default=str))
    except (ArtifactError, OSError, ValueError, KeyError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
