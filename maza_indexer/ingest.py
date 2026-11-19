"""Resumable chain crawl from a mazad JSON-RPC into the sqlite store.

Identity model (scope note, not a defect): the indexer NEVER validates PoW
(MinotaurX/Hive is too heavy off-device); it trusts the daemon's chain
exactly like ElectrumX does.  Header checks are IDENTITY ONLY, per block:
  1. double_sha256(header)[::-1].hex() == the RPC-provided block hash
     (compare in DISPLAY order -- see hashutil's convention docstring);
  2. the header's prevhash equals the hash of the previously stored block
     (all-zero for height 0, the genesis convention).
ANY mismatch is a loud abort (ReorgAbort -> nonzero exit via __main__):
a reorg or manual intervention happened; the operator decides.

Cursor: datadir/cursor.json {"height": N, "hash": ".."} -- the last fully
ingested block -- written ATOMICALLY after every block commit
(tmp + fsync + os.replace + dir fsync, the walletbench persist pattern).
A fresh datadir starts at height 0.

Day-0 probe (parent-measured 2026-11-18 on samihost): getblock <hash> 2
returns FULL transactions with txindex OFF; there is NO "ntx" field at
verbosity 2 on this build -- ntx is counted from the tx array.

vout scripts: P2PKH 76a914<20>88ac, P2SH a914<20>87, OP_RETURN 6a... (no
address, type "data"), anything else type "other" with no address.
Values arrive as decimal MAZA floats from RPC and are converted with
Decimal (exact), never float arithmetic -- money is int sats everywhere.
"""

import json
import os
import struct
import sys
import time
from decimal import Decimal
from typing import Callable, Dict, Optional

from . import config as config_mod
from .hashutil import base58check_encode, double_sha256, hash160
from .rpc import JsonRpcClient
from .store import Store

# Version bytes FETCHED from the repo's ElectrumX coin profile, never from
# memory: P2PKH 50 (indexer/maza_coin.py:47), P2SH 9 (indexer/maza_coin.py:48).
P2PKH_VERSION_BYTE = 50
P2SH_VERSION_BYTE = 9

_SATS = Decimal(100000000)


class ReorgAbort(Exception):
    """Header identity/prevhash mismatch -- loud stop, operator decision."""


def parse_header(header_hex: str) -> Dict[str, object]:
    raw = bytes.fromhex(header_hex)
    if len(raw) != 80:
        raise ValueError(f"header must be 80 bytes, got {len(raw)}")
    return {
        "version": struct.unpack("<I", raw[0:4])[0],
        # Serialized (internal) order -> display via reversal, same convention
        # as every RPC-provided hash.
        "prevhash_display": raw[4:36][::-1].hex(),
        "merkleroot_display": raw[36:68][::-1].hex(),
        "time": struct.unpack("<I", raw[68:72])[0],
    }


def parse_script(script_hex: str):
    """-> (script_type, addresses).  Version bytes from indexer/maza_coin.py
    (:47 P2PKH=50, :48 P2SH=9)."""
    try:
        b = bytes.fromhex(script_hex)
    except ValueError:
        return "other", []
    if (len(b) == 25 and b[0] == 0x76 and b[1] == 0xA9 and b[2] == 0x14
            and b[23] == 0x88 and b[24] == 0xAC):
        return "p2pkh", [base58check_encode(P2PKH_VERSION_BYTE, b[3:23])]
    if len(b) == 23 and b[0] == 0xA9 and b[1] == 0x14 and b[22] == 0x87:
        return "p2sh", [base58check_encode(P2SH_VERSION_BYTE, b[2:22])]
    if b[:1] == b"\x6a":
        return "data", []
    return "other", []


def value_to_sats(value) -> int:
    """RPC decimal MAZA -> int sats, exactly (no float math on money)."""
    d = Decimal(str(value)) * _SATS
    sats = int(d)
    if d != sats:
        raise ValueError(f"sub-satoshi value {value!r} cannot happen on MAZA")
    if sats < 0:
        raise ValueError(f"negative vout value {value!r}")
    return sats


def parse_txs(block: Dict) -> list:
    """Verbosity-2 block -> store.add_block tx dicts."""
    out = []
    for tx in block.get("tx", []):
        txid = tx.get("txid")
        if not txid:
            raise ValueError("verbosity-2 tx object without txid")
        vouts = []
        for n, vout in enumerate(tx.get("vout", [])):
            script = (vout.get("scriptPubKey") or {}).get("hex", "")
            script_type, addresses = parse_script(script)
            vouts.append({"vout": n, "addresses": addresses,
                          "value_sats": value_to_sats(vout.get("value", 0)),
                          "script_type": script_type})
        vins = []
        for vin in tx.get("vin", []):
            if "coinbase" in vin:
                vins.append({"prev_txid": None, "prev_vout": None,
                             "coinbase": True})
            else:
                vins.append({"prev_txid": vin.get("txid"),
                             "prev_vout": vin.get("vout"),
                             "coinbase": False})
        out.append({"txid": txid, "hex": tx.get("hex", ""),
                    "vouts": vouts, "vins": vins})
    return out


