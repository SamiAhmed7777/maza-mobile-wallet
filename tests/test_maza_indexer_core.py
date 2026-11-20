"""Offline core tests for maza_indexer: hashes, base58check, ingest of a
synthesized 12-block chain, cursor resume, abort paths, the hand-computed
addr_tx table, restart invariance, and reorg-delete consistency.

MockRpc only -- no network in unit tests.  The test recomputes every merkle
root with its OWN independent loop (written twice on purpose: proofs.py vs
this loop; any disagreement fails).
"""

import importlib.util
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from maza_indexer.config import IndexerConfig
from maza_indexer.hashutil import (base58check_decode, base58check_encode,
                                   double_sha256, hash160, ripemd160_pure)
from maza_indexer.ingest import Ingestor, ReorgAbort, parse_header, value_to_sats
from maza_indexer.rpc import JsonRpcClient, MockRpc, RpcError
from maza_indexer.store import Store, StoreIntegrityError

# ---------------------------------------------------------------------------
# Real-mainnet fixture pin source.  The repo's ElectrumX coin profile carries
# genuine headers from BOTH PoW eras; we reuse them to pin the display/internal
# byte-order convention (indexer/maza_coin.py:67-104).
# ---------------------------------------------------------------------------
_FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "indexer", "maza_coin.py")
_spec = importlib.util.spec_from_file_location("maza_coin_fixture",
                                               _FIXTURE_PATH)
_maza_coin = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_maza_coin)

# Real public chain address (DECISIONS.md D7/D9 bench context; the parent
# brief pins this exact address).
BENCH_ADDRESS = "MWRVvgWrLRqyEEQSm7J8NuYor1X9J4J9Fa"

# ---------------------------------------------------------------------------
# Synthesized 12-block chain (offline fixture).
# ---------------------------------------------------------------------------


def _fixture_addr(tag, version=50):
    return base58check_encode(version, hash160(b"I1-fixture-" + tag))


H_A = hash160(b"I1-fixture-A")
H_B = hash160(b"I1-fixture-B")
H_C = hash160(b"I1-fixture-C")
H_D = hash160(b"I1-fixture-D")
H_E = hash160(b"I1-fixture-E")
ADDR_A = base58check_encode(50, H_A)
ADDR_B = base58check_encode(50, H_B)
ADDR_C = base58check_encode(50, H_C)
ADDR_D = base58check_encode(50, H_D)
ADDR_E = base58check_encode(9, H_E)

SAT = 100000000  # 1 MAZA in sats


def script_p2pkh(h):
    return b"\x76\xa9\x14" + h + b"\x88\xac"


def script_p2sh(h):
    return b"\xa9\x14" + h + b"\x87"


def script_opret(data):
    return b"\x6a" + bytes([len(data)]) + data


def script_other():
    return b"\x51"  # OP_TRUE: unrecognized output shape -> "other"


def _varint(n):
    if n < 0xFD:
        return bytes([n])
    if n <= 0xFFFF:
        return b"\xfd" + struct.pack("<H", n)
    return b"\xfe" + struct.pack("<I", n)


def make_tx(inputs, outputs, locktime=0):
    """inputs: [(prev_txid_internal_32, prev_vout, script)]
    outputs: [(value_sats, script)] -> serialized tx dict with real txid."""
    raw = struct.pack("<I", 1) + _varint(len(inputs))
    for ptxid, pvout, s in inputs:
        raw += ptxid + struct.pack("<I", pvout) + _varint(len(s)) + s
        raw += struct.pack("<I", 0xFFFFFFFF)
    raw += _varint(len(outputs))
    for value, s in outputs:
        raw += struct.pack("<q", value) + _varint(len(s)) + s
    raw += struct.pack("<I", locktime)
    internal = double_sha256(raw)
    return {"txid": internal[::-1].hex(), "hex": raw.hex(),
            "internal": internal}


def indep_merkle_root(txids_internal):
    """The test's OWN merkle loop (independent of maza_indexer.proofs on
    purpose).  Bitcoin Core pairing: concat left+right, double-SHA256; odd
    node duplicates itself."""
    level = list(txids_internal)
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [double_sha256(level[i] + level[i + 1])
                 for i in range(0, len(level), 2)]
    return level[0]


def make_block(height, prev_internal, txs, mtime):
    root = indep_merkle_root([t["internal"] for t in txs])
    header = (struct.pack("<I", 1) + prev_internal + root
              + struct.pack("<III", mtime, 0x207FFFFF, height))
    block_hash = double_sha256(header)[::-1].hex()
    block_hex = header.hex() + "".join(t["hex"] for t in txs)
    return {"height": height, "hash": block_hash,
            "prev_internal": prev_internal,
            "merkleroot": root[::-1].hex(),
            "header_hex": header.hex(), "block_hex": block_hex,
            "time": mtime, "txs": txs}


