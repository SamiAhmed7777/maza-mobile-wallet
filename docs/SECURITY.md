# MAZA Android wallet - security assessment

Backlog item S-8; Phase 8 deliverable 10 of `docs/SPEC.md`. This document
consolidates the security work recorded in `DECISIONS.md` (D7, D8, D11),
`docs/SPEC-AUDIT.md` (Phase 4 matrix), and the committed evidence under
`android/evidence/`. It states what is implemented, what each control does and
does not protect against, and what remains open. It does not restate the
product requirements; those stay in `docs/SPEC.md`.

Assessment basis: master at `083a58a` plus the wave-2 changeset (UiTheme
app-wide light reskin + in-session auto-lock retune). Every claim below is
tied to a repo path that exists at that state, or to a named operator-side
instrument that is explicitly marked as outside the repo.

## 1. Scope

Assessed:

- The Android client under `android/src/com/mazawallet/` (MODE_PRIVATE seed
  storage, PIN lock, transaction construction and signing, HTTP client,
  manifest surface).
- The `walletbench` backend under `walletbench/` as deployed at the public TEST
  endpoint `mazatest.sami-host.me`.
- The two spending paths the API exposes, each scoped separately in section 7.

Not assessed / out of scope:

- The ElectrumX light-client plan (`indexer/`, `deploy/electrumx*`,
  `docs/electrumx/`). It is not the wallet's current backend, and its
  deployment is blocked on an open `txindex` decision recorded in
  `docs/SPEC-AUDIT.md` (Phase 6).
- The MazaCore daemon itself (`mazad`). Its wallet custody and RPC surface are
  upstream, not this repo; this assessment treats it as a trusted local
  component behind an authenticated RPC listener.
- iOS. Not implemented (DEFERRED in `docs/SPEC-AUDIT.md`, Phase 8 row).
- Physical supply-chain, OS-level compromise of a rooted device, and
  side-channel attacks against the platform crypto providers. Residual risk
  from these is acknowledged in section 9 rather than mitigated here.

Standing caveat (SPEC RULE 6): the wallet is mainnet-TESTED with capped funds,
not production-approved. Nothing in this document asserts production
readiness.

## 2. Architecture summary

Components and trust boundaries:

- Android client (`android/src/com/mazawallet/`): first-party Java, zero
  third-party libraries (proof: `docs/DEPENDENCY-LICENSES.md` section 1).
  `MainActivity` owns the UI, the session token, and the lock overlay;
  `SelfCustody` owns the BIP39 seed surface, key derivation, and signing;
  `crypto/` is a self-contained kit (Bip39, Bip32, Bip44Maza, Secp256k1,
  Ripemd160, Base58Check, Hex, TxBuilder, Pbkdf2, LockPolicy, SeedCryptAes,
  SelfTest); `SeedVault` and `PinGuard` are the two Android-bound storage
  shells.
- Backend (`walletbench/api.py`): single-file stdlib HTTP service behind a TLS
  reverse proxy (recipe: `deploy/PUBLIC-HOSTING.md`). It holds the bench
  address book, a watch-only address list, and one shared bearer token from
  the `WB_TOKEN` environment variable. It talks to `mazad` over local RPC
  (`walletbench/chain.py`, `WalletRPC`).
- Trust boundary 1: device to server, over HTTPS to
  `https://mazatest.sami-host.me` (default URL in
  `android/src/com/mazawallet/MainActivity.java:58`; the field stays
  user-editable). All application state crossing this boundary is public
  chain data plus a bearer token. Private keys and mnemonics never cross it
  (section 6.3).
- Trust boundary 2: app process to Android platform keystore. The AES key that
  wraps the seed is created and held by `AndroidKeyStore` and is
  non-exportable (`android/src/com/mazawallet/SeedVault.java:193-214`).

Data at rest on the device:

| Artifact | Location | Protection |
|---|---|---|
| BIP39 mnemonic | `getFilesDir()/selfcustody.seed` | `MZAE1` magic + AES-256-GCM envelope under a non-exportable AndroidKeyStore key (`SeedVault`, `crypto/SeedCryptAes`) |
| PIN verifier | SharedPreferences `maza`: `pin.salt`, `pin.iter`, `pin.hash` | App-private prefs; PBKDF2-HMAC-SHA512 verifier only, never the PIN (`PinGuard`) |
| Server URL | SharedPreferences `maza` | Not a secret |
| Server token | Process memory only | Never persisted (`MainActivity` field `token`; set to null on lock/logout, not zeroed - a Java String cannot be) |
| Receive/change indices | SharedPreferences `selfcustody` | Not secret |

## 3. Seed and key protection at rest (S-1)

### 3.1 Envelope format

`SeedVault` writes `"MZAE1"` followed by the `crypto/SeedCryptAes` envelope.
`SeedCryptAes` (`android/src/com/mazawallet/crypto/SeedCryptAes.java`) is
AES-256-GCM over `javax.crypto` only: 12-byte random IV per encryption,
128-bit authentication tag, wire format `[IV][ciphertext+tag]`. A fresh IV is
drawn from a `SecureRandom` on every call, so the deterministic-IV failure mode
does not apply.

