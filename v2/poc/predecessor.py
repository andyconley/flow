"""Validated historical linkage between distinct work items; never execution authority."""
from contextlib import contextmanager
import fcntl
from pathlib import Path
from .artifacts import ArtifactError, Artifacts, identifier


def validate_link_reference(project, link):
    if not isinstance(link, dict) or link.get('approval_imported') is not False:
        raise ArtifactError('Predecessor linkage must explicitly exclude approval import')
    store = Artifacts(project, identifier(link.get('work_id')))
    record = store.read(link.get('closure_ref'))
    if record['kind'] != 'closures' or record['id'] != 'closure':
        raise ArtifactError('Predecessor linkage requires a closure artifact')
    return record


@contextmanager
def validated_predecessor(project, new_work, work, revision, state_dir, read_snapshot):
    """Hold the existing predecessor operator lock through successor creation."""
    identifier(work)
    if work == new_work:
        raise ArtifactError('Predecessor must be a distinct work item')
    state_dir = Path(state_dir)
    lock = state_dir/'operator.lock'
    if not lock.is_file() or not (state_dir/'workflow.sqlite').is_file():
        raise ArtifactError('Predecessor requires an existing native checkpoint and operator lock')
    # Read mode is deliberate: missing predecessor state is never created.
    with lock.open('r') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ArtifactError('Predecessor has an active operator; wait before linking')
        try:
            snapshot = read_snapshot()
            state = snapshot.values
            def pending(current):
                return any(task.interrupts or (hasattr(task.state, 'tasks') and pending(task.state))
                           for task in current.tasks)
            if state.get('work_id') != work or state.get('lifecycle_phase') != 'closed' or snapshot.next or pending(snapshot):
                raise ArtifactError('Predecessor must be a closed quiescent native work item')
            reference = state.get('closure_ref')
            if not reference or reference.get('revision') != revision:
                raise ArtifactError('Predecessor revision must match the exact current closure')
            store = Artifacts(project, work)
            current, _ = store.leaf('closures', 'closure')
            if current != reference:
                raise ArtifactError('Predecessor closure and checkpoint disagree; inspect before linking')
            link = {'work_id': work, 'closure_ref': reference, 'approval_imported': False,
                    'quiescence': 'Closed checkpoint observed under operator lock; historical linkage grants no execution authority'}
            validate_link_reference(project, link)
            yield link
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)
