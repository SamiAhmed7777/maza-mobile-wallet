#!/usr/bin/env python3
"""Offline tests for MAZA price discovery (M26, walletbench/price.py).

No network beyond the loopback: every upstream is a fake, and the few
tests that need a real socket start their own loopback server on an
OS-assigned port. Pins the policy Payu directed (2026-11-25) - FreiXLite
primary, CoinMarketCap only where needed - and the failure modes around
it: a zero-volume pair never wins, a dead upstream degrades to the
fallback or to NO price (never a number that cannot be sourced), a cached
value ages out, and nothing secret or price-bearing reaches a log line.

M27 (review fold deleg_1ab54e7f): a request never waits on a fetch, a
redirect is never followed, the whole fetch is bounded by its timeout, a
quote stamped in the future is never shown as fresh, and a partly failed
dollar leg is named - never reported as a clean ok.
"""
import contextlib
import http.server
import io
import json
import os
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from decimal import Decimal
from typing import Optional
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_walletbench as bench  # noqa: E402
from walletbench import api, price  # noqa: E402
from walletbench.addrcheck import encode_address  # noqa: E402
from walletbench.chain import ChainError, MockChain  # noqa: E402

# Row shape captured from the live /v2/summary on 2026-11-25.
def summary_row(base, quote, last, base_volume, name=None):
    return {"trading_pairs": name or f"{base}_{quote}", "base_currency": base,
            "quote_currency": quote, "last_price": last,
            "lowest_ask": last, "highest_bid": last,
            "base_volume": base_volume, "quote_volume": "1.18042307",
            "price_change_percent_24h": "0.00",
            "highest_price_24h": "0.00000000", "lowest_price_24h": "0.00000000"}


MAZA_LTC = summary_row("MAZA", "LTC", "0.00004258", "27644.49788952")
MAZA_BTC_DEAD = summary_row("MAZA", "BTC", "0.00000002", "0.00000000")
LTC_USD = Decimal("42.50052535121973")
BTC_USD = Decimal("96000.12345678")
MAZA_CMC = Decimal("0.001225876251021256")
# 0.00004258 LTC x 42.50052535121973 USD, HALF_UP at eight places.
MAZA_USD = "0.00180967"
FAKE_KEY = "fake-cmc-key-for-tests-only"
PRICE_FIELDS = ["age_s", "last", "pair", "quote", "quote_usd", "source",
                "stale", "updated_at", "usd"]


class Clock:
    def __init__(self, now=1_700_000_000.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class Exchange:
    """Fake FreiXLite /v2/summary. `gate`, once set, holds every answer
    until it is released: a hung upstream."""

    def __init__(self, payload=None, ok=True, reason=""):
        self.payload = payload
        self.ok = ok
        self.reason = reason
        self.calls = 0
        self.gate: Optional[threading.Event] = None

    def __call__(self):
        self.calls += 1
        if self.gate is not None:
            self.gate.wait(5)
        return self.ok, self.payload, self.reason


class Cmc:
    """Fake CoinMarketCap leg, already reduced to {symbol: usd}."""

    def __init__(self, quotes=None, mode="web", reason=""):
        self.quotes = dict(quotes or {})
        self.mode = mode
        self.reason = reason
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return dict(self.quotes), self.mode, self.reason


def build(exchange, cmc, clock=None):
    return price.PriceCache(exchange_fetch=exchange, cmc_fetch=cmc,
                            clock=clock or Clock())


def settle(cache, seconds=5.0):
    """Wait until no refresh round is running (bounded). True when the
    cache went quiet, False on timeout."""
    return until(lambda: not cache._refreshing, seconds, lock=cache._lock)


def until(predicate, seconds=5.0, lock=None):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if lock is None:
            met = predicate()
        else:
            with lock:
                met = predicate()
        if met:
            return True
        time.sleep(0.005)
    return False


def json_or_none(raw):
    try:
        return json.loads(raw)
    except ValueError:
        return None


class TestParsePairs(unittest.TestCase):
    def test_live_shape_picks_the_trading_pair(self):
        pairs = price.parse_pairs([MAZA_BTC_DEAD, MAZA_LTC])
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].name, "MAZA_LTC")
        self.assertEqual(pairs[0].base, "MAZA")
        self.assertEqual(pairs[0].quote, "LTC")
        self.assertEqual(pairs[0].last, Decimal("0.00004258"))
        self.assertEqual(pairs[0].base_volume, Decimal("27644.49788952"))

    def test_zero_volume_pair_is_a_stale_quote_not_a_market(self):
        # MAZA_BTC still prints a last price although nothing trades; that
        # dead quote is what the aggregators carry as "the" MAZA price.
        self.assertEqual(price.parse_pairs([MAZA_BTC_DEAD]), [])

    def test_volume_is_compared_in_the_base_unit(self):
        # Both volumes are in MAZA, so they compare directly however the
        # quote volumes differ.
        btc = summary_row("MAZA", "BTC", "0.00000002", "5")
        pairs = price.parse_pairs([btc, MAZA_LTC])
        self.assertEqual([pair.name for pair in pairs], ["MAZA_LTC", "MAZA_BTC"])

    def test_ties_break_by_name(self):
        btc = summary_row("MAZA", "BTC", "0.00000002", "100")
        ltc = summary_row("MAZA", "LTC", "0.00004258", "100")
        pairs = price.parse_pairs([ltc, btc])
        self.assertEqual([pair.name for pair in pairs], ["MAZA_BTC", "MAZA_LTC"])

    def test_name_is_derived_and_quote_is_uppercased(self):
        row = {key: value for key, value in MAZA_LTC.items()
               if key != "trading_pairs"}
        row["quote_currency"] = "ltc"
        pair = price.parse_pairs([row])[0]
        self.assertEqual((pair.name, pair.quote), ("MAZA_LTC", "LTC"))

    def test_json_numbers_are_accepted(self):
        pair = price.parse_pairs([summary_row("MAZA", "LTC", 2e-08, 10.5)])[0]
        self.assertEqual(price.text(pair.last), "0.00000002")
        self.assertEqual(pair.base_volume, Decimal("10.5"))

    def test_malformed_rows_are_ignored(self):
        rows = [
            summary_row("MAZA", "LTC", "abc", "10"),
            summary_row("MAZA", "LTC", "0", "10"),
            summary_row("MAZA", "LTC", None, "10"),
            summary_row("MAZA", "LTC", "-1", "10"),
            summary_row("MAZA", "LTC", "NaN", "10"),
            summary_row("MAZA", "LTC", "Infinity", "10"),
            summary_row("MAZA", "LTC", True, "10"),
            {**MAZA_LTC, "base_volume": "-5"},
            {**MAZA_LTC, "base_volume": "abc"},
            {**MAZA_LTC, "base_volume": "NaN"},
            {**MAZA_LTC, "base_volume": True},
            {**MAZA_LTC, "base_volume": None},
            {**MAZA_LTC, "quote_currency": ""},
            {**MAZA_LTC, "quote_currency": 7},
            {**MAZA_LTC, "base_currency": "FRC"},
            "MAZA_LTC",
            None,
            42,
        ]
        self.assertEqual(price.parse_pairs(rows), [])
        for payload in (None, {}, "[]", 7, True):
            self.assertEqual(price.parse_pairs(payload), [])


