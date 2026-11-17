# S-2b device proof — PIN lock on BlueStacks (part 1: PIN paths)

Date: 2026-11-17 (device and host clocks PST, UTC-08:00; one timezone throughout).
Device: BlueStacks Pie64 on SAMI-PC, 1600x900, adb device emulator-5554.
APK: built from repo HEAD 8cf4dc6 (S-2a commit), sha256
499192b3d0cc4d9872e70cbb38ed12188da864dbf03f54d7236635e540a3b1e9,
md5 a9ace56ba5707a4c7d8993228c844c70. Install: adb push +
`pm install -r /sdcard/maza-update.apk` -> "Success"; `dumpsys package
com.mazawallet` lastUpdateTime 2026-11-17 00:29:46; installed base.apk md5 ==
host APK md5 (byte-identical update install; app data — seed + PIN prefs —
preserved by the update, not wiped).

Scope of this evidence package: the PIN-lock device proofs (S-2b part 1).
Biometric-where-supported is a separate sub-item (S-2b part 2) and is NOT in
scope here. The server token never appears in any artifact: the Connect card
screenshot shows the field HINT ("bench token" = empty field, per the known
uiautomator hint rule); the token was staged on SAMI-PC via ssh stdin into a
local file, consumed by the driving script, and the file deleted
(TOKENFILE-DELETED=True observed both times). PIN digits never appear in any
screenshot or XML dump (masked bullets only); the driving scripts that type the
test PIN are committed deliberately and state the test PIN in cleartext — the
PIN is a bench-device test value guarding a watch-only bench session, and the
server token is NOT in those scripts.

## Setup proof

- s2-fresh-connect.png + ui-connect-card.xml — after the update install, the
  app opens on the Connect card with the saved URL pref
  (http://100.121.150.22:18701 — pref persistence on in-place update, the
  documented behavior; fresh installs get the mazatest default) and an EMPTY
  token field.
- s1-security-armed.png — WALLET tab SECURITY card after Set PIN: "PIN lock
  ON · auto-lock after 5 min of inactivity (also locks while backgrounded)."
  with CHANGE PIN / REMOVE PIN buttons. Test PIN set via the Set PIN dialog
  (two matching 4+ char fields), toast "PIN saved."

## P1 — fresh connected session starts LOCKED (no inactivity needed)

After force-stop + relaunch the app must be re-connected (token is memory-only
by design). Evidence chain:

- ui-connect-card.xml — fresh process on the Connect card (locked session
  state cannot render pre-connect; the gate lives behind CONNECT by design).
- After CONNECT with zero tab taps and zero inactivity elapsed, the lock
  overlay IS up: s3-immediately-locked.png + ui-immediately-locked.xml show
  "Wallet locked" / "Enter your PIN to continue." / PIN field / UNLOCK over
  the BALANCE tab content. The overlay was raised by the 10-second
  autoLockTick while the gate decision (LockPolicy.forSession
  verifierPresent=true -> lockNow) is the authoritative lock, exactly as the
  S-2a judge round specified (fresh process WITH a stored verifier starts
  LOCKED).

## P2 — wrong PIN path

- s4-wrong1.png + ui-wrong1.xml — one wrong PIN attempt (typed 9999, UNLOCK):
  "Wrong PIN - try again." rendered, field cleared for retry.

## P3 — throttle: engagement, doubling render, no-evaluation refusal, lockout-span observation

Consecutive wrong attempts (the drive hit 5+ because several UNLOCK presses
landed with stale field content — see Driving-difficulty note) produced:

- ui-throttle-engaged.xml — "Too many attempts - wait 9s." — the throttle
  window engaged after 5 consecutive failures (BASE 30s window, remaining
  seconds rendered at showLock time; the countdown decays between re-renders,
  which is why the rendered number is lower than the full window).
