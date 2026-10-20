"""Choose a project Python consistently for workers and independent checks."""
import os
from pathlib import Path
import re

PYTHON = re.compile(r'python(?:[23](?:\.\d+)?)?$')


def select(project, command=None):
    project = Path(project).resolve()
    executable = command[0] if command else ''
    python_check = bool(PYTHON.fullmatch(Path(executable).name))
    if python_check and ('/' in executable):
        path = Path(executable).expanduser()
        selected = path if path.is_absolute() else project/path
    else:
        selected = next((project/relative for relative in
                         ('.venv/bin/python', '.venv/bin/python3', 'venv/bin/python', 'venv/bin/python3')
                         if (project/relative).is_file()), None)
    if selected is None:
        if python_check:
            raise ValueError('Python check requires a project .venv/venv or an explicit interpreter path in check_command; ambient python3 is not selected')
        return None
    # Keep the venv path: resolving its symlink would lose pyvenv.cfg discovery.
    selected = selected.absolute()
    if not selected.is_file() or not os.access(selected, os.X_OK):
        raise ValueError('Project Python is missing or not executable: '+str(selected))
    return selected


def check_command(project, command):
    selected = select(project, command)
    if selected and PYTHON.fullmatch(Path(command[0]).name):
        return [str(selected), *command[1:]]
    return list(command)
