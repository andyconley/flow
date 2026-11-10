"""Snapshot project facts separately from reusable role expertise."""
from pathlib import Path
import hashlib
import json
import subprocess

# Goose refuses a recipe whose serialized parameters exceed 128 KiB ("Serialized
# parameters exceed the 128 KiB limit"). Delegated role recipes carry the task and
# project context as parameter defaults, so both must fit together.
DELEGATE_PARAMETER_LIMIT = 128 * 1024
# Covers the per-operation task suffix, parameter descriptions and the small gap
# between this module's measure and Goose's own serialization.
PARAMETER_HEADROOM = 4 * 1024
RECIPE_PARAMETERS = (('project_context', 'Project instructions, standards and relevant context'),
                     ('task', 'Approved assignment, scope and acceptance criteria'))


def _checkout(directory):
    """(repository common dir, working-tree top level) for a directory, or None."""
    result = subprocess.run(['git', '-C', str(directory), 'rev-parse', '--path-format=absolute',
                             '--git-common-dir', '--show-toplevel'], capture_output=True, text=True)
    lines = result.stdout.split('\n')
    if result.returncode != 0 or len(lines) < 2 or not lines[0] or not lines[1]:
        return None
    return Path(lines[0]).resolve(), Path(lines[1]).resolve()


def resolve(project):
    root = Path(project).resolve()
    documents = []
    checkouts = {}
    def checkout(directory):
        if directory not in checkouts:
            checkouts[directory] = _checkout(directory)
        return checkouts[directory]
    def superseded_by_own_checkout(directory, name):
        # A worktree nested inside another checkout of its own repository sees that
        # checkout's files as ancestors. Skip one only when it is a *separate* checkout
        # (different working tree) and the project's checkout has the same file at the
        # same repository path; that copy is the revision for this branch. A plain
        # subdirectory shares its repository's working tree and keeps every ancestor.
        own, other = checkout(root), checkout(directory)
        if not own or not other or own[0] != other[0] or own[1] == other[1]:
            return False
        counterpart = own[1] / directory.relative_to(other[1])
        # Only a counterpart this snapshot also loads (the project or one of its ancestors).
        return (counterpart == root or counterpart in root.parents) and (counterpart / name).is_file()
    # Ancestor context first, most-specific context last. Native-client instructions
    # remain in force; this snapshot makes their sources visible at a handoff.
    for directory in [*reversed(root.parents), root]:
        names = ['AGENTS.md', 'CODEX.md', 'CLAUDE.md', '.flow/PROJECT.md', '.glg/PROJECT.md']
        if directory == root:
            names += ['.flow/memory/STATE.md']
        for name in names:
            path = directory / name
            if not path.is_file():
                continue
            if directory != root and superseded_by_own_checkout(directory, name):
                continue
            content = path.read_text(encoding='utf-8')
            documents.append({'path': str(path), 'revision': hashlib.sha256(content.encode()).hexdigest(),
                              'authority': 'companion' if name.endswith('STATE.md') else 'project',
                              'content': content})
    # Identical content adds nothing; keep the most-specific occurrence.
    later = set()
    for index in range(len(documents) - 1, -1, -1):
        revision = documents[index]['revision']
        if revision in later:
            documents[index] = None
        later.add(revision)
    documents = [document for document in documents if document]
    def git(*args):
        result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None
    return {'workspace': str(root), 'instruction_precedence': 'ancestor to project; most-specific wins; native instructions remain authoritative',
            'documents': documents, 'git_head': git('rev-parse', 'HEAD'),
            'git_branch': git('branch', '--show-current'), 'git_status': git('status', '--short'),
            'historical_flow': str(root / '.flow') if (root / '.flow').exists() else None}


def json_size(text):
    """Bytes of a string once serialized as a JSON value, the unit Goose limits."""
    return len(json.dumps(text, ensure_ascii=False).encode('utf-8'))


def _section(document):
    return f"Source: {document['path']} ({document['authority']}, {document['revision']})\n{document['content']}"


def _reference(document):
    size = len(document['content'].encode('utf-8'))
    return (f"Source: {document['path']} ({document['authority']}, {document['revision']})\n"
            f"Not inlined: {size} bytes would exceed the delegate parameter budget. Read this file directly if it is relevant.")


def render(value, budget=None):
    """Render the snapshot; with a budget, keep the JSON-serialized text within it.

    Under a budget, project instructions are inlined before companion state, most
    specific first. A document that does not fit is named by path and revision so
    the reader can still open it. Without a budget the full text is rendered.
    """
    documents = value['documents']
    head = [f"Workspace: {value['workspace']}", value['instruction_precedence']]
    tail = []
    if value.get('historical_flow'):
        tail.append(f"Historical Flow artifacts remain at {value['historical_flow']}; verify referenced evidence, do not migrate active runs.")
    if value.get('legacy_handoff'):
        tail.append('Explicit legacy handoff (fresh v2 approval required): '+str(value['legacy_handoff']))
    inlined = set(range(len(documents)))
    if budget is not None:
        inlined = set()
        used = json_size('\n\n'.join([*head, *map(_reference, documents), *tail]))
        for index in sorted(range(len(documents)), key=lambda i: (documents[i]['authority'] == 'companion', -i)):
            delta = json_size(_section(documents[index])) - json_size(_reference(documents[index]))
            if used + delta <= budget:
                inlined.add(index)
                used += delta
    body = [_section(document) if index in inlined else _reference(document) for index, document in enumerate(documents)]
    return '\n\n'.join([*head, *body, *tail])


def context_budget(task, reserved=''):
    """JSON bytes left for rendered project context beside a task and fixed suffix."""
    return DELEGATE_PARAMETER_LIMIT - PARAMETER_HEADROOM - json_size(task) - json_size(reserved)


def delegate_parameter_bytes(task, project_context):
    defaults = {'task': task, 'project_context': project_context}
    parameters = [{'key': key, 'input_type': 'string', 'requirement': 'required', 'description': description,
                   'default': defaults[key]} for key, description in RECIPE_PARAMETERS]
    return len(json.dumps(parameters, separators=(',', ':'), ensure_ascii=False).encode('utf-8'))


def delegate_parameter_error(task, project_context):
    size = delegate_parameter_bytes(task, project_context)
    if size <= DELEGATE_PARAMETER_LIMIT:
        return None
    return (f'Delegate recipe parameters are {size} bytes (task {json_size(task)}, project context '
            f'{json_size(project_context)}); Goose rejects recipes whose serialized parameters exceed '
            f'{DELEGATE_PARAMETER_LIMIT} bytes (128 KiB). Reduce the approved brief or the project context '
            'documents, then create a new work item. No execution was submitted.')
