#!/usr/bin/env python3
"""Wiring contract for M26: MAZA price discovery (wallet half).

The deciding lives in walletbench/price.py and is covered BEHAVIORALLY in
tests/test_price.py. This file pins the wallet side:

  - PriceLine / PricePoll are pure Java: compiled here on the desktop JVM
    and driven for real (the exact copy, the minute gate and its session
    ticket, what is refused).
  - both wallet screens read the price through Api.readPrice, hide the
    line when there is nothing to show, and never turn a price into a
    float. One gate per session is shared by both lines; the read runs
    off the balance worker; a new session forgets the old price, and the
    paint repeats the session check (an answer recorded just before the
    session ended must never reach the screen).
  - the bench's JSON keys and the app's keys are the SAME set (one
    contract across two languages).
  - the read is a registered Net route; nothing price-bearing or secret
    can reach a log line; the APK never talks to a price source itself.

Run:  python3 -m unittest tests.test_price_wiring -v
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_w3_network_repaint import (  # noqa: E402
    JAVA, JAVAC, MAIN_ACTIVITY, NET, REPO_ROOT, SELF_CUSTODY, SRC,
    method_body, parse_route_table, read_text, strip_comments)
from walletbench import price  # noqa: E402

ANDROID_SRC = os.path.join(REPO_ROOT, "android", "src")
API = os.path.join(SRC, "Api.java")
PRICE_LINE = os.path.join(SRC, "PriceLine.java")
PRICE_POLL = os.path.join(SRC, "PricePoll.java")
PURE_JAVA = ("PriceLine.java", "PricePoll.java")
TOUCHED = ("Api.java", "Net.java", "MainActivity.java", "SelfCustody.java",
           "PriceLine.java", "PricePoll.java")
# Only the bench may call a price source; the APK never does.
UPSTREAM_HOSTS = ("freiexchange", "coinmarketcap.com", "pro-api.coinmarketcap")
# Keys the bench sends and the wallet deliberately does not read. Changing
# this set is a conscious decision, never an accident:
#   quote_usd  - the dollar leg's rate, an audit field for API consumers;
#                the wallet shows the already-computed "usd".
#   updated_at - wall clock; the wallet shows "age_s", which the bench
#                computes and which a wrong device clock cannot distort.
NOT_SHOWN = {"quote_usd", "updated_at"}

PROBE = r"""
package com.mazawallet;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public final class PriceProbe {
    static int checks = 0;

    static void eq(String want, String got, String what) {
        checks++;
        if (want == null ? got != null : !want.equals(got)) {
            System.out.println("FAIL " + what + ": want [" + want
                    + "] got [" + got + "]");
            System.exit(1);
        }
    }

    static void ok(boolean cond, String what) {
        checks++;
        if (!cond) {
            System.out.println("FAIL " + what);
            System.exit(1);
        }
    }

    static PriceLine.Quote q(String usd, String source, String pair,
            String last, String quote, long ageS, boolean stale) {
        return new PriceLine.Quote(usd, source, pair, last, quote, ageS, stale);
    }

    public static void main(String[] args) {
        // The lines a user can actually see.
        eq("1 MAZA \u2248 $0.00180249 \u00B7 FreiXLite MAZA_LTC \u00B7 42s old",
                PriceLine.format(q("0.00180249", "freixlite", "MAZA_LTC",
                        "0.00004258", "LTC", 42, false)),
                "venue price through the dollar leg");
        eq("1 MAZA \u2248 $0.00180249 \u00B7 FreiXLite MAZA_LTC \u00B7 STALE 16m old",
                PriceLine.format(q("0.00180249", "freixlite", "MAZA_LTC",
                        "0.00004258", "LTC", 960, true)),
                "a stale quote says so");
        eq("1 MAZA \u2248 $0.00122588 \u00B7 CoinMarketCap \u00B7 2m old",
                PriceLine.format(q("0.00122588", "coinmarketcap", null, null,
                        null, 120, false)),
                "the fallback names its source and no pair");
        eq("1 MAZA \u2248 0.00004258 LTC \u00B7 FreiXLite MAZA_LTC \u00B7 0s old",
                PriceLine.format(q(null, "freixlite", "MAZA_LTC",
                        "0.00004258", "LTC", 0, false)),
                "no dollar leg: the venue price in its own currency");
        eq("1 MAZA \u2248 $0.5 \u00B7 other_venue \u00B7 1s old",
                PriceLine.format(q("0.5", "other_venue", null, null, null, 1, false)),
                "an unknown source is shown as its plain code");

        // Nothing dishonest is ever printed.
        ok(PriceLine.format(null) == null, "no quote, no line");
        String[] notAmounts = {null, "", "0", "0.00000000", "-1", "1e-8",
                "NaN", "Infinity", "1,50", "$1", "abc", "<b>1</b>", "1;drop",
                "0.001802490000000001", "1234567890123", "00.5", "007",
                "01"};
        for (String bad : notAmounts) {
            ok(PriceLine.format(q(bad, "freixlite", "MAZA_LTC", null, null,
                    1, false)) == null, "not an amount: [" + bad + "]");
            ok(PriceLine.format(q(null, "freixlite", "MAZA_LTC", bad, "LTC",
                    1, false)) == null, "not a venue price: [" + bad + "]");
        }
        eq("1 MAZA \u2248 $0.5 \u00B7 0s old",
                PriceLine.format(q("0.5", "<script>", "<b>", null, null, 0, false)),
                "text that is not a symbol is dropped");
        ok(PriceLine.format(q("0.5", "freixlite", null, null, null, -5, false)) == null,
                "a negative age is not an age: no line");
        // An amount is printed exactly as sent - never re-rounded here.
        eq("1 MAZA \u2248 $0.50000001 \u00B7 FreiXLite \u00B7 59s old",
                PriceLine.format(q("0.50000001", "freixlite", null, null,
                        null, 59, false)),
                "an amount is printed as sent");

        // M27 (review fold deleg_1ab54e7f F8): the two honesty fields are
        // read strictly. A quote of UNKNOWN age is not shown - a default
        // of "0 seconds old, not stale" would invent freshness.
        eq("1 MAZA \u2248 $0.5 \u00B7 FreiXLite MAZA_LTC \u00B7 42s old",
                PriceLine.format(PriceLine.Quote.of("0.5", "freixlite",
                        "MAZA_LTC", "1", "LTC", 42, false)),
                "a JSON integer age and a JSON boolean stale: a whole quote");
        eq("1 MAZA \u2248 $0.5 \u00B7 FreiXLite MAZA_LTC \u00B7 STALE 43s old",
                PriceLine.format(PriceLine.Quote.of("0.5", "freixlite",
                        "MAZA_LTC", "1", "LTC", 43L, Boolean.TRUE)),
                "a long age and a boxed stale flag");
        eq("1 MAZA \u2248 $0.5 \u00B7 FreiXLite \u00B7 0s old",
                PriceLine.format(PriceLine.Quote.of("0.5", "freixlite", null,
                        null, null, 0, false)),
                "a real zero age is an age: 0s old, not unknown");
        Object[] notAnAge = {null, 42.0, "42", Boolean.TRUE, -1, -5L};
        for (Object bad : notAnAge) {
            ok(PriceLine.Quote.of("0.5", "freixlite", "MAZA_LTC", "1", "LTC",
                    bad, false) == null, "not an age: [" + bad + "]");
        }
        Object[] notAFlag = {null, "false", "true", 0, 1};
        for (Object bad : notAFlag) {
            ok(PriceLine.Quote.of("0.5", "freixlite", "MAZA_LTC", "1", "LTC",
                    42, bad) == null, "not a stale flag: [" + bad + "]");
        }
        ok(PriceLine.format(PriceLine.Quote.of("0.5", "freixlite", null, null,
                null, null, false)) == null,
                "a quote with no age renders no line at all");

        // Age buckets.
        eq("0s old", PriceLine.age(0), "age 0");
        eq("59s old", PriceLine.age(59), "age 59");
        eq("1m old", PriceLine.age(60), "age 60");
        eq("59m old", PriceLine.age(3599), "age 3599");
        eq("1h old", PriceLine.age(3600), "age 3600");
        eq("23h old", PriceLine.age(86399), "age 86399");
        eq("1d old", PriceLine.age(86400), "age 86400");

        // The minute gate, shared by every line that shows a price.
        PricePoll p = new PricePoll();
        ok(p.last() == null, "nothing on screen before the first read");
        long t1 = p.due(1_000L);
        ok(t1 >= 0, "the first read is due right away");
        ok(p.due(30_000L) == PricePoll.NOT_DUE, "not due inside the minute");
        ok(p.due(60_999L) == PricePoll.NOT_DUE, "still not at 59.999 s");
        long t2 = p.due(61_000L);
        ok(t2 == t1, "due 60 s after the ask, same session");
        PriceLine.Quote live = q("0.00180249", "freixlite", "MAZA_LTC",
                "0.00004258", "LTC", 42, false);
        ok(p.record(t2, live), "the answer lands in the session it was asked in");
        ok(p.last() == live, "and is remembered for repaints");

        // A 404 from an older bench stops the asking - for that session only.
        p.retire(t2);
        ok(p.due(10_000_000L) == PricePoll.NOT_DUE,
                "an endpoint without the route is never asked again");
        p.clear();
        ok(p.last() == null, "a new session forgets the previous endpoint's price");
        ok(!p.record(t2, live), "a late answer from the previous session is dropped");
        ok(p.last() == null, "so the new session's line stays hidden");
        p.retire(t2);
        long t3 = p.due(10_000_001L);
        ok(t3 >= 0 && t3 != t2, "a new session asks right away, under a new ticket");
        ok(p.due(10_000_002L) == PricePoll.NOT_DUE, "the gate closes again after the ask");
        ok(p.record(t3, null), "no source: recorded as null");
        ok(p.last() == null, "no source: the line is hidden");
        p.retire(t3);
        ok(p.due(10_000_003L) == PricePoll.NOT_DUE,
                "retired in this session: never asked again");

        // The paint repeats the check. An answer can be recorded (the
        // session still live), then the session end, and only then the
        // UI thread paint it: that paint must refuse the old ticket.
        PricePoll s = new PricePoll();
        long ask = s.due(1_000L);
        ok(s.isCurrent(ask), "the ticket of the live session is current");
        ok(s.record(ask, live), "recorded while the session lives");
        ok(s.isCurrent(ask), "still current until the session ends");
        s.clear();
        ok(!s.isCurrent(ask), "not current once the session has ended");
        long next = s.due(1_001L);
        ok(next != ask && s.isCurrent(next),
                "a new session: a new ticket, and it is current");
        ok(!s.isCurrent(PricePoll.NOT_DUE), "no ticket is never current");

        // The gate is atomic: lines asking at the same moment get ONE read.
        int rounds = 2000;
        int clean = 0;
        for (int round = 0; round < rounds; round++) {
            final PricePoll race = new PricePoll();
            final CountDownLatch go = new CountDownLatch(1);
            final AtomicInteger tickets = new AtomicInteger();
            Thread[] askers = new Thread[4];
            for (int i = 0; i < askers.length; i++) {
                askers[i] = new Thread(() -> {
                    try {
                        go.await();
                    } catch (InterruptedException e) {
                        throw new RuntimeException(e);
                    }
                    if (race.due(1_000L) != PricePoll.NOT_DUE) {
                        tickets.incrementAndGet();
                    }
                });
                askers[i].start();
            }
            go.countDown();
            for (Thread t : askers) {
                try {
                    t.join();
                } catch (InterruptedException e) {
                    throw new RuntimeException(e);
                }
            }
            if (tickets.get() == 1) clean++;
        }
        ok(clean == rounds, "one ticket per round, got " + clean);

        System.out.println("ALL PRICE PROBES PASSED (" + checks + " checks)");
    }
}
"""


def code(path):
    """Source with comments stripped: assertions target code, not prose."""
    return strip_comments(read_text(path))


class PriceJvmProbe(unittest.TestCase):
    def test_line_and_gate_on_desktop_jvm(self):
        if not JAVAC or not JAVA:
            self.skipTest("javac/java unavailable - JVM probe not run")
        workdir = tempfile.mkdtemp(prefix="maza-price-probe-")
        try:
            classes = os.path.join(workdir, "classes")
            os.makedirs(classes)
            sources = {name: read_text(os.path.join(SRC, name))
                       for name in PURE_JAVA}
            sources["PriceProbe.java"] = PROBE
            for name, body in sources.items():
                with open(os.path.join(workdir, name), "w",
                          encoding="ascii") as handle:
                    handle.write(body)
            compiled = subprocess.run(
                [JAVAC, "-nowarn", "-d", "classes"]
                + [os.path.join(workdir, name) for name in sorted(sources)],
                cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=180)
            self.assertEqual(compiled.returncode, 0,
                             "javac failed:\n%s"
                             % compiled.stdout.decode("utf-8", "replace"))
            run = subprocess.run(
                [JAVA, "-classpath", classes, "com.mazawallet.PriceProbe"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
            output = run.stdout.decode("utf-8", "replace")
            self.assertEqual(run.returncode, 0,
                             "Price probe failed:\n%s" % output)
            self.assertIn("ALL PRICE PROBES PASSED", output)
            self.assertNotIn("FAIL ", output)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)


class ScreenWiring(unittest.TestCase):
    """Both wallet screens: one read path, one gate, hide when empty."""

    def test_both_screens_read_through_the_shared_gate(self):
        for path in (MAIN_ACTIVITY, SELF_CUSTODY):
            src = code(path)
            ask = method_body(src, "private void pollPrice()")
            self.assertTrue(ask, path)
            self.assertIn("pricePoll.due(SystemClock.elapsedRealtime())", ask, path)
            self.assertIn("Api.readPrice(pricePoll, ticket, forUrl, tok)", ask, path)
            self.assertIn("ui.post(() -> paintPrice(price))", ask, path)
            # Not due: repaint from what the other line got, never ask.
            self.assertIn("renderPrice(pricePoll.last())", ask, path)
            self.assertIn("PriceLine.format(quote)", src, path)
            self.assertIn("line == null ? View.GONE : View.VISIBLE", src, path)
            # The line starts hidden and survives a repaint.
            self.assertIn("priceTv.setVisibility(View.GONE)", src, path)
            # Only a new session re-arms the gate: the repaint/ask path
            # (this method) must never clear it - clear() lives in
            # showWallet() alone (pinned in the one-gate test below).
            self.assertNotIn("pricePoll.clear()", ask, path)

    def test_one_gate_per_session_shared_by_both_lines(self):
        main = code(MAIN_ACTIVITY)
        custody = code(SELF_CUSTODY)
        self.assertIn("selfCustody.sharePriceGate(pricePoll);", main)
        self.assertIn("public void sharePriceGate(PricePoll shared)", custody)
        self.assertNotIn("pricePoll.clear()", custody)
        # A new session (unlock) may mean another endpoint: the previous
        # endpoint's price is forgotten BEFORE anything paints it.
        self.assertEqual(main.count("pricePoll.clear()"), 1)
        show = method_body(main, "private void showWallet()")
        self.assertLess(show.index("pricePoll.clear()"), show.index("buildWalletUi()"),
                        "showWallet must clear the gate before it paints")

    def test_the_paint_rechecks_the_session(self):
        # The worker records an answer only under a ticket that is still
        # current AT THAT MOMENT. The paint runs later, on the UI thread -
        # and clear() runs on that same thread. So a read can be recorded,
        # the session end, and the paint still be queued: the paint must
        # repeat the check before it touches the line. Without it the
        # previous endpoint's price could sit on a new session's screen
        # for up to one poll.
        # Both conditions guard ONE return, and the only paint in the
        # method follows it (comments are stripped, so prose cannot
        # satisfy this).
        for path in (MAIN_ACTIVITY, SELF_CUSTODY):
            paint = method_body(code(path), "private void paintPrice(Api.Price price)")
            self.assertTrue(paint, path)
            self.assertEqual(
                paint,
                "\n        if (price.keep || !pricePoll.isCurrent(price.ticket))"
                " return;\n        renderPrice(price.quote);\n    ",
                path)

    def test_the_price_read_is_off_the_balance_worker(self):
        # A slow or hung price read must never delay a balance: the refresh
        # worker posts the paint, and only the posted lambda asks.
        for path, paint in ((MAIN_ACTIVITY, "applyState(ws);"),
                            (SELF_CUSTODY,
                             "applyRefresh(balance, utxos, txs, scan);")):
            refresh = method_body(code(path), "void refresh()")
            self.assertTrue(refresh, path)
            self.assertNotIn("readPrice", refresh, path)
            self.assertLess(refresh.index(paint), refresh.index("pollPrice();"), path)
            # And the read itself never runs on the UI thread: pollPrice()
            # spawns its own worker, and Api.readPrice sits inside it.
            ask = method_body(code(path), "private void pollPrice()")
            self.assertTrue(ask, path)
            self.assertLess(ask.index("new Thread"), ask.index("Api.readPrice"),
                            path)

    def test_the_price_is_never_a_float(self):
        # Decimal strings end to end: no binary floating point ever touches
        # a price, on either side of the wire.
        pattern = re.compile(
            r"(?:Double\.parseDouble|Float\.parseFloat|new\s+(?:Double|Float)\()"
            r"[^;]{0,80}(?:usd|quote|last|price)", re.IGNORECASE)
        for name in TOUCHED:
            self.assertIsNone(pattern.search(code(os.path.join(SRC, name))),
                              "%s turns a price into a float" % name)


class ReadPath(unittest.TestCase):
    def test_registered_as_a_read(self):
        rows = [row for row in parse_route_table(read_text(NET))
                if row["path"] == "/api/price"]
        self.assertEqual(rows, [{"method": "GET", "path": "/api/price",
                                 "attempts": 3, "spend": False}])

    def test_the_read_goes_through_net_and_never_throws(self):
        api = code(API)
        body = api[api.index("public static Price readPrice("):]
        body = body[:body.index("private static PriceLine.Quote quoteOf(")]
        self.assertIn('Net.withRetry("GET", "/api/price",', body)
        self.assertIn("catch (IOException | JSONException e)", body)
        self.assertIn("return Price.KEEP;", body)
        self.assertIn("poll.retire(ticket);", body)
        self.assertIn("poll.record(ticket, null)", body)
        self.assertIn("poll.record(ticket, quote)", body)
        # An answer leaves with the ticket it was recorded under, so the
        # paint can repeat the session check (ScreenWiring).
        self.assertIn("poll.record(ticket, null) ? new Price(null, false, ticket)",
                      body)
        self.assertIn("poll.record(ticket, quote) ? new Price(quote, false, ticket)",
                      body)
        self.assertEqual(re.findall(r"new Price\([^;]*?\)", api),
                         ["new Price(null, true, PricePoll.NOT_DUE)",
                          "new Price(null, false, ticket)",
                          "new Price(quote, false, ticket)"], api)
        self.assertIn("public final long ticket;", api)
        # An older bench (404) stops the asking; any other failure keeps
        # the line that is on screen.
        self.assertIn("HTTP_NOT_FOUND", body)
        # The read never decides to ask: the screen took the ticket.
        self.assertNotIn("poll.due(", body)

    def test_no_price_or_key_can_reach_a_log_line(self):
        api = code(API)
        for call in re.findall(r"AppLog\.[iwd]\([^;]*?\);", api, re.DOTALL):
            self.assertIsNone(
                re.search(r"\b(?:quote|usd|source|pair|token)\b", call), call)
        for name in TOUCHED:
            self.assertNotRegex(code(os.path.join(SRC, name)),
                                r"(?<![\w.])Log\.(?:w|i|d|e|v)\(", name)


class BenchAppContract(unittest.TestCase):
    def test_the_app_reads_exactly_the_keys_the_bench_sends(self):
        from test_price import MAZA_CMC, MAZA_LTC, LTC_USD, Cmc, Exchange
        cache = price.PriceCache(exchange_fetch=Exchange([MAZA_LTC]),
                                 cmc_fetch=Cmc({"MAZA": MAZA_CMC,
                                                "LTC": LTC_USD}))
        sent = set(cache.snapshot()["price"])
        api = code(API)
        reader = api[api.index("private static PriceLine.Quote quoteOf("):]
        read = set(re.findall(r'str\(p, "([a-z_]+)"\)', reader))
        # M27: age_s and stale are read with a bare opt() - a missing value
        # must stay distinguishable, so there is no default any more.
        read |= set(re.findall(r'p\.opt(?:Long|Boolean)?\("([a-z_]+)"', reader))
        self.assertEqual(read, sent - NOT_SHOWN,
                         "a key changed on one side of the wire only")
        self.assertEqual(sent - read, NOT_SHOWN,
                         "the app stopped (or started) using a key")
        self.assertIn('optJSONObject("price")', reader)

    def test_a_missing_freshness_field_never_reads_as_fresh(self):
        # Review fold (deleg_1ab54e7f F8): the defaults are gone, the
        # strict factory is the only way a quote is built here, and the
        # behaviour itself is probed on the JVM (Quote.of, above).
        api = code(API)
        self.assertNotIn('optLong("age_s", 0)', api)
        self.assertNotIn('optBoolean("stale", false)', api)
        self.assertNotIn("new PriceLine.Quote(", api)
        self.assertIn("PriceLine.Quote.of(", api)
        self.assertIn('p.opt("age_s"), p.opt("stale")', api)
        # Neither an integer age nor a boolean flag is coerced from text.
        self.assertNotRegex(api, r"parseLong|parseBoolean|Boolean\.parseBoolean|valueOf\(\"")
        # And nowhere else is a quote built past the factory: the strict
        # read is only as good as its being the ONE way in.
        bypassed = [name for name in TOUCHED if name != "PriceLine.java"
                    and "new PriceLine.Quote(" in code(os.path.join(SRC, name))]
        self.assertEqual(bypassed, [])

    def test_only_the_bench_calls_a_price_source(self):
        # The APK carries no price-source host: discovery is the bench's
        # job, behind the token, from one place.
        offenders = []
        for root, _dirs, files in os.walk(ANDROID_SRC):
            for name in files:
                path = os.path.join(root, name)
                with open(path, encoding="utf-8", errors="ignore") as handle:
                    low = handle.read().lower()
                if any(host in low for host in UPSTREAM_HOSTS):
                    offenders.append(os.path.relpath(path, REPO_ROOT))
        self.assertEqual(offenders, [])


class SourceHygiene(unittest.TestCase):
    def test_pure_java_really_is_pure(self):
        for name in PURE_JAVA:
            src = read_text(os.path.join(SRC, name))
            self.assertNotIn("import android", src, name)
            self.assertNotRegex(src, r"https?://", name)
            self.assertNotIn("org.json", src, name)

    def test_touched_sources_are_ascii(self):
        for name in TOUCHED:
            with open(os.path.join(SRC, name), "rb") as handle:
                raw = handle.read()
            self.assertIsNone(re.search(rb"[\x80-\xff]", raw), name)

    def test_cadence_is_one_named_constant(self):
        src = code(PRICE_POLL)  # assertions target code, never prose
        self.assertIn("INTERVAL_MS = 60_000L", src)
        self.assertEqual(src.count("60_000"), 1)

    def test_every_gate_method_holds_the_lock(self):
        # The race probe in PriceJvmProbe only trips now and then (an
        # unsynchronized gate slipped through ~1 round in 2000 here), so the
        # lock is pinned structurally as well: every method of the gate is
        # synchronized. The class does no I/O, so no lock is ever held
        # across a request.
        src = code(PRICE_POLL)
        public = re.findall(r"public (?:synchronized )?[\w.]+ (\w+)\(", src)
        locked = re.findall(r"public synchronized [\w.]+ (\w+)\(", src)
        self.assertEqual(len(public), 6, public)
        self.assertEqual(locked,
                         ["due", "record", "last", "retire", "clear", "isCurrent"])


if __name__ == "__main__":
    unittest.main()
