"""Controlled handoffs around side effects; LangGraph owns dispatch and recovery."""
from langgraph.types import interrupt
from .artifacts import ArtifactError
from .contracts import digest_tree


class Handoffs:
    def __init__(self, artifacts):
        self.artifacts = artifacts

    def assign(self, state, kind):
        self._recovery_boundary(state, kind)
        operation = f"{kind}-{state.get('corrections', 0)}-{state.get('resume_epoch', 0)}"
        # A restarted prepare node republishes the same immutable assignment.
        ref = self.artifacts.publish('assignments', operation, {
            'operation_id': operation, 'kind': kind, 'brief_ref': state['brief_ref'],
            'approval_ref': state['approval_ref'], 'context_ref': state['context_ref'],
            'recovery_ref': state.get('recovery_ref'),
            'task': state['task'], 'workspace': state['workspace'],
            'expected_result': 'Actual outcome, findings, checks, limitations and effects',
            'authority': 'Approved brief and existing workspace/credential permissions only',
            'candidate_revision': digest_tree(state['workspace']) if kind in {'check', 'review'} else state.get('candidate_revision'),
        })
        return {'assignment_ref': ref,
                'assignment_refs': {**state.get('assignment_refs', {}), operation: ref}}

    def call(self, state, kind, execute):
        self._recovery_boundary(state, kind)
        assignment = self.artifacts.read(state['assignment_ref'])
        if assignment['payload']['kind'] != kind:
            raise ArtifactError('Wrong assignment at execution boundary')
        for name in ('brief_ref', 'approval_ref', 'context_ref'):
            reference=assignment['payload'][name]
            if reference is None and name=='brief_ref' and kind in {'define','solution','plan'}:
                if state.get(name) is not None: raise ArtifactError('Assignment brief changed')
                continue
            self.artifacts.read(reference)
            if reference != state[name]:
                raise ArtifactError('Assignment context changed')
        operation = assignment['id']
        ref, previous = self.artifacts.leaf('results', operation)
        if kind == 'check' and digest_tree(state['workspace']) != assignment['payload']['candidate_revision']:
            result = {'passed': False, 'outcome': 'scope_required',
                      'reason': 'Workspace changed after the check assignment. Inspect the new candidate before continuing.'}
            ref = self._result(operation, state, result, 'completed', ref, 'Observed candidate differs from assigned check input')
            return result, self._refs(state, operation, ref)
        if previous and previous['payload']['effect'] == 'completed':
            return previous['payload']['result'], self._refs(state, operation, ref)
        if previous:
            decision = interrupt({'kind': 'reconcile-effect', 'operation_id': operation,
                                  'assignment_ref': state['assignment_ref'], 'result_ref': ref,
                                  'effect': previous['payload']['effect'],
                                  'instruction': 'Inspect workspace/job. Supply effect=completed with actual result, or effect=not_started with evidence. Never replay an uncertain action by guessing.'})
            if not isinstance(decision, dict) or not decision.get('evidence'):
                raise ArtifactError('Recovery requires observed evidence')
            if not decision.get('actor'):
                raise ArtifactError('Recovery requires the decision actor')
            effect = decision.get('effect')
            if effect not in {'completed', 'not_started'}:
                raise ArtifactError('Pending/uncertain effects must be inspected before resuming')
            decision_ref = self.artifacts.publish('decisions', 'recover-' + operation + '-' + ref['revision'][:12], {
                'action': 'reconcile-effect', 'actor': decision['actor'], 'effect': effect,
                'assignment_ref': state['assignment_ref'], 'target_ref': ref,
                'evidence': decision['evidence']})
            if effect == 'completed':
                result = decision.get('result')
                self._validate_result(kind, result)
                ref = self._result(operation, state, result, 'completed', ref, decision['evidence'], decision_ref)
                return result, self._refs(state, operation, ref)
            if effect != 'not_started':
                raise ArtifactError('Pending/uncertain effects must be inspected before resuming')
            # Explicit observed not-started permits this same authorized operation.
        decision_ref = decision_ref if previous else None
        marker = self._result(operation, state, None, 'uncertain', ref,
                              'Intent published before invocation; completion is not yet known', decision_ref)
        result = execute()
        self._validate_result(kind, result)
        if result.get('status', result.get('outcome')) in {'uncertain', 'pending'}:
            self._result(operation, state, result, result.get('status', result.get('outcome')), marker,
                         'Runtime reported an unresolved effect; inspect before continuing')
            # Restart this node through its durable interrupt, without another call.
            return self.call(state, kind, execute)
        ref = self._result(operation, state, result, 'completed', marker,
                           'Invocation returned this result; reported limitations remain authoritative', decision_ref)
        return result, self._refs(state, operation, ref)

    def _recovery_boundary(self, state, kind):
        if not state.get('candidate_reused'): return
        if kind not in {'check', 'review'}:
            raise ArtifactError('Candidate-only recovery cannot authorize implementation')
        if digest_tree(state['workspace']) != state.get('recovery_candidate', state.get('candidate')):
            raise ArtifactError('Recovery candidate changed; no execution authorized')
        if state.get('recovery_ref'):
            decision = self.artifacts.read(state['recovery_ref'])['payload']
            if decision.get('action') != 'recover-review' or decision.get('candidate_revision') != state['recovery_candidate'] or decision.get('brief_ref') != state['brief_ref']:
                raise ArtifactError('Recovery authority changed')

    def escalation(self, state, decision):
        if not isinstance(decision, dict) or not decision.get('actor') or decision.get('action') not in {'resume', 'stop'}:
            raise ArtifactError('Escalation needs actor and action=resume|stop')
        operation = f"delivery-{state['resume_stage']}-{state.get('corrections', 0)}-{state.get('resume_epoch', 0)}"
        ref = self.artifacts.publish('decisions', operation, {
            'action': decision['action'], 'actor': decision['actor'],
            'reason': decision.get('reason', ''), 'target_ref': state.get('result_ref'),
            'brief_ref': state['brief_ref'], 'authority': 'Continue same approved scope only'})
        return decision['action'], {'decision_refs': [*state.get('decision_refs', []), ref]}

    @staticmethod
    def _validate_result(kind, result):
        if not isinstance(result, dict):
            raise ArtifactError('Result must be a JSON object')
        if kind == 'implement' and 'status' not in result:
            raise ArtifactError('Implementation result requires status')
        if kind in {'check', 'review'} and not isinstance(result.get('passed'), bool):
            raise ArtifactError('Check/review result requires passed boolean')
        if kind in {'define','solution','plan'} and (result.get('status') not in {'completed','blocked','permission_required','scope_required','uncertain','pending','timeout','failed'} or
                (result.get('status')=='completed' and not isinstance(result.get('content'),str))):
            raise ArtifactError('Stage result requires an explicit status and substantive content')

    def _result(self, operation, state, result, effect, supersedes, evidence, decision_ref=None):
        return self.artifacts.publish('results', operation, {
            'assignment_ref': state['assignment_ref'], 'effect': effect,
            'effects': [{'operation_id': operation, 'status': effect, 'evidence': evidence}],
            'decision_ref': decision_ref, 'result': result}, supersedes=supersedes)

    def _refs(self, state, operation, ref):
        refs = {'result_ref': ref, 'result_refs': {**state.get('result_refs', {}), operation: ref}}
        decision = self.artifacts.read(ref)['payload'].get('decision_ref')
        if decision and decision not in state.get('decision_refs', []):
            refs['decision_refs'] = [*state.get('decision_refs', []), decision]
        return refs
