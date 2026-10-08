"""Machine-owned local inference capacity; never grants provider permission."""
from pathlib import Path
from flowtoml import read_toml
from execution_contracts import ContractError

DEFAULTS = {'context_tokens': 12288, 'max_context_tokens': 16384,
            'output_tokens': 2048, 'context_reserve': 1024, 'model': ''}


def load_local_machine(path=None):
    path = Path(path) if path is not None else Path.home()/'.flow/user/flow.toml'
    settings = read_toml(path).get('local_machine', {}) if path.is_file() else {}
    if not isinstance(settings, dict) or set(settings)-set(DEFAULTS):
        raise ContractError('local_machine settings contain unsupported fields')
    result = {**DEFAULTS, **settings}
    for field in ('context_tokens', 'max_context_tokens', 'output_tokens', 'context_reserve'):
        if type(result[field]) is not int or result[field] < 1:
            raise ContractError('local_machine '+field+' must be a positive integer')
    if (result['context_tokens'] > result['max_context_tokens']
            or result['output_tokens']+result['context_reserve'] >= result['context_tokens']
            or not isinstance(result['model'], str)):
        raise ContractError('local_machine context/output/reserve or model is invalid')
    return result


def new_local_profile_settings():
    settings = load_local_machine()
    return {name: settings[name] for name in ('context_tokens', 'output_tokens', 'context_reserve')}


def check_local_compatibility(profile, *, model=None, machine=None, required_context=0):
    """Refuse incompatible sealed work without rewriting its approved authority."""
    machine = load_local_machine() if machine is None else machine
    if required_context > profile['context_tokens']:
        raise ContractError('sealed assignment context exceeds effective local context; explicit successor approval required')
    if profile['context_tokens'] > machine['max_context_tokens']:
        raise ContractError('sealed local context exceeds machine capacity; explicit successor approval required')
    if model is not None and machine['model'] and model != machine['model']:
        raise ContractError('sealed local model differs from machine model; explicit successor approval required')
    return machine
