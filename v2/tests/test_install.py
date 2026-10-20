"""Real launcher/CLI, disposable installation roots, and no provider calls."""
import contextlib
import hashlib
import os
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import yaml
from poc.install import ROOT, install
from poc.glg import storage


class InstallTests(unittest.TestCase):
    def test_activation_preserves_generated_user_overlay_command_and_lists_it(self):
        for runtime, base in (('claude','.claude/skills'),('codex','.agents/skills')):
            path = self.home/base/'session-hygiene/SKILL.md'; path.parent.mkdir(parents=True)
            path.write_text('user overlay session hygiene\n')
            with (self.home/('.'+runtime)/'flow.managed.toml').open('a') as manifest:
                manifest.write('\n[[files]]\npath="'+str(path.relative_to(self.home))+'"\nkind="skill"\nsource="~/.flow/user/commands/session-hygiene.md"\nsync_mode="replace"\nsha256="'+hashlib.sha256(path.read_bytes()).hexdigest()+'"\n')
        before = {path:path.read_bytes() for path in self.home.glob('*/skills/session-hygiene/SKILL.md')}
        self.assertEqual(len(before),2)
        install('install',self.home)
        dry = install('activate',self.home,replace_legacy=True,dry_run=True)
        self.assertEqual(set(dry['legacy_cleanup']['preserved_overlay_commands']), {str(p.resolve()) for p in before})
        install('activate',self.home,replace_legacy=True)
        install('update',self.home)
        for path, raw in before.items(): self.assertEqual(path.read_bytes(),raw)
        install('restore',self.home)
        for path, raw in before.items(): self.assertEqual(path.read_bytes(),raw)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)/'home'; self.home.mkdir()
        binary = Path(self.tmp.name)/'fixture-goose'; binary.write_text('offline fixture, never executed')
        environment = patch.dict(os.environ, {'FLOW_V2_GOOSE_BINARY':str(binary)})
        environment.start(); self.addCleanup(environment.stop)
        self.legacy = self.home/'.local/bin/flow'; self.legacy.parent.mkdir(parents=True)
        self.legacy.write_text('#!/bin/sh\n# legacy Flow launcher\nexec "'+str(self.home)+'/.flow/runtimes/old/bin/python" "$HOME/.flow/source/cli/flow.py" "$@"\n'); self.legacy.chmod(0o755)
        for base in ('.agents/skills', '.claude/skills'):
            p = self.home/base/'flow-boot'; p.mkdir(parents=True)
            (p/'SKILL.md').write_text('legacy boot\n'); (p/'notes.txt').write_text('keep legacy extras\n')
        for runtime, base in (('codex', '.agents/skills'), ('claude', '.claude/skills')):
            directory = self.home/('.'+runtime); directory.mkdir(exist_ok=True)
            (directory/'flow.managed.toml').write_text('[managed]\ngenerator="flow"\n[[files]]\npath="'+base+'/flow-boot/SKILL.md"\nkind="skill"\nsync_mode="replace"\nsha256="'+hashlib.sha256(b'legacy boot\n').hexdigest()+'"\n')

    def test_side_by_side_idempotent_launcher_and_no_legacy_replacement(self):
        first = install('install', self.home)
        manifest = (self.home/'.flow-v2/install.json').read_bytes()
        self.assertTrue(first['changed']); self.assertEqual(first['selection'], 'side-by-side')
        self.assertEqual(install('update', self.home)['changed'], [])
        self.assertEqual(manifest, (self.home/'.flow-v2/install.json').read_bytes())
        self.assertIn('legacy', self.legacy.read_text())
        for base in ('.agents/skills', '.claude/skills'):
            self.assertEqual((self.home/base/'flow-boot/SKILL.md').read_text(), 'legacy boot\n')
            self.assertTrue((self.home/base/'flow-v2/SKILL.md').exists())
        result = subprocess.run([str(self.home/'.local/bin/flow-v2'), '--version'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0); self.assertIn('Flow 2.0.0', result.stdout)

    def test_explicit_cutover_restore_and_skill_directory_symlink(self):
        install('install', self.home)
        with self.assertRaisesRegex(ValueError, 'replace-legacy'): install('activate', self.home)
        target = self.home/'.agents/skills/flow-boot'
        original = self.home/'custom-boot'; target.rename(original); target.symlink_to(original, target_is_directory=True)
        dry = install('activate', self.home, replace_legacy=True, dry_run=True)
        self.assertEqual(dry['selection'], 'active'); self.assertTrue(target.is_symlink())
        activated = install('activate', self.home, replace_legacy=True)
        self.assertFalse(target.is_symlink()); self.assertEqual((original/'SKILL.md').read_text(), 'legacy boot\n')
        self.assertIn('Flow v2.0', (target/'SKILL.md').read_text())
        self.assertEqual(install('update', self.home)['changed'], [])
        (target/'SKILL.md').write_text('a user edit after selection')
        restored = install('restore', self.home)
        self.assertEqual(restored['selection'], 'side-by-side'); self.assertTrue(target.is_symlink())
        self.assertIn('legacy', self.legacy.read_text())
        self.assertFalse((self.home/'.agents/skills/flow-close').exists())
        self.assertTrue((self.home/'.local/bin/flow-v2').exists())
        self.assertEqual(install('restore', self.home)['changed'], [])

    def test_locally_modified_opt_in_surface_is_not_overwritten(self):
        install('install', self.home)
        path = self.home/'.agents/skills/flow-v2/SKILL.md'; path.write_text('user content')
        with self.assertRaisesRegex(ValueError, 'locally modified'): install('update', self.home)
        self.assertEqual(path.read_text(), 'user content')

    def test_dry_run_does_not_create_installation(self):
        result = install('install', self.home, dry_run=True)
        self.assertTrue(result['changed']); self.assertFalse((self.home/'.flow-v2').exists())
        self.assertFalse((self.home/'.local/bin/flow-v2').exists())

    def test_supported_skill_mapping_and_no_obsolete_coordinator_commands(self):
        install('install', self.home)
        names = {p.parent.name for p in (self.home/'.flow-v2/skills').glob('*/SKILL.md')}
        self.assertEqual(names, {'flow-'+x for x in ['boot','define','solution','plan','implement','review','status','resume','close','archive','accept','scout','init-project','help']})
        for p in (self.home/'.flow-v2/skills').glob('*/SKILL.md'):
            text = p.read_text(); metadata = yaml.safe_load(text.split('---', 2)[1])
            self.assertEqual(metadata['name'], p.parent.name)
            self.assertNotIn('FLOW_V2', text); self.assertNotIn('flow workflow execute', text)
            self.assertNotIn('validate-orchestration', text)
        self.assertIn('approve --actor', (self.home/'.flow-v2/skills/flow-implement/SKILL.md').read_text())
        self.assertIn('automatically', (self.home/'.flow-v2/skills/flow-review/SKILL.md').read_text())
        self.assertIn('already graph-generated', (self.home/'.flow-v2/skills/flow-archive/SKILL.md').read_text())

    def test_normal_use_smoke_context_shape_reopen_stops_before_approval(self):
        install('install', self.home)
        project = self.home/'project'; project.mkdir(); (project/'AGENTS.md').write_text('Synthetic local smoke. No network or execution.')
        binary = str(self.home/'.local/bin/flow-v2'); prefix = [binary, '--project', str(project)]
        def run(*args):
            r = subprocess.run([*prefix, *args], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr); return json.loads(r.stdout)
        orientation = run('context'); self.assertEqual(orientation['work'], []); self.assertFalse((project/'.glg').exists())
        state_root = storage(project, 'smoke').parent
        self.addCleanup(lambda: shutil.rmtree(state_root, ignore_errors=True))
        run('--work', 'smoke', 'create', '--request', 'Shape a local docs change')
        run('--work', 'smoke', 'assign', '--stage', 'define', '--question', 'Inspect existing docs')
        note = self.home/'findings.md'; note.write_text('Host-authored source inspection, no delegation claimed.')
        run('--work', 'smoke', 'stage', '--stage', 'define', '--file', str(note))
        brief = self.home/'brief.json'; brief.write_text(json.dumps({'goal':'docs', 'scope':['README'], 'acceptance_criteria':['clear usage'], 'check_command':['python3','-m','unittest']}))
        run('--work', 'smoke', 'brief', '--file', str(brief))
        saved = run('--work', 'smoke', 'resume'); self.assertTrue(saved['pending'])
        self.assertNotIn('approval_ref', saved['references'])
        self.assertEqual(run('context')['work'][0]['work_id'], 'smoke')
        self.assertFalse(list((project/'.glg/work/smoke/results').glob('*.json')))

    def legacy_configuration(self):
        from poc.legacy_install import BEGIN, END
        hook = self.home/'.claude/hooks/flow-session.py'; hook.parent.mkdir(); hook.write_text('# legacy hook\n')
        settings = self.home/'.claude/settings.json'
        doc = {'theme':'keep-user', 'permissions': {'allow':['Bash(git status)']}, 'hooks': {'SessionStart':[{'hooks':[{'type':'command','command':'python3 '+str(hook)}, {'type':'command','command':'echo keep-user'}]}]}}
        settings.write_text(json.dumps(doc))
        with (self.home/'.claude/flow.managed.toml').open('a') as stream:
            stream.write('\n[[files]]\npath=".claude/hooks/flow-session.py"\nkind="hook"\nsync_mode="replace"\nsha256="'+hashlib.sha256(hook.read_bytes()).hexdigest()+'"\n[[files]]\npath=".claude/settings.json"\nkind="settings"\nsync_mode="merge"\n')
        block = BEGIN+'[agents.legacy_role]\nconfig_file="'+str(self.home/'.flow/generated/agents/codex/legacy.toml')+'"\n'+END
        config = self.home/'.codex/config.toml'; config.write_text('model="keep-user"\n'+block)
        with (self.home/'.codex/flow.managed.toml').open('a') as stream:
            stream.write('\n[[files]]\npath=".codex/config.toml"\nkind="agent-registration-config"\nsync_mode="merge"\nblock_sha256="'+hashlib.sha256(block.encode()).hexdigest()+'"\n')
        return hook, settings, config

    def test_upgrade_cleans_only_owned_hooks_and_registration_and_rolls_back(self):
        hook, settings, config = self.legacy_configuration()
        original = {p:p.read_bytes() for p in (hook, settings, config)}
        credentials = self.home/'.aws/credentials'; credentials.parent.mkdir(); credentials.write_text('fixture credential sentinel')
        project = self.home/'project/.flow/runs/history.md'; project.parent.mkdir(parents=True); project.write_text('retain work')
        install('install', self.home)
        result = install('activate', self.home, replace_legacy=True)
        self.assertFalse(hook.exists()); self.assertFalse((self.home/'.claude/flow.managed.toml').exists())
        updated = json.loads(settings.read_text()); self.assertEqual(updated['theme'], 'keep-user')
        self.assertEqual(updated['permissions'], {'allow':['Bash(git status)']})
        self.assertEqual(updated['hooks']['SessionStart'][0]['hooks'], [{'type':'command','command':'echo keep-user'}])
        self.assertEqual(config.read_text(), 'model="keep-user"\n')
        self.assertEqual(install('update', self.home)['changed'], [])
        install('restore', self.home)
        for path, data in original.items(): self.assertEqual(path.read_bytes(), data)
        self.assertEqual(credentials.read_text(), 'fixture credential sentinel'); self.assertEqual(project.read_text(), 'retain work')

    def test_modified_legacy_skill_blocks_cleanup_and_shared_post_edits_block_rollback(self):
        self.legacy_configuration(); install('install', self.home)
        skill = self.home/'.agents/skills/flow-boot/SKILL.md'; skill.write_text('user override')
        with self.assertRaisesRegex(ValueError, 'Ambiguous'): install('activate', self.home, replace_legacy=True)
        self.assertIn('legacy', self.legacy.read_text()); self.assertEqual(skill.read_text(), 'user override')
        skill.write_text('legacy boot\n'); install('activate', self.home, replace_legacy=True)
        config = self.home/'.codex/config.toml'; config.write_text('model="new-user-choice"\n')
        with self.assertRaisesRegex(ValueError, 'Shared configuration changed'): install('restore', self.home)
        self.assertEqual(config.read_text(), 'model="new-user-choice"\n')

    def test_activation_write_failure_restores_original_legacy_surfaces(self):
        from poc.artifacts import atomic_write
        hook, settings, config = self.legacy_configuration(); install('install', self.home)
        before = {p:p.read_bytes() for p in (self.legacy, hook, settings, config)}
        def fail_on_switch(path, data):
            if path.resolve() == self.legacy.resolve(): raise OSError('fixture write failure')
            return atomic_write(path, data)
        with patch('poc.install.atomic_write', side_effect=fail_on_switch), self.assertRaises(OSError):
            install('activate', self.home, replace_legacy=True)
        for path, data in before.items(): self.assertEqual(path.read_bytes(), data)

    def test_ambiguous_agent_link_keeps_its_owned_generated_target(self):
        from poc.legacy_install import inventory
        generated = self.home/'.flow/generated/agents/claude/custom.md'; generated.parent.mkdir(parents=True)
        generated.write_text('Retain linked expertise')
        alias = self.home/'.claude/agents/custom.md'; alias.parent.mkdir(); alias.symlink_to(generated)
        with (self.home/'.claude/flow.managed.toml').open('a') as stream:
            stream.write('\n[[files]]\npath=".flow/generated/agents/claude/custom.md"\nkind="agent-definition"\nsync_mode="replace"\nsha256="'+hashlib.sha256(generated.read_bytes()).hexdigest()+'"\n[[files]]\npath=".claude/agents/custom.md"\nkind="agent"\nsync_mode="replace"\n')
        value=inventory(self.home)
        self.assertNotIn(generated.resolve(), value['remove'])
        self.assertIn(generated.resolve(), value['protected_targets'])
        install('install', self.home);install('activate', self.home, replace_legacy=True)
        self.assertTrue(alias.is_file());self.assertEqual(alias.read_text(), 'Retain linked expertise')
