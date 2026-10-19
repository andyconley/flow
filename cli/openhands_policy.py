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
    if not isinstance(profile, dict):
        return ['runtime profile must be a table']
    reasons = []
    if ('sdk_tool_calling' not in candidate.get('capabilities', [])
            and candidate.get('sdk_tool_use') not in {'user-enabled-unverified', 'default-enabled-unverified'}):
        reasons.append('SDK tool use is neither declared nor explicitly user-enabled')
    context = profile.get('max_input_tokens')
    if isinstance(context, bool) or not isinstance(context, int) or context < SDK_MIN_CONTEXT:
        reasons.append(f'configured SDK context must be at least {SDK_MIN_CONTEXT} tokens')
    return reasons



def specialist_selections(root, parent, config, *, user_overlay=USER_OVERLAY_DIR, diagnostics=None):
    from openhands_config import FRAMEWORK_ROLES, RuntimeConfigurationError, select, identifier
    from sync import merge_user_overlay, shared_agents
    framework = read_toml(FRAMEWORK_ROLES.parent / 'flow.toml')
    admin = read_toml(user_overlay / 'flow.toml') if (user_overlay / 'flow.toml').is_file() else {}
    project_path = root / '.flow/flow.toml'
    project = read_toml(project_path) if project_path.is_file() else {}
    policy = merge_selection_policy(framework.get('provider_selection', {}),
                                   admin.get('provider_selection'), project.get('provider_selection'))
    for layer in (admin, project):
        entries = layer.get('provider_candidates', [])
        if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
            raise RuntimeConfigurationError('provider_candidates must be an array of tables')
        for item in entries:
            identifier(item.get('candidate_id'), 'candidate ID')
    explicit_disables = {item.get('candidate_id') for layer in (admin, project)
                         for item in layer.get('provider_candidates', [])
                         if isinstance(item, dict) and item.get('enabled') is False}
    if explicit_disables:
        policy = {**policy, 'disabled_candidates': sorted(set(policy['disabled_candidates']) | explicit_disables)}
        policy.pop('policy_digest', None)
    catalog = project.get('provider_candidates', admin.get('provider_candidates', framework.get('provider_candidates', [])))
    if not isinstance(catalog, list) or any(not isinstance(item, dict) for item in catalog):
        raise RuntimeConfigurationError('provider_candidates must be an array of tables')
    candidate_ids = [identifier(item.get('candidate_id'), 'candidate ID') for item in catalog]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise RuntimeConfigurationError('provider candidate IDs must be unique')
    order_layers = [layer.get('provider_selection', {}).get('provider_order') for layer in (admin, project)
                    if 'provider_order' in layer.get('provider_selection', {})]
    framework_order = framework.get('provider_selection', {}).get('provider_order')
    # A single stated order is always a deliberate pin, even if it happens to
    # match the framework default. But when every layer that states it
    # restates the identical framework default, that is evidence of a stale
    # full-file copy (e.g. an old full-overlay install), not a real choice,
    # and must not silently mask role-specific hosted_preferences below.
    explicit_order = bool(order_layers) and (len(order_layers) == 1 or any(order != framework_order for order in order_layers))
    preferences = dict(framework.get('implementation_routing', {}).get('hosted_preferences', {}))
    for layer in (admin, project):
        preferences.update(layer.get('implementation_routing', {}).get('hosted_preferences', {}))
    _, manifest = merge_user_overlay(FRAMEWORK_ROLES.parent, user_overlay=user_overlay)
    declarations = {a['name']: a for a in shared_agents(manifest)}
    roster = parent.role_options.get('specialists', list(declarations))
    if not isinstance(roster, list) or len(set(roster)) != len(roster):
        raise RuntimeConfigurationError('implementation specialists must be a unique role list')
    result = {}
    diagnostics = diagnostics if diagnostics is not None else []
    for role in roster:
        options = config.get('roles', {}).get(role, {})
        if 'profile' in options:
            child = select(root, 'implement', role, options['profile'], config=config, user_overlay=user_overlay)
            matching = [item for item in catalog if item.get('runtime_profile', item.get('provider')) == options['profile']]
            if matching:
                eligible = select_candidate({'operation': 'edit', 'minimum_tier': declarations.get(role, {}).get('model_tier', 'working')},
                    policy, matching, [{'candidate_id': item['candidate_id'], 'state': 'ready'} for item in matching])
                if eligible['selected_candidate_id'] is None:
                    raise RuntimeConfigurationError(f'explicit role profile {role} is excluded: {eligible["exclusions"]}')
            if child.provider['kind'] == 'local':
                reasons = local_eligibility({'sdk_tool_use': 'user-enabled-unverified'}, child.provider)
                if reasons:
                    raise RuntimeConfigurationError(f'explicit local role profile {role} is excluded: {reasons}')
            diagnostics.append({'role': role, 'resolved_profile': child.profile, 'reason': 'explicit role profile'})
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
                reasons = []
                if candidate.get('enabled') is False:
                    reasons.append('candidate disabled')
                if provider == 'ollama':
                    reasons.extend(local_eligibility(candidate, profiles.get(profile, {})))
                    if config.get('_local_configuration_error'):
                        reasons.append(config['_local_configuration_error'])
                if profile not in profiles:
                    reasons.append('runtime profile is not configured')
                elif not isinstance(profiles[profile], dict) or profiles[profile].get('kind') != ('local' if provider == 'ollama' else provider):
                    reasons.append('runtime profile kind does not match provider')
                if not reasons:
                    try:
                        select(root, 'implement', role, profile, config=config, user_overlay=user_overlay)
                    except (ValueError, OSError) as exc:
                        reasons.append(str(exc))
                if reasons:
                    diagnostics.append({'role': role, 'candidate_id': candidate.get('candidate_id'), 'reasons': reasons})
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
            diagnostics.append({'role': role, 'resolved_profile': chosen['_profile'] if chosen else None, 'decision': decision})
            if chosen is None:
                raise RuntimeConfigurationError(f'no policy-eligible SDK specialist provider for {role}: {diagnostics}; configure an explicit role profile or eligible candidate')
            for candidate in candidates:
                eligibility = select_candidate(requirements, role_policy, [candidate],
                    [{'candidate_id': candidate['candidate_id'], 'state': 'ready'}])
                if eligibility['selected_candidate_id'] is None:
                    diagnostics.append({'role': role, 'candidate_id': candidate['candidate_id'], 'reasons': [eligibility]})
                    continue
                option = select(root, 'implement', role, candidate['_profile'], config=config, user_overlay=user_overlay)
                target = f"{role}--{candidate['candidate_id']}"
                if target in roster:
                    raise RuntimeConfigurationError(f'provider target collides with a logical role: {target}')
                result[target] = option
            child = select(root, 'implement', role, chosen['_profile'], config=config, user_overlay=user_overlay)
        # A worker cannot become another coordinator through its configuration.
        if child.provider['kind'] == 'openai-subscription':
            raise RuntimeConfigurationError('subscription coordinator profiles cannot be specialist worker bindings')
        result[role] = child
    for name, child in result.items():
        options = {**child.role_options, 'specialists': []}
        options['tools'] = [tool for tool in options.get('tools', ['terminal', 'file_editor']) if tool != 'task']
        options.pop('model_routing', None)
        options.pop('policy_dispatch', None)
        result[name] = replace(child, role_options=options, profile_override=True, routing_profiles={})
    if not result:
        raise RuntimeConfigurationError('implementation coordinator requires at least one approved specialist')
    return result


def subscription_readiness():
    import os
    directory = Path(os.environ.get('OH_PERSISTENCE_DIR', str(Path.home() / '.openhands'))) / 'auth'
    return {'credential_file_present': (directory / 'openai_oauth.json').is_file(),
            'authenticated': 'not checked; no credentials read or refreshed',
            'next_action': 'Human: use OpenHands SDK LLM.subscription_login(vendor="openai", model="gpt-5.6-terra") in an interactive Python terminal. Do not copy native CLI credentials.'}
