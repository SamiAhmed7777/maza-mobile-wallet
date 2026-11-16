# M5 — Release keystore + signed release APK

Date: 2026-11-16 (loop tick 24a7311de928)
Owner lane: MAZA Mobile Wallet Backlog Loop · repo /root/maza-mobile-wallet
Judge history:
- r1 C urn:ump:rwqncp4ghvz43iuba5w6lbrjcelhsx7tf4pjlghtrt3mg5ncpihq
- r2 C urn:ump:7xowxh7aibevrnxk6ookef56pck4vg5hcxw6bkeahlop3xthvixq
- r3: this submission — both r2 blockers + both r2 polish items addressed
  (dispositions below).

## What shipped

1. **`android/build-apk.sh --release`** — a release build variant alongside the
   unchanged bench/debug path:
   - stage [1/7] is the SAME crypto selftest gate (19/19 vector checks, aborts
     before packaging) — release builds can never contain broken crypto;
   - signing key: `mazarelease` alias in a dedicated release keystore
     (NOT the debug keystore; NOT auto-generated — missing key = FATAL exit 1);
   - version identity from `android/release.properties` (committed):
     versionCode=2, versionName=1.0.0 — the release line starts ABOVE the
     bench line's versionCode 1 and is independent of it (different signing
     keys → the two lines can never install over each other);
   - version injected via `aapt2 link --version-code --version-name
     --replace-version` — AndroidManifest.xml is NOT modified (bench line
     keeps 1/1.0). NOTE: `--replace-version` is REQUIRED; without it aapt2
     injects only "if none is present" and the APK silently keeps the
     manifest's versionCode=1 (caught by our own badging check mid-tick);
   - versionName validated against `^[0-9]+([.][0-9]+)*$` (rejects '.',
     '1..0', '.1', '1.'); versionCode must be all-digits;
   - `zipalign -f -p 4` before signing (new stage 6/7; bench path untouched);
   - passwords fed via `--ks-pass file:… / --key-pass file:…` — never argv,
     never shell-visible. apksigner's file: reader consumes lines SEQUENTIALLY:
     line 1 = keystore password, line 2 = key password (a single-line file
     fails the key-password read with "end of file reached" — the shipped
     passfile therefore holds the same password twice);
   - the missing-keystore FATAL hint is emitted with `printf '%s\n'` and
     carries EXACTLY ONE continuation backslash per continued keytool line
     (r2 blocker fix; byte-proven via cat -A and by verbatim replay, probe F);
   - javac/d8 file lists built with NUL-delimited `mapfile` arrays
     (`find -print0`) — no unquoted `$(find …)` word-splitting (r2 polish);
   - output: `android/releases/maza-wallet-v<versionName>.apk`
     (`android/releases/` is gitignored — binaries stay out of git).
2. **Release keystore** (created this tick, off-repo):
   - `/root/.maza-wallet/release.keystore` — mode 0600, RSA-2048,
     alias `mazarelease`, validity 10000 days (to 2054),
     cert SHA-256 fingerprint
     `59b2f5e0948d5de1628651db93d300d8740185d9fb4c2a5a213789b8fef804b5`;
   - `/root/.maza-wallet/release.keystore.pass` — mode 0600, 2 lines
     (keystore pw + key pw per apksigner file: semantics);
   - off-repo backup copies: `/var/backups/maza-mobile/release.keystore{,.pass}`
     (mode 0600, backup password verified functional via keytool -list);
   - password additionally delivered to Sami by Telegram DM (Home chat
     637130179, message 67533) per the standing credential rule — script-file
     path, never inline curl, never group chat, never logged.
3. **`.gitignore`** — `android/releases/` added.

## Round-1 disposition (r1 C — fixed in r2, re-proven every round since)

| r1 blocker | fix | pinning evidence |
|---|---|---|
| Evidence inconsistency: verify-battery.txt cited the then-current sha 5b74d0b7… while PROOF.md/build-transcript claimed 4de6f77a… final | [SUPERSEDED VALUES, historical] All evidence regenerated against ONE immutable APK per round; since r3 the single pinned APK sha is d30a48a9… and every evidence file cites exactly it (5 occurrences within .txt transcripts, all identical; separate counts for PROOF.md/brief — scope-stated in secret-scan.txt) | build-transcript.txt + verify-battery.txt + badging.txt |
| FATAL hint: keytool line used `$(cat file)` (two-line blob) | hint now `head -n1`; probe F proves the required form | refusal-probes.txt probe F |
| r1 polish: hash script + release.properties beside APK evidence | input anchors in build-transcript.txt (r3: build-apk.sh 9a7a7a24…, release.properties de11640a…) | build-transcript.txt |
| r1 polish: extra refusal probes | probes C/D1/D2/E | refusal-probes.txt |
| r1 polish: stricter versionName | regex `^[0-9]+([.][0-9]+)*$`; probe D2 fires | refusal-probes.txt D2 |

