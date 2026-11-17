# S-2b part-1 driving transcript (all times PST, UTC-08:00, 2026-11-17)

JUDGE ARC: r1 (direct-stdin Codex primary, healthy REPLY-OK probe) returned
grade C with three blockers, all packaging-level; dispositions in this
revision: (1) the 15-minute-cap claim narrowed to an incidental
transcript-only observation (PROOF.md "15-minute CAP" paragraph); (2) raw
verbatim build/install/hash provenance attached as provenance.txt (host
sha256/md5/size re-run + device dumpsys/pm-path/installed-md5 re-run — the
installed app still carries this build, so those outputs are live-checkable);
(3) immutability: this gate is the PRE-COMMIT grade — the graded bytes land
as the commit itself on grade >= B, at which point the revision becomes
immutable and auditable (standard flow for every commit in this repo).
Polish folded: SHA256SUMS manifest, capture-provenance table (PROOF.md),
status-bar-clock corroboration for the P4a/P4b durations, scoped
token-exposure statement (grep-verified: zero unexpected hex literals),
ui-lock2/ui-lock3 capture clarification.


Host: DNS2 (repo + orchestration) -> SAMI-PC (Windows, BlueStacks Pie64,
`C:\Program Files\BlueStacks_nxt\HD-Adb.exe`, adb device emulator-5554).
Every adb command ran with `-s emulator-5554`. UI state was ALWAYS read via
`uiautomator dump` + `adb pull` (never eyeballed from downscaled screenshots).

00:14  Tick start. Reconcile: git log matches backlog claims through 8cf4dc6
       (S-2a). Conflict guard: last repo write 23:38 (35m quiet), no live
       delegations. Bench healthy via tunnel (root 200, /api/state 401).
00:15  BlueStacks launched via one-shot schtask -> bench_launch.cmd
       (HD-Player --instance Pie64) in the interactive console session.
00:24  `bash android/build-apk.sh` -> selftest stage [1/6] ALL 49 CHECKS
       PASSED -> SIGNED OK, 283604 bytes. (r1 note: the build/run output is
       setup narrative, not attached raw text; the CHECKABLE provenance —
       host sha256/md5/size and the installed device state — is attached as
       raw verbatim output in provenance.txt.)
00:28  sha256 499192b3… md5 a9ace56b… ; scp APK to SAMI-PC (283,604 bytes).
00:29  `adb push` (283604 bytes, size asserted) + `pm install -r` -> Success.
00:30  `pm path` -> /data/app/com.mazawallet-izZZG2O1_Thqc7j3XNvcoQ==/base.apk;
       lastUpdateTime 2026-11-17 00:29:46; installed base.apk md5
       a9ace56ba5707a4c7d8993228c844c70 == host APK md5.
00:31  am start -> uiautomator dump ui1: Connect card, saved URL
       http://100.121.150.22:18701 (pref persistence), token field EMPTY
       (hint "bench token"). Coordinates: token (800,455), CONNECT (800,576).
00:33  Token staged to C:\Users\hello\.maza-token via `ssh sami-pc powershell`
       with the token piped ON STDIN (never in argv/logs). First connect drive
       (echo $tok | adb input text) -> BlueStacks GameCenter overlay appeared;
       its force-stop left a black surface. Token file deleted
       (TOKENFILE-DELETED=True).
00:35  App restarted (am start) -> Connect card again (ui3: token hint visible).
00:38  Second connect attempt with `input keyevent 4` to dismiss the keyboard:
       BACK finished the activity -> app went to the BlueStacks launcher.
       LESSON: no BACK/ESC keyevents on this shell.
00:41  connect-drive3.ps1: am start -> tap token field -> input text $tok ->
       tap the non-editable "Server URL" row (keyboard dismiss WITHOUT
       keyevents) -> dump (32 masked bullets confirmed, CONNECT visible) ->
       tap CONNECT -> 7s wait.
00:44  Dump: BALANCE tab rendered (0.00000000 MAZA, Last sync 00:49:09, five
       tabs). CONNECTED. (Server-side corroboration: the connect POSTs are
       bearer-authenticated; balance/sync render requires a 200 session.)
00:46  WALLET tab (1440,858) -> "My Wallet / Self-custody", receive index 4
       address MRQswDmXBiGqqmtPzHh2ViMkEL7uNDaaPy (seed intact through the
       update install).
