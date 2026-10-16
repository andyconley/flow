"""Thin integration with pinned OpenHands. No Flow agent loop or tool transport."""
from __future__ import annotations

from contextlib import contextmanager
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
import os
import sys

from openhands_config import SDK_VERSION, RuntimeConfigurationError, Selection
from openhands_policy import specialist_selections


ACP_ACCESS_NOTE = ("Flow defaults to explicit terminal permission choices through its ACP proxy; headless execution fails closed. "
                   "Explicit legacy stock-openhands handling automatically answers native permission requests. "
                   "Flow selects Codex agent (workspace-write/auto_review) or Claude default, "
                   "and inherits the execution environment's actual containment. Claude may offer allow_always first and update native permission rules. "
                   "A live native run requires authorized native network and session-state access; "
                   "this branch has not broadened either or copied credentials.")
ACP_BLOCKER = ACP_ACCESS_NOTE  # historical handoff text; not a blanket runtime veto



def probe() -> dict:
    packages = {}
    for name in ("openhands-sdk", "openhands-tools", "openhands-workspace", "openhands-agent-server"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    return {"ready": all(v == SDK_VERSION for v in packages.values()), "required_version": SDK_VERSION,
            "packages": packages, "native_automation": "implemented", "native_access_note": ACP_ACCESS_NOTE}


def role_context(selection: Selection):
    """Compose the canonical role without constructing an SDK agent or session."""
    # Use the same composition pipeline as distribution, including expertise
    # and user overlay sources. Project-specific files still win in select().
    from sync import agent_body, merge_user_overlay, shared_agents
    from openhands_config import FRAMEWORK_ROLES
    from render import parse_frontmatter, render_openhands_agent
    _, manifest = merge_user_overlay(FRAMEWORK_ROLES.parent)
    declaration = next((a for a in shared_agents(manifest) if a["name"] == selection.role), None)
    from paths import GENERATED_MARKER
    if declaration is not None and GENERATED_MARKER not in selection.role_file.read_text():
        declaration = dict(declaration, source=selection.role_file.name)
        body = agent_body(declaration, selection.role_file.parent, FRAMEWORK_ROLES.parent,
                          manifest.get("claude", {}).get("agent_defaults", {}))
    else:
        body = selection.role_file.read_text()
    capabilities = manifest.get("_agent_capability_decisions", {}).get(selection.role)
    # Already generated definitions carry this guidance; do not duplicate it.
    if GENERATED_MARKER in body:
        capabilities = None
    metadata, prompt = parse_frontmatter(render_openhands_agent(selection.role, str(selection.role_file), body, capabilities))
    return metadata, prompt


def _context(selection: Selection, root: Path, *, explicit_skills_only=False):
    from paths import HOME, USER_OVERLAY_DIR
    from openhands.sdk import AgentContext
    from openhands.sdk.context import Skill, load_skills_from_dir

    metadata, prompt = role_context(selection)
    from openhands.sdk.skills import load_available_skills
    # SDK discovery also composes AGENTS.md and conditional project rules.
    skills = load_available_skills(root, include_user=True, include_project=False, include_public=False)
    def merge_collection(directory):
        if not directory.is_dir():
            return
        # SDK 1.54 discovers AgentSkills packages only immediately below a
        # collection. Nested synced packages otherwise leak their reference
        # Markdown into permanent context. Give the stock loader the package
        # boundaries and load those SKILL.md declarations with its own parser.
        packages = sorted(p for p in directory.rglob("*")
                          if p.name.lower() == "skill.md" and p.is_file() and p.parent.parent != directory)
        package_roots = {p.parent.resolve() for p in packages}
        for name, skill in list(skills.items()):
            source = Path(skill.source).resolve() if skill.source else None
            if source and source.name.lower() != "skill.md" and any(package in source.parents for package in package_roots):
                skills.pop(name)
        groups = load_skills_from_dir(directory, exclude_dirs={p.parent for p in packages})
        collection = {}
        for group in groups:
            collection.update(group)
        for path in packages:
            try:
                skill = Skill.load(path)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("Skipping invalid nested skill %s: %s", path, exc)
                continue
            collection.setdefault(skill.name, skill)
        skills.update(collection)
    # Project sources remain authoritative over user/overlay skills, including
    # SDK-native .openhands skills and scoped AGENTS.md rules.
    for directory in (HOME / ".agents/skills", USER_OVERLAY_DIR / "skills"):
        merge_collection(directory)
    skills.update(load_available_skills(root, include_user=False, include_project=True, include_public=False))
    for directory in (root / ".flow/skills", root / ".openhands/skills", root / ".agents/skills"):
        merge_collection(directory)
    for name in metadata.get("skills", []):
        if name not in skills:
            raise RuntimeConfigurationError(f"role skill not found: {name}")
    explicit_names = set(metadata.get("skills", []))
    for relative in selection.role_options.get("skills", []):
        skill = Skill.load(root / relative)
        skills[skill.name] = skill
        explicit_names.add(skill.name)
    if explicit_skills_only:
        from openhands.sdk.skills.trigger import PathTrigger
        # Keep mandatory repository/user guidance and scoped rules. Optional
        # ambient skill catalogs belong to workers, not the small coordinator.
        skills = {name: skill for name, skill in skills.items()
                  if name in explicit_names or isinstance(skill.trigger, PathTrigger)
                  or (not skill.is_agentskills_format and skill.trigger is None)}
    context = [prompt]
    for relative in selection.role_options.get("context", []):
        context.append((root / relative).read_text())
    project = root / ".flow/PROJECT.md"
    if project.is_file():
        context.append(project.read_text())
    return AgentContext(skills=list(skills.values()), system_message_suffix="\n\n".join(context),
                        load_user_skills=False, load_public_skills=False,
                        load_project_skills=selection.workspace.get("kind") == "remote")


def local_llm(selection: Selection):
    from openhands.sdk import LLM
    provider = selection.provider
    key_env = provider.get("api_key_env")
    key = os.environ.get(key_env) if key_env else "self-hosted"
    if key_env and not key:
        raise RuntimeConfigurationError(f"self-hosted credential variable {key_env} is unset")
    llm_options = {name: provider[name] for name in ("max_input_tokens", "max_output_tokens", "reasoning_effort") if name in provider}
    llm = LLM(model=provider["model"], base_url=provider["base_url"], api_key=key,
              usage_id=f"flow-{selection.role}", **llm_options)
    if provider["model"].startswith(("ollama/", "ollama_chat/")) and provider.get("max_input_tokens"):
        # SDK max_input_tokens is a budget, not Ollama's allocation. LiteLLM
        # merges extra_body after provider transformation; retain generation
        # defaults when explicitly supplying the native options object.
        options = {"num_ctx": provider["max_input_tokens"]}
        if provider.get("max_output_tokens"):
            options["num_predict"] = provider["max_output_tokens"]
        for field in ("temperature", "top_p", "seed"):
            if getattr(llm, field, None) is not None:
                options[field] = getattr(llm, field)
        llm = llm.model_copy(update={"litellm_extra_body": {"options": options}})
    return llm


def build_agent(selection: Selection, root: Path, inherited_llm=None):
    if selection.provider['kind'] == 'openai-subscription' or selection.role_options.get('policy_dispatch'):
        return build_coordinator(selection, root)
    if selection.provider["kind"] != "local":
        return build_native_agent(selection, root)
    from openhands.sdk import Agent, Tool
    from openhands.tools.terminal import TerminalTool
    from openhands.tools.file_editor import FileEditorTool
    from openhands.tools.task_tracker import TaskTrackerTool
    from openhands.tools.task import TaskToolSet
    from openhands.sdk.subagent import register_agent_if_absent
    from openhands_config import load_config, select

    tools = {"terminal": TerminalTool, "file_editor": FileEditorTool,
             "task_tracker": TaskTrackerTool, "task": TaskToolSet}
    llm = inherited_llm.model_copy(update={"usage_id": f"flow-{selection.role}"}) if inherited_llm is not None else local_llm(selection)
    provider = selection.provider
    # Register declared specialists with the SDK's own delegation mechanism.
    # Explicit child bindings win; unbound local children inherit the active SDK LLM.
    config = load_config(root)
    delegation = []
    from sync import merge_user_overlay, shared_agents
    from openhands_config import FRAMEWORK_ROLES
    from dataclasses import replace
    _, manifest = merge_user_overlay(FRAMEWORK_ROLES.parent)
    roster = selection.role_options.get("specialists")
    if roster is None:
        roster = [a["name"] for a in shared_agents(manifest)]
        # Explicit project definitions remain callable alongside framework roles.
        for directory in (root / ".flow/agents", root / ".agents/agents"):
            if directory.is_dir():
                roster.extend(p.stem for p in sorted(directory.glob("*.md")) if p.stem not in roster and p.name.lower() != "readme.md")
    selected_tools = list(selection.role_options.get("tools", ["terminal", "file_editor", "task"]))
    if not roster:
        selected_tools = [tool for tool in selected_tools if tool != "task"]
    if (selection.workspace.get("kind") == "remote" and "task" in selected_tools
            and any(name != selection.role for name in roster)):
        raise RuntimeConfigurationError(
            "OpenHands SDK 1.54 remote transport sends AgentDefinition metadata, not Flow factories; "
            "it cannot reproduce these specialist contexts/profiles or ACPAgent children. "
            "Use a local workspace for Flow specialist delegation, run server-owned stock definitions/factories "
            "directly on the server, or adopt an SDK transport that serializes these agents. "
            "Whole-stage remote execution remains available with specialists=[] or without the task tool; "
            "no native credentials are forwarded.")
    for name in roster if "task" in selected_tools else []:
        if name == selection.role:
            continue
        child_options = config.get("roles", {}).get(name, {})
        bound = "profile" in child_options
        child_profile = child_options["profile"] if bound else selection.profile
        child = select(root, "implement", name, child_profile, config=config)
        # Only explicit role bindings choose a new endpoint. The SDK passes its
        # current (possibly switched) LLM to every unbound local child.
        inherit = not bound and child.provider["kind"] == "local"
        child = replace(child, profile_override=selection.profile_override if inherit else False)
        # The SDK registry is process-global. Scope its identity to the actual
        # project/profile binding so repeats reuse a factory and different
        # projects or changed profiles do not inherit a stale factory.
        import hashlib
        registry_key = f"{name}-{hashlib.sha256((str(root.resolve()) + child.fingerprint()).encode()).hexdigest()[:16]}"
        from render import parse_frontmatter
        metadata, _ = parse_frontmatter(child.role_file.read_text())
        description = metadata.get("description") or f"Flow specialist {name}"
        factory = lambda parent_llm, selected=child, inherit=inherit: build_agent(
            selected, root, parent_llm if inherit else None)
        register_agent_if_absent(name=registry_key, factory_func=factory,
                                 description=f"{description} ({child.profile}, {child.provider['kind']})")
        # v0.43 implicitly registered local children as leaves. Retain those
        # identifiers so an unchanged persisted parent's old task hints remain
        # callable; execution now follows the same stock roster semantics.
        if child.provider["kind"] == "local" and "specialists" not in child.role_options:
            legacy = replace(child, role_options={**child.role_options, "specialists": []})
            legacy_key = f"{name}-{hashlib.sha256((str(root.resolve()) + legacy.fingerprint()).encode()).hexdigest()[:16]}"
            register_agent_if_absent(name=legacy_key, factory_func=factory,
                                     description=f"{description} (v0.43 resume alias)")
        delegation.append(f"{name}: use task subagent_type={registry_key} [profile={child.profile}, kind={child.provider['kind']}, model={'inherited' if inherit else child.provider.get('model', 'native default')}] {description}")
    context = _context(selection, root)
    if delegation:
        context = context.model_copy(update={"system_message_suffix": context.system_message_suffix + "\n\nConfigured specialist roster:\n" + "\n".join(delegation)})
    from openhands_accounting import register_accounting_task_tool
    tool_specs = [Tool(name=register_accounting_task_tool() if t == "task" else tools[t].name) for t in selected_tools]
    routing = selection.role_options.get("model_routing")
    condenser_profiles = [provider]
    condenser_llms = [llm]
    # Stock switches retain the condenser's threshold. Honor every candidate's
    # cap conservatively without intercepting or replacing the SDK switch tool.
    inherited_profile = config.get("profiles", {}).get((inherited_llm or llm).usage_id.removeprefix("profile:")) if (inherited_llm or llm).usage_id.startswith("profile:") else None
    if inherited_profile and inherited_profile.get("kind") == "local":
        condenser_profiles.append(inherited_profile)
    if routing and not selection.profile_override:
        from openhands.sdk.tool.builtins.classify_and_switch_llm import ClassifyAndSwitchLLMTool
        names = {routing["classifier_profile"], *(entry["profile"] for entry in routing["categories"])}
        resolved = {name: local_llm(select(root, "implement", selection.role, name, config=config)) for name in sorted(names)}
        candidates = {entry["profile"] for entry in routing["categories"]}
        condenser_profiles.extend(config["profiles"][name] for name in candidates)
        condenser_llms.extend(resolved[name] for name in candidates)
        tool_specs.append(Tool(name=ClassifyAndSwitchLLMTool.__name__, params={
            "meta_profile": {"classifier_model": routing["classifier_profile"],
                             "classes": [{"description": entry["description"], "model": entry["profile"]}
                                         for entry in routing["categories"]]},
            "meta_profile_llms": resolved}))
        context = context.model_copy(update={"system_message_suffix": context.system_message_suffix +
            "\n\nUse route_task_to_model near the start of a task or when its requirements change. "
            "This switches local models; use task for specialist and native delegation."})
    limits = [profile["condenser_max_tokens"] for profile in condenser_profiles
              if profile.get("condenser_max_tokens") is not None]
    if (routing and not selection.profile_override) or inherited_llm is not None:
        for candidate in condenser_llms:
            inputs = candidate.effective_max_input_tokens
            outputs = candidate.effective_max_output_tokens or 0
            if inputs is not None:
                limits.append(inputs - outputs if inputs > outputs else inputs)
    condenser = None
    if limits:
        from openhands.sdk.context.condenser import LLMSummarizingCondenser
        condenser = LLMSummarizingCondenser(
            llm=llm.model_copy(update={"usage_id": f"flow-{selection.role}-condenser"}),
            max_tokens=min(limits))
    return Agent(llm=llm,
                 tools=tool_specs,
                 agent_context=context, condenser=condenser)


def build_coordinator(selection, root):
    """Stock SDK Agent reasons and delegates; deterministic factories bind providers."""
    from openhands.sdk import Agent, LLM, Tool
    from openhands.sdk.llm.auth.openai import create_subscription_llm_from_config
    from openhands.sdk.subagent import register_agent_if_absent
    from openhands_config import load_config
    from openhands_accounting import register_policy_task_tool
    import hashlib
    children = specialist_selections(root, selection, load_config(root))
    if selection.routing_profiles != {role: child.fingerprint() for role, child in children.items()}:
        raise RuntimeConfigurationError('specialist policy changed after coordinator binding; start a reviewed new session')
    bindings = {}
    for role, child in children.items():
        key = 'flow-policy-' + hashlib.sha256((str(root.resolve()) + child.fingerprint()).encode()).hexdigest()[:20]
        def factory(parent_llm, child=child, expected=child.fingerprint()):
            if child.fingerprint() != expected:
                raise RuntimeConfigurationError('specialist definition changed after coordinator binding; start a reviewed new session')
            return build_agent(child, root)
        register_agent_if_absent(name=key, factory_func=factory,
                                 description=f'Flow policy worker: {role}')
        bindings[role] = key
        if child.provider['kind'] == 'local':
            fallback_key = None
            if child.role_options.get('_hosted_fallback'):
                from openhands_config import select
                from dataclasses import replace
                fallback = select(root, 'implement', role, child.role_options['_hosted_fallback'], config=load_config(root))
                if fallback.fingerprint() != child.role_options['_hosted_fallback_binding']:
                    raise RuntimeConfigurationError('hosted fallback changed after binding')
                fallback = replace(fallback, role_options={**fallback.role_options, 'specialists': []})
                fallback_key = 'flow-policy-' + hashlib.sha256((str(root.resolve()) + fallback.fingerprint()).encode()).hexdigest()[:20]
                def fallback_factory(parent_llm, selected=fallback, expected=fallback.fingerprint()):
                    if selected.fingerprint() != expected:
                        raise RuntimeConfigurationError('fallback role changed after binding')
                    return build_native_agent(selected, root)
                register_agent_if_absent(name=fallback_key, factory_func=fallback_factory,
                    description=f'Flow policy fallback: {role}')
            bindings[role] = {'primary': key, 'fallback': fallback_key, 'local': True}
    # This supported SDK entrypoint loads/refreshes only OpenHands OAuth at execution.
    # It never initiates login and fails if the human has not signed in.
    llm = local_llm(selection) if selection.provider['kind'] == 'local' else create_subscription_llm_from_config(LLM(model=selection.provider['model'],
        auth_type='subscription', subscription_vendor='openai',
        reasoning_effort=selection.provider['reasoning_effort'], usage_id='flow-coordinator'))
    context = _context(selection, root, explicit_skills_only=True)
    context = context.model_copy(update={'system_message_suffix': context.system_message_suffix +
        '\n\nYou coordinate implementation inside OpenHands. Delegate all workspace work and durable output writes '
        'to the approved logical roles through task. Provider assignment is deterministic code, not your choice. '
        'Do not request provider changes, nested delegation, direct CLI launches, or changes to routing policy. '
        'Workers are leaves. Use lead-developer for implementation and output assembly when in the roster. '
        'Do not approve workflow gates. Report specialist evidence and unresolved work.'})
    condenser = None
    if selection.provider.get('condenser_max_tokens') is not None:
        from openhands.sdk.context.condenser import LLMSummarizingCondenser
        condenser = LLMSummarizingCondenser(
            llm=llm.model_copy(update={'usage_id': 'flow-coordinator-condenser'}),
            max_tokens=selection.provider['condenser_max_tokens'])
    return Agent(llm=llm, tools=[Tool(name=register_policy_task_tool(), params={'bindings': bindings})],
                 agent_context=context, condenser=condenser)


def build_native_agent(selection: Selection, root: Path):
    if selection.provider.get("permission_requests", "interactive") not in {"interactive", "stock-openhands"}:
        raise RuntimeConfigurationError("permission_requests must be interactive or explicitly acknowledged stock-openhands")
    from openhands.sdk.agent import ACPAgent
    from openhands.sdk.settings.acp_install_catalog import ACP_INSTALL_CATALOG
    kind = selection.provider["kind"]
    # Reject ambient API routing instead of silently switching account/billing.
    variables = ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL") if kind == "codex" else ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN")
    if any(os.environ.get(name) for name in variables):
        raise RuntimeConfigurationError("native subscription execution requires an environment without paid API credentials or routing overrides")
    modes = {"codex": {"agent", "read-only"}, "claude": {"default", "plan"}}
    mode = selection.provider.get("session_mode", "agent" if kind == "codex" else "default")
    if mode not in modes[kind]:
        raise RuntimeConfigurationError("native session mode would broaden access; supported modes: " + ", ".join(sorted(modes[kind])))
    provider_key = "codex" if kind == "codex" else "claude-code"
    spec = ACP_INSTALL_CATALOG[provider_key]
    # Keep the official adapter, native modes, authentication and SDK sessions.
    # The public command boundary intercepts permission requests only.
    command = list(spec.npx_command())
    if selection.provider.get("permission_requests", "interactive") == "interactive":
        command = [sys.executable, str(Path(__file__).with_name("acp_permissions.py")),
                   "--npm-cache", str(root / ".flow/runs/.acp-cache/npm"), "--", *command]
    return ACPAgent(acp_command=command, acp_server=provider_key,
                    acp_session_mode=mode, acp_model=selection.provider.get("model"),
                    acp_isolate_data_dir=False, acp_file_secrets=[],
                    agent_context=_context(selection, root))


