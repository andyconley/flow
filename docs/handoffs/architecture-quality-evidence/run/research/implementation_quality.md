# Quality implementation evidence

## Observed

- Implemented `collect_quality(source_root, config, raw_dir)` and isolated Radon and mutmut adapters. `quality.source_sha256` is an optional assertion only, so baseline and candidate can retain identical analysis configuration. The collector always binds copied-source hashes itself, requires `quality.mutation_target` for the fast fresh selected-mutant run, copies the complete CLI dependency set, runs the existing 64 collector tests first, and retains native raw logs, source/test hashes, tool pins, and executed target-loaded path proof.
- Supplied `coverage_json` and `mutation_workspace` configuration is rejected as not candidate-bound. A failed fresh command returns `inconclusive`; the helper does not fabricate a zero metric or a mutation result.

## Mutation feasibility checkpoint

- **Observed:** mutmut 3.7.0 installed in the isolated `/private/tmp/flow-architecture-tools` environment on Python 3.14.6.
- **Observed:** in disposable workspace `/private/tmp/architecture-evidence-mutmut.Z3MVDx`, a baseline pytest test passed and mutmut generated 33 mutants for `cli/jsonl_watermark.py`. The test imported `cli.jsonl_watermark` from mutmut's `mutants/` workspace, proving the target-loaded path.
- **Observed:** `cli.jsonl_watermark.x_read_new_lines__mutmut_28` changes `start = nl + 1` to `start = nl + 2`. It survived the weak test, then was killed after the same test asserted `new_offset == len(complete_line_with_newline)`. This is the required controlled weak/strong result.
- **Observed limitation:** this is disposable compatibility evidence, not the candidate-bound pilot mutation packet. Other native outcomes were retained by mutmut (the first run reported killed, survived, timeout, and no-tests outcomes); the eventual packet must retain its own raw output and test/source hashes.
- **Observed:** the fresh collector test against the current isolated checkout produced a native `read_new_lines` record (16/18 statements and 4/6 branches), Radon CC 5, statement-coverage CRAP 5.034293552812072, and a candidate-matching copied-source hash. It retains the complete native mutmut metadata, including `not checked` entries in a selected-mutant run, because `mutmut results` hides killed mutants. The optional `mutation_proof="weak_strong"` mode remains the slower fixed-baseline compatibility proof. This is component integration evidence only; it is not a complete candidate-bound review packet.

## Remaining integration requirement

Root must call the collector with the approved enabled quality configuration, pinned executable/version mapping, and a fresh raw directory. It does not accept externally prepared coverage or mutation inputs.
