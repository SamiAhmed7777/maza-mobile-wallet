# MAZA wallet - testing report

AUTHORITATIVE RESULTS: section 1.0 (merged tree). Sections 1.2-1.6 are
the writing lane's per-lane measurements at base 361af1c and are marked
SUPERSEDED; do not cite them as current.

Backlog item S-9. Consolidates the per-spec-phase test evidence for the MAZA
(MazaCoin) native Android wallet into one document, per docs/SPEC.md Phase 8
deliverable 11 and Phase 7 ("Document all functionality that remains
incomplete").

| Field | Value |
|---|---|
| Report date | 2026-11-17 (all timestamps UTC unless marked) |
| Changeset measured | branch `lane/s9-testing-report`, base commit `361af1c` (= origin/master) |
| Repo | maza-mobile-wallet |
| Test host | DNS2-class Linux build host (see 1.1) |
| Device used for device proofs | BlueStacks Pie64 emulator on SAMI-PC (see section 2; NOT re-run in this lane) |
| Governing spec | docs/SPEC.md (phases 4-8 + RULES 1-8) |
| Prior audit | docs/SPEC-AUDIT.md (compliance matrix) |

Two areas of this document are refreshed by the integrating parent after the
four parallel lanes merge:

- "Measured on this changeset (parent refreshes post-merge)" - re-run the
  three commands on the merged tree and replace the transcripts and the
  numbers table.
- "Statuses and incomplete list (parent updates post-merge)" - update the
  per-phase statuses and the INCOMPLETE list to reflect what actually merged
  (S-3 light mode, S-4 settings, S-8 security doc) and which device proofs
  are still outstanding.

Everything else in this report is evidence citation and should remain valid
across the merge.

## 0. Scope, method, status legend

Three classes of evidence are used, and they are kept separate on purpose:

1. Commands executed by this lane on this changeset (section 1). Raw output
   is embedded verbatim. These are the only numbers in this report that were
   produced by this lane.
2. Committed device / mainnet evidence packages under android/evidence/
   (section 2). These were produced on a real emulator and against MAZA
   mainnet in earlier graded commits; they are cited with their repo-relative
   paths and are re-checkable from the committed bytes.
3. Status synthesis against docs/SPEC.md (section 3). Each checklist row
   cites the code path, test, or evidence package that supports its status.

Status legend:

- PASS - implemented and proven by the cited evidence.
- PARTIAL - implemented and partly proven, or proven only in a subset of the
  required conditions. The missing piece is named in the row.
- PENDING - not implemented / not proven; owner item named.
- IN FLIGHT - being built on a parallel lane at the time of writing.

What this report is NOT:

- It contains no new device runs. This lane had no device or emulator access
  (shared rule: device proofs are the parent's step), so every on-device
  claim below is a citation of committed evidence, never a fresh run.
- It contains no new mainnet broadcasts and no testnet runs.
- It repeats no secret: no seed words, PIN values, tokens, or private
  endpoints appear here.

### 0.1 Documented drift found while writing this report

docs/SPEC-AUDIT.md rows "4.2 encrypted wallet storage", "4.4 OS secure
storage" and Phase 7 "encrypted wallet persistence" still say
"GAP -> S-1 ... seed currently app-private PLAINTEXT file". That is stale:
commit `d8b08ed` ("S-1 code half: encrypted seed at rest") landed
android/src/com/mazawallet/SeedVault.java (AndroidKeyStore AES-256-GCM,
MZAE1 envelope, legacy-plaintext migration) and its envelope is covered by
five passing selftest checks. This report marks those items PARTIAL on the
strength of the code plus selftest, and flags the device half (restart and
migration over the encrypted store) as still unproven. docs/SPEC-AUDIT.md is
outside this lane's territory, so it was NOT edited; it is listed as an
out-of-territory finding in the lane handoff.

## Measured on this changeset (parent refreshes post-merge)

Everything in this section was executed by this lane in
`/root/maza-mobile-worktrees/s9` at commit `361af1c`, with `TZ=UTC`. Nothing
in this section is quoted from an older run.

### 1.0 POST-MERGE REFRESH (parent, 2026-11-17, merged tree = 361af1c + all four lanes + judge-round fixes)

Parent re-ran the same commands on the MERGED tree (S-3/S-4/S-8/S-9 applied
plus the r1/r2 judge-round fixes) with TZ=UTC. Where these numbers differ
from 1.2-1.6 (which remain valid for base 361af1c), THIS subsection is
authoritative:

- Command 1 - Python suite: `Ran 253 tests ... OK (skipped=4)` (216 base +
  21 contrast tests incl. the expected-failure ledger gate + 7 settings
  resume/retune wiring tests + 9 post-merge additions; the 4 skips are the
  pre-existing ElectrumX integration self-skips - the pinned dependency is
  unavailable on this host; the contrast ledger is EMPTY since the wave-2
  reskin, so its former skip is gone).
- Command 2 - crypto self-test: `ALL 96 CHECKS PASSED` (49 base + 22 S-4
  checks + 13 settings-resume-gate checks + 12 pin-retune checks: window
  edges, streak/backoff untouched, in-session retune semantics, and the
  cross-activity bracket scenarios).
- Command 3 - APK build: `SIGNED OK`, 308337 bytes. APK HASH NOTE:
  apksigner output is not byte-reproducible, so every build has a different
  sha256; the recorded transcript run in TRANSCRIPTS.txt produced
  5662e0b767562683320d2d54dda07a0ef928f1f80444b31e580c92598a9487d0.
  "SIGNED OK + battery green on the same tree" is the invariant, not any
  single hash.
- Release battery (operator-side
  /root/.hermes/skills/maza-mobile-wallet/scripts/beta-gate.sh):
  `BATTERY-CLEAN` (PASS=13 FAIL=0).
- Merged changeset inventory (17 paths): docs/SECURITY.md,
  docs/TESTING-REPORT.md, docs/SPEC-AUDIT.md,
  android/res/values/{colors,styles,strings}.xml,
  android/res/layout/{activity_settings,view_wallet_manage}.xml,
  android/src/com/mazawallet/{ThemeController,SettingsActivity}.java,
  android/src/com/mazawallet/MainActivity.java,
  android/src/com/mazawallet/SeedVault.java,
  android/src/com/mazawallet/crypto/{LockPolicy,SelfTest,SettingsResumePolicy}.java,
  android/AndroidManifest.xml, tests/test_theme_contrast.py,
  tests/test_settings_resume_gate.py.

### 1.1 Environment

(The table below describes the WRITING LANE's run at base 361af1c; the
merged-tree runs recorded in section 1.0 used the same parent host and
toolchain. Section 1.0 is authoritative for current numbers.)

| Item | Value |
|---|---|
| Date of run | Tue Nov 17 11:13 UTC 2026 |
| Kernel | Linux 6.8.0-147-generic x86_64 |
| CPU count | 6 |
| Python | 3.14.9 (the interpreter that ran the suite) |
| JDK | javac 21.0.13.0.3 / OpenJDK 21.0.13.0.3 (2026-10-24) |
| Android build-tools | 34.0.0 (aapt2 2.19-10229193, d8 8.2.2-dev, apksigner 0.9) |
| Android platform jar | /opt/android-sdk/platforms/android-34/android.jar present |
| Timezone | TZ=UTC for every command below |

### 1.2 Command 1 - Python suite (SUPERSEDED for the merged tree - see 1.0)

```
$ cd /root/maza-mobile-worktrees/s9
$ export TZ=UTC
$ set -o pipefail; python3 -m unittest discover -s tests; echo "EXIT=$?"
```

Output (verbatim, tail; the run body prints one line per test):

```
----------------------------------------------------------------------
Ran 216 tests in 93.615s

OK (skipped=4)
EXIT=0
```

The 4 skips are pre-existing and are all in the ElectrumX integration class,
which self-skips when the pinned ElectrumX tree is not installed on the test
host. Verbatim skip reasons (`-v` run):

```
test_coin_class_registers_via_env_programmatic_path (test_chain_params.TestElectrumxIntegration...) ... skipped "pinned electrumx (dist 'e-x', git ee28cd8...) not installed"
test_env_accepts_coin_and_server_entry_point_passes_fixtures (test_chain_params.TestElectrumxIntegration...) ... skipped "pinned electrumx (dist 'e-x', git ee28cd8...) not installed"
test_pinned_tree_fingerprints (test_chain_params.TestElectrumxIntegration...) ... skipped "pinned electrumx (dist 'e-x', git ee28cd8...) not installed"
test_runner_check_only_validates_wiring (test_chain_params.TestElectrumxIntegration...) ... skipped "pinned electrumx (dist 'e-x', git ee28cd8...) not installed"
```

Observed noise, stated so nobody mistakes it for a failure: the run also
emits `ResourceWarning: unclosed <socket.socket ...>` lines on stderr, one
per in-process HTTP test server (the suite binds ephemeral loopback ports).
They do not affect the result; the exit code is 0.

### 1.3 Command 2 - crypto self-test (desktop JVM) (SUPERSEDED - see 1.0)

```
$ bash android/selftest.sh
```

Output (verbatim, complete):

```
Compiling android/src/com/mazawallet/crypto ...
Running SelfTest ...

-- BIP39 (official Trezor vectors)
PASS bip39 entropy 0x00.. -> mnemonic
PASS bip39 entropy 0x7f.. -> mnemonic
PASS bip39 seed(mnemonic, TREZOR)
PASS bip39 seed(mnemonic, "")
-- RIPEMD-160 (spec test vectors)
PASS ripemd160("")
PASS ripemd160("abc")
PASS ripemd160(quick brown fox)
-- Base58Check
PASS base58check roundtrip
PASS base58check leading zeros
-- BIP32 (bip-0032 Test Vector 1)
PASS bip32 xprv m
PASS bip32 xprv m/0'
PASS bip32 xprv m/0'/1
-- MAZA profile (canonical mnemonic seed, coin 13)
PASS maza address m/44'/13'/0'/0/0
PASS maza address m/44'/13'/0'/0/1
PASS maza address m/44'/13'/0'/0/2
PASS maza WIF m/44'/13'/0'/0/0
PASS maza p2pkh scriptPubKey
-- BTC cross-check (same mnemonic, m/44'/0'/0'/0/0, version 0x00)
PASS btc address m/44'/0'/0'/0/0
-- TxBuilder (legacy P2PKH, SIGHASH_ALL)
PASS txbuilder sign + verify
-- SeedCryptAes (at-rest envelope)
PASS seedcrypt blob = 12B IV + plain + 16B tag
PASS seedcrypt random IV per encryption
PASS seedcrypt round trip
PASS seedcrypt tamper rejected
PASS seedcrypt wrong key rejected
-- Pbkdf2 (S-2a PIN verifier primitive)
PASS pbkdf2 reproduces BIP39 TREZOR seed
PASS pbkdf2 anchor A (210k iters, hashlib-cross-derived)
PASS pbkdf2 salt sensitivity
PASS pbkdf2 iteration sensitivity
PASS pbkdf2 wrong-pin divergence
-- LockPolicy (S-2a PIN lock state machine)
PASS lock: starts unlocked
PASS lock: inside window unlocked
PASS lock: fires at inactivity deadline
PASS lock: stays locked without activity
PASS lock: activity alone cannot unlock
PASS lock: activity extends deadline
PASS lock: short background stays unlocked
PASS lock: long background locks on resume
PASS lock: manual lockNow engages
PASS lock: wrong pin -> WRONG_PIN
PASS lock: 5th consecutive wrong -> WRONG_PIN (backoff opens after)
PASS lock: 6th attempt within backoff -> THROTTLED
PASS lock: throttle window reported
PASS lock: backoff expiry re-allows (30s base)
PASS lock: accept unlocks and resets streak
PASS lock: fresh 4 wrong then expiry keeps streak
PASS lock: session with verifier starts locked
PASS lock: session without verifier starts unlocked
PASS lock: tap after deadline locks before it counts
PASS lock: in-window tap still extends deadline

ALL 49 CHECKS PASSED
```

Exit code 0.

### 1.4 Command 3 - APK build (raw aapt2/javac/d8/apksigner pipeline) (SUPERSEDED - see 1.0)

```
$ bash android/build-apk.sh
```

Output (verbatim, complete):

```
[1/6] crypto selftest (gate - any FAIL aborts the build before packaging)
Compiling android/src/com/mazawallet/crypto ...
Running SelfTest ...

-- BIP39 (official Trezor vectors)
PASS bip39 entropy 0x00.. -> mnemonic
PASS bip39 entropy 0x7f.. -> mnemonic
PASS bip39 seed(mnemonic, TREZOR)
PASS bip39 seed(mnemonic, "")
-- RIPEMD-160 (spec test vectors)
PASS ripemd160("")
PASS ripemd160("abc")
PASS ripemd160(quick brown fox)
-- Base58Check
PASS base58check roundtrip
PASS base58check leading zeros
-- BIP32 (bip-0032 Test Vector 1)
PASS bip32 xprv m
PASS bip32 xprv m/0'
PASS bip32 xprv m/0'/1
-- MAZA profile (canonical mnemonic seed, coin 13)
PASS maza address m/44'/13'/0'/0/0
PASS maza address m/44'/13'/0'/0/1
PASS maza address m/44'/13'/0'/0/2
PASS maza WIF m/44'/13'/0'/0/0
PASS maza p2pkh scriptPubKey
-- BTC cross-check (same mnemonic, m/44'/0'/0'/0/0, version 0x00)
PASS btc address m/44'/0'/0'/0/0
-- TxBuilder (legacy P2PKH, SIGHASH_ALL)
PASS txbuilder sign + verify
-- SeedCryptAes (at-rest envelope)
PASS seedcrypt blob = 12B IV + plain + 16B tag
PASS seedcrypt random IV per encryption
PASS seedcrypt round trip
PASS seedcrypt tamper rejected
PASS seedcrypt wrong key rejected
-- Pbkdf2 (S-2a PIN verifier primitive)
PASS pbkdf2 reproduces BIP39 TREZOR seed
PASS pbkdf2 anchor A (210k iters, hashlib-cross-derived)
PASS pbkdf2 salt sensitivity
PASS pbkdf2 iteration sensitivity
PASS pbkdf2 wrong-pin divergence
-- LockPolicy (S-2a PIN lock state machine)
PASS lock: starts unlocked
PASS lock: inside window unlocked
PASS lock: fires at inactivity deadline
PASS lock: stays locked without activity
PASS lock: activity alone cannot unlock
PASS lock: activity extends deadline
PASS lock: short background stays unlocked
PASS lock: long background locks on resume
PASS lock: manual lockNow engages
PASS lock: wrong pin -> WRONG_PIN
PASS lock: 5th consecutive wrong -> WRONG_PIN (backoff opens after)
PASS lock: 6th attempt within backoff -> THROTTLED
PASS lock: throttle window reported
PASS lock: backoff expiry re-allows (30s base)
PASS lock: accept unlocks and resets streak
PASS lock: fresh 4 wrong then expiry keeps streak
PASS lock: session with verifier starts locked
PASS lock: session without verifier starts unlocked
PASS lock: tap after deadline locks before it counts
PASS lock: in-window tap still extends deadline

ALL 49 CHECKS PASSED
[2/6] aapt2 compile
[3/6] aapt2 link
[4/6] javac
[5/6] d8
[6/6] apksigner
SIGNED OK: /root/maza-mobile-worktrees/s9/android/maza-wallet-bench.apk (283604 bytes)
```

Exit code 0. Artifact identity of the APK this lane produced:

```
$ sha256sum android/maza-wallet-bench.apk
108aa750e528863fc0a36343477e9cf7a2849fea03fb2052f92b119d87bf6327  android/maza-wallet-bench.apk
$ ls -l android/maza-wallet-bench.apk
-rw-r--r-- 1 root root 283604 Nov 17 11:02 android/maza-wallet-bench.apk
```

Notes that matter for honesty:

- This is the bench/debug build (manifest versionCode 1 / versionName 1.0,
  debug keystore). It is signed and installable but it is NOT the release
  artifact; the release line is `bash android/build-apk.sh --release`
  (versionCode 3 / versionName 1.1.0 from android/release.properties, release
  keystore, zipaligned). The release build was not re-run in this lane
  because it needs the off-repo release keystore; its evidence is committed
  (section 2.5).
- The APK sha256 above is unique to this build. apksigner output is not
  byte-reproducible across builds, so a re-run on the merged tree will
  produce a DIFFERENT hash. The invariant to re-check is "SIGNED OK" plus
  the self-test gate passing, not hash equality.
- The build rewrote the tracked file android/maza-wallet-bench.apk.idsig (the
  signature-scheme carrier). This lane restored it to the committed bytes
  after the run, so the worktree contains only the new report.

### 1.5 Independent re-verification performed in this lane

Three checks were run against committed evidence bytes, by this lane, to
avoid repeating earlier claims on trust alone.

(a) Mainnet self-custody transaction, structural re-parse of the committed
raw hex (txid recomputed with double-SHA256 over the 226-byte serialization;
output scripts decoded with MAZA P2PKH version byte 50):

```
txid(recomputed): ce514b350d2c2dc362b8cea0babc9ac64b8261b547142cc93a94ae366350cd4e
version 1 inputs 1
 in 7a0af47a1d3c1f8a6b83885baf473d9f6a7a0ff8ccfe39b658cdd23d2e5fcc34 vout 1 scriptSig 107 bytes
outputs 2
 out 0 0.50000000 MAZA MV9wCMvTwf2TzRRnaSt3hnLjNktv2Z2AGt  (version 50, MATCH)
 out 1 1.49990000 MAZA MRfcWqfdXjgJYCY8s1BbjrpNpemgTY1q9h  (version 50, MATCH)
locktime 0 consumed 226 of 226
```

(b) Signature gate re-run on the same bytes with the repo's own verifier
(tools/txverify.py, `ecdsa` 0.19.2 in a scratch virtualenv outside the repo):

```
$ /path/to/venv/bin/python tools/txverify.py "$(cat android/evidence/selfcustody-proof/sent-tx-hex.txt)" 0 76a914a8d1e31cee7692a99dc10bdd8d36a7da9f2bde3288ac
tx: version=1 inputs=1 outputs=2 locktime=0 consumed=226/226 bytes
pubkey 03b962f74b70283d... -> address MPHoBsbsNUduo7fsvMCREpDSMWpyeUxq2H
s value: LOW (ok)
SIGNATURE: VALID
  output 0: 0.50000000 MAZA script=76a914e925ffcf7e89ff8082be95...
  output 1: 1.49990000 MAZA script=76a914c2e2616a0e8078cdb83b66...
EXIT=0
```

Meaning: the embedded public key hashes to the app's own receive address
index 0 (`MPHoBsbs...`, m/44'/13'/0'/0/0), the signature is valid, and the
S value is LOW (BIP62). The signature was produced by the device-side key,
not by the server.

(c) Integrity manifest of the PIN device-proof package:

```
$ cd android/evidence/s2b-pin
$ sha256sum -c SHA256SUMS | grep -c ": OK$"
47
$ sha256sum -c SHA256SUMS > /dev/null; echo "EXIT=$?"
EXIT=0
```

All 47 manifest entries verify OK and the check exits 0. The package
directory holds 48 files; the manifest does not list itself.

### 1.6 Numbers at a glance (this changeset) (SUPERSEDED - see 1.0)

| Measurement | Value |
|---|---|
| Python suite | 216 tests, 0 failures, 0 errors, 4 skips, 93.615 s, exit 0 |
| Crypto self-test | 49 checks, 49 PASS, 0 FAIL, 10 sections, exit 0 |
| APK build | 6/6 stages, self-test gate green, SIGNED OK, 283604 bytes |
| APK sha256 (bench build, this run only) | 108aa750e528863fc0a36343477e9cf7a2849fea03fb2052f92b119d87bf6327 |
| Evidence packages committed | 9 under android/evidence/ |
| Files committed as evidence | 134 |
| Java sources in the app | 17 under android/src |
| Third-party runtime libraries in the APK | 0 |

### 1.7 What the suite actually covers

Inventory at this changeset (measured):

Counted with the loader (not by grepping `def test_`), so inherited cases are
included:

| Module / class | Test cases |
|---|---|
| tests/test_walletbench.py - BenchTestCase (base suite: auth, state, QR, send guards, caps, NaN/shape rejection, cold-start address stability) | 31 |
| tests/test_walletbench.py - TestSelfCustody (base suite + watch import/utxos/history, broadcast validation, self-custody surfaces) | 43 |
| tests/test_walletbench.py - TestBookReconcile (base suite + funding reconciliation, rollback/commit phase semantics) | 47 |
| tests/test_walletbench.py - TestWatchImportAccessLog (base suite + count-only access log) | 36 |
| tests/test_walletbench.py - TestReconcileAccessLog (base suite + reconcile access log) | 33 |
| tests/test_walletbench.py - TestChainAdapter (RPC surface, exact-balance fee edge) | 4 |
| tests/test_walletbench.py - TestPersistPhaseSemantics (rename/dirsync failure phases) | 2 |
| tests/test_chain_params.py - TestPowTypeDispatch | 5 |
| tests/test_chain_params.py - TestHeaderHashAgainstLiveChain | 4 |
| tests/test_chain_params.py - TestChainConstants | 3 |
| tests/test_chain_params.py - TestVendoredProvenance | 1 |
| tests/test_chain_params.py - TestElectrumxIntegration (4 of these skip on this host) | 7 |
| Total | 216 |

Reading note (honest): the four BenchTestCase subclasses re-run the inherited
base suite, so the 216 count includes repeated executions of the same base
assertions. The distinct behaviours added by the subclasses are the
self-custody, reconciliation, and access-log properties named above. The
direction of travel is favourable (defensive duplication), but the number
should not be read as 216 distinct properties.

Separately, android/selftest.sh is the crypto gate: 49 vector-pinned checks
across BIP39, RIPEMD-160, Base58Check, BIP32, the MAZA coin profile, a BTC
cross-check, TxBuilder signing, the at-rest seed envelope (SeedCryptAes),
PBKDF2 anchors, and the LockPolicy state machine. It compiles only
android/src/com/mazawallet/crypto, so Android-context classes (PinGuard,
SeedVault, MainActivity, SelfCustody) are compile-proven by the javac stage
of the APK build, not by the self-test.

Tooling used for cross-checks lives in tools/ (oracle.py for independent
BIP39/BIP32/address derivation, txverify.py for offline SIGHASH_ALL + ECDSA
verification); both are developer instruments, not shipping code.

## 2. Committed device and mainnet evidence (cited, not re-run here)

All paths are repo-relative. Device proofs were recorded on BlueStacks Pie64
(Android 9, 1600x900, adb device emulator-5554) on SAMI-PC in earlier graded
commits; each package carries a PROOF.md, and the PIN package additionally
carries a SHA256SUMS manifest that this lane verified (section 1.5c).

### 2.1 Mainnet sends (both authorized, both capped)

| Send | Amount | Signed by | Txid | Authorisation |
|---|---|---|---|---|
| First user-initiated send, from the app's SEND tab (bench account, server-held funds) | 1.0000 MAZA to `MLRe5sWp7LE3skDMQhFbkfd2n5XcZdpKMs` | bench server (server-side funds, 50 MAZA cap) | `c3ceb87e...` (abbreviated as committed) | Sami-directed; recorded in DECISIONS.md D9 |
| Self-custody send, signed on the device from the app's own seed | 0.50000000 MAZA to `MV9wCMvTwf2TzRRnaSt3hnLjNktv2Z2AGt`; change 1.49990000 MAZA to `MRfcWqfdXjgJYCY8s1BbjrpNpemgTY1q9h` (m/44'/13'/0'/1/0) | the phone (keys never leave the device) | `ce514b350d2c2dc362b8cea0babc9ac64b8261b547142cc93a94ae366350cd4e` | Sami-directed; offline-verified before broadcast |

Evidence for row 2: android/evidence/selfcustody-proof/PROOF.md,
sent-tx-hex.txt (raw bytes), sent-tx-raw.json (node capture), and
txverify-output.txt. The 226-byte, 1-in-2-out shape and both output amounts
were independently re-derived in this lane (section 1.5a-b). The 1 MAZA send
is the anchor transaction that proves tools/txverify.py accepts a real
MazaCore-signed transaction (so a VALID verdict on the self-custody send is
meaningful); it is a bench-account send, not a self-custody signature, and
this report does not conflate the two.

Both sends are visible in the app's HISTORY view (HISTORY rows with
timestamps in android/evidence/selfcustody-proof/sc_send.png and in the
M22b dumps).

### 2.2 M21 - unlock-path watch re-import (device proof)

Path: android/evidence/m21-unlock-reimport/ (PROOF.md, RUN2-TRANSCRIPT.txt,
ur2a.xml, ur2b.xml, screenshots).

What was proven: the wallet re-imports its full 40-address watch window as
part of the UNLOCK action itself, with no tab navigation, so a wallet whose
creation-time import was interrupted recovers on the next unlock instead of
staying blind for the session.

Device-side facts as committed (run 2, all UTC): force-stop at 13:03:03.5,
`am start` at 13:03:16.2, token entry 13:03:36-51.8, CONNECT (the unlock) tap
at 13:03:51.8, then no input at all; server journal line
`WATCH_IMPORT seq=5 imported=40 status=200` at 13:04:05 (13.2 s after the
unlock tap, before any tab interaction); a second line `seq=6 imported=40` at
13:04:43 after the WALLET tab tap at 13:04:32.7. The two lines separate the
two triggers in one session. WALLET tab then rendered BALANCE 1.4999 MAZA
with receive card index 2 (`MGo1gjPrj2GDnbwcyRBJMaZ4GJMEAaVkU8`), corroborated
by uiautomator dump ur2b.xml and by the committed screenshot.

Scope caveat carried from the proof: "fresh" means a fresh app PROCESS over
preserved app data, not `pm clear` (which would destroy the on-device seed
that exists only in Sami's backup). A literal fresh-install recovery proof is
still outstanding and is listed as incomplete.

### 2.3 M22 - SEND / WALLET flow separation (code probes + device proof)

Paths: android/evidence/m22a/ (probe-transcript.txt, run-probe.sh,
SelectTabGuardProbe.java) and android/evidence/m22b/ (PROOF.md,
EVIDENCE-RAW.md, RUN-TRANSCRIPT.md, five screenshots, seven uiautomator
dumps).

M22a (desktop probes, 18 checks, ALL CHECKS PASSED) pinned the navigation
semantics: unlock performs exactly one fetch; switching to SEND does not
refresh; navigating to BALANCE and HISTORY does refresh; self-tapping the
selected tab does not refresh; reconnect from a non-BALANCE tab performs
exactly one fetch; and a discriminator check shows the pre-fix code
double-fetches on reconnect.

M22b (on device, commit 26a962b, APK sha256 e9cb8e5c..., installed base.apk
md5 identical to the host build) proved:

- SEND tab renders `SEND - BENCH ACCOUNT` with the note "Spends the bench
  server's held funds (server-side, capped). Your own seed wallet is on the
  WALLET tab." (send-tab-bench-account.png, dump-send-tab.xml).
- WALLET tab send card renders `SEND - SELF-CUSTODY` with the note "Signed on
  this device from your own seed balance." (wallet-send-self-custody.png,
  dump-wallet-send-card.xml), under `My Wallet` / "Self-custody - keys never
  leave this device" / 1.4999 MAZA.
- Balance refresh on navigation is poll-excluding: Last-sync advanced +5 s
  and +6 s across two BALANCE->SEND->BALANCE round trips, which the 15 s
  background poll cannot produce (dump-refresh-s1/s2/s3.xml).

### 2.4 S-2a / S-2b - PIN lock (code + device proof)

Code and policy evidence: android/evidence/s2a-pin/PROOF.md (build.txt,
selftest.txt, suite-tail.txt, anchors-derived.txt). Implementation:
android/src/com/mazawallet/PinGuard.java (MODE_PRIVATE verifier store,
fail-closed ABSENT/VALID/CORRUPT states, constant-time compare, char[]
zeroing), crypto/LockPolicy.java (lazy inactivity lock, background-return
lock, 30 s doubling backoff to a 15 min cap, THROTTLED refuses before any
hash), crypto/Pbkdf2.java (PBKDF2-HMAC-SHA512, 210k iterations, anchors
cross-derived with Python hashlib), and the MainActivity lock overlay with
gating on the WALLET tab and on send.

Device evidence: android/evidence/s2b-pin/PROOF.md plus its 48-file artifact
set (PROOF.md, transcript.md, provenance.txt, SHA256SUMS, 17 uiautomator
dumps, 14 screenshots and the deterministic driving scripts; the manifest was
verified in this lane, section 1.5c):

| Proof | Device observation |
|---|---|
| P1 fresh session starts locked | after CONNECT with zero tab taps and zero idle time, "Wallet locked" overlay is up (s3-immediately-locked.png, ui-immediately-locked.xml) |
| P2 wrong PIN | "Wrong PIN - try again." with field cleared (s4-wrong1.png, ui-wrong1.xml) |
| P3 throttle | engaged after 5 consecutive failures ("wait 9s"), doubling rendered ("wait 113s" of a 120 s window), correct PIN REFUSED during a live window without evaluation (single-script chain ui-ref2-pre.xml -> press -> ui-ref2-post.xml), acceptance after the window drained (ui-accepted.xml) |
| P4a inactivity lock | 5 m 10 s with zero input while the 15 s poll kept syncing -> overlay up (ui-inactivity-locked.xml, s10-idle-locked.png, device clock 1:39 -> 1:45) |
| P4b background-return lock | one driver: unlocked -> launcher foregrounded (root package com.uncube.launcher3) -> 330 s backgrounded -> `am start` -> overlay up (ui-p4b-pre/unlocked/launcher/resumed.xml, s13/s14 with device clocks 2:13 -> 2:19) |

The 15-minute backoff CAP value rests on the desktop-pinned LockPolicy
constants, not on a device render; the PIN package says so explicitly and
this report repeats it rather than upgrading it.

### 2.5 Build-pipeline and release evidence

- Gate: android/evidence/selftest-gate/PROOF.md. A mutation probe (13
  assertions, all PASS) corrupts SelfTest, proves the build refuses with exit
  1 and a FATAL line before any packaging stage, proves the APK md5 is
  unchanged after the aborted build, and restores the tree byte-identically
  (plus a SIGTERM trap test). This is why a green build can be trusted as a
  crypto-correctness signal.
- Release line: android/evidence/m5-release-build/PROOF.md with
  build-transcript.txt, badging.txt, secret-scan.txt, verify-battery.txt.
  Evidence of record: release keystore (separate from debug), version
  injection via aapt2 `--replace-version`, zipalign, apksigner v2+v3, and a
  signed v1.0.0 artifact sha256
  `d30a48a9b6ccf04708d51b7494ccebff3d88aafe97e2bad894afd299f4bd1b77`
  (badging: versionCode 2, versionName 1.0.0, minSdk 24, targetSdk 34).
  android/release.properties in this changeset already carries versionCode=3 /
  versionName=1.1.0, so the next `--release` build yields
  android/releases/maza-wallet-v1.1.0.apk. That directory is gitignored and
  no release build was produced in this lane, so no v1.1.0 hash is claimed
  here.
- Installability: the bench APK built in this lane is signed (apksigner,
  "SIGNED OK") and its minSdk 24 / targetSdk 34 range covers the device class
  used for every proof (Android 9 / API 28 emulator). It was NOT installed in
  this lane; real-phone install is still outstanding (M6).

### 2.6 Evidence package inventory

Nine packages under android/evidence/ (134 files total, measured):

| Package | Proves |
|---|---|
| selfcustody-proof/ | on-device seed creation, oracle cross-check, 40-address watch import, mainnet self-custody send + offline signature gate |
| s2a-pin/ | PIN lock code half: policy, verifier primitive, rebuild transcripts |
| s2b-pin/ | PIN lock device half: locked start, wrong PIN, throttle, refusal, acceptance, inactivity lock, background-return lock |
| m21-unlock-reimport/ | unlock-path watch re-import on device |
| m21-watch-import-log/ | count-only WATCH_IMPORT access log (never addresses/tokens) |
| m22a/ | navigation-refresh and tab-separation code probes |
| m22b/ | SEND/WALLET flow separation on device + poll-excluding refresh |
| m5-release-build/ | release keystore, version injection, signed release artifact |
| selftest-gate/ | build refuses on broken crypto; tree restored byte-identically |

## Statuses and incomplete list (parent updates post-merge)

Statuses below reflect the parent-reconciled post-merge state (all four
lanes landed 2026-11-17; rows the lanes wrote as IN FLIGHT have been
updated to what actually merged). The INCOMPLETE list at the end carries
what is still outstanding (wave-2 reskin, device proofs, S-5/S-6, biometric).

### 3.1 Phase 4 - security requirements

| Item | Status | Evidence / what is missing |
|---|---|---|
| 4.1 local private-key custody | PASS | android/src/com/mazawallet/SelfCustody.java (seed and keys on device); backend is watch-only (walletbench/api.py never receives keys); mainnet proof android/evidence/selfcustody-proof/PROOF.md |
| 4.2 encrypted wallet storage | PARTIAL | Code shipped: android/src/com/mazawallet/SeedVault.java (AndroidKeyStore AES-256-GCM, MZAE1 envelope, atomic staged writes, legacy-plaintext migration) + crypto/SeedCryptAes.java; 5 envelope checks pass in the 49-check selftest. Missing: on-device restart + legacy-migration proof over the encrypted store (S-1 device half) |
| 4.3 secure seed generation + recovery | PASS | crypto/Bip39.java with official Trezor vectors (build stage 1/6); on-device 12-word creation in selfcustody-proof/PROOF.md step 1; import path SelfCustody.java (ST_IMPORT / renderImport) |
| 4.4 OS secure storage where available | PARTIAL | Keystore-held non-exportable AES key for the seed (SeedVault, alias maza_seed_wrap). The PIN verifier lives in MODE_PRIVATE prefs, not Keystore-wrapped (documented residual, DECISIONS.md D11) |
| 4.5 PIN or biometric unlock | PARTIAL | PIN: PASS on device (android/evidence/s2b-pin/PROOF.md). Biometric: NOT IMPLEMENTED (S-2b part 2) |
| 4.6 auto-lock after inactivity | PASS | crypto/LockPolicy.java + PinGuard.java (default 5 min, lazily evaluated, background-return lock); device proofs: 5 m 10 s idle lock and 330 s background-return lock (section 2.4) |
| 4.7 accidental key-exposure protection | PARTIAL | Seed shown once at creation (SelfCustody renderSeed); bench token field masked and memory-only. LANDED 2026-11-17 (S-4): auth-gated seed re-show (PinGuard verify + FLAG_SECURE + scrub on dismiss) and wipe (double-confirm, typed WIPE, current-PIN re-verified immediately before destruction, Keystore wrap-alias removed best-effort); device proofs pending |
| 4.8 secure transaction signing | PASS | crypto/TxBuilder.java (v1 P2PKH, SIGHASH_ALL, RFC6979 nonces, low-S); signature re-verified in this lane (section 1.5b); mainnet tx ce514b35... |
| 4.9 input validation / address verification | PASS | SelfCustody amount checks (positive, finite); crypto/Base58Check.java checksum verify; walletbench/api.py isfinite + own-address refusal; walletbench/chain.py validateaddress |
| 4.10 malicious-tx construction protection | PASS (structural) | No raw/imported-transaction path exists: the app constructs and signs from its own primitives; the server relays client-signed hex only and cannot alter construction |
| keys/seeds never to external servers | PASS | Watch-only backend by design; zero third-party runtime code in the APK; token never placed in URLs (Api.java) |
| never log secrets | PASS | walletbench emits count-only WATCH_IMPORT lines (walletbench/api.py); no seed/key material in app logs; PIN never logged (PinGuard) |
| no custodial wallet infrastructure | PASS | The wallet is non-custodial; walletbench is a separate, token-gated, capped TEST harness, not the wallet's backend path |

### 3.2 Phase 5 - mobile application experience

| Item | Status | Evidence / what is missing |
|---|---|---|
| dark display mode | PASS | Default palette rendered on device in the M21/M22b screenshots |
| light display mode | DONE code (2026-11-17, wave 2) — device proof pending | android/res/values colors.xml + styles.xml (both palettes; dark byte-identical, frozen DARK_RENDER_BASELINE), ThemeController (UI_MODE_NIGHT_MASK), UiTheme palette resolution across ALL screens (15 constants / 113 sites converted; zero ARGB literals in MainActivity/SelfCustody), contrast ledger EMPTY (machine-checked gate), PIN dialogs + dialog themes palette-driven; known residual: live theme-switch repaint of MainActivity = backlog item W3-a; device screenshots pending |
| mobile-first responsive layout | PARTIAL | Programmatic single-activity layout proven at 1600x900 emulator resolution; no proof at phone form factors |
| large readable balance | PASS | BALANCE tab and WALLET tab balance cards (m21/m22b dumps) |
| easy QR scanning | PENDING (M8) | No camera or scan code in android/src (grep-verified absent) |
| minimal send/receive steps | PASS | SEND form and RECEIVE card with QR (dump-send-tab.xml, wallet-tab-top.png) |
| clear transaction confirmations | PARTIAL | Send result line plus timestamped history rows today; richer confirmation copy is optional polish (S-4 landed 2026-11-17) |
| nav: dashboard | PASS | BALANCE tab (MainActivity TABS index 0) |
| nav: send | PASS | SEND tab (index 2) |
| nav: receive | PASS | RECEIVE tab (index 1) |
| nav: transactions | PASS | HISTORY tab (index 3) |
| nav: wallet management | DONE (S-4, 2026-11-17) | SettingsActivity WALLET MANAGEMENT page: receive addresses, PIN-gated seed re-show (FLAG_SECURE), double-confirm + typed-WIPE wipe with current-PIN re-verification and Keystore alias cleanup; device screenshots pending |
| nav: settings | DONE (S-4, 2026-11-17) | SettingsActivity from the SECURITY card: endpoint editor (same saved URL pref), auto-lock 5/10/30 min applying IMMEDIATELY (in-session retune via PinGuard.retuneAutolockMs, wave 2), theme selector System/Light/Dark via ThemeController; device screenshots pending |
| ordinary-user intuitiveness | PARTIAL | Plain-language pass done (BENCH ACCOUNT vs SELF-CUSTODY wording, fee shown); S-3/S-4 landed, app-wide light reskin landed (wave 2); on-device UX proofs + live theme-switch repaint pending |
| native MAZA branding | PASS | Branded header and launcher icons (branding/, mipmap-*) |

### 3.3 Phase 6 - blockchain connectivity

| Item | Status | Evidence / what is missing |
|---|---|---|
| native MAZA only | PASS | SLIP-44 coin 13, m/44'/13'; no wrapped or substitute asset anywhere (DECISIONS.md) |
| evaluate: existing full-node software | PASS | MazaCore 0.16.3 live on the operator host; vendored excerpts sha-pinned (DECISIONS.md, tests/test_chain_params.py TestVendoredProvenance) |
| evaluate: compatible RPC interfaces | PASS | mazad RPC surface used and cited (validateaddress, listunspent, getrawtransaction; walletbench/chain.py) |
| evaluate: existing blockchain explorers | PASS (conclusion) | No third-party explorer dependency taken; balance/history are served self-hosted |
| evaluate: available public infrastructure | PASS (conclusion) | None suitable for MAZA; hence self-hosting (README "Why") |
| evaluate: lightweight synchronization | IN FLIGHT | ElectrumX light-client protocol chosen; coin profile indexer/maza_coin.py, pinned kit docs/electrumx/, deploy recipe present; serving depends on the txindex decision below |
| evaluate: self-hosted infrastructure | PASS (decision) | Public TEST endpoint documented in deploy/PUBLIC-HOSTING.md |
| prefer decentralized architecture | IN FLIGHT | ElectrumX is the multi-server light-wallet protocol by design; single-node deployments are instances of the same recipe |
| RPC backend separated from app + documented | PASS | walletbench is a separate host process with its own token env file and never ships in the APK; security requirements documented in deploy/PUBLIC-HOSTING.md |
| no new blockchain/token/substitute network | PASS | Same as "native MAZA only"; DECISIONS.md |
| wallet interacts with actual native MAZA | PASS | Mainnet tx ce514b35... (section 2.1) |
| derivation scheme documented, desktop import | PARTIAL | m/44'/13' (SLIP-44) is documented and oracle-verified; MazaCore desktop wallets use m/0'/0'/k and store a raw HD seed, so wallet.dat import is a PLANNED lane, not implemented (DECISIONS.md D3) |
| txindex prerequisite for ElectrumX | OPEN - decision gate | The mainnet mazad lacks txindex and ElectrumX refuses index-less daemons; option (a) in-place reindex (~1-3 h with a bridge RPC window) vs (b) a second txindex node (~12-36 h sync) is a product decision (spec-audit row; decision gates now route to Payu per PLAN.md) |
| decentralized, no single centralized service | IN FLIGHT | Depends on the txindex row above; the design supports multiple independent servers |

### 3.4 Phase 7 - testing and validation (the spec's own list)

| Item | Status | Evidence / what is missing |
|---|---|---|
| new wallet creation | PASS | On-device 12-word creation with Python-oracle cross-check (android/evidence/selfcustody-proof/PROOF.md) |
| wallet import and restoration | PARTIAL | In-app seed import path exists (SelfCustody ST_IMPORT / renderImport, PIN-gated). A device proof of restoring a wallet on a wiped install is blocked on Sami's explicit go (it destroys the only on-device copy of the seed) |
| address generation | PASS | crypto/Bip44Maza.java (m/44'/13') with oracle and selftest vectors; three receive addresses observed in sequence on device (M21 evidence) |
| address validation | PASS | crypto/Base58Check.java checksum verify + walletbench/chain.py validateaddress; suite covers invalid-shape rejection |
| balance retrieval | PASS | Live balances rendered on device: 46.9998774 MAZA (bench account) and 1.4999 MAZA (self-custody) |
| transaction history | PASS | HISTORY tab timestamped rows (/api/watch/history); after-send row visible in sc_send.png |
| transaction construction | PASS | crypto/TxBuilder.java; 226-byte 1-in-2-out construction re-parsed in this lane (section 1.5a) |
| transaction signing | PASS | Device-signed, offline-verified (SIGNATURE VALID, LOW-S) in this lane and in the committed proof |
| transaction broadcasting | PASS | /api/broadcast accepted; mainnet tx ce514b35... confirmed on-chain |
| QR generation | PASS | /api/qr.png (walletbench), rendered on device on RECEIVE and WALLET tabs; suite covers auth requirement |
| QR scanning | PENDING (M8) | No camera code present |
| encrypted wallet persistence | PARTIAL | SeedVault envelope code + selftest checks; device restart over the encrypted store not yet proven (same gap as 4.2) |
| application restart and recovery | PASS | M21: fresh process -> watch set re-imported on unlock -> wallet renders (section 2.2) |
| network interruption and reconnection | PARTIAL | Watch import retries 3x with 2 s x attempt backoff and surfaces "Watch import failed; balance may be stale." (SelfCustody.ensureWatchImported); Api.java connect 10 s / read 15 s timeouts. Uniform retry/offline copy is S-5; no airplane-mode device test yet |
| error handling | PARTIAL | API errors surface to the user; per-path copy and no-silent-empty-state work is S-5 |
| mobile build compatibility | PASS | APK builds with the raw toolchain on this host (section 1.4, SIGNED OK). Earlier device proofs installed the same bench line on Android 9 / API 28 (sections 2.2-2.4); this lane's build was not installed. Real-phone install pending (M6) |
| testnet or controlled environment | PARTIAL | All mainnet tests ran against a 50 MAZA-capped, token-gated harness (never uncapped); a MazaCore testnet node runs on the operator host but the app-side testnet switch is S-6 and needs a testnet-backed endpoint |
| never broadcast unauthorized or unintended mainnet txs | PASS | Both mainnet sends were Sami-directed, amount-capped, own-input-selected, and offline-verified before submission (section 2.1) |
| document all incomplete functionality | PASS | This report's INCOMPLETE list plus docs/SPEC-AUDIT.md PARTIAL/GAP rows |

### 3.5 Phase 8 - final deliverables

| Item | Status | Evidence |
|---|---|---|
| 1 refactored wallet source code | PASS | This repo (android/, walletbench/, indexer/, deploy/) |
| 2 standalone mobile application structure | PASS | android/src/com/mazawallet + crypto kit, zero external libraries |
| 3 working wallet dashboard | PASS | BALANCE tab (bench) and WALLET tab (self-custody) render live balances |
| 4 native MAZA blockchain integration | PASS | mazad RPC + MazaCore-anchored chain profile (vendored, sha-pinned) |
| 5 secure wallet creation and restoration | PARTIAL | Creation proven on device; restoration code present but the wiped-install device proof is outstanding (section 3.4) |
| 6 send and receive functionality | PASS | Mainnet sends proven (section 2.1); receive = address + QR |
| 7 transaction history | PASS | HISTORY tab; rows attributed by txid; self-addressed funding sends hidden |
| 8 build and deployment instructions | PASS | README, android/README.md, android/build-apk.sh, deploy/PUBLIC-HOSTING.md, docs/electrumx/ |
| 9 dependency and licensing report | PASS | docs/DEPENDENCY-LICENSES.md (APK: zero third-party libraries; server: Python stdlib plus one vendored MIT component) |
| 10 security assessment | DONE (S-8, 2026-11-17) | docs/SECURITY.md — present at the repo root; spend-path-scoped threat model, controls inventory, 13 accepted risks, 8 open items |
| 11 testing report | THIS DOCUMENT | docs/TESTING-REPORT.md |
| 12 outstanding development requirements | PASS | This report's INCOMPLETE list + docs/SPEC-AUDIT.md + backlog snapshot |
| installable Android APK | PASS (bench build) | SIGNED OK in this lane (section 1.4; signed but not installed here); release artifact evidence in section 2.5 |
| iOS compatibility | DEFERRED | Separate-architecture effort; documented decision, not silently dropped |

### 3.6 Development rules 1-8

| Rule | Status | Basis |
|---|---|---|
| 1 no restart unless the existing architecture is unsuitable | COMPLIANT | Audit verdict: the existing Gradle-free native stack is mainnet-proven, therefore suitable (docs/SPEC-AUDIT.md) |
| 2 no overwrite/delete of working files without backup | COMPLIANT | Changes are additive and judged; the bench installer takes timestamped state.json backups; the selftest-gate probe restores SelfTest.java byte-identically on interruption |
| 3 native MAZA only, no substitutes | COMPLIANT | No wrapped, bridged, or alternate asset anywhere (DECISIONS.md) |
| 4 no DEX/swap/order-book infrastructure in the core | COMPLIANT | None present |
| 5 no fabricated connectivity or simulated balances | COMPLIANT | Every balance and txid in this report traces to a command transcript or a committed node/device capture; the bench is a capped TEST harness and is labelled as such in the UI |
| 6 no production-readiness claims until connectivity, signing, broadcasting, recovery are tested | COMPLIANT | Status language throughout is "mainnet TEST with capped funds"; production readiness is withheld, and restoration/recovery gaps are named in the INCOMPLETE list |
| 7 modular, maintainable, documented | COMPLIANT | First-party crypto kit isolated from the Android shell; coin profile isolated (indexer/maza_coin.py); DECISIONS.md + spec + audit + this report |
| 8 dependency/licensing review, Komodo independence | COMPLIANT (review performed) | docs/DEPENDENCY-LICENSES.md reviews every incorporated item (APK: zero third-party libraries; server: stdlib plus one vendored MIT component) and records the unresolved BIP39 data-level grant openly; no Komodo component is incorporated |

### 3.7 INCOMPLETE - what is not done or not proven

LANDED on 2026-11-17 (parallel burst, all four lanes merged into this tree):

- S-3 light mode: LANDED app-wide (wave 2, 2026-11-17): all 15 hardcoded
  color constants converted (113 sites) to UiTheme palette resolution off the
  live theme; the EXPECTED_BELOW_THRESHOLD ledger is EMPTY (machine-checked
  burn-down gate green); dark render is byte-identical (frozen DARK_RENDER_
  BASELINE test); PIN dialogs + dialog themes covered. Known UX residual
  (new backlog item): choosing a theme in Settings recreates only Settings -
  a live MainActivity keeps its palette until recreated (session-preserving
  rebuild queued as a wave-3 item; token is memory-only so a plain
  recreate() would bounce to Connect). Device screenshots of light mode
  pending.
- S-4 settings + wallet management: DONE (SettingsActivity from the SECURITY
  card: endpoint editor on the same saved URL pref, auto-lock 5/10/30 min
  applying IMMEDIATELY via PinGuard.retuneAutolockMs (wave 2: window-only
  change, streak/backoff untouched, 12 dedicated checks), theme selector
  System/Light/Dark; WALLET MANAGEMENT: receive addresses, PIN-gated seed
  re-show with FLAG_SECURE + scrub on dismiss, double-confirm + typed-WIPE
  wipe). Device screenshots pending.
- S-8 security assessment: DONE (docs/SECURITY.md; every cited path
  existence-verified by the writing lane).
- S-9 testing report: DONE (this document; 1.0 refreshed post-merge).

Not started or gated:

- S-5 network-interruption and error hardening: only the watch-import retry
  plus HTTP timeouts exist today; no airplane-mode device test; error copy
  and no-silent-empty-state work outstanding.
- S-6 testnet mode: app-side endpoint and address-version switch is not
  implemented; testnet testing is gated on a testnet-backed endpoint. All
  testing so far is mainnet against a capped harness.
- Biometric unlock: not implemented (S-2b part 2). BlueStacks has no
  fingerprint hardware, so only the graceful-absence path could ever be
  device-proven there.
- S-1 device half: restart and legacy-plaintext-migration proof over the
  encrypted seed store (AndroidKeyStore path) is outstanding; the code and
  its selftest envelope checks are in place.
- Fresh-install restoration proof: blocked pending Sami's explicit go,
  because `pm clear` destroys the only on-device copy of the seed.
- M8 QR scanning: no camera scan in the SEND flow.
- M6 real-phone install: all device proofs are on a BlueStacks emulator;
  a physical-handset install and proof is outstanding.
- ElectrumX serving path: gated on the txindex decision gate (in-place
  reindex vs a second txindex node). The light-client kit is in-repo but not
  serving balances yet; today's balances come from the mazad RPC watch
  backend.
- Desktop wallet.dat import (m/0'/0'/k scheme): planned lane, not
  implemented.
- iOS: deferred by architecture decision.
- Documentation drift: RESOLVED 2026-11-17 — docs/SPEC-AUDIT.md rows 4.2,
  4.4 and Phase 7 "encrypted wallet persistence" now reflect the landed S-1
  code (the device half remains outstanding under its own bullet above).
- Deferred residuals recorded in DECISIONS.md D11: PIN verifier is not
  Keystore-wrapped, and the wrong-PIN backoff state is memory-resident (a
  process restart clears the streak).

## 4. How a reviewer re-runs this

From a clean checkout of the merged tree:

```
python3 -m unittest discover -s tests      # expect: Ran 253 tests, OK (skipped=4)
bash android/selftest.sh                   # expect: ALL 96 CHECKS PASSED
bash android/build-apk.sh                  # expect: 6/6 stages, SIGNED OK + sha256
sha256sum android/maza-wallet-bench.apk    # artifact identity for the run
```

Device evidence cannot be re-run without BlueStacks on SAMI-PC; it is
re-checkable instead from the committed artifacts:

```
cd android/evidence/s2b-pin && sha256sum -c SHA256SUMS
python3 tools/txverify.py "$(cat ../selfcustody-proof/sent-tx-hex.txt)" \
    0 76a914a8d1e31cee7692a99dc10bdd8d36a7da9f2bde3288ac
# requires the python 'ecdsa' package; the repo itself needs it only for this tool
```

On-chain confirmation of the self-custody send is re-checkable on any synced
MAZA node with `maza-cli getrawtransaction
ce514b350d2c2dc362b8cea0babc9ac64b8261b547142cc93a94ae366350cd4e true`; the
node-side re-check recipe is in android/evidence/selfcustody-proof/PROOF.md.
