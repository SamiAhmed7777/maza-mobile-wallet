# M8B-II-A window of 2026-11-28 02:02-02:53 PST: the M14-ii denial state and the M32 device proof

Lane: interactive lane, thread 54 (MAZA Skunkworks). Device: the BlueStacks Pie64 guest on the owner's PC, driven over adb by the lane's round helper. Every figure in sections 1 to 3 is parsed from a capture in this package by `scripts/m32_pack.py`; `DERIVED.txt` holds the parsed values and the two watch tables. Section 0 quotes the owner and the run log; of the run log itself only the judge's verdict line is in this package (timing/hold_grade.txt). Source lines quoted below are in source/source-lines.txt.

## 0. Authority and scope

- The owner's words that opened the window: "Keep fixing it till it's done" (Telegram message 1225, thread 54, 11-28). It answered the lane's report, which had asked for an OK to reopen the emulator for a 0.1 MAZA send. The run log line of 01:52 PST (in the backlog file, not in this package) recorded the lane's reading of that answer openly - it went through the judge before it was written (judge grade A, urn=urn:ump:h466fhskjoobcd7a4ki2dcz4u5ghfez34zjhlslocc6fhjtsru4q) - and scoped the window to two things: the M14-ii denial state, and the M32 device send once a graded M32 commit was on origin. The owner did not use the runbook's words ("the window is OK"); that is on record in that line. [timing/hold_grade.txt]

- Money: two sends in this window, 0.1 MAZA each, both from the bench account, each to a receive address of the same wallet (indices 6 and 7), so the funds stayed in the test wallet: send 4 for the denial state and send 5 for M32. The bench balance moved by the amount plus a 0.0001 MAZA fee each time (sections 2 and 3).

