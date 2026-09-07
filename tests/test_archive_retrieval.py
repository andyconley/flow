"""Archive integration proof against temporary overlays and real SQLite."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

CLI = Path(__file__).resolve().parents[1] / 'cli'
sys.path.insert(0, str(CLI))
import archive_model as model
import archive_store as store
import archive_service as service
import archive_query as query
import archive_preflight as preflight
from archive_sources import assess_source


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'project'
        self.root.mkdir()
        (self.root / '.flow' / 'runs').mkdir(parents=True)
        (self.root / '.flow' / 'PROJECT.md').write_text('# Project')
        with store.writer_lock(self.root):
            store.ensure_ignore(self.root)
            self.sid = store.ensure_identity(self.root)
        self.available = patch.object(preflight, 'current', return_value={'state': 'available'})
        self.available.start()
        self.addCleanup(self.available.stop)

    def run_fixture(self, work='one', text=None, root=None, live=True):
        root = root or self.root
        directory = root / '.flow' / 'runs' / work
        directory.mkdir(parents=True)
        text = text or '# Archive\n\n## Work Closed\nKeep SQLite storage per overlay.\n\n## Rationale\nPreserve local ownership.\n\n## Applies when\nApplies to archived decisions.\n'
        (directory / 'archive.md').write_text(text)
        event = {'event': 'archive', 'at': '2026-09-01T00:00:00Z', 'to': 'archived', 'dispositions': {'archive_enrichment': '1'} if live else {}}
        run = {'schema_version': 1, 'work_id': work, 'state': 'archived', 'gates': {'archive': event['at']}, 'artifacts': {'archive': f'.flow/runs/{work}/archive.md'}}
        (directory / 'run.json').write_text(json.dumps(run))
        (directory / 'events.jsonl').write_text(json.dumps(event) + '\n')
        return directory

    def fill(self, **kwargs):
        result = service.backfill(self.root, apply=True, yes=True, **kwargs)
        self.assertEqual(result['state'], 'complete', result)
        return result

    def indexed(self):
        self.fill()
        result = query.rebuild(self.root)
        self.assertEqual(result['state'], 'complete', result)

    def tree(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_preview_and_refused_apply_write_nothing(self):
        self.run_fixture()
        before = self.tree()
        self.assertEqual(service.backfill(self.root)['state'], 'preview')
        self.assertEqual(service.backfill(self.root, apply=True)['state'], 'invalid_request')
        self.assertEqual(before, self.tree())

    def test_generated_and_complete_noop_are_deterministic(self):
        path = self.run_fixture()
        self.fill()
        original = (path / 'abstract.json').read_bytes()
        self.fill(rescan=True)
        self.fill(rescan=True)
        self.assertEqual(original, (path / 'abstract.json').read_bytes())
        self.assertEqual(len(model.render_lines(json.loads(original))), 7)

    def test_missing_rationale_unknown_not_invented(self):
        path = self.run_fixture(text='## Work Closed\nKeep SQLite.\n')
        self.fill()
        value = json.loads((path / 'abstract.json').read_text())
        self.assertEqual(value['generated']['fields']['rationale']['state'], 'unknown')
        self.assertEqual(value['generated']['fields']['component']['state'], 'unknown')

    def test_no_final_source_is_failure_and_backfill_selects_exact_run(self):
        path = self.run_fixture(text='## Plan\nThis is not a decision.\n')
        result = service.backfill(self.root, apply=True, yes=True)
        self.assertEqual(result['state'], 'partial')
        self.assertFalse((path / 'abstract.json').exists())
        row = service.backfill(self.root)['runs'][0]
        self.assertEqual(row['work_id'], 'one')
        self.assertIn('live_regression', row['conditions'])
        (path / 'archive.md').write_text('## Work Closed\nUse SQLite.\n')
        self.indexed()
        self.assertEqual(query.search(self.root, 'SQLite')['shown'], 1)

    def test_repair_one_does_not_clear_other_cohorts(self):
        self.run_fixture('one')
        self.run_fixture('two')
        self.run_fixture('old', live=False)
        outdated = self.run_fixture('outdated')
        (outdated / 'abstract.json').write_text(json.dumps({'schema_version': 0, 'generated': {'extractor_version': 0}}))
        service.backfill(self.root, apply=True, yes=True, work_ids=['one'])
        value = store.cached_coverage(self.root)
        self.assertEqual(value['counts']['live_regression'], 1)
        self.assertEqual(value['counts']['historical_gap'], 1)
        remaining = {r['work_id']: r['conditions'] for r in value['runs']}
        self.assertIn('live_regression', remaining['two'])
        self.assertIn('historical_gap', remaining['old'])
        self.assertIn('outdated_abstract', remaining['outdated'])
        self.assertEqual(value['counts']['outdated_abstract'], 1)

    def test_search_freshness_and_no_read_repair(self):
        path = self.run_fixture()
        self.indexed()
        self.assertEqual(query.search(self.root, 'SQLite')['shown'], 1)
        (path / 'archive.md').write_text('## Work Closed\nUse something else.\n')
        before = self.tree()
        result = query.search(self.root, 'SQLite')
        self.assertEqual(result['state'], 'unavailable')
        self.assertEqual(before, self.tree())
        self.assertEqual(store.cached_coverage(self.root)['freshness'], 'last_observed')

    def test_query_caps_count_all_metadata(self):
        for i in range(4):
            self.run_fixture(str(i))
        self.indexed()
        result = query.search(self.root, 'SQLite', top_k=2, max_output_bytes=16384)
        raw = query.serialized(result)
        self.assertLessEqual(len(raw.encode()), 16384)
        self.assertEqual(len(raw.encode()), result['actual_output_bytes'])
        self.assertEqual(result['shown'] + result['withheld'], result['total_matches'])
        self.assertEqual(result['shown'], 2)
        small = query.search(self.root, 'SQLite', max_output_bytes=1200)
        self.assertEqual(small['shown'], 0)
        self.assertTrue(small['size_limited'])
        self.assertLessEqual(len(query.serialized(small).encode()), 1200)

    def test_missing_preflight_does_not_probe_or_fallback(self):
        self.run_fixture()
        self.indexed()
        with patch.object(preflight, 'current', return_value={'state': 'preflight_required', 'remedy': 'run flow doctor'}), patch.object(preflight, 'probe', side_effect=AssertionError('must not probe')), patch.object(query, 'rank', side_effect=AssertionError('must not rank')):
            result = query.search(self.root, 'SQLite')
        self.assertEqual(result['state'], 'preflight_required')

    def test_post_preflight_fts_failure_is_unavailable(self):
        self.run_fixture()
        self.indexed()
        import sqlite3
        with patch.object(query, '_stream_ranked', side_effect=sqlite3.OperationalError('no such module: fts5')):
            result = query.search(self.root, 'SQLite')
        self.assertEqual(result['state'], 'unavailable')
        self.assertEqual(result['reason'], 'fts5_failed_after_preflight')

    def test_temporary_storage_failure_has_its_own_remedy(self):
        self.run_fixture()
        self.indexed()
        with patch.object(query, '_stream_ranked', side_effect=OSError('no writable temporary directory')):
            result = query.search(self.root, 'SQLite')
        self.assertEqual(result['state'], 'unavailable')
        self.assertEqual(result['reason'], 'temporary_storage_unavailable')
        self.assertIn('TMPDIR', result['remedy'])
        self.assertNotIn('FTS5', result['remedy'])

    def test_invalid_stored_closure_date_is_not_mislabeled_as_a_race(self):
        path = self.run_fixture()
        run = json.loads((path / 'run.json').read_text())
        event = json.loads((path / 'events.jsonl').read_text())
        run['gates']['archive'] = event['at'] = 'invalid-date'
        (path / 'run.json').write_text(json.dumps(run))
        (path / 'events.jsonl').write_text(json.dumps(event) + '\n')
        self.indexed()
        result = query.search(self.root, 'SQLite', since='2026-01-01')
        self.assertEqual(result['state'], 'unavailable')
        self.assertEqual(result['reason'], 'invalid_closure_date')
        self.assertIn(self.sid + ':one', result['detail'])

    def test_refinement_stale_preserved_and_consent_rejected(self):
        path = self.run_fixture()
        self.fill()
        value = json.loads((path / 'abstract.json').read_text())
        field = copy.deepcopy(value['generated']['fields']['decision'])
        field['value'] = 'Keep SQLite storage per overlay.'
        data = {'schema_version': 1, 'actor': 'test-refiner', 'reason': 'source-preserving edit', 'base_generated_digest': model.digest(value['generated']), 'patches': {'decision': field}}
        base = store.file_digest(path / 'abstract.json')
        service.mutate(self.root, 'one', 'refine', data, base, True, True)
        refined = json.loads((path / 'abstract.json').read_text())['refinement']
        (path / 'archive.md').write_text('## Work Closed\nKeep SQLite projections in each overlay.\n')
        self.fill(rescan=True)
        updated = json.loads((path / 'abstract.json').read_text())
        self.assertEqual(refined, updated['refinement'])
        self.assertEqual(model.effective_view(updated)['refinement_state'], 'stale')
        with self.assertRaisesRegex(ValueError, 'stale consent'):
            service.mutate(self.root, 'one', 'refine', data, base, True, True)

    def test_symlink_destination_rejected(self):
        target = Path(self.tmp.name) / 'outside'
        target.write_text('untouched')
        link = self.root / '.flow' / 'identity.json'
        link.unlink()
        link.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            store.atomic_write(link, b'bad', self.root)
        self.assertEqual(target.read_text(), 'untouched')

    def test_lost_identity_cannot_retarget_envelope(self):
        self.run_fixture()
        self.fill()
        (self.root / '.flow' / 'identity.json').unlink()
        with store.writer_lock(self.root), self.assertRaisesRegex(ValueError, 'restore'):
            store.ensure_identity(self.root)

    def test_ancestor_default_and_source_filter(self):
        parent = self.root
        self.run_fixture(root=parent)
        self.indexed()
        child = parent / 'child'
        (child / '.flow' / 'runs').mkdir(parents=True)
        with store.writer_lock(child):
            store.ensure_ignore(child)
            child_id = store.ensure_identity(child)
        self.run_fixture(root=child)
        service.backfill(child, apply=True, yes=True)
        query.rebuild(child)
        result = query.search(child, 'SQLite')
        self.assertEqual({h['source_id'] for h in result['hits']}, {self.sid, child_id})
        narrowed = query.search(child, 'SQLite', current_only=True)
        self.assertEqual({h['source_id'] for h in narrowed['hits']}, {child_id})

    def test_filtered_superseder_still_suppresses_target(self):
        self.run_fixture('old')
        path = self.run_fixture('new')
        self.fill()
        value = json.loads((path / 'abstract.json').read_text())
        evidence = value['generated']['fields']['decision']['sources']
        value['declarations'] = {'supersedes': [{'target': {'source_id': self.sid, 'work_id': 'old'}, 'whole_run': True, 'rationale': 'replaces whole decision', 'actor': 'engineer', 'evidence': evidence}]}
        (path / 'abstract.json').write_bytes(store.encode(value))
        event = json.loads((path / 'events.jsonl').read_text())
        event['dispositions']['archive_declarations'] = model.declaration_digest(value['identity'], value['declarations'])
        (path / 'events.jsonl').write_text(json.dumps(event) + '\n')
        self.assertEqual(query.rebuild(self.root)['state'], 'complete')
        result = query.search(self.root, 'SQLite')
        self.assertEqual([h['work_id'] for h in result['hits']], ['new'])
        history = query.search(self.root, 'SQLite', include_superseded=True)
        self.assertEqual({h['work_id'] for h in history['hits']}, {'old', 'new'})

    def test_fixed_tokenizer_compounds_and_unicode(self):
        self.assertEqual(query.tokens('CAFÉ'), query.tokens('cafe\u0301'))
        self.assertIn('c' + b'ae-743'.hex(), query.tokens('AE-743'))
        self.assertNotEqual(query.tokens('AE-743'), query.tokens('AE-744'))

    def test_coverage_failed_write_does_not_claim_freshness(self):
        self.run_fixture()
        self.fill()
        old = (store.cache_dir(self.root) / 'coverage.json').read_bytes()
        with patch.object(service, 'record_coverage', side_effect=OSError('disk full')):
            result = service.backfill(self.root, apply=True, yes=True)
        self.assertEqual(result['state'], 'partial')
        self.assertIn('not persisted', str(result['errors']))
        self.assertEqual(old, (store.cache_dir(self.root) / 'coverage.json').read_bytes())

    def test_lock_contention_bounded(self):
        with store.writer_lock(self.root):
            with self.assertRaisesRegex(ValueError, 'busy'):
                with store.writer_lock(self.root, timeout=0.02):
                    pass


    def test_archive_closure_survives_generation_and_coverage_failure(self):
        import argparse
        import contextlib
        import io
        path = self.root / '.flow' / 'runs' / 'scout'
        path.mkdir()
        (path / 'scout-summary.md').write_text('## Scope\nKeep SQLite.\n')
        args = argparse.Namespace(work_id='scout', event='archive-scout', artifact=['scout_summary=.flow/runs/scout/scout-summary.md'], disposition=['capability_gaps=n/a', 'memory=n/a'], note=None, json=True)
        with patch('fsutil.repo_root', return_value=self.root), patch.object(service, 'build_envelope', side_effect=ValueError('extract failed')), patch.object(service, 'refresh_coverage', side_effect=OSError('cache failed')), contextlib.redirect_stdout(io.StringIO()) as output:
            code = service.archive_transition(args)
        self.assertEqual(code, 0)
        report = json.loads(output.getvalue())
        self.assertTrue(report['ok'])
        self.assertEqual(len(report['enrichment_diagnostics']), 2)
        self.assertEqual(json.loads((path / 'run.json').read_text())['state'], 'archived')
        preview = service.backfill(self.root)
        row = next(r for r in preview['runs'] if r['work_id'] == 'scout')
        self.assertEqual(row['conditions'], ['live_regression'])
        self.fill()
        self.assertTrue((path / 'abstract.json').exists())

    def test_archive_closure_survives_publication_and_index_failures(self):
        import argparse
        import contextlib
        import io
        for stage in ('generation', 'validation', 'envelope', 'index', 'coverage'):
            with self.subTest(stage=stage):
                path = self.root / '.flow' / 'runs' / stage
                path.mkdir()
                (path / 'scout-summary.md').write_text('## Scope\nKeep SQLite.\n')
                args = argparse.Namespace(work_id=stage, event='archive-scout', artifact=[f'scout_summary=.flow/runs/{stage}/scout-summary.md'], disposition=['capability_gaps=n/a', 'memory=n/a'], note=None, json=True)
                if stage == 'index':
                    query.rebuild(self.root)
                targets = {'generation': (service, 'build_envelope'), 'validation': (service, 'validate_envelope'), 'envelope': (service, 'write_envelope'), 'index': (query, 'rebuild'), 'coverage': (service, 'refresh_coverage')}
                owner, method = targets[stage]
                target = patch.object(owner, method, side_effect=ValueError(stage + ' failed') if stage in ('generation', 'validation') else OSError(stage + ' failed'))
                with patch('fsutil.repo_root', return_value=self.root), target, contextlib.redirect_stdout(io.StringIO()) as output:
                    code = service.archive_transition(args)
                self.assertEqual(code, 0)
                report = json.loads(output.getvalue())
                self.assertTrue(report['enrichment_diagnostics'])
                self.assertEqual(json.loads((path / 'run.json').read_text())['state'], 'archived')

    def test_incremental_noop_and_rebuild_records_match(self):
        self.run_fixture()
        self.indexed()
        before = store.projection_path(self.root).read_bytes()
        self.fill()
        self.assertEqual(before, store.projection_path(self.root).read_bytes())
        meta_before, rows_before = store.read_projection(self.root)
        query.rebuild(self.root)
        self.assertEqual((meta_before, rows_before), store.read_projection(self.root))

    def test_interrupted_rebuild_preserves_previous_database(self):
        self.run_fixture()
        self.indexed()
        before = store.projection_path(self.root).read_bytes()
        with self.assertRaisesRegex(ValueError, 'changed'):
            store.publish_projection(self.root, [], 'new', query.VERSIONS, verify=lambda: False)
        self.assertEqual(before, store.projection_path(self.root).read_bytes())

    def test_unanchored_declarations_cannot_establish_current_status(self):
        path = self.run_fixture()
        self.fill()
        envelope = json.loads((path / 'abstract.json').read_text())
        # A closure event claiming a lost declaration body is incomplete authority.
        event = json.loads((path / 'events.jsonl').read_text())
        event['dispositions']['archive_declarations'] = '0' * 64
        (path / 'events.jsonl').write_text(json.dumps(event) + '\n')
        query.rebuild(self.root)
        result = query.search(self.root, 'SQLite')
        self.assertEqual(result['state'], 'partial')
        self.assertEqual(result['shown'], 0)
        self.assertEqual(result['uncertain_matches'], 1)

    def test_stale_refinement_generated_fallback_remains_searchable(self):
        path = self.run_fixture()
        self.fill()
        value = json.loads((path / 'abstract.json').read_text())
        value['refinement'] = {'revision': 'rev1', 'actor': 'agent', 'reason': 'clarify', 'base_generated_digest': model.digest(value['generated']), 'patches': {'decision': copy.deepcopy(value['generated']['fields']['decision'])}}
        (path / 'abstract.json').write_bytes(store.encode(value))
        (path / 'archive.md').write_text('## Work Closed\nKeep SQLite independently per overlay.\n')
        self.fill(rescan=True)
        query.rebuild(self.root)
        result = query.search(self.root, 'SQLite')
        self.assertEqual(result['shown'], 1, result)
        self.assertEqual(result['hits'][0]['effective']['refinement_state'], 'stale')

    def test_wrong_component_never_consumes_slot(self):
        self.run_fixture('one')
        self.run_fixture('wrong', text='## Work Closed\nSQLite SQLite SQLite SQLite SQLite.\n')
        self.indexed()
        # No declared component: a qualified filter must not infer it from text.
        result = query.search(self.root, 'SQLite', component=self.sid + ':search', top_k=1)
        self.assertEqual(result['shown'], 0)
        self.assertEqual(result['total_matches'], 0)

    def test_noop_source_ties_are_stable(self):
        self.run_fixture('a')
        self.run_fixture('b')
        self.indexed()
        first = query.search(self.root, 'SQLite')
        second = query.search(self.root, 'SQLite')
        self.assertEqual([h['qualified_id'] for h in first['hits']], [h['qualified_id'] for h in second['hits']])
        home = Path(self.tmp.name) / 'home'
        (home / '.flow').mkdir(parents=True)
        (home / '.flow' / 'retrieval-capabilities.json').write_text(json.dumps(preflight.probe(persist=False)))
        outputs = [subprocess.run([sys.executable, str(CLI / 'flow.py'), 'archive', 'search', 'SQLite', '--json'], cwd=self.root, env={**os.environ, 'HOME': str(home)}, capture_output=True, text=True, check=True).stdout for _ in range(2)]
        self.assertEqual([[h['qualified_id'] for h in json.loads(raw)['hits']] for raw in outputs], [[h['qualified_id'] for h in first['hits']]] * 2)

    def test_archive_event_coverage_reads_only_named_run(self):
        import argparse
        import contextlib
        import io
        path = self.root / '.flow' / 'runs' / 'scout'
        path.mkdir()
        (path / 'scout-summary.md').write_text('## Scope\nKeep SQLite.\n')
        args = argparse.Namespace(work_id='scout', event='archive-scout', artifact=['scout_summary=.flow/runs/scout/scout-summary.md'], disposition=['capability_gaps=n/a', 'memory=n/a'], note=None, json=True)
        inventory = service.inventory

        def named_only(root, work_ids=None):
            self.assertEqual(work_ids, ['scout'])
            return inventory(root, work_ids=work_ids)

        with patch('fsutil.repo_root', return_value=self.root), patch.object(service, 'inventory', side_effect=named_only), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(service.archive_transition(args), 0)
        self.assertEqual(json.loads(output.getvalue())['enrichment_diagnostics'], [])
        coverage = store.cached_coverage(self.root)
        self.assertIsNone(coverage['counts'])
        self.assertFalse(coverage['inventory_complete'])

    def test_missing_closure_event_is_not_current(self):
        path = self.run_fixture()
        self.fill()
        (path / 'events.jsonl').unlink()
        query.rebuild(self.root)
        result = query.search(self.root, 'SQLite')
        self.assertEqual(result['state'], 'partial')
        self.assertEqual(result['shown'], 0)
        self.assertEqual(result['uncertain_matches'], 1)

    def test_changed_declaration_evidence_quarantines_edges(self):
        self.run_fixture('old')
        path = self.run_fixture('new')
        self.fill()
        envelope = json.loads((path / 'abstract.json').read_text())
        pointer = copy.deepcopy(envelope['generated']['fields']['decision']['sources'][0])
        envelope['declarations'] = {'supersedes': [{'target': {'source_id': self.sid, 'work_id': 'old'}, 'whole_run': True, 'actor': 'engineer', 'rationale': 'replace', 'evidence': [pointer]}]}
        (path / 'abstract.json').write_bytes(store.encode(envelope))
        event = json.loads((path / 'events.jsonl').read_text())
        event['dispositions']['archive_declarations'] = model.declaration_digest(envelope['identity'], envelope['declarations'])
        (path / 'events.jsonl').write_text(json.dumps(event) + '\n')
        (path / 'archive.md').write_text('## Work Closed\nDifferent SQLite decision.\n')
        source = assess_source(self.root)
        new = next(r for r in source['records'] if r['work_id'] == 'new')
        self.assertEqual(new['declaration_status'], 'unverified')
        from archive_graph import resolve_graph
        graph = resolve_graph([source])
        self.assertEqual(graph['records'][self.sid + ':old']['status'], 'unknown')


    def test_inspect_changed_source_never_reports_current(self):
        import argparse
        import contextlib
        import io
        import archive_commands
        path = self.run_fixture()
        self.fill()
        (path / 'archive.md').write_text('## Work Closed\nChanged decision.\n')
        args = argparse.Namespace(command='archive', archive_action='inspect', qualified_id=self.sid + ':one')
        with patch.object(archive_commands, 'repo_root', return_value=self.root), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(archive_commands.dispatch(args), 3)
        result = json.loads(output.getvalue())
        self.assertEqual(result['hits'][0]['status'], 'unknown')
        self.assertIn('content_unverified', str(result['diagnostics']))

    def test_malformed_filter_identity_is_invalid_before_preflight(self):
        for component in ('not-a-uuid:thing', self.sid + ':', self.sid + ':one:two', self.sid + ':/escape'):
            with self.subTest(component=component), patch.object(preflight, 'current', side_effect=AssertionError('must validate first')):
                self.assertEqual(query.search(self.root, 'SQLite', component=component)['state'], 'invalid_request')
        with patch.object(preflight, 'current', side_effect=AssertionError('must validate first')):
            self.assertEqual(query.search(self.root, 'SQLite', sources=['invalid'])['state'], 'invalid_request')

    def test_current_only_does_not_depend_on_unreadable_ancestor(self):
        child = self.root / 'child'
        (child / '.flow' / 'runs').mkdir(parents=True)
        (child / '.flow' / 'PROJECT.md').write_text('# Child')
        with store.writer_lock(child):
            store.ensure_identity(child)
        self.run_fixture(root=child)
        self.assertEqual(service.backfill(child, apply=True, yes=True)['state'], 'complete')
        self.assertEqual(query.rebuild(child)['state'], 'complete')
        (self.root / '.flow' / 'identity.json').write_text('invalid')
        result = query.search(child, 'SQLite', current_only=True)
        self.assertEqual(result['state'], 'complete', result)
        self.assertEqual(result['shown'], 1)
        self.assertEqual(result['context_sources'][1]['state'], 'unavailable')
        self.assertEqual(query.search(child, 'SQLite')['state'], 'partial')

    def test_known_component_and_work_type_filter_before_top_k(self):
        (self.root / '.flow' / 'components.json').write_text(json.dumps({'schema_version': 1, 'components': [{'component_id': 'reader'}, {'component_id': 'writer'}]}))
        for work, component, kind, decision in [('wrong', 'writer', 'bug', 'SQLite'), ('right', 'reader', 'feature', 'Keep SQLite storage owned by each overlay.')]:
            path = self.run_fixture(work, text=f'## Work Closed\n{decision}\n\n## Component\n{component}\n\n## Work type\n{kind}\n')
            self.fill(work_ids=[work])
            pointer = {'source_id': self.sid, 'work_id': work, 'path': f'runs/{work}/archive.md', 'selector': 'heading:component:1', 'digest': hashlib.sha256((path / 'archive.md').read_bytes()).hexdigest()}
            selection = {'field': 'component', 'actor': 'fixture', 'reason': 'Explicit component ownership', 'source': pointer, 'value': {'source_id': self.sid, 'component_id': component}}
            data = {'schema_version': 1, 'actor': 'fixture', 'reason': 'Declare component', 'declarations': {'selections': [selection]}}
            service.mutate(self.root, work, 'declare', data, store.file_digest(path / 'abstract.json'), apply=True, yes=True)
        self.fill(rescan=True)
        self.assertEqual(query.rebuild(self.root)['state'], 'complete')
        self.assertEqual(query.search(self.root, 'SQLite', top_k=1)['hits'][0]['work_id'], 'wrong')
        for filters in ({'component': self.sid + ':reader'}, {'work_type': 'feature'}):
            result = query.search(self.root, 'SQLite', top_k=1, **filters)
            self.assertEqual(result['hits'][0]['work_id'], 'right')
            self.assertEqual(result['total_matches'], 1)

    def test_mixed_backfill_inventory_separates_canonical_and_legacy_states(self):
        self.run_fixture('archived')
        for work, state in [('active', 'implementing'), ('handback', 'handback_ready')]:
            directory = self.run_fixture(work)
            run = json.loads((directory / 'run.json').read_text())
            run['state'] = state
            (directory / 'run.json').write_text(json.dumps(run))
        (self.root / '.flow' / 'runs' / 'legacy').mkdir()
        malformed = self.run_fixture('malformed')
        (malformed / 'abstract.json').write_text('invalid')
        outdated = self.run_fixture('outdated')
        (outdated / 'abstract.json').write_text(json.dumps({'schema_version': 0, 'generated': {'extractor_version': 0}}))
        before = self.tree()
        result = service.backfill(self.root)
        rows = {row['work_id']: row for row in result['runs']}
        self.assertEqual([row['work_id'] for row in result['runs'] if row['action'] == 'generate'], ['archived'])
        for work in ('active', 'handback'):
            self.assertEqual(rows[work]['conditions'], ['not_archived'])
            self.assertFalse(rows[work]['eligible'])
        self.assertEqual(rows['legacy']['conditions'], ['legacy_awaiting_review'])
        self.assertEqual(rows['malformed']['conditions'], ['malformed_abstract'])
        self.assertEqual(rows['outdated']['conditions'], ['outdated_abstract'])
        self.assertEqual(self.tree(), before)

    def test_excluded_child_control_source_change_rejects_parent_result(self):
        self.run_fixture('parent')
        self.indexed()
        child = self.root / 'child'
        (child / '.flow' / 'runs').mkdir(parents=True)
        (child / '.flow' / 'PROJECT.md').write_text('# Child')
        with store.writer_lock(child):
            store.ensure_identity(child)
        path = self.run_fixture('child', root=child)
        self.assertEqual(service.backfill(child, apply=True, yes=True)['state'], 'complete')
        self.assertEqual(query.rebuild(child)['state'], 'complete')
        real_pack = query.pack
        changed = False

        def race(*args, **kwargs):
            nonlocal changed
            result = real_pack(*args, **kwargs)
            if not changed:
                changed = True
                (path / 'archive.md').write_text('## Work Closed\nChanged child control evidence.\n')
            return result

        with patch.object(query, 'pack', side_effect=race):
            result = query.search(child, 'SQLite', sources=[self.sid])
        self.assertEqual(result['state'], 'unavailable')
        self.assertEqual(result['reason'], 'source_changed_during_query')


if __name__ == '__main__':
    unittest.main()
