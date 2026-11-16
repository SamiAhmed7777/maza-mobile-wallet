# Self-custody v0.5 live mainnet proof

Recorded 2026-11-16. Every value below was produced live and is
independently re-checkable with the commands in this file.

## Flow

1. Seed created ON DEVICE (BlueStacks/SAMI-PC): 12-word BIP39 mnemonic,
   shown once, confirmed by checkbox. The mnemonic is held by Sami (chat
   backup) and is NOT stored in this repo.
2. App derived address index 0 (`m/44'/13'/0'/0/0`):
   `MPHoBsbsNUduo7fsvMCREpDSMWpyeUxq2H`
3. INDEPENDENT CROSS-CHECK: `tools/oracle.py` (Python, ecdsa/pycryptodome)
   derived the SAME address from the same mnemonic — Java and Python agree
   on a live seed, anchored to the official BIP39/BIP32 vectors.
4. Watch set: the 40-address window (receive 0..19 + change 0..19) imported
   via `POST /api/watch/import` → `{"imported": 40, "watched": 43}`.
5. Funded from the bench account: **2.0 MAZA**, tx
   `7a0af47a1d3c1f8a6b83885baf473d9f6a7a0ff8ccfe39b658cdd23d2e5fcc34`
   (confirmed; seen in `/api/watch/utxos` and in the app's HISTORY view).
6. The app built, SIGNED ON DEVICE, and broadcast a spend of **0.5 MAZA** to
   the external address `MV9wCMvTwf2TzRRnaSt3hnLjNktv2Z2AGt` via
   `POST /api/broadcast`. The server never saw a private key.
7. Broadcast accepted; tx **CONFIRMED** on mainnet:
   `ce514b350d2c2dc362b8cea0babc9ac64b8261b547142cc93a94ae366350cd4e`
   change 1.4999 MAZA → `MRfcWqfdXjgJYCY8s1BbjrpNpemgTY1q9h`
   (= `m/44'/13'/0'/1/0`, the wallet's own change address, per spec).

## Offline signature gate (the point of this proof)

`tools/txverify.py` recomputes the SIGHASH_ALL digest and ECDSA-verifies the
embedded signature against the pubkey in the scriptSig. This verifier is
anchored: it reproduces a real MazaCore-signed mainnet transaction (tx
c3ceb87e…, Sami's first user send) as VALID, so an INVALID is authoritative.

```
$ /tmp/destvenv/bin/python tools/txverify.py \
    $(cat sent-tx-hex.txt) 0 76a914a8d1e31cee7692a99dc10bdd8d36a7da9f2bde3288ac
tx: version=1 inputs=1 outputs=2 locktime=0 consumed=226/226 bytes
pubkey 03b962f74b70283d... -> address MPHoBsbsNUduo7fsvMCREpDSMWpyeUxq2H
s value: LOW (ok)
SIGNATURE: VALID
  output 0: 0.50000000 MAZA
  output 1: 1.49990000 MAZA
```

- Embedded pubkey hashes to EXACTLY the app's receive address (the phone
  signed with its own derived key).
- LOW-S (BIP62) enforced.
- 226 bytes: 1-in-2-out legacy P2PKH as specified.

## Files

- `sent-tx-raw.json` — full JSON from `getrawtransaction <txid> true`
  (includes hex + confirmations at capture time).
- `sent-tx-hex.txt` — raw tx hex only.
- `txverify-output.txt` — verifier output as run.
- `s1..s4.png` — M1 install screenshots (connect card, balance, WALLET tab
  with self-custody entry, refreshed balance).
- `sc_send.png` — post-send screen ("Sent: ce514b…cd4e", HISTORY row
  "-2 MAZA 11/16/26 12:43 AM, 19 confs, 7a0af4…cc34").
- `w.png` — WALLET tab rendering the persisted seed wallet (address, NEXT,
  QR) after the fix for the `BigInteger.TWO` Android crash.

## Re-checking without trusting this file

```
TXID=ce514b350d2c2dc362b8cea0babc9ac64b8261b547142cc93a94ae366350cd4e
# on any synced node:
maza-cli getrawtransaction $TXID true
# then run tools/txverify.py on the hex with the SPENT prevout's scriptPubKey:
# prevout = 7a0af47a…cc34 : vout 1 (the 2.0 MAZA output to MPHoBsbsNUduo…),
# scriptPubKey 76a914a8d1e31cee7692a99dc10bdd8d36a7da9f2bde3288ac
# (vout 0 is the 46.9998774 change the funding tx left elsewhere).
```

## Incidents found and fixed during this proof

- `BigInteger.TWO` (Java 9+) does not exist on Android's runtime — app
  crashed rendering the first derived address. Fixed (`new BigInteger("2")`),
  selftest re-run green.
- Funding via node `sendtoaddress` swept the bench change UTXO into a
  default-account address (wallet-level coin selection; accounts are labels).
  Change reconciled back into the bench book; M20 in the backlog makes the
  funding flow reconcile automatically.
- Creation-time watch import died with the original crash, leaving the
  wallet blind — covered manually during the proof; M21 (re-import on
  unlock, retries) and the broadcast-gating fix are in this changeset.
