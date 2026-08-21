# Git Commits

This project follows the [**Conventional Commits v1.0.0**](https://www.conventionalcommits.org/en/v1.0.0/) specification.

The authoritative spec is the upstream document. Flow vendors a verbatim copy at [`standards/vendor/conventional-commits-1.0.0.md`](vendor/conventional-commits-1.0.0.md) at a pinned upstream commit; if this distilled standard and the vendored spec disagree, the spec wins. The metadata block `[standards.git-commits]` in `flow.toml` declares the pinned version and source.

## When to follow

Every commit to a flow-aware repo, by every contributor — human or agent. This standard applies at the moment a commit message is being composed, not just at PR time.

## Commit message format

```
<type>[optional scope][!]: <description>

[optional body]

[optional footer(s)]
```

- **`<type>`** — required. A short noun naming the kind of change. See "Types" below.
- **`[optional scope]`** — optional parenthesized noun naming the affected area, e.g. `feat(parser): …`. Scopes are project-specific; see "Project Overrides" below.
- **`[!]`** — optional `!` immediately before the colon to mark a breaking change. May be combined with a `BREAKING CHANGE:` footer.
- **`<description>`** — required. Short, present-tense summary in the imperative mood. Lowercase first word is conventional but not mandatory.
- **`[optional body]`** — one blank line after the description; one or more paragraphs explaining the why, not just the what.
- **`[optional footer(s)]`** — one blank line after the body. Token-value pairs in `git trailer` shape (e.g. `Refs: #123`, `Reviewed-by: name`, `Co-Authored-By: name <email>`). `BREAKING CHANGE: <description>` or `BREAKING-CHANGE: <description>` (uppercase) signals a breaking change when no `!` was used in the prefix.

## Types

Required by the spec:

- **`feat`** — a new feature for the user (MINOR in SemVer)
- **`fix`** — a bug fix for the user (PATCH in SemVer)

Allowed and recommended (from `@commitlint/config-conventional`, derived from the Angular convention):

- **`build`** — changes to the build system or external dependencies
- **`chore`** — maintenance with no user-visible effect (deps bumps, internal hygiene)
- **`ci`** — changes to CI configuration
- **`docs`** — documentation only
- **`perf`** — a code change that improves performance
- **`refactor`** — a code change that neither fixes a bug nor adds a feature
- **`revert`** — reverts a previous commit; use a `Refs: <sha>` footer
- **`style`** — formatting, whitespace, semi-colons (no logic change)
- **`test`** — adding or correcting tests

Types other than `feat`/`fix` have no implicit SemVer effect unless they carry a `BREAKING CHANGE`.

## Breaking changes

Mark them in either of two ways (or both, for emphasis):

1. **In the prefix** — append `!` before the colon: `feat(api)!: drop support for Node 6`
2. **In the footer** — `BREAKING CHANGE: <description>`

If `!` is used, `BREAKING CHANGE:` in the footer is optional and the description itself describes the break. Breaking changes correlate with MAJOR in SemVer regardless of the underlying type.

## Examples

```
feat(parser): add ability to parse arrays
```

```
fix: prevent racing of requests

Introduce a request id and a reference to latest request. Dismiss
incoming responses other than from latest request.

Reviewed-by: Z
Refs: #123
```

```
feat!: send an email to the customer when a product is shipped

BREAKING CHANGE: use JavaScript features not available in Node 6.
```

```
docs: correct spelling of CHANGELOG
```

```
revert: let us never again speak of the noodle incident

Refs: 676104e, a215868
```

## Decision rules for common cases

| Situation | Type to use |
|---|---|
| Adding a new user-facing capability | `feat` |
| Fixing user-observable wrong behavior | `fix` |
| Tightening internals without behavior change | `refactor` |
| Speeding something up without changing behavior | `perf` |
| Editing only docs | `docs` |
| Editing only tests | `test` |
| Editing only CI / build pipeline files | `ci` or `build` |
| Bumping dependencies for hygiene | `chore` (or `build` if it affects build) |
| Reverting a previous commit | `revert` (footer with the reverted SHA) |
| Commit qualifies as more than one type | **Split it into multiple commits.** This is encouraged by the spec — see FAQ in the vendored copy. |

## Project Overrides

This standard MAY be extended via the user overlay at `~/.flow/user/standards/git-commits.md`. It SHOULD NOT be silently weakened.

Reasonable project additions:

- **Allowed scopes** — a short, enumerated list specific to the project's modules or services (e.g., for a multi-service repo: `api`, `worker`, `web`, `docs`). When the framework default leaves scopes free-form, projects can pin them.
- **Reserved scopes** — names that must not be used (e.g., `release` if it's automation-only).
- **Additional types** — domain-specific (e.g., `data` for migrations, `infra` for IaC) — declared explicitly so reviewers know they're allowed.
- **Trailer conventions** — project-specific footer tokens like `Issue:` or `Slack:`.

Project overrides MUST NOT:

- remove the requirement for a type prefix
- redefine `feat`/`fix` semantics
- weaken the breaking-change ceremony

If a project needs different commit semantics entirely, that's a different framework, not a flow override.

## Why this lives in `standards/`

`standards/` is flow's reusable library of how-we-work knowledge. Agents and commands cite this file by path when their work culminates in a commit:

- `agents/lead-developer.md` — implementation work
- `agents/quality-reviewer.md` — review work that lands fixes
- `commands/flow-implement.md` — gated lane (commits at slice boundaries)
- `commands/flow-scout.md` — small-change lane (single commit each)

The vendored spec at `standards/vendor/conventional-commits-1.0.0.md` is the authoritative source. This file is the working summary contributors and agents actually read at commit time.