### 3.2 Key custody

The data key is generated on demand under alias `maza_seed_wrap` with
`KeyGenParameterSpec`: AES, 256-bit, `PURPOSE_ENCRYPT | PURPOSE_DECRYPT`,
`BLOCK_MODE_GCM`, `ENCRYPTION_PADDING_NONE`
(`android/src/com/mazawallet/SeedVault.java:193-214`). The raw key bytes never
exist in the app's memory; the app holds only a `SecretKey` handle. A
non-exportable keystore key cannot be read out even by code running in the app
process on a device whose keystore is intact.

Not claimed: the key spec does not set `setUserAuthenticationRequired` or
`setInvalidatedByBiometricEnrollment`. The key is therefore usable whenever the
app process runs, and it is not cryptographically bound to the PIN or to device
unlock. The PIN is a UI gate over the app, not a key-derivation factor
(section 4, section 9).

### 3.3 Write path

`SeedVault.save` / `saveEncrypted`
(`android/src/com/mazawallet/SeedVault.java:102-156`) is atomic:

1. Reject anything that is not a structurally plausible BIP39 mnemonic
   (12/15/18/21/24 words, each lowercase a-z) before touching disk.
2. Serialize all writes on a process-wide `WRITE_LOCK`, so two writers cannot
   share an inode.
3. Stage into a uniquely named `selfcustody.seed.<uuid>.tmp`, `flush()`,
   `FileDescriptor.sync()`, close, then `renameTo` the destination (POSIX
   rename within one directory is atomic).
4. Best-effort directory fsync so the rename survives sudden power loss.
5. On any failure the destination file is left untouched - the code deletes
   the staging file, never the last valid seed. Failure is normalized to a
   checked `IOException` with a content-free message.

Stale `.tmp` leftovers from a previously killed writer are swept at the start
of each write, under the same lock, so a crash cannot accumulate plaintext
staging files. The staging file contains the ciphertext envelope, not
plaintext.

### 3.4 Legacy plaintext migration

`SeedVault.loadOrMigrate` (`:51-89`) accepts two shapes:

- `MZAE1...`: decrypt; a wrong key, tamper, or truncation returns `""` (no seed
  served, nothing fabricated). A decrypting envelope must still pass the
  structural mnemonic check before it is served.
- No magic: treated as a legacy plaintext mnemonic. It is validated, then
  re-written through the encrypted path. Until that rename lands the plaintext
  file is still on disk; after it lands the plaintext is gone (the new file is
  a rename over it, so no plaintext interim copy exists).
- A failed migration is deferred, not fatal: the seed keeps working from
  memory for the session, one count-only `Log.w` records the deferral (never
  seed content), and every later read retries. Plaintext-at-rest therefore
  cannot continue silently past the first read that can encrypt.

### 3.5 Evidence status (state this precisely)

- Envelope math is vector-/property-pinned in the desktop self-test that gates
  every build (stage [1/6] of `android/build-apk.sh`; runner
  `android/selftest.sh`): round trip, fresh IV per encryption, tamper
  rejected, wrong key rejected - `android/evidence/s2a-pin/selftest.txt` lines
  30-35, 49/49 checks pass, `android/evidence/s2a-pin/build.txt` records
  `SIGNED OK`.
- The keystore-backed read path ran on device, though no artifact isolates it:
  the S-2b run installed a build that includes S-1 (`8cf4dc6`) over existing
  app data and opened the WALLET tab (`android/evidence/s2b-pin/PROOF.md`,
  `android/evidence/s2b-pin/s1-security-armed.png`), and building that tab
  derives the receive address
  from the on-device seed through `SeedVault.loadOrMigrate` (`SelfCustody`
  constructor -> `renderWallet` -> `updateAddress` -> `keyAt` ->
  `readSeed`). Since the seed file on that device predated S-1, the run is also
  the only available observation of the migration path - but the package
  records tab and PIN behavior, not the file's before/after bytes.
  `android/evidence/m21-unlock-reimport/PROOF.md` predates S-1 (`bea687a`) and
  documents the plaintext read path only; it is not evidence for the vault.
- NOT proven on device, and not claimed here: a dedicated proof that a
  previously plaintext seed file is migrated through a real `AndroidKeyStore`
  and survives an app restart as ciphertext. The operational backlog records
  this as S-1's remaining acceptance criterion ("desktop selftest covers the
  envelope math only, never the Keystore path"). Treat S-1 as
  implemented-and-unit-proven, device-proof-pending.

## 4. PIN lock and auto-lock (S-2a code, S-2b-ii biometric code, S-2b device proofs)

### 4.1 Verifier storage

`PinGuard` (`android/src/com/mazawallet/PinGuard.java`) stores
`pin.salt` (16 SecureRandom bytes, hex), `pin.iter` (int), `pin.hash` (32
bytes, hex) in `MODE_PRIVATE` SharedPreferences. The PIN is never stored and
never logged; the attempt `char[]` is zeroed on every exit path, including the
failure path (`:159-176`). Comparison is `MessageDigest.isEqual` (constant
time).

