"""Reviewed legacy integration against actual files, locks and SQLite projections."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))
import archive_legacy as legacy
import archive_model as model
import archive_query as query
import archive_service as service
import archive_sources as sources
import archive_store as store


class LegacyIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / 'parent'
        self.sid = self.project(self.root)
        self.available = patch('archive_preflight.current', return_value={'state': 'available'})
        self.available.start()
        self.addCleanup(self.available.stop)

    def project(self, root):
        (root / '.flow' / 'runs').mkdir(parents=True)
        (root / '.flow' / 'PROJECT.md').write_text('# Fixture\n')
        with store.writer_lock(root):
            store.ensure_ignore(root)
            return store.ensure_identity(root)

    def fixture(self, work='legacy', root=None):
        root = root or self.root
        path = root / '.flow' / 'runs' / work / 'HANDOFF.md'
        path.parent.mkdir(exist_ok=True)
        path.write_text('## Final outcome\nKeep archive retrieval read-only.\n\n## Closure\nReviewer accepts this completed work.\n\n## Rationale\nReads must not mutate shared ancestor indexes.\n\n## Applies when\nProduction shared-reader queries.\n')
        return path

    def request(self, work='legacy', root=None, action='approve'):
        root = root or self.root
        identity = {'source_id': store.read_identity(root), 'work_id': work}
        result = {'schema_version': 1, 'identity': identity, 'action_id': str(uuid.uuid4()),
                  'action': action, 'reviewer': 'fixture-reviewer', 'reviewer_is_author': True,
                  'reason': 'Reviewed retained outcome and closure', 'closed_at': {'state': 'unknown'},
                  'expected_base_fingerprint': legacy.observe(root, work)['fingerprint']}
        if action in {'approve', 'reapprove'}:
            path = root / '.flow' / 'runs' / work / 'HANDOFF.md'
            def pointer(heading):
                return {**identity, 'path': path.relative_to(root / '.flow').as_posix(),
                        'selector': 'heading:' + heading + ':1', 'digest': hashlib.sha256(path.read_bytes()).hexdigest()}
            final, closure = pointer('final outcome'), pointer('closure')
            result.update(closure_assertion='The cited closure accepts the cited outcome for this candidate.',
                          evidence=[{'kind': 'local', 'role': role, 'source': source, 'explanation': 'Selected fixture passage'}
                                    for role, source in [('final_outcome', final), ('closure_evidence', closure)]],
                          selected_final_outcome_sources=[final])
        return result

    def apply(self, record, root=None):
        result = legacy.review(root or self.root, record['identity']['work_id'], record, apply=True, yes=True)
        self.assertEqual(result['review_commit'], 'committed', result)
        return result

    def approve(self, work='legacy', root=None):
        self.fixture(work, root)
        record = self.request(work, root)
        self.apply(record, root)
        result = query.rebuild(root or self.root)
        self.assertEqual(result['state'], 'complete', result)
        return record

    def envelope(self, work='legacy'):
        return self.root / '.flow' / 'runs' / work / 'abstract.json'

    def test_approved_distinct_authority_and_unknown_date_omission(self):
        self.approve()
        result = query.search(self.root, 'archive retrieval')
        self.assertEqual(result['shown'], 1, result)
        hit = result['hits'][0]
        self.assertEqual(hit['abstract']['schema_version'], 2)
        self.assertEqual(hit['abstract']['provenance']['origin'], 'reviewed_legacy')
        self.assertEqual(hit['effective']['fields']['closed_at']['state'], 'unknown')
        filtered = query.search(self.root, 'archive retrieval', since='2026-01-01')
        self.assertEqual(filtered['shown'], 0)
        self.assertTrue(any(d['code'] == 'unknown_legacy_date_omitted' for d in filtered['diagnostics']))
        self.assertFalse((self.envelope().parent / 'run.json').exists())
        self.assertFalse((self.envelope().parent / 'events.jsonl').exists())

    def test_withdrawal_survives_failed_refresh_and_old_approval_retry(self):
        approval = self.approve()
        child = self.root / 'child'
        self.project(child)
        self.assertEqual(query.rebuild(child)['state'], 'complete')
        self.assertEqual(query.search(child, 'archive retrieval')['shown'], 1)
        with patch.object(query, 'rebuild', return_value={'state': 'unavailable', 'reason': 'injected index failure'}), patch.object(service, 'refresh_coverage', side_effect=OSError('injected coverage failure')):
            result = self.apply(self.request(action='withdraw'))
        self.assertEqual(result['review_commit'], 'committed')
        for root in [self.root, child]:
            for historical in [False, True]:
                response = query.search(root, 'archive retrieval', include_superseded=historical)
                self.assertEqual(response['shown'], 0, response)
        replay = self.apply(approval)
        self.assertTrue(replay['replayed'])
        self.assertEqual(replay['effective_disposition'], 'withdrawn')
        self.assertNotEqual(replay['action_revision'], replay['current_revision'])

    def test_rescan_repairs_prose_preserving_review_and_history(self):
        self.approve()
        value = json.loads(self.envelope().read_text())
        review = copy.deepcopy(value['legacy_review'])
        value['generated']['fields']['decision'] = 'malformed'
        self.envelope().write_text(json.dumps(value))
        self.assertEqual(query.search(self.root, 'archive retrieval')['shown'], 0)
        base = legacy.observe(self.root, 'legacy')['fingerprint']
        result = legacy.rescan(self.root, 'legacy', base_fingerprint=base, apply=True, yes=True)
        self.assertIsNone(result['review_commit'])
        repaired = self.envelope().read_bytes()
        self.assertEqual(json.loads(repaired)['legacy_review'], review)
        self.assertEqual(query.search(self.root, 'archive retrieval')['shown'], 1, result)
        for _ in range(2):
            base = legacy.observe(self.root, 'legacy')['fingerprint']
            legacy.rescan(self.root, 'legacy', base_fingerprint=base, apply=True, yes=True)
            self.assertEqual(self.envelope().read_bytes(), repaired)

    def test_evidence_change_excludes_without_review_mutation_and_restoration(self):
        self.approve()
        original = self.envelope().read_bytes()
        path = self.envelope().parent / 'HANDOFF.md'
        evidence = path.read_bytes()
        path.write_text(path.read_text().replace('read-only', 'read-write'))
        base = legacy.observe(self.root, 'legacy')['fingerprint']
        legacy.rescan(self.root, 'legacy', base_fingerprint=base, apply=True, yes=True)
        self.assertEqual(self.envelope().read_bytes(), original)
        self.assertEqual(query.search(self.root, 'archive retrieval')['shown'], 0)
        self.assertEqual(legacy.observe(self.root, 'legacy')['effective_disposition'], 'approved')
        path.write_bytes(evidence)
        self.assertEqual(query.search(self.root, 'archive retrieval')['shown'], 1)
        self.apply(self.request(action='withdraw'))
        path.write_bytes(evidence)
        query.rebuild(self.root)
        self.assertEqual(query.search(self.root, 'archive retrieval', include_superseded=True)['shown'], 0)

    def test_targeted_repair_preserves_unrelated_coverage_rows_and_flags(self):
        self.approve()
        unrelated = {'work_id': 'other-gap', 'eligible': False, 'conditions': ['live_regression'], 'action': 'generate'}
        existing = service.inventory(self.root)
        store.record_coverage(self.root, existing + [unrelated], '2026-01-01T00:00:00Z', inventory_complete=False)
        base = legacy.observe(self.root, 'legacy')['fingerprint']
        legacy.rescan(self.root, 'legacy', base_fingerprint=base, apply=True, yes=True)
        coverage = store.cached_coverage(self.root)
        self.assertFalse(coverage['inventory_complete'])
        self.assertEqual(coverage['observed_at'], '2026-01-01T00:00:00Z')
        self.assertIn(unrelated, coverage['runs'])

    def test_canonical_collision_cannot_take_over_even_if_active(self):
        self.approve()
        path = self.envelope().parent / 'run.json'
        path.write_text(json.dumps({'work_id': 'legacy', 'state': 'planning'}))
        original = path.read_bytes()
        self.assertEqual(query.search(self.root, 'archive retrieval')['shown'], 0)
        query.rebuild(self.root)
        self.assertEqual(query.search(self.root, 'archive retrieval')['shown'], 0)
        self.assertEqual(path.read_bytes(), original)
        self.assertTrue(any('collision' in str(row) for row in service.inventory(self.root)))

    def test_malformed_genesis_plus_new_active_run_remains_quarantined(self):
        self.approve()
        path = self.envelope().parent / 'run.json'
        path.write_text(json.dumps({'work_id': 'legacy', 'state': 'planning'}))
        for malformed in ['{invalid-json', '[]', 'null']:
            with self.subTest(malformed=malformed):
                self.envelope().write_text(malformed)
                observation = sources.assess_source(self.root)
                self.assertEqual(observation['state'], 'partial')
                self.assertTrue(any(d['code'] == 'ambiguous_archive_authority' for d in observation['diagnostics']))
                query.rebuild(self.root)
                result = query.search(self.root, 'archive retrieval')
                self.assertEqual(result['shown'], 0)
                self.assertEqual(result['state'], 'partial')
                self.assertIn('ambiguous_archive_authority', service.inventory(self.root)[0]['conditions'])

    def test_canonical_incoming_link_does_not_lose_independent_closure(self):
        self.approve()
        directory = self.root / '.flow' / 'runs' / 'canonical'
        directory.mkdir()
        path = directory / 'archive.md'
        path.write_text('## Work Closed\nKeep production archive retrieval read-only.\n')
        identity = {'source_id': self.sid, 'work_id': 'canonical'}
        pointer = {**identity, 'path': 'runs/canonical/archive.md', 'selector': 'heading:work closed:1', 'digest': hashlib.sha256(path.read_bytes()).hexdigest()}
        declarations = {'supersedes': [{'target': {'source_id': self.sid, 'work_id': 'legacy'}, 'whole_run': True,
                                        'actor': 'fixture-reviewer', 'rationale': 'Explicit canonical successor', 'evidence': [pointer]}]}
        at = '2026-09-07T00:00:00Z'
        (directory / 'run.json').write_text(json.dumps({'work_id': 'canonical', 'state': 'archived', 'gates': {'archive': at}, 'artifacts': {'archive': '.flow/runs/canonical/archive.md'}}))
        (directory / 'events.jsonl').write_text(json.dumps({'event': 'archive', 'to': 'archived', 'at': at,
                                                         'dispositions': {'archive_declarations': model.declaration_digest(identity, declarations)}}) + '\n')
        # Retain explicit declaration before generation as canonical archiving does.
        value = {'schema_version': 1, 'identity': identity, 'declarations': declarations, 'generated': None, 'refinement': None, 'provenance': {'origin': 'archive'}}
        (directory / 'abstract.json').write_text(json.dumps(value))
        self.assertEqual(service.backfill(self.root, apply=True, yes=True)['state'], 'complete')
        self.apply(self.request(action='withdraw'))
        query.rebuild(self.root)
        result = query.search(self.root, 'archive retrieval')
        self.assertEqual([h['work_id'] for h in result['hits']], ['canonical'], result)
        self.assertEqual(result['hits'][0]['status'], 'current')
        self.assertTrue(any(d['code'] == 'unresolved_legacy_target' for d in result['diagnostics']))

    def test_canonical_backfill_does_not_import_legacy(self):
        self.fixture()
        before = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        rows = service.backfill(self.root)['runs']
        self.assertFalse(rows[0]['eligible'])
        self.assertEqual(rows[0]['conditions'], ['legacy_awaiting_review'])
        self.assertEqual(before, {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_external_capture_is_offline_and_changed_bytes_are_excluded(self):
        import socket
        self.fixture()
        record = self.request()
        for item in record['evidence']:
            item.update(kind='external_capture', url='https://example.invalid/review/legacy', captured_at='2026-09-07T00:00:00Z')
        with patch.object(socket, 'socket', side_effect=AssertionError('offline path opened a network socket')):
            self.apply(record)
            query.rebuild(self.root)
            result = query.search(self.root, 'archive retrieval')
        self.assertEqual(result['shown'], 1, result)
        self.assertEqual(result['hits'][0]['abstract']['legacy_review']['evidence'][0]['kind'], 'external_capture')
        (self.envelope().parent / 'HANDOFF.md').write_text('Capture contents changed')
        self.assertEqual(query.search(self.root, 'archive retrieval')['shown'], 0)
        self.assertEqual(legacy.observe(self.root, 'legacy')['evidence_condition'], 'evidence_stale')

    def test_known_historical_date_uses_reviewed_evidence_not_recording_time(self):
        self.fixture()
        record = self.request()
        record['closed_at'] = {'state': 'known', 'value': '2020-02-03T00:00:00Z', 'source': record['evidence'][1]['source']}
        self.apply(record)
        query.rebuild(self.root)
        result = query.search(self.root, 'archive retrieval', since='2019-01-01')
        self.assertEqual(result['shown'], 1)
        self.assertEqual(result['hits'][0]['effective']['fields']['closed_at']['value'], '2020-02-03T00:00:00Z')
        self.assertEqual(query.search(self.root, 'archive retrieval', since='2021-01-01')['shown'], 0)

    def test_long_reachable_history_is_validated_but_not_returned(self):
        from archive_legacy_model import make_review
        self.approve()
        value = json.loads(self.envelope().read_text())
        current = value['legacy_review']
        directory = self.envelope().parent / 'abstract-history/reviews'
        directory.mkdir(parents=True, exist_ok=True)
        for number in range(100):
            (directory / (current['revision_digest'] + '.json')).write_bytes(store.encode(current))
            request = copy.deepcopy(current)
            for key in ['review_id', 'revision_digest', 'semantic_payload_digest', 'recorded_at', 'previous_revision_digest']:
                request.pop(key, None)
            request.update(action='reapprove', action_id='history-' + str(number))
            current = make_review(request, review_id=current['review_id'], previous_revision_digest=current['revision_digest'], recorded_at='2026-09-07T00:00:00Z')
        value['legacy_review'] = current
        self.envelope().write_bytes(store.encode(value))
        self.assertEqual(len(legacy.observe(self.root, 'legacy')['chain']), 101)
        query.rebuild(self.root)
        result = query.search(self.root, 'archive retrieval')
        self.assertEqual(result['shown'], 1, result)
        raw = query.serialized(result)
        self.assertNotIn('history-0"', raw)
        self.assertIn('history-99', raw)
        self.assertLessEqual(len(raw.encode()), result['max_output_bytes'])
        oldest = directory / (json.loads(next(directory.iterdir()).read_text())['revision_digest'] + '.json')
        oldest.unlink()
        self.assertFalse(legacy.observe(self.root, 'legacy')['eligible'])
        self.assertEqual(query.search(self.root, 'archive retrieval')['shown'], 0)

    def test_no_fit_preserves_whole_authority_and_no_full_history(self):
        self.approve()
        record = self.request(action='reapprove')
        record['reason'] = 'Retained review provenance. ' * 1200
        self.apply(record)
        query.rebuild(self.root)
        result = query.search(self.root, 'archive retrieval', max_output_bytes=2000)
        self.assertEqual(result['shown'], 0)
        self.assertEqual(result['reason'], 'no_hit_fits')
        self.assertLessEqual(len(query.serialized(result).encode()), 2000)

    def test_rescan_preview_proposes_missing_content_and_preserves_every_file(self):
        self.fixture()
        self.apply(self.request())
        value = json.loads(self.envelope().read_text())
        value['generated'] = None
        self.envelope().write_text(json.dumps(value))
        before = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        result = legacy.rescan(self.root, 'legacy')
        proposed = result['proposed_operations']
        self.assertEqual(result['state'], 'preview')
        self.assertEqual(proposed['abstract']['action'], 'regenerate')
        self.assertEqual(proposed['index']['action'], 'skipped')
        self.assertEqual(proposed['coverage']['action'], 'refresh')
        self.assertEqual(proposed['coverage']['qualified_id'], legacy.observe(self.root, 'legacy')['qualified_id'])
        self.assertEqual(before, {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob('*') if path.is_file()})
        applied = legacy.rescan(self.root, 'legacy', result['fingerprint'], apply=True, yes=True)
        self.assertEqual(applied['abstract']['state'], 'committed', applied)
        self.assertIsNotNone(json.loads(self.envelope().read_text())['generated'])

    def test_rescan_preview_distinguishes_noop_and_established_projection(self):
        self.approve()
        base = legacy.observe(self.root, 'legacy')['fingerprint']
        self.assertEqual(legacy.rescan(self.root, 'legacy', base, apply=True, yes=True)['abstract']['state'], 'not_needed')
        query.rebuild(self.root)
        before = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        result = legacy.rescan(self.root, 'legacy')
        proposed = result['proposed_operations']
        self.assertEqual(proposed['abstract']['action'], 'not_needed')
        self.assertEqual(proposed['index']['action'], 'refresh')
        self.assertEqual(proposed['coverage']['action'], 'refresh')
        self.assertEqual(before, {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob('*') if path.is_file()})

    def test_excluded_rescan_preview_proposes_only_coverage_refresh(self):
        self.fixture()
        self.apply(self.request())
        self.apply(self.request(action='withdraw'))
        before = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        result = legacy.rescan(self.root, 'legacy')
        proposed = result['proposed_operations']
        self.assertEqual(proposed['abstract']['action'], 'not_needed')
        self.assertEqual(proposed['index']['action'], 'skipped')
        self.assertEqual(proposed['coverage']['action'], 'refresh')
        self.assertEqual(proposed['coverage']['qualified_id'], legacy.observe(self.root, 'legacy')['qualified_id'])
        self.assertEqual(before, {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob('*') if path.is_file()})


if __name__ == '__main__':
    unittest.main()
