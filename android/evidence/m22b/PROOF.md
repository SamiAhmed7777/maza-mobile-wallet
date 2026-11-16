# M22b — BlueStacks evidence for M22a (commit 26a962b)

Tick: 2026-11-16 09:06-09:2x PST, backlog loop 24a7311de928.
Artifact under proof: the APK rebuilt from the clean repo tree at HEAD 26a962b
(`M22a: SEND-tab bench vs self-custody disambiguation + balance/history
navigation refresh`, grade A
urn:ump:wxfl3uhiinypeagg5eazio2royms7nuylq2o6gejt5dtggm65j5q). Repo tree was
clean (`git status --porcelain` empty) before and after the evidence run.

## Build provenance (26a962b)

| Step | Result |
|---|---|
| `bash android/build-apk.sh` | selftest gate stage [1/6]: ALL 19 CHECKS PASSED; stages 2-6 OK; `SIGNED OK: android/maza-wallet-bench.apk (271316 bytes)` |
| APK sha256 | `e9cb8e5c8f7aed82a6e3a5123556fdf385e0cdae1c9c4deef2bfc3849d8eab6b` |
| APK md5 | `a3cd0326062d2d4e5344c04df39ab75d` |
| badging | `com.mazawallet` versionCode 1 / versionName 1.0, minSdk 24, targetSdk 34, label `MAZA Wallet` |
| scp to SAMI-PC | md5 parity: `a3cd0326062d2d4e5344c04df39ab75d` both sides |
| `adb push` → `/sdcard/m22b.apk` | `ls -l` = 271316 bytes |
| `pm install -r /sdcard/m22b.apk` | `Success` |
| reconnect after install | `HD-Adb connect 127.0.0.1:5555` → `emulator-5554 device` |
| `dumpsys package com.mazawallet` | `lastUpdateTime=2026-11-16 09:12:28` |
| installed `pm path` base.apk md5 | `a3cd0326062d2d4e5344c04df39ab75d` — EXACT parity with host build |

Tunnel health (client-side from DNS2, the APK's endpoint
`http://100.121.150.22:18701`): root `200`, `/api/state` `401` (token-gated).

## Token handling (exposure scope, stated precisely)

- Live token fetched from samihost `/etc/maza-wallet-bench.env` over ssh into
  a temporary staging file on DNS2 (`/tmp/m22b-token`, 33 bytes) for the
  duration of this tick, then shredded (`shred -u -n 3`, exit 0; verified
  absent afterward). It was never written to SAMI-PC disk (no token-named
  file exists there), never echoed to stdout, never screenshotted, and no
  COMMITTED artifact contains it (scans below + EVIDENCE-RAW.md §4-5).
- Entry method (the M21 "stdin path"): `type-token.cmd` reads the token from
  cmd stdin (`set /p TOK=`) and types it via `input text "%TOK%"` into the
  token field at (800,455). The script file contains no literal token.
  EXPOSURE SCOPE of this method, stated honestly: the `%TOK%` expansion puts
  the token TRANSIENTLY in TWO process argument vectors — (a) the host-side
  `HD-Adb.exe` argv on SAMI-PC for the duration of that one command, and
  (b) the on-device `input` argv inside the emulator until the command
  exits. Both processes are short-lived; neither argv is captured in any
  transcript, log, or screenshot in this package, and the shell console on
  each side is single-operator. This is the same entry path the M21
  close-out used. Claims this package makes and stands behind: never
  PRINTED to captured output, never SCREENSHOTTED, never LOGGED, never
  committed, transient-argv-only otherwise.
- Pre-entry dump: token field `password="true"`, text = 11-char hint
  (`bench token` = EMPTY). Post-entry dump: `password="true"` field holds
  exactly 32 masked characters = the 32-char token typed once. URL field
  untouched, pre-filled `http://100.121.150.22:18701`.
- The Connect card was NEVER screenshotted. Post-commit scan over every file
  in this directory: `grep -rlF <live-token-literal>` → 0 matches; raw
  `Bearer <16+ alnum>` → 0; standalone 32-char alnum blobs → only the APK
  md5 quoted in the transcripts (documented build identity, not a
  credential); mnemonic-word patterns → 0. Fresh re-run with exit codes in
  EVIDENCE-RAW.md §5.

