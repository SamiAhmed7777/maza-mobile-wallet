# M22b run transcript (verbatim commands + key outputs, 2026-11-16 09:06-09:25 PST)

All remote commands via `ssh sami-pc` / `ssh samihost`; `ADB` shorthand below =
`"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554`.

## Pre-flight
- reconcile: `git log --oneline -8` → HEAD `26a962b [grade=A urn:ump:wxfl...] M22a: ...`; `git status --porcelain` → empty (clean tree)
- conflict guard: no repo writes in last 10m; `~/.hermes/cache/delegation` newest 02:49 (stale)
- BlueStacks state: `tasklist` → `HD-Player.exe ... Console 1` + `BstkSVC.exe`; `HD-Adb devices` → `emulator-5554 device`; `qwinsta` → console Active; `schtasks /query /tn MazaBenchLaunch` → Status: Ready
- tunnel: `curl http://100.121.150.22:18701/` → `root=200`; `/api/state` → `state=401`

## Build (DNS2)
- `bash android/build-apk.sh` →
  `ALL 19 CHECKS PASSED` (stage [1/6] selftest gate) ... `SIGNED OK: /root/maza-mobile-wallet/android/maza-wallet-bench.apk (271316 bytes)`, rc=0
- `sha256sum` → `e9cb8e5c8f7aed82a6e3a5123556fdf385e0cdae1c9c4deef2bfc3849d8eab6b`
- `aapt2 dump badging` → `package: name='com.mazawallet' versionCode='1' versionName='1.0' ... sdkVersion:'24' targetSdkVersion:'34'`

## Ship + install (SAMI-PC)
- `scp android/maza-wallet-bench.apk sami-pc:C:/Users/hello/m22b.apk`; `certutil -hashfile ... MD5` → `a3cd0326062d2d4e5344c04df39ab75d` == local `md5sum` → parity
- `ADB shell` push+install (m22b evidence run used a combined ssh):
  `push C:\Users\hello\m22b.apk /sdcard/m22b.apk` → `[100%]`; `ls -l /sdcard/m22b.apk` → `-rw-rw---- 1 root sdcard_rw 271316 2026-11-16 09:12`; `pm install -r /sdcard/m22b.apk` → `Success`
- reconnect: sleep 25s; `HD-Adb connect 127.0.0.1:5555` → `connected`; `devices` → `emulator-5554 device` (+duplicate 127.0.0.1:5555 transport; all later calls `-s emulator-5554`)
- `pm list packages com.mazawallet` → `package:com.mazawallet`; `dumpsys ... | findstr lastUpdateTime` → `lastUpdateTime=2026-11-16 09:12:28`; `pm path com.mazawallet` → `/data/app/com.mazawallet-J-0lYxyTQ-rVRyOrgMHV6g==/base.apk`; `md5sum` that path → `a3cd0326062d2d4e5344c04df39ab75d` — byte-parity with host build

## Unlock
- `am force-stop com.mazawallet` + `am start -n com.mazawallet/.MainActivity`; uiautomator dump #1 → Connect card: URL field text `http://100.121.150.22:18701`, token field `password="true"` text=hint `bench token` (11 = EMPTY), CONNECT button; bounds token [54,421][1546,489], CONNECT [54,540][1546,612]
- token fetch: `ssh samihost "grep -oP '^WB_TOKEN=\K.*' /etc/maza-wallet-bench.env" > /tmp/m22b-token` (33 bytes incl newline; staged for this tick only — SHREDDED post-run with `shred -u -n 3`, exit 0, absence verified; never printed. Exposure scope: the token also transits two transient argvs via type-token.cmd — host-side HD-Adb.exe + on-device `input`; neither is captured anywhere. See PROOF.md "Token handling".)
- `type-token.cmd` (stdin path): `set /p TOK=` → `input tap 800 455` → `input text "%TOK%"`; dump #2 → token field `password="true"` length 32 masked chars (single entry; URL field untouched)
- `tap-connect.cmd`: `input tap 800 576`; dump #3 (dump-unlock-landing-balance.xml) → BALANCE tab, `46.9998774 MAZA`, `Last sync 2026-11-16 09:16:48`

## Evidence captures (m22b-round1.cmd, -round2.cmd, -round3.cmd)
- round1: screencap → balance-t0.png (status bar 9:18, Last sync 09:17:54); `input tap 800 858` (SEND) + screencap → send-tab-bench-account.png; dump → `SEND · BENCH ACCOUNT` + note; `input tap 160 858` (BALANCE) + screencap → balance-after-nav.png (Last sync 09:18:10). NOTE: ui5 dump write failed once (`uiautomator dump` sporadic no-write) — screenshot succeeded; state re-dumped later.
- round2: dump-refresh-s1/s2/s3 (BALANCE → NAV1 → BALANCE → NAV2 → BALANCE):
  S1 `Last sync 2026-11-16 09:20:36` → S2 `09:20:41` (+5s) → S3 `09:20:47` (+6s)
  `input tap 1440 858` (WALLET) + screencap → wallet-tab-top.png; dump → `My Wallet / Self-custody · keys never leave this device / 1.4999 MAZA / RECEIVE ADDRESS index 2 / MGo1gjPrj2GDnbwcyRBJMaZ4GJMEAaVkU8 / NEXT / QR`
- round3: `input swipe 800 620 800 180 400` (scroll WALLET) + screencap → wallet-send-self-custody.png; dump → `SEND · SELF-CUSTODY` + `Signed on this device from your own seed balance.`

## Post-capture hygiene
- all 5 PNGs pulled via `adb pull` + scp (no exec-out redirects)
- vision-check 5/5: no credential/token/password/seed material on any screenshot (only public on-chain data)
- token scan over the package: `grep -rlF <live-literal>` = 0; `Bearer [A-Za-z0-9]{16,}` = 0; standalone 32-char alnum blobs = 1 in the FINAL package (the APK md5 quoted in these transcripts — build identity, not a credential; the capture-time scan read 0 because PROOF/RUN-TRANSCRIPT/EVIDENCE-RAW did not exist yet; final-package re-run with exit codes in EVIDENCE-RAW.md §5); mnemonic patterns = 0
- tree at commit time: only `android/evidence/m22b/**` added (no code changes)
