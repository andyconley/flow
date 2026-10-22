"""Flow v2.0 native-host entry, powered by Goose/LangGraph."""
import argparse
from contextlib import closing, contextmanager, ExitStack
import fcntl
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import time
import sys
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from .artifacts import ArtifactError, Artifacts, identifier, validate_brief
from .contracts import digest_tree
from .recovery import PAUSE_POLICY, approve_recovery, require_resume_budget, delivery_state, validate_candidate_recovery, review_delivery_recoverable
from .project_context import resolve
from .runtime_env import ROOT
from .work_lifecycle import build, publish_index

STAGES = {'define': 'business-analyst', 'solution': 'solution-architect', 'plan': 'lead-developer'}


class BriefChecker:
    def __init__(self, artifacts):
        self.artifacts = artifacts

    def run_state(self, state):
        from .verification import preflight, evidence
        brief = validate_brief(self.artifacts.read(state['brief_ref'])['payload'])
        readiness = preflight(state['workspace'], brief)
        def finish(result):
            return evidence(brief, state['workspace'], state['brief_ref'], {**result, 'environment': readiness})
        if not readiness['ready']:
            return finish({'passed': False, 'outcome': 'scope_required', 'reason': '; '.join(readiness['errors'])+'; '+readiness['instruction']})
        remaining = state['deadline'] - time.time()
        if remaining <= 0:
            return finish({'passed': False, 'outcome': 'timeout', 'reason': 'Workflow time budget exhausted'})
        command = readiness['command']
        try:
            result = subprocess.run(command, cwd=state['workspace'], capture_output=True,
                                    text=True, timeout=remaining)
        except subprocess.TimeoutExpired:
            return finish({'passed': False, 'outcome': 'timeout', 'reason': 'Check timed out; inspect subprocess effects before retry'})
        except (OSError, ValueError) as error:
            if isinstance(error, PermissionError): raise
            return finish({'passed': False, 'outcome': 'scope_required', 'reason': str(error)})
        return finish({'passed': result.returncode == 0, 'exit': result.returncode,
                'stdout': result.stdout, 'stderr': result.stderr, 'command': command})


class NativeHarness:
    def __init__(self, options):
        self.options = options
        self.job = None

    def _job(self, state=None):
        if self.job is None:
            from .runtime_env import setup
            from .goose_job import GooseJob
            setup()
            self.job = GooseJob(provider=self.options['provider'], model=self.options['model'],
                                timeout=self.options['budget_seconds'], role_bundle=ROOT / 'role-bundle',
                                implementation_profile=self.options.get('implementation_profile'))
        if state is not None:
            self.job.timeout=state.get('budget_seconds', self.options['budget_seconds'])
        return self.job

    def implement(self, state):
        return self._job(state).implement(state)

    def review(self, state):
        return self._job(state).review(state)

    def shape(self,state,stage,assignment):
        return self._job(state).shape(state,stage,assignment)

    def reconcile(self, state):
        return self._job(state).reconcile(state)


def storage(project, work):
    project = Path(project).resolve()
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


@contextmanager
def checkpoint_snapshot(path):
    """Copy a consistent committed SQLite view; graph setup writes only to memory."""
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True, timeout=.25)) as source:
        with closing(sqlite3.connect(':memory:', check_same_thread=False)) as memory:
            source.backup(memory)
            yield SqliteSaver(memory)


def operator_active(path):
    lock = path/'operator.lock'
    if not lock.exists():
        return False
    with lock.open('r') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(stream, fcntl.LOCK_UN)
    return False


def read_json(path):
    return json.loads(Path(path).read_text())


