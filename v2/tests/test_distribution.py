"""Source distribution and dependency provenance, without credentials or models."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import unittest
import yaml
ROOT=Path(__file__).resolve().parents[1]

class DistributionTests(unittest.TestCase):
    def test_locked_goose_patch_is_the_shipped_dependency(self):
        lock=json.loads((ROOT/'vendor/goose.lock.json').read_text())
        self.assertEqual(hashlib.sha256((ROOT/'vendor'/lock['patch']).read_bytes()).hexdigest(),lock['patch_sha256'])
        self.assertEqual(lock['repository'],'https://github.com/aaif-goose/goose.git')
        self.assertEqual(len(lock['base_commit']),40)

    def test_all_role_expertise_and_common_tools_are_distributed(self):
        roles=json.loads((ROOT/'role-bundle/catalog.json').read_text())['roles'];self.assertEqual(len(roles),13)
        for entry in roles:
            agent=ROOT/'role-bundle'/entry['agent'];recipe=ROOT/'role-bundle'/entry['recipe']
            self.assertTrue(agent.is_file());value=yaml.safe_load(recipe.read_text())
            self.assertIn(agent.read_text().split('---',2)[-1].strip(),value['instructions'])
            self.assertIn({'type':'builtin','name':'developer'},value['extensions'])
            self.assertIn({'type':'platform','name':'skills'},value['extensions'])
            self.assertEqual([x['key'] for x in value['parameters']],['project_context','task'])

    def test_bootstrap_help_and_dry_run_do_not_prepare_dependencies(self):
        for args in (['--help'],['prepare','--build-goose','--dry-run']):
            r=subprocess.run([sys.executable,str(ROOT/'bootstrap.py'),*args],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
        self.assertTrue((ROOT.parent/'install-flow-v2.sh').is_file())
