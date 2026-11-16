#!/usr/bin/env python3
"""Offline tests for the MAZA wallet bench service.

Runs entirely in-process: MockChain + an ephemeral-port HTTP server, so the
suite needs no daemon, no real sockets beyond loopback, no credentials.
Covers the judge-mandated properties: NaN rejection, UTXO isolation (a send
consumes only bench-address outputs, never foreign ones like the bridge
deposit), cold-start address stability, send-history attribution by txid,
auth, caps, and address-shape guards.

Run:  python3 -m unittest discover -s tests -v
"""

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from walletbench import api, config  # noqa: E402
from walletbench.chain import MockChain, WalletRPC, ChainError, FLAT_FEE  # noqa: E402

TOKEN = "test-token-123"
FOREIGN_ADDR = "M9" + "f" * 32  # 34 chars, simulates the bridge deposit addr


def make_server(chain):
    api._cache.pop("addresses", None)  # fresh bench address book per test
    api._cache.pop("txids", None)
    api._cache.pop("watch_addresses", None)
    handler = api.WalletBenchHandler
    handler.chain = chain
    handler.token_digest = api._token_digest(TOKEN)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


class BenchTestCase(unittest.TestCase):
    def setUp(self):
        self.chain = MockChain()
        self.server, self.base = make_server(self.chain)
        self.addCleanup(self.server.shutdown)

    def request(self, method: str, path: str, body: dict = None,
                cookie: str = None, raw_body: bytes = None):
        url = self.base + path
        data = raw_body if raw_body is not None else \
            (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(url, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if cookie:
            req.add_header("Cookie", cookie)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()

    def unlock(self):
        status, headers, _ = self.request(
            "POST", "/api/unlock", {"token": TOKEN})
        self.assertEqual(status, 200)
        return headers.get("Set-Cookie").split(";")[0]

    def state(self):
        """Unlock + fetch state; returns (state_dict, cookie)."""
        cookie = self.unlock()
        status, _, body = self.request("GET", "/api/state", cookie=cookie)
        self.assertEqual(status, 200)
        return json.loads(body), cookie

    def fund_bench(self, amount: float) -> tuple:
        """Fund whatever address the service actually adopted (cold-start
        path: the address comes FROM the API, never from the test)."""
        state, cookie = self.state()
        addr = state["address"]
        self.chain.fund_address(addr, amount)
        return addr, cookie

    # --- auth ---------------------------------------------------------------
    def test_unlock_rejects_bad_token(self):
        status, _, body = self.request(
            "POST", "/api/unlock", {"token": "wrong"})
        self.assertEqual(status, 401)
        self.assertIn("invalid", json.loads(body)["error"])

    def test_unlock_sets_httponly_cookie(self):
        status, headers, _ = self.request(
            "POST", "/api/unlock", {"token": TOKEN})
        self.assertEqual(status, 200)
        cookie = headers.get("Set-Cookie", "")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)

    def test_state_requires_auth(self):
        status, _, _ = self.request("GET", "/api/state")
        self.assertEqual(status, 401)

    # --- state ---------------------------------------------------------------
    def test_state_shape(self):
        state, _ = self.state()
        self.assertEqual(state["balance"], 0.0)
        self.assertEqual(state["account"], config.ACCOUNT)
        self.assertTrue(state["address"].startswith("M"))
        self.assertEqual(len(state["address"]), 34)
        self.assertEqual(state["fee"], FLAT_FEE)
        self.assertIsInstance(state["txs"], list)

    def test_cold_start_address_is_stable(self):
        # Judge round 2: without cache persistence, every request adopted a
        # fresh address and deposited coins vanished from view.
        state1, cookie = self.state()
        resp = self.request("GET", "/api/state", cookie=cookie)
        state2 = json.loads(resp[2])
        self.assertEqual(state1["address"], state2["address"])
        self.chain.fund_address(state1["address"], 5.0)
        resp = self.request("GET", "/api/state", cookie=cookie)
        state3 = json.loads(resp[2])
        self.assertAlmostEqual(state3["balance"], 5.0, places=6)

    def test_state_balance_reflects_sends(self):
        self.fund_bench(50.0)
        state, cookie = self.state()
        to = self.chain.getnewaddress()
        status, _, body = self.request(
            "POST", "/api/send", {"to": to, "amount": 12.5}, cookie=cookie)
        self.assertEqual(status, 200)
        state2, _ = self.state()
        self.assertAlmostEqual(
            state2["balance"], 50.0 - 12.5 - FLAT_FEE, places=6)

    # --- qr -------------------------------------------------------------------
    def test_qr_svg(self):
        cookie = self.unlock()
        status, headers, body = self.request("GET", "/api/qr.svg", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertIn("image/svg+xml", headers.get("Content-Type"))
        self.assertIn("<svg", body.decode())

    def test_qr_png(self):
        cookie = self.unlock()
        status, headers, body = self.request("GET", "/api/qr.png", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Content-Type"), "image/png")
        self.assertEqual(body[:8], b"\x89PNG\r\n\x1a\n")

    def test_query_param_token_is_rejected(self):
        # Regression: query-param auth was REMOVED (credentials must never
        # ride in URLs) — a valid token passed as ?t= must be refused.
        status, _, _ = self.request(
            "GET", f"/api/state?t={TOKEN}")
        self.assertEqual(status, 401)

    def test_bearer_token_auth(self):
        cookie = self.unlock()
        url = self.base + "/api/state"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {TOKEN}")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)

    def test_qr_requires_auth(self):
        status, _, _ = self.request("GET", "/api/qr.svg")
        self.assertEqual(status, 401)

    # --- send guards ------------------------------------------------------------
    def _send(self, payload, cookie=None):
        return self.request("POST", "/api/send", payload,
                            cookie=cookie or self.unlock())

    def test_send_happy_path_is_utxo_scoped(self):
        addr, cookie = self.fund_bench(50.0)
        to = self.chain.getnewaddress()
        status, _, body = self._send({"to": to, "amount": 5}, cookie=cookie)
        self.assertEqual(status, 200)
        txid = json.loads(body)["txid"]
        self.assertEqual(len(txid), 64)
        self.assertEqual(self.chain.last_send["to"], to)
        self.assertEqual(self.chain.last_send["amount"], 5)
        self.assertEqual(self.chain.last_send["from_addresses"], [addr])

    def test_send_never_consumes_foreign_utxos(self):
        # THE isolation property: a foreign (bridge-deposit-like) UTXO must
        # survive a bench send untouched, even though the same wallet holds it.
        addr, cookie = self.fund_bench(100.0)
        self.chain.fund_address(FOREIGN_ADDR, 11500.0, label="bridge-deposit")
        to = self.chain.getnewaddress()
        status, _, body = self._send({"to": to, "amount": 50}, cookie=cookie)
        self.assertEqual(status, 200)
        foreign = [u for u in self.chain.utxos if u["address"] == FOREIGN_ADDR]
        self.assertEqual(len(foreign), 1)
        self.assertEqual(foreign[0]["amount"], 11500.0)
        foreign_txids = {u["txid"] for u in foreign}
        for txid_, vout in self.chain.last_send["consumed"]:
            self.assertNotIn(txid_, foreign_txids)

    def test_send_amounts_from_foreign_addr_fail(self):
        # A bench wallet whose ONLY funds are foreign-looking utxos has
        # spendable = 0 for its own addresses.
        state, cookie = self.state()
        self.chain.utxos = []
        self.chain.fund_address(FOREIGN_ADDR, 11500.0)
        to = self.chain.getnewaddress()
        status, _, body = self._send({"to": to, "amount": 1}, cookie=cookie)
        self.assertEqual(status, 400)
        self.assertIn("insufficient", json.loads(body)["error"])

    def test_send_rejects_invalid_address(self):
        status, _, body = self._send({"to": "Xnotreal", "amount": 1})
        self.assertEqual(status, 400)
        self.assertIn("invalid", json.loads(body)["error"])

    def test_send_rejects_own_bench_address(self):
        state, cookie = self.state()
        status, _, body = self._send(
            {"to": state["address"], "amount": 1}, cookie=cookie)
        self.assertEqual(status, 400)
        self.assertIn("belongs", json.loads(body)["error"])

    def test_send_rejects_nonpositive_amount(self):
        to = self.chain.getnewaddress()
        status, _, _ = self._send({"to": to, "amount": 0})
        self.assertEqual(status, 400)
        status, _, _ = self._send({"to": to, "amount": -3})
        self.assertEqual(status, 400)

    def test_send_rejects_nan(self):
        # json.loads accepts NaN — the API must reject it explicitly.
        cookie = self.unlock()
        raw = ('{"to":"M' + "1" * 33 + '","amount":NaN}').encode()
        status, _, body = self.request(
            "POST", "/api/send", cookie=cookie, raw_body=raw)
        self.assertEqual(status, 400)
        self.assertIn("finite", json.loads(body)["error"])

    def test_send_enforces_bench_cap(self):
        self.fund_bench(500.0)  # funds, not the cap, must not bind
        to = self.chain.getnewaddress()
        status, _, body = self._send({"to": to, "amount": config.MAX_SEND + 1})
        self.assertEqual(status, 400)
        self.assertIn("cap", json.loads(body)["error"])

    def test_send_rejects_insufficient_balance(self):
        self.fund_bench(5.0)  # below the 50 cap
        to = self.chain.getnewaddress()
        status, _, body = self._send({"to": to, "amount": 10})
        self.assertEqual(status, 400)
        self.assertIn("insufficient", json.loads(body)["error"])

    def test_send_requires_auth(self):
        to = self.chain.getnewaddress()
        status, _, _ = self.request(
            "POST", "/api/send", {"to": to, "amount": 1})
        self.assertEqual(status, 401)

    def test_state_persists_across_restart(self):
        # Judge round 3: Restart=always must not orphan funded addresses.
        import tempfile
        fd, state_file = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.unlink(state_file)  # let the service create it (empty file = corrupt)
        os.environ["WB_STATE_FILE"] = state_file
        try:
            state1, cookie = self.state()
            self.chain.fund_address(state1["address"], 25.0)
            # Simulate a service restart: fresh in-memory cache, same chain.
            self.server.shutdown()
            api._cache.clear()
            self.server, self.base = make_server(self.chain)
            state2, _ = self.state()
            self.assertEqual(state2["address"], state1["address"])
            self.assertAlmostEqual(state2["balance"], 25.0, places=6)
        finally:
            os.unlink(state_file)
            os.environ.pop("WB_STATE_FILE", None)

    def test_concurrent_cold_start_adopts_one_address(self):
        # Judge round 3: threaded cold-start must not create different
        # primary addresses per request.
        from concurrent.futures import ThreadPoolExecutor
        cookie = self.unlock()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(
                lambda _: self.request("GET", "/api/state", cookie=cookie),
                range(8)))
        addrs = {json.loads(r[2])["address"] for r in results}
        self.assertEqual(len(addrs), 1)
        self.assertEqual(self.chain._addr_seq, 1)

    def test_corrupt_state_schema_fails_loud(self):
        # A wrong-TYPE addresses field must be rejected, not iterated into
        # one-character "addresses".
        import tempfile
        fd, state_file = tempfile.mkstemp(suffix=".json")
        os.write(fd, b'{"addresses": "M123", "txids": []}')
        os.close(fd)
        os.environ["WB_STATE_FILE"] = state_file
        try:
            cookie = self.unlock()
            status, _, body = self.request(
                "GET", "/api/state", cookie=cookie)
            self.assertEqual(status, 502)
            self.assertIn("corrupt", json.loads(body)["error"])
        finally:
            os.unlink(state_file)
            os.environ.pop("WB_STATE_FILE", None)

    def test_send_returns_txid_even_if_txid_persist_fails(self):
        # Duplicate-payment guard: the payment is already broadcast when the
        # txid is recorded, so a record failure must NOT become a 500.
        # Persist-call order in a send: 1=change address (pre-broadcast —
        # must fail loud), 2=txid record (post-broadcast — must be swallowed).
        addr, cookie = self.fund_bench(50.0)
        to = self.chain.getnewaddress()
        calls = {"n": 0}
        original = api._persist_state_locked

        def flaky():
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("disk gone")  # the post-broadcast record call
            original()

        api._persist_state_locked = flaky
        try:
            status, _, body = self._send({"to": to, "amount": 1},
                                         cookie=cookie)
            self.assertEqual(status, 200)
            self.assertEqual(len(json.loads(body)["txid"]), 64)
            # 2 = change-address persist (pre-broadcast, OK) + txid record
            # (post-broadcast, failed but swallowed). _ensure is a cache hit
            # and does not persist again.
            self.assertEqual(calls["n"], 2)
        finally:
            api._persist_state_locked = original

    def test_send_history_attributed_by_txid(self):
        # Outgoing txs name the EXTERNAL recipient in listtransactions; the
        # state filter must attribute them by recorded txid or the user's
        # own payments vanish from history.
        addr, cookie = self.fund_bench(50.0)
        to = self.chain.getnewaddress()
        status, _, body = self._send({"to": to, "amount": 5}, cookie=cookie)
        self.assertEqual(status, 200)
        txid = json.loads(body)["txid"]
        state, _ = self.state()
        sends = [t for t in state["txs"] if t["category"] == "send"]
        self.assertEqual(len(sends), 1)
        self.assertEqual(sends[0]["amount"], -5.0)
        self.assertEqual(sends[0]["address"], to)

    def test_self_addressed_funding_send_hidden_from_history(self):
        # A funding tx seen from another account's side reads "send -50 to
        # our own address" — it must not appear as a user payment.
        addr, cookie = self.fund_bench(50.0)
        self.chain.txs.insert(0, {"category": "send", "amount": -50.0,
                                  "confirmations": 2, "time": 0,
                                  "address": addr, "txid": "f" * 64})
        state, _ = self.state()
        sends = [t for t in state["txs"] if t["category"] == "send"]
        self.assertEqual(len(sends), 0)  # the funding "send" must be hidden

    # --- static / pages ------------------------------------------------------
    def test_page_served(self):
        status, headers, _ = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get("Content-Type"))

    def test_static_whitelist(self):
        cookie = self.unlock()
        status, headers, body = self.request(
            "GET", "/static/icon.png", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Content-Type"), "image/png")
        status, _, _ = self.request("GET", "/static/../../etc/passwd",
                                    cookie=cookie)
        self.assertEqual(status, 404)

    def test_unknown_route_404(self):
        status, _, _ = self.request("GET", "/api/unknown")
        self.assertEqual(status, 404)

    # --- security headers -----------------------------------------------------
    def test_security_headers_on_page(self):
        status, headers, _ = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("default-src 'none'", headers.get(
            "Content-Security-Policy", ""))
        self.assertEqual(headers.get("X-Frame-Options"), "DENY")


class TestChainAdapter(unittest.TestCase):
    def test_rpc_endpoint_from_conf(self):
        conf = tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False)
        conf.write("rpcuser=u1\nrpcpassword=p1\nrpcport=12832\n")
        conf.close()
        os.environ["WB_RPC_CONF"] = conf.name
        os.environ.pop("WB_RPC_URL", None)
        try:
            url, user, password = config.rpc_endpoint()
            self.assertEqual(url, "http://127.0.0.1:12832/")
            self.assertEqual((user, password), ("u1", "p1"))
        finally:
            os.unlink(conf.name)

    def test_send_precise_insufficient_raises(self):
        chain = MockChain()
        chain.fund_address("M" + "1" * 33, 1.0)
        with self.assertRaises(ChainError):
            chain.send_precise(["M" + "1" * 33], "M" + "2" * 33, 2.0,
                               "M" + "3" * 33)

    def test_send_precise_fee_makes_exact_balance_unspendable(self):
        chain = MockChain()
        chain.fund_address("M" + "1" * 33, 1.0)
        with self.assertRaises(ChainError):
            chain.send_precise(["M" + "1" * 33], "M" + "2" * 33, 1.0,
                               "M" + "3" * 33)  # 1.0 + fee > 1.0

    def test_walletrpc_surface_exists(self):
        rpc = WalletRPC("http://127.0.0.1:1", "u", "p", timeout=1,
                        account="mobile-play")
        for method in ("getnewaddress", "listunspent_for", "send_precise",
                       "listtransactions_all", "validateaddress",
                       "import_watch_addresses", "sendraw_only"):
            self.assertTrue(callable(getattr(rpc, method)))


WATCH_A = "M" + "a" * 33
WATCH_B = "M" + "b" * 33
FOREIGN_WATCH = "M" + "c" * 33


class TestSelfCustody(BenchTestCase):
    """Watch-only endpoints for the phone-held (self-custody) wallet."""

    def test_watch_import_requires_auth(self):
        status, _, _ = self.request(
            "POST", "/api/watch/import", {"addresses": [WATCH_A]})
        self.assertEqual(status, 401)

    def test_watch_import_rejects_bad_address(self):
        cookie = self.unlock()
        for bad in ("not-an-address", "M" + "a" * 32, 42, None):
            status, _, body = self.request(
                "POST", "/api/watch/import", {"addresses": [bad]},
                cookie=cookie)
            self.assertEqual(status, 400, bad)
        status, _, _ = self.request(
            "POST", "/api/watch/import", {"addresses": []}, cookie=cookie)
        self.assertEqual(status, 400)

    def test_watch_import_dedupes_and_counts(self):
        cookie = self.unlock()
        status, _, body = self.request(
            "POST", "/api/watch/import",
            {"addresses": [WATCH_A, WATCH_B, WATCH_A]}, cookie=cookie)
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["imported"], 2)
        self.assertEqual(data["watched"], 2)
        # idempotent second import
        status, _, body = self.request(
            "POST", "/api/watch/import", {"addresses": [WATCH_A]},
            cookie=cookie)
        data = json.loads(body)
        self.assertEqual(data["imported"], 1)
        self.assertEqual(data["watched"], 2)

    def test_watch_utxos_scoped_to_watch_set(self):
        cookie = self.unlock()
        self.request("POST", "/api/watch/import",
                     {"addresses": [WATCH_A]}, cookie=cookie)
        self.chain.fund_address(WATCH_A, 3.5)
        self.chain.fund_address(WATCH_B, 9.0)  # NOT imported
        status, _, body = self.request(
            "GET", "/api/watch/utxos", cookie=cookie)
        self.assertEqual(status, 200)
        utxos = json.loads(body)["utxos"]
        self.assertEqual(len(utxos), 1)
        self.assertEqual(utxos[0]["address"], WATCH_A)
        self.assertEqual(utxos[0]["amount"], 3.5)

    def test_watch_utxos_empty_book(self):
        cookie = self.unlock()
        status, _, body = self.request(
            "GET", "/api/watch/utxos", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"utxos": []})

    def test_watch_history_filters_by_address(self):
        cookie = self.unlock()
        self.request("POST", "/api/watch/import",
                     {"addresses": [WATCH_A]}, cookie=cookie)
        self.chain.txs.append({"category": "receive", "txid": "t" * 64,
                               "amount": 2.0, "confirmations": 3,
                               "time": 1700000000, "address": WATCH_A})
        self.chain.txs.append({"category": "receive", "txid": "e" * 64,
                               "amount": 5.0, "confirmations": 1,
                               "time": 1700000100, "address": FOREIGN_WATCH})
        status, _, body = self.request(
            "GET", "/api/watch/history", cookie=cookie)
        self.assertEqual(status, 200)
        txs = json.loads(body)["transactions"]
        self.assertEqual(len(txs), 1)
        self.assertEqual(txs[0]["address"], WATCH_A)
        self.assertEqual(txs[0]["amount"], 2.0)

    def test_broadcast_validates_hex(self):
        cookie = self.unlock()
        for bad in ("zzzz", "abc", "0" * 10, "0x1234", ""):
            status, _, _ = self.request(
                "POST", "/api/broadcast", {"hex": bad}, cookie=cookie)
            self.assertEqual(status, 400, bad)
        status, _, _ = self.request(
            "POST", "/api/broadcast", {"nope": 1}, cookie=cookie)
        self.assertEqual(status, 400)

    def test_broadcast_returns_txid_and_records_hex(self):
        cookie = self.unlock()
        raw_hex = "01000000" + "ab" * 40
        status, _, body = self.request(
            "POST", "/api/broadcast", {"hex": raw_hex}, cookie=cookie)
        self.assertEqual(status, 200)
        txid = json.loads(body)["txid"]
        self.assertEqual(len(txid), 64)
        self.assertEqual(self.chain.last_broadcast, raw_hex)

    def test_broadcast_requires_auth(self):
        status, _, _ = self.request(
            "POST", "/api/broadcast", {"hex": "0100"})
        self.assertEqual(status, 401)

    def test_broadcast_uppercase_normalized(self):
        cookie = self.unlock()
        raw_hex = "01000000" + "CD" * 20
        status, _, body = self.request(
            "POST", "/api/broadcast", {"hex": raw_hex}, cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(self.chain.last_broadcast, raw_hex.lower())

    def test_qr_addr_requires_watch_membership(self):
        cookie = self.unlock()
        # well-formed but NOT watched -> 400
        status, _, _ = self.request(
            "GET", f"/api/qr.png?addr={FOREIGN_WATCH}", cookie=cookie)
        self.assertEqual(status, 400)
        # imported -> renders
        self.request("POST", "/api/watch/import",
                     {"addresses": [WATCH_A]}, cookie=cookie)
        status, headers, _ = self.request(
            "GET", f"/api/qr.png?addr={WATCH_A}", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Content-Type"), "image/png")
        # bench default (no addr param) still works
        status, _, _ = self.request("GET", "/api/qr.png", cookie=cookie)
        self.assertEqual(status, 200)

    def test_watch_book_surfaces_in_state_restart(self):
        # Watch book must persist across a service restart, same as the
        # bench address book (orphaned watch addresses = blind wallet).
        import tempfile
        fd, state_file = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.unlink(state_file)
        os.environ["WB_STATE_FILE"] = state_file
        try:
            cookie = self.unlock()
            status, _, body = self.request(
                "POST", "/api/watch/import",
                {"addresses": [WATCH_A, WATCH_B]}, cookie=cookie)
            self.assertEqual(status, 200)
            with open(state_file) as fh:
                on_disk = json.load(fh)
            self.assertEqual(on_disk.get("watch_addresses"),
                             [WATCH_A, WATCH_B])
            # restart with an empty in-memory cache: the watch book must
            # come back from disk
            self.server.shutdown()
            api._cache.clear()
            self.server, self.base = make_server(self.chain)
            cookie = self.unlock()
            status, _, body = self.request(
                "GET", "/api/watch/utxos", cookie=cookie)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body), {"utxos": []})
            # prove the book survived: the QR for a restored watch address
            # must be allowed (membership check reads the reloaded book)
            status, headers, _ = self.request(
                "GET", f"/api/qr.png?addr={WATCH_B}", cookie=cookie)
            self.assertEqual(status, 200)
        finally:
            os.unlink(state_file)
            os.environ.pop("WB_STATE_FILE", None)


