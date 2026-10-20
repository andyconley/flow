"""Source-local runtime/tool paths; existing native accounts remain client-owned."""
import os
from pathlib import Path
import shutil
import shlex

ROOT = Path(__file__).resolve().parents[1]
# Real task workers need room for inspect/edit/test/review; the approved job
# deadline still bounds every worker and coordinator process.
WORKER_MAX_TURNS = 12


def node_binary():
    candidate = os.environ.get('FLOW_V2_NODE') or shutil.which('node')
    if candidate:
        return str(Path(candidate).resolve())
    return str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node')


def goose_binary(source=ROOT):
    explicit = os.environ.get('FLOW_V2_GOOSE_BINARY')
    if explicit:
        return Path(explicit).resolve()
    from .goose_artifact import binary_path, selected_binary
    if binary_path(source).exists() or binary_path(source).is_symlink():
        return selected_binary(source)
    return (source/'runtime/goose/target/debug/goose').resolve()


def environment(project=None, provider=None, model=None):
    env = {key: value for key, value in os.environ.items() if key in ['PATH','USER','LOGNAME','SHELL','LANG','LC_ALL','TERM','SSL_CERT_FILE']}
    env.update(HOME=str((ROOT/'runtime/home').resolve()), GOOSE_PATH_ROOT=str((ROOT/'runtime/goose-home').resolve()),
               GOOSE_DISABLE_KEYRING='1', GOOSE_MODE='auto',
               GOOSE_TELEMETRY_ENABLED='false', LANGSMITH_TRACING='false', LANGGRAPH_STRICT_MSGPACK='true',
               CODEX_HOME=str((ROOT/'runtime/codex-home').resolve()), CODEX_PATH=str(ROOT/'runtime/adapters/node_modules/.bin/codex'),
               PATH=str(Path(node_binary()).parent)+':'+str(ROOT/'runtime/bin')+':'+str(ROOT/'runtime/adapters/node_modules/.bin')+':'+env.get('PATH',''),
               TMPDIR=str((ROOT/'runtime/tmp').resolve()))
    from .device_context import ollama_environment
    env.update(ollama_environment(project, model, provider))
    return env


def setup():
    for relative in ['runtime/bin','runtime/goose-home','runtime/codex-home','runtime/home','runtime/tmp','artifacts','workspaces']:
        (ROOT/relative).mkdir(parents=True, exist_ok=True)
    auth = ROOT/'runtime/codex-home/auth.json'
    original = Path.home()/'.codex/auth.json'
    if not auth.exists() and not auth.is_symlink() and original.exists():
        auth.symlink_to(original)
    (ROOT/'runtime/codex-home/config.toml').write_text('cli_auth_credentials_store = "file"\n')
    profile = '''(version 1)
(allow default)
(deny file-write*)
(deny file-read* (subpath "HOME"))
(deny network-bind network-inbound network-outbound)
(allow file-read* (subpath "/System") (subpath "/usr") (subpath "/bin") (subpath "/sbin") (subpath "/opt") (subpath "/Library") (subpath "/Applications") (subpath "/private/var/db") (subpath "/dev"))
(allow file-read-metadata)
(allow file-read* (subpath "ROOT/runtime") (subpath "ROOT/workspaces") (subpath "HOME/.local") (subpath "HOME/.cache/codex-runtimes") (literal "HOME/.codex/auth.json") (literal "HOME/.claude.json") (subpath "HOME/.claude") (subpath "HOME/Library/Keychains"))
(allow file-write* (subpath "ROOT/runtime") (subpath "ROOT/workspaces") (literal "/dev/null"))
(allow network-outbound (remote tcp "*:443"))
(allow network-outbound (remote unix-socket))
'''.replace('ROOT',str(ROOT)).replace('HOME',str(Path.home()))
    # Managed releases keep mutable state behind symlinks. Sandbox paths must
    # name the canonical targets, not a replaceable release's logical aliases.
    import json
    mutable=[str((ROOT/'runtime'/name).resolve()) for name in ('goose-home','codex-home','home','tmp','claude-home')]
    profile+='\n# MANAGED_MUTABLE_START\n(allow file-read* file-write* '+''.join('(subpath '+json.dumps(path)+') ' for path in mutable)+')\n# MANAGED_MUTABLE_END\n'
    (ROOT/'runtime/scope.sb').write_text(profile)
    return ROOT/'runtime/scope.sb'


def scoped(command):
    return ['/usr/bin/sandbox-exec', '-f', str(ROOT/'runtime/scope.sb'), *command]
