# M21 — App re-imports its watch set on unlock

Artifact: 2-file Java change in the MAZA mobile wallet Android app (raw aapt2/javac/d8/apksigner pipeline, no Gradle) + evidence.

## Defect being fixed

The wallet app watches its own derived addresses via the backend's idempotent
watch-only import (`POST /api/watch/import`, 40 addresses = receive 0..19 +
change 0..19). Before this change that import ran from exactly two places:

1. `SelfCustody.finishSetup()` — right after seed creation/import.
2. `SelfCustody.onShown()` — only when the user manually opens the WALLET tab
   (`MainActivity.selectTab` calls it only for `i == TAB_WALLET`, index 4).

Unlock lands on the BALANCE tab (`showWallet()` ends with `selectTab(0)`), so
after a successful unlock neither trigger fires until the user happens to tap
WALLET. A creation-time import that died mid-flight (this exact incident
happened live during the M2 mainnet proof: an Android runtime crash killed the
import, and the watch set had to be re-imported manually from the host) leaves
the wallet blind for the whole session: balance and history silently empty.

## The change

- `android/src/com/mazawallet/SelfCustody.java`: new public `onUnlocked()` —
  guards on `seedExists()` (no seed on a fresh install = nothing to derive or
  import; calling the derive path with no seed would derive from an empty
  mnemonic and import garbage addresses), then runs the existing
  `ensureWatchImported()` (3 attempts, backoff, user-visible failure note).
- `android/src/com/mazawallet/MainActivity.java`: `showWallet()` calls
  `selfCustody.onUnlocked()` immediately after `buildWalletTab()`, i.e. once
  per successful unlock, before any tab is shown.

`ensureWatchImported()` and `allAddresses()` are unchanged and keep the shared
bound `max(ADDR_COUNT, changeIndex + 1)` (the recovery-invariant fixed under a
prior judge round). The backend import is idempotent: `walletbench/api.py`
`_watch_import` dedupes within the request and an existing suite test asserts
a second import of the same address returns 200 (`tests/test_walletbench.py`
"idempotent second import"). No backend change in this artifact.

## What is verified in this round (verbatim transcripts)

### CMD: bash android/build-apk.sh
```
[1/6] crypto selftest (gate — any FAIL aborts the build before packaging)
ALL 19 CHECKS PASSED
[2/6] aapt2 compile
[3/6] aapt2 link
[4/6] javac
[5/6] d8
[6/6] apksigner
SIGNED OK: /root/maza-mobile-wallet/android/maza-wallet-bench.apk (271316 bytes)
```
The stage-1/6 crypto selftest gate passed all 19 vector checks (BIP39
official, BIP32 xprv chain, MAZA profile, tx sign+verify); javac compiled the
new code; APK signed.

### CMD: python3 -m unittest discover -s tests
```
Ran 95 tests in 40.110s
OK (skipped=4)
```
walletbench suite green (the 4 skips are the pre-existing electrumx
integration skips; backend untouched by this change — run confirms no
regression).

### CMD: grep -n "onUnlocked\|selectTab(0)\|i == TAB_WALLET" android/src/com/mazawallet/MainActivity.java
```
191:        selfCustody.onUnlocked();
216:        selectTab(0);
230:        if (i == TAB_WALLET && selfCustody != null) selfCustody.onShown();
```
Trigger path: the new call site MainActivity.java:191 sits inside
`showWallet()` (runs once per successful unlock), and `selectTab(0)` at
MainActivity.java:216 still lands on BALANCE — the exact gap being closed.
`SelfCustody.java:151` declares `public void onUnlocked()`.

## Explicitly deferred (honest scope note — backlog item stays open)

The on-device end-to-end proof (fresh install + unlock -> watch/utxos
populated without touching the WALLET tab) is deferred to a follow-up tick.
Reason: the live bench's mazad wallet already watches the M2 seed's addresses
(watched during the manual M2 recovery), and mazad exposes no un-import or
import-timestamp, while the backend has no per-request logging — so "the
import fired at unlock time" is not observable on the live bench without
either a tiny backend access-log addition or a fresh watch state (which would
mean touching the funded mazad wallet — out of bounds per TERRITORY). The
deferred tick adds the backend access-log line (address-count granularity,
never the addresses) and then runs the BlueStacks proof against it. This
round claims and grades only the client-side trigger fix, its build, and the
suite.

## Rubric

A/B/C/D/F per the standing Codex rubric. Judge the Java diff for correctness
(call-site reachability, the no-seed guard, idempotency assumptions), the
honesty of the deferred-evidence note, and packaging (evidence rides the
commit).
