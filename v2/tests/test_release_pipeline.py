"""Release identity, security boundaries and fail-closed candidate evidence."""
import importlib.util
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import release_gate
import v2_release_checks
from release_verify_published import verify_public_manifest


class ReleasePipelineTests(unittest.TestCase):
    def test_bootstrap_rejects_legacy_release_before_running_its_installer(self):
        script=(ROOT/'install.sh').read_text().split("<<'PYTHON'\n",1)[1].split('\nPYTHON',1)[0]
        tag='v0.51.0';base='https://github.com/andyconley/flow/releases/download/'+tag+'/'
        names=('flow-code.tar.gz','python-wheels.tar.gz','goose-macos-arm64.gz','goose-macos-arm64.json','release-manifest.json')
        payload={'tag_name':tag,'assets':[{'name':name,'browser_download_url':base+name} for name in names]}
        with patch.object(sys,'argv',['bootstrap','andyconley/flow']),patch('builtins.print') as output:
            with patch('urllib.request.urlopen',side_effect=lambda *a,**kw:io.BytesIO(json.dumps(payload).encode())):
                exec(compile(script,'install.sh bootstrap','exec'),{})
            output.assert_called_once_with(tag)
            payload['assets']=[]
            with patch('urllib.request.urlopen',side_effect=lambda *a,**kw:io.BytesIO(json.dumps(payload).encode())):
                with self.assertRaisesRegex(SystemExit,'legacy installation is not supported'):
                    exec(compile(script,'install.sh bootstrap','exec'),{})

    def test_public_manifest_is_bound_to_exact_verified_build(self):
        manifest={'version':'v0.51.0'}
        raw=json.dumps(manifest).encode();digest=hashlib.sha256(raw).hexdigest()
        urls={'release-manifest.json':'https://example.invalid/release-manifest.json'}
        with patch('urllib.request.urlopen',side_effect=lambda *a,**kw:io.BytesIO(raw)):
            verify_public_manifest(manifest,urls,digest)
            for expected in (None,'0'*64):
                with self.assertRaises(release_gate.ContractError):verify_public_manifest(manifest,urls,expected)
            with self.assertRaises(release_gate.ContractError):verify_public_manifest({'version':'changed'},urls,digest)

    def test_every_publisher_depends_on_verified_exact_build_and_candidate(self):
        workflow=yaml.safe_load((ROOT/'.github/workflows/release.yml').read_text())
        jobs=workflow['jobs'];publish=jobs['publish']
        self.assertEqual(set(publish['needs']),{'analyze','build-runtime','validate-candidate'})
        self.assertIn("needs.validate-candidate.result == 'success'",publish['if'])
        serialized=json.dumps(workflow)
        self.assertNotIn('continue-on-error',serialized)
        self.assertNotIn('always()',serialized)
        self.assertIn('Verify publication assets against build identity',serialized)
        self.assertIn('Reject release-analysis drift',serialized)
        self.assertIn('Refresh live baseline immediately before publication',serialized)
        self.assertEqual(workflow['permissions'],{'contents':'read'})
        self.assertNotIn('secrets.GITHUB_TOKEN',json.dumps(jobs['analyze']))
        self.assertNotIn('secrets.GITHUB_TOKEN',json.dumps(jobs['validate-candidate']))
        self.assertIn('needs.publish.result',jobs['verify-published']['if'])
        self.assertIn('build-runtime',jobs['verify-published']['needs'])
        self.assertIn('needs.build-runtime.outputs.manifest_sha256',json.dumps(jobs['verify-published']))

    def test_production_builder_pins_source_patch_compiler_and_has_no_live_checks(self):
        workflow=(ROOT/'.github/workflows/goose-build.yml').read_text()
        builder=(ROOT/'scripts/build_v2_release.py').read_text()
        self.assertIn('rustup toolchain install 1.99.0',workflow)
        self.assertIn('Darwin/arm64',workflow)
        self.assertIn('verify_v2_consumer.py',workflow)
        self.assertNotIn('--existing-binary',workflow)
        self.assertIn('verify_goose_source',builder)
        self.assertIn("'--locked'",builder)
        self.assertIn("'--require-hashes'",(ROOT/'v2/poc/managed.py').read_text())
        self.assertNotIn('native_inference',workflow)
        self.assertNotIn('auth login',workflow)
        # Main's release workflow already owns the production build. Avoid
        # launching a second identical Rust build for the same main push.
        consumer=yaml.safe_load((ROOT/'.github/workflows/openhands-runtime.yml').read_text())
        events=consumer.get('on',consumer.get(True))
        self.assertNotIn('push',events)

    def test_failure_of_each_required_check_stops_all_later_checks(self):
        environment={
            'FLOW_RELEASE_REQUIRED':'true','FLOW_RELEASE_NEW_RELEASE_VERSION':'0.51.0',
            'FLOW_RELEASE_NEW_RELEASE_GIT_TAG':'v0.51.0','FLOW_RELEASE_NEW_RELEASE_GIT_HEAD':'a'*40,
            'FLOW_RELEASE_NEW_RELEASE_NOTES':'## Features\n\n* Managed v2 release\n','FLOW_RELEASE_PREVIOUS_VERSION':'0.50.1',
            'FLOW_RELEASE_PREVIOUS_TAG':'v0.50.1','FLOW_RELEASE_PREVIOUS_COMMIT':'b'*40,
            'FLOW_RELEASE_SOURCE_SHA':'a'*40,'FLOW_RELEASE_REPOSITORY':'andyconley/flow',
            'FLOW_RELEASE_WORKFLOW':'Release','FLOW_RELEASE_RUN_ID':'1','FLOW_RELEASE_RUN_ATTEMPT':'1',
            'FLOW_RELEASE_CREATED_AT':'2026-10-20T00:00:00Z'}
        plan=release_gate.plan_from_environment(environment)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);path=root/'plan.json';release_gate.write_canonical_json(path,plan)
            for index,failed in enumerate(release_gate.STABLE_CHECK_IDS):
                seen=[]
                overrides={name:(lambda name=name:(seen.append(name) or (0,'passed\n'))) for name in release_gate.STABLE_CHECK_IDS}
                with patch('release_candidate._git',return_value='a'*40),patch('release_candidate.create_candidate_remote',return_value='file:///isolated/candidate.git'):
                    evidence,code=v2_release_checks.run_candidate(path,root/failed/'evidence.json',failed,overrides)
                self.assertEqual(code,1)
                self.assertEqual(evidence['overall_result'],'failed')
                self.assertEqual(seen,list(release_gate.STABLE_CHECK_IDS[:index]))
                self.assertTrue(all(row['result']=='not_run' for row in evidence['checks'][index+1:]))