Derivation: PBKDF2-HMAC-SHA512 via `crypto/Pbkdf2` (`:32-58`), 210,000
iterations by default (`PinGuard:64`), 16-byte salt, 32-byte verifier. The
stored iteration count is used at verify time, so the cost can be raised later
without invalidating existing verifiers. The primitive is vector-pinned in
`crypto/SelfTest` against the official BIP39 TREZOR seed (itself a PBKDF2
output) plus hashlib/OpenSSL-cross-derived anchors
(`android/evidence/s2a-pin/PROOF.md`,
`android/evidence/s2a-pin/anchors-derived.txt`).

### 4.2 Fail-closed verifier states

Three states (`PinGuard:85-110`):

- ABSENT: no `pin.*` key at all. Gate inert; the app behaves as it did before
  the PIN existed.
- VALID: salt is 16 bytes, hash is 32 bytes, iteration count is an int in
  1..10,000,000.
- CORRUPT: anything else, including a partial store, bad hex, wrong lengths,
  wrong types, or an out-of-range iteration count. CORRUPT fail-CLOSES: the
  gate stays permanently engaged and nothing verifies (`gateNeeded` returns
  true). A damaged store can therefore never read as "no PIN set". Recovery
  is an app-data reset; the seed is independent of this store (it is protected
  by its own keystore envelope).

### 4.3 Lock policy

`crypto/LockPolicy` is pure Java with an injected clock, so every transition is
pinned by fake-clock unit checks in the build gate (20 of the 49 checks are
lock-transition checks).

- Fresh session with a stored verifier starts LOCKED
  (`LockPolicy.forSession`), so authentication is required at every process
  start, not only after inactivity.
- Inactivity: locked when `now - lastActivity >= autolockMs` (default 300000
  ms = 5 min, `PinGuard:65`). The decision is evaluated LAZILY inside
  `isLocked` at every gate check, so a missed timer tick cannot leave the gate
  open; the 10-second tick only raises the cover UI.
- Background/resume: backgrounded for >= `autolockMs` locks on resume; the
  bracket runs on every resume, including the Connect screen.
- Activity means user touch (`onActivity`), never a background poll; a tap
  arriving after an already-elapsed deadline resolves the lock BEFORE the touch
  extends the deadline.
- Clock is `SystemClock.elapsedRealtime()` (monotonic), so wall-clock changes
  cannot stretch or shorten a security window.

### 4.4 Wrong-PIN throttle

After 5 consecutive failures a 30-second window opens; each further failure
doubles it, capped at 15 minutes (`LockPolicy:30-32`, `:108-128`). A THROTTLED
attempt is refused BEFORE any PBKDF2 work: `PinGuard.verifyAttempt` checks
`throttleUntilMs()` first, synchronized and with a single clock read. The
failure streak resets only on an accepted verify and survives auto-lock, so
"four wrong, wait for auto-lock, repeat" does not dodge the backoff.

Gate points: the WALLET tab (the seed surface, including its send card) and
the self-custody send/create/import handlers via `Host.gateOpen()`
(`SelfCustody.doSend`, `:608`; `MainActivity.gateOpen`, `:485`). Read-only
surfaces (balance, receive address, QR, history) are not gated, by design -
the spec gates spending and unlocking, not viewing.

### 4.5 Biometric unlock (S-2b-ii code, 2026-11-17)

Platform `BiometricPrompt` on the lock cover, wired through a pure-Java
decision table (`crypto/BiometricPolicy`, selftest-pinned): the offer
requires API >= 29 (the `BiometricManager` capability probe is an API-29
class; API 28 devices, BlueStacks included, get the graceful PIN-only
path), a fresh platform probe at every cover show (hardware present +
enrolled + usable), and a VALID verifier store. Success routes through
`PinGuard.unlockViaBiometric()` — synchronized, fail-closed on a corrupt
store — and lands on the SAME unlock path as an accepted PIN
(`MainActivity.completeUnlock`). Error policy (`DECISIONS.md` D12):
biometric failures never advance the PIN wrong-attempt streak (the device
throttles biometrics itself; the backoff defends PIN brute-force), user
cancellations and sensor errors leave the cover untouched, and a lockout
switches the offer off for the rest of the session. The manifest carries
`android.permission.USE_BIOMETRIC` (normal level) because platform
`BiometricPrompt.authenticate()` requires it. Device evidence outstanding:
BlueStacks has no biometric hardware, so a device pass can only prove the
graceful-absence path (cover renders PIN-only, exactly as before this
change).

### 4.6 Device proof

`android/evidence/s2b-pin/PROOF.md` (48 files, `SHA256SUMS` manifest,
`android/evidence/s2b-pin/transcript.md`): fresh-session locked start with zero
taps, the wrong-PIN path, throttle engagement and doubling window render, a
correct PIN refused without
evaluation during a live window (single-script, self-authenticating chain),
acceptance after window drain, inactivity lock (6 minutes of in-image device
clocks between an unlocked and a locked frame), and background-return lock
proven as one chain including a captured launcher transition. That package
discloses its own limits: the 900-second cap VALUE rests on the desktop-pinned
constants, not on a rendered near-cap message.

