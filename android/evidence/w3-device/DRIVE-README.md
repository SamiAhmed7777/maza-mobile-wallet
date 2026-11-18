# DRIVE-README - W3 device-evidence capture pipeline

Device: BlueStacks Pie64 on SAMI-PC, adb emulator-5554 (HD-Adb), 1600x900.
App: wave-2 build (base 436eb40), built in THIS worktree, installed via
adb push + `pm install -r` (update-in-place; firstInstallTime unchanged).

Pipeline (per capture):
1. Delete stale remote files: `adb shell rm -f /sdcard/ui.xml /sdcard/shot.png`.
2. Drive the UI (staged .ps1 drivers in this directory: connect.ps1,
   wrongpin.ps1, seedreveal.ps1, u10-setup.cmd, w3-install.cmd - these are
   the exact files that were run).
3. `uiautomator dump /sdcard/ui.xml` + `adb pull` -> numbered .xml.
4. `screencap -p /sdcard/shot.png` + `adb pull` -> numbered .png.
5. Toasts: three immediate screencaps (t1/t2/t3) - transient ~2s.

Secrets: the server token was staged on SAMI-PC via ssh stdin into
C:\Users\hello\.maza-token (TOKENFILE-DELETED=True after the run) and typed
by the driver; it never appears in argv, transcripts, or screenshots (the
Connect-card capture shows the empty HINT field). The seed-dialog dump was
redacted to [word-NN-REDACTED] and every unredacted copy (device, SAMI-PC,
host) was deleted; walletbench w3bench/seed.png was also deleted in cleanup.

SHA256SUMS covers every file in this directory (generated post-capture).

## W3-a addendum (40-* .. 52-*, 2026-11-17 08:04-08:24 PST)

Same build/install/capture pipeline, same bench wallet (PIN 2468, index 4
`MRQswDmXBiGqqmtPzHh2ViMkEL7uNDaaPy`). New driver: `repaint-connect.ps1` - the
Connect step for this run (typed the token from the staged file, tapped CONNECT,
deleted the file, printed `TOKENFILE-DELETED=True`). Coordinates used:
URL field (800,342), token field (800,455), CONNECT (800,576), tabs y=858
(BALANCE 160 / RECEIVE 480 / SEND 800 / HISTORY 1120 / WALLET 1440), Settings
APPEARANCE row y=872 (System 295 / Light 799 / Dark 1304), SETTINGS button
(800,718) after two upward swipes on the WALLET tab. `52-lifecycle-logcat-excerpt.txt`
is a filtered `logcat -d -v time | grep com.mazawallet` capture, not a screen.
Every file here is covered by SHA256SUMS.

## W4-DEV addendum (62-* .. 81-*, 2026-11-17 17:17-18:5x PST / 2026-11-18 01:17-02:5xZ)

Same bench, same installed build (NO reinstall in this lane; zero product-code
changes, evidence directory only). New captures use the same per-capture
pipeline as above: `rm -f /sdcard/ui.xml /sdcard/shot.png` -> `uiautomator dump`
+ `screencap -p` -> `adb pull` to `C:\Users\hello\w3bench\` -> `scp` here
(`/root/.hermes/cache/scratch/cap.sh 62..79` is the helper that ran it).

What is new is the OFFLINE mechanism. Airplane mode cannot cut this bench's
transport (`58-airplane-mode-device-state.txt`), so the lane arms a
DEVICE-SIDE DNS harness instead:

  settings put global private_dns_mode hostname
  settings put global private_dns_specifier blackhole.invalid

Every NEW lookup then fails (`ping example.com` -> `unknown host`) while the
raw link stays up (`ping 8.8.8.8` answers), and the front door's cached A record
(`mazatest.sami-host.me. 3600 IN A 194.163.161.162`) keeps the app online for up
to its 3600 s TTL. The offline captures below are timestamped AFTER that cache
entry expired; the harness was released with `settings put global
private_dns_mode off` at the end and connectivity re-verified.

Transcripts in this directory: `67-dns-harness-release-reconnect.txt`,
`74-dns-harness-transcript.txt`, `80-dns-restored-final-proof.txt`. Each is
verbatim command + raw output, UTC, blank-line separated.

Driver note for the next lane: on this bench never send `input keyevent 4` to
dismiss the keyboard - the IME has no visible window (`mInputShown=true
mWindowVisible=false`), so BACK reaches the activity, finishes MainActivity, and
the memory-only token is lost (two reconnect cycles were burned on that; the
SEND button is never occluded, just tap it). Token handling is unchanged from A4
(ssh stdin -> `C:\Users\hello\.maza-token`, typed by `w4-connect.ps1`, deleted
by that driver, `TOKENFILE-DELETED=True`, never echoed or screenshotted).
