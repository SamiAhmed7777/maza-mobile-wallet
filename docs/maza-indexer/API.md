# API.md - the MAZA lean indexer HTTP contract

This is the contract, verbatim, as it is written in the plan and in every
lane brief. **Do not edit the block below** - it is the shared, frozen
agreement between the indexer and the wallets that will query it. Money is
always in **sats**, as an integer. There are no floats for money anywhere
in this API (`difficulty` is the one float, and it is not money).

## The contract (verbatim)

```
GET /health                -> {"ok":true,"height":<int>,"chain":"main","txs_indexed":<int>}
GET /api/v0/address/<addr> -> {"address":<str>,"balance_sats":<int>,"tx_count":<int>,"truncated":true|false,"txs":[{"txid":<str>,"height":<int>,"time":<int>,"value_sats":<int>,"direction":"in"|"out"}]}
# address history: newest first, cap 100 entries, truncated=true when more exist; time = block time of the confirmed block
GET /api/v0/tx/<txid>      -> {"txid":<str>,"height":<int>|null,"confirmations":<int>,"blockhash":<str>|null,"size":<int>,"hex":<str>,"vin":[{"txid":<str>|null,"vout":<int>|null,"addresses":[<str>],"value_sats":<int>|null,"coinbase":true|false}],"vout":[{"n":<int>,"addresses":[<str>],"value_sats":<int>,"script_type":"p2pkh"|"p2sh"|"data"|"other"}]}
GET /api/v0/block/<h>      -> {"height":<int>,"hash":<str>,"merkleroot":<str>,"ntx":<int>,"time":<int>,"difficulty":<float>,"txids_truncated":true|false,"txids":[<str>]}
# <h> = block height OR block hash; txids capped at 500 entries, txids_truncated=true when more exist
GET /api/v0/proof/<height>/<txid> -> {"height":<int>,"blockhash":<str>,"txid":<str>,"merkleroot":<str>,"merkle":[<str>],"pos":<int>}
# 404 JSON {"error":<str>} when the txid is not in that block
GET /api/v0/search?q=      -> {"type":"address"|"tx"|"block"|"unknown","query":<str>}
GET /api/v0/stats          -> {"height":<int>,"total_txs":<int>,"address_count":<int>}
Errors are ALWAYS JSON {"error":<str>} with status 404|413|429|500; a handler never drops a connection.
```

Plain-English reading of the same contract:

- **`/health`** - a liveness probe. It answers `200` with `ok:true` once the
  service is up. The installer's health gate polls this.
- **`/api/v0/address/<addr>`** - the balance and the history of one
  address. History is **newest first**, capped at **100** entries; when
  more exist, `truncated` is `true` (so a client knows to keep paging or to
  narrow the query rather than to assume it has seen everything).
  `time` is the **block time** of the confirmed block the transaction is in.
- **`/api/v0/tx/<txid>`** - one transaction, in full: raw `hex`, every
  input and output. `height` is `null` for a transaction that is not
  confirmed yet; `confirmations` is the count.
- **`/api/v0/block/<h>`** - `<h>` is a block **height or block hash**.
  `txids` is capped at **500** entries and `txids_truncated` says whether
  the list was cut.
- **`/api/v0/proof/<height>/<txid>`** - the Merkle proof that a transaction
  is in a given block: the sibling hashes and the position of the
  transaction in the tree. A wallet can verify this against the block
  header's merkle root without trusting the indexer. If the txid is not in
  that block, the answer is a `404` with a JSON error body.
- **`/api/v0/search?q=`** - a best guess at what the query string is:
  an address, a transaction, a block, or `unknown`.
- **`/api/v0/stats`** - how far the index has got: height, total
  transactions indexed, and how many distinct addresses are indexed.

Errors are **always** JSON `{"error":<str>}` with a status of
**404**, **413** (payload too large), **429** (rate limited) or **500**. A
handler never drops a connection without answering.

## Try each route

The examples below use `indexer.example.org` as the host - replace it with
your own. On the box itself the indexer listens on `127.0.0.1:18711`
unless you changed `MAZA_INDEXER_BIND_HOST` / `MAZA_INDEXER_BIND_PORT`.

```sh
# GET /health
curl -s https://indexer.example.org/indexer/health

# GET /api/v0/address/<addr>
curl -s "https://indexer.example.org/indexer/api/v0/address/<address>"

# GET /api/v0/tx/<txid>
curl -s "https://indexer.example.org/indexer/api/v0/tx/<txid>"

# GET /api/v0/block/<h>   (height or block hash)
curl -s "https://indexer.example.org/indexer/api/v0/block/1000"
curl -s "https://indexer.example.org/indexer/api/v0/block/<blockhash>"

# GET /api/v0/proof/<height>/<txid>
curl -s "https://indexer.example.org/indexer/api/v0/proof/1000/<txid>"

# GET /api/v0/search?q=
curl -s "https://indexer.example.org/indexer/api/v0/search?q=<address-or-txid>"

# GET /api/v0/stats
curl -s https://indexer.example.org/indexer/api/v0/stats
```

Without the reverse proxy (running directly on the host):

```sh
curl -s http://127.0.0.1:18711/health
curl -s http://127.0.0.1:18711/api/v0/stats
```

Every response body is JSON. Add `-i` to any of the commands above if you
want to see the HTTP status line as well - for example, a `404` with a
JSON `{"error": ...}` body is a normal answer for a transaction that is
not in the block you asked about.