def summarize(snapshot, artifacts):
    from .recovery import budget_status, delivery_state
    values = {**snapshot.values, **delivery_state(snapshot)}
    budget = budget_status(values)
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
    pending = []
    observed = {}
    for item in pauses(snapshot):
        encoded = json.dumps(item['value'], sort_keys=True, default=str)
        variants = observed.setdefault(item['id'], set())
        if encoded in variants:
            continue
        if variants:
            problems.append({'interrupt_id': item['id'],
                             'error': 'Conflicting pending decisions share an interrupt ID; inspect checkpoint before responding'})
        variants.add(encoded)
        value = item['value'] if isinstance(item['value'], dict) else {}
        kind = value.get('kind')
        if kind in {'permission_required', 'scope_required'}:
            item['decision_options'] = [{'actor': '<actor>', 'action': 'resume', 'reason': '<resolved blocker evidence>'},
                                        {'actor': '<actor>', 'action': 'stop', 'reason': '<why stopped>'}]
            item['instruction'] = 'Resolve the reported blocker, inspect remaining budget, then explicitly resume the same scope or stop.'
            if budget['expired']:
                item['decision_options'] = [item['decision_options'][1]]
                item['instruction'] = 'Approved budget expired; resume is rejected. Stop and create a separately approved successor, preserving this evidence.'
        elif kind == 'reconcile-effect':
            item['decision_options'] = [{'actor': '<actor>', 'effect': 'not_started', 'evidence': '<observed evidence>'},
                                        {'actor': '<actor>', 'effect': 'completed', 'evidence': '<observed evidence>',
                                         'result': '<actual structured result>'}]
            item['instruction'] = 'Inspect the actual operation before deciding; never infer that an uncertain invocation did not execute.'
        if item.get('decision_options'):
            import shlex
            item['command'] = shlex.join(['flow', '--project', str(artifacts.project), '--work', str(values.get('work_id')),
                                         'resume', '--decision-file', 'DECISION.json'])
        pending.append(item)
    launch_context = []
    operations = {}
    for operation, reference in values.get('result_refs', {}).items():
        try:
            record = artifacts.read(reference)
            payload = record['payload']
            result = payload.get('result') or {}
            runtime = result.get('runtime', {})
            if isinstance(runtime, dict) and isinstance(runtime.get('context_configuration'), dict):
                launch_context.append({'operation': operation, 'result_ref': reference,
                                       'configuration': runtime['context_configuration'],
                                       'session_ids': runtime.get('goose_session_ids', [])})
            if not payload.get('assignment_ref'):
                continue  # Older observational records may predate controlled assignments.
            assignment = artifacts.read(payload['assignment_ref'])
            operation_id = assignment['payload'].get('operation_id', assignment['id'])
            history = [{'reference': ref, 'effect': revision['payload'].get('effect'),
                        'supersedes': revision.get('supersedes')}
                       for ref, revision in artifacts.revisions('results', record['id'])]
            operations[operation_id] = {'operation_id': operation_id, 'kind': assignment['payload'].get('kind'),
                               'assignment_ref': payload['assignment_ref'], 'result_ref': reference,
                               'effect': payload.get('effect'), 'result': payload.get('result'),
                               'records': history,
                               'interpretation': 'Intent and outcome records describe one operation boundary; record count is not an execution count. Early rejection may submit no native execution.'}
        except (ArtifactError, OSError, ValueError, KeyError, TypeError, AttributeError):
            pass  # Reference diagnostics above remain visible; observations grant no authority.
    from .monitoring import report, context_report
    stage = values.get('resume_stage')
    detail = values.get('review') if stage == 'review' else values.get('check') if stage == 'check' else values.get('result')
    reason = values.get('failure') or (detail.get('reason') if isinstance(detail, dict) else None)
    intentional = values.get('outcome') in {'stopped', 'replaced'} or values.get('lifecycle_phase') == 'stopped'
    blocked = values.get('phase') in {'blocked', 'permission_required', 'scope_required'} and not intentional
    recovery = None
    if not problems and review_delivery_recoverable(values) and values.get('candidate'):
        import shlex
        recovery = {'decision': {'action': 'recover-review', 'actor': '<actor>', 'reason': '<why a new review is warranted>',
                                 'closure_ref': values.get('closure_ref'), 'brief_ref': values.get('brief_ref'),
                                 'candidate_revision': values['candidate'], 'budget_seconds': 600},
                    'instruction': 'Inspect the exact candidate and evidence; choose an explicit new budget (1–86400 seconds) before approving. Recovery permits independent checks and fresh review only.',
                    'command': shlex.join(['flow', '--project', str(artifacts.project), '--work', str(values.get('work_id')),
                                           'resume', '--decision-file', 'DECISION.json'])}
    return {'work_id': values.get('work_id'),
            'implementation_profile':values.get('runtime_options',{}).get('implementation_profile'), 'phase': values.get('lifecycle_phase'),
            'delivery_phase': values.get('phase'), 'outcome': work_outcome(values, pending),
            'termination': 'intentional-stop' if intentional else 'blocked' if blocked else None,
            'blocker': {'stage': stage, 'reason': reason, 'result': detail} if blocked else None,
            'budget': budget, 'recover_review': recovery,
            'references': references, 'pending': pending, 'next_nodes': list(snapshot.next),
            'recovery_problems': problems,
            'usage': report(artifacts.project, job_id=values.get('job_id')),
            'context_monitoring': context_report(artifacts.project, job_id=values.get('job_id')),
            'launch_context': launch_context, 'operations': list(operations.values()),
            'stage_assignments':values.get('shaping_assignment_refs',{}),'stage_results':values.get('shaping_refs',{}),
            'stage_outcome':values.get('stage_result'),
            'next_action': 'Inspect referenced revision problems' if problems else 'Inspect candidate and approve recover_review with an explicit new budget' if recovery else 'Budget expired; resume is rejected. Stop or create a separately approved successor' if pending and budget['expired'] else 'Respond to pending decision' if pending else 'Inspect blocker/closure' if not snapshot.next else 'Resume the checkpoint'}