00:47-00:49  swipe up x3 -> SECURITY card: "No PIN set..." + SET PIN button.
00:50  Set PIN dialog (dump ug): two fields (800,409)/(800,489), SAVE (1149,604).
00:52  Typed test PIN in both fields (adb input text), SAVE -> dump uh:
       "PIN lock ON · auto-lock after 5 min of inactivity (also locks while
       backgrounded)." + CHANGE PIN / REMOVE PIN. Screenshot s1-security-armed.
00:53  am force-stop + am start -> dump ui-lock1: Connect card (token
       memory-only). Screenshot s2-fresh-connect (field shows HINT = empty).
00:55  p1-drive.ps1: token re-staged via stdin -> tap token -> type -> dismiss
       keyboard via URL-row tap -> CONNECT -> dump ui-lock2 at ~7s: BALANCE
       rendered, overlay NOT yet up (first 10s autoLockTick not elapsed).
00:56  Dump ui-lock3 (+screenshot s3-immediately-locked): "Wallet locked" /
       "Enter your PIN to continue." / PIN field / UNLOCK over the BALANCE
       content — P1 proven: fresh connected session starts LOCKED with zero
       taps (raised by the 10s tick; the gate decision is authoritative).
00:58  Wrong-PIN attempt: tap field (800,375) -> input text 9999 -> tap UNLOCK
       (800,496) -> dump ui-wrong1 + screenshot s4-wrong1: "Wrong PIN - try
       again.", field cleared.
00:59-01:02  4-attempt batch (tap field/text/unlock x4, keyboard open
       between steps) -> dump ui-throttled + screenshot s5-throttled: still
       "Wrong PIN - try again." — batch misfired (see driving-difficulty note
       in PROOF.md): some UNLOCK presses ran with stale contents; streak
       climbed but the throttle message was overwritten by the last wrong-PIN
       render each time.
01:03  Fixed attempt (dismiss keyboard by tapping the overlay title at
       (800,262) before UNLOCK) -> dump ut: "Too many attempts - wait 9s."
       THROTTLE ENGAGED (5 consecutive failures).
01:05  Second fixed attempt -> throttle re-render (countdown decayed).
01:06  throttle-proof.ps1: sleep 12 (window expiry) -> wrong attempt -> dump
       ui-backoff60 + screenshot s5-backoff60: "Wrong PIN - try again." with a
       NEW window opened (message-overwrite render order; the window is live
       but the visible text is the wrong-PIN message). Immediately: correct-PIN
       attempt -> dump ui-refused-correct + screenshot s6-refused-correct:
       "Too many attempts - wait 113s." — a 120s window (2x base) 7s decayed:
       DOUBLING rendered on-device.
01:07  refusal-clean.ps1: correct-PIN attempt -> "Wrong PIN - try again." —
       the attempt EVALUATED (window had expired) and the field content was
       wrong (the keyboard-pan gremlin: stale content + the dismissal tap).
       Honest note: this attempt is what re-opened the window chain.
01:08  pre-dump.ps1: tap field -> type correct PIN -> DUMP FIRST (ui-pre:
       FIELD len=4 bullets, bounds [36,341][1564,409]) + screenshot s8-pre
       (4 masked bullets visible) -> THEN unlock press -> dump ui-unlocked +
       screenshot s-refused-40s: "Too many attempts - wait 40s." — the CORRECT
       PIN refused during the live window WITHOUT evaluation (the field
       contents were pinned by the dump one step earlier; if the PIN had been
       evaluated and matched, the overlay would have closed).
01:10  Unlock attempt (typed, no pre-dump) -> "Wrong PIN - try again."
       (stale-content gremlin again; opened the next window).
01:12  pre2.ps1: tap -> type -> keyevent 66 (ENTER closes IME) -> dump ui-pre2:
       keyboard GONE, FIELD len=4 bullets, UNLOCK at [36,460][1564,532] ->
       unlock press -> "Too many attempts - wait Ns." (window still live).
01:14  final-accept.ps1 (clean flow) -> still throttled: presses stayed
       refused across the long window the sustained wrong-attempt chain had
       armed (see PROOF.md's narrowed "15-minute CAP" paragraph: no dump
       renders a near-cap message; the cap VALUE rests on the desktop-verified
       LockPolicy constants). No further unlock attempts until the window
       drained.
01:16-01:2x  Evidence pulled from SAMI-PC, vision-checked (token-clean: the
       Connect screenshot shows the hint; PIN screenshots show masked bullets
       only, no digits), staged in android/evidence/s2b-pin/, PROOF.md +
       transcript written.
