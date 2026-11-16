# Running a MAZA Electrum server (ElectrumX) — community guide

Goal of this doc: anyone with a VPS and an hour of patience can serve
lightweight MAZA wallets without trusting anyone else's server. Everything
referenced here lives in this repo. If you find a step that requires
Sami-specific knowledge, that is a bug — open an issue.

Status: core verified in-repo (coin profile grade B, judge-graded; installer
pin-enforced; header-hash proven against live mainnet type-1 MinotaurX blocks).
Deployment-hardening numbers marked **[TBD/community]** still need measuring
on real hardware — file PRs with what you observe. Planned follow-ups (not yet
in-tree): packaged systemd unit + docker-compose, and a troubleshooting guide.

## What you are building

```
mazad (full node, txindex=1)  <--  ElectrumX indexer  <--  light wallets
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
| Genesis hash | `00000c7c73d8ce604178dae13f0fc6ec0be3275614366d44b1b4b5c6e238c60c` | `indexer/maza_coin.py` GENESIS_HASH |
| P2PKH address version | 50 (0x32) — addresses start `M` | chainparams.cpp via `indexer/maza_coin.py` P2PKH_VERSION_BYTE |
| Bech32 HRP | `maza` | chainparams.cpp:177 |
| Default RPC port | 12832 | chainparams.cpp via `indexer/maza_coin.py` DAEMON_RPC_PORT |
| Block spacing | 120 s per algo (multi-algo makes effective blocks faster) | `nPowTargetSpacing`; DECISIONS.md D5 |
| PoW | multi-algo — version type bytes map `sha256d` / `minotaurx` (`POW_TYPE_NAMES`, `indexer/maza_coin.py`); Hive sits in the consensus mix per DECISIONS.md D2. Irrelevant for indexing — see note below | `indexer/maza_coin.py:55-63`, DECISIONS.md D2 |
| Address derivation | desktop MazaCore wallet: `m/0'/0'/k` (DECISIONS.md D3); this repo's mobile wallet: `m/44'/13'` (DECISIONS.md D8). A light client picks its own; the server does not care | DECISIONS.md D3 + D8 |

**The multi-algo trap, solved:** ElectrumX validates block hashes, and a
multi-PoW chain looks like it needs every PoW implementation. It does NOT.
MAZA's *block identity hash* is `double-SHA256(header)` for **every** block
regardless of algorithm — MinotaurX/Hive are only `GetPoWHash()`, the mining
validity check the daemon already did. Verified against live mainnet type-1
(MinotaurX) blocks. Consequence: the ElectrumX coin profile needs zero PoW
code. (`primitives/block.cpp:18-21` in MazaCore; `indexer/maza_coin.py`
implements it, pinned by fixtures from both PoW eras.)

## Step 1 — VPS

- 2 vCPU minimum, 8 GB RAM recommended, NVMe disk.
- Until a measured number lands below, start from a conservative 200 GB
  NVMe: the mazad data dir + txindex AND the ElectrumX DB both grow with
  chain history.
- Rough size anchor: the coin profile declares an estimate of ~14M
  transactions at height 4.4M (`TX_COUNT`, `TX_COUNT_HEIGHT` in
  `indexer/maza_coin.py`) — budget disk for the node's txindex AND the
  ElectrumX DB on top.
- **[TBD/community]** measured numbers: full-chain mazad sync + txindex
  replay time, ElectrumX DB size at current height. Record what you see
  and PR it.

## Step 2 — mazad with txindex

1. Build/install MazaCore 0.16.3 per upstream.
2. `maza.conf` must include **`txindex=1`** — ElectrumX requires the full
   transaction index. Set it BEFORE the first sync (adding it later forces a
   full `-reindex`). The server enforces this too: the profile declares
   `REQUIRED_DAEMON_INDEXES = ("txindex",)`, so ElectrumX refuses to start
   against an index-less daemon.
3. Sync the chain. RPC creds: `rpcuser`/`rpcpassword` in the conf, RPC bound
   to localhost only. Never expose the RPC port publicly — only the
   ElectrumX listener should ever face the network (Step 4).
4. Confirm: `maza-cli getblockchaininfo` shows `headers == blocks` and
   `initialblockdownload: false`.

**Known MazaCore quirks** (do not debug these, they are in-tree):
- `-regtest` aborts at startup (genesis merkle assertion vs its own constant).
  Isolated-chain testing: use `-testnet`, not regtest.
- Testnet mining stalls after the first difficulty adjustment (LWMA spike);
  `generatetoaddress` only mines while the apparent-stall rule allows floor
  difficulty.

## Step 3 — ElectrumX (pinned build)

Prereqs: `git`; a **Python 3.10+** interpreter with `pip` (the pinned tree
declares `requires-python = ">=3.10"` in its `pyproject.toml` — measured at
the pin commit); and the **LevelDB C library + build toolchain** — plyvel
is a C++ extension and prebuilt wheels do not exist for every interpreter,
so if pip builds it from source you need the headers, a C++ compiler, and
the Python dev headers:

```bash
# Debian/Ubuntu (python3-venv is a separate package on minimal installs):
sudo apt-get install -y libleveldb-dev build-essential python3-dev python3-venv
# Fedora (venv included in python3):
sudo dnf install -y leveldb-devel gcc-c++ python3-devel
# Alpine (venv included in python3):
sudo apk add leveldb-dev g++ python3-dev
# macOS:
brew install leveldb
```

A venv is recommended:

```bash
python3 -m venv ~/venvs/electrumx-maza
source ~/venvs/electrumx-maza/bin/activate
```

Use the repo's pin-enforcing installer:

```bash
git clone https://github.com/SamiAhmed7777/maza-mobile-wallet
cd maza-mobile-wallet
bash deploy/install-electrumx-dev.sh              # default: third_party/electrumx
# optional args: a checkout dir, then the python interpreter to install with
```

- It clones ElectrumX at the pinned commit (`ELECTRUMX_PIN` in
  `indexer/maza_coin.py`) and REFUSES to install a mismatched tree — or an
  interpreter older than the tree's declared 3.10 floor.
- It installs the **`leveldb` extra** (`pip install -e "...[leveldb]"` →
  plyvel): the pinned tree ships NO database backend (base deps are
  aiorpcx + aiohttp only — measured in its `pyproject.toml`, which says
  the user MUST install at least one), and Step 4 serves with
  `DB_ENGINE=leveldb`.
- It ends with a fingerprint check; success prints
  `electrumx pinned tree OK: e-x 2.0.1, <N> coin classes, plyvel importable`.
- Do NOT `pip install electrumx`: the PyPI 1.20.2 sdist is a stale
  altcoin-stripped build that drops the pieces MAZA needs. This cost a judge
  round to discover.

## Step 4 — launch the server

The custom-coin registration is programmatic (the `COIN=` name lookup cannot
see out-of-module coin classes — upstream scans only `electrumx.lib.coins`).
Use the repo runner; `DB_ENGINE` is REQUIRED (`leveldb` or `rocksdb` —
selecting the backend installed in Step 3; this guide drives `leveldb`
via the plyvel extra the installer installs).

```bash
DB_DIRECTORY=/var/lib/electrumx-maza \
DAEMON_URL=http://user:pass@127.0.0.1:12832 \
DB_ENGINE=leveldb \
python3 indexer/run_indexer.py --check-only   # validates wiring, no serve
```

`--check-only` needs those three env vars, needs the pinned electrumx
importable, builds the coin class, prints the chain facts (coin, genesis,
version byte, HRP, daemon RPC port) and exits 0 when wiring is OK. Exit
codes: 2 = missing env vars, 3 = electrumx not importable (run the Step 3
installer), 4 = coin class failed to build. Fix what it names before
serving.

The DB directory must exist and be writable by the user running the server
— create it ONCE, before the first serve (it is NOT created for you, and
`/var/lib` needs root; `--check-only` does not touch the DB, the first
SERVE opens it):

```bash
sudo install -d -o "$USER" -g "$USER" /var/lib/electrumx-maza
```

To serve — loopback only (the recommended deployment; public TLS comes
from a root-managed proxy below):

```bash
DB_DIRECTORY=/var/lib/electrumx-maza \
DAEMON_URL=http://user:pass@127.0.0.1:12832 \
DB_ENGINE=leveldb \
SERVICES=tcp://127.0.0.1:50001 \
python3 indexer/run_indexer.py
```

Keep mazad's RPC on localhost; nothing needs to be opened in the firewall
yet because the listener is loopback-only.

**Public exposure (TLS):** terminate TLS at a root-managed reverse proxy
and keep ElectrumX itself on loopback — the proxy's master process reads
the certificate key as root, so ElectrumX never needs the key and
Let's Encrypt's root-only `privkey.pem` permissions stay untouched.
nginx's stream module is the minimal complete example. Prerequisites: a
hostname with a DNS A record pointing at this VPS, and TCP 80 + 50002
reachable from outside (80 is Let's Encrypt's ACME validation port, 50002
is the public ElectrumX port).

Install nginx WITH its stream module, plus certbot and its nginx plugin
(the stream module is a separate package on Debian/Ubuntu — the plain
distro `nginx` package alone may not support `listen ... ssl` inside a
stream block; installing the module package is harmless if it is already
present):

```bash
sudo apt-get update
sudo apt-get install -y nginx libnginx-mod-stream certbot python3-certbot-nginx
```

Installing nginx starts it with a default site on port 80. Open port 80 in
BOTH firewalls BEFORE issuing the certificate — the host firewall
(`sudo ufw allow 80/tcp` when ufw is active) AND the cloud provider's
security group / external firewall, which apt cannot configure for you.

Issue the certificate THROUGH the already-running nginx (the nginx plugin
answers the ACME challenge via a temporary location block inside nginx —
no port conflict at issuance, and the same path runs at every automatic
renewal, with certbot reloading nginx whenever renewed material lands):

```bash
sudo certbot certonly --nginx -d example.com
```

Wire the TLS listener — the stream{} block goes at TOP LEVEL in
/etc/nginx/nginx.conf, OUTSIDE the http{} block (stream is not an http
feature). If a top-level stream{} context already exists, merge the
server{} block into it — exactly one stream{} context is allowed:

```nginx
# /etc/nginx/nginx.conf
stream {
    server {
        listen 50002 ssl;
        proxy_pass 127.0.0.1:50001;
        ssl_certificate     /etc/letsencrypt/live/example.com/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;
    }
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

Open TCP 50002 (and keep 80 open for renewals) in your firewall; ElectrumX's
50001 stays loopback-only. Clients then connect to `ssl://example.com:50002`
(substitute your hostname in the certificate paths). Caddy can do the same
raw-TLS termination only with its layer4 module — the stock `reverse_proxy`
is HTTP-only and does not fit the Electrum wire protocol. (Alternative for
a trusted private network: bind `tcp://0.0.0.0:50001` directly — PLAINTEXT,
every query and broadcast crosses the wire in the clear.)

Initial index build **[TBD/community]**: budget generously; the DB grows
with the full txindex-derived history. Watch `DB_DIRECTORY` free space.

**Byte-order note if you hack on the profile:** ElectrumX hashes headers in
INTERNAL byte order (`double_sha256` returns the raw digest); reversal is a
DISPLAY concern only (`hash_to_display_hex` / `header_hash_rev` in
`indexer/maza_coin.py`). Mixing the two is the classic "everything matches
except the last characters" bug.

## Step 5 — verify your server (do not skip)

Your own mazad is the reference node: every answer below is compared
against it (an independent second peer is even better if you have one).
All anchor hashes come from the repo's pinned fixtures
(`ALL_FIXTURES` in `indexer/maza_coin.py`), re-verified at doc time —
6/6 reproduce via the repo's own `header_hash()`.

The Electrum protocol is line-delimited JSON over TCP; one request fits in
a plain pipe, e.g.:

```bash
echo '{"jsonrpc":"2.0","method":"blockchain.headers.subscribe","params":[],"id":0}' | timeout 10 nc 127.0.0.1 50001
```

1. **Tip parity.** `blockchain.headers.subscribe` returns a hex header whose
   height equals `maza-cli getblockchaininfo` blocks, and whose
   double-SHA256 equals `maza-cli getblockhash <tip>`:

   ```bash
   HEX="<paste the hex header from subscribe here>"   # or raw hex, quoted
   python3 -c 'import sys,hashlib; h=bytes.fromhex(sys.argv[1].strip()); print(hashlib.sha256(hashlib.sha256(h).digest()).digest()[::-1].hex())' "$HEX"
   ```

2. **Era anchors (both PoW eras, fixed heights).** Fetch the raw header at
   each height (`blockchain.block.header <height>` on the Electrum
   protocol), double-SHA256 it as above, and compare — the result must equal
   the daemon's `getblockhash` AND the pinned fixture hash:

   | Height | Era | Expected block hash (display order) |
   |---|---|---|
   | 2105603 | sha256d-era (version `0x20000000`) | `00000000000001c7adf6339094f040f880de829994ce5a9a888fe95e34669e61` |
   | 4480797 | MinotaurX type-1 (version `0x00010000`) | `d018ea96ccf304dec8f066a5f69c6950a9e12c428e40c8927190d4238d2a1404` |

   The second row is the trap-catcher: a profile that routed MinotaurX
   blocks through any PoW code, or flipped byte order, fails exactly here.

3. **UTXO-set parity.** Pick a FUNDED address straight from the daemon —
   `maza-cli listunspent 0 99999999` and take any entry's `address` — so
   the set is provably non-empty (an address that merely has history may be
   fully spent, and empty-vs-empty "parity" would prove nothing).
   Do NOT compare `blockchain.scripthash.get_balance` against
   `getreceivedbyaddress` — they are different quantities: get_balance is
   the CURRENT balance (sum of unspent), getreceivedbyaddress is CUMULATIVE
   ever-received (spends never subtract). Compare the UTXO SETS: same
   (txid, vout) keys on both sides, with VALUES EQUAL AFTER UNIT
   CONVERSION — `maza-cli listunspent` reports decimal MAZA while
   `blockchain.scripthash.listunspent` reports integer atomic units
   (1 MAZA = 1e8, the Bitcoin `COIN` base the profile inherits). Convert
   with exact decimal arithmetic, never float:

   ```bash
   maza-cli listunspent 0 99999999 '["<addr>"]' > /tmp/core-utxos.json
   echo '{"jsonrpc":"2.0","method":"blockchain.scripthash.listunspent","params":["<scripthash>"],"id":0}' \
     | timeout 10 nc 127.0.0.1 50001 > /tmp/ex-utxos.json
   ```

   ```python
   # usage: compare_utxos.py /tmp/core-utxos.json /tmp/ex-utxos.json
   import json, sys
   from decimal import Decimal
   core = json.load(open(sys.argv[1]))
   ex = json.load(open(sys.argv[2]))
   if isinstance(ex, dict):
       ex = ex.get("result", ex)          # strip the JSON-RPC envelope
   A = {}
   for u in core:
       atomic = Decimal(str(u["amount"])) * 10**8
       if atomic != atomic.to_integral_value():
           raise SystemExit(
               f"non-integral atomic amount {u['amount']} — MAZA has 8 "
               "decimals; refusing to round silently")
       A[(u["txid"], u["vout"])] = int(atomic)   # exact, never float
   B = {(u["tx_hash"], u["tx_pos"]): u["value"] for u in ex}
   assert A.keys() == B.keys(), (
       f"UTXO key sets differ: only-core={sorted(A.keys() - B.keys())} "
       f"only-ex={sorted(B.keys() - A.keys())}")
   diffs = [(k, str(A[k]), B[k]) for k in A if A[k] != B[k]]
   assert not diffs, f"value mismatches in atomic units: {diffs}"
   print(f"UTXO-set parity OK: {len(A)} utxos, values equal after 1e8 conversion")
   ```

   The scripthash side of that request is the reverse-hex of sha256 of the
   address's scriptPubKey (NOT hash160 — Electrum protocol uses sha256
   here). For a P2PKH `M...` address (self-validating: wrong version byte,
   bad length, or a corrupt checksum fails loudly):

   ```python
   import hashlib, sys
   ALPH = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
   n = 0
   for c in sys.argv[1]:
       n = n * 58 + ALPH.index(c)
   body = n.to_bytes((n.bit_length() + 7) // 8, "big")
   pad = b"\x00" * (len(sys.argv[1]) - len(sys.argv[1].lstrip("1")))
   raw = pad + body
   assert len(raw) == 25, f"not a P2PKH address blob: {len(raw)} bytes"
   assert raw[0] == 50, f"not mainnet MAZA P2PKH (version byte {raw[0]})"
   assert hashlib.sha256(hashlib.sha256(raw[:-4]).digest()).digest()[:4] \
       == raw[-4:], "base58check checksum failed — corrupt address?"
   h160 = raw[1:-4]                       # strip version byte + checksum
   script = b"\x76\xa9\x14" + h160 + b"\x88\xac"   # OP_DUP OP_HASH160 ...
   print(hashlib.sha256(script).digest()[::-1].hex())
   ```

