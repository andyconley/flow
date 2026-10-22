"""Shaping, approvals, existing delivery subgraph and closure; one LangGraph thread."""
import json
import time
from .artifacts import ArtifactError, atomic_write, validate_brief, brief_schema
from .contracts import State, task_input_digest, digest_tree
from .handoffs import Handoffs
from .verification import require_ready
from .project_context import render
from .workflow import build as delivery
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt


class WorkState(State, total=False):
    request: str
    lifecycle_phase: str
    shaping_refs: dict
    shaping_assignment_refs: dict
    decision_refs: list
    closure_ref: dict
    budget_seconds: int
    acceptance: str
    runtime_options: dict


def build(artifacts, harness, checker):
    def approval(s):
        brief_ref = s.get('brief_ref')
        brief = artifacts.read(brief_ref)['payload'] if brief_ref else None
        decision = interrupt({'kind': 'approve-brief' if brief else 'shape-request',
                              'work_id': s['work_id'], 'request': s.get('request'),
                              'brief_ref': brief_ref, 'brief': brief,
                              'verification_expectations': {key: brief.get(key) for key in ('check_command', 'coverage', 'check_scope', 'prerequisites')} if brief else None,
                              'previous_brief_ref': artifacts.read(brief_ref)['supersedes'] if brief_ref else None,
                              'proposed_budget_seconds': s.get('budget_seconds', 600),
                              'implementation_profile': s.get('runtime_options',{}).get('implementation_profile'),
                              'budget_policy': s.get('budget_policy', 'legacy-wall-clock'),
                              'context_ref': s['context_ref'], 'shaping_refs': s.get('shaping_refs', {}),
                              'shaping_assignments': s.get('shaping_assignment_refs', {}),
                              'actions': ['brief', 'assign', 'run-stage', 'stage', 'approve-stage', 'approve', 'stop']})
        if not isinstance(decision, dict):
            raise ArtifactError('A structured host decision is required')
        action = decision.get('action')
        if action=='run-stage':
            stage=decision.get('stage');reference=s.get('shaping_assignment_refs',{}).get(stage)
            if not reference or reference!=decision.get('assignment_ref') or not decision.get('actor'):
                raise ArtifactError('Stage execution requires actor and exact current assignment approval')
            assignment=artifacts.read(reference)
            if assignment['payload']['context_ref']!=s['context_ref'] or assignment['payload'].get('brief_ref')!=s.get('brief_ref'):
                raise ArtifactError('Stage inputs changed; propose and approve a new assignment')
            decisions=s.get('decision_refs',[])
            ref=artifacts.publish('decisions',f'decision-{len(decisions)+1:04d}',{
                'action':'run-stage','actor':decision['actor'],'target_ref':reference,
                'candidate_revision':digest_tree(s['workspace']),
                'authority':'Bounded stage coordination/research only; no implementation or approval authority'})
            return {'stage_to_run':stage,'stage_authorization_ref':ref,'decision_refs':[*decisions,ref],
                    'lifecycle_phase':'coordinate-stage'}
        if action == 'brief':
            reference = decision['brief_ref']
            record = artifacts.read(reference)
            validate_brief(record['payload'], executable=False)
            if record['kind'] != 'briefs' or record['supersedes'] != brief_ref:
                raise ArtifactError('Brief must explicitly supersede the currently proposed revision')
            return {'brief_ref': reference, 'lifecycle_phase': 'awaiting-approval'}
        if action in {'assign', 'stage'}:
            key = 'assignment_ref' if action == 'assign' else 'shaping_ref'
            record = artifacts.read(decision[key])
            expected = 'assignments' if action == 'assign' else 'shaping'
            if record['kind'] != expected or record['payload']['stage'] not in {'define', 'solution', 'plan'}:
                raise ArtifactError('Expected a shaping assignment or stage artifact')
            stage = record['payload']['stage']
            field = 'shaping_assignment_refs' if action == 'assign' else 'shaping_refs'
            previous = s.get(field, {}).get(stage)
            if record['supersedes'] != previous:
                raise ArtifactError('Shaping changes must explicitly supersede the current revision')
            if action == 'stage' and record['payload'].get('assignment_ref') != s.get('shaping_assignment_refs', {}).get(stage):
                raise ArtifactError('Stage result must reference its exact current assignment, or null for direct host input')
            return {field: {**s.get(field, {}), stage: decision[key]}, 'lifecycle_phase': 'shaping'}
        if action in {'approve', 'approve-stage', 'stop'}:
            actor = decision.get('actor')
            if not actor or not isinstance(actor, str):
                raise ArtifactError('A decision needs an explicit actor')
            target = brief_ref
            if action == 'approve-stage':
                stage = decision.get('stage')
                target = s.get('shaping_refs', {}).get(stage)
                if not target:
                    raise ArtifactError('There is no stage artifact to approve')
                if decision.get('stage_ref') is not None and decision['stage_ref']!=target:
                    raise ArtifactError('Stage approval must name the exact current result')
            if action == 'approve':
                if not brief:
                    raise ArtifactError('Publish a complete brief before approving implementation')
                validate_brief(brief)
                require_ready(s['workspace'], brief)
                if decision.get('brief_ref') != brief_ref:
                    raise ArtifactError('Approval must name the exact proposed brief revision')
            decisions = s.get('decision_refs', [])
            ref = artifacts.publish('decisions', f'decision-{len(decisions)+1:04d}', {
                'action': action, 'actor': actor, 'target_ref': target,
                'reason': decision.get('reason', ''), 'supersedes_decision': decision.get('supersedes_decision'),
                'budget_seconds': s.get('budget_seconds', 600) if action == 'approve' else None,
                'budget_policy': s.get('budget_policy', 'legacy-wall-clock') if action == 'approve' else None,
                **({'implementation_profile':s['runtime_options']['implementation_profile']} if action=='approve' and s.get('runtime_options',{}).get('implementation_profile') else {}),
                'authority': 'implementation' if action == 'approve' else 'stage-only' if action == 'approve-stage' else 'stop'})
            update = {'decision_refs': [*decisions, ref], 'lifecycle_phase': 'approved' if action == 'approve' else 'stopped' if action == 'stop' else 'awaiting-approval' if s.get('brief_ref') else 'shaping'}
            if action == 'approve':
                update['approval_ref'] = ref
            return update
        raise ArtifactError('Unknown shaping/approval action')

    def coordinate_stage(s):
        stage=s['stage_to_run'];authorization=artifacts.read(s['stage_authorization_ref'])['payload']
        proposal=s['shaping_assignment_refs'][stage]
        if authorization['action']!='run-stage' or authorization['target_ref']!=proposal:
            raise ArtifactError('Stage execution approval changed')
        operation='stage-'+stage+'-'+s['stage_authorization_ref']['revision'][:16]
        assignment=artifacts.publish('assignments',operation,{
            **artifacts.read(proposal)['payload'],'kind':stage,'source_assignment_ref':proposal,
            'approval_ref':s['stage_authorization_ref'],'context_ref':s['context_ref'],'brief_ref':s.get('brief_ref'),
            'candidate_revision':authorization['candidate_revision']})
        execution={**s,'assignment_ref':assignment,'approval_ref':s['stage_authorization_ref'],'brief_ref':s.get('brief_ref')}
        def execute():
            before=digest_tree(s['workspace'])
            if before!=authorization['candidate_revision']:
                return {'status':'scope_required','reason':'Project changed since stage execution approval; inspect and authorize a fresh assignment before dispatch'}
            result=harness.shape(execution,stage,artifacts.read(proposal)['payload'])
            if digest_tree(s['workspace'])!=before:
                return {'status':'scope_required','reason':'Research/planning changed the project candidate without implementation approval; inspect partial effects before continuing','runtime':result.get('runtime',{})}
            return result
        result,refs=Handoffs(artifacts).call(execution,stage,execute)
        update={**refs,'stage_result':result,'lifecycle_phase':'shaping'}
        if result['status']=='completed':
            ref=artifacts.publish('shaping',stage,{'stage':stage,'content':result['content'],
                'assignment_ref':proposal,'context_ref':s['context_ref'],'brief_ref':s.get('brief_ref'),
                'origin':'goose-langgraph','runtime':result.get('runtime',{}),'authorization_ref':s['stage_authorization_ref']},
                supersedes=s.get('shaping_refs',{}).get(stage))
            update['shaping_refs']={**s.get('shaping_refs',{}),stage:ref}
            if 'brief' in result:
                proposed = result['brief']
                repair_ref = None
                while True:
                    try:
                        brief = validate_brief(proposed, executable=stage == 'plan')
                        break
                    except ArtifactError as error:
                        repair_ref = artifacts.publish('shaping', 'brief-repair-'+operation, {
                            'research_ref': ref, 'result_refs': refs, 'proposed_brief': proposed,
                            'errors': str(error), 'research_outcome': 'completed', 'brief_outcome': 'invalid'}, supersedes=repair_ref)
                        decision = interrupt({'kind': 'repair-brief', 'outcome': 'brief-invalid',
                            'research_outcome': 'completed', 'research_ref': ref, 'repair_ref': repair_ref,
                            'errors': str(error), 'schema': brief_schema(executable=stage == 'plan'),
                            'instruction': 'Repair only the proposed brief; research is retained. Use brief --file or resume with action=brief and exact brief_ref.'})
                        if isinstance(decision, dict) and decision.get('action') == 'stop' and decision.get('actor'):
                            stopped = artifacts.publish('decisions', 'stop-'+operation, {**decision, 'target_ref': repair_ref})
                            return {**update, 'decision_refs': [*s.get('decision_refs', []), stopped], 'lifecycle_phase': 'stopped'}
                        if not isinstance(decision, dict) or decision.get('action') != 'brief':
                            raise ArtifactError('Targeted repair requires action=brief with an immutable brief_ref')
                        repaired = artifacts.read(decision['brief_ref'])
                        if repaired['kind'] != 'briefs' or repaired['supersedes'] != s.get('brief_ref'):
                            raise ArtifactError('Repair must supersede the currently proposed brief')
                        proposed = repaired['payload']
                update['brief_ref']=artifacts.publish('briefs','brief',brief,supersedes=s.get('brief_ref'))
                update['lifecycle_phase']='awaiting-approval'
        return update

    def prepare(s):
        brief = validate_brief(artifacts.read(s['brief_ref'])['payload'])
        readiness = require_ready(s['workspace'], brief)
        artifacts.publish('shaping', 'preflight-'+s['brief_ref']['revision'][:16], readiness)
        context = artifacts.read(s['context_ref'])['payload']
        decision = artifacts.read(s['approval_ref'])['payload']
        if decision['action'] != 'approve' or decision['target_ref'] != s['brief_ref']:
            raise ArtifactError('Implementation requires approval of this exact brief')
        selected=s.get('runtime_options',{}).get('implementation_profile')
        from .implementation_profiles import validate as validate_profile
        validate_profile(selected)
        if selected and (decision.get('implementation_profile')!=selected or context.get('implementation_profile')!=selected):
            raise ArtifactError('Implementation profile changed after proposal/approval; create a new work item')
        task = json.dumps(brief, indent=2, ensure_ascii=False)
        source_refs = {'brief_ref': s['brief_ref'], 'approval_ref': s['approval_ref'],
                       'context_ref': s['context_ref'], 'shaping_refs': s.get('shaping_refs', {})}
        project_context = render(context) + '\nControlled input references:\n' + json.dumps(source_refs, indent=2)
        if selected:project_context+='\nApproved implementation profile: '+json.dumps(selected,sort_keys=True)
        return {**({'implementation_profile_digest':selected['sha256']} if selected else {}),
                'task': task, 'project_context': project_context, 'check_command': brief['check_command'],
                'inputs': task_input_digest(task, s['workspace'], project_context),
                'approved': task_input_digest(task, s['workspace'], project_context),
                'job_id': s['job_id'], 'deadline': time.time() + s.get('budget_seconds', 600),
                'corrections': 0, 'attempt': 0, 'lifecycle_phase': 'delivery'}

    def closure(s):
        # Technical readiness and user acceptance are deliberately separate.
        from .monitoring import report
        stage = s.get('resume_stage')
        detail = s.get('review') if stage == 'review' else s.get('check') if stage == 'check' else s.get('result')
        reason = s.get('failure') or (detail.get('reason') if isinstance(detail, dict) else None)
        intentional = s.get('outcome') in {'stopped', 'replaced'} or s.get('phase') in {'stopped', 'replaced'}
        blocked = s.get('phase') in {'blocked', 'permission_required', 'scope_required'} and not intentional
        payload = {'work_id': s['work_id'], 'outcome': s.get('outcome', s.get('phase')),
                   'termination': 'intentional-stop' if intentional else 'blocked' if blocked else None,
                   'stage': stage, 'reason': reason, 'result': detail,
                   'blocker': {'stage': stage, 'reason': reason, 'result': detail} if blocked else None,
                   'acceptance': s.get('acceptance', 'not-recorded'),
                   'brief_ref': s['brief_ref'], 'context_ref': s['context_ref'],
                   'decision_refs': s.get('decision_refs', []),
                   'assignment_refs': s.get('assignment_refs', {}), 'result_refs': s.get('result_refs', {}),
                   'candidate_revision': s.get('candidate_revision'), 'findings': s.get('findings', []),
                   'test_results': s.get('test_results', {}), 'failure': s.get('failure'),
                   'historical_references': artifacts.read(s['brief_ref'])['payload'].get('historical_references', []),
                   'followups': artifacts.read(s['brief_ref'])['payload'].get('followups', []),
                   'usage': report(artifacts.project, job_id=s.get('job_id')),
                   'deployment': 'not-authorized-by-closure'}
        ref = artifacts.publish('closures', 'closure', payload, supersedes=s.get('closure_ref'))
        return {'closure_ref': ref, 'lifecycle_phase': 'closed'}

    b = StateGraph(WorkState)
    b.add_node('approval', approval)
    b.add_node('coordinate-stage',coordinate_stage)
    b.add_node('prepare', prepare)
    b.add_node('delivery', delivery(harness, checker, boundary=Handoffs(artifacts)).compile())
    b.add_node('closure', closure)
    b.add_edge(START, 'approval')
    b.add_conditional_edges('approval', lambda s: 'prepare' if s['lifecycle_phase'] == 'approved' else 'coordinate-stage' if s['lifecycle_phase']=='coordinate-stage' else END if s['lifecycle_phase'] == 'stopped' else 'approval')
    b.add_conditional_edges('coordinate-stage', lambda s: END if s['lifecycle_phase'] == 'stopped' else 'approval')
    b.add_edge('prepare', 'delivery')
    b.add_edge('delivery', 'closure')
    b.add_edge('closure', END)
    return b


def publish_index(project, records):
    """Rebuildable closure projection; never used to dispatch or resume work."""
    lines = ['# GLG closed work', '', 'Generated from immutable closure artifacts; LangGraph owns current state.', '']
    for work_id, reference, record in sorted(records):
        payload = record['payload']
        lines.append(f"- {work_id}: {payload['outcome']} (acceptance: {payload['acceptance']}) — [{reference['revision'][:12]}](../{reference['path']})")
    atomic_write(project / '.glg' / 'INDEX.md', ('\n'.join(lines) + '\n').encode())
