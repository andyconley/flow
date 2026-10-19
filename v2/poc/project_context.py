"""Snapshot project facts separately from reusable role expertise."""
from pathlib import Path
import hashlib
import subprocess


def resolve(project):
    root = Path(project).resolve()
    documents = []
    # Ancestor context first, most-specific context last. Native-client instructions
    # remain in force; this snapshot makes their sources visible at a handoff.
    for directory in [*reversed(root.parents), root]:
        names = ['AGENTS.md', 'CODEX.md', 'CLAUDE.md', '.flow/PROJECT.md', '.glg/PROJECT.md']
        if directory == root:
            names += ['.flow/memory/STATE.md']
        for name in names:
            path = directory / name
            if path.is_file():
                content = path.read_text()
                documents.append({'path': str(path), 'revision': hashlib.sha256(content.encode()).hexdigest(),
                                  'authority': 'companion' if name.endswith('STATE.md') else 'project',
                                  'content': content})
    def git(*args):
        result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None
    return {'workspace': str(root), 'instruction_precedence': 'ancestor to project; most-specific wins; native instructions remain authoritative',
            'documents': documents, 'git_head': git('rev-parse', 'HEAD'),
            'git_branch': git('branch', '--show-current'), 'git_status': git('status', '--short'),
            'historical_flow': str(root / '.flow') if (root / '.flow').exists() else None}


def render(value):
    sections = [f"Workspace: {value['workspace']}", value['instruction_precedence']]
    for document in value['documents']:
        sections.append(f"Source: {document['path']} ({document['authority']}, {document['revision']})\n{document['content']}")
    if value.get('historical_flow'):
        sections.append(f"Historical Flow artifacts remain at {value['historical_flow']}; verify referenced evidence, do not migrate active runs.")
    return '\n\n'.join(sections)