def build_chain():
    """12 blocks; see the hand-computed table in the class docstring below."""
    zeros = b"\x00" * 32
    cb0 = make_tx([(zeros, 0xFFFFFFFF, b"\x01\x00")],
                  [(5 * SAT, script_p2pkh(H_A)),
                   (0, script_opret(b"I1 genesis"))])
    cb1 = make_tx([(zeros, 0xFFFFFFFF, b"\x01\x01")],
                  [(2 * SAT, script_p2pkh(H_B))])
    t1 = make_tx([(cb0["internal"], 0, b"")],
                 [(2 * SAT, script_p2pkh(H_B)),
                  (3 * SAT, script_p2pkh(H_A))])
    t2 = make_tx([(t1["internal"], 1, b"")],
                 [(3 * SAT, script_p2pkh(H_A))])  # self-transfer, net 0
    t3 = make_tx([(cb1["internal"], 0, b""), (t1["internal"], 0, b"")],
                 [(1 * SAT, script_p2pkh(H_A)),
                  (2 * SAT, script_p2pkh(H_B)),
                  (1 * SAT, script_p2pkh(H_C))])
    cb4 = make_tx([(zeros, 0xFFFFFFFF, b"\x01\x04")],
                  [(int(5.5 * SAT), script_p2pkh(H_C))])
    cb5 = make_tx([(zeros, 0xFFFFFFFF, b"\x01\x05")],
                  [(5 * SAT, script_p2sh(H_E))])
    cb6 = make_tx([(zeros, 0xFFFFFFFF, b"\x01\x06")],
                  [(5 * SAT, script_p2pkh(H_D)), (0, script_other())])
    rest = [make_tx([(zeros, 0xFFFFFFFF, bytes([1, h]))],
                    [(5 * SAT, script_p2pkh(H_D))]) for h in range(7, 12)]

    blocks = []
    prev = zeros
    txs_per_height = {
        0: [cb0], 1: [cb1, t1], 2: [t2], 3: [t3], 4: [cb4], 5: [cb5],
        6: [cb6], 7: [rest[0]], 8: [rest[1]], 9: [rest[2]], 10: [rest[3]],
        11: [rest[4]],
    }
    for h in range(12):
        blk = make_block(h, prev, txs_per_height[h], 1700000000 + 120 * h)
        blk["rpc_txs"] = [_rpc_tx(t) for t in txs_per_height[h]]
        blocks.append(blk)
        prev = double_sha256(bytes.fromhex(blk["header_hex"]))  # internal
    return blocks


def _rpc_tx(t):
    """A verbosity-2 style tx object (values as JSON-ish floats; vin is
    attached separately from the raw tx bytes by _rpc_block)."""
    return {"txid": t["txid"], "hex": t["hex"], "vout": _rpc_vouts(t)}


def _rpc_vouts(t):
    raw = bytes.fromhex(t["hex"])
    pos = 4
    def varint(p):
        v = raw[p]
        if v < 0xFD:
            return v, p + 1
        if v == 0xFD:
            return struct.unpack_from("<H", raw, p + 1)[0], p + 3
        return struct.unpack_from("<I", raw, p + 1)[0], p + 5
    n_in, pos = varint(pos)
    for _ in range(n_in):
        slen, pos = varint(pos + 36)
        pos += slen + 4
    n_out, pos = varint(pos)
    outs = []
    for _ in range(n_out):
        value = struct.unpack_from("<q", raw, pos)[0]
        slen, pos = varint(pos + 8)
        script = raw[pos:pos + slen].hex()
        pos += slen
        outs.append({"value": value / 1e8, "scriptPubKey": {"hex": script}})
    return outs


def rpc_vins_of(t):
    """Build the RPC vin list from the raw tx's own input section."""
    raw = bytes.fromhex(t["hex"])
    pos = 4
    n_in = raw[pos]
    pos += 1
    vins = []
    for _ in range(n_in):
        prev = raw[pos:pos + 32]
        vout = struct.unpack_from("<I", raw, pos + 32)[0]
        slen = raw[pos + 36]
        script = raw[pos + 37:pos + 37 + slen]
        pos += 37 + slen + 4
        if prev == b"\x00" * 32:
            vins.append({"coinbase": script.hex(), "sequence": 0xFFFFFFFF})
        else:
            vins.append({"txid": prev[::-1].hex(), "vout": vout,
                         "scriptSig": {"hex": script.hex()},
                         "sequence": 0xFFFFFFFF})
    return vins


def make_mock_rpc(blocks, tip=None):
    tip = tip if tip is not None else blocks[-1]["height"]
    by_hash = {blk["hash"]: blk for blk in blocks}

    def _getblock(params):
        blk = by_hash.get(params[0])
        if blk is None:
            raise KeyError(f"no fixture block {params[0]}")
        return _rpc_block(blk)

    return MockRpc({
        "getblockchaininfo": {"chain": "main", "blocks": tip,
                              "headers": tip,
                              "initialblockdownload": False},
        "getblockhash": lambda p: blocks[p[0]]["hash"],
        "getblock": _getblock,
    })


def _rpc_block(blk):
    return {"hash": blk["hash"], "height": blk["height"],
            "hex": blk["block_hex"], "time": blk["time"],
            "difficulty": 4.0, "merkleroot": blk["merkleroot"],
            "tx": [dict(t, vin=rpc_vins_of(t_src))
                   for t, t_src in zip(blk["rpc_txs"], blk["txs"])]}


def make_config(datadir):
    return IndexerConfig.from_env({
        "MAZA_INDEXER_RPC_URL": "http://127.0.0.1:1",
        "MAZA_INDEXER_RPC_USER": "user",
        "MAZA_INDEXER_RPC_PASSWORD": "s3cret-pw",
        "MAZA_INDEXER_DATADIR": datadir,
        "MAZA_INDEXER_BIND": "127.0.0.1:18711",
        "MAZA_INDEXER_BATCH": "24",
        "MAZA_INDEXER_RATE": "60",
    })


def ingest_chain(datadir, max_blocks=12, tip=11):
    cfg = make_config(datadir)
    store = Store(cfg.db_path)
    rpc = make_mock_rpc(build_chain(), tip=tip)
    ing = Ingestor(store, rpc, cfg, poll_seconds=0.001,
                   sleep_fn=lambda s: (_ for _ in ()).throw(
                       AssertionError("poll must not run in tests")))
    ing.run(max_blocks=max_blocks)
    return cfg, store, ing


