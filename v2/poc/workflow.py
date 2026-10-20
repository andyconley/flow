"""Durable task transitions; Goose owns implementation coordination and workers."""
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from .contracts import State, digest_tree
from .recovery import PAUSE_POLICY, require_resume_budget
import time

MAX_CORRECTIONS = 3
ESCALATIONS = {'permission_required', 'scope_required'}


def build(harness, checker, boundary=None):
    def call(s, kind, execute):
        return boundary.call(s, kind, execute) if boundary else (execute(), {})

    def dispatch(kind):
        return 'assign-' + kind if boundary else kind

    def authorize(s):
        if s.get('approved') != s['inputs']:
            value = interrupt({'kind': 'approve-inputs', 'digest': s['inputs']})
            if value != s['inputs']:
                return {'phase': 'blocked', 'failure': 'approval digest mismatch'}
            return {'approved': value, 'phase': 'ready'}
        return {'phase': 'ready'}

    def implement(s):
        result, refs = call(s, 'implement', lambda: harness.implement(s))
        return {**refs, 'result': result, 'attempt': s.get('attempt', 0)+1,
                'findings':result.get('findings',[]),'test_results':result.get('test_results',{}), 'outcome':result.get('outcome',result['status']), 'phase': result['status'], 'resume_stage': 'implement', 'pending_kind': 'implement'}

    def reconcile(s):
        result = harness.reconcile(s)
        return {'result': result, 'phase': result['status']}

    def candidate_guard(s):
        if s.get('candidate_reused') and digest_tree(s['workspace']) != s.get('recovery_candidate', s.get('candidate')):
            return {'phase': 'blocked', 'outcome': 'blocked', 'failure': 'Recovery candidate changed; separately approved successor required'}

    def checks(s):
        guard = candidate_guard(s)
        if guard: return guard
        candidate = digest_tree(s['workspace'])
        def execute():
            try:
                return checker.run_state(s) if hasattr(checker, 'run_state') else checker(s['workspace'])
            except PermissionError as error:
                return {'passed':False,'outcome':'permission_required','reason':str(error)}
        result, refs = call(s, 'check', execute)
        return {**refs, 'candidate': candidate, 'candidate_revision': candidate, 'check': result,
                'test_results': result, 'outcome':result.get('outcome','checked'), 'phase': result.get('outcome', 'checked'), 'resume_stage': 'check'}

    def review(s):
        guard = candidate_guard(s)
        if guard: return guard
        result, refs = call(s, 'review', lambda: harness.review(s))
        if result.get('outcome') in ESCALATIONS:
            phase = result['outcome']
        elif result.get('blocked'):
            phase = 'blocked'
        elif digest_tree(s['workspace']) != s['candidate'] or result.get('candidate') != s['candidate']:
            phase = 'blocked'
            result = {**result, 'reason': 'review candidate changed; recheck the actual artifact'}
        else:
            phase = 'reviewed-and-ready' if result.get('passed') else 'correction'
        return {**refs, 'review': result, 'findings': result.get('findings', []),
                'outcome': phase, 'phase': phase, 'resume_stage': 'review', 'pending_kind': 'review'}

    def correct(s):
        if s.get('candidate_reused'):
            return {'phase': 'blocked', 'outcome': 'blocked', 'failure': 'Candidate-only recovery cannot implement corrections; create a separately approved successor'}
        limit = min(MAX_CORRECTIONS, max(0, s.get('max_corrections', MAX_CORRECTIONS)))
        if s.get('corrections', 0) >= limit:
            return {'phase': 'blocked', 'outcome': 'blocked',
                    'failure': f'{limit} correction rounds exhausted; inspect findings and revise the task or approach.',
                    'recommendation': 'Return the unresolved findings and test results to the task owner.'}
        return {'corrections': s.get('corrections', 0)+1, 'phase': 'ready'}

    def pause(s):
        if s.get('budget_policy') == PAUSE_POLICY:
            return {'pause_remaining': max(0, s['deadline'] - time.time())}
        return {}

    def escalate(s):
        detail = s.get('review') if s['resume_stage'] == 'review' else s.get('check') if s['resume_stage'] == 'check' else s.get('result')
        decision = interrupt({'kind': s['phase'], 'task': s.get('task'), 'workspace': s['workspace'],
                              'detail': detail, 'resume_stage': s['resume_stage']})
        action = decision.get('action') if isinstance(decision, dict) else decision
        if action == 'resume': require_resume_budget(s)
        refs = {}
        if boundary:
            decision, refs = boundary.escalation(s, decision)
        if decision != 'resume':
            return {**refs, 'phase': 'stopped', 'outcome': 'stopped', 'failure': 'Task owner stopped the paused action.'}
        update = {**refs, 'phase': 'ready', 'resume_epoch': s.get('resume_epoch', 0)+1}
        if s.get('budget_policy') == PAUSE_POLICY and s.get('pause_remaining') is not None:
            update.update(deadline=time.time()+s['pause_remaining'], pause_remaining=None)
        return update

    def after_implementation(s):
        return 'pause' if s['phase'] in ESCALATIONS else dispatch('check') if s['phase'] == 'completed' else 'reconcile' if s['phase'] == 'uncertain' else 'correct' if s['phase']=='correction' else END

    def after_check(s):
        return 'pause' if s['phase'] in ESCALATIONS else END if s['phase']=='blocked' else dispatch('review') if s['check']['passed'] else 'correct'

    b = StateGraph(State)
    for name, fn in [('authorize', authorize), ('implement', implement), ('reconcile', reconcile),
                     ('check', checks), ('review', review), ('correct', correct), ('pause', pause), ('escalate', escalate)]:
        b.add_node(name, fn)
    if boundary:
        for kind in ('implement', 'check', 'review'):
            b.add_node('assign-' + kind, lambda s, kind=kind: candidate_guard(s) or boundary.assign(s, kind))
            b.add_conditional_edges('assign-' + kind, lambda s, kind=kind: END if s.get('phase') == 'blocked' else kind)
    b.add_edge(START, 'authorize')
    b.add_conditional_edges('authorize', lambda s: dispatch('check' if s.get('candidate_reused') else 'implement') if s['phase'] == 'ready' else END)
    b.add_conditional_edges('implement', after_implementation)
    b.add_conditional_edges('reconcile', lambda s: 'pause' if s['phase'] in ESCALATIONS else dispatch('check') if s['phase'] == 'completed' else END)
    b.add_conditional_edges('check', after_check)
    b.add_conditional_edges('review', lambda s: 'pause' if s['phase'] in ESCALATIONS else 'correct' if s['phase'] == 'correction' else END)
    b.add_conditional_edges('correct', lambda s: dispatch('implement') if s['phase'] == 'ready' else END)
    b.add_edge('pause', 'escalate')
    b.add_conditional_edges('escalate', lambda s: dispatch(s['resume_stage']) if s['phase'] == 'ready' else END)
    return b