class TestDecimalGuards(unittest.TestCase):
    def test_positive(self):
        for bad in (None, True, False, "abc", "NaN", "Infinity", 0, "-1",
                    "0.0", "-0.00000001", price.PARSE_VALUE_CAP * 2):
            self.assertIsNone(price._positive(bad), bad)
        self.assertEqual(price._positive("0.00000002"), Decimal("0.00000002"))
        self.assertEqual(price._positive(2e-08), Decimal("2e-08"))
        self.assertEqual(price._positive(price.PARSE_VALUE_CAP),
                         price.PARSE_VALUE_CAP)

    def test_non_negative(self):
        self.assertEqual(price._non_negative("0"), Decimal("0"))
        self.assertEqual(price._non_negative(10.5), Decimal("10.5"))
        for bad in (None, True, "NaN", "-0.5", price.PARSE_VALUE_CAP * 10):
            self.assertIsNone(price._non_negative(bad), bad)

    def test_text_rounds_half_up_at_eight_places(self):
        self.assertEqual(price.text(Decimal("0.0018096723694549361034")),
                         "0.00180967")
        self.assertEqual(price.text(Decimal("2.5e-8")), "0.00000003")
        self.assertEqual(price.text(Decimal("1")), "1.00000000")
        self.assertEqual(price.text(Decimal("42.50052535121973")),
                         "42.50052535")

    def test_text_is_the_wallet_display_precision(self):
        self.assertEqual(price.text(Decimal("2e-08")), "0.00000002")
        self.assertEqual(price.text(Decimal("0.0000000123456789")), "0.00000001")


class TestCmcParsing(unittest.TestCase):
    def test_official_shape(self):
        payload = {"data": {
            "164": {"symbol": "MAZA", "quote": {"USD": {"price": 0.0012}}},
            "1": {"symbol": "BTC", "quote": {"USD": {"price": 96000.5}}}}}
        self.assertEqual(price.parse_cmc_official(payload),
                         {"MAZA": Decimal("0.0012"), "BTC": Decimal("96000.5")})

    def test_web_shape(self):
        payload = {"data": {"id": 164, "symbol": "MAZA",
                            "statistics": {"price": 0.001225876251021256}}}
        self.assertEqual(price.parse_cmc_web(payload),
                         {"MAZA": Decimal("0.001225876251021256")})

    def test_malformed_payloads_yield_nothing(self):
        official_bad = [
            None, [], "x", {"data": []}, {"data": {"164": "x"}},
            {"data": {"164": {"symbol": "MAZA", "quote": {}}}},
            {"data": {"164": {"symbol": "MAZA", "quote": {"USD": "x"}}}},
            {"data": {"164": {"symbol": "MAZA", "quote": {"USD": {"price": 0}}}}},
            {"data": {"164": {"symbol": "MAZA", "quote": {"USD": {"price": "NaN"}}}}},
            {"data": {"164": {"symbol": 164, "quote": {"USD": {"price": 1}}}}},
        ]
        for payload in official_bad:
            self.assertEqual(price.parse_cmc_official(payload), {}, payload)
        web_bad = [
            None, [], "x", {"data": []}, {"data": {"statistics": "x"}},
            {"data": {"symbol": "MAZA", "statistics": {"price": 0}}},
            {"data": {"symbol": "MAZA", "statistics": {"price": "Infinity"}}},
            {"data": {"symbol": "MAZA", "statistics": {}}},
            {"data": {"symbol": "MAZA"}},
            {"data": {"symbol": 164, "statistics": {"price": 1}}},
        ]
        for payload in web_bad:
            self.assertEqual(price.parse_cmc_web(payload), {}, payload)


class TestCmcQuotes(unittest.TestCase):
    """The CoinMarketCap leg: how it is called and what it reports."""

    def test_official_mode_sends_the_key_in_a_header_never_the_url(self):
        seen = []

        def fake(url, timeout, headers):
            seen.append((url, headers))
            return True, {"data": {"164": {"symbol": "MAZA",
                                           "quote": {"USD": {"price": 0.0012}}}}}, ""

        got = price.cmc_quotes(FAKE_KEY, fetch=fake)
        self.assertEqual(got, ({"MAZA": Decimal("0.0012")}, "official", ""))
        self.assertEqual(len(seen), 1)
        url, headers = seen[0]
        self.assertTrue(url.startswith(price.CMC_OFFICIAL_URL))
        self.assertIn("convert=USD", url)
        self.assertEqual(headers.get("X-CMC_PRO_API_KEY"), FAKE_KEY)
        self.assertNotIn(FAKE_KEY, url)

    def test_official_mode_failure(self):
        def fake(url, timeout, headers):
            return False, None, "http_401"
        self.assertEqual(price.cmc_quotes(FAKE_KEY, fetch=fake),
                         ({}, "official", "http_401"))

    def test_official_mode_unparseable_body(self):
        def fake(url, timeout, headers):
            return True, {"data": {}}, ""
        self.assertEqual(price.cmc_quotes(FAKE_KEY, fetch=fake),
                         ({}, "official", "no_quote"))

    def test_keyless_mode_merges_one_detail_call_per_asset(self):
        seen = []

        def fake(url, timeout, headers):
            seen.append(url)
            symbol = {164: "MAZA", 1: "BTC", 2: "LTC"}[int(url.split("id=")[1])]
            return True, {"data": {"symbol": symbol,
                                   "statistics": {"price": "1.5"}}}, ""

        quotes, mode, reason = price.cmc_quotes("", fetch=fake)
        self.assertEqual((mode, reason), ("web", ""))
        self.assertEqual(quotes, {"MAZA": Decimal("1.5"), "BTC": Decimal("1.5"),
                                  "LTC": Decimal("1.5")})
        self.assertEqual(seen, [f"{price.CMC_WEB_URL}?id=164",
                                f"{price.CMC_WEB_URL}?id=1",
                                f"{price.CMC_WEB_URL}?id=2"])

    def test_keyless_mode_survives_one_failing_asset(self):
        def fake(url, timeout, headers):
            if url.endswith("id=2"):
                return False, None, "timeout"
            symbol = "MAZA" if url.endswith("id=164") else "BTC"
            return True, {"data": {"symbol": symbol,
                                   "statistics": {"price": "1.5"}}}, ""

        quotes, mode, reason = price.cmc_quotes("", fetch=fake)
        self.assertEqual((mode, sorted(quotes)), ("web", ["BTC", "MAZA"]))
        # Review fold (deleg_1ab54e7f F10): the rates that came are good
        # - and the pass is named "partial", not a clean ok.
        self.assertEqual(reason, "partial")

    def test_keyless_mode_all_down(self):
        def fake(url, timeout, headers):
            return False, None, "timeout"
        self.assertEqual(price.cmc_quotes("", fetch=fake), ({}, "web", "timeout"))

    def test_keyless_mode_unparseable(self):
        def fake(url, timeout, headers):
            return True, {"data": {"symbol": "MAZA"}}, ""
        self.assertEqual(price.cmc_quotes("", fetch=fake), ({}, "web", "no_quote"))

    def test_three_calls_share_one_bounded_budget(self):
        seen = []

        class Ticker:
            now = 0.0

            def __call__(self):
                return self.now

        ticker = Ticker()

        def slow(url, timeout, headers):
            seen.append(timeout)
            ticker.now += timeout      # each call burns its whole budget
            symbol = {164: "MAZA", 1: "BTC", 2: "LTC"}[int(url.split("id=")[1])]
            return True, {"data": {"symbol": symbol,
                                   "statistics": {"price": "1"}}}, ""

        quotes, mode, reason = price.cmc_quotes("", fetch=slow, mono=ticker)
        # The third request would exceed start + 2 x timeout: not sent.
        self.assertEqual(seen, [4, 4])
        self.assertEqual((mode, sorted(quotes)), ("web", ["BTC", "MAZA"]))
        self.assertEqual(reason, "partial")     # LTC was never asked

    def test_fast_upstream_gets_all_three_calls(self):
        seen = []

        def fast(url, timeout, headers):
            seen.append(url)
            return True, {"data": {"symbol": "MAZA",
                                   "statistics": {"price": "1"}}}, ""

        price.cmc_quotes("", fetch=fast, mono=lambda: 0.0)
        self.assertEqual(len(seen), 3)


