# S-2b-ii device graceful-absence proof (BlueStacks Pie64, API 28)

Item: S-2b-ii REMAINING half — "device graceful-absence pass (locked cover renders
PIN-only, unchanged vs pre-biometric renders)". BlueStacks has no fingerprint
hardware, so the only device-observable biometric behavior on this bench is the
API-28 graceful-absence path; that is what this package proves.

## Verdict

**PASS.** On the S-2b-ii biometric build (commit 330359e tree), the locked cover
on API 28 renders EXACTLY the pre-biometric PIN-only structure with ZERO
biometric affordances, and the PIN unlock path + wallet session work unchanged
after an in-place update of the seed-bearing build.

## Build provenance (one canonical set of hashes, this build only)

- Graded tree: commit 330359e (`git rev-parse HEAD` at package time = 330359e).
- APK: `android/maza-wallet-bench.apk`, 316529 bytes,
  sha256 `b8332f08a6979288afac74597031d9972742cb1e8eab6c4d1f8daf8e66068d3b`
  (matches the sha recorded in the 330359e commit message for its post-fold
  build; apksigner output is not byte-reproducible, so this hash is identity
  for THIS build only).
- Install: `adb push` + `pm install -r` -> `Success`; pushed size 316529 B =
  host size; installed `pm path` base.apk md5 `6bc3fb2024e196cfba4fb4f21810b829`
  == host APK md5 `6bc3fb2024e196cfba4fb4f21810b829` (byte-identical install).
- `firstInstallTime 2026-11-15 18:39:10` UNCHANGED across the update
  (update-not-wipe; Sami's seed-bearing build preserved — same proof shape as
  the S-2b-i provenance). `lastUpdateTime` moved `2026-11-17 08:07:50` ->
  `2026-11-17 12:08:51` (the new build is the running one).

## Method (before/after on the SAME device, same day)

1. PRE capture on the installed pre-biometric build (wave-3 tree, lastUpdateTime
   08:07:50): fresh session (`am force-stop` + `am start`) -> Connect card
   layout verified by dump (URL prefilled with the saved public endpoint,
   token field EMPTY — hint text; exactly 1 `password="true"` field) -> token
   typed from a staged file (runtime-read, never in a script or artifact) ->
   CONNECT -> locked cover captured (dump + PNG).
2. Install the 330359e APK (push + pm install -r), reconnect, verify package
   survived + update-not-wipe + md5 parity (above).
3. POST capture: fresh session -> Connect card -> connect (token staged file
   again, deleted after, `TOKENFILE-DELETED=True` verified) -> locked cover
   captured at +12s and +27s (two dumps).
4. Unlock with the bench test PIN (disclosed in the committed s2b-pin driving
   scripts; same shape as final-accept.ps1: focus field, type, ENTER, tap
   UNLOCK) -> cover gone, BALANCE renders with a fresh authenticated sync.
5. WALLET tab -> self-custody wallet renders (seed file intact post-update).

## Results

### Locked-cover structure — the four cover dumps

| Element | pre (wave-3 build) | post +12s | post +27s |
|---|---|---|---|
| `Wallet locked` (TextView) | yes | yes | yes |
| `Enter your PIN to continue.` (TextView) | yes | yes | yes |
| `PIN or passphrase` (EditText) | yes | yes | yes |
| `UNLOCK` (Button) | yes | yes | yes |
| `Unlock with biometrics` (Button) | **absent** | **absent** | **absent** |
| any `biometric` substring in the dump | 0 hits | 0 hits | 0 hits |

The POST cover element set is IDENTICAL to the PRE cover element set (same
texts, same classes; `Wallet locked` covers otherwise only tab-bar chrome).
The grep counts are in transcript.md verbatim.

### Code linkage (why absence is the correct behavior, not an omission)

`MainActivity.java` (commit 330359e): `biometricBtn` is created GONE
(line 1086, "before S-2b-ii" comment) and shown only when
`BiometricPolicy.offer(minSdk, apiLevel, biometricReadyNow(), pinGuard
.biometricUnlockAllowed())` is true (lines 1098-1109). `BiometricPolicy`
(MIN_API=29; `BiometricManager` is an API-29 class per the D12 decision
record) returns offer=false below API 29. The bench device is API 28 ->
`biometricBtn` stays GONE -> the cover renders exactly the pre-biometric
structure. The dumps confirm the code path's observable result on device.

### Wallet intact after the in-place update

- PIN unlock works (cover dismissed; `Wallet locked` absent from the
  post-unlock dump; fresh sync line `Last sync 2026-11-17 12:12:38`).
- WALLET tab renders: `My Wallet` / `Self-custody · keys never leave this
  device` / BALANCE / RECEIVE ADDRESS (index 4 + address + QR) — the
  self-custody wallet is functional after the update.

## Honest scope notes

- The biometric-OFFER path itself (API>=29 device with fingerprint hardware)
  is NOT device-provable on this bench and is not scheduled; the wiring is
  proven by the committed contract tests (accepted-with-disclosure in the
  330359e verdict). This package covers only the API-28 graceful absence,
  which is the complete set of device-observable biometric behavior here.
- Screenshots show `0.00000000 MAZA` balances. That is NOT an app defect:
  the bench's mazad node is mid-`initialblockdownload` at capture time (ops
  note below); the app's balance rendering under a synced node is proven by
  prior committed evidence (M21: 1.4999 MAZA; M22b: 46.9998774 MAZA).
- Token handling: the WB_TOKEN was staged to a 0600 file on the driving host
  by a script that assembles the env-var name at runtime, read by the driving
  scripts via Get-Content, never present in any script text, dump text (only
  masked bullets), PNG, or this package; the staged file was deleted after
  each connect with `TOKENFILE-DELETED=True` verified in the transcript.

## Ops note captured during this tick (NOT an app finding; recorded for the run log)

The bench's mazad node on samihost is in a fresh full sync (IBD):
`getblockchaininfo` -> `initialblockdownload: true`, `verificationprogress
~0.486`, blocks ~1.678M vs headers ~2.363M (probe ~20:2x UTC), UpdateTip
lines processing 2020-09-03-era blocks; blocks dir reset 2026-11-17 01:59
CET; service restarted 2026-11-17 20:51:53 CET. Wallet keys intact (bench
book primary address `ismine: true`, account mobile-play). Zero balances
everywhere are a sync side-effect — UTXOs sit at heights the fresh chain has
not reached; they return when the sync passes them. This is the mazapay-ops
lane's territory (the walletbench node), not the mobile-wallet loop's; the
walletbench service itself stayed healthy throughout (root 200, /api/state
401 over the public front door).

## Secret / exposure checks

- All four PNGs vision-checked: no token value, no seed words, no PIN
  plaintext; only public addresses render (WALLET tab receive address).
- `ui-pre-lock.xml` (mid-connect state) shows the token field as 32 masked
  bullets only (`password="true"` field); the corresponding PNG is NOT
  included in this package (the committed cover PNGs contain no token field).
- Package-wide scan: no 32-char opaque literals; PIN appears only as the
  driving scripts' `input text 2468` (the bench test PIN disclosed in the
  committed s2b-pin scripts).