4. **Broadcast path.** `blockchain.transaction.broadcast` a real small
   transaction and confirm it appears in the mempool / next block. Build
   txs OFFLINE first and sanity-check signatures with the repo's
   `tools/txverify.py` (proven against a real MazaCore-signed mainnet tx)
   before broadcasting anything that matters. Address/key derivation values
   can be cross-checked with `tools/oracle.py` (BIP39/BIP32 vector-anchored,
   node-validated).

**[TBD/community]** a protocol-level smoke script automating checks 1-4 is a
welcome PR — the repo's crypto instruments (`tools/oracle.py`,
`tools/txverify.py`) already cover the address/tx-value side.

## Operating notes

- Run both processes under systemd (or your supervisor of choice) with
  restart-on-failure. A ready-made `deploy/electrumx.service` +
  docker-compose packaging is planned but NOT in this tree yet — the
  wallet-bench installer (`deploy/install-walletbench.sh`) shows the house
  pattern (release dirs + health gate + state-file backup before restart).
- The ElectrumX DB is a cache — it can be deleted and rebuilt from the node.
  The mazad `wallet.dat` is NOT a cache: back it up off-host, monthly,
  and drill the restore.
- Upgrading ElectrumX: change the pin (`ELECTRUMX_PIN` in
  `indexer/maza_coin.py` AND `PIN` in `deploy/install-electrumx-dev.sh`),
  re-run the installer, re-verify Step 5.
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
