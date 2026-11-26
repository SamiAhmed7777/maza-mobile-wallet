#!/usr/bin/env python3
"""Offline tests for MAZA price discovery (M26, walletbench/price.py).

No network: every upstream is a fake. Pins the policy Payu directed
(2026-11-25) - FreiXLite primary, CoinMarketCap only where needed - and the
failure modes around it: a zero-volume pair never wins, a dead upstream
degrades to the fallback or to NO price (never a number that cannot be
sourced), a cached value ages out, and nothing secret or price-bearing
reaches a log line.
"""
import contextlib
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
    """Fake FreiXLite /v2/summary."""

    def __init__(self, payload=None, ok=True, reason=""):
        self.payload = payload
        self.ok = ok
        self.reason = reason
        self.calls = 0

    def __call__(self):
        self.calls += 1
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
        self.assertEqual((mode, reason, sorted(quotes)), ("web", "", ["BTC", "MAZA"]))

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

    def test_fast_upstream_gets_all_three_calls(self):
        seen = []

        def fast(url, timeout, headers):
            seen.append(url)
            return True, {"data": {"symbol": "MAZA",
                                   "statistics": {"price": "1"}}}, ""

        price.cmc_quotes("", fetch=fast, mono=lambda: 0.0)
        self.assertEqual(len(seen), 3)


class TestFetchJson(unittest.TestCase):
    """The one function that really opens a socket. Every other suite
    injects a fake `fetch`, so the real branches are exercised here - and
    the 429 matters: CoinMarketCap's keyless feed rate-limits under load."""

    def test_an_http_error_is_closed_and_named_by_status(self):
        # `error` stays referenced by this test on purpose: left to the
        # garbage collector, the response's file object would be closed
        # anyway, and then this assertion could not tell the difference.
        body = io.BytesIO(b"Too Many Requests")
        error = urllib.error.HTTPError("https://upstream.invalid/x", 429,
                                       "Too Many Requests", {}, body)
        original = urllib.request.urlopen

        def refuse(request, timeout=None):
            raise error

        urllib.request.urlopen = refuse
        try:
            answer = price.fetch_json("https://upstream.invalid/x")
        finally:
            urllib.request.urlopen = original
        self.assertEqual(answer, (False, None, "http_429"))
        self.assertTrue(body.closed)

    def test_a_good_response_is_decoded_with_the_named_headers(self):
        seen = {}
        original = urllib.request.urlopen

        def serve(request, timeout=None):
            seen["url"] = request.full_url
            seen["accept"] = request.get_header("Accept")
            seen["agent"] = request.get_header("User-agent")
            return io.BytesIO(b'{"ok": true}')

        urllib.request.urlopen = serve
        try:
            self.assertEqual(price.fetch_json("https://upstream.invalid/x"),
                             (True, {"ok": True}, ""))
        finally:
            urllib.request.urlopen = original
        self.assertEqual(seen, {"url": "https://upstream.invalid/x",
                                "accept": "application/json",
                                "agent": price.USER_AGENT})


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
        # The cached LTC rate is past MAX_AGE_S: not resurrected by the
        # merge; the pair prices in its own currency instead.
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

    def test_single_flight(self):
        gate = threading.Event()
        calls = []

        def slow():
            calls.append(1)
            gate.wait(5)
            return True, [MAZA_LTC], ""

        cache = price.PriceCache(exchange_fetch=slow, cmc_fetch=self.cmc,
                                 clock=self.clock)
        answers = []

        def worker():
            answers.append(cache.snapshot()["price"]["usd"])

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        gate.set()
        for thread in threads:
            thread.join(5)
        self.assertEqual(answers, [MAZA_USD] * 8)
        self.assertEqual(len(calls), 1)

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
        self.exchange = Exchange([MAZA_LTC, MAZA_BTC_DEAD])
        self.cmc = Cmc({"MAZA": MAZA_CMC, "BTC": BTC_USD, "LTC": LTC_USD})
        patcher = mock.patch.object(price, "_default",
                                    build(self.exchange, self.cmc, Clock()))
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

    def test_shape_over_cookie_auth(self):
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
        status, answer = self.get_price({"Authorization": "Bearer " + bench.TOKEN})
        self.assertEqual(status, 200)
        self.assertEqual(answer["price"]["usd"], MAZA_USD)

    def test_unavailable_is_a_200_with_null(self):
        cookie = self.unlock()
        self.exchange.ok, self.exchange.reason = False, "timeout"
        self.cmc.quotes, self.cmc.reason = {}, "unreachable"
        cache = build(self.exchange, self.cmc, Clock())
        # A fresh cache answers from the dead sources.
        with mock.patch.object(price, "_default", cache):
            status, _, body = self.request("GET", "/api/price", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(json_or_none(body), {
            "price": None,
            "reason": "freixlite:timeout; coinmarketcap:unreachable",
            "attempts": ["freixlite:timeout", "coinmarketcap:unreachable"]})

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
