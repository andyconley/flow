# Product Shaping: Agent Web Access Policy

- Ship the resolver, Claude mapping, Codex mapping, safety guidance, tests, and
  documentation together so runtime behavior cannot temporarily diverge.
- Treat malformed user-overlay TOML as fatal. Continuing with framework
  defaults could discard an intended denial; the accepted compatibility cost
  is that any overlay syntax error now blocks sync until corrected.
- The observable consumer outcome is a v0.23.0 release whose installed
  scaffold produces the documented configuration for the complete agent
  inventory and preserves explicit opt-outs.
- Release completion includes source commit and push, candidate validation,
  generated changelog release commit, tag, GitHub release, public fresh-install
  and upgrade verification, then Flow archive.
- Roll back by installing the prior release and resyncing both runtimes.
