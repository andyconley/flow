# Control-Plane Maintenance Exception

Andy Conley approved this exception after Flow rejected a successfully completed Claude producer call solely because its valid event trace exceeded the receipt validator's 1 MiB ceiling. The same defect class previously converted a valid Codex stream above 256 KiB into an unrecoverable unknown.

## Authority and Boundaries

The engineer may directly repair and test only the provider-stream and trace-evidence infrastructure that creates this bootstrap deadlock. The repair must:

- stop treating total valid provider-output size as semantic failure;
- parse provider results without accumulating an unbounded stream in memory;
- stream trace hashing and retain file-backed evidence;
- preserve runtime limits, final-result limits, malformed-output rejection, process cleanup, provider identity, and unknown-send fencing;
- add focused regressions for both Claude and Codex paths;
- be committed separately before invoking the prescribed `recover-delivery-lead` command.

The exception does not authorize copying or manually accepting the producer's Shaper-intent implementation. Flow remains responsible for recovering and validating that completed result after the infrastructure repair.
