# M8B-II-A evening run: receive-notification check (M14-ii), two of three states done

Evening of 2026-11-27, Pacific time. The package runs from boot 1 at 20:14:55 to a final bench reading at 2026-11-28 07:51:35 CET context/bench_state_final.out:1. The bench host prints CET (UTC+1, nine hours ahead).

This package holds device-side and bench-side captures only. Host-side diagnostics (process lists, memory figures, Windows event logs) stay out of this public repo and are archived privately on the lane host. Nothing was edited by hand: each `.out` file is the raw capture of the command file beside it (`.txt`), each `*_screen.txt` is a parsed listing of the screen dump in that capture, each `*.ocr.txt` is unedited machine OCR of the screenshot beside it, and the other excerpt files are line selections made by `scripts/rn_pack.py`.

## Authorization and coordination
- The emulator had been closed by a person on the morning run (powered off at 03:50:02 faults/boot1_timeline.txt:3). It was reopened tonight only after the owner's "reopen as needed".
- A hold line was written to the backlog run log before the launch. Every loop tick since then stood down and left the repo alone: 6 ticks are captured in context/loop_ticks_stood_down.txt, from 2026-11-27_20-39-25 on, each with its decision line context/loop_ticks_stood_down.txt:12. A tick that lands later is not captured here.

## What happened to the emulator (PST)
- Boot 1 ready at 20:16:03 faults/boot1_timeline.txt:5.
- 20:19:07 first guest block error, 244.928761 s into the boot: `I/O error, dev sdb, sector 252312408` faults/guest_disk_errors_boot1.txt:4.
- 20:23:12 `sda` starts failing too faults/guest_disk_errors_boot1.txt:11.
- From 20:23:18 the filesystem logs ext4 errors: 996 lines up to 20:36:08 faults/guest_disk_errors_boot1.txt:42, peaking at 120 a minute faults/guest_disk_errors_boot1.txt:46. The last log line before the stop names the partition: `EXT4-fs error (device sda1)` faults/boot1_timeline.txt:6.
- The guest shell then fails. `pm` itself returns `/system/bin/cmd: I/O error` faults/n0.out:13. In the next round `exec '/system/bin/sh' failed: I/O error` on 6 of its 6 commands faults/n1.out:3; in the retries after that, 4 of 4 faults/n2.out:3.
- 20:41:08 instance stopped faults/boot1_timeline.txt:7. No repair of any kind. The host diagnosis was read-only: no warnings or errors during the fault window faults/host_events_summary.txt:5 and no storage, power or hardware events in the prior 48 h faults/host_events_summary.txt:7. BlueStacks had not changed: program files dated 2025-03-24 faults/bluestacks_version.txt:3.
- 2026-11-27 20:42:43 to 2026-11-27 21:01:19 faults/snapshot_readback.txt:11 both engine disk images were read whole faults/snapshot_readback.txt:5 faults/snapshot_readback.txt:6, copied, and the copies read back identical faults/snapshot_readback.txt:10. Two starts are on record, the second at 2026-11-27 20:48:35. The copy is kept on the host until the owner decides.
- 21:03:17 relaunch, boot 2 faults/boot2_error_counts.txt:3: zero guest error lines at every reading from 21:04:45 to 21:20:57 faults/boot2_error_counts.txt:5. Boot 1's first error had come 244.9 s in faults/guest_disk_errors_boot1.txt:27.
- 21:09:15 the app unlocks (`POST /api/unlock -> 200`, `unlock ok`) faults/n9.out:15 and at 21:09:16 dies with `Fatal signal 6 (SIGABRT)` in `RenderThread` faults/n9.out:20.
- 21:14:20 the same abort after an app relaunch (two of two). The renderer logs `Impossible totalDuration 0` faults/n11.out:19 and the process aborts faults/n11.out:20.
- One ADB `reboot` was then tried. The guest kernel log stops at `reboot: Restarting system with command 'adb'` faults/adb_reboot_hang.txt:6, and the device answers `offline` faults/n13.out:6 faults/n13.out:9.
- The instance was stopped and launched again: boot 3, launched 21:21:52 faults/boot3_error_counts.txt:3. Zero guest error lines for its whole life: 1090 log lines, powered down 3506.030083 s in faults/boot3_error_counts.txt:5 faults/boot3_error_counts.txt:6. A search of the app's log for `Fatal` and `totalDuration` returns nothing faults/n17.out:23.
- 22:20:18 a person closed the window: `Topbar: Close clicked` denial-not-done/close_by_user_2220.txt:4, then `reason Close_by_user` denial-not-done/close_by_user_2220.txt:5, clean power-down at 22:20:27 denial-not-done/close_by_user_2220.txt:14.
- Not reopened. Every device command after that failed with `device 'emulator-5554' not found`: 9 of 9 commands, at script exit status 0 exit_statuses.txt:9.

