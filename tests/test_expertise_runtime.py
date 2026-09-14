"""Focused Slice 2 proofs for local expertise retrieval boundaries."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
import base64
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli"))

import expertise_admission as admission
import expertise_projection as projection
import expertise_ranker as ranker
import expertise_receipts as receipts
import expertise_runtime as runtime
import expertise_service as service
from expertise_model import ExpertiseContractError, SCHEMA_VERSION, digest, validate_admission_decision, validate_outcome


class FakeProvider:
    provider_revision = "fake-provider-v1"
    model_artifact_digest = "model-v1"
    runtime_revision = "runtime-v1"

    def __init__(self, vectors):
        self.vectors = list(vectors)
        self.calls = []

    def embed(self, texts):
        self.calls.append(list(texts))
        return list(self.vectors.pop(0))


class FakeRecordPath:
    """Minimal importlib.metadata PackagePath boundary double."""

    def __init__(self, relative: str, payload: bytes | None):
        self.parts = tuple(relative.split("/"))
        self.hash = None if payload is None else type("Hash", (), {
            "mode": "sha256",
            "value": base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).decode().rstrip("="),
        })()


class FakeDistribution:
    def __init__(self, site: Path, name: str, version: str, files: list[FakeRecordPath]):
        self.site = site
        self.metadata = {"Name": name}
        self.version = version
        self.files = files

    def locate_file(self, package_path):
        return self.site.joinpath(*package_path.parts)


class FakeResponse:
    def __init__(self, payload: bytes, final_url: str):
        self.payload = payload
        self.final_url = final_url
        self.offset = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return self.final_url

    def read(self, size: int = -1):
        if size < 0:
            size = len(self.payload) - self.offset
        result = self.payload[self.offset:self.offset + size]
        self.offset += len(result)
        return result


def entry(entry_id: str, role: str = "support-lead") -> dict:
    return {
        "@id": entry_id, "name": entry_id, "abstract": "principle", "flow:trigger": "trigger-v1",
        "flow:requiredBehavior": "act", "flow:failureMode": "failure-v1", "teaches": [],
        "audience": {"audienceType": role}, "_source_layer": "framework", "_layer": "baseline",
        "_lifecycle": {"state": "current", "owner": "flow:owner/test"}, "_entry_digest": hashlib.sha256(entry_id.encode()).hexdigest(),
        "_effective_current": True,
    }


def snapshot(entries: list[dict]) -> dict:
    return {"entries": entries, "corpus_digest": "corpus-v1", "lifecycle_revision": "lifecycle-v1", "entry_serializer_revision": "serializer-v1"}


def admission_input() -> dict:
    entry_id = "flow:entry/support-lead/a"
    return {
        "schema_version": 1, "role": "support-lead", "admission_contract_revision": "admission-v1",
        "query_view": {"normalizer_revision": "normalizer-v1", "normalized_text": "task", "tokens": ["task"], "identifiers": []},
        "task_facts": {"derivation_revision": "facts-v1", "facts": [{"code": "ready", "value": "present", "evidence_span": [0, 0]}]},
        "eligibility": {"corpus_digest": "corpus-v1", "eligibility_revision": "lifecycle-v1"},
        "ranking": {"ranker_revision": "ranker-v1", "provider_model_revision": "model-v1", "candidates": [
            {"entry_id": entry_id, "ordinal": 1, "provider_score": 0.9, "entry_digest": "a" * 64,
             "score_semantics": "cosine", "structured_exact_match": False,
             "trigger_view": "trigger-v1", "failure_mode_view": "failure-v1"},
        ]},
        "limits": {"ranked_candidate_window": 3, "maximum_admitted_ids": 1, "delivery_entry_cap": 1, "delivery_byte_cap": 256},
    }


class ProjectionAndRankingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.flow_home = Path(self.temporary.name) / "flow-home"

    def test_atomic_projection_preserves_old_index_when_snapshot_changes_before_publish(self):
        original = snapshot([entry("flow:entry/support-lead/a")])
        first = FakeProvider([[(1.0, 0.0)]])
        projection.publish(self.flow_home, original, first, verify_snapshot=lambda: "corpus-v1")
        before = projection.projection_path(self.flow_home).read_bytes()
        changed = dict(original, corpus_digest="corpus-v2")
        with self.assertRaisesRegex(projection.ExpertiseProjectionError, "changed"):
            projection.publish(self.flow_home, changed, FakeProvider([[(0.0, 1.0)]]), verify_snapshot=lambda: "other")
        self.assertEqual(projection.projection_path(self.flow_home).read_bytes(), before)
        self.assertEqual(projection.inspect(self.flow_home)["state"], "ready")
        self.assertEqual(projection.projection_path(self.flow_home).stat().st_mode & 0o777, 0o600)

    def test_exact_cosine_uses_stable_identifier_order_for_ties(self):
        records = [entry("flow:entry/support-lead/b"), entry("flow:entry/support-lead/a")]
        data = snapshot(records)
        publisher = FakeProvider([[(1.0, 0.0), (1.0, 0.0)]])
        published = projection.publish(self.flow_home, data, publisher)
        result = ranker.rank(self.flow_home, "support-lead", "task", FakeProvider([[(1.0, 0.0)]]),
                             published["projection_identity"]["digest"], window=2)
        self.assertEqual([row["entry_id"] for row in result["candidates"]], [
            "flow:entry/support-lead/a", "flow:entry/support-lead/b",
        ])
        self.assertEqual([row["ordinal"] for row in result["candidates"]], [1, 2])


class AdmissionStrategyTests(unittest.TestCase):
    def test_similarity_and_trigger_strategies_use_the_same_ordered_window(self):
        value = admission_input()
        similarity = admission.SimilarityStrategy(0.8).decide(value, "admission-v1")
        self.assertEqual(similarity["admitted_ids"], ["flow:entry/support-lead/a"])
        rule = {"schema_version": 1, "entry_id": "flow:entry/support-lead/a", "entry_digest": "a" * 64,
                "trigger_digest": digest("trigger-v1"), "failure_mode_digest": digest("failure-v1"),
                "revision": "rule-v1", "unknown_policy": "reject",
                "clauses": [{"fact": "ready", "operator": "is", "value": "present"}]}
        rule["digest"] = digest(rule)
        triggered = admission.TriggerRuleStrategy({rule["entry_id"]: rule}).decide(value, "admission-v1")
        self.assertEqual(triggered["admitted_ids"], similarity["admitted_ids"])

    def test_missing_trigger_coverage_is_a_gate_failure_not_a_fallback(self):
        with self.assertRaisesRegex(admission.ExpertiseAdmissionError, "rule_coverage_missing"):
            admission.TriggerRuleStrategy({}).decide(admission_input(), "admission-v1")

    def test_candidate_decision_flags_must_agree_with_the_admitted_list(self):
        candidate = admission_input()["ranking"]["candidates"][0]["entry_id"]
        malformed = {
            "schema_version": SCHEMA_VERSION, "state": "admitted", "strategy": "test-gate",
            "admitted_ids": [candidate],
            "candidate_decisions": [{"entry_id": candidate, "admitted": False,
                                     "reason": "similarity_threshold_met", "evidence_codes": []}],
            "identity": "admission-v1",
        }
        with self.assertRaisesRegex(ExpertiseContractError, "flags disagree"):
            validate_admission_decision(malformed, [candidate])


class ServiceFailureNormalizationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.flow_home = Path(self.temporary.name) / "flow-home"
        self.current = entry("flow:entry/support-lead/a")
        self.snapshot = {
            "entries": [self.current], "corpus_digest": "corpus-v1",
            "lifecycle_revision": "lifecycle-v1", "entry_serializer_revision": "serializer-v1",
        }
        self.provider = FakeProvider([])

    def _execute(self, strategy):
        ranked = {
            "schema_version": 1, "state": "ranked", "reason": "ranked", "provider_calls": 1,
            "identity": "projection-v1", "candidates": [{
                "entry_id": self.current["@id"], "ordinal": 1, "provider_score": 0.9,
                "entry_digest": self.current["_entry_digest"], "score_semantics": "cosine",
                "structured_exact_match": False,
            }],
        }
        definitions = {"schema_version": 1, "revision": "facts-v1", "normalizer_revision": "normalizer-v1",
                       "facts": [{"code": "ready", "present_any": ["ready"], "absent_any": []}]}
        with patch.object(service, "canonical_snapshot", return_value=self.snapshot), patch.object(service, "rank", return_value=ranked):
            return service.execute(
                "support-lead", "ready", framework_dir=self.flow_home, user_dir=None,
                flow_home=self.flow_home, provider=self.provider, strategy=strategy,
                strategy_config={}, fact_definitions=definitions, request_id="request-1",
            )

    def test_malformed_strategy_output_becomes_invalid_gate_output_without_fallback(self):
        class MalformedStrategy:
            revision = "malformed-test-v1"

            def decide(self, _input, identity_digest):
                return {
                    "schema_version": 1, "state": "admitted", "strategy": self.revision,
                    "admitted_ids": [], "candidate_decisions": [], "identity": identity_digest,
                }

        outcome = self._execute(MalformedStrategy())
        self.assertEqual((outcome["state"], outcome["cause"]), ("unavailable", "invalid_gate_output"))
        self.assertEqual(outcome["admission"]["state"], "invalid_gate_output")
        self.assertEqual(outcome["delivery"]["state"], "not_run")

    def test_outer_cause_must_match_the_attributed_degraded_stage(self):
        class UnavailableStrategy:
            revision = "unavailable-test-v1"

            def decide(self, _input, _identity_digest):
                raise admission.ExpertiseAdmissionError("rule_coverage_missing")

        outcome = self._execute(UnavailableStrategy())
        self.assertEqual((outcome["state"], outcome["cause"], outcome["admission"]["state"]),
                         ("unavailable", "gate_unavailable", "gate_unavailable"))
        mismatched = {key: value for key, value in outcome.items() if key != "elapsed_ms"}
        mismatched["cause"] = "invalid_gate_output"
        with self.assertRaisesRegex(ExpertiseContractError, "stage evidence"):
            validate_outcome(mismatched)


class ReceiptAndRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def receipt_outcome(self):
        return {"request_id": "request-1", "role": "support-lead", "state": "no_match", "cause": "no_eligible_entries",
                "eligibility": {"state": "empty", "identity": "eligibility-v1", "eligible_ids": [], "excluded": []},
                "ranking": {"state": "not_run", "reason": "not_run_empty_eligibility", "provider_calls": 0, "identity": "ranking-v1", "candidates": []},
                "admission": {"state": "not_run", "strategy": "not-run", "admitted_ids": [], "candidate_decisions": [], "identity": "admission-v1"},
                "delivery": {"state": "not_run", "reason": "not_run", "delivered_ids": [], "withheld_ids": [], "actual_bytes": 0,
                             "limits": {"delivery_entry_cap": 1, "delivery_byte_cap": 256}, "identity": "delivery-v1"}}

    def test_receipts_are_private_immutable_and_purge_expired_records(self):
        root = self.root / "receipts"
        flow_home = self.root / "flow-home"
        pre = receipts.write_pre(root, flow_home, self.receipt_outcome(), "unique private task fact")
        path = Path(pre["path"])
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("unique private task fact", path.read_text())
        with self.assertRaisesRegex(receipts.ExpertiseReceiptError, "immutable"):
            receipts.write_pre(root, flow_home, self.receipt_outcome(), "unique private task fact")
        post = receipts.write_post(root, {"schema_version": 1, "state": "observed", "request_id": "request-1",
                                          "pre_receipt_digest": pre["digest"], "identity": "disposition-v1", "entries": []}, [])
        self.assertIn("created_at", post["receipt"])
        inspected = receipts.inspect_receipts(root)
        self.assertNotIn("query_hmac", json.dumps(inspected))
        old = json.loads(path.read_text())
        old["created_at"] = "2020-01-01T00:00:00Z"
        path.write_text(json.dumps(old))
        purged = receipts.purge(root, now=datetime.now(timezone.utc), days=30)
        self.assertEqual(purged["deleted"], 1)

    def test_symlinked_receipt_root_and_ancestor_fail_before_private_writes(self):
        outside = self.root / "outside"
        outside.mkdir()
        flow_home = self.root / "flow-home"
        root_link = self.root / "receipts-link"
        root_link.symlink_to(outside, target_is_directory=True)
        parent_link = self.root / "linked-parent"
        parent_link.symlink_to(outside, target_is_directory=True)
        for root in (root_link, parent_link / "receipts"):
            with self.subTest(root=root):
                with self.assertRaises(receipts.ExpertiseReceiptError):
                    receipts.write_pre(root, flow_home, self.receipt_outcome(), "private sentinel")
                with self.assertRaises(receipts.ExpertiseReceiptError):
                    receipts.write_post(root, {"request_id": "request-1"}, [])
                with self.assertRaises(receipts.ExpertiseReceiptError):
                    receipts.inspect_receipts(root)
                with self.assertRaises(receipts.ExpertiseReceiptError):
                    receipts.purge(root)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((flow_home / "cache" / "expertise" / "receipt.key").exists())

    def test_symlinked_runtime_cache_and_ancestor_fail_before_install_or_chmod(self):
        outside = self.root / "outside-runtime"
        outside.mkdir()
        supported = next(iter(json.loads(runtime.runtime_lock_path().read_text())["environments"]))
        with patch.object(runtime, "current_environment_id", return_value=supported):
            for ancestor in (False, True):
                with self.subTest(ancestor=ancestor):
                    flow_home = self.root / ("runtime-ancestor" if ancestor else "runtime-root")
                    flow_home.mkdir()
                    if ancestor:
                        (flow_home / "cache").symlink_to(outside, target_is_directory=True)
                    else:
                        (flow_home / "cache").mkdir()
                        (flow_home / "cache" / "expertise").symlink_to(outside, target_is_directory=True)
                    readiness = runtime.status(flow_home)
                    self.assertEqual(readiness["state"], "unavailable")
                    self.assertEqual(readiness["reason"], "unsafe_permissions")
                    with self.assertRaises(runtime.ExpertiseRuntimeError) as raised:
                        runtime.install(flow_home, accept_license=True)
                    self.assertEqual(raised.exception.reason, "unsafe_permissions")
                    with self.assertRaises(projection.ExpertiseProjectionError):
                        with projection.writer_lock(flow_home):
                            pass
        self.assertEqual(list(outside.iterdir()), [])

    def test_runtime_status_verifies_local_fake_artifacts_and_normalizes_x64(self):
        artifact = b"fake model"
        artifact_hash = hashlib.sha256(artifact).hexdigest()
        model = {"schema_version": 1, "model": {"files": [{"path": "model.bin", "bytes": len(artifact), "sha256": artifact_hash}], "revision": "fake"},
                 "provider": {"revision": "fake-provider"}}
        environment = {"requirements": []}
        lock = {"schema_version": 1, "environments": {"ubuntu-24.04-x64-python-3.12.13": environment}}
        environment_id = "ubuntu-24.04-x64-python-3.12.13"
        flow_home = self.root / "runtime-home"
        with patch.object(runtime, "current_environment_id", return_value=environment_id), patch.object(runtime, "_load_contracts", return_value=(model, lock, environment)):
            target = runtime.install_root(flow_home, environment_id, digest(model["model"]), digest(environment))
            (target / "model").mkdir(parents=True)
            (target / "site").mkdir()
            (target / "model" / "model.bin").write_bytes(artifact)
            receipt = {"schema_version": 1, "environment_id": environment_id, "model_manifest_digest": digest(model),
                       "model_artifact_digest": digest(model["model"]), "runtime_lock_digest": digest(lock),
                       "runtime_revision": digest(environment), "provider_revision": "fake-provider", "license_accepted": True}
            (target / "install.json").write_text(json.dumps(receipt))
            active = projection.cache_root(flow_home) / "active.json"
            active.parent.mkdir(parents=True, exist_ok=True)
            active.write_text(json.dumps({"schema_version": 1, "install": target.name}))
            for directory in (projection.cache_root(flow_home), target.parent, target, target / "model", target / "site"):
                os.chmod(directory, 0o700)
            for path in (target / "model" / "model.bin", target / "install.json", active):
                os.chmod(path, 0o600)
            self.assertEqual(runtime.status(flow_home), {"state": "ready", "environment_id": environment_id,
                                                         "provider_revision": "fake-provider",
                                                         "model_artifact_digest": digest(model["model"]),
                                                         "runtime_revision": digest(environment),
                                                         "install": str(target.resolve()), "persistent_bytes": len(artifact) + (target / "install.json").stat().st_size})
        with patch.object(runtime.platform, "system", return_value="Linux"), patch.object(runtime.platform, "machine", return_value="x86_64"), patch.object(runtime.platform, "python_version", return_value="3.12.13"), patch.object(Path, "read_text", return_value='ID=ubuntu\nVERSION_ID="24.04"\n'):
            self.assertEqual(runtime.current_environment_id(), "ubuntu-24.04-x64-python-3.12.13")


class RuntimeArtifactQualificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def _artifact(self, *, filename: bool, path: str, url: str = "https://files.pythonhosted.org/file.whl"):
        return {
            "filename" if filename else "path": path,
            "bytes": 1,
            "sha256": "a" * 64,
            "url" if filename else "download_url": url,
        }

    def _verify_site(self, files: list[FakeRecordPath], *, extra: bool = False, scripts: bool = False):
        site = self.root / "site"
        site.mkdir()
        for item in files:
            destination = site.joinpath(*item.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"package")
        if extra:
            (site / "untracked.py").write_text("unexpected")
        if scripts:
            (site / "bin").mkdir()
            (site / "bin" / "generated").write_text("script")
        environment = {"requirements": [{"name": "demo", "version": "1.0"}]}
        return site, environment

    def test_model_and_wheel_artifact_paths_reject_absolute_and_parent_traversal(self):
        for filename, path in ((False, "/absolute-model.onnx"), (False, "../model.onnx"),
                               (True, "/absolute-wheel.whl"), (True, "../wheel.whl")):
            with self.subTest(filename=filename, path=path), self.assertRaises(runtime.ExpertiseRuntimeError) as raised:
                runtime._pinned_artifact(self._artifact(filename=filename, path=path), "artifact", filename=filename)
            self.assertEqual(raised.exception.reason, "manifest_invalid")

    def test_unapproved_initial_and_redirect_hosts_are_rejected_before_artifact_write(self):
        target = self.root / "artifact"
        with self.assertRaises(runtime.ExpertiseRuntimeError) as raised:
            runtime._download("https://example.invalid/artifact", target, "a" * 64, 1)
        self.assertEqual(raised.exception.reason, "manifest_invalid")
        self.assertFalse(target.exists())
        response = FakeResponse(b"x", "https://example.invalid/redirect")
        with patch.object(runtime, "urlopen", return_value=response), self.assertRaises(runtime.ExpertiseRuntimeError) as raised:
            runtime._download("https://huggingface.co/allowed", target, hashlib.sha256(b"x").hexdigest(), 1)
        self.assertEqual(raised.exception.reason, "network_install_failed")

    def test_oversize_stream_is_rejected_even_when_prefix_matches(self):
        target = self.root / "oversize"
        response = FakeResponse(b"abcX", "https://huggingface.co/allowed")
        with patch.object(runtime, "urlopen", return_value=response), self.assertRaises(runtime.ExpertiseRuntimeError) as raised:
            runtime._download("https://huggingface.co/allowed", target, hashlib.sha256(b"abc").hexdigest(), 3)
        self.assertEqual(raised.exception.reason, "artifact_too_large")

    def test_site_rejects_bad_record_hash_extra_files_and_console_scripts(self):
        for kind in ("bad-hash", "extra", "scripts"):
            with self.subTest(kind=kind):
                with tempfile.TemporaryDirectory() as temporary:
                    self.root = Path(temporary)
                    record = FakeRecordPath("demo.py", b"wrong" if kind == "bad-hash" else b"package")
                    site, environment = self._verify_site([record], extra=kind == "extra", scripts=kind == "scripts")
                    distribution = FakeDistribution(site, "demo", "1.0", [record])
                    expected = "hash_mismatch" if kind == "bad-hash" else "corrupt_artifact"
                    with patch.object(runtime.metadata, "distributions", return_value=[distribution]), self.assertRaises(runtime.ExpertiseRuntimeError) as raised:
                        runtime._verify_site(site, environment, self.root / "wheels")
                    self.assertEqual(raised.exception.reason, expected)

    def test_site_rejects_package_and_record_changed_together_against_pinned_wheel(self):
        site = self.root / "site"
        site.mkdir()
        installed = site / "demo.py"
        installed.write_bytes(b"original")
        wheels = self.root / "wheels"
        wheels.mkdir()
        wheel = wheels / "demo-1.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr("demo.py", b"original")
        environment = {"requirements": [{
            "name": "demo", "version": "1.0", "filename": wheel.name,
            "bytes": wheel.stat().st_size, "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        }]}
        original = FakeDistribution(site, "demo", "1.0", [FakeRecordPath("demo.py", b"original")])
        with patch.object(runtime.metadata, "distributions", return_value=[original]):
            runtime._verify_site(site, environment, wheels)

        installed.write_bytes(b"tampered")
        changed_record = FakeDistribution(site, "demo", "1.0", [FakeRecordPath("demo.py", b"tampered")])
        with patch.object(runtime.metadata, "distributions", return_value=[changed_record]), self.assertRaises(runtime.ExpertiseRuntimeError) as raised:
            runtime._verify_site(site, environment, wheels)
        self.assertEqual(raised.exception.reason, "hash_mismatch")

        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr("demo.py", b"tampered")
        with patch.object(runtime.metadata, "distributions", return_value=[changed_record]), self.assertRaises(runtime.ExpertiseRuntimeError) as raised:
            runtime._verify_site(site, environment, wheels)
        self.assertEqual(raised.exception.reason, "hash_mismatch")

    def test_real_metadata_record_cannot_authorize_changed_package_bytes(self):
        """Exercise importlib's actual RECORD parser against a pinned wheel."""
        site = self.root / "site"
        wheels = self.root / "wheels"
        site.mkdir()
        wheels.mkdir()
        dist_info = "demo-1.0.dist-info"
        original = {
            "demo.py": b"VALUE = 'original'\n",
            f"{dist_info}/METADATA": b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0\n",
            f"{dist_info}/WHEEL": b"Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        }
        wheel = wheels / "demo-1.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            for name, payload in original.items():
                archive.writestr(name, payload)
            archive.writestr(f"{dist_info}/RECORD", b"")
        installed = dict(original)
        installed.update({f"{dist_info}/{name}": b"" for name in ("INSTALLER", "REQUESTED", "direct_url.json")})

        def write_site() -> None:
            for name, payload in installed.items():
                destination = site / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(payload)
            rows = []
            for name, payload in installed.items():
                encoded = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).decode().rstrip("=")
                rows.append(f"{name},sha256={encoded},{len(payload)}")
            rows.append(f"{dist_info}/RECORD,,")
            (site / dist_info / "RECORD").write_text("\n".join(rows) + "\n")

        environment = {"requirements": [{
            "name": "demo", "version": "1.0", "filename": wheel.name,
            "bytes": wheel.stat().st_size, "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        }]}
        write_site()
        runtime._verify_site(site, environment, wheels)
        installed["demo.py"] = b"VALUE = 'tampered'\n"
        write_site()
        with self.assertRaises(runtime.ExpertiseRuntimeError) as raised:
            runtime._verify_site(site, environment, wheels)
        self.assertEqual(raised.exception.reason, "hash_mismatch")

    def test_provider_import_from_read_only_site_creates_no_bytecode(self):
        site = self.root / "site"
        module = site / "fastembed" / "text" / "onnx_embedding.py"
        module.parent.mkdir(parents=True)
        (site / "fastembed" / "__init__.py").write_text("")
        (site / "fastembed" / "text" / "__init__.py").write_text("")
        module.write_text("class OnnxTextEmbedding:\n    def __init__(self, **_kwargs): pass\n    def embed(self, texts): return [(1.0, 0.0) for _ in texts]\n")
        for directory in (site, site / "fastembed", site / "fastembed" / "text"):
            os.chmod(directory, 0o555)
        for path in (site / "fastembed" / "__init__.py", site / "fastembed" / "text" / "__init__.py", module):
            os.chmod(path, 0o444)
        provider = ranker.FastEmbedProvider(site, self.root, "model-v1", "runtime-v1")
        original_path = list(sys.path)
        try:
            for name in tuple(sys.modules):
                if name == "fastembed" or name.startswith("fastembed."):
                    del sys.modules[name]
            self.assertEqual(provider.embed(["task"]), [(1.0, 0.0)])
            self.assertFalse(any(path.name == "__pycache__" for path in site.rglob("__pycache__")))
        finally:
            sys.path[:] = original_path
            for name in tuple(sys.modules):
                if name == "fastembed" or name.startswith("fastembed."):
                    del sys.modules[name]


if __name__ == "__main__":
    unittest.main()