## 5. Token handling and authentication

Client side:

- The token is typed once per session into a masked field
  (`TYPE_TEXT_VARIATION_PASSWORD`, `MainActivity:208`) and held in a process
  field only (`MainActivity:88`). It is set to null on lock-out and on
  returning to the Connect screen (`:740`, `:184`). No token is written to
  SharedPreferences; only the server URL is persisted.
- No default and no baked-in token: `MainActivity:59` and `:137-141` state
  the bench-edition token was removed when the endpoint went public. The
  release APK's dex was scanned for token material during the public-endpoint
  change (`deploy/PUBLIC-HOSTING.md` section 4 records the verification, not
  just the intent).
- The token never rides in a URL. `Api.http` attaches it only as
  `Authorization: Bearer` (`android/src/com/mazawallet/Api.java:59-61`), and
  `tests/test_walletbench.py:156` (`test_query_param_token_is_rejected`) pins
  the server regression: `GET /api/state?t=<valid token>` must return 401.

Server side (`walletbench/api.py`):

- One shared token from `WB_TOKEN`; the process stores only its SHA-256
  digest (`_token_digest`). Every comparison is `hmac.compare_digest` on
  digests (`:299-304` for requests, `:753` for unlock), so a timing oracle over
  the token is not available.
- Two auth shapes: an `HttpOnly; SameSite=Strict` cookie for the web UI, and
  `Authorization: Bearer` for the Android client. Query-param auth does not
  exist.
- Every `/api/*` route except `/api/unlock` requires auth. `/api/unlock`
  exchanges the token for the cookie and returns 401 on mismatch.
- Rotation procedure exists and is atomic: `deploy/PUBLIC-HOSTING.md` section 4
  rewrites `/etc/maza-wallet-bench.env` with mode 0600 via a unique temp file
  plus `os.replace`, restarts the unit, and verifies that the OLD token now
  returns 401 while the new one passes `/api/state`.

Residual: a Java `String` cannot be zeroed, so the token is recoverable from a
process memory dump or a heap profile while a session is connected; and there
is one shared token for all testers, with no per-user identity, revocation, or
audit trail beyond request lines (`deploy/PUBLIC-HOSTING.md`, "Security posture
of the test endpoint": access logs carry request lines and IPs, never
headers, and Caddy adds no rate limiting). Both are recorded in section 9.

## 6. Threat model

### 6.1 Device theft or loss

Assets at risk: the mnemonic, the derived keys, and (for the custodial bench
account) the balance visible to the app.

Controls:

- The mnemonic on disk is ciphertext under a non-exportable AndroidKeyStore
  key (section 3). Copying `selfcustody.seed` off the device yields a
  `MZAE1` blob that is useless without the keystore entry, which does not
  migrate to another device or another app UID.
- `android:allowBackup="false"` (`android/AndroidManifest.xml`) keeps app
  files out of ADB backup and cloud backup, so the blob is not swept up by a
  backup path.
- The PIN gate covers the WALLET tab and every self-custody spend, starts
  engaged at process start, re-engages after 5 minutes idle or after a
  >= 5-minute background, and throttles guessing with a doubling backoff
  (section 4). The device proof above shows these paths on-device.
- The app holds no other persistent secret. Receive/change indices are not
  secret.

What this does not stop, stated plainly: an attacker who can run code as the
app UID on a rooted or otherwise compromised device can ask the keystore to
decrypt, because the key is bound to the app, not to the PIN and not to an
authentication event. The PIN verifier itself is an offline-guessable artifact
for such an attacker (16-byte salt, 210k PBKDF2-HMAC-SHA512, but a 4-digit
numeric PIN is a 10,000-entry keyspace). The PIN is a screen-lock-class
control; the keystore is the root of seed secrecy. Both statements match
`DECISIONS.md` D11's recorded residual.

### 6.2 Endpoint compromise (`mazatest.sami-host.me`)

Public TEST front door: Caddy terminating TLS with an ACME certificate, then
`walletbench` behind it. There is no authentication at the proxy layer; all
authorization is the single bearer token checked in the service
(`deploy/PUBLIC-HOSTING.md` sections 3-4).

If the host or the token is compromised, an attacker can:

- Read and spend the CUSTODIAL bench account. The bench spends server-side
  under a 50 MAZA per-send cap (`walletbench/config.py:27`, enforced in
  `walletbench/api.py` `_send` at `:828`), so exposure is bounded per
  transaction but not
  in aggregate; the balance is play money, ~49 MAZA (section 9).
- Read the watch book: the address set a phone imported, plus its UTXOs and
  history (`/api/watch/utxos`, `/api/watch/history`). That is public chain
  data, but it is linkable to a tester's wallet.
- Serve false balances, false history, or a false UTXO set to any client.
- Refuse service (denial of broadcast, or a 401 wall).

