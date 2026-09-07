PRE-REGISTERED — written before any output was generated.

Counter-test. SUP-4471 asked whether the expertise entries fire when their
triggers are present. This ticket asks the opposite question: whether they
fire when they should not.

The correct first response is the KI-388 workaround. The distinguishing
observation the entries demand — raw file contents versus rendered contents —
is already in the ticket, recorded by tier 1 and reproduced internally. The
timeline rules out the release. The locale is stated. No sample file is
missing.

An expertise addition that improves triage should reach the workaround here at
least as fast as the control, with the discriminating evidence cited rather
than re-requested.

Scored behaviors:

P1 Answers. Gives the Data > From Text workaround as the operative response,
   not as one option pending further investigation.

P2 Cites the discriminator. Names the raw-line evidence or the internal
   reproduction as the reason KI-388 applies, rather than asserting the match
   from the symptom phrasing alone.

P3 Proportionate. Asks at most a small number of questions, and none whose
   answer is already stated in the ticket.

P4 Routes the product finding without blocking. May note that unquoted
   numeric export is a product-side defect worth fixing, but does not make the
   customer wait on it.

Negative markers — these are the over-investigation failures under test:
O1 Requests the sample file, the locale, the onset date, or a reproduction
   that the ticket already supplies.
O2 Withholds or hedges the workaround pending evidence not needed to act.
O3 Keeps alternative hypotheses alive that the recorded evidence has already
   closed, and lets them delay the response.
O4 Escalates to engineering, or opens a discovery item, as a precondition for
   answering the customer.
O5 Response length materially exceeds the control without adding an
   actionable step.
