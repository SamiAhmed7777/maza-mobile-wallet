# M21 — watch set re-imported on every unlock: device proof

Evidence lane: interactive session, 2026-11-16 04:0x–05:1x PST.
Code under proof (resolvable in origin/master of
`https://github.com/SamiAhmed7777/maza-mobile-wallet`):

- `3d31c2582cd33d8cbdf2ef68e3db90e5566b46fe` — 2026-11-16 03:42:27 -0800,
  grade A (urn:ump:7fsgukdr75jbyfasbasl63tkewasn6roiqszad6txjzfvdtwnmsa):
  `SelfCustody.onUnlocked()` (seedExists guard) wired into the unlock path.
  Pre-fix, `ensureWatchImported()` fired only on WALLET-tab shown while
  unlock lands on BALANCE (`selectTab(0)`).
- `bea687acda834b0e7e07959b63ebed02c9e837f8` — 2026-11-16 04:35:08 -0800,
  grade B (urn:ump:ud37ynbyau6o5zv6wiutupb3qm5hbcs7cjlwbojoidaaa7b6qeqq):
  count-only `WATCH_IMPORT seq=N imported=C status=S` access line per
  /api/watch/import request (journald-visible; never addresses/tokens/IPs);
  deployed release 20261116-123642 live on samihost from 04:36 PST.

Reproduce either commit with `git -C <clone> show <sha>` (both on
origin/master; push verified by `git ls-remote origin master` ==
`bea687acda83…`).

## What was proven

The app re-imports its full 40-address watch window as part of the UNLOCK
action itself (no tab navigation required), so a wallet whose creation-time
import was interrupted recovers on the next unlock instead of staying blind
for the whole session (the live M2 incident).

## THE PROOF — recorded run 2 (raw transcript: RUN2-TRANSCRIPT.txt)

BlueStacks Pie64 on SAMI-PC, emulator-5554, seed data preserved (M2 wallet).
APK built from `bea687a` (build stage [1/6] crypto selftest gate passed;
sha256 `a74792c9cf24b268a5fa18876ed18de47a5ba04b024b435fe26425240188823c`;
installed `base.apk` md5 `062b5ab71d8513e2295473eba774e477` == host APK md5,
byte-identical). Then, every step timestamped (all UTC, from the transcript):