- ui-backoff-doubled.xml + s6-refused-correct.png — "Too many attempts -
  wait 113s." — a 120s window (2x the 30s base) with 7s elapsed: the doubling
  backoff rendered on-device. The accompanying screenshot shows the same
  state with 4 masked bullets in the field (the refused attempt's typed
  content — refused without evaluation).
- ui-ref2-pre.xml / ui-ref2-post.xml + s12-refusal-final.png — THE
  self-authenticating refusal chain (refusal-final2.ps1, ONE script, no
  input between its steps): the script clears the field, types the known
  test PIN, dumps the pre-state (ui-ref2-pre.xml: FIELD = exactly 4 masked
  bullets — the script's own `input text 2468` is the only writer between
  the clear and this dump), presses UNLOCK once, then dumps the post-state
  (ui-ref2-post.xml: throttle message RE-RENDERED at press time with
  remaining "wait 20s" — a live window refused the press — and the 4
  retained bullets). The correct PIN was therefore refused during a live
  window without evaluation: had the PIN been evaluated and matched, the
  overlay would have closed. Screen capture s12 (device clock 2:10) shows
  the same state. The earlier ui-field-4-bullets/ui-refused-40s pair
  (01:08) independently shows the same behavior from the first pass.
  Note (disclosed): arm2.ps1 (ui-armed2.xml) shows the arming state — the
  field holding 16 bullets of accumulated wrong-attempt garbage, because the
  THROTTLED early-return path never clears the field (only wrong-PIN renders
  do). The driver's clear step erased it before typing; the intermediate
  cleared-state dump caught the DEL keyevents mid-flight and was not kept —
  the authoritative pre-press state is ui-ref2-pre.xml, captured after the
  typing step.
- 15-minute CAP: NOT independently established by a raw artifact, and NOT
  claimed as a measured device fact. What the artifacts show: unlock presses
  at 01:12 and 01:14 PST rendered the throttle message, and presses stayed
  refused across a ~27-minute span (01:12 -> 01:39 acceptance), consistent
  with a long/capped window that the driving accident (sustained wrong
  attempts) armed. The 900-second cap VALUE rests on the desktop-verified
  LockPolicy constants (BACKOFF_CAP_MS, pinned by the 49/49 selftest), not on
  device evidence; no dump renders a near-cap message. Recorded here as an
  incidental, transcript-only observation.

## Driving-difficulty note (honest record)

Early multi-attempt batches typed the PIN, then dismissed the soft keyboard
with a coordinate tap. With the keyboard open the window pans, so the dismissal
tap landed on keyboard keys and later UNLOCK presses ran with stale/garbage
field contents — inflating the wrong-attempt streak. The driving scripts in
this directory (type-token.ps1-era flows are NOT committed; the committed
*.ps1 files are the FINAL deterministic flows) use: tap field -> type ->
keyevent 66 (ENTER closes the IME, no coordinate tap) -> verify field contents
via uiautomator dump -> press UNLOCK. All evidence above comes from the
deterministic flows; the inflight accident is documented because the CAP
observation came from it. No server token was ever exposed during any of this.

## Post-window acceptance + inactivity + background-return (same run, part 1 completed)

- ui-accepted.xml + s9-unlocked.png — after the capped window drained (the
  throttle message is a STATIC render; its "wait 238s" text sits unchanged
  across dumps, so the drain was confirmed by re-pressing after the rendered
  window had long elapsed), a clean unlock press with the correct PIN closed
  the overlay: BALANCE tab rendered (Last sync 01:39:36), no overlay nodes.
  ACCEPTANCE after window expiry proven on-device.
- ui-inactivity-locked.xml + s10-idle-locked.png — INACTIVITY LOCK: with the
  session unlocked, zero input while the 15s background poll kept syncing
  (Last sync 01:45:44 — polls are not user activity by design: LockPolicy
  counts only onActivity user touches), the 10s autoLockTick raised the
  overlay. Dump: "Wallet locked" present, PIN field empty. DURATION basis
  (disclosed): the 5m10s idle span rests on the transcript clock, whose
  ordering is corroborated by the DEVICE STATUS-BAR CLOCKS visible in the
  screenshots themselves (s9-unlocked shows 1:39; s10-idle-locked shows
  1:45 — six minutes of wall clock between an unlocked and a locked frame,
  both images committed).