01:29  pre2.ps1 re-run -> field showed 12 bullets: the THROTTLED early-return
       path in doPinUnlock does NOT call showLock, so it never clears the
       field — my three typed "2468"s had concatenated ("246824682468"). This
       is a genuine UI behavior discovered during the drive (wrong-PIN renders
       clear the field; throttle refusals leave it).
01:32  clear-retype.ps1: tap field -> keyevent 123 (END) -> 12x keyevent 67
       (DEL) -> dump (cleared) -> type 2468 -> dump ui-ready: FIELD = exactly
       4 bullets; message "Too many attempts - wait 238s." (countdown noted;
       later discovered the throttle message is a STATIC render — it does not
       tick down between re-renders — so drain state must be confirmed by
       re-pressing after generous elapsed time, not by watching the text).
01:36  ready2.ps1 (no keyevent 66 anywhere in the flow): clear + retype +
       dump -> the in-script dump failed silently (native adb failures do not
       throw under PowerShell Stop), retried as a standalone dump: FIELD = 4
       bullets, message STILL "wait 238s" (same static render as 01:31 —
       confirming it is stale text, and the window it names ended ~01:35:30).
01:39  UNLOCK tap (800,496) -> dump ui-accept-final + screenshot s9-unlocked:
       overlay GONE, BALANCE rendered (Last sync 01:39:36). ACCEPTANCE after
       window drain proven. (The accepted verify resets the wrong-attempt
       streak per LockPolicy.)
01:39-01:45  P4a INACTIVITY LOCK: zero input 5m10s (background poll kept
       syncing: Last sync 01:45:44 — polls are not activity by design) ->
       dump ui-idle + screenshot s10-idle-locked: overlay UP.
01:46  unlock-for-p4b.ps1: tap -> type -> dump ui-r1 (FIELD = 4 bullets) ->
       tap UNLOCK -> dump ui-r2: overlay GONE (accepted; streak reset).
01:47-01:53  P4b BACKGROUND-RETURN LOCK: backgrounded via monkey launch of
       com.uncube.launcher3 (no keyevent navigation) for 5m30s -> am start ->
       dump ui-bg + screenshot s11-bg-locked: root package com.mazawallet,
       overlay UP (onResume found backgrounded >= autolockMs).
01:54  final unlock (same tap flow) -> dump: no overlay. Device left
       UNLOCKED on BALANCE. Evidence pulled, vision-checked (token-clean:
       hint-only token field; PIN visible only as masked bullets), staged.
01:56-02:05  r1 judge round (see JUDGE ARC header) -> blockers + polish
       folded into this revision: provenance.txt + SHA256SUMS written,
       PROOF.md capture-provenance table added, cap claim narrowed to an
       incidental transcript-only observation, scoped token scan added,
       status-bar-clock corroboration documented. SHA256SUMS regenerated
       over the FINAL bytes of every artifact after all edits.

02:0x  r2 judge round -> grade C, two blockers (refusal chain not
       self-authenticating; P4b not distinguished from inactivity lock).
       Dispositions: (1) arm2.ps1 re-armed a 60s window and
       refusal-final2.ps1 ran as ONE script (clear -> dump -> type PIN ->
       dump pre [4 bullets] -> press -> dump post [throttle re-render,
       remaining 20s]) -> ui-ref2-pre/ui-ref2-post/s12 committed;
       (2) bg-return-proof.ps1 ran as ONE script (pre dump -> unlock press ->
       unlocked dump + s13 [clock 2:13] -> monkey launcher launch -> launcher
       dump -> 330s sleep -> am start -> resumed-locked dump + s14 [clock
       2:19]) -> the launcher-foregrounded dump sits between unlocked and
       resumed-locked, distinguishing background-return from inactivity lock.
       Polish folded: provenance.txt device outputs labeled with ### CMD
       headers; 113s->120s mapping labeled code-derived inference in
       PROOF.md. SHA256SUMS regenerated over final bytes.
02:2x  r3 judge round -> GRADE A, ZERO blocking issues (direct-stdin Codex
       primary; 7 verification reasons incl. manifest validation, secret
       scoping, and both driver chains). Polish folded post-grade with
       disclosure: P3 heading renamed to avoid the bare word "cap"
       (non-substantive; the disclaiming text was already in place). The
       other two polish notes are future-package guidance (keep a
       cleared-state dump in the set; attach raw build log if build
       EXECUTION ever becomes a graded claim) — recorded here, not acted on.
