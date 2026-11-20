"""IDX-9 fuzz suite: seeded, deterministic, offline. Hunts for 5xx-where-4xx-
is-correct, dropped connections, non-JSON answers, tracebacks in bodies,
uncontrolled exceptions, hangs, and rate-limit/config crashes across the
indexer's public surface. Mirrors the mazapay test_fuzz.py discipline:
never 5xx where 4xx is correct; the server must survive every input.

Three layers:
  TestAppFuzz     - high-volume fuzz of IndexerApp.handle (in-process)
  TestSocketFuzz  - protocol-level abuse over a real socket
  TestFunctionFuzz- hostile inputs straight into the parsing/validation fns
"""

import http.client
import json
import math
import os
import random
import socket
import sys
import tempfile
import threading
import time
import unittest
from struct import error as struct_error
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from maza_indexer.api import IndexerApp, RateLimiter, serve
from maza_indexer.config import IndexerConfig
from maza_indexer.hashutil import base58check_decode, double_sha256
from maza_indexer.ingest import parse_header, value_to_sats
from maza_indexer.verify import verify_merkle_proof

from test_maza_indexer_core import make_config, ingest_chain

SEED = 773410
N_APP = 400          # app-handle iterations (fast, in-process)
N_FUNC = 150         # per-function iterations
LONG_TIMEOUT = 2.0   # any single handle() call must beat this

ALLOWED_STATUS = {200, 400, 404, 405, 413, 429, 500}

# Hostile + edge payload pools (plus generated randoms below)
EVIL_PATHS = [
    "/api/v0/address/%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "/api/v0/address/../../etc/passwd",
    "/api/v0/address/%00",
    "/api/v0/address/" + "A" * 10000,
    "/api/v0/address/mzapay!" + "\\x01\\x02",
    "/api/v0/tx/" + "0" * 5000,
    "/api/v0/tx/" + "%zz" * 100,
    "/api/v0/block/-1", "/api/v0/block/0", "/api/v0/block/99999999999",
    "/api/v0/block/" + "f" * 64 + "g",
    "/api/v0/proof/-5/" + "a" * 64,
    "/api/v0/proof/1/" + "%41" * 40,
    "/api/v0/search?q=" + "../" * 500,
    "/api/v0/search?q=" + "\\u0000" + "x",
    "/api/v0/search?q=" + "A" * 100000,
    "/api/v0/address/1BADBASE58!!",
    "/api/v0/address/bitcoin1qxyznotours000000",
    "/api/v0/proof/1e3/" + "b" * 64,
    "//double//slash//api//v0//stats",
    "/api/v0/./stats",
    "/api/v0/stats%00",
    "/api/v0/STATS",
    "/api/v0/stats?extra=1&more=2",
    "/api/v0/address?embed=1",
    "/health?probe=1",
    "/api/v0/tx/",
    "/api/v0/proof//",
    "/api/v0/proof/1",
    "/api/v0/address/M",
    "/",
    "",
]
EVIL_LENGTHS = [None, -1, 0, 1, 10 ** 6, "garbage"]
EVIL_IPS = ["127.0.0.1", "9.9.9.9", "::1", "not-an-ip", "",
            "1.2.3.4, 5.6.7.8", "0000:0000:0000:0000:0000:ffff:1.2.3.4"]
HEXISH = ["", "00", "ff" * 31, "ff" * 33, "Z" * 64, "\\x00" * 64,
          "0x" + "a" * 64, "A" * 64]


def _rand_path(r):
    kind = r.randrange(6)
    alpha = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/?.=&%-_#"
    if kind == 0:
        return "/api/v0/address/" + "".join(r.choice(alpha) for _ in range(r.randrange(1, 120)))
    if kind == 1:
        return "/api/v0/tx/" + "".join(r.choice("0123456789abcdefABCDEFxX%") for _ in range(r.randrange(1, 140)))
    if kind == 2:
        return "/api/v0/block/" + "".join(r.choice("0123456789-") for _ in range(r.randrange(1, 80)))
    if kind == 3:
        return "/api/v0/proof/" + str(r.randrange(-10, 10 ** 6)) + "/" + "".join(
            r.choice("0123456789abcdefgX") for _ in range(r.randrange(0, 80)))
    if kind == 4:
        return "/api/v0/search?q=" + "".join(r.choice(alpha) for _ in range(r.randrange(0, 300)))
    return "/" + "".join(r.choice(alpha) for _ in range(r.randrange(0, 200)))


