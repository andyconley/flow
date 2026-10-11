"""Flow-owned specialist and endpoint selection; execution belongs to OpenHands."""
from __future__ import annotations

from dataclasses import dataclass
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


def _merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        result[key] = _merge(result[key], value) if isinstance(result.get(key), dict) and isinstance(value, dict) else value
    return result


def load_config(root: Path, user_overlay: Path = USER_OVERLAY_DIR) -> dict:
    config = {}
    for path in (user_overlay / "runtime.toml", root / ".flow/runtime.toml"):
        if path.is_file():
            config = _merge(config, read_toml(path))
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

    def fingerprint(self) -> str:
        binding = {"role": self.role, "profile": self.profile, "provider": self.provider,
                   "role_text": self.role_file.read_text(), "options": self.role_options,
                   "workspace": self.workspace}
        return hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()


def select(root: Path, stage: str, role: str | None = None, profile: str | None = None,
           *, config: dict | None = None, user_overlay: Path = USER_OVERLAY_DIR) -> Selection:
    config = load_config(root, user_overlay) if config is None else config
    stage_options = config.get("stages", {}).get(stage, {})
    role = identifier(role or stage_options.get("role", STAGES[stage][2]), "role")
    options = config.get("roles", {}).get(role, {})
    profile = identifier(profile or options.get("profile") or stage_options.get("profile") or config.get("default_profile", ""), "profile")
    provider = config.get("profiles", {}).get(profile)
    if not isinstance(provider, dict):
        raise RuntimeConfigurationError(f"profile {profile!r} is not configured in .flow/runtime.toml")
    kind = provider.get("kind")
    if kind == "local":
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
    elif kind not in {"codex", "claude"}:
        raise RuntimeConfigurationError("profile kind must be local, codex, or claude")
    candidates = [root / ".flow/agents" / f"{role}.md", root / ".agents/agents" / f"{role}.md",
                  user_overlay / "agents" / f"{role}.md", FRAMEWORK_ROLES / f"{role}.md"]
    if options.get("file"):
        candidates.insert(0, root / options["file"])
    role_file = next((p.resolve() for p in candidates if p.is_file()), None)
    if role_file is None:
        raise RuntimeConfigurationError(f"specialist definition not found: {role}")
    tools = options.get("tools", ["terminal", "file_editor"])
    if not isinstance(tools, list) or any(t not in {"terminal", "file_editor", "task_tracker", "task"} for t in tools):
        raise RuntimeConfigurationError("role tools must be a list of terminal, file_editor, task_tracker, task")
    if options.get("specialists") and "task" not in tools:
        raise RuntimeConfigurationError("a specialist roster requires the SDK task tool")
    workspace = config.get("workspace", {"kind": "local"})
    if workspace.get("kind", "local") not in {"local", "remote"}:
        raise RuntimeConfigurationError("workspace kind must be local or remote")
    if workspace.get("kind") == "remote" and not workspace.get("host"):
        raise RuntimeConfigurationError("remote workspace needs an existing OpenHands agent-server host")
    if workspace.get("confirmation") not in {None, "always"}:
        raise RuntimeConfigurationError("workspace confirmation must be always, or omitted to use the SDK default")
    return Selection(role, profile, dict(provider), role_file, dict(options), dict(workspace))
