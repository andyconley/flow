import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))
from codex_registration import BEGIN, END, registration_config, write_registration_config, RESERVED_AGENT_NAMES


class CodexRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.config = self.root / '.codex/config.toml'
        self.config.parent.mkdir()
        self.target = self.root / '.flow/generated/agents/codex/support-lead.toml'
        self.roles = {'support-lead': self.target}

    def plan(self, receipt=None):
        return registration_config(self.root, self.roles, receipt)

    def test_preserves_settings_bytes_modes_backups_and_idempotence(self):
        raw = '# comment\r\nmodel = "existing"\r\n[projects."/private/work"]\r\ntrust_level = "untrusted"\r\n[agents.custom]\r\nconfig_file = "custom.toml"'
        self.config.write_bytes(raw.encode())
        self.config.chmod(0o640)
        before, after, digest = self.plan()
        self.assertEqual(before, raw)
        self.assertTrue(after.startswith(raw))
        write_registration_config(self.root, before, after)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o640)
        parsed = tomllib.loads(after)
        self.assertEqual(parsed['model'], 'existing')
        self.assertEqual(parsed['projects']['/private/work']['trust_level'], 'untrusted')
        self.assertEqual(parsed['agents']['custom']['config_file'], 'custom.toml')
        self.assertEqual(parsed['agents']['support-lead']['config_file'], str(self.target))
        backups = list((self.root / '.flow/backups/codex-role-registration').glob('*.toml'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), raw.encode())
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
        b, a, _ = self.plan({'block_sha256': digest})
        self.assertEqual(b, a)
        write_registration_config(self.root, b, a)
        self.assertEqual(len(list(backups[0].parent.glob('*.toml'))), 1)

    def test_all_reserved_names_fail_before_writes(self):
        original = '# untouched\nmodel = "user"\n'
        self.config.write_text(original)
        for name in RESERVED_AGENT_NAMES:
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, 'reserved agents settings'):
                    registration_config(self.root, {name: self.target}, None)
                self.assertEqual(self.config.read_text(), original)
                self.assertFalse((self.root / '.flow/backups').exists())

    def test_conflicting_user_registration_is_not_adopted_or_written(self):
        raw = '[agents."support-lead"]\nconfig_file = "my-custom-role.toml"\n'
        self.config.write_text(raw)
        with self.assertRaisesRegex(ValueError, 'user-owned registration collision'):
            self.plan()
        self.assertEqual(self.config.read_text(), raw)
        self.assertFalse((self.root / '.flow/backups').exists())

    def test_compatible_user_registration_remains_user_owned(self):
        raw = f'[agents."support-lead"]\nconfig_file = {json.dumps(str(self.target))}\ndescription = "User wording"\n'
        self.config.write_text(raw)
        before, after, _ = self.plan()
        self.assertEqual(after, raw)
        self.assertNotIn(BEGIN, after)

    def test_user_owned_symlink_registration_is_preserved_as_conflict(self):
        self.target.parent.mkdir(parents=True)
        self.target.write_text("# generated definition")
        link = self.root / ".codex/agents/support-lead.toml"
        link.parent.mkdir(parents=True)
        link.symlink_to(self.target)
        original = f'[agents."support-lead"]\nconfig_file = {json.dumps(str(link))}\n'
        self.config.write_text(original)
        with self.assertRaisesRegex(ValueError, 'user-owned registration collision'):
            self.plan()
        self.assertEqual(self.config.read_text(), original)
        self.assertTrue(link.is_symlink())

    def test_edited_and_unowned_blocks_are_preserved(self):
        _, after, digest = self.plan()
        self.config.write_text(after)
        with self.assertRaisesRegex(ValueError, 'no Flow ownership'):
            self.plan()
        edited = after.replace(str(self.target), '/custom/owned.toml')
        self.config.write_text(edited)
        with self.assertRaisesRegex(ValueError, 'were edited'):
            self.plan({'block_sha256': digest})
        self.assertEqual(self.config.read_text(), edited)

    def test_removal_preserves_original_and_unmanaged_additions(self):
        original = '# original\nmodel = "user"'
        self.config.write_text(original)
        _, after, digest = self.plan()
        addition = '\n[agents.extra]\nconfig_file = "extra.toml"\n'
        self.config.write_text(after + addition)
        before, after, _ = registration_config(self.root, {}, {'block_sha256': digest})
        self.assertEqual(after, original + addition)
        self.assertNotIn('support-lead', after)

    def test_suffix_keys_cannot_silently_change_owned_role(self):
        _, after, digest = self.plan()
        self.config.write_text(after + 'description = "User edit outside marker"\n')
        with self.assertRaisesRegex(ValueError, 'collision outside managed block'):
            self.plan({'block_sha256': digest})

    def test_symlink_config_and_changed_snapshot_are_preserved(self):
        outside = self.root / 'custom.toml'
        outside.write_text('# custom\n')
        self.config.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'is a symlink'):
            self.plan()
        self.config.unlink()
        before, after, _ = self.plan()
        self.config.write_text('# concurrent edit\n')
        with self.assertRaisesRegex(ValueError, 'changed during sync'):
            write_registration_config(self.root, before, after)
        self.assertEqual(self.config.read_text(), '# concurrent edit\n')

    def test_partial_write_can_reconcile_only_exact_desired_owned_block(self):
        _, old, digest = self.plan()
        self.config.write_text(old)
        roles = {**self.roles, 'architect': self.target.with_name('architect.toml')}
        _, newer, _ = registration_config(self.root, roles, {'block_sha256': digest})
        self.config.write_text(newer)
        before, after, _ = registration_config(self.root, roles, {'block_sha256': digest})
        self.assertEqual(before, after)