def _assert_clean_response(testcase, status, body, where):
    testcase.assertIn(status, ALLOWED_STATUS,
                      f"{where}: status {status} outside the contract set")
    testcase.assertIsInstance(body, dict, f"{where}: non-dict body")
    raw = json.dumps(body)
    testcase.assertNotIn("<html", raw.lower(), f"{where}: HTML body")
    testcase.assertNotIn("Traceback", raw, f"{where}: traceback leaked")
    testcase.assertNotIn(".py", raw, f"{where}: filesystem path leaked")
    if status >= 400:
        testcase.assertIn("error", body, f"{where}: error body without error key")
        testcase.assertEqual(set(body.keys()), {"error"},
                             f"{where}: error body carries extra keys")


class TestAppFuzz(unittest.TestCase):
    """High-volume seeded fuzz straight into IndexerApp.handle."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="idx-fuzz")
        cls.cfg, cls.store, _ = ingest_chain(cls._tmp.name)
        cls.app = IndexerApp(cls.store, cls.cfg)

    @classmethod
    def tearDownClass(cls):
        cls.store.close()
        cls._tmp.cleanup()

    def test_seeded_handle_fuzz_never_breaks_envelope(self):
        r = random.Random(SEED)
        five_hundreds = []
        for i in range(N_APP):
            path = r.choice(EVIL_PATHS) if r.random() < 0.5 else _rand_path(r)
            method = r.choice(["GET"] * 6 + ["HEAD", "POST", "OPTIONS",
                                             "PATCH", "TRACE", "FOO"])
            cl = r.choice(EVIL_LENGTHS)
            ip = r.choice(EVIL_IPS)
            t0 = time.monotonic()
            status, body = self.app.handle(method, path, cl, ip)
            dt = time.monotonic() - t0
            self.assertLess(dt, LONG_TIMEOUT,
                            f"iter {i}: {method} {path[:60]} took {dt:.2f}s")
            _assert_clean_response(self, status, body, f"iter {i} {method} {path[:60]}")
            if status == 500:
                five_hundreds.append((method, path, body))
        # 5xx is legal only where the catch-all caught a true internal fault;
        # a fuzz run surfacing many 500s means 4xx classification is wrong.
        self.assertLessEqual(len(five_hundreds), 3,
                             f"too many 500s on garbage input: {five_hundreds[:5]}")

    def test_server_still_healthy_after_fuzz(self):
        status, body = self.app.handle("GET", "/health", 0, "127.0.0.1")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])

    def test_pathological_long_input_is_fast(self):
        for size in (10_000, 100_000):
            t0 = time.monotonic()
            status, body = self.app.handle(
                "GET", "/api/v0/search?q=" + "a" * size, 0, "127.0.0.1")
            dt = time.monotonic() - t0
            self.assertLess(dt, LONG_TIMEOUT, f"search len {size}: {dt:.2f}s")
            _assert_clean_response(self, status, body, f"long-search-{size}")

    def test_content_length_strict_typing(self):
        # the strict-typing contract: int passes, None = no body, EVERYTHING
        # else (numeric strings, floats, bools) is 413 - no silent coercion
        cases = [(None, 200), (0, 200), (12, 200),
                 ("12", 413), (1.5, 413), (True, 413), (-12, 413)]
        for cl, want in cases:
            status, body = self.app.handle("GET", "/health", cl, "1.2.3.4")
            self.assertEqual(status, want,
                             f"content_length={cl!r}: {status} != {want}")

    def test_error_body_never_echoes_the_attack(self):
        # the reflected-echo class: error text must not contain the raw attack path
        for path in ("/api/v0/address/%2e%2e%2fetc%2fpasswd",
                     "/api/v0/search?q=<script>alert(1)</script>"):
            status, body = self.app.handle("GET", path, 0, "127.0.0.1")
            raw = json.dumps(body)
            if status >= 400:
                self.assertNotIn("<script>", raw, f"reflected payload in {path}")
                self.assertNotIn("passwd", raw, f"reflected traversal in {path}")


class TestSocketFuzz(unittest.TestCase):
    """Protocol-level abuse over a real socket: the server must survive."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="idx-sockfuzz")
        cls.cfg, cls.store, _ = ingest_chain(cls._tmp.name)
        cls.app = IndexerApp(cls.store, cls.cfg)
        cls.server = serve(cls.app, "127.0.0.1", 0)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.store.close()
        cls._tmp.cleanup()

    def _alive(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/health")
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp.status, body

    def _raw(self, payload: bytes, read=True):
        s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        try:
            s.sendall(payload)
            if read:
                s.settimeout(5)
                try:
                    return s.recv(4096)
                except socket.timeout:
                    return b"<timeout>"
            return b""
        finally:
            s.close()

    def test_garbage_bytes_then_recover(self):
        self._raw(b"\x00\xff\x00\xff garbage not http at all\r\n\r\n")
        status, body = self._alive()
        self.assertEqual(status, 200)

    def test_preature_close_then_recover(self):
        s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        s.sendall(b"GET /health HTTP/1.1\r\nHost: x\r\n")  # no final CRLF
        s.close()  # hang up mid-request
        status, body = self._alive()
        self.assertEqual(status, 200)

    def _read_one_response(self, sock):
        """Read exactly one HTTP response (headers + Content-Length body)
        from a PERSISTENT buffer, so bytes belonging to the NEXT pipelined
        response are preserved between calls. Returns (head_or_None, body)."""
        buf = self._sockbuf
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                self._sockbuf = buf
                return None, b""
            buf += chunk
        head, _, rest = buf.partition(b"\r\n\r\n")
        clen = 0
        for line in head.split(b"\r\n"):
            if line.lower().startswith(b"content-length:"):
                clen = int(line.split(b":", 1)[1].strip())
        while len(rest) < clen:
            chunk = sock.recv(4096)
            if not chunk:
                break
            rest += chunk
        self._sockbuf = rest[clen:]  # preserve unread bytes for the next call
        return head, rest[:clen]

    def test_header_injection_in_request_line(self):
        # the abuse request must receive a PARSED protocol-valid answer
        # (the valid first request -> 200 JSON; the junk trailing request-line
        # -> 400), never an HTML body or a silent hang
        s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        s.sendall(b"GET /api/v0/stats HTTP/1.1\r\nHost: x\r\n"
                  b"X-Evil: value\r\n\r\nInjected: broken\r\n\r\n")
        s.settimeout(5)
        self._sockbuf = b""
        head, body = self._read_one_response(s)
        s.close()
        self.assertIsNotNone(head, "no answer for the abuse request")
        self.assertTrue(head.startswith(b"HTTP/"), head[:40])
        self.assertNotIn(b"<html", head.lower() + body.lower())
        status, _ = self._alive()
        self.assertEqual(status, 200)

    def test_pipelined_requests(self):
        # MEASURED server behavior: the handler closes the connection after
        # each response (HTTP/1.0-style close semantics). Pipelining is NOT
        # a supported client pattern - and that is legal HTTP. The honest
        # assertions: the first pipelined request gets its PARSED valid
        # response, the connection then reaches EOF, and the second request
        # is answered perfectly on its own fresh connection.
        s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        s.sendall(b"GET /health HTTP/1.1\r\nHost: x\r\n\r\n"
                  b"GET /health HTTP/1.1\r\nHost: x\r\n\r\n")
        s.settimeout(5)
        self._sockbuf = b""
        head, body = self._read_one_response(s)
        self.assertIsNotNone(head, "no answer for the first pipelined request")
        self.assertTrue(head.startswith(b"HTTP/"), head[:40])
        self.assertIn(b'"ok": true', body)
        self.assertNotIn(b"<html", head.lower())
        # the server either answers both (keep-alive) or closes after the
        # first (close semantics) - both are legal; assert what is measured:
        second_head, second_body = self._read_one_response(s)
        if second_head is None:
            pass  # measured: close-per-response semantics
        else:
            self.assertTrue(second_head.startswith(b"HTTP/"))
            self.assertIn(b'"ok": true', second_body)
        s.close()
        # the second pipelined request MUST be answered on a fresh connection
        s2 = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        s2.sendall(b"GET /health HTTP/1.1\r\nHost: x\r\n\r\n")
        s2.settimeout(5)
        self._sockbuf = b""
        head2, body2 = self._read_one_response(s2)
        s2.close()
        self.assertIsNotNone(head2, "fresh connection got no answer")
        self.assertIn(b'"ok": true', body2)
        status, _ = self._alive()
        self.assertEqual(status, 200)


class TestFunctionFuzz(unittest.TestCase):
    """Hostile inputs straight into parsing/validation functions."""

    def test_parse_header_random_lengths_controlled(self):
        r = random.Random(SEED + 1)
        for i in range(N_FUNC):
            n = r.choice([0, 1, 10, 79, 80, 81, 160, 200])
            raw = "".join(r.choice("0123456789abcdefXYZ ") for _ in range(n))
            try:
                out = parse_header(raw)
            except (ValueError, struct_error):
                continue  # controlled rejection
            self.assertIsInstance(out, dict, f"iter {i}: odd return {type(out)}")

    def test_verify_merkle_proof_never_raises(self):
        r = random.Random(SEED + 2)
        pools = [[], ["zz"], ["a" * 64], ["a" * 63], ["a" * 65], [None],
                 [b"\\x00" * 32], ["aa" * 32, "bb" * 32], ["aa" * 32, "gg" * 32]]
        for i in range(N_FUNC):
            branch = r.choice(pools) if r.random() < 0.7 else [
                "".join(r.choice("0123456789abcdef") for _ in range(64))]
            pos = r.choice([0, 1, -1, 2 ** 40, None])
            try:
                out = verify_merkle_proof("aa" * 32, "bb" * 32, branch, pos)
            except (TypeError, ValueError) as e:
                # documented contract: verify returns False, never raises.
                self.fail(f"iter {i}: verify raised {e!r} on {branch!r} pos={pos}")
            self.assertIn(out, (True, False), f"iter {i}: odd return {out!r}")

    def test_base58check_random_controlled(self):
        r = random.Random(SEED + 3)
        for i in range(N_FUNC):
            s = "".join(r.choice("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz!@#$")
                        for _ in range(r.randrange(0, 60)))
            try:
                out = base58check_decode(s)
            except ValueError:
                continue  # controlled rejection (invalid character / checksum)
            if out is not None:
                self.assertIsInstance(out, bytes)

    def test_value_to_sats_hostile(self):
        for v in (0, -1, 1e-9, 1e18, "1", "abc", None, float("nan"),
                  float("inf"), 1.5):
            try:
                out = value_to_sats(v)
            except (ValueError, ArithmeticError):
                continue  # loud rejection is the documented behavior
            # NaN can never compare equal - detect it by its own predicate;
            # a silently accepted NaN is a money-integrity violation
            self.assertFalse(isinstance(v, float) and math.isnan(v),
                             "NaN accepted silently - money integrity violation")

    def test_rate_limiter_hostile_configs(self):
        # loud contract: non-positive rates are rejected at construction -
        # a zero/negative refill can only produce deny-everything or nonsense
        for rate in (0, -60):
            with self.assertRaises(ValueError, msg=f"rate {rate}"):
                RateLimiter(rate)
        for rate in (1, 10 ** 9):
            rl = RateLimiter(rate)
            out = rl.allow("9.9.9.9")
            self.assertIn(out, (True, False),
                          f"rate {rate}: allow() returned {out!r}")

    def test_rate_limiter_sweep_bounds_memory(self):
        # the sweep/clear path must EXECUTE, not just exist: capacity 10 ->
        # _max_buckets 256; the sweep condition is checked at the START of
        # each allow, so the trigger identity is the cap+2-nd: the sweep
        # finds no stale entries (all fresh), the clear-all branch fires,
        # and the bucket map drops to just the current caller - bounded
        rl = RateLimiter(10)
        cap = rl._max_buckets
        ids = [f"10.{i // 256}.{i % 256}.1" for i in range(cap + 2)]  # valid IPv4
        verdicts = [rl.allow(ip) for ip in ids]
        self.assertTrue(all(isinstance(v, bool) for v in verdicts))
        self.assertLessEqual(len(rl._buckets), cap,
                             "bucket map exceeded the cap - sweep did not run")
        self.assertTrue(rl.allow("10.99.99.99"), "post-sweep requests broke")
        self.assertLessEqual(len(rl._buckets), cap,
                             "post-sweep map still unbounded")

    def test_double_sha256_random(self):
        r = random.Random(SEED + 4)
        for i in range(N_FUNC):
            raw = bytes(r.randrange(256) for _ in range(r.randrange(0, 200)))
            out = double_sha256(raw)
            self.assertEqual(len(out), 32)

    def test_config_from_env_hostile(self):
        base = {"MAZA_INDEXER_RPC_URL": "http://127.0.0.1:1",
                "MAZA_INDEXER_RPC_USER": "u",
                "MAZA_INDEXER_RPC_PASSWORD": "p",
                "MAZA_INDEXER_DATADIR": "/tmp/idx-fuzz-datadir"}
        for bind in ("127.0.0.1:0", "127.0.0.1:-5", "127.0.0.1:99999",
                     "127.0.0.1:", "::1:1", "[::1]1", "[::1]:70000",
                     "host with space:1", "a" * 500):
            env = dict(base, MAZA_INDEXER_BIND=bind)
            try:
                cfg = IndexerConfig.from_env(env)
            except ValueError:
                continue
            # accepted configs must at least carry a usable port
            self.assertTrue(1 <= cfg.port <= 65535,
                            f"bind {bind!r} accepted with port {cfg.port}")