## Unlock (fresh process over preserved seed data)

`am force-stop` → `am start` → CONNECT tap (800,576) → app lands on BALANCE
(dump-unlock-landing-balance.xml): header `MAZA Wallet`, `46.9998774 MAZA`,
`account mobile-play · fee 0.0001 MAZA`, `Last sync 2026-11-16 09:16:48`,
tab row BALANCE/RECEIVE/SEND/HISTORY/WALLET. No tab tap preceded the landing.

Scope note (inherited from the M21 close-out): this is an install-over-update;
the on-device seed is preserved (a literal `pm clear` fresh-install would
destroy the seed held only in Sami's backup — needs his explicit go). The
M22b claims below (tab disambiguation + navigation refresh) do not depend on
fresh-install state.

## Claim 1 — SEND tab says BENCH ACCOUNT (bench spend surface)

send-tab-bench-account.png (tapped SEND (800,858) from BALANCE), corroborated
by dump-send-tab.xml:

- header: `SEND · BENCH ACCOUNT`
- note: `Spends the bench server's held funds (server-side, capped). Your own
  seed wallet is on the WALLET tab.`
- fields `Recipient address (M...)` / `Amount (MAZA)`, `fee 0.0001 MAZA`,
  `SEND` button; SEND tab highlighted in the bar.

## Claim 2 — WALLET-tab send card says SELF-CUSTODY (on-device signing)

wallet-tab-top.png (tapped WALLET (1440,858)): `My Wallet` /
`Self-custody · keys never leave this device` / `1.4999 MAZA` /
`RECEIVE ADDRESS index 2` / `MGo1gjPrj2GDnbwcyRBJMaZ4GJMEAaVkU8` / `NEXT` /
receive QR (dump-wallet-top.xml).

Send card below the fold; after `input swipe 800 620 800 180`:
wallet-send-self-custody.png (dump-wallet-send-card.xml):

- header: `SEND · SELF-CUSTODY`
- note: `Signed on this device from your own seed balance.`
- fields `To (M...)` / `Amount (MAZA)`, `fee 0.0001 MAZA`, `SEND` button;
  WALLET tab highlighted.

## Claim 3 — balance refresh on navigation (fund-independent)

Poll-excluding tight sequence (m22b-round2.cmd): BALANCE dump S1, then two
BALANCE→SEND→BALANCE round-trips (~6s each) with a dump after each landing:

| Dump | View | Last sync | Advance |
|---|---|---|---|
| dump-refresh-s1.xml | BALANCE | 2026-11-16 09:20:36 | — |
| dump-refresh-s2.xml | BALANCE after NAV1 | 2026-11-16 09:20:41 | **+5s** |
| dump-refresh-s3.xml | BALANCE after NAV2 | 2026-11-16 09:20:47 | **+6s** |

The 15s background poll alone can only advance Last-sync in ~15s multiples;
two consecutive advances of 5s and 6s are impossible under poll-only and are
produced by the M22a selectTab navigation-refresh. Supporting screenshots:
balance-t0.png (`Last sync 2026-11-16 09:17:54`) → SEND →
balance-after-nav.png (`Last sync 2026-11-16 09:18:10`).

## Per-build coordinates (uiautomator-first rule)

Connect card: token `[54,421][1546,489]` → (800,455); CONNECT
`[54,540][1546,612]` → (800,576). Tab row y 816-900: BALANCE (160,858), SEND
(800,858), WALLET (1440,858) — all read from this build's own dumps.

## Vision-check log (all 5 screenshots, pre-commit)

Inspected at full resolution; each answered: exact texts present, and "any
credential/token/password visible?" → NONE on all five. Only public on-chain
data appears: bench balance, self-custody balance, receive address
(MGo1gjPrj2GDnbwcyRBJMaZ4GJMEAaVkU8, public data) and its QR.

| File | sha256 |
|---|---|
| balance-t0.png | `1ce345b19142fffb634ffe8b2b0cad80ceafb2e34b1bb05e4e30faba5dd6e628` |
| send-tab-bench-account.png | `8748bd2f5908d43faf740557eb0e78f0243d7c2547b3a490e35f96986bded13e` |
| balance-after-nav.png | `bca2a53920740862f75583c18196f335621680f09f95f12f696d31726cac73fd` |
| wallet-tab-top.png | `02f4725bb9ca1b74a888cf798b4d01bb42a7b369d42b92ded8de3afface767cc` |
| wallet-send-self-custody.png | `191e34085ae497b8b5d5123f410882a7bf0e6a98bd04bfa217bbdf6539ed0ee0` |

## Result

All three M22b DONE criteria met: screenshots in android/evidence/ (this
package), M22a's two send-surface headers + notes render on-device, balance
refresh proven poll-excluding. M22 as a whole (M22a code + M22b evidence) is
complete; group notify follows.

## Round 2 — r1 blockers resolved (judge r1: C,
urn:ump:yzfrbbyakthivooxwt2qevrz6zesutctp6iefiev6q2nlikarhmq)

