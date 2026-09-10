"""Composition of role expertise corpora into generated agent bodies."""
import hashlib
import json
import re
import sys
import tempfile
import tomllib
import unittest
from unittest import mock
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(REPO_ROOT / "cli"))
import expertise  # noqa: E402
import sync  # noqa: E402

SCAFFOLD = REPO_ROOT / "scaffolds" / "default"
RUN = REPO_ROOT / ".flow" / "runs" / "role-method-differentiation-repair-3"
COMPOSED_ROLES = (
    "architect", "business-analyst", "lead-developer", "sre", "support-lead",
    "test-engineer",
)
ADDED_ROLES = ("architect", "lead-developer", "test-engineer")
INACTIVE_BASE_ROLES = ("product-manager", "quality-reviewer")
BASE_ROLE_HASHES = {
    "product-manager": "db45fab8ca7a50d78d25f149f560f4076bc86002ce5627960da274c71dd3d54b",
    "quality-reviewer": "4cd2d84d7500bc240bafb5c79f7f3cf8cff738195b870aad5ed4acbe0eea3592",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def entry(name, layer="baseline", **overrides):
    base = {
        "@id": f"flow:entry/test/{name}",
        "@type": "LearningResource",
        "name": name,
        "flow:layer": layer,
        "abstract": "a durable idea.",
        "flow:trigger": "the trigger holds.",
        "flow:requiredBehavior": "do the thing.",
        "flow:failureMode": "the failure.",
    }
    base.update(overrides)
    return base


def write_corpus(directory: Path, role: str, entries: list) -> Path:
    target = directory / "expertise"
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{role}.jsonld"
    path.write_text(json.dumps({"@context": {}, "@graph": entries}) + "\n")
    return path


class ShippedCorpusTests(unittest.TestCase):

    def test_inactive_roles_match_frozen_base_and_have_no_composed_surface(self):
        manifest = tomllib.loads((SCAFFOLD / "flow.toml").read_text())
        agents = {agent["name"]: agent for agent in manifest["agents"]}
        with mock.patch.object(sync, "USER_OVERLAY_DIR", SCAFFOLD / "no-user-overlay"):
            for role in INACTIVE_BASE_ROLES:
                with self.subTest(role=role):
                    body_path = SCAFFOLD / "agents" / f"{role}.md"
                    self.assertEqual(sha256(body_path), BASE_ROLE_HASHES[role])
                    self.assertIn(role, agents)
                    self.assertNotEqual(agents[role].get("generation_mode"), "composed")
                    self.assertFalse((SCAFFOLD / "expertise" / f"{role}.jsonld").exists())
                    self.assertEqual(expertise.corpus_for(role, SCAFFOLD, None), [])
                    rendered = sync.agent_body(agents[role], SCAFFOLD, SCAFFOLD, {})
                    self.assertNotIn(expertise.SECTION, rendered)

    def test_retained_role_and_corpus_hashes_match_the_start_receipt(self):
        receipt = json.loads((RUN / "evidence" / "start-receipt.json").read_text())
        expected_paths = {
            f"scaffolds/default/{kind}/{role}.{suffix}"
            for role in ADDED_ROLES
            for kind, suffix in (("agents", "md"), ("expertise", "jsonld"))
        }
        self.assertEqual(set(receipt["files"]), expected_paths)
        for relative, expected in receipt["files"].items():
            with self.subTest(path=relative):
                self.assertEqual(sha256(REPO_ROOT / relative), expected)

    def test_release_evidence_map_is_exact_and_complete(self):
        evidence_map = json.loads(
            (RUN / "evidence" / "release-evidence-map.json").read_text()
        )
        roles = {item["role"]: item for item in evidence_map["roles"]}
        self.assertEqual(set(roles), set(ADDED_ROLES))
        for role, item in roles.items():
            with self.subTest(role=role):
                self.assertEqual(item["gate_result"], "pass")
                self.assertEqual(sha256(REPO_ROOT / item["role_body"]["path"]),
                                 item["role_body"]["sha256"])
                self.assertEqual(sha256(REPO_ROOT / item["corpus"]["path"]),
                                 item["corpus"]["sha256"])
                graph = json.loads(
                    (REPO_ROOT / item["corpus"]["path"]).read_text()
                )["@graph"]
                self.assertEqual(
                    {entry["@id"] for entry in graph}, set(item["entry_ids"])
                )
                self.assertEqual(sha256(REPO_ROOT / item["result"]["path"]),
                                 item["result"]["sha256"])
                self.assertEqual(
                    set(item["records"]),
                    {"control_primary", "treatment_primary", "control_counter",
                     "treatment_counter"},
                )
                for record_path, expected in item["records"].values():
                    self.assertEqual(sha256(REPO_ROOT / record_path), expected)

    def test_competency_vocabulary_has_exact_release_coverage(self):
        text = (SCAFFOLD / "expertise" / "competencies.md").read_text()
        terms = re.findall(r"(?m)^### (.+)$", text)
        taught_blocks = re.findall(
            r"(?ms)^- Taught by: (.*?)(?:\n\n|\Z)", text
        )
        edges = sum(len(re.findall(r'"[^"]+"', block)) for block in taught_blocks)
        self.assertEqual(len(terms), 16)
        self.assertEqual(edges, 21)
        self.assertNotIn("Roles: product-manager", text)
        self.assertNotIn("Roles: quality-reviewer", text)

    def test_lead_developer_obligation_is_positive_and_uses_short_form(self):
        body = (SCAFFOLD / "agents" / "lead-developer.md").read_text()
        self.assertRegex(
            body,
            r"(?m)^First classify reversibility, blast radius, and existing test coverage\.",
        )
        self.assertNotRegex(
            body,
            r"(?im)^(?:do not|never)\s+first classify reversibility, blast radius",
        )
        self.assertIn("### Short form", body)
        self.assertIn("Full-plan sections omitted: atomic, local, reversible, covered change.", body)

    def test_current_documents_describe_the_bounded_release(self):
        paths = (
            REPO_ROOT / "docs" / "architecture.md",
            REPO_ROOT / "docs" / "file-structure.md",
            REPO_ROOT / "docs" / "evidence" / "three-role-expertise-expansion" / "README.md",
        )
        for path in paths:
            self.assertTrue(path.is_file(), path)
        current = "\n".join(path.read_text() for path in paths)
        self.assertIn("exactly six roles", current)
        self.assertIn("architect", current)
        self.assertIn("lead-developer", current)
        self.assertIn("test-engineer", current)
        self.assertNotIn("eight roles", current.lower())

    def test_manifest_marks_exactly_the_shipped_roles_composed(self):
        manifest = tomllib.loads((SCAFFOLD / "flow.toml").read_text())
        configured = {
            agent["name"] for agent in manifest["agents"]
            if agent.get("generation_mode") == "composed"
        }
        self.assertEqual(configured, set(COMPOSED_ROLES))

    def test_every_composed_role_has_a_corpus(self):
        for role in COMPOSED_ROLES:
            with self.subTest(role=role):
                self.assertTrue((SCAFFOLD / "expertise" / f"{role}.jsonld").exists())

    def test_composed_roles_no_longer_author_the_section_by_hand(self):
        """The section is generated. Leaving a hand-authored copy behind would
        make the agent carry two, and compose() refuses rather than picking."""
        for role in COMPOSED_ROLES:
            with self.subTest(role=role):
                body = (SCAFFOLD / "agents" / f"{role}.md").read_text()
                self.assertNotIn(expertise.SECTION, body)

    def test_every_shipped_entry_carries_all_five_parts_and_a_source(self):
        for role in COMPOSED_ROLES:
            for item in expertise.corpus_for(role, SCAFFOLD, None):
                with self.subTest(role=role, entry=item["name"]):
                    self.assertTrue(item.get("flow:source"))
                    rendered = "\n".join(expertise.render_entry(item))
                    for label in ("Source", "Principle", "Use when", "Required behavior", "Avoid"):
                        self.assertIn(f"- {label}:", rendered)

    def test_shipped_entries_teach_a_named_competency(self):
        for role in COMPOSED_ROLES:
            for item in expertise.corpus_for(role, SCAFFOLD, None):
                with self.subTest(role=role, entry=item["name"]):
                    names = [t.get("name") for t in item.get("teaches") or []]
                    self.assertTrue(names and all(names))

    def test_shipped_entries_belong_to_their_role_and_have_unique_ids(self):
        ids = set()
        for role in COMPOSED_ROLES:
            for item in expertise.corpus_for(role, SCAFFOLD, None):
                with self.subTest(role=role, entry=item["name"]):
                    self.assertEqual(item.get("@type"), "LearningResource")
                    self.assertEqual(item.get("audience", {}).get("@type"), "Audience")
                    self.assertEqual(item.get("audience", {}).get("audienceType"), role)
                    self.assertTrue(item.get("@id", "").startswith(f"flow:entry/{role}/"))
                    self.assertNotIn(item.get("@id"), ids)
                    ids.add(item.get("@id"))

    def test_each_composed_role_renders_one_expertise_section_from_its_corpus(self):
        """Prove the manifest opt-in reaches the shared agent-body renderer.

        Corpus files alone do not prove either runtime will consume them. This
        exercises the common body that Claude and Codex render from, while
        avoiding a user's experience overlay in the candidate proof.
        """
        manifest = tomllib.loads((SCAFFOLD / "flow.toml").read_text())
        agents = {agent["name"]: agent for agent in manifest["agents"]}
        with mock.patch.object(sync, "USER_OVERLAY_DIR", SCAFFOLD / "no-user-overlay"):
            for role in COMPOSED_ROLES:
                with self.subTest(role=role):
                    rendered = sync.agent_body(agents[role], SCAFFOLD, SCAFFOLD, {})
                    self.assertEqual(rendered.count(expertise.SECTION), 1)
                    for item in expertise.corpus_for(role, SCAFFOLD, None):
                        self.assertIn(f"### {item['name']}", rendered)

    def test_no_role_repeats_the_same_sourced_required_behavior(self):
        seen = {}
        for role in COMPOSED_ROLES:
            for item in expertise.corpus_for(role, SCAFFOLD, None):
                behavior = re.sub(r"\s+", " ", item["flow:requiredBehavior"].strip().lower())
                for source in item.get("flow:source", []):
                    citation = source.get("citation", {})
                    key = (citation.get("@id"), source.get("flow:locator", ""), behavior)
                    with self.subTest(role=role, entry=item["name"]):
                        self.assertNotIn(key, seen, f"also used by {seen.get(key)}")
                        seen[key] = role


class PlacementTests(unittest.TestCase):
    BODY = "# Role\n\n## Rules\n\n- be careful\n\n## Composition\n\nafter\n"

    def test_section_lands_before_composition(self):
        composed = expertise.compose(self.BODY, [entry("E")])
        self.assertLess(composed.index(expertise.SECTION), composed.index("## Composition"))
        self.assertIn("- be careful", composed)
        self.assertTrue(composed.rstrip().endswith("after"))

    def test_body_without_composition_heading_gets_the_section_appended(self):
        composed = expertise.compose("# Role\n\n## Rules\n\n- only\n", [entry("E")])
        self.assertTrue(composed.rstrip().endswith('- Avoid: the failure.'))

    def test_empty_corpus_leaves_the_body_untouched(self):
        self.assertEqual(expertise.compose(self.BODY, []), self.BODY)

    def test_a_body_that_already_has_a_section_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            expertise.compose("## Expertise\n\nhand written\n", [entry("E")])
        self.assertEqual(caught.exception.rule, "duplicate-expertise-section")


class LayerTests(unittest.TestCase):
    def test_experience_entries_precede_baseline_without_suppressing_it(self):
        """Union, not replacement. The `[[agents]]` overlay replaces by name;
        doing that to a corpus would drop baseline entries silently."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            framework, user = root / "fw", root / "user"
            write_corpus(framework, "sre", [entry("Baseline one"), entry("Shared name")])
            write_corpus(user, "sre", [entry("Shared name", layer="experience")])
            merged = expertise.corpus_for("sre", framework, user)
            self.assertEqual([e["name"] for e in merged],
                             ["Shared name", "Baseline one", "Shared name"])
            self.assertEqual([e["_layer"] for e in merged],
                             ["experience", "baseline", "baseline"])

    def test_experience_entries_are_attributed_in_the_rendered_output(self):
        rendered = "\n".join(expertise.render_entry(dict(entry("E"), _layer="experience")))
        self.assertIn("- Layer: experience", rendered)

    def test_baseline_entries_carry_no_layer_line(self):
        rendered = "\n".join(expertise.render_entry(dict(entry("E"), _layer="baseline")))
        self.assertNotIn("- Layer:", rendered)

    def test_absent_user_overlay_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            write_corpus(root / "fw", "sre", [entry("Only")])
            self.assertEqual(len(expertise.corpus_for("sre", root / "fw", root / "nope")), 1)

    def test_role_with_no_corpus_composes_nothing(self):
        with tempfile.TemporaryDirectory() as raw:
            self.assertEqual(expertise.corpus_for("architect", Path(raw), None), [])


class MalformedCorpusTests(unittest.TestCase):
    """A corpus that cannot be read fails the sync. Skipping it would ship an
    agent quietly missing its expertise — the one failure the composed file
    cannot show on its face."""

    def _error(self, payload: str):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "expertise"
            path.mkdir()
            (path / "sre.jsonld").write_text(payload)
            with self.assertRaises(ValueError) as caught:
                expertise.corpus_for("sre", Path(raw), None)
            return caught.exception

    def test_invalid_json_is_named_and_remediated(self):
        error = self._error("{not json")
        self.assertEqual(error.rule, "invalid-expertise-json")
        self.assertTrue(error.remediation)

    def test_missing_graph_is_refused(self):
        self.assertEqual(self._error('{"@context": {}}').rule, "missing-expertise-graph")

    def test_non_object_member_is_refused(self):
        self.assertEqual(self._error('{"@graph": ["oops"]}').rule, "invalid-expertise-entry")

    def test_entry_missing_a_required_part_is_refused(self):
        payload = json.dumps({"@graph": [{"name": "Half", "abstract": "only this"}]})
        error = self._error(payload)
        self.assertEqual(error.rule, "incomplete-expertise-entry")
        self.assertIn("Half", str(error))


class CitationTests(unittest.TestCase):
    def test_article_and_book_titles_are_typeset_differently(self):
        article = expertise._cite({"citation": {
            "@type": "Article", "author": "Gary Klein", "name": "Performing a Project Premortem",
            "isPartOf": "Harvard Business Review", "datePublished": "2007"}})
        self.assertEqual(article, 'Klein, "Performing a Project Premortem" (*Harvard Business Review*, 2007)')
        book = expertise._cite({"citation": {
            "@type": "Book", "author": "Rob Fitzpatrick", "name": "The Mom Test",
            "datePublished": "2013"}, "flow:locator": "chapter 1"})
        self.assertEqual(book, "Fitzpatrick, *The Mom Test* (2013) — chapter 1")

    def test_one_work_carries_a_different_locator_per_entry(self):
        """The reason ADR 0008 puts the locator on the entry: sre cites Cook at
        three different theses, so a locator on the work cannot represent it."""
        cook = [
            source.get("flow:locator")
            for item in expertise.corpus_for("sre", SCAFFOLD, None)
            for source in item.get("flow:source", [])
            if "cook" in source.get("citation", {}).get("@id", "")
        ]
        self.assertEqual(len(cook), len(set(cook)))
        self.assertGreater(len(cook), 1)

    def test_compound_sources_render_as_one_line(self):
        line = expertise._source_line({"flow:source": [
            {"citation": {"@type": "Book", "author": "R Cook", "name": "How Complex Systems Fail"},
             "flow:locator": "thesis 8"},
            {"citation": {"@type": "Article", "author": "J Allspaw", "name": "Blameless PostMortems"}},
        ]})
        self.assertEqual(line, 'Cook, *How Complex Systems Fail* — thesis 8; Allspaw, "Blameless PostMortems".')


def write_vocabulary(directory: Path, terms: dict) -> Path:
    target = directory / "expertise"
    target.mkdir(parents=True, exist_ok=True)
    path = target / "competencies.md"
    blocks = ["# Competencies", ""]
    for name, taught in terms.items():
        blocks += [f"### {name}", "", "A definition.", ""]
        listed = "; ".join(f'"{title}"' for title in taught)
        blocks += [f"- Taught by: {listed}" if taught else "- Taught by:", ""]
    path.write_text("\n".join(blocks))
    return path


def teaching(name, term_name, term_id=None):
    return entry(name, teaches=[{
        "@type": "DefinedTerm",
        "@id": term_id or "flow:competency/" + expertise._slug(term_name),
        "name": term_name,
    }])


class TeachesJoinTests(unittest.TestCase):
    """A `teaches` edge that resolves to nothing renders a competency the
    vocabulary does not define. Caught at load, so sync fails rather than
    shipping the dangling edge."""

    def _corpus(self, entries, terms):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name)
        write_corpus(root / "fw", "sre", entries)
        write_vocabulary(root / "fw", terms)
        return expertise.corpus_for("sre", root / "fw", root / "user")

    def test_a_resolvable_edge_loads(self):
        loaded = self._corpus([teaching("E", "Ask non-leading questions")],
                              {"Ask non-leading questions": ["E"]})
        self.assertEqual(len(loaded), 1)

    def test_unknown_term_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            self._corpus([teaching("E", "No such term")], {"Ask non-leading questions": ["E"]})
        self.assertEqual(caught.exception.rule, "unknown-competency")
        self.assertIn("no-such-term", str(caught.exception))

    def test_unqualified_reference_is_refused(self):
        bad = entry("E", teaches=[{"@type": "DefinedTerm", "@id": "ask-non-leading-questions"}])
        with self.assertRaises(ValueError) as caught:
            self._corpus([bad], {"Ask non-leading questions": ["E"]})
        self.assertEqual(caught.exception.rule, "unqualified-competency-reference")
        self.assertTrue(caught.exception.source)
        self.assertIn("reference the term", caught.exception.remediation)

    def test_stale_term_name_is_refused(self):
        """The id resolves but the wording does not: a renamed term leaves the
        entry rendering a competency that no longer reads that way."""
        stale = teaching("E", "Ask non-leading questions")
        stale["teaches"][0]["name"] = "Ask open questions"
        with self.assertRaises(ValueError) as caught:
            self._corpus([stale], {"Ask non-leading questions": ["E"]})
        self.assertEqual(caught.exception.rule, "stale-competency-name")
        self.assertTrue(caught.exception.source)
        self.assertIn("update the entry", caught.exception.remediation)

    def test_missing_term_name_is_refused(self):
        missing_name = teaching("E", "Ask non-leading questions")
        del missing_name["teaches"][0]["name"]
        with self.assertRaises(ValueError) as caught:
            self._corpus([missing_name], {"Ask non-leading questions": ["E"]})
        self.assertEqual(caught.exception.rule, "missing-competency-name")
        self.assertIn("exact competency", caught.exception.remediation)

    def test_non_object_term_is_refused(self):
        malformed = entry("E", teaches=["not a term"])
        with self.assertRaises(ValueError) as caught:
            self._corpus([malformed], {"Ask non-leading questions": ["E"]})
        self.assertEqual(caught.exception.rule, "invalid-competency-reference")

    def test_missing_term_type_is_refused(self):
        malformed = teaching("E", "Ask non-leading questions")
        del malformed["teaches"][0]["@type"]
        with self.assertRaises(ValueError) as caught:
            self._corpus([malformed], {"Ask non-leading questions": ["E"]})
        self.assertEqual(caught.exception.rule, "invalid-competency-reference")
        self.assertTrue(caught.exception.source)
        self.assertIn("DefinedTerm", caught.exception.remediation)

    def test_wrong_term_type_is_refused(self):
        malformed = teaching("E", "Ask non-leading questions")
        malformed["teaches"][0]["@type"] = "Thing"
        with self.assertRaises(ValueError) as caught:
            self._corpus([malformed], {"Ask non-leading questions": ["E"]})
        self.assertEqual(caught.exception.rule, "invalid-competency-reference")
        self.assertTrue(caught.exception.source)
        self.assertIn("DefinedTerm", caught.exception.remediation)

    def test_single_term_object_is_refused(self):
        malformed = entry("E", teaches=teaching("unused", "Ask non-leading questions")["teaches"][0])
        with self.assertRaises(ValueError) as caught:
            self._corpus([malformed], {"Ask non-leading questions": ["E"]})
        self.assertEqual(caught.exception.rule, "invalid-teaches-list")

    def test_empty_term_object_is_refused(self):
        malformed = entry("E", teaches={})
        with self.assertRaises(ValueError) as caught:
            self._corpus([malformed], {"Ask non-leading questions": ["E"]})
        self.assertEqual(caught.exception.rule, "invalid-teaches-list")

    def test_user_term_cannot_replace_framework_display_name(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            write_corpus(root / "fw", "sre", [])
            write_vocabulary(root / "fw", {"Ask non-leading questions": []})
            write_vocabulary(root / "user", {"Ask Non Leading Questions": []})
            with self.assertRaises(ValueError) as caught:
                expertise.corpus_for("sre", root / "fw", root / "user")
        self.assertEqual(caught.exception.rule, "conflicting-competency-name")

    def test_an_entry_may_teach_nothing(self):
        loaded = self._corpus([entry("E")], {"Ask non-leading questions": []})
        self.assertEqual(len(loaded), 1)

    def test_experience_entry_may_teach_a_user_defined_term(self):
        """Vocabularies union like corpora do. Validating a user's entries
        against flow's terms alone would force them to edit framework files."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            framework, user = root / "fw", root / "user"
            write_corpus(framework, "sre", [])
            write_vocabulary(framework, {"Ask non-leading questions": []})
            write_corpus(user, "sre", [teaching("Mine", "My own term")])
            write_vocabulary(user, {"My own term": ["Mine"]})
            loaded = expertise.corpus_for("sre", framework, user)
            self.assertEqual([e["name"] for e in loaded], ["Mine"])

    def test_user_term_does_not_have_to_exist_in_the_framework(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            write_corpus(root / "fw", "sre", [])
            write_vocabulary(root / "fw", {"Framework term": []})
            write_corpus(root / "user", "sre", [teaching("Mine", "Absent everywhere")])
            write_vocabulary(root / "user", {"Different term": []})
            with self.assertRaises(ValueError) as caught:
                expertise.corpus_for("sre", root / "fw", root / "user")
            self.assertEqual(caught.exception.rule, "unknown-competency")


class ReverseJoinTests(unittest.TestCase):
    """The vocabulary's `Taught by:` lists are the other half of the join.
    Framework-authored, so this is checked before release rather than in every
    user's sync."""

    def test_shipped_corpus_and_vocabulary_agree(self):
        self.assertEqual(
            expertise.reverse_join_problems(SCAFFOLD, COMPOSED_ROLES), []
        )

    def test_a_term_claiming_an_entry_that_does_not_teach_it_is_reported(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "fw"
            write_corpus(root, "sre", [teaching("Real", "Held term")])
            write_vocabulary(root, {"Held term": ["Real", "Imaginary"]})
            problems = expertise.reverse_join_problems(root, ("sre",))
            self.assertEqual(len(problems), 1)
            self.assertIn("Imaginary", problems[0])

    def test_an_entry_teaching_a_term_that_does_not_list_it_is_reported(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "fw"
            write_corpus(root, "sre", [teaching("Real", "Held term")])
            write_vocabulary(root, {"Held term": []})
            problems = expertise.reverse_join_problems(root, ("sre",))
            self.assertEqual(len(problems), 2)
            self.assertTrue(any("lists no entry" in p for p in problems))
            self.assertTrue(any("does not list it" in p for p in problems))

    def test_reverse_list_drift_does_not_block_composition(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "fw"
            write_corpus(root, "sre", [teaching("Real", "Held term")])
            write_vocabulary(root, {"Held term": []})
            self.assertEqual([entry["name"] for entry in expertise.corpus_for("sre", root, None)], ["Real"])
            self.assertTrue(expertise.reverse_join_problems(root, ("sre",)))

    def test_reverse_list_drift_does_not_block_agent_body(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            framework, user = root / "fw", root / "user"
            write_corpus(framework, "sre", [teaching("Real", "Held term")])
            write_vocabulary(framework, {"Held term": []})
            (framework / "agents").mkdir(parents=True)
            (framework / "agents" / "sre.md").write_text("# SRE\n")
            agent = {"name": "sre", "source": "agents/sre.md", "generation_mode": "composed"}
            with mock.patch.object(sync, "USER_OVERLAY_DIR", user):
                rendered = sync.agent_body(agent, framework, framework, {})
            self.assertIn("## Expertise", rendered)
            self.assertTrue(expertise.reverse_join_problems(framework, ("sre",)))


if __name__ == "__main__":
    unittest.main()