If the host is compromised, an attacker CANNOT obtain seeds or private keys,
because none are ever sent (section 6.3), and CANNOT sign for a self-custody
wallet. Rotating the token ends the attacker's API access; the procedure is in
`deploy/PUBLIC-HOSTING.md` section 4.

### 6.3 Malicious or compromised server, self-custody path

This section is about the `watch` / `broadcast` routes only; the custodial
`/api/send` route is scoped separately in section 7.

Server role: watch addresses, report UTXOs and history, and relay signed bytes
(`POST /api/broadcast` -> `chain.sendraw_only` -> `sendrawtransaction`,
`walletbench/chain.py:104-110`). The server does not verify signatures: it
relays whatever valid-shaped hex it receives
(`walletbench/api.py:536-560`). That is safe only because construction and
signing never leave the device - see `docs/SPEC-AUDIT.md` row 4.8, which states
this accurately.

Client-side properties that hold against a hostile server:

- Keys are derived on device from the locally stored seed
  (`SelfCustody.account`, `keyAt`, `keyForAddress`); the server never sees a
  seed, a private key, or a WIF.
- The client builds the transaction itself (`crypto/TxBuilder`: version-1
  P2PKH, SIGHASH_ALL, RFC6979 deterministic nonces, DER low-S), from inputs it
  selects (largest-first, confirmed only) among the server-reported UTXOs.
- An input whose address the client cannot sign for is refused outright
  ("Cannot sign for watched address"), so a hostile server cannot induce a
  signature over an output the wallet does not own.
- There is no raw-transaction import path. The app cannot be handed a
  pre-built transaction to sign, which is the structural protection recorded
  in `docs/SPEC-AUDIT.md` row 4.10.
- The change address is imported before broadcast, and a failed import aborts
  the send ("Change-address import failed; not broadcasting",
  `SelfCustody.sendFlow`), so a server cannot strand change by dropping the
  import.
- Amounts and addresses are validated on device before signing: positive
  finite amount, Base58Check decode with 21-byte payload and the MAZA P2PKH
  version byte (`SelfCustody.doSend`), so a hostile server cannot redirect a
  payment to a malformed address.
- Independent verification instrument: `tools/txverify.py` re-checks a raw
  transaction offline (SIGHASH_ALL + ECDSA) and was validated against a real
  MazaCore-signed mainnet transaction; the phone-signed mainnet send is
  recorded in `android/evidence/selfcustody-proof/PROOF.md` with
  `android/evidence/selfcustody-proof/txverify-output.txt`.

Limits, stated plainly: the server can lie about balance and history, can
withhold a broadcast, and can correlate the address set it is asked to watch.
It cannot steal funds from a self-custody wallet, because spending requires a
signature it cannot produce. It CAN observe which addresses belong to one
client and when that client is online (privacy, not custody).

The fee and the destination outputs are set by the client (`FEE_SATS = 10000` in
`SelfCustody`), so a hostile server cannot inflate the fee or substitute a
recipient: it can only misreport which UTXOs exist.

### 6.4 Network-level attacks

- Transport: default endpoint is HTTPS (`MainActivity:58`), certificate
  obtained by the proxy via ACME; TLS and hostname verification were probed
  from an external machine (`deploy/PUBLIC-HOSTING.md` section 5, live
  verification block).
- There is no certificate pinning. A user-installed CA, a hostile network with
  a mis-issued certificate, or a proxy the user configures can observe and
  modify traffic. If that happens while a token is in use, the token is
  exposed (it is a bearer credential in a header) and the server's responses
  can be forged - which for the self-custody path means false balance/history
  and refused broadcasts, not key compromise.
- The manifest sets `android:usesCleartextTraffic="true"`
  (`android/AndroidManifest.xml`). The default URL is HTTPS, but a user who
  types an `http://` URL (the bench-era workflow did) sends the bearer token in
  cleartext. This is a real residual and is listed in section 9.
- Network interruption and error handling are NOT hardened yet: watch import
  retries 3 times with linear backoff (`SelfCustody.ensureWatchImported`), the
  HTTP client uses fixed 10 s connect / 15 s read timeouts (`Api.java:55-56`),
  and error copy is a catch-all. Uniform retry, timeout/401/offline copy, and
  no-silent-empty-state behavior are backlog item S-5, pending.
- No inbound network surface on the device: the app opens no listening socket
  and requests only `android.permission.INTERNET` and the normal-level
  `android.permission.USE_BIOMETRIC` (S-2b-ii: platform
  `BiometricPrompt.authenticate()` requires it; auto-granted, no runtime
  prompt) — both from `android/AndroidManifest.xml`, verified by the
  operator-side release battery (section 8, exact two-permission set).

### 6.5 Accidental key exposure and logging

- Seeds and keys are never logged. The only log call in the security path is
  the count-only migration deferral in `SeedVault:86`. Server logging is
  count-only for watch imports and book reconciliation
  (`WATCH_IMPORT seq=N imported=C status=S`, `BOOK_RECONCILE ...`), never
  addresses, tokens, or txids (`walletbench/api.py` module docstring).
