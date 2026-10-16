"""Deterministic specialist bindings for SDK-owned implementation coordination.

No provider discovery, authentication, model calls or lifecycle writes occur here.
"""
from dataclasses import replace
from pathlib import Path
from flowtoml import read_toml
from paths import USER_OVERLAY_DIR
from provider_selection import merge_selection_policy, select_candidate

# Pinned SDK 1.54 rejects smaller windows before a model call.
SDK_MIN_CONTEXT = 16384


def local_eligibility(candidate, profile):
    reasons = []
    if ('sdk_tool_calling' not in candidate.get('capabilities', [])
            and candidate.get('sdk_tool_use') != 'user-enabled-unverified'):
        reasons.append('SDK tool use is neither declared nor explicitly user-enabled')
    context = profile.get('max_input_tokens')
    if context is None or context < SDK_MIN_CONTEXT:
        reasons.append(f'configured SDK context must be at least {SDK_MIN_CONTEXT} tokens')
    return reasons



def specialist_selections(root, parent, config, *, user_overlay=USER_OVERLAY_DIR):
    from openhands_config import FRAMEWORK_ROLES, RuntimeConfigurationError, select
    from sync import merge_user_overlay, shared_agents
    framework = read_toml(FRAMEWORK_ROLES.parent / 'flow.toml')
    admin = read_toml(user_overlay / 'flow.toml') if (user_overlay / 'flow.toml').is_file() else {}
    project_path = root / '.flow/flow.toml'
    project = read_toml(project_path) if project_path.is_file() else {}
    policy = merge_selection_policy(framework.get('provider_selection', {}),
                                   admin.get('provider_selection'), project.get('provider_selection'))
    catalog = admin.get('provider_candidates', framework.get('provider_candidates', []))
    explicit_order = any('provider_order' in layer.get('provider_selection', {})
                         for layer in (admin, project))
    preferences = dict(framework.get('implementation_routing', {}).get('hosted_preferences', {}))
    for layer in (admin, project):
        preferences.update(layer.get('implementation_routing', {}).get('hosted_preferences', {}))
    _, manifest = merge_user_overlay(FRAMEWORK_ROLES.parent, user_overlay=user_overlay)
    declarations = {a['name']: a for a in shared_agents(manifest)}
    roster = parent.role_options.get('specialists', list(declarations))
    if not isinstance(roster, list) or len(set(roster)) != len(roster):
        raise RuntimeConfigurationError('implementation specialists must be a unique role list')
    result = {}
    for role in roster:
        options = config.get('roles', {}).get(role, {})
        if 'profile' in options:
            child = select(root, 'implement', role, options['profile'], config=config, user_overlay=user_overlay)
        else:
            declaration = declarations.get(role)
            if declaration is None:
                raise RuntimeConfigurationError(f'custom specialist {role} requires an explicit role profile')
            candidates = []
            profiles = dict(config.get('profiles', {}))
            for item in catalog:
                candidate = dict(item)
                provider = candidate.get('provider')
                profile = candidate.get('runtime_profile', provider)
                if provider == 'ollama':
                    # Historical structured-edit grants do not authorize SDK tools.
                    if profile not in profiles or local_eligibility(candidate, profiles[profile]):
                        continue
                if profile not in profiles:
                    continue
                kind = profiles[profile].get('kind')
                if kind != ('local' if provider == 'ollama' else provider):
                    continue
                candidate['_profile'] = profile
                candidates.append(candidate)
            requirements = {'operation': 'edit', 'minimum_tier': declaration.get('model_tier', 'working')}
            role_policy = policy
            preferred = preferences.get(role)
            if not explicit_order and preferred in {'claude', 'codex'}:
                other = 'codex' if preferred == 'claude' else 'claude'
                role_policy = {**policy, 'provider_order': ['ollama', preferred, other]}
                role_policy.pop('policy_digest', None)
            decision = select_candidate(requirements, role_policy, candidates,
                [{'candidate_id': c['candidate_id'], 'state': 'ready'} for c in candidates])
            chosen = next((c for c in candidates if c['candidate_id'] == decision['selected_candidate_id']), None)
            if chosen is None:
                raise RuntimeConfigurationError(f'no policy-eligible SDK specialist provider for {role}; configure an explicit role profile or eligible candidate')
            child = select(root, 'implement', role, chosen['_profile'], config=config, user_overlay=user_overlay)
            if child.provider['kind'] == 'local':
                hosted = next((c for entry in decision['ordered_candidates'] for c in candidates
                    if c['candidate_id'] == entry['candidate_id'] and c['provider'] in {'claude', 'codex'}), None)
                if hosted:
                    fallback = select(root, 'implement', role, hosted['_profile'], config=config, user_overlay=user_overlay)
                    child = replace(child, role_options={**child.role_options,
                        '_hosted_fallback': hosted['_profile'], '_hosted_fallback_binding': fallback.fingerprint()})
        # A worker cannot become another coordinator through its configuration.
        if child.provider['kind'] == 'openai-subscription':
            raise RuntimeConfigurationError('subscription coordinator profiles cannot be specialist worker bindings')
        options = {**child.role_options, 'specialists': []}
        options['tools'] = [t for t in options.get('tools', ['terminal', 'file_editor']) if t != 'task']
        options.pop('model_routing', None)
        options.pop('policy_dispatch', None)
        result[role] = replace(child, role_options=options, profile_override=True, routing_profiles={})
    if not result:
        raise RuntimeConfigurationError('implementation coordinator requires at least one approved specialist')
    return result


def subscription_readiness():
    import os
    directory = Path(os.environ.get('OH_PERSISTENCE_DIR', str(Path.home() / '.openhands'))) / 'auth'
    return {'credential_file_present': (directory / 'openai_oauth.json').is_file(),
            'authenticated': 'not checked; no credentials read or refreshed',
            'next_action': 'Human: use OpenHands SDK LLM.subscription_login(vendor="openai", model="gpt-5.6-terra") in an interactive Python terminal. Do not copy native CLI credentials.'}