class TestGetblockheaderFallback(unittest.TestCase):
    """LIVE-DAEMON REGRESSION (witnessed 2026-11-19, first real deployment on
    the samihost mazad): MazaCore 0.16.3 getblockheader takes a BOOLEAN
    verbosity - called with 2 it rejects code -1 "JSON value is not a boolean
    as expected". The REAL node never returns a "hex" field on getblock
    verbosity 2, so every block takes the fallback and a wrong fallback shape
    crash-loops the service on block 0. This test replays the REAL node shape:
    getblock answers WITHOUT hex, getblockheader [hash, False] returns the raw
    80-byte header hex STRING, and a non-False verbosity is rejected like the
    node rejects it."""

    def test_ingests_without_block_hex_via_boolean_getblockheader(self):
        blocks = build_chain()
        by_hash = {blk["hash"]: blk for blk in blocks}
        calls = []

        def _getblock_no_hex(params):
            blk = by_hash.get(params[0])
            if blk is None:
                raise KeyError(f"no fixture block {params[0]}")
            b = _rpc_block(blk)
            b.pop("hex", None)  # the real node shape at verbosity 2
            return b

        def _getblockheader(p):
            calls.append(tuple(p))
            if p[1] is not False:
                raise RuntimeError(
                    "rpc getblockheader error: {'code': -1, 'message': "
                    "'JSON value is not a boolean as expected'}")
            return by_hash[p[0]]["block_hex"][:160]

        cfg = make_config(self.enterContext(tempfile.TemporaryDirectory()))
        store = Store(cfg.db_path)
        rpc = MockRpc({
            "getblockhash": lambda p: blocks[p[0]]["hash"],
            "getblock": _getblock_no_hex,
            "getblockheader": _getblockheader,
            "getblockchaininfo": lambda p: {"blocks": 11, "headers": 11,
                                            "initialblockdownload": False},
        })
        ing = Ingestor(store, rpc, cfg, poll_seconds=0.001,
                       sleep_fn=lambda s: (_ for _ in ()).throw(
                           AssertionError("poll must not run in tests")))
        ing.run(max_blocks=12)
        self.assertTrue(calls, "fallback path must have been exercised")
        self.assertTrue(all(p[1] is False for p in calls),
                        "getblockheader must be called with boolean False")
        self.assertEqual(ing.load_cursor()["height"], 11)
        self.assertEqual(store.counts()["blocks"], 12)


class TestBatchCrawl(unittest.TestCase):
    """IDX-10 batched crawl (2026-11-20): live samihost measured ~209
    blocks/min because each block cost 3 SERIAL rpc round trips.  mazad
    0.16.3 accepts JSON-RPC ARRAY requests (live-probed: 3-item batch in
    0.157s, getblockheader [hash, False] returns the 160-char hex string).
    The crawl window now costs 3 round trips TOTAL instead of 3 per block.
    These tests pin the batching contract without a live node."""

    def test_window_costs_two_batches_when_blocks_carry_hex(self):
        cfg, store, ing = ingest_chain(
            self.enterContext(tempfile.TemporaryDirectory()), max_blocks=6)
        kinds = [[m for m, _ in batch]
                 for batch in ing.rpc.batch_calls]
        self.assertEqual(kinds, [["getblockhash"] * 6, ["getblock"] * 6],
                         "one hash window + one block window, "
                         "no getblockheader needed when hex is present")

    def test_header_window_only_for_blocks_lacking_hex(self):
        blocks = build_chain()
        by_hash = {blk["hash"]: blk for blk in blocks}

        def _getblock_no_hex(params):
            b = _rpc_block(by_hash[params[0]])
            b.pop("hex", None)  # the real node shape at verbosity 2
            return b

        cfg = make_config(self.enterContext(tempfile.TemporaryDirectory()))
        store = Store(cfg.db_path)
        rpc = MockRpc({
            "getblockhash": lambda p: blocks[p[0]]["hash"],
            "getblock": _getblock_no_hex,
            "getblockheader": lambda p: by_hash[p[0]]["block_hex"][:160],
            "getblockchaininfo": lambda p: {"blocks": 11, "headers": 11,
                                            "initialblockdownload": False},
        })
        ing = Ingestor(store, rpc, cfg, poll_seconds=0.001,
                       sleep_fn=lambda s: (_ for _ in ()).throw(
                           AssertionError("poll must not run in tests")))
        ing.run(max_blocks=4)
        kinds = [[m for m, _ in batch] for batch in rpc.batch_calls]
        self.assertEqual(kinds, [["getblockhash"] * 4, ["getblock"] * 4,
                                 ["getblockheader"] * 4],
                         "header window covers exactly the hex-less blocks")
        self.assertTrue(all(p[1] is False for _, p in rpc.batch_calls[2]),
                        "batched getblockheader must keep boolean False")
        self.assertEqual(ing.load_cursor()["height"], 3)
        self.assertEqual(store.counts()["blocks"], 4)
        # ingest only completes when each header hashes to the daemon's
        # block hash (check_headers), so stored-at-all == headers verified.
        for h in range(4):
            self.assertEqual(store.block_hash_at(h), blocks[h]["hash"])

    def test_cursor_advances_per_window_not_per_block_crash_safety(self):
        # crash safety contract: cursor saves are per WINDOW; a mid-window
        # crash replays from the last saved cursor and the store's
        # idempotent same-hash skip absorbs the stored prefix (IDX-9b).
        cfg, store, ing = ingest_chain(
            self.enterContext(tempfile.TemporaryDirectory()), max_blocks=5)
        self.assertEqual(ing.load_cursor()["height"], 4)
        # re-crawl the SAME range with a fresh cursor file: the store's
        # duplicate guard must not double-index (blocks 0..4 already there).
        cur_path = cfg.cursor_path
        saved = json.loads(open(cur_path).read())
        saved["height"] = -1
        saved["hash"] = ""
        with open(cur_path, "w") as fh:
            fh.write(json.dumps(saved))
        ing.run(max_blocks=5)
        self.assertEqual(store.counts()["blocks"], 5,
                         "replay must skip, not double-index")

    def test_batch_transient_error_retries_whole_window(self):
        blocks = build_chain()
        cfg = make_config(self.enterContext(tempfile.TemporaryDirectory()))
        store = Store(cfg.db_path)
        rpc = make_mock_rpc(blocks, tip=11)
        real_call_batch = rpc.call_batch
        attempts = {"n": 0}
        sleeps = []

        def flaky_then_ok(items):
            if attempts["n"] == 0:
                attempts["n"] = 1
                raise RpcError("rpc batch[24] error: {'code': -28, "
                               "'message': 'Loading blocks...'}",
                               daemon_code=-28)
            return real_call_batch(items)

        rpc.call_batch = flaky_then_ok
        ing = Ingestor(store, rpc, cfg, poll_seconds=0.001,
                       sleep_fn=sleeps.append)
        ing.run(max_blocks=3)
        self.assertEqual(attempts["n"], 1, "one transient pause before OK")
        self.assertEqual(len(sleeps), 1, "capped backoff slept once")
        self.assertEqual(store.counts()["blocks"], 3)

    def test_max_blocks_zero_is_an_immediate_noop(self):
        blocks = build_chain()
        cfg = make_config(self.enterContext(tempfile.TemporaryDirectory()))
        store = Store(cfg.db_path)
        rpc = make_mock_rpc(blocks, tip=11)
        ing = Ingestor(store, rpc, cfg, poll_seconds=0.001,
                       sleep_fn=lambda s: (_ for _ in ()).throw(
                           AssertionError("noop must not sleep")))
        summary = ing.run(max_blocks=0)
        self.assertEqual(summary, {"synced_to": -1, "crawled": 0})
        self.assertEqual(rpc.batch_calls, [], "no window fetch on a no-op")
        self.assertEqual(store.counts()["blocks"], 0)

    def test_batch_permanent_error_fails_loud(self):
        blocks = build_chain()
        cfg = make_config(self.enterContext(tempfile.TemporaryDirectory()))
        store = Store(cfg.db_path)
        rpc = make_mock_rpc(blocks, tip=11)
        rpc.call_batch = lambda items: (_ for _ in ()).throw(
            RpcError("rpc batch[24] item 2 getblock error: bad block",
                     daemon_code=-5))
        ing = Ingestor(store, rpc, cfg, poll_seconds=0.001,
                       sleep_fn=lambda s: (_ for _ in ()).throw(
                           AssertionError("permanent errors must not sleep")))
        with self.assertRaises(RpcError):
            ing.run(max_blocks=3)