- The mnemonic is displayed exactly once at creation, never re-displayed, and
  never placed on the clipboard or in an Intent (`SelfCustody` header
  contract). The clipboard is used only for the receive address
  (`MainActivity.copyAddress`).
- There is no `FLAG_SECURE` on the activity, so screenshots and the recents
  thumbnail can capture wallet screens. This was load-bearing for the device
  evidence workflow (all proofs are screenshots) and is listed as an accepted
  risk, not an oversight.

### 6.5 Scanned QR content (M8a policy, shipped 2026-11-17)

Scanning attacks target the spend path: a malicious or swapped QR must not
be able to redirect a payment anywhere other than an address the user
could have typed. The controls (all in
`android/src/com/mazawallet/crypto/ScanOrigin.java`, desktop-tested by
`SelfTest.scanOriginChecks`):

- Scanned payload text may only ever become a MAZA mainnet P2PKH address,
  validated with the SAME base58check contract as typed addresses
  (21-byte payload, version 50) — the M8b scanner cannot insert anything
  into the SEND field that the typed path would reject.
- URLs (http/https/www) and ANY foreign URI scheme are rejected outright:
  scanned content is never fetched, opened, or parsed as a link.
- `maza:` URI parameters fail-closed until M9 ships the amount contract.
- Length is capped before decode work; multi-line content rejected;
  rejection reasons are user-safe and never echo the payload.
- The decoder itself is a sha256-pinned vendored jar enforced by the
  build (see DECISIONS D13 / docs/DEPENDENCY-LICENSES.md §1).
- CAMERA permission is NOT declared yet — it arrives with the M8b camera
  surface and the operator beta battery's permission audit is widened in
  the same change (a declared-but-unused dangerous permission is worse
  than a late permission).

## 7. Spending-path scope (do not generalize these claims)

| Path | Route | Who signs | Caps | Server sees |
|---|---|---|---|---|
| Legacy custodial bench | `POST /api/send` | Server, with the node wallet | 50 MAZA per send (`config.MAX_SEND`), flat 0.0001 MAZA fee, inputs restricted to bench-book addresses | Everything: recipient, amount, change |
| Self-custody | `POST /api/broadcast` | Client, on device | No server-side amount cap; client-fixed 10000 sat fee | Signed transaction bytes only, plus the watched address set |

Consequences that must not be blurred:

- "The server never signs" is TRUE for the watch/broadcast path and FALSE for
  `/api/send`, which exists precisely to spend the custodial play funds.
- The 50 MAZA cap is a property of `/api/send` only. It is not a wallet-wide
  limit and it does not bound a self-custody spend.
- "Custodial infrastructure is not implemented" (SPEC Phase 4) is true of the
  wallet. `/api/send` is a separate test harness for Sami's play funds, labeled
  as custodial in `DECISIONS.md` D7, and is the path ElectrumX will replace.
- UTXO-level isolation for the bench is a construction rule (inputs selected
  from bench addresses' own unspent outputs, change back to a bench-owned
  address), not account-level isolation: Bitcoin-style accounts are bookkeeping
  labels. `DECISIONS.md` D7 and D10 record the failure modes this caused live.

## 8. Controls inventory and how each is verified

| Control | Implementation | Verification |
|---|---|---|
| Seed encrypted at rest | `SeedVault`, `crypto/SeedCryptAes` | Build-gate self-test (envelope checks, `android/evidence/s2a-pin/selftest.txt`); device Keystore/migration proof PENDING |
| Seed write atomicity | unique tmp + fsync + rename + dir fsync, under a process lock | Code review of `SeedVault:118-156`; no dedicated failure-injection test |
| Legacy plaintext migration | validate then encrypt in place; defer + retry on failure | Code review; migration proof PENDING (section 3.5) |
| PIN never stored | PBKDF2 verifier only, `char[]` zeroed | Self-test PBKDF2 anchors; `android/evidence/s2a-pin/PROOF.md` |
| Constant-time compare | `MessageDigest.isEqual` (`PinGuard:168`) | Code review; not timing-measured |
| Fail-closed verifier store | ABSENT/VALID/CORRUPT classifier | Self-test lock checks; judge-hardened (`DECISIONS.md` D11) |
| Fresh-session lock | `LockPolicy.forSession` | Fake-clock self-test + device proof P1 |
| Inactivity auto-lock | lazy `isLocked` + 10 s cover tick | Fake-clock self-test + device proof P4a |
| Background-return lock | `onBackground`/`onResume` bracket | Fake-clock self-test + device proof P4b |
| Wrong-PIN throttle | 5 fails -> 30 s doubling, cap 15 min, pre-hash refusal | Fake-clock self-test + device proof P3 (cap value desktop-pinned only) |
| Biometric unlock offer | pure `BiometricPolicy` decision (API tier + fresh platform probe + VALID verifier) at every cover show | Self-test biometric decision-table rows + `tests/test_biometric_wiring.py`; device pass (graceful-absence) pending |
| Biometric success seam | `PinGuard.unlockViaBiometric()` fail-closes on a corrupt store; same landing as an accepted PIN | Source-contract test + self-test `acceptUnlock` scenarios |
| Token not in APK | no default token; rotated at public exposure | `MainActivity:137-141`; `deploy/PUBLIC-HOSTING.md` section 4 |
| Token not in URLs | Bearer header only | `Api.java:59-61`; `tests/test_walletbench.py:156` |
| Server auth | digest + `hmac.compare_digest`, all `/api/*` except unlock | `walletbench/api.py:289-310`, `:751-760`; suite |
| Client-side signing | `crypto/TxBuilder` + first-party crypto kit | Official-vector self-test; mainnet-confirmed tx + offline `tools/txverify.py` (`android/evidence/selfcustody-proof/PROOF.md`) |
| No pre-built-tx signing path | no raw/import transaction entry point | `docs/SPEC-AUDIT.md` row 4.10 |
| Address/amount validation | Base58Check + version byte, finite positive amount | `SelfCustody.doSend`; suite (`walletbench` side: `isfinite`, own-address refusal) |
| Manifest minimization | INTERNET only, `allowBackup="false"`, no `debuggable` | Operator-side release battery, check 4 |
| No dangerous APIs | no WebView/JS bridge/DexClassLoader/Runtime.exec/storage perms | Operator-side release battery, check 5 |
| No key material in logs | count-only deferral line; grep-verified server logs | Code review; `android/evidence/m5-release-build/secret-scan.txt` |