def work_outcome(values, pending):
    kinds = {p['value'].get('kind') for p in pending}
    if 'reconcile-effect' in kinds: return 'uncertain'
    if 'repair-brief' in kinds: return 'brief-invalid'
    if values.get('lifecycle_phase') == 'stopped': return 'stopped'
    if values.get('outcome'): return values['outcome']
    stage = values.get('stage_result', {}).get('status')
    if stage and stage != 'completed': return stage
    if pending: return 'awaiting-approval'
    if values.get('shaping_refs'): return 'research-complete'
    return None


def outcome_exit(summary):
    """Zero means successful command handling, never implicit work completion."""
    kinds = {row.get('value', {}).get('kind') for row in summary.get('pending', [])}
    if 'reconcile-effect' in kinds: return 3
    if 'repair-brief' in kinds: return 2
    if summary.get('outcome') in {'timeout', 'uncertain', 'failed', 'blocked', 'scope_required', 'permission_required', 'stopped'}: return 2
    return 0


def main(argv=None):
    from .utilities import dispatch
    utility = dispatch(sys.argv[1:] if argv is None else argv)
    if utility is not None:
        return utility
    parser = argparse.ArgumentParser(description=__doc__, epilog='Installation identity (no work ID): flow installation status --json. Reports/discovery: metrics, cost, harvest, normalize, runs, run, archive, backlog, gaps, projects, model. These also support the --project prefix.')
    parser.add_argument('--version', action='version', version='Flow 2.0.0 (Goose/LangGraph)')
    parser.add_argument('--project', required=True, type=Path)
    parser.add_argument('--work')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('context', help='Read project orientation and recorded work; no inference or writes')
    create = sub.add_parser('create')
    create.add_argument('--request', default='')
    create.add_argument('--brief-file', type=Path)
    create.add_argument('--legacy-run', help='Reference an existing legacy run in a NEW work item; never import its approval/checkpoint')
    create.add_argument('--predecessor-work', help='Link a distinct closed native work item as history; no approval is imported')
    create.add_argument('--predecessor-revision', help='Exact current predecessor closure revision; required with --predecessor-work')
    create.add_argument('--provider', default='chatgpt_codex')
    create.add_argument('--model', default='gpt-5.6-sol')
    create.add_argument('--implementation-pool', nargs='+', help='Freeze profile names as an approved Goose-selectable implementation pool')
    create.add_argument('--implementation-profile', help='Freeze a runtime profile for the implementation worker; coordinator and independent reviewer remain separately configured')
    create.add_argument('--budget-seconds', type=int, default=600)
    brief = sub.add_parser('brief'); brief.add_argument('--file', required=True, type=Path)
    assign = sub.add_parser('assign'); assign.add_argument('--stage', required=True, choices=STAGES)
    assign.add_argument('--question', required=True)
    run_stage=sub.add_parser('run-stage',help='Authorize Goose/LangGraph coordination of an exact stage assignment')
    run_stage.add_argument('--stage',required=True,choices=STAGES)
    run_stage.add_argument('--revision',required=True);run_stage.add_argument('--actor',required=True)
    stage = sub.add_parser('stage'); stage.add_argument('--stage', required=True, choices=STAGES)
    stage.add_argument('--file', required=True, type=Path, help='Research/definition/solution/planning narrative')
    approve = sub.add_parser('approve'); approve.add_argument('--actor', required=True)
    approve.add_argument('--revision', required=True, help='Exact brief revision shown by status')
    decision = sub.add_parser('approve-stage'); decision.add_argument('--stage', required=True, choices=STAGES)
    decision.add_argument('--actor', required=True); decision.add_argument('--reason', default='')
    decision.add_argument('--revision',help='Exact stage-result revision being approved')
    stop = sub.add_parser('stop'); stop.add_argument('--actor', required=True); stop.add_argument('--reason', default='')
    accept = sub.add_parser('accept'); accept.add_argument('--actor', required=True)
    accept.add_argument('--revision', required=True, help='Exact closure revision shown by status')
    resume = sub.add_parser('resume'); resume.add_argument('--decision-file', type=Path)
    status = sub.add_parser('status'); status.add_argument('--legacy', action='store_true', help='Read the legacy run explicitly; no v2 resume compatibility implied')
    sub.add_parser('index')
    args = parser.parse_args(argv)
    project = args.project.resolve()
    if not project.is_dir():
        parser.error('Project workspace must already exist')
    if args.command == 'status' and args.legacy:
        from .history import legacy_run
        if not args.work:
            parser.error('--work is required')
        try:
            print(json.dumps(legacy_run(project, args.work), indent=2))
        except (ArtifactError, OSError, ValueError) as error:
            parser.error(str(error))
        return
    if args.command == 'context':
        from .history import legacy_runs, current_runs
        from .device_context import settings
        print(json.dumps({'product': 'Flow v2.0', 'context': resolve(project), 'work': current_runs(project),
                          'legacy_work': legacy_runs(project), 'device_context': settings(project)}, indent=2))
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
        missing_checkpoint = 'No v2 checkpoint exists. Legacy .flow runs require their original runtime or create --legacy-run ID with fresh approval.'
        if args.command == 'create':
            if bool(args.predecessor_work) != bool(args.predecessor_revision):
                parser.error('--predecessor-work and --predecessor-revision must be provided together')
            if args.predecessor_work == args.work:
                parser.error('Predecessor must be a distinct work item')
            if args.legacy_run == args.work:
                parser.error('A legacy handoff requires a distinct new v2 work ID; checkpoints and approvals are not imported')
            if args.budget_seconds <= 0 or not (args.request or args.brief_file):
                parser.error('Provide a request/brief and a positive budget')
        elif not (state_dir / 'workflow.sqlite').exists():
            parser.error(missing_checkpoint)
        # state/artifacts is a symlink in managed installations.
        imported=(ROOT/'artifacts').resolve().parent/'imported-work.json'
        if args.command not in {'create','status','context','index'} and imported.is_file():
            key=str(state_dir.relative_to(ROOT/'artifacts'))
            if key in json.loads(imported.read_text()).get('work_paths',[]):
                parser.error('This work item was preserved from the prior installation as read-only history. Create a fresh successor; prior approvals do not authorize new execution.')
        if args.command == 'status':
            with checkpoint_snapshot(state_dir/'workflow.sqlite') as saver:
                config = {'configurable': {'thread_id': args.work}, 'recursion_limit': 100}
                checkpoint = saver.get(config)
                if not checkpoint or not checkpoint['channel_values']:
                    parser.error(missing_checkpoint)
                options = checkpoint['channel_values']['runtime_options']
                graph = build(artifacts, NativeHarness(options), BriefChecker(artifacts)).compile(checkpointer=saver)
                result = summarize(graph.get_state(config, subgraphs=True), artifacts)
                from .managed import installation_status
                result['installation'] = installation_status(Path.home(), ROOT)
                result['checkpoint_view'] = 'latest_committed_snapshot'
                result['operator_active'] = operator_active(state_dir)
                if result['operator_active']:
                    result['next_action'] = 'Inspect running delivery; wait for the active operator before mutations'
                print(json.dumps(result, indent=2, default=str))
            return
        with locked(state_dir), SqliteSaver.from_conn_string(str(state_dir / 'workflow.sqlite')) as saver, ExitStack() as guards:
            config = {'configurable': {'thread_id': args.work}, 'recursion_limit': 100}
            checkpoint = saver.get(config)
            old = checkpoint['channel_values'] if checkpoint else {}
            if args.command == 'create':
                if old:
                    parser.error('Work item already exists; inspect status or resume it')
                options = {'provider': args.provider, 'model': args.model, 'budget_seconds': args.budget_seconds}
                if args.implementation_pool and args.implementation_profile:
                    parser.error('Choose either an implementation profile or an explicitly approved pool')
                if args.implementation_pool:
                    from .implementation_profiles import resolve_pool,apply_environment
                    options['implementation_profile']=resolve_pool(project,args.implementation_pool)
                    apply_environment({},options['implementation_profile'],args.provider,args.model)
                if args.implementation_profile:
                    from .implementation_profiles import resolve as resolve_profile, apply_environment
                    options['implementation_profile']=resolve_profile(project,args.implementation_profile)
                    apply_environment({},options['implementation_profile'],args.provider,args.model)
            else:
                if not old:
                    parser.error(missing_checkpoint)
                options = old['runtime_options']
            graph = build(artifacts, NativeHarness(options), BriefChecker(artifacts)).compile(checkpointer=saver)
            saved = graph.get_state(config, subgraphs=True)
            if args.command == 'create':
                context = resolve(project)
                if options.get('implementation_profile'):
                    context['implementation_profile']=options['implementation_profile']
                if args.predecessor_work:
                    from .predecessor import validated_predecessor
                    predecessor_dir = storage(project, args.predecessor_work)
                    def predecessor_snapshot():
                        with checkpoint_snapshot(predecessor_dir/'workflow.sqlite') as prior_saver:
                            prior_config = {'configurable': {'thread_id': args.predecessor_work}}
                            prior = prior_saver.get(prior_config)
                            if not prior or not prior.get('channel_values'):
                                raise ArtifactError('Predecessor checkpoint is empty')
                            prior_options = prior['channel_values']['runtime_options']
                            prior_graph = build(Artifacts(project, args.predecessor_work), NativeHarness(prior_options),
                                                BriefChecker(Artifacts(project, args.predecessor_work))).compile(checkpointer=prior_saver)
                            return prior_graph.get_state(prior_config, subgraphs=True)
                    context['predecessor_work'] = guards.enter_context(validated_predecessor(
                        project, args.work, args.predecessor_work, args.predecessor_revision,
                        predecessor_dir, predecessor_snapshot))
                if args.legacy_run:
                    from .history import legacy_run
                    legacy = legacy_run(project, args.legacy_run)
                    context['legacy_handoff'] = {'path': legacy['path'], 'revision': legacy['revision'],
                                                'origin': 'legacy', 'approval_imported': False,
                                                'legacy_state': legacy['record'].get('state'), 'legacy_runtime': legacy['record'].get('runtime'),
                                                'legacy_process_quiescence': 'not-observed',
                                                'instruction': 'Inspect original evidence, establish legacy execution is quiescent through its original runtime, and define a new brief. Do not run overlapping coordinators; prior approvals/checkpoints do not authorize v2 execution'}
                context_ref = artifacts.publish('contexts', 'project', context)
                initial = {'work_id': args.work, 'workspace': str(project), 'request': args.request,
                           'job_id': hashlib.sha256(str(project).encode()).hexdigest()[:16] + '-' + args.work,
                           'context_ref': context_ref, 'runtime_options': options,
                           'budget_seconds': args.budget_seconds, 'budget_policy': PAUSE_POLICY, 'lifecycle_phase': 'shaping'}
                if args.brief_file:
                    brief = validate_brief(read_json(args.brief_file), executable=False)
                    if context.get('legacy_handoff'):
                        brief['historical_references'] = [*brief.get('historical_references', []), context['legacy_handoff']]
                    initial['brief_ref'] = artifacts.publish('briefs', 'brief', brief)
                graph.invoke(initial, config)
            elif args.command == 'resume':
                decision = read_json(args.decision_file) if args.decision_file else None
                if isinstance(decision, dict) and decision.get('action') == 'recover-review':
                    if saved.next:
                        parser.error('Recovery requires quiescent closed work with no pending execution')
                    update = approve_recovery(old, decision, artifacts)
                    graph.update_state(config, update, as_node='prepare')
                    graph.invoke(None, config)
                elif isinstance(decision, dict) and decision.get('action') == 'retry-review':
                    if old.get('lifecycle_phase') != 'closed' or old.get('phase') != 'blocked' or not old.get('review'):
                        parser.error('retry-review requires a closed blocked review')
                    if not decision.get('actor') or not decision.get('reason'):
                        parser.error('retry-review requires actor and reason')
                    if old.get('candidate') != digest_tree(project):
                        parser.error('Candidate changed; use a separately approved successor work item')
                    if old['deadline'] <= time.time():
                        parser.error('Original delivery budget exhausted; no retry started')
                    if saved.next:
                        parser.error('Recovery requires quiescent closed work with no pending execution')
                    validate_candidate_recovery(old, decision, artifacts)
                    decisions = old.get('decision_refs', [])
                    ref = artifacts.publish('decisions', f'decision-{len(decisions)+1:04d}',
                                            {**decision, 'target_ref': old['closure_ref'],
                                             'brief_ref': old['brief_ref'], 'authority': 'Recheck unchanged candidate; no implementation'})
                    # LangGraph re-enters the existing delivery subgraph. Its
                    # authorize node routes candidate_reused directly to checks.
                    graph.update_state(config, {'candidate_reused': True, 'recovery_candidate': old['candidate'], 'lifecycle_phase': 'delivery',
                                                'decision_refs': [*decisions, ref],
                                                'resume_epoch': old.get('resume_epoch', 0)+1}, as_node='prepare')
                    graph.invoke(None, config)
                else:
                    if saved.next and old.get('deadline') is not None and not (isinstance(decision, dict) and decision.get('action') == 'stop'):
                        require_resume_budget(delivery_state(saved))
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
                repairing = any(item.get('value', {}).get('kind') == 'repair-brief' for item in summarize(saved, artifacts)['pending'])
                if (saved.values.get('lifecycle_phase') not in {'shaping', 'awaiting-approval'} and not (repairing and args.command in {'brief', 'stop'})) or not saved.next:
                    parser.error('Shaping commands apply only before implementation approval; start a successor work item for changed scope')
                if args.command == 'brief':
                    brief = validate_brief(read_json(args.file), executable=False)
                    legacy = artifacts.read(old['context_ref'])['payload'].get('legacy_handoff')
                    if legacy and legacy not in brief.get('historical_references', []):
                        brief['historical_references'] = [*brief.get('historical_references', []), legacy]
                    ref = artifacts.publish('briefs', 'brief', brief, supersedes=old.get('brief_ref'))
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
                elif args.command=='run-stage':
                    reference=old.get('shaping_assignment_refs',{}).get(args.stage)
                    if not reference or reference['revision']!=args.revision:
                        parser.error('Stage execution requires the exact current assignment revision')
                    response={'action':'run-stage','stage':args.stage,'actor':args.actor,'assignment_ref':reference}
                elif args.command == 'approve':
                    if not old.get('brief_ref') or args.revision != old['brief_ref']['revision']:
                        parser.error('Approval revision must match the exact currently proposed brief')
                    from .verification import require_ready
                    require_ready(project, validate_brief(artifacts.read(old['brief_ref'])['payload']))
                    response = {'action': 'approve', 'actor': args.actor, 'brief_ref': old['brief_ref']}
                else:
                    response = {'action': args.command, 'actor': args.actor, 'reason': args.reason}
                    if args.command == 'approve-stage':
                        response['stage'] = args.stage
                        reference=old.get('shaping_refs',{}).get(args.stage)
                        if args.revision and (not reference or args.revision!=reference['revision']):
                            parser.error('Stage approval revision does not match the current stage result')
                        response['stage_ref']=reference
                graph.invoke(Command(resume=response), config)
            summary = summarize(graph.get_state(config, subgraphs=True), artifacts)
            print(json.dumps(summary, indent=2, default=str))
            return outcome_exit(summary)
    except (ArtifactError, OSError, ValueError, KeyError, sqlite3.Error) as error:
        parser.error(str(error))


if __name__ == '__main__':
    raise SystemExit(main())
