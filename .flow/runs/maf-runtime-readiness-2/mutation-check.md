# Mutation evidence: chartered MAF readiness fence

The covering regression is
`CharteredPreparationTests.test_unready_runtime_refuses_before_any_attempt_side_effect`
in `tests/test_chartered_delivery_gateway.py`.

Mutation performed on 2026-09-27: `runtime_identity = require_ready()` in
`prepare_chartered_delivery` was temporarily replaced with a fixed dictionary.
The command
`/opt/homebrew/bin/python3.12 -m unittest tests.test_chartered_delivery_gateway.CharteredPreparationTests.test_unready_runtime_refuses_before_any_attempt_side_effect`
then failed with `AssertionError: MafRuntimeUnready not raised`. The original
call was restored immediately after the observation.

The current focused verification runs the regression with the real fence in
place; it passes. This mutation uses only the fixture's temporary worktree and
has no provider, network, or project-worktree side effect.
