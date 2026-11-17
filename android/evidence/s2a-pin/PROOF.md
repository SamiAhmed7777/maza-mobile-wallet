# S-2a — PIN lock + hashed PIN storage + auto-lock timer + settings hook

Date: 2026-11-16 (loop 24a7311de928) · Code half of S-2 (S-2b = biometric +
BlueStacks device proofs). Spec: docs/SPEC.md Phase 5.5/5.6. Decision
record: DECISIONS.md D11 (app-security, NOT coin policy — no Payu routing).

## What shipped

| File | Change |
|---|---|
| android/src/com/mazawallet/crypto/Pbkdf2.java | NEW — PBKDF2-HMAC-SHA512 wrapper (platform SecretKeyFactory; the exact primitive Bip39.toSeed uses, on-device proven) |
| android/src/com/mazawallet/crypto/LockPolicy.java | NEW — pure-Java lock state machine: lazy inactivity lock, background-return lock, wrong-PIN backoff (5 fails -> 30s doubling, cap 15 min, THROTTLED refuses without hashing, streak survives auto-lock) |
| android/src/com/mazawallet/PinGuard.java | NEW — Android shell: MODE_PRIVATE prefs (salt hex / iter / hash hex / autolock_ms), SecureRandom salt, constant-time compare, char[] zeroing, throttled() reporting |
| android/src/com/mazawallet/MainActivity.java | MOD — lock overlay UI, PIN verify flow (worker thread), gates: WALLET tab + SEND action; dispatchTouchEvent activity tracking; onPause/onResume background lock; WALLET-tab SECURITY card (Set/Change/Remove PIN + auto-lock status = the S-4 settings hook); autoLockTick 10s cover |
| android/src/com/mazawallet/crypto/SelfTest.java | MOD — +25 checks: Pbkdf2 anchors + LockPolicy transitions (49 total, all PASS) |
| android/src/com/mazawallet/crypto/Hex.java | MOD — package-private -> public (PinGuard reuses it; pure Java) |
| DECISIONS.md | MOD — D11 decision record incl. accepted residuals |
| docs/SPEC-AUDIT.md | MOD — rows 4.5 + 4.6 GAP -> PARTIAL with evidence pointers |
| android/evidence/s2a-pin/ | NEW — this PROOF + transcripts |

## Security properties

- PIN never stored/logged; only salt + iteration count + 32-byte
  PBKDF2-HMAC-SHA512 verifier (210k iterations, OWASP guidance for
  PBKDF2-HMAC-SHA512) in app-private prefs; MessageDigest.isEqual
  constant-time compare; char[] zeroed after every use path.
- A process WITH a stored verifier starts LOCKED (LockPolicy.forSession):
  authentication is required at every fresh app start, not only after
  inactivity (judge r1 blocker — fixed).
- The background/resume policy bracket runs on EVERY resume, Connect
  screen included (judge r1 blocker — fixed): a long background is never
  missed just because the wallet UI was not built yet.
- THROTTLED refuses BEFORE any PBKDF2 work: PinGuard.verifyAttempt checks
  LockPolicy.throttleUntilMs() first (synchronized, single clock read) —
  the hash-free-throttle claim is now true in the shell, not just the
  policy (judge r1 blocker — fixed).
- Verifier-store states ABSENT/VALID/CORRUPT: a partial or corrupt store
  fail-CLOSES — the gate stays permanently engaged and can never read as
  "no PIN set" (judge r1 blocker — fixed). Recovery = app-data reset; the
  seed is independent (S-1 Keystore envelope).
- Clock = SystemClock.elapsedRealtime() (monotonic — wall-clock changes
  cannot stretch security windows; r1 polish, folded).
- Change/Remove REQUIRE the current PIN (also from the unlocked WALLET tab
  — defense-in-depth for a briefly-borrowed phone). Set requires min 4
  chars + typed-twice confirmation.
- Wrong-PIN throttle: THROTTLED refuses without evaluating the PIN; the
  streak resets ONLY on accept and survives auto-lock.
- Auto-lock is evaluated LAZILY at every gate check (isLocked(now) locks by
  itself), so a missed timer tick can never leave the gate open; the 10s
  tick only makes the cover appear. Background >= autolock locks on resume.
