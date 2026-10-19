"""Durable task transitions; Goose owns implementation coordination and workers."""
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from .contracts import State, digest_tree

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

    def checks(s):
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
        limit = min(MAX_CORRECTIONS, max(0, s.get('max_corrections', MAX_CORRECTIONS)))
        if s.get('corrections', 0) >= limit:
            return {'phase': 'blocked', 'outcome': 'blocked',
                    'failure': f'{limit} correction rounds exhausted; inspect findings and revise the task or approach.',
                    'recommendation': 'Return the unresolved findings and test results to the task owner.'}
        return {'corrections': s.get('corrections', 0)+1, 'phase': 'ready'}

    def escalate(s):
        detail = s.get('review') if s['resume_stage'] == 'review' else s.get('check') if s['resume_stage'] == 'check' else s.get('result')
        decision = interrupt({'kind': s['phase'], 'task': s.get('task'), 'workspace': s['workspace'],
                              'detail': detail, 'resume_stage': s['resume_stage']})
        refs = {}
        if boundary:
            decision, refs = boundary.escalation(s, decision)
        if decision != 'resume':
            return {**refs, 'phase': 'blocked', 'outcome': 'blocked', 'failure': 'Task owner stopped the paused action.'}
        return {**refs, 'phase': 'ready', 'resume_epoch': s.get('resume_epoch', 0)+1}

    def after_implementation(s):
        return 'escalate' if s['phase'] in ESCALATIONS else dispatch('check') if s['phase'] == 'completed' else 'reconcile' if s['phase'] == 'uncertain' else 'correct' if s['phase']=='correction' else END

    def after_check(s):
        return 'escalate' if s['phase'] in ESCALATIONS else END if s['phase']=='blocked' else dispatch('review') if s['check']['passed'] else 'correct'

    b = StateGraph(State)
    for name, fn in [('authorize', authorize), ('implement', implement), ('reconcile', reconcile),
                     ('check', checks), ('review', review), ('correct', correct), ('escalate', escalate)]:
        b.add_node(name, fn)
    if boundary:
        for kind in ('implement', 'check', 'review'):
            b.add_node('assign-' + kind, lambda s, kind=kind: boundary.assign(s, kind))
            b.add_edge('assign-' + kind, kind)
    b.add_edge(START, 'authorize')
    b.add_conditional_edges('authorize', lambda s: dispatch('check' if s.get('candidate_reused') else 'implement') if s['phase'] == 'ready' else END)
    b.add_conditional_edges('implement', after_implementation)
    b.add_conditional_edges('reconcile', lambda s: 'escalate' if s['phase'] in ESCALATIONS else dispatch('check') if s['phase'] == 'completed' else END)
    b.add_conditional_edges('check', after_check)
    b.add_conditional_edges('review', lambda s: 'escalate' if s['phase'] in ESCALATIONS else 'correct' if s['phase'] == 'correction' else END)
    b.add_conditional_edges('correct', lambda s: dispatch('implement') if s['phase'] == 'ready' else END)
    b.add_conditional_edges('escalate', lambda s: dispatch(s['resume_stage']) if s['phase'] == 'ready' else END)
    return b
