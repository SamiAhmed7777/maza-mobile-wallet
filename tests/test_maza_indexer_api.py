"""Offline API tests: ThreadingHTTPServer on 127.0.0.1 port 0, driven with
http.client.  Covers every contract route, the 404/413/429/500 JSON paths,
and the catch-all guarantee that a handler exception never drops the
connection.  No network beyond loopback; the chain fixture comes from
test_maza_indexer_core (same synthesized 12-block chain).
"""

import http.client
import json
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from maza_indexer.api import IndexerApp, RateLimiter, serve
from maza_indexer.config import IndexerConfig
from maza_indexer.verify import verify_merkle_proof

from test_maza_indexer_core import (ADDR_A, ADDR_B, ADDR_C, ADDR_D,
                                    make_config, ingest_chain)

SAT = 100000000


def _json_body(resp):
    return json.loads(resp.read().decode("utf-8"))


class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="idx-api")
        cls.cfg, cls.store, _ing = ingest_chain(cls._tmp.name)
        cls.app = IndexerApp(cls.store, cls.cfg)
        cls.server = serve(cls.app, "127.0.0.1", 0)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.store.close()
        cls._tmp.cleanup()

    def _get(self, path, method="GET", body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, path, body=body)
            resp = conn.getresponse()
            return resp.status, _json_body(resp)
        finally:
            conn.close()

    # -- contract routes ------------------------------------------------
    def test_health(self):
        status, obj = self._get("/health")
        self.assertEqual(status, 200)
        self.assertEqual(obj, {"ok": True, "height": 11, "chain": "main",
                               "txs_indexed": 13})

    def test_address_full_payload(self):
        status, obj = self._get(f"/api/v0/address/{ADDR_A}")
        self.assertEqual(status, 200)
        self.assertEqual(obj["address"], ADDR_A)
        self.assertEqual(obj["balance_sats"], 400000000)
        self.assertEqual(obj["tx_count"], 4)
        self.assertFalse(obj["truncated"])
        self.assertEqual(len(obj["txs"]), 4)
        # newest first; entries carry exactly the contract keys
        heights = [t["height"] for t in obj["txs"]]
        self.assertEqual(heights, [3, 2, 1, 0])
        entry = obj["txs"][0]
        self.assertEqual(set(entry), {"txid", "height", "time",
                                      "value_sats", "direction"})
        self.assertIsInstance(entry["time"], int)
        self.assertIsInstance(entry["value_sats"], int)

    def test_address_404(self):
        status, obj = self._get("/api/v0/address/MNopeNopeNopeNopeNotHereX")
        self.assertEqual(status, 404)
        self.assertIn("error", obj)

    def test_tx_vin_resolution_and_coinbase(self):
        chain = __import__("test_maza_indexer_core").build_chain()
        t3 = chain[3]["txs"][0]["txid"]
        status, obj = self._get(f"/api/v0/tx/{t3}")
        self.assertEqual(status, 200)
        self.assertEqual(obj["height"], 3)
        self.assertEqual(obj["confirmations"], 9)
        self.assertEqual(obj["size"], len(bytes.fromhex(obj["hex"])))
        self.assertEqual(len(obj["vin"]), 2)
        for vin in obj["vin"]:
            self.assertFalse(vin["coinbase"])
            self.assertEqual(vin["addresses"], [ADDR_B])
            self.assertEqual(vin["value_sats"], 2 * SAT)
        self.assertEqual([v["n"] for v in obj["vout"]], [0, 1, 2])
        self.assertEqual(obj["vout"][2]["addresses"], [ADDR_C])
        # Coinbase tx: vin row is the null-shape contract entry.
        cb0 = chain[0]["txs"][0]["txid"]
        status, obj = self._get(f"/api/v0/tx/{cb0}")
        self.assertEqual(status, 200)
        self.assertEqual(obj["vin"], [{"txid": None, "vout": None,
                                       "addresses": [], "value_sats": None,
                                       "coinbase": True}])

    def test_tx_404(self):
        status, obj = self._get("/api/v0/tx/" + "ab" * 32)
        self.assertEqual(status, 404)
        self.assertIn("error", obj)

    def test_block_by_height_and_by_hash(self):
        from test_maza_indexer_core import build_chain
        blk = build_chain()[3]
        status, obj = self._get("/api/v0/block/3")
        self.assertEqual(status, 200)
        self.assertEqual(obj["height"], 3)
        self.assertEqual(obj["hash"], blk["hash"])
        self.assertEqual(obj["merkleroot"], blk["merkleroot"])
        self.assertEqual(obj["ntx"], 1)
        self.assertIsInstance(obj["difficulty"], float)
        self.assertFalse(obj["txids_truncated"])
        self.assertEqual(len(obj["txids"]), obj["ntx"])
        # Same block by HASH.
        status2, obj2 = self._get(f"/api/v0/block/{blk['hash']}")
        self.assertEqual(status2, 200)
        self.assertEqual(obj2, obj)
        status3, obj3 = self._get("/api/v0/block/999999")
        self.assertEqual(status3, 404)
        self.assertIn("error", obj3)

    def test_block_txids_truncated_over_500(self):
        # A synthetic block with 501 txs exercises the 500 cap honestly.
        from test_maza_indexer_core import (make_tx, indep_merkle_root,
                                            script_p2pkh,
                                            H_A as _HA)
        import struct as _s
        txs = [make_tx([(_s.pack("<I", i) + b"\x00" * 28, 0xFFFFFFFF,
                         b"\x01")], [(0, b"")]) for i in range(501)]
        root = indep_merkle_root([t["internal"] for t in txs])
        header = (_s.pack("<I", 1) + b"\x11" * 32 + root
                  + _s.pack("<III", 1700002000, 0x207FFFFF, 12))
        tx_dicts = [{"txid": t["txid"], "hex": t["hex"],
                     "vouts": [], "vins": [{"prev_txid": None,
                                            "prev_vout": None,
                                            "coinbase": True}]}
                    for t in txs]
        self.store.add_block(12, "ab" * 32, header.hex(), root[::-1].hex(),
                             501, 1700002000, 4.0, tx_dicts)
        try:
            status, obj = self._get("/api/v0/block/12")
            self.assertEqual(status, 200)
            self.assertEqual(obj["ntx"], 501)
            self.assertTrue(obj["txids_truncated"])
            self.assertEqual(len(obj["txids"]), 500)
            self.assertEqual(obj["txids"][0], txs[0]["txid"])
        finally:
            self.store.reorg_delete(12)

    def test_proof_validated_two_ways(self):
        from test_maza_indexer_core import build_chain, indep_merkle_root
        chain = build_chain()
        t3 = chain[3]["txs"][0]["txid"]
        status, obj = self._get(f"/api/v0/proof/3/{t3}")
        self.assertEqual(status, 200)
        self.assertEqual(obj["height"], 3)
        self.assertEqual(obj["txid"], t3)
        self.assertEqual(obj["blockhash"], chain[3]["hash"])
        self.assertEqual(obj["merkleroot"], chain[3]["merkleroot"])
        self.assertIsInstance(obj["pos"], int)
        # (1) verify.py
        self.assertTrue(verify_merkle_proof(t3, obj["merkleroot"],
                                            obj["merkle"], obj["pos"]))
        # (2) the test's OWN independent verifier
        self.assertTrue(_indep_verify(t3, obj["merkleroot"],
                                      obj["merkle"], obj["pos"]))
        # 404s: wrong txid for the block; bad height.
        t1 = chain[1]["txs"][1]["txid"]
        status, obj = self._get(f"/api/v0/proof/3/{t1}")
        self.assertEqual(status, 404)
        self.assertIn("error", obj)
        status, obj = self._get(f"/api/v0/proof/999/{t3}")
        self.assertEqual(status, 404)

    def test_search(self):
        chain = __import__("test_maza_indexer_core").build_chain()
        for q, want in ((ADDR_A, "address"),
                        (chain[2]["txs"][0]["txid"], "tx"),
                        ("5", "block"),
                        (chain[0]["hash"], "block"),
                        ("zzz-not-here", "unknown")):
            status, obj = self._get(f"/api/v0/search?q={q}")
            self.assertEqual(status, 200)
            self.assertEqual(obj, {"type": want, "query": q})

    def test_stats(self):
        status, obj = self._get("/api/v0/stats")
        self.assertEqual(status, 200)
        self.assertEqual(obj, {"height": 11, "total_txs": 13,
                               "address_count": 5})

    # -- error discipline -------------------------------------------------
    def test_unknown_route_404_json(self):
        status, obj = self._get("/api/v0/unknown")
        self.assertEqual(status, 404)
        self.assertIn("error", obj)

    def test_post_is_405_json(self):
        status, obj = self._get("/health", method="POST", body="x")
        self.assertEqual(status, 405)
        self.assertIn("error", obj)

    def test_413_on_oversized_body(self):
        status, obj = self._get("/health", body="x" * 70000)
        self.assertEqual(status, 413)
        self.assertIn("error", obj)

    def test_429_rate_limit_then_recovery(self):
        app = IndexerApp(self.store, self.cfg,
                         rate_limiter=RateLimiter(2))  # 2 req/min
        server = serve(app, "127.0.0.1", 0)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            statuses = []
            for _ in range(4):
                conn = http.client.HTTPConnection("127.0.0.1", port,
                                                  timeout=10)
                conn.request("GET", "/health")
                resp = conn.getresponse()
                statuses.append(resp.status)
                resp.read()
                conn.close()
            self.assertEqual(statuses, [200, 200, 429, 429])
        finally:
            server.shutdown()
            server.server_close()

    def test_500_json_and_connection_survives(self):
        class BrokenStore:
            def __getattr__(self, name):
                def boom(*a, **k):
                    raise RuntimeError(f"boom {name}")
                return boom

        app = IndexerApp(BrokenStore(), self.cfg,
                         rate_limiter=RateLimiter(1000))
        server = serve(app, "127.0.0.1", 0)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            conn.request("GET", "/api/v0/stats")
            resp = conn.getresponse()
            status, obj = resp.status, _json_body(resp)
            conn.close()
            self.assertEqual(status, 500)
            self.assertIn("error", obj)
            # The catch-all did NOT drop the connection: a fresh request on
            # a new connection still works.
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            conn.request("GET", "/health")
            resp = conn.getresponse()
            self.assertEqual(resp.status, 500)  # BrokenStore /health too
            resp.read()
            conn.close()
        finally:
            server.shutdown()
            server.server_close()


def _indep_verify(txid_hex, merkleroot_hex, branch, pos):
    """The test's own independent merkle verifier (NOT verify.py)."""
    from maza_indexer.hashutil import double_sha256
    current = bytes.fromhex(txid_hex)[::-1]
    p = pos
    for sib in branch:
        s = bytes.fromhex(sib)[::-1]
        if p & 1:
            current = double_sha256(s + current)
        else:
            current = double_sha256(current + s)
        p >>= 1
    return current[::-1].hex() == merkleroot_hex.lower()


if __name__ == "__main__":
    unittest.main()