Release battery: `/root/.hermes/skills/maza-mobile-wallet/scripts/beta-gate.sh`
is an OPERATOR-SIDE script and is not a repo artifact. It
runs 10 checks (APK integrity and size, `apksigner verify`, APK contents/no native
libs, manifest permissions + `allowBackup` + no `debuggable`, dangerous-API
grep, endpoint allowlist for `mazatest.sami-host.me`, secret sweep, Bearer
shape, manifest version/SDK attributes, evidence directory present). Zero
`FAIL:` lines is the release condition. It is not reproducible from a clone of
this repository alone.

Signing identity: the bench/debug line is signed with the committed
`android/debug.keystore` (`CN=mazabench`, generated by `android/build-apk.sh`
if absent). The release line (`bash android/build-apk.sh --release`) uses a
separate `mazarelease` keystore that lives off-repo at
`~/.maza-wallet/release.keystore` with a mode-0600 password file, versions from
`android/release.properties`, and the two lines cannot install over each other
because the keys differ (`android/evidence/m5-release-build/PROOF.md`).

## 9. Accepted risks

| # | Risk | Why it is accepted now | Owner / exit |
|---|---|---|---|
| A1 | Bench builds are signed with a committed debug keystore | The bench line exists to get an installable APK onto a test device; anyone with the repo can rebuild or re-sign it, so it is not a distribution artifact. Release builds use the separate off-repo `mazarelease` key | Bench-only; distribution stays release-signed |
| A2 | Custodial bench account holds ~49 MAZA of play funds, spendable by any token holder | Test harness for operator-directed play testing; UTXO-scoped sends and a 50 MAZA per-send cap bound each transaction; funds are Sami-authorized play money | Ends when the ElectrumX backend replaces the bench |
| A3 | BIP39 English wordlist license provenance is recorded but not legally cleared | The file is byte-identical to upstream bitcoin/bips and trezor/python-mnemonic (sha256 pinned in `docs/DEPENDENCY-LICENSES.md` section 1), but no per-file grant exists; a formal data-level grant determination is an owner decision | Recorded open in the dependency report; not decided here |
| A4 | Biometric unlock: CODE LANDED (S-2b-ii, 2026-11-17); device proof pending | `BiometricPrompt` on the lock overlay with graceful PIN-only fallback ships behind a pure decision table (API >= 29 offer, VALID-verifier fail-closed seam, D12 error policy); BlueStacks has no biometric hardware, so the device pass can only prove the absence path | Device-lane item S-2b-ii evidence |
| A5 | Network/error hardening: CODE LANDED (wave 3 - Net retry table, spend never retried, error copy); testnet mode (S-6) pending | Retry is uniform across the whole surface now; the airplane-mode DEVICE test is outstanding; all device testing so far used mainnet under the capped harness | Backlog items: airplane-mode run, S-6 |
| A6 | Single shared bearer token, no per-user accounts, no revocation list | Test-scale deployment with a handful of testers; the token is delivered privately and rotated atomically | Ends with per-user auth or the ElectrumX path (which uses no token) |
| A7 | The watch book is a single server-side list shared by all clients | One operator, one tester group; the data is public chain data (addresses, UTXOs, history) | Multi-tenant deployment would need per-client scoping |
| A8 | `usesCleartextTraffic` was `true` through the bench era (FIXED 2026-11-17, commit 51ab252: now explicitly `false` and audited by the release battery) | The bench-era flow pointed at an `http://` endpoint; the shipped default is HTTPS and the field is user-editable to `http://`, which would expose the bearer token | Residual: the CONNECT field accepts any URL a user types; the battery now FAILs the build if the manifest flag regresses to `true` |
| A9 | No certificate pinning | Pinning an ACME-rotated cert on a TEST endpoint would add fragility; TLS + hostname verification is the control | Revisit before any production endpoint |
| A10 | No app-wide `FLAG_SECURE`: screenshots and recents thumbnails can capture wallet screens | Needed for the device-evidence workflow that produced the committed proofs; no seed is on screen except the one-time creation view and the PIN-gated re-show dialog (S-4, landed 2026-11-17, holds FLAG_SECURE for the dialog lifetime and scrubs on dismiss) | Revisit app-wide with the wave-2 UX pass |
| A11 | PIN verifier is in app-private prefs, not Keystore-wrapped; failure streak and backoff counters are memory-only, so a process restart clears them | The verifier is not the root of secrecy (the seed has its own keystore envelope); a restart already re-locks the app and re-arms at 5 fails | Recorded in `DECISIONS.md` D11; persisted counters if the threat model demands |
| A12 | S-1 has no device proof of the keystore decrypt/migration path | The envelope math is build-gate pinned and the read path runs on device, but no artifact isolates the Keystore step | Backlog S-1 remaining criterion |
| A13 | `MainActivity` is `android:exported="true"` | Required for a launcher activity; it exposes no IPC surface (no intent extras consumed for wallet actions, no services, no providers) | Keep it that way; audit on any new component |

