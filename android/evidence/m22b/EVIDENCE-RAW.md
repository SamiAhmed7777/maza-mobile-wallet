# M22b EVIDENCE-RAW.md — raw command outputs backing the PROOF.md claims

Captured 2026-11-16, tick 24a7311de928, judge round 2 of
m22b-bluestacks-evidence (r1: urn:ump:yzfrbbyakthivooxwt2qevrz6zesutctp6iefiev6q2nlikarhmq,
grade C — blockers: (1) unqualified pulls vs documented duplicate transport,
(2) provenance claims lacking raw output in-package; polish: exact
apostrophe quote, exit codes). This file answers both blockers with fresh,
re-runnable captures. `ADB` = `"C:\Program Files\BlueStacks_nxt\HD-Adb.exe" -s emulator-5554`.

## 1. Build + host APK identity (DNS2, fresh re-run at ~09:57 PST)

```
$ sha256sum android/maza-wallet-bench.apk
e9cb8e5c8f7aed82a6e3a5123556fdf385e0cdae1c9c4deef2bfc3849d8eab6b  android/maza-wallet-bench.apk
$ md5sum android/maza-wallet-bench.apk
a3cd0326062d2d4e5344c04df39ab75d  android/maza-wallet-bench.apk
RC=0
$ aapt2 dump badging android/maza-wallet-bench.apk | grep -E "^package|sdkVersion|targetSdk|application-label"
package: name='com.mazawallet' versionCode='1' versionName='1.0' platformBuildVersionName='14' platformBuildVersionCode='34' compileSdkVersion='34' compileSdkVersionCodename='14'
sdkVersion:'24'
targetSdkVersion:'34'
application-label:'MAZA Wallet'
$ bash android/selftest.sh        # the build's stage [1/6] gate, re-run standalone
...
PASS btc address m/44'/0'/0'/0/0
-- TxBuilder (legacy P2PKH, SIGHASH_ALL)
PASS txbuilder sign + verify

ALL 19 CHECKS PASSED
SELFTEST_RC=0
```

Build-tail verbatim from the 09:10 PST build this tick (terminal capture):
`[1/6] ... ALL 19 CHECKS PASSED` then `[2/6] aapt2 compile` `[3/6] aapt2
link` `[4/6] javac` `[5/6] d8` `[6/6] apksigner` `SIGNED OK:
/root/maza-mobile-wallet/android/maza-wallet-bench.apk (271316 bytes)`
`BUILD_RC=0`.

## 2. Install identity on the emulator (fresh re-run, device-targeted calls -s-qualified)

From m22b-round4.cmd (in this package), unfiltered key output:

```
=== devices ===
List of devices attached
* daemon not running. starting it now on port 5037 *
* daemon started successfully *
emulator-5554	device          <-- exactly ONE transport attached

=== installed apk identity ===
package:/data/app/com.mazawallet-J-0lYxyTQ-rVRyOrgMHV6g==/base.apk
a3cd0326062d2d4e5344c04df39ab75d  /data/app/com.mazawallet-J-0lYxyTQ-rVRyOrgMHV6g==/base.apk
    lastUpdateTime=2026-11-16 09:12:28
```

Installed base.apk md5 == host build md5 (`a3cd0326062d2d4e5344c04df39ab75d`)
— parity re-proven live at ~09:56 PST, ~44 minutes after install.

## 3. Transport explanation + byte-identity of the committed captures

Round-1/2/3 scripts as first written ran `pull` WITHOUT `-s` and succeeded.
Explanation, verified in round 4: the SAMI-PC adb SERVER RESTARTS between ssh
sessions (each ssh invocation found `daemon not running. starting it now`),
and a fresh server attaches only the emulator transport (`emulator-5554`);
the duplicate `127.0.0.1:5555` transport from the post-install `connect`
exists only until that server restart. Round-4 `devices` (above) shows
exactly one transport — the state under which the unqualified pulls ran.
The scripts in this package have been CORRECTED to `-s emulator-5554` on
every device-targeted call (the reproducible form), and round 4 re-pulled
all five PNGs from `/sdcard` with `-s`:

```
Hash : 1CE345B19142FFFB634FFE8B2B0CAD80CEAFB2E34B1BB05E4E30FABA5DD6E628   = balance-t0.png
Hash : 8748BD2F5908D43FAF740557EB0E78F0243D7C2547B3A490E35F96986BDED13E   = send-tab-bench-account.png
Hash : BCA2A53920740862F75583C18196F335621680F09F95F12F696D31726CAC73FD   = balance-after-nav.png
Hash : 02F4725BB9CA1B74A888CF798B4D01BB42A7B369D42B92DED8DE3AFFACE767CC   = wallet-tab-top.png
Hash : 191E34085AE497B8B5D5123F410882A7BF0E6A98BD04BFA217BBDF6539ED0EE0   = wallet-send-self-custody.png
```