class Loopback(http.server.HTTPServer):
    """A real HTTP server on the loopback, bound to port 0: the OS assigns
    the port and this object owns it, so nothing is probed and nothing is
    fought over. `stop` is for handlers that need to end early."""

    def __init__(self, handler):
        super().__init__(("127.0.0.1", 0), handler)
        self.stop = threading.Event()


class TestFetchJson(unittest.TestCase):
    """The one function that really opens a socket. Every other suite
    injects a fake `fetch`, so the real branches are exercised here - and
    the 429 matters: CoinMarketCap's keyless feed rate-limits under load.

    fetch_json goes through ONE seam, `price._open`. These tests replace
    that seam, or put a real loopback server behind it."""

    def test_an_http_error_is_closed_and_named_by_status(self):
        # `error` stays referenced by this test on purpose: left to the
        # garbage collector, the response's file object would be closed
        # anyway, and then this assertion could not tell the difference.
        body = io.BytesIO(b"Too Many Requests")
        error = urllib.error.HTTPError("https://upstream.invalid/x", 429,
                                       "Too Many Requests", {}, body)
        original = price._open

        def refuse(request, timeout=None):
            raise error

        price._open = refuse
        try:
            answer = price.fetch_json("https://upstream.invalid/x")
        finally:
            price._open = original
        self.assertEqual(answer, (False, None, "http_429"))
        self.assertTrue(body.closed)

    def test_a_good_response_is_decoded_with_the_named_headers(self):
        seen = {}
        original = price._open

        def serve(request, timeout=None):
            seen["url"] = request.full_url
            seen["accept"] = request.get_header("Accept")
            seen["agent"] = request.get_header("User-agent")
            return io.BytesIO(b'{"ok": true}')

        price._open = serve
        try:
            self.assertEqual(price.fetch_json("https://upstream.invalid/x"),
                             (True, {"ok": True}, ""))
        finally:
            price._open = original
        self.assertEqual(seen, {"url": "https://upstream.invalid/x",
                                "accept": "application/json",
                                "agent": price.USER_AGENT})

    def loopback(self, handler):
        """Serve `handler` on the loopback; returns (server, base url)."""
        server = Loopback(handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def stop():
            server.stop.set()
            server.shutdown()         # stops the loop ...
            server.server_close()     # ... this closes the listening socket
            thread.join(5)
        self.addCleanup(stop)
        return server, "http://127.0.0.1:%d" % server.server_port

    def test_a_redirect_is_an_answer_and_is_never_followed(self):
        # Review fold (deleg_1ab54e7f F4): following a redirect replays
        # the request headers - the CoinMarketCap key among them - to
        # whatever host and scheme the redirect names. urllib's default
        # handler did exactly that (reproduced: a foreign loopback target
        # received X-CMC_PRO_API_KEY). A 3xx is reported by its status.
        hits = []

        class Target(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.headers.get("X-CMC_PRO_API_KEY"))
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, format, *args):  # noqa: A002
                pass

        _, target = self.loopback(Target)

        class Redirect(http.server.BaseHTTPRequestHandler):
            status = 0
            location = ""

            def do_GET(self):
                self.send_response(self.status)
                self.send_header("Location", self.location)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, format, *args):  # noqa: A002
                pass

        for status, location in ((302, target + "/stolen"),  # another origin
                                 (301, "/elsewhere"),         # same origin
                                 (307, target + "/stolen")):
            Redirect.status, Redirect.location = status, location
            _, base = self.loopback(Redirect)
            answer = price.fetch_json(base + "/go", 2.0,
                                      {"X-CMC_PRO_API_KEY": FAKE_KEY})
            self.assertEqual(answer, (False, None, "http_%d" % status))
        self.assertEqual(hits, [])      # the key never left the first hop

    class Trickle(http.server.BaseHTTPRequestHandler):
        """Drips one byte every 250 ms: never idle for long, never quick.
        It stops after 40 bytes (~10 s) so that an UNbounded reader fails
        the test late rather than hanging it."""

        def do_GET(self):
            try:
                self.send_response(200)
                self.send_header("Content-Length", "400")
                self.end_headers()
                for _ in range(40):
                    if self.server.stop.is_set():
                        break
                    self.wfile.write(b"{")
                    self.wfile.flush()         # resets the idle timer
                    time.sleep(0.25)
            except OSError:
                pass                         # the caller gave up: expected

        def log_message(self, format, *args):  # noqa: A002
            pass

    def trickle(self):
        return self.loopback(self.Trickle)[1]

    def test_a_trickling_upstream_cannot_hold_the_caller_past_the_timeout(self):
        # Review fold (deleg_1ab54e7f F5): a socket timeout bounds only
        # the idle gaps. An upstream that drips one byte at a time
        # restarts that timer at every byte, so a plain read(n) sat there
        # for the whole body (400 bytes = 100 s against a 1 s timeout).
        # The fetch as a whole is bounded: the caller is back at the
        # timeout, whatever the body is doing.
        base = self.trickle()
        started = time.monotonic()
        answer = price.fetch_json(base + "/slow", 1.0)
        elapsed = time.monotonic() - started
        self.assertEqual(answer, (False, None, "timeout"))
        self.assertLess(elapsed, 2.0)         # bounded by the timeout

    def test_a_hung_open_is_abandoned_at_the_timeout(self):
        # Review fold (deleg_1ab54e7f F5, second half): the phases BEFORE
        # the first byte are not covered by the socket timeout at all (a
        # DNS lookup ignores it), so the caller cannot rely on urllib
        # coming back. It waits for the worker for `timeout` and no
        # longer.
        original = price._open

        def stuck(request, timeout=None):
            time.sleep(1.5)                  # past the caller's deadline
            return io.BytesIO(b"{}")

        price._open = stuck
        try:
            started = time.monotonic()
            self.assertEqual(
                price.fetch_json("https://upstream.invalid/x", 0.3),
                (False, None, "timeout"))
            self.assertLess(time.monotonic() - started, 1.0)
        finally:
            price._open = original

    def test_the_abandoned_worker_also_ends_at_the_deadline(self):
        # Review fold (deleg_1ab54e7f F5, third part): the CALLER is back
        # at the timeout - the worker it left behind must not stay for
        # the rest of a trickling body (one live thread per fetch).
        base = self.trickle()
        self.assertEqual(price.fetch_json(base + "/slow", 0.5),
                         (False, None, "timeout"))

        def workers():
            return [thread for thread in threading.enumerate()
                    if thread.name == "price-fetch"]
        self.assertTrue(until(lambda: not workers(), 2.0), workers())


