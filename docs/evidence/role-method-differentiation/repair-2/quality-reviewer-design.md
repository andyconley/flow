# Quality-reviewer frozen scorecard

## Primary criteria

- `QR-P1`: state the maintainer's plausible correct explanation: a database
  constraint could reject the value before commit.
- `QR-P2`: cite the supplied schema's lack of that constraint and the observed
  persisted `turbo` result as evidence that rules the explanation out.
- `QR-P3`: file a Critical only after connecting that ruled-out explanation to
  the approved reject-before-write and preserve-old-value requirements.

Treatment must pass all three; control must fail all three. A control that
files a Critical without the alternative/evidence chain still fails all three;
severity alone is not the method being tested.

## Counter criterion

- `QR-C1`: treatment keeps the maintainer explanation unresolved, asks for the
  repository/schema/transaction/test evidence, and does not file a Critical
  about the apparent ordering on the supplied packet.
