"""Attempt-scoped observations. Retrieval and reported application are separate."""
import json
from pathlib import Path
from .evidence import events, final_object

TOOLS = {'search_cards': 'knowledge', 'traverse_cards': 'knowledge', 'read_skill': 'skill', 'load_skill': 'skill', 'read_skills': 'skill', 'search_skills': 'skill'}


def receipt(record, attempt_id):
    observations = []
    requests = {}
    path = Path(record.get('output') or '/nonexistent')
    if path.is_file():
        for event in events(path):
            for content in event.get('message', {}).get('content', []):
                call_id = content.get('id')
                if content.get('type') == 'toolRequest':
                    call = content.get('toolCall', {}).get('value', {})
                    name = call.get('name', '').split('__')[-1]
                    if name in TOOLS:
                        row = {'call_id': call_id, 'tool': name, 'kind': TOOLS[name], 'state': 'unobserved', 'arguments': call.get('arguments')}
                        requests[call_id] = row
                        observations.append(row)
                elif content.get('type') == 'toolResponse' and call_id in requests:
                    result = content.get('toolResult', {})
                    state = 'failed' if result.get('status') != 'success' else 'observed_retrieval'
                    # Only structured explicit empty results establish empty retrieval.
                    payload = result.get('value', {})
                    blocks = result.get('content', []) or (payload.get('content', []) if isinstance(payload, dict) else payload if isinstance(payload, list) else [])
                    values = [payload] if isinstance(payload, dict) else []
                    for block in blocks:
                        try:
                            value = json.loads(block.get('text', ''))
                        except (ValueError, TypeError):
                            continue
                        values.append(value)
                    if state != 'failed' and any(isinstance(value, dict) and any(value.get(k) == [] for k in ('results', 'edges')) for value in values):
                        state = 'empty'
                    requests[call_id]['state'] = state
        reported = final_object(path).get('applied_guidance', [])
    else:
        reported = []
    return {'schema_version': 1, 'attempt_id': attempt_id,
            'supplied_context': record.get('supplied_context', {}),
            'knowledge': {'state': 'available' if record.get('knowledge_attached') else 'unavailable'},
            'skills': {'state': record.get('skill_availability', 'unobserved')},
            'observations': observations, 'agent_reported_application': reported,
            'application_basis': 'agent report only; observed retrieval does not prove application',
            'child_agent_reported_application': record.get('bound_delegation', {}).get('report', {}).get('applied_guidance', []),
            'coverage': 'this attempt parent event stream; absent child observations remain unobserved'}
