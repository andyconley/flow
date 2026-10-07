"""Native local participants behind the existing Flow selection and send ledger."""
from __future__ import annotations
import hashlib
import json
import time
import sys
from pathlib import Path
from functools import partial
from local_agent import LocalAgentPool
from local_agent_workspace import LocalAgentWorkspace
from local_resources import ResourceMonitor
from execution_contracts import ContractError, canonical
from execution_ledger import ExecutionLedger
from local_worker import call_local
from ollama_manager import call_ollama_manager


class NativeLocalAdapter:
    def __init__(self, envelope, *, read_paths, write_paths):
        self.envelope = envelope
        self.profile = envelope['local_agent_profile']
        from local_machine import check_local_compatibility
        check_local_compatibility(self.profile)
        self.workspace_root = Path(envelope['worktree'])
        self.artifact_dir = Path(envelope['checkpoint_dir']).parent
        self.assignments = {a['assignment_id']: a for a in envelope['logical_assignments']}
        self.ledger = ExecutionLedger(self.artifact_dir.parent / 'ledger.sqlite')
        self.action = None
        manifest_path = self.artifact_dir / 'manifest.snapshot.json'
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {'assignments': []}
        declared = {a['id']: a for a in manifest['assignments']}
        scopes = {}
        for key, assignment in self.assignments.items():
            declaration = declared.get(key, {})
            writable = assignment['requirements']['operation'] == 'edit'
            scopes[key] = {'read_paths': declaration.get('read_scopes', read_paths + write_paths),
                           'write_paths': declaration.get('write_scopes', write_paths) if writable else [],
                           'handoff_dependencies': [dependency for dependency in assignment.get('depends_on', [])
                               if self.assignments[dependency]['requirements']['operation'] == 'edit']}
        from delivery_gateway import _run_chartered_test
        job = json.loads((self.artifact_dir / 'job-charter.snapshot.json').read_text())
        self.workspace = LocalAgentWorkspace(self.workspace_root, read_paths=read_paths,
            write_paths=write_paths, artifact_dir=self.artifact_dir,
            assignment_scopes=scopes, authority_callback=self.authority,
            test_callback=lambda: _run_chartered_test(self.workspace_root, job, return_failure_evidence=True))
        self.pool = LocalAgentPool(runtime_python=envelope['maf_runtime']['interpreter'],
            artifact_dir=self.artifact_dir, source_root=Path(__file__).resolve().parents[1],
            num_ctx=self.profile['context_tokens'], num_predict=self.profile['output_tokens'],
            request_timeout=self.profile['request_timeout_seconds'],
            turn_timeout=self.profile['turn_timeout_seconds'],
            context_reserve=self.profile['context_reserve'], max_iterations=sys.maxsize,
            max_function_calls=self.profile['tool_calls'],
            resource_monitor_factory=partial(ResourceMonitor, endpoint='http://127.0.0.1:11434'))

    def authority(self):
        import delivery_cancel
        controller = delivery_cancel.current()
        if controller is not None:
            controller.check()
        from execution_budgets import remaining_runtime
        remaining_runtime(self.envelope)
        self.ledger.assert_owner(self.envelope['attempt_id'], self.envelope['delivery_lead_claim']['generation'])
        snapshot = self.ledger.snapshot(self.envelope['attempt_id'])
        if snapshot['status'] != 'started':
            raise ContractError('Local agent authority is closed')
        if self.action is not None:
            row = next((r for r in snapshot['actions'] if r['request']['action_id'] == self.action['action_id']), None)
            if row is None or row['status'] != 'started':
                raise ContractError('Local tool lacks a live Flow send claim')
        return True

    def __call__(self, binding, action):
        self.action = action
        if binding['provider'] != 'ollama':
            raise ContractError('Retained local-agent profile requires an explicit local selection')
        from local_machine import check_local_compatibility
        check_local_compatibility(self.profile, model=binding['model'])
        self.authority()
        timeout = self.envelope.get('call_budgets', {}).get(action['assignment_id'],
            self.profile['request_timeout_seconds'])
        timeout = min(timeout, self.profile['request_timeout_seconds'])
        turn_timeout = min(self.profile['turn_timeout_seconds'],
            self.envelope.get('limits', {}).get('max_runtime_seconds', self.profile['turn_timeout_seconds']))
        from execution_budgets import remaining_runtime
        remaining = remaining_runtime(self.envelope)
        if remaining is not None:
            turn_timeout = min(turn_timeout, remaining)
        assignment = self.assignments[action['assignment_id']]
        operation = assignment['requirements']['operation']
        events = []
        def observer(event):
            self.authority()
            events.append(event)
            with (self.artifact_dir / ('action-'+action['action_id']+'-observations.jsonl')).open('a') as handle:
                handle.write(json.dumps(event, default=str)+'\n')
            return True
        if operation == 'manage':
            if remaining is not None:
                import math
                timeout = min(timeout, max(1, math.ceil(remaining)))
            monitor_factory = partial(ResourceMonitor, endpoint='http://127.0.0.1:11434')
            try:
                packet = json.loads(action['task'])
            except (TypeError, ValueError) as exc:
                raise ContractError('Native manager task lacks its sealed conversation packet') from exc
            if not isinstance(packet, dict) or set(packet) != {'phase', 'messages', 'flow_authority'}:
                raise ContractError('Native manager conversation packet fields are invalid')
            phase = packet['phase']
            if phase not in {'facts', 'plan', 'progress', 'replan_facts', 'replan_plan', 'final'}:
                raise ContractError('Native manager phase is invalid')
            authority = packet['flow_authority']
            if not isinstance(authority, dict) or set(authority) != {'completed', 'frontier'}:
                raise ContractError('Native manager authority packet is invalid')
            for identities in authority.values():
                if (not isinstance(identities, list) or len(set(identities)) != len(identities)
                        or any(not isinstance(item, str) or item not in self.assignments for item in identities)):
                    raise ContractError('Native manager authority identities are invalid')
            messages = packet['messages']
            if not isinstance(messages, list) or not messages:
                raise ContractError('Native manager conversation is absent')
            for message in messages:
                if (not isinstance(message, dict) or message.get('role') not in {'system', 'user', 'assistant', 'tool'}
                        or not isinstance(message.get('content'), str)):
                    raise ContractError('Native manager conversation role/content is invalid')
            frontier = authority['frontier'] or authority['completed']
            note = 'Flow observed completed assignments: '+canonical(authority['completed'])+'.'
            if phase == 'progress':
                note += (' Flow permits next_speaker.answer only from '+canonical(frontier)
                         +'. Set is_request_satisfied.answer=false while unfinished assignments remain.')
            native_messages = [*messages, {'role': 'system', 'content': note}]
            if phase == 'progress':
                result = call_ollama_manager(messages,
                    model=binding['model'], attempt_id=action['attempt_id'],
                    timeout_seconds=timeout,
                    preserve_observed_invalid=True, allowed_speakers=frontier,
                    local_agent_profile=self.profile, observer=observer, phase=phase,
                    native_messages=[{'role': 'system', 'content': assignment['instructions']}, *native_messages],
                    resource_monitor_factory=monitor_factory)
            else:
                result = call_local({'provider': 'ollama', 'model': binding['model'],
                    'attempt_id': action['attempt_id'], 'instructions': assignment['instructions'], 'task': action['task']},
                    timeout_seconds=timeout, chat_messages=native_messages,
                    local_agent_profile=self.profile, observer=observer, resource_monitor_factory=monitor_factory)
            evidence = {'session_id': 'stock-manager-'+action['action_id'], 'events': events,
                'model_requests': [e for e in events if e['type']=='model_request'],
                'model_sends': [e for e in events if e['type']=='model_send'],
                'model_responses': [e for e in events if e['type']=='model_response'], 'tool_observations': []}
            return {**result, 'local_agent_observations': evidence}
        tools = ['read_files', 'run_tests']
        instructions = assignment['instructions'] + '\nUse your native tools on the actual source. Separate sessions hold each assignment history.'
        if operation == 'edit':
            tools += ['write_file', 'submit_handoff', 'read_handoff']
            instructions += '\nImplement the approved change, run tests, and repair failures. Submit a concrete handoff when complete.'
        elif operation == 'verify':
            tools += ['submit_review']
            instructions += '\nRead every current source file, run the approved tests, and submit_review with actual findings. You have read-only authority.'
        packet = action['task'] + '\nAuthorized scope: '+canonical(self.workspace._scopes(action['assignment_id']))
        packet += '\nCurrent source hashes: '+canonical(self.workspace._snapshot())
        if assignment.get('depends_on') and operation == 'edit':
            packet += '\nRead the preceding specialist handoff before integrating its source.'
        producer_dependencies = [key for key in assignment.get('depends_on', [])
                                 if self.assignments[key]['requirements']['operation'] == 'edit']
        dependent_producers = [a for a in self.assignments.values()
                               if operation == 'edit' and action['assignment_id'] in a.get('depends_on', [])
                               and a['requirements']['operation'] == 'edit']
        def tool(name, args):
            if name == 'write_file' and producer_dependencies:
                observed = {h['producer'] for h in self.workspace.handoff_reads.get(action['assignment_id'], [])}
                if not set(producer_dependencies) <= observed:
                    return {'status': 'denied', 'reason': 'Read the preceding specialist handoff before writing integration source'}
            return self.workspace.callback(action['assignment_id'], name, args)
        result = self.pool.run(action['assignment_id'], instructions, packet,
            tool,
            model=binding['model'], tools=tools, observer=observer,
            request_timeout=timeout, turn_timeout=turn_timeout)
        evidence = dict(result)
        if operation == 'edit':
            writes = [e for e in result['tool_observations'] if e.get('name') == 'write_file'
                      and e.get('result', {}).get('status') == 'written']
            if not writes:
                return {**result, 'observed_invalid': True, 'detail': 'Producer completed without an observed source write', 'local_agent_observations': evidence}
            if dependent_producers and action['assignment_id'] not in self.workspace.handoffs:
                return {**result, 'observed_invalid': True, 'detail': 'Producer completed without the required current-source specialist handoff', 'local_agent_observations': evidence}
        if operation == 'verify':
            review = self.workspace.reviews.get(action['assignment_id'])
            if review is None or review['source_digest'] != self.workspace.current_source_digest:
                return {**result, 'observed_invalid': True, 'detail': 'Reviewer did not submit current-source findings', 'local_agent_observations': evidence}
            result = {**result, 'output': canonical(review['candidate']), 'current_source_review': review,
                      'model_output': result['output']}
        return {**result, 'provider': 'ollama', 'model': binding['model'], 'physical_call': bool(evidence['model_sends']),
                'local_agent_observations': evidence}

    def close(self):
        self.pool.close()