class TestJsonRpcClientBatchShape(unittest.TestCase):
    """call_batch must validate the daemon's array reply shape loudly
    (IDX-7 defect class: never accept a malformed shape silently)."""

    def _client(self, body):
        c = JsonRpcClient("http://127.0.0.1:1", "u", "p")
        c._post = lambda payload, method, timeout: body
        return c

    def test_happy_path_returns_results_in_item_order(self):
        c = self._client([{"id": 0, "result": "h1", "error": None},
                          {"id": 1, "result": 2, "error": None}])
        self.assertEqual(c.call_batch([("getblockhash", [1]),
                                       ("getblockcount", [])]),
                         ["h1", 2])

    def test_empty_batch_is_local_no_op(self):
        self.assertEqual(self._client(None).call_batch([]), [])

    def test_non_list_reply_fails_loud(self):
        with self.assertRaises(RpcError):
            self._client({"id": 0, "result": None}).call_batch(
                [("getblockcount", [])])

    def test_length_mismatch_fails_loud(self):
        with self.assertRaises(RpcError):
            self._client([{"id": 0, "result": None}]).call_batch(
                [("getblockcount", []), ("getblockcount", [])])

    def test_entry_without_id_fails_loud(self):
        with self.assertRaises(RpcError):
            self._client([{"result": "x"}]).call_batch(
                [("getblockcount", [])])

    def test_out_of_order_ids_fail_loud(self):
        body = [{"id": 1, "result": None, "error": None},
                {"id": 0, "result": None, "error": None}]
        with self.assertRaises(RpcError):
            self._client(body).call_batch([("a", []), ("b", [])])

    def test_id_out_of_range_fails_loud(self):
        with self.assertRaises(RpcError):
            self._client([{"id": 7, "result": None, "error": None}]).call_batch(
                [("getblockcount", [])])

    def test_per_item_error_names_method_and_carries_code(self):
        body = [{"id": 0, "result": None, "error": None},
                {"id": 1, "result": None,
                 "error": {"code": -5, "message": "block not found"}}]
        with self.assertRaises(RpcError) as ctx:
            self._client(body).call_batch([("getblockhash", [1]),
                                           ("getblock", ["zz", 2])])
        self.assertIn("getblock", str(ctx.exception))
        self.assertEqual(ctx.exception.daemon_code, -5)


class TestHandComputedTableDoc:
    """HAND-COMPUTED FIXTURE TABLE (the binding expectations; heights 0-11):

    A (p2pkh):
      cb0 h0  in  +5.0 SAT_M  (coinbase 5 MAZA)          balance running 5
      T1  h1  out -2.0        (spent cb0: 2->B, 3 change->A) => net -2
      T2  h2  in   0          (SPEND-WITH-CHANGE-TO-SELF then SELF-TRANSFER:
                               spends own 3, pays 3 back to self -> net 0,
                               row KEPT with value_sats 0, direction "in")
      T3  h3  in  +1.0
      => balance_sats 4.0 SAT_M = 400000000, tx_count 4

    B (p2pkh):
      cb1 h1 in +2.0; T1 h1 in +2.0; T3 h3 out -2.0 (T3 = MULTI-INPUT
      [cb1 + T1-B-output] / MULTI-OUTPUT [A 1, B 2, C 1])
      => balance_sats 200000000, tx_count 3

    C (p2pkh): T3 h3 in +1.0; cb4 h4 in +5.5 (the Decimal(float) value path)
      => balance_sats 650000000, tx_count 2

    E (p2sh, version byte 9): cb5 h5 in +5.0 => 500000000, tx_count 1
    D (p2pkh): cb6..cb11 in +5.0 x6 => 3000000000, tx_count 6

    Totals: 12 blocks, 13 txs, 5 addresses.
    """


