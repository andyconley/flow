"""Common ephemeral native runtime, reused for implementation and fresh review."""
import os
import shutil
import shlex
import json
import subprocess
import uuid
from pathlib import Path
from .runtime_env import ROOT, environment, node_binary, goose_binary, WORKER_MAX_TURNS
from .codex_adapter_guard import build


def git_metadata(workspace):
    """Read-only paths Git needs for an approved linked worktree."""
    if not any((p/'.git').exists() for p in (workspace, *workspace.parents)):
        return []
    result = subprocess.run(['git', '-C', str(workspace), 'rev-parse',
                             '--path-format=absolute', '--git-dir', '--git-common-dir'],
                            capture_output=True, text=True, timeout=5,
                            env={**os.environ, 'GIT_CONFIG_NOSYSTEM':'1',
                                 'GIT_CONFIG_GLOBAL':'/dev/null', 'GIT_OPTIONAL_LOCKS':'0'})
    if result.returncode:
        raise ValueError('Cannot resolve approved workspace Git metadata: '+result.stderr.strip())
    return sorted({str(Path(path).resolve()) for path in result.stdout.splitlines()})


def prepare(workspace, run_dir, role_bundle, provider=None, model=None, check_command=None):
    workspace, run_dir = Path(workspace).resolve(), Path(run_dir).resolve()
    tools = run_dir/'native-runtime'; tools.mkdir(exist_ok=True)
    bindir = tools/'bin'; bindir.mkdir(exist_ok=True)
    from .project_python import select
    python = select(workspace, check_command)
    if python:
        for name in ('python', 'python3'):
            wrapper = bindir/name
            wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(str(python))+' "$@"\n')
            wrapper.chmod(0o755)
    debug = ROOT/'runtime'/f'{run_dir.name}-native-claude.debug'
    profile = (ROOT/'runtime/scope.sb').read_text().replace(' (remote ip "localhost:11434")', '')
    old = f'(allow file-write* (subpath "{ROOT}/runtime") (subpath "{ROOT}/workspaces") (literal "/dev/null"))'
    new = f'(allow file-write* (subpath "{workspace}") (subpath "{ROOT}/runtime/codex-home") (subpath "{ROOT}/runtime/tmp") (literal "{debug}") (literal "/dev/null"))'
    profile = profile.replace(old, new)
    # Claude appends its own uid/workspace suffixes. Own the entire per-run
    # temp root instead of guessing its workspace-name normalization.
    scratch = tools/'claude-tmp'
    scratch.mkdir(parents=True, exist_ok=True)
    home = tools/'home'; home.mkdir(exist_ok=True)
    temporary = tools/'tmp'; temporary.mkdir(exist_ok=True)
    evidence = tools/'acp-evidence'; evidence.mkdir(mode=0o700, exist_ok=True); evidence.chmod(0o700)
    claude_config = ROOT/'runtime/claude-home'
    claude_config.mkdir(mode=0o700, exist_ok=True); claude_config.chmod(0o700)
    client_error = tools/f'claude-auth-{uuid.uuid4().hex}.json'
    shutil.copyfile(Path(__file__).with_name('acp_evidence.mjs'), tools/'acp_evidence.mjs')
    profile += f'\n(allow file-read* (subpath "{tools}") (subpath "{role_bundle}") (literal "{goose_binary()}"))\n'
    # Approved project checks may use the existing isolated Python executable.
    # Its base binary is under /opt, but startup also reads this venv's config
    # and libraries. Grant tool reads only, not writes or credential access.
    profile += f'(allow file-read* (subpath "{ROOT}/.venv"))\n'
    if python:
        # External venvs need their own libraries; a standalone executable
        # does not grant reads of its entire parent hierarchy.
        venv = python.parent.parent
        if (venv/'pyvenv.cfg').is_file():
            profile += '(allow file-read* (subpath '+json.dumps(str(venv.resolve()))+'))\n'
        profile += '(allow file-read* (literal '+json.dumps(str(python.resolve()))+'))\n'
    profile += f'\n(deny file-read* file-write* (subpath "{ROOT}/runtime/goose-home"))\n(allow file-read* (subpath "{workspace}"))\n(allow file-write* (subpath "{scratch}"))\n'
    profile += f'(allow file-write* (subpath "{home}") (subpath "{temporary}"))\n'
    profile += f'(allow file-write* (subpath "{evidence}"))\n'
    profile += '(allow file-write* (subpath '+json.dumps(str(claude_config))+') (literal '+json.dumps(str(client_error))+') (literal '+json.dumps(str(client_error)+'.tmp')+'))\n'
    for path in git_metadata(workspace):
        profile += '(allow file-read* (subpath '+json.dumps(path)+'))\n'
    profile += '(allow file-write* (regex #"^(/private)?/tmp/claude-[0-9a-f]+-cwd$"))\n'
    sandbox = tools/'worker.sb'; sandbox.write_text(profile)
    build(ROOT/'runtime/adapters/node_modules/@agentclientprotocol/codex-acp/dist/index.js',tools/'phase-codex.mjs')
    node = node_binary()
    for name, command in [('codex-acp',f'"{node}" "{tools}/acp_evidence.mjs" "{evidence}" "{tools}/phase-codex.mjs"'),('claude-agent-acp',f'"{ROOT}/runtime/adapters/node_modules/.bin/claude-agent-acp"')]:
        path=bindir/name;path.write_text(f'#!/bin/sh\nexport GOOSE_PATH_ROOT="{ROOT}/runtime/tmp/native-worker-config"\nexec /usr/bin/sandbox-exec -f "{sandbox}" {command} "$@"\n');path.chmod(0o755)
    executable = os.environ.get('FLOW_V2_CLAUDE') or shutil.which('claude') or str(Path.home()/'.local/bin/claude')
    auth_error = json.dumps({'schema_version':1, 'kind':'permission_required',
        'source':'claude_native_auth_preflight', 'error':{'code':'AUTH_REQUIRED',
        'message':'Claude authentication preflight failed in the private Flow configuration. Complete native sign-in with CLAUDE_CONFIG_DIR='+str(claude_config)+' before explicitly resuming; no login or credential copying was attempted.'}})
    claude=tools/'claude';claude.write_text('#!/bin/sh\nexport HOME='+shlex.quote(str(home))+'\nexport CLAUDE_CONFIG_DIR='+shlex.quote(str(claude_config))+'\nunset CLAUDE_CODE_SAFE_MODE\n'
        +'if ! '+shlex.quote(executable)+' --setting-sources "" auth status --json >/dev/null 2>&1; then\n'
        +'  umask 077\n  printf "%s\\n" '+shlex.quote(auth_error)+' > '+shlex.quote(str(client_error)+'.tmp')+'\n  /bin/mv '+shlex.quote(str(client_error)+'.tmp')+' '+shlex.quote(str(client_error))+'\n'
        +'  echo "Flow Claude authentication preflight failed; native sign-in is required in its private configuration." >&2\n  exit 77\nfi\n'
        +'exec '+shlex.quote(executable)+' --setting-sources "" --disable-slash-commands --settings \'{"disableAllHooks":true,"enabledPlugins":{},"autoMemoryEnabled":false}\' --max-turns '+str(WORKER_MAX_TURNS)+' --no-session-persistence --debug-file "'+str(debug)+'" "$@"\n');claude.chmod(0o755)
    env=environment(project=workspace,provider=provider,model=model);env.pop('OLLAMA_HOST',None);env.pop('CLAUDE_CODE_SAFE_MODE',None)
    env.update(PATH=str(bindir)+':'+env['PATH'],CLAUDE_CODE_EXECUTABLE=str(claude),
               FLOW_V2_ACP_EVIDENCE_DIR=str(evidence),
               FLOW_V2_CLIENT_ERROR_FILE=str(client_error),
               CLAUDE_CONFIG_DIR=str(claude_config),
               CLAUDE_CODE_TMPDIR=str(scratch),
               HOME=str(home), TMPDIR=str(temporary), TMPPREFIX=str(temporary/'zsh'),
               PYTHONPYCACHEPREFIX=str(home/'pycache'),
               GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_NOSYSTEM='1',GIT_OPTIONAL_LOCKS='0',GOOSE_SUBAGENT_MAX_TURNS=str(WORKER_MAX_TURNS))
    if python:
        env['FLOW_V2_PROJECT_PYTHON'] = str(python)
    # macOS login-shell path_helper otherwise moves /usr/bin ahead of the
    # selected project interpreter. Use only attempt-local startup files.
    startup = 'export PATH='+shlex.quote(env['PATH'])+'\n'
    for name in ('.zprofile', '.bash_profile'):
        (home/name).write_text(startup)
    env['ZDOTDIR'] = str(home)
    # The coordinator needs its own state; only its native worker subtree is sandboxed above.
    return sandbox, env
