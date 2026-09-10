# Adversarial review: testability of the narrowed definition

- Reviewer role: test-engineer
- Date: 2026-09-09
- Verdict: needs refinement before approval

## Evidence inventory

- **Read:** the repair-3 draft requirements and acceptance criteria; the
  repair-3 start receipt; `tests/test_expertise_composition.py`; the current
  production diff; repair-2 manifest, results, mutation record, and frozen
  receipt; the earlier formal review and test audit.
- **Observed from the existing surfaces:** the start receipt hashes the three
  retained role bodies/corpora and hashes both whole evidence trees. The test
  module currently asserts an eight-role cohort and repair-2 PM/QR boundaries,
  so it will need replacement rather than merely an added count assertion.
- **Known limits:** repair-2 has no repair-start preservation receipt and no
  quality-boundary mutation. Static smoke and generated-adapter checks do not
  prove native client loading. There is no repair-3 implementation, final
  receipt, or validation plan yet.

## Findings

### Critical: immutable-evidence requirement conflicts with the required README update

Acceptance criterion 5 requires both prior PM/QR evidence generations to stay
byte-identical. Criterion 6 measures that through the start receipt, which
hashes the complete `docs/evidence/agent-expertise-expansion` and
`docs/evidence/role-method-differentiation` trees. Criterion 9 also requires
an evidence README update. The first of those trees already contains
`docs/evidence/agent-expertise-expansion/README.md`; changing it changes the
tree digest and therefore fails criterion 6.

This is not a dispositionable "unexpected" delta: either the historical tree
is immutable or its documented baseline is no longer byte-identical. Specify
one of these before approval:

1. Keep both captured trees immutable and put the current three-role evidence
   summary/README outside them; or
2. Define a new current-release documentation path and an immutable allowlist
   that excludes no historical evidence files; or
3. Intentionally change a historical README, record the old and new digest,
   and weaken the claim from byte-identical preservation. This is not
   recommended because it conflicts with the desired historical-evidence
   guarantee.

The first option preserves the stated outcome and gives criterion 6 a simple,
non-vacuous oracle: reproduce the receipt's specified sorted-path/NUL/hash
algorithm and require equality for both tree hashes.

### Critical: the live-client condition is simultaneously a gate and a non-gate

Criterion 8 says a newly composed agent "loads through Claude" and "through
Codex" with its expected method/model/effort, then says inability to verify a
live client is a limitation rather than a passed result. Those statements do
not define an acceptance result for an unavailable client. Existing static
smoke explicitly cannot prove native-client loading, so it cannot substitute.

Choose and state one rule. If live loading is release-blocking, require an
observed, dated record for each client and fail when either cannot be observed.
If it is not release-blocking, exclude it from the pass formula and require the
validation record to label it `observed`, `asserted`, or `unavailable`; only
static artifact/configuration checks can then support acceptance. The draft's
technical outcome is valid under the second rule, but it must not claim live
loading was passed. Refreshing the develop install and the commands used to
check it belong in the later validation plan, not the acceptance criterion.

### Important: documentation and scope searches need a fixed search surface and allowlist

Criterion 9's "exact searches" has no command, directories, patterns, or
historical exception list. A repository-wide string search would either fail on
frozen historical evidence (which must retain its failed five-role language) or
pass after wording changes that leave an equivalent current overclaim. Criterion
10 similarly cannot prove the absence of all unrelated work without a declared
change surface.

Replace these with outcome-level requirements: current release documents make
only the six-role/three-role claim, and repair-3 does not change the listed
out-of-scope capability surfaces. Put the plan procedure in the validation
plan: freeze a path list for current release documents, a separate allowlist of
immutable historical locations, case-insensitive claim patterns plus structured
manifest assertions, and a predeclared changed-file allowlist. Review any
outside-allowlist file as a blocking scope exception. This catches a wrong
narrowed release without treating the required historical record as a defect.

### Important: criterion 7's mutation is under-specified and could protect only one boundary

"At least one delete-or-negate mutation" can pass after proving only that a
product-manager entry is absent, while a retained role is silently removed; it
can also pass a raw substring test after a semantic negation. The old audit
already demonstrated that literal boundary checks are insufficient.

Require two named negative mutations and restoration checks: (a) reintroduce
one PM or QR `generation_mode = "composed"` declaration or active entry and
prove the exclusion/cohort test fails; (b) remove one retained role declaration
or its required corpus/join and prove the retained-cohort test fails. The final
focused suite must pass after exact restoration. Where a test asserts role
instruction behavior rather than a structural declaration, add a negate/restore
mutation that violates the positive obligation; do not count substring presence
as semantic proof.

### Important: criteria 2 and 3 need immutable record identifiers, not only role names

