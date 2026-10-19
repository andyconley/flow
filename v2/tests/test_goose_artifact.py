"""Artifact integrity and strict source validation; no Rust, accounts or inference."""
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from poc import goose_artifact as artifact
from poc.runtime_env import goose_binary

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('flow_bootstrap', ROOT/'bootstrap.py')
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        vendor = self.root/'vendor'; (vendor/'artifacts').mkdir(parents=True)
        (vendor/'fixture.patch').write_bytes(b'fixture patch')
        lock = {'patch':'fixture.patch', 'patch_sha256':artifact.digest(vendor/'fixture.patch')}
        (vendor/'goose.lock.json').write_text(json.dumps(lock))
        binary = b'#!/bin/sh\necho fixture\n'
        archive = vendor/'artifacts/goose-macos-arm64.gz'
        archive.write_bytes(gzip.compress(binary, mtime=0))
        self.meta = {'platform':'Darwin', 'architecture':'arm64', 'minimum_macos':'11.0',
                     'source_lock':lock, 'binary_size':len(binary),
                     'binary_sha256':hashlib.sha256(binary).hexdigest(),
                     'archive':archive.name, 'archive_size':archive.stat().st_size,
                     'archive_sha256':artifact.digest(archive)}
        self.manifest = vendor/'artifacts/goose-macos-arm64.json'
        self.manifest.write_text(json.dumps(self.meta))
        self.platform = patch.multiple(artifact.platform, system=lambda:'Darwin', machine=lambda:'arm64', mac_ver=lambda:('14.0', (), ''))
        self.platform.start(); self.addCleanup(self.platform.stop)

    def test_extract_select_idempotence_and_explicit_override(self):
        with patch.dict(os.environ, {}, clear=True):
            target = artifact.extract(self.root)
            self.assertEqual(goose_binary(self.root), target)
            before = target.stat().st_mtime_ns
            self.assertEqual(artifact.extract(self.root), target)
            self.assertEqual(target.stat().st_mtime_ns, before)
            with patch.dict(os.environ, {'FLOW_V2_GOOSE_BINARY':'/explicit/goose'}):
                self.assertEqual(goose_binary(self.root), Path('/explicit/goose'))

    def test_corrupted_archive_is_rejected_before_extract(self):
        (self.root/'vendor/artifacts'/self.meta['archive']).write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError, 'archive checksum'):
            artifact.extract(self.root)
        self.assertFalse(artifact.binary_path(self.root).exists())

    def test_corrupted_executable_is_preserved_and_rejected(self):
        target = artifact.extract(self.root); target.write_bytes(b'user change')
        with self.assertRaisesRegex(ValueError, 'executable checksum'):
            artifact.extract(self.root)
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(ValueError, 'executable checksum'):
            goose_binary(self.root)
        self.assertEqual(target.read_bytes(), b'user change')

    def test_lock_patch_and_uncompressed_digest_are_enforced(self):
        (self.root/'vendor/fixture.patch').write_bytes(b'unrelated')
        with self.assertRaisesRegex(ValueError, 'provenance'):
            artifact.extract(self.root)
        (self.root/'vendor/fixture.patch').write_bytes(b'fixture patch')
        self.meta['binary_sha256'] = '0'*64
        self.manifest.write_text(json.dumps(self.meta))
        with self.assertRaisesRegex(ValueError, 'executable checksum'):
            artifact.extract(self.root)
        self.assertFalse(artifact.binary_path(self.root).exists())
        self.assertFalse(list(artifact.binary_path(self.root).parent.glob('.goose-*')))

    def test_wrong_platform_architecture_and_old_macos_rejected(self):
        for name, value in [('system','Linux'), ('machine','x86_64'), ('mac_ver',('10.15', (), ''))]:
            with self.subTest(name=name), patch.object(artifact.platform, name, return_value=value):
                with self.assertRaises(ValueError): artifact.extract(self.root)
        self.assertFalse(artifact.binary_path(self.root).exists())

    def test_prepare_automatically_extracts_without_cargo_and_reruns(self):
        for name in ('adapters.package.json', 'adapters.package-lock.json'):
            (self.root/name).write_text('{}')
        with patch.dict(os.environ, {}, clear=True), patch.object(bootstrap, 'ROOT', self.root), patch.object(bootstrap, 'run') as run:
            bootstrap.prepare()
            target = artifact.binary_path(self.root)
            before = target.stat().st_mtime_ns
            bootstrap.prepare()
            self.assertEqual(target.stat().st_mtime_ns, before)
            self.assertFalse(any(str(call.args[0][0]) in ('cargo', 'git') for call in run.call_args_list))

    def test_install_and_update_extract_automatically_and_dry_run_is_read_only(self):
        from poc.install import install
        # Supply real distributed skill content and an existing Python environment;
        # the executable is a tiny offline fixture, never used for inference.
        import shutil
        shutil.copytree(ROOT/'skills', self.root/'skills')
        (self.root/'role-bundle').mkdir()
        (self.root/'role-bundle/catalog.json').write_text('{}')
        (self.root/'.venv/bin').mkdir(parents=True)
        (self.root/'.venv/bin/python').symlink_to(os.sys.executable)
        home = self.root/'home'
        with patch.dict(os.environ, {}, clear=True):
            dry = install('install', home, source=self.root, dry_run=True)
            self.assertIn('goose_extraction_planned', dry)
            self.assertFalse((self.root/'runtime').exists())
            self.assertFalse(home.exists())
            install('install', home, source=self.root)
            target = artifact.binary_path(self.root)
            before = target.stat().st_mtime_ns
            self.assertEqual(install('install', home, source=self.root)['changed'], [])
            self.assertEqual(target.stat().st_mtime_ns, before)
            target.unlink()
            install('update', home, source=self.root)
            self.assertTrue(target.is_file())
            target.write_bytes(b'user changed binary')
            with self.assertRaisesRegex(ValueError, 'executable checksum'):
                install('update', home, source=self.root)
            self.assertEqual(target.read_bytes(), b'user changed binary')

    def test_provision_preserves_override_source_build_and_incompatible_host(self):
        with patch.dict(os.environ, {'FLOW_V2_GOOSE_BINARY':'/explicit/goose'}, clear=True):
            self.assertEqual(artifact.provision(self.root), (Path('/explicit/goose'), False))
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(artifact.platform, 'system', return_value='Linux'):
                self.assertEqual(artifact.provision(self.root), ((self.root/'runtime/goose/target/debug/goose').resolve(), False))
                self.assertFalse((self.root/'runtime').exists())
            with patch.object(artifact.platform, 'mac_ver', return_value=('10.15', (), '')):
                with self.assertRaises(ValueError): artifact.provision(self.root)
            (self.root/'vendor/artifacts'/self.meta['archive']).write_bytes(b'bad')
            for dry in (True, False):
                with self.assertRaisesRegex(ValueError, 'archive checksum'):
                    artifact.provision(self.root, dry_run=dry)
            self.assertFalse((self.root/'runtime').exists())

    def test_shipped_artifact_and_lock_identity(self):
        value = artifact.metadata(ROOT)
        archive = ROOT/'vendor/artifacts'/value['archive']
        self.assertLess(archive.stat().st_size, 50*1024*1024)
        self.assertEqual(artifact.digest(archive), value['archive_sha256'])
        digest = hashlib.sha256(); size = 0
        with gzip.open(archive, 'rb') as stream:
            while chunk := stream.read(1024*1024):
                digest.update(chunk); size += len(chunk)
        self.assertEqual(digest.hexdigest(), value['binary_sha256'])
        self.assertEqual(size, value['binary_size'])


