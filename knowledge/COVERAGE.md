# Knowledge coverage inventory

Current Flow has 13 agent roles. The imported seed contains all 21 authoritative existing cards for 6 roles. It does **not** provide role-specific expertise cards for every agent. No missing authoritative cards were found to import.

| Agent | Imported cards | Authoritative card source |
| --- | ---: | --- |
| architect | 1 | scaffolds/default/expertise/architect.jsonld |
| business-analyst | 5 | scaffolds/default/expertise/business-analyst.jsonld |
| data-engineer | 0 | None exists; role instructions remain in `scaffolds/default/agents/data-engineer.md` |
| lead-developer | 2 | scaffolds/default/expertise/lead-developer.jsonld |
| product-manager | 0 | None exists; role instructions remain in `scaffolds/default/agents/product-manager.md` |
| quality-reviewer | 0 | None exists; role instructions remain in `scaffolds/default/agents/quality-reviewer.md` |
| security-reviewer | 0 | None exists; role instructions remain in `scaffolds/default/agents/security-reviewer.md` |
| solution-architect | 0 | None exists; role instructions remain in `scaffolds/default/agents/solution-architect.md` |
| sre | 6 | scaffolds/default/expertise/sre.jsonld |
| support-lead | 6 | scaffolds/default/expertise/support-lead.jsonld |
| tech-writer | 0 | None exists; role instructions remain in `scaffolds/default/agents/tech-writer.md` |
| test-engineer | 1 | scaffolds/default/expertise/test-engineer.jsonld |
| ux-specialist | 0 | None exists; role instructions remain in `scaffolds/default/agents/ux-specialist.md` |

The seven zero-card roles retain their authored responsibilities and instructions. Their absence from the card corpus is an existing authoring gap, not an import failure. In particular, product-manager and quality-reviewer historical expansions failed their release gates; promoting those experimental treatments would change their authority.

There are also 33 authoritative shared standards documents under `scaffolds/default/standards/`, including vendored standards. They are distributed framework/project instructions, not role-specific cards. The solution architect explicitly references that corpus. They were inventoried with hashes and role references in `evidence/coverage.json`; this integration does not silently relabel them as evidence-extracted expertise cards.

Inspected sources: all tracked JSON-LD files; all 13 current agent Markdown sources; shared standards and their role references; expertise fact definitions, trigger rules and runtime manifests; historical expertise-expansion and role-method evaluation records; archive ranker fixtures. The source schema has exactly the six canonical JSON-LD files used by the POC. Original installed card hashes were separately verified unchanged.

Adding expertise for the seven missing roles requires authored, sourced cards and their existing acceptance/review process. No new role expertise was fabricated for coverage counts.
