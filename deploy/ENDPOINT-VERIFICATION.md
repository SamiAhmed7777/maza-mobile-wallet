ENDPOINT VERIFICATION BUNDLE — mazatest public test endpoint
Generated 2026-11-16 (evidence for deploy/PUBLIC-HOSTING.md; all outputs
verbatim from machine runs; token values never printed).
Every section verifies the SAME shipped artifact:
  maza-wallet-v1.1.0-mazatest.apk  sha256 013b964f272636bf6139e80b2b7081b3b2a0e3ce9bf0d20917285ca58a1b9567

## 1. Test suite (full offline suite at master)

$ date -u
Mon Nov 16 20:38:14 UTC 2026
$ python3 -m unittest discover -s tests
Ran 213 tests in 98.297s

OK (skipped=4)
(4 skips = electrumx-integration tests that run only with the pinned e-x tree installed)

## 2. Shipped APK: build linkage + credential scan

Source-to-APK linkage:

$ source state: master + this changeset (MainActivity.java DEFAULT_URL =
  https://mazatest.sami-host.me, token field EMPTY, no DEFAULT_TOKEN
  constant anywhere; release.properties versionCode=3 versionName=1.1.0)
$ bash android/build-apk.sh --release /root/maza-builds/maza-wallet-v1.1.0-mazatest.apk
[1/6] crypto selftest gate: PASS (19 vector checks, desktop JVM)
[2/6] aapt2 / [3/6] resource link / [4/6] javac / [5/6] d8
[6/6] apksigner
SIGNED OK: /root/maza-builds/maza-wallet-v1.1.0-mazatest.apk (271316 bytes, versionCode=3 versionName=1.1.0)
Signer #1 certificate SHA-256 digest: 59b2f5e0948d5de1628651db93d300d8740185d9fb4c2a5a213789b8fef804b5
$ sha256sum /root/maza-builds/maza-wallet-v1.1.0-mazatest.apk
013b964f272636bf6139e80b2b7081b3b2a0e3ce9bf0d20917285ca58a1b9567

Credential scan of the shipped dex (results from `strings`-extracted
full-line matches, deduped; grep -c on the raw binary overcounts
"binary file matches", so every number below is a distinct-string count
inspected by eye):

$ unzip -p maza-wallet-v1.1.0-mazatest.apk classes.dex | strings | grep -cE "f7977f02434c4a2cc6566da792c081c2"
0   (the removed stale baked value: absent in any form)

$ unzip -p maza-wallet-v1.1.0-mazatest.apk classes.dex | strings | grep -cE "default_token|DEFAULT_TOKEN"
0   (the constant and its name are gone)

$ unzip -p maza-wallet-v1.1.0-mazatest.apk classes.dex | strings | grep -oE "^[0-9a-f]{32}$" | sort -u
(no output — zero standalone 32-hex strings, i.e. no token-length credential)

$ unzip -p maza-wallet-v1.1.0-mazatest.apk classes.dex | strings | grep -oE "^[0-9a-f]{64}$" | sort -u
(no output — zero standalone 64-hex strings)

$ unzip -p maza-wallet-v1.1.0-mazatest.apk classes.dex | strings | grep -oE "^[0-9a-f]{96,}$" | sort -u | awk '{print length($0)}'
128
128
(two 128-hex strings — attribution CORRECTED in review round 11: these are
the OFFICIAL BIP39 Trezor mnemonic-to-seed vectors, not BIP32 Test Vector 1:
PBKDF2-SHA512 seeds of the mnemonic "abandon abandon … about" —
  c55257c3… with passphrase "TREZOR"
  5eb00bbd… with empty passphrase
both embedded as verification anchors in the crypto SelfTest (source:
android/src/com/mazawallet/crypto/SelfTest.java:42 and :49, comparing
against the official Trezor-published values). Public spec constants,
not secrets.)

APK-WIDE SWEEP (all 14 zip members: AndroidManifest.xml, META-INF/
MANIFEST.MF + MAZARELE.RSA/.SF, classes.dex, 6 PNGs, res/raw/
bip39_english.txt, resources.arsc): the stale token literal is absent from
EVERY member; zero 32-hex/64-hex full-line strings in any member. The only
non-code, non-signature content is the public BIP39 English wordlist and
brand PNGs.

$ unzip -p maza-wallet-v1.1.0-mazatest.apk classes.dex | strings | grep -m1 mazatest
https://mazatest.sami-host.me
(the ONLY baked endpoint: the public TEST URL — user-editable in the app)

Note on the "96-character" shape raised in review: a 96-CHARACTER string is
the UI masking of a 32-char token (3 bullet bytes per char) and exists only
at runtime in the EditText — it cannot appear in a dex; the 96+-hex scan
above covers any stored literal of that length class and found only the two
documented spec constants.

CREDENTIAL HISTORY NOTE: the bench-edition source previously carried a
baked-in DEFAULT_TOKEN ("users never type it" era, when the only endpoint
was a private tailnet IP). It was REMOVED from MainActivity before this
build: the token field is now empty with a hint, typed per session,
memory-only. The stale baked value was itself dead — its md5 differs from
both the pre-rotation server token and the current one, and the server
token was rotated again before public exposure (old 401s, new 200s, see §4).

## 3. Live public endpoint (external host, public path)

$ date -u
Mon Nov 16 20:51:26 UTC 2026
$ curl -s -o /dev/null -w "%{http_code}\n" https://mazatest.sami-host.me/
200
$ curl -s -o /dev/null -w "%{http_code}\n" https://mazatest.sami-host.me/api/state
401
$ curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "Content-Type: application/json" -d '{"addresses":["..."]}' https://mazatest.sami-host.me/api/watch/import
401
$ echo | openssl s_client -connect mazatest.sami-host.me:443 -servername mazatest.sami-host.me -verify_hostname mazatest.sami-host.me -verify_return_error 2>/dev/null | grep -m1 "Verify return code"
Verify return code: 0 (ok)

## 4. Token rotation before public exposure

$ rotation executed 2026-11-16 ~12:0x PST on samihost: new random WB_TOKEN
  spliced into /etc/maza-wallet-bench.env (0600), unit restarted, then:
$ old-token /api/state -> 401   (revoked)
$ new-token /api/state -> 200   (accepted)
$ no-auth     /api/state -> 401 (gate intact)
New token delivered to Sami by Telegram DM (msg 67575); never posted in a
group chat; server-side copy kept only in the 0600 env file.

## 5. Related on-chain / device proofs (committed in-repo; SCOPE NOTE)

android/evidence/selfcustody-proof/PROOF.md — mainnet self-custody send
  (tx ce514b350d2c…cd4e confirmed; SIGNATURE VALID + LOW-S offline gate)
android/evidence/m21-unlock-reimport/PROOF.md — unlock-path re-import device
  proof (fresh unlock, no tab tap -> WATCH_IMPORT seq=5 imported=40 status=200)

SCOPE: those proofs were performed on EARLIER builds of the same source
line (debug/bench-signature builds, evidence committed alongside). The
v1.1.0 release artifact verified in THIS document (013b964f…) has not
itself sent mainnet funds; no on-chain result is claimed for it here.
