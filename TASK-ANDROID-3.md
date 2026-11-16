# TASK-ANDROID-3: Self-custody seed-phrase wallet (BIP39 + local signing)

You are adding REAL self-custody to the MAZA Wallet Android app: the app
generates/imports a BIP39 mnemonic, derives MAZA keys locally, builds and
SIGNS transactions on-device, and the server only watches addresses and
broadcasts signed bytes. The server NEVER sees a key.

## Ground rules (non-negotiable)
1. ASCII only. Any non-ASCII glyph goes in as a unicode escape (\u2192 etc).
2. All crypto values below are VECTOR-VERIFIED. Your implementations must
   reproduce them EXACTLY. If one mismatches, your code is wrong — fix your
   code, never "adjust" an expected value.
3. No external crypto libraries: pure Java (BigInteger, javax.crypto
   PBKDF2WithHmacSHA512, Mac HmacSHA512/HmacSHA256, MessageDigest SHA-256,
   java.security.SecureRandom for entropy).
4. Derivation path: m/44'/13'/0'/0/i for receiving (i=0,1,2,...) and
   m/44'/13'/0'/1/i for change. Coin type 13 (SLIP-44 MAZA). P2PKH only,
   compressed pubkeys. Address version byte 50 (0x32) -> "M..." base58.
   WIF version byte 224 (0xE0) with 0x01 compressed suffix.
5. Everything consensus-related lives in
   android/src/com/mazawallet/crypto/ as separate classes:
   - Secp256k1.java   (point math + ECDSA sign/verify, RFC6979 nonce, low-S)
   - Base58Check.java (encode + decode, double-SHA256 checksum)
   - Bip39.java       (entropy->mnemonic->seed; wordlist from res/raw)
   - Bip32.java       (master key, CKDpriv hardened/softened, path parser)
   - Bip44Maza.java   (m/44'/13' derivation, MAZA address/WIF formatting)
   - TxBuilder.java   (legacy P2PKH tx build + SIGHASH_ALL sign)
   - SelfTest.java    (public static void main — prints PASS/FAIL per check)
6. SelfTest must ALSO run on desktop JVM (plain java, no android.*):
   every check self-contained, no Android deps.

## Anchor values (all independently verified against official vectors)

### BIP39 (official Trezor vectors; reference harness uses passphrase "TREZOR")
- mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
- seed(mnemonic, passphrase="TREZOR") =
  c55257c360c07c72029aebc1b53c05ed0362ada38ead3e3e9efa3708e53495531f09a6987599d18264c1e1c92f2cf141630c7a3c4ab7c81b2f001698e7463b04
- seed(mnemonic, passphrase="") =
  5eb00bbddcf069084889a8ab9155568165f5c453ccb85e70811aaed6f6da5fc19a5ac40b389cd370d086206dec8aa6c43daea6690f20ad3d8d48b2d2ce9e38e4
- mnemonic from entropy 00000000000000000000000000000000 = "abandon"*11 + " about" (checksum word about)
- mnemonic from entropy 7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f = "legal winner thank year wave sausage worth useful legal winner thank yellow"
- SelfTest: assert mnemonic_from_entropy for BOTH entropies above, and
  seed_from_mnemonic for BOTH seed vectors above. (Wordlist:
  android/res/raw/bip39_english.txt — 2048 lines, already in the repo.)

### BIP32 (official bitcoin/bips bip-0032.mediawiki Test Vector 1, seed = 000102030405060708090a0b0c0d0e0f)
- m       xprv = xprv9s21ZrQH143K3QTDL4LXw2F7HEK3wJUD2nW2nRk4stbPy6cq3jPPqjiChkVvvNKmPGJxWUtg6LnF5kejMRNNU3TGtRBeJgk33yuGBxrMPHi
- m/0'    xprv = xprv9uHRZZhk6KAJC1avXpDAp4MDc3sQKNxDiPvvkX8Br5ngLNv1TxvUxt4cV1rGL5hj6KCesnDYUhd7oWgT11eZG7XnxHrnYeSvkzY7d2bhkJ7
- m/0'/1  xprv = xprv9wTYmMFdV23N2TdNG573QoEsfRrWKQgWeibmLntzniatZvR9BmLnvSxqu53Kw1UmYPxLgboyZQaXwTCg8MSY3H2EU4pWcQDnRnrVA1xe8fs
- xprv format: 0x0488ADE4 || depth(1) || parent_fingerprint(4 = hash160(parent compressed pubkey)[:4]) || child_number(4 BE) || chaincode(32) || 0x00 || key(32), checksum = first4(doubleSHA256), base58.
- SelfTest: derive m, m/0', m/0'/1 from that seed and assert the xprv strings EXACTLY. This single check validates: HMAC-SHA512 CKD, EC point math (pubkey derivation), fingerprinting, and base58check.

### MAZA profile (seed = the canonical mnemonic's empty-passphrase seed, hex above; coin 13)
Compute it in SelfTest, then assert these addresses (VERIFIED against
MazaCore itself via importprivkey + validateaddress, plus the official
vector pipeline):
- m/44'/13'/0'/0/0 -> MLhJ8cs5sG8YY6YcMs5rmqCV6hZjqF7LEE
- m/44'/13'/0'/0/1 -> M8jVzPpyy3HMLfhahY2fnqquLfqENRXaW8
- m/44'/13'/0'/0/2 -> MGnAbzXuVf3ywFBeVH3a2AprzdP61igYPU
- WIF for m/44'/13'/0'/0/0 (assert exact):
  aGpgV4Riom5x1wdH7TXrsc4zJhLgYajVJMUsrYBJoUbChz5xcwi6