## Round-2 disposition (r2 C — fixed in r3)

| r2 blocker | fix | pinning evidence |
|---|---|---|
| Hint emitted TWO literal backslashes (`\\`) on continuation lines — copy-paste would break the keytool command | hint block rewritten with `printf '%s\n'` and single-quoted strings emitting exactly ONE `\` per continuation; byte-proven with cat -A (each continued line ends `\$`, i.e. one backslash before EOL) | r3 build-transcript run of the hint (this PROOF.md), refusal-probes.txt probe F |
| Probe F must execute the ACTUAL EMITTED hint text, not a hand-rebuilt equivalent | probe F now: triggers the FATAL with SCRATCH env paths (the hint interpolates the env-provided paths itself), captures stderr, extracts the hint lines, EXECUTES the captured file verbatim (`bash hint-verbatim.txt`) → keytool generates the keystore from the captured text alone (exit 0), keytool -list opens it, apksigner signs a copy with it, negative control (raw cat form) fails | refusal-probes.txt probe F |
| r2 polish: printf for deterministic multi-line hint | done (see above) | build-apk.sh |
| r2 polish: replace unquoted `$(find …)` with whitespace-safe handling | `mapfile -t -d ''` + `find -print0` arrays for javac and d8 inputs | build-apk.sh stage 4/5 |

## Verified (all evidence in this directory, one immutable APK)

- **Round-3 release build** (`build-transcript.txt`): stages [1/7]–[7/7] all
  green, selftest 19/19 PASS, SIGNED OK (versionCode=2 versionName=1.0.0),
  EXIT=0.
  - APK: `android/releases/maza-wallet-v1.0.0.apk`, 271316 bytes,
    sha256 `d30a48a9b6ccf04708d51b7494ccebff3d88aafe97e2bad894afd299f4bd1b77`
    — ALSO attached to the judge worktree so the grader can hash/badging/
    verify the exact bytes itself (note: the judge worktree renames --files
    entries with numeric index prefixes 0_…N_, so the APK's in-worktree name
    shifts position between rounds — basenames identify files; in the r3
    worktree it was delivered as `11_maza-wallet-v1.0.0.apk` and the brief's
    `0_` reference was the r3 judge's polish finding, folded via
    POLISH-FOLD.md)
  - input anchors: android/build-apk.sh sha256 9a7a7a2400bd8ecb2f5c18593ba0bb91830a5e13c4a856f857d1eb707d42ca89,
    android/release.properties sha256 de11640a30066eb56587a56f974cfc72ed4769e39001d125277567640a9a8ea3
- **Battery on the same APK** (`verify-battery.txt`, `badging.txt`):
  regenerated IN FULL post-grade (r3 judge polish caught the round's file
  truncated by a display-pipeline SIGPIPE — see POLISH-FOLD.md); commands
  re-run against the SAME immutable APK with EXIT codes captured:
  `versionCode='2' versionName='1.0.0'`, `sdkVersion:'24'`,
  `targetSdkVersion:'34'` (min/max SDK pinned — already satisfied by
  AndroidManifest.xml uses-sdk for the bench line; release badging confirms
  both survive version injection); `zipalign -c 4` ALIGNED OK; apksigner
  v2 scheme true, v3 scheme true (v1/v3.1/v4 false — expected for minSdk 24);
  signer cert SHA-256 equals the keystore fingerprint → the APK is provably
  signed by the mazarelease key.
- **Refusal probes** (`refusal-probes.txt`, final script bytes):
  - A missing keystore → FATAL, EXIT=1, before packaging
  - B world-readable passfile → FATAL, EXIT=1
  - C missing passfile → FATAL, EXIT=1
  - D1 invalid versionCode `abc` → FATAL, EXIT=1
  - D2 invalid versionName `1..0` → FATAL, EXIT=1
  - E wrong password → apksigner exit 2, NO output APK written
  - F VERBATIM hint replay: captured stderr text executed as-is → keystore
    created by the captured lines (exit 0); keytool -list opens with head -n1;
    apksigner roundtrip-sign of a COPY succeeds with the scratch cert; raw
    cat-form negative control fails as required
- **Bench-mode regression** (`bench-regression.txt`): default
  `bash android/build-apk.sh` still SIGNED OK on the r3 script. Mid-tick this
  probe caught a REAL regression in my own rewrite (bench default output path
  lost → apksigner got an empty --out and crashed); fixed before shipping.
  Bench rebuild md5 differs from the M22b build (a3cd0326…) because
  `classes.dex` is added by `zip -uj` with the build-time mtime (aapt2
  entries are fixed at 1980-12-31; two consecutive bench builds minutes apart
  produce different md5s). No cross-build byte-identity was ever claimed in
  M4/M22b evidence — "APK md5 unchanged" there meant the ABORTED forced-fail
  build did not touch the existing APK file. The bench APK itself is not
  committed (gitignored), so its md5 is not part of the graded bytes.
- **Secret hygiene** (`secret-scan.txt`): grep with the actual password
  (read from the passfile as pattern, count-only) over every evidence file
  and every committed M5 file: TOTAL_SECRET_MATCHES=0. sha-consistency sweep:
  the APK sha appears 4× in evidence, always d30a48a9…; zero stale sha
  references in transcripts (the only old-sha strings are the explicitly
  labeled SUPERSEDED history rows in this PROOF.md).
- **Walletbench suite**: NOT re-run this tick — the M5 diff touches no
  Python/backend code (build script + release.properties + .gitignore only);
  the last suite state (213 OK, skipped=4) is unchanged by this surface.

## Device/emulator install — honest status: DECISION-GATED, not skipped

Backlog DONE criterion: "signed APK installs on a real Android device or
emulator-image sanity check." Status per available infrastructure:

1. **DNS2 (this host): a literal emulator install is UNAVAILABLE, measured.**
   - `/dev/kvm` does not exist (checked this tick) — an x86 Android emulator
     cannot boot here in usable time (software emulation only);
   - disk is at 96% (8.2 GB free) — a system image + AVD (~3 GB) would push
     the host toward full;
   - `/opt/android-sdk` carries build-tools + platforms only, no emulator
     package, no system-images.
   These are environmental unavailability facts (like a journald window that
   rotated away), not failures of the artifact.
2. **SAMI-PC BlueStacks: the only live emulator — install is AUTHORIZATION-GATED.**
   It runs the BENCH build with the M2 seed on-device. A release-keystore APK
   can never install over it (different signature →
   INSTALL_FAILED_UPDATE_INCOMPATIBLE); the install test requires
   `adb uninstall com.mazawallet` FIRST, which destroys the on-device seed.
   Standing rule: literal seed destruction needs Sami's explicit go (his
   12 words are the only backup). Same gate recorded in M21's scope caveat.
   A zero-risk second BlueStacks instance is possible (~10 min + a wrapper
   schtask per the M21/M22 ops lessons) but changes SAMI-PC guest state —
   also proposed for Sami's go.
3. **What IS proven about installability, non-destructively:** badging
   (version/SDK pins valid for an install), zipalign (4-byte aligned, the
   requirement real PackageManager checks), apksigner v2+v3 (signature
   schemes Android 7+/9+ accept for minSdk 24), signer identity anchored to
   the release key. The APK additionally carries versionCode=2 > the bench
   line's 1 for clean version ordering.
4. **Decision menu for Sami (next interactive contact):** (a) with his go,
   uninstall+install the release APK on the existing instance (seed already
   backed up in-chat); (b) zero-risk second instance for install sanity;
   (c) defer the literal install to his phone once M6 (distribution channel)
   lands. Until one is chosen, M5 ships with this honest gate note; the
   backlog checkbox stays UNTICKED until a literal install happens (the
   build/signing/keystore deliverable itself is complete and verified).

## Files changed (git)

- android/build-apk.sh (modified: --release variant; bench path behavior
  identical — regression-proven)
- android/release.properties (new: release line version identity)
- .gitignore (modified: android/releases/)
- android/evidence/m5-release-build/* (new evidence: this PROOF.md,
  build-transcript.txt, verify-battery.txt, badging.txt, refusal-probes.txt,
  bench-regression.txt, secret-scan.txt)

Keystore + password + backup NEVER enter the repo (paths only, as above).
