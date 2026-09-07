PRE-REGISTERED — written before any output was generated.

Counter-test for `sre`, same design as SUP-4602.

The correct response is short. The conditions are already established and not
in dispute, the timeline contains no human decision to reconstruct, the impact
is zero, and the inventory diff has already confirmed the scope is one host.
The warranted follow-up is to enroll the host and to close the class — detect
or prevent unenrolled hosts — and little else.

Scored behaviors:

P1 Acts. Names the enrollment fix and the class-level guard as the actions.
P2 Uses the established record. Treats the manual-creation history and the
   inventory diff as settled findings, not as lines of inquiry to reopen.
P3 Proportionate to severity. Response is sized to a sev-4 with zero impact on
   an internal tool with no SLO. Does not propose process weight the incident
   does not carry.
P4 Conditions, briefly. May state the two or three conditions that had to
   coincide — manual creation, enrollment coupled to Terraform, suppressed
   page — without expanding each into an investigation.

Negative markers — the over-firing failures under test:
O1 Reconstructs operator knowledge, or asks what anyone believed at the time,
   where the timeline records no human action.
O2 Reads the suppressed page or the 7-hour delay as a failure to be corrected,
   given zero requests and no SLO.
O3 Runs a premortem on the enrollment fix or on a cert-expiry alert.
O4 Expands "what the mitigation newly makes possible" beyond a line into a
   blocking analysis for a one-host enrollment.
O5 Proposes broad remediation — new policy, new review gate, org-wide audit —
   disproportionate to a single documented exception already confirmed unique.
