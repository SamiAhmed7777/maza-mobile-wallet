# MAZA Mobile Wallet

A native MAZA (MazaCoin) mobile wallet: **v0.5 self-custody is implemented
and live-proven on mainnet**. The Android app generates/imports a BIP39
seed phrase on-device, derives keys at `m/44'/13'` (SLIP-44 coin 13),
builds and signs legacy P2PKH transactions locally, and talks to a small
token-gated watch/broadcast service — the server never sees a private key.

Also in this repo: the bench backend (walletbench), the ElectrumX coin
profile + installer for running your own Electrum server, and the
verification tooling that gates every crypto change.

License: MIT ([LICENSE](LICENSE)). Every chain parameter is inherited from MazaCore
0.16.3 with file/line citations in `DECISIONS.md` — decisions are
documented, not invented.

## Why

No maintained official mobile wallet exists: the Android repo was last touched
in 2018 (its master is marked "DO NOT USE"), iOS in 2017, and the 2015-era
Electrum fork (mazaclub/tate) predates the 2022 MinotaurX/Hive consensus
upgrade. The official site points users at Komodo Wallet, whose MAZA config
drifts from chain code (WIF byte, derivation path, block time). This project
builds the missing piece on chain-code defaults.

## What works today

- **Self-custody wallet (shipped, mainnet-proven 2026-11-16)**: on-device
  BIP39 seed, local signing, watch-only backend; live proof in
  `android/evidence/selfcustody-proof/PROOF.md` (phone-signed tx
  ce514b350d2c...cd4e confirmed, `tools/txverify.py` SIGNATURE VALID +
  LOW-S offline gate).
- **Encrypted seed at rest**: AES-256-GCM envelope with a non-exportable
  AndroidKeyStore key, atomic writes, in-place migration of legacy
  plaintext seed files.
- **Bench (custodial play wallet) v0** live since 2026-11-15: custodial
  play wallet (`mobile-play` account), raw-tx sends with explicit input
  selection, funding-flow change reconciliation, count-only access logs.
- **ElectrumX community kit**: MAZA coin profile + pinned installer +
  zero-to-serving guide (`docs/electrumx/README.md`), systemd/compose
  deploy kit (`deploy/`), troubleshooting + takeover runbooks
  (`docs/electrumx/`).
- **Chain-params rigor**: decision table locked (`DECISIONS.md`,
  2026-11-15); fixtures from BOTH PoW eras reproduce the daemon's own
  block hashes exactly; constants anchored to sha256-pinned MazaCore
  excerpts (`vendor/`).
- In flight / open: PIN + biometric lock, device proofs for the
  encrypted-seed and lock lanes, APK distribution channel, QR-scan
  on-device proof (scan surface code shipped 2026-11-17), payment URIs,
  MazaPay checkout integration, indexer deployment (blocked
  on a txindex build decision — see `docs/electrumx/TROUBLESHOOTING.md`).

## Quickstart

### 1. Build and install the wallet app

Needs a JDK (21 tested) + an Android SDK (build-tools 34, platform
android-34).

```bash
bash android/build-apk.sh            # bench build -> maza-wallet-bench.apk
bash android/build-apk.sh --release  # release build -> android/releases/
```

Install the APK on any Android 7+ device, enter a walletbench server URL
and token on the Connect screen, and the wallet is live. The shipped
default endpoint is a token-gated TEST service run by the maintainers
(`https://mazatest.sami-host.me`); the field is user-editable — point it
at your own backend (step 2) for anything real.

### 2. Run the backend (walletbench)

walletbench is a small token-gated watch/broadcast service in front of a
`mazad` node (RPC `127.0.0.1:12832`). It watches addresses
(`importaddress` — no keys ever), serves UTXOs / history / QR codes, and
broadcasts client-signed raw transactions.

The self-custody backend is watch-only and cannot sign or spend independently: addresses are
imported with `importaddress` (no keys), and every outgoing self-custody
transaction is signed on the phone — the backend only relays
client-signed bytes. The legacy custodial bench endpoints (`/api/send`
on the capped play account) are the deliberate exception: they spend the
bench account's server-side funds by design.

```bash
bash deploy/install-walletbench.sh     # on the host running mazad: systemd
                                       # unit + env + token, health-gates on 401
python3 -m unittest discover -s tests  # offline backend suite, no deps
```

The token lives in the unit's env file; deliver it to app users out of
band. The app keeps it memory-only — typed once per session, never
persisted, never baked into the APK, never passed in URLs.

### 3. Run your own Electrum server

