"""Offline defaults review, byte preservation and transaction failure fixtures."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))
import defaults_review as review


class DefaultsReviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.user = self.root / 'user'
        self.user.mkdir()
        self.incoming = self.root / 'incoming.toml'
        self.incoming.write_text('[routing]\nprovider="new"\n')
        self.overlay = self.user / 'flow.toml'
        self.overlay.write_text('# mine\n[routing]\nprovider="old" # explanation\n')

    @contextlib.contextmanager
    def isolated_cwd(self):
        """Run inside `self.root`, which has no `.flow` or `.git` of its own.

        `install_command`/`update_command` now fold the current project into
        the review scope automatically when the process cwd sits inside one
        (see `lifecycle._with_current_project_scope`). The checkout running
        this test suite has its own `.flow` overlay, so a test that calls
        those functions in-process without isolating cwd would pick it up by
        surprise. Isolating here keeps that real automatic-inclusion behavior
        intact while giving these tests a cwd it has nothing to find.
        """
        previous = os.getcwd()
        os.chdir(self.root)
        try:
            yield
        finally:
            os.chdir(previous)

    def command(self, *arguments):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            review.main(['--incoming', str(self.incoming), '--user-overlay', str(self.user), *arguments])
        return output.getvalue()

    def test_provider_selection_preview_unions_disables_instead_of_replacing(self):
        # disabled_candidates is a monotonic union across layers (see
        # provider_selection.merge_selection_policy), not a last-layer-wins
        # replacement. A generic recursive-merge preview would show the
        # project scope's removal dropping the framework's own disable
        # entirely instead of surfacing the real post-removal union.
        self.incoming.write_text('[provider_selection]\ndisabled_candidates=["framework-x"]\n')
        self.overlay.write_text('[provider_selection]\ndisabled_candidates=["user-y"]\n')
        project = self.root / 'project'
        (project / '.flow').mkdir(parents=True)
        (project / '.flow/flow.toml').write_text('[provider_selection]\ndisabled_candidates=["project-z"]\n')
        output = self.command('--check', '--project', str(project))
        reports = [json.loads(line) for line in output.splitlines() if line.startswith('{')]
        project_report = next(r for r in reports if r['path'] == ['provider_selection', 'disabled_candidates'] and r['scope'] != 'user')
        self.assertEqual(sorted(project_report['effective_after_removal']), ['framework-x', 'user-y'])

    def test_only_masking_values_are_reported_with_higher_scope(self):
        result = review.DefaultsReviewEngine().compare({'new': 1, 'same': 2, 'routing': {'provider': 'new'}},
            {'same': 2, 'machine': 'keep', 'routing': {'provider': 'old'}}, higher={'routing': {'provider': 'project'}})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['effective_after_removal'], 'project')
        self.assertEqual(result[0]['incoming'], 'new')

    def test_arrays_replace_and_partial_candidate_reset_is_refused(self):
        self.assertEqual(review.merge({'items': [1, 2]}, {'items': [3]}), {'items': [3]})
        source = b'[[provider_candidates]]\ncandidate_id="one"\nenabled=false\n[[provider_candidates]]\ncandidate_id="two"\n'
        with self.assertRaisesRegex(ValueError, 'partial candidate'):
            review.remove_candidate(source, 'one')
        self.assertEqual(review.edit_toml(source, [('provider_candidates',)]), b'')

    def test_unique_candidate_removal_and_duplicate_rejection(self):
        source = b'# keep\n[[provider_candidates]]\ncandidate_id="one"\nenabled=false # preserve\n'
        self.assertEqual(review.remove_candidate(source, 'one'), b'# keep\n# preserve\n')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            review.edit_toml(source + b'[[provider_candidates]]\ncandidate_id="one"\n', [('provider_candidates',)])

    def test_exact_unrelated_bytes_and_comments_preserved(self):
        source = b'# top\r\n[routing]\r\nprovider = "old#string" # explain\r\nother = 9\r\n\r\n[machine]\r\nendpoint="local"\r\n'
        self.assertEqual(review.edit_toml(source, [('routing', 'provider')]),
            source.replace(b'provider = "old#string" # explain', b'# explain'))

    def test_unsupported_multiline_and_quoted_keys_fail_without_writes(self):
        for source in [b'[routing]\nprovider=[\n"one",\n"two"\n]\n', b'[routing]\n"provider"="old"\n']:
            with self.assertRaises(ValueError):
                review.edit_toml(source, [('routing', 'provider')])

    def test_check_never_prompts_or_writes(self):
        before = self.overlay.read_bytes()
        with patch('sys.stdin.isatty', return_value=True), patch('builtins.input', side_effect=AssertionError('stdin read')):
            self.assertIn('"incoming": "new"', self.command('--check'))
        self.assertEqual(self.overlay.read_bytes(), before)

    def test_default_run_adopts_automatically_without_prompting(self):
        # No interactive Keep/Adopt question by default, tty or not: the
        # incoming default is adopted whether or not a human is present to
        # answer a prompt that no longer exists.
        with patch('sys.stdin.isatty', return_value=True), patch('builtins.input', side_effect=AssertionError('stdin read')):
            output = self.command()
        self.assertNotIn('provider=', self.overlay.read_text())
        self.assertIn('Applied; recovery receipt', output)
        with patch('sys.stdin.isatty', return_value=False), patch('builtins.input', side_effect=AssertionError('stdin read')):
            self.overlay.write_text('[routing]\nprovider="old"\n')
            self.command()
        self.assertNotIn('provider=', self.overlay.read_text())

    def test_explicit_scope_and_adoption_inherits_next_release(self):
        project = self.root / 'project'
        (project / '.flow').mkdir(parents=True)
        (project / '.flow/flow.toml').write_text('[routing]\nprovider="project"\n')
        output = self.command('--project', str(project), '--project', str(self.root / 'missing'))
        self.assertIn('"selected_projects_after_removal"', output)
        self.assertIn('project', output)
        self.assertIn('Skipped', output)
        self.assertNotIn('provider=', self.overlay.read_text())
        self.assertNotIn('provider=', (project / '.flow/flow.toml').read_text())
        inherited = review.merge({'routing': {'provider': 'next'}}, review.read_toml(self.overlay))
        self.assertEqual(inherited['routing']['provider'], 'next')

    def test_masking_provider_order_equal_to_incoming_is_still_adopted(self):
        # Studio's explicit provider_order can exactly match the framework's
        # own order and still mask role-specific hosted preferences by its
        # mere presence (see openhands_policy.py's explicit_order handling).
        # A plain value comparison would never flag this; MASKING_PATHS must.
        result = review.DefaultsReviewEngine().compare(
            {'provider_selection': {'provider_order': ['ollama', 'claude', 'codex']}},
            {'provider_selection': {'provider_order': ['ollama', 'claude', 'codex']}})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['path'], ['provider_selection', 'provider_order'])
        self.assertEqual(result[0]['local'], result[0]['incoming'])
        self.incoming.write_text('[provider_selection]\nprovider_order=["ollama","claude","codex"]\n[routing]\nprovider="new"\n')
        self.overlay.write_text('[provider_selection]\nprovider_order=["ollama","claude","codex"]\n')
        self.command()
        self.assertNotIn('provider_order', self.overlay.read_text())

    def test_native_permission_override_is_adopted_by_default(self):
        runtime = self.user / 'runtime.toml'
        runtime.write_text('[profiles.codex]\nkind="codex"\npermission_requests="interactive"\n')
        self.command()
        self.assertEqual(runtime.read_text(), '[profiles.codex]\nkind="codex"\n')

    def test_native_coordinator_pins_are_reviewable_without_resetting_machine(self):
        runtime = self.user / 'runtime.toml'
        runtime.write_text('default_profile="codex"\n[stages.implement]\nprofile="claude"\n[profiles.local]\nkind="local"\nmodel="ollama_chat/installed"\nbase_url="http://localhost:11434"\nmax_input_tokens=32768\n')
        before = runtime.read_bytes()
        self.command()
        self.assertEqual(runtime.read_bytes(), before.replace(b'default_profile="codex"\n', b'').replace(b'profile="claude"\n', b''))

    def test_local_routing_pins_are_also_reviewable_not_just_native(self):
        # A default_profile/stage pin is a behavior override regardless of
        # which provider it names — the built-in default needs no pin at
        # all — so a local/ollama routing pin must be just as reviewable as
        # a native one, while the local profile's own connection fields
        # (model, base_url, context) stay preserved as machine data.
        runtime = self.user / 'runtime.toml'
        runtime.write_text('default_profile="ollama"\n[stages.plan]\nprofile="ollama"\n'
            '[profiles.ollama]\nkind="local"\nmodel="ollama_chat/installed"\nbase_url="http://localhost:11434"\nmax_input_tokens=32768\n')
        before = runtime.read_bytes()
        self.command()
        after = before.replace(b'default_profile="ollama"\n', b'').replace(b'profile="ollama"\n', b'', 1)
        self.assertEqual(runtime.read_bytes(), after)
        self.assertIn(b'model="ollama_chat/installed"', runtime.read_bytes())
        self.assertIn(b'base_url="http://localhost:11434"', runtime.read_bytes())

    def changes(self):
        second = self.root / 'second.toml'
        second.write_bytes(b'value=1\n')
        return [(self.overlay, self.overlay.read_bytes(), b'[routing]\n'), (second, second.read_bytes(), b'value=2\n')]

    def test_apply_backups_hashes_and_recover_are_idempotent(self):
        changes = self.changes()
        receipt = review.apply_changes(changes, self.root / 'backup')
        self.assertEqual(json.loads(receipt.read_text())['state'], 'applied')
        review.recover(receipt)
        review.recover(receipt)
        for path, original, _ in changes:
            self.assertEqual(path.read_bytes(), original)

    def test_backup_and_validation_fail_before_mutation(self):
        changes = self.changes()
        for context in [patch.object(Path, 'write_bytes', side_effect=OSError('backup'))]:
            with context, self.assertRaises(OSError):
                review.apply_changes(changes, self.root / 'backup')
        with self.assertRaises(ValueError):
            review.apply_changes(changes, self.root / 'validation', validate=lambda _: (_ for _ in ()).throw(ValueError('invalid')))
        for path, original, _ in changes:
            self.assertEqual(path.read_bytes(), original)

    def test_second_write_failure_restores_first(self):
        changes = self.changes()
        actual = review.atomic_write
        def fail_second(path, data):
            if path == changes[1][0]:
                raise OSError('second write')
            actual(path, data)
        with patch.object(review, 'atomic_write', side_effect=fail_second), self.assertRaises(OSError):
            review.apply_changes(changes, self.root / 'backup')
        for path, original, _ in changes:
            self.assertEqual(path.read_bytes(), original)

    def test_concurrent_edit_and_partial_recovery_preserve_new_content(self):
        changes = self.changes()
        receipt = review.apply_changes(changes, self.root / 'backup')
        changes[0][0].write_bytes(b'newer=true\n')
        with self.assertRaisesRegex(ValueError, 'partial recovery'):
            review.recover(receipt)
        self.assertEqual(changes[0][0].read_bytes(), b'newer=true\n')
        self.assertEqual(changes[1][0].read_bytes(), changes[1][1])
        with self.assertRaisesRegex(ValueError, 'source changed'):
            review.apply_changes(changes, self.root / 'retry')

    def test_drift_after_backup_is_rechecked(self):
        changes = self.changes()
        actual = review.atomic_write
        def concurrent(path, data):
            actual(path, data)
            changes[1][0].write_bytes(b'newer=true\n')
        with patch.object(review, 'atomic_write', side_effect=concurrent), self.assertRaisesRegex(ValueError, 'partial recovery'):
            review.apply_changes(changes, self.root / 'backup')
        self.assertEqual(changes[1][0].read_bytes(), b'newer=true\n')

    def test_restoration_failure_is_recorded(self):
        changes = self.changes()
        receipt = review.apply_changes(changes, self.root / 'backup')
        with patch.object(review, 'atomic_write', side_effect=OSError('restore')), self.assertRaisesRegex(ValueError, 'partial recovery'):
            review.recover(receipt)
        self.assertEqual(len(json.loads(receipt.read_text())['recovery_errors']), 2)

    def test_activated_review_runs_before_sync_and_failure_stops_sync(self):
        import lifecycle
        from types import SimpleNamespace
        with patch.object(lifecycle, 'SOURCE_DIR', self.root), patch.object(lifecycle, 'FLOW_CONFIG', self.root / 'config.toml'), \
                patch.object(lifecycle.subprocess, 'run', return_value=SimpleNamespace(returncode=1)) as run:
            self.assertEqual(lifecycle._sync_installed_adapters(), 1)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][1], str(self.root / 'cli/defaults_review.py'))

    def test_quiet_sync_never_degrades_to_a_check_preview(self):
        # The noninteractive post-upgrade bridge call (`quiet=True`) must
        # still perform a real reset. An earlier version appended `--check`
        # whenever quiet, which made that bridge report-only instead of
        # actually resetting anything.
        import lifecycle
        with patch.object(lifecycle, 'SOURCE_DIR', self.root), patch.object(lifecycle, 'FLOW_CONFIG', self.root / 'config.toml'), \
                patch.object(lifecycle.subprocess, 'run',
                             return_value=SimpleNamespace(returncode=0, stdout='', stderr='')) as run:
            self.assertEqual(lifecycle._sync_installed_adapters(quiet=True), 0)
        review_argv = run.call_args_list[0].args[0]
        self.assertNotIn('--check', review_argv)

    def test_develop_resync_enters_review_sync_boundary(self):
        import lifecycle
        with self.isolated_cwd(), \
                patch.object(lifecycle, 'read_install_config', return_value={'mode': 'develop'}), \
                patch.object(lifecycle, '_sync_installed_adapters', return_value=0) as sync:
            self.assertEqual(lifecycle.update_command(False, True, None), 0)
        sync.assert_called_once_with(projects=())

    def test_update_project_flag_is_additive_to_an_isolated_cwd(self):
        # `--project` only ever adds scopes; it does not replace the
        # automatic current-project inclusion. With no `.flow` at this
        # isolated cwd, the explicit `--project` is the only scope reviewed.
        import lifecycle
        with self.isolated_cwd(), \
                patch.object(lifecycle, 'read_install_config', return_value={'mode': 'develop'}), \
                patch.object(lifecycle, '_sync_installed_adapters', return_value=0) as sync:
            self.assertEqual(lifecycle.update_command(False, True, None, projects=(Path('/tmp/example'),)), 0)
        sync.assert_called_once_with(projects=(Path('/tmp/example'),))
        with patch.object(lifecycle, 'FLOW_CONFIG', self.root / 'config.toml'), \
                patch.object(lifecycle, 'SOURCE_DIR', self.root), \
                patch.object(lifecycle.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
            lifecycle._sync_installed_adapters(projects=(Path('/tmp/example'),))
        self.assertEqual(run.call_args_list[0].args[0][2:], ['--project', '/tmp/example'])

    def test_current_project_scope_excludes_flow_home_itself(self):
        # A `$HOME` managed as a dotfiles git repo makes `repo_root()` match
        # on `.git` at the very first directory it checks — landing exactly
        # on flow's own home, not a project. `.flow` existing there must not
        # be mistaken for a project overlay to review.
        import lifecycle
        home = self.root / 'home'
        home.mkdir()
        (home / '.flow').mkdir()
        (home / '.git').mkdir()
        previous = os.getcwd()
        os.chdir(home)
        try:
            with patch('pathlib.Path.home', return_value=home), \
                    patch.object(lifecycle, 'FLOW_HOME', home / '.flow'):
                self.assertEqual(lifecycle._with_current_project_scope(()), ())
        finally:
            os.chdir(previous)

    def test_update_command_includes_current_project_when_cwd_has_flow(self):
        # The counterpart to the isolated-cwd tests above: standing inside a
        # project with its own `.flow` must fold that project into the
        # review automatically, with no `--project` flag at all.
        import lifecycle
        project = self.root / 'project'
        (project / '.flow').mkdir(parents=True)
        previous = os.getcwd()
        os.chdir(project)
        try:
            with patch.object(lifecycle, 'read_install_config', return_value={'mode': 'develop'}), \
                    patch.object(lifecycle, '_sync_installed_adapters', return_value=0) as sync:
                self.assertEqual(lifecycle.update_command(False, True, None), 0)
        finally:
            os.chdir(previous)
        sync.assert_called_once_with(projects=(project.resolve(),))

    def test_auto_project_flag_reviews_the_cwd_project(self):
        # `install-flow.sh` has no Python-side caller to fold the current
        # project in for it the way `flow install`/`flow update` do via
        # `lifecycle._with_current_project_scope`. `--auto-project` applies
        # the identical rule (`fsutil.current_project_root`) directly from
        # this process's own cwd, so the shell installer can pass one flag
        # instead of reimplementing the walk-up/exclusion logic in bash.
        project = self.root / 'project'
        (project / '.flow').mkdir(parents=True)
        (project / '.flow/flow.toml').write_text('[routing]\nprovider="project"\n')
        previous = os.getcwd()
        os.chdir(project)
        try:
            output = self.command('--check', '--auto-project')
        finally:
            os.chdir(previous)
        reports = [json.loads(line) for line in output.splitlines() if line.startswith('{')]
        self.assertTrue(any(r['scope'] == str(project.resolve()) for r in reports))

    def test_auto_project_flag_is_additive_with_explicit_project(self):
        # Mirrors `--project`'s additive contract for `flow update`
        # (`test_update_project_flag_is_additive_to_an_isolated_cwd`):
        # `--auto-project` only ever adds the cwd's project on top of
        # whatever `--project` already named, never in place of it.
        project = self.root / 'project'
        (project / '.flow').mkdir(parents=True)
        (project / '.flow/flow.toml').write_text('[routing]\nprovider="project"\n')
        extra = self.root / 'extra'
        (extra / '.flow').mkdir(parents=True)
        (extra / '.flow/flow.toml').write_text('[routing]\nprovider="extra"\n')
        previous = os.getcwd()
        os.chdir(project)
        try:
            output = self.command('--check', '--auto-project', '--project', str(extra))
        finally:
            os.chdir(previous)
        reports = [json.loads(line) for line in output.splitlines() if line.startswith('{')]
        self.assertEqual({r['scope'] for r in reports}, {'user', str(project.resolve()), str(extra.resolve())})

    def test_auto_project_flag_does_not_duplicate_an_explicit_match(self):
        project = self.root / 'project'
        (project / '.flow').mkdir(parents=True)
        (project / '.flow/flow.toml').write_text('[routing]\nprovider="project"\n')
        previous = os.getcwd()
        os.chdir(project)
        try:
            output = self.command('--check', '--auto-project', '--project', str(project))
        finally:
            os.chdir(previous)
        reports = [json.loads(line) for line in output.splitlines() if line.startswith('{')]
        self.assertEqual(len([r for r in reports if r['scope'] == str(project.resolve())]), 1)

    def test_without_auto_project_flag_direct_run_does_no_cwd_detection(self):
        # The documented contract this flag is additive to: `flow
        # defaults-review` run directly still does no cwd detection by
        # default — only `--project` scopes, and now `--auto-project`,
        # ever add anything beyond the user overlay.
        project = self.root / 'project'
        (project / '.flow').mkdir(parents=True)
        (project / '.flow/flow.toml').write_text('[routing]\nprovider="project"\n')
        previous = os.getcwd()
        os.chdir(project)
        try:
            output = self.command('--check')
        finally:
            os.chdir(previous)
        reports = [json.loads(line) for line in output.splitlines() if line.startswith('{')]
        self.assertTrue(reports)
        self.assertTrue(all(r['scope'] == 'user' for r in reports))

    def test_auto_project_flag_excludes_flow_home_itself(self):
        # The same dotfiles-repo edge case as
        # `test_current_project_scope_excludes_flow_home_itself`, exercised
        # through the CLI flag instead of the lifecycle helper, since both
        # now share `fsutil.current_project_root`.
        home = self.root / 'home'
        home.mkdir()
        (home / '.flow').mkdir()
        (home / '.git').mkdir()
        previous = os.getcwd()
        os.chdir(home)
        try:
            with patch('pathlib.Path.home', return_value=home):
                output = self.command('--check', '--auto-project')
        finally:
            os.chdir(previous)
        reports = [json.loads(line) for line in output.splitlines() if line.startswith('{')]
        self.assertTrue(reports)
        self.assertTrue(all(r['scope'] == 'user' for r in reports))

    def test_cli_check_uses_explicit_incoming_without_home_writes(self):
        import os
        import subprocess
        home = self.root / 'home'
        home.mkdir()
        result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'cli/flow.py'),
            'defaults-review', '--incoming', str(self.incoming), '--user-overlay', str(self.user), '--check'],
            capture_output=True, text=True, env={**os.environ, 'HOME': str(home)}, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"incoming": "new"', result.stdout)
        self.assertEqual(list(home.iterdir()), [])

    def test_project_pin_equal_to_user_pin_is_still_reviewed(self):
        project = self.root / 'project'
        (project / '.flow').mkdir(parents=True)
        (project / '.flow/flow.toml').write_text('[routing]\nprovider="old"\n')
        output = self.command('--check', '--project', str(project))
        reports = [json.loads(line) for line in output.splitlines() if line.startswith('{')]
        self.assertEqual(len(reports), 2)
        self.assertEqual(reports[1]['incoming'], 'new')
        self.assertEqual(reports[1]['effective_after_removal'], 'old')

    def test_invalid_effective_policy_rejects_before_backup(self):
        self.overlay.write_text('[provider_selection]\nprovider_order=["codex"]\n[routing]\nprovider="old"\n')
        before = self.overlay.read_bytes()
        with self.assertRaises(ValueError):
            self.command()
        self.assertEqual(self.overlay.read_bytes(), before)
        self.assertFalse((self.user / 'defaults-review').exists())

    def test_malformed_existing_overlay_reports_incomplete_not_success(self):
        # A genuinely unreadable/unparseable existing file is a real reset
        # failure, not the routine "no override file here" case — it must
        # not be reported with the same bare "Skipped" line that an absent,
        # perfectly normal optional file gets, and the run must not claim a
        # successful complete reset by returning 0.
        self.overlay.write_text('[routing]\nprovider="unterminated\n')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = review.main(['--incoming', str(self.incoming), '--user-overlay', str(self.user)])
        self.assertEqual(code, 1)
        self.assertIn('Skipped', output.getvalue())
        self.assertIn('incomplete', output.getvalue().lower())

    def test_missing_optional_runtime_toml_is_not_incomplete(self):
        # runtime.toml is optional and absent for most users/projects; its
        # absence must not make an otherwise-successful run report failure.
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = review.main(['--incoming', str(self.incoming), '--user-overlay', str(self.user)])
        self.assertEqual(code, 0)
        self.assertIn('Skipped', output.getvalue())
        self.assertNotIn('incomplete', output.getvalue().lower())


if __name__ == '__main__':
    unittest.main()
