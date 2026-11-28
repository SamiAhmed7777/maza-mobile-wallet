# M8b-II-A device run — 2026-11-27 ~03:00–03:50 PST (interactive lane, Telegram thread 54)

> **STATUS (capture time, 2026-11-27): STAGED, UNGRADED, UNCOMMITTED.** Two device
> checks were incomplete at capture (see "Not proven" below).
> **STATUS NOW (2026-11-28, after the window's 05:31 CLOSE line): committed and
> judge-graded by the backlog loop as the M8b-ii-a bring-up half.** The "Not proven"
> checks and the M8b-ii-b evidence half stay open (emulator and miner launches stay
> vetoed until Sami re-opens a window). `SHA256SUMS` was regenerated over the final
> bytes after this header edit and the Files-section defect note; both edits are
> disclosed in the commit message.

Lane file: `/root/maza-mobile-lanes/device/M8B-II-A-DRIVE.md` · Backlog: `/root/maza-mobile-backlog.md`

## Setup

- Device: BlueStacks_nxt instance `Pie64` on SAMI-PC, adb device `emulator-5554`
  (`C:\Program Files\BlueStacks_nxt\HD-Adb.exe`), package `com.mazawallet/.MainActivity`.
- Build under test: APK md5 `1a287b66e3ee91a61a1fd8f66c7b51c4` (repo master 9014cf1 era: has
  the M26/M27 price line, M29 USD-approx line, S-6-ii network card).
- Installed IN PLACE (`pm install -r`): `firstInstallTime=2026-11-15 18:39:10` unchanged,
  `lastUpdateTime=2026-11-27 03:00:21`, device md5 == new-APK md5 (`transcripts/install.out`).
  No uninstall, no `pm clear`; wallet data and PIN kept.
- Bench node (read-only probe, `scripts/ibd_probe.py` → `transcripts/ibd_probe.out`,
  2026-11-27 10:53:17Z): `chain=main blocks=4496969 headers=4496969
  verificationprogress=0.99999997 initialblockdownload=False` → synced.
- Token: read in-process from the bench env on samihost, piped over ssh STDIN to
  `scripts/token.ps1`, typed into the password-masked field. Not in argv, not in any file
  here. Every password-class node in the 21 UI dumps parsed for this package carried only a
  hint string ("bench token" ×4, "PIN or passphrase" ×1) — i.e. the fields were empty at
  capture time.
- PIN: the bench PIN already disclosed in `s2b-pin/` and `s2b2-graceful/` evidence.

## Timeline (PST, device/host clocks)

| time | event | evidence |
|---|---|---|
| ~02:58 | Emulator launched (Sami: "Go ahead and open it", msg 254) | — |
| 02:58:21 | First boot: another guest app aborted with the same message (`Impossible totalDuration 0`, pid 3232) | `r_e.out` |
| 03:00:21 | Build installed in place | `install.out` |
| ~03:03 | Token typed, CONNECT (connect-card dump before the token in `r_a2.out`) | — |
| 03:09:58, 03:14:00 | Wallet aborted on open, twice: `Fatal signal 6 (SIGABRT) … RenderThread`, `>>> com.mazawallet <<<`, `Abort message: 'Impossible totalDuration 0'` | `r_e.out` |
| 03:19:56 | Instance restarted (HD-Player + BstkSVC stopped, relaunched) | `cmds/r_i.txt` |
| 03:22:50 | BlueStacks launcher OOM at boot (`com.uncube.launcher3 … OutOfMemoryError`) — guest was memory-tight | `r_u.out` |
| ~03:23 | Instance Ready; adb up | — |
| 03:24:04 | Wallet started, pid 5153; `Impossible totalDuration` count in crash buffer = 0 | `r_k.out` |
| ~03:25 | Connect → lock cover → PIN unlock | `r_l.out`, `r_m.out` |
| 03:28 | RECEIVE tab: typed `10` → `≈ $0.01854 · FreiXLite · 3m old`; payment QR line | `r_n.out`, `r_o.out`, `r_p.out` |
| 03:29:08 | SCAN QR → camera opened by the app (`CONNECT device 0 client … PID 5153`) | `r_q.out`, `r_t.out` |
| ~03:30:20 | CANCEL tapped → app frozen | see "Finding 1" |
| ~03:44 | `am force-stop` → camera released → app restarted | `r_z.out` |
| ~03:46 | Token re-staged, reconnect, PIN unlock, WALLET tab | `r_aa.out`, `r_ab.out` |
| 03:47–03:48 | WALLET tab scroll captures; Settings screen | `r_ac.out`, `r_ad.out` |
| 03:49:45 | BlueStacks topbar close clicked (not this lane) → `plrStopPlayer: reason Close_by_user` 03:49:50 | Player.log, quoted in backlog run log |
| ~03:53 | Asked Sami whether to reopen; no answer in 1 min → left closed | — |

## Checks — what the screenshots show

| # | check | result | file |
|---|---|---|---|
| 1 | Price line on device | SEEN: `1 MAZA ≈ $0.00185424 · FreiXLite MAZA_LTC · 2m old` on BALANCE (bench 46.9998774 MAZA); `… ≈ $0.00185674 · … · 2m old` on WALLET (self-custody 1.4999 MAZA) | `png/02_balance_priceline.png`, `png/10_wallet_tab.png` |
| 2 | Network switch | CARD RENDERS ONLY: Settings → NETWORK, `Mainnet` filled/selected, `Testnet` outlined. Testnet was NOT tapped (Finding 2) | `png/13_settings.png`, `r_ad.out` |
| 3 | Send fee | LABELS RENDER ONLY: bench SEND `fee 0.0001 MAZA`; self-custody SEND `fee 10 sat/byte per-tx (MazaCore rate; exact fee at send)`. No transaction was sent | `png/06_send_bench.png`, `png/11_wallet_scrolled1.png`, `png/12_wallet_scrolled2.png` |
| 4 | Receive notification | NOT EXERCISED (window closed before the funding send) | — |
| 5 | QR scan | OVERLAY RENDERS: `Point the camera at a MAZA QR code` + CANCEL over the send form. No frame decoded (Finding 1) | `png/07_scan_surface_REDACTED.png` |

Bonus on-device looks (first time on a device): M29 USD-approx line
(`png/04_receive_amount_usd.png`), M9 payment-URI line
`maza:MWRVvg…?amount=10.00000000` (`png/05_receive_payment_qr.png`).

## Not proven

- QR decode end-to-end (displayed QR → decoded address in the SEND field) and the non-MAZA rejection render.
- A real self-custody send with the exact-fee label + txverify (M10-ii).
- The receive notification, locked and backgrounded, and its denial path (M14-ii).
- An actual Mainnet → Testnet switch (M8b-ii context, S-6-ii).
- Gap-limit display advance (M11-ii).

## Finding 1 — scan CANCEL freezes the app when the camera delivers no frames

- Emulator camera service, pid 1848, every 3 s from 03:29 onward:
  `E Camera3-Stream: getBuffer: wait for output buffer return timed out after 3000ms (max_buffers 2)`
  and `E Camera3-Device: RequestThread: Can't get output buffer, skipping request: Connection timed out (-110)`
  (`r_r.out`).
- First CANCEL tap ~03:30:20. The app's own poll log stops at `03:30:19 #92 GET /api/watch/history -> 200`
  and has no later line (`r_y.out`). `dumpsys media.camera` still showed
  `Device 0 is open` with client `com.mazawallet, PID 5153` at 03:33 and again at 03:40 (`r_t.out`, `r_x.out`).
- `uiautomator dump` failed from then on with `ERROR: null root node returned by UiTestAutomationBridge`
  (`r_r.out`, `r_s.out`); `png/09_scan_state_REDACTED.png` at 03:36 still shows the overlay.
- A second CANCEL tap ~03:40 changed nothing: `dumpsys activity lastanr` =
  `<no ANR has occurred since boot>`; crash buffer had no `com.mazawallet` entry (`r_x.out`).
- Recovery that worked: `am force-stop com.mazawallet` → `Device 0 is closed, no client instance`
  → `am start` → Connect card (token field empty, hint `bench token`) → token re-staged (`r_z.out`, `r_aa.out`).
- Code path (not proven on device by a stack trace): `MainActivity.closeScan()` runs
  `QrScanner.stop()` on the main thread, which calls `CameraCaptureSession.close()` then
  `CameraDevice.close()` before the overlay is removed. A main-thread block there fits the
  frozen screen + stopped poll. No thread dump was captured.
- Camera images: the emulator passes the host webcam through. The three scanner captures were
  black-boxed on the PC before leaving it (`scripts/redact.ps1`, rect 430,180 740×575, the
  SurfaceView bounds 470,220–1130,715 plus margin). Raw originals deleted on the PC
  (`r_r.out`, `r_v.out`, `r_w.out` print raw vs new sha256 and `raw-exists=False`).

## Finding 2 — switching to Testnet with no testnet endpoint has no way back

Read from source, not exercised on the device:

- The network preference is written only by the Settings NETWORK card
  (`SettingsActivity.java` ~170–200).
- Settings is reachable only from the WALLET tab's SETTINGS button
  (`MainActivity.java` ~1789), which needs a live session.
- After a switch the session is dropped on resume and the Connect card shows the new network
  with an empty endpoint (`MainActivity.java` ~416–420: testnet hint `""`).

So a user who taps Testnet without a reachable testnet server lands on a Connect card for
testnet with no UI path back to Mainnet. On the bench device that would strand a seed-bearing
install (no root to edit prefs; `pm clear` would destroy the wallet). Not tapped tonight for
that reason.

## Earlier-boot renderer abort (resolved by the instance restart)

On the first boot of the session the wallet's RenderThread aborted with
`Impossible totalDuration 0` on open (`r_e.out`); the same abort hit BlueStacks' own
built-in app at boot. After the 03:19:56 restart the wallet ran ~25 minutes across
BALANCE / RECEIVE / SEND / WALLET / Settings with 0 such aborts (`r_k.out`, `r_s.out`).
Cause not established (host was under memory pressure; guest launcher OOM'd at boot).

## Misses

- The backup copy of the previously installed (Nov-17) APK was not saved before the in-place
  update (`install.out`: `OLD-APK MISSING`). It is no longer on the device.
- Host-side round transcripts with machine details (`r_f`, `r_h`, `r_i`, `r_af`, `r_ag`) are
  deliberately not in this package; their relevant lines are quoted above.

## Files

- `png/` 14 captures (`00`–`06`, `07_scan_surface_REDACTED`, `08_after_scan_cancel_REDACTED`,
  `09_scan_state_REDACTED`, `10`–`13`). The three `_REDACTED` files are the only scanner
  images kept.
- `transcripts/` adb round outputs (`r_*.out`), `install.out`, `ibd_probe.out`.
- `cmds/` the command lists each round ran.
- `scripts/` the lane tooling: `adbrun.ps1` (adb runner, base64 argv), `round.py`
  (run a cmd list), `uidump.py` (dump → labelled nodes, password nodes redacted),
  `redact.ps1`, `install.ps1`, `ship.py`, `token.ps1`, `stage_token.sh`, `ibd_probe.py`.
- `SHA256SUMS` over every file here.
- Known defect, disclosed after the fact: `adbrun.ps1`'s push/pull handlers cut the
  first character of their first argument (`Substring(6, ...)` over the 5-char verbs)
  — the drive letter on push, the leading slash on pull (pulls still resolved). The
  lane worked around it with the `raw` verb. Documented with the exact lines in
  `m32/RUNLOG.md`; fix candidate, NOT fixed here (historical record as-used).
