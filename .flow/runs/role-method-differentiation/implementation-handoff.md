# Implementation handoff: role-method differentiation repair

Implement the approved two-role replacement inside the existing run. Product-
manager owns time-sensitive sequencing; quality-reviewer owns Critical-finding
calibration. Remove the superseded corpus entries and the unselected role-body
additions. Do not change the passing lead-developer method.

Keep the first attempt's raw evidence unchanged. Put the new frozen manifest,
prompts, rubrics, and four arms per role under a separate `repair-2` directory.
Only a strict two-role pass closes the earlier five-role release gate.
