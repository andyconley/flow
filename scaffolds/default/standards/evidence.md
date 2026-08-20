# Evidence Standard

This standard defines what makes a claim of proof trustworthy: what the prover
was told already existed, where the proof was collected, and whether the proof
could have failed.

## What a brief must carry

Any brief that asks someone to review, audit, or look for what is missing must
state what already exists. Without it, "X is missing" is an unsupported finding
— the reviewer had no way to distinguish absent from unfound.

An evidence inventory names, for the area under review:

- what already exists, with file paths and line references
- what is partially covered, and by what
- what was checked and genuinely found absent

Defaults:

- `DO` write the inventory before dispatching the brief, not after
- `DO` cite a path or a line for each claim of coverage
- `AVOID` "nothing exists for X" without saying where you looked

## The inventory is only as good as the search behind it

An inventory is itself evidence and carries the same burden as any other.
A case-sensitive search, a wrong directory, or an unchecked assumption produces
an inventory that is confidently wrong, and every reviewer who trusts it
inherits the error.

Defaults:

- `DO` state how you searched, so a reader can judge the search
- `DO` correct the inventory in place when a reviewer disproves an entry, and
  say what changed
- `DO NOT` treat an inventory as settled because it was written down

## Where the evidence was collected

Proof collected somewhere other than the thing being changed transfers in
parts, not as a whole. A surrogate — staging, a copy of the sheet, a sandbox
tenant, a local stub — differs from the original in specific ways, and each
validation step either depends on one of those differences or it does not.
"Validated in staging" is the failure mode: it claims one verdict for an
environment when the verdicts belong to the checks.

Enumerate the deltas first, against fixed classes, so the list does not depend
on remembering to think of one:

- **data** — volume, shape, or freshness; anything scale-dependent or
  edge-case-dependent is observable only where the data is
- **integrations** — mocked, stubbed, or pointed at endpoints the original does
  not call
- **credentials and permissions** — broader or narrower access than the
  original; permission-gated behavior transfers in neither direction
- **scale and concurrency** — a single-user surrogate cannot show contention,
  throughput, or races
- **external references** — links, IDs, imports, or feeds that resolve to a copy
  which may be stale or broken independently of the change
- **configuration** — flags, environment variables, versions, or retention that
  drifted between the two

Then take each validation step in turn and ask whether its pass or fail depends
on a property in that list. If it depends only on properties that are identical,
the result transfers. If it touches one that differs, the result speaks to the
surrogate alone and is unverified for the original — say so, rather than folding
it into an overall pass.

Partial transfer is the normal case. Most surrogate validation carries some
steps and not others, so a transfer claim is a mixed table and not a boolean:
which steps ran, which differing properties each depends on, and which results
are therefore claimed for the original. A broken surrogate invalidates the steps
that touched the break, not the run.

Defaults:

- `DO` list the deltas before judging any step, so the judgment has something
  concrete to check against
- `DO` record a verdict per check — transfers, does not transfer, or unverified
- `AVOID` discarding an entire surrogate run because one delta broke one step
- `DO NOT` offer "validated in <environment>" as the evidence for a change to
  something else

## Whether the evidence could have failed

A test that cannot fail is not evidence. A vacuous assertion passes regardless
of whether the behavior under it is correct: asserting only that a result is
defined or non-null, asserting on a mock that returns the same value whatever it
is given, or comparing against a snapshot generated from output that was already
wrong. The tell is one question — can you name a wrong implementation that still
passes this test? If you can, the assertion is vacuous, and the green suite is
not proof of the behavior.

Checking this needs no tooling: break one behavior in the source, confirm the
test that covers it goes red, restore the source. Do it for the behaviors the
change actually depends on, not for the whole suite. Projects with mutation
tooling wired into CI (`standards/reference-stack.md`) get the same check at
larger scale automatically, but the manual form works in any language and any
repo, which is why it is the default here.

Whether to run it is a cost judgment. Whether to say so is not: validation that
never states whether fault detection was checked reads identically whether it
happened or not.

Defaults:

- `DO` state whether a mutation check ran, and when it did not, why
- `DO` name the behavior you broke and the test that caught it
- `AVOID` reading a passing suite as evidence that the tests would have gone red
- `DO NOT` make the check a gate — a gate that is routinely skipped is a broken
  gate (`standards/delivery.md`), and an honest "not run" beats a ritual one

## Relevant principle

An inventory converts "I did not find it" into "it is not there" — but only
when the search is stated. Unstated, it converts one reviewer's blind spot into
everyone's.

The same test applies downstream: evidence is worth what it could have said no
to. A check run somewhere else, or a check that could not have failed, answers a
question nobody asked.