class TestHashutil(unittest.TestCase):
    def test_ripemd160_pure_spec_vectors(self):
        # RIPEMD-160 spec, basic vectors (Dobbertin/Bosselaers/Preneel 1996).
        self.assertEqual(ripemd160_pure(b"").hex(),
                         "9c1185a5c5e9fc54612808977ee8f548b2258d31")
        self.assertEqual(ripemd160_pure(b"abc").hex(),
                         "8eb208f7e05d987a9b044a8e98c6b087f15a0bfc")
        self.assertEqual(ripemd160_pure(b"message digest").hex(),
                         "5d0689ef49d2fae572b881b123a85ffa21595f36")

    def test_ripemd160_hashlib_agreement_when_available(self):
        import hashlib
        try:
            hashlib.new("ripemd160", b"")
        except Exception:
            self.skipTest("hashlib refuses legacy ripemd160 (pure fallback "
                          "is the live path; spec vectors above pin it)")
        import random
        rng = random.Random(1)
        for n in range(0, 200):
            data = bytes(rng.randrange(256) for _ in range(n))
            self.assertEqual(ripemd160_pure(data),
                             hashlib.new("ripemd160", data).digest(),
                             f"len={n}")

    def test_base58check_roundtrip_bench_address(self):
        version, payload = base58check_decode(BENCH_ADDRESS)
        # Version byte fetched from the profile, never from memory:
        # P2PKH_VERSION_BYTE = 50 -- indexer/maza_coin.py:47.
        self.assertEqual(version, _maza_coin.P2PKH_VERSION_BYTE)
        self.assertEqual(version, 50)
        self.assertEqual(base58check_encode(version, payload),
                         BENCH_ADDRESS)
        with self.assertRaises(ValueError):
            base58check_decode(BENCH_ADDRESS[:-1] + "2" if
                               BENCH_ADDRESS[-1] != "2" else
                               BENCH_ADDRESS[:-1] + "3")

    def test_header_identity_convention_pinned_on_real_mainnet_headers(self):
        # Hash byte order: RPC "hash" fields are DISPLAY order;
        # double_sha256 returns INTERNAL order.  The identity check MUST be
        # double_sha256(header)[::-1].hex() == rpc hash.  Pinned against REAL
        # mainnet headers from the repo's fixtures (indexer/maza_coin.py:67-104),
        # both PoW eras.
        for name, header_hex, display_hash in _maza_coin.ALL_FIXTURES:
            computed = double_sha256(bytes.fromhex(header_hex))[::-1].hex()
            self.assertEqual(computed, display_hash,
                             f"fixture {name}: display-order convention")
            # And the WRONG comparison (no reversal) must actually differ --
            # the convention has teeth.
            wrong = double_sha256(bytes.fromhex(header_hex)).hex()
            self.assertNotEqual(wrong, display_hash)

    def test_config_masks_password_everywhere(self):
        cfg = make_config(tempfile.mkdtemp(prefix="idxcfg"))
        self.assertIn("***", repr(cfg))
        self.assertIn("***", str(cfg))
        self.assertNotIn("s3cret-pw", repr(cfg))
        self.assertNotIn("s3cret-pw", str(cfg))


class TestIngest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="idx-core")

    def test_full_ingest_counts_and_stats(self):
        cfg, store, ing = ingest_chain(self.dir)
        try:
            counts = store.counts()
            self.assertEqual(counts["blocks"], 12)
            self.assertEqual(counts["txs"], 13)
            self.assertEqual(counts["addresses"], 5)
            self.assertEqual(store.tip_height(), 11)
            cursor = ing.load_cursor()
            self.assertEqual(cursor["height"], 11)
            self.assertEqual(cursor["hash"],
                             build_chain()[11]["hash"])
        finally:
            store.close()

    def test_cursor_resume_mid_chain(self):
        cfg, store, ing = ingest_chain(self.dir, max_blocks=5)
        self.assertEqual(store.counts()["blocks"], 5)
        store.close()
        # Fresh objects (same files): resumes from the cursor.
        cfg2 = make_config(self.dir)
        store2 = Store(cfg2.db_path)
        rpc2 = make_mock_rpc(build_chain())
        ing2 = Ingestor(store2, rpc2, cfg2, poll_seconds=0.001)
        ing2.run(max_blocks=12)
        try:
            self.assertEqual(store2.counts()["blocks"], 12)
            self.assertEqual(store2.counts()["txs"], 13)
            self.assertEqual(ing2.load_cursor()["height"], 11)
        finally:
            store2.close()

    def test_prevhash_mismatch_aborts_loudly(self):
        chain = build_chain()
        # Tamper block 6's header prevhash (flip a prevhash byte).
        tampered = bytearray(bytes.fromhex(chain[6]["header_hex"]))
        tampered[10] ^= 0xFF
        chain[6]["header_hex"] = bytes(tampered).hex()
        chain[6]["block_hex"] = chain[6]["header_hex"] \
            + chain[6]["block_hex"][160:]
        cfg = make_config(self.dir)
        store = Store(cfg.db_path)
        rpc = make_mock_rpc(chain)
        ing = Ingestor(store, rpc, cfg, poll_seconds=0.001)
        with self.assertRaises(ReorgAbort):
            ing.run(max_blocks=12)
        try:
            self.assertEqual(store.counts()["blocks"], 6)  # 0..5 survive
            self.assertEqual(ing.load_cursor()["height"], 5)
        finally:
            store.close()

    def test_identity_mismatch_aborts_loudly(self):
        chain = build_chain()
        # Daemon reports a hash that the header does not reproduce.
        chain[4]["hash"] = "ff" * 32
        cfg = make_config(self.dir)
        store = Store(cfg.db_path)
        rpc = make_mock_rpc(chain)
        ing = Ingestor(store, rpc, cfg, poll_seconds=0.001)
        with self.assertRaises(ReorgAbort):
            ing.run(max_blocks=12)
        try:
            self.assertEqual(store.counts()["blocks"], 4)
        finally:
            store.close()

    def test_values_are_exact_int_sats(self):
        self.assertEqual(value_to_sats(50.0), 50 * SAT)
        self.assertEqual(value_to_sats(5.5), 550000000)
        self.assertEqual(value_to_sats(0.00000001), 1)
        with self.assertRaises(ValueError):
            value_to_sats(-1)