| T+ | Action (exact command/event) |
|---|---|
| 13:03:03.5 | T0: about to force-stop (app from prior session still running) |
| 13:03:03.5 | `adb shell am force-stop com.mazawallet` |
| 13:03:16.2 | `adb shell am start -n com.mazawallet/.MainActivity` |
| 13:03:36.3–51.8 | bench token typed into the Connect-card field (stdin path; the script's only output is the masked-field line `EditText[1] len=96`) |
| 13:03:51.8 | `adb shell input tap 800 576` → **CONNECT = the unlock. NO tab tap.** |
| 13:03:52–13:04:05 | passive wait; **no input of any kind** |
| **13:04:05** | **samihost journald: `WATCH_IMPORT seq=5 imported=40 status=200` — 13.2 s after the unlock tap, before any tab interaction** (raw UTC-native line in RUN2-TRANSCRIPT.txt) |
| 13:04:18 | uiautomator dump #1: app is on the bench BALANCE tab (landing view; `46.9998774 MAZA / account mobile-play`) |
| 13:04:32.7 | `adb shell input tap 1440 858` → WALLET tab (first tab interaction) |
| **13:04:43** | journald: `WATCH_IMPORT seq=6 imported=40 status=200` — 10.3 s after the tab tap (the pre-existing tab-path import) |
| 13:04:51 | uiautomator dump #2: `My Wallet / BALANCE 1.4999 MAZA / RECEIVE ADDRESS index 2 / MGo1gjPrj2GDnbwcyRBJMaZ4GJMEAaVkU8` |

The two journal lines demonstrate BOTH triggers separately in one session:
the **unlock-path import (seq=5) is the M21 fix firing with zero tab
interaction**, and the tab-path import (seq=6) is the pre-existing behavior
firing on the WALLET-tab show. Correlation is tight: the device's entire
input stream in the window is enumerated above (two adb commands, one
scripted token typing, two taps — nothing else), the emulator was otherwise
idle, and `imported=40` matches exactly the app's `allAddresses()` window
for this seed (20 receive + 20 change; the M2 send advanced changeIndex to
19 → max(20, 19+1) × 2 = 40). Request IDs do not exist by design (the
access line is deliberately count-only per `bea687a`'s privacy requirement).

## Screenshot inventory (files in this directory, sha256)

| File | sha256 | Shows |
|---|---|---|
| `m21_run2_wallet.png` | `a9955d8a0d688d4a5414e10f06d9ace9257818762f237ad01159846aae22b736` | Run 2, WALLET tab after the proof: **self-custody BALANCE 1.4999 MAZA; RECEIVE ADDRESS card index 2 `MGo1gjPrj2GDnbwcyRBJMaZ4GJMEAaVkU8`** + QR. Verified by uiautomator XML (ur2b.xml) AND visual inspection. |
| `m21_unlock_wallet.png` | `5fea73c84f9a2caf95294809048e9a595a343952af62ea53571ce295879d13cc` | Run 1, WALLET tab after that run's proof: same wallet state (1.4999 MAZA, receive card **index 2**, same `MGo1gj…` address). |
| `m21_unlock_balance.png` | `7dda7bca3f86c3211cf1e4556594fd60f43ef04fa56d833ee9f60ea1cb0212a3` | Run 1, the app's **bench BALANCE tab** right after unlock: the CUSTODIAL bench account (`mobile-play`, 46.9998 MAZA) — NOT the self-custody balance. This is the view unlock lands on. |
| `wallet-after-unlock.png` | `43a3c4fac96d9697889e6c4e0bca24bb2acd0316f9b8b4565f97a628ff5717ce` | Second tab-path flow (~04:20 PST, pre-`3d31c25` build): WALLET tab, BALANCE 1.4999 MAZA, receive card at **index 1 `MNMk5rQLqj6VEasAcMsnZF3y4LUHUordxm`** (verified by visual inspection of the PNG). |
| `wallet-render-1st-unlock.png` | `7d137989771e60ecffab1e448bbb9218c06cb022417b9f556290c59ea43321a3` | First tab-path flow (~04:09 PST, pre-`3d31c25` build): WALLET tab, BALANCE 1.4999 MAZA, receive card at **index 0 `MPHoBsbsNUduo7fsvMCREpDSMWpyeUxq2H`** (verified live by uiautomator dump ur2-era AND visual inspection). |

The receive-card progression across the session (0 → 1 → 2, addresses
`MPHoBsbs…` → `MNMk5rQL…` → `MGo1gjPrj…`) is itself a cross-check: those
three addresses are exactly the first three entries of the app's derived
receive chain, and all three appear (in the same order) inside the
40-address import body captured on the wire earlier in the session.

### Address note (why the receive card is index 2, not index 0)

The WALLET screen shows TWO different addresses by design, and both advance
independently of the balance:

- **BALANCE 1.4999 MAZA** lives at the chain-1 CHANGE address
  `MRfcWqfdXjgJYCY8s1BbjrpNpemgTY1q9h` (change index 0) — exactly where the
  M2 spend tx `ce514b350d2c…cd4e` sent its change (verified on-chain via
  `/api/watch/utxos`, transcript below).
- The **RECEIVE ADDRESS card** shows the next unused RECEIVE address. In the
  earlier runs it was index 0 (`MPHoBsbs…`); across the session's multiple
  unlock/render cycles the app advanced its receive window, so the run-1/
  run-2 post-proof screens show **index 2** (`MGo1gjPrj2GDnbwcyRBJMaZ4GJMEAaVkU8`).
  Normal wallet behavior — the balance address and the displayed receive
  address are different addresses on purpose.

## Command/output transcript (run 1 + suite; sanitized, token = ***)

```
$ bash android/build-apk.sh            # stage [1/6] = crypto selftest gate
[4/6] javac
[5/6] d8
[6/6] apksigner
SIGNED OK: /root/maza-mobile-wallet/android/maza-wallet-bench.apk (271316 bytes)
$ sha256sum android/maza-wallet-bench.apk
a74792c9cf24b268a5fa18876ed18de47a5ba04b024b435fe26425240188823c  android/maza-wallet-bench.apk

$ adb -s emulator-5554 shell pm install -r /sdcard/maza.apk
Success
$ adb -s emulator-5554 shell md5sum /data/app/com.mazawallet-VIoivqhMRY-r6kV1tbfhYA==/base.apk
062b5ab71d8513e2295473eba774e477  /data/app/com.mazawallet-VIoivqhMRY-r6kV1tbfhYA==/base.apk
$ # host-md5 of the pushed file: 062b5ab71d8513e2295473eba774e477 -> byte-identical install

$ python3 -m unittest discover -s tests          # at bea687acda83…
Ran 131 tests in 54.934s
OK (skipped=4)                                    # 4 electrumx-integration skips

$ curl -H "Authorization: Bearer ***" "http://100.121.150.22:18701/api/watch/utxos"
{"utxos": [{"txid": "ce514b350d2c2dc362b8cea0babc9ac64b8261b547142cc93a94ae366350cd4e",
  "vout": 1, "address": "MRfcWqfdXjgJYCY8s1BbjrpNpemgTY1q9h", "amount": 1.4999,
  "confirmations": 180}]}
# NOTE: /api/watch/utxos ignores any ?addr= query parameter by design — it
# returns UTXOs for the ENTIRE watch set (walletbench/api.py _watch_utxos).
```

## Supporting evidence: run 1 + tab-path wire captures (pre-fix build)

Run 1 (04:44–04:45 PST) proved the same fix earlier: T0 12:44:14 UTC, fresh
unlock with no tab tap, journald `WATCH_IMPORT seq=3 imported=40 status=200`
at 12:45:16 UTC (14 s after the CONNECT tap). Three earlier tab-path flows
were wire-captured on the tunnel (plaintext HTTP, DNS2 leg; `tcpdump -i any
-A -s … tcp port 18701`), each producing **exactly one**
`POST /api/watch/import` with a 40-unique-address body covering both chains
— including receive index 0 (`MPHoBsbs…`) and the funded change address
(`MRfcWq…`). Raw pcap text was deleted after extraction because it contains
the bearer header; only the counts and address facts above were retained.

## Scope caveat (honest note)

"Fresh install" here = fresh app PROCESS over preserved app data (seed
intact), which is the recovery scenario M21 targets (M2's blind wallet). A
literal `pm clear` fresh-install proof is possible but destroys the on-device
seed; that seed's 12 words exist only in Sami's paper/in-chat backup, so the
device copy must not be wiped without his explicit go (funds would remain
on-chain recoverable solely from that backup).
