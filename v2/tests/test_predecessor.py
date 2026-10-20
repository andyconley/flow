"""Predecessor links are validated history and never carry execution approval."""
import contextlib
import fcntl
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from poc import glg
from poc.artifacts import Artifacts, ArtifactError
from poc.predecessor import validated_predecessor, validate_link_reference
from tests.test_glg_lifecycle import BRIEF, Harness


class PredecessorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root/'project'
        self.project.mkdir()
        self.prior = Artifacts(self.project, 'prior')
        self.closure = self.prior.publish('closures', 'closure', {'outcome': 'blocked'})
        self.state_dir = self.root/'state'
        self.state_dir.mkdir()
        (self.state_dir/'operator.lock').touch()
        (self.state_dir/'workflow.sqlite').touch()
        self.snapshot = NS(values={'work_id': 'prior', 'lifecycle_phase': 'closed', 'closure_ref': self.closure},
                           next=(), tasks=())

    def link(self, **overrides):
        values = dict(project=self.project, new_work='next', work='prior', revision=self.closure['revision'],
                      state_dir=self.state_dir, read_snapshot=lambda: self.snapshot)
        return validated_predecessor(**{**values, **overrides})

    def test_validated_historical_link_preserves_predecessor_bytes(self):
        before = (self.project/self.closure['path']).read_bytes()
        with self.link() as link:
            self.assertEqual(link['closure_ref'], self.closure)
            self.assertFalse(link['approval_imported'])
            self.assertNotIn('approval_ref', link)
            self.assertEqual(validate_link_reference(self.project, link)['kind'], 'closures')
        self.assertEqual((self.project/self.closure['path']).read_bytes(), before)

    def test_active_wrong_stale_tampered_and_pending_predecessors_are_rejected(self):
        with (self.state_dir/'operator.lock').open('r') as active:
            fcntl.flock(active, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(ArtifactError, 'active operator'), self.link():
                pass
        with self.assertRaisesRegex(ArtifactError, 'distinct'), self.link(new_work='prior'):
            pass
        with self.assertRaisesRegex(ArtifactError, 'exact current closure'), self.link(revision='wrong'):
            pass
        self.snapshot.next = ('delivery',)
        with self.assertRaisesRegex(ArtifactError, 'quiescent'), self.link():
            pass
        self.snapshot.next = ()
        self.prior.publish('closures', 'closure', {'outcome': 'ready'}, supersedes=self.closure)
        with self.assertRaisesRegex(ArtifactError, 'disagree'), self.link():
            pass
        (self.project/self.closure['path']).write_text('{}')
        with self.assertRaisesRegex(ArtifactError, 'modified'), self.link():
            pass

    def test_missing_predecessor_never_creates_its_state(self):
        absent = self.root/'absent'
        with self.assertRaisesRegex(ArtifactError, 'existing native checkpoint'), self.link(state_dir=absent):
            pass
        self.assertFalse(absent.exists())

    def test_cli_links_dedicated_context_without_importing_approval(self):
        brief_file = self.root/'brief.json'
        brief_file.write_text(json.dumps(BRIEF))
        harness = Harness()
        def invoke(work, *arguments):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                glg.main(['--project', str(self.project), '--work', work, *arguments])
            return json.loads(output.getvalue())
        with patch.object(glg, 'ROOT', self.root), patch.object(glg, 'NativeHarness', return_value=harness):
            shaped = invoke('closed', 'create', '--brief-file', str(brief_file))
            closed = invoke('closed', 'approve', '--actor', 'fixture', '--revision', shaped['references']['brief_ref']['revision'])
            prior_ref = closed['references']['closure_ref']
            successor = invoke('successor', 'create', '--request', 'New separately approved scope',
                               '--predecessor-work', 'closed', '--predecessor-revision', prior_ref['revision'])
            self.assertNotIn('approval_ref', successor['references'])
            context = Artifacts(self.project, 'successor').read(successor['references']['context_ref'])
            self.assertIsNone(context['supersedes'])
            self.assertEqual(context['payload']['predecessor_work']['closure_ref'], prior_ref)
            self.assertFalse(context['payload']['predecessor_work']['approval_imported'])
            self.assertEqual(harness.calls, 1)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                invoke('bad', 'create', '--request', 'new', '--predecessor-work', 'closed')


if __name__ == '__main__':
    unittest.main()