class SourceValidationTests(unittest.TestCase):
    def test_old_lock_stamp_is_rejected_without_rewriting_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'vendor').mkdir(); (root/'runtime/goose').mkdir(parents=True)
            for name in ('adapters.package.json', 'adapters.package-lock.json'):
                (root/name).write_text('{}')
            (root/'vendor/fixture.patch').write_bytes(b'patch')
            lock = {'patch':'fixture.patch', 'patch_sha256':artifact.digest(root/'vendor/fixture.patch')}
            (root/'vendor/goose.lock.json').write_text(json.dumps(lock))
            stamp = root/'runtime/goose/.flow-v2-patch.json'
            stamp.write_text(json.dumps(dict(lock, patch_sha256='old-lock-hash')))
            before = stamp.read_bytes()
            with patch.object(bootstrap, 'ROOT', root), patch.object(bootstrap, 'run'), patch.object(bootstrap.subprocess, 'run') as git_status:
                git_status.return_value.stdout = ''
                with self.assertRaisesRegex(SystemExit, 'different lock; preserve'):
                    bootstrap.prepare(True)
            self.assertEqual(stamp.read_bytes(), before)

    def test_full_index_ignores_abbreviation_but_rejects_unrelated_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.check_output(['git', *args], cwd=root)
            git('init', '-q'); git('config', 'user.name', 'Fixture'); git('config', 'user.email', 'fixture@example.invalid')
            (root/'source').write_text('base\n'); git('add', '.'); git('commit', '-qm', 'base')
            base = git('rev-parse', 'HEAD').decode().strip()
            (root/'source').write_text('patched\n'); git('add', 'source')
            diff = git('diff', '--binary', '--full-index', base)
            lock = {'base_commit':base, 'patch_sha256':hashlib.sha256(diff).hexdigest()}
            (root/'.flow-v2-patch.json').write_text(json.dumps(lock))
            for abbrev in ('7', '12', '40'):
                git('config', 'core.abbrev', abbrev)
                bootstrap.verify_goose_source(root, lock)
            (root/'source').write_text('unrelated tracked edit\n')
            with self.assertRaisesRegex(SystemExit, 'differs from the locked'):
                bootstrap.verify_goose_source(root, lock)
            (root/'source').write_text('patched\n')
            (root/'unrelated').write_text('untracked')
            with self.assertRaisesRegex(SystemExit, 'unrelated untracked'):
                bootstrap.verify_goose_source(root, lock)
            self.assertEqual(json.loads((root/'.flow-v2-patch.json').read_text()), lock)
