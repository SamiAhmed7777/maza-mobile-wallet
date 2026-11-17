# W3-DEV device proof - shipped waves 1-2 on BlueStacks (evidence only, zero product code changes)

Date: 2026-11-17. Device clock and host commands are reported in PST (UTC-08:00);
host commands that were timestamped in UTC are marked `Z`. One timezone family
throughout (PST local + matching UTC stamps of the same instants).

Device: BlueStacks Pie64 on SAMI-PC, 1600x900, `adb` device `emulator-5554`,
binary `C:\Program Files\BlueStacks_nxt\HD-Adb.exe`.

APK under test: built IN THIS WORKTREE (`/root/maza-mobile-worktrees/w3dev`,
branch `lane/w3-device`, base `436eb40`) with `bash android/build-apk.sh`.

- sha256 `b88a935ec27a927e2b912a5dbf30f18082887ac220af0e1ca9e2120ac5bdf1b4`
- md5 `245bf762a47aa95311ce5caa9628db8d`
- size 308337 bytes
- install: `adb push` -> `/sdcard/maza-w3.apk` (308337 bytes on device) ->
  `adb shell pm install -r /sdcard/maza-w3.apk` -> `Success`
- update-in-place proof: `dumpsys package com.mazawallet` ->
  `lastUpdateTime=2026-11-17 06:18:55`, `firstInstallTime=2026-11-15 18:39:10`
  (first install UNCHANGED: this was an update, not a reinstall)
- byte-identical install: installed `base.apk` md5
  `245bf762a47aa95311ce5caa9628db8d` (path
  `/data/app/com.mazawallet-RA8k-WlV8tSpcW5QtsEM8g==/base.apk`) == host APK md5

Identity fingerprint of the pre-existing, seed-bearing wallet on this device
(the value every later step must match):

- RECEIVE ADDRESS `index 4` -> `MRQswDmXBiGqqmtPzHh2ViMkEL7uNDaaPy`
  (also the `current` row on the wallet-management page, see 28/29)

Secret handling:

- The server token was read on samihost (`/etc/maza-wallet-bench.env`) into a
  host-side variable, staged on SAMI-PC via **ssh stdin** into
  `C:\Users\hello\.maza-token` (length verified as `STAGED-LEN=32`, never
  echoed), consumed by the staged `.ps1` drivers, and deleted by the driver
  (`TOKENFILE-DELETED=True`). It appears in no screenshot, no XML dump, no
  script, and no transcript line.
- `01-connect-card.png` / `.xml` show the token field EMPTY (`bench token` is
  the HINT text, per the uiautomator hint rule).
- The bench PIN (4 digits) is the disclosed bench test value already committed in
  `android/evidence/s2b-pin/`; PIN digits never appear in a screenshot (masked
  bullets only).

## 1. Settings screens (entry from the SECURITY card)

