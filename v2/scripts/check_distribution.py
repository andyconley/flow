"""Credential-free distribution checks; no provider capability qualification."""
from pathlib import Path
import hashlib
import json
ROOT=Path(__file__).resolve().parents[1]
lock=json.loads((ROOT/'vendor/goose.lock.json').read_text())
assert hashlib.sha256((ROOT/'vendor'/lock['patch']).read_bytes()).hexdigest()==lock['patch_sha256']
assert lock['repository']=='https://github.com/aaif-goose/goose.git'
assert len(lock['base_commit'])==40
assert len(list((ROOT/'role-bundle/recipes').glob('*.yaml')))==13
assert len(list((ROOT/'skills').glob('flow-*/SKILL.md')))==14
print('Goose source/patch lock, role inventory and native command inventory verified')
