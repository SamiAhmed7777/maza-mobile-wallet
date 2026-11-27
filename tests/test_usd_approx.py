#!/usr/bin/env python3
"""Wiring contract for M29: the receive amount as an approximate dollar figure.

Payu's ask (2026-11-26): the "amount to request" input on RECEIVE should
also read in USD. This file pins the wallet side:

  - UsdApprox is pure Java: compiled here on the desktop JVM and driven for
    real - the exact copy, the rounding, everything it refuses, and the
    two calls the receive screen makes end to end (typed text -> sats ->
    figure; typed text -> payment URI, which stays the MAZA amount alone).
  - the figure is the typed MAZA amount times the dollar leg of the
    latest quote, exact decimals (no float), and DISPLAY ONLY.
  - NOTHING STALE: hidden for a stale quote, a quote with no usable
    dollar leg, an unusable age, or an amount that is not a positive
    number of sats. The expected strings below were computed independently
    in Python's decimal module, not copied from the Java.

Run:  python3 -m unittest tests.test_usd_approx -v
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
    JAVA, JAVAC, MAIN_ACTIVITY, REPO_ROOT, SELF_CUSTODY, SRC,
    method_body, read_text, strip_comments)

ANDROID_SRC = os.path.join(REPO_ROOT, "android", "src")
BENCH = os.path.join(REPO_ROOT, "walletbench")
USD_APPROX = os.path.join(SRC, "UsdApprox.java")
PRICE_LINE = os.path.join(SRC, "PriceLine.java")
MAZA_URI = os.path.join(SRC, "crypto", "MazaUri.java")
REQ_WATCHER = os.path.join(SRC, "ReqUsdWatcher.java")
PURE_JAVA = ("UsdApprox.java", "PriceLine.java", "crypto/MazaUri.java")

PROBE = r'''
package com.mazawallet;

import com.mazawallet.crypto.MazaUri;

/** Desktop-JVM probe for UsdApprox. One PASS/FAIL line per check. */
public final class UsdProbe {

    private static int failures = 0;

    private static PriceLine.Quote quote(String usd, long ageS,
            boolean stale) {
        return new PriceLine.Quote(usd, "freixlite", "MAZA_LTC",
                "0.00004258", "LTC", ageS, stale);
    }

    private static void check(String name, String want, String got) {
        boolean ok = want == null ? got == null : want.equals(got);
        report(name, ok, ok ? "" : "  want=" + want + " got=" + got);
    }

    private static void check(String name, boolean ok) {
        report(name, ok, "");
    }

    private static void report(String name, boolean ok, String detail) {
        if (!ok) failures++;
        System.out.println((ok ? "PASS " : "FAIL ") + name + detail);
    }

    public static void main(String[] args) {
        final String approx = "\u2248 ";
        final String dot = " \u00B7 ";
        final String tail = dot + "FreiXLite" + dot + "42s old";
        final long maza = 100000000L;
        final PriceLine.Quote fresh = quote("0.00180249", 42L, false);

        // --- the copy
        check("5000 MAZA reads as cents", approx + "$9.01" + tail,
                UsdApprox.format(5000L * maza, fresh));
        check("1 MAZA keeps four significant digits",
                approx + "$0.001802" + tail, UsdApprox.format(maza, fresh));
        check("10 MAZA", approx + "$0.01802" + tail,
                UsdApprox.format(10L * maza, fresh));
        check("100 MAZA", approx + "$0.1802" + tail,
                UsdApprox.format(100L * maza, fresh));
        check("0.5 MAZA", approx + "$0.0009012" + tail,
                UsdApprox.format(maza / 2, fresh));
        check("fallback quote names its venue and age",
                approx + "$1.80" + dot + "CoinMarketCap" + dot + "2m old",
                UsdApprox.format(1500L * maza, new PriceLine.Quote("0.0012",
                        "coinmarketcap", null, null, null, 120L, false)));
        check("trailing zeros are dropped", approx + "$0.5" + tail,
                UsdApprox.format(maza, quote("0.5", 42L, false)));
        check("largest amount the parser accepts",
                approx + "$18024900.00" + tail,
                UsdApprox.format(999999999999999999L, fresh));

        // --- the rounding
        check("cents round half up", approx + "$1.01" + tail,
                UsdApprox.format(maza, quote("1.005", 42L, false)));
        check("rounding across the dollar stays in cents",
                approx + "$1.00" + tail,
                UsdApprox.format(maza, quote("0.99996", 42L, false)));
        check("just under that boundary keeps four digits",
                approx + "$0.9999" + tail,
                UsdApprox.format(maza, quote("0.99994999", 42L, false)));
        check("the smallest figure prints as itself",
                approx + "$0.00000001" + tail,
                UsdApprox.format(maza, quote("0.00000001", 42L, false)));
        check("below it says less than", approx + "< $0.00000001" + tail,
                UsdApprox.format(1L, quote("0.001", 42L, false)));
        check("under a dollar a tie rounds up", approx + "$0.001803" + tail,
                UsdApprox.format(maza, quote("0.0018025", 42L, false)));
        check("at the floor a tie rounds up", approx + "$0.00000003" + tail,
                UsdApprox.format(maza, quote("0.000000025", 42L, false)));

        // --- everything refused: no line at all
        check("stale quote", null,
                UsdApprox.format(5000L * maza, quote("0.00180249", 900L, true)));
        check("negative age", null,
                UsdApprox.format(5000L * maza, quote("0.00180249", -1L, false)));
        check("no quote", null, UsdApprox.format(5000L * maza, null));
        check("no dollar leg", null, UsdApprox.format(5000L * maza,
                new PriceLine.Quote(null, "freixlite", "MAZA_LTC",
                        "0.00004258", "LTC", 42L, false)));
        for (String bad : new String[] {"", "abc", "1e-5", "-1", "00.5", "0"}) {
            check("dollar leg '" + bad + "' is not an amount", null,
                    UsdApprox.format(5000L * maza, quote(bad, 42L, false)));
        }
        check("zero sats", null, UsdApprox.format(0L, fresh));
        check("negative sats", null, UsdApprox.format(-5L, fresh));
        check("no sats", null, UsdApprox.format(null, fresh));

        // --- end to end: the exact two calls the receive screen makes
        final Long sats = MazaUri.parseAmountText("5000");
        check("typed 5000 goes through the real parser",
                approx + "$9.01" + tail, UsdApprox.format(sats, fresh));
        check("typed junk has no line", null,
                UsdApprox.format(MazaUri.parseAmountText("5f"), fresh));
        final String uri = MazaUri.format("MExampleAddress", sats, null, null);
        check("the payment URI is the MAZA amount alone",
                "maza:MExampleAddress?amount=5000.00000000", uri);
        check("the payment URI carries no dollar value",
                uri.indexOf('$') < 0 && !uri.contains("usd"));

        if (failures > 0) {
            System.out.println("USD PROBES FAILED: " + failures);
            System.exit(1);
        }
        System.out.println("ALL USD PROBES PASSED");
    }
}
'''


def code(path):
    """Source with comments stripped: assertions target code, not prose."""
    return strip_comments(read_text(path))


class UsdJvmProbe(unittest.TestCase):
    """The real formatter on the desktop JVM."""

    def test_every_probe_line_passes(self):
        if not (JAVA and JAVAC):
            self.skipTest("no desktop JDK")
        work = tempfile.mkdtemp(prefix="usd-probe-")
        self.addCleanup(shutil.rmtree, work, True)
        sources = []
        for name in PURE_JAVA:
            target = os.path.join(work, os.path.basename(name))
            shutil.copy(os.path.join(SRC, name), target)
            sources.append(target)
        with open(os.path.join(work, "UsdProbe.java"), "w",
                  encoding="utf-8") as handle:
            handle.write(PROBE)
        sources.append(os.path.join(work, "UsdProbe.java"))
        build = subprocess.run(
            [JAVAC, "-encoding", "UTF-8", "-Xlint:all", "-d", work] + sources,
            capture_output=True, text=True)
        self.assertEqual(build.returncode, 0, build.stderr)
        self.assertEqual(build.stderr.strip(), "", "the compile must be warning-free")
        run = subprocess.run([JAVA, "-cp", work, "com.mazawallet.UsdProbe"],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        passes = [line for line in run.stdout.splitlines() if line.startswith("PASS ")]
        fails = [line for line in run.stdout.splitlines() if line.startswith("FAIL ")]
        self.assertEqual(fails, [], run.stdout)
        self.assertEqual(len(passes), 32, run.stdout)
        self.assertEqual(run.stdout.splitlines()[-1], "ALL USD PROBES PASSED")


class ReceiveFigure(unittest.TestCase):
    """How the receive screen uses it."""

    def test_the_line_starts_hidden_under_the_input(self):
        build = method_body(code(MAIN_ACTIVITY), "private void buildReceiveTab()")
        self.assertTrue(build)
        made = 'reqUsdTv = label("", 12, pal.textSecondary(), Typeface.NORMAL);'
        hidden = "reqUsdTv.setVisibility(View.GONE);"
        added = "col.addView(reqUsdTv, "
        self.assertEqual(build.count(made), 1)
        self.assertEqual(build.count(hidden), 1)
        self.assertEqual(build.count(added), 1)
        # Input, then the figure, then the button that composes the request.
        self.assertLess(build.index("col.addView(reqAmountEt, "), build.index(made))
        self.assertLess(build.index(made), build.index(hidden))
        self.assertLess(build.index(hidden), build.index(added))
        self.assertLess(build.index(added), build.index("Button reqBtn = new Button(this);"))

    def test_it_follows_the_typed_amount_and_asks_for_nothing(self):
        build = method_body(code(MAIN_ACTIVITY), "private void buildReceiveTab()")
        self.assertEqual(build.count("addTextChangedListener("), 1)
        self.assertIn("reqAmountEt.addTextChangedListener(new ReqUsdWatcher(this));", build)
        # One keystroke, one repaint, from the quote the gate remembers.
        edited = method_body(code(MAIN_ACTIVITY), "void onReceiveAmountEdited()")
        self.assertTrue(edited, "MainActivity.onReceiveAmountEdited() is missing")
        self.assertEqual("".join(edited.split()), "renderReqUsd(pricePoll.last());")
        after = method_body(code(REQ_WATCHER), "public void afterTextChanged(Editable s)")
        self.assertTrue(after, "ReqUsdWatcher.afterTextChanged is missing")
        self.assertEqual("".join(after.split()), "act.onReceiveAmountEdited();")

    def test_the_watcher_is_top_level(self):
        """A NESTED class that captures its outer instance crashes the dexer
        on this toolchain (d8 8.2.2-dev: NullPointerException while dexing) -
        anonymous or named alike - and this watcher has to call back into
        the activity. Measured on the build's own flags, with sources compiled
        by this toolchain's javac; the two matrices are in DECISIONS.md D20.
        Same rule PromptCb is pinned by."""
        watcher = code(REQ_WATCHER)
        self.assertIn("class ReqUsdWatcher implements TextWatcher", watcher)
        self.assertNotIn("class MainActivity", watcher)
        self.assertEqual(watcher.count("act."), 1)
        activity = code(MAIN_ACTIVITY)
        self.assertNotIn("new TextWatcher(", activity,
                         "the watcher must stay TOP-LEVEL (d8 nested-class rule)")
        self.assertNotIn("implements TextWatcher", activity)

    def test_it_repaints_from_the_balance_quote(self):
        src = code(MAIN_ACTIVITY)
        paint = method_body(src, "private void renderPrice(PriceLine.Quote quote)")
        self.assertTrue(paint)
        self.assertLess(paint.index("priceTv.setText("), paint.index("renderReqUsd(quote);"))
        # One definition, one composer: nothing else builds the figure.
        self.assertEqual(src.count("UsdApprox.format("), 1)
        self.assertEqual(src.count("private void renderReqUsd("), 1)

    def test_the_render_is_hide_or_show_and_never_reads_the_network(self):
        render = method_body(code(MAIN_ACTIVITY),
                             "private void renderReqUsd(PriceLine.Quote quote)")
        self.assertRegex(render, re.compile(
            r"UsdApprox\.format\(\s*MazaUri\.parseAmountText\(\s*"
            r"reqAmountEt\.getText\(\)\.toString\(\)\.trim\(\)\),\s*quote\)"))
        self.assertIn("line == null ? View.GONE : View.VISIBLE", render)
        for forbidden in ("Api.", "readPrice", "new Thread", "pricePoll.due(",
                          "pricePoll.record(", "pricePoll.clear(", "AppLog", "Log."):
            self.assertNotIn(forbidden, render)

    def test_the_payment_uri_carries_no_dollar_value(self):
        # The request is composed from the MAZA amount alone: MazaCore's
        # formatBitcoinURI carries amount, label and message - no fiat.
        request = method_body(code(MAIN_ACTIVITY), "private void onRequestQrTapped()")
        self.assertTrue(request)
        self.assertIn("final Long sats = MazaUri.parseAmountText(text);", request)
        self.assertEqual(request.count("loadQrUri("), 1)
        self.assertIn("loadQrUri(MazaUri.format(addr, sats, null, null));", request)
        self.assertNotIn("UsdApprox", request)
        self.assertNotIn("reqUsdTv", request)
        self.assertNotIn("UsdApprox", code(MAZA_URI))
        self.assertNotIn("UsdApprox", code(SELF_CUSTODY))
        # Exactly two wallet files know the class; the server knows none.
        know = []
        for root, _, names in os.walk(ANDROID_SRC):
            for name in names:
                if name.endswith(".java") and "UsdApprox" in code(os.path.join(root, name)):
                    know.append(name)
        self.assertEqual(sorted(know), ["MainActivity.java", "UsdApprox.java"])
        for root, _, names in os.walk(BENCH):
            for name in names:
                if name.endswith(".py"):
                    self.assertNotIn("UsdApprox", read_text(os.path.join(root, name)),
                                     os.path.join(root, name))

    def test_pure_java_ascii_no_url_no_float_no_log(self):
        for name in PURE_JAVA:
            self.assertTrue(read_text(os.path.join(SRC, name)).isascii(), name)
        self.assertTrue(read_text(REQ_WATCHER).isascii())
        self.assertIsNone(re.search(r"https?://", read_text(REQ_WATCHER)))
        self.assertNotIn("AppLog", code(REQ_WATCHER))
        self.assertTrue(read_text(MAIN_ACTIVITY).isascii())
        src = read_text(USD_APPROX)
        self.assertIsNone(re.search(r"https?://", src))
        imports = re.findall(r"(?m)^import\s+(\S+);", src)
        self.assertTrue(imports and all(i.startswith("java.") for i in imports), imports)
        body = strip_comments(src)
        self.assertIsNone(re.search(
            r"(?:Double\.parseDouble|Float\.parseFloat|new\s+(?:Double|Float)\()", body))
        self.assertNotIn("AppLog", body)
        self.assertIsNone(re.search(r"\bLog\.", body))


if __name__ == "__main__":
    unittest.main()
