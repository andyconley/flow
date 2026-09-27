# Spikes: step5-cancellation (2026-09-27, macOS arm64, local, no paid calls)

Script: session scratchpad `spike.py`. The results are observed.

## S1. Process start time source (F10 open question)

- **The macOS `sysctl` read works.** `sysctl` (`CTL_KERN, KERN_PROC, KERN_PROC_PID`), read through ctypes, gives `kp_proc.p_starttime` (a timeval at offset 0) with microsecond precision, for example `1790523514.199776`.
  - It is independent of timezone and locale.
  - For a dead pid the returned size is 0, and the reader returns `None`.
- **`ps -o lstart=` depends on the timezone** (observed with UTC against America/Los_Angeles: `15:38:34` vs `08:38:34`). It also has only one-second resolution. **Rejected.**
- **Linux:** `/proc/<pid>/stat` field 22 (start time in clock ticks since boot) plus `/proc/sys/kernel/random/boot_id`. CI does not run delivery tests (the CI workflows run only `test_archive*` and `test_expertise*`), so the Linux reader gets a parser unit test on fixture text and is **not validated on Linux**.
- **Machine id:** `ioreg -rd1 -c IOPlatformExpertDevice` exposes `IOPlatformUUID` (observed); on Linux it is `/etc/machine-id`.

**Implication:** R1 uses the sysctl timeval on macOS and the Linux `/proc` reader, stored canonically as a string: `darwin:<sec>.<usec>` or `linux:<boot_id>:<ticks>`.

## S2. Reaping group members after the leader exits (F11 spike)

- **The group outlives its leader.** A leader started with `start_new_session=True` spawned a child and exited. The child stayed alive, with `getpgid(child) == leader pid` (observed).
- **Members can be listed.** `ps -A -o pid=,pgid=,uid=` listed the member.
- **`os.killpg(pgid, SIGKILL)` killed it** (observed).
- **An empty group raises `ProcessLookupError`** from `killpg` (observed).
- **Member start times are readable** through S1's sysctl.

**Implication:** R4's reaping of a group whose leader is gone is feasible. Kill only members with the recorded pgid, the same uid, and a start time at or after the recorded leader start time. This guards against pgid reuse, which requires the old group to be empty and the pid to be reused. Treat `ProcessLookupError` as "already gone".
