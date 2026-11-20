"""Offline API tests: ThreadingHTTPServer on 127.0.0.1 port 0, driven with
http.client.  Covers every contract route, the 404/413/429/500 JSON paths,
and the catch-all guarantee that a handler exception never drops the
connection.  No network beyond loopback; the chain fixture comes from
test_maza_indexer_core (same synthesized 12-block chain).
"""

import http.client
import json
import os
import socket
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from maza_indexer.api import (IndexerApp, RateLimiter, _Handler, bucket_key,
                              derive_client_ip, serve)
from maza_indexer.config import IndexerConfig
from maza_indexer.ingest import reset_loop_progress_for_tests
from maza_indexer.verify import verify_merkle_proof

from test_maza_indexer_core import (ADDR_A, ADDR_B, ADDR_C, ADDR_D,
                                    make_config, ingest_chain)

SAT = 100000000


def _json_body(resp):
    return json.loads(resp.read().decode("utf-8"))


class TestAPI(unittest.TestCase):
    def setUp(self):
        # The crawler-liveness registry is module-global (the real process
        # runs one crawler); another test class in the same run may have
        # marked it. Pin the never-ran state so the exact /health equality
        # below tests THIS class's app, not discovery-order side effects.
        reset_loop_progress_for_tests()

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
        # crawler_progress_age_s is the IDX-9c-ii stall-watchdog liveness
        # field; the test app never runs a crawler, so it is None (null on
        # the wire) here -- the value contract is pinned in
        # test_maza_indexer_liveness.py.
        self.assertEqual(obj, {"ok": True, "height": 11, "chain": "main",
                               "txs_indexed": 13,
                               "crawler_progress_age_s": None})

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


