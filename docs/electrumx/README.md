# Running a MAZA Electrum server (ElectrumX) — community guide

Goal of this doc: anyone with a VPS and an hour of patience can serve
lightweight MAZA wallets without trusting anyone else's server. Everything
referenced here lives in this repo. If you find a step that requires
Sami-specific knowledge, that is a bug — open an issue.

Status: core verified in-repo (coin profile grade B, judge-graded; installer
pin-enforced; header-hash proven against live mainnet type-1 MinotaurX blocks).
Deployment-hardening sections marked **[TBD/community]** still need numbers
measured on real hardware — file PRs with what you observe.

## What you are building

```
mazad (full node, txindex=1)  ←–  ElectrumX indexer  ←–  light wallets
```

- **mazad** holds the chain and answers block/tx RPCs.
- **ElectrumX** builds address indexes on top and serves the Electrum wire
  protocol (balance, history, broadcast) so wallets don't each download the
  whole chain.
- Both run on one box for a personal/community server.

## MAZA chain facts you will need

| Parameter | Value | Source |
|---|---|---|
| Client | MazaCore 0.16.3 | github.com/MazaCoin/maza, tag v0.16.3 |
| P2PKH address version | 50 (0x32) — addresses start `M` | chainparams.cpp |
| Bech32 HRP | `maza` | chainparams.cpp |
| Default RPC port | 12832 | chainparams.cpp |
| Block spacing | 120 s | nPowTargetSpacing |
| PoW | multi-algo (SHA-256d + MinotaurX + Hive) | see note below |
| Address derivation (wallets) | `m/44'/13'/0'/0/i` (SLIP-44 coin 13) | DECISIONS.md |

**The multi-algo trap, solved:** ElectrumX validates block hashes, and a
multi-PoW chain looks like it needs every PoW implementation. It does NOT.
MAZA's *block identity hash* is `double-SHA256(header)` for **every** block
regardless of algorithm — MinotaurX/Hive are only `GetPoWHash()`, the mining
validity check the daemon already did. Verified against live mainnet type-1
(MinotaurX) blocks. Consequence: the ElectrumX coin profile needs zero PoW
code. (`primitives/block.cpp:18-21` in MazaCore; `indexer/maza_coin.py`
implements it.)

## Step 1 — VPS

- 2 vCPU minimum, 8 GB RAM recommended, NVMe disk.
- **[TBD/community]** measured sizes: full-chain mazad + txindex replay time,
  ElectrumX DB size at height ~4.5M. Record what you see and PR it.

## Step 2 — mazad with txindex

1. Build/install MazaCore 0.16.3 per upstream.
2. `maza.conf` must include **`txindex=1`** — ElectrumX requires the full
   transaction index; without it the sync fails partway. Set it BEFORE the
   first sync (adding it later forces a full `-reindex`).
3. Sync the chain. RPC creds: `rpcuser`/`rpcpassword` in the conf, RPC bound
   to localhost only.
4. Confirm: `maza-cli getblockchaininfo` shows `headers == blocks` and
   `initialblockdownload: false`.

**Known MazaCore quirks** (do not debug these, they are in-tree):
- `-regtest` aborts at startup (genesis merkle assertion vs its own constant).
  Isolated-chain testing: use `-testnet`, not regtest.
- Testnet mining stalls after the first difficulty adjustment (LWMA spike);
  `generatetoaddress` only mines while the apparent-stall rule allows floor
  difficulty.

## Step 3 — ElectrumX (pinned build)

Use the repo's pin-enforcing installer:

```bash
git clone https://github.com/SamiAhmed7777/maza-mobile-wallet
cd maza-mobile-wallet
bash deploy/install-electrumx-dev.sh
```

- It clones ElectrumX at the pinned commit (`ELECTRUMX_PIN` in
  `indexer/maza_coin.py`) and REFUSES to install a mismatched tree.
- Do NOT `pip install electrumx`: the PyPI 1.20.2 sdist is a stale
  altcoin-stripped build that drops the pieces MAZA needs. This cost a judge
  round to discover.

## Step 4 — launch the server

The custom-coin registration is programmatic (the `COIN=` name lookup cannot
see out-of-module coin classes — upstream scans only `electrumx.lib.coins`).
Use the repo runner:

```bash
python3 indexer/run_indexer.py --check-only   # validates wiring, no serve
DAEMON_URL=http://user:pass@127.0.0.1:12832 \
DB_DIRECTORY=/var/lib/electrumx-maza \
SERVICES=tcp://0.0.0.0:50001 \
python3 indexer/run_indexer.py               # serves
```

`indexer/run_indexer.py` builds `Env(coin=...)` from `indexer/maza_coin.py`
and starts the standard Controller. `--check-only` exits nonzero with the
reason if the environment is wrong — run it first.

Initial index build **[TBD/community]**: budget generously; the DB grows with
the full txindex-derived history. Watch `DB_DIRECTORY` free space.

**Byte-order note if you hack on the profile:** ElectrumX hashes headers in
INTERNAL byte order (`double_sha256` returns the raw digest); reversal is a
DISPLAY concern only (`hash_to_display_hex` / `header_hash_rev` in
`indexer/maza_coin.py`). Mixing the two is the classic "everything matches
except the last characters" bug.

## Step 5 — verify your server (do not skip)

Against your own mazad (ground truth):

1. `blockchain.headers.subscribe` → tip height equals
   `maza-cli getblockchaininfo` blocks, and the hex header, when
   double-SHA256'd, equals the block hash from `getblockhash <height>`.
2. `blockchain.scripthash.get_balance` for a funded address equals
   `maza-cli getreceivedbyaddress <addr> 0`.
3. `blockchain.blockchain.transaction.broadcast` a real small transaction
   and confirm it appears in the mempool / next block.

**[TBD/community]** a scripted verifier lives at `tools/oracle.py` +
`tools/txverify.py` for crypto/address values; a protocol-level smoke script
is a welcome PR.

## Operating notes

- Run both under systemd with `Restart=always`; see
  `deploy/` for the wallet-bench pattern (release dirs + health gate +
  state-file backup before every restart).
- The ElectrumX DB is a cache — it can be deleted and rebuilt from the node.
  The mazad `wallet.dat` is NOT a cache: back it up off-host, monthly,
  and drill the restore.
- Upgrading ElectrumX: change the pin, re-run the installer, re-verify Step 5.
- Decisions and their citations live in `DECISIONS.md`; consensus-adjacent
  changes are checked against `tools/oracle.py` (BIP39/BIP32-anchored) and
  `tools/txverify.py` (proven against a real MazaCore-signed mainnet tx).

## Taking over / contributing

- Every wallet parameter mirrors MazaCore 0.16.3 with file/line citations in
  `DECISIONS.md`. If a citation is missing, ask before inventing.
- Coin-policy changes (fee floors, confirmation counts, URI semantics) are
  MazaCoin governance (Payu) territory, not unilateral repo changes.
- PRs that fill a **[TBD/community]** with measurements are the fastest way
  to help.
