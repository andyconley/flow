# Requirements — `greeting` rejects an empty name

- Work ID: claude-acceptance
- Stage: define (business-analyst)
- Date: 2026-10-11
- Status: draft for Flow approval — writing this file does not approve the work

## Evidence

Observed facts, each tied to something read in this workspace:

| # | Fact | Source |
|---|------|--------|
| E1 | `greeting` takes one positional parameter `name` and returns `f"Hello, {name}!"`. There is no validation, no type hint, no docstring, no return-type contract. | `fixture.py:1-2` |
| E2 | Current behaviour for an empty string is `greeting("") == "Hello, !"` — a well-formed-looking greeting addressed to nobody. Derived by reading the f-string, not by executing it. | `fixture.py:2` (not executed) |
| E3 | `fixture.py` is the only Python source file in the project. | `find . -name "*.py" -not -path "./.flow/*"` → `./fixture.py` |
| E4 | No caller, import, or test references `greeting` anywhere in project-owned files. The only other `greeting` hits are vendored `node_modules` under `.flow/runs/claude-acceptance/openhands/npm-cache/`, which are unrelated third-party fixtures. | repo-wide grep for `greeting` |
| E5 | There is no `.flow/PROJECT.md` and no `.flow/memory/STATE.md` in this project, so no product constraints, style standards, or error-handling conventions are available to inherit. | `ls .flow` → `runs/`, `runtime.toml` only |
| E6 | The requested change is scoped by the run prompt to "changing greeting to reject an empty name"; the definition stage is explicitly not to implement it. | `task.md:1` |

Everything below marked as an assumption is **not** supported by the evidence above.

## Problem Statement

- **What:** `greeting` accepts an empty name and returns `"Hello, !"` (E2). The function silently produces a greeting that names no one, so a caller that passes bad or missing input gets back a string that looks successful and will flow downstream undetected.
- **Who:** Developers calling `greeting` from application code, and whoever ultimately reads the rendered greeting. There are no callers today (E4), so the affected party is any future consumer of this function.
- **Why now:** The function is still a two-line leaf with no dependents (E3, E4). Tightening the input contract now costs one guard clause and breaks nothing; doing it after callers exist turns it into a breaking change that has to be coordinated.

## Users and Workflows

- **Primary personas:** Developer-as-caller (passes a name in, consumes a string back). Secondarily, the end user who sees the greeting text.
- **Current workflow:** Caller invokes `greeting(name)` → always receives a string → no signal distinguishes a real name from an empty one. Any defence against empty input must be written separately by each caller, and today none exists.
- **Future workflow:** Caller invokes `greeting(name)` → a valid name returns the same greeting as before → an empty name raises immediately at the call site, where the caller still has the context to handle, log, or surface it.

## Scope

**In scope**

- Input validation in `greeting` for an empty name.
- Defining what "empty" means and what "reject" does, precisely enough to test.
- Preserving existing behaviour for every non-empty name.

**Out of scope**

- Implementing the change — definition stage only (E6).
- Editing any file other than the two stage artifacts (E6).
- Changing the greeting text, format, or language for valid names.
- Localisation, name normalisation, length limits, profanity or character-set restrictions.
- Introducing a logging, i18n, or validation framework for a two-line module.
- Changing `greeting`'s signature, adding parameters, or adding a default value for `name`.

**Constraints**

- No existing error-handling or typing convention to conform to (E5), so this change sets the precedent for the module rather than following one.
- No test suite exists yet (E3), so acceptance verification needs tests to be created alongside the implementation slice.

## Requirements

### Goals

- **G1.** `greeting` rejects an empty name instead of returning `"Hello, !"`.
- **G2.** Rejection is unambiguous to the caller — it cannot be mistaken for a successful greeting.
- **G3.** Behaviour for every currently-valid name is unchanged, byte for byte.
- **G4.** The rejection path is covered by an automated test that fails against today's `fixture.py`.

### Non-goals

- **NG1.** No validation beyond emptiness (no length, charset, or content rules).
- **NG2.** No change to the success-path output string.
- **NG3.** No new dependencies.
- **NG4.** No caller-side migration work — there are no callers (E4).

### User stories

- **US1.** As a developer calling `greeting`, when I pass an empty name, I want the call to fail loudly so the bug surfaces at my call site instead of as `"Hello, !"` in output.
- **US2.** As a developer calling `greeting` with a real name, I want the existing return value unchanged so adopting this version requires no work from me.
- **US3.** As a reviewer, I want the rejection behaviour pinned by a test so a later refactor cannot quietly restore the old permissiveness.

### Decisions needed before implementation

