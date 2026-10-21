"""Informational device context and Ollama options; never an execution/usage gate."""
import os
from pathlib import Path
import tomllib


def settings(project=None, model=None, home=None):
    home = Path(home or Path.home())
    project = Path(project or Path.cwd())
    profiles, origins, warnings = {}, {}, []
    machine = {}
    for path in [home/'.flow/user/flow.toml', home/'.flow/user/runtime.toml', project/'.flow/runtime.toml']:
        if not path.is_file():
            continue
        try:
            data = tomllib.loads(path.read_text())
        except (OSError, ValueError) as error:
            warnings.append(f'{path}: {error}')
            continue
        # Hardware capacity belongs to the user/device overlay, not a project.
        capacity = data.get('local_machine', {}) if path == home/'.flow/user/flow.toml' else {}
        if isinstance(capacity, dict):
            machine.update(capacity)
        else:
            warnings.append(f'{path}: local_machine must be a table; ignored')
        entries = data.get('profiles', {})
        if not isinstance(entries, dict):
            warnings.append(f'{path}: profiles must be a table; ignored')
            continue
        for name, value in entries.items():
            if not isinstance(value, dict):
                warnings.append(f'{path}: invalid profile {name}; ignored')
                continue
            profiles[name] = {**profiles.get(name, {}), **value}
            origins[name] = str(path)
    local = {name: row for name, row in profiles.items() if row.get('kind') == 'local'
             and isinstance(row.get('model'), str) and row['model'].startswith(('ollama/', 'ollama_chat/'))}
    normalized = lambda value: value.removeprefix('ollama_chat/').removeprefix('ollama/')
    matching = {name: row for name, row in local.items() if model and normalized(row['model']) == normalized(model)}
    candidates = matching or local
    valid = lambda value: type(value) is int and value > 0
    windows = {row['max_input_tokens'] for row in candidates.values() if valid(row.get('max_input_tokens'))}
    if any(row.get('max_input_tokens') is not None and not valid(row['max_input_tokens']) for row in candidates.values()):
        warnings.append('Invalid local profile context; no invalid value is applied')
    context = next(iter(windows)) if len(windows) == 1 else machine.get('context_tokens')
    source = ', '.join(sorted({origins[name] for name in candidates})) if len(windows) == 1 else 'local_machine' if context else 'provider_default'
    if len(windows) > 1 and context is None:
        warnings.append('Local profiles have different context windows; no arbitrary shared override selected')
    explicit = os.environ.get('GOOSE_INPUT_LIMIT')
    if explicit:
        try:
            context = int(explicit)
            source = 'GOOSE_INPUT_LIMIT'
        except ValueError:
            warnings.append('Invalid GOOSE_INPUT_LIMIT; provider default retained')
            context = None
    if context is not None and not valid(context):
        warnings.append('Invalid local context window; provider default retained')
        context = None
    if context and valid(machine.get('max_context_tokens')) and context > machine['max_context_tokens']:
        warnings.append('Profile context exceeds declared device capacity; inspect the profile/device settings. No usage gate or automatic clamp was added')
    valid_output = lambda value: type(value) is int and (value == -1 or value > 0)
    outputs = {row.get('max_output_tokens') for row in candidates.values() if valid_output(row.get('max_output_tokens'))}
    condensers = {row.get('condenser_max_tokens') for row in candidates.values() if valid(row.get('condenser_max_tokens'))}
    return {'context_tokens': context, 'source': source, 'profiles': list(candidates),
            'output_tokens': next(iter(outputs)) if len(outputs) == 1 else machine.get('output_tokens'),
            'legacy_condenser_tokens': next(iter(condensers)) if len(condensers) == 1 else None,
            'context_reserve': machine.get('context_reserve'), 'warnings': warnings,
            'native_context_owner': 'native client; occupancy/compaction may be unavailable',
            'enforcement': 'provider context configuration only; no token/rate/usage gate'}


def ollama_environment(project=None, model=None, provider=None):
    value = settings(project, model)
    result = {}
    if value['context_tokens']:
        # Goose's Ollama provider maps this to num_ctx AND its context resolver.
        result['GOOSE_INPUT_LIMIT'] = str(value['context_tokens'])
    if provider == 'ollama' and type(value['output_tokens']) is int and (value['output_tokens'] == -1 or value['output_tokens'] > 0):
        # The shipped Goose validator rejects -1. Omitting its output override
        # preserves Ollama's open-ended default for non-canonical local models.
        if value['output_tokens'] > 0:
            result['GOOSE_MAX_TOKENS'] = str(value['output_tokens'])
        if value['context_tokens'] and value['legacy_condenser_tokens']:
            ratio = value['legacy_condenser_tokens']/value['context_tokens']
            if 0 < ratio < 1:
                result['GOOSE_AUTO_COMPACT_THRESHOLD'] = str(ratio)
    return result