def atomic_write_json(path: str, payload: Dict) -> None:
    """tmp + fsync + os.replace + dir fsync (walletbench persist pattern)."""
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(json.dumps(payload).encode("utf-8"))
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    dir_fd = os.open(os.path.dirname(path) or ".", os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


class Ingestor:
    def __init__(self, store: Store, rpc, cfg: config_mod.IndexerConfig,
                 poll_seconds: float = 30.0,
                 sleep_fn: Callable[[float], None] = time.sleep):
        self.store = store
        self.rpc = rpc
        self.cfg = cfg
        self.poll_seconds = poll_seconds
        self.sleep_fn = sleep_fn

    # -- cursor ----------------------------------------------------------
    def load_cursor(self) -> Dict[str, object]:
        path = self.cfg.cursor_path
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                data = json.loads(fh.read())
            return {"height": int(data.get("height", -1)),
                    "hash": str(data.get("hash", ""))}
        return {"height": -1, "hash": ""}

    def save_cursor(self, height: int, block_hash: str) -> None:
        os.makedirs(self.cfg.datadir, exist_ok=True)
        atomic_write_json(self.cfg.cursor_path,
                          {"height": height, "hash": block_hash})

    # -- crawl -----------------------------------------------------------
    def previous_stored_hash(self, height: int) -> Optional[str]:
        # Through the store's locked accessor: the API serves concurrently
        # on other threads while the crawler runs.
        return self.store.block_hash_at(height)

    def check_headers(self, height: int, block: Dict,
                      header_hex: str) -> None:
        parsed = parse_header(header_hex)
        got = double_sha256(bytes.fromhex(header_hex))[::-1].hex()
        want = block.get("hash")
        if want and got != want:
            raise ReorgAbort(
                f"height {height}: header identity mismatch "
                f"(computed {got}, daemon says {want}) -- the chain the node "
                f"serves no longer matches what we stored; a reorg or manual "
                f"step is needed.  Run --reorg-delete <height> or investigate.")
        prev = self.previous_stored_hash(height - 1)
        if height == 0:
            if bytes.fromhex(header_hex)[4:36] != b"\x00" * 32:
                raise ReorgAbort(
                    "height 0: genesis prevhash is not all-zero")
        elif prev is not None and parsed["prevhash_display"] != prev:
            raise ReorgAbort(
                f"height {height}: prevhash {parsed['prevhash_display']} "
                f"!= stored block {height - 1} hash {prev} -- reorg or "
                f"manual step needed (--reorg-delete <height>).")

    def ingest_block(self, height: int, block: Dict) -> Dict:
        raw_hex = block.get("hex") or ""
        if len(raw_hex) >= 160:
            header_hex = raw_hex[:160]
        else:
            header = self.rpc.call("getblockheader", [block["hash"], 2])
            header_hex = header["rawheader"]
        self.check_headers(height, block, header_hex)
        txs = parse_txs(block)
        parsed = parse_header(header_hex)
        record = {
            "height": height,
            "hash": block["hash"],
            "header_hex": header_hex,
            "merkleroot": str(block.get("merkleroot")
                              or parsed["merkleroot_display"]),
            # No "ntx" field at verbosity 2 on this build (Day-0 probe):
            # count from the tx array.
            "ntx": len(block.get("tx", [])),
            "time": int(block.get("time") or parsed["time"]),
            "difficulty": float(block.get("difficulty", 0.0)),
            "txs": txs,
        }
        self.store.add_block(
            record["height"], record["hash"], record["header_hex"],
            record["merkleroot"], record["ntx"], record["time"],
            record["difficulty"], txs)
        self.save_cursor(height, record["hash"])
        return record

    def run(self, max_blocks: Optional[int] = None) -> Dict[str, object]:
        """Crawl from the cursor to the tip; then poll for new blocks.
        max_blocks bounds the crawl (tests / operational slices)."""
        crawled = 0
        while True:
            info = self.rpc.call("getblockchaininfo", [])
            tip = int(info.get("blocks", 0))
            cur = self.load_cursor()
            height = int(cur["height"]) + 1
            if height > tip:
                if max_blocks is not None:
                    break
                self.sleep_fn(self.poll_seconds)
                continue
            # Batch the block-hash lookups (MAZA_INDEXER_BATCH); the span is
            # INCLUSIVE of the tip (tip + 1 as the exclusive end).
            heights = list(range(height,
                                 min(tip + 1, height + self.cfg.batch)))
            if max_blocks is not None:
                heights = heights[: max_blocks - crawled]
            hashes = {}
            for h in heights:
                hashes[h] = self.rpc.call("getblockhash", [h])
            bounded = False
            for h in heights:
                block = self.rpc.call("getblock", [hashes[h], 2])
                rec = self.ingest_block(h, block)
                crawled += 1
                print(f"INGEST height={rec['height']} hash={rec['hash']}"
                      f" txs={rec['ntx']}", file=sys.stderr)
                if max_blocks is not None and crawled >= max_blocks:
                    bounded = True
                    break
            if bounded:
                break
            if int(self.load_cursor()["height"]) >= tip:
                break  # caught up; outer loop re-decides crawl vs poll
        return {"synced_to": self.load_cursor()["height"],
                "crawled": crawled}