All five hashes are byte-identical to the committed files (the same table in
PROOF.md), proving the committed artifacts are the device's bytes via a
transport-qualified retrieval path. (Round-4 output above elides only the
adb `[ 48%]`-style progress-percentage lines and blank lines.)

## 4. Token-entry pre/post field nodes (verbatim from the uiautomator dumps)

PRE (fresh app, before entry) — hint only, field EMPTY:

```
<node index="3" text="bench token" resource-id="" class="android.widget.EditText" package="com.mazawallet" ... password="true" ... bounds="[54,421][1546,489]" />
```

POST (after type-token.cmd typed the token via stdin) — exactly 32 bullet
characters, one per token character; NO plaintext:

```
<node index="3" text="••••••••••••••••••••••••••••••••" resource-id="" class="android.widget.EditText" package="com.mazawallet" ... password="true" ... bounds="[54,421][1546,489]" />
```

(Same field bounds before/after; `focused="true"` post-entry.) The 32-char
token was typed ONCE, never echoed, never screenshotted; the Connect card
appears in NO committed screenshot. Exposure scope (matching PROOF.md): the
token transited the two transient argvs (host-side `HD-Adb.exe` on SAMI-PC +
on-device `input`), was staged only in `/tmp/m22b-token` on DNS2 (SHREDDED
post-run, `shred -u -n 3` exit 0, verified absent; SAMI-PC never held a
token file), and appears in no committed artifact.

## 5. Token-hygiene scans over this package (fresh re-run, with exit codes)

```
$ grep -rlF <live-token-literal> .
(no output)  grep_rc=1   <- 1 = no match = CLEAN
$ grep -rE 'Bearer [A-Za-z0-9]{16,}' .
(no output)  grep_rc=1   <- CLEAN
$ grep -rhoE '\b[A-Za-z0-9]{32}\b' . | grep -v '^M' | sort -u
a3cd0326062d2d4e5344c04df39ab75d
```

The single 32-char blob hit is the APK md5 quoted in this package's own
transcripts — the documented build identity, not a credential. Mnemonic-word
pattern scan: 0 matches.

## 6. Exact on-screen texts (from the committed dumps, apostrophe preserved)

```
$ grep -o 'text="Spends[^"]*"' dump-send-tab.xml
text="Spends the bench server's held funds (server-side, capped). Your own seed wallet is on the WALLET tab."
$ grep -o 'text="Signed[^"]*"' dump-wallet-send-card.xml
text="Signed on this device from your own seed balance."
$ grep -o 'text="SEND[^"]*"' dump-send-tab.xml
text="SEND · BENCH ACCOUNT"
$ grep -o 'text="SEND[^"]*"' dump-wallet-send-card.xml
text="SEND · SELF-CUSTODY"
```

PROOF.md round-2 edition quotes the note with the possessive apostrophe.

## 7. Refresh-sequence capture moments (wall clock from the SAMI-PC session)

m22b-round2.cmd ran: S1 dump → NAV1 (tap SEND 800,858; ping ~2-3s; tap
BALANCE 160,858; ping ~2-3s) → S2 dump → NAV2 → S3 dump. Round-trip wall
time ~5-6s each (ping -n 3 ≈ 2s per hop + adb overhead ~0.5-1s per call).
Last-sync values S1 09:20:36 → S2 09:20:41 (+5s) → S3 09:20:47 (+6s): each
advance equals the navigation round-trip duration, i.e. the sync happened ON
navigation. Under poll-only the two advances would each be ≈15s (multiples
of the poll grid).

## 8. Token staging-file lifecycle (post-run cleanup, fresh transcript ~10:1x PST)

```
$ ls -la /tmp/m22b-token
-rw-r--r-- 1 root root 33 Nov 16 09:15 /tmp/m22b-token
$ wc -c < /tmp/m22b-token
33
$ shred -u -n 3 /tmp/m22b-token
shred_rc=0
$ ls -la /tmp/m22b-token
ls: cannot access '/tmp/m22b-token': No such file or directory
$ ssh sami-pc "dir C:\Users\hello\m22b* | findstr /i token"
(no token-named files above = clean)
```

The token's only STAGING copy (distinct from its origin in the samihost env
file) existed on DNS2, for the tick's duration, and is now destroyed.
Committed artifacts never contained it (§5 scans).