class Test5bF1(unittest.TestCase):
    """F1/F5: rate-limiter identity.  XFF is trusted only from loopback
    peers (the Caddy front door, TRUSTED_PROXIES); Caddy APPENDS the real
    client IP, so the RIGHTMOST parseable entry wins -- the leftmost is
    attacker-rotatable; every key path normalizes IPv6 to /64."""

    def _fake_handler(self, peer, xff):
        headers = {}
        if xff is not None:
            headers["X-Forwarded-For"] = xff
        return SimpleNamespace(client_address=(peer, 5555), headers=headers)

    # -- helper on the handler (fake peer + headers) ----------------------
    def test_rightmost_parseable_wins_on_loopback_peer(self):
        # Caddy appends the observed IP last: "client junk, ..., real-ip".
        h = self._fake_handler("127.0.0.1",
                               "203.0.113.7, 10.0.0.1, 70.41.3.18")
        self.assertEqual(_Handler.client_ip(h), "70.41.3.18")

    def test_non_parseable_xff_entries_are_skipped(self):
        # Junk anywhere in the list is skipped; the parseable entry closest
        # to the right (the trusted proxy's own observation) wins.
        h = self._fake_handler("127.0.0.1", "not-an-ip, , 203.0.113.7")
        self.assertEqual(_Handler.client_ip(h), "203.0.113.7")
        h = self._fake_handler("127.0.0.1", "203.0.113.7, not-an-ip")
        self.assertEqual(_Handler.client_ip(h), "203.0.113.7")

    def test_all_garbage_xff_falls_back_to_peer(self):
        h = self._fake_handler("127.0.0.1", "garbage, worse")
        self.assertEqual(_Handler.client_ip(h), "127.0.0.1")

    def test_no_xff_header_uses_peer(self):
        h = self._fake_handler("127.0.0.1", None)
        self.assertEqual(_Handler.client_ip(h), "127.0.0.1")

    def test_ipv6_loopback_peer_trusts_xff(self):
        h = self._fake_handler("::1", "2001:db8::42, 198.51.100.2")
        self.assertEqual(_Handler.client_ip(h), "198.51.100.2")

    def test_non_loopback_peer_ignores_xff_entirely(self):
        for peer in ("192.0.2.1", "8.8.8.8", "2001:db8::99"):
            h = self._fake_handler(peer, "203.0.113.7")
            self.assertEqual(_Handler.client_ip(h), peer, peer)

    # -- module function ---------------------------------------------------
    def test_derive_client_ip_directly(self):
        self.assertEqual(derive_client_ip("127.0.0.1", " 198.51.100.9 "),
                         "198.51.100.9")
        self.assertEqual(derive_client_ip("127.0.0.1", ""), "127.0.0.1")
        self.assertEqual(derive_client_ip("not-an-ip", "203.0.113.7"),
                         "not-an-ip")
        # Alternate IPv6 loopback spelling normalizes into TRUSTED_PROXIES.
        self.assertEqual(derive_client_ip("0:0:0:0:0:0:0:1", "198.51.100.9"),
                         "198.51.100.9")

    def test_attacker_prepended_junk_keeps_derived_identity(self):
        # F1 rework: leftmost junk is attacker-chosen (Caddy appends the
        # real IP), so prepending it must leave the derived identity -- and
        # therefore the rate-limit bucket -- unchanged.
        real = "198.51.100.9"
        forged = "1.2.3.4, " + real
        self.assertEqual(derive_client_ip("127.0.0.1", forged), real)
        self.assertEqual(bucket_key(derive_client_ip("127.0.0.1", forged)),
                         bucket_key(real))

    # -- F5: bucket normalization ------------------------------------------
    def test_ipv6_keys_normalize_to_64(self):
        rl = RateLimiter(2)
        self.assertTrue(rl.allow("2001:db8::1"))
        # Same /64: a second address in the network shares the bucket.
        self.assertTrue(rl.allow("2001:db8::2"))
        self.assertFalse(rl.allow("2001:db8::3"))  # same /64, now empty
        self.assertTrue(rl.allow("2001:db8:1::1"))  # other /64: fresh bucket

    def test_ipv4_keys_stay_host_scoped(self):
        rl = RateLimiter(1)
        self.assertTrue(rl.allow("198.51.100.1"))
        self.assertFalse(rl.allow("198.51.100.1"))
        self.assertTrue(rl.allow("198.51.100.2"))

    def test_bucket_key_normalization(self):
        self.assertEqual(bucket_key("2001:DB8::ABCD"), "2001:db8::")
        self.assertEqual(bucket_key("198.51.100.7"), "198.51.100.7")
        self.assertEqual(bucket_key("garbage"), "garbage")

    # -- end to end: the gating F1 behavior --------------------------------
    def test_xff_clients_get_separate_buckets(self):
        tmp = tempfile.TemporaryDirectory(prefix="idx-5bf1")
        try:
            cfg, store, _ing = ingest_chain(tmp.name)
        except Exception:
            tmp.cleanup()
            raise
        app = IndexerApp(store, cfg, rate_limiter=RateLimiter(2))
        server = serve(app, "127.0.0.1", 0)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def get(xff):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            try:
                conn.request("GET", "/health",
                             headers={"X-Forwarded-For": xff})
                resp = conn.getresponse()
                resp.read()
                return resp.status
            finally:
                conn.close()

        try:
            self.assertEqual(get("198.51.100.1"), 200)
            self.assertEqual(get("198.51.100.1"), 200)
            self.assertEqual(get("198.51.100.1"), 429)
            # A DIFFERENT XFF identity has its own bucket (the F1 fix):
            self.assertEqual(get("198.51.100.2"), 200)
            self.assertEqual(get("198.51.100.2"), 200)
            self.assertEqual(get("198.51.100.2"), 429)
            # F1 rework: prepending attacker junk must NOT mint a fresh
            # bucket -- the rightmost (proxy-observed) entry is the
            # identity, and that bucket is already empty:
            self.assertEqual(get("1.2.3.4, 198.51.100.2"), 429)
            self.assertEqual(get("203.0.113.99, 198.51.100.1"), 429)
        finally:
            server.shutdown()
            server.server_close()
            store.close()
            tmp.cleanup()