The three passing roles are known from the original evidence results and the
later lead-developer replacement, but "exact approved role boundaries" and
"immutable passing primary and counter records" lack a mapping manifest.
Without paths, raw-output hashes, the relevant gate result, and the source
revision, a summary can cite any favorable-looking transcript and still pass.

Add a three-row release-evidence map with role, role-body/corpus start hash,
entry id, source locator, primary record path/hash, counter record path/hash,
and recorded gate result. The final validator compares it against the start
receipt and raw files. It must reject a missing row, duplicate role, a failed
gate, a repair-2 PM/QR record, or a record hash mismatch. This is a feasible
oracle; it separates retained behavioral evidence from the new narrowing work
without rerunning models.

### Important: PM/QR exclusion is feasible but "active" needs one structural definition

Criterion 4 correctly targets frozen pre-repair bodies, no active corpus/edge,
and no rendered expertise section. "Active corpus" is ambiguous if an archival
JSON-LD file remains on disk. Define active as: the role has no composed
manifest declaration, no baseline/external corpus selected by the composition
loader, no competency vocabulary `Taught by` reference to an active PM/QR
entry, and `sync.agent_body()` emits zero expertise sections for that role.
Then compare each restored body byte-for-byte to the named control hash from
the frozen commit. The tests should use the loader and renderer, not only
filesystem absence, so a renamed or orphaned file cannot be mistaken for an
excluded role.

### Feasible as drafted with a small precision addition: exact cohort and preservation receipt

Criteria 1 and 6 can reliably block a wrong cohort if the expected set is
stored as lowercase canonical identifiers:

`{architect, business-analyst, lead-developer, sre, support-lead, test-engineer}`.

Use set equality from `flow.toml`, then assert one corpus and one rendered
expertise section for each retained composed role. Require the final receipt to
reuse the start receipt's digest algorithm and enumerate exactly its six
retained files and two evidence trees. A mismatch is a failed preservation
claim; it may be investigated, but it cannot be passed as an unexplained
exception. Criterion 2's generated adapter check remains a separate rendering
oracle and should report the adapter versions/configuration used.

## Definition outcomes versus plan procedures

The definition should retain these outcomes: exact six-role composition;
three named evidenced additions; PM/QR restored and inactive; immutable failed
history; truthful claims; and no out-of-scope capability changes. The following
are implementation/validation-plan procedures and should not be mistaken for
outcomes: receipt-generation commands, hash and search commands, develop
install refresh, client navigation, test names, mutation mechanics, adapter
sync commands, and the final diff allowlist. Acceptance can require evidence
of the outcome, while the validation plan specifies the reproducible procedure
and artifacts that produce it.

## Acceptance disposition

After resolving the immutable-README conflict and live-client pass semantics,
the narrowed release can reliably block a wrong result. The cohort, PM/QR
exclusion, preserved evidence, named retained evidence, and scope boundaries
all have feasible non-vacuous oracles when the proposed maps, two mutations,
and fixed search/allowlist are added. Until then, criteria 5/6/9 can conflict,
criterion 8 has no determinate status, and criterion 7 can pass while a
separate protected boundary is broken.

## Recheck

- **Immutable-README conflict — resolved.** Requirement 7 and criterion 5 put
  the new release summary outside protected roots, retain historical READMEs,
  and bind preservation to the new per-file inventory. This no longer requires
  a documentation edit inside a byte-protected tree.
- **Live-client rule — resolved.** Criterion 8 makes dated Claude and Codex
  observations a hard requirement and says unavailable or inconclusive records
  fail; static output cannot substitute.
- **Scope search — resolved at the definition level.** Criteria 9 and 10 now
  separate the current-document outcome from immutable historical evidence and
  require the later validation plan to freeze the active-document search
  surface, exclusions, and production change surface. The exact commands remain
  correctly plan-level work.
- **Two mutations — resolved.** Criterion 7 requires separate restored
  exclusion and retained-role mutations, plus semantic negate/restore proof
  for any instruction-level assertion.
- **Evidence map — resolved.** `release-evidence-map.json` is valid JSON with
  exactly architect, lead-developer, and test-engineer rows; each carries a
  passing gate, source revision, role/corpus hashes, entry/source data, result
  hash, and four raw-record path/hash pairs. Criterion 3 rejects the prior
  missing/duplicate/failed/PM-QR/mismatch cases.
- **PM/QR inactive definition — resolved.** Criterion 4 defines inactive
  across the manifest, loader, competency vocabulary, shared renderer, base
  body, and refreshed generated install. That prevents an archival file from
  being mistaken for active composition.

The revised draft addresses every testability finding. The remaining proof
artifacts are intentionally implementation and validation-plan work, so there
is no unresolved definition-level acceptance blocker.