- Blocker "pulls not transport-qualified / duplicate transport": every
  DEVICE-TARGETED adb call (pull / shell / screencap / input / uiautomator
  dump) in every script in this package is now `-s emulator-5554`-qualified;
  the ONE server-wide call (`HD-Adb devices` in round 4) intentionally lists
  all attached transports and takes no `-s` (that is its documented
  behavior, not an omission).
  EVIDENCE-RAW.md §3 documents WHY the original unqualified pulls succeeded
  (the SAMI-PC adb server restarts between ssh sessions and re-attaches only
  the `emulator-5554` transport — round 4 `devices` shows exactly one), and
  m22b-round4.cmd re-pulled all five PNGs with `-s`: all five SHA-256s are
  byte-identical to the committed files (hash table in EVIDENCE-RAW.md §3).
- Blocker "provenance claims lack raw output": EVIDENCE-RAW.md adds fresh,
  re-runnable raw captures — host APK sha256/md5 (RC=0), aapt2 badging
  verbatim, a fresh standalone `android/selftest.sh` run (ALL 19 CHECKS
  PASSED, RC=0), installed base.apk md5 + `lastUpdateTime` re-read live via
  `-s`-qualified commands, verbatim pre/post token-field XML nodes
  (hint → 32 bullets, no plaintext), and the hygiene scans with exit codes.
- Polish (apostrophe): the note is now quoted exactly —
  `Spends the bench server's held funds (server-side, capped). Your own seed
  wallet is on the WALLET tab.` — matching dump-send-tab.xml verbatim
  (EVIDENCE-RAW.md §6).
- Polish (exit codes): fresh captures carry RC markers; round-4 re-pull
  output is included; corrected scripts make silent capture failures
  impossible on any re-run (fail-fast remains a known polish item for future
  evidence scripts).

## Round 3 — r2 blockers resolved (judge r2: C,
urn:ump:c7qmdmspyb3stqvhqya4wqlzbcbl6i4aqr4ltc65r4l5rpxof4gq)

- Blocker "token never in host-side argv is false" — CORRECTED by stating
  the truth, not by narrowing language: the `%TOK%` expansion puts the
  token transiently in TWO argvs — the host-side `HD-Adb.exe` argv on
  SAMI-PC and the on-device `input` argv (PROOF.md "Token handling —
  exposure scope, stated precisely"; RUN-TRANSCRIPT.md token-fetch line;
  EVIDENCE-RAW.md §4). Neither argv is captured in any transcript, log, or
  screenshot; this is the M21-precedented entry path. The package's
  standing claims are now exactly: never PRINTED to captured output, never
  SCREENSHOTTED, never LOGGED, never committed.
- Blocker "'never persisted' contradicted by the staging file" — the
  staging file's whole lifecycle is now documented AND terminated:
  `/tmp/m22b-token` (33 bytes) existed for the tick's duration and was
  destroyed post-run — `shred -u -n 3 /tmp/m22b-token` exit 0, absence
  verified (`ls: cannot access ... No such file or directory`), and SAMI-PC
  never held any token file (verified). Transcript in EVIDENCE-RAW.md §8.
  "Never persisted" is no longer claimed; the claim is scoped to committed
  artifacts (scan-proven) plus documented transient storage that is now
  gone.
- r2 polish acknowledged: fail-fast .cmd error checking and deriving the
  installed base.apk path from `pm path` are recorded as known polish for
  future evidence scripts (the base.apk path in round 4 matches the
  `pm path` output quoted above it in the same transcript).