Memory pressure was present in every episode: commit charge about 92% of the commit limit during the episodes and about 80% with the emulator off faults/host_events_summary.txt:10 (ratios only; figures in the private archive).

Root cause of the disk fault and of the renderer abort: not determined (see Open questions).

## The check
The app polls every 15 s while locked and while backgrounded, and announces a receive on a strict increase of a watched balance between two consecutive samples. Each state needs its own confirmed send to the wallet's self-custody receive address, which is in the app's watch set.

- Gate, bench node synced: gate/ibd_probe_2.out:1, block count 4498163 and header count 4498163, gate/ibd_probe_2.out:5. The probe ran on the bench host.
- The poll runs while locked, with the lock cover in front. In the State 1 capture the log holds a full cycle at 22:00:29 locked/l1.out:12, then unspent coins locked/l1.out:13 and history locked/l1.out:14, and the screenshots taken seconds later in the same round show `Wallet locked` locked/l1_locked_cover.ocr.txt:5 with the wallet the resumed activity locked/l1.out:9. Two earlier cycles, at 21:44:12 locked/r_rn1.out:7 and at 21:44:27 locked/r_rn1.out:10, were read as the first step of a round that then typed the PIN and pressed UNLOCK locked/r_rn1.txt:8. No screen was captured before that unlock, so the lock state at those two times rests on the app's own rule (it locks after an inactivity window and on return from background, `android/src/com/mazawallet/crypto/LockPolicy.java`) and not on a screen.
- The poll runs while backgrounded: cycle at 21:53:08 context/n22.out:10.
- Starting balances: bench account `mobile-play` 46.9998774 MAZA context/bench_state_0.txt:3; watch set 1.4999 MAZA in 1 coin context/bench_state_0.txt:4, shown on the wallet's own screen at receive address index 4 context/n20_screen.txt:9.

### State 1, locked: PASS
- Send 1: 0.5 MAZA at 2026-11-28 06:58:26 CET, HTTP 200 locked/send1.out:2.
- Watch set 1.4999 at 21:59:52 locked/send1_watch.out:3, then 1.9999 at 22:00:11 locked/send1_watch.out:4: the coin confirmed.
- Posted at 22:00:16: `MAZA received`, `+0.50000000 MAZA - self-custody wallet` locked/l1.out:11. The wallet was the resumed activity, on its lock cover locked/l1.out:9.
- `l1_locked.png` (shade over the lock cover; OCR locked/l1_locked.ocr.txt:7), `l1_locked_cover.png` (cover alone, OCR locked/l1_locked_cover.ocr.txt:5). Commands: locked/l1.txt:7.
- The same shade holds a second wallet notification, `+46.49977740 MAZA - bench account`, and nothing was sent to the bench account. See Defect locked/l1_locked.ocr.txt:10.

### State 2, backgrounded: PASS
- Unlocked, then Android Settings put on top: the wallet's activity is paused at 22:08:31.964 backgrounded/a2.out:23, Settings is the resumed activity backgrounded/a2.out:15, the process is alive backgrounded/a2.out:17, and a full poll cycle runs at 22:09:06 backgrounded/a2.out:26 through backgrounded/a2.out:28.
- Send 2: 0.2 MAZA at 2026-11-28 07:09:43 CET backgrounded/send2.out:2, to the app's current receive address. The app had moved past the used address: context/r_a0_screen.txt:9.
- Watch set still 1.9999 at 22:11:12 backgrounded/send2_watch.out:3, then 2.1999 at 22:11:31 backgrounded/send2_watch.out:4, so the advanced address is watched too.
- Posted at 22:11:25 while paused: `+0.20000000 MAZA - self-custody wallet` backgrounded/a3.out:17. The last activity events are the wallet's pause at 22:08:31.964 backgrounded/a3.out:12 and Settings resuming at 22:08:32.243 backgrounded/a3.out:13; nothing for the wallet follows.
- After the shade was opened and closed, Settings is still the resumed activity backgrounded/a3.out:571 and the wallet is still the background process backgrounded/a3.out:573.
- `a3_bg.png`: shade over Settings, no wallet screen behind it. OCR backgrounded/a3_bg.ocr.txt:7.

