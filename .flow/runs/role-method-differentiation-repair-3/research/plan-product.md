## Product Decision Summary

### Opportunity

- **Problem (observed):** The earlier five-role release is blocked because
  product-manager and quality-reviewer failed the frozen treatment-over-control
  gate, while architect, lead-developer, and test-engineer have named passing
  evidence. The formal review says the five-role claim must not ship.
- **Users (observed):** Flow maintainers and users need the three supported
  additions without a false behavioral-improvement claim for the two base
  roles.
- **Why now (recommendation):** The value of the three-role correction erodes
  gradually: retained work stays coupled to a known-false five-role claim until
  the active cohort is narrowed. A third PM/QR experiment has flat present
  value because no workflow failure, adoption need, or deadline was supplied.
  The narrow repair therefore has higher value per delivery time, with medium
  confidence because no adoption metric exists.

### Recommendation

- **Prioritize:** Ship only the evidence-backed three-role expansion, restoring
  product-manager and quality-reviewer to their exact frozen base contracts.
- **Defer:** A third PM/QR experiment, the candidate screen, and the two-axis
  provenance/behavior admission policy. None may be smuggled into the repair
  through corpus, fixture, routing, or documentation changes.
- **Why:** Removal is reversible at repository level; changing the failed
  evidence or admitting a new method is not. The reversible correction should
  be completed now, while any irreversible new evidence envelope needs its own
  named trigger and approval.

### Minimum coherent release and sequence

The release is coherent only if all four outcomes travel together: the active
composed set is exactly six, the three retained additions stay byte-consistent
with their evidence map, PM/QR become base roles in source and generated
surfaces, and the historical failures remain immutable and visibly failed.

1. Freeze the permitted production-path list and recheck the start receipt,
   protected inventory, and retained-role map before edits.
2. Make the narrow reversible source change: remove PM/QR active composition
   and restore their frozen base bodies; retain the architect,
   lead-developer, and test-engineer contracts and corpora.
3. Update deterministic checks and current release documentation, including a
   new evidence summary outside protected historical roots. Produce the final
   hash receipt and the two independent mutation records.
4. Validate the candidate tree: focused and full tests, whitespace, generated
   adapter checks, static smoke, and doctor. Refresh the develop install and
   record dated Claude and Codex live reads of test-engineer. A static success
   cannot replace either live observation.
5. Commit the verified candidate using the repository convention, then obtain
   formal `flow-review` acceptance against that candidate. The review must
   verify the three-role claim and all preservation/live evidence, rather than
   treating the earlier five-role result as a release basis.
6. After review acceptance, merge to `main`, allow the normal semantic-release
   path to publish the approved change, refresh the develop install from the
   merged tree, and repeat the adapter/smoke/doctor and live-readback checks if
   the merge or release changes the installed revision. Record the shipped
   revision in the handoff/archive record.

Steps 1–4 are candidate-proof work and can be retried while the source is still
uncommitted or while a candidate commit is being amended. A failed test,
receipt, generated adapter check, install refresh, or live observation is not
something to waive or relabel: correct the candidate and repeat the affected
proof. Historical-inventory mismatch and a seventh/eighth active composed role
are delivery-stopping conditions until an explicit scope disposition exists.

### Stop conditions

- **Before formal review:** Stop the candidate from proceeding if any of the
  following is true: the active set is not exactly six; any of the three role
  records is absent or fails; PM/QR is still composed in any active surface;
  protected evidence or retained hashes differ; a required mutation guard does
  not fail; current documentation overclaims; or either live client lacks a
  dated, conclusive test-engineer record.
- **At formal review:** Stop merge and release unless the reviewer accepts the
  narrowed evidence claim. Review rejection returns the work to the candidate
  proof stage; it does not reopen PM/QR scope by default.
- **After merge:** A release/install readback failure stops the release claim
  from being marked delivered and requires diagnosis or rollback under the
  normal release process. It does not authorize a fallback to the failed PM/QR
  methods.

### Risks and tradeoffs

- **Observed risk:** The prior review found controls already display much of
  the proposed PM/QR behavior. Reintroducing either method would recreate the
  unsupported claim.
- **Observed risk:** Historical evidence is needed to explain why two roles are
  absent, but searching it as current material can create a false five-role
  narrative. Current-document checks must exclude protected historical roots.
- **Recommendation:** Treat the local source edit as cheap to reverse, but
  treat an external semantic release as the point after which restoration and
  evidence requirements must be re-established through a new release change.
- **Assumption:** The user has selected delivery through commit, merge, and
  release rather than stopping at review-ready. This does not bypass the
  required formal review gate.

### Success

- **Release success:** The merged and released revision truthfully exposes six
  composed roles, with exactly the three named additions and working base PM/QR
  roles, and has current evidence plus both live runtime records.
- **Failure condition:** Any missing proof, unsupported active role, protected
  hash mismatch, failed formal review, or failed post-merge readback means the
  release has not succeeded, even if a commit or tag exists.
- **Follow-through:** Reconsider PM/QR only after the deferred work has a named
  workflow/adoption trigger, verified locators, a fixed approved budget, and a
  new versioned evidence envelope.

## Draft plan recheck

### Finding: operational-state edit needs disposition before implementation

**Blocking scope exception.** The draft adds `.flow/memory/STATE.md` to the
candidate, active-claim surface, handoff, and the possible post-review `S`
commit. The approved requirements and acceptance criterion 10 do not include
this file in the declared change surface; it is not required to establish the
six-role cohort, PM/QR inactivity, preservation, or either live-client gate.
Calling it "operational" does not resolve the exception, and placing it after
review could make `C -> S` look evidence-only while changing a current
release-facing claim.

Resolve this before implementation by either excluding the state-file change
from this release candidate, or recording an explicit scope disposition that
limits it to observed status only and includes it in the review range and
current-claim proof. Do not let a checklist update create a route around the
review-before-merge gate.

### No further product findings

Subject to that disposition, the drafts preserve the minimum coherent scope:
they retain only the three passing additions, restore PM/QR base behavior,
defer both the candidate screen and two-axis policy, and make all candidate
proof—including both live clients—precede formal review. Their `C -> S -> R`
contract also prevents a commit, merge, or semantic-release event from being
counted as delivery without the accepted candidate, public release identity,
and post-release installed-runtime readback.
