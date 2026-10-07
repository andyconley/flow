"""Narrow legacy bootstrap recovery cannot hide other upgrade failures."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import release_candidate


class LegacyUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.source = self.home / '.flow/source/cli'
        self.source.mkdir(parents=True)
        self.config = self.home / '.flow/config.toml'
        self.config.write_text('[install]\nversion = "v0.40.16"\n')
        self.old = subprocess.check_output(['git', 'show', 'v0.40.16:cli/maf_runtime.py'],
            cwd=Path(__file__).resolve().parents[1], text=True)
        (self.source / 'maf_runtime.py').write_text(self.old)
        self.failure = (1, 'managed MAF runtime provisioning failed: version_mismatch: run runtime install-maf\n')

    def test_known_failure_with_verified_rollback_uses_bootstrap_and_readiness(self):
        with patch.object(release_candidate, '_flow', side_effect=[self.failure, (0, '{"state":"ready"}')]) as flow, \
                patch.object(release_candidate, '_install', return_value=(0, 'Installed target release')) as install:
            result = release_candidate._upgrade_previous('remote', self.home, 'v0.40.16')
        self.assertEqual(result[0], 0)
        self.assertIn('Legacy updater exit=1', result[1])
        self.assertIn('Recovery method:', result[1])
        install.assert_called_once_with('remote', self.home)
        self.assertEqual(flow.call_args_list[-1].args[1:], ('runtime', 'readiness', '--json'))

    def test_other_failures_versions_and_modified_checker_never_bootstrap(self):
        for tag, failure, modified in [('v0.40.16', (1, 'network failed'), False),
                ('v0.41.0', self.failure, False), ('v0.40.16', self.failure, True)]:
            with self.subTest(tag=tag, failure=failure, modified=modified):
                (self.source / 'maf_runtime.py').write_text(self.old + ('\n# local edit\n' if modified else ''))
                with patch.object(release_candidate, '_flow', return_value=failure), \
                        patch.object(release_candidate, '_install') as install:
                    self.assertEqual(release_candidate._upgrade_previous('remote', self.home, tag), failure)
                install.assert_not_called()

    def test_failed_rollback_never_bootstraps(self):
        def update(*args):
            self.config.write_text('[install]\nversion = "v0.41.0"\n')
            return self.failure
        with patch.object(release_candidate, '_flow', side_effect=update), \
                patch.object(release_candidate, '_install') as install:
            self.assertEqual(release_candidate._upgrade_previous('remote', self.home, 'v0.40.16'), self.failure)
        install.assert_not_called()

    def test_successful_update_never_bootstraps(self):
        with patch.object(release_candidate, '_flow', return_value=(0, 'updated')), \
                patch.object(release_candidate, '_install') as install:
            self.assertEqual(release_candidate._upgrade_previous('remote', self.home, 'v0.40.16'), (0, 'updated'))
        install.assert_not_called()

    def test_bootstrap_or_readiness_failure_remains_failure(self):
        for bootstrap, ready in [((1, 'bootstrap failed'), (0, 'ready')),
                ((0, 'installed'), (1, 'runtime unready'))]:
            with self.subTest(bootstrap=bootstrap, ready=ready):
                with patch.object(release_candidate, '_flow', side_effect=[self.failure, ready]), \
                        patch.object(release_candidate, '_install', return_value=bootstrap):
                    result = release_candidate._upgrade_previous('remote', self.home, 'v0.40.16')
                self.assertEqual(result[0], 1)
