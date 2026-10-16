"""Flow-owned specialist and endpoint selection; execution belongs to OpenHands."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit
import hashlib
import json
import re

from flowtoml import read_toml
from paths import USER_OVERLAY_DIR

SDK_VERSION = "1.54.0"
STAGES = {
    "define": ("start-definition", "defining", "business-analyst"),
    "solution": ("start-solution", "solutioning", "solution-architect"),
    "plan": ("start-plan", "planning", "lead-developer"),
    "implement": ("start-implementation", "implementing", "lead-developer"),
    "review": ("start-review", "reviewing", "quality-reviewer"),
}
OUTPUTS = {
    "define": {"requirements": "requirements.md", "acceptance_criteria": "acceptance-criteria.md"},
    "solution": {"solution": "solution.md"},
    "plan": {"plan": "plan.md", "handoff": "handoff.md", "validation_plan": "validation-plan.md"},
    "implement": {"implementation_evidence": "implementation-evidence.md", "handback": "handback.md"},
    "review": {"review": "review.md"},
}
FRAMEWORK_ROLES = Path(__file__).resolve().parent.parent / "scaffolds/default/agents"


class RuntimeConfigurationError(ValueError):
    pass


def provision_native_profiles(user_overlay: Path) -> str:
    """Add usable interactive routes without choosing a provider or granting access."""
    path = user_overlay / "runtime.toml"
    user_overlay.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x") as stream:
            stream.write('# Native subscriptions; select explicitly with --profile claude or codex.\n'
                         '# No default provider or automated permission acknowledgement is set.\n'
                         '# Model defaults follow the canonical Flow role policy.\n'
                         '[profiles.claude]\nkind = "claude"\nsession_mode = "default"\n\n'
                         '[profiles.codex]\nkind = "codex"\nsession_mode = "agent"\n')
    except FileExistsError:
        return f"runtime profiles preserved: {path}"
    return f"interactive native profiles installed: {path}; select --profile claude or codex; execution requires explicit terminal approvals; headless execution is refused"


def _merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        result[key] = _merge(result[key], value) if isinstance(result.get(key), dict) and isinstance(value, dict) else value
    return result


def load_config(root: Path, user_overlay: Path = USER_OVERLAY_DIR) -> dict:
    config = {'profiles': {
        'claude': {'kind': 'claude', 'session_mode': 'default'},
        'codex': {'kind': 'codex', 'session_mode': 'agent'},
        'openhands-coordinator': {'kind': 'openai-subscription'},
    }}
    from local_machine import load_local_machine
    machine = load_local_machine(user_overlay / 'flow.toml')
    if machine['model']:
        config['profiles']['ollama'] = {'kind': 'local', 'model': 'ollama_chat/' + machine['model'],
            'base_url': 'http://127.0.0.1:11434', 'max_input_tokens': machine['context_tokens'],
            'max_output_tokens': machine['output_tokens'],
            'condenser_max_tokens': machine['context_tokens'] - machine['output_tokens'] - machine['context_reserve']}
    for path in (user_overlay / "runtime.toml", root / ".flow/runtime.toml"):
        if path.is_file():
            config = _merge(config, read_toml(path))
    if 'default_profile' not in config:
        config.setdefault('stages', {}).setdefault('implement', {}).setdefault('profile', 'openhands-coordinator')
    return config


def identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value) or value in {".", ".."}:
        raise RuntimeConfigurationError(f"invalid {label}: {value!r}")
    return value


@dataclass(frozen=True)
class Selection:
    role: str
    profile: str
    provider: dict
    role_file: Path
    role_options: dict
    workspace: dict
    profile_override: bool = False
    routing_profiles: dict = field(default_factory=dict)

    def fingerprint(self) -> str:
        binding = {"role": self.role, "profile": self.profile, "provider": self.provider,
                   "role_text": self.role_file.read_text(), "options": self.role_options,
                   "workspace": self.workspace}
        if self.role_options.get("model_routing") or self.provider.get('kind') == 'openai-subscription' or self.role_options.get('policy_dispatch'):
            binding["profile_override"] = self.profile_override
            binding["routing_profiles"] = self.routing_profiles
        return hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()


def select(root: Path, stage: str, role: str | None = None, profile: str | None = None,
           *, config: dict | None = None, user_overlay: Path = USER_OVERLAY_DIR) -> Selection:
    coordinator_request = stage == 'implement' and role is None
    profile_override = profile is not None
    config = load_config(root, user_overlay) if config is None else config
    stage_options = config.get("stages", {}).get(stage, {})
    role = identifier(role or stage_options.get("role", STAGES[stage][2]), "role")
    options = config.get("roles", {}).get(role, {})
    if profile is None:
        if coordinator_request:
            profile = stage_options.get("profile", config.get("default_profile", ""))
        elif "profile" in options:
            profile = options["profile"]
        elif "profile" in stage_options:
            profile = stage_options["profile"]
        else:
            profile = config.get("default_profile", "")
    if not profile:
        raise RuntimeConfigurationError("invalid profile: No runtime profile selected. Use --profile claude or codex for a configured native route, or configure a self-hosted default_profile in .flow/runtime.toml. Missing configuration never enables host fallback.")
    profile = identifier(profile, "profile")
    provider = config.get("profiles", {}).get(profile)
    if not isinstance(provider, dict):
        raise RuntimeConfigurationError(f"profile {profile!r} is not configured in .flow/runtime.toml")
    kind = provider.get("kind")
    if kind == "local":
        if "reasoning_effort" in provider and (not isinstance(provider["reasoning_effort"], str) or not provider["reasoning_effort"].strip()):
            raise RuntimeConfigurationError("reasoning_effort must be a nonempty provider-supported string")
        url = urlsplit(provider.get("base_url", ""))
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
            raise RuntimeConfigurationError("local profiles require an explicit compatible base_url without embedded credentials")
        if url.hostname in {"api.openai.com", "api.anthropic.com"}:
            raise RuntimeConfigurationError("paid vendor APIs are not a Flow runtime provider; use an existing native subscription")
        model = provider.get("model", "")
        if not isinstance(model, str) or not model.startswith(("openai/", "ollama/", "ollama_chat/")):
            raise RuntimeConfigurationError("local model must use openai/, ollama/, or ollama_chat/ with an explicit self-hosted endpoint")
        for name in ("max_input_tokens", "max_output_tokens", "condenser_max_tokens"):
            value = provider.get(name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value <= 0):
                raise RuntimeConfigurationError(f"{name} must be a positive integer")
        key_env = provider.get("api_key_env")
        if key_env and (not re.fullmatch(r"[A-Z][A-Z0-9_]*", key_env) or key_env in {"OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"}):
            raise RuntimeConfigurationError("use a dedicated self-hosted credential environment variable")
        if "api_key" in provider:
            raise RuntimeConfigurationError("do not persist credentials in runtime.toml; use api_key_env")
    elif kind == 'openai-subscription':
        if stage != 'implement':
            raise RuntimeConfigurationError('subscription coordinator is for implementation; shaping stays in the native host')
        if set(provider) - {'kind', 'model', 'reasoning_effort'}:
            raise RuntimeConfigurationError('subscription coordinator accepts only model and reasoning_effort; no API credentials or endpoint overrides')
    elif kind not in {"codex", "claude"}:
        raise RuntimeConfigurationError("profile kind must be local, openai-subscription, codex, or claude")
    from sync import merge_user_overlay, shared_agents
    _, manifest = merge_user_overlay(FRAMEWORK_ROLES.parent, user_overlay=user_overlay)
    declaration = next((a for a in shared_agents(manifest) if a["name"] == role), None)
    provider = dict(provider)
    if kind == 'openai-subscription':
        from model_policy import runtime_policy_for_agent
        policy = runtime_policy_for_agent(manifest, 'codex', declaration or {})
        provider.setdefault('model', policy.get('model', 'gpt-5.6-terra'))
        provider.setdefault('reasoning_effort', policy.get('model_reasoning_effort', 'medium'))
    if kind in {"codex", "claude"}:
        provider.setdefault("permission_requests", "interactive")
        if provider["permission_requests"] not in {"interactive", "stock-openhands"}:
            raise RuntimeConfigurationError("permission_requests must be interactive or explicitly acknowledged stock-openhands")
    if kind in {"codex", "claude"} and declaration:
        from model_policy import runtime_policy_for_agent
        policy = runtime_policy_for_agent(manifest, kind, declaration)
        if policy.get("model"):
            provider.setdefault("model", policy["model"])
    declared_file = declaration["_root"] / declaration["source"] if declaration else FRAMEWORK_ROLES / f"{role}.md"
    candidates = [root / ".flow/agents" / f"{role}.md", root / ".agents/agents" / f"{role}.md",
                  user_overlay / "agents" / f"{role}.md", declared_file, FRAMEWORK_ROLES / f"{role}.md"]
    if options.get("file"):
        candidates.insert(0, root / options["file"])
    role_file = next((p.resolve() for p in candidates if p.is_file()), None)
    if role_file is None:
        raise RuntimeConfigurationError(f"specialist definition not found: {role}")
    tools = options.get("tools", ["terminal", "file_editor", "task"])
    if not isinstance(tools, list) or any(t not in {"terminal", "file_editor", "task_tracker", "task"} for t in tools):
        raise RuntimeConfigurationError("role tools must be a list of terminal, file_editor, task_tracker, task")
    specialists = options.get("specialists")
    if specialists is not None:
        if not isinstance(specialists, list) or any(not isinstance(name, str) for name in specialists):
            raise RuntimeConfigurationError("specialists must be a list of role names")
        for name in specialists:
            identifier(name, "specialist")
        if len(set(specialists)) != len(specialists):
            raise RuntimeConfigurationError("specialist names must be unique")
    if options.get("specialists") and "task" not in tools:
        raise RuntimeConfigurationError("a specialist roster requires the SDK task tool")
    routing_profiles = {}
    routing = options.get("model_routing")
    if routing is not None:
        if kind != "local" and not profile_override:
            raise RuntimeConfigurationError("model_routing switches SDK LLMs; native specialists use role profile bindings")
        if not isinstance(routing, dict) or not isinstance(routing.get("categories"), list) or not routing["categories"]:
            raise RuntimeConfigurationError("model_routing requires classifier_profile and nonempty categories")
        names = [routing.get("classifier_profile")]
        for entry in routing["categories"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("description"), str) or not entry["description"].strip():
                raise RuntimeConfigurationError("routing categories require description and profile")
            names.append(entry.get("profile"))
        for name in names:
            identifier(name, "routing profile")
            if config.get("profiles", {}).get(name, {}).get("kind") != "local":
                raise RuntimeConfigurationError(f"routing profile {name!r} must be a configured local LLM; use a specialist for native execution")
            routing_profiles[name] = dict(config["profiles"][name])
    workspace = config.get("workspace", {"kind": "local"})
    if workspace.get("kind", "local") not in {"local", "remote"}:
        raise RuntimeConfigurationError("workspace kind must be local or remote")
    if workspace.get("kind") == "remote" and not workspace.get("host"):
        raise RuntimeConfigurationError("remote workspace needs an existing OpenHands agent-server host")
    if workspace.get("confirmation") not in {None, "always"}:
        raise RuntimeConfigurationError("workspace confirmation must be always, or omitted to use the SDK default")
    selected = Selection(role, profile, dict(provider), role_file, dict(options), dict(workspace), profile_override, routing_profiles)
    if kind == 'openai-subscription':
        if workspace.get('kind', 'local') != 'local':
            raise RuntimeConfigurationError('policy coordinator requires a local SDK workspace')
        if options.get('model_routing') or ('tools' in options and options['tools'] != ['task']):
            raise RuntimeConfigurationError('policy coordinator tools are task only; configure worker tools on worker role bindings')
        from openhands_policy import specialist_selections
        from dataclasses import replace
        children = specialist_selections(root, selected, config, user_overlay=user_overlay)
        selected = replace(selected, routing_profiles={name: child.fingerprint() for name, child in children.items()})
    return selected


def wiring_report(root: Path, user_overlay: Path = USER_OVERLAY_DIR) -> dict:
    """Inspect configuration without SDK construction, credentials or provider calls."""
    config = load_config(root, user_overlay)
    from sync import merge_user_overlay, shared_agents
    from model_policy import runtime_policy_for_agent
    _, manifest = merge_user_overlay(FRAMEWORK_ROLES.parent, user_overlay=user_overlay)
    roles = shared_agents(manifest)
    routes = []
    for profile in config.get("profiles", {}):
        for role in roles:
            try:
                selected = select(root, "implement", role["name"], profile,
                                  config=config, user_overlay=user_overlay)
                kind = selected.provider["kind"]
                policy = runtime_policy_for_agent(manifest, "codex" if kind == "openai-subscription" else kind, role) if kind != "local" else {}
                supported = ({"kind", "model", "base_url", "api_key_env", "max_input_tokens", "max_output_tokens", "condenser_max_tokens", "reasoning_effort"}
                             if kind == "local" else ({"kind", "model", "reasoning_effort"} if kind == "openai-subscription" else {"kind", "model", "session_mode", "permission_requests"}))
                routes.append({"profile": profile, "role": selected.role, "kind": kind,
                    "role_file": str(selected.role_file), "model": selected.provider.get("model"),
                    "canonical_effort": policy.get("effort", policy.get("model_reasoning_effort")),
                    "reasoning_effort": selected.provider.get("reasoning_effort") if kind in {"local", "openai-subscription"} else "native harness setting; ACP does not forward Flow effort",
                    "tools": "checked task only" if kind == "openai-subscription" else selected.role_options.get("tools", ["terminal", "file_editor", "task"]) if kind == "local" else "native harness permissions; SDK tool restrictions do not apply",
                    "context": selected.role_options.get("context", []),
                    "skills": selected.role_options.get("skills", []),
                    "untranslated_profile_fields": sorted(set(selected.provider) - supported),
                    "interactive_handoff_configured": kind in {"claude", "codex"},
                    "permission_requests": selected.provider.get("permission_requests"),
                    "human_terminal_required": kind != "local" and selected.provider.get("permission_requests") == "interactive",
                    "execution_configured": kind in {"local", "openai-subscription"} or selected.provider.get("permission_requests") in {"interactive", "stock-openhands"}})
            except (ValueError, OSError) as exc:
                routes.append({"profile": profile, "role": role["name"], "error": str(exc)})
    from openhands_policy import subscription_readiness, specialist_selections, local_eligibility
    framework = read_toml(FRAMEWORK_ROLES.parent / 'flow.toml')
    admin_path = user_overlay / 'flow.toml'
    admin = read_toml(admin_path) if admin_path.is_file() else {}
    local_candidates = []
    for candidate in admin.get('provider_candidates', framework.get('provider_candidates', [])):
        if candidate.get('provider') == 'ollama':
            profile = config.get('profiles', {}).get(candidate.get('runtime_profile', 'ollama'), {})
            reasons = local_eligibility(candidate, profile)
            if candidate.get('enabled') is False:
                reasons.append('candidate disabled')
            local_candidates.append({'candidate_id': candidate['candidate_id'],
                'model': profile.get('model'), 'context_tokens': profile.get('max_input_tokens'),
                'local_capability_eligible': not reasons, 'ineligibility_reasons': reasons})
    implementation = {}
    try:
        coordinator = select(root, 'implement', config=config, user_overlay=user_overlay)
        implementation['coordinator'] = {'profile': coordinator.profile, 'kind': coordinator.provider['kind'],
            'model': coordinator.provider.get('model'), 'reasoning_effort': coordinator.provider.get('reasoning_effort')}
        implementation['workers'] = {name: {'profile': worker.profile, 'kind': worker.provider['kind'], 'model': worker.provider.get('model')}
            for name, worker in specialist_selections(root, coordinator, config, user_overlay=user_overlay).items()}
        if coordinator.provider['kind'] not in {'local', 'openai-subscription'}:
            implementation['error'] = 'native coordinator is not supported; bind native profiles to worker roles'
    except (ValueError, OSError) as exc:
        implementation['error'] = str(exc)
    return {"default_profile": config.get("default_profile"), "routes": routes,
            'implementation_profile': config.get('stages', {}).get('implement', {}).get('profile'),
            'subscription': subscription_readiness(), 'implementation': implementation,
            'local_candidates': local_candidates,
            "note": "Configuration only: no authentication, model availability or effective permissions verified. Skills/AGENTS discovery and PROJECT.md are composed at execution. SDK readiness alone does not mean execution is configured."}