class TestBalances(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="idx-bal")
        cfg, store, ing = ingest_chain(cls._tmp.name)
        cls.cfg = cfg
        cls.store = store
        cls.chain = build_chain()

    @classmethod
    def tearDownClass(cls):
        cls.store.close()
        cls._tmp.cleanup()

    def _addr_summary(self, addr):
        return self.store.address_summary(addr)

    def test_hand_computed_table(self):
        # See the hand-computed table in TestHandComputedTableDoc above.
        cases = [
            (ADDR_A, 400000000, 4),
            (ADDR_B, 200000000, 3),
            (ADDR_C, 650000000, 2),
            (ADDR_E, 500000000, 1),
            (ADDR_D, 3000000000, 6),
        ]
        for addr, balance, tx_count in cases:
            summary = self._addr_summary(addr)
            self.assertIsNotNone(summary, addr)
            self.assertEqual(summary["balance_sats"], balance, addr)
            self.assertEqual(summary["tx_count"], tx_count, addr)
            # Whole-store integrity on read: signed sum of history rows.
            rows = self.store.address_history(addr, cap=1000)[0]
            signed = sum(r["value_sats"] if r["direction"] == "in"
                         else -r["value_sats"] for r in rows)
            self.assertEqual(signed, balance, addr)
            self.assertEqual(len(rows), tx_count, addr)

    def test_self_transfer_row_kept_zero(self):
        # T2 (height 2, self-transfer 3 -> 3 at A): net 0 -> direction "in",
        # value_sats 0, row kept.
        t2 = build_chain()[2]["txs"][0]["txid"]
        rows = self.store.address_history(ADDR_A, cap=100)[0]
        row = next(r for r in rows if r["txid"] == t2)
        self.assertEqual(row["direction"], "in")
        self.assertEqual(row["value_sats"], 0)
        self.assertEqual(row["height"], 2)

    def test_multi_input_multi_output_directions(self):
        # T3 (height 3): A in +1, B out -2, C in +1.
        t3 = build_chain()[3]["txs"][0]["txid"]
        for addr, direction, value in ((ADDR_A, "in", SAT),
                                       (ADDR_B, "out", 2 * SAT),
                                       (ADDR_C, "in", SAT)):
            rows = self.store.address_history(addr, cap=100)[0]
            row = next(r for r in rows if r["txid"] == t3)
            self.assertEqual(row["direction"], direction, addr)
            self.assertEqual(row["value_sats"], value, addr)

    def test_history_newest_first(self):
        rows = self.store.address_history(ADDR_A, cap=100)[0]
        heights = [r["height"] for r in rows]
        self.assertEqual(heights, sorted(heights, reverse=True))

    def test_data_and_other_script_rows_have_no_address(self):
        # cb0 OP_RETURN output: type "data", no address; cb6 OP_TRUE:
        # type "other".
        cb0 = self.chain[0]["txs"][0]["txid"]
        out_rows = self.store.get_outputs_for_tx(cb0)
        self.assertEqual(out_rows[1]["script_type"], "data")
        self.assertEqual(out_rows[1]["addresses"], [])
        self.assertEqual(out_rows[0]["script_type"], "p2pkh")
        cb6 = self.chain[6]["txs"][0]["txid"]
        out_rows = self.store.get_outputs_for_tx(cb6)
        self.assertEqual(out_rows[1]["script_type"], "other")
        self.assertEqual(out_rows[1]["addresses"], [])


