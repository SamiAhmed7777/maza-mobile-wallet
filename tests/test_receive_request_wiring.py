#!/usr/bin/env python3
"""Wiring contract for M9-ii: the request-amount RECEIVE screen.

The BEHAVIOR lives where it is executed:
  - the amount math (parse rules, 8dp boundary, signed rejection) is
    driven on the desktop JVM by crypto/SelfTest.java mazaUriChecks()
    (parseAmountText rows + the receive-screen compose row);
  - the backend re-validation is driven through the REAL HTTP endpoint
    by tests/test_walletbench.py TestQrPaymentRequestUri.

This file pins the WIRING SelfTest and the HTTP tests cannot see: the
RECEIVE-tab UI elements, the compose path (typed amount -> MazaUri.format
-> /api/qr.png?uri=<query-encoded payload>), the S-5 retry routing of the
uri form, the backend mirror's contract-fidelity choices ('+' literal,
strict fail-closed decoding, watch-book membership, length cap, both-
params guard), and the docs honesty (no stale "not in the app yet"
claim about the receive screen).
"""
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(REPO, "android", "src", "com", "mazawallet",
                    "MainActivity.java")
MAZA_URI = os.path.join(REPO, "android", "src", "com", "mazawallet",
                        "crypto", "MazaUri.java")
SELFTEST = os.path.join(REPO, "android", "src", "com", "mazawallet",
                        "crypto", "SelfTest.java")
STRINGS = os.path.join(REPO, "android", "res", "values", "strings.xml")
API = os.path.join(REPO, "walletbench", "api.py")
NET = os.path.join(REPO, "android", "src", "com", "mazawallet", "Net.java")
USER_GUIDE = os.path.join(REPO, "docs", "user-guide.md")
DECISIONS = os.path.join(REPO, "DECISIONS.md")
SPEC_AUDIT = os.path.join(REPO, "docs", "SPEC-AUDIT.md")


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class ReceiveScreenWiring(unittest.TestCase):
    """MainActivity: typed amount -> MazaUri -> payment-request QR."""

    def setUp(self):
        self.src = read(MAIN)

    def test_receive_tab_has_request_ui(self):
        self.assertIn("reqAmountEt", self.src)
        self.assertIn("onRequestQrTapped", self.src)
        self.assertIn("R.string.req_amount_hint", self.src)
        self.assertIn("R.string.req_qr_button", self.src)

    def test_compose_through_mazauri_only(self):
        # The typed amount NEVER reaches the QR by ad-hoc string assembly:
        # it is parsed by the shared contract entry and composed by
        # MazaUri.format (the tested formatBitcoinURI port).
        self.assertIn("MazaUri.parseAmountText(text)", self.src)
        self.assertIn("MazaUri.format(addr, sats, null, null)", self.src)

    def test_zero_and_invalid_amount_rejected_before_request(self):
        # "0" can never become a zero-value payment request; parse failures
        # surface the dedicated copy, not a crash or a silent fallback.
        self.assertIn("sats == null || sats <= 0L", self.src)
        self.assertIn("R.string.req_amount_invalid", self.src)

    def test_empty_input_falls_back_to_plain_address_qr(self):
        # The plain-address path stays the default (empty amount field).
        self.assertIn("if (text.length() == 0) {\n            loadQr();",
                      self.src)

    def test_uri_form_query_encodes_the_whole_payload(self):
        # android.net.Uri.encode escapes every reserved char incl.
        # '%' -> '%25', so the payload arrives byte-exactly and the
        # payload's own percent-escapes survive the query round trip.
        self.assertIn('"/api/qr.png?uri=" + android.net.Uri.encode(payload)',
                      self.src)

    def test_shared_fetcher_keeps_s5_retry_routing(self):
        # The uri form rides the SAME loadQrPath worker and Net table row:
        # routeFor strips the query (Net.normalizePath), so GET
        # /api/qr.png?uri=... keeps its 3 read attempts.
        self.assertIn("loadQrPath(\"/api/qr.png\", null)", self.src)
        self.assertIn("Api.Resp r = Net.withRetry(\"GET\", path,",
                      self.src)
        net = read(NET)
        self.assertIn('new Route("GET", "/api/qr.png", 3, false)', net)

    def test_displayed_request_is_only_a_display(self):
        # Nothing is ever sent from RECEIVE: the success status shows the
        # composed URI so the user can read what they hand out.
        self.assertIn("successStatus == null ? \"\" : successStatus",
                      self.src)

    def test_empty_amount_fallback_composes_no_uri_param(self):
        # The empty-input branch must fall back to the PLAIN endpoint
        # (loadQr -> "/api/qr.png", no query): the app mirrors the
        # server's empty-uri 400 by never sending an empty uri at all.
        self.assertIn("if (text.length() == 0) {\n            loadQr();",
                      self.src)
        self.assertIn('loadQrPath("/api/qr.png", null)', self.src)
        # and the only ?uri= composer is loadQrUri, reached with a
        # parsed-and-composed payload (never raw user text).
        uri_composers = [l for l in self.src.splitlines()
                         if "/api/qr.png?uri=" in l]
        self.assertEqual(len(uri_composers), 1)
        self.assertIn("android.net.Uri.encode(payload)", uri_composers[0])

    def test_strings_resources_present(self):
        s = read(STRINGS)
        self.assertIn('name="req_amount_hint"', s)
        self.assertIn('name="req_qr_button"', s)
        self.assertIn('name="req_amount_invalid"', s)