- ui-p4b-pre.xml / ui-p4b-unlocked.xml / ui-p4b-launcher.xml /
  ui-p4b-resumed.xml + s13-unlocked-pre-bg.png + s14-bg-return-locked.png —
  BACKGROUND-RETURN LOCK as ONE self-authenticating chain
  (bg-return-proof.ps1, single script): (1) pre-state dump — overlay up,
  field holding the 4 retained bullets, root package com.mazawallet;
  (2) one UNLOCK press -> dump: overlay GONE (accepted; streak reset);
  screenshot s13 (device clock 2:13, sync 02:13:47) shows the unlocked
  BALANCE; (3) `monkey` launch of com.uncube.launcher3 -> dump: root
  package com.uncube.launcher3 (the app BACKGROUND — the launcher
  transition captured, not just asserted); (4) 330-second sleep inside the
  script; (5) `am start com.mazawallet/.MainActivity` -> dump: root package
  com.mazawallet, "Wallet locked" overlay UP (onResume found backgrounded
  >= autolockMs); screenshot s14 (device clock 2:19 — six minutes after
  s13's 2:13, bracketing the backgrounded span on the in-image clocks).
  The raw artifacts therefore distinguish background-return from an
  ordinary inactivity lock: the launcher-foregrounded dump sits between
  the unlocked and resumed-locked dumps in the same driver.
- Device state at run end: LOCKED (the P4b driver's final dump shows the
  overlay up; no further unlock was performed) with the bench test PIN still
  set (CHANGE PIN / REMOVE PIN armed in SECURITY). The 113s -> 120s window
  mapping is code-derived inference from the desktop-verified LockPolicy
  constants (BACKOFF_BASE_MS 30s doubling per consecutive failure past the
  5th, pinned by the selftest), stated here so the render is not read as a
  directly measured window size.

## Artifacts

| file | what it proves |
|---|---|
| s2-fresh-connect.png + ui-connect-card.xml | update install survived; Connect card with saved URL + empty token field |
| s1-security-armed.png | PIN set; SECURITY card armed state |
| s3-immediately-locked.png + ui-immediately-locked.xml | P1: fresh connected session locked, zero taps |
| s4-wrong1.png + ui-wrong1.xml | P2: wrong-PIN message + cleared field |
| ui-throttle-engaged.xml | P3: throttle engaged ("wait 9s") |
| ui-backoff-doubled.xml + s6-refused-correct.png | P3: doubled window rendered ("wait 113s" = 120s window) |
| ui-field-4-bullets.xml + s8-pre.png | field content pinned before a refusal press |
| s-refused-40s.png + ui-refused-40s.xml | P3: correct PIN refused during live window (no evaluation) |
| ui-accepted.xml + s9-unlocked.png | acceptance after window drain: overlay closed, BALANCE rendered |
| ui-inactivity-locked.xml + s10-idle-locked.png | P4a: inactivity lock (5m10s idle, poll kept syncing) |
| ui-background-return-locked.xml + s11-bg-locked.png | P4b: background-return lock (5m30s backgrounded, resumed locked) |
| ui-p4b-pre.xml / ui-p4b-unlocked.xml / ui-p4b-launcher.xml / ui-p4b-resumed.xml + s13-unlocked-pre-bg.png + s14-bg-return-locked.png | P4b: one-driver chain — unlocked state, launcher transition, resumed locked |
| ui-ref2-pre.xml / ui-ref2-post.xml + s12-refusal-final.png | P3: self-authenticating refusal chain (correct PIN typed, dumped, pressed, refused) |
| ui-armed2.xml + arm2.ps1 | the arming pass (6-bullet-window state; accumulated-garbage field disclosed) |
| unlock-for-p4b.ps1, ready2.ps1, clear-retype.ps1, refusal-final2.ps1, bg-return-proof.ps1 | the deterministic driving flows (contain the bench test PIN in cleartext, disclosed above) |
| provenance.txt | raw verbatim command outputs: host sha256/md5/size of the APK; device dumpsys (firstInstallTime 2026-11-15, lastUpdateTime 2026-11-17 00:29:46 — update-not-wipe), pm path, installed base.apk md5 == host md5; bench-side date marker |
| SHA256SUMS | integrity manifest over every artifact in this directory (`sha256sum -c SHA256SUMS` from this dir) |
| transcript.md | command-level driving transcript |

## Capture provenance (which command produced each committed dump)

Every committed XML came from a two-step device flow: `uiautomator dump
/sdcard/<name>.xml` then `adb pull /sdcard/<name>.xml C:\Users\hello\<name>.xml`
then scp to this directory (rename shown where the committed name differs):

| committed file | /sdcard dump name | produced during |
|---|---|---|
| ui-connect-card.xml | ui-lock1.xml | 00:53 fresh-process dump |
| ui-immediately-locked.xml | ui-lock3.xml | 00:56 standalone dump (the p1-drive.ps1 in-script dump at ~7s is ui-lock2.xml, NOT committed — it predated the 10s tick and showed no overlay; the transcript documents that sequence) |
| ui-wrong1.xml | ui-wrong1.xml | 00:58 wrong-PIN attempt |
| ui-throttle-engaged.xml | ut.xml | 01:03 fixed-flow attempt |
| ui-backoff-doubled.xml | ui-refused-correct.xml | 01:06 throttle-proof.ps1 phase 2 |
| ui-field-4-bullets.xml | ui-pre.xml | 01:08 pre-dump.ps1 |
| ui-refused-40s.xml | ui-unlocked.xml | 01:08 press after ui-pre |
| ui-accepted.xml | ui-accept-final.xml | 01:39 post-drain press |
| ui-inactivity-locked.xml | ui-idle.xml | 01:45 idle capture |
| ui-background-return-locked.xml | ui-bg.xml | 01:53 resume capture (first pass; superseded by the one-driver P4b chain below) |
| ui-ref2-pre.xml | ui-ref2-pre.xml | 02:05 refusal-final2.ps1 in-script pre-press dump |
| ui-ref2-post.xml | ui-ref2-post.xml | 02:05 refusal-final2.ps1 in-script post-press dump |
| ui-armed2.xml | ui-armed2.xml | 02:05 arm2.ps1 arming dump |
| ui-p4b-pre.xml | ui-p4b-pre.xml | 02:12 bg-return-proof.ps1 in-script pre-state |
| ui-p4b-unlocked.xml | ui-p4b-unlocked.xml | 02:12 bg-return-proof.ps1 in-script post-unlock |
| ui-p4b-launcher.xml | ui-p4b-launcher.xml | 02:12 bg-return-proof.ps1 in-script launcher transition |
| ui-p4b-resumed.xml | ui-p4b-resumed.xml | 02:19 bg-return-proof.ps1 in-script resumed-locked |

## Token-exposure scan (scoped statement)

The only hex-literal strings in this package are the three DISCLOSED digest
values (APK sha256 — one 64-char literal — and APK md5 — one 32-char literal)
as committed in PROOF.md/provenance.txt/SHA256SUMS. A secret-shaped scan for
any OTHER 32-hex literal (excluding the disclosed md5 and substrings of the
disclosed sha256) over every text artifact returns zero matches; the driving
scripts carry the bench TEST PIN ("2468") in cleartext, disclosed above, and
no WB_TOKEN/server credential anywhere.

## Remaining (S-2b part 2, next tick)

- Biometric-where-supported (BiometricPrompt on the lock overlay + graceful
  PIN-only fallback where no sensor exists — BlueStacks has no fingerprint HW,
  so device evidence can only cover the graceful-absence path).