These three have more than one defensible answer. **A1–A3 below are the assumptions carried into `acceptance-criteria.md`**; if a reviewer disagrees with any of them, the corresponding criteria change and should be revised before the build stage.

- **A1 — Rejection mechanism: raise `ValueError`.** Rationale: `ValueError` is the Python-idiomatic signal for a right-type-wrong-value argument, and it is the only option that cannot be ignored by a caller that does not check the return value — which is what makes `"Hello, !"` dangerous today (E2). Alternatives considered and set aside: returning `None` (silently propagates, same class of bug), returning an error string (indistinguishable from a greeting), returning a result object (disproportionate for a two-line function).
- **A2 — "Empty" means `""` and whitespace-only.** Rationale: `greeting("   ")` returns `"Hello,    !"`, which has the same defect as `"Hello, !"` and typically has the same cause — an unvalidated form field or stripped record. Treating only `""` as empty would leave the identical bug reachable. Note this is a judgement call, not something the fixture states; it is the most likely reviewer disagreement and is called out as OQ1.
- **A3 — `None` is rejected, as `TypeError`.** Rationale: `greeting(None)` currently returns `"Hello, None!"`, which is the same user-visible defect, so leaving `None` accepted would satisfy the letter of the request and not its intent. `TypeError` rather than `ValueError` because `None` is a wrong *type*, not a wrong *value*. See OQ2 — a reviewer may prefer a single `ValueError` for both, or may consider `None` out of scope entirely.

## Risks and Open Questions

### Risks

- **R1 — Behavioural break for unknown callers.** Low: no callers exist (E4). If any external consumer relies on `greeting("")` returning a string, this change breaks it at runtime rather than at import.
- **R2 — Over-rejection via A2.** If a legitimate caller passes a name that is meaningfully whitespace, it is now rejected. No such caller is known, and no naming convention in this workspace suggests one.
- **R3 — Scope creep into general input validation.** The function is two lines; adding a validation layer, custom exception hierarchy, or logging would outweigh the change. NG1/NG3 exist to bound this.
- **R4 — Unverifiable acceptance.** With no test suite (E3), the criteria below cannot be checked until the implementation slice adds tests. The criteria are written to be executable so this is mechanical, not a judgement call.

### Assumptions

- **AS1.** `greeting` is intended to produce human-facing greeting text; a greeting addressed to nobody is a defect, not an accepted edge case. (Inferred from the function name and output format at `fixture.py:2`; not stated anywhere.)
- **AS2.** `name` is intended to be a `str`. There is no type hint (E1), so this is inferred from the f-string usage.
- **AS3.** The project targets a Python version where f-strings work — Python 3.6+. Not pinned anywhere in the workspace; there is no `pyproject.toml`, `setup.py`, or version file.
- **AS4.** The absence of `.flow/PROJECT.md` (E5) means no standard is being violated by choosing `ValueError`, rather than meaning the standard lives somewhere unread.

### Open questions

- **OQ1.** Is whitespace-only input in scope? A2 says yes. If the reviewer says no, AC-3 is deleted and `greeting("   ")` keeps returning `"Hello,    !"`.
- **OQ2.** Is `None` in scope, and should it raise `TypeError` or `ValueError`? A3 says in scope, `TypeError`. A reviewer preferring one exception type for all bad input would merge AC-5 into AC-2.
- **OQ3.** Should non-string, non-`None` types (`0`, `[]`, `42`) be validated? Currently they stringify into the greeting. Treated as out of scope here (NG1) on the grounds that A2/A3 cover the realistic failure modes — but this is a boundary a reviewer may want drawn differently. AC-6 pins the current behaviour so the decision is at least visible.
- **OQ4.** What exact message should the exception carry? Not specified by the request. AC-2 requires a non-empty message that names the parameter, without pinning wording, so a later copy change does not break the test.
- **OQ5.** Should this slice also add type hints and a docstring to `greeting`? They are absent (E1) and the function is being touched anyway. Left out of scope to keep the diff to one behavioural change; flagged because it is the obvious adjacent cleanup.

## Delivery Slices

1. **Slice 1 — Reject empty and whitespace-only names.** Guard clause in `greeting` raising `ValueError`; tests for `""`, `"   "`, and unchanged behaviour for a normal name. Delivers G1–G4 and satisfies US1–US3 on its own. This is the whole requested change.
2. **Slice 2 — Reject `None` as `TypeError`.** Separable because it hangs on OQ2; splitting it lets Slice 1 land while that is decided. Fold into Slice 1 if the reviewer confirms A3 up front.
3. **Slice 3 (optional, follow-on) — Type hint, docstring, and documented contract.** Addresses OQ5 and turns AS2 into something enforced rather than inferred. Not required by this request.