class TestRestartAndReorg(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="idx-reorg")

    def test_restart_invariance_of_vin_resolution(self):
        cfg, store, ing = ingest_chain(self.dir)
        try:
            t3 = build_chain()[3]["txs"][0]["txid"]
            from maza_indexer.api import IndexerApp
            app = IndexerApp(store, cfg)
            before = app.handle("GET", f"/api/v0/tx/{t3}", 0, "t")[1]
            self.assertEqual(len(before["vin"]), 2)
            for vin in before["vin"]:
                self.assertFalse(vin["coinbase"])
                self.assertEqual(vin["addresses"], [ADDR_B])
                self.assertEqual(vin["value_sats"], 2 * SAT)
        finally:
            store.close()
        # Fresh object, SAME files -- the durable outputs table must carry
        # everything the vin resolution needs.
        cfg2 = make_config(self.dir)
        store2 = Store(cfg2.db_path)
        try:
            t3 = build_chain()[3]["txs"][0]["txid"]
            from maza_indexer.api import IndexerApp
            app = IndexerApp(store2, cfg2)
            after = app.handle("GET", f"/api/v0/tx/{t3}", 0, "t")[1]
            self.assertEqual(after["vin"], before["vin"])
            self.assertEqual(after["vout"], [
                {"n": 0, "addresses": [ADDR_A], "value_sats": SAT,
                 "script_type": "p2pkh"},
                {"n": 1, "addresses": [ADDR_B], "value_sats": 2 * SAT,
                 "script_type": "p2pkh"},
                {"n": 2, "addresses": [ADDR_C], "value_sats": SAT,
                 "script_type": "p2pkh"},
            ])
        finally:
            store2.close()

    def test_reorg_delete_is_consistent(self):
        cfg, store, ing = ingest_chain(self.dir)
        try:
            summary = store.reorg_delete(3)
            self.assertEqual(summary["blocks"], 9)  # heights 3..11
            counts = store.counts()
            self.assertEqual(counts["blocks"], 3)
            # Surviving history: cb0, cb1, T1, T2 (heights 0..2).
            a = store.address_summary(ADDR_A)
            self.assertEqual(a["balance_sats"], 300000000)  # 5 - 2 + 0
            self.assertEqual(a["tx_count"], 3)
            b = store.address_summary(ADDR_B)
            self.assertEqual(b["balance_sats"], 400000000)  # cb1 + T1
            self.assertEqual(b["tx_count"], 2)
            # C/D/E lost every row -> recomputed to 0/0.
            for addr in (ADDR_C, ADDR_D, ADDR_E):
                s = store.address_summary(addr)
                self.assertEqual(s["balance_sats"], 0, addr)
                self.assertEqual(s["tx_count"], 0, addr)
            # Un-marking: T1's outputs spent_by cleared (T2 still marks the
            # A-change output).
            t1 = build_chain()[1]["txs"][1]["txid"]
            outs = {o["n"]: o for o in store.get_outputs_for_tx(t1)}
            self.assertEqual(set(outs), {0, 1})
        finally:
            store.close()
        # The full check continues on a reopened store to prove durability.
        cfg2 = make_config(self.dir)
        store2 = Store(cfg2.db_path)
        try:
            t1 = build_chain()[1]["txs"][1]["txid"]
            row = store2.conn.execute(
                "SELECT spent_by FROM outputs WHERE txid=? AND vout=0",
                (t1,)).fetchone()
            self.assertIsNone(row[0])  # un-marked (its spender T3 >= 3)
            row = store2.conn.execute(
                "SELECT spent_by FROM outputs WHERE txid=? AND vout=1",
                (t1,)).fetchone()
            self.assertIsNotNone(row[0])  # still spent by T2 (height 2)
            # Integrity invariant holds across the whole store.
            for (addr,) in store2.conn.execute(
                    "SELECT address FROM addresses").fetchall():
                store2._assert_address_integrity(addr)
        finally:
            store2.close()

    def test_reorg_then_reingest_recovers_the_table(self):
        cfg, store, ing = ingest_chain(self.dir)
        store.reorg_delete(3)
        # The CLI (--reorg-delete) rewinds the cursor to height-1 after the
        # store transaction; mirror that here before re-crawling.
        Ingestor(store, None, cfg).save_cursor(
            2, build_chain()[2]["hash"])
        store.close()
        cfg2 = make_config(self.dir)
        store2 = Store(cfg2.db_path)
        rpc2 = make_mock_rpc(build_chain())
        ing2 = Ingestor(store2, rpc2, cfg2, poll_seconds=0.001)
        ing2.run(max_blocks=12)
        try:
            self.assertEqual(ing2.load_cursor()["height"], 11)
            self.assertEqual(store2.address_summary(ADDR_A)["balance_sats"],
                             400000000)
            self.assertEqual(store2.address_summary(ADDR_B)["balance_sats"],
                             200000000)
            self.assertEqual(store2.address_summary(ADDR_C)["balance_sats"],
                             650000000)
            self.assertEqual(store2.address_summary(ADDR_D)["balance_sats"],
                             3000000000)
            self.assertEqual(store2.address_summary(ADDR_E)["balance_sats"],
                             500000000)
        finally:
            store2.close()

    def test_integrity_assert_fires_on_corruption(self):
        cfg, store, ing = ingest_chain(self.dir)
        try:
            # Corrupt the balance behind the store's back.
            store.conn.execute(
                "UPDATE addresses SET balance_sats = 1 WHERE address=?",
                (ADDR_A,))
            store.conn.commit()
            # The NEXT incremental write touching A (add_block) must trip
            # the on-write signed-sum assert.  (reorg_delete recomputes from
            # the surviving rows, so it HEALS corruption by design.)
            tx = make_tx([(b"\x00" * 32, 0xFFFFFFFF, b"\x01\x63")],
                         [(1 * SAT, script_p2pkh(H_A))])
            tx_dict = {"txid": tx["txid"], "hex": tx["hex"],
                       "vouts": [{"vout": 0, "addresses": [ADDR_A],
                                  "value_sats": SAT,
                                  "script_type": "p2pkh"}],
                       "vins": [{"prev_txid": None, "prev_vout": None,
                                 "coinbase": True}]}
            with self.assertRaises(StoreIntegrityError):
                store.add_block(12, "ff" * 32, "00" * 80, "ee" * 32, 1,
                                1700001440, 4.0, [tx_dict])
        finally:
            store.close()

    def test_header_parse_fields(self):
        blk = build_chain()[5]
        parsed = parse_header(blk["header_hex"])
        self.assertEqual(parsed["time"], blk["time"])
        self.assertEqual(parsed["merkleroot_display"], blk["merkleroot"])
        self.assertEqual(parsed["prevhash_display"],
                         build_chain()[4]["hash"])


class Test5bF7(unittest.TestCase):
    """F7: the legacy vin parser (maza_indexer.api.parse_tx_prevouts) skips
    the segwit marker+flag bytes (0x00 0x01 after the version) so a
    witness-shaped tx parses to the same vin list as its legacy-stripped
    equivalent.  (Future-proofing only today: the live chain has no segwit
    softfork entry -- node-probed 2026-11-19.)"""

    def test_witness_shaped_tx_matches_legacy_parse(self):
        from maza_indexer.api import parse_tx_prevouts
        legacy = make_tx([(b"\x11" * 32, 1, b"\x51\x21")],
                         [(SAT, script_p2pkh(H_A)),
                          (2 * SAT, script_p2pkh(H_B))])
        raw = bytes.fromhex(legacy["hex"])
        self.assertEqual(raw[4], 1)  # sanity: legacy input-count varint
        witness_hex = (raw[:4] + b"\x00\x01" + raw[4:]).hex()
        expected = [{"txid": (b"\x11" * 32)[::-1].hex(), "prev_vout": 1,
                     "coinbase": False}]
        self.assertEqual(parse_tx_prevouts(witness_hex), expected)
        self.assertEqual(parse_tx_prevouts(legacy["hex"]), expected)

    def test_zero_flag_is_not_a_witness_marker(self):
        # raw[4] == 0x00 with raw[5] == 0x00 is NOT marker+flag (the flag
        # must be non-zero): parsed as n_in == 0, no skip.
        from maza_indexer.api import parse_tx_prevouts
        raw = struct.pack("<I", 1) + b"\x00\x00" + b"\xff" * 20
        self.assertEqual(parse_tx_prevouts(raw.hex()), [])