### State 3, notifications denied: NOT DONE
- Switch used: `cmd appops set com.mazawallet POST_NOTIFICATION ignore` denial-not-done/d1.txt:3, read back as `POST_NOTIFICATION: ignore` before the send denial-not-done/d1.out:8 and after it denial-not-done/d2.out:9.
- Send 3: 0.1 MAZA at 2026-11-28 07:14:14 CET denial-not-done/send3.out:2. Watch set still 2.1999 at 22:16:28 denial-not-done/send3_watch.out:6, then 2.2999 at 22:16:46 denial-not-done/send3_watch.out:7.
- The notification was posted anyway, at 22:16:46: `+0.10000000 MAZA - self-custody wallet` denial-not-done/d2.out:22. On this Android 9 guest that switch does not gate delivery, so this round is a non-result: neither a pass nor a fail of the denial path.
- The system's own per-app switch is Settings, Apps, MAZA Wallet, Notifications, "Show notifications" - not yet exercised here. That screen was opened in the round after denial-not-done/d3.txt:4; the switch is `ON` denial-not-done/d3_screen.txt:17. It was never flipped: the window was closed denial-not-done/close_by_user_2220.txt:4 before the next round could reach the device denial-not-done/d4.out:5.
- Still to do: switch it off, send a fourth distinct amount, show no notification and the wallet unaffected, switch it back on.

## Defect: the app announces its own change as a receive
Every bench send produced a second notification:
- Send 1, locked: `+46.49977740 MAZA - bench account`, read off the shade screenshot by OCR locked/l1_locked.ocr.txt:10. The capture lists two wallet notification records locked/l1.out:19 locked/l1.out:67, but the system dump redacts their bodies locked/l1.out:38, and its log excerpt was cut to four lines, which dropped the hook line of the bench post.
- Send 2, backgrounded: `+46.29967740 MAZA - bench account` backgrounded/a3.out:16, posted at 22:11:24. The shade screenshot reads the same backgrounded/a3_bg.ocr.txt:10.
- Send 3, notifications switched off: `+46.19957740 MAZA - bench account` denial-not-done/d2.out:21, posted at 22:16:44 denial-not-done/d2_blocked.ocr.txt:10.

Three of three. Each is the change of that send, and the balances read before the sends give it to the digit. Before send 2: 46.4997774 backgrounded/send2.out:1. Before send 3: 46.2996774 denial-not-done/send3.out:1. The difference is send 2's 0.2 MAZA plus a fee of 0.0001. Cause:
- The balance the app samples is the confirmed-unspent sum walletbench/api.py:809, and the node call keeps coins with at least one confirmation walletbench/chain.py:115.
- A send spends the largest coin whole walletbench/chain.py:142 and pays the change to a freshly derived address walletbench/api.py:890 walletbench/api.py:349; the change is the total minus amount minus fee walletbench/chain.py:151.
- So the account's reported balance drops to zero and comes back lower. The zero is captured: `GET /api/state -> 200 balance=0` backgrounded/send2.out:4 at 2026-11-28 07:09:47 CET, the send having gone out at 2026-11-28 07:09:43 CET; the same after send 3 denial-not-done/send3.out:4.
- The app fires on any strict increase between two samples android/src/com/mazawallet/crypto/NotifyPolicy.java:56, so the change confirming looks like a receive.

The wallet's own self-custody send path probably has the same shape; it was not exercised tonight. Proposed as backlog item M32. The fix needs its own lane, with tests and a gate.

