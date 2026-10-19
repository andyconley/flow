"""Render Flow roles through Flow's own resolver; no sessions or installations."""
import json
from pathlib import Path
import subprocess
import sys
import yaml

# Isolate Flow's top-level Python imports from the POC's module namespace.
COMPOSE = r'''
import json,sys
from pathlib import Path
sys.path.insert(0, sys.argv[1] + '/cli')
import sync
from openhands_config import select,load_config
from openhands_runtime import role_context
root,overlay,role,profile,stage = Path(sys.argv[2]),Path(sys.argv[3]),sys.argv[4],sys.argv[5],sys.argv[6]
sync.USER_OVERLAY_DIR = overlay
config = load_config(root, user_overlay=overlay)
selection = select(root, stage, role=role,
                   profile=profile, config=config, user_overlay=overlay)
metadata,body = role_context(selection)
print(json.dumps({'role':role,'metadata':metadata,'body':body,'source':str(selection.role_file),
                  'profile':profile,'provider_kind':selection.provider.get('kind'),'model':selection.provider.get('model')}))
'''
CATALOG = r'''
import json,sys
from pathlib import Path
sys.path.insert(0, sys.argv[1] + '/cli')
from sync import merge_user_overlay,shared_agents
from flowtoml import read_toml
from openhands_config import load_config
root,overlay = Path(sys.argv[2]),Path(sys.argv[3])
framework = Path(sys.argv[1])/'scaffolds/default'
_,manifest = merge_user_overlay(framework,user_overlay=overlay)
preferences = {}
for path in [framework/'flow.toml',overlay/'flow.toml',root/'.flow/flow.toml']:
    if path.is_file():
        preferences.update(read_toml(path).get('implementation_routing',{}).get('hosted_preferences',{}))
config = load_config(root,user_overlay=overlay)
roles = []
for agent in shared_agents(manifest):
    name = agent['name']
    profile = config.get('roles',{}).get(name,{}).get('profile',preferences.get(name,'codex'))
    provider = config.get('profiles',{}).get(profile,{}).get('kind',profile)
    roles.append({'role':name,'profile':profile,'provider':provider})
print(json.dumps(roles))
'''
PROVIDERS = {'codex': 'codex-acp', 'claude': 'claude-acp', 'ollama': 'ollama',
             'local': 'ollama', 'openai-subscription': 'chatgpt_codex'}
COMMON_EXTENSIONS = [
    {'type': 'builtin', 'name': 'developer'},
    {'type': 'platform', 'name': 'skills'},
]
RESULT_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {
        'success': {'type': 'boolean'},
        'summary': {'type': 'string'},
        'verdict': {'type': 'string', 'enum': ['completed', 'implemented', 'approve', 'request_changes', 'blocked']},
        'findings': {'type': 'array', 'items': {'type': 'string'}},
        'verification': {'type': 'array', 'items': {'type': 'string'}},
        'limitations': {'type': 'array', 'items': {'type': 'string'}},
    },
    'required': ['success', 'summary', 'verdict', 'findings', 'verification', 'limitations'],
}


def compose(flow_root, project, role, profile, overlay=None, stage="implement"):
    overlay = Path(overlay) if overlay else Path.home() / '.flow/user'
    return json.loads(subprocess.check_output(
        [sys.executable, '-B', '-c', COMPOSE, str(Path(flow_root).resolve()),
         str(Path(project).resolve()), str(overlay.resolve()), role, profile, stage], text=True))


def catalog(flow_root, project, overlay=None):
    overlay = Path(overlay) if overlay else Path.home() / '.flow/user'
    return json.loads(subprocess.check_output(
        [sys.executable, '-B', '-c', CATALOG, str(Path(flow_root).resolve()),
         str(Path(project).resolve()), str(overlay.resolve())], text=True))


def render(composed, provider, model=None, responsibility="implement"):
    """Provider aliases are explicit; a Claude model alias never becomes a Codex model."""
    actual_provider = PROVIDERS.get(provider, provider)
    actual_model = model or (composed.get('model') if PROVIDERS.get(composed.get('provider_kind', composed.get('profile'))) == actual_provider else None)
    if not actual_model or actual_model == 'inherit':
        actual_model = 'current' if actual_provider == 'codex-acp' else 'default'
    if actual_provider == 'ollama' and model is None:
        raise ValueError('Supply the configured Ollama model explicitly')
    role = composed['role']
    description = composed['metadata'].get('description', role)
    body = composed['body']
    agent = ('---\nname: ' + json.dumps(role) + '\ndescription: ' + json.dumps(description)
             + '\nmodel: ' + json.dumps(actual_model) + '\n---\n\n' + body + '\n')
    task_instructions = ('Implement the approved task with actual code and appropriate tests. Return verdict implemented or blocked.'
                      if responsibility == 'implement' else
                      'Perform the approved assignment using your own role instructions and expertise. Return completed or blocked; preserve the role-specific substantive output in the structured report.' if responsibility == 'role' else
                      'Independently review the actual change against the approved criteria. Return approve, request_changes or blocked. Report findings; leave fixes to the implementer unless separately assigned.')
    recipe = {
        'version': '1.0.0', 'title': role, 'description': description,
        'instructions': body + '\n\nTask responsibility:\n' + task_instructions
            + '\nAll roles have the same broad development tools within the existing workspace scope. Existing credential and external-action approvals apply.'
            + '\n\nProject context (task-specific, separate from role expertise):\n{{ project_context | indent(2) }}'
            + '\n\nApproved task and acceptance criteria:\n{{ task | indent(2) }}'
            + '\nReturn the required final JSON. Preserve verification results and limitations; report failure truthfully.',
        'prompt': 'Execute the task assigned in the instructions.',
        'parameters': [{'key': key, 'input_type': 'string', 'requirement': 'required', 'description': description}
                       for key, description in [('project_context', 'Project instructions, standards and relevant context'),
                                                ('task', 'Approved assignment, scope and acceptance criteria')]],
        'extensions': COMMON_EXTENSIONS,
        'settings': {'goose_provider': actual_provider, 'goose_model': actual_model, 'max_turns': 4},
        'response': {'json_schema': RESULT_SCHEMA},
    }
    return agent, recipe


def write_bundle(destination, composed, provider, model=None, responsibility="implement"):
    destination = Path(destination)
    agent, recipe = render(composed, provider, model, responsibility)
    role = composed['role']
    agent_path = destination / '.agents/agents' / (role + '.md')
    recipe_path = destination / 'recipes' / (role + '.yaml')
    for path in (agent_path, recipe_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    agent_path.write_text(agent)
    class RecipeDumper(yaml.SafeDumper):
        pass

    def text(dumper, value):
        return dumper.represent_scalar('tag:yaml.org,2002:str', value, style='|' if '\n' in value else None)

    RecipeDumper.add_representer(str, text)
    recipe_path.write_text(yaml.dump(recipe, Dumper=RecipeDumper, sort_keys=False, allow_unicode=True))
    return agent_path, recipe_path