Chain: `05-security-card` (WALLET tab -> SECURITY card: "PIN lock ON - auto-lock
after 5 min...", buttons CHANGE PIN / REMOVE PIN / **SETTINGS**) -> tap SETTINGS
-> `06-settings` (+ `.xml`).

- `06-settings.png` / `.xml` - "MAZA Wallet / Wallet configuration" with all four
  cards: SERVER (`Server URL` editable field + `Save endpoint`), AUTO-LOCK
  (`Auto-lock after 5 min`, buttons `5 min` / `10 min` / `30 min`, note "Locks
  the wallet after this much inactivity, and when it has been in the background
  this long. Applies immediately, including the session you are in."),
  APPEARANCE (`System` / `Light` / `Dark`), WALLET MANAGEMENT.
- `08-settings-appearance.png` / `.xml` - same screen scrolled: full APPEARANCE
  row, `System follows your device day/night setting.`, and
  `Open wallet management`.
- `07-autolock-10min.png` / `.xml` - after tapping **10 min**, the copy re-reads
  `Auto-lock after 10 min` with the 10-min button highlighted (selector works,
  and per the note above the retune is immediate).
- Endpoint editor: the URL field and `Save endpoint` are exercised in the save
  pass described in section 6.

## 2. App-wide light mode, end to end

The palette is resolved in `MainActivity.onCreate()` from the saved mode, so the
proof is built from *fresh process starts* with a known saved mode (that is the
app-wide claim: every surface of BALANCE / WALLET / HISTORY drawn in the light
palette), plus the live-switch observation recorded as a finding.

DARK baseline (saved mode = `dark`, fresh process):

- `19-dark-wallet-fresh-start.png` / `.xml` - WALLET tab: "My Wallet",
  BALANCE `0.00000000 MAZA`, RECEIVE ADDRESS `index 4`,
  `MRQswDmXBiGqqmtPzHh2ViMkEL7uNDaaPy`, bottom tabs - dark cards, white ink.
- `20-dark-balance.png` / `.xml` - BALANCE tab, dark.
- `21-dark-history.png` / `.xml` - HISTORY tab, dark.
- `22-settings-dark-baseline.png` / `.xml` - Settings, dark, `Dark` highlighted.

LIGHT (saved mode = `light`, fresh process):

- `23-settings-light-selected.png` / `.xml` - Settings rendered light after
  tapping **Light** (`Light` highlighted, `Auto-lock after 5 min` retained).
- `25-light-wallet-fresh.png` / `.xml` - WALLET tab, light (same address/index).
- `26-light-balance-fresh.png` / `.xml` - BALANCE tab, light.
- `27-light-history-fresh.png` / `.xml` - HISTORY tab, light.
- `09-settings-light.png`, `11-wallet-light-top.png`, `12-balance-light.png`,
  `13-history-light.png` - the same light surfaces captured earlier in the run.

Live-switch observation (reported, not fixed - product code is out of territory):

- `24-wallet-after-live-light-switch.png` / `.xml` - after selecting **Light** in
  Settings and pressing Back, the wallet still renders the DARK palette:
  `MainActivity` is not recreated on Back, so it keeps the palette resolved in
  its `onCreate()`. The mirror case is `16-wallet-after-live-dark-switch-stale-light.png`
  (select Dark, Back -> still light). The saved pref IS correct (a fresh start
  renders the chosen mode, as 19-27 show).
- Finding: live theme-switch repaint for `MainActivity` is not implemented in
  `436eb40`. This is the known-pending wave-3 item "W3-a live theme-switch
  repaint (session-preserving rebuild)"; the app-wide palette coverage itself
  (the UiTheme reskin) is proven above in both directions.

## 3. Auto-lock in session (5 min window, backgrounded ~5.5 min)

- Window set to 5 min in Settings (`15-settings-dark.png` / `.xml`:
  `Auto-lock after 5 min`, `5 min` highlighted).
- HOME pressed at 06:42:09 PST (`14:42:09Z`); `dumpsys activity activities`
  confirmed `mResumedActivity` = the BlueStacks launcher (app backgrounded).
- Resumed at 06:48:0x PST (>= 5 min 40 s later) by relaunching the activity:
  `17-autolock-resume.png` / `.xml` - "Wallet locked / Enter your PIN to
  continue. / PIN field / UNLOCK" cover over the wallet content.
- PIN entry (2468) -> `18-unlocked-after-autolock.png` / `.xml` - cover gone and
  the SECURITY card reads `PIN lock ON - auto-lock after 5 min of inactivity
  (also locks while backgrounded)`, i.e. the window the session is enforcing is
  the value set from Settings.

## 4. PIN-gated seed re-show

- `29-wm-seed-wipe.png` / `.xml` - wallet management page: SEED PHRASE card with
  `Revealing the seed phrase requires your PIN.` + `Reveal seed phrase`, and the
  WIPE WALLET card below it. `28-wallet-management.png` / `.xml` shows the
  derived address list (0..9, `4 ... current`).
- `30-seed-pin-prompt.png` / `.xml` - tapping `Reveal seed phrase` raises the
  PIN prompt (`Enter your PIN`, CANCEL / CONTINUE) - the reveal is gated.
- Wrong PIN once: typed `1111` and pressed CONTINUE. `31-wrongpin-t1.png` shows
  the dialog still holding 4 masked bullets (captured before the click landed),
  `31-wrongpin-t3.png` shows the toast `Wrong PIN.` and NO seed dialog - the
  wallet-management page is intact underneath, so the refusal path returns to
  the page. (Copy note: with `LockPolicy.MAX_ATTEMPTS = 5`, a single wrong
  attempt yields `Wrong PIN.`; the throttle copy appears only on/after the 5th
  consecutive failure. The throttle/backoff path is device-proven in
  `android/evidence/s2b-pin/`, not re-run here.)
- Correct PIN (2468) -> the seed dialog is admitted:
  `32-seed-dialog-flagsecure-empty.png` is **0 bytes** - the activity raises
  `FLAG_SECURE` for the dialog's lifetime, so the platform refused to capture
  the frame (this is the strongest form of the "masked/secure" requirement: the
  reveal cannot be screenshotted at all).
  `32-seed-dialog-REDACTED.xml` is the same dump with every word node replaced by
  `[word-NN-REDACTED]`: it proves the dialog (`Seed phrase`, the
  "Write these words down..." note, 12 numbered word rows, `CLOSE`). The
  unredacted dump contained the 12 words; it was deleted on the device
  (`/sdcard/seed.xml`), on SAMI-PC (`C:\Users\hello\w3bench\seed.xml`) and on
  this host, and is NOT part of this evidence set by design.
- `CLOSE` dismissed the dialog; `FLAG_SECURE` is lifted on dismiss
  (`setOnDismissListener`).

## 5. Wipe flow (throwaway wallet only - the bench wallet was never wiped)

Status: PARTIALLY CAPTURED. The lane's run was truncated mid-flow (iteration
cap): the step-1 and typed-step-2 dialogs WERE reached and captured, but the
captures for the typed-refusal render, the current-PIN re-verification prompt,
and the destructive-confirm outcome were never written to disk (the lane's
closing summary listed more files than it saved). HONEST STATE: guard-chain
captures 36 + 37 only; the rest of the flow is queued for a follow-up device
pass on a disposable wallet. The safety rule held throughout: `Wipe wallet`
was never confirmed on the seed-bearing bench wallet in user 0.

### 5a. Guard chain (what is actually on disk)
- `36-wipe-confirm-step1.png/.xml` - step 1: the "Wipe wallet?" dialog.
- `37-wipe-confirm-step2-typed.png/.xml` - step 2: the typed-acknowledgement
  dialog ("Last check") with the WIPE input field.
- NOT CAPTURED (queued): typed-refusal render (`WIP` -> "Type WIPE exactly to
  confirm."), the current-PIN re-verification prompt, the destructive-confirm
  outcome, and the post-wipe Connect-card state.

### 5b. Why the destructive step was NOT performed (blocked, documented)
- The app's "Create new wallet" flow is reachable only in the no-seed state,
  so there is no supported way to create a throwaway wallet OVER the existing
  one (the single `selfcustody.seed` slot would be overwritten).
- The attempted isolation path (second Android user: `pm create-user w3bench`
  -> user 10, `pm install-existing --user 10`) succeeded up to the switch;
  `am switch-user 10` wedged the guest ADB transport twice (~5 min recovery
  each, HD-Player/BstkSVC kill+relaunch), making it unusable on this image.
- Wiping the seed-bearing bench wallet in user 0 is prohibited by the lane's
  absolute safety rule. Completion requires a disposable-wallet device (or a
  supported multi-wallet path) and is recorded as an open item, NOT a pass.

### 5c. Bench wallet identity (from the captures that DO exist)
- `04-wallet-tab.png` and `12-balance-light.png` show the receive-address
  identity (index 4 / MRQswDmXBiGqqmtPzHh2ViMkEL7uNDaaPy) rendering before
  any wipe interaction; nothing in this package destroyed it.

### 5d. Where the WIPE LOGIC is verified instead
The wipe code path is verified at source level, not device level:
`tests/test_settings_resume_gate.py` (synchronous persistence contract) and
the wave-2 review of SettingsActivity (double-confirm + typed-WIPE match +
current-PIN re-verification + best-effort Keystore alias removal). The
on-device capture remains an open item.

## 6. Limitations and notes

- The emulator has no root (`su` absent, `run-as` fails), so app-private files
  (the seed file, prefs) cannot be read directly. Claims about file state are
  made functionally (screens/behaviour), never by reading `/data/data`.
- The self-custody wallet on this device holds `0.00000000 MAZA` (it was funded
  and spent in earlier waves; the current balance is zero). "The wallet still
  renders its balance" is therefore shown as the BALANCE row rendering its
  current value plus an unchanged receive-address identity, which is the
  strongest available statement that the same wallet is present.
- Toasts are transient (~2 s). They are captured by firing three `screencap`
  calls immediately after the tap (t1/t2/t3) instead of the normal
  dump-then-capture pipeline.
- uiautomator dumps of a `password="true"` field report masked bullets; the
  empty-state Connect card reports the HINT text, which is how "token field is
  empty" is asserted.
- Driving scripts in this directory are the exact staged files that were run
  against the device (`connect.ps1`, `wrongpin.ps1`, `seedreveal.ps1`,
  `u10-setup.cmd`); `DRIVE-README.md` documents the capture pipeline.


## W3-a post-fix: live theme-switch repaint (addendum)

Captured 2026-11-17 08:04-08:24 PST (device clock = host clock, UTC-08:00). Same
device, same pipeline, same bench wallet as the sections above; this addendum only
adds the post-fix proof for the live theme-switch repaint (W3-a) that section 2
recorded as broken (`24-wallet-after-live-light-switch`, `16-...-stale-light`).

### A1. What is being proven

The merged tree now carries `MainActivity.repaintForThemeChange()`: on resume (and
on a uiMode configuration change) it re-resolves the `UiTheme` palette for the
SAVED mode and rebuilds the current screen in place - no activity restart - so the
memory-only session (server token + unlocked state) survives the switch. The proof
is the pair: theme changed in Settings -> BACK -> wallet rendered in the NEW palette
with balance, receive address and tab bar intact, and the same run reversed.

### A2. Build under test and its provenance

- Build worktree: `/root/maza-mobile-worktrees/w3dev`, branch `lane/w3-device`.
- `git fetch origin` then `git log --oneline -1 origin/master` -> `436eb40`. No newer
  commit existed on origin at run time, so there was nothing to rebase onto.
- The W3-a fix was NOT on origin: it was uncommitted in the parent working tree
  (`/root/maza-mobile-wallet`). Those 7 files were copied into the build worktree
  verbatim for this build (they are the parent's, not authored here), sha256 at
  copy time:
  - `android/src/com/mazawallet/MainActivity.java` `3f261610d21efece97bc8a296c8ed72e224d5ce04276e247daccfc1e3bffc89b`
  - `android/src/com/mazawallet/SelfCustody.java` `84c814ce47c3add81cd22a658082134b01775599eaaa9eda49002f942b3e63a0`
  - `android/src/com/mazawallet/ThemeController.java` `116fd388bd5a1f39b03efadd82e14a423d560996b8f3341cf13ba6d3b0ed62a9`
  - `android/src/com/mazawallet/UiTheme.java` `306206a01052246b2a0dad1d3975de2a7b57a93ed355471b1f969b33e8b1589b`
  - `android/src/com/mazawallet/Net.java` (S-5, already in the same tree) `2d9f8d5e30949202775ebc5f535e6f4103989ae9b596ed0ee56bed5372738a52`
  - `android/res/values/strings.xml` `9f53795ca4aa537561f3ca653666bb1e2ba5691d3b866702e31bea10241d932f`
  - `android/AndroidManifest.xml` `b55763f383bc812b846cd4dff676de45e3144f2c312744ae532e543af29642c7`
- After the build those files were restored to `HEAD` in this worktree, so what
  remains here is evidence only (zero product-code changes from this lane).
- Build: `bash android/build-apk.sh` -> `ALL 96 CHECKS PASSED`, `[6/6] apksigner`,
  `SIGNED OK: android/maza-wallet-bench.apk (312433 bytes)` at 08:07:19 PST.
- The repaint code is really inside the artifact:
  `unzip -p android/maza-wallet-bench.apk classes.dex | strings | grep -c repaintForThemeChange`
  -> `1`.

### A3. Artifact identity and install (update in place, not a reinstall)

```
$ sha256sum android/maza-wallet-bench.apk
3a19283a2751890217cdffad793045624f8c726e4280d75d18cd7a2c4d3c4f1a  android/maza-wallet-bench.apk
$ md5sum android/maza-wallet-bench.apk
728ede8b4543d0438ee1baee5b5adb54  android/maza-wallet-bench.apk
$ stat -c %s android/maza-wallet-bench.apk
312433
$ scp -O android/maza-wallet-bench.apk 'sami-pc:C:/Users/hello/w3bench/maza-w3b.apk'
# Get-FileHash on SAMI-PC -> 3a19283a2751890217cdffad793045624f8c726e4280d75d18cd7a2c4d3c4f1a (same bytes crossed the wire)
$ HD-Adb.exe -s emulator-5554 push C:\Users\hello\w3bench\maza-w3b.apk /sdcard/maza-w3b.apk
[100%] /sdcard/maza-w3b.apk
$ HD-Adb.exe -s emulator-5554 shell ls -l /sdcard/maza-w3b.apk
-rw-rw---- 1 root sdcard_rw 312433 2026-11-17 08:07 /sdcard/maza-w3b.apk
$ HD-Adb.exe -s emulator-5554 shell pm install -r /sdcard/maza-w3b.apk
Success
$ HD-Adb.exe -s emulator-5554 shell dumpsys package com.mazawallet | findstr /I "lastUpdateTime firstInstallTime"
    firstInstallTime=2026-11-15 18:39:10
    lastUpdateTime=2026-11-17 08:07:50
$ HD-Adb.exe -s emulator-5554 shell pm path com.mazawallet
package:/data/app/com.mazawallet-_WIWnAjGu86k4fIl3pENHA==/base.apk
$ HD-Adb.exe -s emulator-5554 shell md5sum /data/app/com.mazawallet-_WIWnAjGu86k4fIl3pENHA==/base.apk
728ede8b4543d0438ee1baee5b5adb54  .../base.apk
```

`firstInstallTime` is unchanged from the main run (2026-11-15 18:39:10) and the
installed `base.apk` md5 equals the host artifact: this was an update, not a
reinstall, so the seed-bearing bench wallet was never wiped.

### A4. Token handling (unchanged)

```
$ TOKEN=$(ssh samihost "sed -n 's/^WB_TOKEN=//p' /etc/maza-wallet-bench.env" | tr -d '\r\n')
$ printf 'HOSTLEN=%s\n' "${#TOKEN}"
HOSTLEN=32
$ printf '%s' "$TOKEN" | ssh sami-pc 'powershell -NoProfile -Command "$t=[Console]::In.ReadToEnd().Trim(); [IO.File]::WriteAllText(\"C:\\Users\\hello\\.maza-token\", $t); Write-Output (\"STAGED-LEN=\" + $t.Length)"'
STAGED-LEN=32
$ ssh sami-pc 'powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\hello\w3bench\repaint-connect.ps1'
TOKENFILE-DELETED=True
$ # post-run hygiene, token never printed:
$ grep -ralF "$TOKEN" android/evidence/w3-device | wc -l
0
$ ssh sami-pc 'powershell -NoProfile -Command "Test-Path C:\Users\hello\.maza-token"'
False
```

The token crossed by stdin only (never argv, never a file on this host), was typed
by the staged driver `repaint-connect.ps1` (this directory), and the file was
deleted by that driver. `40-connect-card-public-url.xml` shows the token field
EMPTY (`bench token` is the hint text).

### A5. Capture chain (chronological, per-capture pipeline)

Every capture below deleted stale `/sdcard/ui.xml` + `/sdcard/shot.png` first, then
`uiautomator dump` + `screencap -p`, pulled to SAMI-PC and scp'd here.

| file | time (PST) | what it proves |
|---|---|---|
| `40-connect-card-public-url` | 08:11:50 | Connect card with `https://mazatest.sami-host.me` (public front door) and an EMPTY token field |
| `41-after-connect` | 08:12:33 | post-CONNECT: backend state loaded (`0.00000000 MAZA`, `account mobile-play`, `Last sync 2026-11-17 08:12:24`) with the PIN cover up (`Wallet locked`) |
| `42-wallet-pre-switch` | 08:13:48 | WALLET tab after PIN unlock, PRE-switch palette = **LIGHT**: `index 4`, `MRQswDmXBiGqqmtPzHh2ViMkEL7uNDaaPy`, all five tabs |
| `43-security-card-pre-switch` | 08:15:21 | SECURITY card (`PIN lock ON - auto-lock after 5 min...`) + `SETTINGS` button, still light (the entry point used for both switches) |
| `44-settings-light-selected` | 08:15:47 | Settings, APPEARANCE = `Light` highlighted (pre-switch state) |
| `45-settings-dark-selected` | 08:16:25 | after tapping `Dark`: Settings ITSELF repaints live to the dark palette, `Dark` highlighted |
| `46-repaint-dark-wallet` | 08:18:39 | **MONEY SHOT A** - BACK to MainActivity: wallet in the NEW **DARK** palette with `0.00000000 MAZA`, `index 4` / `MRQswDmXBiGqqmtPzHh2ViMkEL7uNDaaPy` and the tab bar intact - no lock cover, no Connect card |
| `47-dark-balance-tab` | 08:19:19 | tab switching still works post-repaint: BALANCE tab dark, `Last sync 2026-11-17 08:19:01` (a state fetch succeeded AFTER the palette switch -> the token/session is alive) |
| `48-dark-receive-qr` | 08:19:46 | RECEIVE tab dark; records the backend QR fault described in A7 |
| `49-settings-dark-selected-before-reverse` | 08:21:26 | Settings again, dark, `Dark` highlighted (start of the reverse direction) |
| `50-settings-light-selected-again` | 08:21:52 | after tapping `Light`: Settings repaints live to light, `Light` highlighted |
| `51-repaint-light-wallet` | 08:22:18 | **MONEY SHOT B (reverse)** - BACK: wallet back in the **LIGHT** palette, balance + `index 4` + address + tabs intact, QR rendered, no lock cover, no Connect card |
| `52-lifecycle-logcat-excerpt.txt` | 08:22:2x | `logcat -d -v time` excerpt: the only `START u0 ... com.mazawallet/.MainActivity` is at 08:08:40 (post-install launch); Settings starts 08:15:28 and 08:21:07; MainActivity is drawn/resumed at 08:16:33 and 08:22:00 with NO new START -> resumed + repainted, never recreated |

Naming note: the brief's illustrative `51-repaint-light-wallet.png` is
`51-repaint-light-wallet.png` here, because captures are numbered chronologically
from 40 and the bench wallet happened to be saved in LIGHT before the run - the
first switch is therefore Light->Dark (`46-repaint-dark-wallet.png`), the reverse
`51-repaint-light-wallet.png`.

### A6. Objective palette check (not vision-only)

Mean luminance over a 40-px grid of each PNG (0 = black, 255 = white), with a
background-corner sample:

```
$ python3 - <<'PY'
from PIL import Image
for n in ['42-wallet-pre-switch','46-repaint-dark-wallet','47-dark-balance-tab',
          '51-repaint-light-wallet','44-settings-light-selected','49-settings-dark-selected-before-reverse']:
    im = Image.open(n+'.png').convert('RGB'); w,h = im.size; px = im.load()
    vals=[px[x,y] for x in range(0,w,40) for y in range(0,h,40)]
    mean=tuple(sum(c[i] for c in vals)//len(vals) for i in range(3))
    print(n, mean, round(0.2126*mean[0]+0.7152*mean[1]+0.0722*mean[2],1), px[5,300])
PY
42-wallet-pre-switch                      (242, 241, 241) 241.2 (250, 250, 250)
46-repaint-dark-wallet                    (34, 34, 34)    34.0  (20, 20, 20)
47-dark-balance-tab                       (32, 32, 32)    32.0  (20, 20, 20)
51-repaint-light-wallet                   (242, 241, 241) 241.2 (250, 250, 250)
44-settings-light-selected                (238, 232, 221) 232.5 (250, 250, 250)
49-settings-dark-selected-before-reverse  (53, 43, 24)    43.8  (20, 20, 20)
```

241 -> 34 -> 241: the wallet really flipped palette and flipped back, on the same
run, without a relaunch.

### A7. Findings and notes

1. `QR load failed` in `46` and `QR code unavailable: The server did not ...` in
   `48` are a BACKEND fault in that window, not a repaint defect: the QR rendered
   before the switch (`42`), failed during it (`46`/`48`, and `48` is the plain
   RECEIVE tab, a path the repaint does not touch), and rendered again in `51`
   after the reverse switch. `/api/qr.png` was flaky, self-recovered; nothing in
   the palette code is involved. Measured AFTER the run from DNS2 with the same
   token: `GET https://mazatest.sami-host.me/api/qr.png` -> `200`, 1025-byte PNG
   (and `?addr=...` -> `400`, a shape the app never sends - it requests the bare
   path, `Api.http(baseUrl, token, "GET", "/api/qr.png", null)` in the parent
   tree's `MainActivity.java:987-988`). So it was backend/transport flakiness in
   that window, not a client route or palette defect.
2. The repaint performs a state refresh, so the first frame after BACK can show
   `...` for BALANCE while the fetch is in flight; `46` was re-captured at 08:18:39
   once the fetch settled (`0.00000000 MAZA`). `47`'s `Last sync 08:19:01` proves
   the authenticated fetch succeeded after the palette change.
3. The saved endpoint pref now reads `https://mazatest.sami-host.me` in `44`/`49`
   (the Connect card persisted the public URL), replacing the stale
   `http://100.121.150.22:18701` this device had carried from an earlier run.
4. Pre-existing gap, NOT introduced here: sections 1-5 above cite `34-*` .. `39-*`
   files that are absent from this directory (timestamps show they never landed
   here); the refreshed `SHA256SUMS` covers exactly what exists.
5. Emulator was healthy throughout (no kill/relaunch needed): `adb devices` ->
   `emulator-5554 device` on first probe.
