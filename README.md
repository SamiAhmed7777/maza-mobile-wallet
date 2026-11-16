# MAZA Mobile Wallet

A native MAZA (MazaCoin) mobile wallet: **v0.5 self-custody is implemented
and live-proven on mainnet**. The Android app generates/imports a BIP39
seed phrase on-device, derives keys at `m/44'/13'` (SLIP-44 coin 13),
builds and signs legacy P2PKH transactions locally, and talks to a small
token-gated watch/broadcast service — the server never sees a private key.

Also in this repo: the bench backend (walletbench), the ElectrumX coin
profile + installer for running your own Electrum server, and the
verification tooling that gates every crypto change.

## Why

No maintained official mobile wallet exists: the Android repo was last touched
in 2018 (its master is marked "DO NOT USE"), iOS in 2017, and the 2015-era
Electrum fork (mazaclub/tate) predates the 2022 MinotaurX/Hive consensus
upgrade. The official site points users at Komodo Wallet, whose MAZA config
drifts from chain code (WIF byte, derivation path, block time). This project
builds the missing piece on chain-code defaults.

## Components

| Path | What it is |
|---|---|
| `android/` | The app: `MainActivity` (bench views) + `SelfCustody` (seed wallet), crypto package `com.mazawallet.crypto` (BIP39/BIP32/Secp256k1/Base58Check/TxBuilder), `selftest.sh` (desktop JVM vector tests), `build-apk.sh` (Gradle-free aapt2/javac/d8/apksigner) |
| `walletbench/` | Watch-only backend: `/api/watch/import`, `/api/watch/utxos`, `/api/watch/history`, `/api/broadcast`, scoped `/api/qr.png?addr=`, plus the v0 bench (custodial) API |
| `indexer/` | ElectrumX MAZA coin profile + launcher |
| `deploy/` | samihost installer (bench service), ElectrumX pinned installer |
| `tools/` | `oracle.py` — independent Python oracle (official BIP39/BIP32 vectors + MAZA profile); `txverify.py` — offline SIGHASH_ALL/ECDSA verifier (validated against a real MazaCore-signed mainnet tx); `requirements.txt` for the oracle venv |
| `docs/electrumx/` | Community guide: run your own Electrum server for MAZA |
| `android/evidence/` | Install + live-proof evidence, incl. `selfcustody-proof/PROOF.md` |

## Verify everything yourself (do not trust this README)

```bash
# Crypto vectors (desktop JVM; Java + Python must agree):
bash android/selftest.sh                        # 19 checks, ALL PASS, exit 0
python tools/oracle.py                          # BIP39/BIP32 anchored checks

# Backend tests:
python3 -m unittest discover -s tests           # walletbench + chain suites

# Python deps for tools/ (system python lacks ecdsa/pycryptodome):
pip install -r tools/requirements.txt

# Android build:
bash android/build-apk.sh                       # signed APK

# Live mainnet proof (re-checkable without trusting us):
cat android/evidence/selfcustody-proof/PROOF.md
```

## Wallet parameters (inherited, cited)

Every parameter mirrors MazaCore 0.16.3 (`github.com/MazaCoin/maza`, tag
v0.16.3) with file/line citations — see `DECISIONS.md`. Headlines:
P2PKH version byte 50 (`M...`), WIF 224, bech32 HRP `maza`, 120 s blocks,
RPC 12832, SLIP-44 coin 13, derivation `m/44'/13'/0'/0/i` (+ `/1/i`
change), spend at 1 confirmation, SIGHASH_ALL with low-S.

Note on derivation: the MOBILE wallet follows the SLIP-44 standard
`m/44'/13'/0'/0/i` (matching the Komodo registry config); MazaCore's own
desktop wallet.dat uses a raw HD seed at `m/0'/0'/k` (wallet.cpp:185) —
seed import from a desktop wallet.dat into the mobile wallet is a planned
lane, not an established fact.

## Architecture (self-custody flow)

```
Android app                          walletbench (token-gated)
  BIP39 seed (on device)   --watch-->  importaddress (no keys)
  derive m/44'/13'                    listunspent -> /api/watch/utxos
  build+sign locally      --bytes-->  sendrawtransaction (/api/broadcast)
  history/balance         <--watch--  listunspent/listtransactions
```

The bench (custodial `mobile-play` account) flow remains for the play
funds; its tab-bar SEND is the custodial path, while the WALLET tab holds
the self-custody wallet (seed + its own send form).

## Running your own Electrum server

See `docs/electrumx/README.md` — pinned ElectrumX installer, MAZA coin
profile, verify checklist. The multi-algo PoW is a non-issue for indexing:
the block identity hash is plain double-SHA256 for every block regardless
of PoW algorithm (`CBlockHeader::GetHash()` = `SerializeHash`, proven live
on genuine MinotaurX blocks), so ElectrumX ingests the whole chain with no
PoW oracle.

## Android APK / BlueStacks bench

`android/build-apk.sh` builds a signed APK (aapt2/javac/d8/apksigner — no
Gradle, no external libraries). The app talks to the walletbench API with
stateless auth: `Authorization: Bearer <token>` on every request; the token
never rides in a URL. Default endpoint: `https://mazatest.sami-host.me` (public
TEST endpoint — recipe: `deploy/PUBLIC-HOSTING.md`; the field is user-editable,
so any walletbench host works — ordinary users need nothing beyond the APK,
a server URL, and a token).

Maintainer/admin note: the maintainer's own bench instances stay on private
networks (the DNS2 tailnet tunnel, `deploy/maza-bench-tunnel.service`, binds
DNS2's tailnet IP only and forwards to the bench on samihost; the public
`mazatest` Caddy site proxies the same samihost bench). The tailnet is an
administration convenience, never a requirement for wallet users. Launcher
icon is the official MazaCoin roundel, Sami-supplied (sha256-pinned in
`walletbench/static/icon.png`). The bench unlock token rotates on demand
and goes to Sami by DM only.

## Verification

```bash
python3 -m unittest discover -s tests -v
# With electrumx installed (integration tests exercised):
bash deploy/install-electrumx-dev.sh          # clone + pin-check + install
python3 indexer/run_indexer.py --check-only   # validate wiring, no sockets
```

No external dependencies for the offline backend suite (the ElectrumX
integration tests run whenever the pinned `e-x` tree is installed and skip
cleanly otherwise); `tools/` needs `pip install -r tools/requirements.txt`.

## Status

- Decision table locked (`DECISIONS.md`, 2026-11-15).
- **Wallet bench v0** live since 2026-11-15: custodial play wallet
  (`mobile-play` account), raw-tx sends with explicit input selection.
- **Self-custody v0.5 SHIPPED 2026-11-16**: on-device BIP39 seed, local
  signing, watch-only backend; live mainnet proof
  (`android/evidence/selfcustody-proof/PROOF.md`): phone-signed tx
  ce514b350d2c...cd4e confirmed, SIGNATURE VALID + LOW-S offline gate.
- Coin profile + fixtures from BOTH PoW eras reproduce the daemon's own
  block hashes exactly; chain constants anchored to vendored MazaCore
  excerpts (`vendor/`, sha256-pinned).
- Open: indexer deployment, release keystore + distribution, QR scanning,
  payment URIs, MazaPay checkout integration (backlog M-items).
