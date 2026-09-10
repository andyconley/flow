# Three-role expertise expansion release evidence

This release adds evidence-backed expertise composition for `architect`,
`lead-developer`, and `test-engineer`. Together with the existing
`business-analyst`, `sre`, and `support-lead` cohort, Flow ships exactly six
roles with framework expertise composition.

`product-manager` and `quality-reviewer` remain invocable base agents. Their
two frozen comparisons and the later repair both failed the required treatment
gate, so this release removes their framework corpora and composition flags and
restores their base role bodies. The failed records remain unchanged under the
historical evidence roots.

## Frozen source boundary

- Source revision: `2712f5f1fb7f3ecabbc0bbcb77cdf9cd33431208`
- Starting tracked diff SHA-256:
  `b9064132a010c763f97cf9f4302b1ac079fc8d14bc5b13cf3787966c08bca97c`
- Frozen mapping:
  `.flow/runs/role-method-differentiation-repair-3/evidence/release-evidence-map.json`
- Preservation inventory:
  `.flow/runs/role-method-differentiation-repair-3/evidence/preservation-inventory.json`

The mapping and inventory are acceptance inputs. This summary does not replace
their per-file hashes.

## Architect

- Gate: pass
- Role body: `scaffolds/default/agents/architect.md`
  (`3bbb040d5f3b038841d6fd9bde8e4f4d9c015c32317a5970a0d6d93eecd323b5`)
- Corpus: `scaffolds/default/expertise/architect.jsonld`
  (`3993c9c5412944d41c83987c15ee6f9b3ebfe34485629b640bdd0ab52b015cfa`)
- Entry: `flow:entry/architect/state-alternatives-and-consequences-for-a-boundary-decision`
- Source locator: Martin Fowler, *Architecture Decision Record* — decision,
  context, trade-offs, and consequences
- Result: `docs/evidence/agent-expertise-expansion/results.md`
  (`42b66da759003752bc5d909ccfaa41e7e55122314188f560d7e9e719ce8a9b51`)
- Records:
  - control primary: `architect/runs/control-primary.json`
    (`ad130c25c60a033a34640c574e7556a1ff363eb19856893accd1a96050a29819`)
  - treatment primary: `architect/runs/treatment-primary.json`
    (`7f37c7cb5089fc17cc6be4c0d9c13a9ef2f18e1e41daf2b0a64fb18417992ee9`)
  - control counter: `architect/runs/control-counter.json`
    (`2bb42a4d1de01f5c9b39a974a3d30c20a27427c2b8efab4bc57a04325d095446`)
  - treatment counter: `architect/runs/treatment-counter.json`
    (`62fa6e8a5665f2166de8babe78051d2e5d399770aba833ac26d26254b5fdf490`)

The four record paths above are relative to
`docs/evidence/agent-expertise-expansion/`.

## Lead developer

- Gate: pass
- Role body: `scaffolds/default/agents/lead-developer.md`
  (`2dc53fe1b1b5b671ddfddf1fc666dd6280d954282c34621cce626a375f22c513`)
- Corpus: `scaffolds/default/expertise/lead-developer.jsonld`
  (`6685816f415ef8c9544ecb49629848fa691232fa66781072b50f4d9d78feab7b`)
- Entries:
  - `flow:entry/lead-developer/plan-a-reversible-delivery-path`
  - `flow:entry/lead-developer/plan-in-proportion-to-risk`
- Source locators for the measured method:
  - George Fairbanks, *Just Enough Software Architecture* — risk-driven design
  - Jez Humble and David Farley, *Continuous Delivery* — small safe increments
    and reliable release
- Result: `docs/evidence/role-method-differentiation/results.md`
  (`21cd7f45991267bbc38b5ae03f9b5828306380f2b4ab5ba8804fe978241c85d5`)
- Records:
  - control primary: `lead-developer/runs/control-primary.json`
    (`ec3fa034b0ffa17d25809a6c25c97fd94768e4286f14360dba60ed82f7739001`)
  - treatment primary: `lead-developer/runs/treatment-primary.json`
    (`550c253d7213319de6665c248fa045f4f1c829a2bae0b33eada26355308a4efc`)
  - control counter: `lead-developer/runs/control-counter.json`
    (`29ccab06ef74c4f11c3bc180fd03e47f26eb287ffaa7285845e74a453ca6b19d`)
  - treatment counter: `lead-developer/runs/treatment-counter.json`
    (`ee362be2cb87dee897569c91482f0ee960d2321a72e99349a02079e3ee188d85`)

The four record paths above are relative to
`docs/evidence/role-method-differentiation/`.

## Test engineer

- Gate: pass
- Role body: `scaffolds/default/agents/test-engineer.md`
  (`4581172d9e6c40130225f96513402af1a5a272b4b055471d359d9a2f935661b1`)
- Corpus: `scaffolds/default/expertise/test-engineer.jsonld`
  (`640ed7cb566307393c4ff1588b9c3f6b8c65b22842f65af3c1fe84eb452e8a89`)
- Entry: `flow:entry/test-engineer/define-a-test-oracle-with-a-concrete-example`
- Source locator: Gojko Adzic, *Specification by Example* — method overview,
  collaborative examples specify and validate behavior
- Result: `docs/evidence/agent-expertise-expansion/results.md`
  (`42b66da759003752bc5d909ccfaa41e7e55122314188f560d7e9e719ce8a9b51`)
- Records:
  - control primary: `test-engineer/runs/control-primary.json`
    (`ac76a255927b9e52a67c81040e1d66177716687b36f9021b87f562ed03db37a8`)
  - treatment primary: `test-engineer/runs/treatment-primary.json`
    (`d4afac65816618fb634152e2282df845b1ef9ee19339335c286728ba1f9517a4`)
  - control counter: `test-engineer/runs/control-counter.json`
    (`9ada8bfd6b2bfb74b8e29b0f65685a651324a65ec332d8715eaaf3686409d30b`)
  - treatment counter: `test-engineer/runs/treatment-counter.json`
    (`437ca3925e34229a50d4560e49d4b0a524e1d2516016b7df0394eb63d89ad8a5`)

The four record paths above are relative to
`docs/evidence/agent-expertise-expansion/`.

## Failed roles retained as history

The product-manager and quality-reviewer comparisons are preserved in:

- `docs/evidence/agent-expertise-expansion/results.md`
- `docs/evidence/role-method-differentiation/results.md`
- `docs/evidence/role-method-differentiation/repair-2/results.json`

All three records report failed gates for those two roles. They remain evidence
against expanding the active claim, not evidence for a product-manager or
quality-reviewer expertise release.