class Test5bF2(unittest.TestCase):
    """F2: HEAD rides the GET route with a suppressed body; OPTIONS/PATCH/
    POST/PUT/DELETE answer 405 JSON with an Allow header; never HTML."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="idx-5bf2")
        cls.cfg, cls.store, _ing = ingest_chain(cls._tmp.name)
        cls.server = serve(IndexerApp(cls.store, cls.cfg),
                           "127.0.0.1", 0)
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

    def _raw(self, request_bytes):
        """One raw HTTP/1.0 request, response read to EOF."""
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=10)
        try:
            sock.sendall(request_bytes)
            chunks = []
            while True:
                data = sock.recv(65536)
                if not data:
                    break
                chunks.append(data)
            return b"".join(chunks)
        finally:
            sock.close()

    @staticmethod
    def _header(headers_block, name):
        name = name.lower().encode()
        for line in headers_block.split(b"\r\n")[1:]:
            k, _, v = line.partition(b":")
            if k.strip().lower() == name:
                return v.strip()
        return None

    def _request(self, method, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, path)
            resp = conn.getresponse()
            body = resp.read()
            return resp.status, {k.lower(): v
                                 for k, v in resp.getheaders()}, body
        finally:
            conn.close()

    def test_head_matches_get_status_and_headers_empty_body(self):
        got = self._raw(b"GET /health HTTP/1.0\r\nHost: x\r\n\r\n")
        head = self._raw(b"HEAD /health HTTP/1.0\r\nHost: x\r\n\r\n")
        self.assertEqual(head.split(b"\r\n", 1)[0], got.split(b"\r\n", 1)[0])
        self.assertTrue(head.startswith(b"HTTP/1.0 200"))
        g_headers, _, g_body = got.partition(b"\r\n\r\n")
        h_headers, _, h_body = head.partition(b"\r\n\r\n")
        self.assertEqual(h_body, b"")  # bodyless
        self.assertNotEqual(g_body, b"")
        # /health embeds crawler_progress_age_s (a live clock), so the GET
        # and HEAD snapshots can legally differ in length (the age float
        # repr crossing a digit boundary between the two requests -- seen
        # as a flake under machine load).  Assert the header CONTRACT:
        # HEAD carries a parseable Content-Length and Content-Type, not a
        # byte-identical snapshot of a later GET.
        h_len = self._header(h_headers, "Content-Length")
        g_len = self._header(g_headers, "Content-Length")
        self.assertTrue(h_len.isdigit())
        self.assertTrue(g_len.isdigit())
        self.assertEqual(int(g_len), len(g_body))  # GET's own length is exact
        self.assertEqual(self._header(h_headers, "Content-Type"),
                         b"application/json")

    def test_head_on_404_route_is_bodyless_404(self):
        head = self._raw(b"HEAD /api/v0/unknown HTTP/1.0\r\nHost: x\r\n\r\n")
        self.assertTrue(head.startswith(b"HTTP/1.0 404"))
        self.assertEqual(head.partition(b"\r\n\r\n")[2], b"")

    def test_options_and_patch_405_json_with_allow(self):
        for method in ("OPTIONS", "PATCH"):
            status, headers, body = self._request(method, "/health")
            self.assertEqual(status, 405, method)
            self.assertEqual(headers.get("allow"), "GET, HEAD", method)
            self.assertIn("error", json.loads(body.decode()), method)
            self.assertNotIn("<html", body.decode().lower(), method)

    def test_post_put_delete_still_405_json_no_html(self):
        for method in ("POST", "PUT", "DELETE"):
            status, headers, body = self._request(method, "/health")
            self.assertEqual(status, 405, method)
            self.assertEqual(headers.get("allow"), "GET, HEAD", method)
            self.assertIn("error", json.loads(body.decode()), method)
            self.assertNotIn("<html", body.decode().lower(), method)

    def test_trace_and_junk_verbs_405_json_with_allow(self):
        # Catch-all completion: ANY verb without an explicit do_<VERB> --
        # TRACE, or a made-up token like FOO -- gets the 405 JSON, never
        # http.server's default 501 HTML page.
        for verb in ("TRACE", "FOO"):
            raw = self._raw(verb.encode("ascii")
                            + b" /health HTTP/1.0\r\nHost: x\r\n\r\n")
            status_line, _, body = raw.partition(b"\r\n\r\n")
            self.assertTrue(status_line.startswith(b"HTTP/1.0 405"), verb)
            self.assertEqual(self._header(status_line, "Allow"),
                             b"GET, HEAD", verb)
            self.assertIn("error", json.loads(body.decode()), verb)
            self.assertNotIn("<html", body.decode().lower(), verb)


class Test5bF3(unittest.TestCase):
    """F3: a malformed Content-Length gets a 413 JSON answer (never an
    uncaught ValueError / dropped connection)."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="idx-5bf3")
        cls.cfg, cls.store, _ing = ingest_chain(cls._tmp.name)
        cls.server = serve(IndexerApp(cls.store, cls.cfg),
                           "127.0.0.1", 0)
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

    def _malformed(self, value):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("GET", "/health", body=b"x",
                         headers={"Content-Length": value})
            resp = conn.getresponse()
            return resp.status, resp.read()
        finally:
            conn.close()

    def _raw(self, request_bytes):
        """One raw HTTP/1.0 request, response read to EOF."""
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=10)
        try:
            sock.sendall(request_bytes)
            chunks = []
            while True:
                data = sock.recv(65536)
                if not data:
                    break
                chunks.append(data)
            return b"".join(chunks)
        finally:
            sock.close()

    @staticmethod
    def _header(headers_block, name):
        name = name.lower().encode()
        for line in headers_block.split(b"\r\n")[1:]:
            k, _, v = line.partition(b":")
            if k.strip().lower() == name:
                return v.strip()
        return None

    def test_non_integer_content_length_413_json(self):
        status, body = self._malformed("abc")
        self.assertEqual(status, 413)
        self.assertEqual(json.loads(body.decode()),
                         {"error": "invalid content-length"})

    def test_negative_content_length_413_json(self):
        status, body = self._malformed("-5")
        self.assertEqual(status, 413)
        self.assertEqual(json.loads(body.decode()),
                         {"error": "invalid content-length"})

    def test_413_json_body_proves_no_drop_and_server_survives(self):
        # The 413 JSON body ARRIVING is the proof the connection was not
        # dropped before the response; the follow-up GET proves the server
        # is still healthy afterwards.
        self._malformed("abc")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("GET", "/health")
            resp = conn.getresponse()
            self.assertEqual(resp.status, 200)
            resp.read()
        finally:
            conn.close()

    def test_head_malformed_content_length_413_bodyless_valid_headers(self):
        # The invalid-content-length branch honors HEAD's body_allowed=False:
        # 413 with a complete, valid header set and an EMPTY body.
        raw = self._raw(b"HEAD /health HTTP/1.0\r\nHost: x\r\n"
                        b"Content-Length: abc\r\n\r\n")
        head, _, body = raw.partition(b"\r\n\r\n")
        self.assertTrue(head.startswith(b"HTTP/1.0 413"))
        self.assertEqual(body, b"")
        self.assertEqual(self._header(head, "Content-Type"),
                         b"application/json")
        cl = self._header(head, "Content-Length")
        self.assertIsNotNone(cl)
        # The suppressed body's Content-Length matches the GET 413 payload.
        self.assertEqual(int(cl), len(json.dumps(
            {"error": "invalid content-length"}).encode()))


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