class TestWatchImportAccessLog(BenchTestCase):
    """M21: count-only WATCH_IMPORT access line for /api/watch/import.

    The unlock-path proof needs "did the app re-import its watch window on
    unlock?" to be observable on the live bench (journald captures service
    stdout). The line carries a sequence number, the COUNT of addresses in
    the request, and the response status — never addresses, tokens, or IPs.
    The line is flushed BEFORE the response is sent, so observing the
    response implies the log line landed.
    """

    def _capture(self, fn):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            fn()
        return buf.getvalue()

    @staticmethod
    def _lines(out: str):
        return [l for l in out.splitlines() if l.startswith("WATCH_IMPORT ")]

    def test_success_logs_one_count_only_line(self):
        cookie = self.unlock()
        out = self._capture(lambda: self.request(
            "POST", "/api/watch/import",
            {"addresses": [WATCH_A, WATCH_B]}, cookie=cookie)[0])
        lines = self._lines(out)
        self.assertEqual(len(lines), 1, out)
        self.assertIn("status=200", lines[0])
        self.assertIn("imported=2", lines[0])
        # count-only invariant: no address or token material, ever
        self.assertNotIn(WATCH_A, out)
        self.assertNotIn(WATCH_B, out)
        self.assertNotIn(TOKEN, out)

    def test_seq_increments_per_request(self):
        cookie = self.unlock()
        out = self._capture(lambda: (
            self.request("POST", "/api/watch/import",
                         {"addresses": [WATCH_A]}, cookie=cookie)[0],
            self.request("POST", "/api/watch/import",
                         {"addresses": [WATCH_B]}, cookie=cookie)[0],
        ))
        lines = self._lines(out)
        self.assertEqual(len(lines), 2, out)
        seq = [int(l.split("seq=")[1].split()[0]) for l in lines]
        self.assertEqual(seq[1], seq[0] + 1)

    def test_failure_paths_log_without_leaking_input(self):
        # unauthenticated probe -> 401 line, no address in stdout
        out = self._capture(lambda: self.request(
            "POST", "/api/watch/import", {"addresses": [WATCH_A]}))
        lines = self._lines(out)
        self.assertEqual(len(lines), 1, out)
        self.assertIn("status=401", lines[0])
        self.assertIn("imported=0", lines[0])
        self.assertNotIn(WATCH_A, out)
        # malformed address -> 400 line; the log line stays count-only
        cookie = self.unlock()
        out = self._capture(lambda: self.request(
            "POST", "/api/watch/import",
            {"addresses": ["not-an-address"]}, cookie=cookie))
        lines = self._lines(out)
        self.assertEqual(len(lines), 1, out)
        self.assertIn("status=400", lines[0])
        self.assertNotIn("not-an-address", lines[0])


if __name__ == "__main__":
    unittest.main()