- Gate points: selectTab(WALLET) + doSend(); the WALLET-tab send card is
  behind the tab gate. With NO PIN set the app behaves exactly as before
  (gate inert — no regression to existing flows).
- Honest residuals (D11): verifier in prefs not Keystore-wrapped; backoff
  state memory-resident (process restart clears it); shell-level on-device
  tests land with S-2b — S-8 threat model revisits if stronger measures
  (persisted counters, Keystore-wrapped verifier) are warranted.

## Verification on the final bytes

RE-VERIFIED BY THE ADOPTING LOOP (24a7311de928, 2026-11-16 ~23:2x PST) after
the lane went >60m quiet: the lane's original transcripts predated its final
SelfTest/MainActivity writes (evidence 20:44 < sources 20:48-20:49), so the
counts below had drifted (PROOF said 45, transcripts said 47). Every check
below was RE-RUN on the final bytes by the adopting loop:

- Desktop selftest (stage 1/6 of the build): 49/49 PASS, exit 0
  (selftest.txt — regenerated from the final bytes). New checks vector-pin
  Pbkdf2 against (a) the official BIP39 TREZOR seed — itself a PBKDF2-
  HMAC-SHA512 output — and (b) direct anchors cross-derived with Python 3
  hashlib.pbkdf2_hmac (OpenSSL) — the tools/oracle.py independent-oracle
  pattern (anchors-derived.txt shows the derivation). LockPolicy
  transitions pinned with a fake clock. INDEPENDENT ORACLE RE-CHECK: the
  adopting loop re-derived ALL five anchors with Python hashlib before
  trusting the green selftest — all five byte-match (TREZOR seed,
  anchors A/B/C, wrong-pin divergence).
- Full APK build: SIGNED OK, 283604 bytes (build.txt — regenerated;
  apk sha256 e261c8c8dd197b12dbd777434135838ccb04834d8b722de6e8ff28c3ccd208bd)
  — javac vs android.jar is the compile proof for the Android-context
  classes the desktop selftest does not compile (PinGuard, MainActivity
  wiring).
- walletbench suite: Ran 216 tests, OK (skipped=4 — pre-existing
  electrumx-tree skips) (suite-tail.txt — regenerated). Backend untouched.
- Secret scan of the diff: zero token/seed/key-shaped hits. The PIN test
  vector "1234" is a pinned test anchor, not a credential.

## Polish fold (post-grade disclosure)

Grade of record: r1 B, ZERO blocking issues (direct-stdin Codex primary;
verdict recorded topic=codex-judge-verdict). Both r1 polish notes were
FOLDED into these commit bytes AFTER the grade — shipped bytes differ from
graded bytes in exactly two places:

1. docs/SPEC-AUDIT.md stale selftest counts (the judge's polish #1):
   row 4.3 "19-check" -> "49-check", row 4.5 "45/45" -> "49/49".
2. MainActivity.showPinSetPrompt (the judge's polish #2): invalid PIN input
   now keeps the dialog OPEN with the error inline (in-dialog errTv +
   post-show positive-button override) instead of dismissing with a Toast.
   No crypto/PinGuard/LockPolicy byte changed.

Post-fold re-verification on the final bytes: desktop selftest 49/49 exit 0
(full build re-run, SIGNED OK — see build.txt footer for the post-fold
artifact hash) and walletbench suite green (see suite-tail.txt footer).

## Verified-live toolchain finding (recorded in D11)

The repo's d8 (R8 8.2.2-dev) fails dexing ANONYMOUS inner classes and
nested enum classes with `NPE: Cannot invoke String.length()` (class named
in `origin:`). Lambdas + named classes dex fine. The two anonymous
DialogInterface.OnClickListener classes were converted to lambda
expressions; the codebase stays lambda-based. Cost: two build iterations,
caught before any judge round.

## Honest scope (what this tick does NOT claim)

- NO on-device proof: the BlueStacks proofs (lock on background/foreground,
  inactivity lock, wrong-PIN path, throttling UI) are S-2b's DONE
  criterion, per the backlog's S-2 split. Everything here compiles, passes
  the desktop selftest, and is policy-pinned by fake-clock tests.
- No attempt to gate the SEND tab's QR/receive surfaces (read-only — the
  spec gates spending/unlock, not viewing).
