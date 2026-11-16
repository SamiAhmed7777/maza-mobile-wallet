# M4 — Selftest gate in the build pipeline (evidence)

Gate: `build-apk.sh` stage `[1/6]` runs `android/selftest.sh` as the FIRST
build stage (only variable/path resolution precedes it — it runs before the
Android SDK/toolchain preflight checks; `selftest.sh` self-checks javac),
and the build aborts with exit 1 and a FATAL line BEFORE any packaging step
on any FAIL.

## Files

- `probe.sh` — the evidence generator. Safety design: hard exit BEFORE any
  mutation if SelfTest.java is dirty; byte backup of SelfTest.java + a
  restore trap on EXIT/INT/TERM (restores from the byte backup, never
  `git checkout --`); every step prints the command it runs plus its real
  output; 13 assertions; exits nonzero on any failure. Runs the build
  twice AND the walletbench suite, writing `suite-transcript.log` itself.
- `probe-transcript.log` — full output of one `probe.sh` run (13/13
  assertions PASS, exit 0).
- `trap-test.sh` + `trap-test-transcript.log` — deterministic proof that
  the restore trap works on interruption: the harness launches probe.sh,
  waits until the corruption is OBSERVED in the live tree (poll 2s), sends
  SIGTERM to the probe's own pid ($!, no pgrep guessing), ASSERTS the
  probe exited exactly 90 (the trap restore path — an assert, not a
  printed value), and verifies the tree byte-identical to the committed
  content. This transcript was produced by the CURRENT trap-test.sh and
  teed directly to this path (round-3 shipped a stale failed transcript
  from an earlier harness revision — fixed). Note recorded in the
  transcript: the probe is an async job, and POSIX sets SIGINT to SIG_IGN
  for async jobs (a signal ignored at entry cannot be trapped), so the
  trap is exercised via SIGTERM — same handler as INT. The transcript ends
  with the harness's own status lines, verbatim:
  "TRAP TEST RESULT: PASS" / "TRAP TEST EXIT CODE: 0".
- `suite-transcript.log` — written by probe.sh step 7 during the recorded
  run: 95 tests, OK (skipped=4 — pre-existing electrumx-integration skips),
  SUITE_RC=0.
- Superseded: round-1 hand-run transcripts and round-2's pre-suite probe
  were removed from the repo; every claim is re-proven by the current
  probe/trap transcripts.

## Probe result (probe-transcript.log, verbatim)

- 13 ASSERT PASS lines, 0 ASSERT FAIL
- forced-fail build exit code 1; gate FATAL line present; no [6/6] stage ran
- APK md5 unchanged after aborted build (summary line verbatim):
  "md5 before=f3fa859127c3d8701393acbb9d40ebf7 after-abort=f3fa859127c3d8701393acbb9d40ebf7 after-green=0e9b3766d046b640004cc99f514149ec"
- original vector restored / corrupted vector gone: 1 / 0
- green build exit code 0; selftest PASS=19 FAIL=0; SIGNED OK present
- walletbench suite exit code 0; suite OK line present
- The transcript's final THREE lines, quoted verbatim in their actual order:
  "## probe summary: FAILS=0"
  "md5 before=f3fa859127c3d8701393acbb9d40ebf7 after-abort=f3fa859127c3d8701393acbb9d40ebf7 after-green=0e9b3766d046b640004cc99f514149ec"
  "PROBE RESULT: ALL ASSERTIONS PASS"

## Corruption detail

One character of the expected RIPEMD-160("abc") hex constant inside
SelfTest.java (…15a0bfc → …15a0bfd) — compiles cleanly, fails the vector
check at runtime. The corruption exists ONLY inside the probe run; the
byte backup is verified restored and the corrupted constant asserted gone
before the green build. The dirty-tree guard test (refuse to start, no
mutation) and the interrupt-restore trap test are separate transcripts.
