"""Common ephemeral native runtime, reused for implementation and fresh review."""
import os
import shutil
import shlex
from pathlib import Path
from .runtime_env import ROOT, environment, node_binary, goose_binary
from .codex_adapter_guard import build


def prepare(workspace, run_dir, role_bundle, provider=None, model=None):
    workspace, run_dir = Path(workspace).resolve(), Path(run_dir).resolve()
    tools = run_dir/'native-runtime'; tools.mkdir(exist_ok=True)
    bindir = tools/'bin'; bindir.mkdir(exist_ok=True)
    debug = ROOT/'runtime'/f'{run_dir.name}-native-claude.debug'
    profile = (ROOT/'runtime/scope.sb').read_text().replace(' (remote ip "localhost:11434")', '')
    old = f'(allow file-write* (subpath "{ROOT}/runtime") (subpath "{ROOT}/workspaces") (literal "/dev/null"))'
    new = f'(allow file-write* (subpath "{workspace}") (subpath "{ROOT}/runtime/codex-home") (subpath "{ROOT}/runtime/tmp") (literal "{debug}") (literal "/dev/null"))'
    profile = profile.replace(old, new)
    scratch = Path('/private/tmp')/f'claude-{os.getuid()}'/str(workspace).replace('/', '-')
    scratch.mkdir(parents=True, exist_ok=True)
    profile += f'\n(allow file-read* (subpath "{tools}") (subpath "{role_bundle}") (literal "{goose_binary()}"))\n'
    # Approved project checks may use the existing isolated Python executable.
    # Its base binary is under /opt, but startup also reads this venv's config
    # and libraries. Grant tool reads only, not writes or credential access.
    profile += f'(allow file-read* (subpath "{ROOT}/.venv"))\n'
    profile += f'\n(deny file-read* file-write* (subpath "{ROOT}/runtime/goose-home"))\n(allow file-read* (subpath "{workspace}"))\n(allow file-write* (subpath "{scratch}"))\n'
    profile += '(allow file-write* (regex #"^(/private)?/tmp/claude-[0-9a-f]+-cwd$"))\n'
    sandbox = tools/'worker.sb'; sandbox.write_text(profile)
    build(ROOT/'runtime/adapters/node_modules/@agentclientprotocol/codex-acp/dist/index.js',tools/'phase-codex.mjs')
    node = node_binary()
    for name, command in [('codex-acp',f'"{node}" "{tools}/phase-codex.mjs"'),('claude-agent-acp',f'"{ROOT}/runtime/adapters/node_modules/.bin/claude-agent-acp"')]:
        path=bindir/name;path.write_text(f'#!/bin/sh\nexport GOOSE_PATH_ROOT="{ROOT}/runtime/tmp/native-worker-config"\nexec /usr/bin/sandbox-exec -f "{sandbox}" {command} "$@"\n');path.chmod(0o755)
    executable = os.environ.get('FLOW_V2_CLAUDE') or shutil.which('claude') or str(Path.home()/'.local/bin/claude')
    claude=tools/'claude';claude.write_text('#!/bin/sh\nexport HOME="'+str(Path.home())+'"\nunset CLAUDE_CONFIG_DIR CLAUDE_CODE_SAFE_MODE\nexec '+shlex.quote(executable)+' --setting-sources "" --disable-slash-commands --settings \'{"disableAllHooks":true,"enabledPlugins":{},"autoMemoryEnabled":false}\' --max-turns 4 --no-session-persistence --debug-file "'+str(debug)+'" "$@"\n');claude.chmod(0o755)
    env=environment(project=workspace,provider=provider,model=model);env.pop('OLLAMA_HOST',None);env.pop('CLAUDE_CODE_SAFE_MODE',None)
    env.update(PATH=str(bindir)+':'+env['PATH'],CLAUDE_CODE_EXECUTABLE=str(claude),
               GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_NOSYSTEM='1',GOOSE_SUBAGENT_MAX_TURNS='4')
    # The coordinator needs its own state; only its native worker subtree is sandboxed above.
    return sandbox, env