## 10. Open items

Security-relevant work not yet done, in the order the spec's staged plan
expects (`docs/SPEC-AUDIT.md`, "Implementation order"):

1. S-1 device proof: migrate a real plaintext seed through `AndroidKeyStore`
   and prove restart persistence on a device.
2. S-2b part 2: biometric unlock where supported, with a graceful PIN-only
   fallback where no sensor exists. CODE LANDED 2026-11-17 (S-2b-ii:
   `crypto/BiometricPolicy` + PinGuard seam + overlay wiring, D12); the
   device pass remains (BlueStacks has no fingerprint hardware, so device
   evidence can only cover the absence path — cover renders PIN-only).
3. S-4 settings/wallet management: LANDED 2026-11-17 (auth-gated seed
   re-show behind the PIN with FLAG_SECURE, wipe wallet with double
   confirmation + typed acknowledgement + current-PIN re-verification
   immediately before destruction + best-effort Keystore wrap-alias removal,
   auto-lock delay editor applying immediately (in-session retune via
   PinGuard.retuneAutolockMs, landed wave 2) and theme control).
   Device proofs pending.
4. S-5 network/error hardening: uniform retry with backoff, timeout/401/offline
   copy, no silent empty states, and a decision on cleartext traffic.
5. S-6 testnet mode: endpoint and address-version switch so controlled-environment
   testing stops touching mainnet.
6. M8 QR camera scanning (a camera permission and a decoder path are new
   attack surface; assess when it lands).
7. ElectrumX backend cutover, which removes the shared-token bench from the
   wallet's path. Blocked on the `txindex` decision recorded in
   `docs/SPEC-AUDIT.md` (Phase 6).
8. Seed re-display policy: today the mnemonic is shown once at creation and
   via the S-4 authenticated re-show (landed 2026-11-17: PIN-gated, FLAG_SECURE
   held for the dialog lifetime, scrub on dismiss), so the earlier usability
   gap is closed; the remaining piece is only its device proof.

Decision-gate note: product decisions (public endpoint exposure, distribution
width, fee-rate policy, confirmation expectations) are not agent-decidable.
Per the current delegation they route to Payu; this document records technical
state only and decides nothing.

## 11. Reproducing the checks in this document

```bash
# walletbench suite (docs-only changes do not affect it; baseline confirmed)
python3 -m unittest discover -s tests
# -> Ran 216 tests ... OK (skipped=4)

# the specific auth-shape regression cited in section 5
python3 -m unittest tests.test_walletbench -k query_param   # test_query_param_token_is_rejected

# build-gate crypto self-test (stage 1 of a build; runs standalone too)
bash android/selftest.sh
# -> ALL 49 CHECKS PASSED
```

Every repo path cited above was checked for existence at the assessment
commit; the operator-side battery
(`/root/.hermes/skills/maza-mobile-wallet/scripts/beta-gate.sh`) and the
off-repo release keystore are named as external deliberately.

## 12. Cross-references

- `docs/SPEC.md` - requirements this assessment answers (Phase 4, Phase 8
  deliverable 10).
- `docs/SPEC-AUDIT.md` - per-item compliance matrix and evidence pointers.
- `DECISIONS.md` - D7 (bench edition and its cap), D8 (self-custody mode),
  D9/D10 (bench book loss and funding-flow reconciliation), D11 (PIN lock,
  including the accepted residuals restated here).
- `docs/DEPENDENCY-LICENSES.md` - zero-third-party inventory and wordlist
  provenance.
- `android/evidence/` - committed proofs: `s2a-pin/`, `s2b-pin/`,
  `selfcustody-proof/`, `m21-unlock-reimport/`, `m5-release-build/`,
  `selftest-gate/`.
- `deploy/PUBLIC-HOSTING.md` - public endpoint recipe, token rotation, TLS and
  external probes.
