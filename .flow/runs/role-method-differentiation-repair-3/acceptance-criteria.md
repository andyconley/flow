# Acceptance criteria: three-role expertise expansion

1. The final manifest identifies exactly six composed roles: the existing
   business-analyst, SRE, and support-lead cohort plus architect,
   lead-developer, and test-engineer. Product-manager and quality-reviewer are
   absent from the composed set.
2. Architect, lead-developer, and test-engineer retain their exact approved role
   boundaries, role-owned corpus entries, verified source metadata and locators,
   competency edges, and generated Claude/Codex rendering. Forward and reverse
   joins pass for every retained entry.
3. The released evidence summary maps each of the three added roles to its
   immutable control/treatment primary and counter records, role/corpus hashes,
   entry ids, source locators, source revision, and recorded passing gate. The
   required mapping is frozen in `evidence/release-evidence-map.json`; a missing
   role, duplicate role, failed gate, PM/QR record, or hash mismatch fails.
4. Product-manager and quality-reviewer executable role bodies match the frozen
   pre-repair controls and remain invocable as base roles. “Inactive” means each
   has no composed manifest declaration, no corpus selected by the composition
   loader, no active competency `Taught by` edge, and zero expertise sections
   from the shared renderer. A refreshed generated install carries that state;
   tests reject either role being silently reintroduced.
5. Both prior PM/QR evidence generations remain byte-identical to their frozen
   baselines and visibly failed. The protected scope is every file listed in
   `evidence/preservation-inventory.json`, including the prior run's reviews and
   source-verification records. New release documentation lives outside those
   roots and never converts provenance or safe counters into a behavioral pass.
6. A final receipt compares every protected per-file hash and each retained
   role/corpus hash against the repair-3 start inventory. An unexplained
   mismatch, missing path, replacement path, or late/missing start digest fails
   preservation; aggregate directory counts or hashes are supplementary only.
7. Deterministic tests prove the exact composed-role set, excluded PM/QR active
   surfaces, retained corpus schema and joins, shared renderer path, and current
   documentation counts. Two separate restored mutations are required: one
   reintroduces a PM/QR composed declaration or active entry and makes the
   exclusion guard fail; one removes a retained role declaration, required
   corpus, or evidence mapping and makes the retained-role guard fail. A test of
   role instruction semantics must also fail for a negated positive obligation;
   substring presence alone is not proof.
8. Focused and full tests, `git diff --check`, both generated-adapter checks,
   static runtime smoke, and `flow doctor` pass against the final tree. After a
   develop-install refresh, dated live records show one newly composed agent
   loading through Claude and one through Codex with the expected method and
   configured model/effort. If either record is unavailable or inconclusive,
   this criterion fails; static output cannot substitute for it.
9. Current release documents, the new evidence summary outside protected roots,
   validation record, and handoff describe a three-role expansion and exactly
   six total composed roles. The validation plan fixes the active-document
   search surface and immutable historical exclusions before implementation so
   retained failed language cannot be mistaken for a current overclaim.
10. The declared production change surface is limited to PM/QR active-role
    restoration and removal, cohort configuration/vocabulary, composition tests,
    current architecture/file-layout/release documentation, generated adapter
    reconciliation, and new repair-3 artifacts outside protected roots. Any
    other changed production path is a blocking scope exception until explicitly
    dispositioned. No candidate trial or change to retrieval, indexing, routing,
    overlays, corpus format, renderer behavior, or unrelated role behavior is
    accepted under this definition.
