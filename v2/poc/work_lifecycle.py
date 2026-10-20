"""Shaping, approvals, existing delivery subgraph and closure; one LangGraph thread."""
import json
import time
from .artifacts import ArtifactError, atomic_write, validate_brief
from .contracts import State, task_input_digest, digest_tree
from .handoffs import Handoffs
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
            validate_brief(record['payload'])
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
                if decision.get('brief_ref') != brief_ref:
                    raise ArtifactError('Approval must name the exact proposed brief revision')
            decisions = s.get('decision_refs', [])
            ref = artifacts.publish('decisions', f'decision-{len(decisions)+1:04d}', {
                'action': action, 'actor': actor, 'target_ref': target,
                'reason': decision.get('reason', ''), 'supersedes_decision': decision.get('supersedes_decision'),
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
            if result.get('brief'):
                brief=validate_brief(result['brief'])
                update['brief_ref']=artifacts.publish('briefs','brief',brief,supersedes=s.get('brief_ref'))
                update['lifecycle_phase']='awaiting-approval'
        return update

    def prepare(s):
        brief = validate_brief(artifacts.read(s['brief_ref'])['payload'])
        context = artifacts.read(s['context_ref'])['payload']
        decision = artifacts.read(s['approval_ref'])['payload']
        if decision['action'] != 'approve' or decision['target_ref'] != s['brief_ref']:
            raise ArtifactError('Implementation requires approval of this exact brief')
        task = json.dumps(brief, indent=2, ensure_ascii=False)
        source_refs = {'brief_ref': s['brief_ref'], 'approval_ref': s['approval_ref'],
                       'context_ref': s['context_ref'], 'shaping_refs': s.get('shaping_refs', {})}
        project_context = render(context) + '\nControlled input references:\n' + json.dumps(source_refs, indent=2)
        return {'task': task, 'project_context': project_context, 'check_command': brief['check_command'],
                'inputs': task_input_digest(task, s['workspace'], project_context),
                'approved': task_input_digest(task, s['workspace'], project_context),
                'job_id': s['job_id'], 'deadline': time.time() + s.get('budget_seconds', 600),
                'corrections': 0, 'attempt': 0, 'lifecycle_phase': 'delivery'}

    def closure(s):
        # Technical readiness and user acceptance are deliberately separate.
        from .monitoring import report
        payload = {'work_id': s['work_id'], 'outcome': s.get('outcome', s.get('phase')),
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
    b.add_edge('coordinate-stage','approval')
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
