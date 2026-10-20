"""Candidate-only recovery and explicit delivery budget policies."""
import time
from .artifacts import ArtifactError
from .contracts import digest_tree

PAUSE_POLICY = 'exclude-permission-scope-pauses-v1'
MAX_RECOVERY_SECONDS = 86400


def budget_status(state, now=None):
    now = time.time() if now is None else now
    policy = state.get('budget_policy', 'legacy-wall-clock')
    paused = state.get('pause_remaining')
    remaining = (paused if policy == PAUSE_POLICY and paused is not None else
                 max(0, state['deadline'] - now) if state.get('deadline') is not None else None)
    return {'proposed_seconds': state.get('budget_seconds', 600), 'policy': policy,
            'remaining_seconds': remaining, 'expired': remaining is not None and remaining <= 0,
            'paused': policy == PAUSE_POLICY and paused is not None,
            'human_waiting_policy': 'Permission/scope pauses freeze remaining execution time. Uncertain-effect reconciliation retains the original deadline; inspect effects before recovery.' if policy == PAUSE_POLICY else 'Existing record retains its approved wall-clock deadline, including human waiting; no automatic extension.'}


def require_resume_budget(state):
    if budget_status(state)['expired']:
        raise ArtifactError('Approved delivery budget expired; no resume recorded. Inspect status; an unchanged closed candidate needs explicit recover-review approval, or create a fresh successor.')


def validate_candidate_recovery(state, decision, artifacts):
    """Validate everything before publishing authority or changing a checkpoint."""
    if state.get('lifecycle_phase') != 'closed' or state.get('phase') != 'blocked' or not state.get('review'):
        raise ArtifactError('recover-review requires a closed blocked review')
    if not all(isinstance(decision.get(k), str) and decision[k].strip() for k in ('actor', 'reason')):
        raise ArtifactError('recover-review requires actor and reason')
    for name in ('closure_ref', 'brief_ref'):
        if decision.get(name) != state.get(name):
            raise ArtifactError('Recovery approval must name the exact current '+name)
    for kind, name in (('closures', 'closure'), ('briefs', 'brief')):
        leaf, _ = artifacts.leaf(kind, name)
        if leaf != state.get(name+'_ref'):
            raise ArtifactError('Recovery requires the exact current '+name+' artifact and checkpoint')
    # Verify the entire evidence chain, including older intents and closures.
    def verify(value):
        if isinstance(value, dict):
            if 'predecessor_work' in value:
                from .predecessor import validate_link_reference
                validate_link_reference(artifacts.project, value['predecessor_work'])
                value = {k: v for k, v in value.items() if k != 'predecessor_work'}
            if set(value) == {'path', 'revision'}:
                record = artifacts.read(value)
                verify(record)
            else:
                for item in value.values(): verify(item)
        elif isinstance(value, list):
            for item in value: verify(item)
    verify(state)
    require_quiescent(state, artifacts)
    closure = artifacts.read(state['closure_ref'])['payload']
    candidate = decision.get('candidate_revision')
    if not candidate or candidate != state.get('candidate') or candidate != closure.get('candidate_revision') or candidate != digest_tree(state['workspace']):
        raise ArtifactError('Candidate changed or wrong revision; use a separately approved successor')
    return candidate


def approve_recovery(state, decision, artifacts):
    candidate = validate_candidate_recovery(state, decision, artifacts)
    seconds = decision.get('budget_seconds')
    if type(seconds) is not int or not 0 < seconds <= MAX_RECOVERY_SECONDS:
        raise ArtifactError('Recovery requires an explicit new budget_seconds from 1 to 86400')
    decisions = state.get('decision_refs', [])
    ref = artifacts.publish('decisions', f'decision-{len(decisions)+1:04d}', {
        **decision, 'target_ref': state['closure_ref'],
        'authority': 'Independent checks and fresh review of this exact candidate only; no implementation or correction'})
    return {'candidate_reused': True, 'recovery_ref': ref, 'recovery_candidate': candidate,
            'lifecycle_phase': 'delivery', 'decision_refs': [*decisions, ref],
            'deadline': time.time()+seconds, 'budget_seconds': seconds,
            'pause_remaining': None, 'budget_policy': PAUSE_POLICY,
            'resume_epoch': state.get('resume_epoch', 0)+1, 'failure': '',
            'review': {}, 'check': {}, 'findings': [], 'test_results': {}}


def delivery_state(snapshot):
    """An interrupted delivery subgraph has not merged its values into its parent."""
    values = snapshot.values
    for task in snapshot.tasks:
        if hasattr(task.state, 'tasks'):
            nested = delivery_state(task.state)
            if nested.get('deadline') is not None:
                values = nested
    return values


def require_quiescent(state, artifacts):
    """Reject ambiguous native effects and identity-check recorded process scopes."""
    observed = None
    def inspect(value):
        nonlocal observed
        if isinstance(value, dict):
            if 'predecessor_work' in value:
                from .predecessor import validate_link_reference
                validate_link_reference(artifacts.project, value['predecessor_work'])
                value = {k: v for k, v in value.items() if k != 'predecessor_work'}
            if set(value) == {'path', 'revision'}:
                inspect(artifacts.read(value))
                return
            if value.get('scope_uncertain') or value.get('quiescent') is False or value.get('alive') or value.get('signal_errors'):
                raise ArtifactError('Native execution is active or its quiescence is uncertain; inspect original runtime before recovery')
            processes = value.get('processes')
            if processes:
                if observed is None:
                    from .lifecycle import snapshot
                    try: observed = snapshot()
                    except (OSError, ValueError) as error:
                        raise ArtifactError('Cannot establish native process quiescence: '+str(error)) from error
                for pid, identity in processes.items():
                    current = observed.get(int(pid))
                    if not isinstance(identity, dict) or not identity.get('birth'):
                        raise ArtifactError('Native process identity evidence is incomplete')
                    if current and current.get('birth') == identity['birth']:
                        raise ArtifactError('Recorded native execution is still active; recovery not started')
            elif value.get('pid') and value.get('quiescent') is not True:
                raise ArtifactError('Native execution lacks verified quiescence; recovery not started')
            for item in value.values(): inspect(item)
        elif isinstance(value, list):
            for item in value: inspect(item)
    inspect(state)