class Test5bF8(unittest.TestCase):
    """F8: MAZA_INDEXER_BIND strict parsing (host:port, bracketed IPv6,
    integer port 1-65535; every violation a one-line ValueError naming
    the env key)."""

    def test_valid_forms_accepted(self):
        cfg = IndexerConfig.from_env({"MAZA_INDEXER_BIND": "127.0.0.1:18711"})
        self.assertEqual((cfg.host, cfg.port), ("127.0.0.1", 18711))
        cfg = IndexerConfig.from_env({"MAZA_INDEXER_BIND": "[::1]:18711"})
        self.assertEqual((cfg.host, cfg.port), ("::1", 18711))
        cfg = IndexerConfig.from_env({"MAZA_INDEXER_BIND": "0.0.0.0:1"})
        self.assertEqual((cfg.host, cfg.port), ("0.0.0.0", 1))

    def test_default_bind_untouched(self):
        cfg = IndexerConfig.from_env({})
        self.assertEqual((cfg.host, cfg.port), ("127.0.0.1", 18711))

    def test_invalid_forms_raise_valueerror_naming_the_key(self):
        for bad in (":18711", "127.0.0.1:notaport", "127.0.0.1:0",
                    "127.0.0.1:99999", "127.0.0.1:", "127.0.0.1",
                    "[::1]", "[::1]18711", "::1:18711"):
            with self.assertRaises(ValueError) as cm:
                IndexerConfig.from_env({"MAZA_INDEXER_BIND": bad})
            self.assertIn("MAZA_INDEXER_BIND", str(cm.exception), bad)


class Test5bF10(unittest.TestCase):
    """F10: python3 -m maza_indexer.verify CLI -- true/false on stdout,
    exit 0/1, exit 2 on usage/parse errors.  Vector from the same
    synthesized chain the proof route serves."""

    def _vector(self):
        from maza_indexer.proofs import merkle_branch_hex
        chain = build_chain()
        # Height 1 holds TWO txs (coinbase + t1): a non-trivial branch.
        txids = [t["txid"] for t in chain[1]["txs"]]
        index = 1  # t1
        merkle, pos = merkle_branch_hex(txids, index)
        self.assertEqual(len(merkle), 1)
        return txids[index], chain[1]["merkleroot"], merkle, pos

    def _run(self, args):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return subprocess.run(
            [sys.executable, "-m", "maza_indexer.verify"] + args,
            capture_output=True, text=True, cwd=root)

    def test_true_vector_exit_0_stdout_true(self):
        txid, root, merkle, pos = self._vector()
        r = self._run([txid, root, json.dumps(merkle), str(pos)])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "true")

    def test_branch_json_via_at_file(self):
        txid, root, merkle, pos = self._vector()
        fd, path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(merkle, fh)
            r = self._run([txid, root, "@" + path, str(pos)])
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.strip(), "true")
        finally:
            os.unlink(path)

    def test_corrupted_branch_exit_1_stdout_false(self):
        txid, root, merkle, pos = self._vector()
        bad = list(merkle)
        bad[0] = "ff" * 32
        r = self._run([txid, root, json.dumps(bad), str(pos)])
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout.strip(), "false")

    def test_bad_usage_and_parse_errors_exit_2(self):
        txid, root, merkle, pos = self._vector()
        cases = [
            [],                       # no args at all
            [txid],                   # too few
            [txid, root, json.dumps(merkle)],          # missing pos
            [txid, root, json.dumps(merkle), "notanint"],  # bad pos
            [txid, root, "{not json", str(pos)],        # bad branch JSON
            [txid, root, "{}", str(pos)],              # branch not a list
        ]
        for args in cases:
            r = self._run(args)
            self.assertEqual(r.returncode, 2, args)
            self.assertNotEqual(r.stdout.strip(), "true", args)

    def test_malformed_proof_inputs_are_usage_errors_exit_2(self):
        # A malformed proof is a USAGE error (exit 2, one-line stderr naming
        # the offending argument) -- it can never be answered "false".
        txid, root, merkle, pos = self._vector()
        cases = [
            (["zz" * 32, root, json.dumps(merkle), str(pos)], "txid"),
            ([txid, "ab" * 31 + "a", json.dumps(merkle), str(pos)],
             "merkleroot"),  # 63 hex chars: wrong length
            ([txid, root, '{"a": 1}', str(pos)], "branch"),  # not a list
            ([txid, root, json.dumps(merkle), "-1"], "pos"),  # negative
        ]
        for args, name in cases:
            r = self._run(args)
            self.assertEqual(r.returncode, 2, args)
            self.assertEqual(r.stdout.strip(), "", args)  # never true/false
            self.assertEqual(r.stderr.strip().count("\n"), 0, args)
            self.assertIn(name, r.stderr, args)

    def test_branch_element_not_exactly_64_hex_exit_2(self):
        # F10 hardening: a branch element that parses as hex but is not
        # EXACTLY 64 chars (one 32-byte sibling hash) is malformed.
        txid, root, merkle, pos = self._vector()
        cases = [
            ["ab" * 32 + "a"],   # 65 hex chars: parses, wrong length
            ["ab" * 33],         # 66 hex chars: parses, wrong length
            ["zz" * 32],         # 64 chars but not hex
        ]
        for bad in cases:
            r = self._run([txid, root, json.dumps(bad), str(pos)])
            self.assertEqual(r.returncode, 2, bad)
            self.assertEqual(r.stdout.strip(), "", bad)  # never true/false
            self.assertEqual(r.stderr.strip().count("\n"), 0, bad)
            self.assertIn("branch", r.stderr, bad)

    def test_pos_at_tree_width_exit_2(self):
        # F10 hardening: the 1-level branch proves a tree of width 2**1=2,
        # so pos == 2 has nonzero residual bits past the branch levels and
        # is unprovable -- usage error, never "false".
        txid, root, merkle, pos = self._vector()
        self.assertEqual(len(merkle), 1)
        r = self._run([txid, root, json.dumps(merkle), "2"])
        self.assertEqual(r.returncode, 2)
        self.assertEqual(r.stdout.strip(), "")
        self.assertEqual(r.stderr.strip().count("\n"), 0)
        self.assertIn("pos", r.stderr)

    def test_valid_shaped_wrong_proof_exit_1_stdout_false(self):
        # Well-formed inputs (64-char hex elements, in-range pos) that do
        # not climb to the root are "false" with exit 1 -- NOT exit 2.
        txid, root, merkle, pos = self._vector()
        bad = list(merkle)
        bad[0] = "ab" * 32
        self.assertNotEqual(bad[0], merkle[0])
        r = self._run([txid, root, json.dumps(bad), str(pos)])
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout.strip(), "false")


if __name__ == "__main__":
    unittest.main()
