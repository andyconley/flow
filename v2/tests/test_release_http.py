"""Quota failures retain safe evidence and never weaken consumer checks."""
import contextlib
from email.message import Message
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from poc import managed, release_http


class ReleaseHttpTests(unittest.TestCase):
    def setUp(self):
        self.clock = 0
        self.sleeps = []
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {}, clear=True))
        self.stack.enter_context(patch.object(release_http.time, 'time', side_effect=lambda: 1800000000 + self.clock))
        self.stack.enter_context(patch.object(release_http.time, 'monotonic', side_effect=lambda: self.clock))
        self.stack.enter_context(patch.object(release_http.time, 'sleep', side_effect=self.sleep))
        self.stderr = self.stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
        self.request = urllib.request.Request('https://api.github.com/repos/andyconley/flow/releases/latest')

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.clock += seconds

    def failure(self, status=403, **headers):
        message = Message()
        for name, value in headers.items():
            message[name.replace('_', '-')] = str(value)
        error = urllib.error.HTTPError(self.request.full_url, status, 'PRIVATE_SERVER_REASON', message, io.BytesIO(b'PRIVATE_BODY'))
        return error

    def get(self, *responses, evidence=None):
        with patch.object(urllib.request, 'urlopen', side_effect=responses) as opened:
            value = release_http.github_json(self.request, evidence=evidence)
        return value, opened

    def test_plain_success_does_not_sleep_or_log(self):
        value, opened = self.get(io.BytesIO(b'{"tag_name":"v0.51.2"}'))
        self.assertEqual(value, {'tag_name': 'v0.51.2'})
        self.assertEqual(opened.call_args.args, (self.request,))
        self.assertEqual(self.sleeps, [])
        self.assertEqual(self.stderr.getvalue(), '')

    def test_primary_reset_waits_until_after_reset_and_keeps_request_anonymous(self):
        rows = []
        value, opened = self.get(self.failure(X_RateLimit_Remaining=0, X_RateLimit_Reset=1800000010,
            X_RateLimit_Limit=60, X_RateLimit_Used=60, X_GitHub_Request_Id='ABCD:1234'), io.BytesIO(b'{}'), evidence=rows)
        self.assertEqual(self.sleeps, [11])
        self.assertEqual(opened.call_count, 2)
        self.assertTrue(all(call.args[0].get_header('Authorization') is None for call in opened.call_args_list))
        self.assertEqual(rows[0]['auth_mode'], 'anonymous')
        self.assertEqual(rows[0]['remaining'], 0)
        self.assertEqual(rows[0]['reset_at'], '2027-01-15T08:00:10Z')
        self.assertEqual(rows[0]['request_id'], 'ABCD:1234')

    def test_retry_after_and_reset_both_respected(self):
        self.get(self.failure(Retry_After=' 20 ', X_RateLimit_Remaining=' 0 ', X_RateLimit_Reset=' 1800000010 '), io.BytesIO(b'{}'))
        self.assertEqual(self.sleeps, [20])

    def test_retry_after_http_date(self):
        self.get(self.failure(429, Retry_After='Fri, 15 Jan 2027 08:00:20 GMT'), io.BytesIO(b'{}'))
        self.assertEqual(self.sleeps, [21])

    def test_missing_or_stale_headers_back_off_and_stop_after_four_attempts(self):
        os.environ['FLOW_GITHUB_RETRY_WAIT_SECONDS'] = '3900'
        for headers in ({}, {'X_RateLimit_Remaining': 0, 'X_RateLimit_Reset': 1799999999}):
            self.clock = 0
            self.sleeps.clear()
            with self.subTest(headers=headers), self.assertRaisesRegex(ValueError, 'quota-attempt-limit'):
                self.get(*(self.failure(429, **headers) for _ in range(4)))
            self.assertEqual(self.sleeps, [60, 120, 240])

    def test_budget_is_total_and_never_clamps_wait_before_server_reset(self):
        os.environ['FLOW_GITHUB_RETRY_WAIT_SECONDS'] = '30'
        with self.assertRaisesRegex(ValueError, 'quota-budget-exhausted'):
            self.get(self.failure(Retry_After=20), self.failure(Retry_After=20))
        self.assertEqual(self.sleeps, [20])
        self.sleeps.clear()
        with self.assertRaisesRegex(ValueError, 'quota-budget-exhausted'):
            self.get(self.failure(X_RateLimit_Remaining=0, X_RateLimit_Reset=1800003600))
        self.assertEqual(self.sleeps, [])
        self.assertIn('1800003600', self.stderr.getvalue())

    def test_hosted_budget_can_wait_one_full_hour(self):
        os.environ['FLOW_GITHUB_RETRY_WAIT_SECONDS'] = '3900'
        self.get(self.failure(X_RateLimit_Remaining=0, X_RateLimit_Reset=1800003600), io.BytesIO(b'{}'))
        self.assertEqual(self.sleeps, [3601])

    def test_non_quota_http_errors_are_not_retried(self):
        for status in (401, 403, 404, 500):
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, 'http-error'):
                self.get(self.failure(status))
        self.assertEqual(self.sleeps, [])

    def test_secondary_limit_without_retry_headers_uses_bounded_fallback(self):
        error = self.failure(X_RateLimit_Remaining=57)
        error = urllib.error.HTTPError(self.request.full_url, 403, 'Forbidden', error.headers,
            io.BytesIO(json.dumps({'message': 'You have exceeded a secondary rate limit. PRIVATE_CONTEXT'}).encode()))
        self.get(error, io.BytesIO(b'{}'))
        self.assertEqual(self.sleeps, [60])
        self.assertNotIn('PRIVATE_CONTEXT', self.stderr.getvalue())

    def test_invalid_headers_body_reason_and_credentials_are_not_logged(self):
        self.request.add_header('Authorization', 'Bearer PRIVATE_TOKEN')
        rows = []
        with self.assertRaises(ValueError) as error:
            self.get(self.failure(403, X_RateLimit_Reset='PRIVATE_TOKEN', X_RateLimit_Remaining='PRIVATE_TOKEN',
                Retry_After='PRIVATE_TOKEN', X_GitHub_Request_Id='PRIVATE_TOKEN', Set_Cookie='PRIVATE_COOKIE'), evidence=rows)
        output = self.stderr.getvalue() + str(error.exception) + json.dumps(rows)
        self.assertNotIn('PRIVATE_', output)
        self.assertEqual(rows[0]['auth_mode'], 'token')
        self.assertIsNone(rows[0]['reset_at'])
        self.assertNotIn('request_id', rows[0])
        self.assertEqual(self.sleeps, [])

    def test_invalid_budget_is_rejected_before_network(self):
        for value in ('-1', 'nan', '3901', '300.5'):
            with patch.dict(os.environ, {'FLOW_GITHUB_RETRY_WAIT_SECONDS': value}), \
                    patch.object(urllib.request, 'urlopen') as opened, self.assertRaisesRegex(ValueError, '0 to 3900'):
                release_http.github_json(self.request)
            opened.assert_not_called()

    def test_latest_still_checks_manifest_and_release_identity_after_retry(self):
        tag = 'v0.51.2'
        base = 'https://github.com/andyconley/flow/releases/download/' + tag + '/'
        release = {'tag_name': tag, 'assets': [{'name': name, 'browser_download_url': base + name}
            for name in (*managed.ASSETS, 'release-manifest.json')]}
        manifest = {'schema_version': 1, 'version': tag, 'source_sha': 'a' * 40,
            'supported_targets': ['Darwin-arm64'], 'minimum_macos': '15.0',
            'assets': {name: {'sha256': 'b' * 64, 'size': 10} for name in managed.ASSETS}}
        with patch.object(urllib.request, 'urlopen', side_effect=[self.failure(Retry_After=1),
                io.BytesIO(json.dumps(release).encode()), io.BytesIO(json.dumps(manifest).encode())]):
            actual, urls = managed.latest()
        self.assertEqual(actual, manifest)
        self.assertEqual(self.sleeps, [1])
        manifest['source_sha'] = 'unrelated'
        with patch.object(urllib.request, 'urlopen', side_effect=[io.BytesIO(json.dumps(release).encode()),
                io.BytesIO(json.dumps(manifest).encode())]), self.assertRaisesRegex(ValueError, 'source identity'):
            managed.latest()

    def test_consumer_keeps_wait_policy_but_never_inherits_tokens(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
        import v2_release_checks
        with patch.dict(os.environ, {'FLOW_GITHUB_RETRY_WAIT_SECONDS': '3900',
                **{name: 'PRIVATE_TOKEN' for name in ('GITHUB_TOKEN', 'GH_TOKEN', 'FLOW_RELEASE_READ_TOKEN', 'GIT_ASKPASS', 'SSH_ASKPASS')}}), \
                patch.object(subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '{}')) as run:
            v2_release_checks.flow(Path('/isolated/home'), 'update', '--check', '--json')
        self.assertEqual(run.call_args.kwargs['env']['FLOW_GITHUB_RETRY_WAIT_SECONDS'], '3900')
        self.assertNotIn('PRIVATE_TOKEN', json.dumps(run.call_args.kwargs['env']))
        self.assertEqual(run.call_args.args[0], ['/isolated/home/.local/bin/flow', 'update', '--check', '--json'])

    def test_failed_consumer_quota_evidence_is_written_before_failure(self):
        import tempfile
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
        import release_verify_published as verifier
        import v2_release_checks
        row = {'status': 403, 'remaining': 0, 'reset_epoch': 1800003600,
            'auth_mode': 'anonymous', 'decision': 'quota-budget-exhausted'}
        output = release_http.PREFIX + json.dumps(row) + '\nGitHub release metadata HTTP 403\n'
        with tempfile.TemporaryDirectory() as raw, contextlib.ExitStack() as stack:
            root = Path(raw)
            plan = {'source_sha': 'a' * 40, 'release_required': True,
                'predicted_release': {'version': '0.51.2', 'tag': 'v0.51.2', 'notes_sha256': verifier.hashlib.sha256(b'notes').hexdigest()}}
            # Isolate setup; keep the actual consumer loop, failure handling,
            # evidence serialization, and terminal failure assertion intact.
            stack.enter_context(patch.object(verifier, 'load_plan', return_value=plan))
            stack.enter_context(patch.object(verifier, 'load_evidence', return_value={'overall_result': 'passed'}))
            stack.enter_context(patch.object(verifier, 'file_sha256', return_value='b' * 64))
            stack.enter_context(patch.object(verifier, '_checked', side_effect=['', '', 'c' * 40, 'a' * 40,
                'c' * 40, 'subject', 'M\tCHANGELOG.md', '## [0.51.2]']))
            stack.enter_context(patch.object(verifier, 'validate_release_commit_shape'))
            stack.enter_context(patch.object(verifier, '_release_body', return_value=('notes', 'https://github.com/andyconley/flow')))
            stack.enter_context(patch.object(managed, 'latest', return_value=({'source_sha': 'a' * 40}, {})))
            stack.enter_context(patch.object(verifier, 'verify_public_manifest'))
            stack.enter_context(patch.object(managed, 'fetch_assets', side_effect=lambda manifest, target, urls: target.mkdir()))
            stack.enter_context(patch.object(managed, 'install_release'))
            rollback = stack.enter_context(patch.object(managed, 'rollback'))
            flow = stack.enter_context(patch.object(v2_release_checks, 'flow', side_effect=[(0, 'v0.51.2'), (0, '{}'), (1, output)]))
            with self.assertRaisesRegex(verifier.ContractError, 'public-release-update-check failed'):
                verifier.verify(root/'plan', root/'evidence', 'https://github.com/andyconley/flow.git',
                    'andyconley/flow', root/'result.json', None)
            result = json.loads((root/'result.json').read_text())
            self.assertEqual(result['overall_result'], 'failed')
            self.assertEqual(result['quota_responses'], [{'check_id': 'public-release-update-check', **row}])
            self.assertEqual(result['checks'][-1]['id'], 'failure')
            self.assertEqual(flow.call_count, 3)
            rollback.assert_not_called()


if __name__ == '__main__':
    unittest.main()
