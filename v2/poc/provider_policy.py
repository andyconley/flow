"""Machine-owned native subscription constraint; projects cannot override it."""
from pathlib import Path
import tomllib

def native_only():
    path=Path.home()/'.flow/user/runtime.toml'
    return path.is_file() and tomllib.loads(path.read_text()).get('execution_policy',{}).get('native_only') is True

def require(provider):
    if native_only() and provider not in {'codex-acp','claude-acp','chatgpt_codex'}:
        raise ValueError('Flow is constrained to Codex and Claude subscriptions; provider '+str(provider)+' is disabled')

def native_knowledge():
    return native_only()
