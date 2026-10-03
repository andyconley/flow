"""Mock coordinator for gateway unit tests. Real stock MAF is tested separately."""
import hashlib
import json
from execution_contracts import canonical


def coordinate(envelope, task, on_action, *, on_manager, completed_assignments=None,
               worker_hook=None, **kwargs):
    completed = set(completed_assignments or [])
    workers = {a['assignment_id']: a for a in envelope['logical_assignments'] if a['requirements']['operation'] != 'manage'}
    turn = 0
    while set(workers) - completed:
        turn += 1
        messages = [{'role': 'user', 'text': 'Mock progress'}]
        response = on_manager({'phase': 'progress', 'sequence': turn, 'messages': messages,
                               'prompt_digest': hashlib.sha256(canonical(messages).encode()).hexdigest()})
        try:
            progress = json.loads(response)
        except json.JSONDecodeError:
            if turn >= 3:
                raise __import__('maf_supervisor').MafChildError('mock progress retries exhausted')
            continue
        selected = progress['next_speaker']['answer']
        decision = {'assignment_id': selected, 'task': progress['instruction_or_question']['answer'], 'manager_turn': turn}
        if worker_hook is None:
            result = on_action({**decision, 'sequence': turn, 'attempt_id': envelope['attempt_id']})
        else:
            result = worker_hook(envelope, task, on_action, manager_decision=decision, timeout_s=900)
        if result.get('status') != 'validation_failed':
            completed.add(selected)
    return {'type': 'workflow_finished', 'attempt_id': envelope['attempt_id'], 'summary': 'mock coordination', 'coordination': 'mock', 'status': 'completed', 'outcome': result}


def adapt(worker_hook):
    def supervisor(envelope, task, on_action, **kwargs):
        return coordinate(envelope, task, on_action, worker_hook=worker_hook, **kwargs)
    return supervisor