@contextmanager
def conversation(selection: Selection, root: Path, persistence: Path, conversation_id, callback):
    diagnostic = probe()
    if not diagnostic["ready"]:
        raise RuntimeConfigurationError("run this command with the isolated pinned OpenHands environment: " + str(diagnostic["packages"]))
    if selection.provider["kind"] != "local" and selection.provider.get("permission_requests", "interactive") not in {"interactive", "stock-openhands"}:
        raise RuntimeConfigurationError("Native access decision required: stock ACP auto-approval may add native permission rules. See docs/native-access-decision.md; after approval select permission_requests=stock-openhands in the native profile.")
    from openhands.sdk import Conversation
    from openhands.sdk.workspace import LocalWorkspace
    from openhands.sdk.security import AlwaysConfirm
    agent = build_agent(selection, root)
    workspace_options = selection.workspace
    restored_llm = None
    if (workspace_options.get("kind", "local") == "local" and selection.provider["kind"] == "local"
            and selection.role_options.get("model_routing") and not selection.profile_override):
        import json
        from openhands.sdk.conversation.impl.local_conversation import LocalConversation
        from openhands.sdk.conversation.state import BASE_STATE
        from openhands_config import load_config, select
        # Read the SDK's own snapshot, not a second Flow model/session ledger.
        snapshot = Path(LocalConversation.get_persistence_dir(persistence, conversation_id)) / BASE_STATE
        try:
            saved = json.loads(snapshot.read_text())
        except FileNotFoundError:
            saved = None
        if saved:
            usage = saved.get("agent", {}).get("llm", {}).get("usage_id", "")
            if usage.startswith("profile:"):
                profile = usage.removeprefix("profile:")
                candidates = {entry["profile"] for entry in selection.role_options["model_routing"]["categories"]}
                if profile not in candidates:
                    raise RuntimeConfigurationError("persisted routed profile is no longer a candidate; use --new-session")
                resolved = select(root, "implement", selection.role, profile, config=load_config(root))
                # Re-resolve credentials in place: SDK snapshots redact secrets.
                restored_llm = local_llm(resolved).model_copy(update={"usage_id": usage})
    if workspace_options.get("kind", "local") == "local":
        workspace = LocalWorkspace(working_dir=root)
    else:
        from openhands.sdk import RemoteWorkspace
        key_env = workspace_options.get("api_key_env")
        workspace = RemoteWorkspace(host=workspace_options["host"],
                                    api_key=os.environ.get(key_env) if key_env else None,
                                    working_dir=workspace_options.get("working_dir", "/workspace"))
    # LocalWorkspace inherits the process's actual OS permissions. A cwd is not
    # a sandbox. Flow does not manufacture filesystem or network grants.
    kwargs = {"agent": agent, "workspace": workspace, "conversation_id": conversation_id,
              "callbacks": [callback], "visualizer": None}
    if workspace_options.get("kind", "local") == "local":
        kwargs["persistence_dir"] = persistence
    session = Conversation(**kwargs)
    try:
        if restored_llm is not None:
            session.switch_llm(restored_llm)
        if workspace_options.get("confirmation") == "always" or selection.provider['kind'] == 'openai-subscription' or selection.role_options.get('policy_dispatch'):
            session.set_confirmation_policy(AlwaysConfirm())
        yield session
    finally:
        session.close()