class MazaUriTypedEntry(unittest.TestCase):
    """The public typed-amount entry shares ONE implementation."""

    def setUp(self):
        self.src = read(MAZA_URI)

    def test_public_wrapper_delegates_to_parse_amount(self):
        self.assertIn("public static Long parseAmountText(String text)",
                      self.src)
        self.assertIn("return parseAmount(text);", self.src)

    def test_empty_semantics_documented_for_caller(self):
        # "" -> 0L (NOT null): the screen treats sats <= 0 as invalid.
        self.assertIn("parseAmountText EMPTY -> 0L", read(SELFTEST))


class BackendContractMirror(unittest.TestCase):
    """walletbench re-validates the payload against the same contract."""

    def setUp(self):
        self.src = read(API)

    def test_strict_decode_no_form_encoding(self):
        # urllib.parse.parse_qs/parse_qsl decode '+' as a space; the maza:
        # contract keeps it literal, so the parameter is extracted raw.
        self.assertIn("_query_param_raw", self.src)
        self.assertNotIn("parse_qs(", self.src)
        self.assertNotIn("parse_qsl(", self.src)
        self.assertIn("'+' stays literal", self.src)

    def test_strict_decode_fails_closed(self):
        self.assertIn("return None  # truncated escape", self.src)
        self.assertIn("return None  # malformed escape", self.src)
        self.assertIn("except UnicodeDecodeError:\n            return None",
                      self.src)

    def test_watch_book_membership_enforced(self):
        # Same no-arbitrary-address invariant as ?addr=: the ADDRESS part
        # of the payload must be a watch-book address.
        self.assertIn("path not in watch", self.src)
        self.assertIn("payment request for this wallet", self.src)

    def test_length_cap_and_both_params_guard(self):
        self.assertIn("QR_URI_MAX_CHARS = 512", self.src)
        self.assertIn("use either addr or uri, not both", self.src)

    def test_amount_mirror_digits_only_8dp(self):
        self.assertIn('all("0" <= c <= "9" for c in digits)', self.src)
        self.assertIn("if len(frac) > 8:", self.src)

    def test_both_qr_endpoints_use_the_resolver(self):
        self.assertEqual(self.src.count("_requested_qr_payload"), 3)  # def + 2 calls
        self.assertNotIn("_requested_qr_address", self.src)

    def test_endpoint_docstring_scoped(self):
        self.assertIn("?uri=<maza: payment request>", self.src)


class DocsHonesty(unittest.TestCase):
    """No stale claim that the request screen is missing."""

    def test_user_guide_documents_the_request_qr(self):
        s = read(USER_GUIDE)
        self.assertIn("Show payment QR", s)
        self.assertIn("payment REQUEST", s)
        self.assertIn("nothing is ever sent from this screen", s)

    def test_user_guide_has_no_stale_not_in_app_claim(self):
        s = read(USER_GUIDE)
        self.assertNotIn("receive screen (generating a `maza:` request QR)",
                         s)
        self.assertNotIn("Request-amount\n  receive screen", s)

    def test_decisions_documents_the_backend_mirror(self):
        s = read(DECISIONS)
        self.assertIn("Backend QR-layer mirror", s)
        self.assertIn("invalid UTF-8 byte\nsequence", s)

    def test_spec_audit_rows_updated(self):
        s = read(SPEC_AUDIT)
        self.assertIn("M9-ii request-amount receive screen", s)
        self.assertNotIn("Request-amount receive screen = M9-ii", s)


if __name__ == "__main__":
    unittest.main()