`docs/electrumx/README.md` is a zero-to-serving guide (VPS sizing, mazad
sync with `txindex=1`, pinned installer, wiring check, verify checklist),
with a systemd unit + docker-compose kit in `deploy/` and
troubleshooting/takeover runbooks in `docs/electrumx/`.

### 4. Verify the crypto claims yourself

```bash
bash android/selftest.sh       # crypto vectors, desktop JVM: ALL PASS, exit 0
python tools/oracle.py         # independent Python oracle: BIP39/BIP32 + MAZA profile
pip install -r tools/requirements.txt   # oracle deps (ecdsa, pycryptodome)
cat android/evidence/selfcustody-proof/PROOF.md  # the live mainnet send

# Backend suite verbose + ElectrumX wiring (when the pinned tree is installed):
python3 -m unittest discover -s tests -v
bash deploy/install-electrumx-dev.sh          # clone + pin-check + install
python3 indexer/run_indexer.py --check-only   # validate wiring, no sockets
```

The offline backend suite has no external dependencies; the ElectrumX
integration tests run whenever the pinned `e-x` tree is installed and
skip cleanly otherwise.

## Repo map — who owns what

| Path | What it is |
|---|---|
| `android/` | The app: `MainActivity` (bench views) + `SelfCustody` (seed wallet), crypto package `com.mazawallet.crypto` (BIP39/BIP32/Secp256k1/Base58Check/TxBuilder), `selftest.sh` (vector gate), `build-apk.sh` (Gradle-free aapt2/javac/d8/apksigner) |
| `android/evidence/` | Install + live-proof evidence, `PROOF.md` per milestone |
| `walletbench/` | Watch-only backend: `/api/state`, `/api/watch/{import,utxos,history}`, `/api/broadcast`, `/api/book/reconcile`, scoped `/api/qr.png` + `/api/qr.svg`, plus the v0 bench (custodial) API |
| `indexer/` | ElectrumX MAZA coin profile + launcher |
| `deploy/` | walletbench installer, ElectrumX pinned installer, systemd/compose kit, public-hosting recipe, tunnel unit template |
| `docs/` | `SPEC.md` + `SPEC-AUDIT.md` (wallet spec + per-item compliance matrix), `DEPENDENCY-LICENSES.md`, `electrumx/` (community kit docs) |
| `tools/` | `oracle.py` (independent Python oracle, official vectors + MAZA profile, node-validated), `txverify.py` (offline SIGHASH_ALL/ECDSA verifier, validated against a real MazaCore-signed mainnet tx), `requirements.txt` |
| `vendor/` | sha256-pinned MazaCore excerpts anchoring chain constants |

**Who owns what:** the product and all coin policy are maintained by
Sami Ahmed (coin-policy changes are deliberate, documented calls, never
drive-by edits); the ElectrumX kit and docs are the community-contribution
surface — outside fixes and takeovers are the point of M18/M19.

**Where decisions live:**

- Chain parameters (confirmations, fees, derivation path, address
  versions, block timing): [DECISIONS.md](DECISIONS.md) — every value
  cites MazaCore 0.16.3 source. Changes to coin policy are deliberate,
  documented calls, never code accidents.
- Wallet requirements + per-item compliance: [docs/SPEC.md](docs/SPEC.md) +
  [docs/SPEC-AUDIT.md](docs/SPEC-AUDIT.md).
- Dependency/licensing posture:
  [docs/DEPENDENCY-LICENSES.md](docs/DEPENDENCY-LICENSES.md) — the APK
  ships ZERO third-party runtime libraries.
- `TASK-ANDROID*.md` and `deploy/backlog-snapshot-*.txt` are historical
  work-order archives, not setup docs.

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

## Maintainer notes

- The public `mazatest` endpoint is a TEST service behind a token and a
  per-send cap. Its hosting recipe (Caddy vhost in front of walletbench)
  is `deploy/PUBLIC-HOSTING.md`. Rotate the token server-side and
  redeliver to testers out of band; a token shipped inside the APK would
  defeat the gate it guards.
- Secrets/IP audit scope: `android/evidence/`, `TASK-ANDROID*.md` and
  `deploy/backlog-snapshot-*.txt` are frozen historical records — they
  still cite retired private endpoints on purpose (rewriting evidence
  would falsify it). Every ACTIVE setup doc carries no private
  infrastructure values.
- The maintainers' own bench instances stay on private networks;
  `deploy/maza-bench-tunnel.service.example` is the placeholder template
  for an SSH port-forward unit of that shape. The tailnet is an
  administration convenience, never a requirement for wallet users.
- Launcher icon: the official MazaCoin roundel (Sami-supplied),
  sha256-pinned in `walletbench/static/icon.png`.
