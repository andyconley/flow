# Solution architect review

## Observed

- The existing Flow lifecycle, execution ledger, supervised MAF runner, gateway, provider adapters, receipts, and recovery controls supply the control-plane spine.
- V6 is a narrow execution projection that hard-codes job, provider, path, test, roster, and verification assumptions.
- ADR 0011 assigns coordination to supervised MAF behind a Flow gateway. ADR 0012 makes Flow state and generation fencing authoritative for recovery.

## Recommended

- Add canonical Flow-owned Shaper and Delivery contracts above the gateway.
- Seal the Delivery Charter at `start-plan`, after the last approved Shaper-owned artifact.
- Translate the charter into a new execution-envelope version rather than expanding v6.
- Use explicit generation-fenced Delivery Lead resume/supersede.
- Keep v6 inspectable but ineligible for new execute/resume paths.
- Prove the design through one real producer plus Ollama verifier job in the first slice.

## Alternatives rejected

- Expanding v6 into the domain charter.
- Creating a new event-sourced orchestration kernel.
- Copying state independently into each runtime.
- Allowing automatic time-based takeover.
