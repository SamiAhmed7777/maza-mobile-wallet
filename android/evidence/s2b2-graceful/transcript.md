# S-2b-ii graceful-absence — verbatim transcript (TZ: PST; dumps device-side)

Commands executed from DNS2 over SSH to SAMI-PC (BlueStacks HD-Adb); outputs
pasted verbatim from the tool results. Clock references: screenshots embed the
device clock (12:07 pre / 12:11-12:13 post).

## 1. Environment at tick start

$ sha256sum /root/maza-mobile-wallet/android/maza-wallet-bench.apk
b8332f08a6979288afac74597031d9972742cb1e8eab6c4d1f8daf8e66068d3b  /root/maza-mobile-wallet/android/maza-wallet-bench.apk

$ ssh sami-pc 'HD-Adb connect 127.0.0.1:5555 & HD-Adb devices'
connected to 127.0.0.1:5555
List of devices attached
127.0.0.1:5555	device
emulator-5554	device

$ ssh sami-pc 'HD-Adb -s emulator-5554 shell dumpsys package com.mazawallet | findstr lastUpdateTime/firstInstallTime/versionName'  (pre-install)
versionName=1.0
firstInstallTime=2026-11-15 18:39:10
lastUpdateTime=2026-11-17 08:07:50     <- the PRE-biometric (wave-3) build

## 2. PRE-biometric connect + locked cover

$ ssh sami-pc 'powershell -File ...\s2b2-pre\pre-dump.ps1'   (Connect card layout)
android.widget.EditText 'https://mazatest.sami-host.me' [54,308][1546,376]
android.widget.EditText 'bench token' [54,421][1546,489]     <- hint = EMPTY
android.widget.Button 'CONNECT' [54,540][1546,612]
password fields: 1

$ ssh sami-pc 'powershell -File ...\s2b2-pre\pre-connect.ps1'
TOKENFILE-DELETED=True
PRE-CONNECT-DONE

$ python3 - (grep of ui-pre-lock.xml, mid-connect state)
biometric mentions: 0
 android.widget.EditText | '••••••••••••••••••••••••••••••'   <- 32 masked bullets
 android.widget.TextView | 'Connecting...'

$ python3 - (grep of ui-pre-lock2.xml, locked cover, +15s)
biometric mentions: 0
 android.widget.TextView  | 'MAZA Wallet'
 android.widget.TextView  | '0.00000000 MAZA'
 android.widget.TextView  | 'account mobile-play · fee 0.0001 MAZA'
 android.widget.TextView  | 'Last sync 2026-11-17 12:07:54'
 android.widget.Button    | 'REFRESH' ... 'BALANCE' 'RECEIVE' 'SEND' 'HISTORY' 'WALLET'
 android.widget.TextView  | 'MAZA Wallet'
 android.widget.TextView  | 'Wallet locked'
 android.widget.TextView  | 'Enter your PIN to continue.'
 android.widget.EditText  | 'PIN or passphrase'
 android.widget.Button    | 'UNLOCK'
('Unlock with biometrics' count: 0)

## 3. Install the 330359e build

$ ssh sami-pc 'powershell -File ...\s2b2-pre\install.ps1'
[100%] /sdcard/maza-s2b2.apk
-rw-rw---- 1 root sdcard_rw 316529 2026-11-17 12:08 /sdcard/maza-s2b2.apk
Success
INSTALL-ISSUED

$ ssh sami-pc 'powershell -File ...\s2b2-pre\verify-install.ps1'
versionName=1.0
firstInstallTime=2026-11-15 18:39:10     <- unchanged: update-not-wipe
lastUpdateTime=2026-11-17 12:08:51       <- new build in
6bc3fb2024e196cfba4fb4f21810b829  /data/app/com.mazawallet-5JVKpx-SnhD4psV0ieH1cA==/base.apk

