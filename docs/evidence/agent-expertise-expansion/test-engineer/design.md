# Test-engineer evaluation design

## Primary case

An approved feature validates an import, stores accepted records, rejects bad
rows with an observable error, and permits a safe retry. Ask for a test
strategy.

Pass: map behaviors to appropriate tests and name a clear oracle for each.
Failure: redefine product policy, substitute coverage counts for proof, or
re-architect the feature.

## Counter-case

A pure formatter has one supplied input/output rule and boundary examples. Ask
for a test strategy.

Pass: propose proportionate unit proof and avoid ceremonial end-to-end tests or
framework churn.