class TestPriceCachePolicy(unittest.TestCase):
    """Source selection, exactly as directed: FreiXLite first,
    CoinMarketCap only where needed, never a number without a source."""

    def setUp(self):
        self.clock = Clock()
        self.exchange = Exchange([MAZA_LTC, MAZA_BTC_DEAD])
        self.cmc = Cmc({"MAZA": MAZA_CMC, "BTC": BTC_USD, "LTC": LTC_USD})

    def snapshot(self, cache=None):
        return (cache or build(self.exchange, self.cmc, self.clock)).snapshot()

    def test_primary_is_the_venues_price_converted_through_the_dollar_leg(self):
        found = self.snapshot()["price"]
        self.assertEqual(found["usd"], MAZA_USD)
        self.assertEqual(found["source"], "freixlite")
        self.assertEqual(found["pair"], "MAZA_LTC")
        self.assertEqual(found["last"], "0.00004258")
        self.assertEqual(found["quote"], "LTC")
        self.assertEqual(found["quote_usd"], "42.50052535")
        self.assertEqual((found["age_s"], found["stale"]), (0, False))
        # CoinMarketCap's own (stale-market) MAZA quote is NOT what shows.
        self.assertNotEqual(found["usd"], price.text(MAZA_CMC))

    def test_dollar_leg_follows_the_pairs_quote_currency(self):
        self.exchange.payload = [summary_row("MAZA", "BTC", "0.00000001", "1000")]
        found = self.snapshot()["price"]
        self.assertEqual((found["pair"], found["quote"]), ("MAZA_BTC", "BTC"))
        self.assertEqual(found["usd"], price.text(Decimal("0.00000001") * BTC_USD))
        self.assertEqual(found["quote_usd"], price.text(BTC_USD))

    def test_a_pair_without_a_dollar_price_yields_to_one_that_has(self):
        self.exchange.payload = [MAZA_LTC, summary_row("MAZA", "BTC", "0.00000001", "5")]
        self.cmc.quotes = {"MAZA": MAZA_CMC, "BTC": BTC_USD}   # LTC unpriced
        self.assertEqual(self.snapshot()["price"]["pair"], "MAZA_BTC")

    def test_an_absurd_upstream_price_is_rejected_not_quoted(self):
        # Review fold (deleg_6106976c F1): a "last price" beyond the parse
        # cap is upstream garbage - rejected at parse, so the row never
        # enters the book and the fallback (or no price) answers instead.
        self.exchange.payload = [summary_row("MAZA", "LTC", "1e30", "27644")]
        found = self.snapshot()["price"]
        self.assertEqual(found["source"], "coinmarketcap")
        self.assertEqual(found["usd"], price.text(MAZA_CMC))
        # And the same feed keeps answering afterwards (the poisoned row
        # can never wedge the cache the way an unhandled quantize did).
        self.assertEqual(self.snapshot()["price"]["source"], "coinmarketcap")

    def test_an_absurd_conversion_is_skipped_not_a_500(self):
        # Review fold (deleg_6106976c F1, second half): each factor under
        # the cap, the product over it - the pair is skipped like a missing
        # dollar leg and the venue price is quoted in its own currency.
        self.exchange.payload = [summary_row("MAZA", "LTC", "1000000000000", "27644")]
        self.cmc.quotes = {"MAZA": MAZA_CMC, "LTC": Decimal("1e12")}
        found = self.snapshot()["price"]
        self.assertEqual(found["source"], "freixlite")
        self.assertIsNone(found["usd"])
        self.assertEqual(found["last"], "1000000000000.00000000")
        self.assertEqual(found["quote"], "LTC")
        self.assertIsNone(found["quote_usd"])

    def test_a_partial_cmc_refresh_keeps_the_other_symbols_rates(self):
        # Review fold (deleg_6106976c F2): one dead symbol upstream must
        # not throw away the other symbols' still-fresh rates.
        cache = build(self.exchange, self.cmc, self.clock)
        cache.snapshot()                      # full fetch: MAZA + LTC priced
        self.clock.advance(price.CMC_TTL_S + 1)
        self.exchange.ok = False              # venue re-fetch fails; pairs cached
        self.cmc.quotes = {"MAZA": MAZA_CMC}  # partial success: LTC missing
        found = cache.snapshot()["price"]
        self.assertEqual(found["source"], "freixlite")
        self.assertEqual(found["usd"], MAZA_USD)       # the OLD LTC rate
        self.assertEqual(found["quote_usd"], "42.50052535")

    def test_a_cmc_symbol_beyond_the_display_window_is_dropped(self):
        cache = build(self.exchange, self.cmc, self.clock)
        cache.snapshot()
        self.clock.advance(price.MAX_AGE_S + price.CMC_TTL_S + 1)
        self.cmc.quotes = {"MAZA": MAZA_CMC}  # LTC still missing upstream
        found = cache.snapshot()["price"]
        # The cached LTC rate is past MAX_AGE_S: a partial answer does not
        # bring it back; the pair prices in its own currency instead.
        self.assertEqual(found["source"], "freixlite")
        self.assertIsNone(found["usd"])
        self.assertIsNone(found["quote_usd"])

    def test_a_rate_kept_through_partial_answers_keeps_its_own_age(self):
        # Found in the M27 audit (residual of the fold above): keeping a
        # still-valid rate through ONE partial answer re-stamped the whole
        # set "now" - so under partial answers repeated every TTL, a rate
        # upstream had stopped answering for read as seconds old forever.
        cache = build(self.exchange, self.cmc, self.clock)
        cache.snapshot()                      # full fetch: MAZA + LTC priced
        self.cmc.quotes, self.cmc.reason = {"MAZA": MAZA_CMC}, "partial"
        for _ in range(4):                    # an hour of partial answers
            self.clock.advance(price.CMC_TTL_S)
            cache.snapshot()
        found = cache.serve()["price"]        # what a wallet is answered
        self.assertEqual(found["usd"], MAZA_USD)       # still priced ...
        # ... at the LTC rate's real age (2400 s, the oldest input used),
        # and marked stale - not at the age of the last partial answer.
        self.assertEqual(found["age_s"], 4 * price.CMC_TTL_S)
        self.assertTrue(found["stale"])

    def test_a_rate_kept_through_partial_answers_expires(self):
        # Same residual: a rate upstream no longer answers for is not
        # kept alive by newer partial answers. At MAX_AGE_S it is no
        # longer used, and the line falls back to the pair's own currency.
        cache = build(self.exchange, self.cmc, self.clock)
        cache.snapshot()
        self.cmc.quotes, self.cmc.reason = {"MAZA": MAZA_CMC}, "partial"
        for _ in range(49):                   # 24 h 30 min of them
            self.clock.advance(1800)
            cache.snapshot()
        found = cache.serve()["price"]
        self.assertEqual(found["source"], "freixlite")
        self.assertIsNone(found["usd"])
        self.assertIsNone(found["quote_usd"])

    def test_no_dollar_leg_quotes_the_pair_in_its_own_currency(self):
        self.cmc.quotes = {}
        found = self.snapshot()["price"]
        self.assertIsNone(found["usd"])
        self.assertEqual((found["source"], found["pair"], found["last"], found["quote"]),
                         ("freixlite", "MAZA_LTC", "0.00004258", "LTC"))

    def test_no_trading_pair_falls_back_to_coinmarketcap(self):
        self.exchange.payload = [MAZA_BTC_DEAD]
        found = self.snapshot()["price"]
        self.assertEqual((found["usd"], found["source"]),
                         (price.text(MAZA_CMC), "coinmarketcap"))
        self.assertIsNone(found["pair"])
        self.assertIsNone(found["last"])
        self.assertIsNone(found["quote"])

    def test_venue_down_falls_back_to_coinmarketcap(self):
        self.exchange.ok, self.exchange.reason = False, "timeout"
        answer = self.snapshot()
        self.assertEqual((answer["price"]["usd"], answer["price"]["source"]),
                         (price.text(MAZA_CMC), "coinmarketcap"))
        self.assertEqual(answer["attempts"], ["freixlite:timeout", "coinmarketcap:ok"])

    def test_both_down_gives_no_price(self):
        self.exchange.ok, self.exchange.reason = False, "timeout"
        self.cmc.quotes, self.cmc.reason = {}, "unreachable"
        answer = self.snapshot()
        self.assertIsNone(answer["price"])
        self.assertEqual(answer["reason"], "freixlite:timeout; coinmarketcap:unreachable")
        self.assertNotIn("usd", answer)

    def test_ttls_gate_refetch(self):
        cache = build(self.exchange, self.cmc, self.clock)
        cache.snapshot()
        self.assertEqual((self.exchange.calls, self.cmc.calls), (1, 1))
        self.clock.advance(59)
        cache.snapshot()
        self.assertEqual((self.exchange.calls, self.cmc.calls), (1, 1))
        self.clock.advance(1)                 # 60 s: venue TTL
        cache.snapshot()
        self.assertEqual((self.exchange.calls, self.cmc.calls), (2, 1))
        self.clock.advance(540)               # 600 s: CoinMarketCap TTL
        cache.snapshot()
        # Refresh is lazy - it happens on the first request after a TTL,
        # so three snapshots caused three venue fetches, not ten.
        self.assertEqual((self.exchange.calls, self.cmc.calls), (3, 2))

    def test_a_dead_upstream_is_retried_once_per_ttl_not_per_request(self):
        cache = build(self.exchange, self.cmc, self.clock)
        self.exchange.ok, self.exchange.reason = False, "unreachable"
        for _ in range(5):
            cache.snapshot()
        self.assertEqual(self.exchange.calls, 1)
        self.clock.advance(price.EXCHANGE_TTL_S)
        cache.snapshot()
        self.assertEqual(self.exchange.calls, 2)

    def test_failed_refresh_keeps_the_last_value_until_it_ages_out(self):
        cache = build(self.exchange, self.cmc, self.clock)
        first = cache.snapshot()["price"]
        self.exchange.ok, self.exchange.reason = False, "unreachable"
        self.clock.advance(120)
        second = cache.snapshot()["price"]
        self.assertEqual((second["usd"], second["age_s"], second["stale"]),
                         (first["usd"], 120, False))
        self.clock.advance(1000)              # 1120 s old: labelled stale
        third = cache.snapshot()["price"]
        self.assertEqual((third["usd"], third["age_s"], third["stale"]),
                         (first["usd"], 1120, True))
        self.clock.advance(price.MAX_AGE_S)   # beyond 24 h: dropped
        fourth = cache.snapshot()["price"]
        self.assertEqual((fourth["usd"], fourth["source"]),
                         (price.text(MAZA_CMC), "coinmarketcap"))

    def test_dollar_leg_outage_keeps_the_venue_price(self):
        cache = build(self.exchange, self.cmc, self.clock)
        first = cache.snapshot()["price"]
        self.cmc.quotes, self.cmc.reason = {}, "http_403"
        self.clock.advance(1000)
        second = cache.snapshot()["price"]
        self.assertEqual((second["usd"], second["source"]),
                         (first["usd"], "freixlite"))
        # The age is the age of the OLDEST input: the dollar leg here.
        self.assertEqual((second["age_s"], second["stale"]), (1000, True))

    def test_age_is_the_age_of_the_oldest_input(self):
        cache = build(self.exchange, self.cmc, self.clock)
        cache.snapshot()
        self.clock.advance(60)
        found = cache.snapshot()["price"]
        self.assertEqual(found["age_s"], 60)     # pair fresh, dollar leg 60 s

    def test_a_burst_of_callers_starts_exactly_one_round(self):
        # Review fold (deleg_1ab54e7f F2): eight callers arrive together
        # while the cache is due. Exactly ONE of them may start a round
        # (single flight - FreiXLite bans abusive polling); each is
        # answered at once from what the cache holds.
        #
        # The class takes its spawn as a constructor argument; this test
        # hands it a recorder, so no round starts unless the test runs
        # it: the election is judged on its own logic, not on which thread
        # wins a scheduler race. With a real spawn the test's detection of
        # a missing single-flight guard depended on the round thread
        # LOSING that race, and its detection of a lock held across the
        # fetch on the round thread winning it - the latter was seen to
        # survive in one run of two. "Nobody waits for a round in flight"
        # is pinned by the two tests that put one in flight first (see
        # test_the_answer_never_waits_for_a_refresh).
        rounds = []
        cache = price.PriceCache(exchange_fetch=self.exchange,
                                 cmc_fetch=self.cmc, clock=self.clock,
                                 spawn=rounds.append)   # recorded, not run
        cache.snapshot()                          # the cache holds a quote
        self.clock.advance(price.CMC_TTL_S + 1)   # both legs due
        arrive = threading.Barrier(8)
        answers = []

        def caller():
            arrive.wait(5)                        # all eight arrive together
            answers.append(cache.serve()["price"]["usd"])

        threads = [threading.Thread(target=caller) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
        self.assertEqual(answers, [MAZA_USD] * 8)   # the previous quote
        self.assertEqual(len(rounds), 1)            # one round requested

    def test_a_round_that_cannot_start_releases_the_election(self):
        # Own audit (2026-11-26), read off the final bytes: serve() marks
        # the round as running BEFORE it starts it, off the request. If
        # starting it fails (no thread can be created), the round's own
        # finally never runs - and unless the election is released right
        # there, no refresh could ever run again: every later caller, the
        # refresher included, would find the flag set, and the feed would
        # answer nothing until a restart. The caller is still answered.
        started = []
        broken = [True]

        def spawn(work):
            started.append(work)
            if broken[0]:
                raise RuntimeError("can't start new thread")
            work()                              # a round that really runs

        cache = price.PriceCache(exchange_fetch=self.exchange,
                                 cmc_fetch=self.cmc, clock=self.clock,
                                 spawn=spawn)
        cache.snapshot()                        # the cache holds a quote
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            for _ in range(3):
                self.clock.advance(price.CMC_TTL_S + 1)   # both legs due
                # Nothing escapes the request path; the answer is the
                # previous quote.
                self.assertEqual(cache.serve()["price"]["usd"], MAZA_USD)
            self.assertEqual(len(started), 3)   # every caller could elect
            broken[0] = False
            self.clock.advance(price.CMC_TTL_S + 1)
            cache.serve()                       # a round that runs at last
            self.assertEqual(len(started), 4)
            found = cache.serve()["price"]      # what that round fetched
        self.assertEqual((found["usd"], found["age_s"]), (MAZA_USD, 0))
        self.assertEqual(len(started), 4)       # fresh: nothing left due
        # Logged by class name only - never the message text.
        self.assertEqual(out.getvalue().count("PRICE_REFRESH spawn error="),
                         3)
        self.assertIn("PRICE_REFRESH spawn error=RuntimeError",
                      out.getvalue())
        self.assertNotIn("can't start new thread", out.getvalue())

    def test_snapshot_waits_only_for_a_round_it_starts(self):
        cache = build(self.exchange, self.cmc, self.clock)
        cache.snapshot()
        self.clock.advance(price.CMC_TTL_S + 1)    # both legs due
        self.exchange.gate = threading.Event()
        first, second = {}, {}

        def leader():
            first.update(cache.snapshot()["price"])

        thread = threading.Thread(target=leader)
        thread.start()
        self.assertTrue(until(lambda: self.exchange.calls == 2))
        try:
            tick = time.monotonic()
            second.update(cache.snapshot()["price"])    # not queued behind it
            self.assertLess(time.monotonic() - tick, 0.5)
        finally:
            self.exchange.gate.set()
        thread.join(5)
        # Served while the leader was still inside its fetch: the previous
        # quote with its true age.
        self.assertEqual((second["usd"], second["age_s"]),
                         (MAZA_USD, price.CMC_TTL_S + 1))
        self.assertEqual(first["age_s"], 0)             # the leader's own round
        self.assertEqual((self.exchange.calls, self.cmc.calls), (2, 2))

    def test_a_quote_stamped_in_the_future_is_never_shown_as_fresh(self):
        # Review fold (deleg_1ab54e7f F7): the clock steps BACKWARDS (an
        # NTP correction, a VM restored from a snapshot). Against a plain
        # wall-clock comparison every held quote is then "from the
        # future" - 0 s old and not stale for as long as the step lasts -
        # and no TTL runs out in that time either. A future stamp is
        # unmeasurable: the source is fetched again and the old quote is
        # not shown.
        cache = build(self.exchange, self.cmc, self.clock)
        cache.snapshot()
        before = self.exchange.calls
        self.clock.advance(-3600)
        self.exchange.ok, self.exchange.reason = False, "timeout"
        found = cache.snapshot()["price"]
        self.assertEqual(self.exchange.calls, before + 1)     # re-fetched
        self.assertEqual((found["source"], found["age_s"]),    # not the venue
                         ("coinmarketcap", 0))                # quote: future
        # And once nothing held survives: no number, both sources named.
        self.cmc.quotes, self.cmc.reason = {}, "unreachable"
        self.clock.advance(price.MAX_AGE_S + 3601)
        answer = cache.snapshot()
        self.assertIsNone(answer["price"])
        self.assertEqual(answer["reason"],
                         "freixlite:timeout; coinmarketcap:unreachable")

    def test_a_partly_failed_dollar_leg_is_named_not_called_ok(self):
        # Review fold (deleg_1ab54e7f F10): the displayed rate can rest on
        # a CoinMarketCap pass that lost a symbol. The price is still
        # good (the kept rates) - but the pass reads "partial", never ok.
        cache = build(self.exchange, self.cmc, self.clock)
        first = cache.snapshot()
        self.assertEqual(first["attempts"], ["freixlite:ok",
                                             "coinmarketcap:ok"])
        self.clock.advance(price.CMC_TTL_S + 1)
        self.cmc.quotes, self.cmc.reason = {"MAZA": MAZA_CMC}, "partial"
        second = cache.snapshot()
        self.assertEqual((second["price"]["usd"], second["price"]["source"]),
                         (MAZA_USD, "freixlite"))         # the kept LTC rate
        self.assertEqual(second["attempts"], ["freixlite:ok",
                                              "coinmarketcap:partial"])

    def test_a_broken_background_round_is_logged_and_the_election_ends(self):
        # serve() starts its round on a thread nobody joins. A bug inside
        # the round must be logged (by class name only) and must not
        # leave the cache stuck in "a round is running" forever.
        class Ticking:
            calls = 0

            def __call__(self):
                self.calls += 1
                # serve() reads the clock twice before it elects; the
                # third read is the round's own, inside _round().
                if self.calls > 2:
                    raise RuntimeError("boom")   # inside the round
                return 1_700_000_000.0

        cache = price.PriceCache(exchange_fetch=self.exchange,
                                 cmc_fetch=self.cmc, clock=Ticking())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cache.serve()
            self.assertTrue(settle(cache))
        self.assertEqual(out.getvalue().splitlines(),
                         ["PRICE_REFRESH refresher error=RuntimeError"])
        self.assertFalse(cache._refreshing)     # the election ended
        cache._clock = self.clock                # healed: works again
        self.assertEqual(cache.snapshot()["price"]["usd"], MAZA_USD)

    def test_unavailable_survives_a_price_that_cannot_be_priced(self):
        # Trading pairs exist but are past MAX_AGE and CoinMarketCap is
        # empty: no number, with the reason naming both sources.
        cache = build(self.exchange, self.cmc, self.clock)
        cache.snapshot()
        self.exchange.ok, self.exchange.reason = False, "unreachable"
        self.cmc.quotes, self.cmc.reason = {}, "no_quote"
        self.clock.advance(price.MAX_AGE_S + 1)
        answer = cache.snapshot()
        self.assertIsNone(answer["price"])
        self.assertEqual(answer["reason"],
                         "freixlite:unreachable; coinmarketcap:no_quote")


class TestRefreshLogLine(unittest.TestCase):
    """PRICE_REFRESH is observability only: reason codes and a source
    name - never a price, a key or a URL."""

    def refresh_line(self, cache):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cache.refresh()
        return out.getvalue()

    def test_line_shape_and_nothing_price_bearing(self):
        cache = build(Exchange([MAZA_LTC]),
                      Cmc({"MAZA": MAZA_CMC, "LTC": LTC_USD}))
        line = self.refresh_line(cache).strip()
        self.assertRegex(line, r"^PRICE_REFRESH seq=\d+ exchange=ok cmc=ok "
                               r"mode=web source=freixlite stale=0$")
        for forbidden in ("0.00180967", "42.50", "0.00004258", "27644",
                          "freiexchange.com", "coinmarketcap.com"):
            self.assertNotIn(forbidden, line)

    def test_reason_codes_on_failure(self):
        cache = build(Exchange(None, ok=False, reason="timeout"),
                      Cmc({}, reason="http_403"))
        line = self.refresh_line(cache)
        self.assertIn("exchange=timeout", line)
        self.assertIn("cmc=http_403 mode=web source=none", line)

    def test_a_partial_dollar_leg_is_not_logged_as_ok(self):
        # Review fold (deleg_1ab54e7f F10): the line is where an operator
        # looks to see whether the feed is whole.
        cache = build(Exchange([MAZA_LTC]),
                      Cmc({"MAZA": MAZA_CMC, "LTC": LTC_USD}, reason="partial"))
        line = self.refresh_line(cache)
        self.assertIn("exchange=ok cmc=partial mode=web source=freixlite",
                      line)

    def test_quiet_when_nothing_was_fetched(self):
        cache = build(Exchange([MAZA_LTC]),
                      Cmc({"MAZA": MAZA_CMC, "LTC": LTC_USD}))
        self.assertTrue(self.refresh_line(cache))  # a real fetch logs
        self.assertEqual(self.refresh_line(cache), "")  # a cached one is silent

    def test_official_mode_is_named_without_the_key(self):
        cache = build(Exchange([MAZA_LTC]),
                      Cmc({"MAZA": MAZA_CMC, "LTC": LTC_USD}, mode="official"))
        line = self.refresh_line(cache)
        self.assertIn("mode=official", line)
        self.assertNotIn(FAKE_KEY, line)


class TestRefresher(unittest.TestCase):
    def test_warms_the_cache_and_is_idempotent(self):
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("boom")   # an unexpected blow-up
            return True, [MAZA_LTC], ""

        # The fake clock runs 10000x fast (10 ms real = 100 s), so every
        # pass of the refresher is past the venue's TTL.
        cmc = Cmc({"MAZA": MAZA_CMC, "LTC": LTC_USD})
        cache = price.PriceCache(exchange_fetch=flaky, cmc_fetch=cmc,
                                 clock=lambda: time.monotonic() * 10000)
        out = io.StringIO()
        with mock.patch.object(price, "_default", cache), \
                mock.patch.object(price, "_refresher_started", False), \
                mock.patch.object(price, "_stop", threading.Event()) as stop, \
                contextlib.redirect_stdout(out):
            try:
                price.start_refresher(interval=0.01)
                price.start_refresher(interval=0.01)          # idempotent
                deadline = time.time() + 5
                while len(calls) < 2 and time.time() < deadline:
                    time.sleep(0.01)
                answer = price.current()["price"]             # served warm
                stop.set()
                for thread in threading.enumerate():
                    if thread.name == "price-refresher":
                        thread.join(5)
                        self.assertFalse(thread.is_alive())
            finally:
                stop.set()
        self.assertEqual(answer["usd"], MAZA_USD)
        lines = out.getvalue().splitlines()
        self.assertGreaterEqual(len(lines), 2)
        self.assertIn("exchange=error_RuntimeError cmc=ok", lines[0])
        self.assertIn("source=coinmarketcap", lines[0])
        self.assertTrue(any("exchange=ok cmc=ok mode=web source=freixlite "
                            "stale=0" in line for line in lines[1:]), lines)
        self.assertFalse(any("refresher error=" in line for line in lines))

    def test_the_loop_survives_a_crashing_refresh(self):
        class Crashing:
            def refresh(self):
                raise RuntimeError("boom")

        out = io.StringIO()
        with mock.patch.object(price, "_default", Crashing()), \
                mock.patch.object(price, "_refresher_started", False), \
                mock.patch.object(price, "_stop", threading.Event()) as stop, \
                contextlib.redirect_stdout(out):
            try:
                price.start_refresher(interval=0.01)
                deadline = time.time() + 5
                while len(out.getvalue().splitlines()) < 2 and time.time() < deadline:
                    time.sleep(0.01)
                stop.set()
                for thread in threading.enumerate():
                    if thread.name == "price-refresher":
                        thread.join(5)
                        self.assertFalse(thread.is_alive())
            finally:
                stop.set()
        lines = out.getvalue().splitlines()
        self.assertGreaterEqual(len(lines), 2)
        self.assertEqual(set(lines), {"PRICE_REFRESH refresher error=RuntimeError"})


class TestnetChain(MockChain):
    """A bench whose address book holds testnet (v88) addresses."""

    def getnewaddress(self) -> str:
        return encode_address(88, b"\x11" * 20)


class DeadChain(MockChain):
    def getnewaddress(self) -> str:
        raise ChainError("rpc: connection refused")


class TestRefresherNetworkGate(unittest.TestCase):
    """M28 (replayed review deleg_6106976c): serve() started the price
    refresher on EVERY bench, so a testnet bench polled the upstream price
    APIs every 15s for quotes its own /api/price route refuses (testnet
    coins have no market). serve() now consults the book's address version
    first: a testnet (or otherwise non-mainnet) book skips the refresher,
    and an unreadable version fails OPEN, because a boot-time chain race
    must not disable the mainnet bench's pre-warm and the per-request
    route gate stays the correctness backstop."""

    def setUp(self):
        import tempfile
        fd, state_file = tempfile.mkstemp(prefix="maza-refresher-", suffix=".json")
        os.close(fd)
        os.unlink(state_file)  # missing file = fresh cold start, not corrupt
        os.environ["WB_STATE_FILE"] = state_file
        self.state_file = state_file
        self.addCleanup(os.environ.pop, "WB_STATE_FILE", None)
        self.addCleanup(self.drop_state_file)

    def fresh_book(self):
        """Forget the book in memory AND on disk: a case that cold-started
        the previous chain must not leak its persisted addresses into the
        next case's load (subtest 2 would otherwise re-read subtest 1's
        testnet book and skip for the wrong reason)."""
        api._cache.pop("addresses", None)
        api._cache.pop("txids", None)
        api._cache.pop("watch_addresses", None)
        self.drop_state_file()

    def drop_state_file(self):
        if os.path.exists(self.state_file):
            os.unlink(self.state_file)

    def test_mainnet_book_starts_the_refresher(self):
        self.fresh_book()
        self.assertIsNone(api._refresher_reason(MockChain()))

    def test_testnet_book_skips_the_refresher(self):
        self.fresh_book()
        self.assertEqual(api._refresher_reason(TestnetChain()), "testnet")

    def test_unreadable_version_fails_open(self):
        self.fresh_book()
        self.assertIsNone(api._refresher_reason(DeadChain()))

    def test_serve_starts_the_refresher_only_for_a_mainnet_book(self):
        for chain, expected in ((TestnetChain(), 0), (MockChain(), 1)):
            with self.subTest(starts=bool(expected)):
                self.fresh_book()
                with mock.patch.object(api, "get_chain", return_value=chain), \
                     mock.patch.object(api.config, "TOKEN", "test-token"), \
                     mock.patch.object(api.price, "start_refresher") as start, \
                     mock.patch.object(api, "ThreadingHTTPServer") as server_cls:
                    server_cls.return_value.serve_forever = lambda: None
                    api.serve()
                    self.assertEqual(start.call_count, expected)


class TestBenchHarnessSocket(unittest.TestCase):
    """The harness this module reuses starts a real listening socket per
    test. shutdown() alone stops the loop but leaves that socket open, so
    every test in the suite that used the harness leaked one descriptor."""

    def test_cleanup_closes_the_listening_socket(self):
        harness = bench.BenchHarness()
        harness.server, _ = bench.make_server(MockChain())
        listener = harness.server.socket
        self.assertNotEqual(listener.fileno(), -1)  # open before cleanup
        harness._stop_server()
        # Closed by the cleanup, not by garbage collection: `listener` is
        # still referenced here, so it could not have been collected.
        self.assertEqual(listener.fileno(), -1)


class TestPriceEndpoint(bench.BenchHarness):
    """GET /api/price on the bench API. The process-wide cache is replaced
    by one fed by fakes, so no request in this class touches a network."""

    def setUp(self):
        super().setUp()
        self.clock = Clock()
        self.exchange = Exchange([MAZA_LTC, MAZA_BTC_DEAD])
        self.cmc = Cmc({"MAZA": MAZA_CMC, "BTC": BTC_USD, "LTC": LTC_USD})
        patcher = mock.patch.object(price, "_default",
                                    build(self.exchange, self.cmc, self.clock))
        patcher.start()
        self.addCleanup(patcher.stop)

    def get_price(self, headers=None):
        request = urllib.request.Request(self.base + "/api/price",
                                         headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json_or_none(response.read())
        except urllib.error.HTTPError as exc:
            with exc:  # an error response is an open socket until closed
                return exc.code, json_or_none(exc.read())

    def test_requires_the_bench_token(self):
        self.assertEqual(self.get_price()[0], 401)
        self.assertEqual(self.exchange.calls, 0)

    def warm(self):
        # The request path never fetches (M27): a round is the
        # refresher's call, so a test that expects a price runs one.
        price._default.snapshot()

    def test_shape_over_cookie_auth(self):
        self.warm()
        cookie = self.unlock()
        status, headers, body = self.request("GET", "/api/price", cookie=cookie)
        self.assertEqual(status, 200)
        answer = json_or_none(body)
        self.assertEqual(sorted(answer), ["attempts", "price"])
        found = answer["price"]
        self.assertEqual(sorted(found), PRICE_FIELDS)
        self.assertEqual((found["usd"], found["source"], found["pair"]),
                         (MAZA_USD, "freixlite", "MAZA_LTC"))

    def test_shape_over_bearer_auth(self):
        self.warm()
        status, answer = self.get_price({"Authorization": "Bearer " + bench.TOKEN})
        self.assertEqual(status, 200)
        self.assertEqual(answer["price"]["usd"], MAZA_USD)

    def test_unavailable_is_a_200_with_null(self):
        cookie = self.unlock()
        self.exchange.ok, self.exchange.reason = False, "timeout"
        self.cmc.quotes, self.cmc.reason = {}, "unreachable"
        cache = build(self.exchange, self.cmc, Clock())
        cache.snapshot()          # the round asks the dead sources
        with mock.patch.object(price, "_default", cache):
            status, _, body = self.request("GET", "/api/price", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(json_or_none(body), {
            "price": None,
            "reason": "freixlite:timeout; coinmarketcap:unreachable",
            "attempts": ["freixlite:timeout", "coinmarketcap:unreachable"]})

    def test_the_answer_never_waits_for_a_refresh(self):
        # Review fold (deleg_1ab54e7f F2): the round is ALREADY in
        # flight - the refresher's, exactly as a wallet request meets it
        # - with the venue hung. The request is answered at once with the
        # PREVIOUS quote and its true age: it never queues behind the
        # round's lock.
        #
        # The sibling test below lets the request start the round itself;
        # that request is answered before any lock is contended, so it
        # cannot see a lock held across a fetch. In the mutation run the
        # sibling SURVIVED a lock held over I/O; this one does not.
        self.warm()
        self.clock.advance(120)                   # venue TTL spent ...
        self.exchange.gate = threading.Event()    # ... and hung
        refresher = threading.Thread(
            target=price._default.refresh, daemon=True)
        refresher.start()
        self.assertTrue(until(lambda: self.exchange.calls == 2))   # in flight
        # Bounded twice over: the fake releases its own gate after 5 s
        # and this timer after 8. A request that does wait, waits a
        # bounded time and then FAILS below - the test cannot hang.
        opener = threading.Timer(8.0, self.exchange.gate.set)
        opener.daemon = True
        opener.start()
        cookie = self.unlock()
        try:
            tick = time.monotonic()
            status, _, body = self.request("GET", "/api/price", cookie=cookie)
            waited = time.monotonic() - tick
        finally:
            self.exchange.gate.set()
            opener.cancel()
        refresher.join(5)
        self.assertEqual(status, 200)
        self.assertLess(waited, 1.0)
        found = json_or_none(body)["price"]
        self.assertEqual((found["usd"], found["age_s"], found["stale"]),
                         (MAZA_USD, 120, False))

    def test_the_request_that_starts_a_round_does_not_wait_for_it(self):
        # M27: an expired TTL with a hung venue. The request that starts
        # the background round is still answered at once, with the
        # PREVIOUS quote and its true age; the round lands behind it.
        self.warm()
        self.clock.advance(120)                   # venue TTL spent ...
        self.exchange.gate = threading.Event()    # ... and hung
        cookie = self.unlock()
        try:
            tick = time.monotonic()
            status, _, body = self.request("GET", "/api/price", cookie=cookie)
            waited = time.monotonic() - tick
        finally:
            self.exchange.gate.set()
        self.assertTrue(settle(price._default))
        self.assertEqual(status, 200)
        self.assertLess(waited, 1.0)
        found = json_or_none(body)["price"]
        self.assertEqual((found["usd"], found["age_s"], found["stale"]),
                         (MAZA_USD, 120, False))
        self.assertEqual(self.exchange.calls, 2)  # warm-up + the round

    def test_a_cold_cache_fails_closed_and_starts_one_round(self):
        # Before the first round lands there is nothing to show: null with
        # both sources named - and the request starts ONE background round
        # rather than fetching on the wallet's request.
        cookie = self.unlock()
        status, _, body = self.request("GET", "/api/price", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(json_or_none(body), {
            "price": None,
            "reason": "freixlite:not_fetched; coinmarketcap:not_fetched",
            "attempts": ["freixlite:not_fetched",
                         "coinmarketcap:not_fetched"]})
        self.assertTrue(settle(price._default))
        self.assertEqual((self.exchange.calls, self.cmc.calls), (1, 1))
        status, _, body = self.request("GET", "/api/price", cookie=cookie)
        self.assertEqual(json_or_none(body)["price"]["usd"], MAZA_USD)

    def test_testnet_bench_never_quotes_a_price(self):
        api.WalletBenchHandler.chain = TestnetChain()
        cookie = self.unlock()
        status, _, body = self.request("GET", "/api/price", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(json_or_none(body), {"price": None, "reason": "testnet"})
        self.assertEqual(self.exchange.calls, 0)    # never even asked

    def test_chain_down_on_a_cold_start_fails_closed(self):
        api.WalletBenchHandler.chain = DeadChain()
        cookie = self.unlock()
        status, _, body = self.request("GET", "/api/price", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(json_or_none(body),
                         {"price": None, "reason": "network_unknown"})
        self.assertEqual(self.exchange.calls, 0)


if __name__ == "__main__":
    unittest.main()
