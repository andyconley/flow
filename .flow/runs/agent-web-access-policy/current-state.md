# Current State: Agent Web Access Policy

- The pre-change framework had thirteen shared agents and only
  `solution-architect.md` declared Claude web tools.
- `cli/sync.py` merged user agents by name and previously warned then ignored a
  malformed user overlay.
- `cli/render.py` preserved Claude source frontmatter and emitted Codex model
  policy, but had no cross-runtime capability domain.
- Generated user-level files are replaceable adapter outputs; framework source
  under `scaffolds/default/` and user overlay source are authoritative.
- The release pipeline already owns semantic version analysis, candidate
  validation, changelog release commit, tag, GitHub release, and public
  verification.
