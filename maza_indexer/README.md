# maza_indexer - MAZA lean chain indexer

Stdlib-only Python package that ingests the MAZA chain from a node's
JSON-RPC (the samihost `mazad`, RPC `127.0.0.1:12832`) and serves
address / tx / block / merkle-proof JSON.  This is the lean path that
replaces the txindex-blocked ElectrumX.

## Quickstart

```
export MAZA_INDEXER_RPC_URL=http://127.0.0.1:12832
export MAZA_INDEXER_RPC_USER=...        # mazad rpcuser
export MAZA_INDEXER_RPC_PASSWORD=...    # mazad rpcpassword
export MAZA_INDEXER_DATADIR=./maza-indexer-data
python3 -m maza_indexer run            # crawl + serve
python3 -m maza_indexer --status       # cursor + counts, no secrets
python3 -m maza_indexer --reorg-delete 12345   # manual reorg recovery
```

First sync is a full crawl from height 0; the cursor resumes after any
stop.  **Honest sync note: first full sync takes time on this chain;
measure and report; the cursor resumes -- never guess a rate you have not
measured.**  `--status` shows how far the crawl has actually gotten.

## Environment

| Variable                  | Default                  | Meaning                          |
|---------------------------|--------------------------|----------------------------------|
| MAZA_INDEXER_RPC_URL      | http://127.0.0.1:12832   | mazad JSON-RPC endpoint          |
| MAZA_INDEXER_RPC_USER     | (empty)                  | RPC user                         |
| MAZA_INDEXER_RPC_PASSWORD | (empty)                  | RPC password (never logged; masked in repr/str/errors) |
| MAZA_INDEXER_DATADIR      | ./maza-indexer-data      | where maza_indexer.db + cursor.json live |
| MAZA_INDEXER_BIND         | 127.0.0.1:18711          | HTTP bind                        |
| MAZA_INDEXER_BATCH        | 24                       | block-hash lookups per crawl batch |
| MAZA_INDEXER_RATE         | 60                       | per-IP req/min token bucket      |

## Scope notes (design, not defects)

- **PoW trust.**  The indexer NEVER validates proof-of-work (MinotaurX/Hive
  are too heavy off-device).  It trusts the daemon's chain exactly like
  ElectrumX does: header IDENTITY checks only (double-SHA256 of the 80-byte
  header reproduces the RPC block hash for every block in every PoW era,
  MazaCore primitives/block.cpp:18-21; prevhash must link to the stored
  previous block).  PoW validity stays the daemon's job, as it is for every
  ElectrumX-backed fork (DECISIONS.md D2).
- **Reorg policy.**  No automatic reorg following.  A header identity or
  prevhash mismatch is a LOUD ABORT (message on stderr, nonzero exit): the
  operator runs `--reorg-delete <height>`, which deletes blocks >= height in
  one store transaction (un-marking outputs spent by deleted txs and
  recomputing every affected address), rewinds the cursor, and exits; the
  next `run` re-crawls the deleted span.
- **No txindex needed.**  getblock <hash> 2 returns full transactions with
  txindex OFF on this daemon build (Day-0 probe 2026-11-18); there is no
  `ntx` field at verbosity 2, so ntx is counted from the tx array.
- **Auth surface.**  The read-only HTTP surface has no per-route auth;
  /health included.  The Caddy front door is the TLS/hosts layer; the
  default bind is loopback-only.
- **Byte order.**  Hashes returned by the API are exactly as the RPC
  provided them (display order), never re-reversed.  Internally,
  double_sha256 returns INTERNAL order; comparisons reverse explicitly
  (maza_indexer/hashutil.py docstring).
- **Money.**  Int satoshis everywhere; sats -> display conversion is the
  CLIENT's job.  RPC decimal values are converted with Decimal (exact),
  never float math.

## API (v0)

GET-only, JSON in / JSON out; errors are ALWAYS `{"error": str}` with
status 404 | 413 | 429 | 500.

- `GET /health` -> `{"ok":true,"height":<int>,"chain":"main","txs_indexed":<int>}`
- `GET /api/v0/address/<addr>` -> balance_sats, tx_count, truncated,
  newest-first history capped at 100 (time = block time)
- `GET /api/v0/tx/<txid>` -> height, confirmations, blockhash, size, hex,
  vin (resolved AT SERVE TIME from the durable outputs table; coinbase:
  txid null, value_sats null, coinbase true), vout
- `GET /api/v0/block/<h>` (height or hash) -> merkleroot, ntx, time,
  difficulty, txids capped at 500 with txids_truncated
- `GET /api/v0/proof/<height>/<txid>` -> merkle branch + pos (Bitcoin Core
  pairing: concat left+right, double-SHA256, odd node duplicates itself);
  404 JSON when the txid is not in that block
- `GET /api/v0/search?q=` -> `{"type":"address"|"tx"|"block"|"unknown","query":<str>}`
- `GET /api/v0/stats` -> height, total_txs, address_count

## Verification helpers

`maza_indexer/verify.py` is PURE (stdlib + hashutil only) so it can lift to
a phone later: `verify_merkle_proof(txid, root, branch, pos)` and
`header_hash(header_hex)`.

## addr_tx aggregation semantics

One row per (address, tx), NET flow: `net = SUM(vouts paying A) -
SUM(inputs spent from A)`.  net > 0 -> direction "in", value_sats = net;
net < 0 -> direction "out", value_sats = abs(net); net == 0 (self-transfer)
-> direction "in", value_sats = 0, row kept for history completeness.
`tx_count` = COUNT of the address's addr_tx rows; `balance_sats` = SUM of
signed net, asserted against the history rows on every write.