- Address format: base58check(0x32, hash160(compressed_pubkey)).
- P2PKH scriptPubKey: 76 a9 14 <20-byte-hash160> 88 ac.

### Canonical BTC cross-check
- m/44'/0'/0'/0/0 of the same mnemonic (version 0x00):
  1LqBGSKuX5yYUonjxT5qGfpUsXKYYWeabA  (assert exactly)

## TxBuilder spec (legacy, P2PKH, SIGHASH_ALL)
- Version 1 (4-byte LE), varint input count, inputs (prev txid 32B REVERSED
  wire order, prev vout 4B LE, varint scriptSig len, scriptSig, sequence
  0xFFFFFFFF), varint output count, outputs (value 8B LE in satoshis, varint
  scriptPubKey len, scriptPubKey), locktime 0 (4B LE).
- sighash = doubleSHA256(copy of tx where EVERY input's scriptSig is empty
  except the one being signed, which carries the UTXO's scriptPubKey,
  with SIGHASH_ALL(1) appended 4-byte LE) -> 32-byte digest.
- Signature: ECDSA on secp256k1 over that digest with RFC6979 deterministic
  nonce (HMAC-SHA256), DER-encode, LOW-S enforced (if s > n/2, s = n - s),
  append hashtype byte 0x01. scriptSig = <push sig> <push pubkey(33B)>.
- Size check: refuse to build if any output value < 0 (int64), negative fee,
  or empty inputs.
- SelfTest for signing: fixed key (use WIF above), fake prev txid, verify
  the DER signature internally with your own verify() (yes, implement
  verify() too — it's 10 lines given point math). Print PASS/FAIL.

## App integration
1. Res file: android/res/raw/bip39_english.txt ALREADY EXISTS (2048 lines).
   Load via getResources().openRawResource(R.raw.bip39_english). The
   build script already generates R via aapt2 --java. If R.raw is missing,
   ensure the res/raw dir is passed to aapt2 (it packages everything under
   android/res).
2. "My Wallet" (self-custody) section, reached from the main screen:
   - If no seed: buttons "Create new wallet" / "Import seed phrase".
   - Create: 128 bits SecureRandom entropy -> 12 words -> display ONCE in a
     scrollable list with a numbered layout, warning text "Anyone with
     these words can spend this wallet. Write them down. This screen will
     not show them again.", checkbox "I have written them down" enables
     the DONE button. Store ONLY: the mnemonic itself encrypted? NO —
     store it in app-private storage (MODE_PRIVATE file) plainly but
     never display again; do NOT log it; do NOT include it in any
     Intent/clipboard.
   - Import: text field accepting 12 words (case-insensitive, whitespace
     split), validate wordlist membership + checksum before accepting;
     error text on invalid (no alert dialogs with stack traces).
3. When a self-custody wallet exists, its screen shows:
   - Balance = sum of server watch utxos (endpoint below).
   - Address of index 0 (+ NEXT tap cycles address indices 0..19).
   - QR: GET /api/qr.png?addr=<address> with the Bearer token (server renders).
   - SEND: To (M-address), Amount (MAZA), fee fixed 0.0001. On SEND:
     a) GET /api/watch/utxos -> pick inputs (largest-first, all confirmed)
     b) build + sign with TxBuilder (change to m/44'/13'/0'/1/<next>)
     c) POST /api/broadcast {"hex": "<rawtx hex>"} -> show txid or error
     d) before (c), POST /api/watch/import the change address (so the
        backend watches it) — include change in the same import call at
        wallet creation: import indices 0..19 of BOTH chains (40 addresses).
   - HISTORY: GET /api/watch/history -> rows like the bench history view.
4. Keep ALL existing bench (custodial) functionality intact. The
   self-custody section is additive; do not remove or rename existing
   screens, endpoints, or the Bearer-token flow.
5. Server contract (I am building these now; treat as authoritative):
   - GET  /api/watch/utxos  -> {"utxos":[{"txid","vout","address","amount","confirmations"}]}
   - GET  /api/watch/history-> {"transactions":[{"txid","address","amount","confirmations","time"}]}
   - POST /api/watch/import {"addresses":["M..."]} -> {"imported":N,"watched":M}
   - POST /api/broadcast    {"hex":"..."} -> {"txid":"..."}
   All Bearer-token gated like existing endpoints. Amounts in MAZA floats.
6. MainActivity: keep the file under ~900 lines; factor crypto into the
   classes above; keep networking logic in one place.
7. Build: ./android/build-apk.sh (signs, outputs android/maza-wallet-bench.apk).
   SelfTest must also compile/run on desktop JVM: add a target
   android/selftest.sh that compiles the crypto package with javac and runs
   SelfTest, printing one PASS/FAIL line per check and exiting nonzero on
   any FAIL. ALL checks must PASS before you declare done.

## Out of scope (do NOT do)
- No bech32, no SegWit, no multi-sig, no passphrase-protected seeds in UI
  (Bip39 seed function accepts a passphrase argument; pass "" from UI).
- No encryption of the stored mnemonic (app-private storage only).
- No changes to walletbench backend files (backend is mine).

## Deliverables
- crypto/ classes + res/raw wiring + self-custody UI + integration
- android/selftest.sh (desktop JVM runner) — ALL PASS required
- Rebuilt android/maza-wallet-bench.apk
- A short CHANGES note at the end of your final message: files added, test
  results, anything you could not finish (be honest).