## State left behind
- Bench: 2.2999 MAZA in the wallet's self-custody watch set, against 1.4999 before, out of the bench account, plus the fees. Bench account at the final reading 46.1995774 context/bench_state_final.out:1.
- Guest: the app-ops entry `POST_NOTIFICATION: ignore` for `com.mazawallet` was left set (last read denial-not-done/d2.out:9). It had no observed effect. Its reset never ran: the shell rejected `appops reset`, and the `set ... default` came when the device was already gone denial-not-done/d4.out:5. Whether it survived the power-down is unchecked. Reset it at the next launch and read it back.
- Guest: the wallet's "Show notifications" switch is unchanged denial-not-done/d3_screen.txt:17.
- Host: the disk-image copy is kept until the owner decides.
- Bench host: the send helper stays in the private lane directory for the remaining send.

## Lessons, each verified tonight
1. `round.py` writes its raw capture to `<cmds>.out` and also prints a copy of each line to its own stdout, cut at 240 characters and without the XML lines (`scripts/round.py`, the loop after the capture is written). Redirecting that stdout onto the capture path overwrites the first part of the raw capture with the printed copy. `locked/n18.out` was taken that way and is spoiled: two end markers locked/n18.out:15 locked/n18.out:25, the script's summary line inside the capture locked/n18.out:17, the first screen dump's output missing where its command stands locked/n18.out:9, and after the summary the tail of the raw capture, the same commands again locked/n18.out:19. The HISTORY tab reading of that round is not in the file. stdout goes to a `.sum` file.
2. A round's exit status 0 means the script ran, not that the device answered exit_statuses.txt:9. Read the capture for `[e]` lines denial-not-done/d4.out:5.
3. Opening the shade over the BlueStacks launcher dismisses the launcher and brings the previous app back: launcher paused at 21:52:28.983 context/n23.out:14, wallet resumed at 21:52:28.990 context/n23.out:15. Use Android Settings as the cover app for backgrounded captures.
4. ADB `reboot` parks this instance faults/adb_reboot_hang.txt:6. Use stop and launch.
5. After the renderer abort an app relaunch does not help faults/n10.txt:7: the abort recurs faults/n11.out:20. A full instance restart cleared it faults/n17.out:23.
6. `cmd appops set ... POST_NOTIFICATION ignore` does not block notifications on this guest denial-not-done/d2.out:9 denial-not-done/d2.out:22.
7. An empty `pidof` context/a1.txt:6 with no log lines context/a1.txt:7 was a capture glitch, not a kill: the next round shows the process alive context/n21.out:7.
8. A log excerpt cut to the last four matching lines dropped the hook line of a second post one second older locked/l1.txt:5. When two posts are expected, take a wider excerpt.

## Open questions
- Disk fault. The host disk images read whole faults/snapshot_readback.txt:5 faults/snapshot_readback.txt:6, Windows logged no storage or hardware events faults/host_events_summary.txt:7, and BlueStacks was unchanged faults/bluestacks_version.txt:3. Memory pressure was present in every episode faults/host_events_summary.txt:10. The same error shape is in this log from Nov 15 and 16 faults/guest_disk_errors_boot1.txt:62 faults/guest_disk_errors_boot1.txt:63.
- Renderer abort. Two of two on boot 2 faults/n11.out:20, gone after a full instance restart faults/n17.out:23; the memory readings of that boot are the tightest of the night faults/host_events_summary.txt:10.
- Denial state: pending one short emulator window, by the owner's leave.

## Files
- `gate/`, `context/`, `locked/`, `backgrounded/`, `denial-not-done/`, `faults/`: captures (`.txt` command file, `.out` raw capture, `.png` screenshot) and excerpts.
- `*_screen.txt`: parsed listings of the screen dumps, made by `scripts/uidump.py`, which redacts password-class nodes.
- `*.ocr.txt`: unedited machine OCR (tesseract) of the screenshot of the same name.
- `exit_statuses.txt`: script exit status per round.
- `scripts/pinround.py`: runs a command file holding the `[PIN]` placeholder; the PIN is substituted at run time from the committed `s2b-pin` script, and the rendered file and transcript are deleted.
- `scripts/rn_pack.py`: built this package (copy map, excerpt rules, PIN and token scans, citation check).
- `scripts/round.py`, `scripts/uidump.py`: byte-exact copies of the round runner and the screen-dump parser from the earlier package (`android/evidence/m8b2a/scripts/`), the two tools this package's captures went through.
- The package scanner this package was checked with (`scan-pkg.py`, in the same earlier package) stays outside it: it carries the secret-shaped patterns it searches for.
- `SHA256SUMS`: every file in this package.