$ md5sum /root/maza-mobile-wallet/android/maza-wallet-bench.apk
6bc3fb2024e196cfba4fb4f21810b829  /root/maza-mobile-wallet/android/maza-wallet-bench.apk
(host md5 == installed md5)

## 4. POST-biometric connect + locked covers

$ ssh sami-pc 'powershell -File ...\s2b2-pre\post-connect.ps1'
TOKENFILE-DELETED=True
POST-CONNECT-DONE

$ python3 - (grep of ui-post-lock1.xml, +12s; ui-post-lock2.xml, +27s)
=== ui-post-lock1 === biometric mentions: 0 | unlock-with-biometrics: 0
 ... 'Wallet locked' / 'Enter your PIN to continue.' / 'PIN or passphrase' / 'UNLOCK'
     ('Last sync 2026-11-17 12:10:36')
=== ui-post-lock2 === biometric mentions: 0 | unlock-with-biometrics: 0
 ... identical element set ('Last sync 2026-11-17 12:10:51')

## 5. PIN unlock + wallet render

$ ssh sami-pc 'powershell -File ...\s2b2-pre\unlock.ps1'   (tap 800,375; input 2468; keyevent 66; tap 800,496)
UNLOCK-STEP1-DONE

$ python3 - (grep of ui-post-unlock1.xml)
locked cover still present: False
 android.widget.TextView | 'MAZA Wallet' / '0.00000000 MAZA'
 android.widget.TextView | 'account mobile-play · fee 0.0001 MAZA'
 android.widget.TextView | 'Last sync 2026-11-17 12:12:38'
 android.widget.Button   | 'REFRESH' + tab bar

$ ssh sami-pc 'powershell -File ...\s2b2-pre\wallettab.ps1'   (tap WALLET 1440,858)
WALLET-TAB-DONE

$ python3 - (grep of ui-post-wallet-tab.xml)
 android.widget.TextView | 'My Wallet'
 android.widget.TextView | 'Self-custody · keys never leave this device'
 android.widget.TextView | 'BALANCE' / '0.00000000 MAZA'
 android.widget.TextView | 'RECEIVE ADDRESS' / 'index 4'
 android.widget.TextView | 'MRQswDmXBiGqqmtPzHh2ViMkEL7uNDaaPy'
 android.widget.Button   | 'NEXT'

## 6. Screenshot vision checks (4 PNGs)

pre-lock2.png: PIN-only cover, no biometric button, no token/seed/PIN plaintext.
post-lock2.png: identical PIN-only cover, no biometric button, clean.
post-unlock1.png: BALANCE tab unlocked, clean.
post-wallet-tab.png: WALLET tab with public receive address + QR, clean.

## 7. Node-state probes recorded during the same tick (ops note)

$ curl -s -H "Authorization: Bearer $T" https://mazatest.sami-host.me/api/state
{'balance': 0, 'address': 'MWRVvgWrLRqyEEQSm7J8NuYor1X9J4J9Fa', 'account': 'mobile-play', 'fee': 0.0001, 'txs': '3 items'}
$ curl -s -H "Authorization: Bearer $T" https://mazatest.sami-host.me/api/watch/utxos
utxo count: 0 utxo total: 0
$ python3 (via walletbench.chain on samihost) getblockchaininfo
headers 2363299 blocks 1678584 IBD True verifprogress 0.4904 connections: 8 version 160300 /MazaCore:0.16.3/
$ validateaddress MPHoBsbsNUduo7fsvMCREpDSMWpyeUxq2H  -> ismine False watchonly True
$ validateaddress MWRVvgWrLRqyEEQSm7J8NuYor1X9J4J9Fa  -> ismine True watchonly False account mobile-play
$ journalctl -u mazad -n 12: UpdateTip height=1658416..1658417 date='2020-09-03 06:0x' progress=0.486353
(processing 2020-era blocks; blocks dir mtime 2026-11-17 01:59; service ExecMainStartTimestamp 2026-11-17 20:51:53 CET)