- Not touched: no uninstall, no data clear, no repair or disk check on the PC, nothing in the app source (the M32 code is the loop's, commit `b819df1`; this lane adds evidence files only).

## 1. The window

- Launched 2026-11-28 02:02:15.286 PST, player ready 2026-11-28 02:02:59.644 (44 seconds). [timing/launch-stop.txt]

- Closed by this lane at 2026-11-28 02:53:54 PST. The stop script tries the window's own close path first and fell back to its usual stop ("falling back to Stop-Process (the lane stop; writes no stop line of its own)"); it touches no guest data. Read-back: `tasklist` for the player process -> "INFO: No tasks are running which match the specified criteria.". [timing/launch-stop.txt, timing/w26_tasklist.out]

- Length: 51 minutes 39 seconds. DISCLOSED OVERRUN: the 01:52 line announced about 5 minutes. When the denial test was done the lane found the loop's M32 commit on origin, so it went on to the M32 device send in the same boot instead of closing and reopening. The window is closed; the veto stands again until the owner says the window is OK.

- Guest disk: the boot error count at 02:03:26 PST reads "guest error lines this boot: 0". At the end of the window the kernel log holds 2 `EXT4-fs` lines (the boot-time mount message for sda1 and sdb1), one boot-time firmware note ("[    0.660525] platform regulatory.0: Direct firmware load for regulatory.db failed with error -2"), and 0 `blk_update` lines. [timing/launch-stop.txt, after/w25.out]

## 2. Part A - M14-ii, the third state: notifications denied (PASS)

The app-ops route was shown not to gate delivery on this guest on 11-27 (the rn/ package). The switch tried here is the app's own notification-settings screen.

1. Build on the device: the 11-27 build (`codePath=/data/app/com.mazawallet-V-nPHHzLocdis6_rzUelqg==`, `lastUpdateTime=2026-11-27 03:00:21`). Its `POST_NOTIFICATION` app-ops entry still read `ignore` from the evening ("POST_NOTIFICATION: ignore"); set back to `default` and read back ("POST_NOTIFICATION: default"). [boot/w1.out, boot/w2.out, old-build/w12.out]

2. Connect: the bench token staged by the lane's script - "TOKEN len=32 class=safe", "TYPED-LEN 32", "CONNECT-TAPPED"; no token value is in any capture. Balance on screen after the connect: 46.1995774 MAZA. [boot/w_token.out, boot/w3.out]

3. Unlock with the PIN (placeholder `[PIN]` in the command list; the digits are substituted at run time and never written): unlocked: yes. WALLET tab, receive address index 6. [unlock/w4.txt, unlock/w4.out, unlock/to_addr.txt]

4. The app's notification settings: the master "Show notifications" switch reads ON at (1541,324); tapped once. The notification service then reports the app with `importance=NONE` and the screen shows "At your request, Android is blocking this app's notifications from appearing on this device". The wallet was not killed by this: process 3482; its log in that capture ends with a `GET /api/state -> 200` answer at 02:08:57.536. [switch/w5.out, switch/w6.out, switch/w7.out, switch/w6_off_red.ocr.txt]

5. Wallet back to the front (in front: yes), unlocked: yes, still blocked (`importance=NONE` present: yes). Baseline capture w9_00. [switch/w8.out, denial/w9_00.out]

6. SEND 4: 02:11:55 PST (2026-11-28 11:11:55 on the bench host's clock, CET), 0.1 MAZA to the index-6 address, HTTP 200, txid 73bfda3b33b16171ba75fd2a68f02a79a41bfed0c7f36a940341bd6537e574c5. Bench balance before: 46.1995774 MAZA. [denial/send4.out]

7. Watch: 22 captures, read-only - the baseline w9_00 before the send, then 21 rounds from 02:11:59 to 02:16:50 PST. The wallet's own poll picked the coin up (watch-set balance on screen 2.2999 MAZA before round w9_03, 2.3999 MAZA from that round on). Notification posts in every capture: 0. Notification records for the app in every capture: none. `importance=NONE` in every capture: yes. Wallet process in every capture: 3482. [denial/w9_00.out .. w9_21.out, denial/w9_times.txt, DERIVED.txt]

   The previous build (11-27, the committed rn/ package): its false echo reached the host log 101 seconds after the 0.2 MAZA send; 150 seconds after the 0.1 MAZA send. The last capture of the watch is stamped 295 seconds after the send time. That length is as recorded: the send time is the bench host's clock, the round times the lane's. The record count is the cumulative check; the log count is the immediate one. Both read zero throughout.

8. Bench state after send 4, 02:18:57 PST: balance 46.0994774 MAZA (= 46.1995774 - 0.1 - 0.0001 fee); watch set 2.3999 MAZA, 5 unspent coins, the least-confirmed of them with 7 confirmations. [denial/send4_state.out]

9. Switch restored. The dump before the tap shows the switch OFF (yes); the dump after it shows ON (yes) and no longer holds the banner (gone); `importance=NONE` is absent in the whole capture. [switch/w11_switch.txt, switch/w11.out]

Not used as evidence: the notification-shade screenshot of this part (switch/w10_shade_red.ocr.txt). Its OCR text shows only the clock and the date: the privacy box covers the card area. The denial claim rests on the service records and the log, not on that picture.

## 3. Part B - M32: an app-initiated send without the echo (PASS)

The defect: after a send the sampled bench balance dips to zero (the change is unconfirmed), then settles - a strict increase, which the poll announced as "MAZA received". The fix is the loop's: commit `b819df1` - M32: the app's own send-settle change no longer announces as "MAZA received" - judge grade A, urn:ump:zgx2sv7syeahfrfqy2h32h2qjq2a5po2ys64ynpgwpo53q3udx4a - on origin before the device work started (the lane found it there after the denial test). `SendEchoTracker` is a Java class of the app's `com.mazawallet.crypto` package (android/src/com/mazawallet/crypto/SendEchoTracker.java: line 52 declares it, line 54 its settle window); the tree's build-time self-test has a section for it (SelfTest.java line 329), and the lane's independent rebuild ran it: 28 lines starting "PASS sendecho:", among them "PASS sendecho: own change settling never fires". [source/source-lines.txt, apk/build.out]

- Git dates the loop's commit `b819df1` 2026-11-28 02:04:35 -0800 (committer date, read with `git log -1 --format=%cd --date=iso`): after the denial test the lane fetched and found it on origin. This log does not compare the clocks of different hosts; the time is given as recorded.

### 3.1 Is the APK in the tree a build of that commit? (checked independently by this lane)

- The APK on origin: 591033 bytes, sha256 2b8bf013bbc8e0e71e04eb191477997c5dd4aa3a6f3c96b0245a51e09cd4c3f1. The PC copy, hashed on the PC: 2B8BF013BBC8E0E71E04EB191477997C5DD4AA3A6F3C96B0245A51E09CD4C3F1 - the same digest. [old-build/w13_pc_sha.txt]

- Rebuilt by this lane from `git archive b819df1` with the tree's own build script: "ALL 375 CHECKS PASSED", "591033 bytes". The whole-file hashes differ; the unpacked entries do not: 16 of 16 entries are identical, `classes.dex` included, and the two unpacked trees were hashed again while this package was built (identical). [apk/build.out, apk/cmpA.sha, apk/cmpB.sha]

- So the file installed below is the tree's own APK, and that APK is a build of commit `b819df1`.

### 3.2 Install in place

- First push attempt failed: "adb: error: cannot stat ':\Users\hello\maza-bench-lane\m32-b819df1.apk'". Second attempt, forward slashes: "adb: error: cannot stat ':/Users/hello/maza-bench-lane/m32-b819df1.apk'". Cause, read from the round helper itself (`adbrun.ps1`, a script of the earlier android/evidence/m8b2a/ package, which is not committed yet; not changed in this window): line 26 reads `if ($line.StartsWith('push ')) { $i = $line.IndexOf(' ', 6); & $adb -s $dev push $line.Substring(6, $i - 6) $line.Substring($i + 1) 2>&1 | ForEach-Object { Emit $_ }; continue }`; line 25 reads `if ($line.StartsWith('pull ')) { $i = $line.IndexOf(' ', 6); & $adb -s $dev pull $line.Substring(6, $i - 6) $line.Substring($i + 1) 2>&1 | ForEach-Object { Emit $_ }; continue }`. Both handlers cut their first argument with `Substring(6, ...)`, but `push ` and `pull ` are 5 characters, so the first character is dropped: the drive letter of a local path on `push`; the leading slash of the remote path on `pull`, which resolves to the same file, so pulls worked. The `raw` verb passes its arguments through untouched. [old-build/w13.out, old-build/w14.out]

- `raw push` to the guest temp dir: "[100%] /data/local/tmp/m32.apk"; on the device: 591033 bytes, sha256 2b8bf013bbc8e0e71e04eb191477997c5dd4aa3a6f3c96b0245a51e09cd4c3f1 - the same digest as host, PC and origin. [install/w15.out]

- `pm install -r` inside the guest: "Success". Read back: `codePath=/data/app/com.mazawallet-TlqPW5KxiVy7PzddKGux5w==`, `lastUpdateTime=2026-11-28 02:33:07`, `firstInstallTime=2026-11-15 18:39:10` - the same as before the update (2026-11-15 18:39:10), so nothing was uninstalled or reinstalled; the app's PIN was still set afterwards (the same unlock worked: yes). [install/w16.out, old-build/w12.out, connect/w19.out]

- The installed file itself, hashed inside the guest: md5 e3c0f63458875c148e2d27245a5b57d0, sha256 2b8bf013bbc8e0e71e04eb191477997c5dd4aa3a6f3c96b0245a51e09cd4c3f1 - both equal the APK on origin. Temp copy removed: yes. The notification service no longer lists the app as blocked (`importance=NONE` absent), so the switch restored in Part A survived the update. [install/w17.out]

### 3.3 The form

- The new build started on its Connect card; FATAL lines in that capture: 0. Token staged again (the same three lines as before: identical capture), connected, balance on screen 46.0994774 MAZA; unlocked: yes; receive address index 7. [install/w17.out, connect/w18_token.out, connect/w18.out, connect/w19.out, connect/to_addr2.txt]

- SEND tab layout read from a dump: the form's button is `text="SEND"` at [24,492][1576,564] (the theme upper-cases it). Post count in the log at this point: 0. [form/w20.out]

- The two fields were typed from a command file the lane generated from the lifted address (nothing hand-typed: yes). The dump in that round failed ("ERROR: null root node returned by UiTestAutomationBridge."); that round sent nothing (`/api/send` lines in its log read: 0). A fresh dump read the fields back: address field equal to the lifted address: yes; amount field equal to 0.1: yes; `/api/send` lines in the log: 0. [form/w21.txt, form/w21.out, form/w22.out]

- Screenshot before the tap (redacted; its OCR text is in the package): `/api/send` lines in the log: 0. [form/w23.out, form/w23_form_red.ocr.txt]

### 3.4 The send

- The send round started at 02:40:52 PST by the lane's clock: one tap on the form's SEND button. The app logged "POST /api/send -> 200" (request no. 100) at 02:41:00.778 by the guest's clock; result on the tab: "Sent (bench account): 7b23db..7850". In the source at that commit the send path is marked "S-5: SPEND. Net's table gives /api/send exactly ONE attempt" (MainActivity.java line 1190; the send call is at lines 1194-1195); the log holds one POST for the one tap. [send/s1_times.txt, send/s1.out, source/source-lines.txt]

- BALANCE tab right after: 0.00000000 MAZA at "Last sync 2026-11-28 02:41:09" - the dip. Post count: 0. [send/s1.out]

### 3.5 The watch

- Batch 1, 12 rounds from 02:41:32 to 02:43:39 PST, read-only. (The watcher stops early only when a screen dump matches a target text it was given; in the two M32 batches it stopped early 0 times.) Round m1_01: post count 0, no record yet, and the balance tab already reads 45.9993774 MAZA with "Last sync 2026-11-28 02:41:39" - the climb. From round m1_02 on every capture holds exactly one notification host call: 11-28 02:41:41.279, package com.mazawallet, "MAZA received", "+0.10000000 MAZA - self-custody wallet" - the genuine receive of the 0.1 MAZA into the wallet's own address (the watch set went from 2.3999 to 2.4999 MAZA between the two bench-state reads). Post count before that round: 0; from it on: 1. Notification records for the app before that round: none; from it on: 2. Wallet process: 7538 in every round. The balance tab was not readable in round m1_06 (its dump came back with the transient error of section 5); every other round shows 45.9993774 MAZA. [watch/m1_01.out .. m1_12.out, watch/m1_times.txt, DERIVED.txt]

- Batch 2, 9 rounds from 02:48:32 to 02:50:09 PST: notification records for the app id 2 in every round; wallet process 7538 in every round; post count 0 in every round. That count is lower than batch 1's: `logcat -d` is not a fixed record. The 02:41:41 line is in every capture of batch 1 from round m1_02 on and in none of batch 2 (my reading is that the log buffer had moved on; I did not check that). The service records are the cumulative evidence. The balance tab was not readable in round m2_04 (its dump came back with the transient error of section 5); every other round shows 45.9993774 MAZA. [watch/m2_01.out .. m2_09.out, watch/m2_times.txt, DERIVED.txt]

- At the end of the window: `codePath=/data/app/com.mazawallet-TlqPW5KxiVy7PzddKGux5w==`, `lastUpdateTime=2026-11-28 02:33:07`; the notification service holds 2 record(s): the wallet's id 2 and one android record (id 19); wallet in front: yes. [after/w24.out]

- Bench state at 02:52:19 PST: balance 45.9993774 MAZA (= 46.0994774 - 0.1 - 0.0001 fee); watch set 2.4999 MAZA, 6 unspent coins, confirmations [12, 44, 296, 298, 312, 17151]. [after/bench_state_m32.out]

### 3.6 Why "one record" proves "no echo"

- From the app's source at commit `b819df1`: `29: private static final int ID_BENCH = 1;`; `30: private static final int ID_WALLET = 2;` - the comment above them reads "Distinct ids so a bench receive and a seed receive never overwrite each other's notification.". The post call is `123: nm.notify(id, b.build());`, the text `121: .setContentText("+" + fmtMaza(deltaSats) + " MAZA - " + source)`. So the echo would be its own record, id 1; it cannot hide behind the genuine one. [source/source-lines.txt]

- The previous build, send of 0.5 MAZA at 21:58:26 PST (11-27): the service held records 1 and 2 for the app; the host log in the committed capture shows 11-27 22:00:16.066 "+0.50000000 MAZA - self-custody wallet" (110 s after) - the echo's own log line is not in that capture; its record, id 1, is. [rn/locked/l1.out, rn/locked/send1.out]

- The previous build, send of 0.2 MAZA at 22:09:43 PST (11-27): the service held records 1 and 2 for the app; the host log in the committed capture shows 11-27 22:11:24.134 "+46.29967740 MAZA - bench account" (101 s after); 11-27 22:11:25.335 "+0.20000000 MAZA - self-custody wallet" (102 s after). [rn/backgrounded/a3.out, rn/backgrounded/send2.out]

- The previous build, send of 0.1 MAZA at 22:14:14 PST (11-27): the service held records 1 and 2 for the app; the host log in the committed capture shows 11-27 22:16:44.454 "+46.19957740 MAZA - bench account" (150 s after); 11-27 22:16:46.200 "+0.10000000 MAZA - self-custody wallet" (152 s after). [rn/denial-not-done/d2.out, rn/denial-not-done/send3.out]

- So the echo's log line was captured in 2 of those 3 cases: 101 seconds after the 0.2 MAZA send; 150 seconds after the 0.1 MAZA send. This build: the dip and the climb happened (0.00000000 at 02:41:09, 45.9993774 at 02:41:39) and the service held id 2 only - read in every round of batch 1 from round m1_02 on and in every round of batch 2, the last one ending 549 seconds after the send as recorded (guest clock for the POST, lane clock for the rounds). No record with id 1 appeared in any capture of this window.

## 4. What this package does not claim

- It does not claim the previous build's echo latency beyond what the rn/ package records, and it does not claim the log count after 02:43:39: from 02:48:32 the record check is the evidence.

- The gap between the two batches (02:43:39 to 02:48:32) was not watched round by round. An echo in that gap would have left a record with id 1, and none exists afterwards.

- The shade screenshot taken at the end (after/w24_redact.txt) is not evidence of anything: the privacy box covers the cards.

- Three clocks feed this log: the bench host's (send times of part A and of the 11-27 sends), the lane's (round times) and the guest's (the app's own log). No capture in this package compares them, so every "N seconds" figure is as recorded.

- One send on one device. The tracker's own limits are covered by the loop's tests for commit `b819df1`, not by this package.

- The M14-ii denial result is for the app's master switch on this guest. App-ops `ignore` was shown not to gate delivery on 11-27 (rn/ package).

## 5. Faults met in this window

- The round helper's `push` and `pull` handlers drop the first character of their first argument (section 3.2). Not changed in this window: it belongs to the earlier package, which is not committed yet. Use `raw push` until its owner fixes it.

- A UI dump taken right after a tap failed with "ERROR: null root node returned by UiTestAutomationBridge." in these captures: m1_06.out, m2_04.out, w21.out, w6.out. A second dump a moment later worked each time.

- The log (section 3.5): a count read from `logcat -d` is evidence for minutes, not for the whole window.

## 6. Privacy

- This is a public repository. Two captures are host-side (the owner's PC): the launch/stop record and the boot error count. They go in as trimmed excerpts of allow-listed lines only (timing/launch-stop.txt); their memory figures and process lists stay in the lane's private archive. No PNG is in the package: the redacted screenshots stay in the lane's private archive and the OCR text of three of them is here. The PIN and the bench token are not in any capture: the PIN is substituted at run time, the token travels only as a header.

- Addresses and transaction ids are test-wallet public data, as in the rn/ package.

## 7. Files

- timing/ launch-stop.txt (trimmed excerpt of two host-side captures), hold_grade.txt (the judge's verdict line for the run-log line that opened the window), w26_tasklist.out
- source/ source-lines.txt (the source lines quoted in this log, read from commit b819df1 with `git show`)
- boot/ w1-w3 (boot check, app-ops reset, first start), w_token.out (token staged)
- unlock/ w4 (PIN unlock, WALLET tab), to_addr.txt (receive address, index 6)
- switch/ w5-w8, w10, w11 (the switch off, the checks around it, on again), the OCR of the OFF screenshot, w11_switch.txt
- denial/ w9_00-w9_21 (baseline and the watch), w9_times.txt, the watcher logs, send4.out, send4_state.out
- old-build/ w12-w14 (identity before the update, the two failed pushes), w13_pc_sha.txt
- apk/ build.out, cmpA.sha, cmpB.sha (the independent rebuild)
- install/ w15-w17 (push, install, identity of the installed file)
- connect/ w18-w19 (reconnect on the new build), w18_token.out, to_addr2.txt (receive address, index 7)
- form/ w20-w23 (layout, typing, read-back, screenshot)
- send/ s1 (the send)
- watch/ m1_01-m1_12, m2_01-m2_09 (the two watch batches), their times and logs
- after/ w24-w25 (final state, kernel and crash lines), bench_state_m32.out
- scripts/ watch.sh (the watcher), m32_pack.py (this builder)
- DERIVED.txt, RUNLOG.md, SHA256SUMS

Round mechanics: a `.txt` file is the command list (one adb or host command per line), the `.out` file is what the device and the helper printed, the `.sum` file is the round's own one-line summary with its exit status. The round runner is `round.py` in the committed `rn/scripts` set; the PC-side helper `adbrun.ps1` belongs to the earlier package, which is not committed yet.

## 8. Rebuild

On the lane host only: the script reads the raw captures in the lane's scratch directory, which is not in the repository.

    python3 m32_pack.py facts   # parses every fact from the captures and prints it; writes nothing

    python3 m32_pack.py build   # rebuilds this package; it refuses to write on any value it cannot parse

