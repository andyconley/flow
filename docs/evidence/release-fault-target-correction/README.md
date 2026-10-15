# Equivalent fault-injection harness correction

The first required release gate failed two crash-recovery tests because string-based mocks targeted a reloaded module instead of Flow’s executing module. The failure is retained. A bounded reproducer established the exact mismatch and same assertions pass when actual fault injection occurs.

The correction binds mocks to `flow.runstate`, explicitly places a detached module in the import cache during fault injection, and retains every exception, recovery, fresh-process and persistent-budget assertion. The fixed-timestamp target is corrected likewise. Production and frozen evaluation criteria are unchanged. Author and independent reviewer each passed the three affected checks. This is a legitimate equivalent harness repair, not a weakened success condition. See assessment.json and preserved logs.

Normal repository policy requires a new exact-SHA candidate gate after this corrective commit. The failed publisher was not rerun or bypassed; publication had been skipped. No new live-model evaluation round was started.
