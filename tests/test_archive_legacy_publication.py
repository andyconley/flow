import copy
import hashlib
import json
import os
import stat
from contextlib import contextmanager
from unittest.mock import patch
from pathlib import Path
import sys
import tempfile
import unittest

CLI = Path(__file__).resolve().parents[1] / "cli"
sys.path.insert(0, str(CLI))

import archive_legacy as legacy
from archive_store import ensure_identity, writer_lock


class LegacyPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        (self.root / ".flow" / "runs" / "legacy").mkdir(parents=True)
        (self.root / ".flow" / "PROJECT.md").write_text("# Project\n")
        with writer_lock(self.root):
            self.source_id = ensure_identity(self.root)
        (self.root / ".flow" / "runs" / "legacy" / "outcome.md").write_text("# Work Closed\nDone\n")
        (self.root / ".flow" / "runs" / "legacy" / "closure.md").write_text("# Acceptance\nAccepted\n")

    def _pointer(self, name, heading):
        path = self.root / ".flow" / "runs" / "legacy" / name
        return {"source_id": self.source_id, "work_id": "legacy", "path": "runs/legacy/" + name,
                "selector": heading, "digest": hashlib.sha256(path.read_bytes()).hexdigest()}

    def _request(self, action="approve", action_id="22222222-2222-4222-8222-222222222222"):
        outcome, closure = self._pointer("outcome.md", "heading:work closed:1"), self._pointer("closure.md", "heading:acceptance:1")
        value = {"schema_version": 1, "identity": {"source_id": self.source_id, "work_id": "legacy"},
                 "action_id": action_id, "action": action, "reviewer": "andy", "reviewer_is_author": True,
                 "reason": "reviewed", "expected_base_fingerprint": legacy.observe(self.root, "legacy")["fingerprint"],
                 "closed_at": {"state": "unknown"}, "evidence": [], "selected_final_outcome_sources": [], "field_selections": []}
        if action in {"approve", "reapprove"}:
            value.update({"evidence": [
                {"kind": "local", "role": "final_outcome", "source": outcome, "explanation": "outcome"},
                {"kind": "local", "role": "closure_evidence", "source": closure, "explanation": "closure"},
            ], "selected_final_outcome_sources": [outcome], "closure_assertion": "closed"})
        return value

    def test_preview_is_read_only_and_apply_preserves_lifecycle_files(self):
        before = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        request = self._request()
        preview = legacy.review(self.root, "legacy", request)
        self.assertEqual(preview["state"], "preview")
        after = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        applied = legacy.review(self.root, "legacy", request, apply=True, yes=True)
        self.assertEqual(applied["review_commit"], "committed")
        self.assertTrue(legacy.observe(self.root, "legacy")["eligible"])
        self.assertFalse((self.root / ".flow" / "runs" / "legacy" / "run.json").exists())
        self.assertFalse((self.root / ".flow" / "runs" / "legacy" / "events.jsonl").exists())

    def test_old_approval_replay_reports_latest_withdrawal(self):
        approval = self._request()
        self.assertEqual(legacy.review(self.root, "legacy", approval, apply=True, yes=True)["review_commit"], "committed")
        withdrawal = self._request("withdraw", "33333333-3333-4333-8333-333333333333")
        self.assertEqual(legacy.review(self.root, "legacy", withdrawal, apply=True, yes=True)["effective_disposition"], "withdrawn")
        replay = legacy.review(self.root, "legacy", approval, apply=True, yes=True)
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["effective_disposition"], "withdrawn")
        self.assertNotEqual(replay["action_revision"], replay["current_revision"])

    def test_changed_evidence_is_stale_and_cannot_be_rescanned(self):
        approval = self._request()
        legacy.review(self.root, "legacy", approval, apply=True, yes=True)
        (self.root / ".flow" / "runs" / "legacy" / "closure.md").write_text("# Acceptance\nChanged\n")
        observation = legacy.observe(self.root, "legacy")
        self.assertEqual(observation["effective_disposition"], "approved")
        self.assertEqual(observation["evidence_condition"], "evidence_stale")
        self.assertFalse(observation["eligible"])
        result = legacy.rescan(self.root, "legacy")
        self.assertEqual(result["abstract"]["state"], "not_needed")

    def test_replay_after_deleted_evidence_reports_receipt_and_current_state(self):
        approval = self._request()
        legacy.review(self.root, "legacy", approval, apply=True, yes=True)
        withdrawal = self._request("withdraw", "withdraw-id")
        legacy.review(self.root, "legacy", withdrawal, apply=True, yes=True)
        path = self.root / ".flow/runs/legacy/closure.md"
        path.unlink()
        before = (self.root / ".flow/runs/legacy/abstract.json").read_bytes()
        result = legacy.review(self.root, "legacy", approval, apply=True, yes=True)
        self.assertEqual(result["review_commit"], "committed", result)
        self.assertTrue(result["replayed"])
        self.assertEqual(result["effective_disposition"], "withdrawn")
        self.assertEqual(before, (self.root / ".flow/runs/legacy/abstract.json").read_bytes())

    def test_generation_failure_commits_review_and_is_repaired_by_rescan(self):
        request = self._request()
        with patch("archive_extract.extract_legacy", side_effect=ValueError("extractor failure")):
            result = legacy.review(self.root, "legacy", request, apply=True, yes=True)
        self.assertEqual(result["review_commit"], "committed")
        self.assertEqual(result["state"], "partial")
        observed = legacy.observe(self.root, "legacy")
        control = observed["review"]
        self.assertTrue(observed["eligible"])
        self.assertIsNone(observed["envelope"]["generated"])
        result = legacy.rescan(self.root, "legacy", observed["fingerprint"], apply=True, yes=True)
        self.assertIsNone(result["review_commit"])
        self.assertEqual(legacy.observe(self.root, "legacy")["review"], control)
        self.assertIsNotNone(legacy.observe(self.root, "legacy")["envelope"]["generated"])

    def test_history_and_before_replace_failures_preserve_prior_authority(self):
        approval = self._request()
        legacy.review(self.root, "legacy", approval, apply=True, yes=True)
        before = (self.root / ".flow/runs/legacy/abstract.json").read_bytes()
        original = legacy.atomic_write
        for failure in ["history", "current"]:
            with self.subTest(failure=failure):
                request = self._request("withdraw", "withdraw-" + failure)
                def fail(path, data, root):
                    if (failure == "history" and "abstract-history" in str(path)) or (failure == "current" and path.name == "abstract.json"):
                        raise OSError("injected before replacement")
                    return original(path, data, root)
                with patch.object(legacy, "atomic_write", side_effect=fail):
                    result = legacy.review(self.root, "legacy", request, apply=True, yes=True)
                self.assertEqual(result["review_commit"], "not_committed", result)
                self.assertEqual((self.root / ".flow/runs/legacy/abstract.json").read_bytes(), before)
                self.assertEqual(legacy.observe(self.root, "legacy")["effective_disposition"], "approved")

    def test_post_replace_failure_is_uncertain_and_replay_confirms_directory(self):
        approval = self._request()
        original = os.fsync
        def fail_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("injected directory durability failure")
            return original(fd)
        with patch("archive_store.os.fsync", side_effect=fail_directory):
            result = legacy.review(self.root, "legacy", approval, apply=True, yes=True)
        self.assertEqual(result["review_commit"], "uncertain", result)
        self.assertIsNotNone(result["current_revision"])
        with patch("archive_store.os.fsync", side_effect=fail_directory):
            retry = legacy.review(self.root, "legacy", approval, apply=True, yes=True)
        self.assertEqual(retry["review_commit"], "uncertain", retry)
        retry = legacy.review(self.root, "legacy", approval, apply=True, yes=True)
        self.assertEqual(retry["review_commit"], "committed")
        self.assertEqual(retry["current_revision"], result["current_revision"])
        self.assertEqual(len(legacy.observe(self.root, "legacy")["chain"]), 1)

    def test_rescan_post_replace_failure_reports_uncertain_content(self):
        approval = self._request()
        legacy.review(self.root, "legacy", approval, apply=True, yes=True)
        path = self.root / ".flow/runs/legacy/abstract.json"
        value = json.loads(path.read_text())
        control = copy.deepcopy(value["legacy_review"])
        value["generated"] = None
        path.write_text(json.dumps(value))
        before = legacy.observe(self.root, "legacy")
        original = os.fsync
        def fail_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("injected content durability failure")
            return original(fd)
        with patch("archive_store.os.fsync", side_effect=fail_directory):
            result = legacy.rescan(self.root, "legacy", before["fingerprint"], apply=True, yes=True)
        self.assertEqual(result["abstract"]["state"], "uncertain", result)
        self.assertIsNone(result["review_commit"])
        self.assertEqual(json.loads(path.read_text())["legacy_review"], control)

    def test_rescan_lost_readback_after_failed_publication_is_uncertain_and_preserves_review(self):
        approval = self._request()
        legacy.review(self.root, "legacy", approval, apply=True, yes=True)
        path = self.root / ".flow/runs/legacy/abstract.json"
        value = json.loads(path.read_text())
        control = copy.deepcopy(value["legacy_review"])
        value["generated"] = None
        path.write_text(json.dumps(value))
        base = legacy.observe(self.root, "legacy")["fingerprint"]
        original_write, original_observe = legacy.write_envelope, legacy.observe
        wrote = False

        def publish_then_fail(*args, **kwargs):
            nonlocal wrote
            original_write(*args, **kwargs)
            wrote = True
            raise OSError("directory durability failed")

        def lose_readback(*args, **kwargs):
            if wrote:
                raise OSError("readback unavailable")
            return original_observe(*args, **kwargs)

        with patch.object(legacy, "write_envelope", side_effect=publish_then_fail), patch.object(legacy, "observe", side_effect=lose_readback):
            result = legacy.rescan(self.root, "legacy", base, apply=True, yes=True)
        self.assertEqual(result["state"], "unavailable", result)
        self.assertEqual(result["abstract"]["state"], "uncertain", result)
        self.assertEqual(result["index"]["state"], "skipped", result)
        self.assertEqual(result["coverage"]["state"], "skipped", result)
        self.assertEqual(json.loads(path.read_text())["legacy_review"], control)
        self.assertIsNotNone(json.loads(path.read_text())["generated"])
        self.assertIsNone(result["current_revision"], result)
        self.assertEqual(result["qualified_id"], legacy.observe(self.root, "legacy")["qualified_id"])
        self.assertIn("retry", result["remedy"])

    def test_rescan_readback_failure_after_successful_write_reports_committed_content(self):
        approval = self._request()
        legacy.review(self.root, "legacy", approval, apply=True, yes=True)
        path = self.root / ".flow/runs/legacy/abstract.json"
        value = json.loads(path.read_text())
        control = copy.deepcopy(value["legacy_review"])
        value["generated"] = None
        path.write_text(json.dumps(value))
        base = legacy.observe(self.root, "legacy")["fingerprint"]
        original_write, original_observe = legacy.write_envelope, legacy.observe
        wrote = False

        def publish_then_mark(*args, **kwargs):
            nonlocal wrote
            original_write(*args, **kwargs)
            wrote = True

        def lose_post_write_readback(*args, **kwargs):
            if wrote:
                raise OSError("readback unavailable")
            return original_observe(*args, **kwargs)

        with patch.object(legacy, "write_envelope", side_effect=publish_then_mark), patch.object(legacy, "observe", side_effect=lose_post_write_readback):
            result = legacy.rescan(self.root, "legacy", base, apply=True, yes=True)
        self.assertEqual(result["state"], "unavailable", result)
        self.assertEqual(result["abstract"]["state"], "committed", result)
        self.assertEqual(result["index"]["state"], "skipped", result)
        self.assertEqual(result["coverage"]["state"], "skipped", result)
        self.assertEqual(json.loads(path.read_text())["legacy_review"], control)
        self.assertIsNotNone(json.loads(path.read_text())["generated"])
        self.assertIsNone(result["current_revision"], result)
        self.assertEqual(result["qualified_id"], legacy.observe(self.root, "legacy")["qualified_id"])
        self.assertIn("retry", result["remedy"])

    def test_rescan_path_readback_loss_after_publication_is_uncertain(self):
        legacy.review(self.root, "legacy", self._request(), apply=True, yes=True)
        path = self.root / ".flow/runs/legacy/abstract.json"
        value = json.loads(path.read_text())
        value["generated"] = None
        path.write_text(json.dumps(value))
        base = legacy.observe(self.root, "legacy")["fingerprint"]
        original_write, original_read = legacy.write_envelope, Path.read_bytes
        original_observe = legacy.observe
        wrote = readback_attempted = False

        def publish_then_fail(*args, **kwargs):
            nonlocal wrote
            original_write(*args, **kwargs)
            wrote = True
            raise OSError("directory durability failed")

        def lose_envelope_readback(candidate, *args, **kwargs):
            nonlocal readback_attempted
            if wrote and candidate.resolve() == path.resolve():
                readback_attempted = True
                raise OSError("envelope bytes unavailable")
            return original_read(candidate, *args, **kwargs)

        def lose_observation_after_readback(*args, **kwargs):
            if wrote and readback_attempted:
                raise OSError("observation unavailable after readback loss")
            return original_observe(*args, **kwargs)

        with patch.object(legacy, "write_envelope", side_effect=publish_then_fail), patch.object(Path, "read_bytes", lose_envelope_readback), patch.object(legacy, "observe", side_effect=lose_observation_after_readback):
            result = legacy.rescan(self.root, "legacy", base, apply=True, yes=True)
        self.assertEqual(result["abstract"]["state"], "uncertain", result)
        self.assertTrue(readback_attempted)
        self.assertIsNone(result["current_revision"], result)
        self.assertEqual(result["qualified_id"], legacy.observe(self.root, "legacy")["qualified_id"])
        self.assertIn("retry", result["remedy"])
        self.assertIsNotNone(json.loads(path.read_text())["generated"])

    def test_rescan_pre_replace_failure_reports_not_committed_when_bytes_are_unchanged(self):
        legacy.review(self.root, "legacy", self._request(), apply=True, yes=True)
        path = self.root / ".flow/runs/legacy/abstract.json"
        value = json.loads(path.read_text())
        control = copy.deepcopy(value["legacy_review"])
        value["generated"] = None
        path.write_text(json.dumps(value))
        before = path.read_bytes()
        base = legacy.observe(self.root, "legacy")["fingerprint"]
        with patch.object(legacy, "write_envelope", side_effect=OSError("pre-replace write failed")):
            result = legacy.rescan(self.root, "legacy", base, apply=True, yes=True)
        self.assertEqual(result["abstract"]["state"], "not_committed", result)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(json.loads(path.read_text())["legacy_review"], control)

    def test_same_base_writers_have_one_winner(self):
        first = self._request()
        second = self._request(action_id="second")
        self.assertEqual(legacy.review(self.root, "legacy", first, apply=True, yes=True)["review_commit"], "committed")
        result = legacy.review(self.root, "legacy", second, apply=True, yes=True)
        self.assertEqual(result["review_commit"], "not_committed")
        self.assertEqual(len(legacy.observe(self.root, "legacy")["chain"]), 1)

    def test_source_edit_during_extraction_rejects_stale_consent(self):
        import archive_extract
        request = self._request()
        original = archive_extract.extract_legacy
        def extract_then_edit(*args):
            generated = original(*args)
            (self.root / ".flow/runs/legacy/closure.md").write_text("# Acceptance\nChanged\n")
            return generated
        with patch.object(archive_extract, "extract_legacy", side_effect=extract_then_edit):
            result = legacy.review(self.root, "legacy", request, apply=True, yes=True)
        self.assertEqual(result["review_commit"], "not_committed", result)
        self.assertFalse((self.root / ".flow/runs/legacy/abstract.json").exists())

    def test_reachable_history_symlink_is_rejected_without_reading_target(self):
        approval = self._request()
        legacy.review(self.root, "legacy", approval, apply=True, yes=True)
        withdrawal = self._request("withdraw", "withdraw")
        legacy.review(self.root, "legacy", withdrawal, apply=True, yes=True)
        history = next((self.root / ".flow/runs/legacy/abstract-history/reviews").glob("*.json"))
        outside = Path(self.temp.name) / "outside.json"
        outside.write_bytes(history.read_bytes())
        history.unlink()
        history.symlink_to(outside)
        result = legacy.observe(self.root, "legacy")
        self.assertFalse(result["eligible"])
        self.assertEqual(result["candidate_state"], "invalid_review")
        self.assertIn("symlink", str(result["diagnostics"]))

    def test_withdraw_with_missing_evidence_and_malformed_prose(self):
        approval = self._request()
        legacy.review(self.root, "legacy", approval, apply=True, yes=True)
        withdrawal = self._request("withdraw", "withdraw")
        path = self.root / ".flow/runs/legacy/abstract.json"
        value = json.loads(path.read_text()); value["generated"] = "malformed"
        path.write_text(json.dumps(value))
        (path.parent / "closure.md").unlink()
        withdrawal["expected_base_fingerprint"] = legacy.observe(self.root, "legacy")["fingerprint"]
        result = legacy.review(self.root, "legacy", withdrawal, apply=True, yes=True)
        self.assertEqual(result["review_commit"], "committed", result)
        self.assertEqual(result["effective_disposition"], "withdrawn")

    def test_preview_names_unreviewed_sources_and_missing_roles(self):
        result = legacy.preview(self.root, "legacy")["runs"][0]
        self.assertEqual(result["missing_evidence_roles"], ["closure_evidence", "final_outcome"])
        self.assertEqual(len(result["available_evidence"]), 2)
        self.assertTrue(all(row["status"] == "available_unreviewed_source" for row in result["available_evidence"]))

    def test_invalid_and_unavailable_operations_keep_outcome_contract(self):
        required = {"review_commit", "replayed", "action_revision", "current_revision",
                    "effective_disposition", "evidence_condition", "abstract", "index", "coverage"}
        results = [legacy.review(self.root, "legacy", {}),
                   legacy.review(self.root, "legacy", self.root / "missing.json", apply=True, yes=True),
                   legacy.rescan(self.root, "legacy", apply=True)]
        for result in results:
            self.assertTrue(required.issubset(result), result)
            self.assertFalse(result["replayed"])
            self.assertEqual(result["abstract"]["state"], "not_needed")

    def test_post_replace_unreadable_readback_never_claims_not_committed(self):
        request = self._request()
        original = legacy.atomic_write
        def publish_then_fail(path, data, root):
            original(path, data, root)
            # Simulate replacement followed by a durability error and lost read access.
            legacy.observe = lambda *args, **kwargs: (_ for _ in ()).throw(OSError("readback unavailable"))
            raise OSError("directory fsync failed")
        with patch.object(legacy, "observe", wraps=legacy.observe), patch.object(legacy, "atomic_write", side_effect=publish_then_fail):
            result = legacy.review(self.root, "legacy", request, apply=True, yes=True)
        self.assertEqual(result["review_commit"], "uncertain", result)
        self.assertIsNone(result["current_revision"])
        self.assertEqual(result["action_revision"], legacy.observe(self.root, "legacy")["review"]["revision_digest"])

    def test_excluded_rescan_reports_actual_coverage_work_and_failure(self):
        legacy.review(self.root, "legacy", self._request("unresolved"), apply=True, yes=True)
        before = (self.root / ".flow/runs/legacy/abstract.json").read_bytes()
        base = legacy.observe(self.root, "legacy")["fingerprint"]
        result = legacy.rescan(self.root, "legacy", base, apply=True, yes=True)
        self.assertEqual(result["coverage"]["state"], "completed")
        self.assertEqual(result["abstract"]["state"], "not_needed")
        with patch("archive_service.refresh_coverage", side_effect=OSError("coverage unavailable")):
            result = legacy.rescan(self.root, "legacy", base, apply=True, yes=True)
        self.assertEqual(result["state"], "unavailable")
        self.assertEqual(result["coverage"]["state"], "failed")
        self.assertIsNone(result["review_commit"])
        self.assertEqual(before, (self.root / ".flow/runs/legacy/abstract.json").read_bytes())

    def test_action_receipt_stays_distinct_from_later_observed_revision(self):
        from contextlib import contextmanager
        request = self._request()
        original_lock = legacy.writer_lock
        interleaved = False

        @contextmanager
        def release_to_competing_writer(root):
            nonlocal interleaved
            with original_lock(root):
                yield
            if not interleaved:
                interleaved = True
                withdrawal = self._request('withdraw', 'competing-withdrawal')
                self.assertEqual(legacy.review(root, 'legacy', withdrawal, apply=True, yes=True)['review_commit'], 'committed')

        with patch.object(legacy, 'writer_lock', release_to_competing_writer):
            result = legacy.review(self.root, 'legacy', request, apply=True, yes=True)
        current = legacy.observe(self.root, 'legacy')
        self.assertEqual(result['review_commit'], 'committed')
        self.assertEqual(result['action_revision'], current['chain'][0]['revision_digest'])
        self.assertEqual(result['current_revision'], current['review']['revision_digest'])
        self.assertNotEqual(result['action_revision'], result['current_revision'])
        self.assertEqual(result['effective_disposition'], 'withdrawn')

    def test_apply_rejects_semantically_changed_record_during_lock_before_replay(self):
        approval = self._request()
        record = self.root / "approval.json"
        record.write_text(json.dumps(approval))
        self.assertEqual(legacy.review(self.root, "legacy", record, apply=True, yes=True)["review_commit"], "committed")
        self.assertEqual(legacy.review(self.root, "legacy", self._request("withdraw", "withdraw"), apply=True, yes=True)["review_commit"], "committed")
        before = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        original_lock = legacy.writer_lock

        @contextmanager
        def mutate_after_lock(root):
            with original_lock(root):
                changed = dict(approval, reason="a different review rationale")
                record.write_text(json.dumps(changed))
                yield

        with patch.object(legacy, "writer_lock", mutate_after_lock):
            result = legacy.review(self.root, "legacy", record, apply=True, yes=True)
        self.assertEqual(result["review_commit"], "not_committed", result)
        self.assertEqual(result["state"], "invalid_request", result)
        before.pop(record.relative_to(self.root))
        after = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        after.pop(record.relative_to(self.root))
        self.assertEqual(before, after)

    def test_apply_permits_formatting_only_record_change_during_lock(self):
        request = self._request()
        record = self.root / "approval.json"
        record.write_text(json.dumps(request, separators=(",", ":")))
        original_lock = legacy.writer_lock

        @contextmanager
        def reformat_after_lock(root):
            with original_lock(root):
                record.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n")
                yield

        with patch.object(legacy, "writer_lock", reformat_after_lock):
            result = legacy.review(self.root, "legacy", record, apply=True, yes=True)
        self.assertEqual(result["review_commit"], "committed", result)

    def test_apply_rejects_removed_or_malformed_record_during_lock_without_publication(self):
        for replacement in [None, "{not json"]:
            with self.subTest(replacement=replacement):
                request = self._request(action_id="race-" + ("missing" if replacement is None else "malformed"))
                record = self.root / "approval.json"
                record.write_text(json.dumps(request))
                before = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
                original_lock = legacy.writer_lock

                @contextmanager
                def replace_after_lock(root):
                    with original_lock(root):
                        if replacement is None:
                            record.unlink()
                        else:
                            record.write_text(replacement)
                        yield

                with patch.object(legacy, "writer_lock", replace_after_lock):
                    result = legacy.review(self.root, "legacy", record, apply=True, yes=True)
                self.assertEqual(result["review_commit"], "not_committed", result)
                self.assertIn(result["state"], {"invalid_request", "unavailable"}, result)
                expected = dict(before)
                expected.pop(record.relative_to(self.root))
                if replacement is not None:
                    expected[record.relative_to(self.root)] = replacement.encode()
                self.assertEqual(expected, {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob("*") if path.is_file()})
