"""Bounded readiness checks for every provider the coordinator may delegate to.

These checks never infer permission to sign in, copy credentials or switch providers.
They use the same per-operation environment and sandbox as the native workers.
"""
import json
from pathlib import Path
import subprocess
import time
import tomllib
from urllib.parse import urlparse
import yaml


class PreflightError(ValueError):
    def __init__(self, status, reason):
        self.status = status
        super().__init__(reason)


def planned(bundle, provider, model):
    providers = {(provider, model)}
    for path in sorted((Path(bundle)/'recipes').glob('*.yaml')):
        recipe = yaml.safe_load(path.read_text())
        settings = recipe.get('settings', {}) if isinstance(recipe, dict) else {}
        selected = settings.get('goose_provider')
        selected_model = settings.get('goose_model')
        if not isinstance(selected, str) or not selected or not isinstance(selected_model, str) or not selected_model:
            raise PreflightError('scope_required', 'Role recipe lacks an explicit provider/model: '+path.name)
        providers.add((selected, selected_model))
    return sorted(providers)


def _auth(command, profile, env, timeout, label):
    try:
        result = subprocess.run(['/usr/bin/sandbox-exec', '-f', str(profile), *command],
                                env=env, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PreflightError('permission_required', label+' readiness check unavailable: '+str(error)) from error
    if result.returncode:
        raise PreflightError('permission_required', label+' is not signed in or its private configuration is inaccessible. Complete native sign-in separately, then explicitly resume; no login or credential copying was attempted.')
    return result.stdout


def check(bundle, provider, model, profile, env, deadline=None):
    """No model invocation or workspace writes. Successful checks are observations only."""
    rows = []
    limit = min(deadline, time.time()+30) if deadline is not None else time.time()+30
    authenticated = set()
    for selected, selected_model in planned(bundle, provider, model):
        remaining = limit-time.time()
        if remaining <= 0:
            raise PreflightError('blocked', 'Provider readiness budget exhausted before execution; no coordinator was submitted')
        timeout = min(5, remaining)
        if selected in {'codex-acp', 'chatgpt_codex'}:
            key = 'codex'
            config = Path(env['CODEX_HOME'])/'config.toml'
            settings = tomllib.loads(config.read_text()) if config.exists() else {}
            configured = settings.get('model_providers', {}).get(settings.get('model_provider'), {})
            if configured.get('requires_openai_auth') is False:
                endpoint = urlparse(configured.get('base_url', ''))
                if endpoint.scheme != 'http' or endpoint.hostname not in {'localhost', '127.0.0.1', '::1'} or endpoint.username or endpoint.password:
                    raise PreflightError('scope_required', 'Credential-free Codex requires an explicitly configured loopback endpoint')
                readiness = 'explicit credential-free local configuration; inference availability is checked by the provider at dispatch'
            else:
                if key not in authenticated:
                    _auth([env['CODEX_PATH'], 'login', 'status'], profile, env, timeout, 'Codex')
                    authenticated.add(key)
                readiness = 'native account status'
        elif selected == 'claude-acp':
            if 'claude' not in authenticated:
                raw = _auth([env['FLOW_V2_CLAUDE_BINARY'], '--setting-sources', '', 'auth', 'status', '--json'],
                            profile, env, timeout, 'Claude')
                try:
                    logged_in = json.loads(raw).get('loggedIn') is True
                except (ValueError, AttributeError):
                    logged_in = False
                if not logged_in:
                    raise PreflightError('permission_required', 'Claude is not signed in in CLAUDE_CONFIG_DIR='+env['CLAUDE_CONFIG_DIR']+'. Sign in separately, then explicitly resume; no login or credential copying was attempted.')
                authenticated.add('claude')
            readiness = 'native account status'
        elif selected == 'ollama':
            endpoint = env.get('OLLAMA_HOST', 'http://127.0.0.1:11434').rstrip('/')
            if '://' not in endpoint:
                endpoint = 'http://'+endpoint
            try:
                result = subprocess.run(['/usr/bin/sandbox-exec', '-f', env.get('FLOW_V2_LOCAL_PREFLIGHT_SCOPE',str(profile)),
                                         '/usr/bin/curl', '--fail', '--silent', '--show-error',
                                         '--max-time', str(timeout), endpoint+'/api/tags'],
                                        env=env, capture_output=True, text=True, timeout=timeout)
                if result.returncode:
                    raise ValueError('endpoint check failed')
                models=json.loads(result.stdout).get('models', [])
                names = {item.get('name') for item in models}
                implementation=json.loads(env.get('FLOW_V2_IMPLEMENTATION_PROFILE','null'))
                if implementation and selected_model==implementation['model']:
                    from .implementation_profiles import validate
                    validate(implementation)
                    matched=[item for item in models if item.get('name')==selected_model or item.get('name')==selected_model+':latest']
                    if any(item.get('remote_host') or item.get('remote_model') for item in matched):
                        raise PreflightError('scope_required','Implementation worker requires downloaded local weights, not a cloud alias')
                    observed={item.get('digest') for item in matched}
                    if observed!={implementation['model_digest']}:
                        raise PreflightError('scope_required','Implementation model digest changed since work creation; create a new work item')
            except PreflightError:
                raise
            except (OSError, ValueError, subprocess.TimeoutExpired) as error:
                raise PreflightError('scope_required', 'Configured Ollama endpoint is unavailable in the native sandbox: '+endpoint) from error
            if selected_model not in names and selected_model+':latest' not in names:
                raise PreflightError('scope_required', 'Configured Ollama model is unavailable: '+selected_model+'; no pull or provider switching was attempted')
            readiness = 'configured endpoint and installed model'
        else:
            raise PreflightError('scope_required', 'No safe readiness check is defined for planned provider '+selected+'; configure and validate it explicitly before execution')
        rows.append({'provider': selected, 'model': selected_model, 'readiness': readiness})
    return {'passed': True, 'providers': rows,
            'limitations': 'Account/configuration readiness does not guarantee quota, remote model availability or later authorization.'}
