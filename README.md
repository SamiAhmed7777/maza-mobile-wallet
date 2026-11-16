# MAZA Mobile Wallet

An indexer/decision scaffold for a MazaCoin (MAZA) mobile wallet. **This is
not yet a working wallet app** — it holds the locked decision table and the
first tested building block (the ElectrumX MAZA coin profile). Decisions are
inherited from the existing wallet code — MazaCore 0.16.3 — not invented
(see `DECISIONS.md` for the cited decision table and the rule behind it).

## Why

No maintained official mobile wallet exists: the Android repo was last touched
in 2018 (its master is marked "DO NOT USE"), iOS in 2017, and the 2015-era
Electrum fork (mazaclub/tate) predates the 2022 MinotaurX/Hive consensus
upgrade. The official site points users at Komodo Wallet, whose MAZA config
drifts from chain code (WIF byte, derivation path, block time). This project
builds the missing piece on chain-code defaults.

## Architecture

- **Light client** (phone) — address derivation mirrors MazaCore's own HD
  scheme (`m/0'/0'/k`, wallet.cpp:185). Note: MazaCore's wallet.dat stores a
  raw HD seed (not a BIP39 mnemonic); importing a desktop wallet seed into
  the mobile wallet is a planned lane, not an established fact. Address,
  fee, and confirmation behavior mirror MazaCore's wallet code (DECISIONS.md).
- **Indexer** (samihost, next to the existing `mazad`) — ElectrumX with the
  MAZA coin profile (`indexer/maza_coin.py`): server merkle proofs for tx
  verification, so the phone never validates multi-algo PoW itself (Hive
  consensus needs chain state a header-only client can't rebuild — see
  DECISIONS.md D2).
- **MazaPay integration** — scan a merchant checkout QR and pay it directly.

## Lanes

1. **Indexer** — ElectrumX + MAZA coin profile on samihost. Coin profile and
   header-hash behavior are in this repo and tested offline against live
   mainnet fixtures from both PoW eras. **Unblocked finding (2026-11-16):**
   the block identity hash is double-SHA256 for every block regardless of
   PoW algorithm (`CBlockHeader::GetHash()` = `SerializeHash`, verified live
   on genuine MinotaurX blocks), so ElectrumX ingests the whole chain with
   no MinotaurX hash oracle. Open: daemon `txindex=1`, the `Env(coin=...)`
   launch runner, `DB_ENGINE` choice, deploy script, public TCP verification.
2. **Mobile app** — Android-first wallet on the indexer above (m/0'/0'/k,
   MazaCore-faithful defaults per DECISIONS.md).
3. **MazaPay bridge integration** — checkout deep links + confirmation display
   consistent with D1.

## Status

- Decision table locked (`DECISIONS.md`, 2026-11-15).
- **Wallet bench v0 (added in this changeset)**: `walletbench/` — UTXO-scoped
  wallet service (raw-tx sends with explicit input selection so only bench
  addresses' coins are ever consumed), token-authed mobile UI (Kimi-CLI-built,
  adopted via an adoption gate), samihost installer binding the tailnet IP
  only. This is the D7 bench edition: keys in the node wallet, NOT
  self-custody.
- Coin profile + offline tests landed (previous commit): fixtures from BOTH
  PoW eras reproduce the daemon's own block hashes exactly; chain constants
  anchored to vendored MazaCore excerpts (`vendor/`, sha256-pinned).
- **Identity-hash finding (2026-11-16):** block identity = double-SHA256 for
  all blocks (incl. MinotaurX-mined ones) — the indexer has no oracle
  blocker. PoW validation stays the daemon's job.
- Not started: indexer deployment on samihost, v1 self-custody wallet
  (client-side keys over the indexer), MazaPay checkout integration.

## Android APK / bench app

`android/build-apk.sh` builds a signed APK (aapt2/javac/d8/apksigner — no
Gradle, no external libraries). The app talks to the walletbench API with
stateless auth: `Authorization: Bearer <token>` on every request (GETs and
POSTs). Default endpoint: `http://100.121.150.22:18701` — the DNS2 tunnel
(`deploy/maza-bench-tunnel.service`, bound to DNS2's tailnet IP only) that
forwards to the bench on samihost; the samihost tailnet IP directly is
blocked for non-granted ports by the tailnet ACL. Launcher icon is the
official MazaCoin roundel, Sami-supplied (sha256-pinned in
`walletbench/static/icon.png`).

## Verification

```bash
python3 -m unittest discover -s tests -v
# With electrumx installed (integration tests exercised):
bash deploy/install-electrumx-dev.sh          # clone + pin-check + install
python3 indexer/run_indexer.py --check-only   # validate wiring, no sockets
```

No external dependencies for the offline suite; the ElectrumX integration
tests (registration via `Env(coin=...)`, server entry-point fixtures, tree
fingerprints, runner check) run whenever the pinned `e-x` tree is installed
and skip cleanly otherwise.
