"""Execution-environment readiness and honest, revision-bound check evidence."""
import os
from pathlib import Path
import shutil
from .artifacts import ArtifactError, validate_brief
from .project_python import check_command
from .contracts import digest_tree


def preflight(workspace, brief):
    validate_brief(brief)
    cwd = Path(workspace).resolve()
    environment = {'cwd': str(cwd), 'PATH': os.environ.get('PATH', os.defpath)}
    errors = []
    if not cwd.is_dir(): errors.append('Working directory does not exist: '+str(cwd))
    try:
        command = check_command(cwd, brief['check_command'])
    except ValueError as error:
        command = brief['check_command']; errors.append(str(error))
    resolved = {}
    for name in [command[0], *brief.get('prerequisites', [])]:
        if '/' in name:
            path = Path(name).expanduser(); path = path if path.is_absolute() else cwd/path
            found = str(path) if path.is_file() and os.access(path, os.X_OK) else None
        else:
            # Relative PATH entries are interpreted in the execution cwd.
            search = os.pathsep.join(str(cwd/p) if not Path(p).is_absolute() else p for p in environment['PATH'].split(os.pathsep))
            found = shutil.which(name, path=search)
        resolved[name] = found
        if not found: errors.append('Executable/prerequisite unavailable: '+name)
    if resolved.get(command[0]): command = [resolved[command[0]], *command[1:]]
    return {**environment, 'command': command, 'executables': resolved, 'ready': not errors,
            'errors': errors, 'instruction': 'Prepare the declared prerequisites in this environment with existing authorization, then retry. Flow does not install dependencies or change credentials.'}


def require_ready(workspace, brief):
    result = preflight(workspace, brief)
    if not result['ready']: raise ArtifactError('; '.join(result['errors'])+'; '+result['instruction'])
    return result


def evidence(brief, workspace, brief_ref, result):
    criteria = brief['acceptance_criteria']
    criteria = [criteria] if isinstance(criteria, str) else criteria
    coverage = brief.get('coverage') or [{'criterion': c, 'method': 'uncovered', 'evidence': 'No explicit verification mapping supplied'} for c in criteria]
    return {**result, 'brief_ref': brief_ref, 'candidate_revision': digest_tree(workspace),
            'check_scope': brief.get('check_scope', 'smoke'), 'coverage': coverage,
            'acceptance_proven': bool(result.get('passed')) and brief.get('check_scope') == 'acceptance' and all(row['method'] == 'automated' for row in coverage),
            'manual_review_required': [row for row in coverage if row['method'] == 'manual'],
            'uncovered': [row for row in coverage if row['method'] == 'uncovered']}
