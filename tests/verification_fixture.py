"""Small valid evidence fixture for lifecycle tests (not model-quality evidence)."""
import json
import subprocess
import sys
import verification


def prepare(root):
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    (root / 'check.py').write_text("print('fixture check passed')\n")


def outputs(root, directory, stage, run):
    if stage == 'plan':
        (directory / 'verification-plan.json').write_text(json.dumps({
            'schema_version': 1, 'repair_limit': 2, 'evaluation_inputs': ['check.py'],
            'checks': [{'id': 'behavior', 'criterion': 'fixture', 'argv': [sys.executable, 'check.py']}]}))
    if stage == 'implement':
        verification.capture(root, run, 'behavior', 'fixture-producer', 'fixture-assignment', 'Python fixture')
