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
